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

Before creating a private VM, azlin reads the subnet the VM will land in and
checks whether a NAT gateway is attached. If none is, it prompts you to create
one, switch to a public IP, or abort — never silently, and never
optional-by-default: azlin will not create a private VM in a subnet it knows has
no egress. For when the check runs and when it is skipped, see
[When the Pre-Check Runs](../reference/nat-gateway-provisioning.md#when-the-pre-check-runs).

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

Creating a private VM in a region whose subnet has no NAT gateway stops for a
decision before anything is created:

```
How would you like to proceed?
> Create NAT gateway now (takes ~1-2 min, ~$36/mo per region)
  Switch to public IP instead
  Abort
```

Creating the gateway attaches it to the VM subnet and continues with the private
VM; switching to a public IP skips NAT creation, because the VM's own address
provides egress; aborting creates nothing at all. The prompt banner and every
progress line go to stderr, alongside a spinner cleared when provisioning
finishes.

`--yes`, a non-TTY stdin, `--public`, and `--no-bastion` each remove the prompt.
Non-interactive runs auto-create the gateway, mirroring the bastion pre-check,
which auto-creates a substantially more expensive resource under the same
conditions. For the full matrix, see
[Prompt Selection](../reference/nat-gateway-provisioning.md#prompt-selection).

## What Gets Created

A Standard, zone-redundant public IP and a regional NAT gateway, both named
after the region, with the gateway attached to the `default` subnet of
`azlin-bastion-{region}-vnet` — the VM subnet, **never** `AzureBastionSubnet`,
which Azure rejects and which would not help anyway, since the bastion carries
inbound traffic only. Both live in the resource group used for VM provisioning
and are shared by every private VM in that region. The zonal public IP on a
regional gateway is intentional and matches the verified working configuration;
do not "harmonize" them. The exact names are in
[Resource Naming](../reference/nat-gateway-provisioning.md#resource-naming) and
the exact `az` invocations in
[Azure CLI Commands](../reference/nat-gateway-provisioning.md#azure-cli-commands).

### Idempotent

The check asks a single question — *does this subnet have egress?* — so any
attached gateway satisfies it, including one you created yourself under a
different name, and because the names derive only from the region, a re-run
after an interrupted attempt reuses the existing resources rather than billing a
second Standard address forever. This holds only when azlin could actually read
the subnet; see [Detection Failure Is Not Absence](#detection-failure-is-not-absence).

### Creation Failure

Any failed step exits non-zero **before** a VM exists, reporting the sanitized
`az` error under the same abort text a declined prompt produces — the region,
both resource names, and the three commands to provision egress by hand. The
exact wording is in
[Detection Failure vs. Provisioning Failure](../reference/nat-gateway-provisioning.md#detection-failure-vs-provisioning-failure).

### Detection Failure Is Not Absence

A subnet read that errors, times out, or returns unparseable JSON is retried
once and then aborts non-zero rather than being downgraded to "no gateway",
because the create plan's final step *replaces* the subnet's existing
association: one transient ARM failure against a subnet carrying a hand-made or
corporate-named gateway would silently repoint it at a brand-new azlin gateway,
orphan the old one, and start billing a second gateway plus a second public IP
with nothing saying so. The same rule covers a manually built VNet with no
`default` subnet. For the exact error text, see
[Why an Unreadable Subnet Aborts](../reference/nat-gateway-provisioning.md#why-an-unreadable-subnet-aborts).

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
existing SSH session: a TLS `HEAD` request with full certificate validation,
sending no VM data and transferring no body. It runs on **private VMs only** — a
VM with its own public IP has egress by construction, so the probe is skipped.

Only a definite failure marks a VM **degraded**. An SSH hiccup during the probe
is not evidence that egress is absent, and treating it as such would manufacture
exactly the kind of misleading status this feature was built to remove. A VM
missing `curl` does report degraded rather than indeterminate, and that is the
intended reading — on an image whose toolchain is installed by cloud-init over
the network, a missing `curl` is itself evidence that egress was unavailable.

A degraded VM is still fully announced: the rest of the creation flow prints its
connection details, and the non-zero exit comes after all of it, so a degraded
VM is never left unnamed. With `--pool N`, degraded names are collected across
the whole batch and azlin exits non-zero once at the end.

The probe command, the result-to-status table, the degraded banner, and the exit
codes are in
[Post-Provision Egress Probe](../reference/nat-gateway-provisioning.md#post-provision-egress-probe)
and
[Exit Codes and Output Ordering](../reference/nat-gateway-provisioning.md#exit-codes-and-output-ordering).

## Configuration

There is no new configuration key: the NAT gateway's public IP carries the same
IP tag as the bastion public IP, from the same `bastion_pip_ip_tags` setting
(environment variable `AZLIN_BASTION_PIP_IP_TAGS`, default
`FirstPartyUsage=/ATEVETNonProd`) — see
[Bastion Public IP IP-Tag](bastion-pip-first-party-ip-tag.md) for precedence and
validation. The tag is immutable after the address is allocated, so if Azure
rejects it azlin fails rather than retrying without it. The address deliberately
carries **no** Azure resource tags, including no `azlin-session` tag: tagging it
would make it a teardown candidate.

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
| `azlin connect` / `azlin tunnel` | Unaffected. These use the bastion, which is inbound. |
| `azlin kill` / `azlin destroy` / `azlin delete` / `azlin cleanup` | Never remove the NAT gateway or its public IP, and never name that address in teardown's "Left in place (may keep billing)" advisory — both are shared regional infrastructure, like the bastion, and these commands tear down one VM's own session resources only. A NAT-attached address reports `ipConfiguration: null`, which previously looked exactly like an orphan; the orphan predicate now also requires `natGateway` to be absent. `azlin destroy --delete-rg` does not change this: the flag is refused outright, because deleting a resource group would destroy unrelated resources. See [Teardown Interaction](../reference/nat-gateway-provisioning.md#teardown-interaction). |
| `az group delete` | Deletes the NAT gateway and its public IP along with everything else. azlin never runs it for you. |

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
