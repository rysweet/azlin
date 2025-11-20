# Azure Key Vault SSH Security Review - Executive Summary

**Date:** 2025-11-18
**Reviewer:** Security Agent
**Status:** APPROVED WITH CONDITIONS

---

## Quick Answers to Your Questions

### 1. What are the minimum required Azure permissions?

**For azlin CLI users (read-only access):**
```bash
az role assignment create \
  --assignee <user-or-sp-id> \
  --role "Key Vault Secrets User" \
  --scope "<vault-resource-id>"
```

**For automation/rotation (read-write):**
```bash
az role assignment create \
  --assignee <automation-sp-id> \
  --role "Key Vault Secrets Officer" \
  --scope "<vault-resource-id>"
```

**NEVER use these roles:**
- Owner
- Contributor
- Key Vault Administrator (except infrastructure admins)

**Additional VM permissions needed:**
- `Microsoft.Compute/virtualMachines/read` - List VMs
- `Microsoft.Compute/virtualMachines/write` - Update SSH keys

### 2. How to prevent key leakage in logs/errors?

**Critical Rules:**

```python
# ✓ CORRECT: Never log private key content
logger.info(f"Retrieved SSH key from vault: {vault_url}")
logger.info(f"Secret name: {secret_name}")
# DO NOT LOG: secret.value, private_key_content

# ✓ CORRECT: Sanitize exceptions
try:
    secret = client.get_secret(secret_name)
except Exception as e:
    logger.error(f"Key retrieval failed: {type(e).__name__}")  # Type only
    raise KeyVaultError("Failed to retrieve SSH key") from e  # Generic message

# ✗ WRONG: Exposing secrets
logger.debug(f"Private key: {private_key_content}")  # NEVER DO THIS
print(f"Key: {secret.value}")  # NEVER DO THIS
raise Exception(f"Failed: {key_content}")  # NEVER DO THIS
```

**Integration with existing sanitizer:**
```python
# Update azure_command_sanitizer.py
SENSITIVE_PARAMS.add("--vault-url")
SENSITIVE_PARAMS.add("--secret-name")
SENSITIVE_PARAMS.add("--secret-value")

SECRET_VALUE_PATTERNS["ssh_private_key"] = re.compile(
    r"(-----BEGIN [A-Z0-9 ]+PRIVATE KEY-----[\\s\\S]+?-----END [A-Z0-9 ]+PRIVATE KEY-----)"
)
```

### 3. What's the secure key naming strategy?

**Pattern:**
```
azlin-{vm-name}-ssh-private-v{version}
```

**Examples:**
```
azlin-dev-vm-123-ssh-private-v1
azlin-prod-api-server-ssh-private-v1
azlin-staging-worker-01-ssh-private-v1
```

**Implementation:**
```python
def generate_secret_name(vm_name: str) -> str:
    """Generate Key Vault secret name with validation."""
    # Sanitize VM name (alphanumeric and hyphens only)
    safe_vm_name = re.sub(r'[^a-zA-Z0-9-]', '', vm_name)

    if len(safe_vm_name) == 0 or safe_vm_name != vm_name:
        raise ValueError(f"Invalid VM name: {vm_name}")

    secret_name = f"azlin-{safe_vm_name}-ssh-private-v1"

    if len(secret_name) > 127:  # Key Vault limit
        raise ValueError("Secret name too long")

    return secret_name
```

**Anti-patterns (DO NOT USE):**
```
vm-123-key                    # Not namespaced
ssh_key_prod                  # No version
azlin/prod/vm/key             # Slashes not allowed
user-input-{vm_name}          # Injection risk
```

### 4. How to handle permission errors gracefully?

**Pre-flight validation:**
```python
def validate_keyvault_access(vault_url: str) -> bool:
    """Verify current identity has Key Vault access."""
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        # Test with harmless operation
        properties = client.list_properties_of_secrets()
        next(properties, None)

        return True

    except ClientAuthenticationError:
        logger.error("Authentication failed for Key Vault")
        return False
    except HttpResponseError as e:
        if e.status_code == 403:
            logger.error("Insufficient Key Vault permissions")
            # Provide actionable guidance
            print("Required role: Key Vault Secrets User")
            print("Run: az role assignment create --assignee <id> --role 'Key Vault Secrets User' --scope <vault-id>")
            return False
        raise
```

**User-friendly error messages:**
```python
class PermissionHandler:
    def handle_permission_error(self, error: HttpResponseError) -> None:
        """Provide actionable error messages for permission issues."""
        if error.status_code == 403:
            print("Error: Insufficient permissions to access Key Vault")
            print()
            print("Required permission: Key Vault Secrets User")
            print()
            print("To grant access, ask your Azure administrator to run:")
            print(f"  az role assignment create \\")
            print(f"    --assignee <your-principal-id> \\")
            print(f"    --role 'Key Vault Secrets User' \\")
            print(f"    --scope '<key-vault-resource-id>'")
            print()
            print("Or use 'azlin auth test --profile <profile>' to diagnose issues")
```

### 5. Should we encrypt keys before storing (double encryption)?

**Answer: NO** (unless regulatory compliance mandates it)

**Rationale:**
- Azure Key Vault already provides HSM-backed AES-256 encryption
- Double encryption adds significant complexity
- Marginal security benefit for SSH keys (ephemeral usage)
- Increases attack surface (encryption key management burden)
- Complicates key rotation procedures

**When to use double encryption:**
- Regulatory compliance explicitly requires it (ITAR, FedRAMP High, PCI DSS Level 1)
- You have existing key management infrastructure
- You can handle encryption key rotation complexity
- Defense-in-depth is mandated by security policy

**If required:**
```python
from cryptography.fernet import Fernet

class DoubleEncryptedKeyVault:
    """ONLY USE IF REQUIRED BY COMPLIANCE."""

    def __init__(self, vault_url: str, encryption_key: bytes):
        self.vault_url = vault_url
        self.cipher = Fernet(encryption_key)

    def store_encrypted_key(self, secret_name: str, private_key: str):
        # Encrypt before storing in vault
        encrypted = self.cipher.encrypt(private_key.encode())
        # Store in Key Vault (already encrypted at rest by Azure)

    def retrieve_encrypted_key(self, secret_name: str) -> str:
        # Retrieve from vault, then decrypt
        encrypted = self.client.get_secret(secret_name).value
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()
```

### 6. What are the security implications of caching keys locally?

**Security Tradeoffs:**

| Aspect | Benefit | Risk |
|--------|---------|------|
| Performance | Reduced Key Vault API calls | Stale keys after rotation |
| Cost | Lower Azure costs | Increased local attack surface |
| Offline access | Works without network | Permission drift |
| Latency | Faster SSH connections | Orphaned keys after VM deletion |

**Recommendation: LIMITED CACHING with strict controls**

**Implementation:**
```python
class SSHKeyCacheManager:
    CACHE_DIR = Path.home() / ".azlin" / "ssh_cache"
    CACHE_MAX_AGE = timedelta(hours=1)  # SHORT TTL

    def __init__(self):
        # Create cache dir with restricted permissions
        self.CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Register cleanup on exit
        atexit.register(self.purge_all_caches)

    def get_cached_key(self, vault_url: str, secret_name: str) -> Path | None:
        """Get cached key if valid (check age and permissions)."""
        cache_path = self._cache_path(vault_url, secret_name)

        if not cache_path.exists():
            return None

        # Verify file permissions (must be 0600)
        stat = cache_path.stat()
        if stat.st_mode & 0o077:
            logger.warning("Cache has insecure permissions, deleting")
            cache_path.unlink()
            return None

        # Check age
        age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
        if age > self.CACHE_MAX_AGE:
            return None

        return cache_path

    def cache_key(self, vault_url: str, secret_name: str, key_content: str) -> Path:
        """Cache key with secure permissions."""
        cache_path = self._cache_path(vault_url, secret_name)
        cache_path.touch(mode=0o600)  # Secure permissions FIRST
        cache_path.write_text(key_content)
        return cache_path

    def purge_all_caches(self):
        """Securely delete all cached keys on exit."""
        for cache_file in self.CACHE_DIR.glob("key_*"):
            # Overwrite before delete
            cache_file.write_bytes(os.urandom(cache_file.stat().st_size))
            cache_file.unlink()
```

**Cache Configuration:**
```toml
# ~/.azlin/config.toml
[keyvault]
cache_enabled = true
cache_ttl_hours = 1          # SHORT TTL (1 hour maximum)
cache_max_size_mb = 10       # Limit cache size
purge_cache_on_exit = true   # Clean up on exit
```

---

## Critical Security Requirements

### MUST IMPLEMENT (Blocking for approval)

1. **No Key Logging:** Private keys NEVER appear in logs/errors/stdout
2. **RBAC Enforcement:** Use "Key Vault Secrets User" role (not Contributor)
3. **Audit Logging:** Enable Key Vault diagnostic logs
4. **Permission Validation:** Check service principal access before operations
5. **File Permissions:** Cached keys must be 0600
6. **Secure Deletion:** Overwrite keys before unlinking files
7. **Error Sanitization:** Generic user-facing messages only

### SHOULD IMPLEMENT (Recommended)

8. Certificate-based service principal authentication
9. Key Vault firewall with IP whitelisting
10. Automated key rotation (90-day cycle)
11. Cache TTL ≤ 1 hour
12. Cache purge on exit
13. Anomaly detection alerts
14. Azure Private Link for production

---

## Threat Model Summary

### Top Threats & Mitigations

**1. Compromised Service Principal**
- **Impact:** Unauthorized Key Vault access, SSH key theft
- **Mitigation:**
  - Rotate secrets every 90 days
  - Use certificate-based auth
  - Monitor for anomalous access patterns
  - Enable rate limiting

**2. Key Leakage in Logs**
- **Impact:** Private key exposure, VM compromise
- **Mitigation:**
  - Never log `secret.value` or `private_key_content`
  - Sanitize all exceptions
  - Use generic error messages
  - Review logs before production

**3. Excessive RBAC Permissions**
- **Impact:** Unauthorized secret deletion, policy modification
- **Mitigation:**
  - Grant "Key Vault Secrets User" (not Contributor)
  - Audit role assignments regularly
  - Implement Azure Policy guardrails

**4. Cached Key Compromise**
- **Impact:** VM access via stolen cache file
- **Mitigation:**
  - Short TTL (1 hour maximum)
  - Verify permissions on every access
  - Purge cache on exit
  - Overwrite before delete

**5. MITM Attack on Key Retrieval**
- **Impact:** Interception of private key in transit
- **Mitigation:**
  - Enforce TLS 1.2+ for Azure SDK
  - Validate server certificates
  - Consider certificate pinning

---

## Permission Matrix

| Identity | Role | Get Secret | Set Secret | Delete Secret | Rotate Keys |
|----------|------|------------|------------|---------------|-------------|
| azlin CLI User | Key Vault Secrets User | ✓ | ✗ | ✗ | ✗ |
| Rotation Service | Key Vault Secrets Officer | ✓ | ✓ | ✓ | ✓ |
| Infrastructure Admin | Key Vault Administrator | ✓ | ✓ | ✓ | ✓ |

---

## Testing Checklist

Security test requirements before production:

- [ ] Private key never appears in logs (test with `caplog`)
- [ ] File permissions enforced (0600 for cached keys)
- [ ] Vault URL validation prevents injection
- [ ] Secret name sanitization prevents traversal
- [ ] Error messages don't leak sensitive info
- [ ] Cache purge on exit deletes all keys
- [ ] RBAC permission check validates access
- [ ] Failed auth attempts don't expose details
- [ ] TLS version enforcement (reject < 1.2)
- [ ] Rate limiting prevents brute force
- [ ] Audit logs capture all operations

---

## Monitoring & Alerting

**Azure Monitor Queries:**

```kusto
// Failed Key Vault access attempts
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where ResultType == "Unauthorized"
| summarize FailedAttempts=count() by CallerIPAddress, identity_claim_appid_g
| where FailedAttempts > 5

// SSH key retrievals
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where OperationName == "SecretGet"
| where id_s contains "azlin-" and id_s contains "-ssh-private"
| order by TimeGenerated desc
```

**Alert Rules:**
- Failed authentication > 10 attempts in 5 minutes
- Bulk key retrieval > 50 requests in 15 minutes
- Access from new country/region
- Secret deletion events

---

## Decision

**APPROVED** with conditions:
1. All MUST IMPLEMENT requirements completed
2. Security test suite passes 100%
3. Penetration testing validates controls
4. Incident response playbook documented

**Risk Level:** MEDIUM (after controls implemented)
**Next Review:** 2026-02-18 (90 days)

---

## Quick Reference

**Store SSH key in vault:**
```python
from azlin.modules.ssh_keyvault import SSHKeyVaultManager

manager = SSHKeyVaultManager(vault_url="https://azlin-ssh.vault.azure.net")
manager.store_key_in_vault(
    secret_name="azlin-prod-vm-ssh-private-v1",
    private_key_content=key_content
)
```

**Retrieve SSH key:**
```python
key_path = manager.retrieve_key_from_vault(
    secret_name="azlin-prod-vm-ssh-private-v1",
    destination_path=Path.home() / ".ssh" / "azlin_key"
)
# File created with 0600 permissions
```

**Validate access:**
```python
if not manager.validate_keyvault_access():
    print("Error: Insufficient Key Vault permissions")
    print("Required role: Key Vault Secrets User")
    sys.exit(1)
```

---

**Full Review:** See [KEYVAULT_SSH_SECURITY_REVIEW.md](./KEYVAULT_SSH_SECURITY_REVIEW.md)
