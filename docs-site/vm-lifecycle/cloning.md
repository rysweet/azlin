# Cloning VMs

Duplicate VMs with their home directory contents for parallel work, testing, or team onboarding.

## Quick Start

```bash
# Clone single VM
azlin clone my-vm

# Clone with custom session name
azlin clone my-vm --session-prefix dev-env

# Create multiple clones
azlin clone my-vm --num-replicas 3 --session-prefix worker
```

## Overview

The `azlin clone` command creates new VMs based on an existing VM with:

- **Home directory copy** - All files, code, and configurations
- **Security filtering** - Excludes SSH keys, credentials, tokens
- **Parallel creation** - Clone multiple VMs simultaneously
- **Custom sizing** - Override VM size for clones
- **Session naming** - Auto-generate meaningful session names

## Command Reference

```bash
azlin clone [OPTIONS] SOURCE_VM
```

### Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `SOURCE_VM` | VM name or session name to clone | Yes |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--num-replicas INTEGER` | Number of clones to create | 1 |
| `--session-prefix TEXT` | Session name prefix for clones | None |
| `--resource-group, --rg TEXT` | Resource group | From config |
| `--vm-size TEXT` | VM size for clones | Same as source |
| `--region TEXT` | Azure region | Same as source |

## Common Usage Patterns

### Single Clone

```bash
# Clone VM with default name
azlin clone my-dev-vm

# Creates: my-dev-vm-clone-1 (or similar)
```

**What happens:**

1. Creates new VM with same specs as source
2. Copies `/home/azureuser` from source to clone
3. Filters out sensitive files (SSH keys, .env, etc.)
4. VM ready to use immediately

### Clone with Session Name

```bash
# Clone and assign session name
azlin clone my-dev-vm --session-prefix backend-api

# Creates VM with session: backend-api
```

**What happens:**

1. Creates clone as normal
2. Sets session name to `backend-api`
3. Can connect with: `azlin connect backend-api`

### Multiple Clones (Replicas)

```bash
# Create 3 identical VMs
azlin clone my-vm --num-replicas 3 --session-prefix worker

# Creates:
#   - worker-1
#   - worker-2
#   - worker-3
```

**What happens:**

1. Provisions 3 VMs in parallel
2. Each gets sequentially numbered session name
3. All share the same home directory contents (copied)
4. Perfect for distributed workloads

### Clone with Different Size

```bash
# Clone to larger VM
azlin clone dev-vm --vm-size Standard_E64s_v5 --session-prefix training

# Clone to smaller VM (for testing)
azlin clone ml-vm --vm-size Standard_D4s_v3 --session-prefix test
```

### Clone by Session Name

```bash
# Set session on source VM
azlin session azlin-vm-12345 my-project

# Clone using session name
azlin clone my-project --session-prefix my-project-test
```

## Use Cases

### Parallel Development

```bash
# Create environment for each developer
azlin clone shared-dev-vm --num-replicas 5 --session-prefix dev
# Creates: dev-1, dev-2, dev-3, dev-4, dev-5

# Each developer connects to their own
azlin connect dev-1  # Sarah
azlin connect dev-2  # John
azlin connect dev-3  # Maria
```

### Testing/QA

```bash
# Clone production-like environment for testing
azlin clone prod-vm --session-prefix qa-test --vm-size Standard_D16s_v3

# Run tests without affecting prod
azlin connect qa-test -- pytest tests/
```

### Training/Education

```bash
# Clone instructor environment for students
azlin clone instructor-vm --num-replicas 20 --session-prefix student
# Creates: student-1, student-2, ..., student-20

# Each student gets identical setup
```

### Distributed Computing

```bash
# Clone for parallel processing
azlin clone base-worker --num-replicas 10 --session-prefix worker

# Each worker processes different data
azlin connect worker-1 -- python process.py --shard 1
azlin connect worker-2 -- python process.py --shard 2
# ...
```

### A/B Testing

```bash
# Clone for experimental features
azlin clone stable-vm --session-prefix experimental

# Test changes without affecting stable
azlin connect experimental
# Make changes, test, compare results
```

## What Gets Copied

### Included

- All files in `/home/azureuser`
- Code repositories
- Configuration files (non-sensitive)
- Docker images and containers
- Installed Python packages
- Project dependencies

### Excluded (Security Filters)

- SSH keys (`~/.ssh/id_*`)
- Environment files (`.env`, `.env.*`)
- Credential files (`credentials.json`, etc.)
- API tokens and secrets
- Azure CLI credentials (`~/.azure`)
- Git credentials cache

!!! tip "Fresh Credentials"
    Clones get fresh SSH keys from Azure Key Vault automatically. You'll need to re-configure any API keys or tokens.

## Performance

### Timing

- **Single clone:** 10-15 minutes
- **Multiple clones:** Same (parallel provisioning)
- **Home copy:** 1-5 minutes (depends on size)

### Optimization

```bash
# Faster cloning - clean up source first
azlin connect source-vm -- "
  docker system prune -af
  rm -rf ~/.cache
  uv cache clean
"

azlin clone source-vm --num-replicas 5
```

## Advanced Scenarios

### Cross-Region Cloning

```bash
# Clone to different region
azlin clone eastus-vm --region westus --session-prefix westus-clone
```

### Custom Resource Group

```bash
# Clone to different resource group
azlin clone my-vm --rg production-rg --session-prefix prod-clone
```

### Batch Clone Script

```bash
#!/bin/bash
# Create clones for entire team

TEAM=(alice bob carol dave)
for member in "${TEAM[@]}"; do
  azlin clone shared-dev --session-prefix "dev-$member"
done
```

## Troubleshooting

### Clone Fails to Provision

```bash
# Check quota
azlin quota

# Try smaller VM size
azlin clone my-vm --vm-size Standard_D4s_v3

# Try different region
azlin clone my-vm --region westus
```

### Home Directory Too Large

```bash
# Clean up source VM first
azlin connect source-vm -- "
  docker system prune -af
  rm -rf ~/.cache ~/.npm ~/.cargo/registry
"

# Then clone
azlin clone source-vm
```

### Missing Files After Clone

```bash
# Check security filters
# Sensitive files are intentionally excluded

# Manually copy if needed (after verifying safety)
azlin connect source-vm -- tar czf /tmp/extra.tar.gz ~/specific-files
azlin connect clone-vm -- "cd ~ && tar xzf -" < /tmp/extra.tar.gz
```

### Clones Have Same Name

```bash
# Always use --session-prefix for clarity
azlin clone source --session-prefix unique-name-1
azlin clone source --session-prefix unique-name-2
```

## Cleanup

### Delete Single Clone

```bash
azlin delete clone-vm
```

### Delete Multiple Clones

```bash
# Delete all worker clones
for i in {1..10}; do
  azlin delete worker-$i
done

# Or use Azure CLI for batch deletion
az vm delete --ids $(az vm list -g <rg> --query "[?contains(name, 'worker')].id" -o tsv) --yes
```

## Related Commands

- [`azlin new`](creating.md) - Create fresh VM
- [`azlin list`](listing.md) - View all VMs
- [`azlin connect`](connecting.md) - Connect to clone
- [`azlin session`](sessions.md) - Manage session names
- [`azlin delete`](deleting.md) - Remove clones

## Source Code

- [Clone Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L800)
- [Home Directory Copy](https://github.com/rysweet/azlin/blob/main/azlin/clone.py)
- [Security Filters](https://github.com/rysweet/azlin/blob/main/azlin/security_filters.py)

---

*Last updated: 2025-11-24*
