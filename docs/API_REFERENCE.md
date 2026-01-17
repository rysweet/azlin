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
- [Cost Optimization & Intelligence](#cost-optimization--intelligence)
  - [Cost Dashboard](#cost-dashboard)
  - [Cost Optimizer](#cost-optimizer)
  - [Cost History & Trends](#cost-history--trends)
  - [Budget Management](#budget-management)
  - [Cost Actions](#cost-actions)
- [Monitoring & Metrics](#monitoring--metrics)
  - [VM Metrics Collection](#vm-metrics-collection)
- [Network Security Management](#network-security-management)
  - [NSG Management & Validation](#nsg-management--validation)
- [Multi-Tenant Context Management](#multi-tenant-context-management)
  - [Context Management](#context-management)
  - [Fleet Orchestration](#fleet-orchestration)
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
    tmux_sessions: list[TmuxSessionInfo] | None = None  # Tmux session info with connection status

@dataclass
class TmuxSessionInfo:
    """Tmux session information with connection status."""
    name: str
    is_connected: bool  # True if session has attached clients
    num_windows: int
    created: str
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

# Check tmux session connection status
if status.tmux_sessions:
    for session in status.tmux_sessions:
        connection_status = "connected (bold)" if session.is_connected else "disconnected (dim)"
        print(f"Session: {session.name} - {connection_status}")
        print(f"  Windows: {session.num_windows}")
else:
    print("No tmux sessions")

# Display full dashboard (includes visual tmux session status)
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

## Cost Optimization & Intelligence

### Cost Dashboard

#### `azlin.costs.dashboard`

Real-time cost dashboard with Azure API integration and caching.

**Classes:**

##### `CostDashboard`

Main dashboard interface for real-time cost tracking.

```python
class CostDashboard:
    """Real-time cost dashboard with Azure API integration.

    Philosophy:
    - Performance first: < 2 seconds response time with 5-minute cache
    - Ruthless simplicity: Direct Azure API calls with local caching
    """

    def __init__(self, resource_group: str, cache_ttl: int = 300):
        """Initialize dashboard with Azure client.

        Args:
            resource_group: Azure resource group name
            cache_ttl: Cache TTL in seconds (default: 300)
        """

    def get_metrics(self, force_refresh: bool = False) -> DashboardMetrics:
        """Get current cost metrics.

        Args:
            force_refresh: Force cache refresh (default: False)

        Returns:
            DashboardMetrics with cost data

        Raises:
            CostDashboardError: If metrics fetch fails
        """

    def get_resource_breakdown(self) -> list[ResourceCostBreakdown]:
        """Get per-resource cost breakdown.

        Returns:
            List of ResourceCostBreakdown sorted by cost
        """
```

**Data Classes:**

```python
@dataclass
class DashboardMetrics:
    """Dashboard cost metrics."""
    total_cost: Decimal
    daily_cost: Decimal
    monthly_projection: Decimal
    resource_breakdown: list[ResourceCostBreakdown]
    last_updated: datetime
    previous_day_cost: Decimal | None = None

    def get_cost_trend(self) -> str:
        """Calculate cost trend (increasing/decreasing/stable)."""

    def get_cost_change_percent(self) -> Decimal:
        """Calculate percentage change from previous day."""

    def get_top_resources(self, n: int) -> list[ResourceCostBreakdown]:
        """Get top N resources by cost."""

@dataclass
class ResourceCostBreakdown:
    """Per-resource cost breakdown."""
    resource_type: str
    resource_name: str
    cost: Decimal
    percentage: Decimal

    def format(self) -> str:
        """Format for display."""

class CostDashboardCache:
    """Caching mechanism for dashboard metrics."""

    def __init__(self, ttl_seconds: int = 300):
        """Initialize cache with TTL."""

    def get(self, key: str) -> DashboardMetrics | None:
        """Retrieve metrics from cache if not expired."""

    def set(self, key: str, metrics: DashboardMetrics) -> None:
        """Store metrics in cache with timestamp."""

    def is_expired(self, key: str) -> bool:
        """Check if cache entry is expired."""

    def clear(self) -> None:
        """Clear entire cache."""
```

**Example:**

```python
from azlin.costs.dashboard import (
    CostDashboard,
    DashboardMetrics,
    CostDashboardError
)

try:
    # Create dashboard for resource group
    dashboard = CostDashboard(
        resource_group="azlin-rg",
        cache_ttl=300  # 5 minute cache
    )

    # Get current metrics
    metrics = dashboard.get_metrics()
    print(f"Total cost: ${metrics.total_cost:.2f}")
    print(f"Daily cost: ${metrics.daily_cost:.2f}")
    print(f"Monthly projection: ${metrics.monthly_projection:.2f}")
    print(f"Trend: {metrics.get_cost_trend()}")

    # Get top 5 resources by cost
    top_resources = metrics.get_top_resources(5)
    for resource in top_resources:
        print(resource.format())

    # Force refresh cache
    metrics = dashboard.get_metrics(force_refresh=True)

except CostDashboardError as e:
    print(f"Dashboard error: {e}")
```

**Exports:**
```python
__all__ = [
    "CostDashboard",
    "CostDashboardCache",
    "CostDashboardError",
    "DashboardMetrics",
    "ResourceCostBreakdown",
]
```

---

### Cost Optimizer

#### `azlin.costs.optimizer`

AI-powered cost optimization recommendations engine.

**Classes:**

##### `CostOptimizer`

Main optimization orchestrator that coordinates all detectors.

```python
class CostOptimizer:
    """Main cost optimization orchestrator.

    Coordinates multiple detectors to generate comprehensive
    optimization recommendations.
    """

    def __init__(self, resource_group: str):
        """Initialize optimizer with resource group.

        Args:
            resource_group: Azure resource group name
        """

    def get_recommendations(
        self,
        include_oversized: bool = True,
        include_idle: bool = True,
        include_scheduling: bool = True
    ) -> list[OptimizationRecommendation]:
        """Get all optimization recommendations.

        Args:
            include_oversized: Include oversized VM detection
            include_idle: Include idle resource detection
            include_scheduling: Include scheduling opportunities

        Returns:
            List of OptimizationRecommendation sorted by priority
        """

    def estimate_total_savings(
        self,
        recommendations: list[OptimizationRecommendation]
    ) -> Decimal:
        """Calculate total estimated savings from recommendations.

        Args:
            recommendations: List of recommendations

        Returns:
            Total monthly savings estimate
        """
```

##### `OversizedVMDetector`

Detector for oversized/underutilized VMs.

```python
class OversizedVMDetector:
    """Detect oversized/underutilized VMs."""

    def __init__(
        self,
        cpu_threshold: float = 30.0,
        memory_threshold: float = 30.0
    ):
        """Initialize detector with utilization thresholds.

        Args:
            cpu_threshold: CPU utilization threshold (%)
            memory_threshold: Memory utilization threshold (%)
        """

    def analyze_vm(
        self,
        vm_name: str,
        vm_metrics: dict
    ) -> OptimizationRecommendation | None:
        """Analyze VM for downsizing opportunities.

        Args:
            vm_name: VM name
            vm_metrics: Dict with cpu_avg, memory_avg, vm_size, cost_per_hour

        Returns:
            OptimizationRecommendation if downsize opportunity found, None otherwise
        """
```

##### `IdleResourceDetector`

Detector for idle/unused resources.

```python
class IdleResourceDetector:
    """Detect idle/unused resources."""

    def __init__(self, snapshot_retention_days: int = 90):
        """Initialize detector with retention policy.

        Args:
            snapshot_retention_days: Days to retain snapshots
        """

    def analyze_stopped_vm(self, vm_info: dict) -> OptimizationRecommendation | None:
        """Analyze stopped VMs for deletion opportunities."""

    def analyze_disk(self, disk_info: dict) -> OptimizationRecommendation | None:
        """Analyze disks for unattached resources."""
```

##### `SchedulingOpportunity`

Identify scheduling opportunities for cost savings.

```python
class SchedulingOpportunity:
    """Identify VM scheduling opportunities."""

    def __init__(self):
        """Initialize scheduling detector."""

    def analyze_vm_usage(
        self,
        vm_name: str,
        usage_pattern: dict
    ) -> OptimizationRecommendation | None:
        """Analyze VM usage patterns for scheduling opportunities.

        Args:
            vm_name: VM name
            usage_pattern: Dict with hourly usage data

        Returns:
            OptimizationRecommendation if scheduling opportunity found
        """
```

**Data Classes:**

```python
class RecommendationPriority(Enum):
    """Recommendation priority levels."""
    HIGH = 3
    MEDIUM = 2
    LOW = 1

@dataclass
class OptimizationRecommendation:
    """Optimization recommendation data structure."""
    resource_name: str
    resource_type: str
    action: str
    reason: str
    estimated_savings: Decimal
    priority: RecommendationPriority
    details: dict = field(default_factory=dict)
    suggested_size: str | None = None
    schedule: str | None = None

    def format(self) -> str:
        """Format recommendation for CLI display."""
```

**Example:**

```python
from azlin.costs.optimizer import (
    CostOptimizer,
    OversizedVMDetector,
    IdleResourceDetector,
    RecommendationPriority
)

# Get comprehensive optimization recommendations
optimizer = CostOptimizer(resource_group="azlin-rg")
recommendations = optimizer.get_recommendations()

# Display recommendations by priority
high_priority = [r for r in recommendations if r.priority == RecommendationPriority.HIGH]
for rec in high_priority:
    print(rec.format())

# Calculate total potential savings
total_savings = optimizer.estimate_total_savings(recommendations)
print(f"Total potential savings: ${total_savings:.2f}/month")

# Analyze specific VM for downsizing
detector = OversizedVMDetector(cpu_threshold=30.0, memory_threshold=30.0)
vm_metrics = {
    "cpu_avg": 15.0,
    "memory_avg": 20.0,
    "vm_size": "Standard_D8s_v5",
    "cost_per_hour": 0.384
}
recommendation = detector.analyze_vm("my-vm", vm_metrics)
if recommendation:
    print(f"Downsize recommendation: {recommendation.format()}")
```

**Exports:**
```python
__all__ = [
    "CostOptimizer",
    "IdleResourceDetector",
    "OptimizationRecommendation",
    "OversizedVMDetector",
    "RecommendationPriority",
    "SchedulingOpportunity",
]
```

---

### Cost History & Trends

#### `azlin.costs.history`

Historical cost tracking and trend analysis.

**Classes:**

##### `CostHistory`

Track and query historical cost data.

```python
class CostHistory:
    """Historical cost tracking with SQLite storage."""

    def __init__(self, db_path: str | None = None):
        """Initialize cost history tracker.

        Args:
            db_path: Path to SQLite database (default: ~/.azlin/cost_history.db)
        """

    def record_cost(
        self,
        resource_group: str,
        cost: Decimal,
        timestamp: datetime | None = None
    ) -> None:
        """Record cost data point.

        Args:
            resource_group: Resource group name
            cost: Cost amount
            timestamp: Timestamp (default: now)
        """

    def get_cost_range(
        self,
        resource_group: str,
        start_date: datetime,
        end_date: datetime
    ) -> list[CostHistoryEntry]:
        """Get cost history for date range.

        Args:
            resource_group: Resource group name
            start_date: Start date
            end_date: End date

        Returns:
            List of CostHistoryEntry
        """
```

##### `TrendAnalyzer`

Analyze cost trends and patterns.

```python
class TrendAnalyzer:
    """Analyze cost trends and patterns."""

    @classmethod
    def analyze_trend(
        cls,
        history: list[CostHistoryEntry]
    ) -> CostTrend:
        """Analyze cost trend from history.

        Args:
            history: List of cost history entries

        Returns:
            CostTrend with analysis results
        """

    @classmethod
    def detect_anomalies(
        cls,
        history: list[CostHistoryEntry],
        threshold: float = 2.0
    ) -> list[CostHistoryEntry]:
        """Detect cost anomalies using statistical analysis.

        Args:
            history: List of cost history entries
            threshold: Standard deviation threshold

        Returns:
            List of anomalous entries
        """
```

**Data Classes:**

```python
@dataclass
class CostHistoryEntry:
    """Historical cost data point."""
    timestamp: datetime
    cost: Decimal
    resource_group: str

class TimeRange(Enum):
    """Time range options for history queries."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

@dataclass
class CostTrend:
    """Cost trend analysis results."""
    direction: str  # "increasing", "decreasing", "stable"
    rate_of_change: Decimal
    average_cost: Decimal
    peak_cost: Decimal
    low_cost: Decimal
```

**Example:**

```python
from azlin.costs.history import (
    CostHistory,
    TrendAnalyzer,
    TimeRange
)
from datetime import datetime, timedelta

# Initialize cost history tracker
history = CostHistory()

# Record daily costs
history.record_cost("azlin-rg", Decimal("45.67"))

# Get 30-day cost history
end_date = datetime.now()
start_date = end_date - timedelta(days=30)
entries = history.get_cost_range("azlin-rg", start_date, end_date)

# Analyze trends
trend = TrendAnalyzer.analyze_trend(entries)
print(f"Cost trend: {trend.direction}")
print(f"Average cost: ${trend.average_cost:.2f}")
print(f"Rate of change: {trend.rate_of_change:.2f}%")

# Detect anomalies (costs > 2 std dev from mean)
anomalies = TrendAnalyzer.detect_anomalies(entries, threshold=2.0)
for anomaly in anomalies:
    print(f"Anomaly detected on {anomaly.timestamp}: ${anomaly.cost:.2f}")
```

**Exports:**
```python
__all__ = [
    "CostHistory",
    "CostHistoryEntry",
    "CostTrend",
    "TimeRange",
    "TrendAnalyzer",
]
```

---

### Budget Management

#### `azlin.costs.budget`

Budget tracking, alerts, and forecasting.

**Classes:**

##### `BudgetAlertManager`

Manage budget alerts and thresholds.

```python
class BudgetAlertManager:
    """Manage budget alerts and notifications."""

    def __init__(self, resource_group: str):
        """Initialize budget alert manager.

        Args:
            resource_group: Azure resource group name
        """

    def set_budget(
        self,
        amount: Decimal,
        thresholds: list[BudgetThreshold]
    ) -> None:
        """Set budget with alert thresholds.

        Args:
            amount: Monthly budget amount
            thresholds: List of alert thresholds
        """

    def check_budget(self, current_cost: Decimal) -> list[BudgetAlert]:
        """Check current cost against budget thresholds.

        Args:
            current_cost: Current monthly cost

        Returns:
            List of triggered BudgetAlert
        """

    def forecast_budget(
        self,
        current_cost: Decimal,
        days_elapsed: int
    ) -> BudgetForecast:
        """Forecast end-of-month cost.

        Args:
            current_cost: Current month-to-date cost
            days_elapsed: Days elapsed in current month

        Returns:
            BudgetForecast with projection
        """
```

**Data Classes:**

```python
@dataclass
class BudgetThreshold:
    """Budget alert threshold."""
    percentage: int  # 50, 80, 100, etc.
    action: str  # "notify", "stop_vms", "alert"

@dataclass
class BudgetAlert:
    """Budget alert notification."""
    threshold_percentage: int
    current_percentage: int
    budget_amount: Decimal
    current_cost: Decimal
    action: str

@dataclass
class BudgetForecast:
    """Budget forecast projection."""
    projected_cost: Decimal
    budget_amount: Decimal
    projected_percentage: int
    will_exceed: bool
    days_to_exceed: int | None
```

**Example:**

```python
from azlin.costs.budget import (
    BudgetAlertManager,
    BudgetThreshold,
    BudgetForecast
)

# Set up budget with thresholds
manager = BudgetAlertManager(resource_group="azlin-rg")

thresholds = [
    BudgetThreshold(percentage=50, action="notify"),
    BudgetThreshold(percentage=80, action="alert"),
    BudgetThreshold(percentage=100, action="stop_vms"),
]

manager.set_budget(amount=Decimal("1000.00"), thresholds=thresholds)

# Check current cost against budget
current_cost = Decimal("850.00")
alerts = manager.check_budget(current_cost)
for alert in alerts:
    print(f"Alert: {alert.current_percentage}% of budget ({alert.action})")

# Forecast end-of-month cost
forecast = manager.forecast_budget(current_cost=Decimal("350.00"), days_elapsed=10)
print(f"Projected cost: ${forecast.projected_cost:.2f}")
if forecast.will_exceed:
    print(f"Budget will exceed in {forecast.days_to_exceed} days")
```

**Exports:**
```python
__all__ = [
    "BudgetAlert",
    "BudgetAlertManager",
    "BudgetForecast",
    "BudgetThreshold",
]
```

---

### Cost Actions

#### `azlin.costs.actions`

Automated cost optimization actions executor.

**Classes:**

##### `ActionExecutor`

Execute cost optimization actions.

```python
class ActionExecutor:
    """Execute cost optimization actions."""

    def __init__(self, resource_group: str, dry_run: bool = False):
        """Initialize action executor.

        Args:
            resource_group: Azure resource group
            dry_run: If True, don't execute actions (default: False)
        """

    def execute_action(
        self,
        action: AutomatedAction
    ) -> ActionResult:
        """Execute a single cost optimization action.

        Args:
            action: Action to execute

        Returns:
            ActionResult with execution status
        """

    def execute_batch(
        self,
        actions: list[AutomatedAction]
    ) -> list[ActionResult]:
        """Execute multiple actions in batch.

        Args:
            actions: List of actions to execute

        Returns:
            List of ActionResult
        """
```

**Data Classes:**

```python
class ActionStatus(Enum):
    """Action execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class AutomatedAction:
    """Automated cost optimization action."""
    action_type: str  # "resize", "stop", "delete", "schedule"
    resource_name: str
    resource_type: str
    parameters: dict

@dataclass
class VMResizeAction(AutomatedAction):
    """VM resize action."""
    target_size: str

@dataclass
class VMScheduleAction(AutomatedAction):
    """VM scheduling action."""
    start_time: str  # "08:00"
    stop_time: str   # "18:00"
    days: list[str]  # ["Mon", "Tue", "Wed", "Thu", "Fri"]

@dataclass
class ResourceDeleteAction(AutomatedAction):
    """Resource deletion action."""
    confirmation_required: bool = True

@dataclass
class ActionResult:
    """Action execution result."""
    action: AutomatedAction
    status: ActionStatus
    message: str
    execution_time: float
```

**Example:**

```python
from azlin.costs.actions import (
    ActionExecutor,
    VMResizeAction,
    VMScheduleAction,
    ActionStatus
)

# Execute VM resize (dry-run mode)
executor = ActionExecutor(resource_group="azlin-rg", dry_run=True)

resize_action = VMResizeAction(
    action_type="resize",
    resource_name="my-vm",
    resource_type="VirtualMachine",
    parameters={},
    target_size="Standard_D2s_v5"
)

result = executor.execute_action(resize_action)
print(f"Action {result.status.value}: {result.message}")

# Execute VM scheduling
schedule_action = VMScheduleAction(
    action_type="schedule",
    resource_name="dev-vm",
    resource_type="VirtualMachine",
    parameters={},
    start_time="08:00",
    stop_time="18:00",
    days=["Mon", "Tue", "Wed", "Thu", "Fri"]
)

result = executor.execute_action(schedule_action)

# Execute batch actions
actions = [resize_action, schedule_action]
results = executor.execute_batch(actions)
success_count = sum(1 for r in results if r.status == ActionStatus.SUCCESS)
print(f"Executed {success_count}/{len(actions)} actions successfully")
```

**Exports:**
```python
__all__ = [
    "ActionExecutor",
    "ActionResult",
    "ActionStatus",
    "AutomatedAction",
    "ResourceDeleteAction",
    "VMResizeAction",
    "VMScheduleAction",
]
```

---

## Monitoring & Metrics

### VM Metrics Collection

#### `azlin.monitoring`

Comprehensive monitoring capabilities for Azure VMs including metrics collection, storage, and alerting.

**Classes:**

##### `MetricsCollector`

Azure Monitor API client for collecting VM metrics.

```python
class MetricsCollector:
    """Collect VM metrics from Azure Monitor API."""

    def __init__(self, subscription_id: str, resource_group: str):
        """Initialize metrics collector.

        Args:
            subscription_id: Azure subscription ID
            resource_group: Resource group name
        """

    def collect_metrics(
        self,
        vm_name: str,
        metrics: list[str] | None = None
    ) -> list[VMMetric]:
        """Collect metrics for a VM.

        Args:
            vm_name: VM name
            metrics: List of metric names to collect (default: cpu, memory, disk, network)

        Returns:
            List of VMMetric objects
        """
```

##### `MetricsStorage`

SQLite-based metrics persistence with retention policies.

```python
class MetricsStorage:
    """SQLite-based metrics storage with retention."""

    def __init__(self, db_path: Path | None = None, retention_days: int = 30):
        """Initialize metrics storage.

        Args:
            db_path: Path to SQLite database (default: ~/.azlin/metrics.db)
            retention_days: Days to retain metrics (default: 30)
        """

    def store_metric(self, metric: VMMetric) -> None:
        """Store a single metric."""

    def store_metrics(self, metrics: list[VMMetric]) -> None:
        """Store multiple metrics in batch."""

    def get_metrics(
        self,
        vm_name: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> list[VMMetric]:
        """Query metrics for time range."""

    def cleanup_old_metrics(self) -> int:
        """Remove metrics older than retention period.

        Returns:
            Number of metrics deleted
        """
```

##### `AlertEngine`

Alert evaluation and notification engine.

```python
class AlertEngine:
    """Alert evaluation and notification engine."""

    def __init__(self, rules_config: Path | None = None):
        """Initialize alert engine.

        Args:
            rules_config: Path to YAML rules configuration
        """

    def evaluate_metric(
        self,
        vm_name: str,
        metric: VMMetric
    ) -> list[Alert]:
        """Evaluate metric against all rules.

        Args:
            vm_name: VM name
            metric: Metric to evaluate

        Returns:
            List of triggered Alert objects
        """

    def send_alert(self, alert: Alert) -> None:
        """Send alert via configured notification channels.

        Args:
            alert: Alert to send
        """

    def load_rules(self) -> list[AlertRule]:
        """Load alert rules from configuration."""
```

**Data Classes:**

```python
@dataclass
class VMMetric:
    """VM metric data point."""
    vm_name: str
    metric_name: str
    value: float
    timestamp: datetime
    unit: str = ""

class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    metric: str
    threshold: float
    comparison: str  # ">", "<", ">=", "<=", "=="
    severity: AlertSeverity
    enabled: bool = True
    notification_channels: list[str] = field(default_factory=list)

@dataclass
class Alert:
    """Triggered alert data model."""
    rule_name: str
    vm_name: str
    metric: str
    actual_value: float
    threshold: float
    severity: AlertSeverity
    timestamp: datetime
    message: str
```

**Example:**

```python
from azlin.monitoring import (
    MetricsCollector,
    MetricsStorage,
    AlertEngine,
    AlertRule,
    AlertSeverity
)
from datetime import datetime, timedelta

# Collect VM metrics
collector = MetricsCollector(
    subscription_id="12345678-1234-1234-1234-123456789012",
    resource_group="azlin-rg"
)
metrics = collector.collect_metrics("my-vm")

# Store metrics
storage = MetricsStorage(retention_days=30)
storage.store_metrics(metrics)

# Query historical metrics
end_time = datetime.now()
start_time = end_time - timedelta(hours=24)
cpu_metrics = storage.get_metrics(
    vm_name="my-vm",
    metric_name="cpu_percent",
    start_time=start_time,
    end_time=end_time
)

# Set up alerts
alert_engine = AlertEngine()
for metric in metrics:
    alerts = alert_engine.evaluate_metric("my-vm", metric)
    for alert in alerts:
        print(f"{alert.severity.value}: {alert.message}")
        alert_engine.send_alert(alert)

# Cleanup old metrics
deleted_count = storage.cleanup_old_metrics()
print(f"Cleaned up {deleted_count} old metrics")
```

**Exports:**
```python
__all__ = [
    "Alert",
    "AlertEngine",
    "AlertRule",
    "AlertSeverity",
    "MetricsCollector",
    "MetricsStorage",
    "VMMetric",
]
```

---

## Network Security Management

### NSG Management & Validation

#### `azlin.network_security`

Comprehensive network security management including NSG validation, Bastion connection pooling, security scanning, and VPN management.

**Classes:**

##### `NSGValidator`

Validate NSG templates against security policies.

```python
class NSGValidator:
    """Validate NSG (Network Security Group) templates."""

    def __init__(self, policy: SecurityPolicy):
        """Initialize NSG validator.

        Args:
            policy: Security policy for validation
        """

    def validate_template(
        self,
        nsg_template: dict
    ) -> ValidationResult:
        """Validate NSG template against policy.

        Args:
            nsg_template: NSG template dictionary

        Returns:
            ValidationResult with findings
        """

    def validate_rule(
        self,
        rule: dict,
        rule_type: str
    ) -> list[PolicyFinding]:
        """Validate individual NSG rule.

        Args:
            rule: NSG rule dictionary
            rule_type: "inbound" or "outbound"

        Returns:
            List of PolicyFinding objects
        """
```

##### `SecurityPolicy`

Security policy engine for NSG rules.

```python
class SecurityPolicy:
    """Security policy engine for NSG rule validation."""

    def __init__(self, config_path: Path | None = None):
        """Initialize security policy.

        Args:
            config_path: Path to policy YAML configuration
        """

    def check_rule(
        self,
        rule: dict,
        rule_type: str
    ) -> list[PolicyFinding]:
        """Check rule against all policies.

        Args:
            rule: NSG rule to check
            rule_type: "inbound" or "outbound"

        Returns:
            List of policy violations
        """

    def is_allowed_port(self, port: int, protocol: str) -> bool:
        """Check if port/protocol combination is allowed."""

    def is_allowed_source(self, source: str) -> bool:
        """Check if source address is allowed."""
```

##### `BastionConnectionPool`

Manage reusable Bastion tunnels for improved performance.

```python
class BastionConnectionPool:
    """Connection pool for reusable Bastion SSH tunnels."""

    def __init__(
        self,
        max_tunnels: int = 10,
        tunnel_ttl: int = 3600,
        cleanup_interval: int = 300
    ):
        """Initialize connection pool.

        Args:
            max_tunnels: Maximum concurrent tunnels (default: 10)
            tunnel_ttl: Tunnel TTL in seconds (default: 3600)
            cleanup_interval: Cleanup check interval in seconds (default: 300)
        """

    def get_tunnel(
        self,
        vm_name: str,
        bastion_name: str,
        resource_group: str
    ) -> PooledTunnel:
        """Get existing tunnel or create new one.

        Args:
            vm_name: Target VM name
            bastion_name: Bastion host name
            resource_group: Resource group name

        Returns:
            PooledTunnel ready for use
        """

    def release_tunnel(self, tunnel_id: str) -> None:
        """Release tunnel back to pool."""

    def close_all_tunnels(self) -> None:
        """Close all tunnels and cleanup."""
```

##### `SecurityScanner`

Vulnerability scanning integration with Azure Security Center.

```python
class SecurityScanner:
    """Vulnerability scanning via Azure Security Center."""

    def __init__(self, subscription_id: str, resource_group: str):
        """Initialize security scanner.

        Args:
            subscription_id: Azure subscription ID
            resource_group: Resource group name
        """

    def scan_vm(
        self,
        vm_name: str
    ) -> list[SecurityFinding]:
        """Scan VM for vulnerabilities.

        Args:
            vm_name: VM to scan

        Returns:
            List of SecurityFinding objects
        """

    def scan_all_vms(self) -> dict[str, list[SecurityFinding]]:
        """Scan all VMs in resource group.

        Returns:
            Dict mapping VM names to findings
        """
```

##### `VPNManager`

VPN gateway configuration and management.

```python
class VPNManager:
    """VPN gateway configuration manager."""

    def __init__(self, resource_group: str):
        """Initialize VPN manager.

        Args:
            resource_group: Resource group name
        """

    def create_vpn_gateway(
        self,
        name: str,
        vnet_name: str,
        sku: str = "VpnGw1"
    ) -> str:
        """Create VPN gateway.

        Args:
            name: Gateway name
            vnet_name: Virtual network name
            sku: Gateway SKU (default: VpnGw1)

        Returns:
            Gateway ID

        Raises:
            VPNManagerError: If creation fails
        """

    def configure_site_to_site(
        self,
        gateway_name: str,
        remote_address: str,
        shared_key: str
    ) -> None:
        """Configure site-to-site VPN connection."""
```

##### `PrivateEndpointManager`

Private endpoint management for secure service access.

```python
class PrivateEndpointManager:
    """Manage private endpoints for Azure services."""

    def __init__(self, resource_group: str):
        """Initialize private endpoint manager.

        Args:
            resource_group: Resource group name
        """

    def create_private_endpoint(
        self,
        name: str,
        service_id: str,
        subnet_id: str
    ) -> str:
        """Create private endpoint.

        Args:
            name: Endpoint name
            service_id: Azure service resource ID
            subnet_id: Subnet resource ID

        Returns:
            Private endpoint ID

        Raises:
            PrivateEndpointManagerError: If creation fails
        """

    def list_private_endpoints(self) -> list[dict]:
        """List all private endpoints in resource group."""
```

**Data Classes:**

```python
class RuleSeverity(Enum):
    """NSG rule validation severity."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class PolicyFinding:
    """Security policy finding."""
    rule_name: str
    severity: RuleSeverity
    message: str
    recommendation: str

@dataclass
class ValidationResult:
    """NSG validation result."""
    valid: bool
    findings: list[PolicyFinding]
    score: int  # 0-100

@dataclass
class PooledTunnel:
    """Pooled Bastion tunnel."""
    tunnel_id: str
    vm_name: str
    local_port: int
    created_at: datetime
    last_used: datetime

class ScanSeverity(Enum):
    """Security finding severity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityFinding:
    """Security vulnerability finding."""
    vm_name: str
    finding_type: str
    severity: ScanSeverity
    title: str
    description: str
    remediation: str
    cve_ids: list[str] = field(default_factory=list)
```

**Example:**

```python
from azlin.network_security import (
    NSGValidator,
    SecurityPolicy,
    BastionConnectionPool,
    SecurityScanner,
    VPNManager
)

# Validate NSG template
policy = SecurityPolicy()
validator = NSGValidator(policy)

nsg_template = {
    "security_rules": [
        {
            "name": "allow-ssh",
            "direction": "Inbound",
            "priority": 100,
            "protocol": "Tcp",
            "source_port_range": "*",
            "destination_port_range": "22",
            "source_address_prefix": "0.0.0.0/0",  # Too permissive!
            "destination_address_prefix": "*",
            "access": "Allow"
        }
    ]
}

result = validator.validate_template(nsg_template)
if not result.valid:
    for finding in result.findings:
        print(f"{finding.severity.value}: {finding.message}")
        print(f"Recommendation: {finding.recommendation}")

# Use Bastion connection pool
pool = BastionConnectionPool(max_tunnels=10)
tunnel = pool.get_tunnel(
    vm_name="my-vm",
    bastion_name="my-bastion",
    resource_group="azlin-rg"
)
print(f"Connected via localhost:{tunnel.local_port}")
# ... use tunnel ...
pool.release_tunnel(tunnel.tunnel_id)

# Scan VM for vulnerabilities
scanner = SecurityScanner(
    subscription_id="12345678-1234-1234-1234-123456789012",
    resource_group="azlin-rg"
)
findings = scanner.scan_vm("my-vm")
critical = [f for f in findings if f.severity == ScanSeverity.CRITICAL]
for finding in critical:
    print(f"CRITICAL: {finding.title}")
    print(f"CVEs: {', '.join(finding.cve_ids)}")
    print(f"Remediation: {finding.remediation}")

# Create VPN gateway
vpn_mgr = VPNManager(resource_group="azlin-rg")
gateway_id = vpn_mgr.create_vpn_gateway(
    name="my-vpn-gateway",
    vnet_name="my-vnet",
    sku="VpnGw1"
)
print(f"Created VPN gateway: {gateway_id}")
```

**Exports:**
```python
__all__ = [
    "AuditEvent",
    "AuditEventType",
    "BastionCleanupDaemon",
    "BastionConnectionPool",
    "NSGManager",
    "NSGValidator",
    "PolicyFinding",
    "PooledTunnel",
    "PrivateEndpointManager",
    "PrivateEndpointManagerError",
    "RuleSeverity",
    "ScanSeverity",
    "SecurityAuditLogger",
    "SecurityFinding",
    "SecurityPolicy",
    "SecurityScanner",
    "SecurityScannerError",
    "VPNManager",
    "VPNManagerError",
    "ValidationResult",
]
```

---

## Multi-Tenant Context Management

### Context Management

#### `azlin.context_manager`

kubectl-style context management for seamless switching between multiple Azure tenants and subscriptions.

**Classes:**

##### `ContextManager`

Manage Azure subscription and tenant contexts.

```python
class ContextManager:
    """Manage Azure subscription/tenant contexts."""

    def __init__(self, config_path: Path | None = None):
        """Initialize context manager.

        Args:
            config_path: Path to contexts configuration (default: ~/.azlin/contexts.toml)
        """

    def create_context(
        self,
        name: str,
        subscription_id: str,
        tenant_id: str,
        description: str = ""
    ) -> None:
        """Create new context.

        Args:
            name: Context name
            subscription_id: Azure subscription ID
            tenant_id: Azure tenant ID
            description: Optional description
        """

    def use_context(self, name: str) -> None:
        """Switch to specified context.

        Args:
            name: Context name to activate
        """

    def get_current_context(self) -> dict | None:
        """Get current active context.

        Returns:
            Context dict or None if no context active
        """

    def list_contexts(self) -> list[dict]:
        """List all configured contexts.

        Returns:
            List of context dictionaries
        """

    def delete_context(self, name: str) -> None:
        """Delete context.

        Args:
            name: Context name to delete
        """

    def rename_context(self, old_name: str, new_name: str) -> None:
        """Rename context.

        Args:
            old_name: Current context name
            new_name: New context name
        """
```

**Example:**

```python
from azlin.context_manager import ContextManager

# Initialize context manager
ctx_mgr = ContextManager()

# Create contexts for different environments
ctx_mgr.create_context(
    name="dev",
    subscription_id="11111111-1111-1111-1111-111111111111",
    tenant_id="22222222-2222-2222-2222-222222222222",
    description="Development environment"
)

ctx_mgr.create_context(
    name="prod",
    subscription_id="33333333-3333-3333-3333-333333333333",
    tenant_id="44444444-4444-4444-4444-444444444444",
    description="Production environment"
)

# Switch between contexts
ctx_mgr.use_context("dev")
print(f"Switched to dev context")

# List all contexts
contexts = ctx_mgr.list_contexts()
for ctx in contexts:
    current = " (current)" if ctx.get("current") else ""
    print(f"{ctx['name']}: {ctx['description']}{current}")

# Get current context
current = ctx_mgr.get_current_context()
print(f"Current subscription: {current['subscription_id']}")

# Switch to production
ctx_mgr.use_context("prod")
```

**Exports:**
```python
__all__ = ["ContextManager", "ContextError"]
```

---

### Fleet Orchestration

#### `azlin.fleet_orchestrator`

Orchestrate operations across multiple VMs in parallel.

**Classes:**

##### `FleetOrchestrator`

Coordinate operations across VM fleets.

```python
class FleetOrchestrator:
    """Orchestrate operations across multiple VMs."""

    def __init__(
        self,
        resource_group: str,
        max_parallel: int = 10,
        timeout: int = 300
    ):
        """Initialize fleet orchestrator.

        Args:
            resource_group: Azure resource group
            max_parallel: Maximum parallel operations (default: 10)
            timeout: Operation timeout in seconds (default: 300)
        """

    def execute_on_fleet(
        self,
        command: str,
        vm_filter: dict | None = None
    ) -> dict[str, dict]:
        """Execute command on multiple VMs in parallel.

        Args:
            command: Command to execute
            vm_filter: Optional filter (e.g., {"tag": "env=dev"})

        Returns:
            Dict mapping VM names to execution results
        """

    def batch_start(
        self,
        vm_pattern: str | None = None,
        tag_filter: dict | None = None
    ) -> dict[str, bool]:
        """Start multiple VMs in parallel.

        Args:
            vm_pattern: VM name pattern (e.g., "test-*")
            tag_filter: Tag filter (e.g., {"env": "staging"})

        Returns:
            Dict mapping VM names to success status
        """

    def batch_stop(
        self,
        vm_pattern: str | None = None,
        tag_filter: dict | None = None,
        deallocate: bool = True
    ) -> dict[str, bool]:
        """Stop multiple VMs in parallel.

        Args:
            vm_pattern: VM name pattern
            tag_filter: Tag filter
            deallocate: Deallocate VMs (default: True)

        Returns:
            Dict mapping VM names to success status
        """

    def sync_files_to_fleet(
        self,
        source_path: str,
        dest_path: str,
        vm_filter: dict | None = None
    ) -> dict[str, bool]:
        """Sync files to multiple VMs.

        Args:
            source_path: Local source path
            dest_path: Remote destination path
            vm_filter: Optional VM filter

        Returns:
            Dict mapping VM names to success status
        """
```

**Example:**

```python
from azlin.fleet_orchestrator import FleetOrchestrator

# Initialize orchestrator
orchestrator = FleetOrchestrator(
    resource_group="azlin-rg",
    max_parallel=10,
    timeout=300
)

# Execute command on all dev VMs
results = orchestrator.execute_on_fleet(
    command="git pull origin main",
    vm_filter={"tag": "env=dev"}
)

for vm_name, result in results.items():
    if result["success"]:
        print(f"{vm_name}: {result['stdout']}")
    else:
        print(f"{vm_name}: ERROR - {result['stderr']}")

# Start all test VMs
start_results = orchestrator.batch_start(vm_pattern="test-*")
success_count = sum(1 for success in start_results.values() if success)
print(f"Started {success_count}/{len(start_results)} VMs")

# Stop all staging VMs to save costs
stop_results = orchestrator.batch_stop(tag_filter={"env": "staging"})

# Sync configuration to all production VMs
sync_results = orchestrator.sync_files_to_fleet(
    source_path="~/.azlin/home/",
    dest_path="~/",
    vm_filter={"tag": "env=production"}
)
```

**Exports:**
```python
__all__ = ["FleetOrchestrator", "FleetOperationError"]
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
- **Cost Optimization & Intelligence**: Dashboard, Optimizer, History & Trends, Budget Management, Automated Actions
- **Monitoring & Metrics**: Metrics Collection, Storage with Retention, Alert Engine
- **Network Security**: NSG Validation, Bastion Connection Pooling, Security Scanning, VPN Management, Private Endpoints
- **Multi-Tenant Management**: Context Switching, Fleet Orchestration
- **Remote Execution**: Commands, Batch Operations
- **Advanced**: Templates, Key Rotation, Monitoring, Terminal Launch
- **Utilities**: Prerequisites, Progress, Notifications, Tags, Environment

### New in This Version

This API reference now includes comprehensive documentation for:

- **Cost Optimization Intelligence** (5 modules): AI-powered recommendations, real-time dashboards, historical trends, budget alerts, and automated actions
- **Monitoring & Alerting** (3 modules): Azure Monitor integration, SQLite-based metrics storage, and configurable alert rules
- **Network Security** (7 modules): NSG policy validation, Bastion connection pooling, vulnerability scanning, VPN management, and private endpoints
- **Multi-Tenant Operations** (2 modules): kubectl-style context management and parallel fleet orchestration

For usage examples and more details, see:
- [README.md](../README.md) - User guide and CLI documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture and design
- [testing/test_strategy.md](testing/test_strategy.md) - Testing approach and coverage

---

**Philosophy**: All APIs follow azlin's core principles of ruthless simplicity, security by design, and fail-fast error handling. Each module is a self-contained "brick" with clear inputs, outputs, and error conditions.
