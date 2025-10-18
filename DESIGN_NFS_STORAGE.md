# Azure Files NFS Storage - Architecture Design

**Epic**: Phase 1.1 - Core Storage Management  
**Issue**: #66  
**Date**: October 18, 2025  
**Status**: Step 4 - Design (Following DEFAULT_WORKFLOW)

---

## Architecture Overview

### Design Principles (from azlin philosophy)
1. **Ruthless Simplicity**: Single-purpose modules with clear contracts
2. **Brick Architecture**: Independently regenerable components
3. **Zero Credentials in Code**: Delegate to Azure CLI
4. **Fail Fast**: Validate prerequisites before operations
5. **Standard Library Preference**: Minimize external dependencies

### Module Structure (Brick Pattern)

```
src/azlin/
├── storage_manager.py          # NEW: Core storage operations (Brick #28)
├── nfs_mount_manager.py        # NEW: NFS mount/unmount (Brick #29)
├── cli.py                      # MODIFY: Add storage command group
├── config_manager.py           # MODIFY: Store storage configurations
├── cost_tracker.py             # MODIFY: Include storage costs
└── vm_provisioning.py          # MODIFY: Add NFS mount to cloud-init
```

---

## Component Design

### Brick #28: `storage_manager.py`

**Purpose**: Manage Azure Files NFS storage accounts

**Public API**:
```python
class StorageManager:
    """Azure Files NFS storage account management.
    
    Philosophy:
    - Uses Azure CLI (az storage account) for operations
    - No credentials in code
    - Validates all inputs before Azure calls
    - Returns structured data (dataclasses)
    """
    
    @classmethod
    def create_storage(
        cls,
        name: str,
        resource_group: str,
        region: str,
        tier: str = "Premium",
        size_gb: int = 100,
    ) -> StorageInfo:
        """Create Azure Files NFS storage account.
        
        Steps:
        1. Validate inputs (name, tier, size)
        2. Check if storage account exists (idempotent)
        3. Get or create VNet and subnet
        4. Create storage account with NFS enabled
        5. Create file share with quota
        6. Configure private endpoint
        7. Return StorageInfo
        
        Raises:
            StorageError: If creation fails
            ValidationError: If inputs invalid
        """
        
    @classmethod
    def list_storage(
        cls,
        resource_group: str,
    ) -> list[StorageInfo]:
        """List all azlin storage accounts in resource group."""
        
    @classmethod
    def get_storage(
        cls,
        name: str,
        resource_group: str,
    ) -> StorageInfo:
        """Get storage account details.
        
        Raises:
            StorageNotFoundError: If storage doesn't exist
        """
        
    @classmethod
    def delete_storage(
        cls,
        name: str,
        resource_group: str,
        force: bool = False,
    ) -> None:
        """Delete storage account.
        
        Args:
            force: Skip connected VMs check
            
        Raises:
            StorageInUseError: If VMs still connected and not force
        """
        
    @classmethod
    def get_storage_status(
        cls,
        name: str,
        resource_group: str,
    ) -> StorageStatus:
        """Get detailed storage status including usage and connected VMs."""
```

**Data Models**:
```python
@dataclass
class StorageInfo:
    """Storage account information."""
    name: str
    resource_group: str
    region: str
    tier: str  # "Premium" or "Standard"
    size_gb: int
    nfs_endpoint: str  # e.g., "name.file.core.windows.net:/sharename"
    created: datetime
    
@dataclass
class StorageStatus:
    """Detailed storage status."""
    info: StorageInfo
    used_gb: float
    utilization_percent: float
    connected_vms: list[str]  # VM names
    cost_per_month: float
```

**Error Hierarchy**:
```python
class StorageError(Exception):
    """Base storage error."""
    
class StorageNotFoundError(StorageError):
    """Storage account not found."""
    
class StorageInUseError(StorageError):
    """Storage still has connected VMs."""
    
class ValidationError(StorageError):
    """Invalid input parameters."""
```

---

### Brick #29: `nfs_mount_manager.py`

**Purpose**: Handle NFS mount/unmount operations on VMs

**Public API**:
```python
class NFSMountManager:
    """NFS mount operations for Azure Files shares.
    
    Philosophy:
    - Remote operations via SSH
    - Atomic mount/unmount (rollback on failure)
    - Preserves user data (backup before mount)
    - Updates /etc/fstab for persistence
    """
    
    @classmethod
    def mount_storage(
        cls,
        vm_ip: str,
        ssh_key: Path,
        nfs_endpoint: str,
        mount_point: str = "/home/azureuser",
    ) -> MountResult:
        """Mount NFS share on VM.
        
        Steps:
        1. Install nfs-common if not present
        2. Backup existing mount point to .backup
        3. Create mount point if doesn't exist
        4. Mount NFS share
        5. Update /etc/fstab for persistence
        6. Verify mount successful
        7. Copy backup files to mounted share if empty
        
        Rollback on failure:
        - Unmount if partially mounted
        - Restore from backup
        
        Returns:
            MountResult with success status and details
        """
        
    @classmethod
    def unmount_storage(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str = "/home/azureuser",
    ) -> UnmountResult:
        """Unmount NFS share from VM.
        
        Steps:
        1. Copy mounted files to local backup
        2. Unmount NFS share
        3. Remove from /etc/fstab
        4. Move backup to original mount point
        5. Verify unmount successful
        
        Returns:
            UnmountResult with success status
        """
        
    @classmethod
    def verify_mount(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str = "/home/azureuser",
    ) -> bool:
        """Check if mount point is NFS-mounted."""
        
    @classmethod
    def get_mount_info(
        cls,
        vm_ip: str,
        ssh_key: Path,
        mount_point: str = "/home/azureuser",
    ) -> MountInfo | None:
        """Get mount information if mounted."""
```

**Data Models**:
```python
@dataclass
class MountResult:
    """Result of mount operation."""
    success: bool
    mount_point: str
    nfs_endpoint: str
    backed_up_files: int
    copied_files: int
    errors: list[str]
    
@dataclass
class UnmountResult:
    """Result of unmount operation."""
    success: bool
    mount_point: str
    backed_up_files: int
    errors: list[str]
    
@dataclass
class MountInfo:
    """Current mount information."""
    mount_point: str
    nfs_endpoint: str
    filesystem_type: str
    mount_options: str
```

---

## CLI Integration

### New Command Group: `azlin storage`

**Implementation in `cli.py`**:
```python
@main.group()
def storage():
    """Manage Azure Files NFS storage accounts."""
    pass

@storage.command("create")
@click.argument("name")
@click.option("--tier", type=click.Choice(["Premium", "Standard"]), default="Premium")
@click.option("--size", default="100GB", help="Storage size (e.g., 100GB, 1TB)")
@click.option("--region", help="Azure region")
@click.option("--resource-group", help="Resource group")
def storage_create(name, tier, size, region, resource_group):
    """Create Azure Files NFS storage account."""
    # Parse size to GB
    # Get config
    # Call StorageManager.create_storage()
    # Display result
    
@storage.command("list")
@click.option("--resource-group", help="Resource group")
def storage_list(resource_group):
    """List storage accounts."""
    # Get config
    # Call StorageManager.list_storage()
    # Display table
    
@storage.command("status")
@click.argument("name")
@click.option("--resource-group", help="Resource group")
def storage_status(name, resource_group):
    """Show storage account status."""
    # Get config
    # Call StorageManager.get_storage_status()
    # Display detailed status
    
@storage.command("attach")
@click.argument("name")
@click.option("--vm", required=True, help="VM name or session name")
@click.option("--resource-group", help="Resource group")
def storage_attach(name, vm, resource_group):
    """Attach VM to storage account."""
    # Resolve VM name
    # Get storage info
    # Get VM IP
    # Call NFSMountManager.mount_storage()
    # Update config
    # Display result
    
@storage.command("detach")
@click.option("--vm", required=True, help="VM name or session name")
@click.option("--resource-group", help="Resource group")
def storage_detach(vm, resource_group):
    """Detach VM from storage."""
    # Resolve VM name
    # Get VM IP
    # Call NFSMountManager.unmount_storage()
    # Update config
    # Display result
    
@storage.command("delete")
@click.argument("name")
@click.option("--resource-group", help="Resource group")
@click.option("--force", is_flag=True, help="Skip connected VMs check")
def storage_delete(name, resource_group, force):
    """Delete storage account."""
    # Get storage status
    # Confirm deletion
    # Call StorageManager.delete_storage()
    # Display result
```

### Modify `azlin new` command

**Add `--shared-home` option**:
```python
@click.command()
@click.option("--shared-home", help="Shared storage name for home directory")
# ... existing options
def new_command(..., shared_home, ...):
    """Provision new VM."""
    # ... existing logic
    
    # NEW: If shared_home specified
    if shared_home:
        # Validate storage exists
        storage = StorageManager.get_storage(shared_home, resource_group)
        
        # Modify cloud-init to mount NFS
        cloud_init = _build_cloud_init_with_nfs(storage.nfs_endpoint)
        
    # ... continue provisioning
```

---

## Configuration Management

### Extend `config_manager.py`

**New configuration structure**:
```python
# ~/.azlin/config.toml
[storage]
# Storage account -> resource group mapping
shared-dev = "azlin-rg-12345"
ml-data = "azlin-rg-12345"

[vm_storage]
# VM -> storage mapping
worker-1 = "shared-dev"
worker-2 = "shared-dev"  
worker-3 = "shared-dev"
```

**New methods**:
```python
class ConfigManager:
    # ... existing methods
    
    @classmethod
    def register_storage(cls, name: str, resource_group: str):
        """Register storage account in config."""
        
    @classmethod
    def get_storage_resource_group(cls, name: str) -> str | None:
        """Get resource group for storage account."""
        
    @classmethod
    def attach_vm_to_storage(cls, vm_name: str, storage_name: str):
        """Record VM-storage relationship."""
        
    @classmethod
    def detach_vm_from_storage(cls, vm_name: str):
        """Remove VM-storage relationship."""
        
    @classmethod
    def get_vm_storage(cls, vm_name: str) -> str | None:
        """Get storage attached to VM."""
```

---

## Cost Tracking Integration

### Extend `cost_tracker.py`

**Storage cost calculations**:
```python
class CostTracker:
    # ... existing methods
    
    STORAGE_COSTS = {
        "Premium": {
            "per_gb_month": 0.1536,  # $0.1536/GB/month
        },
        "Standard": {
            "per_gb_month": 0.04,  # $0.04/GB/month
        },
    }
    
    @classmethod
    def calculate_storage_cost(
        cls,
        size_gb: int,
        tier: str,
        days: int = 30,
    ) -> float:
        """Calculate storage cost for given period."""
        
    @classmethod
    def get_total_costs(
        cls,
        resource_group: str,
    ) -> dict:
        """Get total costs including VMs and storage.
        
        Returns:
            {
                "vms": [...],
                "storage": [...],
                "total_vm_cost": float,
                "total_storage_cost": float,
                "grand_total": float,
            }
        """
```

---

## VM Provisioning Integration

### Extend `vm_provisioning.py`

**Add NFS mount to cloud-init**:
```python
class VMProvisioner:
    # ... existing methods
    
    @classmethod
    def _build_cloud_init_with_nfs(
        cls,
        nfs_endpoint: str,
        mount_point: str = "/home/azureuser",
    ) -> str:
        """Build cloud-init with NFS mount.
        
        Adds to cloud-init:
        - Install nfs-common
        - Create mount point
        - Mount NFS share
        - Add to /etc/fstab
        - Set ownership to azureuser:azureuser
        """
        
        cloud_init = """#cloud-config
packages:
  - nfs-common
  # ... existing packages

runcmd:
  # ... existing commands
  
  # Mount NFS storage
  - mkdir -p {mount_point}
  - mount -t nfs -o sec=sys {nfs_endpoint} {mount_point}
  - echo "{nfs_endpoint} {mount_point} nfs defaults 0 0" >> /etc/fstab
  - chown -R azureuser:azureuser {mount_point}
"""
        return cloud_init
```

---

## Security Considerations

### Network Security
1. **VNet-only access**: Storage account has no public endpoint
2. **Private endpoint**: Direct VNet connection to storage
3. **NSG rules**: Allow NFS port (2049) within VNet
4. **Service endpoints**: Enable Microsoft.Storage on subnet

### Authentication
1. **No credentials in code**: Use Azure CLI authentication
2. **SSH keys**: Existing key management for VM access
3. **UID/GID consistency**: azureuser = 1000 on all VMs

### Data Protection
1. **Encryption at rest**: Azure default (256-bit AES)
2. **Encryption in transit**: NFS 4.1 with Kerberos (optional)
3. **Backup before mount**: Preserve existing data
4. **Atomic operations**: Rollback on failure

---

## Error Handling

### Validation Errors
- Invalid storage name (must be 3-24 chars, alphanumeric)
- Invalid tier (must be Premium or Standard)
- Invalid size (must be positive integer with GB/TB)
- Storage name conflict (already exists)

### Runtime Errors
- Storage creation failed (Azure API error)
- VNet creation failed
- NFS mount failed (network issue, permissions)
- VM not accessible (SSH failure)
- Storage in use (can't delete)

### Error Messages
All errors follow pattern:
```
[ERROR] Operation failed: <specific reason>

Possible causes:
  - Cause 1 with mitigation
  - Cause 2 with mitigation
  
Try: azlin storage status <name>
```

---

## Testing Strategy (TDD Approach)

### Unit Tests (Step 4)

**Write these tests BEFORE implementation**:

```python
# tests/unit/test_storage_manager.py

def test_create_storage_validates_name():
    """Test storage name validation."""
    with pytest.raises(ValidationError):
        StorageManager.create_storage("ab", "rg", "westus2")  # Too short
        
def test_create_storage_validates_tier():
    """Test tier validation."""
    with pytest.raises(ValidationError):
        StorageManager.create_storage("test", "rg", "westus2", tier="Invalid")
        
def test_create_storage_idempotent(mock_az_cli):
    """Test create is idempotent (returns existing if present)."""
    mock_az_cli.return_value = '{"name": "test", "exists": true}'
    result = StorageManager.create_storage("test", "rg", "westus2")
    assert result.name == "test"
    
def test_list_storage_empty(mock_az_cli):
    """Test list returns empty list when no storage."""
    mock_az_cli.return_value = "[]"
    result = StorageManager.list_storage("rg")
    assert result == []
    
def test_get_storage_not_found(mock_az_cli):
    """Test get raises error when storage doesn't exist."""
    mock_az_cli.side_effect = subprocess.CalledProcessError(1, "az")
    with pytest.raises(StorageNotFoundError):
        StorageManager.get_storage("nonexistent", "rg")
        
def test_delete_storage_in_use():
    """Test delete fails when VMs connected."""
    with pytest.raises(StorageInUseError):
        StorageManager.delete_storage("test", "rg", force=False)
```

```python
# tests/unit/test_nfs_mount_manager.py

def test_mount_installs_nfs_common(mock_ssh):
    """Test mount installs nfs-common package."""
    NFSMountManager.mount_storage("1.2.3.4", Path("key"), "endpoint")
    assert "apt-get install -y nfs-common" in mock_ssh.commands
    
def test_mount_backs_up_existing_data(mock_ssh):
    """Test mount backs up existing home directory."""
    NFSMountManager.mount_storage("1.2.3.4", Path("key"), "endpoint")
    assert "mv /home/azureuser /home/azureuser.backup" in mock_ssh.commands
    
def test_mount_updates_fstab(mock_ssh):
    """Test mount adds entry to /etc/fstab."""
    NFSMountManager.mount_storage("1.2.3.4", Path("key"), "endpoint")
    assert ">> /etc/fstab" in mock_ssh.commands
    
def test_mount_rollback_on_failure(mock_ssh):
    """Test mount rolls back on failure."""
    mock_ssh.side_effect = [None, Exception("Mount failed")]
    result = NFSMountManager.mount_storage("1.2.3.4", Path("key"), "endpoint")
    assert not result.success
    assert "mv /home/azureuser.backup /home/azureuser" in mock_ssh.commands
    
def test_unmount_preserves_data(mock_ssh):
    """Test unmount copies data to local before unmounting."""
    NFSMountManager.unmount_storage("1.2.3.4", Path("key"))
    assert "cp -a /home/azureuser /home/azureuser.local" in mock_ssh.commands
```

### Integration Tests

```python
# tests/integration/test_storage_integration.py

@pytest.mark.integration
def test_create_and_delete_storage():
    """Test full storage lifecycle."""
    name = f"test-{int(time.time())}"
    # Create
    storage = StorageManager.create_storage(name, "test-rg", "westus2")
    assert storage.name == name
    # List
    storages = StorageManager.list_storage("test-rg")
    assert any(s.name == name for s in storages)
    # Delete
    StorageManager.delete_storage(name, "test-rg")
    # Verify deleted
    with pytest.raises(StorageNotFoundError):
        StorageManager.get_storage(name, "test-rg")
```

---

## Implementation Plan

### Day 1-2: TDD Setup and Design ✅
- [x] Write requirements document
- [x] Create architecture design
- [ ] Write all failing tests (TDD)
- [ ] Set up mocks for Azure CLI and SSH

### Day 3-5: StorageManager Implementation
- [ ] Implement `create_storage()` 
- [ ] Implement `list_storage()`
- [ ] Implement `get_storage()`
- [ ] Implement `get_storage_status()`
- [ ] Implement `delete_storage()`
- [ ] Make unit tests pass

### Day 6-7: NFSMountManager Implementation
- [ ] Implement `mount_storage()`
- [ ] Implement `unmount_storage()`
- [ ] Implement `verify_mount()`
- [ ] Implement `get_mount_info()`
- [ ] Make unit tests pass

### Day 8-10: CLI Integration
- [ ] Add `storage` command group
- [ ] Implement all subcommands
- [ ] Modify `new` command for `--shared-home`
- [ ] Update config_manager
- [ ] Update cost_tracker

### Day 11-12: Integration Testing
- [ ] Test against real Azure
- [ ] Test multi-VM scenarios
- [ ] Performance testing
- [ ] Security testing

### Day 13: Manual Testing (Step 8)
- [ ] Create storage account
- [ ] Provision 2 VMs with shared home
- [ ] Verify file sharing works
- [ ] Attach 3rd VM
- [ ] Detach VM
- [ ] Delete storage
- [ ] Document results

### Day 14-15: Documentation and Cleanup
- [ ] Update README.md
- [ ] Add examples to documentation
- [ ] Create troubleshooting guide
- [ ] Final code review
- [ ] Cleanup and refactor

---

## Success Metrics

### Performance
- Storage creation: < 3 minutes
- NFS mount: < 30 seconds
- List operation: < 5 seconds
- Read/write: > 90% of local disk speed

### Reliability
- Idempotent operations: 100%
- Atomic rollback: 100%
- Data preservation: 100%
- Mount persistence: 100% after reboot

### Usability
- One command to create storage
- One command to attach VM
- Clear error messages
- Progress indicators for long operations

---

*Design document created on October 18, 2025 (Step 4 of DEFAULT_WORKFLOW)*
