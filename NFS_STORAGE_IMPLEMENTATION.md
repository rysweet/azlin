# NFS Storage Integration - Implementation Summary

## Feature Completed

Added support for automatically mounting NFS storage as the home directory when creating new VMs with `azlin new`.

## What Was Implemented

### 1. Command Line Interface

Added `--nfs-storage` option to:
- `azlin new` command
- `azlin vm` command (alias)
- `azlin create` command (alias)

### 2. Core Functionality

**CLIOrchestrator Changes:**
- Added `nfs_storage` parameter to constructor
- Added `_mount_nfs_storage()` method to handle NFS mounting
- Modified `run()` workflow to:
  - Mount NFS storage after cloud-init completes
  - Skip home directory sync when using NFS storage
  - Mount NFS before GitHub setup

**Workflow Logic:**
```
VM Provisioning → Cloud-init → NFS Mount (if specified) → GitHub Setup → SSH Connect
                              OR
                              Home Dir Sync (if no NFS)
```

### 3. Documentation

**README.md Updates:**
- Added NFS storage provisioning section
- Added usage examples showing multi-VM shared storage workflow
- Added to "Creating VMs" section examples
- Updated help text with NFS examples

## Usage Examples

### Basic Usage
```bash
# Create storage once
azlin storage create team-shared --size 100 --tier Premium

# Create VMs with shared home directory
azlin new --nfs-storage team-shared --name worker-1
azlin new --nfs-storage team-shared --name worker-2
```

### What Happens
1. VM is provisioned with standard tools
2. After cloud-init completes, NFS client tools are installed
3. Storage is mounted at `/home/azureuser`
4. If there were files in `~/.azlin/home`, they're copied to shared storage on first mount
5. All subsequent VMs mounting the same storage share the home directory

## Key Benefits

1. **Ease of Use**: Single command to create VM with shared storage
2. **No Manual Steps**: No need to run separate mount commands
3. **Automatic Backup**: Existing home directory backed up before mounting
4. **Immediate Sharing**: Files shared across all VMs instantly
5. **Clean Integration**: Works seamlessly with existing features (GitHub clone, repos, etc.)

## Technical Details

### Storage Mount Location
- Mount point: `/home/azureuser`
- NFS version: 4.1
- Options: Auto-configured by NFSMountManager

### Error Handling
- Storage not found: Clear error message with creation instructions
- Mount failure: Exception raised with detailed error
- Automatic rollback on failure (handled by NFSMountManager)

### Security
- Storage is VNet-only (no public access)
- Uses existing Azure authentication
- SSH keys managed by azlin

## Testing

Verified:
- ✓ `--nfs-storage` option appears in help text
- ✓ CLIOrchestrator accepts nfs_storage parameter
- ✓ Storage commands are available
- ✓ Main help includes storage commands section
- ✓ Python syntax is valid
- ✓ Ruff formatting applied

## Files Modified

1. `src/azlin/cli.py`
   - Added `nfs_storage` parameter to `new_command()` and aliases
   - Added `nfs_storage` to CLIOrchestrator `__init__()`
   - Added `_mount_nfs_storage()` method
   - Modified VM provisioning workflow in `run()`
   - Updated help text and examples

2. `README.md`
   - Added "Provisioning VMs with Shared Storage" section
   - Updated "Creating VMs" section with NFS examples
   - Enhanced shared storage documentation

## Commit

```
commit 5bf50a3
feat: Add --nfs-storage option to azlin new command

- Add --nfs-storage option to 'azlin new' command and its aliases (vm, create)
- Automatically mount NFS storage as /home/azureuser during VM provisioning
- Skip home directory sync when using NFS storage (shared storage provides home)
- Mount storage after cloud-init completes but before GitHub setup
- Add _mount_nfs_storage method to CLIOrchestrator
- Update README with NFS storage provisioning examples
- Add usage examples showing multi-VM shared storage workflow
```

## Next Steps (Future Enhancements)

1. **Default Storage**: Add config option for default storage account
2. **Storage Name Mapping**: Allow friendly names for storage accounts
3. **Multiple Storage**: Support multiple storage accounts per VM
4. **Auto-Creation**: Offer to create storage if it doesn't exist
5. **Storage Templates**: Pre-configured storage layouts

## Known Limitations

- Storage must be created before provisioning VMs
- Only supports one storage account per VM home directory
- Storage must be in the same resource group as VM
- Manual unmount required if switching between storage accounts

## Documentation References

- User-facing: See README.md "Shared Storage" section
- Architecture: See AZURE_FILES_NFS_REQUIREMENTS.md
- Storage commands: Run `azlin storage --help`
- New command: Run `azlin new --help`
