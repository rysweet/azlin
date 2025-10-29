# azlin API Reference

This document provides a comprehensive reference for all public APIs in the azlin project. Use these APIs to programmatically integrate azlin into your own tools and automation scripts.

## Table of Contents

- [Overview](#overview)
- [Core Modules](#core-modules)
  - [CLI & Orchestration](#cli--orchestration)
  - [Configuration Management](#configuration-management)
  - [Azure Authentication](#azure-authentication)
- [VM Management](#vm-management)
  - [VM Lifecycle](#vm-lifecycle)
  - [VM Provisioning](#vm-provisioning)
  - [VM Operations](#vm-operations)
  - [VM Status & Monitoring](#vm-status--monitoring)
- [Connection & SSH](#connection--ssh)
  - [SSH Connection](#ssh-connection)
  - [SSH Keys](#ssh-keys)
  - [SSH Reconnect](#ssh-reconnect)
- [File Operations](#file-operations)
  - [File Transfer](#file-transfer)
  - [Home Directory Sync](#home-directory-sync)
- [Storage Management](#storage-management)
  - [NFS Storage](#nfs-storage)
  - [NFS Mount Management](#nfs-mount-management)
  - [Snapshot Management](#snapshot-management)
- [Cost & Resource Management](#cost--resource-management)
  - [Cost Tracking](#cost-tracking)
  - [Resource Cleanup](#resource-cleanup)
- [Remote Execution](#remote-execution)
  - [Command Execution](#command-execution)
  - [Batch Operations](#batch-operations)
- [Advanced Features](#advanced-features)
  - [Templates](#templates)
  - [SSH Key Rotation](#ssh-key-rotation)
  - [Distributed Monitoring](#distributed-monitoring)
  - [Terminal Launcher](#terminal-launcher)
- [Utilities](#utilities)
  - [Prerequisites](#prerequisites)
  - [Progress Display](#progress-display)
  - [Notifications](#notifications)
  - [Tags](#tags)
  - [Environment Management](#environment-management)

---

## Overview

The azlin API is organized into self-contained modules following the "brick architecture" philosophy. Each module provides a focused set of functionality with clear inputs and outputs.

**Key Design Principles:**
- **Ruthless Simplicity**: Each module has one clear purpose
- **Security by Design**: No credentials in code, input validation, secure permissions
- **Fail Fast**: Clear error messages with actionable guidance
- **Type Safety**: Full type hints on all public APIs

**Common Patterns:**
- Most managers use classmethods for stateless operations
- Dataclasses for structured data (VMInfo, StorageInfo, etc.)
- Custom exceptions with clear error messages
- No shell=True in subprocess calls

---

## Core Modules

### CLI & Orchestration

#### `azlin.cli`

Main CLI entry point and workflow orchestration.

**Classes:**

##### `CLIOrchestrator`

Coordinates the complete azlin workflow from prerequisites to VM provisioning.

```python
class CLIOrchestrator:
    """Orchestrate azlin workflow.

    Coordinates all modules to execute the complete workflow:
    1. Prerequisites check
    2. Azure authentication
    3. SSH key generation
    4. VM provisioning
    5. Wait for VM ready
    6. SSH connection
    7. GitHub repo cloning (optional)
    """

    def __init__(self, config_manager: ConfigManager, skip_prerequisites: bool = False):
        """Initialize orchestrator.

        Args:
            config_manager: Configuration manager instance
            skip_prerequisites: Skip prerequisite checks (default: False)
        """
```

**Functions:**

##### `generate_vm_name()`

Generate a unique VM name with optional custom prefix.

```python
def generate_vm_name(custom_name: str | None = None, command: str | None = None) -> str:
    """Generate VM name.

    Args:
        custom_name: Custom name prefix (optional)
        command: Command being executed (for context)

    Returns:
        Generated VM name in format: azlin-vm-TIMESTAMP or custom-TIMESTAMP
    """
```

**Example:**

```python
from azlin.cli import CLIOrchestrator, generate_vm_name
from azlin.config_manager import ConfigManager

# Generate a unique VM name
vm_name = generate_vm_name(custom_name="dev")
print(f"VM name: {vm_name}")  # Output: dev-1729265432

# Use the orchestrator
config_mgr = ConfigManager()
orchestrator = CLIOrchestrator(config_mgr)
```

**Exports:**
```python
__all__ = ["AzlinError", "CLIOrchestrator", "main"]
```

---

### Configuration Management

#### `azlin.config_manager`

Persistent configuration storage using TOML format.

**Classes:**

##### `AzlinConfig`

Configuration data structure.

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
```

##### `ConfigManager`

Manage azlin configuration file at `~/.azlin/config.toml`.

```python
class ConfigManager:
    """Manage azlin configuration file with secure permissions."""

    DEFAULT_CONFIG_DIR = Path.home() / ".azlin"
    DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.toml"

    @classmethod
    def load_config(cls, custom_path: str | None = None) -> AzlinConfig:
        """Load configuration from file.

        Args:
            custom_path: Custom config file path (optional)

        Returns:
            AzlinConfig object

        Raises:
            ConfigError: If loading fails
        """

    @classmethod
    def save_config(cls, config: AzlinConfig, custom_path: str | None = None) -> None:
        """Save configuration to file.

        Args:
            config: Configuration to save
            custom_path: Custom config file path (optional)

        Raises:
            ConfigError: If saving fails
        """

    @classmethod
    def set_session_name(cls, vm_name: str, session_name: str) -> None:
        """Set session name for a VM.

        Args:
            vm_name: VM name
            session_name: Human-readable session name
        """

    @classmethod
    def get_session_name(cls, vm_name: str) -> str | None:
        """Get session name for a VM.

        Args:
            vm_name: VM name

        Returns:
            Session name if set, None otherwise
        """
```

**Example:**

```python
from azlin.config_manager import ConfigManager, AzlinConfig

# Load configuration
config = ConfigManager.load_config()
print(f"Default region: {config.default_region}")

# Update configuration
config.default_vm_size = "Standard_D4s_v3"
ConfigManager.save_config(config)

# Set session name
ConfigManager.set_session_name("azlin-vm-123", "my-dev-env")
```

**Exports:**
```python
__all__ = ["AzlinConfig", "ConfigError", "ConfigManager"]
```

---

### Azure Authentication

#### `azlin.azure_auth`

Azure authentication and credential management.

**Classes:**

##### `AzureCredentials`

Azure authentication credentials.

```python
@dataclass
class AzureCredentials:
    """Azure authentication credentials."""

    subscription_id: str
    tenant_id: str | None = None
    user_name: str | None = None
```

##### `AzureAuthenticator`

Handle Azure CLI authentication.

```python
class AzureAuthenticator:
    """Handle Azure CLI authentication."""

    @classmethod
    def authenticate(cls) -> AzureCredentials:
        """Authenticate with Azure CLI.

        Returns:
            AzureCredentials with subscription ID and tenant ID

        Raises:
            AuthenticationError: If authentication fails
        """

    @classmethod
    def check_logged_in(cls) -> bool:
        """Check if user is logged in to Azure CLI.

        Returns:
            True if logged in, False otherwise
        """

    @classmethod
    def get_subscription_id(cls) -> str:
        """Get current Azure subscription ID.

        Returns:
            Subscription ID

        Raises:
            AuthenticationError: If unable to get subscription
        """
```

**Example:**

```python
from azlin.azure_auth import AzureAuthenticator, AuthenticationError

try:
    # Check if logged in
    if not AzureAuthenticator.check_logged_in():
        print("Not logged in to Azure. Please run: az login")
    else:
        # Get credentials
        creds = AzureAuthenticator.authenticate()
        print(f"Subscription: {creds.subscription_id}")
        print(f"Tenant: {creds.tenant_id}")
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
```

**Exports:**
```python
__all__ = ["AuthenticationError", "AzureAuthenticator", "AzureCredentials"]
```

---

## VM Management

### VM Lifecycle

#### `azlin.vm_lifecycle`

VM deletion and lifecycle management.

**Classes:**

##### `VMLifecycleManager`

Manage VM lifecycle operations.

```python
class VMLifecycleManager:
    """Manage VM lifecycle operations."""

    @classmethod
    def delete_vm(
        cls,
        vm_name: str,
        resource_group: str,
        delete_resource_group: bool = False,
        dry_run: bool = False
    ) -> DeletionSummary:
        """Delete a VM and associated resources.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            delete_resource_group: Delete entire resource group (default: False)
            dry_run: Preview without deleting (default: False)

        Returns:
            DeletionSummary with results

        Raises:
            VMLifecycleError: If deletion fails
        """

    @classmethod
    def delete_all_vms(
        cls,
        resource_group: str,
        force: bool = False
    ) -> DeletionSummary:
        """Delete all VMs in a resource group.

        Args:
            resource_group: Resource group name
            force: Skip confirmation prompt

        Returns:
            DeletionSummary with results
        """
```

**Data Classes:**

```python
@dataclass
class DeletionResult:
    """Result of a single resource deletion."""
    resource_type: str  # "vm", "disk", "nic", "public-ip"
    resource_name: str
    success: bool
    error_message: str | None = None

@dataclass
class DeletionSummary:
    """Summary of VM deletion operation."""
    vm_name: str
    resource_group: str
    total_resources: int
    deleted_resources: int
    failed_resources: int
    results: list[DeletionResult]
```

**Example:**

```python
from azlin.vm_lifecycle import VMLifecycleManager, VMLifecycleError

try:
    # Preview deletion
    summary = VMLifecycleManager.delete_vm(
        vm_name="azlin-vm-123",
        resource_group="azlin-rg",
        dry_run=True
    )
    print(f"Would delete {summary.total_resources} resources")

    # Actual deletion
    summary = VMLifecycleManager.delete_vm(
        vm_name="azlin-vm-123",
        resource_group="azlin-rg"
    )
    print(f"Deleted {summary.deleted_resources}/{summary.total_resources} resources")
except VMLifecycleError as e:
    print(f"Deletion failed: {e}")
```

**Exports:**
```python
__all__ = ["DeletionResult", "DeletionSummary", "VMLifecycleError", "VMLifecycleManager"]
```

---

### VM Provisioning

#### `azlin.vm_provisioning`

VM provisioning and resource group management.

**Classes:**

##### `VMProvisioner`

Provision Azure VMs with development tools.

```python
class VMProvisioner:
    """Provision Azure VMs with development tools."""

    @classmethod
    def provision_vm(
        cls,
        vm_name: str,
        resource_group: str,
        region: str,
        vm_size: str,
        ssh_key_path: Path,
        admin_username: str = "azureuser",
        nfs_storage: str | None = None
    ) -> VMDetails:
        """Provision a new VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            region: Azure region (e.g., "westus2")
            vm_size: VM size (e.g., "Standard_B2s")
            ssh_key_path: Path to SSH public key
            admin_username: Admin username (default: "azureuser")
            nfs_storage: NFS storage account name (optional)

        Returns:
            VMDetails with IP address and connection info

        Raises:
            ProvisioningError: If provisioning fails
        """

    @classmethod
    def provision_pool(
        cls,
        count: int,
        resource_group: str,
        region: str,
        vm_size: str,
        ssh_key_path: Path,
        name_prefix: str | None = None
    ) -> PoolProvisioningResult:
        """Provision multiple VMs in parallel.

        Args:
            count: Number of VMs to create
            resource_group: Resource group name
            region: Azure region
            vm_size: VM size
            ssh_key_path: Path to SSH public key
            name_prefix: Custom name prefix (optional)

        Returns:
            PoolProvisioningResult with all VM details
        """
```

**Data Classes:**

```python
@dataclass
class VMDetails:
    """VM provisioning details."""
    vm_name: str
    resource_group: str
    public_ip: str
    region: str
    vm_size: str
    admin_username: str
    ssh_key_path: Path

@dataclass
class PoolProvisioningResult:
    """Results from pool provisioning."""
    successful: list[VMDetails]
    failed: list[ProvisioningFailure]
    total_time: float
```

**Example:**

```python
from azlin.vm_provisioning import VMProvisioner, ProvisioningError
from pathlib import Path

try:
    # Provision a single VM
    details = VMProvisioner.provision_vm(
        vm_name="my-dev-vm",
        resource_group="azlin-rg",
        region="westus2",
        vm_size="Standard_B2s",
        ssh_key_path=Path("~/.ssh/azlin_key.pub")
    )
    print(f"VM created: {details.public_ip}")

    # Provision a pool of VMs
    result = VMProvisioner.provision_pool(
        count=3,
        resource_group="azlin-rg",
        region="westus2",
        vm_size="Standard_B2s",
        ssh_key_path=Path("~/.ssh/azlin_key.pub"),
        name_prefix="worker"
    )
    print(f"Created {len(result.successful)} VMs in {result.total_time:.1f}s")
except ProvisioningError as e:
    print(f"Provisioning failed: {e}")
```

**Exports:**
```python
__all__ = [
    "ProvisioningError",
    "ProvisioningFailure",
    "PoolProvisioningResult",
    "ResourceGroupFailure",
    "ResourceGroupManager",
    "VMConfig",
    "VMDetails",
    "VMProvisioner",
]
```

---

### VM Operations

#### `azlin.vm_manager`

VM listing, querying, and status operations.

**Classes:**

##### `VMManager`

Manage Azure VMs - list, query, filter operations.

```python
class VMManager:
    """Manage Azure VMs."""

    @classmethod
    def list_vms(
        cls,
        resource_group: str,
        include_stopped: bool = True
    ) -> list[VMInfo]:
        """List all VMs in a resource group.

        Args:
            resource_group: Resource group name
            include_stopped: Include stopped/deallocated VMs

        Returns:
            List of VMInfo objects

        Raises:
            VMManagerError: If listing fails
        """

    @classmethod
    def get_vm_by_name(
        cls,
        vm_name: str,
        resource_group: str
    ) -> VMInfo | None:
        """Get VM by name.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VMInfo if found, None otherwise
        """

    @classmethod
    def get_running_vms(cls, resource_group: str) -> list[VMInfo]:
        """Get only running VMs.

        Args:
            resource_group: Resource group name

        Returns:
            List of running VMInfo objects
        """
```

**Data Classes:**

```python
@dataclass
class VMInfo:
    """VM information from Azure."""

    name: str
    resource_group: str
    location: str
    power_state: str
    public_ip: str | None = None
    private_ip: str | None = None
    vm_size: str | None = None
    os_type: str | None = None
    provisioning_state: str | None = None
    created_time: str | None = None
    tags: dict[str, str] | None = None
    session_name: str | None = None

    def is_running(self) -> bool:
        """Check if VM is running."""

    def is_stopped(self) -> bool:
        """Check if VM is stopped."""

    def get_status_display(self) -> str:
        """Get formatted status display."""

    def get_display_name(self) -> str:
        """Get display name (session name if set, otherwise VM name)."""
```

**Example:**

```python
from azlin.vm_manager import VMManager, VMManagerError

try:
    # List all VMs
    vms = VMManager.list_vms(resource_group="azlin-rg")
    for vm in vms:
        print(f"{vm.name}: {vm.get_status_display()} @ {vm.public_ip}")

    # Get specific VM
    vm = VMManager.get_vm_by_name("my-vm", "azlin-rg")
    if vm and vm.is_running():
        print(f"VM is running at {vm.public_ip}")

    # Get only running VMs
    running = VMManager.get_running_vms("azlin-rg")
    print(f"Found {len(running)} running VMs")
except VMManagerError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["VMInfo", "VMManager", "VMManagerError"]
```

---

#### `azlin.vm_lifecycle_control`

VM start/stop operations.

**Classes:**

##### `VMLifecycleController`

Control VM power state (start/stop/deallocate).

```python
class VMLifecycleController:
    """Control VM power state."""

    @classmethod
    def start_vm(
        cls,
        vm_name: str,
        resource_group: str,
        wait: bool = True
    ) -> LifecycleResult:
        """Start a stopped VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            wait: Wait for operation to complete (default: True)

        Returns:
            LifecycleResult with operation status

        Raises:
            VMLifecycleControlError: If operation fails
        """

    @classmethod
    def stop_vm(
        cls,
        vm_name: str,
        resource_group: str,
        deallocate: bool = True,
        wait: bool = True
    ) -> LifecycleResult:
        """Stop a running VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            deallocate: Deallocate resources (default: True for cost savings)
            wait: Wait for operation to complete (default: True)

        Returns:
            LifecycleResult with operation status
        """

    @classmethod
    def restart_vm(
        cls,
        vm_name: str,
        resource_group: str
    ) -> LifecycleResult:
        """Restart a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            LifecycleResult with operation status
        """
```

**Example:**

```python
from azlin.vm_lifecycle_control import VMLifecycleController

# Start a VM
result = VMLifecycleController.start_vm("my-vm", "azlin-rg")
print(f"Start operation: {result.success}")

# Stop and deallocate (saves costs)
result = VMLifecycleController.stop_vm(
    "my-vm", "azlin-rg",
    deallocate=True
)
print(f"Stop operation: {result.success}")
```

**Exports:**
```python
__all__ = [
    "LifecycleResult",
    "LifecycleSummary",
    "VMLifecycleControlError",
    "VMLifecycleController",
]
```

---

#### `azlin.vm_updater`

Update development tools on VMs.

**Classes:**

##### `VMUpdater`

Update programming tools and packages on VMs.

```python
class VMUpdater:
    """Update development tools on VMs."""

    @classmethod
    def update_vm(
        cls,
        vm_name: str,
        resource_group: str,
        ssh_key_path: Path,
        timeout: int = 300
    ) -> UpdateResult:
        """Update development tools on a VM.

        Updates: Node.js, Python, Rust, Go, Docker, Azure CLI, GitHub CLI

        Args:
            vm_name: VM name
            resource_group: Resource group name
            ssh_key_path: Path to SSH private key
            timeout: Command timeout in seconds (default: 300)

        Returns:
            UpdateResult with operation status

        Raises:
            VMUpdaterError: If update fails
        """
```

**Example:**

```python
from azlin.vm_updater import VMUpdater
from pathlib import Path

result = VMUpdater.update_vm(
    vm_name="my-vm",
    resource_group="azlin-rg",
    ssh_key_path=Path("~/.ssh/azlin_key"),
    timeout=600
)
print(f"Update completed: {result.success}")
```

**Exports:**
```python
__all__ = ["UpdateResult", "VMUpdateSummary", "VMUpdater", "VMUpdaterError"]
```

---

### VM Status & Monitoring

#### `azlin.status_dashboard`

VM status display and monitoring.

**Classes:**

##### `StatusDashboard`

Display VM status, resource usage, and costs.

```python
class StatusDashboard:
    """Manages VM status display and retrieval."""

    def get_vm_status(
        self,
        vm_name: str,
        resource_group: str
    ) -> VMStatus:
        """Get detailed status for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Returns:
            VMStatus with detailed information
        """

    def display_status(
        self,
        resource_group: str | None = None,
        vm_name: str | None = None
    ) -> None:
        """Display status dashboard.

        Args:
            resource_group: Resource group filter (optional)
            vm_name: Specific VM filter (optional)
        """
```

**Data Classes:**

```python
@dataclass
class VMStatus:
    """VM status information."""
    name: str
    status: str
    power_state: str
    resource_group: str
    location: str
    size: str
    public_ip: str | None
    provisioning_state: str
    os_type: str
    uptime: str | None = None
    cpu_usage: float | None = None
    memory_usage: float | None = None
    estimated_cost: float | None = None
```

**Example:**

```python
from azlin.status_dashboard import StatusDashboard

dashboard = StatusDashboard()

# Get status for specific VM
status = dashboard.get_vm_status("my-vm", "azlin-rg")
print(f"VM: {status.name}")
print(f"State: {status.power_state}")
print(f"Cost: ${status.estimated_cost:.2f}/month")

# Display full dashboard
dashboard.display_status(resource_group="azlin-rg")
```

---

#### `azlin.connection_tracker`

Track SSH connections to VMs.

**Classes:**

##### `ConnectionTracker`

Track and record SSH connection history.

```python
class ConnectionTracker:
    """Track SSH connections to VMs."""

    @classmethod
    def record_connection(
        cls,
        vm_name: str,
        vm_ip: str,
        session_name: str | None = None
    ) -> None:
        """Record a successful connection.

        Args:
            vm_name: VM name
            vm_ip: VM IP address
            session_name: Session name (optional)
        """

    @classmethod
    def get_last_connection(cls) -> dict[str, str] | None:
        """Get last connection details.

        Returns:
            Dictionary with vm_name, vm_ip, timestamp, or None
        """
```

**Exports:**
```python
__all__ = ["ConnectionTracker", "ConnectionTrackerError"]
```

---

## Connection & SSH

### SSH Connection

#### `azlin.modules.ssh_connector`

SSH connection management with tmux support.

**Classes:**

##### `SSHConnector`

Manage SSH connections to VMs with automatic tmux session handling.

```python
class SSHConnector:
    """Manage SSH connections to VMs."""

    @classmethod
    def connect(
        cls,
        ssh_config: SSHConfig,
        auto_reconnect: bool = True,
        max_reconnect_attempts: int = 3
    ) -> int:
        """Connect to VM via SSH.

        Args:
            ssh_config: SSH configuration
            auto_reconnect: Enable auto-reconnect on disconnect (default: True)
            max_reconnect_attempts: Maximum reconnect attempts (default: 3)

        Returns:
            Exit code from SSH session

        Raises:
            SSHConnectionError: If connection fails
        """

    @classmethod
    def test_connection(cls, ssh_config: SSHConfig, timeout: int = 10) -> bool:
        """Test SSH connection.

        Args:
            ssh_config: SSH configuration
            timeout: Connection timeout in seconds

        Returns:
            True if connection successful, False otherwise
        """

    @classmethod
    def wait_for_ssh(
        cls,
        ssh_config: SSHConfig,
        max_wait: int = 300,
        check_interval: int = 5
    ) -> bool:
        """Wait for SSH to become available.

        Args:
            ssh_config: SSH configuration
            max_wait: Maximum wait time in seconds (default: 300)
            check_interval: Check interval in seconds (default: 5)

        Returns:
            True if SSH becomes available, False if timeout
        """
```

**Data Classes:**

```python
@dataclass
class SSHConfig:
    """SSH connection configuration."""

    host: str
    user: str = "azureuser"
    port: int = 22
    key_path: Path | None = None
    tmux_session: str | None = None
    command: str | None = None
```

**Functions:**

```python
def connect_ssh(
    host: str,
    user: str = "azureuser",
    key_path: Path | None = None,
    tmux_session: str | None = None
) -> int:
    """Convenience function to connect via SSH.

    Args:
        host: Hostname or IP address
        user: SSH username (default: "azureuser")
        key_path: Path to SSH private key (optional)
        tmux_session: Tmux session name (optional)

    Returns:
        Exit code from SSH session
    """
```

**Example:**

```python
from azlin.modules.ssh_connector import SSHConnector, SSHConfig, connect_ssh
from pathlib import Path

# Using SSHConfig
ssh_config = SSHConfig(
    host="20.12.34.56",
    user="azureuser",
    key_path=Path("~/.ssh/azlin_key"),
    tmux_session="my-session"
)

# Test connection first
if SSHConnector.test_connection(ssh_config):
    # Connect with auto-reconnect
    exit_code = SSHConnector.connect(ssh_config, auto_reconnect=True)
else:
    print("SSH not available")

# Or use convenience function
exit_code = connect_ssh(
    host="20.12.34.56",
    key_path=Path("~/.ssh/azlin_key"),
    tmux_session="dev-session"
)
```

**Exports:**
```python
__all__ = ["SSHConfig", "SSHConnectionError", "SSHConnector", "connect_ssh"]
```

---

### SSH Keys

#### `azlin.modules.ssh_keys`

SSH key generation and management.

**Classes:**

##### `SSHKeyManager`

Generate and manage SSH keys for VMs.

```python
class SSHKeyManager:
    """Manage SSH keys for Azure VMs."""

    DEFAULT_KEY_DIR = Path.home() / ".ssh"

    @classmethod
    def generate_key_pair(
        cls,
        key_name: str = "azlin_key",
        key_dir: Path | None = None
    ) -> tuple[Path, Path]:
        """Generate SSH key pair.

        Args:
            key_name: Key name (default: "azlin_key")
            key_dir: Directory for keys (default: ~/.ssh)

        Returns:
            Tuple of (private_key_path, public_key_path)

        Raises:
            SSHKeyError: If key generation fails
        """

    @classmethod
    def key_exists(cls, key_name: str = "azlin_key") -> bool:
        """Check if SSH key pair exists.

        Args:
            key_name: Key name to check

        Returns:
            True if both private and public keys exist
        """

    @classmethod
    def get_public_key_content(cls, public_key_path: Path) -> str:
        """Read public key content.

        Args:
            public_key_path: Path to public key file

        Returns:
            Public key content as string
        """
```

**Example:**

```python
from azlin.modules.ssh_keys import SSHKeyManager
from pathlib import Path

# Check if keys exist
if not SSHKeyManager.key_exists("azlin_key"):
    # Generate new key pair
    private_key, public_key = SSHKeyManager.generate_key_pair()
    print(f"Generated keys: {private_key}, {public_key}")
else:
    print("Keys already exist")

# Read public key content
public_key_path = Path.home() / ".ssh" / "azlin_key.pub"
content = SSHKeyManager.get_public_key_content(public_key_path)
```

**Exports:**
```python
__all__ = ["SSHKeyError", "SSHKeyManager"]
```

---

### SSH Reconnect

#### `azlin.modules.ssh_reconnect`

Automatic SSH reconnection handling.

**Classes:**

##### `SSHReconnectHandler`

Handle SSH disconnections and automatic reconnection.

```python
class SSHReconnectHandler:
    """Handle SSH reconnection logic."""

    @classmethod
    def handle_disconnect(
        cls,
        exit_code: int,
        ssh_config: SSHConfig,
        max_attempts: int = 3
    ) -> int:
        """Handle SSH disconnect and attempt reconnection.

        Args:
            exit_code: Exit code from SSH session
            ssh_config: SSH configuration
            max_attempts: Maximum reconnection attempts (default: 3)

        Returns:
            Final exit code after reconnection attempts
        """
```

**Functions:**

```python
def is_disconnect_exit_code(exit_code: int) -> bool:
    """Check if exit code indicates a disconnect.

    Args:
        exit_code: Exit code to check

    Returns:
        True if exit code indicates disconnect
    """

def should_attempt_reconnect(exit_code: int) -> bool:
    """Determine if reconnection should be attempted.

    Args:
        exit_code: Exit code to check

    Returns:
        True if reconnection should be attempted
    """
```

**Example:**

```python
from azlin.modules.ssh_reconnect import (
    SSHReconnectHandler,
    is_disconnect_exit_code,
    should_attempt_reconnect
)

# Check exit code
exit_code = 255  # SSH disconnect
if is_disconnect_exit_code(exit_code):
    if should_attempt_reconnect(exit_code):
        # Attempt reconnection
        new_exit_code = SSHReconnectHandler.handle_disconnect(
            exit_code,
            ssh_config,
            max_attempts=3
        )
```

**Exports:**
```python
__all__ = ["SSHReconnectHandler", "is_disconnect_exit_code", "should_attempt_reconnect"]
```

---

## File Operations

### File Transfer

#### `azlin.modules.file_transfer`

Secure bidirectional file transfer between local and VMs.

**Classes:**

##### `FileTransfer`

Secure file transfer using scp with validation.

```python
class FileTransfer:
    """Secure file transfer for azlin cp command."""

    @classmethod
    def transfer(
        cls,
        source: TransferEndpoint,
        destination: TransferEndpoint,
        recursive: bool = False,
        dry_run: bool = False
    ) -> TransferResult:
        """Transfer files between endpoints.

        Args:
            source: Source endpoint
            destination: Destination endpoint
            recursive: Copy directories recursively (default: False)
            dry_run: Preview without transferring (default: False)

        Returns:
            TransferResult with operation status

        Raises:
            FileTransferError: If transfer fails
            SecurityValidationError: If security validation fails
        """
```

##### `PathParser`

Parse and validate file transfer paths.

```python
class PathParser:
    """Parse file transfer paths."""

    @classmethod
    def parse(cls, path: str) -> tuple[str | None, str]:
        """Parse path into (session_name, file_path).

        Args:
            path: Path string (e.g., "vm1:~/file.txt" or "/local/file.txt")

        Returns:
            Tuple of (session_name or None, file_path)

        Raises:
            InvalidPathError: If path is invalid
        """
```

##### `SessionManager`

Manage VM session resolution for file transfer.

```python
class SessionManager:
    """Manage VM sessions for file transfer."""

    @classmethod
    def resolve_session(
        cls,
        session_name: str,
        resource_group: str | None = None
    ) -> VMSession:
        """Resolve session name to VM details.

        Args:
            session_name: Session name or VM name
            resource_group: Resource group (optional)

        Returns:
            VMSession with VM details

        Raises:
            SessionNotFoundError: If session not found
            MultipleSessionsError: If multiple matches found
        """
```

**Data Classes:**

```python
@dataclass
class TransferEndpoint:
    """File transfer endpoint."""
    is_remote: bool
    path: str
    host: str | None = None
    user: str = "azureuser"
    key_path: Path | None = None

@dataclass
class TransferResult:
    """File transfer result."""
    success: bool
    bytes_transferred: int
    duration: float
    error_message: str | None = None

@dataclass
class VMSession:
    """VM session information."""
    vm_name: str
    ip_address: str
    resource_group: str
    session_name: str | None = None
```

**Example:**

```python
from azlin.modules.file_transfer import (
    FileTransfer,
    PathParser,
    SessionManager,
    TransferEndpoint
)
from pathlib import Path

# Parse paths
session, path = PathParser.parse("my-vm:~/data.txt")
print(f"Session: {session}, Path: {path}")

# Resolve session to VM
vm_session = SessionManager.resolve_session(session)
print(f"VM IP: {vm_session.ip_address}")

# Create endpoints
source = TransferEndpoint(
    is_remote=False,
    path="/local/file.txt"
)
destination = TransferEndpoint(
    is_remote=True,
    path="/home/azureuser/file.txt",
    host=vm_session.ip_address,
    key_path=Path("~/.ssh/azlin_key")
)

# Transfer file
result = FileTransfer.transfer(source, destination)
if result.success:
    print(f"Transferred {result.bytes_transferred} bytes in {result.duration:.2f}s")
```

**Exports:**
```python
__all__ = [
    "FileTransfer",
    "FileTransferError",
    "InvalidPathError",
    "InvalidSessionNameError",
    "InvalidTransferError",
    "MultipleSessionsError",
    "PathParser",
    "PathTraversalError",
    "SessionManager",
    "SessionNotFoundError",
    "SymlinkSecurityError",
    "TransferEndpoint",
    "TransferError",
    "TransferResult",
    "VMSession",
]
```

---

### Home Directory Sync

#### `azlin.modules.home_sync`

Sync dotfiles from ~/.azlin/home/ to VMs.

**Classes:**

##### `HomeSyncManager`

Sync home directory contents to VMs with security validation.

```python
class HomeSyncManager:
    """Manage home directory synchronization."""

    HOME_SYNC_DIR = Path.home() / ".azlin" / "home"

    @classmethod
    def sync_to_vm(
        cls,
        vm_ip: str,
        ssh_key_path: Path,
        dry_run: bool = False,
        ssh_user: str = "azureuser"
    ) -> SyncResult:
        """Sync home directory to VM.

        Args:
            vm_ip: VM IP address
            ssh_key_path: Path to SSH private key
            dry_run: Preview without syncing (default: False)
            ssh_user: SSH username (default: "azureuser")

        Returns:
            SyncResult with operation status

        Raises:
            HomeSyncError: If sync fails
            SecurityValidationError: If security validation fails
        """

    @classmethod
    def validate_sync_directory(cls) -> ValidationResult:
        """Validate sync directory for security issues.

        Returns:
            ValidationResult with validation status and warnings
        """
```

**Data Classes:**

```python
@dataclass
class SyncResult:
    """Home directory sync result."""
    success: bool
    files_synced: int
    bytes_transferred: int
    duration: float
    warnings: list[SecurityWarning]
    error_message: str | None = None

@dataclass
class ValidationResult:
    """Security validation result."""
    is_safe: bool
    warnings: list[SecurityWarning]
    blocked_files: list[str]

@dataclass
class SecurityWarning:
    """Security warning for potentially sensitive files."""
    file_path: str
    reason: str
    severity: str  # "error", "warning", "info"
```

**Example:**

```python
from azlin.modules.home_sync import HomeSyncManager, HomeSyncError
from pathlib import Path

try:
    # Validate sync directory first
    validation = HomeSyncManager.validate_sync_directory()
    if not validation.is_safe:
        print(f"Security issues: {len(validation.warnings)}")
        for warning in validation.warnings:
            print(f"  {warning.severity}: {warning.file_path} - {warning.reason}")

    # Sync to VM
    result = HomeSyncManager.sync_to_vm(
        vm_ip="20.12.34.56",
        ssh_key_path=Path("~/.ssh/azlin_key"),
        dry_run=False
    )

    if result.success:
        print(f"Synced {result.files_synced} files ({result.bytes_transferred} bytes)")
    else:
        print(f"Sync failed: {result.error_message}")

except HomeSyncError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = [
    "HomeSyncError",
    "HomeSyncManager",
    "RsyncError",
    "SecurityValidationError",
    "SecurityWarning",
    "SyncResult",
    "ValidationResult",
]
```

---

## Storage Management

### NFS Storage

#### `azlin.modules.storage_manager`

Azure Files NFS storage account management.

**Classes:**

##### `StorageManager`

Manage Azure Files NFS storage accounts for shared home directories.

```python
class StorageManager:
    """Azure Files NFS storage account management."""

    @classmethod
    def create_storage(
        cls,
        name: str,
        resource_group: str,
        region: str,
        size_gb: int,
        tier: str = "Premium"
    ) -> StorageInfo:
        """Create NFS storage account.

        Args:
            name: Storage account name (3-24 lowercase alphanumeric)
            resource_group: Resource group name
            region: Azure region
            size_gb: Size in GB
            tier: "Premium" or "Standard" (default: "Premium")

        Returns:
            StorageInfo with storage details

        Raises:
            StorageError: If creation fails
            ValidationError: If input validation fails
        """

    @classmethod
    def delete_storage(
        cls,
        name: str,
        resource_group: str,
        force: bool = False
    ) -> None:
        """Delete storage account.

        Args:
            name: Storage account name
            resource_group: Resource group name
            force: Skip confirmation if no connected VMs

        Raises:
            StorageNotFoundError: If storage not found
            StorageInUseError: If storage has connected VMs
        """

    @classmethod
    def list_storage(cls, resource_group: str) -> list[StorageInfo]:
        """List all NFS storage accounts.

        Args:
            resource_group: Resource group name

        Returns:
            List of StorageInfo objects
        """

    @classmethod
    def get_storage_status(
        cls,
        name: str,
        resource_group: str
    ) -> StorageStatus:
        """Get detailed storage status.

        Args:
            name: Storage account name
            resource_group: Resource group name

        Returns:
            StorageStatus with usage and connected VMs

        Raises:
            StorageNotFoundError: If storage not found
        """
```

**Data Classes:**

```python
@dataclass
class StorageInfo:
    """Storage account information."""
    name: str
    resource_group: str
    region: str
    tier: str  # "Premium" or "Standard"
    size_gb: int
    nfs_endpoint: str
    created: datetime

@dataclass
class StorageStatus:
    """Detailed storage status."""
    info: StorageInfo
    used_gb: float
    utilization_percent: float
    connected_vms: list[str]
    cost_per_month: float
```

**Example:**

```python
from azlin.modules.storage_manager import StorageManager, StorageError

try:
    # Create NFS storage
    storage = StorageManager.create_storage(
        name="teamshared",
        resource_group="azlin-rg",
        region="westus2",
        size_gb=100,
        tier="Premium"
    )
    print(f"Created storage: {storage.nfs_endpoint}")

    # List storage accounts
    storage_list = StorageManager.list_storage("azlin-rg")
    for s in storage_list:
        print(f"{s.name}: {s.size_gb}GB {s.tier}")

    # Get storage status
    status = StorageManager.get_storage_status("teamshared", "azlin-rg")
    print(f"Usage: {status.used_gb:.1f}GB ({status.utilization_percent:.1f}%)")
    print(f"Cost: ${status.cost_per_month:.2f}/month")
    print(f"Connected VMs: {len(status.connected_vms)}")

except StorageError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = [
    "StorageError",
    "StorageInUseError",
    "StorageInfo",
    "StorageManager",
    "StorageNotFoundError",
    "StorageStatus",
    "ValidationError",
]
```

---

### NFS Mount Management

#### `azlin.modules.nfs_mount_manager`

Mount Azure Files NFS shares on VMs.

**Classes:**

##### `NFSMountManager`

Manage NFS mount operations on VMs.

```python
class NFSMountManager:
    """Manage NFS mount operations."""

    @classmethod
    def mount_nfs(
        cls,
        vm_ip: str,
        nfs_endpoint: str,
        mount_point: str,
        ssh_key_path: Path,
        ssh_user: str = "azureuser"
    ) -> MountResult:
        """Mount NFS share on VM.

        Args:
            vm_ip: VM IP address
            nfs_endpoint: NFS endpoint (e.g., "storage.file.core.windows.net:/share")
            mount_point: Mount point path (e.g., "/mnt/shared")
            ssh_key_path: Path to SSH private key
            ssh_user: SSH username (default: "azureuser")

        Returns:
            MountResult with operation status
        """

    @classmethod
    def unmount_nfs(
        cls,
        vm_ip: str,
        mount_point: str,
        ssh_key_path: Path,
        ssh_user: str = "azureuser"
    ) -> UnmountResult:
        """Unmount NFS share from VM.

        Args:
            vm_ip: VM IP address
            mount_point: Mount point path
            ssh_key_path: Path to SSH private key
            ssh_user: SSH username (default: "azureuser")

        Returns:
            UnmountResult with operation status
        """

    @classmethod
    def get_mount_info(
        cls,
        vm_ip: str,
        ssh_key_path: Path
    ) -> list[MountInfo]:
        """Get NFS mount information from VM.

        Args:
            vm_ip: VM IP address
            ssh_key_path: Path to SSH private key

        Returns:
            List of MountInfo objects
        """
```

**Data Classes:**

```python
@dataclass
class MountResult:
    """NFS mount operation result."""
    success: bool
    mount_point: str
    nfs_endpoint: str
    error_message: str | None = None

@dataclass
class UnmountResult:
    """NFS unmount operation result."""
    success: bool
    mount_point: str
    error_message: str | None = None

@dataclass
class MountInfo:
    """NFS mount information."""
    mount_point: str
    nfs_endpoint: str
    filesystem_type: str
```

**Example:**

```python
from azlin.modules.nfs_mount_manager import NFSMountManager
from pathlib import Path

# Mount NFS share
result = NFSMountManager.mount_nfs(
    vm_ip="20.12.34.56",
    nfs_endpoint="storage.file.core.windows.net:/share",
    mount_point="/home/azureuser",
    ssh_key_path=Path("~/.ssh/azlin_key")
)

if result.success:
    print(f"Mounted {result.nfs_endpoint} at {result.mount_point}")
else:
    print(f"Mount failed: {result.error_message}")

# Get mount information
mounts = NFSMountManager.get_mount_info(
    vm_ip="20.12.34.56",
    ssh_key_path=Path("~/.ssh/azlin_key")
)
for mount in mounts:
    print(f"{mount.mount_point}: {mount.nfs_endpoint}")
```

**Exports:**
```python
__all__ = [
    "MountInfo",
    "MountResult",
    "NFSMountManager",
    "UnmountResult",
]
```

---

### Snapshot Management

#### `azlin.modules.snapshot_manager`

Automated VM disk snapshots.

**Classes:**

##### `SnapshotManager`

Manage automated disk snapshots for VMs.

```python
class SnapshotManager:
    """Manage VM disk snapshots."""

    @classmethod
    def create_snapshot(
        cls,
        vm_name: str,
        resource_group: str,
        snapshot_name: str | None = None
    ) -> SnapshotInfo:
        """Create a snapshot of VM disk.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            snapshot_name: Custom snapshot name (optional)

        Returns:
            SnapshotInfo with snapshot details

        Raises:
            SnapshotError: If snapshot creation fails
        """

    @classmethod
    def enable_automated_snapshots(
        cls,
        vm_name: str,
        resource_group: str,
        schedule: SnapshotSchedule
    ) -> None:
        """Enable automated snapshots.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            schedule: Snapshot schedule configuration
        """

    @classmethod
    def list_snapshots(
        cls,
        resource_group: str,
        vm_name: str | None = None
    ) -> list[SnapshotInfo]:
        """List snapshots.

        Args:
            resource_group: Resource group name
            vm_name: Filter by VM name (optional)

        Returns:
            List of SnapshotInfo objects
        """
```

**Data Classes:**

```python
@dataclass
class SnapshotSchedule:
    """Snapshot schedule configuration."""
    frequency: str  # "hourly", "daily", "weekly"
    retention_days: int
    enabled: bool = True

@dataclass
class SnapshotInfo:
    """Snapshot information."""
    name: str
    resource_group: str
    vm_name: str
    created_time: datetime
    size_gb: int
```

**Example:**

```python
from azlin.modules.snapshot_manager import (
    SnapshotManager,
    SnapshotSchedule,
    SnapshotError
)

try:
    # Create manual snapshot
    snapshot = SnapshotManager.create_snapshot(
        vm_name="my-vm",
        resource_group="azlin-rg"
    )
    print(f"Created snapshot: {snapshot.name}")

    # Enable automated snapshots
    schedule = SnapshotSchedule(
        frequency="daily",
        retention_days=7
    )
    SnapshotManager.enable_automated_snapshots(
        vm_name="my-vm",
        resource_group="azlin-rg",
        schedule=schedule
    )

    # List snapshots
    snapshots = SnapshotManager.list_snapshots(
        resource_group="azlin-rg",
        vm_name="my-vm"
    )
    for s in snapshots:
        print(f"{s.name}: {s.size_gb}GB created {s.created_time}")

except SnapshotError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["SnapshotError", "SnapshotInfo", "SnapshotManager", "SnapshotSchedule"]
```

---

## Cost & Resource Management

### Cost Tracking

#### `azlin.cost_tracker`

Azure VM cost tracking and estimation.

**Classes:**

##### `CostTracker`

Track and estimate VM costs.

```python
class CostTracker:
    """Track Azure VM costs."""

    @classmethod
    def get_vm_cost_estimate(
        cls,
        vm_size: str,
        hours_running: float | None = None
    ) -> VMCostEstimate:
        """Get cost estimate for VM.

        Args:
            vm_size: VM size (e.g., "Standard_B2s")
            hours_running: Hours running (optional, defaults to monthly)

        Returns:
            VMCostEstimate with cost details
        """

    @classmethod
    def get_resource_group_costs(
        cls,
        resource_group: str,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> CostSummary:
        """Get costs for resource group.

        Args:
            resource_group: Resource group name
            start_date: Start date (YYYY-MM-DD, optional)
            end_date: End date (YYYY-MM-DD, optional)

        Returns:
            CostSummary with detailed cost breakdown

        Raises:
            CostTrackerError: If cost retrieval fails
        """

    @classmethod
    def get_vm_specific_costs(
        cls,
        vm_name: str,
        resource_group: str,
        start_date: str | None = None,
        end_date: str | None = None
    ) -> float:
        """Get costs for specific VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Total cost in USD
        """
```

**Data Classes:**

```python
@dataclass
class VMCostEstimate:
    """VM cost estimate."""
    vm_size: str
    hourly_cost: float
    daily_cost: float
    monthly_cost: float
    annual_cost: float

@dataclass
class CostSummary:
    """Cost summary for resource group."""
    resource_group: str
    total_cost: float
    start_date: str
    end_date: str
    vm_costs: dict[str, float]  # vm_name -> cost
```

**Example:**

```python
from azlin.cost_tracker import CostTracker, CostTrackerError

try:
    # Get VM cost estimate
    estimate = CostTracker.get_vm_cost_estimate("Standard_B2s")
    print(f"Hourly: ${estimate.hourly_cost:.4f}")
    print(f"Monthly: ${estimate.monthly_cost:.2f}")

    # Get resource group costs
    summary = CostTracker.get_resource_group_costs(
        resource_group="azlin-rg",
        start_date="2025-01-01",
        end_date="2025-01-31"
    )
    print(f"Total: ${summary.total_cost:.2f}")
    for vm_name, cost in summary.vm_costs.items():
        print(f"  {vm_name}: ${cost:.2f}")

except CostTrackerError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["CostSummary", "CostTracker", "CostTrackerError", "VMCostEstimate"]
```

---

### Resource Cleanup

#### `azlin.resource_cleanup`

Identify and clean up orphaned Azure resources.

**Classes:**

##### `ResourceCleanup`

Find and remove orphaned resources (disks, NICs, IPs).

```python
class ResourceCleanup:
    """Clean up orphaned Azure resources."""

    @classmethod
    def find_orphaned_resources(
        cls,
        resource_group: str
    ) -> list[OrphanedResource]:
        """Find orphaned resources in resource group.

        Args:
            resource_group: Resource group name

        Returns:
            List of OrphanedResource objects

        Raises:
            ResourceCleanupError: If scan fails
        """

    @classmethod
    def cleanup_orphaned_resources(
        cls,
        resource_group: str,
        dry_run: bool = False,
        force: bool = False
    ) -> CleanupSummary:
        """Clean up orphaned resources.

        Args:
            resource_group: Resource group name
            dry_run: Preview without deleting (default: False)
            force: Skip confirmation (default: False)

        Returns:
            CleanupSummary with cleanup results
        """
```

**Data Classes:**

```python
@dataclass
class OrphanedResource:
    """Orphaned resource information."""
    resource_type: str  # "disk", "nic", "public-ip"
    resource_name: str
    resource_id: str
    estimated_cost_monthly: float

@dataclass
class CleanupSummary:
    """Resource cleanup summary."""
    total_found: int
    total_deleted: int
    total_failed: int
    estimated_savings_monthly: float
    resources: list[OrphanedResource]
```

**Example:**

```python
from azlin.resource_cleanup import ResourceCleanup, ResourceCleanupError

try:
    # Find orphaned resources
    orphaned = ResourceCleanup.find_orphaned_resources("azlin-rg")
    print(f"Found {len(orphaned)} orphaned resources")
    for resource in orphaned:
        print(f"  {resource.resource_type}: {resource.resource_name}")
        print(f"    Estimated cost: ${resource.estimated_cost_monthly:.2f}/month")

    # Clean up with dry-run first
    summary = ResourceCleanup.cleanup_orphaned_resources(
        resource_group="azlin-rg",
        dry_run=True
    )
    print(f"Would delete {summary.total_found} resources")
    print(f"Estimated savings: ${summary.estimated_savings_monthly:.2f}/month")

    # Actual cleanup
    summary = ResourceCleanup.cleanup_orphaned_resources(
        resource_group="azlin-rg",
        force=True
    )
    print(f"Deleted {summary.total_deleted} resources")

except ResourceCleanupError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["CleanupSummary", "OrphanedResource", "ResourceCleanup", "ResourceCleanupError"]
```

---

## Remote Execution

### Command Execution

#### `azlin.remote_exec`

Execute commands remotely on VMs via SSH.

**Classes:**

##### `RemoteExecutor`

Execute commands on VMs remotely.

```python
class RemoteExecutor:
    """Execute commands on VMs remotely."""

    @classmethod
    def execute(
        cls,
        vm_ip: str,
        command: str,
        ssh_key_path: Path,
        timeout: int = 300,
        ssh_user: str = "azureuser"
    ) -> RemoteResult:
        """Execute command on VM.

        Args:
            vm_ip: VM IP address
            command: Command to execute
            ssh_key_path: Path to SSH private key
            timeout: Command timeout in seconds (default: 300)
            ssh_user: SSH username (default: "azureuser")

        Returns:
            RemoteResult with command output and exit code

        Raises:
            RemoteExecError: If execution fails
        """
```

##### `WCommandExecutor`

Execute 'w' command to show logged-in users.

```python
class WCommandExecutor:
    """Execute 'w' command on VMs."""

    @classmethod
    def execute_on_vm(
        cls,
        vm_info: VMInfo,
        ssh_key_path: Path
    ) -> RemoteResult:
        """Execute 'w' command on a VM.

        Args:
            vm_info: VM information
            ssh_key_path: Path to SSH private key

        Returns:
            RemoteResult with 'w' command output
        """
```

##### `PSCommandExecutor`

Execute 'ps aux' command to show processes.

```python
class PSCommandExecutor:
    """Execute 'ps aux' command on VMs."""

    @classmethod
    def execute_on_vm(
        cls,
        vm_info: VMInfo,
        ssh_key_path: Path
    ) -> RemoteResult:
        """Execute 'ps aux' command on a VM.

        Args:
            vm_info: VM information
            ssh_key_path: Path to SSH private key

        Returns:
            RemoteResult with process list
        """
```

##### `OSUpdateExecutor`

Execute OS package updates (apt update && apt upgrade).

```python
class OSUpdateExecutor:
    """Execute OS updates on VMs."""

    @classmethod
    def execute_on_vm(
        cls,
        vm_info: VMInfo,
        ssh_key_path: Path,
        timeout: int = 600
    ) -> RemoteResult:
        """Execute OS updates on a VM.

        Args:
            vm_info: VM information
            ssh_key_path: Path to SSH private key
            timeout: Update timeout in seconds (default: 600)

        Returns:
            RemoteResult with update output
        """
```

**Data Classes:**

```python
@dataclass
class RemoteResult:
    """Remote command execution result."""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration: float
```

**Example:**

```python
from azlin.remote_exec import (
    RemoteExecutor,
    WCommandExecutor,
    PSCommandExecutor,
    OSUpdateExecutor,
    RemoteExecError
)
from azlin.vm_manager import VMManager
from pathlib import Path

try:
    # Execute custom command
    result = RemoteExecutor.execute(
        vm_ip="20.12.34.56",
        command="uname -a",
        ssh_key_path=Path("~/.ssh/azlin_key"),
        timeout=30
    )
    print(f"Output: {result.stdout}")

    # Get VM info
    vm = VMManager.get_vm_by_name("my-vm", "azlin-rg")
    key_path = Path("~/.ssh/azlin_key")

    # Execute 'w' command
    w_result = WCommandExecutor.execute_on_vm(vm, key_path)
    print(f"Logged in users:\n{w_result.stdout}")

    # Execute 'ps' command
    ps_result = PSCommandExecutor.execute_on_vm(vm, key_path)
    print(f"Processes:\n{ps_result.stdout}")

    # Execute OS updates
    update_result = OSUpdateExecutor.execute_on_vm(vm, key_path, timeout=600)
    print(f"Update completed in {update_result.duration:.1f}s")

except RemoteExecError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = [
    "OSUpdateExecutor",
    "PSCommandExecutor",
    "RemoteExecError",
    "RemoteExecutor",
    "RemoteResult",
    "WCommandExecutor",
]
```

---

### Batch Operations

#### `azlin.batch_executor`

Execute operations on multiple VMs in parallel.

**Classes:**

##### `BatchExecutor`

Execute operations on multiple VMs concurrently.

```python
class BatchExecutor:
    """Execute operations on multiple VMs in parallel."""

    @classmethod
    def execute_batch(
        cls,
        vms: list[VMInfo],
        operation: callable,
        max_workers: int = 10
    ) -> BatchResult:
        """Execute operation on multiple VMs.

        Args:
            vms: List of VMs to operate on
            operation: Callable that takes VMInfo and returns result
            max_workers: Maximum concurrent workers (default: 10)

        Returns:
            BatchResult with all operation results

        Raises:
            BatchExecutorError: If batch execution fails
        """
```

##### `BatchSelector`

Select VMs for batch operations using filters.

```python
class BatchSelector:
    """Select VMs for batch operations."""

    @classmethod
    def select_by_tag(
        cls,
        vms: list[VMInfo],
        tag_filter: TagFilter
    ) -> list[VMInfo]:
        """Select VMs by tag.

        Args:
            vms: List of VMs to filter
            tag_filter: Tag filter criteria

        Returns:
            Filtered list of VMInfo objects
        """

    @classmethod
    def select_by_prefix(
        cls,
        vms: list[VMInfo],
        prefix: str
    ) -> list[VMInfo]:
        """Select VMs by name prefix.

        Args:
            vms: List of VMs to filter
            prefix: Name prefix to match

        Returns:
            Filtered list of VMInfo objects
        """
```

**Data Classes:**

```python
@dataclass
class TagFilter:
    """Tag filter for VM selection."""
    key: str
    value: str | None = None
    operator: str = "equals"  # "equals", "contains", "startswith"

@dataclass
class BatchOperationResult:
    """Result from single batch operation."""
    vm_name: str
    success: bool
    result: Any
    error_message: str | None = None

@dataclass
class BatchResult:
    """Results from batch execution."""
    total: int
    successful: int
    failed: int
    results: list[BatchOperationResult]
    duration: float
```

**Example:**

```python
from azlin.batch_executor import (
    BatchExecutor,
    BatchSelector,
    TagFilter,
    BatchExecutorError
)
from azlin.vm_manager import VMManager
from azlin.remote_exec import RemoteExecutor
from pathlib import Path

try:
    # Get all VMs
    all_vms = VMManager.list_vms("azlin-rg")

    # Select VMs by prefix
    worker_vms = BatchSelector.select_by_prefix(all_vms, "worker-")
    print(f"Selected {len(worker_vms)} worker VMs")

    # Define operation
    def check_disk_space(vm_info):
        result = RemoteExecutor.execute(
            vm_ip=vm_info.public_ip,
            command="df -h /",
            ssh_key_path=Path("~/.ssh/azlin_key")
        )
        return result.stdout

    # Execute batch operation
    batch_result = BatchExecutor.execute_batch(
        vms=worker_vms,
        operation=check_disk_space,
        max_workers=5
    )

    print(f"Completed {batch_result.successful}/{batch_result.total} operations")
    for result in batch_result.results:
        if result.success:
            print(f"{result.vm_name}: {result.result}")
        else:
            print(f"{result.vm_name}: FAILED - {result.error_message}")

except BatchExecutorError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = [
    "BatchExecutor",
    "BatchExecutorError",
    "BatchOperationResult",
    "BatchResult",
    "BatchSelector",
    "TagFilter",
]
```

---

## Advanced Features

### Templates

#### `azlin.template_manager`

Save and restore VM configurations as templates.

**Classes:**

##### `TemplateManager`

Manage VM configuration templates.

```python
class TemplateManager:
    """Manage VM configuration templates."""

    TEMPLATE_DIR = Path.home() / ".azlin" / "templates"

    @classmethod
    def create_template(
        cls,
        name: str,
        config: VMTemplateConfig
    ) -> None:
        """Create a VM template.

        Args:
            name: Template name
            config: Template configuration

        Raises:
            TemplateError: If template creation fails
        """

    @classmethod
    def load_template(cls, name: str) -> VMTemplateConfig:
        """Load a template.

        Args:
            name: Template name

        Returns:
            VMTemplateConfig object

        Raises:
            TemplateError: If template not found
        """

    @classmethod
    def list_templates(cls) -> list[str]:
        """List all available templates.

        Returns:
            List of template names
        """

    @classmethod
    def delete_template(cls, name: str) -> None:
        """Delete a template.

        Args:
            name: Template name

        Raises:
            TemplateError: If template not found
        """
```

**Data Classes:**

```python
@dataclass
class VMTemplateConfig:
    """VM template configuration."""
    name: str
    vm_size: str
    region: str
    image: str
    admin_username: str
    install_tools: list[str]
    startup_script: str | None = None
    tags: dict[str, str] | None = None
```

**Example:**

```python
from azlin.template_manager import TemplateManager, VMTemplateConfig, TemplateError

try:
    # Create template
    config = VMTemplateConfig(
        name="dev-template",
        vm_size="Standard_D4s_v3",
        region="westus2",
        image="UbuntuLTS",
        admin_username="azureuser",
        install_tools=["docker", "nodejs", "python"],
        tags={"environment": "development"}
    )
    TemplateManager.create_template("dev-template", config)

    # List templates
    templates = TemplateManager.list_templates()
    print(f"Available templates: {templates}")

    # Load template
    loaded = TemplateManager.load_template("dev-template")
    print(f"Template VM size: {loaded.vm_size}")

    # Delete template
    TemplateManager.delete_template("dev-template")

except TemplateError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["TemplateError", "TemplateManager", "VMTemplateConfig"]
```

---

### SSH Key Rotation

#### `azlin.key_rotator`

Rotate SSH keys across multiple VMs.

**Classes:**

##### `SSHKeyRotator`

Rotate SSH keys for VMs with backup and rollback.

```python
class SSHKeyRotator:
    """Rotate SSH keys for Azure VMs."""

    @classmethod
    def rotate_key(
        cls,
        vm_name: str,
        resource_group: str,
        new_public_key_path: Path,
        backup: bool = True
    ) -> KeyRotationResult:
        """Rotate SSH key for a VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            new_public_key_path: Path to new public key
            backup: Create backup of old key (default: True)

        Returns:
            KeyRotationResult with operation status

        Raises:
            KeyRotationError: If rotation fails
        """

    @classmethod
    def rotate_keys_batch(
        cls,
        vms: list[VMInfo],
        new_public_key_path: Path
    ) -> list[KeyRotationResult]:
        """Rotate keys for multiple VMs.

        Args:
            vms: List of VMs
            new_public_key_path: Path to new public key

        Returns:
            List of KeyRotationResult objects
        """
```

**Data Classes:**

```python
@dataclass
class KeyRotationResult:
    """SSH key rotation result."""
    vm_name: str
    success: bool
    old_key_backed_up: bool
    backup_path: Path | None = None
    error_message: str | None = None
```

**Example:**

```python
from azlin.key_rotator import SSHKeyRotator, KeyRotationError
from azlin.vm_manager import VMManager
from pathlib import Path

try:
    # Rotate key for single VM
    result = SSHKeyRotator.rotate_key(
        vm_name="my-vm",
        resource_group="azlin-rg",
        new_public_key_path=Path("~/.ssh/new_key.pub"),
        backup=True
    )

    if result.success:
        print(f"Key rotated successfully")
        if result.old_key_backed_up:
            print(f"Old key backed up to: {result.backup_path}")

    # Rotate keys for multiple VMs
    vms = VMManager.list_vms("azlin-rg")
    results = SSHKeyRotator.rotate_keys_batch(
        vms=vms,
        new_public_key_path=Path("~/.ssh/new_key.pub")
    )

    successful = sum(1 for r in results if r.success)
    print(f"Rotated keys for {successful}/{len(results)} VMs")

except KeyRotationError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["KeyBackup", "KeyRotationError", "KeyRotationResult", "SSHKeyRotator", "VMKeyInfo"]
```

---

### Distributed Monitoring

#### `azlin.distributed_top`

Live distributed VM metrics dashboard.

**Classes:**

##### `DistributedTopExecutor`

Display live metrics from multiple VMs in a dashboard.

```python
class DistributedTopExecutor:
    """Execute distributed top command across VMs."""

    @classmethod
    def run(
        cls,
        resource_group: str,
        refresh_interval: int = 2,
        sort_by: str = "cpu"
    ) -> None:
        """Run distributed top dashboard.

        Args:
            resource_group: Resource group name
            refresh_interval: Refresh interval in seconds (default: 2)
            sort_by: Sort metric ("cpu", "memory", "name")

        Raises:
            DistributedTopError: If execution fails
        """
```

**Data Classes:**

```python
@dataclass
class VMMetrics:
    """VM metrics snapshot."""
    vm_name: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    load_average: tuple[float, float, float]
    uptime: str
    users_count: int
```

**Example:**

```python
from azlin.distributed_top import DistributedTopExecutor, DistributedTopError

try:
    # Run distributed top dashboard
    DistributedTopExecutor.run(
        resource_group="azlin-rg",
        refresh_interval=2,
        sort_by="cpu"
    )
    # Press Ctrl+C to exit
except DistributedTopError as e:
    print(f"Error: {e}")
except KeyboardInterrupt:
    print("\nExiting dashboard")
```

**Exports:**
```python
__all__ = [
    "DistributedTopError",
    "DistributedTopExecutor",
    "VMMetrics",
    "run_distributed_top",
]
```

---

### Terminal Launcher

#### `azlin.terminal_launcher`

Launch new terminal windows for VMs.

**Classes:**

##### `TerminalLauncher`

Launch new terminal windows with SSH connections.

```python
class TerminalLauncher:
    """Launch terminal windows for VMs."""

    @classmethod
    def launch(
        cls,
        ssh_config: SSHConfig,
        terminal_config: TerminalConfig | None = None
    ) -> int:
        """Launch new terminal window with SSH connection.

        Args:
            ssh_config: SSH configuration
            terminal_config: Terminal-specific configuration (optional)

        Returns:
            Process ID of launched terminal

        Raises:
            TerminalLauncherError: If launch fails
        """
```

**Data Classes:**

```python
@dataclass
class TerminalConfig:
    """Terminal launch configuration."""
    terminal_app: str  # "iterm", "terminal", "gnome-terminal", etc.
    window_title: str | None = None
    new_tab: bool = False
    new_window: bool = True
```

**Example:**

```python
from azlin.terminal_launcher import TerminalLauncher, TerminalConfig
from azlin.modules.ssh_connector import SSHConfig
from pathlib import Path

# Configure SSH
ssh_config = SSHConfig(
    host="20.12.34.56",
    key_path=Path("~/.ssh/azlin_key"),
    tmux_session="dev-session"
)

# Configure terminal
terminal_config = TerminalConfig(
    terminal_app="iterm",
    window_title="My Dev VM",
    new_window=True
)

# Launch terminal
pid = TerminalLauncher.launch(ssh_config, terminal_config)
print(f"Launched terminal with PID: {pid}")
```

**Exports:**
```python
__all__ = ["TerminalConfig", "TerminalLauncher", "TerminalLauncherError"]
```

---

## Utilities

### Prerequisites

#### `azlin.modules.prerequisites`

Check required tools and dependencies.

**Classes:**

##### `PrerequisiteChecker`

Check for required CLI tools and dependencies.

```python
class PrerequisiteChecker:
    """Check for required tools and dependencies."""

    REQUIRED_TOOLS = ["az", "gh", "git", "ssh", "tmux"]

    @classmethod
    def check_all(cls) -> None:
        """Check all prerequisites.

        Raises:
            PrerequisiteError: If any required tool is missing
        """

    @classmethod
    def check_tool(cls, tool: str) -> bool:
        """Check if a specific tool is available.

        Args:
            tool: Tool name to check

        Returns:
            True if tool is available, False otherwise
        """

    @classmethod
    def get_missing_tools(cls) -> list[str]:
        """Get list of missing required tools.

        Returns:
            List of missing tool names
        """
```

**Example:**

```python
from azlin.modules.prerequisites import PrerequisiteChecker, PrerequisiteError

try:
    # Check all prerequisites
    PrerequisiteChecker.check_all()
    print("All prerequisites satisfied")
except PrerequisiteError as e:
    print(f"Missing prerequisites: {e}")

    # Get specific missing tools
    missing = PrerequisiteChecker.get_missing_tools()
    print(f"Missing tools: {', '.join(missing)}")

# Check specific tool
if PrerequisiteChecker.check_tool("docker"):
    print("Docker is available")
```

**Exports:**
```python
__all__ = ["PrerequisiteChecker", "PrerequisiteError"]
```

---

### Progress Display

#### `azlin.modules.progress`

Rich progress bars and status display.

**Classes:**

##### `ProgressDisplay`

Display progress for long-running operations.

```python
class ProgressDisplay:
    """Display progress for operations."""

    def __init__(self, total_stages: int):
        """Initialize progress display.

        Args:
            total_stages: Total number of stages
        """

    def start_stage(self, stage: ProgressStage) -> None:
        """Start a new stage.

        Args:
            stage: Progress stage information
        """

    def complete_stage(self) -> None:
        """Mark current stage as complete."""

    def fail_stage(self, error_message: str) -> None:
        """Mark current stage as failed.

        Args:
            error_message: Error description
        """
```

**Data Classes:**

```python
@dataclass
class ProgressStage:
    """Progress stage information."""
    name: str
    description: str
    estimated_duration: int  # seconds
```

**Example:**

```python
from azlin.modules.progress import ProgressDisplay, ProgressStage
import time

# Create progress display
progress = ProgressDisplay(total_stages=3)

# Stage 1
progress.start_stage(ProgressStage(
    name="Provisioning",
    description="Creating VM resources",
    estimated_duration=180
))
time.sleep(2)
progress.complete_stage()

# Stage 2
progress.start_stage(ProgressStage(
    name="Installing",
    description="Installing development tools",
    estimated_duration=120
))
time.sleep(2)
progress.complete_stage()

# Stage 3
progress.start_stage(ProgressStage(
    name="Connecting",
    description="Establishing SSH connection",
    estimated_duration=10
))
time.sleep(1)
progress.complete_stage()
```

**Exports:**
```python
__all__ = ["ProgressDisplay", "ProgressStage"]
```

---

### Notifications

#### `azlin.modules.notifications`

Send notifications on VM provisioning completion.

**Classes:**

##### `NotificationHandler`

Send desktop notifications.

```python
class NotificationHandler:
    """Handle desktop notifications."""

    @classmethod
    def send(
        cls,
        message: str,
        title: str = "azlin",
        config: NotificationConfig | None = None
    ) -> NotificationResult:
        """Send desktop notification.

        Args:
            message: Notification message
            title: Notification title (default: "azlin")
            config: Notification configuration (optional)

        Returns:
            NotificationResult with send status
        """
```

**Functions:**

```python
def notify(message: str) -> bool:
    """Convenience function to send notification.

    Args:
        message: Notification message

    Returns:
        True if notification sent successfully
    """

def notify_completion(vm_name: str, vm_ip: str) -> bool:
    """Notify VM provisioning completion.

    Args:
        vm_name: VM name
        vm_ip: VM IP address

    Returns:
        True if notification sent successfully
    """

def notify_error(error_message: str) -> bool:
    """Notify error occurrence.

    Args:
        error_message: Error description

    Returns:
        True if notification sent successfully
    """

def is_notification_available() -> bool:
    """Check if notification system is available.

    Returns:
        True if notifications can be sent
    """
```

**Example:**

```python
from azlin.modules.notifications import (
    NotificationHandler,
    notify,
    notify_completion,
    is_notification_available
)

# Check availability
if is_notification_available():
    # Send simple notification
    notify("VM provisioning started")

    # Notify completion
    notify_completion("my-vm", "20.12.34.56")

    # Use handler for custom notifications
    result = NotificationHandler.send(
        message="VM is ready",
        title="azlin - VM Ready"
    )
    print(f"Notification sent: {result.success}")
else:
    print("Notifications not available")
```

**Exports:**
```python
__all__ = [
    "NotificationConfig",
    "NotificationHandler",
    "NotificationResult",
    "is_notification_available",
    "notify",
    "notify_completion",
    "notify_error",
]
```

---

### Tags

#### `azlin.tag_manager`

Manage Azure resource tags.

**Classes:**

##### `TagManager`

Manage tags on Azure resources.

```python
class TagManager:
    """Manage Azure resource tags."""

    @classmethod
    def add_tag(
        cls,
        resource_id: str,
        key: str,
        value: str
    ) -> None:
        """Add tag to resource.

        Args:
            resource_id: Azure resource ID
            key: Tag key
            value: Tag value

        Raises:
            TagManagerError: If tagging fails
        """

    @classmethod
    def remove_tag(
        cls,
        resource_id: str,
        key: str
    ) -> None:
        """Remove tag from resource.

        Args:
            resource_id: Azure resource ID
            key: Tag key to remove
        """

    @classmethod
    def get_tags(cls, resource_id: str) -> dict[str, str]:
        """Get all tags for resource.

        Args:
            resource_id: Azure resource ID

        Returns:
            Dictionary of tags
        """
```

**Example:**

```python
from azlin.tag_manager import TagManager, TagManagerError

try:
    resource_id = "/subscriptions/.../resourceGroups/azlin-rg/providers/Microsoft.Compute/virtualMachines/my-vm"

    # Add tag
    TagManager.add_tag(resource_id, "environment", "development")
    TagManager.add_tag(resource_id, "owner", "team-a")

    # Get tags
    tags = TagManager.get_tags(resource_id)
    print(f"Tags: {tags}")

    # Remove tag
    TagManager.remove_tag(resource_id, "owner")

except TagManagerError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["TagManager", "TagManagerError"]
```

---

### Environment Management

#### `azlin.env_manager`

Manage environment variables and Azure settings.

**Classes:**

##### `EnvManager`

Manage environment configuration.

```python
class EnvManager:
    """Manage environment variables and configuration."""

    @classmethod
    def get_azure_subscription(cls) -> str | None:
        """Get current Azure subscription ID.

        Returns:
            Subscription ID or None if not set
        """

    @classmethod
    def set_azure_subscription(cls, subscription_id: str) -> None:
        """Set Azure subscription.

        Args:
            subscription_id: Subscription ID to set

        Raises:
            EnvManagerError: If setting fails
        """

    @classmethod
    def get_default_region(cls) -> str:
        """Get default Azure region.

        Returns:
            Region name (default: "westus2")
        """
```

**Example:**

```python
from azlin.env_manager import EnvManager, EnvManagerError

try:
    # Get current subscription
    sub_id = EnvManager.get_azure_subscription()
    print(f"Current subscription: {sub_id}")

    # Set subscription
    EnvManager.set_azure_subscription("12345678-1234-1234-1234-123456789012")

    # Get default region
    region = EnvManager.get_default_region()
    print(f"Default region: {region}")

except EnvManagerError as e:
    print(f"Error: {e}")
```

**Exports:**
```python
__all__ = ["EnvManager", "EnvManagerError"]
```

---

## Summary

This API reference covers all public APIs in the azlin project organized by functionality:

- **Core**: CLI, Configuration, Authentication
- **VM Management**: Lifecycle, Provisioning, Operations, Monitoring
- **Connection**: SSH, Keys, Reconnection
- **File Operations**: Transfer, Sync
- **Storage**: NFS Storage, Mounts, Snapshots
- **Cost Management**: Cost Tracking, Resource Cleanup
- **Remote Execution**: Commands, Batch Operations
- **Advanced**: Templates, Key Rotation, Monitoring, Terminal Launch
- **Utilities**: Prerequisites, Progress, Notifications, Tags, Environment

For usage examples and more details, see:
- [README.md](../README.md) - User guide and CLI documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and design
- [testing/test_strategy.md](testing/test_strategy.md) - Testing approach and coverage

---

**Philosophy**: All APIs follow azlin's core principles of ruthless simplicity, security by design, and fail-fast error handling. Each module is a self-contained "brick" with clear inputs, outputs, and error conditions.
