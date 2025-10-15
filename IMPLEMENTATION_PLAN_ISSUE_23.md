# Implementation Plan: Issue #23 - azlin cleanup command

## Overview
Add `azlin cleanup` command to find and remove orphaned Azure resources.

## Architecture

### New Module: `src/azlin/resource_cleanup.py`
**Purpose:** Find and cleanup orphaned Azure resources

**Key Components:**
1. `OrphanedResource` dataclass - represents an orphaned resource
2. `CleanupSummary` dataclass - cleanup operation results
3. `ResourceCleanup` class - main cleanup logic

**Functionality:**
- Detect unattached disks
- Find orphaned NICs (not attached to VMs)
- Find orphaned public IPs (not attached to NICs)
- Safe deletion with confirmation
- Dry-run mode for preview

### CLI Integration: `src/azlin/cli.py`
Add new `cleanup` command with options:
- `--dry-run` - Preview only, no deletions
- `--delete` - Actually delete resources (requires confirmation)
- `--resource-group` - Specific resource group
- `--force` - Skip confirmation prompts

### Test Suite: `tests/unit/test_resource_cleanup.py`
**Test Coverage:**
- Detect orphaned disks
- Detect orphaned NICs
- Detect orphaned public IPs
- Dry-run functionality
- Delete functionality
- Confirmation flow
- Error handling

## Implementation Steps (TDD)

### Step 1: Architecture Planning ✓
Create this implementation plan

### Step 2: Write FAILING Tests (RED)
Create `tests/unit/test_resource_cleanup.py` with:
- Test detect orphaned disks
- Test detect orphaned NICs
- Test detect orphaned public IPs
- Test dry-run mode
- Test delete with confirmation
- Test resource group filtering

### Step 3: Implement Feature (GREEN)
Create `src/azlin/resource_cleanup.py`:
- Implement resource detection
- Implement deletion logic
- Add error handling

Update `src/azlin/cli.py`:
- Add cleanup command
- Add command options
- Wire up to ResourceCleanup module

### Step 4: Refactor (REFACTOR)
- Clean up code
- Add documentation
- Optimize queries

### Step 5: Run Linter
- Run ruff linter
- Fix any issues

### Step 6: Commit
Commit with message: "feat: Add azlin cleanup command for orphaned resources (#23)"

### Step 7: Create Summary Document
Create IMPLEMENTATION_COMPLETE_23.md

## Technical Details

### Azure CLI Commands Used
```bash
# List all disks in resource group
az disk list --resource-group <rg> --output json

# List all NICs in resource group
az network nic list --resource-group <rg> --output json

# List all public IPs in resource group
az network public-ip list --resource-group <rg> --output json

# List all VMs in resource group (to cross-reference)
az vm list --resource-group <rg> --output json

# Delete disk
az disk delete --name <name> --resource-group <rg> --yes

# Delete NIC
az network nic delete --name <name> --resource-group <rg>

# Delete public IP
az network public-ip delete --name <name> --resource-group <rg>
```

### Resource Detection Logic

**Orphaned Disks:**
- Disk exists
- `managedBy` field is null/empty
- Or `diskState` is "Unattached"

**Orphaned NICs:**
- NIC exists
- `virtualMachine` field is null/empty
- Not attached to any VM

**Orphaned Public IPs:**
- Public IP exists
- `ipConfiguration` field is null/empty
- Not attached to any NIC

### Safety Features
1. Dry-run mode by default (no deletions)
2. Explicit `--delete` flag required for deletions
3. Confirmation prompt before deletion (unless `--force`)
4. Clear summary of what will be deleted
5. Error handling with rollback capability

## Expected Output

### Dry-run Example
```
$ azlin cleanup --dry-run

Finding orphaned resources in resource group: azlin-rg-12345...

Orphaned Resources Found:
========================

DISKS (3):
  - azlin-vm-12345_OsDisk_1 (30 GB, Premium SSD)
  - data-disk-old (100 GB, Standard HDD)
  - temp-disk-123 (50 GB, Premium SSD)

NETWORK INTERFACES (2):
  - azlin-vm-12345-nic
  - test-nic-old

PUBLIC IPs (1):
  - azlin-vm-12345-ip (20.1.2.3)

Total Resources: 6
Estimated Cost Savings: ~$15.20/month

DRY RUN - No resources deleted
Use --delete to remove these resources
```

### Delete Example
```
$ azlin cleanup --delete

Finding orphaned resources in resource group: azlin-rg-12345...

Orphaned Resources Found:
  6 resources (3 disks, 2 NICs, 1 public IP)
  Estimated savings: ~$15.20/month

WARNING: This will permanently delete these resources!
Type 'delete' to confirm: delete

Deleting resources...
  ✓ Deleted disk: azlin-vm-12345_OsDisk_1
  ✓ Deleted disk: data-disk-old
  ✓ Deleted disk: temp-disk-123
  ✓ Deleted NIC: azlin-vm-12345-nic
  ✓ Deleted NIC: test-nic-old
  ✓ Deleted public IP: azlin-vm-12345-ip

Cleanup Complete!
  Successfully deleted: 6 resources
  Failed: 0
  Estimated savings: ~$15.20/month
```

## Files to Create/Modify

### New Files:
1. `src/azlin/resource_cleanup.py` - Main cleanup module
2. `tests/unit/test_resource_cleanup.py` - Unit tests
3. `IMPLEMENTATION_COMPLETE_23.md` - Summary document

### Modified Files:
1. `src/azlin/cli.py` - Add cleanup command

## Acceptance Criteria
- [x] Implementation plan created
- [ ] Tests written (failing)
- [ ] Tests passing (green)
- [ ] Code refactored
- [ ] Linter passing
- [ ] Committed with issue reference
- [ ] Summary document created
