# AZLIN AUTHENTICATION ARCHITECTURE ANALYSIS

## Executive Summary

Azlin uses an **Azure CLI delegation pattern** for authentication - it does NOT store credentials directly. All Azure API calls go through the `az` CLI command, which manages tokens securely in `~/.azure/`. This design ensures maximum security and backward compatibility.

**Key Architectural Principles:**
- No credential storage in application code
- Azure CLI token management delegation
- Environment variable support for CI/CD
- Configuration via TOML files in `~/.azlin/config.toml`
- Extensible to support service principals via env vars

---

## 1. CURRENT ARCHITECTURE SUMMARY

### 1.1 Authentication Flow (Current State)

```
User/CI Environment
        ↓
    CLI Entry Point (cli.py:main)
        ↓
    CLIOrchestrator._authenticate_azure()
        ↓
    AzureAuthenticator (azure_auth.py)
        ↓
    Priority Chain:
    1. Environment Variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
    2. Azure CLI (az account get-access-token)
    3. Managed Identity (Azure metadata service)
        ↓
    AzureCredentials (dataclass - no token storage)
        ↓
    Operations use az CLI directly (no SDK)
```

### 1.2 Configuration System

**Location:** `~/.azlin/config.toml` (TOML format)

**Structure:**
```toml
default_resource_group = "my-rg"
default_region = "westus2"
default_vm_size = "Standard_B2s"
last_vm_name = "azlin-vm-12345"
notification_command = "imessR"

[session_names]
"vm-name" = "session-name"  # VM name mapping to session names

[vm_storage]
"vm-name" = "storage-account"  # VM to NFS storage mapping

default_nfs_storage = "team-storage"
```

**File Permissions:** `0600` (owner read/write only)

### 1.3 ConfigManager Architecture

**File:** `/Users/ryan/src/azlin/worktrees/feat-issue-177-service-principal-auth/src/azlin/config_manager.py`

**Key Classes:**
- `AzlinConfig` - Dataclass (lines 44-89): Represents configuration state
- `ConfigManager` - Manager class (lines 92-558): Handles TOML I/O operations

**Key Methods:**

| Method | Purpose | Line | Type |
|--------|---------|------|------|
| `get_config_path()` | Resolve config file path | 155 | @classmethod |
| `load_config()` | Load from TOML file | 215 | @classmethod |
| `save_config()` | Save to TOML file atomically | 255 | @classmethod |
| `update_config()` | Update specific config values | 301 | @classmethod |
| `get_resource_group()` | Get RG with CLI override | 330 | @classmethod |
| `get_region()` | Get region with CLI override | 349 | @classmethod |
| `get_vm_size()` | Get VM size with CLI override | 366 | @classmethod |
| `set_session_name()` | Map VM name to session name | 430 | @classmethod |
| `get_session_name()` | Look up session name by VM | 462 | @classmethod |

**Security Features:**
- Path validation preventing traversal attacks (line 102)
- Atomic writes using temp file + rename (line 281-290)
- Secure permissions enforcement (0600 directory, 0600 files)
- Session name uniqueness validation (line 383)

### 1.4 AzureAuthenticator Architecture

**File:** `/Users/ryan/src/azlin/worktrees/feat-issue-177-service-principal-auth/src/azlin/azure_auth.py`

**Key Classes:**
- `AuthenticationError` - Exception (line 25)
- `AzureCredentials` - Dataclass (lines 31-38): Stores auth metadata ONLY (no tokens)
- `AzureAuthenticator` - Manager (lines 41-262): Orchestrates authentication

**AzureCredentials Fields:**
```python
@dataclass
class AzureCredentials:
    method: str  # 'az_cli', 'env_vars', or 'managed_identity'
    token: str | None = None
    subscription_id: str | None = None
    tenant_id: str | None = None
```

**Key Methods:**

| Method | Purpose | Line | Returns |
|--------|---------|------|---------|
| `get_credentials()` | Get credentials from priority chain | 65 | AzureCredentials |
| `check_az_cli_available()` | Verify az CLI in PATH | 151 | bool |
| `validate_credentials()` | Test credential validity | 167 | bool |
| `validate_subscription_id()` | Validate UUID format | 182 | bool |
| `get_subscription_id()` | Get current subscription | 198 | str |
| `get_tenant_id()` | Get current tenant | 231 | str |
| `clear_cache()` | Clear credentials cache | 259 | None |

**Credential Priority Chain (lines 68-125):**
1. Environment variables: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`
2. Azure CLI: `az account get-access-token` (no credentials stored)
3. Managed Identity: Azure metadata service check

**Important:** Tokens are caching only - retrieved fresh each time from `az account get-access-token`

### 1.5 CLI Command Structure

**File:** `/Users/ryan/src/azlin/worktrees/feat-issue-177-service-principal-auth/src/azlin/cli.py`

**Main Entry Point:**
```python
@click.group(cls=AzlinGroup)  # Line 1168
@click.pass_context
@click.version_option(version=__version__)
def main(ctx: click.Context) -> None:
    """Azlin v2.0 CLI"""
```

**Command Group Structure (excerpt):**
```
azlin [command] [options]
├── new          - Provision new VM
├── list         - List VMs
├── connect      - Connect to VM
├── kill/destroy - Delete VMs
├── session      - Manage session names
├── env          - Environment variables
├── tag          - Tag management
├── start/stop   - VM lifecycle
└── ... (30+ commands total)
```

**Common CLI Options Pattern:**
```python
@main.command(name="new")
@click.option("--resource-group", "--rg", help="Azure resource group", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--repo", help="GitHub repository URL", type=str)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--template", help="Template name", type=str)
@click.option("--nfs-storage", help="NFS storage account", type=str)
@click.option("--pool", help="Number of VMs to create", type=int)
@click.option("--no-auto-connect", is_flag=True)
```

**Config + Arg Override Pattern (line 1373):**
```python
def _load_config_and_template(config: str | None, template: str | None) -> tuple[AzlinConfig, VMTemplateConfig | None]:
    try:
        azlin_config = ConfigManager.load_config(config)
    except ConfigError:
        azlin_config = AzlinConfig()
    # ... CLI args override config values
```

### 1.6 VM Operations Integration Points

**File:** `/Users/ryan/src/azlin/worktrees/feat-issue-177-service-principal-auth/src/azlin/vm_provisioning.py`

**VM Provisioning Flow:**
1. `VMProvisioner.create_vm_config()` - Build VM configuration
2. `VMProvisioner.provision_vm()` - Call `az vm create ...`
3. Operations use subprocess to call `az` CLI directly
4. No SDK - pure CLI delegation

**VMConfig Dataclass (lines 31-42):**
```python
@dataclass
class VMConfig:
    name: str
    resource_group: str
    location: str = "westus2"
    size: str = "Standard_B2s"
    image: str = "Ubuntu2204"
    ssh_public_key: str | None = None
    admin_username: str = "azureuser"
    disable_password_auth: bool = True
```

**Key Auth Integration Point:**
- Authentication happens BEFORE provisioning (CLIOrchestrator.run() line 170)
- AzureAuthenticator.get_subscription_id() validates auth works
- All `az` commands inherit user's authenticated session

---

## 2. INTEGRATION POINTS FOR SERVICE PRINCIPAL AUTH

### 2.1 Where Service Principal Code Should Live

**New Module Recommendation:**
```
src/azlin/service_principal_auth.py
├── ServicePrincipalManager    # Manage SP credentials
├── ServicePrincipalConfig      # SP configuration dataclass
├── ServicePrincipalError       # SP-specific exception
└── SpAuthenticator             # SP-specific auth logic
```

**Location:** `/Users/ryan/src/azlin/src/azlin/service_principal_auth.py` (NEW)

### 2.2 Integration with Existing AzureAuthenticator

**Current Priority Chain (azure_auth.py:65-125):**
```python
def get_credentials(self) -> AzureCredentials:
    # Priority 1: Environment variables
    if self._check_env_credentials():
        # AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID

    # Priority 2: Azure CLI
    if self.check_az_cli_available():
        # az account get-access-token

    # Priority 3: Managed identity
    if self._use_managed_identity:
        # Azure metadata service
```

**Service Principal Auth Extension Point:**
- Add Priority 0 check: Service Principal config file (NEW)
- Service principal credentials → translate to env vars
- Delegate to Priority 1 check (env vars already supported!)

**Pattern:**
```python
# In AzureAuthenticator.__init__():
def __init__(self,
    subscription_id: str | None = None,
    use_managed_identity: bool = False,
    service_principal_config: str | None = None):  # NEW
    self._service_principal_config = service_principal_config

# In get_credentials():
def get_credentials(self) -> AzureCredentials:
    # Priority 0: Load and apply Service Principal config
    if self._service_principal_config:
        self._load_service_principal_credentials()

    # Then existing priorities continue...
```

### 2.3 Configuration Integration

**New Config Section in `~/.azlin/config.toml`:**
```toml
[service_principal]
enabled = false
config_file = "~/.azlin/sp-config.toml"
```

**Service Principal Config File (`~/.azlin/sp-config.toml`):**
```toml
client_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
client_secret = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
tenant_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

**File Permissions:** `0600` (owner read/write only)

**ConfigManager Extension (config_manager.py):**
- Add `service_principal_config_path` field to AzlinConfig
- Add methods:
  - `get_service_principal_config()` - Load SP config
  - `set_service_principal_config()` - Save SP config
  - `enable_service_principal()` - Enable SP auth
  - `disable_service_principal()` - Disable SP auth

### 2.4 CLI Command Group for Auth Management

**New Command Group in cli.py:**
```python
@main.group(name="auth")
def auth_group():
    """Manage Azure authentication methods."""
    pass

@auth_group.command(name="login")
@click.option("--method", type=click.Choice(["cli", "sp"]), default="cli")
def auth_login(method: str):
    """Authenticate with Azure."""
    pass

@auth_group.command(name="status")
def auth_status():
    """Show current authentication status."""
    pass

@auth_group.command(name="sp-configure")
@click.option("--client-id", prompt=True)
@click.option("--client-secret", prompt=True, hide_input=True)
@click.option("--tenant-id", prompt=True)
@click.option("--subscription-id", prompt=True)
def auth_sp_configure(client_id, client_secret, tenant_id, subscription_id):
    """Configure service principal authentication."""
    pass

@auth_group.command(name="sp-disable")
def auth_sp_disable():
    """Disable service principal authentication."""
    pass
```

**Placement in cli.py:** After main group definition (after line 1168)

### 2.5 Which Files Need Modification

**Files TO MODIFY (Backward Compatible):**

1. **azure_auth.py** - Add service principal support
   - Add `service_principal_config` parameter to `AzureAuthenticator.__init__()`
   - Add method to load SP config and populate environment variables
   - Extend `get_credentials()` to check service principal first

2. **config_manager.py** - Add SP config management
   - Add `service_principal_enabled: bool` to `AzlinConfig`
   - Add `service_principal_config_path: str | None` to `AzlinConfig`
   - Add methods for SP config management

3. **cli.py** - Add auth command group
   - Add new `@auth_group` commands (lines after 1168)
   - No changes to existing commands needed

4. **pyproject.toml** - No changes needed (dependencies already sufficient)

**Files TO PRESERVE (No changes):**

1. **vm_provisioning.py** - Use existing auth flow
2. **vm_manager.py** - Use existing auth flow
3. **remote_exec.py** - Use existing auth flow
4. All command handlers that use auth

---

## 3. DESIGN CONSTRAINTS & PATTERNS

### 3.1 Existing Patterns to Follow

**Error Handling Pattern:**
```python
# From azure_auth.py:25-28
class AuthenticationError(Exception):
    """Raised when Azure authentication fails."""
    pass

# From config_manager.py:37-40
class ConfigError(Exception):
    """Raised when configuration operations fail."""
    pass

# Pattern: Create specific exception classes inheriting from Exception
```

**Naming Conventions:**
- Classes: PascalCase with descriptive names
- Methods: snake_case, prefix with `_` for private
- Constants: UPPER_SNAKE_CASE
- Environment variables: `AZURE_*` format (Azure standard)

**Logging Pattern:**
```python
# From azure_auth.py
import logging
logger = logging.getLogger(__name__)

# Usage
logger.info("Using Azure credentials from az CLI")
logger.debug(f"Found Azure CLI at: {az_path}")
logger.warning(f"Config file has insecure permissions: {oct(mode)}")
```

**Dataclass Pattern:**
```python
# From azure_auth.py:31-38
@dataclass
class AzureCredentials:
    """Azure credentials representation."""
    method: str  # 'az_cli', 'env_vars', or 'managed_identity'
    token: str | None = None
    subscription_id: str | None = None
    tenant_id: str | None = None
```

**Configuration Loading Pattern:**
```python
# From cli.py:1373
def _load_config_and_template(config: str | None, template: str | None):
    try:
        azlin_config = ConfigManager.load_config(config)
    except ConfigError:
        azlin_config = AzlinConfig()
    return azlin_config
```

### 3.2 Security Patterns

**Sensitive File Protection:**
```python
# From config_manager.py:287-290
os.chmod(temp_path, 0o600)  # Set before move
temp_path.replace(config_path)  # Atomic operation
```

**Path Validation:**
```python
# From config_manager.py:102-152
@classmethod
def _validate_config_path(cls, path: Path) -> Path:
    """Validate path is within allowed directories."""
    resolved_path = path.resolve()
    allowed_dirs = [cls.DEFAULT_CONFIG_DIR.resolve(), ...]
    for allowed_dir in allowed_dirs:
        try:
            resolved_path.relative_to(allowed_dir)
            return resolved_path
        except ValueError:
            continue
    raise ConfigError(f"Config path outside allowed directories: {resolved_path}")
```

**Input Validation:**
```python
# From config_manager.py:416-421
if not session_name or not re.match(r"^[a-zA-Z0-9_-]{1,64}$", session_name):
    raise ConfigError(f"Invalid session name format: {session_name}")
```

### 3.3 Subprocess Pattern (NO shell=True)

**From vm_provisioning.py and azure_auth.py:**
```python
# CORRECT: List of arguments (no shell injection possible)
result = subprocess.run(
    ["az", "account", "get-access-token"],
    capture_output=True,
    text=True,
    timeout=10,
    check=True
)

# WRONG: shell=True allows injection
# result = subprocess.run("az account get-access-token", shell=True)
```

---

## 4. KEY CODE SNIPPETS FOR REFERENCE

### 4.1 ConfigManager Usage Example

```python
# Load config (or defaults)
config = ConfigManager.load_config()

# Access properties
rg = config.resource_group  # None if not set
region = config.region       # "westus2" (default)
vm_size = config.vm_size     # "Standard_B2s" (default)

# Get with CLI override
rg = ConfigManager.get_resource_group(cli_value=None, custom_path=None)
region = ConfigManager.get_region(cli_value=args.region, custom_path=None)

# Update config
config = ConfigManager.update_config(
    default_resource_group="my-rg",
    default_region="eastus",
)

# Save config
ConfigManager.save_config(config)
```

### 4.2 Current Auth Invocation

```python
# From cli.py:292-315 (CLIOrchestrator._authenticate_azure)
def _authenticate_azure(self) -> str:
    """Authenticate with Azure and get subscription ID."""
    self.progress.update("Checking Azure CLI authentication...")

    # Verify az CLI is available
    if not self.auth.check_az_cli_available():
        raise AuthenticationError("Azure CLI not available. Please install az CLI.")

    # Get credentials (triggers az login if needed)
    self.auth.get_credentials()

    # Get subscription ID
    subscription_id = self.auth.get_subscription_id()

    return subscription_id
```

### 4.3 Environment Variables Check Pattern

```python
# From azure_auth.py:127-130
def _check_env_credentials(self) -> bool:
    """Check if environment variables have credentials."""
    required = ["AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"]
    return all(os.environ.get(var) for var in required)
```

### 4.4 CLI Option Override Pattern

```python
# From config_manager.py:330-346
@classmethod
def get_resource_group(
    cls, cli_value: str | None = None, custom_path: str | None = None
) -> str | None:
    """Get resource group with CLI override."""
    if cli_value:  # CLI args take precedence
        return cli_value

    config = cls.load_config(custom_path)
    return config.default_resource_group
```

### 4.5 Test Fixture Pattern

```python
# From tests/unit/test_config_manager.py
class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_get_config_path_custom(self, tmp_path):
        """Test custom config path."""
        custom_path = tmp_path / "custom.toml"
        custom_path.touch()
        path = ConfigManager.get_config_path(str(custom_path))
        assert path == custom_path

    def test_load_config_not_exists(self, tmp_path):
        """Test loading config when file doesn't exist."""
        with patch.object(ConfigManager, "get_config_path",
                         return_value=tmp_path / "missing.toml"):
            config = ConfigManager.load_config()
            assert isinstance(config, AzlinConfig)
            assert config.default_resource_group is None
```

### 4.6 Mock Azure Environment Pattern

```python
# From tests/mocks/azure_mock.py
class MockAzureCredential:
    """Mock Azure DefaultAzureCredential."""

    def __init__(self, token: str = "fake-token-12345"):
        self.token = token

    def get_token(self, *scopes):
        """Return a fake token."""
        return Mock(token=self.token, expires_on=9999999999)

def create_mock_azure_environment() -> dict[str, Any]:
    """Create a complete mock Azure environment."""
    credential = MockAzureCredential()
    return {
        "credential": credential,
        "compute_client": MockComputeManagementClient(credential, "sub-id"),
    }
```

---

## 5. BACKWARD COMPATIBILITY PRESERVATION

### 5.1 Guarantees

All changes are ADDITIVE only:

1. **No changes to existing auth flow** - Service principal is optional
2. **Config format backward compatible** - New fields are optional
3. **CLI commands unchanged** - New `auth` group added, existing commands unchanged
4. **Environment variable behavior unchanged** - Still supports `AZURE_SUBSCRIPTION_ID`, `AZURE_TENANT_ID`

### 5.2 Migration Path

**For Existing Users:**
1. No action required - continue using Azure CLI auth
2. Optional: Configure service principal when needed for CI/CD

**For CI/CD:**
1. Set `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`
2. Or use new `azlin auth sp-configure` command

### 5.3 Version Compatibility

- Existing configs remain valid (no breaking changes)
- New SP config is separate file (`~/.azlin/sp-config.toml`)
- CLI stays backward compatible (only adding new commands)

---

## 6. TESTING PATTERNS TO FOLLOW

### 6.1 Test File Structure

```python
# File: tests/unit/test_[module_name].py

from unittest.mock import Mock, patch
import pytest

class Test[ClassName]:
    """Tests for [ClassName]."""

    def test_[method_name]_[scenario](self):
        """Test [method] in [scenario]."""
        # Arrange
        setup_data = ...

        # Act
        result = function_under_test(setup_data)

        # Assert
        assert result == expected_value

    @patch("module.subprocess.run")
    def test_[method]_[scenario]_with_mock(self, mock_run):
        """Test with mocked subprocess."""
        mock_run.return_value = Mock(returncode=0, stdout="{}")
        # ... test code
```

### 6.2 Mocking Pattern

```python
@patch("azlin.azure_auth.subprocess.run")
@patch("azlin.azure_auth.shutil.which")
def test_az_cli_auth(self, mock_which, mock_run):
    """Test Azure CLI authentication."""
    # Setup mocks
    mock_which.return_value = "/usr/bin/az"
    mock_run.return_value = Mock(
        returncode=0,
        stdout=json.dumps({
            "accessToken": "fake-token",
            "subscription": "sub-id",
            "tenant": "tenant-id"
        })
    )

    # Test
    auth = AzureAuthenticator()
    creds = auth.get_credentials()

    # Verify
    assert creds.method == "az_cli"
    assert creds.subscription_id == "sub-id"
```

### 6.3 Config Test Pattern

```python
def test_config_load_save_roundtrip(self, tmp_path):
    """Test config loads and saves correctly."""
    # Create config
    config = AzlinConfig(
        default_resource_group="test-rg",
        default_region="eastus"
    )

    # Save
    config_path = tmp_path / "config.toml"
    with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_path):
        ConfigManager.save_config(config)

    # Load
    loaded = ConfigManager.load_config()

    # Verify
    assert loaded.default_resource_group == "test-rg"
    assert loaded.default_region == "eastus"
```

---

## 7. SUMMARY TABLE: Files & Their Roles

| File | Purpose | Modification Type | Key Classes |
|------|---------|-------------------|-------------|
| `azure_auth.py` | Azure authentication | MODIFY | `AzureAuthenticator`, `AzureCredentials` |
| `config_manager.py` | Configuration I/O | MODIFY | `ConfigManager`, `AzlinConfig` |
| `cli.py` | CLI command handler | MODIFY (ADD auth group) | `AzlinGroup`, command functions |
| `service_principal_auth.py` | NEW - SP auth logic | CREATE | `ServicePrincipalManager`, `SpAuthenticator` |
| `vm_provisioning.py` | VM provisioning | PRESERVE | `VMProvisioner` |
| `vm_manager.py` | VM management | PRESERVE | `VMManager` |
| `remote_exec.py` | Remote execution | PRESERVE | `RemoteExecutor` |

---

## 8. NEXT STEPS FOR SERVICE PRINCIPAL IMPLEMENTATION

### Phase 1: Core Infrastructure
1. Create `service_principal_auth.py` module
2. Extend `AzureAuthenticator` to support SP config
3. Add SP fields to `AzlinConfig`

### Phase 2: Configuration Management
1. Add SP config load/save methods to `ConfigManager`
2. Implement secure SP credential file handling
3. Add SP validation methods

### Phase 3: CLI Interface
1. Create `auth` command group in `cli.py`
2. Add `auth sp-configure` command
3. Add `auth status` command
4. Add `auth sp-disable` command

### Phase 4: Testing
1. Write unit tests for SP auth
2. Write integration tests
3. Test backward compatibility

### Phase 5: Documentation
1. Update README with SP auth guide
2. Add CLI help text
3. Create migration guide
