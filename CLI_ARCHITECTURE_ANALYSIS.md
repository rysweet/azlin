# CLI Architecture Analysis: VM Creation & Storage Configuration

**Analysis Date**: 2026-01-11
**Target**: `src/azlin/cli.py` (354KB)
**Focus**: VM provisioning command structure and storage integration points

---

## Executive Summary

The azlin CLI uses a multi-layer architecture for VM provisioning:
1. **CLI Layer** (`cli.py`): Click-based command parsing and orchestration
2. **Orchestrator Layer** (`CLIOrchestrator`): Workflow coordination
3. **Provisioner Layer** (`vm_provisioning.py`): Azure VM creation via Azure CLI

**Current Storage Options**: `--nfs-storage` (NFS mount for home directory)
**No Existing Options For**: OS disk size, data disk configuration, or separate home disk

---

## 1. CLI Command Structure

### Entry Point: `azlin new`

**Location**: `cli.py:2759` (`new_command()` function)

**Command Definition**:
```python
@main.command(name="new")
@click.option("--repo", help="GitHub repository URL to clone", type=str)
@click.option("--size", help="VM size tier (s, m, l, xl)", type=str)
@click.option("--vm-size", help="Explicit Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--resource-group", help="Resource group name", type=str)
@click.option("--name", help="Custom session name", type=str)
@click.option("--pool", help="Number of VMs to provision in parallel", type=int)
@click.option("--no-auto-connect", help="Do not auto-connect via SSH", is_flag=True)
@click.option("--config", help="Config file path", type=click.Path())
@click.option("--template", help="Template name for VM configuration", type=str)
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
@click.option("--no-nfs", is_flag=True, help="Skip NFS storage mounting")
@click.option("--no-bastion", help="Skip bastion auto-detection", is_flag=True)
@click.option("--bastion-name", help="Explicit bastion host name", type=str)
@click.option("--yes", "-y", is_flag=True, help="Accept all defaults (non-interactive)")
def new_command(ctx, repo, size, vm_size, region, resource_group, name, pool,
                no_auto_connect, config, template, nfs_storage, no_nfs,
                no_bastion, bastion_name, yes):
    """Provision a new Azure VM with development tools."""
```

**Key Functions**:
- `_load_config_and_template()` - Load configuration and template settings
- `_resolve_vm_settings()` - Resolve final resource group, region, and VM size
- `generate_vm_name()` - Generate unique VM name
- `_validate_inputs()` - Validate pool and repo inputs

---

## 2. Parameter Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI LAYER (cli.py)                       │
│                                                             │
│  azlin new --size xl --nfs-storage shared --name dev-vm   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              CLIOrchestrator (cli.py:173)                   │
│                                                             │
│  __init__(repo, vm_size, region, resource_group,          │
│           nfs_storage, no_nfs, session_name, ...)         │
│                                                             │
│  - self.provisioner = VMProvisioner()                      │
│  - Coordinates: auth, provisioning, SSH, GitHub           │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           _provision_vm() (cli.py:819)                      │
│                                                             │
│  1. Check bastion availability                             │
│  2. Create VMConfig via provisioner.create_vm_config()     │
│  3. Call provisioner.provision_vm(config, callback)        │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│    VMProvisioner.provision_vm() (vm_provisioning.py:894)   │
│                                                             │
│  1. Create resource group                                  │
│  2. Generate cloud-init script                             │
│  3. Build Azure CLI command: az vm create [OPTIONS]        │
│  4. Execute via AzureCLIExecutor                          │
│  5. Return VMDetails                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Existing Storage-Related Options

### 3.1 NFS Storage Option

**CLI Flag**: `--nfs-storage <storage-account-name>`
**Alternative**: `--no-nfs` (disable NFS mounting)

**Flow**:
1. **CLI**: `nfs_storage` parameter passed to `CLIOrchestrator.__init__()`
2. **Orchestrator**: Stores as `self.nfs_storage`
3. **Resolution**: `_resolve_nfs_storage()` method (cli.py:1473)
   - Priority 1: Explicit `--nfs-storage` option
   - Priority 2: Config file `default_nfs_storage`
   - Priority 3: Auto-detect if only one storage exists
4. **Usage**: Mount NFS share as `/home` after VM provisioning

**Current Implementation** (cli.py:1406-1545):
```python
def _resolve_nfs_storage(self, resource_group: str) -> StorageInfo | None:
    """Resolve which NFS storage to use.

    Priority:
    1. Explicit --nfs-storage option
    2. Config file default_nfs_storage
    3. Auto-detect if only one storage exists
    4. None if no storage or multiple without explicit choice
    """
    # ... implementation details
```

### 3.2 No Existing Disk Options

**Currently Missing**:
- ❌ `--os-disk-size` - OS disk size configuration
- ❌ `--data-disk-size` - Data disk size configuration
- ❌ `--home-disk-size` - Separate home directory disk
- ❌ `--no-home-disk` - Disable separate home disk
- ❌ `--storage-sku` - Disk SKU (Premium SSD, Standard SSD, etc.)

---

## 4. VMConfig Data Structure

**Location**: `vm_provisioning.py:40-53`

**Current Fields**:
```python
@dataclass
class VMConfig:
    """VM configuration parameters."""

    name: str
    resource_group: str
    location: str = "westus2"
    size: str = "Standard_E16as_v5"
    image: str = "Ubuntu2204"
    ssh_public_key: str | None = None
    admin_username: str = "azureuser"
    disable_password_auth: bool = True
    session_name: str | None = None
    public_ip_enabled: bool = True  # Bastion support
```

**Missing Fields for Disk Configuration**:
- `os_disk_size_gb: int | None = None`
- `home_disk_size_gb: int | None = None`
- `home_disk_enabled: bool = True`
- `storage_sku: str = "Premium_LRS"`

---

## 5. Azure CLI Command Construction

**Location**: `vm_provisioning.py:564-607`

**Current Command**:
```python
cmd = [
    "az", "vm", "create",
    "--name", config.name,
    "--resource-group", config.resource_group,
    "--location", config.location,
    "--size", config.size,
    "--image", config.image,
    "--admin-username", config.admin_username,
    "--authentication-type", "ssh",
    "--ssh-key-values", config.ssh_public_key,
    "--custom-data", cloud_init,
    "--public-ip-sku", "Standard",  # or "" for no public IP
    "--subnet", "default",
    "--vnet-name", f"azlin-bastion-{config.location}-vnet",
    "--output", "json"
]
```

**Missing Disk Options**:
```python
# Need to add:
"--os-disk-size-gb", str(config.os_disk_size_gb),
"--data-disk-sizes-gb", str(config.home_disk_size_gb),
"--storage-sku", config.storage_sku
```

---

## 6. Integration Points for New Flags

### 6.1 CLI Layer Changes

**File**: `src/azlin/cli.py`
**Function**: `new_command()` (line 2759)

**Add CLI Options**:
```python
@click.option(
    "--home-disk-size",
    type=int,
    default=100,
    help="Size of separate home directory disk in GB (default: 100GB)"
)
@click.option(
    "--no-home-disk",
    is_flag=True,
    help="Disable separate home disk (use OS disk only)"
)
@click.option(
    "--os-disk-size",
    type=int,
    default=30,
    help="OS disk size in GB (default: 30GB)"
)
```

**Update Function Signature**:
```python
def new_command(
    ctx, repo, size, vm_size, region, resource_group, name, pool,
    no_auto_connect, config, template, nfs_storage, no_nfs,
    no_bastion, bastion_name, yes,
    home_disk_size: int,  # NEW
    no_home_disk: bool,   # NEW
    os_disk_size: int     # NEW
):
```

**Pass to Orchestrator**:
```python
orchestrator = CLIOrchestrator(
    repo=repo,
    vm_size=final_vm_size,
    region=final_region,
    resource_group=final_rg,
    auto_connect=not no_auto_connect,
    config_file=config,
    nfs_storage=nfs_storage,
    no_nfs=no_nfs,
    session_name=name,
    no_bastion=no_bastion,
    bastion_name=bastion_name,
    auto_approve=yes,
    home_disk_size=home_disk_size,      # NEW
    home_disk_enabled=not no_home_disk, # NEW
    os_disk_size=os_disk_size           # NEW
)
```

### 6.2 Orchestrator Layer Changes

**File**: `src/azlin/cli.py`
**Class**: `CLIOrchestrator.__init__()` (line 188)

**Add Constructor Parameters**:
```python
def __init__(
    self,
    repo: str | None = None,
    vm_size: str = "Standard_D2s_v3",
    region: str = "eastus",
    resource_group: str | None = None,
    auto_connect: bool = True,
    config_file: str | None = None,
    nfs_storage: str | None = None,
    no_nfs: bool = False,
    session_name: str | None = None,
    no_bastion: bool = False,
    bastion_name: str | None = None,
    auto_approve: bool = False,
    home_disk_size: int = 100,          # NEW
    home_disk_enabled: bool = True,     # NEW
    os_disk_size: int = 30              # NEW
):
    # ... existing initialization
    self.home_disk_size = home_disk_size
    self.home_disk_enabled = home_disk_enabled
    self.os_disk_size = os_disk_size
```

**Update `_provision_vm()` Call** (line 845):
```python
config = self.provisioner.create_vm_config(
    name=vm_name,
    resource_group=rg_name,
    location=self.region,
    size=self.vm_size,
    ssh_public_key=public_key,
    session_name=self.session_name,
    public_ip_enabled=public_ip_enabled,
    home_disk_size_gb=self.home_disk_size if self.home_disk_enabled else None,  # NEW
    os_disk_size_gb=self.os_disk_size  # NEW
)
```

### 6.3 Provisioner Layer Changes

**File**: `src/azlin/vm_provisioning.py`

**Update VMConfig** (line 40):
```python
@dataclass
class VMConfig:
    """VM configuration parameters."""

    name: str
    resource_group: str
    location: str = "westus2"
    size: str = "Standard_E16as_v5"
    image: str = "Ubuntu2204"
    ssh_public_key: str | None = None
    admin_username: str = "azureuser"
    disable_password_auth: bool = True
    session_name: str | None = None
    public_ip_enabled: bool = True
    os_disk_size_gb: int = 30           # NEW
    home_disk_size_gb: int | None = None  # NEW (None = no separate home disk)
    storage_sku: str = "Premium_LRS"   # NEW
```

**Update `create_vm_config()`** (line 366):
```python
def create_vm_config(
    self,
    name: str,
    resource_group: str,
    location: str = "westus2",
    size: str = "Standard_E16as_v5",
    ssh_public_key: str | None = None,
    session_name: str | None = None,
    public_ip_enabled: bool = True,
    os_disk_size_gb: int = 30,              # NEW
    home_disk_size_gb: int | None = None    # NEW
) -> VMConfig:
    """Create VM configuration with validation."""
    # ... validation logic
    return VMConfig(
        name=name,
        resource_group=resource_group,
        location=location,
        size=size,
        image="Ubuntu2204",
        ssh_public_key=ssh_public_key,
        admin_username="azureuser",
        disable_password_auth=True,
        session_name=session_name,
        public_ip_enabled=public_ip_enabled,
        os_disk_size_gb=os_disk_size_gb,        # NEW
        home_disk_size_gb=home_disk_size_gb,    # NEW
        storage_sku="Premium_LRS"               # NEW
    )
```

**Update Azure CLI Command** (line 564):
```python
cmd = [
    "az", "vm", "create",
    "--name", config.name,
    "--resource-group", config.resource_group,
    "--location", config.location,
    "--size", config.size,
    "--image", config.image,
    "--admin-username", config.admin_username,
    "--authentication-type", "ssh",
    "--ssh-key-values", config.ssh_public_key,
    "--custom-data", cloud_init,
    "--os-disk-size-gb", str(config.os_disk_size_gb),  # NEW
    "--storage-sku", config.storage_sku,               # NEW
]

# Add data disk for home directory if configured
if config.home_disk_size_gb:
    cmd.extend([
        "--data-disk-sizes-gb", str(config.home_disk_size_gb)
    ])

# Add public IP or bastion configuration
if config.public_ip_enabled:
    cmd.extend(["--public-ip-sku", "Standard"])
else:
    cmd.extend(["--public-ip-address", ""])
    vnet_name = f"azlin-bastion-{config.location}-vnet"
    cmd.extend(["--subnet", "default", "--vnet-name", vnet_name])

cmd.extend(["--output", "json"])
```

---

## 7. Code Snippets: Key Integration Points

### Snippet 1: CLI Option Definitions
**Location**: `cli.py:2740-2776`

```python
# EXISTING NFS STORAGE OPTION
@click.option("--nfs-storage", help="NFS storage account name to mount as home directory", type=str)
@click.option("--no-nfs", is_flag=True, help="Skip NFS storage mounting (use local home directory only)")

# ADD NEW DISK OPTIONS HERE:
@click.option("--home-disk-size", type=int, default=100, help="Size of separate home directory disk in GB (default: 100GB)")
@click.option("--no-home-disk", is_flag=True, help="Disable separate home disk (use OS disk only)")
@click.option("--os-disk-size", type=int, default=30, help="OS disk size in GB (default: 30GB)")
```

### Snippet 2: Orchestrator Initialization
**Location**: `cli.py:2837-2850`

```python
# CREATE ORCHESTRATOR WITH NEW PARAMETERS
orchestrator = CLIOrchestrator(
    repo=repo,
    vm_size=final_vm_size,
    region=final_region,
    resource_group=final_rg,
    auto_connect=not no_auto_connect,
    config_file=config,
    nfs_storage=nfs_storage,
    no_nfs=no_nfs,
    session_name=name,
    no_bastion=no_bastion,
    bastion_name=bastion_name,
    auto_approve=yes,
    # ADD THESE:
    home_disk_size=home_disk_size,
    home_disk_enabled=not no_home_disk,
    os_disk_size=os_disk_size
)
```

### Snippet 3: VM Config Creation
**Location**: `cli.py:845-853`

```python
# CREATE VM CONFIG WITH DISK PARAMETERS
config = self.provisioner.create_vm_config(
    name=vm_name,
    resource_group=rg_name,
    location=self.region,
    size=self.vm_size,
    ssh_public_key=public_key,
    session_name=self.session_name,
    public_ip_enabled=public_ip_enabled,
    # ADD THESE:
    os_disk_size_gb=self.os_disk_size,
    home_disk_size_gb=self.home_disk_size if self.home_disk_enabled else None
)
```

### Snippet 4: Azure CLI Command Construction
**Location**: `vm_provisioning.py:564-607`

```python
# BUILD VM CREATE COMMAND WITH DISK OPTIONS
cmd = [
    "az", "vm", "create",
    "--name", config.name,
    "--resource-group", config.resource_group,
    "--location", config.location,
    "--size", config.size,
    "--image", config.image,
    "--admin-username", config.admin_username,
    "--authentication-type", "ssh",
    "--ssh-key-values", config.ssh_public_key,
    "--custom-data", cloud_init,
    # ADD THESE DISK OPTIONS:
    "--os-disk-size-gb", str(config.os_disk_size_gb),
    "--storage-sku", config.storage_sku,
]

# ADD DATA DISK FOR SEPARATE HOME DIRECTORY
if config.home_disk_size_gb:
    cmd.extend(["--data-disk-sizes-gb", str(config.home_disk_size_gb)])

# ... rest of command configuration
```

---

## 8. Recommendations

### Priority 1: Add CLI Flags
1. Add `--home-disk-size`, `--no-home-disk`, `--os-disk-size` to `new_command()`
2. Update function signature and parameter passing

### Priority 2: Extend VMConfig
1. Add disk-related fields to `VMConfig` dataclass
2. Update `create_vm_config()` to accept and validate disk parameters
3. Add validation for disk sizes (min/max ranges)

### Priority 3: Update Azure CLI Command
1. Add `--os-disk-size-gb`, `--storage-sku` to base command
2. Conditionally add `--data-disk-sizes-gb` when home disk enabled
3. Handle edge cases (bastion VMs, pool provisioning)

### Priority 4: Post-Provisioning Logic
1. Add disk attachment verification
2. Add filesystem creation and mounting for home disk
3. Update cloud-init to handle separate home disk
4. Test with both NFS and local home disk scenarios

### Priority 5: Template Support
1. Add disk configuration to template schema
2. Update `TemplateManager` to support disk options
3. Document template examples

---

## 9. Example Usage (Proposed)

```bash
# Provision VM with custom disk sizes
azlin new --os-disk-size 50 --home-disk-size 200

# Provision VM with no separate home disk (use OS disk only)
azlin new --no-home-disk --os-disk-size 100

# Provision VM with NFS storage (no local home disk needed)
azlin new --nfs-storage team-shared --no-home-disk

# Provision VM with both NFS and local home disk
azlin new --nfs-storage team-shared --home-disk-size 100

# Template with disk configuration
azlin new --template large-dev-vm
# (template specifies os_disk_size: 100, home_disk_size: 500)
```

---

## 10. Testing Checklist

- [ ] CLI flags parse correctly
- [ ] VMConfig validates disk sizes (30-4095 GB for OS, 4-32767 GB for data)
- [ ] Azure CLI command includes correct disk options
- [ ] VM provisions successfully with custom disk sizes
- [ ] Data disk attaches and mounts correctly
- [ ] Home directory uses separate disk (when enabled)
- [ ] NFS storage works with `--no-home-disk`
- [ ] Template support works for disk configuration
- [ ] Pool provisioning handles disk options
- [ ] Error handling for invalid disk sizes

---

## Appendix: File Structure

```
src/azlin/
├── cli.py                      # CLI entry point (354KB)
│   ├── new_command()          # Line 2759 - VM provisioning command
│   ├── CLIOrchestrator        # Line 173 - Workflow orchestration
│   │   ├── __init__()         # Line 188 - Initialize with parameters
│   │   └── _provision_vm()    # Line 819 - Provision VM via provisioner
│   └── _resolve_nfs_storage() # Line 1473 - NFS storage resolution
│
├── vm_provisioning.py          # VM provisioner (1122 lines)
│   ├── VMConfig               # Line 40 - VM configuration dataclass
│   ├── VMProvisioner          # Line 218 - Provisioner class
│   │   ├── create_vm_config() # Line 366 - Create validated config
│   │   └── provision_vm()     # Line 894 - Provision VM via Azure CLI
│   └── _generate_cloud_init() # Line 711 - Cloud-init script generation
│
└── modules/
    ├── bastion_provisioner.py  # Bastion host provisioning
    ├── nfs_provisioner.py      # NFS storage provisioning
    └── github_runner_provisioner.py  # GitHub runner provisioning
```

---

**Analysis Complete**: All integration points identified for adding `--home-disk-size` and `--no-home-disk` flags.
