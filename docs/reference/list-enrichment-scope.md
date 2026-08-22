# `azlin list` Enrichment and Output Safety Reference

The **design intent** behind the enrichment columns of `azlin list`: why the
gate that guards them is what it is, and what azlin guarantees about the bytes
it prints.

For the narrative version see
[Tmux Session Status](../features/tmux-session-status.md). For flags, columns
and troubleshooting, see the
[`azlin list` command page](../../docs-site/commands/vm/list.md).

## What this file is, and is not

This file records **why** the rules below are the rules — the failure each one
was written against, and the reasoning a change has to preserve. It does not
restate facts the code already holds: which flag turns on which column, what a
listing costs in `az` invocations, which columns are quoted. Those change with
the code, a copy here would not, and the doc-code reference gate checks only
that a named symbol *exists* — never that a sentence about it is true.

Where a rule is enforced, the enforcing test is named. Prefer reading the test
over trusting the prose.

```bash
cargo test --manifest-path rust/Cargo.toml -p azlin --bin azlin cmd_list
```

## Rule 1: enrichment is gated on subscription identity, not count alone

A **bastion-routed** enrichment probe addresses a VM by an ARM resource id
built from the subscription the CLI is currently on, and `VmInfo` carries no
subscription of its own — so such a probe reaches the right machine only when
the listing was read from the same subscription the probe will be built
against. `collect_disk_configs` is scoped by the CLI's ambient subscription in
the same way, without building an id at all.

`probe_route`'s `Direct` branches are narrower: they carry an address taken
from the listing itself, so the *connection* goes to the right host whichever
subscription the CLI is on. That does not make the row safe. `collect_disk_configs`
matches ARM rows **by VM name** within the ambient subscription, and passes no
`--subscription`, so a directly-routed VM read from another subscription can
still be described by a same-named VM's disk layout. Misattribution is not
confined to the bastion path.

**A count of one does not imply safety. The one subscription queried must also
*be* the one the probes will use.**

Identity was *added* to the gate, not substituted for the count. A listing
spanning more than one subscription is still withheld on count alone, because no
single probe subscription can be correct for all of them. What changed is that
passing the count is no longer sufficient.

Counting by itself was the earlier rule, and it was wrong in an ordinary case: a
single context pinning a *different* subscription gives a count of one and
passes, after which every probe runs against a resource id in the CLI's
subscription. Three routine `--all-contexts` paths reach that state — `azlin
context create` does not activate the new context, `--contexts` can select a
single non-active context, and a partial listing failure collapses a
two-subscription run to one. (All three require `--all-contexts`: on a plain
`azlin list` no context subscriptions are collected and `resolve_enrichment`
returns early.)

Where a resource group and VM name exist in both subscriptions — which templated
IaC naming makes ordinary rather than exotic — the probe succeeds against the
**wrong machine**, and that host's sessions, health and processes render under
this listing's rows. The failure is silent and confidently wrong, which is worse
than an empty column.

### Why a mismatch has three distinct causes

Identity is compared trimmed and case-insensitively: a subscription id is a
GUID, which is case-insensitive as an identifier, and the queried side comes
from a hand-edited context file while the probe side comes from `az`. Withholding
on a casing difference alone would drop the columns an operator asked for and
blame a mismatch that does not exist.

`resolve_enrichment` therefore distinguishes three reasons to withhold — more
than one subscription queried; exactly one that differs and is GUID-shaped; and
exactly one that differs and is *not* GUID-shaped — and names the applicable one
in the note. The third is the one worth knowing about. `az` accepts a
subscription name as well as an id, and nothing on the context write path
requires a GUID (`looks_like_subscription_id` is what tells them apart), so a
context may name the very subscription the CLI is already on, and a name never
equals a GUID. Reporting that as a mismatch would assert as fact something
unknown. The note says what is actually knowable and what would make it
knowable, rather than inventing a cause.

### One call produces both the gate and the note

`resolve_enrichment` returns the decision and the operator-facing note together.

They were previously computed separately, and they drifted: the note recited a
fixed string naming "bastion, tmux and health" while `--show-procs` ran anyway,
so the screen claimed to have withheld something that had in fact executed. The
note now names what was actually withheld, so it can neither over-claim nor stay
silent about a collector that was skipped.

**Every subscription-scoped collector takes this one gate.** A collector that
carries its own copy of the threshold is the bug this structure exists to
prevent. `Latency` is the deliberate exception and does not take it:
`collect_latencies` is a bare TCP connect to port 22 that builds no ARM id and
addresses no subscription, so it has nothing to be wrong about.

When the gate withholds, `resolve_enrichment` returns an `Enrichment` with every
field false. Callers test `enrichment.any()`, so a withheld listing runs none of
the gated collectors and performs **no bastion lookup at all** — the cheapest
listing, not the most expensive one. It is not literally free: `--with-latency`
still runs (it is outside the gate, as above), and rendering any row still calls
`query_vm_size_specs`, which shells out to `az vm list-sizes`. That result is
cached per location **only when the call succeeds and parses** — so where `az`
fails or times out there is no negative cache and the listing pays the call, and
its timeout, once per row.

**The variable that carries this decision is named `enrichment_withheld`, not
`cross_subscription`.** The earlier name invited exactly the inference this rule
refutes: a note is also produced for a *single* subscription that merely
differs, so reading the flag as a count test gets the behaviour wrong.

## Rule 2: routing is discovered once per command

Bastion routing is a pure function of the VM list. It is computed once by the
caller and lent to every collector as a shared `BastionMap`, keyed by
(resource group, region).

`collect_tmux_sessions`, `collect_health_data`, `collect_storage_status` and
`collect_procs` each used to call `discover_bastions_async` for themselves, so
`azlin list --with-health --show-procs` re-derived the same answer once per
collector per resource group and the operator watched the spinners repeat it.
Each `az` invocation costs process start plus an ARM round trip, so the waste
grew with the number of resource groups in the listing.

There are **two sweeps — one for the `Azure Bastion Hosts` table, one for
routing — and they share one cache.** Treating them as independent is how the
counts in the older docs went wrong. The table sweep's answers, cached failures
included, are handed down through `reuse_or_look_up`, so a group that already
refused is not asked again. Routing's predicate selects, from any real ARM
listing, a subset of the groups the table sweep covers, so where the table
renders, routing asks `az` nothing. (The two predicates are not literally
nested: the table sweep drops VMs with an empty resource group and routing does
not, so the subset relation holds for every listing seen in practice but is not
enforced anywhere.)

The table sweep is gated on `enrichment_withheld` — the same identity decision
as Rule 1, **not** a subscription count. A listing whose enrichment was withheld
renders no bastion table, because the note that explains the withheld columns
explains the absent table too.

Callers running a single collector go through `discover_bastions_async`, which
starts from an empty cache and delegates to `discover_bastions_async_reusing` —
the shared body, and where the `spawn_blocking` hop and the discovery-failure
warning live. `cmd_list` calls the `_reusing` form directly because it is the
caller that has a cache to pass.

## Rule 3: probes are bounded

`collect_tmux_sessions` holds at most `MAX_CONCURRENT_SSH_PROBES` SSH probes in
flight.

The probe set previously had no limit: one `ssh` child per listed VM, each
holding a piped stdout and stderr. A wide enough listing exhausts the process
descriptor limit, `cmd.output()` returns `EMFILE`, and that error is reported
only under `--verbose` — so on the default path those VMs simply render as
having no sessions. Silent degradation that worsens with fleet size, which is
the direction a fleet tool is used.

**The bound is enforced in that one collector, not globally.** The other probing
collectors are serial today and the listing awaits each in turn, so the process
total happens to stay bounded — but nothing enforces that, and parallelising
another collector would reopen the descriptor exhaustion this rule closed.
Anything made concurrent here needs its own share of the same limit.

## Rule 4: a failure that changes the output is reported

The governing rule: **a column that is empty because something failed should be
distinguishable from a column that is empty because there was nothing to
report.**

- A non-zero `az` exit from `detect_bastion_hosts` is an error, not an empty
  result. Returning success-with-nothing made "no authorization on this
  resource" indistinguishable from "this group has no bastion", and the
  aggregated notice that should have named it was fed only by the spawn-failure
  path — so it was unreachable in the case that actually happens.
- The **bastion-discovery** warnings are returned to the listing and printed
  by it after its spinner is cleared. A line written from inside
  `spawn_blocking` while the progress indicator redraws is overwritten before
  it can be read. This is not yet true of every warning: the tunnel-cap,
  tunnel-failure and session-cap messages still `eprintln!` from inside a
  collector while a spinner is live, and can still be overwritten.
- A bastion lookup answered with unparseable output is reported rather than
  recorded as an answer of "none". A JSON `null` and empty output both still
  mean "no bastion here" — that is how it is ordinarily spelled.
- A bastion at a location the coordinate allowlist rejects (an ARM response
  giving `"East US"` in display form) is **named**, not silently dropped.
- The same-name collision warning is printed **once by the listing** and covers
  every collector that skips a colliding VM — tmux, health, storage, processes
  and latency. Printing it from the tmux collector meant
  `--no-tmux --with-health --show-procs` withheld the same VMs from the
  remaining collectors and said nothing.
- The bastion-lookup warning reports **one line** — the line that names the
  failure, skipping blanks and `az` advisory banners, falling back to the banner
  when that is all `az` said. An imprecise cause beats silence; a multi-line
  error blob that lets an extension warning be read as the cause of an
  authorization failure does not.
- `collect_storage_status` ignores the probe only when it exited non-zero **and
  printed nothing** — the same verdict `probe_vm_storage` reaches for the same
  script under `azlin disk check`. A non-zero code alone is deliberately not
  enough: on the bastion route that code belongs to `az network bastion ssh`,
  not to the remote script, so a wrapper that exits non-zero after delivering
  complete output would blank the `Storage` column here while the per-VM
  command still reported a verdict for the same machine. That per-VM-versus-
  fleet split is the failure `disk_layout` is shared to prevent. Nothing is
  lost by parsing anyway: `parse_disk_probe` returns `Unknown` unless it finds
  the trailing provisioning line *and* the expected number of disk lines, and
  the probe emits that line last — so a script that died early yields no
  verdict on its own.

**Where this rule is not yet met.** `collect_procs` reports unevenly, and the
two routes disagree about what a failure even is.

- **Direct route.** Spawn failure and a non-zero exit are distinguished, and the
  probe prints the first reportable line of `stderr`, so a timeout and a refused
  key are usually told apart. Usually, not always: `first_reportable_line` skips
  banner lines by matching `WARNING:` case-sensitively — the spelling `az` uses
  — so an `ssh` notice spelled `Warning:` is not skipped and is reported as the
  cause instead. And all of it is behind `--verbose`, so the default path shows
  an empty cell either way — the condition the governing rule names.
- **Bastion route.** A command that reached the VM and exited non-zero is
  dropped with **no diagnostic at any verbosity**. A timeout is not that case:
  `run_with_timeout` returns an `Err`, which is treated as a transport failure,
  retried at the private address, and — if that has nowhere to go — reported on
  the **default** path.

So the two failures an operator most wants to tell apart are handled by opposite
mechanisms depending on how the VM was reached. Stating this is the point: the
rule is the target, and this is the distance left. Closing it is tracked in
[#1152](https://github.com/rysweet/azlin/issues/1152).

### Routing decisions are pure and testable

`probe_route` decides `ProbeRoute::Bastion`, `ProbeRoute::Direct` or
`ProbeRoute::Unreachable` before any connection is attempted, so it is unit
tested rather than inferred from behaviour. A VM with no public address and no
bastion route still routes direct to its private address, preserving the
behaviour operators on a VPN or peered network already had.

Where a fallback exists, a bastion route that fails to **carry** the command — a
transport error — retries once at the private address. A command that reached the
VM and exited non-zero is that VM's own answer and is **never** retried: a retry
could land on a different host and report its processes under this VM's name.
That second half is the invariant. The fallback itself is uneven, and in three
shapes. `collect_procs` reruns the failed command at the private address.
`collect_health_metrics` does that too and then latches the tunnel as dead, so
that VM's *remaining* probes go direct without attempting it -- it runs several
commands per VM, and paying the bastion timeout on each would cost the whole
listing (with no usable address to fall back to, it retries the tunnel instead
of inventing a failure). `collect_tmux_sessions` does not retry at all: it
swaps in the direct address *before* the command is issued, and only when the
tunnel failed to **open**. `collect_storage_status` simply gives up.

`probe_ssh_opts` builds the shared timeout, batch-mode and identity options for
the collectors that spawn `ssh` directly. It **omits** `-i` entirely when the key
path is not usable. The call sites previously spelled that fallback as an empty
string, which hands `ssh` an empty identity argument rather than no argument at
all; `ssh` then failed on a missing identity file and a reachable VM was
reported unreachable.
`probe_ssh_opts_omits_the_identity_flag_rather_than_passing_an_empty_one` pins
the current behaviour.

## Rule 5: what azlin guarantees about printed bytes

Azure-supplied names are chosen by anyone with write access to the subscription,
and text read off a listed host is chosen by whoever controls that host. The
`azlin-session` tag is in the **default** table, so no extra flag is needed for
tag content to reach a terminal.

### Sanitisation

`sanitize_remote_text` strips the character classes that let a value forge
structure rather than occupy a cell: `Cc` (C0 controls, `DEL`, the 8-bit C1
range including CSI), the whole `Cf` format block (bidirectional overrides,
`U+00AD`, `U+061C`, word joiners, the tag block), and `Zl`/`Zp`.

`Zl` and `Zp` matter because `is_control` does not report them, yet every
terminal and text consumer breaks a line on them — which defeats the
no-forged-rows rule the function exists to enforce.

Alignment is the second thing this protects. Truncation pads a cell to a count of
characters, and a control character is a character that occupies no width — so an
unsanitised name silently shifted every border to its right. (The count is of
`char`s, not display columns, so a CJK or emoji name can still misalign. That is
a cosmetic residual, not a forgery one.)

**Residual:** stripping is followed by truncation to `MAX_REMOTE_TEXT_LEN` with
no marker, so two VMs sharing a long enough prefix render identically in the
column an operator reads to pick a connection target — the tail of the same
spoofing class, narrowed to values that must first collide on that prefix.

### CSV: two properties, composed on the same value

Sanitising is not escaping, and neither substitutes for the other. They close
different failures, and a CSV cell needs **both**:

- **Strip**, by `sanitize_remote_text`, closes **record** injection — a newline
  (or `U+2028`) ends the row early and what follows parses as a VM of someone
  else's design.
- **Quote**, by `csv_field`, closes **field** injection — a comma ends the cell
  early and shifts every later column by one, which a consumer reads as valid
  data for the wrong VM.

A comma is not a control character, so stripping cannot close the second. A
quote is not a sanitiser, so quoting cannot close the first. A session literally
named `a,b`, or an `azlin-session` tag carrying a comma, is field injection; the
same tag carrying `U+2028` is record injection.

**The composition is the contract, not either half.** `csv_field` quotes per
RFC 4180 — wrapping the value and doubling any embedded quote — when the value
contains a comma, a quote, `CR` or `LF`, and it is applied to the text
`sanitize_remote_text` already produced, never to the raw Azure value. A tag
carrying a control character *and* a comma must come out both stripped and
quoted; that single case is what distinguishes a correct implementation from one
that kept only the half it was last edited for.

**The rule is: every free-form field on the row is quoted.** Do not maintain a
list of which columns those are — read `csv_row`, which is the list.

`csv_row_quotes_every_free_form_field` enforces it, and enforces it *on the row*:
it renders the widest row the writer emits from a VM whose every *free-form*
Azure-supplied value on that row contains a comma, parses the result with an
independent RFC 4180 splitter, and asserts the field count equals
`csv_headers`' column count. It then checks each value survived — by equality
for the fields the writer passes through unchanged, and by containment for the
two it reformats (`OS`, which `format_os_display` may wrap or replace outright,
and the address, which gains a routing suffix). Field count alone would be
satisfied by stripping the commas, which would silently rename a VM.

This was checked by mutation, not assumed: removing each of the writer's
`csv_field` calls in turn breaks the build in one case (the return type stops
matching) and fails this test in every other. Adding a free-form column that
forgets to quote fails it the same way.

This is deliberately stronger than the tests that drive `csv_field` in
isolation. Those pin the helper; only a test that renders a row can pin that the
writer calls it, and that gap is what let a stale claim about this control stand
while every test stayed green.

**Not handled: spreadsheet formula injection.** A value beginning with `=`, `+`,
`-` or `@` is still evaluated on open, and quoting does not change that — a
quoted `"=1+1"` is still evaluated. The mitigation is on the import side: open
the file through a text import rather than directly, or prefix suspect values
with `'`. **`-o json` is not a workaround** — see below.

### JSON applies neither property, deliberately

`render_json` builds a fresh object *per VM* with azlin's own field names, some
of them computed rather than echoed from ARM, and serialises them under the
`vms` key of the result envelope (`#1146`; the envelope's shape is
`docs-site/commands/vm/list.md`'s subject, not this file's). It applies neither
`sanitize_remote_text` nor any quoting beyond what `serde_json` requires for
well-formed JSON. Its consumer is a program that parses JSON, for which
`serde_json`'s escaping is the correct and sufficient contract.

What that does and does not mean:

- Every Azure-supplied string on the object reaches JSON **unsanitised** — the
  VM name, resource group, region, SKU, OS offer, both addresses and the
  `azlin-session` tag. The table and CSV writers strip these; this one does
  not. `resource_group` is worth calling out separately: no other list *column*
  carries it, so JSON is the only path that prints it unsanitised. (It does
  reach the table path, sanitised, through the bastion-lookup failure warning.)
  Read `render_json` for the current set rather than trusting this list.
- `serde_json` escapes `0x00`–`0x1F`, `"` and `\`, so `U+007F`, the C1 range and
  `U+2028` are emitted **raw**. Rendering JSON safely on a terminal is the
  consumer's problem, not azlin's — but a pipeline that `jq -r`s a field onto a
  terminal is printing unsanitised Azure-supplied text.
- The values read off a listed host are **not** in that category, for reasons
  that are worth stating because they are easy to get backwards. The `Tmux`
  session names are sanitised at collection, so they are already clean by the
  time any writer sees them. The health agent status is not free-form at all:
  `classify_agent_status` collapses the host's `systemctl is-active` output to
  one of `"OK"`, `"Down"` or `"N/A"`, and a VM with no reading at all gets `"-"`
  from `default_metrics`. The sanitising and quoting the CSV writer
  applies to it are defence in depth against it becoming free-form later, not a
  live control — and JSON's lack of them is correspondingly not a live hole.

This is still why `-o json` is not the answer to the CSV formula-injection
residual: it applies neither sanitisation nor quoting, so it has fewer
guarantees than CSV, not more.

### Session names: two different validators

`sanitize_remote_text` is used on the **display** path — it strips, and keeps
every legitimate name. `parse_session_name` is used where a name **addresses** a
VM (`match_session_in_map` and session restore) and is an allowlist: ASCII
alphanumeric, `_` and `-`, with a length cap.

Applying the allowlist on the display path would silently drop names tmux itself
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

**Resource-group names are not covered, at three sites** — and the two that run
on a bare `azlin list` are not the one that is easiest to notice:

- `detect_bastion_hosts` passes a resource group into `az network bastion list`
  with no validator. This is the one that runs by default: `cmd_list` calls it
  per group to draw the `Azure Bastion Hosts` table, and the routing sweep
  reaches it again through `reuse_or_look_up` — the two sweeps of Rule 2.
- `resolve_bastion_dns_name` passes a resource group into
  `az network bastion show` beside a bastion name that **was** allowlisted
  upstream. It is on the default path too, reached through tmux collection and
  `get_or_create_tunnel`. The asymmetry on a single argument vector is the
  point: one argument is validated and the one next to it is not.
- `collect_disk_configs` passes each VM's resource group straight into an
  `az vm list --resource-group` invocation, also with no validator. This one is
  **not** on the default path: it is reached only through
  `collect_storage_status`, which is gated on `enrichment.health`. (It is also
  why `--with-health` costs ARM queries as well as SSH probes — storage reads
  disk layout out of ARM before probing the host.)

In all three the value arrives from the ARM listing rather than from user input,
and `az` is spawned with an argument vector rather than a shell line — so there
is no shell to inject into — but the leading-dash reading that `valid_bastion_name`
exists to prevent is not prevented there, and Azure permits a leading hyphen in
resource-group names. Extending the allowlist to resource groups at all three
sites is tracked in [#1147](https://github.com/rysweet/azlin/issues/1147).

The durable fix is to validate at the `az` boundary rather than per call site, so
a newly added invocation cannot omit it.

## Related

- [Tmux Session Status](../features/tmux-session-status.md) — narrative and
  design history
- [`azlin list` command page](../../docs-site/commands/vm/list.md) — flags,
  columns, troubleshooting
- [Doc-Code Reference Check](./doc-code-reference-check.md) — the CI gate that
  keeps the symbols named above from going stale
