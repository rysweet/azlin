# How to Set Up Bastion Infrastructure

Create Azure Bastion infrastructure in a new region so that `azlin new` can
provision private (bastion-routed) VMs there.

## Automatic Setup (Recommended)

Simply run `azlin new` targeting the region. If no bastion exists, azlin offers
to create one:

```bash
azlin new --name my-vm --region southcentralus
```

If bastion is missing, you'll be prompted:

```
⚠ No Azure Bastion found in southcentralus.
  A bastion is required to SSH into private VMs.

What would you like to do?
> Create bastion now (takes ~5-10 min)
  Switch to public IP
  Abort
```

Select "Create bastion now" and azlin handles the rest.

To skip the prompt:

```bash
azlin new --name my-vm --region southcentralus --yes
```

## Manual Setup

If you prefer to create bastion infrastructure manually (or need custom
configuration), use the Azure CLI directly:

### Step 1: Create VNet

> **Warning:** The default address space `10.0.0.0/16` may conflict with existing
> VNets in your resource group. Check with `az network vnet list -g $RG -o table`
> before proceeding, and adjust the prefix if needed.

```bash
REGION=southcentralus
RG=<your-resource-group>

az network vnet create \
  --resource-group $RG \
  --name azlin-bastion-${REGION}-vnet \
  --location $REGION \
  --address-prefix 10.0.0.0/16 \
  --subnet-name default \
  --subnet-prefix 10.0.0.0/24
```

### Step 2: Create Bastion Subnet

```bash
az network vnet subnet create \
  --resource-group $RG \
  --vnet-name azlin-bastion-${REGION}-vnet \
  --name AzureBastionSubnet \
  --address-prefix 10.0.1.0/26
```

### Step 3: Create Public IP

```bash
az network public-ip create \
  --resource-group $RG \
  --name azlin-bastion-${REGION}-pip \
  --location $REGION \
  --sku Standard \
  --allocation-method Static
```

### Step 4: Create Bastion Host

```bash
az network bastion create \
  --resource-group $RG \
  --name azlin-bastion-${REGION} \
  --location $REGION \
  --vnet-name azlin-bastion-${REGION}-vnet \
  --public-ip-address azlin-bastion-${REGION}-pip \
  --sku Standard \
  --enable-tunneling true
```

This takes 5–10 minutes. After completion, `azlin new` will detect the bastion
and create private VMs in that region without prompting.

## Verify Bastion Exists

```bash
az network bastion list --resource-group $RG --query "[].{name:name, location:location, sku:sku.name}" -o table
```

## See Also

- [Bastion Pre-Check for Private VMs](../features/bastion-pre-check.md)
- [How to Use SSH Tunnels](use-tunnels.md)
- [Troubleshoot Connection Issues](troubleshoot-connection-issues.md)
