# NAT Gateway Provisioning Reference

Complete reference for how azlin detects, plans, and creates NAT gateway egress
for private VMs: resource naming, the exact Azure CLI invocations, the
`nat_helpers` module API, decision rules, and exit behavior.

For the narrative version see
[NAT Gateway Egress for Private VMs](../features/nat-gateway-egress.md).

## Resource Naming

All names derive from the target region, lowercased. Nothing else varies, which
is what makes provisioning idempotent across re-runs and machines.

| Resource | Name pattern | Example (`centralus`) |
|----------|--------------|-----------------------|
| NAT gateway | `azlin-natgw-{region}` | `azlin-natgw-centralus` |
| NAT public IP | `azlin-natgw-{region}-ip-tagged` | `azlin-natgw-centralus-ip-tagged` |
| VNet (existing) | `azlin-bastion-{region}-vnet` | `azlin-bastion-centralus-vnet` |
| Subnet (existing) | `default` | `default` |

The public IP suffix is `-ip-tagged`, not `-pip`. The bastion public IP —
`azlin-bastion-{region}-pip` — is a different address for a different purpose,
and the two are never interchanged.

## Azure CLI Commands

azlin builds each command as an argument vector and executes `az` directly. No
shell is involved: there is no `sh -c`, no string interpolation into a command
line, and every value is a discrete `argv` element.

The command blocks below are shown in shell form for readability. Multi-value
flags expand to one `argv` element per value — `--zone 1 2 3` is the four
elements `["--zone", "1", "2", "3"]`, **not** the two elements
`["--zone", "1 2 3"]`. `az` rejects the second form, and because the difference
is invisible in a shell transcript, the verbatim-argv unit test asserts all four
elements explicitly.

### Detect

```bash
az network vnet subnet show \
  --resource-group <rg> \
  --vnet-name azlin-bastion-<region>-vnet \
  --name default \
  --output json
```

The `natGateway.id` field of the response determines the result. Its presence
means the subnet has egress, whatever the gateway is named.

### Create the Public IP

```bash
az network public-ip create \
  --resource-group <rg> \
  --name azlin-natgw-<region>-ip-tagged \
  --location <region> \
  --sku Standard \
  --allocation-method Static \
  --zone 1 2 3 \
  --ip-tags <resolved bastion_pip_ip_tags> \
  --output none
```

`--zone 1 2 3` makes the address zone-redundant. This is the one place the NAT
public IP differs from the bastion public IP, which takes no `--zone` — the two
are built by separate functions for exactly this reason.

No `--tags` is emitted, ever. An `azlin-session` resource tag would reclassify
this address as a teardown candidate and make cleanup destroy the region's
egress.

### Create the Gateway

```bash
az network nat gateway create \
  --resource-group <rg> \
  --name azlin-natgw-<region> \
  --location <region> \
  --sku Standard \
  --idle-timeout 10 \
  --public-ip-addresses azlin-natgw-<region>-ip-tagged \
  --output none
```

The gateway takes no `--zone`. A zonal address on a regional gateway is the
verified working shape.

### Attach to the Subnet

```bash
az network vnet subnet update \
  --resource-group <rg> \
  --vnet-name azlin-bastion-<region>-vnet \
  --name default \
  --nat-gateway azlin-natgw-<region> \
  --output none
```

The subnet is `default`. `AzureBastionSubnet` never appears in any NAT command;
Azure rejects a NAT gateway there, and the bastion subnet carries no VM traffic.

If this step fails with an error whose stderr contains `AnotherOperationInProgress`
or `Conflict` — which happens when two `azlin new` runs race in the same region —
azlin prints

```
  Attach conflicted with a concurrent operation; re-checking subnet...
```

then **waits before looking**, and re-runs detection. The wait is the point: a
409 means the other run's write is in flight, so an immediate read is the one
guaranteed to be too early, and azlin would report a failure for work that
succeeded a moment later. Detection is repeated a bounded number of times,
each preceded by its own wait; the interval and the attempt count are
`CONFLICT_RECHECK_BACKOFF` and `CONFLICT_RECHECK_ATTEMPTS` in `nat_helpers.rs`.

If the subnet is attached by then it prints

```
  ✓ Subnet already attached to NAT gateway '<name>' by a concurrent run
```

and succeeds. If every look still reports no gateway, the original conflict is
the failure the user sees. If the re-check itself fails, both errors are
surfaced — the conflict and the read failure — because the second may be the
real problem. Any non-conflict attach error fails immediately, without waiting.

This guards only against a **concurrent** azlin run: within a single
`azlin new` the subnet is read once, before the VM creation loop.

## Module API

`rust/crates/azlin/src/nat_helpers.rs` owns naming, command construction,
parsing, and planning. It knows nothing about CLI flags, prompts, VMs, or SSH.
Everything listed in this section is `pub` and lives in that module.

The prompt and policy surface — `NatMissingAction`, `decide_nat_action`,
`map_nat_selection`, `nat_abort_message`, `prompt_nat_action` — is **not** in
`nat_helpers.rs`. It lives in `cmd_vm_ops.rs`, is `pub(crate)`, and is
documented under [Prompt Selection](#prompt-selection). The egress probe
(`EgressStatus`, `egress_probe_command`, `parse_egress_probe`,
`egress_failure_message`, `verify_egress`) lives in `auth_forward.rs` and is
likewise `pub(crate)`; see
[Post-Provision Egress Probe](#post-provision-egress-probe).

```rust
/// Whether the VM subnet already has outbound internet.
///
/// Only ever constructed from a subnet read that SUCCEEDED. A failed read is an
/// `Err` from `detect_nat_status`, never `Absent` — see "Why an Unreadable
/// Subnet Aborts".
pub enum NatStatus {
    /// A NAT gateway is attached. `name` is the gateway's short name, which
    /// need not follow azlin's naming convention.
    Attached { name: String },
    /// The subnet was read and carries no `natGateway.id`.
    Absent,
}

// Naming — region is lowercased internally.
pub fn natgw_name_for_region(region: &str) -> String;
pub fn natgw_pip_name(region: &str) -> String;

// Command builders — total, infallible, no I/O.
pub fn build_check_subnet_args(resource_group: &str, region: &str) -> Vec<String>;
pub fn build_create_natgw_pip_args(resource_group: &str, region: &str, ip_tags: &str) -> Vec<String>;
pub fn build_create_natgw_args(resource_group: &str, region: &str) -> Vec<String>;
pub fn build_attach_natgw_args(resource_group: &str, region: &str) -> Vec<String>;

/// Classify an already-parsed subnet object. Total: an unexpected but
/// well-formed shape (missing key, wrong type, hostile string) yields `Absent`
/// rather than panicking. Deciding that `az` itself failed, or that its stdout
/// was not JSON at all, happens in `detect_nat_status` and never reaches here.
pub fn parse_subnet_nat_status(subnet: &serde_json::Value) -> NatStatus;

/// The commands needed to reach an egress-capable subnet, in order.
/// Empty when `status` is `Attached`.
pub fn plan_nat_provisioning(
    status: &NatStatus,
    resource_group: &str,
    region: &str,
    ip_tags: &str,
) -> Vec<Vec<String>>;

// Execution.

/// Read the subnet and classify it. Retries the read once before giving up; the
/// error text quotes both attempts. `Err` means "could not determine" and must
/// abort the caller — it must never be mapped to `Absent`.
pub fn detect_nat_status(resource_group: &str, region: &str) -> anyhow::Result<NatStatus>;
/// Idempotent. An already-attached subnet logs
/// `  ✓ NAT gateway '<name>' already provides egress for <region>` and returns
/// without provisioning; the caller's own pre-check logs
/// `  ✓ NAT gateway '<name>' provides egress for <region>` in that case.
/// Otherwise each step is announced on stderr, in order:
/// `Creating NAT gateway public IP '<pip>' (Standard, zones 1 2 3)...`,
/// `  ✓ Public IP '<pip>' ready`,
/// `Creating NAT gateway '<natgw>' (Standard SKU, 10 min idle timeout)...`,
/// `  ✓ NAT gateway '<natgw>' created`,
/// `Attaching '<natgw>' to subnet 'default' of '<vnet>'...`,
/// `  ✓ Attached to subnet 'default' of '<vnet>'`,
/// `  ✓ Outbound internet enabled for private VMs in <region>`.
pub fn ensure_nat_gateway(resource_group: &str, region: &str, ip_tags: &str) -> anyhow::Result<()>;
```

The split is deliberate: everything above `detect_nat_status` is pure and unit
tested offline, so the command shapes — which are the load-bearing part — are
asserted verbatim without touching Azure.

### Input Validation

`ensure_nat_gateway` validates before building any argument vector:

| Input | Rule | On violation |
|-------|------|--------------|
| `region` | `^[a-z0-9]{2,32}$` after lowercasing | Error. Blocks a leading `-` from being read as a flag, and protects the naming convention that prevents duplicate billing. |
| `resource_group` | Azure's own rule: `^[-\w._()]{1,90}$`, no trailing period, and never starting with `-` | Error |
| `ip_tags` | `AzlinConfig::validate_bastion_pip_ip_tags` — non-empty, ≤ 512 characters, no control characters, and `Key=Value` form whose key is non-empty and does not start with `-` | Error |

The flag-injection guard applies to the **key**, before the `=`. There is no
constraint on the value: `FirstPartyUsage=/ATEVETNonProd` and any other
`-`-leading value are both accepted, because the whole `Key=Value` string is a
single `argv` element and cannot be reinterpreted as a flag.

`ip_tags` is validated at the point of use, not only where it is read, because a
hand-edited config file bypasses the environment-variable validation path.

`--subscription` is never passed. azlin inherits the ambient `az` context.

## Decision Rules

### When the Pre-Check Runs

The check runs once per `azlin new` invocation, before the VM creation loop,
only when the VM will be private. It runs after the bastion pre-check and
re-reads the public-IP flag, because choosing "Switch to public IP" at the
bastion prompt changes the answer.

| Condition | NAT check |
|-----------|-----------|
| Private VM (default) | Runs |
| `--public` or `--no-bastion` | Skipped |
| "Switch to public IP" chosen at the bastion prompt | Skipped |
| `--pool N` | Runs once, not per VM |
| Bastion already exists in the region | Still runs — the two are independent |

### Prompt Selection

Defined in `cmd_vm_ops.rs`, `pub(crate)`:

```rust
pub(crate) enum NatMissingAction {
    CreateNatGateway,
    SwitchToPublicIp,
    Abort,
}

/// `None` means an interactive prompt is required.
pub(crate) fn decide_nat_action(yes: bool, stdin_is_tty: bool) -> Option<NatMissingAction>;

/// Maps a `dialoguer::Select` index to an action.
pub(crate) fn map_nat_selection(index: usize) -> NatMissingAction;

/// The declined-by-user text. Names both resources and the three manual
/// commands, with the resolved resource group interpolated into each.
pub(crate) fn nat_abort_message(resource_group: &str, region: &str) -> String;

/// The provisioning-failed text. Distinct from the abort text because a
/// failure mid-sequence can leave billing resources behind.
pub(crate) fn nat_provisioning_failed_message(resource_group: &str, region: &str) -> String;
```

The prompt is preceded by a single stderr line:

```
No NAT gateway found for the VM subnet in <region>. Private VMs there have no outbound internet (Azure Bastion is inbound-only).
```

`dialoguer::Select` then renders the prompt `How would you like to proceed?`
with default index `0` and exactly these items, in order:

1. `Create NAT gateway now (takes ~1-2 min, ~$36/mo per region)`
2. `Switch to public IP instead`
3. `Abort`

The quoted cost is the NAT gateway (~$32/mo) plus its Standard public IP
(~$3.65/mo) per region, before data-processing charges.

| `yes` | stdin is a TTY | Result |
|-------|----------------|--------|
| `true` | either | `CreateNatGateway` |
| `false` | `false` | `CreateNatGateway`, with a warning on stderr |
| `false` | `true` | `None` — prompt the user |

When no prompt is shown, azlin says why on stderr:

| Condition | stderr |
|-----------|--------|
| `--yes` | `--yes flag set: auto-creating NAT gateway...` |
| stdin is not a TTY | `Warning: non-interactive session detected. Auto-creating a NAT gateway in <region> so the VM has outbound internet. Use --public to give the VM its own public IP instead.` |

| Prompt index | Action |
|--------------|--------|
| `0` | `CreateNatGateway` |
| `1` | `SwitchToPublicIp` |
| `2` (and anything else) | `Abort` |

Handling each action:

| Action | Effect at the call site |
|--------|-------------------------|
| `CreateNatGateway` | Call `ensure_nat_gateway`. On `Err`, abort non-zero. |
| `SwitchToPublicIp` | Set the caller's `want_public_ip` to `true` and skip NAT provisioning. |
| `Abort` | Return the `nat_abort_message` error. No VM, no network resources. |

`SwitchToPublicIp` is a **mutation, not just a skip**. `want_public_ip` is
declared `mut` in `cmd_vm_ops.rs` and the bastion pre-check already sets it; the
`if !want_public_ip` NAT block sits after that bastion block and before the VM
creation loop, and must perform the same assignment. `want_public_ip` is read
once, as the `public_ip_enabled` argument to VM creation, so an unset flag here
does not produce an error — it silently produces the private VM with no egress
that this feature exists to prevent. Because the bastion decision has already
been resolved by this point, setting the flag is also what keeps the two
pre-checks consistent: a VM that switched to a public IP at the NAT prompt is
identical to one created with `--public`.

### Detection Failure vs. Provisioning Failure

| Failure | Behavior |
|---------|----------|
| `az network vnet subnet show` errors, times out, or returns unparseable JSON | Retry the read once. If the retry also fails, abort non-zero **before** creating anything. Never treated as `Absent` — see below. |
| Any create or attach command fails | Abort with a non-zero exit before any VM is created. `nat_provisioning_failed_message` is attached as context above the underlying `az` error. It does **not** say "Aborted": provisioning runs in three steps, so a failure at step two or three can leave a Standard public IP and a gateway behind, both billing. |
| User selects `Abort` | `nat_abort_message` alone. No VM and no network resources are created. |
| `AuthorizationFailed` / `does not have authorization` on the read or on any write | The same abort, with the permissions hint appended — see [Authorization Failures](#authorization-failures). azlin never degrades to assuming egress exists. |

On a double read failure the error is:

```
`az network vnet subnet show` failed twice for subnet 'default' of VNet 'azlin-bastion-<region>-vnet' in <region>:
  first attempt:  <sanitized az error>
  second attempt: <sanitized az error>
```

and the caller wraps it with:

```
Could not determine whether the VM subnet in <region> has outbound internet. Refusing to create a private VM that may silently have no egress. Re-run with --public to give this VM its own public IP instead.
```

Both messages end with the same manual remediation steps, produced by a single
shared `nat_remediation_text` helper so the two paths cannot drift apart. Only
the framing differs. The resource group shown below is the group azlin resolved
for the run, interpolated into every command — the messages never print a `<rg>`
placeholder the user would have to hand-edit before running.

`nat_abort_message(resource_group, region)` reads:

```
Aborted: the VM subnet in <region> has no NAT gateway, so a private VM created there would have no outbound internet.
Azure Bastion is inbound-only: it lets you reach the VM, but it does not provide egress. Without a NAT gateway every apt/curl/wget on the VM fails and the cloud-init toolchain install collapses.

To provision egress manually:
  az network public-ip create --resource-group azlin-rg --name azlin-natgw-<region>-ip-tagged --location <region> --sku Standard --allocation-method Static --zone 1 2 3
  az network nat gateway create --resource-group azlin-rg --name azlin-natgw-<region> --location <region> --sku Standard --idle-timeout 10 --public-ip-addresses azlin-natgw-<region>-ip-tagged
  az network vnet subnet update --resource-group azlin-rg --vnet-name azlin-bastion-<region>-vnet --name default --nat-gateway azlin-natgw-<region>

Or re-run with --public to give this VM its own public IP instead.
```

`nat_provisioning_failed_message(resource_group, region)` opens differently,
then repeats the same steps:

```
NAT gateway provisioning FAILED for <region>, so no VM was created.
Provisioning runs in three steps, so partial resources may already exist and may already be billing. Check resource group 'azlin-rg' for public IP 'azlin-natgw-<region>-ip-tagged' and NAT gateway 'azlin-natgw-<region>' before retrying:
  az network nat gateway list --resource-group azlin-rg -o table
  az network public-ip list --resource-group azlin-rg -o table

Re-running `azlin new` is safe: provisioning is idempotent and reuses whatever already exists.
```

Every `az` stderr on these paths is passed through
`azlin_core::sanitizer::sanitize` before display, which redacts keys,
passwords, secrets, tokens, SAS query strings, `Bearer` values, and PEM blocks.
It does not rewrite ARM resource IDs, so subscription GUIDs present in an `az`
error are shown as `az` emitted them.

#### Authorization Failures

When an `az` error contains `AuthorizationFailed` or `does not have
authorization`, azlin appends:

```
  This is a permissions failure, not a missing resource. Provisioning egress requires the 'Network Contributor' role (or equivalent write access to Microsoft.Network) on the resource group.
```

This applies to the subnet read as well as to each of the three write steps.

#### Why an Unreadable Subnet Aborts

`Absent` means *the read succeeded and reported no gateway*. It never means *the
read failed*. Collapsing the two would be destructive, not conservative: the
final step of the create plan is

```
az network vnet subnet update ... --nat-gateway azlin-natgw-<region>
```

and `--nat-gateway` **replaces** the subnet's existing association rather than
appending to it. A subnet carrying a hand-made or corporate-named gateway, read
during one transient ARM failure, would be silently repointed at a new azlin
gateway; the previous gateway would be orphaned and a second gateway plus a
second Standard public IP would begin billing, with nothing in the output saying
so.

`detect_nat_status` therefore surfaces read failure as `Err`, and the caller
propagates it. `NatStatus` has exactly two variants and no "unknown" state,
because an unknown state is never allowed to reach the planner.

## Post-Provision Egress Probe

Runs on private VMs only, after SSH readiness, over the session azlin already
has. A VM created with a public IP is never probed: it has egress via its own
instance IP, so `EgressStatus::Ok` is assumed without an SSH round-trip.

The remote command is a fixed literal with no interpolation. The sentinels are
single-quoted in the literal:

```bash
if curl -fsI -m 10 https://packages.microsoft.com >/dev/null 2>&1; then \
  echo 'azlin-egress: ok'; else echo 'azlin-egress: fail'; fi
```

Defined in `auth_forward.rs`, `pub(crate)`:

```rust
pub(crate) enum EgressStatus {
    Ok,
    Failed,
    Unknown,
}

/// The fixed remote literal above.
pub(crate) fn egress_probe_command() -> &'static str;

/// Exact-sentinel match on trimmed output. Never substring-scans, never echoes
/// raw remote stdout.
pub(crate) fn parse_egress_probe(output: &str) -> EgressStatus;

/// The stderr banner printed for a degraded VM.
pub(crate) fn egress_failure_message(vm_name: &str, resource_group: &str, region: &str) -> String;

/// Runs the probe over the SSH path already established for post-create work,
/// taking the same target parameters as the other `auth_forward` helpers
/// (address, user, optional bastion port, optional key override, interactive
/// flag). Total — never returns `Err`; SSH transport failure maps to `Unknown`.
pub(crate) fn verify_egress(/* … */) -> EgressStatus;
```

| Remote output | `EgressStatus` | VM reported as |
|---------------|----------------|----------------|
| A trimmed line `azlin-egress: ok`, and no `fail` line | `Ok` | Complete |
| A trimmed line `azlin-egress: fail` | `Failed` | Degraded |
| Both sentinels present | `Failed` — failure wins | Degraded |
| Anything else, empty, or SSH failure | `Unknown` | Complete, with a warning |
| VM has a public IP (probe skipped) | `Ok` | Complete |
| SSH readiness timed out (probe skipped) | `Unknown` | Complete, with a warning |

An SSH failure yields `Unknown`, never `Failed`: only the VM's own explicit
`fail` sentinel marks it degraded. The cause of the SSH failure is printed to
stderr before the verdict is downgraded, sanitized first because an SSH error
can carry remote stderr.

`egress_probe_shortcut(want_public_ip, ssh_ready)` decides whether the probe is
worth an SSH round-trip at all, returning `Some(status)` when it is not. It
skips the probe when the VM has a public IP (`Ok` -- its instance IP is the
egress) and when SSH readiness timed out (`Unknown` -- SSH never authenticated,
so the probe would spend a full connect timeout per VM, in a sequential creation
loop, to reach `Unknown` anyway). Skipping never *infers* a verdict: it can
return `Ok` only for the public-IP case and can never return `Failed`.

The output is remote-controlled and treated as untrusted: it is matched exactly
against the sentinels and never echoed back. The degraded banner is composed
from the VM name and region alone, so control and ANSI sequences from a
compromised VM cannot reach the terminal.

`-k` / `--insecure` is never added to the probe. A probe that skips certificate
validation would report success against a hostile intercepting proxy.

## Exit Codes and Output Ordering

| Situation | stdout | Exit code |
|-----------|--------|-----------|
| Egress present or created, VM healthy | `VM '<name>' created successfully!` | 0 |
| Egress missing, user aborts | — | non-zero |
| Egress provisioning fails | — | non-zero |
| VM created, probe returns `Failed` | `VM '<name>' created — DEGRADED: no outbound internet access.`, preceded on **stderr** by the `egress_failure_message` banner | non-zero |
| VM created, probe returns `Unknown` | `VM '<name>' created successfully!`, preceded on **stderr** by `Warning: could not verify outbound internet on '<name>'. ...` | 0 |

`egress_failure_message(vm_name, resource_group, region)` is:

```
VM '<name>' has NO outbound internet. It is reachable, but every apt/curl/wget on it will fail and the cloud-init toolchain install (az, gh, node, go, rust) is incomplete.
  Azure Bastion is inbound-only and does not provide egress. Check that a NAT gateway is attached to the 'default' subnet of 'azlin-bastion-<region>-vnet':
    az network vnet subnet show --resource-group azlin-rg --vnet-name azlin-bastion-<region>-vnet --name default --query natGateway
  Then re-run `azlin new` (NAT provisioning is idempotent), or delete and recreate this VM once egress is in place.
```

A degraded VM is never abandoned mid-loop: the rest of the creation flow still
prints its connection details, and with `--pool N` the non-zero exit is issued
once after the whole loop, naming every degraded VM, so a partially degraded
batch never hides the names of VMs that exist and bill.

*"VM '<name>' created successfully!"* is printed only when the VM is not
degraded. The cloud-init line is unchanged by this work and still reads
*"Cloud-init provisioning complete."*

## Teardown Interaction

A NAT gateway's public IP reports `ipConfiguration: null` — that field only ever
holds NIC and Bastion IP configurations. The orphan predicate therefore requires
both fields to be absent before an address is considered unassociated:

`public_ip_is_unassociated` in `azlin-azure/src/teardown.rs` treats an address
as orphaned only when **both** `ipConfiguration` and `natGateway` are null or
absent. A missing field counts as free, so the predicate stays correct against
an `az` response that omits either key.

`azlin cleanup` (via `cmd_cleanup_ops.rs`) and the teardown planner used by
`azlin kill` / `azlin destroy` / `azlin delete` share this one predicate, so
neither deletes an address that is providing egress, nor names it in teardown's
`⚠️  Left in place (may keep billing):` advisory.

There is no top-level `azlin down` command; `down` exists only as
`azlin compose down`, which stops composed services and does not touch regional
network infrastructure. `azlin destroy --delete-rg` is refused with an error
rather than executed, so it is not a path to deleting the NAT gateway either.
Only an explicit `az group delete` removes these resources.

## See Also

- [NAT Gateway Egress for Private VMs](../features/nat-gateway-egress.md)
- [Set Up a NAT Gateway](../how-to/setup-nat-gateway.md)
- [Diagnose Missing Outbound Internet](../troubleshooting/no-outbound-internet.md)
- [Destroy Command](destroy-command.md) — teardown classification rules
