# Implementation Plan: Issue #25 - VM Snapshot Management

## Overview
Add snapshot/backup management functionality to azlin for Azure VMs using managed disk snapshots.

## Feature Requirements
- Create snapshots of VM disks
- List existing snapshots
- Restore VM from snapshot
- Delete snapshots
- Auto-naming with timestamps
- Metadata storage in config
- Size/cost warnings

## Architecture

### New Module: `snapshot_manager.py`
Core snapshot management functionality:
- `SnapshotManager` class for Azure snapshot operations
- Uses Azure CLI (`az snapshot`) for operations
- Integrates with existing `ConfigManager` for metadata

### CLI Integration
Update `cli.py` to add snapshot command group:
```
azlin snapshot create <vm>
azlin snapshot list <vm>
azlin snapshot restore <vm> <snapshot-name>
azlin snapshot delete <vm> <snapshot-name>
```

### Data Models
```python
@dataclass
class SnapshotInfo:
    name: str
    vm_name: str
    resource_group: str
    disk_name: str
    size_gb: int
    created_time: str
    location: str
    provisioning_state: str
```

### Key Functions
1. `create_snapshot(vm_name, resource_group)` - Create snapshot with timestamp
2. `list_snapshots(vm_name, resource_group)` - List snapshots for VM
3. `restore_snapshot(vm_name, snapshot_name, resource_group)` - Restore from snapshot
4. `delete_snapshot(snapshot_name, resource_group)` - Delete snapshot
5. `get_snapshot_cost_estimate(size_gb, days)` - Calculate storage cost

## Implementation Steps

### 1. Create Tests (RED Phase)
- `tests/unit/test_snapshot_manager.py`
  - Test snapshot creation
  - Test snapshot listing
  - Test snapshot restoration
  - Test snapshot deletion
  - Test error handling
  - Test cost estimation

### 2. Implement Feature (GREEN Phase)
- `src/azlin/snapshot_manager.py`
  - Implement SnapshotManager class
  - Azure CLI integration for snapshot operations
  - Auto-naming with timestamps
  - Error handling

### 3. CLI Integration
- Update `src/azlin/cli.py`
  - Add snapshot command group
  - Add create/list/restore/delete subcommands
  - Add cost warnings

### 4. Refactor (REFACTOR Phase)
- Extract common patterns
- Optimize Azure CLI calls
- Improve error messages

### 5. Validation
- Run linter
- Run all tests
- Manual testing

## Technical Details

### Snapshot Naming Convention
`{vm_name}-snapshot-{timestamp}`
Example: `azlin-dev-snapshot-20251015-053000`

### Azure CLI Commands Used
- `az snapshot create` - Create snapshot from disk
- `az snapshot list` - List snapshots
- `az snapshot delete` - Delete snapshot
- `az disk list` - Get VM disk information
- `az vm show` - Get VM details

### Cost Estimation
- Snapshot storage: ~$0.05 per GB-month (Standard HDD)
- Calculate based on disk size and retention period
- Show warning before creation

### Error Handling
- VM not found
- Disk not found
- Snapshot already exists
- Insufficient permissions
- Azure API errors

## Files to Create/Modify

### New Files
1. `src/azlin/snapshot_manager.py`
2. `tests/unit/test_snapshot_manager.py`

### Modified Files
1. `src/azlin/cli.py` - Add snapshot commands

## Testing Strategy
- Unit tests with mocked Azure CLI calls
- Test success and error paths
- Verify snapshot naming
- Verify cost calculations
- Test integration with existing config

## Security Considerations
- No credential storage (delegated to Azure CLI)
- Input validation for VM names and snapshot names
- No shell=True in subprocess calls
- Sanitized logging

## Dependencies
- Existing: azure-cli, click
- No new dependencies required

## Timeline
1. Write failing tests: 15 min
2. Implement snapshot_manager.py: 30 min
3. Update CLI: 15 min
4. Run tests and fix: 15 min
5. Refactor: 10 min
6. Final validation: 10 min

Total: ~90 minutes
