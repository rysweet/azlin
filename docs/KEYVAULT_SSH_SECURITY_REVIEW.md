# Azure Key Vault SSH Key Storage - Security Review

**Version:** 1.0
**Date:** 2025-11-18
**Status:** Security Design Review
**Reviewer:** Security Agent

---

## Executive Summary

This document provides a comprehensive security review for implementing Azure Key Vault storage of SSH private keys for multi-host VM access in azlin. The feature enables centralized SSH key management with the following security properties:

**Security Posture:** HIGH RISK if not implemented correctly
**Recommendation:** APPROVE with mandatory security controls
**Risk Level:** MEDIUM (after controls implemented)

---

## Table of Contents

1. [Feature Overview](#feature-overview)
2. [Threat Model](#threat-model)
3. [Security Requirements](#security-requirements)
4. [Azure Permissions](#azure-permissions)
5. [Implementation Guidelines](#implementation-guidelines)
6. [Security Controls](#security-controls)
7. [Attack Scenarios & Mitigations](#attack-scenarios--mitigations)
8. [Monitoring & Audit](#monitoring--audit)
9. [Testing Requirements](#testing-requirements)
10. [Operational Procedures](#operational-procedures)

---

## Feature Overview

### Purpose

Store SSH private keys in Azure Key Vault to enable:
- Multi-host VM access with same key pair
- Team sharing of SSH access credentials
- Centralized key rotation and lifecycle management
- Secure key distribution without file transfer
- Service principal-based automated access

### Current State

```python
# Current implementation in ssh_keys.py
class SSHKeyManager:
    DEFAULT_KEY_PATH = Path.home() / ".ssh" / "azlin_key"

    # Keys stored locally at ~/.ssh/azlin_key
    # Private key permissions: 0600
    # Public key permissions: 0644
```

**Security characteristics:**
- Keys stored on local filesystem
- Standard Unix file permissions
- Single-user access model
- No central management
- Manual key distribution

### Proposed Enhancement

```python
# Proposed enhancement
class SSHKeyVaultManager:
    """Manage SSH keys in Azure Key Vault."""

    def store_key_in_vault(
        self,
        vault_url: str,
        key_name: str,
        private_key_content: str
    ) -> None:
        """Store private key as Key Vault secret."""

    def retrieve_key_from_vault(
        self,
        vault_url: str,
        key_name: str,
        destination_path: Path
    ) -> Path:
        """Retrieve private key and write to secure local file."""
```

**Benefits:**
- Centralized key management
- Azure RBAC for access control
- Audit logging built-in
- Automatic key rotation support
- Multi-user/multi-VM access
- Service principal automation

**Risks:**
- Network exposure of private keys
- Misconfigured RBAC leading to unauthorized access
- Key leakage through logs/errors
- Credential stuffing if service principal compromised
- Cached keys on local filesystem

---

## Threat Model

### Assets

1. **SSH Private Keys** (CRITICAL)
   - Value: Complete VM access control
   - Exposure impact: Full system compromise
   - Confidentiality requirement: MAXIMUM

2. **Azure Key Vault Access Credentials** (HIGH)
   - Service principal client secrets
   - Managed identity tokens
   - Azure CLI credentials

3. **VM Access Tokens** (HIGH)
   - SSH sessions
   - Sudo privileges
   - Data access

### Threat Actors

#### External Attackers
- **Skill Level:** Medium to Advanced
- **Motivation:** Data theft, ransomware, cryptomining
- **Attack Vectors:**
  - Compromised dependencies (supply chain)
  - Network interception (MITM)
  - Credential phishing
  - Cloud misconfigurations

#### Malicious Insiders
- **Skill Level:** Advanced (Azure knowledge)
- **Motivation:** Data exfiltration, sabotage
- **Attack Vectors:**
  - Excessive RBAC permissions
  - Audit log tampering
  - Key vault secret export

#### Compromised Service Principals
- **Skill Level:** N/A (automated)
- **Motivation:** Lateral movement, persistence
- **Attack Vectors:**
  - Leaked client secrets in code/logs
  - CI/CD pipeline compromise
  - Container image vulnerabilities

### Attack Surface

1. **Network Transmission**
   - Key Vault API calls over HTTPS
   - SSH key data in transit
   - Service principal authentication

2. **Local Storage**
   - Cached private keys at ~/.ssh/
   - Temporary files during retrieval
   - In-memory key material

3. **Azure Control Plane**
   - Key Vault access policies
   - RBAC role assignments
   - Audit log configuration

4. **Authentication Chain**
   - Azure CLI credentials
   - Service principal secrets
   - Managed identity tokens

5. **Application Code**
   - Error messages exposing keys
   - Debug logging
   - Stack traces with secrets

### Trust Boundaries

```
┌────────────────────────────────────────────────────┐
│ User Machine (UNTRUSTED)                           │
│  ┌─────────────────────────────────────────────┐   │
│  │ azlin CLI Process                           │   │
│  │  - Azure SDK calls                          │   │
│  │  - Key retrieval logic                      │   │
│  │  - Local file I/O                           │   │
│  └─────────────────────────────────────────────┘   │
│                     ↓ HTTPS (TLS 1.2+)             │
└────────────────────────────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────┐
│ Azure Cloud (TRUSTED)                              │
│  ┌─────────────────────────────────────────────┐   │
│  │ Azure Key Vault                             │   │
│  │  - Secrets storage (encrypted at rest)     │   │
│  │  - RBAC enforcement                         │   │
│  │  - Audit logging                            │   │
│  └─────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────┐
│ Target VM (SEMI-TRUSTED)                           │
│  - SSH daemon                                      │
│  - User processes                                  │
│  - ~/.ssh/authorized_keys                          │
└────────────────────────────────────────────────────┘
```

**Critical Trust Boundary:** User Machine → Azure Key Vault

---

## Security Requirements

### 1. Private Key Protection (CRITICAL)

**REQUIREMENT:** Private keys MUST NEVER be exposed in plain text outside secure contexts.

**Implementation:**
```python
import logging
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

logger = logging.getLogger(__name__)

class SSHKeyVaultManager:
    """SECURITY: This class handles highly sensitive SSH private keys."""

    # CRITICAL: Sanitize all log messages
    def retrieve_key_from_vault(
        self,
        vault_url: str,
        secret_name: str,
        destination_path: Path
    ) -> Path:
        """
        Retrieve SSH private key from Key Vault.

        SECURITY CONTROLS:
        - Never logs private key content
        - Validates vault URL (HTTPS only)
        - Sets file permissions before writing
        - Uses atomic file operations
        - Clears key material from memory
        """
        # Validate inputs
        if not vault_url.startswith("https://"):
            raise ValueError("Vault URL must use HTTPS")

        # SECURITY: Use DefaultAzureCredential (respects auth chain)
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        # SECURITY: Never log the secret value
        logger.info(f"Retrieving SSH key from vault: {vault_url}")
        logger.info(f"Secret name: {secret_name}")
        # DO NOT LOG: secret.value

        try:
            secret = client.get_secret(secret_name)
            private_key_content = secret.value

            # SECURITY: Create file with restricted permissions BEFORE writing
            destination_path.touch(mode=0o600)

            # SECURITY: Atomic write
            temp_path = destination_path.with_suffix('.tmp')
            temp_path.touch(mode=0o600)
            temp_path.write_text(private_key_content)
            temp_path.replace(destination_path)

            # SECURITY: Verify permissions
            stat = destination_path.stat()
            if stat.st_mode & 0o077:
                raise PermissionError("Failed to set secure permissions")

            logger.info(f"SSH key retrieved successfully: {destination_path}")
            return destination_path

        except Exception as e:
            # SECURITY: Sanitize error messages
            logger.error(f"Failed to retrieve key: {type(e).__name__}")
            raise KeyVaultError("Key retrieval failed") from e
        finally:
            # SECURITY: Clear sensitive data from memory
            if 'private_key_content' in locals():
                del private_key_content
```

**Prohibited Actions:**
```python
# NEVER DO THIS:
logger.debug(f"Private key: {private_key_content}")  # SECURITY VIOLATION
print(f"Key retrieved: {secret.value}")              # SECURITY VIOLATION
raise Exception(f"Failed: {private_key_content}")    # SECURITY VIOLATION
```

### 2. RBAC Permissions (HIGH)

**REQUIREMENT:** Follow principle of least privilege for Key Vault access.

**Minimum Required Permissions:**

```bash
# For azlin CLI (read-only)
az role assignment create \
  --assignee <principal-id> \
  --role "Key Vault Secrets User" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault-name>"

# For key rotation automation (read-write)
az role assignment create \
  --assignee <principal-id> \
  --role "Key Vault Secrets Officer" \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault-name>"
```

**Role Definitions:**

| Role | Permissions | Use Case | Risk Level |
|------|------------|----------|-----------|
| Key Vault Secrets User | Read secrets | azlin CLI users | LOW |
| Key Vault Secrets Officer | Read, write, delete secrets | Key rotation automation | MEDIUM |
| Key Vault Administrator | Full control | Infrastructure admin | HIGH |

**NEVER use these roles:**
- Owner
- Contributor
- Key Vault Administrator (except infra team)

### 3. Audit Logging (CRITICAL)

**REQUIREMENT:** All Key Vault access MUST be auditable.

**Enable Diagnostic Settings:**
```bash
# Enable Key Vault audit logs
az monitor diagnostic-settings create \
  --name "ssh-key-vault-audit" \
  --resource "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault-name>" \
  --logs '[
    {
      "category": "AuditEvent",
      "enabled": true,
      "retentionPolicy": {
        "enabled": true,
        "days": 90
      }
    }
  ]' \
  --workspace "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.OperationalInsights/workspaces/<workspace-name>"
```

**Monitored Events:**
- Secret retrieval (GET)
- Secret creation (SET)
- Secret deletion (DELETE)
- Failed authentication attempts
- Permission denied errors

### 4. Secure Key Deletion (HIGH)

**REQUIREMENT:** Keys MUST be securely deleted on VM cleanup.

**Implementation:**
```python
def cleanup_ssh_key(key_path: Path) -> None:
    """
    Securely delete SSH private key.

    SECURITY CONTROLS:
    - Overwrites file before deletion
    - Removes from filesystem
    - Clears file cache
    """
    if not key_path.exists():
        return

    try:
        # SECURITY: Overwrite with random data
        key_size = key_path.stat().st_size
        with open(key_path, 'wb') as f:
            f.write(os.urandom(key_size))
            f.flush()
            os.fsync(f.fileno())

        # SECURITY: Delete file
        key_path.unlink()

        logger.info(f"Securely deleted SSH key: {key_path}")

    except Exception as e:
        logger.error(f"Failed to delete key: {type(e).__name__}")
        raise
```

### 5. Error Handling (CRITICAL)

**REQUIREMENT:** Error messages MUST NOT leak sensitive information.

**Safe Error Handling:**
```python
class KeyVaultError(Exception):
    """Base exception for Key Vault operations."""
    pass

class KeyRetrievalError(KeyVaultError):
    """Raised when key retrieval fails."""
    pass

def safe_error_handler(func):
    """Decorator to sanitize error messages."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # SECURITY: Never expose exception details to user
            logger.error(f"Operation failed: {type(e).__name__}")

            # Generic user-facing message
            if isinstance(e, azure.core.exceptions.ResourceNotFoundError):
                raise KeyRetrievalError("Key not found in vault") from e
            elif isinstance(e, azure.core.exceptions.ClientAuthenticationError):
                raise KeyVaultError("Authentication failed") from e
            else:
                raise KeyVaultError("Key Vault operation failed") from e

    return wrapper
```

### 6. Service Principal Validation (HIGH)

**REQUIREMENT:** Validate service principal has Key Vault permissions before operations.

**Pre-flight Check:**
```python
def validate_keyvault_access(vault_url: str) -> bool:
    """
    Verify current identity has Key Vault access.

    Returns:
        bool: True if access granted, False otherwise
    """
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        # SECURITY: Test with harmless operation
        # Try to list secret properties (doesn't expose values)
        properties = client.list_properties_of_secrets()
        next(properties, None)  # Attempt to read first item

        return True

    except azure.core.exceptions.ClientAuthenticationError:
        logger.error("Authentication failed for Key Vault")
        return False
    except azure.core.exceptions.HttpResponseError as e:
        if e.status_code == 403:
            logger.error("Insufficient permissions for Key Vault")
            return False
        raise
```

---

## Azure Permissions

### Recommended Permission Model

```
┌─────────────────────────────────────────────────────────┐
│ Subscription: Production                                │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Resource Group: azlin-ssh-keys                     │ │
│  │                                                     │ │
│  │  ┌──────────────────────────────────────────────┐  │ │
│  │  │ Key Vault: azlin-ssh-vault                   │  │ │
│  │  │                                               │  │ │
│  │  │ RBAC Assignments:                            │  │ │
│  │  │  - azlin-users-group                         │  │ │
│  │  │    Role: Key Vault Secrets User              │  │ │
│  │  │    Scope: This vault                         │  │ │
│  │  │                                               │  │ │
│  │  │  - azlin-automation-sp                       │  │ │
│  │  │    Role: Key Vault Secrets Officer           │  │ │
│  │  │    Scope: This vault                         │  │ │
│  │  │                                               │  │ │
│  │  │  - infra-admin-group                         │  │ │
│  │  │    Role: Key Vault Administrator             │  │ │
│  │  │    Scope: This vault                         │  │ │
│  │  └──────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Permission Matrix

| Identity | Role | Get Secret | Set Secret | Delete Secret | List Secrets |
|----------|------|------------|------------|---------------|-------------|
| azlin CLI User | Key Vault Secrets User | ✓ | ✗ | ✗ | ✓ (properties only) |
| Rotation Service | Key Vault Secrets Officer | ✓ | ✓ | ✓ | ✓ |
| Infrastructure Admin | Key Vault Administrator | ✓ | ✓ | ✓ | ✓ |

### Network Security

```bash
# Enable Key Vault firewall
az keyvault update \
  --name <vault-name> \
  --resource-group <rg> \
  --default-action Deny \
  --bypass AzureServices

# Whitelist specific IP ranges (if needed)
az keyvault network-rule add \
  --name <vault-name> \
  --resource-group <rg> \
  --ip-address <office-ip>/32
```

**Recommendation:** Use Azure Private Link for Key Vault in production.

---

## Implementation Guidelines

### Secure Key Naming Strategy

**REQUIREMENT:** Use predictable, collision-resistant secret names.

**Pattern:**
```python
def generate_secret_name(vm_name: str, key_type: str = "ssh-private") -> str:
    """
    Generate Key Vault secret name for SSH key.

    Format: azlin-<vm-name>-<key-type>-<version>
    Example: azlin-prod-vm-123-ssh-private-v1

    SECURITY: Validates vm_name for injection attacks
    """
    # Sanitize VM name
    safe_vm_name = re.sub(r'[^a-zA-Z0-9-]', '', vm_name)
    if len(safe_vm_name) == 0 or safe_vm_name != vm_name:
        raise ValueError(f"Invalid VM name: {vm_name}")

    # Key Vault secret name constraints:
    # - Alphanumeric and hyphens only
    # - Max length 127 characters
    secret_name = f"azlin-{safe_vm_name}-{key_type}-v1"

    if len(secret_name) > 127:
        raise ValueError("Secret name too long")

    return secret_name
```

**Examples:**
```
azlin-dev-vm-ssh-private-v1
azlin-prod-api-server-ssh-private-v1
azlin-staging-worker-01-ssh-private-v1
```

**Anti-patterns (DO NOT USE):**
```
vm-123-key                    # Not namespaced
ssh_key_prod                  # Underscores not recommended
azlin/prod/vm/key             # Slashes not allowed
```

### Double Encryption Consideration

**QUESTION:** Should we encrypt keys before storing in Key Vault?

**Analysis:**

| Aspect | Key Vault Native | Double Encryption |
|--------|-----------------|-------------------|
| Encryption at rest | ✓ (AES-256) | ✓✓ (AES-256 + custom) |
| Key rotation | Automatic | Manual |
| Complexity | Low | High |
| Performance | Fast | Slower (decrypt on retrieve) |
| Compliance | Sufficient for most | Required for specific regulations |

**Recommendation:** **NO** - Do not implement double encryption unless:
1. Regulatory compliance explicitly requires it (e.g., ITAR, FedRAMP High)
2. You have key management infrastructure in place
3. You can handle key rotation complexity

**Rationale:**
- Azure Key Vault provides HSM-backed encryption
- Double encryption adds significant complexity
- Marginal security benefit for SSH keys (ephemeral usage)
- Increases attack surface (encryption key management)

**If required by compliance:**
```python
from cryptography.fernet import Fernet

class DoubleEncryptedKeyVault:
    """ONLY USE IF REQUIRED BY COMPLIANCE."""

    def __init__(self, vault_url: str, encryption_key: bytes):
        self.vault_url = vault_url
        self.cipher = Fernet(encryption_key)

    def store_encrypted_key(self, secret_name: str, private_key: str) -> None:
        """Encrypt key before storing in vault."""
        encrypted = self.cipher.encrypt(private_key.encode())
        # Store encrypted bytes in vault
        # ...

    def retrieve_encrypted_key(self, secret_name: str) -> str:
        """Retrieve and decrypt key from vault."""
        encrypted = # retrieve from vault
        decrypted = self.cipher.decrypt(encrypted)
        return decrypted.decode()
```

### Local Key Caching

**QUESTION:** What are security implications of caching keys locally?

**Security Tradeoffs:**

**Benefits:**
- Reduced Key Vault API calls (cost savings)
- Faster SSH connections
- Offline access support

**Risks:**
- Stale keys after rotation
- Increased local attack surface
- Permission drift (cached file permissions)
- Orphaned keys after VM deletion

**Recommendation:** **LIMITED CACHING** with strict controls

**Implementation:**
```python
class SSHKeyCacheManager:
    """Manage cached SSH keys with security controls."""

    CACHE_DIR = Path.home() / ".azlin" / "ssh_cache"
    CACHE_MAX_AGE = timedelta(hours=1)  # Short TTL

    def __init__(self):
        # SECURITY: Create cache dir with restricted permissions
        self.CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

    def get_cached_key(
        self,
        vault_url: str,
        secret_name: str
    ) -> Path | None:
        """
        Get cached key if valid.

        Returns:
            Path to cached key if valid, None if expired/missing
        """
        cache_path = self._cache_path(vault_url, secret_name)

        if not cache_path.exists():
            return None

        # SECURITY: Verify file permissions
        stat = cache_path.stat()
        if stat.st_mode & 0o077:
            logger.warning(f"Cache has insecure permissions: {cache_path}")
            cache_path.unlink()  # Delete insecure cache
            return None

        # Check age
        age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
        if age > self.CACHE_MAX_AGE:
            logger.info("Cache expired, will refresh")
            return None

        logger.info(f"Using cached key (age: {age})")
        return cache_path

    def cache_key(
        self,
        vault_url: str,
        secret_name: str,
        key_content: str
    ) -> Path:
        """Cache key with secure permissions."""
        cache_path = self._cache_path(vault_url, secret_name)

        # SECURITY: Atomic write with restricted permissions
        cache_path.touch(mode=0o600)
        cache_path.write_text(key_content)

        return cache_path

    def invalidate_cache(self, vault_url: str, secret_name: str) -> None:
        """Remove cached key."""
        cache_path = self._cache_path(vault_url, secret_name)
        if cache_path.exists():
            # SECURITY: Overwrite before delete
            with open(cache_path, 'wb') as f:
                f.write(os.urandom(cache_path.stat().st_size))
            cache_path.unlink()

    def _cache_path(self, vault_url: str, secret_name: str) -> Path:
        """Generate cache file path."""
        # Hash vault URL + secret name for filename
        cache_key = hashlib.sha256(
            f"{vault_url}:{secret_name}".encode()
        ).hexdigest()[:16]

        return self.CACHE_DIR / f"key_{cache_key}"
```

**Cache Policy:**
```python
# Configuration in ~/.azlin/config.toml
[keyvault]
cache_enabled = true
cache_ttl_hours = 1  # Short TTL
cache_max_size_mb = 10
purge_cache_on_exit = true  # Clean up cached keys
```

---

## Security Controls

### Defense in Depth Layers

```
Layer 1: Network Security
  └─ HTTPS (TLS 1.2+) for all Key Vault API calls
  └─ Azure Private Link (optional, recommended for prod)
  └─ Key Vault firewall rules

Layer 2: Identity & Access
  └─ Azure RBAC (Key Vault Secrets User role)
  └─ Service principal validation
  └─ Credential expiration checks

Layer 3: Data Protection
  └─ Key Vault HSM-backed encryption at rest
  └─ In-transit encryption (TLS)
  └─ Secure local file permissions (0600)

Layer 4: Application Security
  └─ Input validation (vault URL, secret names)
  └─ Error sanitization (no key leakage)
  └─ Memory clearing after use

Layer 5: Audit & Monitoring
  └─ Key Vault diagnostic logs
  └─ Failed access attempt alerts
  └─ Anomaly detection (unusual access patterns)

Layer 6: Operational Security
  └─ Key rotation procedures
  └─ Incident response playbook
  └─ Secure key deletion on cleanup
```

### Input Validation

```python
def validate_vault_url(url: str) -> str:
    """
    Validate Key Vault URL format.

    Security: Prevents injection attacks and URL tampering
    """
    # Must be HTTPS
    if not url.startswith("https://"):
        raise ValueError("Vault URL must use HTTPS")

    # Must match Azure Key Vault URL pattern
    pattern = r'^https://[a-zA-Z0-9-]+\.vault\.azure\.net/?$'
    if not re.match(pattern, url):
        raise ValueError("Invalid Key Vault URL format")

    return url.rstrip('/')

def validate_secret_name(name: str) -> str:
    """
    Validate secret name.

    Security: Prevents directory traversal and injection
    """
    # Alphanumeric and hyphens only
    if not re.match(r'^[a-zA-Z0-9-]+$', name):
        raise ValueError("Secret name contains invalid characters")

    # Length check
    if len(name) > 127:
        raise ValueError("Secret name too long (max 127 chars)")

    if len(name) == 0:
        raise ValueError("Secret name cannot be empty")

    return name
```

### Sanitization Layer

**Integration with AzureCommandSanitizer:**

```python
# Update azure_command_sanitizer.py
class AzureCommandSanitizer:
    SENSITIVE_PARAMS: ClassVar[set[str]] = {
        # ... existing params ...

        # Key Vault parameters
        "--vault-url",
        "--secret-name",
        "--secret-value",
        "--vault-secret",
    }

    # Value-based patterns
    SECRET_VALUE_PATTERNS: ClassVar[dict[str, Pattern]] = {
        # ... existing patterns ...

        # SSH private key pattern (BEGIN RSA/ED25519 PRIVATE KEY)
        "ssh_private_key": re.compile(
            r"(-----BEGIN [A-Z0-9 ]+PRIVATE KEY-----[\\s\\S]+?-----END [A-Z0-9 ]+PRIVATE KEY-----)",
            re.MULTILINE
        ),

        # Azure Key Vault URL
        "keyvault_url": re.compile(
            r"(https://[a-zA-Z0-9-]+\.vault\.azure\.net)",
            re.IGNORECASE
        ),
    }
```

---

## Attack Scenarios & Mitigations

### Scenario 1: Compromised Service Principal

**Attack:** Adversary obtains service principal client secret from leaked GitHub repo.

**Impact:** Unauthorized access to Key Vault, SSH key retrieval, full VM compromise.

**Mitigation:**
1. **Detection:**
   - Enable GitHub secret scanning
   - Monitor Key Vault audit logs for anomalous access
   - Alert on first-time secret access from new IPs

2. **Prevention:**
   - Never commit secrets to version control
   - Use environment variables for secrets
   - Implement secret rotation policy (90 days)
   - Use certificate-based auth instead of client secrets

3. **Response:**
   - Immediately rotate compromised client secret
   - Revoke all active SSH sessions
   - Rotate SSH keys stored in vault
   - Audit all accessed resources

**Code:**
```python
# Security control: Rate limiting
class KeyVaultAccessControl:
    def __init__(self):
        self.access_counts = {}  # IP -> (count, timestamp)

    def check_rate_limit(self, client_ip: str) -> bool:
        """Detect suspicious access patterns."""
        now = time.time()

        if client_ip in self.access_counts:
            count, first_time = self.access_counts[client_ip]

            # 10 accesses per minute threshold
            if now - first_time < 60 and count > 10:
                logger.warning(f"Rate limit exceeded: {client_ip}")
                return False

        # Update count
        if client_ip not in self.access_counts or now - self.access_counts[client_ip][1] > 60:
            self.access_counts[client_ip] = (1, now)
        else:
            count, first_time = self.access_counts[client_ip]
            self.access_counts[client_ip] = (count + 1, first_time)

        return True
```

### Scenario 2: Key Leakage in Error Messages

**Attack:** Private key exposed in exception stack trace logged to application logs.

**Impact:** SSH key compromise, VM access, data breach.

**Mitigation:**
```python
# Secure exception handling
class SecureKeyVaultClient:
    def retrieve_key(self, secret_name: str) -> str:
        try:
            secret = self.client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            # SECURITY: Never include secret.value in error
            logger.error(
                f"Key retrieval failed: {type(e).__name__}",
                extra={
                    "secret_name": secret_name,
                    "vault_url": self.vault_url,
                    # DO NOT LOG: secret.value
                }
            )
            # Generic user-facing error
            raise KeyRetrievalError("Failed to retrieve SSH key") from e
```

### Scenario 3: MITM Attack on Key Retrieval

**Attack:** Adversary intercepts Key Vault API calls to steal SSH private key.

**Impact:** Private key exposure, VM compromise.

**Mitigation:**
1. **Prevention:**
   - Enforce TLS 1.2+ for all Azure SDK calls
   - Use certificate pinning (advanced)
   - Validate server certificates

2. **Code:**
```python
from azure.core.pipeline.policies import RetryPolicy, UserAgentPolicy
from azure.core.pipeline.transport import RequestsTransport

# Enforce TLS 1.2+
import ssl
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

transport = RequestsTransport(
    connection_verify=True,  # Verify server certificate
    connection_cert=None,
    ssl_context=ssl_context
)

client = SecretClient(
    vault_url=vault_url,
    credential=credential,
    transport=transport
)
```

### Scenario 4: Excessive RBAC Permissions

**Attack:** Service principal granted "Contributor" role on Key Vault instead of "Key Vault Secrets User".

**Impact:** Ability to delete vault, modify access policies, expose all secrets.

**Mitigation:**
```bash
# Audit existing permissions
az role assignment list \
  --scope "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.KeyVault/vaults/<vault>" \
  --output table

# Correct approach: Grant minimal permissions
az role assignment create \
  --assignee <principal-id> \
  --role "Key Vault Secrets User" \  # NOT "Contributor"
  --scope "<vault-resource-id>"

# Implement permission guardrails
az policy assignment create \
  --name "deny-keyvault-contributor" \
  --policy "Deny Contributor on Key Vaults" \
  --scope "/subscriptions/<sub-id>"
```

### Scenario 5: Cached Key Compromise

**Attack:** Attacker gains access to user's laptop, finds cached SSH key at ~/.azlin/ssh_cache/.

**Impact:** VM access using cached key until it expires.

**Mitigation:**
```python
# Security controls for caching
class SecureKeyCache:
    CACHE_TTL = timedelta(minutes=30)  # Short TTL

    def __init__(self):
        # SECURITY: Register cleanup on exit
        atexit.register(self.purge_all_caches)

    def purge_all_caches(self):
        """Securely delete all cached keys on exit."""
        for cache_file in self.CACHE_DIR.glob("key_*"):
            try:
                # Overwrite before delete
                cache_file.write_bytes(os.urandom(cache_file.stat().st_size))
                cache_file.unlink()
            except Exception as e:
                logger.error(f"Failed to purge cache: {e}")

    # SECURITY: Verify permissions on every access
    def validate_cache_file(self, path: Path) -> bool:
        stat = path.stat()

        # Must be owned by current user
        if stat.st_uid != os.getuid():
            return False

        # Must have 0600 permissions
        if stat.st_mode & 0o077:
            return False

        return True
```

---

## Monitoring & Audit

### Key Metrics

1. **Access Metrics:**
   - Key retrievals per hour
   - Failed authentication attempts
   - Unique callers per day
   - Access from new IP addresses

2. **Security Metrics:**
   - Permission denied errors
   - Invalid secret name attempts
   - Key deletion events
   - Unusual access patterns

### Azure Monitor Queries

```kusto
// Failed Key Vault access attempts
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where ResultType == "Unauthorized" or httpStatusCode_d == 403
| summarize FailedAttempts=count() by CallerIPAddress, identity_claim_appid_g
| where FailedAttempts > 5
| order by FailedAttempts desc

// SSH key retrievals
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where OperationName == "SecretGet"
| where id_s contains "azlin-" and id_s contains "-ssh-private"
| project TimeGenerated, CallerIPAddress, identity_claim_appid_g, id_s, httpStatusCode_d
| order by TimeGenerated desc

// Anomalous access patterns (access from new countries)
let baseline = AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where TimeGenerated between (ago(30d) .. ago(1d))
| summarize Countries=make_set(clientInfo_s) by identity_claim_appid_g;
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.KEYVAULT"
| where TimeGenerated > ago(1h)
| join kind=leftanti baseline on identity_claim_appid_g
| project TimeGenerated, CallerIPAddress, identity_claim_appid_g, OperationName, clientInfo_s
```

### Alert Rules

```bash
# Alert on failed authentication
az monitor metrics alert create \
  --name "keyvault-auth-failures" \
  --resource-group <rg> \
  --scopes "<vault-resource-id>" \
  --condition "total ServiceApiHit > 10 where ResultType == Unauthorized" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action <action-group-id>

# Alert on bulk key retrieval
az monitor metrics alert create \
  --name "keyvault-bulk-retrieval" \
  --resource-group <rg> \
  --scopes "<vault-resource-id>" \
  --condition "total ServiceApiHit > 50 where OperationName == SecretGet" \
  --window-size 15m \
  --evaluation-frequency 5m \
  --action <action-group-id>
```

---

## Testing Requirements

### Security Test Suite

```python
# tests/security/test_keyvault_ssh_security.py
import pytest
from azlin.modules.ssh_keyvault import SSHKeyVaultManager

class TestKeyVaultSecurity:
    """Security tests for Key Vault SSH key storage."""

    def test_private_key_never_logged(self, caplog):
        """CRITICAL: Verify private key never appears in logs."""
        manager = SSHKeyVaultManager(vault_url="https://test.vault.azure.net")

        with pytest.raises(KeyRetrievalError):
            manager.retrieve_key_from_vault("nonexistent-key", Path("/tmp/test"))

        # Verify logs don't contain key material
        for record in caplog.records:
            assert "BEGIN PRIVATE KEY" not in record.message
            assert "BEGIN RSA PRIVATE KEY" not in record.message

    def test_file_permissions_enforced(self, tmp_path):
        """Verify cached keys have 0600 permissions."""
        key_path = tmp_path / "test_key"

        # Simulate key retrieval
        manager = SSHKeyVaultManager(vault_url="https://test.vault.azure.net")
        # ... retrieve key to key_path ...

        # Check permissions
        stat = key_path.stat()
        assert stat.st_mode & 0o777 == 0o600

    def test_vault_url_validation(self):
        """Verify URL validation prevents injection."""
        manager = SSHKeyVaultManager(vault_url="https://test.vault.azure.net")

        # Should reject non-HTTPS
        with pytest.raises(ValueError, match="HTTPS"):
            manager._validate_vault_url("http://evil.com")

        # Should reject invalid format
        with pytest.raises(ValueError, match="Invalid"):
            manager._validate_vault_url("https://evil.com/../../etc/passwd")

    def test_secret_name_sanitization(self):
        """Verify secret names are sanitized."""
        with pytest.raises(ValueError):
            SSHKeyVaultManager.generate_secret_name("vm'; DROP TABLE--")

        with pytest.raises(ValueError):
            SSHKeyVaultManager.generate_secret_name("../../../etc/passwd")

    def test_error_messages_sanitized(self):
        """Verify error messages don't leak sensitive info."""
        manager = SSHKeyVaultManager(vault_url="https://test.vault.azure.net")

        with pytest.raises(KeyRetrievalError) as exc_info:
            manager.retrieve_key_from_vault("secret-key", Path("/tmp/test"))

        # Error should not contain vault URL, secret name details
        assert "https://test.vault.azure.net" not in str(exc_info.value)

    def test_cache_purge_on_exit(self, tmp_path):
        """Verify cached keys are deleted on exit."""
        cache_manager = SSHKeyCacheManager()
        cache_manager.CACHE_DIR = tmp_path

        # Create cache file
        cache_file = tmp_path / "key_abc123"
        cache_file.touch(mode=0o600)

        # Trigger cleanup
        cache_manager.purge_all_caches()

        # Verify file deleted
        assert not cache_file.exists()

    def test_rbac_permission_check(self):
        """Verify RBAC permissions are validated."""
        manager = SSHKeyVaultManager(vault_url="https://test.vault.azure.net")

        # Should detect insufficient permissions
        with patch('azure.keyvault.secrets.SecretClient.get_secret') as mock:
            mock.side_effect = azure.core.exceptions.HttpResponseError(
                response=MagicMock(status_code=403)
            )

            with pytest.raises(KeyVaultError, match="permissions"):
                manager.retrieve_key_from_vault("key", Path("/tmp/test"))
```

### Penetration Testing Checklist

- [ ] Attempt to retrieve key without authentication
- [ ] Attempt to retrieve key with expired service principal
- [ ] Attempt SQL injection in secret names
- [ ] Attempt path traversal in vault URLs
- [ ] Verify TLS version enforcement (reject TLS 1.0, 1.1)
- [ ] Attempt to intercept key during retrieval (MITM)
- [ ] Verify cached keys are encrypted at rest (OS-level)
- [ ] Attempt to access Key Vault from unauthorized IP
- [ ] Verify audit logs capture all access attempts
- [ ] Attempt to enumerate secret names via API
- [ ] Verify rate limiting prevents brute force
- [ ] Attempt privilege escalation via RBAC bypass

---

## Operational Procedures

### Key Rotation Procedure

**Frequency:** Every 90 days (automated)

**Steps:**
```bash
#!/bin/bash
# rotate_ssh_keys.sh - Automated SSH key rotation

set -euo pipefail

VAULT_URL="https://azlin-ssh-vault.vault.azure.net"
VM_LIST_FILE="/tmp/azlin_vms.txt"

# 1. Generate new SSH key pair
NEW_KEY_PATH="/tmp/azlin_key_new"
ssh-keygen -t ed25519 -f "$NEW_KEY_PATH" -N "" -C "azlin-rotated-$(date +%Y%m%d)"

# 2. Store new private key in Key Vault
az keyvault secret set \
  --vault-name "azlin-ssh-vault" \
  --name "azlin-ssh-private-v2" \
  --file "$NEW_KEY_PATH" \
  --description "Rotated on $(date --iso-8601)"

# 3. Update all VMs with new public key
azlin list --format json > "$VM_LIST_FILE"
jq -r '.[].name' "$VM_LIST_FILE" | while read VM_NAME; do
  echo "Updating $VM_NAME..."

  # Add new key to VM
  az vm user update \
    --resource-group "azlin-vms" \
    --name "$VM_NAME" \
    --username "azureuser" \
    --ssh-key-value "$(cat ${NEW_KEY_PATH}.pub)"

  # Wait for propagation
  sleep 5

  # Test new key
  if ssh -i "$NEW_KEY_PATH" "azureuser@$VM_NAME" "echo OK" 2>/dev/null; then
    echo "✓ $VM_NAME updated successfully"
  else
    echo "✗ $VM_NAME update failed"
    exit 1
  fi
done

# 4. Archive old key (do not delete immediately)
az keyvault secret set-attributes \
  --vault-name "azlin-ssh-vault" \
  --name "azlin-ssh-private-v1" \
  --enabled false

# 5. Update azlin configuration
azlin config set keyvault.secret_name "azlin-ssh-private-v2"

# 6. Secure cleanup
shred -vfz -n 3 "$NEW_KEY_PATH"
rm -f "$VM_LIST_FILE"

echo "✓ SSH key rotation completed successfully"
```

### Incident Response Playbook

**Scenario:** Suspected SSH private key compromise

**Immediate Actions (< 5 minutes):**
1. Disable compromised key in Key Vault:
   ```bash
   az keyvault secret set-attributes \
     --vault-name "azlin-ssh-vault" \
     --name "azlin-ssh-private-v1" \
     --enabled false
   ```

2. Revoke active SSH sessions:
   ```bash
   # On each VM
   sudo pkill -u azureuser  # Terminate all user sessions
   ```

3. Rotate client secret (if service principal compromised):
   ```bash
   az ad sp credential reset --id <client-id>
   ```

**Investigation (< 30 minutes):**
4. Query Key Vault audit logs:
   ```kusto
   AzureDiagnostics
   | where ResourceProvider == "MICROSOFT.KEYVAULT"
   | where TimeGenerated > ago(7d)
   | where OperationName contains "Secret"
   | project TimeGenerated, CallerIPAddress, identity_claim_appid_g, OperationName, ResultType
   | order by TimeGenerated desc
   ```

5. Identify compromised VMs:
   ```bash
   # Check SSH logs on each VM
   sudo grep "Accepted publickey" /var/log/auth.log | tail -50
   ```

**Remediation (< 2 hours):**
6. Generate new SSH key pair
7. Store new key in Key Vault (new secret name)
8. Update all VMs with new public key
9. Delete old key from Key Vault (after grace period)

**Post-Incident (< 24 hours):**
10. Root cause analysis
11. Update RBAC permissions if needed
12. Review and enhance monitoring alerts
13. Document lessons learned

---

## Conclusion

### Security Assessment Summary

| Aspect | Rating | Notes |
|--------|--------|-------|
| Data Protection | STRONG | HSM-backed encryption, TLS in transit |
| Access Control | STRONG | Azure RBAC, principle of least privilege |
| Audit Logging | STRONG | Comprehensive Key Vault diagnostics |
| Error Handling | MEDIUM | Requires careful implementation |
| Key Management | MEDIUM | Rotation procedures need automation |
| Local Caching | MEDIUM | Acceptable with short TTL and purge on exit |

### Recommendations

**MUST IMPLEMENT (Critical):**
1. Never log private key content in any scenario
2. Enforce Key Vault Secrets User role (not Contributor)
3. Enable Key Vault diagnostic logging to Log Analytics
4. Validate service principal permissions before operations
5. Set cached key file permissions to 0600
6. Implement secure key deletion (overwrite before unlink)
7. Sanitize all error messages

**SHOULD IMPLEMENT (High):**
8. Use certificate-based service principal auth
9. Enable Key Vault firewall with IP whitelisting
10. Implement key rotation automation (90-day cycle)
11. Set cache TTL to 1 hour maximum
12. Purge cache on application exit
13. Monitor for anomalous access patterns
14. Use Azure Private Link for production

**MAY IMPLEMENT (Medium):**
15. Double encryption (only if compliance mandates)
16. Hardware security module (HSM) tier Key Vault
17. Geo-replication for disaster recovery
18. Custom alert rules for security events

### Approval Decision

**APPROVED** with the following conditions:

1. All MUST IMPLEMENT recommendations are completed
2. Security test suite passes with 100% coverage
3. Penetration testing validates controls
4. Security review sign-off from infra team
5. Incident response playbook documented

**Risk Level:** MEDIUM (after controls implemented)
**Reviewer:** Security Agent
**Date:** 2025-11-18

---

## References

- [Azure Key Vault Best Practices](https://learn.microsoft.com/en-us/azure/key-vault/general/best-practices)
- [Azure RBAC for Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide)
- [SSH Key Management](https://www.ssh.com/academy/ssh/key-management)
- [NIST SP 800-57: Key Management](https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final)

---

**Document Control:**
- Version: 1.0
- Last Updated: 2025-11-18
- Next Review: 2026-02-18 (90 days)
- Classification: Internal - Security Review
