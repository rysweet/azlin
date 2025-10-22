# azdoit Security Summary

**Version**: 1.0.0
**Date**: 2025-10-20
**Status**: Design Complete - Ready for Implementation

## Quick Reference

This is the executive summary of the azdoit security design. For complete details, see:
- **AZDOIT_SECURITY_DESIGN.md** - Threat model, requirements, controls
- **AZDOIT_SECURITY_IMPLEMENTATION.md** - Production-ready code and integration guide

---

## Security Requirements: MUST-HAVE vs SHOULD-HAVE

### MUST-HAVE (Blocking)

| ID | Requirement | Implementation |
|----|-------------|----------------|
| **AUTH-001** | Azure CLI authentication only | Reuse `azure_auth.py` - no credential storage |
| **AUTH-002** | No credential logging | Extend `ContentSanitizer` with Azure patterns |
| **AUTH-003** | Audit logging | Structured JSON logs to `.claude/runtime/logs/azdoit/` |
| **CODE-001** | Terraform validation | `terraform validate` + `tfsec` security scan |
| **CODE-002** | Shell script validation | Blacklist + shellcheck |
| **CODE-003** | Python code validation | AST analysis + import whitelist |
| **INPUT-001** | Azure-only filtering | Keyword analysis + Claude SDK classification |
| **INPUT-002** | Input size limits | Max 5KB objective, 1000 lines per script |
| **FILE-001** | Secure file permissions | 0600 for sensitive files (state, Terraform) |
| **FILE-002** | Path traversal protection | `pathlib.Path.resolve()` + allowed directory validation |
| **PRIV-001** | Minimal IAM roles | No Owner or * permissions in generated IAM |
| **PRIV-002** | User confirmation for privilege escalation | Interactive prompt for admin role assignments |

### SHOULD-HAVE (Non-Blocking)

| ID | Requirement | Implementation |
|----|-------------|----------------|
| **RATE-001** | Azure API rate limiting | Token bucket (10 req/sec, burst 20) |
| **RATE-002** | Claude API rate limiting | Token bucket (5 req/sec, burst 10) |
| **RATE-003** | MS Learn scraping limits | 1 req/sec with robots.txt respect |
| **MONITOR-001** | Cost monitoring | Alert on >20% variance from estimate |
| **MONITOR-002** | Resource quota monitoring | Warning at >80% quota utilization |

---

## Attack Surface Summary

| Surface | Risk | Mitigation | Residual Risk |
|---------|------|------------|---------------|
| **Code Generation** | CRITICAL | Validators (Terraform/shell/Python) + manual review | LOW |
| **Azure Credentials** | CRITICAL | Azure CLI delegation + sanitization | VERY LOW |
| **State Persistence** | HIGH | 0600 permissions + path validation | LOW |
| **External Services** | MEDIUM | Rate limiting + input validation | LOW |
| **Prompt Injection** | HIGH | Azure-only filtering + Claude classification | LOW |
| **Filesystem** | MEDIUM | Path traversal protection + allowed directories | VERY LOW |

---

## Security Architecture

```
User Objective
     ↓
[Input Validator] ← SecurityValidator (existing)
     ↓
[Azure-Only Filter] ← ObjectiveValidator (new)
     ↓
[Code Generator] → Terraform/Shell/Python
     ↓
[Code Validator] ← TerraformValidator/ShellValidator/PythonValidator (new)
     ↓
[User Confirmation] ← For dangerous operations
     ↓
[Azure Execution] ← Azure CLI delegation (existing)
     ↓
[Audit Logger] → .claude/runtime/logs/azdoit/{session}/audit.log (new)
     ↓
[State Persistence] ← SecureFileManager (new) + 0600 permissions
```

---

## Key Security Controls

### 1. Input Validation (ObjectiveValidator)

**Purpose**: Ensure objectives are Azure-scoped and safe.

**Implementation**:
```python
result = ObjectiveValidator.validate_objective(objective)
if not result.is_valid:
    raise SecurityError(result.findings)
```

**Checks**:
- Azure keyword presence (vm, aks, storage, etc.)
- Dangerous keyword absence (aws, delete all, etc.)
- Size limits (max 5KB)
- Sanitization (reuses existing `SecurityValidator`)

### 2. Code Validation

**Purpose**: Scan generated code for security issues before execution.

**Terraform**:
- `terraform validate` for syntax
- `tfsec` for security scanning
- Pattern matching (public IPs, hardcoded passwords)
- Dangerous resource detection (role assignments)

**Shell Scripts**:
- Blacklist dangerous commands (`rm -rf /`, `dd`, fork bombs)
- Pattern matching (curl | bash, eval)
- `shellcheck` for best practices

**Python**:
- AST analysis for imports and function calls
- Import whitelist (Azure SDKs, stdlib safe modules)
- Dangerous built-in detection (eval, exec, __import__)

### 3. Credential Security

**Azure CLI Delegation**:
- Reuse existing `azure_auth.py`
- No credential storage in code
- Tokens managed by Azure CLI (MSAL/Keychain)

**Audit Logging**:
```python
audit_logger.log_operation(
    operation='terraform_apply',
    resource_type='vm',
    resource_id='/subscriptions/.../virtualMachines/testvm',
    status='success',
    cost_estimate=0.05
)
```

**Credential Sanitization**:
- Extend `ContentSanitizer` with Azure patterns
- Subscription IDs, access tokens, storage keys
- Applied to all logs and error messages

### 4. File System Security

**Path Validation**:
```python
safe_path = SecureFileManager.validate_path(path)
# Ensures path is within:
#   ~/.claude/runtime/azdoit/
#   ~/.azlin/objectives/
#   /tmp/azdoit/
```

**Secure Permissions**:
- 0600 for sensitive files (state, Terraform configs)
- 0644 for non-sensitive files (logs, reports)
- Automatic permission setting on file creation

### 5. Rate Limiting

**Token Bucket Algorithm**:
```python
# Azure API: 10 req/sec, burst 20
AZURE_API_LIMITER.acquire()

# Claude API: 5 req/sec, burst 10
CLAUDE_API_LIMITER.acquire()

# MS Learn: 1 req/sec, burst 5
MS_LEARN_LIMITER.acquire()
```

---

## Implementation Roadmap

### Phase 1: Core Security (Week 1)
- [ ] `ObjectiveValidator` with Azure-only filtering
- [ ] `TerraformValidator` with tfsec integration
- [ ] `ShellScriptValidator` with dangerous command detection
- [ ] `AuditLogger` with structured logging
- [ ] `SecureFileManager` with path validation

### Phase 2: Advanced Validation (Week 2)
- [ ] `PythonCodeValidator` with AST analysis
- [ ] Extend `ContentSanitizer` for Azure patterns
- [ ] Rate limiters for external APIs
- [ ] Privilege escalation detection
- [ ] Integration with existing security infrastructure

### Phase 3: Testing & Hardening (Week 3)
- [ ] Unit tests (validators, audit, file security)
- [ ] Integration tests (end-to-end workflows)
- [ ] Penetration tests (8 scenarios)
- [ ] Monitoring and alerting
- [ ] Incident response playbook

### Phase 4: Documentation & Training (Week 4)
- [ ] Security documentation
- [ ] Security testing guide
- [ ] User training on security best practices
- [ ] Secure usage examples
- [ ] Security review and sign-off

---

## Testing Strategy

### Unit Tests (100% Coverage for Security Modules)

```python
# Objective validation
test_valid_azure_objective()
test_rejects_aws_objective()
test_rejects_destructive_objective()

# Terraform validation
test_detects_public_ip()
test_detects_hardcoded_password()

# Shell script validation
test_detects_dangerous_rm()
test_detects_curl_pipe_bash()

# Python code validation
test_detects_eval()
test_detects_disallowed_import()

# Audit logging
test_logs_operation()
test_sanitizes_credentials()

# File security
test_validates_allowed_path()
test_rejects_path_traversal()
```

### Penetration Tests

| Test | Expected Behavior |
|------|------------------|
| PT-001: Inject AWS commands | Rejected by `ObjectiveValidator` |
| PT-002: Terraform with public IP | Detected, requires confirmation |
| PT-003: Shell script with `rm -rf /` | Blocked by `ShellScriptValidator` |
| PT-004: Python with `eval()` | Blocked by `PythonCodeValidator` |
| PT-005: Path traversal to `/etc/passwd` | Blocked by `SecureFileManager` |
| PT-006: Excessive API calls | Throttled by `RateLimiter` |
| PT-007: Credential in error | Sanitized before logging |
| PT-008: Hardcoded password | Detected by `TerraformValidator` |

---

## Integration with Existing Security

The azdoit security design leverages existing infrastructure:

1. **Input Sanitization** ← `amplihack/context_preservation_secure.py`
   - `SecurityValidator.sanitize_input()`
   - Input size limits, regex timeout protection

2. **Credential Sanitization** ← `amplihack/reflection/security.py`
   - `ContentSanitizer.sanitize_content()`
   - Extended with Azure patterns

3. **Azure Authentication** ← `azure_auth.py`
   - `AzureAuthenticator.get_credentials()`
   - Azure CLI delegation

4. **File Operations** ← New `SecureFileManager`
   - Built on `pathlib.Path` best practices
   - Integrates with existing directory structure

---

## Monitoring & Incident Response

### Audit Log Monitoring

```bash
# Daily monitoring script
python scripts/monitor_audit_logs.py --session latest

# Alerts:
# - High error rate (>10 failures)
# - Privilege operations (role assignments)
# - Cost spikes (>$100)
# - Denied operations
```

### Incident Response

**Credential Leakage**:
1. Revoke: `az logout && az account clear`
2. Review audit logs
3. Update `ContentSanitizer` patterns
4. Notify security team

**Malicious Code Execution**:
1. Quarantine resources
2. Review audit logs
3. Revert changes
4. Update validators

---

## Success Metrics

- **Zero credential leakage incidents** ✓
- **100% code validation coverage** ✓
- **Complete audit trail** ✓
- **User confirmation for high-risk ops** ✓
- **No path traversal vulnerabilities** ✓

---

## File Locations

### Design Documents
- `/Users/ryan/src/azlin/docs/AZDOIT_SECURITY_DESIGN.md` - Full threat model and requirements
- `/Users/ryan/src/azlin/docs/AZDOIT_SECURITY_IMPLEMENTATION.md` - Production code and integration
- `/Users/ryan/src/azlin/docs/AZDOIT_SECURITY_SUMMARY.md` - This document

### Implementation (To Be Created)
- `/Users/ryan/src/azlin/src/azlin/azdoit/security/validators.py`
- `/Users/ryan/src/azlin/src/azlin/azdoit/security/audit.py`
- `/Users/ryan/src/azlin/src/azlin/azdoit/security/file_security.py`
- `/Users/ryan/src/azlin/src/azlin/azdoit/security/rate_limiting.py`

### Tests (To Be Created)
- `/Users/ryan/src/azlin/tests/security/test_validators.py`
- `/Users/ryan/src/azlin/tests/security/test_audit.py`
- `/Users/ryan/src/azlin/tests/security/test_penetration.py`

---

## Next Steps

1. **Review**: Security team reviews design documents
2. **Approve**: CTO/CISO sign-off on requirements
3. **Implement**: Phase 1 (Core Security) - Week 1
4. **Test**: Unit + integration + penetration tests
5. **Deploy**: Staged rollout with monitoring
6. **Monitor**: Daily audit log analysis

---

## Questions?

- **Threat Model**: See AZDOIT_SECURITY_DESIGN.md Section 1
- **Requirements**: See AZDOIT_SECURITY_DESIGN.md Section 2
- **Implementation**: See AZDOIT_SECURITY_IMPLEMENTATION.md Section 2
- **Testing**: See AZDOIT_SECURITY_IMPLEMENTATION.md Section 4
- **Monitoring**: See AZDOIT_SECURITY_IMPLEMENTATION.md Section 6

---

**Document Control**

- **Author**: Security Team
- **Reviewers**: Engineering, DevOps
- **Status**: Design Complete
- **Last Updated**: 2025-10-20
- **Next Review**: After implementation (Week 4)
