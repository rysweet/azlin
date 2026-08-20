# How to Set Up a NAT Gateway

Give private (bastion-routed) VMs outbound internet access in a region, so that
`apt`, `curl`, and the cloud-init toolchain install can reach the internet.

Azure Bastion does **not** provide this. Bastion is inbound only: it lets you
reach a VM that has no public IP. Outbound traffic needs a NAT gateway attached
to the VM's subnet.

## Automatic Setup (Recommended)

Run `azlin new` targeting the region. If the VM subnet has no NAT gateway,
azlin offers to create one:

```bash
azlin new --name my-vm --region centralus
```

```
No NAT gateway found for the VM subnet in centralus. Private VMs there have no outbound internet (Azure Bastion is inbound-only).

How would you like to proceed?
> Create NAT gateway now (takes ~1-2 min, ~$36/mo per region)
  Switch to public IP instead
  Abort
```

Select "Create NAT gateway now". The ~$36/month is the NAT gateway (~$32) plus
its Standard public IP (~$3.65), per region, before data-processing charges.

To skip the prompt in scripts and CI:

```bash
azlin new --name my-vm --region centralus --yes
```

When stdin is not a TTY, azlin auto-creates the gateway and says so on stderr,
without waiting for an answer.

## Manual Setup

Create the resources with the Azure CLI if you need custom configuration, or if
your account cannot create network resources at VM-creation time. Use the same
names azlin uses, so azlin detects and reuses them.

```bash
REGION=centralus
RG=<your-resource-group>
IP_TAGS=FirstPartyUsage=/ATEVETNonProd   # must match your bastion_pip_ip_tags
```

### Step 1: Create the Public IP

```bash
az network public-ip create \
  --resource-group $RG \
  --name azlin-natgw-${REGION}-ip-tagged \
  --location $REGION \
  --sku Standard \
  --allocation-method Static \
  --zone 1 2 3 \
  --ip-tags $IP_TAGS \
  --output none
```

The `-ip-tagged` suffix is part of the name azlin looks for. The IP tag is
immutable after allocation — if your subscription requires a different tag,
set it now, not later.

Do **not** add `--tags`. Azure resource tags on this address make it a
teardown candidate.

### Step 2: Create the NAT Gateway

```bash
az network nat gateway create \
  --resource-group $RG \
  --name azlin-natgw-${REGION} \
  --location $REGION \
  --sku Standard \
  --idle-timeout 10 \
  --public-ip-addresses azlin-natgw-${REGION}-ip-tagged \
  --output none
```

The gateway is regional — it takes no `--zone`, even though its public IP is
zonal. This asymmetry is correct.

### Step 3: Attach It to the VM Subnet

`--nat-gateway` **replaces** the subnet's existing NAT gateway association
rather than adding to it. Check what is attached before running this against a
subnet you did not create:

```bash
az network vnet subnet show \
  --resource-group $RG --vnet-name azlin-bastion-${REGION}-vnet \
  --name default --query natGateway.id -o tsv
```

Empty output, or an ID naming the gateway you just created, means it is safe to
proceed:

```bash
az network vnet subnet update \
  --resource-group $RG \
  --vnet-name azlin-bastion-${REGION}-vnet \
  --name default \
  --nat-gateway azlin-natgw-${REGION} \
  --output none
```

> **Attach to `default`, never to `AzureBastionSubnet`.** `default` is where
> azlin places private VMs. Azure rejects a NAT gateway on `AzureBastionSubnet`,
> and attaching it there would not give any VM egress.

The VNet must already exist. If it does not, create the bastion infrastructure
first — see [Set Up Bastion Infrastructure](setup-bastion-infrastructure.md).

## Verify the Setup

Confirm the gateway is attached to the subnet:

```bash
az network vnet subnet show \
  --resource-group $RG \
  --vnet-name azlin-bastion-${REGION}-vnet \
  --name default \
  --query natGateway.id -o tsv
```

Expected output — a resource ID ending in your gateway name:

```
/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Network/natGateways/azlin-natgw-centralus
```

Empty output means no gateway is attached. For a VNet created on or after
30 September 2025 that also means no egress. Older VNets may still have Azure's
retired **default outbound access**, so an empty result there does not by itself
prove VMs are cut off — see
[The Gateway Query Is Empty but Egress Works](../troubleshooting/no-outbound-internet.md#the-gateway-query-is-empty-but-egress-works).

Confirm the public IP carries the required tag:

```bash
az network public-ip show \
  --resource-group $RG \
  --name azlin-natgw-${REGION}-ip-tagged \
  --query ipTags -o json
```

```json
[
  {
    "ipTagType": "FirstPartyUsage",
    "tag": "/ATEVETNonProd"
  }
]
```

Confirm a VM actually has egress:

```bash
azlin connect my-vm -- curl -fsI https://packages.microsoft.com
```

Any `HTTP/... 200` status line means egress works. A hang followed by a
timeout means it does not.

## Add Capacity to an Existing Gateway

One public IP provides 64,512 SNAT ports. If a large fleet exhausts them,
attach more addresses rather than lowering the idle timeout:

```bash
az network public-ip create \
  --resource-group $RG \
  --name azlin-natgw-${REGION}-ip-2 \
  --location $REGION \
  --sku Standard --allocation-method Static --zone 1 2 3 \
  --ip-tags $IP_TAGS --output none

az network nat gateway update \
  --resource-group $RG \
  --name azlin-natgw-${REGION} \
  --public-ip-addresses azlin-natgw-${REGION}-ip-tagged azlin-natgw-${REGION}-ip-2 \
  --output none
```

A NAT gateway supports up to 16 public IP addresses.

## Required Permissions

Creating and attaching a NAT gateway needs, on the resource group:

- `Microsoft.Network/publicIPAddresses/write` and `/join/action`
- `Microsoft.Network/natGateways/write` and `/join/action`
- `Microsoft.Network/virtualNetworks/subnets/write`

The built-in `Network Contributor` role covers all of these. Check your
assignments:

```bash
az role assignment list \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --resource-group $RG -o table
```

## See Also

- [NAT Gateway Egress for Private VMs](../features/nat-gateway-egress.md) — how azlin uses this
- [NAT Gateway Provisioning Reference](../reference/nat-gateway-provisioning.md) — exact commands azlin runs
- [Diagnose Missing Outbound Internet](../troubleshooting/no-outbound-internet.md)
- [Set Up Bastion Infrastructure](setup-bastion-infrastructure.md) — the inbound half
