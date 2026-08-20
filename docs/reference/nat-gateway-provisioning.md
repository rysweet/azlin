# NAT Gateway Provisioning Reference

How azlin detects, plans, and creates NAT gateway egress for private VMs:
resource naming, module boundaries, decision rules, failure handling, and exit
behavior.

For the narrative version see
[NAT Gateway Egress for Private VMs](../features/nat-gateway-egress.md).

## What this file is, and is not

This file states the **contract**: the rules a change has to preserve, and
where each of them is enforced.

It deliberately does **not** reproduce the `az` argument vectors or the exact
text of error messages. Those live in the code, are asserted verbatim by unit
tests, and a second copy here has no mechanism keeping it honest — this file
drifted three times inside the pull request that introduced it (#1103). Where
the exact bytes matter, the function that produces them and the test that pins
them are named instead.

To read the current argv or message text, read the test. `cargo test -p azlin
--bin azlin nat_helpers` runs all of them offline.

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
and the two are never interchanged (`test_natgw_pip_name_is_not_the_bastion_pip_name`).

A typo in either suffix silently double-bills a Standard public IP and orphans
the previous one, which is why both are asserted verbatim rather than by
substring.

## Azure CLI Commands

azlin builds each command as an argument vector and executes `az` directly.
There is no `sh -c`, no string interpolation into a command line, and every
value is a discrete `argv` element.

| Step | Builder in `nat_helpers.rs` | Verbatim argv asserted by |
|------|-----------------------------|---------------------------|
| Detect | `build_check_subnet_args` | `test_build_check_subnet_args_verbatim` |
| Create the public IP | `build_create_natgw_pip_args` | `test_build_create_natgw_pip_args_verbatim` |
| Create the gateway | `build_create_natgw_args` | `test_build_create_natgw_args_verbatim` |
| Attach to the subnet | `build_attach_natgw_args` | `test_build_attach_natgw_args_verbatim` |

`plan_nat_provisioning` emits the last three in that order, and only when the
subnet has no gateway (`test_plan_nat_provisioning_absent_emits_three_steps_in_order`,
`test_plan_nat_provisioning_attached_is_empty`).

### Rules the builders must keep

These are the parts a rewrite could get wrong without failing obviously.

| Rule | Why | Enforced by |
|------|-----|-------------|
| The NAT public IP is zone-redundant; the gateway is regional | A zonal address on a regional gateway is the verified working shape | `test_build_create_natgw_args_is_regional_not_zonal` |
| A multi-value flag expands to one `argv` element per value | `--zone 1 2 3` is four elements, not two. `az` rejects the two-element form, and the difference is invisible in a shell transcript | `test_build_create_natgw_pip_args_zone_is_four_argv_elements` |
| No `--tags` is ever emitted | An `azlin-session` resource tag would reclassify the address as a teardown candidate and make cleanup destroy the region's egress | `test_build_create_natgw_pip_args_never_emits_session_tags` |
| `AzureBastionSubnet` never appears in any NAT command | Azure rejects a NAT gateway there, and the bastion subnet carries no VM traffic | `test_no_builder_ever_touches_azure_bastion_subnet` |
| The VNet name comes from the shared `bastion_vnet_name` | So the two features cannot drift apart | `test_builders_reuse_bastion_vnet_name` |
| Region case is normalized everywhere | Naming is the idempotency mechanism | `test_builders_normalize_region_case` |
| `--subscription` is never passed | azlin inherits the ambient `az` context | — |

Detection reads the subnet's `natGateway.id`. Its presence means the subnet has
egress, whatever the gateway is named — including one azlin did not create
(`test_parse_subnet_nat_status_attached_accepts_foreign_name`).

### Attach conflicts

Two `azlin new` runs in the same region write the same subnet, and Azure
serialises them with `AnotherOperationInProgress` / `Conflict`. On that error
azlin **waits, then re-reads** — the 409 is evidence that the other run's write
is in flight, so an immediate read is the one guaranteed to be too early, and
azlin would report a failure for work that succeeded a moment later (#1101).

| Outcome | Result |
|---------|--------|
| A re-check finds the subnet attached | Success; the gateway the other run created is reused |
| Every re-check still reports no gateway | The original conflict is the failure the user sees |
| A re-check itself fails | Both errors are surfaced — the second may be the real problem |
| The attach error was not a conflict | Fails immediately, without waiting |

`resolve_attach_conflict` owns this, with the wait and the re-read injected so
the ordering is testable; `CONFLICT_RECHECK_BACKOFF` and
`CONFLICT_RECHECK_ATTEMPTS` set the interval and the bound. See
`conflict_waits_before_the_first_recheck` and its four siblings.

This guards only against a **concurrent** azlin run: within a single
`azlin new` the subnet is read once, before the VM creation loop.

## Module Boundaries

`rust/crates/azlin/src/nat_helpers.rs` owns naming, command construction,
parsing, and planning. It knows nothing about CLI flags, prompts, VMs, or SSH.

```rust
/// Whether the VM subnet already has outbound internet.
///
/// Only ever constructed from a subnet read that SUCCEEDED. A failed read is an
/// `Err` from `detect_nat_status`, never `Absent` — see "Why an Unreadable
/// Subnet Aborts".
pub enum NatStatus {
    Attached { name: String },
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

/// Idempotent: an existing gateway is reused and nothing is provisioned.
/// Announces each step on stderr as it runs.
pub fn ensure_nat_gateway(resource_group: &str, region: &str, ip_tags: &str) -> anyhow::Result<()>;
```

Everything above `detect_nat_status` is pure and unit tested offline, so the
command shapes — the load-bearing part — are asserted without touching Azure.

The rest of the feature lives elsewhere, on purpose:

| Surface | Module | Visibility |
|---------|--------|------------|
| Prompt and policy (`NatMissingAction`, `decide_nat_action`, `map_nat_selection`, `nat_abort_message`, `nat_provisioning_failed_message`, `prompt_nat_action`) | `cmd_vm_ops.rs` | `pub(crate)` |
| The R4 egress gate and the R5 degraded-VM tally (`resolve_private_vm_egress`, `EgressDecision`, `DegradedVms`) | `egress_gate.rs` | `pub(crate)` |
| The egress probe (`EgressStatus`, `egress_probe_command`, `parse_egress_probe`, `egress_probe_shortcut`, `egress_failure_message`, `verify_egress`) | `auth_forward.rs` | `pub(crate)` |

### Input Validation

`ensure_nat_gateway` validates before building any argument vector, and
`detect_nat_status` validates independently because it is called first and from
a different path (`test_detect_nat_status_validates_before_running_az`).

| Input | Rule | On violation |
|-------|------|--------------|
| `region` | `^[a-z0-9]{2,32}$` after lowercasing | Error. Blocks a leading `-` from being read as a flag, and protects the naming convention that prevents duplicate billing. |
| `resource_group` | Azure's own rule: `^[-\w._()]{1,90}$`, no trailing period, never starting with `-` | Error |
| `ip_tags` | `AzlinConfig::validate_bastion_pip_ip_tags` | Error |

The flag-injection guard applies to the **key**, before the `=`. There is no
constraint on the value: the whole `Key=Value` string is a single `argv`
element and cannot be reinterpreted as a flag.

`ip_tags` is validated at the point of use, not only where it is read, because a
hand-edited config file bypasses the environment-variable validation path.

## Decision Rules

### When the Pre-Check Runs

Once per `azlin new` invocation, before the VM creation loop, only when the VM
will be private. It runs after the bastion pre-check and re-reads the
public-IP flag, because choosing "Switch to public IP" at the bastion prompt
changes the answer.

| Condition | NAT check |
|-----------|-----------|
| Private VM (default) | Runs |
| `--public` or `--no-bastion` | Skipped |
| "Switch to public IP" chosen at the bastion prompt | Skipped |
| `--pool N` | Runs once, not per VM |
| Bastion already exists in the region | Still runs — the two are independent |

### Prompt Selection

`decide_nat_action(yes, stdin_is_tty)` decides whether a prompt is needed at
all; `None` means ask.

| `yes` | stdin is a TTY | Result |
|-------|----------------|--------|
| `true` | either | `CreateNatGateway` |
| `false` | `false` | `CreateNatGateway`, with a warning on stderr |
| `false` | `true` | `None` — prompt the user |

When a prompt is shown it offers three items in this order, and
`map_nat_selection` maps the index:

| Prompt index | Action |
|--------------|--------|
| `0` | `CreateNatGateway` — the default |
| `1` | `SwitchToPublicIp` |
| `2` (and anything else) | `Abort` |

The prompt quotes the running cost, which is the NAT gateway (~$32/mo) plus its
Standard public IP (~$3.65/mo) per region, before data-processing charges.

When no prompt is shown, azlin says why on stderr — `--yes` and
non-interactive have distinct messages.

### Handling each action

| Action | Effect | Enforced by |
|--------|--------|-------------|
| `CreateNatGateway` | Provision; on failure, abort non-zero | `failed_provisioning_never_returns_a_decision` |
| `SwitchToPublicIp` | Set `want_public_ip` and skip provisioning | `switching_to_a_public_ip_is_a_decision_not_an_error` |
| `Abort` | Return the abort error. No VM, no network resources | `aborting_fails_with_the_abort_message` |

`SwitchToPublicIp` is a **mutation, not just a skip**. `want_public_ip` is read
once, as the `public_ip_enabled` argument to VM creation, so failing to set it
produces no error — it silently produces the private VM with no egress that
this feature exists to prevent. `EgressDecision` has no third variant, so the
gate cannot return "proceed anyway"; `every_combination_maps_to_the_required_outcome`
walks the whole (subnet state × answer × provisioning outcome) table.

### Detection Failure vs. Provisioning Failure

| Failure | Behavior |
|---------|----------|
| `az network vnet subnet show` errors, times out, or returns unparseable JSON | Retry the read once after a backoff. If the retry also fails, abort non-zero **before** creating anything. Never treated as `Absent`. |
| Any create or attach command fails | Abort non-zero before any VM is created. `nat_provisioning_failed_message` is attached as context above the underlying `az` error. It does **not** say "Aborted": provisioning runs in three steps, so a failure at step two or three can leave a Standard public IP and a gateway behind, both billing. |
| User selects `Abort` | `nat_abort_message` alone. No VM and no network resources are created. |
| `AuthorizationFailed` / `does not have authorization` on the read or on any write | The same abort, with the permissions hint appended. azlin never degrades to assuming egress exists. |

Both message helpers name the two resources and the three manual `az` commands,
with the **resolved** resource group interpolated into each — never a `<rg>`
placeholder the user would have to hand-edit. They share one
`nat_remediation_text` helper so the two paths cannot drift apart; only the
framing differs. `test_read_failure_message_reports_only_the_attempts_made`
pins the read-failure text to the number of attempts actually made, so it never
claims two when only one happened.

Every `az` stderr on these paths is passed through
`azlin_core::sanitizer::sanitize` before display, which redacts keys,
passwords, secrets, tokens, SAS query strings, `Bearer` values, and PEM blocks.
It does not rewrite ARM resource IDs, so subscription GUIDs present in an `az`
error are shown as `az` emitted them.

#### Authorization Failures

An `az` error containing `AuthorizationFailed` or `does not have authorization`
gets a hint naming the `Network Contributor` role appended. It applies to the
subnet read as well as to each of the three write steps
(`test_annotate_authz_adds_role_hint_for_denials`,
`test_annotate_authz_leaves_other_errors_untouched`).

An authorization denial is the one read failure that is **not** retried: RBAC
does not grant itself two seconds later, so retrying costs time to reach an
identical verdict (`test_authz_failures_are_not_retried`). A *not-found* read
is still retried, because the VNet may have been created moments earlier and
ARM read-after-write is not instantaneous (`test_not_found_is_still_retried`).

The hint appears exactly once even when a failure passes through two layers
(`test_conflict_recheck_failure_message_carries_the_role_hint_exactly_once`).

#### Why an Unreadable Subnet Aborts

`Absent` means *the read succeeded and reported no gateway*. It never means *the
read failed*. Collapsing the two would be destructive, not conservative: the
final step of the create plan is `az network vnet subnet update ... --nat-gateway`,
and `--nat-gateway` **replaces** the subnet's existing association rather than
appending to it.

A subnet carrying a hand-made or corporate-named gateway, read during one
transient ARM failure, would be silently repointed at a new azlin gateway; the
previous gateway would be orphaned and a second gateway plus a second Standard
public IP would begin billing, with nothing in the output saying so.

`detect_nat_status` therefore surfaces read failure as `Err`, and the caller
propagates it. `NatStatus` has exactly two variants and no "unknown" state
(`test_nat_status_has_exactly_two_states`), because an unknown state is never
allowed to reach the planner. The gate refuses without prompting or
provisioning (`an_unreadable_subnet_is_an_error_and_asks_nothing`).

## Post-Provision Egress Probe

Runs on private VMs only, after SSH readiness, over the session azlin already
has. `egress_probe_command` is a fixed literal with no interpolation
(`test_egress_probe_command_is_a_safe_fixed_literal`); it curls a known host
and echoes one of two sentinels.

| Remote output | `EgressStatus` | VM reported as |
|---------------|----------------|----------------|
| The success sentinel, and no failure sentinel | `Ok` | Complete |
| The failure sentinel | `Failed` | Degraded |
| Both sentinels present | `Failed` — failure wins | Degraded |
| Anything else, empty, or SSH failure | `Unknown` | Complete, with a warning |
| VM has a public IP (probe skipped) | `Ok` | Complete |
| SSH readiness timed out (probe skipped) | `Unknown` | Complete, with a warning |

`parse_egress_probe` matches the sentinels **exactly** on trimmed lines. It is
not a substring scan: an embedded or ANSI-prefixed sentinel does not count
(`test_parse_egress_probe_rejects_substring_embedded_sentinel`,
`test_parse_egress_probe_rejects_ansi_prefixed_sentinel`).

An SSH failure yields `Unknown`, never `Failed`: only the VM's own explicit
failure sentinel marks it degraded. The cause is printed to stderr before the
verdict is downgraded, sanitized first because an SSH error can carry remote
stderr.

`egress_probe_shortcut(want_public_ip, ssh_ready)` decides whether the probe is
worth an SSH round-trip at all. Skipping never *infers* a verdict: it can
return `Ok` only for the public-IP case and can never return `Failed`.

The output is remote-controlled and treated as untrusted: matched exactly
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
| VM created, probe returns `Unknown` | `VM '<name>' created successfully!`, preceded on **stderr** by a warning | 0 |

`egress_failure_message` names the VM, says it is reachable but has no egress,
and gives the `az` command to check the subnet's `natGateway`
(`test_egress_failure_message_is_actionable`).

A degraded VM is never abandoned mid-loop: the rest of the creation flow still
prints its connection details, and with `--pool N` the non-zero exit is issued
once after the whole loop, naming every degraded VM, so a partially degraded
batch never hides the names of VMs that exist and bill. `DegradedVms` produces
that failure only when consumed, which is what keeps the exit after the loop
(`every_degraded_vm_is_named_in_the_failure`,
`no_degraded_vms_is_the_only_path_to_success`).

*"VM '<name>' created successfully!"* is printed only when the VM is not
degraded.

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
