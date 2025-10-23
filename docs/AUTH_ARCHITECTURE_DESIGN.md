# Service Principal Authentication Architecture Design

**Version:** 1.0
**Date:** 2025-10-23
**Status:** Design Complete
**Author:** Architecture Agent

---

## Executive Summary

This document defines the comprehensive architecture for adding service principal authentication to azlin while maintaining 100% backward compatibility with existing Azure CLI delegation patterns. The design introduces **8 self-contained modules (bricks)** that follow the established azlin philosophy of ruthless simplicity and modular regenerability.

**Core Design Principles:**
1. **Zero Breaking Changes**: Azure CLI remains the default authentication method with identical behavior
2. **Azure CLI Delegation**: No token storage - all credentials delegated to trusted auth providers (az CLI, Azure Identity SDK)
3. **Security-First**: All 10 P0 security controls mandatory, enforced at compile-time where possible
4. **Brick Architecture**: Each module is self-contained with clear contracts (studs), enabling independent regeneration
5. **Modular Testing**: >90% coverage through isolated unit tests, integration tests, and security tests

**Authentication Priority Chain:**
```
1. Service Principal (Certificate) - highest security
2. Service Principal (Client Secret) - secure with secret management
3. Managed Identity - for Azure environments
4. Azure CLI - existing default (backward compatible)
5. Fail with clear error message
```

The architecture extends the existing `AzureAuthenticator` class with new authentication methods while preserving the current `az CLI` code path completely unchanged. Configuration extends the existing TOML structure with a new `[auth]` section, remaining fully backward compatible with existing config files.

---

## 1. Module Catalog (The 8 Bricks)

### Brick 1: AuthMethod Enum
**File:** `src/azlin/auth/auth_method.py`
**Responsibility:** Define authentication method enumeration
**Dependencies:** None
**Studs (Public Interface):**
```python
class AuthMethod(str, Enum):
    """Authentication method enumeration."""
    AZURE_CLI = "azure_cli"              # Default - existing behavior
    SERVICE_PRINCIPAL_SECRET = "sp_secret"  # Client ID + secret
    SERVICE_PRINCIPAL_CERT = "sp_cert"      # Client ID + certificate
    MANAGED_IDENTITY = "managed_identity"   # System/user-assigned MI
```

**Design Rationale:**
- String enum for easy serialization to TOML
- Clear naming that maps to Azure Identity SDK credential types
- Explicit default value preserves backward compatibility

---

### Brick 2: AuthConfig Data Models
**File:** `src/azlin/auth/models.py`
**Responsibility:** Define immutable authentication configuration structures
**Dependencies:** AuthMethod
**Studs (Public Interface):**
```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from azlin.auth.auth_method import AuthMethod

@dataclass(frozen=True)
class CertificateInfo:
    """Certificate-based authentication metadata.

    Security: No certificate data stored, only file path.
    """
    certificate_path: Path
    thumbprint: Optional[str] = None  # For validation, not auth

    def __post_init__(self):
        """Validate certificate path exists and has secure permissions."""
        if not self.certificate_path.exists():
            raise ValueError(f"Certificate not found: {self.certificate_path}")

        # Validate permissions: 0600 or 0400 (owner read only)
        mode = self.certificate_path.stat().st_mode & 0o777
        if mode not in (0o600, 0o400):
            raise ValueError(
                f"Certificate has insecure permissions: {oct(mode)}. "
                f"Expected: 0600 or 0400"
            )

@dataclass(frozen=True)
class ServicePrincipalConfig:
    """Service principal authentication configuration.

    Security: No secrets stored. Client secret must come from:
    - Environment variable (AZURE_CLIENT_SECRET)
    - Azure Key Vault (future)
    - User prompt (future)
    """
    client_id: str
    tenant_id: str
    certificate_info: Optional[CertificateInfo] = None

    def __post_init__(self):
        """Validate UUIDs for client_id and tenant_id."""
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

        if not re.match(uuid_pattern, self.client_id, re.IGNORECASE):
            raise ValueError(f"Invalid client_id format: {self.client_id}")

        if not re.match(uuid_pattern, self.tenant_id, re.IGNORECASE):
            raise ValueError(f"Invalid tenant_id format: {self.tenant_id}")

@dataclass(frozen=True)
class ManagedIdentityConfig:
    """Managed identity authentication configuration."""
    client_id: Optional[str] = None  # For user-assigned MI

    def __post_init__(self):
        """Validate client_id if provided."""
        if self.client_id:
            import re
            uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            if not re.match(uuid_pattern, self.client_id, re.IGNORECASE):
                raise ValueError(f"Invalid client_id format: {self.client_id}")

@dataclass(frozen=True)
class AuthConfig:
    """Complete authentication configuration.

    Exactly one of sp_config or mi_config should be set for non-CLI auth.
    """
    method: AuthMethod
    subscription_id: str
    sp_config: Optional[ServicePrincipalConfig] = None
    mi_config: Optional[ManagedIdentityConfig] = None

    def __post_init__(self):
        """Validate configuration consistency."""
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

        # Validate subscription_id
        if not re.match(uuid_pattern, self.subscription_id, re.IGNORECASE):
            raise ValueError(f"Invalid subscription_id: {self.subscription_id}")

        # Validate method-specific config
        if self.method in (AuthMethod.SERVICE_PRINCIPAL_SECRET,
                          AuthMethod.SERVICE_PRINCIPAL_CERT):
            if not self.sp_config:
                raise ValueError(f"{self.method} requires sp_config")

        if self.method == AuthMethod.MANAGED_IDENTITY:
            if not self.mi_config:
                raise ValueError(f"{self.method} requires mi_config")

        # Validate certificate presence for cert-based auth
        if self.method == AuthMethod.SERVICE_PRINCIPAL_CERT:
            if not self.sp_config or not self.sp_config.certificate_info:
                raise ValueError("Certificate auth requires certificate_info")

@dataclass
class AuthContext:
    """Runtime authentication context.

    Mutable context for tracking auth state during operations.
    """
    config: AuthConfig
    credential: Any  # Azure Identity credential object
    authenticated: bool = False
    error: Optional[str] = None

    def mark_authenticated(self) -> None:
        """Mark authentication successful."""
        self.authenticated = True
        self.error = None

    def mark_failed(self, error: str) -> None:
        """Mark authentication failed."""
        self.authenticated = False
        self.error = error
```

**Design Rationale:**
- Frozen dataclasses enforce immutability for config (defense against mutation bugs)
- Runtime validation in `__post_init__` catches configuration errors early
- Clear separation between config (what to do) and context (runtime state)
- Certificate permissions validated at construction time (fail-fast)
- No secrets in any structure - only references to secret sources

---

### Brick 3: AuthConfigManager
**File:** `src/azlin/auth/config_manager.py`
**Responsibility:** Load/save authentication configuration to TOML
**Dependencies:** AuthMethod, AuthConfig models, ConfigManager
**Studs (Public Interface):**
```python
from azlin.config_manager import ConfigManager
from azlin.auth.models import AuthConfig, ServicePrincipalConfig, ManagedIdentityConfig
from azlin.auth.auth_method import AuthMethod

class AuthConfigManager:
    """Manage authentication configuration in TOML.

    Extends existing ConfigManager with [auth] section support.
    Configuration format:

    [auth]
    method = "sp_secret"  # or "sp_cert", "managed_identity", "azure_cli"
    subscription_id = "..."

    [auth.service_principal]
    client_id = "..."
    tenant_id = "..."
    certificate_path = "/path/to/cert.pem"  # Only for sp_cert

    [auth.managed_identity]
    client_id = "..."  # Optional, for user-assigned MI
    """

    @staticmethod
    def load_auth_config(custom_path: str | None = None) -> AuthConfig | None:
        """Load authentication config from TOML.

        Returns None if [auth] section not present (backward compatible).
        """
        ...

    @staticmethod
    def save_auth_config(auth_config: AuthConfig, custom_path: str | None = None) -> None:
        """Save authentication config to TOML.

        Preserves existing config sections.
        """
        ...

    @staticmethod
    def validate_auth_section(data: dict) -> None:
        """Validate [auth] section structure.

        Raises ConfigError on invalid structure.
        """
        ...
```

**Integration Point:** Extends `ConfigManager` - modifies existing config file handling
**Security Controls:**
- No secrets written to TOML (P0-1)
- Certificate path validation (P0-2)
- Config file permissions enforced by ConfigManager (0600)

**Design Rationale:**
- Reuses existing TOML infrastructure from ConfigManager
- New `[auth]` section is optional - absence means use Azure CLI (backward compatible)
- Validates configuration structure at load time
- Atomic writes via ConfigManager's temp file + rename pattern

---

### Brick 4: CertificateValidator
**File:** `src/azlin/auth/certificate_validator.py`
**Responsibility:** Validate certificate files for service principal authentication
**Dependencies:** None (uses stdlib only)
**Studs (Public Interface):**
```python
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class CertificateValidation:
    """Certificate validation result."""
    valid: bool
    format: str  # "PEM", "PFX", etc.
    has_private_key: bool
    permissions_ok: bool
    error: Optional[str] = None

class CertificateValidator:
    """Validate certificate files for authentication.

    Security: Validates permissions, format, private key presence.
    """

    ALLOWED_PERMISSIONS = (0o600, 0o400)  # Owner read-only
    ALLOWED_FORMATS = {"PEM", "PFX"}

    @staticmethod
    def validate_certificate(cert_path: Path) -> CertificateValidation:
        """Validate certificate file.

        Checks:
        1. File exists and is readable
        2. Permissions are 0600 or 0400
        3. Format is PEM or PFX
        4. Contains private key (required for auth)
        """
        ...

    @staticmethod
    def check_permissions(cert_path: Path) -> bool:
        """Check certificate file has secure permissions."""
        ...

    @staticmethod
    def detect_format(cert_path: Path) -> str:
        """Detect certificate format (PEM/PFX/unknown)."""
        ...

    @staticmethod
    def has_private_key(cert_path: Path, format: str) -> bool:
        """Check if certificate file contains private key."""
        ...
```

**Security Controls:**
- Permission validation (P0-2)
- Format validation prevents malformed input
- Private key presence check

**Design Rationale:**
- Standalone validator enables reuse across auth flows
- Returns structured result for clear error reporting
- No external dependencies (uses stdlib for PEM parsing)
- Fail-fast validation before attempting authentication

---

### Brick 5: CredentialFactory
**File:** `src/azlin/auth/credential_factory.py`
**Responsibility:** Create Azure Identity credential objects from AuthConfig
**Dependencies:** AuthConfig models, azure-identity SDK
**Studs (Public Interface):**
```python
from azure.identity import (
    ClientSecretCredential,
    CertificateCredential,
    ManagedIdentityCredential,
    AzureCliCredential,
)
from azlin.auth.models import AuthConfig
from azlin.auth.auth_method import AuthMethod

class CredentialFactoryError(Exception):
    """Raised when credential creation fails."""
    pass

class CredentialFactory:
    """Factory for creating Azure Identity credentials.

    Maps AuthConfig to Azure Identity SDK credential types.
    """

    @staticmethod
    def create_credential(auth_config: AuthConfig) -> Any:
        """Create credential from configuration.

        Returns Azure Identity credential object for the specified method.

        Raises:
            CredentialFactoryError: If credential creation fails
            ValueError: If configuration is invalid
        """
        ...

    @staticmethod
    def _create_client_secret_credential(config: ServicePrincipalConfig) -> ClientSecretCredential:
        """Create service principal credential with client secret.

        Secret sourced from AZURE_CLIENT_SECRET environment variable.
        """
        ...

    @staticmethod
    def _create_certificate_credential(config: ServicePrincipalConfig) -> CertificateCredential:
        """Create service principal credential with certificate."""
        ...

    @staticmethod
    def _create_managed_identity_credential(config: ManagedIdentityConfig) -> ManagedIdentityCredential:
        """Create managed identity credential."""
        ...

    @staticmethod
    def _create_azure_cli_credential() -> AzureCliCredential:
        """Create Azure CLI credential (existing behavior)."""
        ...
```

**Security Controls:**
- Client secret from environment only (P0-1)
- Certificate path validation via CertificateInfo
- No credential caching (credentials are short-lived objects)

**Design Rationale:**
- Factory pattern isolates Azure SDK complexity
- Each credential type has dedicated factory method
- Clear error messages for missing secrets/certificates
- Returns Azure Identity credential objects (not tokens)

---

### Brick 6: AuthenticationChain
**File:** `src/azlin/auth/authentication_chain.py`
**Responsibility:** Execute authentication priority chain with fallback
**Dependencies:** AuthConfig, CredentialFactory, AzureAuthenticator
**Studs (Public Interface):**
```python
from typing import List, Optional, Tuple
from azlin.auth.models import AuthConfig, AuthContext
from azlin.auth.credential_factory import CredentialFactory
from azlin.auth.auth_method import AuthMethod

@dataclass
class ChainResult:
    """Result of authentication chain execution."""
    success: bool
    method: AuthMethod
    context: Optional[AuthContext] = None
    errors: List[Tuple[AuthMethod, str]] = None

class AuthenticationChain:
    """Execute authentication with fallback chain.

    Priority order (configurable):
    1. Service principal (certificate) - if configured
    2. Service principal (secret) - if configured
    3. Managed identity - if in Azure environment
    4. Azure CLI - always available (default)
    """

    def __init__(self, auth_config: Optional[AuthConfig] = None):
        """Initialize authentication chain.

        Args:
            auth_config: Optional explicit configuration.
                        If None, uses priority-based auto-detection.
        """
        self.auth_config = auth_config
        self._chain: List[AuthMethod] = self._build_chain()

    def authenticate(self) -> ChainResult:
        """Execute authentication chain.

        Tries each method in priority order until one succeeds.
        """
        ...

    def _build_chain(self) -> List[AuthMethod]:
        """Build authentication chain based on configuration and environment."""
        ...

    def _try_method(self, method: AuthMethod) -> AuthContext:
        """Try single authentication method."""
        ...
```

**Design Rationale:**
- Chain-of-responsibility pattern for clear fallback logic
- Explicit configuration bypasses auto-detection (for scripts/CI)
- Structured result includes all attempted methods and errors
- Preserves Azure CLI as final fallback (backward compatible)

---

### Brick 7: EnhancedAzureAuthenticator
**File:** `src/azlin/auth/azure_authenticator.py`
**Responsibility:** Extended AzureAuthenticator with service principal support
**Dependencies:** All auth bricks, existing AzureAuthenticator
**Studs (Public Interface):**
```python
from azlin.azure_auth import AzureAuthenticator as BaseAuthenticator
from azlin.auth.models import AuthConfig, AuthContext
from azlin.auth.authentication_chain import AuthenticationChain

class EnhancedAzureAuthenticator(BaseAuthenticator):
    """Extended Azure authenticator with service principal support.

    Backward compatible - preserves all existing behavior.
    """

    def __init__(
        self,
        subscription_id: str | None = None,
        use_managed_identity: bool = False,
        auth_config: AuthConfig | None = None,  # NEW
    ):
        """Initialize authenticator.

        Args:
            subscription_id: Azure subscription ID
            use_managed_identity: Use managed identity (existing param)
            auth_config: Explicit auth configuration (NEW)
        """
        super().__init__(subscription_id, use_managed_identity)
        self.auth_config = auth_config
        self._auth_context: AuthContext | None = None

    def get_credentials(self) -> AzureCredentials:
        """Get Azure credentials (extended).

        NEW: Tries service principal if configured.
        EXISTING: Falls back to Azure CLI (unchanged).
        """
        # NEW: If explicit config provided, use it
        if self.auth_config:
            chain = AuthenticationChain(self.auth_config)
            result = chain.authenticate()
            if result.success:
                self._auth_context = result.context
                return self._convert_context_to_credentials(result.context)

        # EXISTING: Fall back to parent implementation (Azure CLI)
        return super().get_credentials()

    def authenticate_with_service_principal(
        self,
        client_id: str,
        tenant_id: str,
        certificate_path: str | None = None,
    ) -> AuthContext:
        """Authenticate with service principal.

        NEW method - explicit service principal authentication.
        """
        ...

    def _convert_context_to_credentials(self, context: AuthContext) -> AzureCredentials:
        """Convert AuthContext to AzureCredentials (for compatibility)."""
        ...
```

**Integration Point:** Extends existing `AzureAuthenticator` class
**Backward Compatibility:**
- Preserves all existing methods unchanged
- New parameter `auth_config` is optional (default None)
- Falls back to parent implementation when no config provided
- Existing callers see zero behavior change

**Design Rationale:**
- Inheritance preserves existing interface
- New functionality opt-in via auth_config parameter
- Clear separation: parent handles Azure CLI, child adds SP/MI
- Conversion method maintains existing AzureCredentials contract

---

### Brick 8: LogSanitizer
**File:** `src/azlin/auth/log_sanitizer.py`
**Responsibility:** Sanitize logs to prevent secret leakage
**Dependencies:** None
**Studs (Public Interface):**
```python
import re
from typing import Dict, Pattern

class LogSanitizer:
    """Sanitize sensitive data from logs.

    Security: Prevents accidental secret leakage in logs/errors.
    """

    # Patterns for sensitive data
    PATTERNS: Dict[str, Pattern] = {
        "client_secret": re.compile(
            r"(client[_-]?secret[=:\s]+)([^\s&]+)",
            re.IGNORECASE
        ),
        "password": re.compile(
            r"(password[=:\s]+)([^\s&]+)",
            re.IGNORECASE
        ),
        "authorization": re.compile(
            r"(Authorization:\s*Bearer\s+)([^\s]+)",
            re.IGNORECASE
        ),
        "access_token": re.compile(
            r"(access[_-]?token[=:\s]+)([^\s&]+)",
            re.IGNORECASE
        ),
    }

    REDACTED = "[REDACTED]"

    @classmethod
    def sanitize(cls, message: str) -> str:
        """Sanitize message by redacting sensitive patterns."""
        ...

    @classmethod
    def sanitize_dict(cls, data: dict) -> dict:
        """Sanitize dictionary values recursively."""
        ...

    @classmethod
    def sanitize_exception(cls, exc: Exception) -> str:
        """Sanitize exception message."""
        ...
```

**Security Controls:**
- Pattern-based secret detection (P0-6)
- Recursive sanitization for nested structures
- Exception message sanitization

**Design Rationale:**
- Centralized sanitization logic (DRY)
- Extensible pattern dictionary
- Used in all logging statements that touch auth data
- Fail-safe: sanitize even if pattern matching fails

---

## 2. Authentication Flow Diagrams

### Flow 1: Azure CLI Authentication (Existing - Unchanged)
```
┌─────────────┐
│   azlin     │
│  new VM     │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ AzureAuthenticator.__init__()    │
│ (no auth_config param)           │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ get_credentials()                │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Check: AZURE_* env vars?         │
└──────┬───────────────────────────┘
       │ No
       v
┌──────────────────────────────────┐
│ Check: az CLI available?         │
│ subprocess: az account           │
│             get-access-token     │
└──────┬───────────────────────────┘
       │ Yes
       v
┌──────────────────────────────────┐
│ Return AzureCredentials          │
│   method="az_cli"                │
│   token=[from az CLI]            │
│   subscription_id=[from token]   │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Proceed with VM provisioning     │
└──────────────────────────────────┘

UNCHANGED: Existing code path preserved exactly.
```

### Flow 2: Service Principal (Client Secret) - New
```
┌─────────────┐
│   User      │
│  Setup      │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ 1. Create config.toml            │
│    [auth]                        │
│    method = "sp_secret"          │
│    subscription_id = "..."       │
│    [auth.service_principal]      │
│    client_id = "..."             │
│    tenant_id = "..."             │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ 2. Set environment variable      │
│    export AZURE_CLIENT_SECRET=...│
└──────┬───────────────────────────┘
       │
       v
┌─────────────┐
│   azlin     │
│  new VM     │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ AuthConfigManager.load_auth_     │
│ config()                         │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Load [auth] from TOML            │
│ Create AuthConfig object         │
│ Validate: client_id, tenant_id   │
│           (UUID format)          │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ EnhancedAzureAuthenticator       │
│   .__init__(auth_config=config)  │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ get_credentials()                │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ CredentialFactory.create_        │
│ credential(auth_config)          │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Check: AZURE_CLIENT_SECRET set?  │
└──────┬───────────────────────────┘
       │ Yes
       v
┌──────────────────────────────────┐
│ Create ClientSecretCredential    │
│   client_id=config.client_id     │
│   client_secret=[from env]       │
│   tenant_id=config.tenant_id     │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Test credential: get token       │
│   scope="https://management...   │
└──────┬───────────────────────────┘
       │ Success
       v
┌──────────────────────────────────┐
│ Create AuthContext               │
│   authenticated=True             │
│   credential=[credential obj]    │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Convert to AzureCredentials      │
│   method="sp_secret"             │
│   subscription_id=[from config]  │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Proceed with VM provisioning     │
└──────────────────────────────────┘

ERROR PATH:
┌──────────────────────────────────┐
│ AZURE_CLIENT_SECRET not set?     │
└──────┬───────────────────────────┘
       │ No
       v
┌──────────────────────────────────┐
│ Raise CredentialFactoryError:    │
│ "Service principal secret auth   │
│  requires AZURE_CLIENT_SECRET"   │
└──────────────────────────────────┘
```

### Flow 3: Service Principal (Certificate) - New
```
┌─────────────┐
│   User      │
│  Setup      │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ 1. Upload cert to SP             │
│    az ad sp credential reset     │
│       --id <client_id>           │
│       --cert @/path/cert.pem     │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ 2. Set cert permissions          │
│    chmod 600 /path/cert.pem      │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ 3. Create config.toml            │
│    [auth]                        │
│    method = "sp_cert"            │
│    [auth.service_principal]      │
│    client_id = "..."             │
│    tenant_id = "..."             │
│    certificate_path =            │
│      "/path/cert.pem"            │
└──────┬───────────────────────────┘
       │
       v
┌─────────────┐
│   azlin     │
│  new VM     │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ AuthConfigManager.load_auth_     │
│ config()                         │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Parse [auth] section             │
│ Create CertificateInfo           │
│   certificate_path=[from TOML]   │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ CertificateInfo.__post_init__()  │
│ Validate:                        │
│   - File exists                  │
│   - Permissions 0600 or 0400     │
└──────┬───────────────────────────┘
       │ Valid
       v
┌──────────────────────────────────┐
│ CertificateValidator.validate_   │
│ certificate(cert_path)           │
│ Check:                           │
│   - Format (PEM/PFX)             │
│   - Has private key              │
└──────┬───────────────────────────┘
       │ Valid
       v
┌──────────────────────────────────┐
│ Create ServicePrincipalConfig    │
│   client_id=[from TOML]          │
│   tenant_id=[from TOML]          │
│   certificate_info=[validated]   │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ CredentialFactory.create_        │
│ credential(auth_config)          │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Create CertificateCredential     │
│   tenant_id=[from config]        │
│   client_id=[from config]        │
│   certificate_path=[from config] │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Test credential: get token       │
└──────┬───────────────────────────┘
       │ Success
       v
┌──────────────────────────────────┐
│ Proceed with VM provisioning     │
└──────────────────────────────────┘

ERROR PATH 1 - Invalid Permissions:
┌──────────────────────────────────┐
│ CertificateInfo validation       │
│ Permissions not 0600/0400?       │
└──────┬───────────────────────────┘
       │ Error
       v
┌──────────────────────────────────┐
│ Raise ValueError:                │
│ "Certificate has insecure        │
│  permissions: 0644. Expected:    │
│  0600 or 0400"                   │
│                                  │
│ User must: chmod 600 cert.pem    │
└──────────────────────────────────┘

ERROR PATH 2 - No Private Key:
┌──────────────────────────────────┐
│ CertificateValidator             │
│ No private key found?            │
└──────┬───────────────────────────┘
       │ Error
       v
┌──────────────────────────────────┐
│ Raise ValueError:                │
│ "Certificate missing private     │
│  key. Use cert with private key" │
└──────────────────────────────────┘
```

### Flow 4: Managed Identity - New
```
┌─────────────────────────┐
│   Azure VM/Container    │
│  (with MI assigned)     │
└──────┬──────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Optional: Create config.toml     │
│    [auth]                        │
│    method = "managed_identity"   │
│    [auth.managed_identity]       │
│    client_id = "..." # Optional  │
│                      # for user- │
│                      # assigned  │
└──────┬───────────────────────────┘
       │
       v
┌─────────────┐
│   azlin     │
│  new VM     │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ Detect: Running in Azure?        │
│ Check IMDS endpoint available    │
│ (169.254.169.254)                │
└──────┬───────────────────────────┘
       │ Yes
       v
┌──────────────────────────────────┐
│ AuthConfigManager.load_auth_     │
│ config()                         │
│ OR                               │
│ Auto-detect: use_managed_        │
│              identity=True       │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ CredentialFactory.create_        │
│ credential(auth_config)          │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Create ManagedIdentityCredential │
│   client_id=[from config or None]│
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Credential queries IMDS          │
│ Gets token from Azure platform   │
└──────┬───────────────────────────┘
       │ Success
       v
┌──────────────────────────────────┐
│ Proceed with VM provisioning     │
└──────────────────────────────────┘

ERROR PATH - MI Not Assigned:
┌──────────────────────────────────┐
│ ManagedIdentityCredential        │
│ IMDS returns 404/403?            │
└──────┬───────────────────────────┘
       │ Error
       v
┌──────────────────────────────────┐
│ Raise CredentialFactoryError:    │
│ "Managed identity not assigned   │
│  to this resource. Assign MI or  │
│  use different auth method."     │
└──────────────────────────────────┘
```

### Flow 5: Authentication Chain with Fallback
```
┌─────────────┐
│   azlin     │
│  new VM     │
└──────┬──────┘
       │
       v
┌──────────────────────────────────┐
│ EnhancedAzureAuthenticator       │
│   (no explicit auth_config)      │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ AuthenticationChain.__init__()   │
│ Build priority chain:            │
│ 1. Check for [auth] in config    │
│ 2. Detect Azure environment      │
│ 3. Check az CLI available        │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Chain: [sp_cert, sp_secret,      │
│         managed_identity,         │
│         azure_cli]                │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Try Method 1: sp_cert            │
└──────┬───────────────────────────┘
       │ Config not found
       v
┌──────────────────────────────────┐
│ Try Method 2: sp_secret          │
└──────┬───────────────────────────┘
       │ Config not found
       v
┌──────────────────────────────────┐
│ Try Method 3: managed_identity   │
└──────┬───────────────────────────┘
       │ Not in Azure environment
       v
┌──────────────────────────────────┐
│ Try Method 4: azure_cli          │
└──────┬───────────────────────────┘
       │ Success!
       v
┌──────────────────────────────────┐
│ Return ChainResult               │
│   success=True                   │
│   method=AuthMethod.AZURE_CLI    │
│   context=AuthContext(...)       │
│   errors=[(sp_cert, "config not  │
│            found"),...]          │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Proceed with VM provisioning     │
│ (using Azure CLI credentials)    │
└──────────────────────────────────┘

COMPLETE FAILURE PATH:
┌──────────────────────────────────┐
│ All methods failed?              │
└──────┬───────────────────────────┘
       │ Yes
       v
┌──────────────────────────────────┐
│ Return ChainResult               │
│   success=False                  │
│   method=None                    │
│   errors=[all method errors]     │
└──────┬───────────────────────────┘
       │
       v
┌──────────────────────────────────┐
│ Raise AuthenticationError:       │
│ "No authentication available:    │
│  - sp_cert: config not found     │
│  - sp_secret: config not found   │
│  - managed_identity: not in Azure│
│  - azure_cli: not logged in"     │
│                                  │
│ Suggest: az login                │
└──────────────────────────────────┘
```

---

## 3. Security Architecture

### Security Control Mapping

| Control | Priority | Implementation | Module(s) | Verification |
|---------|----------|----------------|-----------|--------------|
| **P0-1: No Secret Storage** | P0 | Client secret only from `AZURE_CLIENT_SECRET` env var. Never written to config/logs. | AuthConfigManager, LogSanitizer | Unit test: verify TOML never contains secrets |
| **P0-2: Certificate Permissions** | P0 | Validate permissions 0600/0400 in `CertificateInfo.__post_init__()` | CertificateInfo, CertificateValidator | Unit test: reject 0644, accept 0600/0400 |
| **P0-3: UUID Validation** | P0 | Validate UUID format in `__post_init__()` of all config classes | ServicePrincipalConfig, ManagedIdentityConfig, AuthConfig | Unit test: reject malformed UUIDs |
| **P0-4: Log Sanitization** | P0 | `LogSanitizer.sanitize()` called on all log messages in auth modules | LogSanitizer | Unit test: verify secrets redacted |
| **P0-5: Input Validation** | P0 | Frozen dataclasses with `__post_init__()` validation | All model classes | Unit test: invalid inputs raise ValueError |
| **P0-6: Path Validation** | P0 | Reuse `ConfigManager._validate_config_path()` for certificate paths | CertificateValidator | Unit test: reject path traversal |
| **P0-7: Secure Defaults** | P0 | Default method = `AZURE_CLI`, no auto-selection of weaker methods | AuthenticationChain | Unit test: verify default behavior |
| **P0-8: Error Messages** | P0 | Error messages never contain secrets, sanitized via LogSanitizer | All error handling | Unit test: check exception messages |
| **P0-9: Token Lifetime** | P0 | Delegate to Azure Identity SDK - credentials not cached | CredentialFactory | Integration test: tokens refresh automatically |
| **P0-10: Audit Logging** | P0 | Log authentication method used (sanitized) | EnhancedAzureAuthenticator | Integration test: verify auth method logged |

### Security Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    USER SPACE                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ~/.azlin/config.toml (0600)                          │  │
│  │ - [auth] section                                     │  │
│  │ - NO SECRETS (only references)                       │  │
│  │   ✓ client_id                                        │  │
│  │   ✓ tenant_id                                        │  │
│  │   ✓ certificate_path                                 │  │
│  │   ✗ client_secret (NEVER stored)                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Certificate File (0600/0400)                         │  │
│  │ - Validated permissions on load                      │  │
│  │ - Must contain private key                           │  │
│  │ - PEM or PFX format                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Environment Variables                                │  │
│  │ - AZURE_CLIENT_SECRET (if using SP secret auth)      │  │
│  │ - Ephemeral: cleared after azlin exits               │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                             │
                             v
┌─────────────────────────────────────────────────────────────┐
│                    AZLIN PROCESS                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ AuthConfig (in-memory)                               │  │
│  │ - Frozen dataclasses                                 │  │
│  │ - Validated on construction                          │  │
│  │ - NO SECRETS (only credential references)            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Azure Identity Credential Objects                    │  │
│  │ - Short-lived in-memory objects                      │  │
│  │ - Managed by Azure SDK                               │  │
│  │ - NOT cached by azlin                                │  │
│  │ - Tokens fetched on-demand by SDK                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Logging                                              │  │
│  │ - All auth logs sanitized                            │  │
│  │ - Secrets replaced with [REDACTED]                   │  │
│  │ - Exception messages sanitized                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                             │
                             v
┌─────────────────────────────────────────────────────────────┐
│                    AZURE IDENTITY SDK                       │
│                                                             │
│  - Handles token acquisition                                │
│  - Manages token refresh                                    │
│  - Communicates with Azure AD                               │
│  - NOT controlled by azlin (delegated)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                             │
                             v
┌─────────────────────────────────────────────────────────────┐
│                    AZURE AD / IMDS                          │
│                                                             │
│  - Validates credentials                                    │
│  - Issues access tokens                                     │
│  - Enforces RBAC                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Secret Handling Strategy

**Client Secret (for SP Secret Auth):**
1. **Source:** `AZURE_CLIENT_SECRET` environment variable ONLY
2. **Never:** Written to config file
3. **Never:** Logged (sanitized by LogSanitizer)
4. **Never:** Cached by azlin
5. **Lifetime:** Only exists in environment during azlin execution
6. **Alternatives:** Azure Key Vault (future enhancement)

**Certificate (for SP Cert Auth):**
1. **Source:** File path in config (`certificate_path`)
2. **Permissions:** MUST be 0600 or 0400 (validated on load)
3. **Format:** PEM or PFX with private key
4. **Validation:** Checked before credential creation
5. **Recommendation:** Store in `~/.azlin/certs/` (secure directory)

**Tokens:**
1. **Never stored by azlin** - delegated to Azure Identity SDK
2. SDK manages token cache securely (OS keychain on macOS)
3. Tokens automatically refreshed by SDK
4. Azlin never sees raw token values (opaque credential objects)

---

## 4. Integration Strategy

### 4.1 File Modifications Required

#### File: `src/azlin/azure_auth.py`
**Change Type:** Extension
**Modifications:**
1. Import new auth modules at top
2. Add `EnhancedAzureAuthenticator` class (extends `AzureAuthenticator`)
3. **No changes to existing `AzureAuthenticator` class**

**Backward Compatibility:** ✓ Complete
- Existing code uses `AzureAuthenticator` (unchanged)
- New code can opt-in to `EnhancedAzureAuthenticator`
- Migration path: change import, add `auth_config` parameter

#### File: `src/azlin/config_manager.py`
**Change Type:** Extension
**Modifications:**
1. Import auth config types
2. Add `AuthConfigManager` class methods
3. **No changes to existing `ConfigManager` methods**
4. Optional: Update `AzlinConfig` to include `auth_method` field

**Backward Compatibility:** ✓ Complete
- Existing config files work unchanged (no [auth] section)
- New [auth] section is optional
- Config loading handles missing [auth] section gracefully

#### File: `src/azlin/cli.py`
**Change Type:** Minor Extension
**Modifications:**
1. Import `AuthConfigManager`
2. In `CLIOrchestrator.__init__()`:
   ```python
   # NEW: Load auth config if present
   self.auth_config = AuthConfigManager.load_auth_config(config_path)

   # MODIFIED: Pass auth_config to authenticator
   self.authenticator = EnhancedAzureAuthenticator(
       subscription_id=subscription_id,
       use_managed_identity=use_managed_identity,
       auth_config=self.auth_config,  # NEW parameter
   )
   ```
3. Add optional CLI flag: `--auth-method` (for explicit method selection)

**Backward Compatibility:** ✓ Complete
- All existing CLI commands work unchanged
- `auth_config` parameter defaults to `None` (uses Azure CLI)
- New `--auth-method` flag is optional

#### File: `pyproject.toml`
**Change Type:** Dependency Addition
**Modifications:**
```toml
dependencies = [
    "anthropic>=0.40.0",
    "azure-identity>=1.15.0",  # NEW
    "click>=8.1.0",
    "pyyaml>=6.0.0",
    "rich>=13.7.0",
    "tomli>=2.0.0; python_version < '3.11'",
    "tomli-w>=1.0.0",
]
```

**Backward Compatibility:** ✓ Complete
- `azure-identity` is new dependency (install required)
- All existing dependencies unchanged

### 4.2 New Files to Create

```
src/azlin/auth/
├── __init__.py                    # Package exports
├── auth_method.py                 # Brick 1: AuthMethod enum
├── models.py                      # Brick 2: Data models
├── config_manager.py              # Brick 3: TOML config handling
├── certificate_validator.py       # Brick 4: Certificate validation
├── credential_factory.py          # Brick 5: Azure SDK credential factory
├── authentication_chain.py        # Brick 6: Fallback chain
├── azure_authenticator.py         # Brick 7: Enhanced authenticator
└── log_sanitizer.py               # Brick 8: Secret sanitization

tests/unit/auth/
├── __init__.py
├── test_auth_method.py            # Test enum
├── test_models.py                 # Test data models
├── test_config_manager.py         # Test TOML operations
├── test_certificate_validator.py  # Test cert validation
├── test_credential_factory.py     # Test credential creation
├── test_authentication_chain.py   # Test fallback logic
├── test_azure_authenticator.py    # Test enhanced authenticator
└── test_log_sanitizer.py          # Test sanitization

tests/integration/auth/
├── __init__.py
├── test_sp_secret_auth.py         # Integration test: SP secret flow
├── test_sp_cert_auth.py           # Integration test: SP cert flow
├── test_managed_identity.py       # Integration test: MI flow
├── test_fallback_chain.py         # Integration test: fallback behavior
└── test_backward_compatibility.py # Integration test: existing behavior

tests/security/auth/
├── __init__.py
├── test_secret_leakage.py         # Security test: no secrets in logs
├── test_certificate_permissions.py # Security test: permission enforcement
└── test_path_traversal.py         # Security test: path validation
```

### 4.3 Migration Guide for Existing Code

**For azlin maintainers updating code:**

**Before:**
```python
from azlin.azure_auth import AzureAuthenticator

auth = AzureAuthenticator(subscription_id=sub_id)
creds = auth.get_credentials()
```

**After (with service principal support):**
```python
from azlin.auth.azure_authenticator import EnhancedAzureAuthenticator
from azlin.auth.config_manager import AuthConfigManager

# Load auth config (returns None if not configured)
auth_config = AuthConfigManager.load_auth_config()

# Create authenticator (backward compatible)
auth = EnhancedAzureAuthenticator(
    subscription_id=sub_id,
    auth_config=auth_config,  # NEW: None = use Azure CLI (existing behavior)
)
creds = auth.get_credentials()
```

**For users configuring service principal authentication:**

**Step 1: Create service principal**
```bash
az ad sp create-for-rbac \
  --name azlin-automation \
  --role Contributor \
  --scopes /subscriptions/{subscription-id}
```

**Step 2: Configure azlin**

Option A - Client Secret:
```bash
# Edit ~/.azlin/config.toml
[auth]
method = "sp_secret"
subscription_id = "..."

[auth.service_principal]
client_id = "..."
tenant_id = "..."

# Set secret in environment
export AZURE_CLIENT_SECRET="..."

# Run azlin
azlin new my-vm
```

Option B - Certificate:
```bash
# Generate certificate
openssl req -x509 -newkey rsa:4096 -keyout cert.pem -out cert.pem -days 365 -nodes

# Upload to service principal
az ad sp credential reset --id {client_id} --cert @cert.pem

# Secure certificate file
chmod 600 ~/.azlin/certs/sp-cert.pem

# Edit ~/.azlin/config.toml
[auth]
method = "sp_cert"
subscription_id = "..."

[auth.service_principal]
client_id = "..."
tenant_id = "..."
certificate_path = "/Users/username/.azlin/certs/sp-cert.pem"

# Run azlin
azlin new my-vm
```

---

## 5. Error Handling Taxonomy

### Exception Hierarchy

```
Exception
│
├── AzlinError (existing base)
│   │
│   ├── AuthenticationError (existing)
│   │   │
│   │   ├── CredentialFactoryError (NEW)
│   │   │   ├── ClientSecretMissingError
│   │   │   ├── CertificateNotFoundError
│   │   │   └── ManagedIdentityNotAvailableError
│   │   │
│   │   ├── CertificateValidationError (NEW)
│   │   │   ├── CertificatePermissionError
│   │   │   ├── CertificateFormatError
│   │   │   └── CertificateMissingPrivateKeyError
│   │   │
│   │   ├── AuthConfigError (NEW)
│   │   │   ├── InvalidClientIdError
│   │   │   ├── InvalidTenantIdError
│   │   │   └── InvalidSubscriptionIdError
│   │   │
│   │   └── AuthenticationChainError (NEW)
│   │       └── NoAuthMethodAvailableError
│   │
│   └── ConfigError (existing)
│       └── AuthConfigSectionError (NEW)
│
└── ValueError (stdlib)
    └── (Used for validation errors in __post_init__)
```

### Error Handling Strategy by Module

#### Brick 1-2: AuthMethod, Models
**Strategy:** Fail-fast with ValueError
**Rationale:** Invalid configuration should never reach runtime
**User Action:** Fix config file, check UUID formats

**Example:**
```python
# Invalid client_id
try:
    config = ServicePrincipalConfig(
        client_id="not-a-uuid",
        tenant_id="...",
    )
except ValueError as e:
    print(f"Configuration error: {e}")
    # Output: Configuration error: Invalid client_id format: not-a-uuid
```

#### Brick 3: AuthConfigManager
**Strategy:** Graceful degradation
**Rationale:** Missing [auth] section is valid (use Azure CLI)
**User Action:** None (defaults to Azure CLI) or add [auth] section

**Example:**
```python
# Config file has no [auth] section
auth_config = AuthConfigManager.load_auth_config()
# Returns: None (not an error)

# Config file has invalid [auth] section
try:
    auth_config = AuthConfigManager.load_auth_config()
except ConfigError as e:
    print(f"Invalid auth configuration: {e}")
    # Output: Invalid auth configuration: [auth] section missing required field: method
```

#### Brick 4: CertificateValidator
**Strategy:** Fail-fast with detailed error
**Rationale:** Certificate issues must be fixed before attempting auth
**User Action:** Fix permissions, use correct format, include private key

**Example:**
```python
# Certificate has wrong permissions
try:
    validation = CertificateValidator.validate_certificate(cert_path)
    if not validation.valid:
        print(f"Certificate validation failed: {validation.error}")
except CertificateValidationError as e:
    print(f"Certificate error: {e}")
    print(f"Fix: chmod 600 {cert_path}")
```

#### Brick 5: CredentialFactory
**Strategy:** Fail with actionable error message
**Rationale:** Credential creation failure indicates missing setup
**User Action:** Set environment variable, assign managed identity, or use different method

**Example:**
```python
# Client secret not in environment
try:
    credential = CredentialFactory.create_credential(auth_config)
except ClientSecretMissingError as e:
    print(f"Authentication failed: {e}")
    # Output: Authentication failed: Service principal secret authentication requires
    #         AZURE_CLIENT_SECRET environment variable.
    print("Fix: export AZURE_CLIENT_SECRET=your-secret")
```

#### Brick 6: AuthenticationChain
**Strategy:** Try-all, collect errors, fail with comprehensive message
**Rationale:** User needs to know why all methods failed
**User Action:** Configure at least one auth method

**Example:**
```python
# All auth methods failed
result = chain.authenticate()
if not result.success:
    print("Authentication failed. Attempted methods:")
    for method, error in result.errors:
        print(f"  - {method}: {error}")
    # Output:
    # Authentication failed. Attempted methods:
    #   - sp_cert: [auth] section not found in config
    #   - sp_secret: [auth] section not found in config
    #   - managed_identity: Not running in Azure environment
    #   - azure_cli: Not logged in (run: az login)
    print("\nRecommendation: Run 'az login' or configure service principal")
```

#### Brick 7: EnhancedAzureAuthenticator
**Strategy:** Fallback to parent (Azure CLI) on failure
**Rationale:** Preserve existing behavior, always try Azure CLI
**User Action:** None (Azure CLI fallback) or fix configured method

**Example:**
```python
# Service principal auth fails, falls back to Azure CLI
auth = EnhancedAzureAuthenticator(auth_config=sp_config)
try:
    creds = auth.get_credentials()
    # If SP auth fails, automatically tries Azure CLI
    print(f"Authenticated via: {creds.method}")
    # Output: Authenticated via: azure_cli
except AuthenticationError as e:
    # Only raised if ALL methods fail (including Azure CLI)
    print(f"All authentication methods failed: {e}")
```

#### Brick 8: LogSanitizer
**Strategy:** Best-effort sanitization, never fail
**Rationale:** Logging errors should not break the application
**User Action:** None (transparent)

**Example:**
```python
# Sanitization always succeeds
try:
    message = "Client secret: abc123xyz"
    sanitized = LogSanitizer.sanitize(message)
    logger.info(sanitized)
    # Log output: Client secret: [REDACTED]
except Exception:
    # Never happens - sanitizer catches all exceptions
    pass
```

### Error Message Guidelines

**Good Error Messages:**
```
✓ "Certificate has insecure permissions: 0644. Expected: 0600 or 0400.
   Fix: chmod 600 /path/to/cert.pem"

✓ "Service principal secret authentication requires AZURE_CLIENT_SECRET environment variable.
   Set it with: export AZURE_CLIENT_SECRET=your-secret"

✓ "Invalid client_id format: not-a-uuid. Expected: UUID format like
   'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'"
```

**Bad Error Messages:**
```
✗ "Authentication failed"  (too vague)
✗ "Invalid config"  (no details)
✗ "Error: 401"  (no context)
```

**Error Message Template:**
```
{What went wrong} [: {specific details}].
{Expected/Required: what should be}[.
{Action: how to fix}]
```

---

## 6. Data Model Complete Definitions

### AuthMethod Enum
```python
"""Authentication method enumeration."""
from enum import Enum

class AuthMethod(str, Enum):
    """Authentication method for Azure.

    Priority order (in fallback chain):
    1. SERVICE_PRINCIPAL_CERT - highest security
    2. SERVICE_PRINCIPAL_SECRET - requires secret management
    3. MANAGED_IDENTITY - for Azure-hosted workloads
    4. AZURE_CLI - default, backward compatible
    """

    AZURE_CLI = "azure_cli"
    SERVICE_PRINCIPAL_SECRET = "sp_secret"
    SERVICE_PRINCIPAL_CERT = "sp_cert"
    MANAGED_IDENTITY = "managed_identity"

    def __str__(self) -> str:
        """String representation for logging."""
        names = {
            "azure_cli": "Azure CLI",
            "sp_secret": "Service Principal (Secret)",
            "sp_cert": "Service Principal (Certificate)",
            "managed_identity": "Managed Identity",
        }
        return names[self.value]

    @property
    def requires_config(self) -> bool:
        """Whether this method requires [auth] config section."""
        return self != AuthMethod.AZURE_CLI

    @property
    def requires_secret(self) -> bool:
        """Whether this method requires AZURE_CLIENT_SECRET."""
        return self == AuthMethod.SERVICE_PRINCIPAL_SECRET

    @property
    def requires_certificate(self) -> bool:
        """Whether this method requires certificate file."""
        return self == AuthMethod.SERVICE_PRINCIPAL_CERT
```

### Complete Type Definitions
```python
"""Complete type definitions for authentication."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List, Tuple
import re

# UUID validation regex (used across all models)
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE
)

def validate_uuid(value: str, field_name: str) -> None:
    """Validate UUID format.

    Raises:
        ValueError: If not valid UUID
    """
    if not UUID_PATTERN.match(value):
        raise ValueError(
            f"Invalid {field_name} format: {value}. "
            f"Expected UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        )

@dataclass(frozen=True)
class CertificateInfo:
    """Certificate metadata for authentication.

    Security:
    - Only stores path, not certificate data
    - Validates permissions on construction
    - Thumbprint optional (for validation, not required for auth)
    """
    certificate_path: Path
    thumbprint: Optional[str] = None

    def __post_init__(self):
        """Validate certificate file."""
        # Ensure path is Path object
        if isinstance(self.certificate_path, str):
            object.__setattr__(self, 'certificate_path', Path(self.certificate_path))

        # Check existence
        if not self.certificate_path.exists():
            raise ValueError(f"Certificate not found: {self.certificate_path}")

        # Check permissions (0600 or 0400)
        mode = self.certificate_path.stat().st_mode & 0o777
        if mode not in (0o600, 0o400):
            raise ValueError(
                f"Certificate has insecure permissions: {oct(mode)}. "
                f"Expected: 0600 or 0400. "
                f"Fix: chmod 600 {self.certificate_path}"
            )

        # Validate thumbprint format if provided
        if self.thumbprint:
            # Thumbprint should be 40 hex characters (SHA-1) or 64 hex characters (SHA-256)
            if not re.match(r'^[0-9a-f]{40}$|^[0-9a-f]{64}$', self.thumbprint, re.IGNORECASE):
                raise ValueError(
                    f"Invalid certificate thumbprint format: {self.thumbprint}. "
                    f"Expected: 40 (SHA-1) or 64 (SHA-256) hex characters"
                )

@dataclass(frozen=True)
class ServicePrincipalConfig:
    """Service principal configuration.

    Security:
    - No client_secret field (must come from environment)
    - Validates UUID formats
    - Certificate info validated separately
    """
    client_id: str
    tenant_id: str
    certificate_info: Optional[CertificateInfo] = None

    def __post_init__(self):
        """Validate UUIDs."""
        validate_uuid(self.client_id, "client_id")
        validate_uuid(self.tenant_id, "tenant_id")

@dataclass(frozen=True)
class ManagedIdentityConfig:
    """Managed identity configuration.

    For system-assigned MI: client_id is None
    For user-assigned MI: client_id is the identity's client ID
    """
    client_id: Optional[str] = None

    def __post_init__(self):
        """Validate client_id if provided."""
        if self.client_id:
            validate_uuid(self.client_id, "client_id")

@dataclass(frozen=True)
class AuthConfig:
    """Complete authentication configuration.

    Invariants:
    - Exactly one of sp_config/mi_config set for non-CLI methods
    - Certificate required for cert-based auth
    - All UUIDs validated
    """
    method: AuthMethod
    subscription_id: str
    sp_config: Optional[ServicePrincipalConfig] = None
    mi_config: Optional[ManagedIdentityConfig] = None

    def __post_init__(self):
        """Validate configuration consistency."""
        # Validate subscription_id
        validate_uuid(self.subscription_id, "subscription_id")

        # Validate method-specific config presence
        if self.method in (AuthMethod.SERVICE_PRINCIPAL_SECRET,
                          AuthMethod.SERVICE_PRINCIPAL_CERT):
            if not self.sp_config:
                raise ValueError(
                    f"{self.method} requires service_principal configuration. "
                    f"Provide sp_config parameter."
                )

        if self.method == AuthMethod.MANAGED_IDENTITY:
            if not self.mi_config:
                raise ValueError(
                    f"{self.method} requires managed_identity configuration. "
                    f"Provide mi_config parameter."
                )

        # Validate certificate for cert-based auth
        if self.method == AuthMethod.SERVICE_PRINCIPAL_CERT:
            if not self.sp_config or not self.sp_config.certificate_info:
                raise ValueError(
                    "Certificate authentication requires certificate_info in sp_config"
                )

        # Ensure Azure CLI method has no extra config
        if self.method == AuthMethod.AZURE_CLI:
            if self.sp_config or self.mi_config:
                raise ValueError(
                    "Azure CLI authentication should not have sp_config or mi_config"
                )

@dataclass
class AuthContext:
    """Runtime authentication context (mutable).

    Tracks authentication state during operations.
    """
    config: AuthConfig
    credential: Any  # Azure Identity credential object
    authenticated: bool = False
    error: Optional[str] = None
    method_used: Optional[AuthMethod] = None

    def mark_authenticated(self, method: AuthMethod) -> None:
        """Mark authentication successful."""
        self.authenticated = True
        self.error = None
        self.method_used = method

    def mark_failed(self, error: str) -> None:
        """Mark authentication failed."""
        self.authenticated = False
        self.error = error
        self.method_used = None

    def __repr__(self) -> str:
        """Safe repr (no credential details)."""
        return (
            f"AuthContext("
            f"method={self.config.method}, "
            f"authenticated={self.authenticated}, "
            f"error={self.error})"
        )

@dataclass
class ChainResult:
    """Result of authentication chain execution."""
    success: bool
    method: Optional[AuthMethod] = None
    context: Optional[AuthContext] = None
    errors: List[Tuple[AuthMethod, str]] = field(default_factory=list)

    def add_error(self, method: AuthMethod, error: str) -> None:
        """Record authentication failure for a method."""
        self.errors.append((method, error))

    def get_error_summary(self) -> str:
        """Get formatted error summary."""
        if not self.errors:
            return "No errors"

        lines = ["Authentication failed. Attempted methods:"]
        for method, error in self.errors:
            lines.append(f"  - {method}: {error}")

        return "\n".join(lines)

@dataclass
class CertificateValidation:
    """Certificate validation result."""
    valid: bool
    format: str  # "PEM", "PFX", "unknown"
    has_private_key: bool
    permissions_ok: bool
    error: Optional[str] = None

    @property
    def can_authenticate(self) -> bool:
        """Whether certificate can be used for authentication."""
        return self.valid and self.has_private_key and self.permissions_ok
```

---

## 7. Testing Strategy

### Test Coverage Goals

| Component | Unit Tests | Integration Tests | Security Tests | Target Coverage |
|-----------|-----------|------------------|----------------|-----------------|
| AuthMethod | ✓ | - | - | 100% |
| Models (CertificateInfo, ServicePrincipalConfig, etc.) | ✓ | - | ✓ | 95% |
| AuthConfigManager | ✓ | ✓ | ✓ | 90% |
| CertificateValidator | ✓ | - | ✓ | 95% |
| CredentialFactory | ✓ | ✓ | - | 85% |
| AuthenticationChain | ✓ | ✓ | - | 90% |
| EnhancedAzureAuthenticator | ✓ | ✓ | - | 85% |
| LogSanitizer | ✓ | - | ✓ | 100% |
| **Overall** | **Required** | **Required** | **Required** | **>90%** |

### Unit Test Matrix

#### Brick 1: AuthMethod
```python
def test_auth_method_string_values():
    """Test enum string values match expected."""
    assert AuthMethod.AZURE_CLI.value == "azure_cli"
    assert AuthMethod.SERVICE_PRINCIPAL_SECRET.value == "sp_secret"

def test_auth_method_str_representation():
    """Test human-readable string representation."""
    assert str(AuthMethod.AZURE_CLI) == "Azure CLI"
    assert str(AuthMethod.SERVICE_PRINCIPAL_CERT) == "Service Principal (Certificate)"

def test_auth_method_requires_config():
    """Test requires_config property."""
    assert not AuthMethod.AZURE_CLI.requires_config
    assert AuthMethod.SERVICE_PRINCIPAL_SECRET.requires_config

def test_auth_method_requires_secret():
    """Test requires_secret property."""
    assert AuthMethod.SERVICE_PRINCIPAL_SECRET.requires_secret
    assert not AuthMethod.SERVICE_PRINCIPAL_CERT.requires_secret

def test_auth_method_requires_certificate():
    """Test requires_certificate property."""
    assert AuthMethod.SERVICE_PRINCIPAL_CERT.requires_certificate
    assert not AuthMethod.SERVICE_PRINCIPAL_SECRET.requires_certificate
```

#### Brick 2: Models
```python
def test_certificate_info_valid(tmp_path):
    """Test CertificateInfo with valid certificate."""
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("DUMMY CERT")
    cert_path.chmod(0o600)

    cert_info = CertificateInfo(certificate_path=cert_path)
    assert cert_info.certificate_path == cert_path

def test_certificate_info_insecure_permissions(tmp_path):
    """Test CertificateInfo rejects insecure permissions."""
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("DUMMY CERT")
    cert_path.chmod(0o644)  # Insecure

    with pytest.raises(ValueError, match="insecure permissions"):
        CertificateInfo(certificate_path=cert_path)

def test_certificate_info_missing_file():
    """Test CertificateInfo rejects missing file."""
    with pytest.raises(ValueError, match="not found"):
        CertificateInfo(certificate_path=Path("/nonexistent/cert.pem"))

def test_service_principal_config_valid():
    """Test ServicePrincipalConfig with valid UUIDs."""
    config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    assert config.client_id
    assert config.tenant_id

def test_service_principal_config_invalid_client_id():
    """Test ServicePrincipalConfig rejects invalid client_id."""
    with pytest.raises(ValueError, match="Invalid client_id"):
        ServicePrincipalConfig(
            client_id="not-a-uuid",
            tenant_id="87654321-4321-4321-4321-210987654321",
        )

def test_service_principal_config_invalid_tenant_id():
    """Test ServicePrincipalConfig rejects invalid tenant_id."""
    with pytest.raises(ValueError, match="Invalid tenant_id"):
        ServicePrincipalConfig(
            client_id="12345678-1234-1234-1234-123456789012",
            tenant_id="not-a-uuid",
        )

def test_auth_config_sp_secret_valid():
    """Test AuthConfig for SP secret auth."""
    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )
    assert auth_config.method == AuthMethod.SERVICE_PRINCIPAL_SECRET

def test_auth_config_sp_secret_missing_config():
    """Test AuthConfig rejects SP auth without sp_config."""
    with pytest.raises(ValueError, match="requires service_principal configuration"):
        AuthConfig(
            method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
            subscription_id="11111111-1111-1111-1111-111111111111",
        )

def test_auth_config_sp_cert_missing_certificate():
    """Test AuthConfig rejects cert auth without certificate."""
    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
        # No certificate_info
    )
    with pytest.raises(ValueError, match="requires certificate_info"):
        AuthConfig(
            method=AuthMethod.SERVICE_PRINCIPAL_CERT,
            subscription_id="11111111-1111-1111-1111-111111111111",
            sp_config=sp_config,
        )
```

#### Brick 3: AuthConfigManager
```python
def test_load_auth_config_missing_section(tmp_path):
    """Test loading config without [auth] section returns None."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("[general]\nkey = 'value'\n")

    auth_config = AuthConfigManager.load_auth_config(str(config_file))
    assert auth_config is None

def test_load_auth_config_sp_secret(tmp_path):
    """Test loading SP secret config from TOML."""
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[auth]
method = "sp_secret"
subscription_id = "11111111-1111-1111-1111-111111111111"

[auth.service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
""")

    auth_config = AuthConfigManager.load_auth_config(str(config_file))
    assert auth_config.method == AuthMethod.SERVICE_PRINCIPAL_SECRET
    assert auth_config.sp_config.client_id == "12345678-1234-1234-1234-123456789012"

def test_save_auth_config_sp_secret(tmp_path):
    """Test saving SP secret config to TOML."""
    config_file = tmp_path / "config.toml"

    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )

    AuthConfigManager.save_auth_config(auth_config, str(config_file))

    # Verify file contents
    content = config_file.read_text()
    assert "[auth]" in content
    assert "method = \"sp_secret\"" in content
    assert "12345678-1234-1234-1234-123456789012" in content

def test_save_auth_config_no_secrets(tmp_path):
    """Test saved config never contains secrets."""
    config_file = tmp_path / "config.toml"

    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )

    AuthConfigManager.save_auth_config(auth_config, str(config_file))

    content = config_file.read_text()
    assert "client_secret" not in content.lower()
    assert "secret" not in content  # No secret field at all
```

#### Brick 4: CertificateValidator
```python
def test_validate_certificate_valid_pem(tmp_path):
    """Test validation of valid PEM certificate."""
    cert_path = tmp_path / "cert.pem"
    # Create valid PEM with private key
    cert_path.write_text("""
-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...
-----END PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRbKjMA0GCSqGSIb3DQEBBQUA...
-----END CERTIFICATE-----
""")
    cert_path.chmod(0o600)

    validation = CertificateValidator.validate_certificate(cert_path)
    assert validation.valid
    assert validation.format == "PEM"
    assert validation.has_private_key
    assert validation.permissions_ok

def test_validate_certificate_insecure_permissions(tmp_path):
    """Test validation fails for insecure permissions."""
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("DUMMY CERT")
    cert_path.chmod(0o644)

    validation = CertificateValidator.validate_certificate(cert_path)
    assert not validation.permissions_ok
    assert not validation.can_authenticate

def test_validate_certificate_no_private_key(tmp_path):
    """Test validation fails for cert without private key."""
    cert_path = tmp_path / "cert.pem"
    # Only certificate, no private key
    cert_path.write_text("""
-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKL0UG+mRbKjMA0GCSqGSIb3DQEBBQUA...
-----END CERTIFICATE-----
""")
    cert_path.chmod(0o600)

    validation = CertificateValidator.validate_certificate(cert_path)
    assert not validation.has_private_key
    assert not validation.can_authenticate
```

#### Brick 5: CredentialFactory
```python
def test_create_credential_azure_cli():
    """Test creating Azure CLI credential."""
    auth_config = AuthConfig(
        method=AuthMethod.AZURE_CLI,
        subscription_id="11111111-1111-1111-1111-111111111111",
    )

    credential = CredentialFactory.create_credential(auth_config)
    assert isinstance(credential, AzureCliCredential)

def test_create_credential_sp_secret_with_env_var(monkeypatch):
    """Test creating SP secret credential with env var."""
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-secret")

    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )

    credential = CredentialFactory.create_credential(auth_config)
    assert isinstance(credential, ClientSecretCredential)

def test_create_credential_sp_secret_missing_env_var():
    """Test SP secret credential fails without env var."""
    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )

    with pytest.raises(ClientSecretMissingError, match="AZURE_CLIENT_SECRET"):
        CredentialFactory.create_credential(auth_config)

def test_create_credential_sp_cert(tmp_path):
    """Test creating SP cert credential."""
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("DUMMY CERT WITH PRIVATE KEY")
    cert_path.chmod(0o600)

    cert_info = CertificateInfo(certificate_path=cert_path)
    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
        certificate_info=cert_info,
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_CERT,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )

    credential = CredentialFactory.create_credential(auth_config)
    assert isinstance(credential, CertificateCredential)
```

#### Brick 8: LogSanitizer
```python
def test_sanitize_client_secret():
    """Test sanitization of client_secret."""
    message = "Connecting with client_secret=abc123xyz"
    sanitized = LogSanitizer.sanitize(message)
    assert sanitized == "Connecting with client_secret=[REDACTED]"

def test_sanitize_password():
    """Test sanitization of password."""
    message = "Login failed: password=secret123"
    sanitized = LogSanitizer.sanitize(message)
    assert sanitized == "Login failed: password=[REDACTED]"

def test_sanitize_authorization_header():
    """Test sanitization of Authorization header."""
    message = "Request: Authorization: Bearer eyJ0eXAiOiJKV1..."
    sanitized = LogSanitizer.sanitize(message)
    assert sanitized == "Request: Authorization: Bearer [REDACTED]"

def test_sanitize_multiple_secrets():
    """Test sanitization of multiple secrets in one message."""
    message = "Auth: client_secret=abc password=xyz token=123"
    sanitized = LogSanitizer.sanitize(message)
    assert "abc" not in sanitized
    assert "xyz" not in sanitized
    assert "123" not in sanitized
    assert sanitized.count("[REDACTED]") == 3

def test_sanitize_dict_recursive():
    """Test recursive sanitization of nested dict."""
    data = {
        "config": {
            "client_secret": "abc123",
            "tenant_id": "valid-uuid",
        },
        "password": "secret",
    }
    sanitized = LogSanitizer.sanitize_dict(data)
    assert sanitized["config"]["client_secret"] == "[REDACTED]"
    assert sanitized["config"]["tenant_id"] == "valid-uuid"
    assert sanitized["password"] == "[REDACTED]"

def test_sanitize_exception():
    """Test sanitization of exception messages."""
    exc = ValueError("Authentication failed: client_secret=abc123")
    sanitized = LogSanitizer.sanitize_exception(exc)
    assert "abc123" not in sanitized
    assert "[REDACTED]" in sanitized
```

### Integration Test Strategy

#### Test: Service Principal Secret Flow (End-to-End)
```python
@pytest.mark.integration
def test_sp_secret_auth_flow(tmp_path, monkeypatch):
    """Integration test: Complete SP secret auth flow."""
    # Setup config file
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[auth]
method = "sp_secret"
subscription_id = "11111111-1111-1111-1111-111111111111"

[auth.service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
""")

    # Set environment variable
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "test-secret")

    # Load config
    auth_config = AuthConfigManager.load_auth_config(str(config_file))
    assert auth_config is not None

    # Create authenticator
    auth = EnhancedAzureAuthenticator(auth_config=auth_config)

    # Get credentials (mocked Azure SDK)
    with patch('azure.identity.ClientSecretCredential') as mock_cred:
        mock_cred.return_value.get_token.return_value = Mock(token="fake-token")

        creds = auth.get_credentials()
        assert creds.method == "sp_secret"
```

#### Test: Certificate Validation Integration
```python
@pytest.mark.integration
def test_certificate_auth_validation_flow(tmp_path):
    """Integration test: Certificate validation through auth flow."""
    # Create certificate with wrong permissions
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("DUMMY CERT")
    cert_path.chmod(0o644)  # Insecure

    # Config references this cert
    config_file = tmp_path / "config.toml"
    config_file.write_text(f"""
[auth]
method = "sp_cert"
subscription_id = "11111111-1111-1111-1111-111111111111"

[auth.service_principal]
client_id = "12345678-1234-1234-1234-123456789012"
tenant_id = "87654321-4321-4321-4321-210987654321"
certificate_path = "{cert_path}"
""")

    # Loading should fail due to permissions
    with pytest.raises(ValueError, match="insecure permissions"):
        AuthConfigManager.load_auth_config(str(config_file))
```

#### Test: Fallback Chain Behavior
```python
@pytest.mark.integration
def test_authentication_chain_fallback(monkeypatch):
    """Integration test: Chain falls back to Azure CLI."""
    # No config file, no managed identity
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)

    # Mock Azure CLI as available
    with patch('shutil.which', return_value="/usr/local/bin/az"):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"accessToken": "fake-token", "subscription": "sub-id"}'
            )

            auth = EnhancedAzureAuthenticator()
            creds = auth.get_credentials()

            # Should fall back to Azure CLI
            assert creds.method == "az_cli"
```

### Security Test Strategy

#### Test: No Secrets in Config File
```python
@pytest.mark.security
def test_no_secrets_written_to_config(tmp_path):
    """Security test: Verify secrets never written to config."""
    config_file = tmp_path / "config.toml"

    # Create config with SP secret auth
    sp_config = ServicePrincipalConfig(
        client_id="12345678-1234-1234-1234-123456789012",
        tenant_id="87654321-4321-4321-4321-210987654321",
    )
    auth_config = AuthConfig(
        method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
        subscription_id="11111111-1111-1111-1111-111111111111",
        sp_config=sp_config,
    )

    AuthConfigManager.save_auth_config(auth_config, str(config_file))

    # Read file and verify no secrets
    content = config_file.read_text().lower()
    forbidden_keywords = ["secret", "password", "token", "key"]
    for keyword in forbidden_keywords:
        assert keyword not in content, f"Found forbidden keyword: {keyword}"

@pytest.mark.security
def test_certificate_permissions_enforced(tmp_path):
    """Security test: Certificate permissions enforced."""
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("DUMMY CERT")

    # Test all permission combinations
    insecure_perms = [0o644, 0o755, 0o777, 0o604, 0o640]
    for perm in insecure_perms:
        cert_path.chmod(perm)
        with pytest.raises(ValueError, match="insecure permissions"):
            CertificateInfo(certificate_path=cert_path)

    # Test secure permissions
    secure_perms = [0o600, 0o400]
    for perm in secure_perms:
        cert_path.chmod(perm)
        # Should not raise
        CertificateInfo(certificate_path=cert_path)

@pytest.mark.security
def test_log_sanitization_comprehensive():
    """Security test: All secret patterns sanitized."""
    test_cases = [
        ("client_secret=abc123", "[REDACTED]"),
        ("CLIENT_SECRET=abc123", "[REDACTED]"),
        ("password: secret", "[REDACTED]"),
        ("Authorization: Bearer token123", "[REDACTED]"),
        ("access_token=xyz789", "[REDACTED]"),
        # Nested in JSON
        ('{"client_secret": "abc123"}', "[REDACTED]"),
    ]

    for message, expected_redaction in test_cases:
        sanitized = LogSanitizer.sanitize(message)
        assert expected_redaction in sanitized
        # Verify original secret not present
        secret_value = message.split("=")[-1].split('"')[-2]
        assert secret_value not in sanitized
```

---

## 8. Implementation Order (Dependency-Aware)

### Phase 1: Foundation (No Dependencies)
**Order:** 1 → 2 → 3
**Duration:** 1-2 days

1. **Brick 1: AuthMethod** (30 min)
   - Create `src/azlin/auth/auth_method.py`
   - Implement enum
   - Write unit tests
   - No dependencies

2. **Brick 8: LogSanitizer** (2 hours)
   - Create `src/azlin/auth/log_sanitizer.py`
   - Implement sanitization patterns
   - Write comprehensive unit tests (all patterns)
   - Write security tests
   - No dependencies

3. **Brick 2: Data Models** (3-4 hours)
   - Create `src/azlin/auth/models.py`
   - Implement all dataclasses with validation
   - Write unit tests (validation, frozen, errors)
   - Depends on: AuthMethod
   - **Checkpoint:** All P0 validation controls implemented

### Phase 2: Configuration Layer (Depends on Models)
**Order:** 4 → 5
**Duration:** 2-3 days

4. **Brick 4: CertificateValidator** (3-4 hours)
   - Create `src/azlin/auth/certificate_validator.py`
   - Implement validation logic
   - Write unit tests
   - Write security tests (permissions)
   - Depends on: Models (CertificateInfo)

5. **Brick 3: AuthConfigManager** (4-6 hours)
   - Create `src/azlin/auth/config_manager.py`
   - Implement TOML load/save
   - Write unit tests
   - Write integration tests with existing ConfigManager
   - Write security tests (no secrets in TOML)
   - Depends on: Models, AuthMethod
   - **Checkpoint:** Configuration can be loaded/saved

### Phase 3: Credential Layer (Depends on Config)
**Order:** 6
**Duration:** 2-3 days

6. **Brick 5: CredentialFactory** (6-8 hours)
   - Add `azure-identity` to dependencies
   - Create `src/azlin/auth/credential_factory.py`
   - Implement factory methods for each auth type
   - Write unit tests (mocked Azure SDK)
   - Write integration tests (real Azure SDK, mocked endpoints)
   - Depends on: Models, AuthMethod
   - **Checkpoint:** Can create Azure Identity credential objects

### Phase 4: Authentication Logic (Depends on All)
**Order:** 7 → 8
**Duration:** 3-4 days

7. **Brick 6: AuthenticationChain** (6-8 hours)
   - Create `src/azlin/auth/authentication_chain.py`
   - Implement chain-of-responsibility pattern
   - Write unit tests (mocked credential creation)
   - Write integration tests (fallback behavior)
   - Depends on: CredentialFactory, Models
   - **Checkpoint:** Fallback chain works

8. **Brick 7: EnhancedAzureAuthenticator** (8-10 hours)
   - Create `src/azlin/auth/azure_authenticator.py`
   - Extend existing AzureAuthenticator
   - Write unit tests
   - Write integration tests
   - Write backward compatibility tests (existing behavior unchanged)
   - Depends on: All previous bricks
   - **Checkpoint:** Auth module complete

### Phase 5: Integration (Depends on Complete Auth Module)
**Order:** 9 → 10
**Duration:** 2-3 days

9. **CLI Integration** (4-6 hours)
   - Modify `src/azlin/cli.py`
   - Update CLIOrchestrator to load auth config
   - Add `--auth-method` flag
   - Write integration tests
   - Depends on: Complete auth module
   - **Checkpoint:** CLI uses new auth system

10. **End-to-End Testing** (6-8 hours)
    - Write E2E tests for all auth methods
    - Test complete provisioning workflow with SP auth
    - Test fallback chain in real scenarios
    - Test backward compatibility (existing users)
    - **Checkpoint:** All flows tested

### Phase 6: Documentation & Polish
**Order:** 11
**Duration:** 1-2 days

11. **Documentation** (6-8 hours)
    - User guide: How to configure service principal
    - Developer guide: How to add new auth methods
    - Migration guide: Upgrading from Azure CLI only
    - API reference: All public interfaces
    - **Checkpoint:** Documentation complete

### Implementation Checklist

**Phase 1:**
- [ ] AuthMethod enum implemented
- [ ] LogSanitizer implemented
- [ ] All data models with validation
- [ ] Unit tests: 100% coverage for models
- [ ] Security tests: validation enforcement

**Phase 2:**
- [ ] CertificateValidator implemented
- [ ] AuthConfigManager implemented
- [ ] Unit tests: TOML operations
- [ ] Integration tests: ConfigManager integration
- [ ] Security tests: no secrets in TOML

**Phase 3:**
- [ ] azure-identity dependency added
- [ ] CredentialFactory implemented
- [ ] Unit tests: all credential types
- [ ] Integration tests: Azure SDK integration

**Phase 4:**
- [ ] AuthenticationChain implemented
- [ ] EnhancedAzureAuthenticator implemented
- [ ] Unit tests: chain logic
- [ ] Integration tests: fallback behavior
- [ ] Backward compatibility tests

**Phase 5:**
- [ ] CLI integration complete
- [ ] E2E tests pass
- [ ] Backward compatibility verified
- [ ] All security controls validated

**Phase 6:**
- [ ] User documentation complete
- [ ] Developer documentation complete
- [ ] Migration guide complete
- [ ] API reference complete

### Risk Mitigation

**Risk 1: Breaking existing Azure CLI behavior**
- **Mitigation:** Complete backward compatibility test suite before Phase 5
- **Validation:** Run existing E2E tests, verify no changes

**Risk 2: Certificate permissions not enforced on all platforms**
- **Mitigation:** Test on macOS, Linux, Windows in Phase 2
- **Validation:** Security tests run on all platforms

**Risk 3: Secrets leak in logs/errors**
- **Mitigation:** LogSanitizer implemented in Phase 1, used everywhere
- **Validation:** Comprehensive security tests for all log statements

**Risk 4: Config file backward compatibility**
- **Mitigation:** AuthConfigManager handles missing [auth] section gracefully
- **Validation:** Integration tests with old config files

---

## 9. Key Design Decisions & Rationale

### Decision 1: Extend vs Replace AzureAuthenticator
**Decision:** Extend existing class (create EnhancedAzureAuthenticator)
**Rationale:**
- Preserves existing behavior 100% (no risk of breaking changes)
- Existing code continues to work without modifications
- New functionality opt-in via `auth_config` parameter
- Clear migration path for future updates
- Inheritance expresses "is-a" relationship correctly

**Alternatives Considered:**
- Replace with new implementation: ✗ High risk of breaking changes
- Modify existing class directly: ✗ Violates single responsibility principle
- Create parallel implementation: ✗ Code duplication

### Decision 2: Frozen Dataclasses for Configuration
**Decision:** Use `@dataclass(frozen=True)` for all config models
**Rationale:**
- Immutability prevents accidental mutation bugs
- Configuration should not change after validation
- Thread-safe by design (no locks needed)
- Clear intent: config is read-only after construction
- Enables hashability (can use as dict keys)

**Alternatives Considered:**
- Mutable dataclasses: ✗ Risk of mutation bugs
- Plain classes with properties: ✗ More boilerplate
- TypedDict: ✗ Runtime only, no validation at construction

### Decision 3: No Token Caching in azlin
**Decision:** Delegate all token management to Azure Identity SDK
**Rationale:**
- Azure SDK has battle-tested token refresh logic
- SDK handles platform-specific secure storage (keychain)
- Reduces security surface area (fewer places for bugs)
- Automatic token refresh without azlin involvement
- Compliance: SDK is certified by Microsoft

**Alternatives Considered:**
- Cache tokens in memory: ✗ Risk of expiry handling bugs
- Store tokens in config: ✗ Major security violation
- Custom token refresh: ✗ Reinventing the wheel, high risk

### Decision 4: Environment Variable for Client Secret
**Decision:** Only support `AZURE_CLIENT_SECRET` env var (no prompting)
**Rationale:**
- Standard Azure SDK convention
- Works in CI/CD pipelines
- No risk of secret in command history
- Clear error message if missing
- Future: Can add Azure Key Vault support

**Alternatives Considered:**
- Command-line argument: ✗ Appears in process list, history
- Interactive prompt: ✗ Breaks automation, poor UX
- Store in config: ✗ Major security violation

### Decision 5: Certificate Permissions Enforcement
**Decision:** Validate permissions (0600/0400) at config load time
**Rationale:**
- Fail-fast: catch misconfiguration immediately
- Clear error message with fix command
- Prevents accidental secret leakage via file permissions
- Industry standard (SSH uses same approach)
- Enforces least-privilege principle

**Alternatives Considered:**
- Only log warning: ✗ Users ignore warnings
- Validate at auth time: ✗ Fails later in workflow
- Auto-fix permissions: ✗ Surprising behavior, may hide issues

### Decision 6: Authentication Chain with Fallback
**Decision:** Implement chain-of-responsibility pattern for auth methods
**Rationale:**
- Graceful degradation (try multiple methods)
- Azure CLI always works as fallback (backward compatible)
- Clear error messages list all attempted methods
- Explicit config bypasses auto-detection (for scripts)
- Easy to add new methods in future

**Alternatives Considered:**
- Single method only: ✗ No fallback, poor UX
- Parallel attempt: ✗ Complex, hard to debug
- Manual fallback in caller: ✗ Code duplication

### Decision 7: Separate LogSanitizer Module
**Decision:** Dedicated module for log sanitization, not integrated into logger
**Rationale:**
- Single responsibility: sanitization separate from logging
- Reusable across different logging contexts
- Testable in isolation
- Easy to add new patterns without touching logger
- Explicit sanitization calls (clear in code)

**Alternatives Considered:**
- Custom logger class: ✗ Harder to integrate with existing code
- Logging filter: ✗ Implicit behavior, hard to verify
- Ad-hoc sanitization: ✗ Easy to forget, inconsistent

### Decision 8: UUID Validation in __post_init__
**Decision:** Validate UUIDs at dataclass construction time
**Rationale:**
- Fail-fast: invalid config never enters system
- Clear error messages at source of problem
- No need to validate at use sites (trust dataclass is valid)
- Compile-time guarantee (if dataclass exists, it's valid)
- Reduces defensive programming throughout codebase

**Alternatives Considered:**
- Validate at use time: ✗ Scattered validation logic
- No validation: ✗ Azure API errors are cryptic
- Separate validator class: ✗ Easy to bypass

### Decision 9: TOML Configuration Format
**Decision:** Extend existing TOML config with `[auth]` section
**Rationale:**
- Consistent with existing azlin configuration
- Human-readable and editable
- TOML has native section support for organization
- No new dependencies (already using tomli/tomli-w)
- Config file permissions already enforced by ConfigManager

**Alternatives Considered:**
- Separate auth config file: ✗ User confusion (multiple configs)
- JSON: ✗ No comments, less human-friendly
- YAML: ✗ New dependency, security issues (arbitrary code execution)

### Decision 10: Integration via CLI Orchestrator
**Decision:** Load auth config in CLIOrchestrator, pass to authenticator
**Rationale:**
- Single point of integration (DRY)
- Consistent auth behavior across all commands
- Easy to override for testing
- Clear flow: config → orchestrator → authenticator → operations
- No changes to individual command implementations

**Alternatives Considered:**
- Load in each command: ✗ Code duplication, inconsistent behavior
- Global singleton: ✗ Testing nightmare, hidden dependencies
- Implicit loading in authenticator: ✗ Hard to override, unclear flow

---

## 10. Integration Points Summary

### Files Modified (3)
1. **src/azlin/azure_auth.py**
   - Add: `from azlin.auth.azure_authenticator import EnhancedAzureAuthenticator`
   - Extend: No changes to existing code

2. **src/azlin/cli.py**
   - Add: `from azlin.auth.config_manager import AuthConfigManager`
   - Modify: CLIOrchestrator.__init__() - load auth_config, pass to authenticator
   - Add: Optional `--auth-method` CLI flag

3. **pyproject.toml**
   - Add: `azure-identity>=1.15.0` to dependencies

### Files Created (8 modules + 23 tests)

**Source Modules (8):**
- `src/azlin/auth/__init__.py`
- `src/azlin/auth/auth_method.py`
- `src/azlin/auth/models.py`
- `src/azlin/auth/config_manager.py`
- `src/azlin/auth/certificate_validator.py`
- `src/azlin/auth/credential_factory.py`
- `src/azlin/auth/authentication_chain.py`
- `src/azlin/auth/azure_authenticator.py`
- `src/azlin/auth/log_sanitizer.py`

**Test Files (23):**
- Unit tests: 8 files (one per module)
- Integration tests: 5 files
- Security tests: 3 files

### External Dependencies Added (1)
- `azure-identity>=1.15.0` - Microsoft's official Azure authentication library

### Backward Compatibility Guarantees
✓ Existing config files work unchanged
✓ Azure CLI authentication unchanged
✓ All existing CLI commands work
✓ No breaking API changes
✓ Existing tests pass without modification

---

## Conclusion

This architecture design delivers service principal authentication for azlin with:

- **8 self-contained modules (bricks)** - each independently testable and regeneratable
- **5 data models** - immutable, validated configuration structures
- **4 authentication methods** - with clear fallback chain and priority
- **10 P0 security controls** - mandatory, enforced at compile-time where possible
- **100% backward compatibility** - zero breaking changes to existing functionality
- **>90% test coverage** - comprehensive unit, integration, and security tests

The design follows azlin's brick philosophy: ruthless simplicity, modular architecture, and zero-BS implementation. Each brick has clear responsibilities (single responsibility principle) and well-defined contracts (studs). The architecture can be implemented incrementally over 5 phases, with clear checkpoints for validation.

**Key Benefits:**
1. **Security-First**: All P0 controls enforced, no secrets stored, comprehensive sanitization
2. **Modular**: Each brick regeneratable independently, clear dependencies
3. **Testable**: >90% coverage achievable through isolated tests
4. **Maintainable**: Clear separation of concerns, explicit error handling
5. **Extensible**: Easy to add new auth methods (just add to factory and chain)

**Implementation Ready:** All modules specified with complete interfaces, all flows documented with diagrams, all tests planned with examples. Ready for development to begin.

---

**Architecture design complete.**
- **8 modules** (bricks) defined with clear responsibilities and contracts
- **5 data models** with comprehensive validation and security controls
- **11 integration points** identified with backward compatibility preserved
- **5 authentication flows** documented with text-based diagrams
- **10 security controls** mapped to modules with enforcement strategy
- **23 test files** planned with >90% coverage target
- **6 implementation phases** with dependency-aware sequencing

**Next Steps:** Begin Phase 1 implementation (AuthMethod → LogSanitizer → Data Models).
