# SERVICE PRINCIPAL AUTHENTICATION - IMPLEMENTATION GUIDE

## Quick Reference: File Modifications Required

### 1. CREATE: `src/azlin/service_principal_auth.py` (NEW MODULE)

```python
"""Service Principal authentication module.

Handles service principal credential configuration and management.
Integrates with AzureAuthenticator for seamless authentication.

Security:
- SP credentials stored in encrypted config file
- No credentials in environment variables (only when needed)
- File permissions: 0600
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli
import tomli_w

logger = logging.getLogger(__name__)


class ServicePrincipalError(Exception):
    """Raised when service principal operations fail."""
    pass


@dataclass
class ServicePrincipalConfig:
    """Service principal configuration."""
    
    client_id: str
    client_secret: str
    tenant_id: str
    subscription_id: str
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "tenant_id": self.tenant_id,
            "subscription_id": self.subscription_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServicePrincipalConfig":
        """Create from dictionary."""
        return cls(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            tenant_id=data["tenant_id"],
            subscription_id=data["subscription_id"],
        )


class ServicePrincipalManager:
    """Manage service principal credentials securely."""
    
    DEFAULT_SP_CONFIG_DIR = Path.home() / ".azlin"
    DEFAULT_SP_CONFIG_FILE = DEFAULT_SP_CONFIG_DIR / "sp-config.toml"
    
    @classmethod
    def load_sp_config(cls, config_path: str | None = None) -> ServicePrincipalConfig:
        """Load service principal configuration.
        
        Args:
            config_path: Custom SP config path
            
        Returns:
            ServicePrincipalConfig
            
        Raises:
            ServicePrincipalError: If loading fails
        """
        path = Path(config_path) if config_path else cls.DEFAULT_SP_CONFIG_FILE
        
        if not path.exists():
            raise ServicePrincipalError(f"SP config file not found: {path}")
        
        try:
            # Verify file permissions
            stat = path.stat()
            mode = stat.st_mode & 0o777
            
            if mode & 0o077:  # Check if group/other have any permissions
                logger.warning(f"SP config has insecure permissions: {oct(mode)}. Fixing...")
                os.chmod(path, 0o600)
            
            # Load TOML
            with open(path, "rb") as f:
                data = tomli.load(f)
            
            logger.debug(f"Loaded SP config from: {path}")
            return ServicePrincipalConfig.from_dict(data)
            
        except Exception as e:
            raise ServicePrincipalError(f"Failed to load SP config: {e}") from e
    
    @classmethod
    def save_sp_config(
        cls, config: ServicePrincipalConfig, config_path: str | None = None
    ) -> None:
        """Save service principal configuration securely.
        
        Args:
            config: ServicePrincipalConfig to save
            config_path: Custom SP config path
            
        Raises:
            ServicePrincipalError: If saving fails
        """
        try:
            # Ensure directory exists
            cls.DEFAULT_SP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            os.chmod(cls.DEFAULT_SP_CONFIG_DIR, 0o700)
            
            # Determine path
            path = Path(config_path) if config_path else cls.DEFAULT_SP_CONFIG_FILE
            
            # Write with atomic operations
            temp_path = path.with_suffix(".tmp")
            
            with open(temp_path, "wb") as f:
                tomli_w.dump(config.to_dict(), f)
            
            # Set secure permissions before moving
            os.chmod(temp_path, 0o600)
            
            # Atomic rename
            temp_path.replace(path)
            
            logger.debug(f"Saved SP config to: {path}")
            
        except Exception as e:
            # Cleanup temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise ServicePrincipalError(f"Failed to save SP config: {e}") from e
    
    @classmethod
    def apply_sp_credentials(cls, config: ServicePrincipalConfig) -> None:
        """Apply SP credentials to environment variables.
        
        Args:
            config: ServicePrincipalConfig to apply
        """
        os.environ["AZURE_CLIENT_ID"] = config.client_id
        os.environ["AZURE_CLIENT_SECRET"] = config.client_secret
        os.environ["AZURE_TENANT_ID"] = config.tenant_id
        os.environ["AZURE_SUBSCRIPTION_ID"] = config.subscription_id
        logger.debug("Applied service principal credentials to environment")
    
    @classmethod
    def clear_sp_credentials(cls) -> None:
        """Clear SP credentials from environment variables."""
        for key in ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"]:
            os.environ.pop(key, None)
        logger.debug("Cleared service principal credentials from environment")
```

### 2. MODIFY: `src/azlin/azure_auth.py`

Add to imports:
```python
from azlin.service_principal_auth import (
    ServicePrincipalConfig,
    ServicePrincipalError,
    ServicePrincipalManager,
)
```

Modify `AzureAuthenticator.__init__()`:
```python
def __init__(
    self, 
    subscription_id: str | None = None, 
    use_managed_identity: bool = False,
    service_principal_config: str | None = None,  # NEW
):
    """Initialize Azure authenticator.
    
    Args:
        subscription_id: Optional Azure subscription ID
        use_managed_identity: Whether to use managed identity
        service_principal_config: Path to SP config file (optional)  # NEW
    """
    self._subscription_id = subscription_id
    self._use_managed_identity = use_managed_identity
    self._service_principal_config = service_principal_config  # NEW
    self._credentials_cache: AzureCredentials | None = None
```

Modify `AzureAuthenticator.get_credentials()`:
```python
def get_credentials(self) -> AzureCredentials:
    """Get Azure credentials from available sources.
    
    Priority order:
    0. Service Principal config file (NEW)
    1. Environment variables (AZURE_CLIENT_ID, etc.)
    2. Azure CLI (az account show)
    3. Managed identity (if use_managed_identity=True)
    """
    if self._credentials_cache:
        return self._credentials_cache
    
    # Priority 0: Service Principal config file  # NEW
    if self._service_principal_config:
        try:
            sp_config = ServicePrincipalManager.load_sp_config(
                self._service_principal_config
            )
            ServicePrincipalManager.apply_sp_credentials(sp_config)
            logger.info("Loaded credentials from service principal config")
        except ServicePrincipalError as e:
            logger.warning(f"Failed to load SP config: {e}. Trying other methods...")
    
    # Priority 1: Environment variables
    if self._check_env_credentials():
        # ... existing code ...
    
    # ... rest of priorities unchanged ...
```

### 3. MODIFY: `src/azlin/config_manager.py`

Modify `AzlinConfig` dataclass:
```python
@dataclass
class AzlinConfig:
    """Azlin configuration data."""
    
    default_resource_group: str | None = None
    default_region: str = "westus2"
    default_vm_size: str = "Standard_B2s"
    last_vm_name: str | None = None
    notification_command: str = "imessR"
    session_names: dict[str, str] | None = None
    vm_storage: dict[str, str] | None = None
    default_nfs_storage: str | None = None
    
    # NEW: Service Principal support
    service_principal_enabled: bool = False
    service_principal_config_path: str | None = None
```

Add methods to `ConfigManager`:
```python
@classmethod
def enable_service_principal(
    cls, 
    config_path: str | None = None,
    custom_config_path: str | None = None
) -> None:
    """Enable service principal authentication.
    
    Args:
        config_path: Path to SP config file
        custom_config_path: Custom azlin config path
    """
    config = cls.load_config(custom_config_path)
    config.service_principal_enabled = True
    config.service_principal_config_path = config_path or "~/.azlin/sp-config.toml"
    cls.save_config(config, custom_config_path)

@classmethod
def disable_service_principal(cls, custom_config_path: str | None = None) -> None:
    """Disable service principal authentication.
    
    Args:
        custom_config_path: Custom azlin config path
    """
    config = cls.load_config(custom_config_path)
    config.service_principal_enabled = False
    config.service_principal_config_path = None
    cls.save_config(config, custom_config_path)

@classmethod
def get_service_principal_enabled(cls, custom_config_path: str | None = None) -> bool:
    """Check if service principal is enabled.
    
    Args:
        custom_config_path: Custom azlin config path
        
    Returns:
        True if SP is enabled
    """
    config = cls.load_config(custom_config_path)
    return config.service_principal_enabled
```

### 4. MODIFY: `src/azlin/cli.py`

Add after main group definition (after line 1168):
```python
@main.group(name="auth")
@click.pass_context
def auth_group(ctx: click.Context) -> None:
    """Manage Azure authentication methods.
    
    \b
    Examples:
        azlin auth status                    # Show current auth method
        azlin auth sp-configure              # Configure service principal
        azlin auth sp-disable                # Disable service principal
    """
    pass


@auth_group.command(name="status")
@click.pass_context
def auth_status(ctx: click.Context) -> None:
    """Show current authentication status."""
    try:
        auth = AzureAuthenticator()
        
        # Check which method is active
        try:
            creds = auth.get_credentials()
            click.echo(f"Authentication Method: {creds.method}")
            
            if creds.subscription_id:
                click.echo(f"Subscription: {creds.subscription_id[:8]}...")
            if creds.tenant_id:
                click.echo(f"Tenant: {creds.tenant_id[:8]}...")
            
            click.echo("Status: AUTHENTICATED")
            
        except AuthenticationError:
            click.echo("Status: NOT AUTHENTICATED")
            click.echo("Run: az login")
            
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@auth_group.command(name="sp-configure")
@click.option("--client-id", prompt="Client ID", hide_input=False)
@click.option("--client-secret", prompt="Client Secret", hide_input=True)
@click.option("--tenant-id", prompt="Tenant ID", hide_input=False)
@click.option("--subscription-id", prompt="Subscription ID", hide_input=False)
@click.pass_context
def auth_sp_configure(
    ctx: click.Context,
    client_id: str,
    client_secret: str,
    tenant_id: str,
    subscription_id: str,
) -> None:
    """Configure service principal authentication."""
    try:
        from azlin.service_principal_auth import ServicePrincipalConfig, ServicePrincipalManager
        
        click.echo("\nConfiguring service principal...")
        
        # Create config
        sp_config = ServicePrincipalConfig(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
            subscription_id=subscription_id,
        )
        
        # Save config
        ServicePrincipalManager.save_sp_config(sp_config)
        click.echo("Service principal config saved to: ~/.azlin/sp-config.toml")
        
        # Enable in main config
        ConfigManager.enable_service_principal()
        click.echo("Service principal authentication ENABLED")
        
        # Test authentication
        auth = AzureAuthenticator(service_principal_config=str(
            ServicePrincipalManager.DEFAULT_SP_CONFIG_FILE
        ))
        auth.validate_credentials()
        click.echo("Service principal authentication verified!")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@auth_group.command(name="sp-disable")
@click.confirmation_option(prompt="Disable service principal authentication?")
@click.pass_context
def auth_sp_disable(ctx: click.Context) -> None:
    """Disable service principal authentication."""
    try:
        ConfigManager.disable_service_principal()
        click.echo("Service principal authentication DISABLED")
        click.echo("Falling back to Azure CLI authentication")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
```

---

## Integration Checklist

### Phase 1: Core Module
- [ ] Create `service_principal_auth.py` with `ServicePrincipalManager`
- [ ] Add `ServicePrincipalConfig` dataclass
- [ ] Implement secure file handling with 0600 permissions
- [ ] Add tests for SP module

### Phase 2: AzureAuthenticator Integration
- [ ] Update `AzureAuthenticator.__init__()` to accept `service_principal_config`
- [ ] Modify `get_credentials()` to check SP config first
- [ ] Add SP credentials loading in priority chain
- [ ] Add tests for SP integration

### Phase 3: ConfigManager Extension
- [ ] Add `service_principal_enabled` to `AzlinConfig`
- [ ] Add `service_principal_config_path` to `AzlinConfig`
- [ ] Implement `enable_service_principal()` method
- [ ] Implement `disable_service_principal()` method
- [ ] Add tests for config methods

### Phase 4: CLI Commands
- [ ] Create `auth` command group
- [ ] Add `auth status` command
- [ ] Add `auth sp-configure` command
- [ ] Add `auth sp-disable` command
- [ ] Add integration tests

### Phase 5: Testing
- [ ] Unit tests for all new methods
- [ ] Integration tests for full flow
- [ ] Backward compatibility tests
- [ ] Security tests (file permissions)

### Phase 6: Documentation
- [ ] Update README with SP setup guide
- [ ] Add help text for new commands
- [ ] Create migration guide for CI/CD

---

## Design Decisions Rationale

### Why Separate Module?
- Isolates SP-specific logic from general auth
- Makes future auth method additions easier
- Reduces cognitive load in `azure_auth.py`

### Why Priority 0?
- SP configured explicitly by user = should take precedence
- Env vars (Priority 1) can still be used as fallback
- Maintains backward compatibility

### Why Separate Config File?
- Keeps SP credentials separate from general config
- Easier to rotate/revoke without affecting other settings
- Can be version-controlled separately (with gitignore)

### Why 0600 Permissions?
- Security best practice for credential files
- Matches AWS, Azure CLI, and other tool standards
- Only owner can read sensitive credentials

### Why Apply to Env Vars?
- `az` CLI already reads these variables
- Reuses existing Priority 1 check logic
- No need to modify subprocess calls throughout codebase
- Automatic cleanup when SP instance is destroyed

---

## Backward Compatibility Guarantees

1. **Existing Code**: All existing code continues to work unchanged
2. **Existing Configs**: Old configs without SP fields still load (defaults applied)
3. **CLI Commands**: All existing commands work exactly as before
4. **Environment**: SP is opt-in (disabled by default)
5. **Migration**: Users can enable SP whenever ready

---

## Security Considerations

1. **File Permissions**: SP config file is 0600 (owner only)
2. **No Credential Logging**: SP credentials never logged
3. **Env Var Cleanup**: Credentials cleared after use
4. **Token Delegation**: Still uses `az` CLI (no direct token storage)
5. **Path Validation**: SP config path validated like other configs

