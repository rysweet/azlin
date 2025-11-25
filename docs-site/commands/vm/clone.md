# azlin clone

Clone a VM with its home directory contents.

## Synopsis

```bash
azlin clone SOURCE_VM [OPTIONS]
```

## Description

Creates new VM(s) and copies the entire home directory from the source VM. Useful for creating development environments, parallel testing, or team onboarding.

Home directory security filters are applied (no SSH keys, credentials, etc.).

## Arguments

**SOURCE_VM** - Source VM name or session name (required)

## Options

| Option | Description |
|--------|-------------|
| `--num-replicas INTEGER` | Number of clones to create (default: 1) |
| `--session-prefix TEXT` | Session name prefix for clones |
| `--resource-group, --rg TEXT` | Resource group |
| `--vm-size TEXT` | VM size for clones (default: same as source) |
| `--region TEXT` | Azure region (default: same as source) |
| `--config PATH` | Config file path |
| `-h, --help` | Show help message |

## Examples

### Clone Single VM

```bash
# Clone VM with default name
azlin clone amplihack
```

Creates one clone with auto-generated name.

### Clone with Custom Name

```bash
# Clone with session name
azlin clone amplihack --session-prefix dev-env
```

Creates: `dev-env` VM

### Clone Multiple Replicas

```bash
# Create 3 clones
azlin clone amplihack --num-replicas 3 --session-prefix worker
```

Creates:
- `worker-1`
- `worker-2`
- `worker-3`

### Clone with Different VM Size

```bash
# Clone with larger VM size
azlin clone my-vm --vm-size Standard_D4s_v3
```

Useful for scaling up/down resources.

### Clone to Different Region

```bash
# Clone to different region
azlin clone my-vm --region westus2
```

## Use Cases

### Development Environment

```bash
# Set up base development VM
azlin new --name dev-base
azlin connect dev-base

# Install tools, configure environment
sudo apt install -y build-essential python3 nodejs
git clone https://github.com/myorg/project
# ... more setup ...

exit

# Clone for team members
azlin clone dev-base --session-prefix alice
azlin clone dev-base --session-prefix bob
azlin clone dev-base --session-prefix charlie
```

### Parallel Testing

```bash
# Create test environment
azlin new --name test-template
# ... configure test environment ...

# Clone for parallel test runs
azlin clone test-template --num-replicas 5 --session-prefix test-runner
```

Enables parallel test execution across multiple VMs.

### Team Onboarding

```bash
# Prepare onboarding VM
azlin new --name onboarding-template
azlin connect onboarding-template

# Set up documentation, tools, configs
mkdir ~/docs ~/projects ~/scripts
# ... add files ...

exit

# Clone for new team members
azlin clone onboarding-template --session-prefix new-hire-jan
azlin clone onboarding-template --session-prefix new-hire-feb
```

### Scale Testing

```bash
# Create base load generator
azlin new --name load-gen-base
# ... install load testing tools ...

# Scale out for distributed load test
azlin clone load-gen-base --num-replicas 10 --session-prefix load-gen
```

## What Gets Cloned

### VM Configuration

Cloned from source:
- VM size (unless overridden)
- Region (unless overridden)
- OS image
- Network configuration
- Tags

### Home Directory

Copied from `/home/azureuser/`:
- All files and directories
- File permissions
- Directory structure
- Dotfiles (`.bashrc`, `.vimrc`, etc.)

### Security Filters

**Not copied:**
- `.ssh/` directory
- SSH private keys
- `.env` files with credentials
- Azure credentials
- Git credentials

### Not Cloned

- VM name (new name generated)
- Public IP address (new IP assigned)
- SSH host keys (newly generated)
- System configurations outside home directory

## Cloning Process

1. **Validate Source** - Ensure source VM exists and is accessible
2. **Create New VM(s)** - Provision with same configuration
3. **Wait for Ready** - Wait for VMs to become running
4. **Copy Home Directory** - rsync home directory from source
5. **Apply Filters** - Remove sensitive files
6. **Report Status** - Show clone results

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| VM creation | 2-3 minutes | Per VM |
| Home directory copy | 1-5 minutes | Depends on size |
| Total (1 clone) | 3-8 minutes | |
| Total (5 clones) | 10-15 minutes | Parallel creation |

Home directory size significantly affects copy time:
- Small (< 1 GB): 1-2 minutes
- Medium (1-10 GB): 2-5 minutes
- Large (> 10 GB): 5-15 minutes

## Output Example

```bash
$ azlin clone dev-base --num-replicas 3 --session-prefix worker
```

**Output:**
```
Cloning dev-base...

Creating 3 VMs...
✓ worker-1 created (20.1.2.10)
✓ worker-2 created (20.1.2.11)
✓ worker-3 created (20.1.2.12)

Copying home directory from dev-base...
✓ worker-1: Copied 2.3 GB in 3.2 minutes
✓ worker-2: Copied 2.3 GB in 3.5 minutes
✓ worker-3: Copied 2.3 GB in 3.1 minutes

Clone complete!

VMs created:
  worker-1 (20.1.2.10)
  worker-2 (20.1.2.11)
  worker-3 (20.1.2.12)

Connect:
  azlin connect worker-1
  azlin connect worker-2
  azlin connect worker-3
```

## Best Practices

### Prepare Source VM

```bash
# Clean up before cloning
azlin connect source-vm

# Remove temporary files
rm -rf /tmp/*
rm -rf ~/.cache/*

# Remove sensitive data
rm ~/.env ~/.aws/credentials

# Document setup
cat > ~/README.md <<EOF
This VM includes:
- Python 3.11
- Node.js 20
- Docker
- Project repo cloned to ~/project
EOF
```

### Use Descriptive Session Prefixes

```bash
# Good: Clear purpose
azlin clone base --session-prefix test-runner
azlin clone base --session-prefix dev-alice

# Bad: Unclear
azlin clone base --session-prefix vm
azlin clone base --session-prefix x
```

### Choose Appropriate VM Sizes

```bash
# Scale down for cost
azlin clone powerful-vm --vm-size Standard_B2s

# Scale up for performance
azlin clone small-vm --vm-size Standard_D8s_v3
```

### Tag Clones

```bash
# After cloning, tag for organization
azlin tag worker-1 --add purpose=testing --add source=dev-base
azlin tag worker-2 --add purpose=testing --add source=dev-base
```

## Troubleshooting

### Source VM Not Found

```bash
# Verify source exists
azlin list

# Check session names
azlin list --show-session

# Use correct identifier
azlin clone correct-vm-name
```

### Clone Fails During Copy

```bash
# Check source VM is running
azlin status source-vm

# Test connectivity
azlin connect source-vm

# Check disk space on source
azlin connect source-vm --command "df -h"
```

### Slow Cloning

```bash
# Check home directory size
azlin connect source-vm --command "du -sh ~"

# Reduce clones created at once
azlin clone source --num-replicas 2  # Instead of 10
```

### Out of Quota

```bash
# Check quota
az vm list-usage --location eastus --output table

# Delete unused VMs
azlin killall --unused

# Or use different region
azlin clone source --region westus2
```

## Related Commands

- [azlin new](new.md) - Create new VM
- [azlin sync](../util/sync.md) - Sync files to VM
- [azlin batch sync](../batch/sync.md) - Sync to multiple VMs
- [azlin list](list.md) - List VMs

## See Also

- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Shared Home Directories](../../storage/shared-home.md)
- [Cloning VMs](../../vm-lifecycle/cloning.md)
