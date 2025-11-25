# azlin storage create

Create Azure Files NFS storage account for shared home directories across VMs.

## Description

The `azlin storage create` command provisions a new Azure Files storage account with NFS v4.1 support, enabling you to share home directories and data across multiple VMs. The storage is accessible only within your Azure VNet for enhanced security.

Storage accounts provide persistent, shared storage that survives VM deletions and allows seamless data sharing between development environments.

## Usage

```bash
azlin storage create NAME [OPTIONS]
```

## Arguments

- `NAME` - Globally unique storage account name (required)
  - Must be 3-24 characters long
  - Lowercase letters and numbers only
  - Must be unique across all of Azure

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--size INTEGER` | Storage size in GB | 100 |
| `--tier [premium\|standard]` | Performance tier | Premium |
| `--resource-group, --rg TEXT` | Azure resource group | Current context |
| `--region TEXT` | Azure region | Current context region |
| `-h, --help` | Show help message | |

## Storage Tiers

### Premium
- **Cost**: $0.153/GB/month
- **Performance**: High IOPS and throughput
- **Use Case**: Development workloads, databases, frequent access
- **Minimum Size**: 100 GB

### Standard
- **Cost**: $0.0184/GB/month
- **Performance**: Standard throughput
- **Use Case**: Backups, archives, infrequent access
- **Suitable for**: Cost-sensitive workloads

## Examples

### Create Premium Storage for Team Development

```bash
# High-performance storage for active development
azlin storage create myteam-shared --size 100 --tier Premium
```

**Output:**
```
Creating storage account 'myteam-shared'...
  Region: eastus
  Size: 100 GB
  Tier: Premium
  Monthly cost: ~$15.30

Storage account created successfully!
NFS endpoint: myteam-shared.file.core.windows.net

Mount on VMs with:
  azlin storage mount vm myteam-shared --vm <vm-name>
```

### Create Standard Storage for Backups

```bash
# Cost-effective storage for backups
azlin storage create backups --size 500 --tier Standard
```

**Output:**
```
Creating storage account 'backups'...
  Region: eastus
  Size: 500 GB
  Tier: Standard
  Monthly cost: ~$9.20

Storage account created successfully!
```

### Create Storage in Specific Region

```bash
# Create storage in west coast region
azlin storage create westcoast-dev --size 200 --tier Premium --region westus2
```

### Create Storage in Different Resource Group

```bash
# Create in production resource group
azlin storage create prod-shared --size 1000 --tier Premium --rg azlin-prod-rg
```

### Large Backup Storage

```bash
# 2TB standard storage for long-term backups
azlin storage create longterm-backup --size 2000 --tier Standard
```

## Common Use Cases

### Shared Development Environment

Create shared storage for a team working on the same codebase:

```bash
# 1. Create shared storage
azlin storage create team-code --size 200 --tier Premium

# 2. Mount on all dev VMs
azlin storage mount vm team-code --vm dev-vm-1
azlin storage mount vm team-code --vm dev-vm-2
azlin storage mount vm team-code --vm dev-vm-3

# Now all VMs share the same /home directory
```

### Persistent Project Data

Create storage that persists across VM recreations:

```bash
# Create project storage
azlin storage create ml-project --size 500 --tier Premium

# Clone VM with shared storage
azlin clone ml-base --name ml-worker-1
azlin storage mount vm ml-project --vm ml-worker-1

# Data persists even if VM is deleted
```

### Cost-Optimized Backup Storage

```bash
# Large, infrequent-access storage
azlin storage create monthly-backups --size 5000 --tier Standard

# Mount temporarily for backups
azlin storage mount vm monthly-backups --vm backup-vm
# ... perform backup ...
azlin storage unmount --vm backup-vm
```

## Cost Estimation

Storage costs are based on provisioned size:

| Size | Premium Monthly | Standard Monthly |
|------|-----------------|------------------|
| 100 GB | $15.30 | $1.84 |
| 250 GB | $38.25 | $4.60 |
| 500 GB | $76.50 | $9.20 |
| 1 TB | $156.67 | $18.84 |
| 2 TB | $313.34 | $37.68 |

**Note**: Costs are estimates and may vary by region. Actual costs depend on provisioned capacity, not used capacity.

## Troubleshooting

### Storage Name Already Exists

**Error**: "Storage account name 'myteam' is already taken"

**Solution**: Storage names must be globally unique. Try adding a suffix:
```bash
azlin storage create myteam-dev-2025 --size 100 --tier Premium
```

### Invalid Storage Name

**Error**: "Storage name must be 3-24 chars, lowercase and numbers only"

**Solution**: Use only lowercase letters and numbers:
```bash
# Bad: MyTeam-Shared, my_team
# Good: myteamshared, myteam2025
azlin storage create myteamshared --size 100 --tier Premium
```

### Region Not Supported

**Error**: "NFS storage not available in region"

**Solution**: Use a supported region:
```bash
azlin storage create mystorage --size 100 --tier Premium --region eastus
```

### Quota Exceeded

**Error**: "Storage account quota exceeded"

**Solution**: Request quota increase or delete unused storage accounts:
```bash
# List existing storage
azlin storage list

# Delete unused storage
azlin storage delete old-storage
```

## Technical Details

### NFS Configuration

- **Protocol**: NFS v4.1
- **Network**: VNet-integrated (no public access)
- **Security**: Azure AD authentication
- **Encryption**: Data encrypted at rest and in transit
- **Redundancy**: Locally redundant storage (LRS)

### Performance Characteristics

**Premium Tier:**
- IOPS: Up to 100,000
- Throughput: Up to 10 GB/s
- Latency: Single-digit milliseconds

**Standard Tier:**
- IOPS: Up to 20,000
- Throughput: Up to 300 MB/s
- Latency: 10-20 milliseconds

### Storage Account Naming

Azure enforces strict naming rules:
- Length: 3-24 characters
- Characters: Lowercase letters (a-z) and numbers (0-9)
- Must be globally unique across ALL Azure storage accounts
- Cannot contain: Uppercase, hyphens, underscores, special characters

**Good names:**
- `myteam2025` (team with year)
- `projxdev` (project abbreviation)
- `ai4research` (descriptive)

**Bad names:**
- `MyTeam` (uppercase)
- `my-team` (hyphen)
- `my_team` (underscore)
- `m` (too short)

## Related Commands

- [azlin storage list](list.md) - List all storage accounts
- [azlin storage status](status.md) - Check storage usage and connected VMs
- [azlin storage mount](mount.md) - Mount storage on VMs
- [azlin storage unmount](unmount.md) - Unmount storage from VMs
- [azlin storage delete](delete.md) - Delete storage account

## See Also

- [Storage Overview](../../storage/index.md) - Understanding azlin storage architecture
- [Shared Home Directories](../../storage/shared-home.md) - Setting up team workspaces
- [Storage Best Practices](../../storage/mounting.md) - Optimization tips
