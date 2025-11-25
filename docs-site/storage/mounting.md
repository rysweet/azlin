# Mounting Storage


## What is it?

The `--nfs-storage` option lets you create multiple VMs that all share the same home directory using Azure Files NFS. Any file you create on one VM is instantly visible on all other VMs using the same storage.

## Why use it?

- **Team Collaboration**: Multiple developers in the same environment
- **Seamless Switching**: Move between VMs without losing work
- **Distributed Computing**: Multiple workers accessing shared datasets
- **Consistent Environment**: Same configs and tools across all VMs

## Quick Start (3 Commands)

```bash
# 1. Create shared storage (one time)
azlin storage create team-shared --size 100 --tier Premium

# 2. Create first worker VM
azlin new --nfs-storage team-shared --name worker-1

# 3. Create second worker VM
azlin new --nfs-storage team-shared --name worker-2
```

That's it! Both VMs now share `/home/azureuser`.

## Test it Out

```bash
# On worker-1, create a file
ssh worker-1
echo "Hello from worker-1" > ~/test.txt
exit

# On worker-2, read the file
ssh worker-2
cat ~/test.txt  # Shows: Hello from worker-1
exit
```

## Common Commands

```bash
# Create storage
azlin storage create <name> --size <GB> --tier <Premium|Standard>

# List storage accounts
azlin storage list

# Check storage usage and connected VMs
azlin storage status <name>

# Create VM with shared storage
azlin new --nfs-storage <name> --name <vm-name>

# Mount storage on existing VM
azlin storage mount <name> --vm <vm-name>

# Unmount storage
azlin storage unmount --vm <vm-name>

# Delete storage
azlin storage delete <name>
```

## Pricing

| Tier | Cost/GB/month | Best For |
|------|---------------|----------|
| Premium | $0.153 | Active development, high performance |
| Standard | $0.04 | Backups, less frequent access |

**Example**: 100GB Premium = ~$15/month

## What Gets Shared?

Everything in `/home/azureuser`:
- All files and directories
- Configuration files (.bashrc, .gitconfig, etc.)
- Source code repositories
- Development tools configs

## What Doesn't Get Shared?

- SSH keys (each VM has its own)
- VM system files (outside /home/azureuser)
- Processes running on VMs

## Best Practices

1. **Create storage first**: Before creating VMs
2. **Use meaningful names**: Like "team-shared" or "ml-data"
3. **Choose right tier**: Premium for active work, Standard for archives
4. **Monitor usage**: Use `azlin storage status` to check space
5. **Right-size storage**: Start with 100GB, expand as needed

## Workflow Example: Distributed ML Training

```bash
# Setup (once)
azlin storage create ml-shared --size 500 --tier Premium

# Create 3 worker VMs
azlin new --nfs-storage ml-shared --name ml-worker-1
azlin new --nfs-storage ml-shared --name ml-worker-2
azlin new --nfs-storage ml-shared --name ml-worker-3

# All workers now have access to:
# - Same training data in ~/data/
# - Same model checkpoints in ~/models/
# - Same config files in ~/config/
```

## Troubleshooting

**"Storage account not found"**
- Create storage first: `azlin storage create <name>`

**"Mount failed"**
- Check storage exists: `azlin storage list`
- Verify VM is running: `azlin status`
- Check resource group matches

**"Out of space"**
- Check usage: `azlin storage status <name>`
- Delete unneeded files on any connected VM
- Or delete and recreate with larger size

## More Information

- Full docs: See README.md "Shared Storage" section
- Storage commands: `azlin storage --help`
- New VM command: `azlin new --help`
- Technical details: See AZURE_FILES_NFS_REQUIREMENTS.md
