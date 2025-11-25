# Bastion Support Documentation for `azlin cp`

This document contains the NEW sections to add to `/docs-site/commands/util/cp.md` for Issue #415.
This is RETCON documentation - written as if the feature is already fully implemented and working.

---

## Azure Bastion Support (AUTOMATIC)

`azlin cp` automatically detects and uses Azure Bastion for VMs without public IP addresses, providing the same seamless experience as `azlin connect`. No configuration or special flags required.

### How It Works

When you copy files to/from a VM, `azlin cp`:

1. **Checks for public IP** - If VM has public IP, uses direct connection (fastest)
2. **Auto-detects Bastion** - If no public IP, searches for Azure Bastion in resource group
3. **Creates secure tunnel** - Automatically establishes tunnel through Bastion (localhost:50000-60000)
4. **Transfers files** - Routes rsync through tunnel transparently
5. **Cleans up** - Automatically closes tunnel when transfer completes

**No user action required** - Works identically to VMs with public IPs.

### Examples

#### Copy to Bastion-Only VM

```bash
# VM has no public IP, but Bastion exists in resource group
azlin cp dataset.tar.gz secure-vm:~/data/
```

**Output:**
```
VM secure-vm has no public IP, checking for Bastion...
✓ Found Bastion: azlin-bastion-eastus
Creating Bastion tunnel...
✓ Bastion tunnel established: azlin-bastion-eastus -> 127.0.0.1:52341

Copying to secure-vm (via Bastion)...
  Source: /Users/ryan/dataset.tar.gz
  Destination: /home/azureuser/data/dataset.tar.gz

Transferring...
dataset.tar.gz: 100% [===================] 2.1 MB/s

✓ Transfer complete!
  Files: 1
  Size: 450 MB
  Time: 3m 35s
  Connection: Bastion (azlin-bastion-eastus)

Cleaning up Bastion tunnel...
✓ Tunnel closed
```

####

 Download from Bastion-Only VM

```bash
# Download trained model from private VM
azlin cp ml-vm:~/models/trained-model.pkl ./models/
```

**Output:**
```
VM ml-vm has no public IP, checking for Bastion...
✓ Found Bastion: azlin-bastion-westus2
Creating Bastion tunnel...
✓ Bastion tunnel established: azlin-bastion-westus2 -> 127.0.0.1:51234

Copying from ml-vm (via Bastion)...
  Source: /home/azureuser/models/trained-model.pkl
  Destination: /Users/ryan/models/trained-model.pkl

Transferring...
trained-model.pkl: 100% [=================] 1.8 MB/s

✓ Transfer complete!
  Files: 1
  Size: 125 MB
  Time: 1m 10s
  Connection: Bastion (azlin-bastion-westus2)

Cleaning up Bastion tunnel...
✓ Tunnel closed
```

#### Copy Between Two Bastion-Only VMs

```bash
# Copy data from one secure VM to another
azlin cp source-vm:~/data/ target-vm:~/backup/
```

**Output:**
```
VM source-vm has no public IP, checking for Bastion...
✓ Found Bastion: azlin-bastion-eastus
Creating Bastion tunnel for source-vm...
✓ Bastion tunnel established: azlin-bastion-eastus -> 127.0.0.1:50123

VM target-vm has no public IP, checking for Bastion...
✓ Found Bastion: azlin-bastion-eastus (reusing)
Creating Bastion tunnel for target-vm...
✓ Bastion tunnel established: azlin-bastion-eastus -> 127.0.0.1:50124

Copying from source-vm to target-vm (both via Bastion)...
  Source: source-vm:/home/azureuser/data/
  Destination: target-vm:/home/azureuser/backup/data/

Scanning directory...
  Files found: 1,247
  Total size: 5.3 GB

Transferring...
████████████████████████████████ 100%

✓ Transfer complete!
  Files: 1,247
  Size: 5.3 GB
  Time: 45m 12s
  Speed: 2.0 MB/s
  Connection: Both via Bastion

Cleaning up Bastion tunnels...
✓ All tunnels closed
```

### Bastion Auto-Detection

`azlin cp` searches for Azure Bastion in this order:

1. **Same region as VM** - Preferred for lowest latency
2. **Any region in resource group** - Falls back if needed (logs warning)
3. **No Bastion found** - Clear error with guidance

**Example with region mismatch:**
```bash
azlin cp file.txt vm-westus2:~/
```

**Output:**
```
VM vm-westus2 has no public IP, checking for Bastion...
⚠ Found Bastion in eastus (VM in westus2) - may have higher latency
✓ Using Bastion: azlin-bastion-eastus
Creating Bastion tunnel...
✓ Bastion tunnel established

[... transfer proceeds normally ...]
```

### Performance Comparison

| Connection Type | Typical Speed | Use Case |
|----------------|---------------|----------|
| **Direct (public IP)** | 10-50 MB/s | Development VMs, temporary instances |
| **Bastion tunnel** | 2-20 MB/s | Production VMs, compliance requirements |

**Notes:**
- Bastion adds 10-30% overhead vs direct connection
- Regional Bastion (same region as VM) performs best
- Cross-region Bastion adds additional latency
- Security benefits often outweigh performance impact

### Security Benefits

Using Bastion for file transfers provides:

- **No public IP exposure** - VMs completely isolated from internet
- **Centralized access control** - All access through Azure Bastion
- **Audit logging** - Azure logs all Bastion connections
- **Just-in-time access** - Can be combined with JIT VM access
- **No VPN required** - Works from any location with Azure CLI

### Common Workflows with Bastion

#### Deploy to Zero-Trust Environment

```bash
# All VMs in production have no public IPs
azlin cp -r ./app/ prod-api-1:~/app/
azlin cp -r ./app/ prod-api-2:~/app/
azlin cp -r ./app/ prod-api-3:~/app/

# Bastion automatically used for all transfers
# No configuration changes needed
```

#### Download Sensitive Data Securely

```bash
# Download PII data from compliant VM
azlin cp secure-db-vm:~/exports/customer-data-$(date +%Y%m%d).csv ./backups/

# Transfer automatically routed through Bastion
# No public internet exposure of data
```

#### Automated Deployment Scripts

```bash
#!/bin/bash
# deploy.sh - Works identically for public and private VMs

# Build
npm run build

# Deploy to all VMs (mix of public and private)
for vm in $(azlin list --tag app=web --format json | jq -r '.[].name'); do
  echo "Deploying to $vm..."
  azlin cp -r ./dist/ $vm:~/app/dist/

  # azlin cp auto-detects: uses public IP if available, Bastion if not
done

echo "✓ Deployment complete"
```

### Troubleshooting

#### No Bastion Found

**Problem:** "VM has no public IP and no Bastion found"

**Solution:**
```bash
# Check if Bastion exists in resource group
az network bastion list \
  --resource-group your-resource-group \
  --query "[].{name:name, location:location, state:provisioningState}" \
  --output table

# If no Bastion exists, create one:
# See: https://rysweet.github.io/azlin/bastion/setup/

# Or add public IP to VM temporarily:
az vm update \
  --resource-group your-resource-group \
  --name your-vm \
  --set networkProfile.networkInterfaces[0].ipConfigurations[0].publicIPAddress.id=/subscriptions/.../publicIPAddresses/your-ip
```

#### Bastion Timeout

**Problem:** "Bastion tunnel creation timed out (30s)"

**Solution:**
```bash
# Check Bastion provisioning state
az network bastion show \
  --resource-group your-resource-group \
  --name your-bastion \
  --query "provisioningState"

# If "Failed", delete and recreate Bastion
# If "Updating", wait for completion

# Check Azure service health
az rest --method get --url https://management.azure.com/subscriptions/YOUR_SUB/providers/Microsoft.ResourceHealth/availabilityStatuses
```

#### Slow Transfer via Bastion

**Problem:** Transfer much slower than expected

**Solutions:**
```bash
# 1. Check Bastion and VM are in same region
az vm show --resource-group rg --name vm --query location
az network bastion show --resource-group rg --name bastion --query location

# 2. Use compression for large files
gzip large-file.dat
azlin cp large-file.dat.gz vm:~/
# Decompress on VM
azlin connect vm "gunzip ~/large-file.dat.gz"

# 3. Use archives instead of many small files
tar -czf project.tar.gz ./project/
azlin cp project.tar.gz vm:~/
azlin connect vm "tar -xzf ~/project.tar.gz"

# 4. Consider upgrading Bastion SKU
az network bastion update \
  --resource-group rg \
  --name bastion \
  --sku Standard  # Supports more concurrent connections
```

#### Port Already in Use

**Problem:** "Failed to bind Bastion tunnel port"

**Solution:**
```bash
# azlin automatically finds available ports (50000-60000)
# This error usually means all ports in range are in use

# Check active tunnels
lsof -i :50000-60000

# Clean up stale tunnels
ps aux | grep "az network bastion tunnel"
kill <PID>  # For any stale tunnel processes

# Retry transfer (azlin will use different port)
azlin cp file.txt vm:~/
```

## Comparison: Public IP vs Bastion

| Feature | Public IP VM | Bastion-Only VM |
|---------|-------------|-----------------|
| **Setup** | `azlin cp vm:~/file` | `azlin cp vm:~/file` |
| **User experience** | Identical | Identical |
| **Auto-detection** | ✓ | ✓ |
| **Speed** | 10-50 MB/s | 2-20 MB/s |
| **Security** | Exposed to internet | Fully isolated |
| **Cost** | Public IP: ~$3/month | Bastion: ~$140/month (shared) |
| **Best for** | Development, temporary | Production, compliance |

**Key Point:** From the user perspective, `azlin cp` works identically regardless of VM network configuration. The tool handles routing automatically.

## Migration Guide: Adding Bastion to Existing Setup

If you're transitioning VMs from public IPs to Bastion:

### 1. Create Bastion (one-time setup)

```bash
# See: https://rysweet.github.io/azlin/bastion/setup/
azlin bastion create --resource-group your-rg --location eastus
```

### 2. Test file transfer with Bastion

```bash
# VM still has public IP at this point
azlin cp test.txt your-vm:~/

# Verify direct connection works
# Output shows: "Copying to your-vm (20.12.34.56)..."
```

### 3. Remove public IP from VM

```bash
# Remove public IP
az vm update \
  --resource-group your-rg \
  --name your-vm \
  --remove networkProfile.networkInterfaces[0].ipConfigurations[0].publicIPAddress

# Deallocate and restart VM for changes to take effect
azlin stop your-vm
azlin start your-vm
```

### 4. Verify Bastion file transfer

```bash
# Same command as before
azlin cp test.txt your-vm:~/

# Output now shows:
# "VM your-vm has no public IP, checking for Bastion..."
# "✓ Found Bastion: azlin-bastion-eastus"
# "Copying to your-vm (via Bastion)..."
```

### 5. Update automation scripts (no changes needed!)

```bash
# Scripts work unchanged
# azlin cp automatically adapts to new network configuration
./deploy.sh  # Works with both public and private VMs
```

## Advanced: Bastion Configuration

### Bastion SKUs

`azlin cp` works with all Azure Bastion SKUs:

| SKU | Max Tunnels | Use Case |
|-----|-------------|----------|
| **Basic** | 25 | Small teams, dev/test |
| **Standard** | 50 | Production, multiple teams |

### Resource Group Best Practices

**Option 1: One Bastion per Resource Group (Recommended)**
```bash
Resource Group: prod-eastus-rg
├── azlin-bastion-eastus (shared)
├── prod-api-1 (private)
├── prod-api-2 (private)
└── prod-db-1 (private)

# All VMs automatically use shared Bastion
```

**Option 2: Regional Bastions**
```bash
Resource Group: prod-multi-region-rg
├── azlin-bastion-eastus
├── azlin-bastion-westus2
├── prod-api-east-1 (private, uses eastus Bastion)
├── prod-api-east-2 (private, uses eastus Bastion)
├── prod-api-west-1 (private, uses westus2 Bastion)
└── prod-api-west-2 (private, uses westus2 Bastion)

# azlin cp automatically matches VM region to Bastion region
```

## Related Commands

- [`azlin connect`](../vm/connect.md) - SSH with Bastion support (uses same auto-detection)
- [`azlin bastion create`](../bastion/create.md) - Set up Azure Bastion
- [`azlin bastion status`](../bastion/status.md) - Check Bastion availability
- [`azlin storage mount`](../storage/mount.md) - Alternative for persistent file access

## See Also

- [Azure Bastion Overview](../../bastion/overview.md)
- [Bastion Setup Guide](../../bastion/setup.md)
- [Bastion Security Benefits](../../bastion/security.md)
- [Bastion Cost Analysis](../../bastion/cost.md)

---

*Feature added in azlin v0.3.3 (Issue #415)*
