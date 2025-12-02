# Monitoring & Alerting - Security Review

## Executive Summary

This document reviews the security aspects of the Enhanced Monitoring & Alerting feature.

## Security Analysis

### 1. Authentication & Authorization

**Current Design**:
- Uses Azure CLI auth token for Azure Monitor API access
- Relies on existing `az login` session

**Security Assessment**: ✅ **APPROVED**
- Leverages Azure's built-in authentication
- No custom password storage or authentication
- Follows principle of least privilege (uses existing Azure RBAC)

**Recommendations**:
- Verify token expiry handling
- Ensure graceful degradation when token expires
- Document required Azure permissions (Reader role on VMs)

### 2. Data Storage

**Current Design**:
- SQLite database at `~/.azlin/metrics.db`
- Stores VM metrics (CPU, memory, disk, network)
- No encryption at rest

**Security Assessment**: ⚠️ **APPROVED WITH CONDITIONS**
- Metrics data is operational, not highly sensitive
- Database location in user home directory (appropriate)
- No PII or credentials stored

**Recommendations**:
- Set appropriate file permissions (0600) on metrics.db
- Document that metrics may reveal usage patterns
- Consider adding optional encryption for compliance use cases (future enhancement)

### 3. Alert Configuration

**Current Design**:
- YAML configuration file at `~/.azlin/alert_rules.yaml`
- Contains SMTP credentials, Slack webhook URLs

**Security Assessment**: ❌ **REQUIRES CHANGES**
- **CRITICAL**: Storing SMTP passwords in plain text is unacceptable
- Webhook URLs in config file is acceptable (not secrets)

**Required Changes**:
1. **Never store SMTP passwords in config files**
2. Use Azure Key Vault or system keyring for secrets:
   ```python
   from keyring import get_password, set_password

   # Store: set_password("azlin_monitoring", "smtp_password", password)
   # Retrieve: get_password("azlin_monitoring", "smtp_password")
   ```
3. Prompt for SMTP password on first alert setup
4. Document in alert_rules.yaml that password must be set via CLI:
   ```yaml
   notification_config:
     email:
       enabled: true
       smtp_host: smtp.gmail.com
       smtp_port: 587
       from_address: alerts@example.com
       # Password stored securely in system keyring
       # Set with: azlin monitor alert config-email
   ```

### 4. Notification Dispatch

**Current Design**:
- Email via SMTP with TLS
- Slack via webhook POST
- Generic webhook via POST with JSON payload

**Security Assessment**: ⚠️ **APPROVED WITH CONDITIONS**
- SMTP with TLS: Good ✅
- Slack webhook: Acceptable (webhook URL acts as auth) ✅
- Generic webhook: No authentication specified ❌

**Recommendations**:
1. **Email**: Verify TLS is enforced (not opportunistic)
2. **Slack**: Document that webhook URL should be treated as secret
3. **Generic Webhook**: Add optional authentication:
   ```yaml
   webhook:
     enabled: false
     url: https://example.com/alerts
     auth_type: bearer  # none, bearer, basic
     auth_token: ${WEBHOOK_TOKEN}  # From environment variable
   ```
4. **Alert Content**: Sanitize error messages in alerts to prevent information disclosure

### 5. Azure Monitor API Access

**Current Design**:
- REST API calls to `https://management.azure.com`
- Uses Azure CLI auth token
- Parallel collection from multiple VMs

**Security Assessment**: ✅ **APPROVED**
- HTTPS enforced for all API calls
- Uses Azure's OAuth2 token authentication
- Rate limiting considerations documented

**Recommendations**:
- Implement request timeout (30s) to prevent hung connections
- Log API errors without exposing sensitive details
- Validate API response structure before processing

### 6. Input Validation

**Current Design**:
- VM names from Azure CLI output
- User input for alert rules, thresholds, CLI arguments

**Security Assessment**: ⚠️ **REQUIRES ATTENTION**
- VM names from Azure API: Trusted source ✅
- User input for alert rules: **MUST VALIDATE**

**Required Validation**:
```python
# Alert rule validation
def validate_alert_rule(rule: AlertRule) -> None:
    # Metric name: alphanumeric and underscore only
    if not re.match(r'^[a-zA-Z0-9_]+$', rule.metric):
        raise ValueError("Invalid metric name")

    # Threshold: must be numeric and reasonable
    if not 0 <= rule.threshold <= 100:
        raise ValueError("Threshold must be 0-100")

    # Comparison operator: whitelist only
    if rule.comparison not in ['>', '<', '>=', '<=', '==']:
        raise ValueError("Invalid comparison operator")

# VM name validation (from user input)
def validate_vm_name(vm_name: str) -> None:
    # Alphanumeric, hyphens, underscores only
    if not re.match(r'^[a-zA-Z0-9_-]+$', vm_name):
        raise ValueError("Invalid VM name format")
    if len(vm_name) > 64:
        raise ValueError("VM name too long")
```

### 7. SQL Injection

**Current Design**:
- SQLite queries with user-provided VM names, time ranges

**Security Assessment**: ❌ **REQUIRES CHANGES**
- **CRITICAL**: Must use parameterized queries for all user input

**Required Changes**:
```python
# WRONG - SQL injection vulnerability
def query_metrics(self, vm_name: str, start_time: datetime):
    query = f"SELECT * FROM metrics WHERE vm_name = '{vm_name}'"
    self.cursor.execute(query)

# RIGHT - Parameterized query
def query_metrics(self, vm_name: str, start_time: datetime):
    query = "SELECT * FROM metrics WHERE vm_name = ? AND timestamp >= ?"
    self.cursor.execute(query, (vm_name, start_time))
```

**Verify ALL SQL queries use parameterization**:
- store_metric()
- store_metrics()
- query_metrics()
- aggregate_hourly()
- cleanup_old_data()

### 8. Error Message Sanitization

**Current Design**:
- Error messages displayed in dashboard and alerts

**Security Assessment**: ⚠️ **REQUIRES ATTENTION**
- Must not expose internal paths, IP addresses, or sensitive details

**Required Sanitization**:
```python
def sanitize_error_message(message: str) -> str:
    """Sanitize error messages to prevent information disclosure."""
    if not message:
        return "Unknown error"

    # Remove file paths
    sanitized = re.sub(r'/[a-zA-Z0-9/_.-]+', '[path]', message)
    sanitized = re.sub(r'[A-Z]:\\[a-zA-Z0-9\\._-]+', '[path]', sanitized)

    # Mask internal IP addresses
    sanitized = re.sub(r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '10.x.x.x', sanitized)
    sanitized = re.sub(
        r'\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b',
        '172.x.x.x',
        sanitized
    )
    sanitized = re.sub(r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '192.168.x.x', sanitized)

    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + "..."

    return sanitized
```

### 9. Rate Limiting

**Current Design**:
- Configurable refresh interval (1-5 minutes)
- Parallel collection from multiple VMs

**Security Assessment**: ✅ **APPROVED**
- Minimum 1-minute interval prevents Azure API abuse
- Parallel collection bounded by max_workers

**Recommendations**:
- Document Azure Monitor API rate limits
- Implement exponential backoff on 429 (Too Many Requests) responses
- Log rate limit violations

### 10. Logging & Auditing

**Current Design**:
- Not specified in architecture spec

**Security Assessment**: ⚠️ **REQUIRES ADDITION**
- Must log security-relevant events
- Must NOT log sensitive data

**Required Logging**:
```python
# Log security events
logger.info("Alert notification sent", extra={
    "alert_name": alert.rule_name,
    "severity": alert.severity,
    "vm_name": alert.vm_name,
    "channel": "email",  # Don't log email addresses or webhook URLs
})

# NEVER log sensitive data
# ❌ logger.debug(f"SMTP password: {password}")
# ❌ logger.debug(f"API token: {token}")
# ❌ logger.debug(f"Webhook URL: {webhook_url}")
```

## Security Requirements Summary

### CRITICAL (Must Fix Before Merge)
1. ✅ Use parameterized SQL queries for all database operations
2. ✅ Store SMTP credentials in system keyring, not config files
3. ✅ Validate all user input (alert rules, VM names, thresholds)
4. ✅ Sanitize error messages before display/logging

### HIGH (Should Fix Before Merge)
1. ⚠️ Add webhook authentication support
2. ⚠️ Implement request timeouts for Azure API calls
3. ⚠️ Set appropriate file permissions on database and config files

### MEDIUM (Can Address in Follow-up)
1. 📝 Add optional encryption for metrics database
2. 📝 Implement detailed security audit logging
3. 📝 Add rate limit monitoring and alerting

### LOW (Future Enhancement)
1. 💡 Multi-factor authentication for high-severity alerts
2. 💡 Integration with Azure Security Center

## Testing Requirements

### Security Test Cases
1. **SQL Injection**: Test with malicious VM names (`'; DROP TABLE metrics; --`)
2. **Path Traversal**: Test with relative paths in config (`../../etc/passwd`)
3. **Command Injection**: Test with shell metacharacters in inputs
4. **Error Information Disclosure**: Verify error messages don't expose internals
5. **Authentication Token Expiry**: Test behavior when Azure token expires
6. **Rate Limiting**: Test with excessive API requests
7. **File Permissions**: Verify database and config files have appropriate permissions

## Compliance Considerations

### GDPR/Privacy
- ✅ Metrics data is operational, not PII
- ✅ No user tracking or profiling
- ⚠️ Document data retention policies (90 days)

### SOC 2
- ⚠️ Need audit logging for compliance
- ⚠️ Need documented access controls
- ✅ Encryption in transit (HTTPS, SMTP TLS)

## Approval Status

**Overall Status**: ⚠️ **CONDITIONAL APPROVAL**

**Conditions for Merge**:
1. Implement parameterized SQL queries
2. Move SMTP credentials to system keyring
3. Add input validation for all user inputs
4. Implement error message sanitization

**Security Review**: Once critical items are addressed, this feature will meet security standards.

**Reviewer**: Security Agent
**Date**: 2025-12-01
