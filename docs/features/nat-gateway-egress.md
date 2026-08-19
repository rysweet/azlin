# NAT Gateway Egress for Private VMs

Automatically verifies that the target subnet has outbound internet access
before creating a private (bastion-routed) VM, and provisions an Azure NAT
gateway if it does not.

## Azure Bastion Is Not Egress

Azure Bastion and a NAT gateway solve opposite problems, and confusing them is
the reason this feature exists:

| Direction | Provided by | Lets you |
|-----------|-------------|----------|
| **Inbound** | Azure Bastion | Reach a VM that has no public IP (`azlin connect`, `azlin tunnel`) |
| **Outbound** | NAT gateway | Let the VM reach the internet (`apt`, `curl`, `git clone`) |

A private VM behind a bastion with no NAT gateway is *reachable but isolated*.
You can SSH into it; it cannot download anything.

## What the Pre-Check Does

When you run `azlin new` without `--public` or `--no-bastion`, azlin creates a
private VM in the `default` subnet of `azlin-bastion-{region}-vnet`. Before
creating the VM, azlin reads that subnet and checks whether a NAT gateway is
attached to it.

If none is attached, azlin prompts you to create one, switch to a public IP, or
abort. Creation is never silent and never optional-by-default: azlin will not
create a private VM in a subnet it knows has no egress.

## Why This Exists

### Problem: A VM That Looks Healthy and Cannot Install Anything

Before this feature, creating a private VM in a region whose subnet had no NAT
gateway produced a VM that passed every check azlin performed:

```bash
azlin new --name my-vm --region centralus
# State: Running
# Cloud-init provisioning complete.
# VM 'my-vm' created successfully!
```

The VM was reachable through the bastion, so `azlin connect` worked. But every
outbound request from the VM failed, so the entire cloud-init toolchain install
had already collapsed silently — no `az`, no `gh`, no `node`, no `go`, no
`rustup`. The failure only surfaced later, on the VM, as an unexplained
`apt-get update` timeout.

### Solution: Check Egress Before Creating, Verify Egress After

Two independent mechanisms, at two points in time:

1. **Before the VM exists** — the subnet is inspected. Missing egress is a hard
   gate: azlin prompts, and on abort or failure it exits non-zero without
   creating anything.
2. **After the VM exists** — azlin runs one HTTP probe over the SSH session it
   already has. A VM that cannot reach the internet is reported as **degraded**,
   with its name and IP printed first so you can still reach and delete it.

## Usage

### Interactive Mode (default)

```bash
azlin new --name my-vm --region centralus
```

If the subnet has no NAT gateway:

```
No NAT gateway found for the VM subnet in centralus. Private VMs there have no outbound internet (Azure Bastion is inbound-only).

How would you like to proceed?
> Create NAT gateway now (takes ~1-2 min, ~$36/mo per region)
  Switch to public IP instead
  Abort

Creating NAT gateway public IP 'azlin-natgw-centralus-ip-tagged' (Standard, zones 1 2 3)...
  ✓ Public IP 'azlin-natgw-centralus-ip-tagged' ready
Creating NAT gateway 'azlin-natgw-centralus' (Standard SKU, 10 min idle timeout)...
  ✓ NAT gateway 'azlin-natgw-centralus' created
Attaching 'azlin-natgw-centralus' to subnet 'default' of 'azlin-bastion-centralus-vnet'...
  ✓ Attached to subnet 'default' of 'azlin-bastion-centralus-vnet'
  ✓ Outbound internet enabled for private VMs in centralus

Creating VM 'my-vm'...
```

The banner and every progress line are written to stderr; a spinner reading
`Provisioning NAT gateway in centralus...` runs alongside them and is cleared
when provisioning finishes.

| Option | What happens |
|--------|--------------|
| **Create NAT gateway now** | Creates the public IP and gateway, attaches the gateway to the `default` subnet, then continues with the private VM. |
| **Switch to public IP instead** | Skips NAT creation. The VM gets its own public IP, which provides egress on its own. |
| **Abort** | Cancels VM creation. No VM and no network resources are created. |

### Non-Interactive / CI Mode

When stdin is not a TTY, azlin auto-selects "Create NAT gateway now" and warns
on stderr:

```bash
echo "" | azlin new --name ci-vm --region centralus
# stderr: Warning: non-interactive session detected. Auto-creating a NAT gateway
#         in centralus so the VM has outbound internet. Use --public to give the
#         VM its own public IP instead.
```

This mirrors the bastion pre-check, which auto-creates a substantially more
expensive resource under the same conditions.

### With `--yes`

```bash
azlin new --name my-vm --region centralus --yes
# stderr: --yes flag set: auto-creating NAT gateway...
```

### With `--public` or `--no-bastion`

Both opt into a VM-attached public IP, which provides its own egress. The NAT
pre-check is skipped entirely:

```bash
azlin new --name my-vm --region centralus --public
azlin new --name my-vm --region centralus --no-bastion
```

Choosing **Switch to public IP instead** at the bastion prompt has the same
effect: the NAT pre-check re-reads the flag afterwards and does not run.

## What Gets Created

| Resource | Name | Details |
|----------|------|---------|
| Public IP | `azlin-natgw-{region}-ip-tagged` | Standard SKU, Static allocation, zones `1 2 3`, IP tag from `bastion_pip_ip_tags` |
| NAT Gateway | `azlin-natgw-{region}` | Standard SKU, 10-minute idle timeout, regional (no zone) |
| Subnet attachment | `default` subnet of `azlin-bastion-{region}-vnet` | The VM subnet — **never** `AzureBastionSubnet` |

Resources are created in the same resource group used for VM provisioning, and
are shared by every private VM in that region. A NAT gateway cannot be attached
to `AzureBastionSubnet`: Azure rejects it, and it would not help anyway, since
the bastion carries inbound traffic only.

The zonal public IP paired with a regional gateway is intentional and matches
the verified working configuration. Do not "harmonize" them.

### Idempotent

The check asks a single question: *does this subnet have egress?* If the subnet
read succeeds and reports any attached NAT gateway — including one you created
yourself under a different name — the subnet is already satisfied and azlin
creates nothing and touches nothing:

```
$ azlin new --name my-vm --region southcentralus
#   ✓ NAT gateway 'azlin-natgw-southcentralus' provides egress for southcentralus
```

(A re-run that reaches `ensure_nat_gateway` itself — for example after choosing
**Create NAT gateway now** on a subnet another run has just attached — reports
`  ✓ NAT gateway '<name>' already provides egress for <region>`.)

This guarantee holds only when azlin could actually read the subnet. See
[Detection Failure Is Not Absence](#detection-failure-is-not-absence) — a failed
read is never silently downgraded to "no gateway", because the last step of the
create plan *replaces* whatever gateway the subnet already had.

Resource names are fully determined by the region, and `az ... create` is
create-or-update, so a re-run after an interrupted attempt reuses the existing
public IP and gateway rather than allocating a second one. This matters: every
duplicate Standard public IP bills about $3.65/month forever.

### Creation Failure

If any step fails, azlin exits non-zero **before** creating a VM. The failing
`az` error is reported underneath the same abort text that a declined prompt
produces — the region, both resource names, and the three manual commands:

```
Error: Aborted: the VM subnet in centralus has no NAT gateway, so a private VM created there would have no outbound internet.
Azure Bastion is inbound-only: it lets you reach the VM, but it does not provide egress. Without a NAT gateway every apt/curl/wget on the VM fails and the cloud-init toolchain install collapses.

To provision egress manually:
  az network public-ip create --resource-group <rg> --name azlin-natgw-centralus-ip-tagged --location centralus --sku Standard --allocation-method Static --zone 1 2 3
  az network nat gateway create --resource-group <rg> --name azlin-natgw-centralus --location centralus --sku Standard --idle-timeout 10 --public-ip-addresses azlin-natgw-centralus-ip-tagged
  az network vnet subnet update --resource-group <rg> --vnet-name azlin-bastion-centralus-vnet --name default --nat-gateway azlin-natgw-centralus

Or re-run with --public to give this VM its own public IP instead.

Caused by:
    Failed to create NAT gateway 'azlin-natgw-centralus' in centralus: <sanitized az error>
```

Choosing **Abort** at the prompt produces the same text with no `Caused by:`
section.

### Detection Failure Is Not Absence

If the `az network vnet subnet show` call itself errors, times out, or returns
JSON azlin cannot parse, azlin does **not** treat that as "no gateway". It
retries the read once, and if the retry also fails it aborts non-zero without
creating anything:

```
Error: Could not determine whether the VM subnet in centralus has outbound internet. Refusing to create a private VM that may silently have no egress. Re-run with --public to give this VM its own public IP instead.

Caused by:
    `az network vnet subnet show` failed twice for subnet 'default' of VNet 'azlin-bastion-centralus-vnet' in centralus:
      first attempt:  <sanitized az error>
      second attempt: <sanitized az error>
```

Falling through to the create path on an unreadable subnet would be actively
destructive, not merely redundant. The final step of the create plan is
`az network vnet subnet update --nat-gateway azlin-natgw-<region>`, and that
command *replaces* any existing association. A single transient ARM read failure
against a subnet carrying a hand-made or corporate-named gateway would silently
repoint the whole subnet at a brand-new azlin gateway, orphan the old one, and
start billing a second gateway plus a second public IP — with no message saying
so. Aborting is strictly cheaper than that.

The same rule covers a manually built VNet with no `default` subnet: the read
fails, azlin says so by name, and no resource is created.

### You May Already Have Egress Without a NAT Gateway

The pre-check is purely structural: it asks whether a NAT gateway is attached to
the subnet, not whether packets actually leave it. Those are not the same
question for older VNets.

Azure historically gave VMs with no public IP and no NAT gateway an implicit
outbound path called **default outbound access**. Microsoft retired it for newly
created VNets on 30 September 2025, but VNets created before that date keep it.
If your `azlin-bastion-{region}-vnet` predates the retirement, its VMs already
reach the internet and azlin will still prompt you to spend roughly $36/month on
a gateway you do not strictly need.

Confirm before accepting the prompt. Choose **Abort**, then test an existing VM
in that subnet:

```bash
azlin connect existing-vm -- curl -fsI -m 10 https://packages.microsoft.com
```

If that returns an `HTTP/... 200` status line, the subnet has working egress
today and you can keep creating VMs with `--yes` suppressed. Two caveats before
you rely on it: default outbound access uses an Azure-assigned, unannounced,
non-static SNAT address that can change, and Microsoft's stated direction is that
it is a legacy path. A NAT gateway is still the durable answer — just an
informed purchase rather than a surprised one.

## Post-Provision Egress Verification

After a private VM is created and SSH is ready, azlin runs one probe over the
existing SSH session:

```bash
curl -fsI -m 10 https://packages.microsoft.com
```

The probe is a TLS `HEAD` request with full certificate validation. It sends no
VM data and transfers no body. It runs on **private VMs only** — a VM with its
own public IP has egress by construction, so the probe is skipped and the VM is
treated as reachable without an SSH round-trip.

| Probe result | VM reported as | Exit code |
|--------------|----------------|-----------|
| Reachable | Complete | 0 |
| Explicitly unreachable | **Degraded** | non-zero |
| Indeterminate (SSH transport failure) | Complete, with a warning | 0 |

Only a definite failure marks a VM degraded. An SSH hiccup during the probe is
not evidence that egress is absent, and treating it as such would manufacture
exactly the kind of misleading status this feature was built to remove. If both
verdict lines somehow appear in one output, the failure verdict wins.

Note that a VM missing `curl` reports **degraded**, not indeterminate: the probe
is a single `if`, so an absent binary takes the `else` branch and emits the same
`fail` verdict a blocked request does. That is the intended reading — on an
image whose toolchain is installed by cloud-init over the network, a missing
`curl` is itself evidence that egress was unavailable.

A degraded VM is announced on stdout, after a stderr banner naming the VNet and
the query that shows what is attached:

```
⚠ VM 'my-vm' has NO outbound internet. It is reachable, but every apt/curl/wget on it will fail and the cloud-init toolchain install (az, gh, node, go, rust) is incomplete.
  Azure Bastion is inbound-only and does not provide egress. Check that a NAT gateway is attached to the 'default' subnet of 'azlin-bastion-centralus-vnet':
    az network vnet subnet show --resource-group <rg> --vnet-name azlin-bastion-centralus-vnet --name default --query natGateway
  Then re-run `azlin new` (NAT provisioning is idempotent), or delete and recreate this VM once egress is in place.
VM 'my-vm' created — DEGRADED: no outbound internet access.
```

The VM's connection details are printed by the rest of the creation flow, so a
degraded VM is never left unnamed — the non-zero exit comes after all of it.

With `--pool N`, degraded VM names are collected across the whole batch. Every
VM's details are printed, and azlin exits non-zero once at the end.

## Configuration

There is no new configuration key. The NAT gateway's public IP carries the same
IP tag as the bastion public IP, resolved from the same source:

| Setting | Config field | Environment variable | Default |
|---------|--------------|----------------------|---------|
| IP tag | `bastion_pip_ip_tags` | `AZLIN_BASTION_PIP_IP_TAGS` | `FirstPartyUsage=/ATEVETNonProd` |

```bash
azlin config set bastion_pip_ip_tags "FirstPartyUsage=/ATEVETProd"
```

See [Bastion Public IP IP-Tag](bastion-pip-first-party-ip-tag.md) for the full
precedence rules and validation. The IP tag is immutable after the address is
allocated — if Azure rejects it, azlin fails rather than retrying without it.

The NAT gateway public IP deliberately carries **no** Azure resource tags,
including no `azlin-session` tag. Tagging it would make it a teardown candidate.

## Cost

A NAT gateway is billed per hour plus per GB processed, and its public IP is
billed separately. At current list prices this is roughly $32/month for the
gateway plus $3.65/month for the Standard address — about **$36/month per
region** — plus roughly $0.045 per GB of processed traffic. Check the
[Azure NAT Gateway pricing page](https://azure.microsoft.com/pricing/details/azure-nat-gateway/)
for your region and current rates.

The gateway is regional and shared by every private VM in the subnet, so the
fixed cost is paid once per region, not per VM. It is materially cheaper than
the Azure Bastion that azlin already auto-creates alongside it.

## Interaction with Other Features

| Feature | Interaction |
|---------|-------------|
| Bastion pre-check | Runs first. The NAT check runs after it and re-reads the public-IP flag, so choosing "Switch to public IP" at the bastion prompt skips NAT entirely. |
| `--pool N` | The NAT check runs once before the VM creation loop, not per VM. The egress probe runs per VM. |
| `azlin kill` / `azlin destroy` / `azlin delete` | Never removes the NAT gateway or its public IP — both are shared regional infrastructure, like the bastion. These commands tear down one VM's own session resources only. `azlin destroy --delete-rg` does not change this: the flag is refused outright, because deleting a resource group would destroy unrelated resources. |
| `azlin cleanup` | Will not delete a NAT gateway's public IP. A NAT-attached address reports `ipConfiguration: null`, which previously looked exactly like an orphan; the orphan predicate now also requires `natGateway` to be absent. |
| Teardown's "Left in place (may keep billing)" advisory | Printed by `azlin kill` / `azlin destroy` / `azlin delete` when resources are skipped. For the same reason as above, it no longer lists the NAT public IP among addresses you are advised to reclaim. |
| `az group delete` | Deletes the NAT gateway and its public IP along with everything else. azlin never runs it for you. |
| `azlin connect` / `azlin tunnel` | Unaffected. These use the bastion, which is inbound. |

## Security Posture

- **No inbound exposure is added.** A NAT gateway is outbound-only. Its public
  IP has no inbound listener and cannot be connected to. It is not a jump host
  and does not weaken the private-VM model.
- **Egress is unfiltered and subnet-wide.** Attaching the gateway to `default`
  grants unrestricted outbound internet to every VM in that subnet in that
  region, including VMs belonging to other users of the same resource group.
  NSG and Azure Firewall egress filtering are out of scope.
- **The SNAT address is shared.** All VMs in the subnet leave from one IP.
  Destination-side logs cannot attribute traffic to an individual VM, and one
  abusive VM can get the region's address blocklisted for everyone.
- **Provisioning requires write access.** The feature needs
  `Microsoft.Network/natGateways/write` and
  `Microsoft.Network/virtualNetworks/subnets/write` (plus the corresponding
  join actions) on the resource group — `Network Contributor` covers it. An `az`
  error containing `AuthorizationFailed` (or `does not have authorization`) is
  annotated with *"This is a permissions failure, not a missing resource"* and
  the role to request, on the subnet read as well as on every write. azlin never
  assumes egress exists because it could not check.

## Scaling: SNAT Port Exhaustion

One public IP provides 64,512 SNAT ports, held for the 10-minute idle timeout
after each connection closes. A large fleet opening many short-lived outbound
connections in one subnet can exhaust them, and exhaustion presents exactly like
no egress at all: connections hang, then fail.

azlin provisions a single address. If you hit this, attach more addresses to the
existing gateway — it supports up to 16 — rather than lowering the idle timeout
below the verified 10 minutes:

```bash
az network nat gateway update \
  --resource-group <rg> \
  --name azlin-natgw-centralus \
  --public-ip-addresses azlin-natgw-centralus-ip-tagged azlin-natgw-centralus-ip-2
```

## See Also

- [Set Up a NAT Gateway](../how-to/setup-nat-gateway.md) — manual creation and verification
- [Diagnose Missing Outbound Internet](../troubleshooting/no-outbound-internet.md) — symptom-first triage
- [NAT Gateway Provisioning Reference](../reference/nat-gateway-provisioning.md) — exact commands, module API, exit codes
- [Bastion Pre-Check for Private VMs](bastion-pre-check.md) — the inbound half of the same story
- [Bastion Public IP IP-Tag](bastion-pip-first-party-ip-tag.md) — the shared `bastion_pip_ip_tags` setting
