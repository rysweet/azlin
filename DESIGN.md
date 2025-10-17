# azlin clone Command - Architecture Design

## Overview
The `azlin clone` command creates new VM(s) with home directory contents copied from an existing source VM.

## Design Principles
- **Reuse Existing Components**: Leverage `VMProvisioner.provision_vm_pool()` and `azlin cp`
- **Parallel Execution**: Provision and copy in parallel for multiple replicas
- **Partial Success Handling**: Continue operation even if some replicas fail
- **Security**: Respect existing file transfer security filters

## Architecture

### Component Diagram
```
┌─────────────────────────────────────────────────────────┐
│                    clone_command()                       │
│                                                          │
│  1. Validate source VM                                   │
│  2. Generate clone configs                               │
│  3. Provision VMs (parallel)                            │
│  4. Copy home directories (parallel)                    │
│  5. Set session names                                    │
└─────────────────────────────────────────────────────────┘
           │                      │                │
           ▼                      ▼                ▼
    ┌──────────┐         ┌──────────────┐   ┌──────────────┐
    │VMManager │         │VMProvisioner │   │FileTransfer  │
    │          │         │              │   │              │
    │ -get_vm()│         │-provision_   │   │ -transfer()  │
    │          │         │  vm_pool()   │   │              │
    └──────────┘         └──────────────┘   └──────────────┘
```

### Data Flow
1. **Input Validation**
   - Resolve source VM (by session name or VM name)
   - Validate source VM exists and is accessible
   - Check resource group and configuration

2. **Clone VM Creation**
   - Generate unique VM names (azlin-vm-TIMESTAMP-1, azlin-vm-TIMESTAMP-2, etc.)
   - Create VMConfig objects with source VM attributes
   - Call `VMProvisioner.provision_vm_pool()` for parallel provisioning

3. **Home Directory Copy**
   - Wait for all VMs to be ready
   - For each successful clone:
     - Build rsync paths: `source_vm:/home/azureuser/` → `clone_vm:/home/azureuser/`
     - Use FileTransfer module with recursive copy
     - Execute in parallel using ThreadPoolExecutor

4. **Session Name Assignment**
   - If `--session-prefix` provided:
     - Single replica: Set to `<prefix>`
     - Multiple replicas: Set to `<prefix>-1`, `<prefix>-2`, etc.
   - Use ConfigManager to persist session names

5. **Result Display**
   - Show summary: `N/M clones successful`
   - List each clone: name, session name, IP address
   - Show any failures with error messages

## CLI Interface

### Command Signature
```python
@click.command()
@click.argument('source_vm')
@click.option('--num-replicas', default=1, type=int,
              help='Number of clones to create (default: 1)')
@click.option('--session-prefix', type=str,
              help='Session name prefix for clones')
@click.option('--resource-group', type=str,
              help='Resource group (uses config default if not specified)')
@click.option('--vm-size', type=str,
              help='VM size for clones (default: same as source)')
@click.option('--region', type=str,
              help='Azure region (default: same as source)')
@click.option('--config', type=click.Path(),
              help='Config file path')
def clone_command(source_vm, num_replicas, session_prefix,
                  resource_group, vm_size, region, config):
    """Clone a VM with its home directory contents."""
```

### Implementation Location
- **File**: `src/azlin/cli.py`
- **Function**: `clone_command()`
- **Helper Functions**:
  - `_resolve_source_vm()` - Find VM by session name or VM name
  - `_generate_clone_configs()` - Create VMConfig list
  - `_copy_home_directories()` - Parallel home directory copy
  - `_set_clone_session_names()` - Assign session names

## Error Handling

### Validation Errors (fail fast)
- Source VM not found → Exit with error
- Invalid num-replicas (< 1) → Exit with error
- Invalid vm-size or region → Exit with error

### Provisioning Errors (partial success)
- Some VMs fail to provision → Continue with successful ones
- Display failed VMs in summary
- Return non-zero exit code if all failed

### Copy Errors (partial success)
- Home directory copy fails for some VMs → Mark as warning
- Continue with other clones
- Display warnings in summary

### Example Error Messages
```
Error: Source VM 'amplihack' not found
  Available VMs: azlin-vm-001, azlin-vm-002
  Available sessions: dev-env, test-env

Error: num-replicas must be >= 1

Warning: Failed to copy home directory to clone-2
  Error: rsync timeout after 5 minutes
  Clone VM is running but home directory is empty

Success: 2/3 clones created successfully
  ✓ clone-1 (dev-clone-1): 20.12.34.56
  ✓ clone-3 (dev-clone-3): 20.12.34.58
  ✗ clone-2: provisioning failed (SKU unavailable)
```

## Security Considerations

### File Transfer Security
- Reuse existing FileTransfer security:
  - Block SSH keys (`.ssh/`, `id_rsa`, etc.)
  - Block cloud credentials (`.aws/`, `.azure/`, etc.)
  - Block environment files (`.env`, `.env.*`)
  - Block secrets (`*.pem`, `*.key`, `credentials.json`)

### Input Validation
- Validate VM names (alphanumeric, hyphens only)
- Validate session prefixes (alphanumeric, hyphens, underscores)
- Use argument arrays (no shell=True) for all subprocess calls

### Authentication
- Use existing SSH key management
- Respect Azure authentication (az cli credentials)

## Performance Characteristics

### Single Clone (1 replica)
- Provision time: 3-5 minutes (VM creation + cloud-init)
- Copy time: 1-10 minutes (depends on home directory size)
- Total: ~4-15 minutes

### Multiple Clones (3 replicas)
- Provision time: 3-5 minutes (parallel provisioning)
- Copy time: 1-10 minutes (parallel copying)
- Total: ~4-15 minutes (same as single clone due to parallelism)

### Bottlenecks
- Azure VM provisioning API limits
- Network bandwidth for file transfer
- Source VM SSH connection limit

### Optimization Strategies
- Parallel VM provisioning (already implemented in provision_vm_pool)
- Parallel home directory copying (use ThreadPoolExecutor)
- Limit max_workers to avoid overwhelming source VM

## Testing Strategy

### Unit Tests
```python
def test_clone_single_vm():
    """Test cloning a single VM."""

def test_clone_multiple_replicas():
    """Test cloning multiple VMs in parallel."""

def test_clone_with_session_prefix():
    """Test session name assignment."""

def test_clone_source_not_found():
    """Test error when source VM doesn't exist."""

def test_clone_partial_provisioning_failure():
    """Test handling of partial provisioning failures."""

def test_clone_copy_failure():
    """Test handling of home directory copy failures."""
```

### Integration Tests
```python
def test_clone_end_to_end_mocked():
    """Test complete clone workflow with mocked Azure API."""

def test_clone_session_name_resolution():
    """Test finding source VM by session name."""
```

### Manual Testing Checklist
- [ ] Clone single VM with default settings
- [ ] Clone multiple replicas (3 VMs)
- [ ] Clone with session prefix
- [ ] Clone with custom VM size
- [ ] Clone with custom region
- [ ] Test source VM not found error
- [ ] Test partial provisioning failure
- [ ] Test home directory copy with large files
- [ ] Verify security filters work (don't copy .ssh, .env, etc.)

## Implementation Plan

### Phase 1: Core Functionality (Must Have)
1. Add `clone_command()` to cli.py
2. Implement source VM resolution (session name or VM name)
3. Implement VM provisioning using `provision_vm_pool()`
4. Implement home directory copy using FileTransfer
5. Basic error handling and user feedback

### Phase 2: Session Names (Must Have)
6. Implement session name assignment logic
7. Integrate with ConfigManager
8. Test session name resolution and assignment

### Phase 3: Robustness (Must Have)
9. Implement partial success handling
10. Add comprehensive error messages
11. Add progress indicators
12. Handle edge cases (source VM stopped, etc.)

### Phase 4: Testing & Documentation (Must Have)
13. Write unit tests
14. Write integration tests
15. Update README.md
16. Add CLI help text

## Dependencies

### Existing Modules (No Changes)
- `VMProvisioner` - Provision VMs in parallel
- `FileTransfer` - Copy files with security filters
- `VMManager` - Query VM information
- `ConfigManager` - Manage session names

### New Code (To Be Written)
- `clone_command()` in cli.py (~200 lines)
- Helper functions (~100 lines)
- Unit tests (~300 lines)
- Integration tests (~200 lines)

## API Contracts

### clone_command() Interface
```python
def clone_command(
    source_vm: str,
    num_replicas: int = 1,
    session_prefix: Optional[str] = None,
    resource_group: Optional[str] = None,
    vm_size: Optional[str] = None,
    region: Optional[str] = None,
    config: Optional[str] = None
) -> int:
    """
    Clone a VM with its home directory contents.

    Args:
        source_vm: Source VM (session name or VM name)
        num_replicas: Number of clones to create
        session_prefix: Session name prefix for clones
        resource_group: Resource group
        vm_size: VM size for clones (default: same as source)
        region: Azure region (default: same as source)
        config: Config file path

    Returns:
        Exit code (0 for success, 1 for error)

    Raises:
        None (prints errors and returns exit code)
    """
```

### Helper Function Interfaces
```python
def _resolve_source_vm(
    source_vm: str,
    resource_group: str,
    config_manager: ConfigManager
) -> VMInfo:
    """Resolve source VM by session name or VM name."""

def _generate_clone_configs(
    source_vm: VMInfo,
    num_replicas: int,
    vm_size: Optional[str],
    region: Optional[str]
) -> List[VMConfig]:
    """Generate VMConfig objects for clones."""

def _copy_home_directories(
    source_vm: VMInfo,
    clone_vms: List[VMDetails],
    ssh_key_path: str,
    max_workers: int = 5
) -> Dict[str, bool]:
    """Copy home directories from source to clones in parallel."""

def _set_clone_session_names(
    clone_vms: List[VMDetails],
    session_prefix: str,
    config_manager: ConfigManager
) -> None:
    """Set session names for cloned VMs."""
```

## Success Metrics
- Clone command completes successfully in < 10 minutes for single VM
- Clone command handles partial failures gracefully
- All security filters are respected
- Session names work correctly
- All tests pass
- Documentation is comprehensive

## Risks and Mitigations

### Risk: Source VM SSH overload
**Mitigation**: Limit parallel copy workers to 5

### Risk: Partial provisioning failures
**Mitigation**: Implement partial success handling, continue with successful clones

### Risk: Large home directories timeout
**Mitigation**: Increase rsync timeout, show progress, allow resume

### Risk: Name collisions
**Mitigation**: Use timestamp-based VM names, validate uniqueness

## Future Enhancements (Out of Scope)
- Snapshot-based cloning (faster for large home directories)
- Incremental copying (rsync with --link-dest)
- Clone from stopped VMs (auto-start source)
- Clone to different resource group
- Clone with custom cloud-init (different tools)
