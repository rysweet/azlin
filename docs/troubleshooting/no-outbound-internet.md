# Troubleshooting: VM Has No Outbound Internet

Diagnosis and resolution for private VMs that you can connect to but that cannot
reach the internet.

## Symptoms

The VM is running and `azlin connect` works, but on the VM:

- `sudo apt-get update` hangs, then fails with `Could not connect` or
  `Connection timed out`
- `curl https://example.com` hangs until timeout
- `az`, `gh`, `node`, `go`, and `rustup` are missing even though cloud-init
  reported completion
- `git clone` from GitHub hangs

If azlin created the VM, it will normally have told you already — a banner on
stderr, then the verdict on stdout:

```
⚠ VM 'my-vm' has NO outbound internet. It is reachable, but every apt/curl/wget on it will fail and the cloud-init toolchain install (az, gh, node, go, rust) is incomplete.
  Azure Bastion is inbound-only and does not provide egress. Check that a NAT gateway is attached to the 'default' subnet of 'azlin-bastion-centralus-vnet':
    az network vnet subnet show --resource-group <rg> --vnet-name azlin-bastion-centralus-vnet --name default --query natGateway
  Then re-run `azlin new` (NAT provisioning is idempotent), or delete and recreate this VM once egress is in place.
VM 'my-vm' created — DEGRADED: no outbound internet access.
```

## Quick Diagnosis

```bash
# 1. Does the VM have egress at all?
azlin connect my-vm -- curl -fsI -m 10 https://packages.microsoft.com

# 2. Does the VM's subnet have a NAT gateway?
az network vnet subnet show \
  --resource-group <rg> \
  --vnet-name azlin-bastion-<region>-vnet \
  --name default \
  --query natGateway.id -o tsv
```

Empty output from the second command is the answer in almost every case: no NAT
gateway, therefore no egress.

## The Root Cause: Bastion Is Not Egress

Azure Bastion gives you a way *in* to a VM with no public IP. It gives the VM no
way *out*. These are opposite directions, and a private VM can have one without
the other:

| You have | You can | You cannot |
|----------|---------|------------|
| Bastion only | SSH in with `azlin connect` | `apt`, `curl`, `git clone` from the VM |
| NAT gateway only | Reach the internet from the VM | SSH in without a public IP |
| Both | Both | — |

A VM in this state passes every reachability check while being unable to install
anything, which is why the failure used to go unnoticed until someone tried to
use the toolchain.

## Fixes

### No NAT Gateway on the Subnet

**Symptom:** `natGateway.id` query above returns nothing.

**Cause:** The region's VM subnet was never given egress. This is common in
regions where bastion infrastructure was created before azlin provisioned NAT
gateways, or created by hand.

**Fix:** create and attach one. No VM restart or recreation is needed: **new**
outbound connections from existing VMs start using the gateway within seconds of
the attach completing. Connections already established keep their old path and
are not migrated, so a hung `apt-get update` started before the attach will stay
hung — interrupt it and re-run.

```bash
REGION=centralus
RG=<your-resource-group>

az network public-ip create \
  --resource-group $RG --name azlin-natgw-${REGION}-ip-tagged \
  --location $REGION --sku Standard --allocation-method Static \
  --zone 1 2 3 --ip-tags FirstPartyUsage=/ATEVETNonProd --output none

az network nat gateway create \
  --resource-group $RG --name azlin-natgw-${REGION} \
  --location $REGION --sku Standard --idle-timeout 10 \
  --public-ip-addresses azlin-natgw-${REGION}-ip-tagged --output none

az network vnet subnet update \
  --resource-group $RG --vnet-name azlin-bastion-${REGION}-vnet \
  --name default --nat-gateway azlin-natgw-${REGION} --output none
```

Full walkthrough: [Set Up a NAT Gateway](../how-to/setup-nat-gateway.md).

### The Toolchain Is Missing After Egress Is Restored

**Symptom:** Egress works now, but `az`, `gh`, `node`, `go`, or `rustup` are
still absent.

**Cause:** cloud-init ran once, during the window when the VM had no egress.
Restoring egress does not re-run it.

**Fix:** recreate the VM. It is faster and more reliable than repairing a
half-installed toolchain:

```bash
azlin kill my-vm
azlin new --name my-vm --region centralus
```

The pre-check now finds the NAT gateway you attached and creates nothing.

### The NAT Gateway Was Attached to the Wrong Subnet

**Symptom:** A gateway exists, but the subnet query still returns nothing.

**Cause:** It was attached to `AzureBastionSubnet` instead of `default`. Azure
normally rejects this, but a gateway can also simply be attached to a subnet in
a different VNet.

**Fix:** check what it is attached to, then attach it to `default`:

```bash
az network nat gateway show \
  --resource-group $RG --name azlin-natgw-${REGION} \
  --query "subnets[].id" -o tsv

az network vnet subnet update \
  --resource-group $RG --vnet-name azlin-bastion-${REGION}-vnet \
  --name default --nat-gateway azlin-natgw-${REGION} --output none
```

### Egress Worked, Then Stopped Under Load

**Symptom:** Outbound connections from a fleet of VMs start hanging
intermittently. Small numbers of VMs are fine.

**Cause:** SNAT port exhaustion. One public IP provides 64,512 ports, and each
is held for the 10-minute idle timeout after its connection closes. Exhaustion
looks identical to having no egress.

**Fix:** add a second public IP to the gateway rather than lowering the idle
timeout — see
[Add Capacity to an Existing Gateway](../how-to/setup-nat-gateway.md#add-capacity-to-an-existing-gateway).

### The NAT Public IP Disappeared

**Symptom:** Egress stopped working for every private VM in a region, and
`az network nat gateway show` reports no public IP addresses.

**Cause:** The address was deleted as an apparent orphan. A NAT gateway's SNAT
address reports `ipConfiguration: null`, which older cleanup logic read as
"unassociated".

**Fix:** recreate and reattach the address using Step 1 and Step 2 of
[Set Up a NAT Gateway](../how-to/setup-nat-gateway.md). Current versions of
`azlin cleanup` and of the teardown used by `azlin kill` / `azlin destroy` /
`azlin delete` exclude NAT-attached addresses, so this will not recur. Never add
an `azlin-session` resource tag to the address — that would make it a deliberate
teardown candidate.

### The Gateway Query Is Empty but Egress Works

**Symptom:** `natGateway.id` returns nothing, yet
`curl -fsI https://packages.microsoft.com` on the VM succeeds. `azlin new` still
prompts you to create a gateway.

**Cause:** Azure **default outbound access** — the implicit, Azure-managed
outbound path given to VMs with no public IP and no NAT gateway. Microsoft
retired it for VNets created on or after 30 September 2025, but VNets created
before that date keep it. azlin's pre-check is structural: it asks whether a
gateway is attached, not whether packets leave. For these older VNets the honest
answer to both questions differs.

**Fix:** nothing is broken. Decide deliberately:

- **Keep using it.** Choose **Abort** at the prompt, then re-run with `--public`
  or accept that the prompt appears each time. The path works, but its SNAT
  address is Azure-assigned, non-static, and unannounced, so a destination that
  allowlists your egress IP can break without warning.
- **Provision the gateway anyway.** Roughly $36/month per region — ~$32 for the
  gateway plus ~$3.65 for its Standard public IP, before data-processing
  charges — buys a static,
  known SNAT address and removes dependence on a path Microsoft has retired for
  new VNets. This is the recommended end state.

Check which case you are in — a VNet created after the retirement date has no
default outbound access, so an empty gateway query there really does mean no
egress:

```bash
az network vnet show \
  --resource-group $RG --name azlin-bastion-${REGION}-vnet \
  --query "{name:name, defaultOutbound:defaultOutboundAccess}" -o json
```

### Provisioning Fails with `AuthorizationFailed`

**Symptom:** the abort text naming the three manual `az` commands, with an `az`
error underneath it that ends in the permissions hint:

```
Error: Aborted: the VM subnet in centralus has no NAT gateway, so a private VM created there would have no outbound internet.
...
Caused by:
    Failed to create NAT gateway 'azlin-natgw-centralus' in centralus: ... AuthorizationFailed ...
      This is a permissions failure, not a missing resource. Provisioning egress requires the 'Network Contributor' role (or equivalent write access to Microsoft.Network) on the resource group.
```

The same hint is appended when the *subnet read* is the step that is denied.

**Cause:** Your identity cannot create network resources in the resource group.

**Fix:** you need `Network Contributor` (or equivalent) on the resource group.
Verify with:

```bash
az role assignment list \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --resource-group $RG -o table
```

If you cannot be granted the role, have someone with it create the gateway
manually, or use `azlin new --public` to give the VM its own public IP, which
provides egress independently.

### `azlin new` Aborts: "Could not determine whether the VM subnet ... has outbound internet"

**Symptom:**

```
Error: Could not determine whether the VM subnet in centralus has outbound internet. Refusing to create a private VM that may silently have no egress. Re-run with --public to give this VM its own public IP instead.

Caused by:
    `az network vnet subnet show` failed twice for subnet 'default' of VNet 'azlin-bastion-centralus-vnet' in centralus:
      first attempt:  <sanitized az error>
      second attempt: <sanitized az error>
```

**Cause:** `az network vnet subnet show` failed twice — azlin retries the read
once — because of a transient ARM or CLI error, an expired login, a missing
permission, or a VNet that has no subnet named `default`.

**Fix:** azlin deliberately refuses to guess here, because provisioning would
*replace* whatever gateway the subnet already has. Read the subnet yourself:

```bash
az account show -o none || az login
az network vnet subnet show \
  --resource-group $RG --vnet-name azlin-bastion-${REGION}-vnet \
  --name default --query natGateway.id -o tsv
```

- Command succeeds and prints an ID → the subnet has egress; re-run `azlin new`.
- Command succeeds and prints nothing → no gateway; re-run `azlin new` and
  accept the prompt.
- Subnet `default` does not exist → the VNet was not built by azlin. Create the
  subnet, or use `azlin new --public`.

### `azlin new` Fails with 409 / `AnotherOperationInProgress`

**Symptom:** A pool or fleet creation fails while attaching the gateway.

**Cause:** Two `azlin new` runs raced to update the same subnet. (Within one
`azlin new` the check runs once, before the VM loop, so a single run cannot race
itself.)

**Fix:** azlin already handles this. On an attach error containing
`AnotherOperationInProgress` or `Conflict` it prints

```
  Attach conflicted with a concurrent operation; re-checking subnet...
```

and re-reads the subnet; if the other run won the race it prints

```
  ✓ Subnet already attached to NAT gateway 'azlin-natgw-centralus' by a concurrent run
```

and continues. If the re-check still shows no gateway, the original error is
raised — simply re-run the command, by which point the subnet is normally
attached and the pre-check is a no-op.

## Confirming the Fix

```bash
azlin connect my-vm -- curl -fsI -m 10 https://packages.microsoft.com
```

Any `HTTP/... 200` status line means egress is working. This is the same probe
azlin runs after creating a private VM.

## See Also

- [NAT Gateway Egress for Private VMs](../features/nat-gateway-egress.md)
- [Set Up a NAT Gateway](../how-to/setup-nat-gateway.md)
- [NAT Gateway Provisioning Reference](../reference/nat-gateway-provisioning.md)
- [Troubleshoot Connection Issues](../how-to/troubleshoot-connection-issues.md) — for inbound problems
