# Implementation Plan: Issue #27 - SSH Key Rotation and Management

## Overview
Implement `azlin keys` command for SSH key rotation and management across all VMs.

## Commands to Implement
```bash
azlin keys rotate [--all-vms] [--backup]
azlin keys list [--all-vms]
azlin keys export [--output FILE]
azlin keys backup [--destination PATH]
```

## Architecture

### 1. Core Module: `src/azlin/key_rotator.py`

**Classes:**
- `KeyRotationResult`: Dataclass for rotation results
- `KeyBackup`: Dataclass for backup information
- `SSHKeyRotator`: Main rotation logic

**Key Methods:**
- `rotate_keys()`: Generate new key pair and update VMs
- `backup_keys()`: Backup current keys to timestamped directory
- `update_vm_keys()`: Update a single VM with new key via Azure API
- `update_all_vms()`: Update all VMs in parallel
- `rollback_vm()`: Restore old key on failure
- `list_vm_keys()`: List VMs and their public keys
- `export_public_keys()`: Export public keys to file

**Security:**
- Backup old keys before rotation
- Atomic updates (all-or-nothing)
- Graceful rollback on failure
- Secure permissions on backup directory

### 2. CLI Integration: `src/azlin/cli.py`

Add new command group:
```python
@main.group(name='keys')
def keys_group():
    """SSH key management and rotation."""
    pass

@keys_group.command(name='rotate')
@click.option('--all-vms', is_flag=True)
@click.option('--backup/--no-backup', default=True)
@click.option('--resource-group', '--rg')
@click.option('--config')
def keys_rotate(...):
    """Rotate SSH keys for VMs."""
    pass

@keys_group.command(name='list')
@click.option('--all-vms', is_flag=True)
@click.option('--resource-group', '--rg')
@click.option('--config')
def keys_list(...):
    """List VMs and their SSH keys."""
    pass

@keys_group.command(name='export')
@click.option('--output', type=click.Path())
@click.option('--resource-group', '--rg')
@click.option('--config')
def keys_export(...):
    """Export public keys."""
    pass

@keys_group.command(name='backup')
@click.option('--destination', type=click.Path())
def keys_backup(...):
    """Backup current SSH keys."""
    pass
```

### 3. Test Suite: `tests/unit/test_key_rotator.py`

**Test Coverage:**
- Key generation and backup
- Single VM key update
- Multiple VM key update (parallel)
- Rollback on failure
- Error handling
- List and export functionality
- Permission verification

## Implementation Steps (TDD)

### Phase 1: Architecture Planning ✓
- [x] Create implementation plan

### Phase 2: Write Failing Tests (RED)
1. Create `tests/unit/test_key_rotator.py`
2. Write tests for:
   - `test_rotate_keys_creates_new_key`
   - `test_rotate_keys_backs_up_old_key`
   - `test_update_single_vm_success`
   - `test_update_all_vms_parallel`
   - `test_rollback_on_failure`
   - `test_list_vm_keys`
   - `test_export_public_keys`
   - `test_backup_keys_with_timestamp`
3. Run tests → should fail (RED)

### Phase 3: Implement Feature (GREEN)
1. Create `src/azlin/key_rotator.py`
2. Implement core classes and methods
3. Integrate with Azure SDK for VM key updates
4. Add CLI commands to `cli.py`
5. Run tests → should pass (GREEN)

### Phase 4: Refactor
1. Extract common patterns
2. Improve error messages
3. Add logging
4. Optimize parallel operations

### Phase 5: Lint and Commit
1. Run `ruff check` and fix issues
2. Run `pyright` for type checking
3. Commit with message: "feat: implement SSH key rotation (closes #27)"

### Phase 6: Documentation
1. Create `IMPLEMENTATION_COMPLETE_27.md`
2. Document usage examples
3. Update README if needed

## Azure API Integration

Use Azure SDK to update VM SSH keys:
```python
from azure.mgmt.compute import ComputeManagementClient
from azure.identity import DefaultAzureCredential

# Update VM's os_profile with new SSH key
vm = compute_client.virtual_machines.get(rg, vm_name)
vm.os_profile.linux_configuration.ssh.public_keys[0].key_data = new_public_key
compute_client.virtual_machines.begin_create_or_update(rg, vm_name, vm)
```

## Error Handling Strategy

1. **Pre-flight checks:**
   - Verify VMs exist and are accessible
   - Check current key validity
   - Verify backup directory writable

2. **Atomic operations:**
   - Backup before rotation
   - Track which VMs updated successfully
   - Rollback failed VMs to old key

3. **Failure scenarios:**
   - New key generation fails → keep old key
   - Some VMs fail to update → rollback those VMs
   - All VMs fail → restore from backup

## Security Considerations

1. **Key Permissions:**
   - Private key: 0600
   - Public key: 0644
   - Backup directory: 0700

2. **Backup Strategy:**
   - Timestamped backups: `~/.azlin/key_backups/YYYY-MM-DD-HH-MM-SS/`
   - Keep old private/public keys
   - Retention policy (keep last 5 backups)

3. **Validation:**
   - Verify new key can connect before removing old key
   - Test SSH connection after rotation
   - Maintain connection during rotation

## Success Criteria

- [ ] All tests pass
- [ ] `azlin keys rotate` successfully rotates keys
- [ ] `azlin keys list` shows VM key information
- [ ] `azlin keys export` exports public keys
- [ ] `azlin keys backup` creates timestamped backup
- [ ] Rollback works on failure
- [ ] No linter errors
- [ ] Committed with proper message

## Dependencies

- Existing: `azure-mgmt-compute`, `azure-identity` (assumed available)
- Reuse: `SSHKeyManager` from `modules/ssh_keys.py`
- Reuse: `VMManager` for VM listing
- Reuse: `ConfigManager` for resource group config
