# `azlin list` Enrichment and Output Safety Reference

The contract behind the enrichment columns of `azlin list`: which collectors
run, the gate that decides whether they may run at all, how many Azure lookups
a listing costs, and what azlin guarantees about the bytes it prints.

For the narrative version see
[Tmux Session Status](../features/tmux-session-status.md). For flags, columns
and troubleshooting, see the
[`azlin list` command page](../../docs-site/commands/vm/list.md).

## What this file is, and is not

This file states the **rules a change has to preserve** and names where each is
enforced. It does not reproduce `az` argument vectors or exact message text —
those live in the code, are pinned verbatim by unit tests, and a second copy
here has no mechanism keeping it honest.

```bash
cargo test -p azlin --bin azlin cmd_list
```

## The enrichment columns

Four collectors add columns beyond the base VM listing. All four read data off
the VM itself rather than out of ARM, and all four are subject to the same gate.

| Columns | Collector | Added by |
|---|---|---|
| `Tmux` | `collect_tmux_sessions` | on by default; `--no-tmux` disables |
| `Agent`, `CPU%`, `Mem%`, `Disk%` | `collect_health_data` | `--with-health` |
| `Procs` | `collect_procs` | `--show-procs` (table output only) |
| `Storage` | `collect_storage_status` | storage listing |

`Latency` is derived from the same probes and is withheld under the same
conditions.

## Rule 1: enrichment is gated on subscription identity, not count alone

Every enrichment probe addresses a VM by an ARM resource id built from the
subscription the CLI is currently on. `VmInfo` carries no subscription of its
own. A probe therefore reaches the right machine only when the listing was read
from the same subscription the probe will be built against.

**A count of one no longer implies safety. The one subscription queried must
also *be* the one the probes will use.**

Identity was *added* to the gate, not substituted for the count. A listing
spanning more than one subscription is still withheld on count alone, because no
single probe subscription can be correct for all of them. What changed is that
passing the count is no longer sufficient.

Counting by itself was the earlier rule, and it was wrong in an ordinary case: a
single context pinning a *different* subscription gives a count of one and
passes, after which every probe runs against a resource id in the CLI's
subscription. Three routine paths reach that state — `azlin context create` does
not activate the new context, `--contexts` can select a single non-active
context, and a partial listing failure collapses a two-subscription run to one.

Where a resource group and VM name exist in both subscriptions — which templated
IaC naming makes ordinary rather than exotic — the probe succeeds against the
**wrong machine**, and that host's sessions, health and processes render under
this listing's rows. The failure is silent and confidently wrong, which is worse
than an empty column.

### The comparison has three outcomes, not two

Identity is compared trimmed and case-insensitively: a subscription id is a
GUID, which is case-insensitive as an identifier, and the queried side comes
from a hand-edited context file while the probe side comes from `az`. Withholding
on a casing difference alone would drop the columns an operator asked for and
blame a mismatch that does not exist.

| What was queried | Result | What the note says |
|---|---|---|
| More than one subscription | withheld | names how many subscriptions the listing spans |
| Exactly one, matching the probe subscription | **enrichment runs** | no note |
| Exactly one, differing, GUID-shaped | withheld | names both subscriptions — a genuine mismatch |
| Exactly one, differing, not GUID-shaped | withheld | says the context pins its subscription **by name**, which cannot be matched against a GUID, and asks for an id |

The fourth row is the one worth knowing about. `az` accepts a subscription name
as well as an id, and nothing on the context write path requires a GUID — so a
context may name the very subscription the CLI is already on, and a name never
equals a GUID. Reporting that as a mismatch would assert as fact something
unknown. The note states what is actually knowable and what would make it
knowable, rather than inventing a cause.

### One call produces both the gate and the note

`resolve_enrichment` returns the decision and the operator-facing note together.

They were previously computed separately, and they drifted: the note recited a
fixed string naming "bastion, tmux and health" while `--show-procs` ran anyway,
so the screen claimed to have withheld something that had in fact executed. The
note now names what was actually withheld, so it can neither over-claim nor stay
silent about a collector that was skipped. Where a single subscription was
queried, the note names both it and the probe subscription; the multi-subscription
case has no single counterpart to name and reports the span instead.

**All four collectors take this one gate.** A collector that carries its own
copy of the threshold is the bug this structure exists to prevent.

## Rule 2: routing is discovered once per command

Bastion routing is a pure function of the VM list. It is computed once by the
caller and lent to every collector as a shared `BastionMap`, keyed by
(resource group, region).

`collect_tmux_sessions`, `collect_health_data` and `collect_procs` each used to
call `discover_bastions` for themselves. `azlin list --with-health --show-procs`
therefore ran `az network bastion list` three times per resource group to
compute the same answer three times, and the operator watched three spinners
re-derive it. `az` costs roughly 0.9s of process start before the ARM round
trip, so a five-resource-group listing spent at least nine seconds on ten
redundant lookups.

Callers running a single collector go through `discover_bastions_async`, which
is also where the `spawn_blocking` hop and the discovery-failure warning live.

### The lookup budget

There are **two sweeps, and they share one cache.** Treating them as
independent is how the counts in the older docs went wrong — and how this
section had them wrong before.

**Table sweep** — one `az network bastion list` per distinct resource group in
the listing, to render the `Azure Bastion Hosts` table. It runs only when all
three hold: the output format is `table`, the listing is not cross-subscription,
and at least one resource group survived filtering. It is *not* filtered by
public IP: the table documents the bastions in the scope you asked about, which
does not change because a VM happens to have a public address. A table listing
of public-IP-only VMs therefore still costs one lookup per resource group.

It is driven by the listing that survives filtering, so a resource group whose
VMs are all deallocated contributes no lookup and its bastions are absent unless
`--show-all-vms` keeps those VMs in the listing.

**Routing sweep** — runs only when a collector that needs it will run
(`enrichment.any()`), and *needs* one lookup per distinct resource group holding
a running VM with no public IP. What it *costs* is a separate question: the
table sweep's answers are handed down through `reuse_or_look_up`, cached
failures included, so a group that already refused is neither asked twice nor
reported twice. Both sweeps read the same VM list and routing's predicate
selects a subset of the groups the table sweep already covered, so **on the
default table path routing costs zero additional `az` invocations.** Its
per-group counts apply only where the table sweep does not run.

| Listing | `-o table` | `-o json` / `-o csv`, or cross-subscription |
|---|---|---|
| Every VM has a public IP | 1 per resource group — table sweep alone | 0 |
| Single resource group, some private VMs | 1 | 1 |
| `--show-all-vms` spanning several groups | 1 per resource group in the listing | 1 per resource group that needs it |
| Adding `--with-health` or `--show-procs` | **unchanged** — the map is shared | **unchanged** — the map is shared |
| `--no-tmux` alone | 1 per resource group — the table sweep does not depend on collectors | 0 — no collector runs |
| `--no-tmux` plus the first enrichment flag | unchanged — routing reuses the sweep above | 0 → 1 per resource group that needs it |

## Rule 3: probes are bounded

**At most 64 SSH probes are in flight at once.**

The probe set previously had no limit: one `ssh` child per listed VM, three pipe
descriptors each. A subscription with a few hundred running VMs ran into the
default 1024-descriptor limit, and the failure surfaced only under `--verbose`.
On the default path those VMs simply rendered as having no sessions — silent
degradation that worsens with fleet size, which is the direction a fleet tool is
used.

## Rule 4: a failure that changes the output is reported

The governing rule: **a column that is empty because something failed must be
distinguishable from a column that is empty because there was nothing to
report.**

- A non-zero `az` exit from `detect_bastion_hosts` is an error, not an empty
  result. Returning success-with-nothing made "no authorization on this
  resource" indistinguishable from "this group has no bastion", and the
  aggregated notice that should have named it was fed only by the spawn-failure
  path — so it was unreachable in the case that actually happens.
- Warnings are printed by the listing **after its spinner is cleared**. A line
  written from inside `spawn_blocking` while the progress indicator redraws
  every 120ms is overwritten before it can be read.
- A bastion lookup answered with unparseable output is reported rather than
  recorded as an answer of "none". A JSON `null` and empty output both still
  mean "no bastion here" — that is how it is ordinarily spelled.
- A bastion at a location the coordinate allowlist rejects (an ARM response
  giving `"East US"` in display form) is **named**, not silently dropped.
- The failed process probe reports its cause. It previously collapsed spawn
  failure, timeout, refused authentication and non-zero exit into a blank cell,
  leaving no way to tell an idle VM from an unreachable one.
- The same-name collision warning is printed **once by the listing** and covers
  tmux, health, processes and latency alike. Printing it from the tmux collector
  meant `--no-tmux --with-health --show-procs` withheld the same VMs from three
  collectors and said nothing.
- The bastion-lookup warning reports **one line** — the line that names the
  failure, skipping blanks and `az` advisory banners, falling back to the banner
  when that is all `az` said. An imprecise cause beats silence; a multi-line
  error blob that lets an extension warning be read as the cause of an
  authorization failure does not.

### Routing decisions are pure and testable

`probe_route` decides `ProbeRoute::Bastion`, `ProbeRoute::Direct` or
`ProbeRoute::Unreachable` before any connection is attempted, so it is unit
tested rather than inferred from behaviour. A VM with no public address and no
bastion route still routes direct to its private address, preserving the
behaviour operators on a VPN or peered network already had.

A bastion route that fails to **carry** the command — a transport error — retries
once at the private address. A command that reached the VM and exited non-zero is
that VM's own answer and is **never** retried: a retry could land on a different
host and report its processes under this VM's name.

`probe_ssh_opts` is the single source of the shared timeout, batch-mode and
identity options. It **omits** `-i` entirely when the key path is not usable.
Three sites previously spelled the fallback as an empty string, which hands
`ssh` an empty identity argument rather than no argument at all; `ssh` then
failed on a missing identity file and a reachable VM was reported unreachable.

## Rule 5: what azlin guarantees about printed bytes

Azure-supplied names are chosen by anyone with write access to the subscription.
The `azlin-session` tag is in the **default** table, so no extra flag is needed
for tag content to reach a terminal.

### Sanitisation

`sanitize_remote_text` is applied **once per VM, in one place**, shared by the
table and CSV writers. It covers the VM name, region, SKU, OS offer, rendered
address and the `azlin-session` tag, plus session, process and agent-status text
read off remote hosts. It also covers the warning paths and the
`Azure Bastion Hosts` table — a warning is not a safer place to print an escape
sequence than a table cell is.

It strips:

| Class | Covers |
|---|---|
| `Cc` | C0 controls, `DEL`, and the 8-bit C1 range including CSI |
| `Cf` | the **whole** format block — bidirectional overrides, `U+00AD`, `U+061C`, word joiners, the tag block |
| `Zl` / `Zp` | `U+2028` and `U+2029` |

`Zl` and `Zp` matter because `is_control` does not report them, yet every
terminal and text consumer breaks a line on them — which defeats the
no-forged-rows rule the function exists to enforce. Coverage was verified
exhaustively against Unicode 16 rather than asserted: every assigned `Cf` code
point is stripped, and nothing outside `Cf`/`Zl`/`Zp`/unassigned is caught, so
no legitimate name loses a character.

**Residual:** stripping is followed by truncation to `MAX_REMOTE_TEXT_LEN` (512
characters) with no marker, so two VMs sharing a 512-character prefix render
identically in the column an operator reads to pick a connection target — the
tail of the same spoofing class, narrowed to values that must first collide on
512 characters.

Alignment is the second thing this protects. Truncation pads a cell to an exact
count of *visible* columns, and a control character is a character that occupies
none — so an unsanitised name silently shifted every border to its right.

### CSV: two properties, composed on the same value

Sanitising is not escaping, and neither substitutes for the other. They close
different failures, and a CSV cell needs **both**:

| Property | Applied by | Closes |
|---|---|---|
| Strip | `sanitize_remote_text` | **record** injection — a newline (or `U+2028`) ends the row early, and what follows parses as a VM of someone else's design |
| Quote | `csv_field` | **field** injection — a comma ends the cell early and shifts every later column by one, which a consumer reads as valid data for the wrong VM |

A comma is not a control character, so stripping cannot close the second. A
quote is not a sanitiser, so quoting cannot close the first. A session literally
named `a,b`, or an `azlin-session` tag carrying a comma, is field injection; the
same tag carrying `U+2028` is record injection.

**The composition is the contract, not either half.** `csv_field` quotes per
RFC 4180 — wrapping the value and doubling any embedded quote — when it contains
a comma, a quote, `CR` or `LF`, and it is applied to the text
`sanitize_remote_text` already produced, never to the raw Azure value. A tag
carrying a control character *and* a comma must come out both stripped and
quoted; that single case is what distinguishes a correct implementation from one
that kept only the half it was last edited for, and it is the regression test
this rule is worth.

The `Tmux` column joins session names with `;` before quoting, so the cell reads
as one field.

#### Which columns get which

| Column | Stripped | Quoted |
|---|---|---|
| `Session` (the `azlin-session` tag) | yes | **yes** |
| `Tmux` | yes | **yes** |
| `VM Name` (`--wide`) | yes | **yes** |
| `OS`, `IP`, `Region` | yes | **yes** |
| `SKU` (`--wide`) | yes | **yes** |
| `Agent` (`--with-health`) | yes | **yes** |
| `Status`, `CPU`, `Mem`, `Latency`, `CPU%`, `Mem%`, `Disk%` | enumerated or numeric | no |

Every free-form column is stripped **and quoted**. The unquoted columns are an
enum (`Status`) and computed or numeric values (`CPU`, `Mem`, `Latency`, and the
health metrics via `metric_csv`), which carry no delimiter to quote.

`csv_field_covers_every_free_form_field_on_the_row` pins this: it drives one
comma-bearing value per free-form column through `csv_field` and asserts each
comes back quoted and otherwise unchanged, so the rule is bound to a test rather
than to this paragraph.

**Not handled: spreadsheet formula injection.** A value beginning with `=`, `+`,
`-` or `@` is still evaluated on open. Prefer `-o json` for anything you will
open in a spreadsheet.

### JSON is deliberately unchanged

`-o json` emits the exact bytes Azure returned. Its consumer is a machine, and
escaping there would corrupt the contract rather than protect anyone.

Note what this does **not** mean: `serde_json` escapes `0x00`–`0x1F`, `"` and
`\`, so `U+007F`, the C1 range and `U+2028` are emitted raw. Rendering JSON
safely on a terminal is the terminal's problem, not azlin's.

### Session names: two different validators

| Function | Where | Rule |
|---|---|---|
| `sanitize_remote_text` | the **display** path | strips; keeps every legitimate name |
| `parse_session_name` | `match_session_in_map` and session restore | allowlist: alphanumeric, `_`, `-`, 128-char cap |

The stricter allowlist is used where a name **addresses** a VM, not where it is
printed. Applying it on the display path would silently drop names tmux itself
permits. An allowlist is unavailable for process names in any case — they are
arbitrary executable paths.

## Rule 6: resource ids are built by one function

Within the listing path, `build_vm_resource_id` produces every string the tunnel
registry keys on. Two hand-rolled copies of that format could diverge and leak a
fresh tunnel per VM per invocation.

**Not yet true repository-wide, and not claimed here:** `cmd_tunnel`,
`cmd_connect`, `cmd_session` and `cmd_monitoring` still format the id inline, and
a second helper of the same name exists with the same format string.
Consolidating those is follow-up work.

### The allowlist covers bastion coordinates, and only those

`valid_bastion_coordinates` — `valid_bastion_name` plus `valid_bastion_location`,
split so a rejection can say which half failed — is a tested allowlist on the
bastion name and region that reach an `az` argument vector. It rejects a leading
dash, so an ARM-supplied name of `--query` cannot be read by `az` as a flag.

**That is its entire extent, and the wider claim is not made here.** Resource-group
names are not covered: `collect_disk_configs` passes each VM's resource group
straight into an `az vm list --resource-group` invocation with no validator. The
value arrives from the ARM listing rather than from user input, and `az` is
spawned with an argument vector rather than a shell line — so there is no shell
to inject into — but the leading-dash reading that `valid_bastion_name` exists to
prevent is not prevented there. Extending the allowlist to resource groups is
tracked in [#1147](https://github.com/rysweet/azlin/issues/1147).

## Related

- [Tmux Session Status](../features/tmux-session-status.md) — narrative and
  design history
- [`azlin list` command page](../../docs-site/commands/vm/list.md) — flags,
  columns, troubleshooting
- [Doc-Code Reference Check](./doc-code-reference-check.md) — the CI gate that
  keeps the symbols named above from going stale
