# Bastion Pre-Check for Private VMs

Automatically verifies that Azure Bastion infrastructure exists before creating
private (bastion-routed) VMs, and offers to create it if missing.

## What is Bastion Pre-Check?

When you run `azlin new` without `--public` or `--no-bastion`, azlin defaults to
creating a private VM routed through Azure Bastion. Before creating the VM, azlin
now checks that the required bastion infrastructure exists in the target region:

1. VNet `azlin-bastion-{region}-vnet` exists
2. `AzureBastionSubnet` exists within that VNet
3. A bastion host `azlin-bastion-{region}` is provisioned

If any component is missing, azlin prompts you to create it, switch to a public
IP, or abort — so you never end up with a private VM you can't SSH into.

## Why Would I Use It?

This feature activates automatically. You don't need to opt in.

### Problem: Unreachable Private VM

Previously, running `azlin new` in a region without bastion infrastructure would
create a VM with a private IP and no way to connect:

```bash
azlin new --name my-vm --region eastus2 --size xl
# VM created with private IP 10.0.0.4
# But no bastion exists in eastus2 → cannot SSH!
```

### Solution: Pre-Check and Auto-Create

Now, azlin detects the missing infrastructure and offers to create it:

```
$ azlin new --name my-vm --region eastus2 --size xl

⚠ No Azure Bastion found in eastus2. A bastion is required to SSH into private VMs.

What would you like to do?
> Create bastion now (takes ~5-10 min)
  Switch to public IP
  Abort

Creating bastion infrastructure in eastus2...
  ✓ VNet azlin-bastion-eastus2-vnet (10.0.0.0/16)
  ✓ Subnet default (10.0.0.0/24)
  ✓ Subnet AzureBastionSubnet (10.0.1.0/26)
  ✓ Public IP azlin-bastion-eastus2-pip
  ✓ Bastion azlin-bastion-eastus2 (Standard SKU, tunneling enabled)
  ⏳ Waiting for bastion provisioning... done (6m 12s)

Creating VM my-vm in eastus2...
```

## Usage

### Interactive Mode (default)

```bash
# Bastion check happens automatically for private VMs
azlin new --name my-vm --region westus3
```

If bastion is missing, you see a 3-option prompt:

| Option | What happens |
|--------|-------------|
| **Create bastion now** | Creates VNet, subnet, public IP, and bastion host. Continues with private VM after provisioning completes. |
| **Switch to public IP** | Skips bastion creation. Creates VM with a public IP instead. |
| **Abort** | Cancels VM creation entirely. |

### Non-Interactive / CI Mode

When stdin is not a TTY (e.g., piped input, CI pipelines), azlin auto-selects
"Create bastion now" with a warning:

```bash
echo "" | azlin new --name ci-vm --region eastus2
# stderr: WARNING: No bastion in eastus2. Auto-creating bastion infrastructure (non-interactive mode).
```

> **CI consideration:** Auto-creating bastion infrastructure in non-interactive mode
> provisions resources that cost ~$100+/month and take 5–10 minutes. For CI pipelines
> where bastion is not needed, use `--public` or `--no-bastion` to skip the check.
> Pre-provisioning bastion in your target regions before running CI is recommended.

### With `--yes` Flag

The `--yes` flag skips all confirmation prompts (including auth forwarding).
For bastion pre-check, it auto-selects "Create bastion now" without prompting:

```bash
azlin new --name my-vm --region eastus2 --yes
# Bastion created automatically, no prompt shown
```

> **Note:** `--yes` also affects other prompts like auth forwarding acceptance.

### With `--no-bastion` or `--public`

These flags opt into a public IP, bypassing the bastion check entirely:

```bash
# Both skip the bastion pre-check
azlin new --name my-vm --region eastus2 --no-bastion
azlin new --name my-vm --region eastus2 --public
```

## What Gets Created

When bastion infrastructure is missing and you choose to create it, azlin
provisions these Azure resources in the target region:

| Resource | Name | Details |
|----------|------|---------|
| Virtual Network | `azlin-bastion-{region}-vnet` | Address space `10.0.0.0/16` |
| Default Subnet | `default` | Address prefix `10.0.0.0/24` |
| Bastion Subnet | `AzureBastionSubnet` | Address prefix `10.0.1.0/26` |
| Public IP | `azlin-bastion-{region}-pip` | Standard SKU, Static allocation |
| Bastion Host | `azlin-bastion-{region}` | Standard SKU, tunneling enabled |

Resources are created in the same resource group used for VM provisioning.
These follow the same naming convention used by `azlin` throughout the codebase.

### Idempotent Creation

The pre-check is idempotent. If some resources already exist (e.g., VNet exists
but bastion host doesn't), only the missing resources are created:

```
$ azlin new --name my-vm --region eastus2

⚠ No Azure Bastion found in eastus2. A bastion is required to SSH into private VMs.

> Create bastion now

Creating bastion infrastructure in eastus2...
  ✓ VNet azlin-bastion-eastus2-vnet already exists
  ✓ Subnet AzureBastionSubnet already exists
  ✓ Public IP azlin-bastion-eastus2-pip (created)
  ✓ Bastion azlin-bastion-eastus2 (created)
```

### Partial Failure

If creation fails partway through (e.g., quota exceeded for the public IP),
azlin reports the error and exits. Already-created resources remain in place.
Re-running `azlin new` will skip the resources that already exist:

```
$ azlin new --name my-vm --region eastus2

Creating bastion infrastructure in eastus2...
  ✓ VNet azlin-bastion-eastus2-vnet (created)
  ✓ Subnet AzureBastionSubnet (created)
  ✗ Public IP creation failed: quota exceeded for Standard public IPs in eastus2

Error: Failed to create bastion infrastructure. Fix the issue and retry.
Existing resources (VNet, subnet) will be reused on next attempt.
```

## Timing

Bastion host provisioning typically takes 5–10 minutes. During this time, azlin
displays a spinner with elapsed time. VM creation begins only after the bastion
is fully provisioned.

## Interaction with Other Features

| Feature | Interaction |
|---------|-------------|
| `--pool N` | Bastion check runs once before the VM creation loop, not per-VM |
| `--no-nfs` | No interaction — NFS and bastion are independent |
| `azlin kill` | Does not remove bastion infrastructure (shared across VMs) |
| `azlin connect` | Uses the bastion created by pre-check for SSH tunneling |
| `azlin tunnel` | Uses the bastion created by pre-check for port forwarding |

## Troubleshooting

### "Permission denied" during bastion creation

You need `Contributor` role (or equivalent) on the resource group to create
VNet, public IP, and bastion resources. Check your Azure RBAC:

```bash
az role assignment list --assignee $(az ad signed-in-user show --query id -o tsv) \
  --scope /subscriptions/$(az account show --query id -o tsv) -o table
```

### Bastion creation times out

Azure Bastion provisioning can take up to 15 minutes in some regions. If it
appears stuck, check the Azure portal for provisioning status. You can also
verify with:

```bash
az network bastion show \
  --name azlin-bastion-eastus2 \
  --resource-group <your-rg> \
  --query provisioningState -o tsv
```

### "VNet address space conflict"

If `10.0.0.0/16` conflicts with an existing VNet in the resource group, creation
will fail. This can happen if bastion infrastructure was partially created by a
previous run, or if you have other VNets using the same address space. Inspect
existing VNets to identify conflicts:

```bash
az network vnet list --resource-group <your-rg> \
  --query "[].{name:name, addressSpace:addressSpace.addressPrefixes}" -o table
```

### Azure location casing mismatch

Azure may return region names with inconsistent casing (e.g., `eastus2` vs
`EastUS2`). Azlin normalizes locations to lowercase for comparison, but if you
see unexpected "no bastion found" messages after manual creation, verify the
bastion's location matches your target region (case-insensitively).

## See Also

- [How to Use SSH Tunnels](../how-to/use-tunnels.md)
- [Troubleshoot Connection Issues](../how-to/troubleshoot-connection-issues.md)
- [Troubleshoot Tunnel Issues](../troubleshooting/tunnel-issues.md)
- [Bastion Security Requirements](../BASTION_SECURITY_REQUIREMENTS.md)
