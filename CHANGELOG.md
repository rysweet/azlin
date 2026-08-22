# Changelog

All notable changes to azlin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **`azlin list` discovers bastion routing once per command instead of once per
  enrichment collector** — `collect_tmux_sessions`, `collect_health_data` and
  `collect_procs` each discovered routing for themselves, so
  `azlin list --with-health --show-procs` ran `az network bastion list` three
  times per resource group to compute the same `BastionMap` three times, and the
  operator watched three spinners re-derive one answer. `az` costs about 0.9s of
  process start alone before the ARM round-trip, so a five-resource-group
  listing spent at least nine seconds on ten redundant lookups. Discovery is a
  pure function of the VM list, so it is now done once by the caller and lent to
  every collector. Callers that run a single collector go through the new
  `discover_bastions_async`, which is also where the `spawn_blocking` hop and
  the discovery-failed warning now live.
- **…and on the default path it costs no `az` call at all** — collapsing three
  collector sweeps into one still left that one sweep next to another. Table
  output draws an "Azure Bastion Hosts" table, which looks bastions up across
  every resource group in the listing, and the groups routing needs are a
  *subset* of those — so the ordinary `azlin list`, with no flags, ran the table
  sweep and then asked `az` the same questions again for routing. The table's
  answers are now carried forward through `BastionLookups` and routing reads
  them, so a default listing performs one sweep rather than two and the counts
  above become honest about the command rather than about the collectors alone.
  A resource group whose lookup was *refused* is carried forward too: re-asking
  pays a second timeout on a group that has already said no, and reports one
  failure through two different warnings. `-o json` and `-o csv` draw no table,
  so they sweep for routing alone — one lookup per resource group holding a
  bastion-only running VM, and none at all when no collector was asked for.
- **Bastion discovery no longer deep-clones the VM list to name a few resource
  groups** — `discover_bastions_async` cloned the whole `Vec<VmInfo>`, tags map
  and all, across the `spawn_blocking` boundary in order to derive the deduped
  `Vec<String>` of groups that is the only thing discovery reads from it. The
  group list is computed before the hop and only it crosses. Same answer,
  proportional to the number of resource groups instead of the number of VMs.
- **The list table sanitizes each VM's display text once instead of twice** —
  under `-w` the column-width pass built a `VmDisplayText` per VM to measure the
  widest name, dropped it, and the row loop built the same six sanitized strings
  again. They are built once and shared, which also removes the possibility of
  sizing a column against text other than the text that gets printed.

### Fixed
- **`azlin list --show-procs --all-contexts` no longer attributes one
  subscription's processes to another's VMs** — bastion, tmux and health
  enrichment are all subscription-scoped, because they probe by an ARM id built
  from the queried subscription and `VmInfo` carries no subscription of its own.
  A listing spanning several subscriptions therefore skips them and says so.
  `--show-procs` was missing that gate: it ran anyway, against ARM ids in
  whichever subscription the CLI was on. With the IaC-templated dev/prod name
  pairs this tool is pointed at, the `ps` output of a same-named VM in one
  subscription rendered under a row read from another — while the note on screen
  told the operator enrichment had been omitted. All three collectors now take
  the same gate -- and the gate and the note are returned from one call
  (`resolve_enrichment`), because they were written separately and that is
  exactly how they drifted. The note now names what was actually withheld
  rather than reciting a fixed string, so it can neither claim to have omitted
  something that in fact ran nor stay silent about something that did not.
- **SSH probes are bounded, and a failed process probe says so under
  `--verbose`** — the probe `JoinSet` had no limit: one `ssh` child per listed
  VM, three pipe fds each, so a subscription with a few hundred running VMs ran
  into the default 1024-fd limit and `cmd.output()` returned `EMFILE`. That was
  reported only under `--verbose`, so on the default path those VMs rendered as
  having no sessions -- silent degradation that worsens with fleet size, which
  is the direction a fleet tool is used. At most 64 probes are now in flight.
  Separately, the process probe collapsed spawn failure, timeout, refused auth
  and non-zero exit into a blank cell with no diagnostic at all, leaving no way
  to tell an idle VM from an unreachable one; the tmux probe had said this
  under `--verbose` all along.
- **The `Storage` column shares the one bastion map and takes the same
  subscription gate** — it arrived (with the column itself) discovering routing
  for itself, which is the cost this change exists to stop paying: a fifth
  `az network bastion list` per resource group to recompute a map the caller
  already holds, and a lookup failure with nowhere to report itself now that
  discovery hands its warnings back. It is read through an ARM id built from
  the probe subscription like its three siblings, so it is gated with them
  rather than on a second copy of the threshold.
- **Enrichment is gated on which subscription probes can reach, not on how many
  the listing read** — the gate counted subscriptions, and probes are built from
  the subscription the CLI is on rather than the one a context named. A single
  context pinning another subscription therefore gave a count of one and passed:
  every probe then ran against an ARM id in the CLI's subscription. Reachable
  three ordinary ways — `azlin context create` does not make the new context
  active, `--contexts` can select a single non-active context, and a partial
  listing failure collapses a two-subscription run to one. Where the resource
  group and VM name exist in both, which shared IaC naming makes ordinary, the
  probe succeeds against the *wrong machine* and its sessions, health and
  processes render under this listing's rows. The gate now compares identity,
  and the note names both subscriptions. (The note also read "bastion routing
  are subscription-scoped" whenever nothing else was withheld.)
- **A failed bastion lookup is no longer erased by the spinner that was drawn
  over it** — `detect_bastion_hosts` printed its own warning and returned
  `Ok(empty)` whenever `az` merely exited non-zero, which is how a bastion
  lookup actually fails: no authorization on the resource, a missing extension,
  a subscription the credential cannot see. Two things followed. The line was
  written from inside `spawn_blocking` while `indicatif` redrew its spinner
  every 120ms, so it was overwritten before it could be read; and because
  `Ok(empty)` is indistinguishable from "this group has no bastion", the
  warning list the caller prints after clearing that spinner came back empty.
  The aggregated "could not list bastion hosts in resource group(s) …" notice
  was unreachable for the same reason — it was fed only by the `Err` arm, which
  `az` reached only when it could not be spawned at all. Every bastion-only VM
  in the group showed no tmux, health or process data with nothing on screen
  explaining why. A non-zero exit is now an `Err`, so the report travels to the
  caller and is printed where it survives.
- **A bastion lookup that `az` answers with something other than a JSON array
  is no longer read as "no bastion"** — a zero exit with unparseable stdout was
  swallowed by `unwrap_or_default()`, degrading the whole group silently. An
  answer that cannot be read is now reported rather than recorded as an answer
  of "none". A JSON `null` and an empty stdout both still mean "no bastion
  here", because they are how that is ordinarily spelled.
- **A bastion Azure reports at an unusable location is named instead of
  dropped** — the coordinate allowlist admits only ASCII alphanumerics in a
  region, so an ARM response giving a location in display form ("East US")
  removed the group's only route while the adjacent duplicate-bastion branch
  warned about far less. Losing a route is now narrated like every other
  degradation on this path.
- **The same-name collision warning covers every enrichment column, not just
  tmux** — it was printed from the tmux collector, so `--no-tmux --with-health
  --show-procs` withheld exactly the same VMs from three other collectors and
  said nothing. It is now printed once by the listing, after its spinner is
  cleared, and covers tmux, health, processes and latency alike.
- **The bastion-lookup warning reports one line, and the line that names the
  failure** — it previously printed the whole trimmed `stderr` blob, so a
  multi-line `az` error could occupy the screen, and `az`'s own `WARNING:`
  advisory banners could be read as the cause (blaming a missing extension for
  what was an authorization error). It now skips blank lines and banners to
  reach the line that names the failure, falling back to the banner when that
  is all `az` said — an imprecise cause still beats silence.
- **`sanitize_remote_text` no longer lets `U+2028`/`U+2029` through** — they are
  `Zl`/`Zp`, not `Cc`, so `char::is_control` missed them while every terminal
  and text consumer still breaks a line on them, defeating the no-forged-rows
  rule the function is built around. The invisible-character filter now covers
  the whole `Cf` block rather than the handful of code points the Trojan Source
  write-ups name (`U+061C`, `U+00AD`, the word joiners and the tag block were
  all getting through). The C1 range needed no change and was verified rather
  than assumed: it is `Cc`, so the 8-bit CSI was already handled, and there is
  now a test pinning that. Coverage was then checked exhaustively against
  Unicode 16 rather than asserted: every assigned `Cf` code point is stripped,
  and nothing outside `Cf`/`Zl`/`Zp`/unassigned is caught, so no legitimate
  name loses a character.
- **The `azlin list` table and CSV no longer print Azure-supplied names
  unsanitized** — the warnings and the bastion table were fixed above, but the
  table `azlin list` prints on every run was not: the VM name, the region, the
  SKU, the OS offer and the `azlin-session` tag all reached the terminal exactly
  as Azure returned them. The tag is in the *default* table, so no `-w` was
  needed to be exposed. A name carrying `ESC [ 2 K` and a carriage return erases
  the row that reports it and prints whatever follows in its place, so the
  operator reads a fleet that does not exist; in CSV a newline in a name ended
  the record early and forged an extra row in output a script goes on to parse.
  All of them are sanitized once now, in one place per VM, shared by the table
  and CSV writers. Alignment was the second casualty: `trunc` pads a cell to an
  exact count of *visible* columns, and a control character is a `char` that
  occupies none, so an unsanitized name silently shifted every border to its
  right. JSON output is deliberately unchanged: its consumer is a machine and
  must keep the exact bytes Azure returned, so escaping there would corrupt the
  contract rather than protect anyone. (An earlier draft of this note claimed
  `serde_json` escapes control characters so a terminal never interprets them.
  That is only partly true — its escape table covers `0x00`–`0x1F`, `"` and `\`,
  so `U+007F`, the C1 range and `U+2028` are emitted raw. Rendering JSON safely
  is the terminal's problem, not azlin's.) CSV record injection is closed;
  *field* injection is not — fields are still emitted unquoted, so a comma in an
  Azure name shifts every column after it by one. That is tracked in #1133,
  because the fix is to quote per RFC 4180, not to strip more characters.
  Found by outside-in testing against the real binary, which also confirmed the
  pre-fix CSV really did emit three records where two were correct.
- **Terminal escape sequences in Azure-supplied names no longer reach the
  terminal through `azlin list` warnings or the bastion table** — session and
  process names read off remote hosts were sanitized, but resource group, VM and
  bastion names, and the `az` error text that quotes them back, were not.
  Resource names are chosen by anyone with write access to the subscription, and
  `--verbose` printed the whole `anyhow` chain of a tunnel failure raw. Taking
  the first line of an error blocks a *fabricated second warning*; it does
  nothing about a cursor-movement sequence rewriting the line that is printed.
  `bastion_lookup_failure_warning`, `tunnel_failure_warning`,
  `collision_warning`, the verbose tunnel-error line, the "Azure Bastion Hosts"
  table and the failed-resource-group warning all sanitize now. A warning is not
  a safer place to print an escape sequence than a table cell is. Outside-in
  testing against the real binary then found the one site the audit had missed
  and the one that matters most: `detect_bastion_hosts` prints its own warning
  and returns `Ok(empty)` when `az` exits non-zero, so *that* — not the `Err`
  arm `bastion_lookup_failure_warning` guards, which is only taken when `az`
  cannot be spawned at all — is the failure an operator actually sees, and it
  echoed `az`'s stderr verbatim. It sanitizes the group name and the reported
  line of `az`'s stderr now. Review of that change closed four more sites the
  sweep had not reached: the duplicate-bastion warning (which interpolated a
  resource group that passes no validator at all), the verbose
  "no reachable address" line, the tmux session-cap warning — which is on the
  *default* path and remotely triggerable, since a compromised VM can open
  enough sessions to force it — and the `--all-contexts` header and
  list-failure warnings.
- **A non-UTF-8 SSH key path no longer reports reachable VMs as unreachable** —
  the three SSH probe sites each spelled the identity fallback
  `key.to_str().unwrap_or("")`, which hands `ssh` an empty `-i` argument rather
  than omitting the flag. `ssh` then failed on a missing identity file and the
  probe was indistinguishable from an unreachable VM. The shared timeout, batch
  mode and identity options now come from one `probe_ssh_opts` helper, which
  omits `-i` entirely when the path is not usable — the same state as having no
  key at all.
- **`azlin list` no longer reports zero tmux sessions for every bastion-only VM
  but one** (the tunnel keying shipped in `v2.6.126-rust.12ccf60`; recorded
  retroactively together with the gaps found reviewing it) — an Azure Bastion
  tunnel is opened against a single target VM's ARM resource id, so it reaches
  exactly that one VM. `collect_tmux_sessions` nevertheless kept one port per
  *bastion*, so when two or more VMs with no public IP sat behind the same
  regional bastion, every SSH probe was sent through whichever VM's tunnel was
  created first. That VM's sessions were reported correctly and the others
  silently showed none. Because the probe landed on a real host that answered,
  there was no error to see; and because the winner was decided by iteration
  order, the bug stayed invisible until a second bastion-only VM appeared in
  one region. It was a regression from #999, which replaced the per-VM tunnel
  pool with the native tunnel path and collapsed the port map to one entry per
  bastion. `plan_bastion_tunnels` now emits one tunnel per VM, and every map
  that decides *which host a command runs on* is keyed by the VM's full
  resource id rather than its name, so plan, lookup and tunnel-registry keys
  cannot collide (#1127)
  - The plan's dedup key and the probe-loop lookup are both built by
    `build_vm_resource_id`, which is now the sole producer of the string the
    tunnel registry uses as its key — two hand-rolled copies of that format
    could diverge and leak a fresh tunnel per VM per invocation
  - `BastionTunnelPlan` carries the bastion's own resource group alongside the
    target VM's, so the `(bastion name, resource group)` pair handed to
    `get_or_create_tunnel` is self-consistent. Bastion names are commonly
    templated per region, so passing the VM's resource group with the bastion's
    name could resolve to a same-named bastion in a different resource group
  - A tunnel that cannot be opened now prints a warning on stderr instead of
    only under `--verbose`. The VM's row previously looked identical to a VM
    with no sessions. The warning carries the VM name and the first line of
    the error; the full error chain is still `--verbose`-only, so nothing new
    is written to CI logs
- **`azlin list` now discovers bastions in every resource group it lists, not
  just the first VM's** — bastion detection ran one `az network bastion list`
  against the resource group of whichever VM happened to be first in the
  result set. Under `--show-all-vms` that is an arbitrary choice: a
  bastion-only VM in any other resource group had no bastion in the map, was
  skipped without a tunnel, and rendered `-` in the `Tmux` column. This is
  the same first-iterated-wins failure as the tunnel bug one call frame up, and
  it hid behind it. Bastion coordinates now live in a `BastionMap` keyed by
  resource group *and* region, populated by one `az network bastion list` per
  distinct resource group that actually contains a running VM with no public
  IP — one call on the common single-resource-group path, none at all when
  every VM has a public IP. A resource group the caller lacks
  `Microsoft.Network/bastionHosts/read` on degrades that resource group alone;
  the rest of the listing is unaffected. Bastion coordinates returned by `az`
  are validated before use: entries with an empty name or location, or a name
  beginning with `-`, are dropped rather than passed into an argument vector
  (#1127)
- **The `Azure Bastion Hosts` table lists the bastions of every resource group
  in the listing** — the table above the VM rows was built from a single `az
  network bastion list` against `all_vms.first()`'s resource group, so a
  listing spanning resource groups displayed one group's bastions and omitted
  the others with no indication that it had. This is the routing bug's twin in
  the display path: same first-iterated-wins shape, same silent omission, and
  it survived the routing fix because the two paths derive their resource
  groups independently. The table is now built from every distinct resource
  group in the listing, deduplicated so a bastion serving VMs in several groups
  is listed once, and sorted so the output does not depend on VM order. Unlike
  the routing lookup this is deliberately not filtered by power state or public
  IP — the table documents the bastions in the scope the user asked about,
  which does not change because a VM happens to be deallocated. A resource
  group whose lookup fails is named on stderr rather than dropped, so an
  incomplete table cannot be mistaken for a complete one (#1127)
- **A bastion lookup that fails now says so instead of reporting zero
  sessions** — `discover_bastions` took `detect_bastion_hosts(...)` through
  `unwrap_or_default()`, so a resource group the caller lacks
  `Microsoft.Network/bastionHosts/read` on, or a transient `az` failure,
  produced an empty bastion set for that group. Every bastion-only VM there
  then fell back to its own private IP, which the operator usually cannot
  route to, and reported zero tmux sessions — the original #1127 symptom
  arriving through the error path. The resource group and the first line of
  the cause are now named on stderr. The same applies when bastion discovery
  itself does not complete: an empty map means "we never found out", not "there
  are no bastions" (#1127)
- **A bastion is no longer lost to an Azure casing difference** — the bastion
  map is *inserted* with the bastion's location as `az network bastion list`
  reports it and *looked up* with the VM's location as the VM listing reports
  it. Those are two different commands, Azure is not consistent about casing,
  and resource group names are case-insensitive to begin with; the raw string
  comparison therefore dropped the bastion on a casing difference alone, giving
  the same silent zero. Both sides now go through one `bastion_key` helper that
  case-folds the pair (#1127)
- **`azlin list` says when a VM has more tmux sessions than it shows** — the
  per-VM cap silently kept the first 20, which renders as "this VM has 20
  sessions". The count not shown is now reported on stderr, matching the
  tunnel-cap behaviour; a cap that hides what it dropped is the same
  confidently-wrong answer this PR exists to remove (#1127)
- **Remotely-collected text can no longer reorder the row it is printed in** —
  `char::is_control` covers only the `Cc` category, so stripping control
  characters removed the ESC that begins an ANSI sequence but let
  `U+202E RIGHT-TO-LEFT OVERRIDE` and its relatives through; those are `Cf`.
  In a table cell such a character reverses the rendering of everything after
  it, which is enough to make one VM's row read as another's. Bidirectional
  overrides, isolates, zero-width spaces and the BOM are now stripped alongside
  control characters, finishing the defense the control filter starts (#1127)
- **`azlin list` omits tmux, health and process data for VMs whose names
  collide** — those results are keyed by VM name for display, so two running
  VMs with the same name in different resource groups would render one VM's
  sessions and processes against the other's row. Azure only guarantees name
  uniqueness within a resource group, so `--show-all-vms` and `--all-contexts`
  can produce that collision. Enrichment is now skipped for every VM sharing a
  colliding name and a note naming them is printed on stderr, following the
  cross-subscription precedent from #1090. Showing the wrong VM's processes is
  worse than showing none, and a JSON consumer never sees the stderr note at
  all. The row itself still lists — only the remotely-collected columns are
  withheld (#1127)
- **`azlin list` bounds how many bastion tunnels one invocation opens, and says
  when it stops** — tmux collection is on by default, so a wide listing now
  reaches every running private VM in every listed resource group. Tunnel
  creation is sequential and each tunnel costs an `az` invocation, so the fan-out
  is capped per invocation and the VMs skipped by the cap are reported by count
  on stderr. Silently truncating the fan-out would have read as full coverage
  (#1127)
- **`azlin list --show-procs` now returns data for VMs with no public IP** —
  `collect_procs` only ever tried direct SSH to `public_ip` or `private_ip`, so
  for a bastion-only VM on a network the operator could not route to, the
  `Procs` column was permanently empty with no indication why. It now takes
  the same bastion path `collect_health_data` uses, via `bastion_ssh_exec`. The
  routing decision is a pure `proc_route` function returning `Bastion`, `Direct`
  or `Skip`, decided before any connection is attempted, so it is unit-tested
  rather than inferred. A VM with no public IP and no bastion route still routes
  `Direct` to its private IP, so operators on a VPN or peered network keep the
  behavior they had; there is deliberately no retry from `Bastion` to `Direct` on
  failure, because `collect_procs` is sequential and a fallback would spend a
  second full `ConnectTimeout` per unreachable host to produce the same empty
  cell. `--show-procs` is now also skipped when a listing spans more than one
  subscription, as tmux and health already were: building a resource id from
  the wrong subscription would have pointed `ps` at a same-named VM in another
  subscription (#1090, #1127). Note that this widens what `azlin list`
  discloses: process names for private-network VMs now appear in the `Procs`
  column where they previously did not. The widening is bounded to table output
  — neither `-o json` nor `-o csv` carries a process field. No new privilege is
  involved (the bastion path is gated by Azure RBAC on both the bastion and the
  target VM, plus the SSH key). The command remains restricted to the executable
  path (`awk '{print $11}'`) and never emits process arguments
- **`azlin list --with-health` no longer skips VMs that have no IP address at
  all** — `collect_health_data` bailed out of each VM before consulting the
  bastion map unless the VM had a public or private IP recorded, so a
  bastion-only VM whose private IP was absent from the listing was dropped
  even though it was reachable through its bastion. A VM is now skipped only
  when it has neither an address nor a bastion route. `collect_health_metrics`
  states the matching precondition as a guard rather than a comment: with no
  bastion route and an empty address it returns default metrics instead of
  relying on a future caller not adding a direct-SSH fallback (#1127)
- **`azlin list --with-latency` no longer reports a fabricated latency** — the
  address was formatted as `{ip}:22` and parsed, and any parse failure fell back
  to `0.0.0.0:22`. An IPv6 private address, which needs brackets in that form,
  therefore measured a TCP connect to the operator's own machine and recorded
  the result as the VM's latency — a confident wrong number, the exact failure
  mode #1106 was filed about. The address is now parsed as an `IpAddr` and the
  socket built with `SocketAddr::new`; a VM whose address will not parse is
  skipped and records no measurement — rendered as `-` in the table, an empty
  field in CSV and `null` in JSON. Latency is still measured only to a
  directly routable address and never through a bastion tunnel, which would
  time the tunnel rather than the host (#1127)
- **`azlin list` strips control characters from remotely-collected process
  names** — process names arrive from the listed VMs, and the bastion fix newly
  routes the least-observed hosts in a fleet into that path. `collect_procs`
  took the remote bytes through `String::from_utf8_lossy` straight into the
  `Procs` cell, so a process name carrying ANSI escapes could rewrite the
  operator's screen. Values entering the `Procs` column are now stripped of
  ASCII control characters and length-capped. The `Tmux` column needed no
  change: `parse_session_name` already validates every session name against an
  alphanumeric + `_` + `-` allowlist with a 128-character cap and drops anything
  that fails, which is strictly stronger than stripping. An allowlist is not
  available for process names, which are arbitrary executable paths (#1127)
- **`azlin connect <session-name>` now finds sessions on bastion-only VMs** —
  resolving a bare identifier as a tmux session name probes every running VM in
  the resource group, and bastion-only VMs were among those returning nothing
  before the tunnel fix. Their sessions are now reachable by bare name. The
  ambiguity check itself is unchanged from #1043: `match_session_in_map` still
  reports `SessionLookup::Ambiguous` when two differently named VMs each run a
  session with the requested name, and asks for `vm:session` notation. Keying
  tunnels by resource id makes that lookup fail closed rather than resolve
  arbitrarily now that the candidate list can span resource groups
- **`azlin list --with-health` now falls back to the direct address when the
  bastion fails** — the health collector was the one collector that computed a
  fallback address and never used it. `collect_health_data` resolved the VM's
  private IP into `ip` and passed it to `collect_health_metrics`, but that
  function ignores `ip` entirely whenever a bastion route is present, so a
  tunnel outage blanked the `CPU%`, `Mem%` and `Disk%` cells instead of
  retrying at an address an operator on a VPN or peered network can reach.
  Empty health cells read as a quiet, idle machine, which is the same
  confidently-wrong-by-omission failure as the tunnel bug. The bastion exec now
  retries directly on *transport* failure only: a command that reached the VM
  and exited non-zero is that VM's own answer and is returned unchanged, because
  retrying it at the private IP could reach a different host and report its
  numbers under this VM's name. `direct_fallback_host` is shared with the tmux
  and process collectors so the three cannot drift (#1127)
- **`azlin list` no longer lets a second bastion in one region silently take
  the route** — a resource group can hold several virtual networks and so
  several bastions in one region, and the discovery map used a plain `insert`.
  Whichever bastion `az` listed last won the slot, making the route a VM
  received depend on Azure's listing order; a bastion that cannot see the VM
  produces exactly the same empty row as having no bastion at all. The first
  entry now wins deterministically and the bastion that was passed over is named
  on stderr. The rule lives in `insert_bastions_for_group`, a pure function, so
  it is unit-tested without `az` — an untested tie-break is how the original
  keying defect shipped (#1127)
- **`azlin list --verbose` now says when a tmux probe failed rather than found
  nothing** — an SSH probe that could not be spawned, whose task did not
  complete, or that exited non-zero produced no output whatsoever, so a blank
  `Tmux` cell was indistinguishable from a VM with genuinely no sessions even
  with `--verbose` on. Each of those three outcomes is now reported per VM under
  `--verbose`. It is deliberately not a default-level warning: a fleet
  legitimately contains hosts the operator cannot SSH to, and one warning per
  such host per listing would train people to ignore the tunnel warnings that do
  matter (#1127)
- **The bastion table's failure warning now carries the cause, not just the
  resource group** — a failed `az network bastion list` in the display path was
  matched with `Err(_)`, discarding the error. "Not authorized" and "no such
  resource group" call for different actions, and the operator was left to guess
  which they had hit. The first line of the error now travels with the group
  name, matching what the routing path already reported (#1127)
- **The bastion tunnel cap is no longer spent on VMs that are never probed** —
  VMs whose names collide across resource groups have their enrichment columns
  withheld, but they were still fed to `plan_bastion_tunnels`, so they consumed
  slots under the per-run tunnel cap and were counted in the "skipped" total
  printed to the operator. A listing with enough colliding names could push
  genuinely probeable VMs past the cap, and the skip count named a number
  nobody could act on. Colliding VMs are now filtered out before planning
  (#1127)
- **The new `--verbose` probe diagnostic sanitises the remote host's stderr** —
  a failed SSH probe's stderr carries whatever the listed host chose to print,
  including its banner or MOTD, and the diagnostic puts it straight in the
  operator's terminal. It now passes through `sanitize_remote_text`, the same
  filter the `Tmux` and `Procs` columns use, so a listed host cannot emit ANSI
  escapes or bidi overrides into a `--verbose` listing (#1127)
- **`cmd_list_data` no longer suppresses dead-code warnings for the whole
  module** — the file carried a blanket `#![allow(dead_code)]`, and this change
  added roughly twenty functions underneath it. Removing it restores dead-code
  detection for a 2,300-line module; the module compiles clean without it on
  every target, since it contains no `#[cfg]`-gated items (#1127)

- **`cargo test` no longer mutates or corrupts the real `~/.azlin/config.toml`**
  — several dispatch tests drove `config set`, `session <vm> <name>` and the
  autopilot lifecycle in-process, so they read and wrote the developer's actual
  config and `autopilot.toml`. Their save/restore was best-effort and left the
  file modified whenever an assertion failed in between, and under `cargo test`'s
  thread parallelism two of them interleaved read-modify-write cycles and could
  corrupt the file outright (an appended duplicate `[vm_storage]` table, plus
  `Failed to rename config` from the racing side). They now run as subprocesses
  against an isolated `AZLIN_CONFIG_DIR` (or `HOME` for autopilot, which does not
  honour `AZLIN_CONFIG_DIR`), with a regression test asserting writes cannot
  escape the isolated directory (#1079)
- **A malformed config is now reported instead of silently replaced by defaults**
  — `AzlinConfig::load()` already returned an error for a file that exists but
  cannot be parsed, but ~12 call sites discarded it with `.unwrap_or_default()`.
  A syntax error therefore surfaced as an unrelated downstream message: a
  duplicate table on line 32 produced "No resource group specified. Use
  --resource-group or set in config." while `default_resource_group` sat correct
  in the file, so following the advice could never fix it. Parse failures now
  abort with the file path and the parser's line/column; a *missing* config still
  yields defaults as before (#1080)
- **`azlin gui install` no longer fails closed on every legitimate pull** —
  the post-pull digest check added alongside the container-based GUI installer
  compared the pulled image's `RepoDigests` entry against the pinned
  `linux/amd64` child-manifest digest, but `docker pull <tag>` on a multi-arch
  repository records the manifest-list/OCI-index digest instead. The two
  differ by construction, so the check rejected every install with exit 10.
  `GuiImage` now pins both the index digest (the value a normal tag pull
  records) and the amd64 child digest (accepted as an alternative for an
  explicit single-platform pull); anything else still fails closed
- **`destroy` no longer leaks the session Public IP and NSG** — `az vm delete`
  removes only the VM; the disk and NIC disappear via ARM's implicit
  `deleteOption: Delete`, but Azure has no equivalent for the Public IP or the
  NSG, so both were left behind on every create/destroy cycle. The leaked
  Standard static Public IP bills ~$3.65/month indefinitely, and the leftover
  `<vm>NSG` blocks reusing the VM name. This regressed the NSG behavior fixed by
  #517 (issue #516) and the Public IP behavior that the removed Python
  `vm_lifecycle.py` also implemented; neither was reimplemented during the Rust
  rewrite (#516, #517)
  - New teardown planner discovers the VM's disks, NIC, Public IP and NSG,
    scoped by the `azlin-session` tag so sibling sessions are never touched
  - Deletes in dependency order (VM → disks → NIC → Public IP → NSG), since
    Azure refuses to delete a Public IP or NSG while a NIC still references it
  - A second `plan_recheck` pass re-evaluates resources skipped as in-use after
    the NIC delete settles, covering Azure's eventual consistency on NIC/NSG
    association
  - `destroy --dry-run` now queries Azure and reports the actual resources and
    the estimated monthly saving, instead of printing a static string
  - `killall` now matches session VMs by exact name rather than a JMESPath name
    prefix, so destroying `foo` can no longer match `foobar`
  - Pooled sessions (`azlin new --name X --pool N`) tag every member's Public
    IP/NSG with the pool's base name, not that member's own VM name. Recovering
    a member's orphaned Public IP/NSG after its VM is already gone now falls
    back to Azure's default per-VM resource naming (`also_match_by_name`) when
    the guessed session tag cannot match, so a pool member's leak is no longer
    silently unrecoverable

### Security
- **Bastion WSS URL redaction** — the `wss://` tunnel URL embeds the short-lived
  `websocketToken` bearer secret as a path segment. On a failed WSS connect the
  `warn!` now logs a redacted URL (`redact_wss_url`) and scrubs the token from
  the rendered `tungstenite` error, so the token can never reach a `tracing`/OTel
  sink regardless of upstream `Display` behavior. Fail-closed: unrecognized URL
  shapes collapse to `wss://<redacted>`. Defense-in-depth; no confirmed leak (#1056)
  - New docs: `docs/WSS_URL_REDACTION.md`

### Added
- **GUI Forwarding**: Run remote Linux GUI applications locally (#828)
  - `azlin connect --x11` / `-X` — X11 forwarding for lightweight GUI apps (gitk, meld, xeyes)
  - `azlin gui [VM]` — Full VNC desktop session with XFCE, auto-managed dependencies
  - `azlin gui --minimal` — Openbox window manager only (no full desktop overhead)
  - `azlin gui --app "cmd"` — Single-app VNC mode, exits when app closes
  - Automatic local/remote dependency detection and installation guidance
  - VNC on localhost only with random per-session passwords
  - Works through Azure Bastion for private VMs
  - New docs: `docs/GUI_FORWARDING.md`

## [2.3.0-rust] - 2026-03-08

### Rust Rewrite
- Complete rewrite from Python to Rust -- 75-85x faster startup
- 2,536 tests, 53 commands, 154 subcommand variants
- Pre-built binaries for Linux, macOS, Windows
- `azlin self-update` for automatic updates
- `azlin-py` preserves access to Python CLI
- Migration bridge: existing uvx alias auto-routes to Rust binary
- Custom table renderer with guaranteed single-line truncation
- Non-TTY safe: all confirmation prompts handle piped input

## [2.3.0] - 2026-02-27

### Major Features

#### `azlin logs` - VM Log Viewer (#654)
- View cloud-init, syslog, and custom logs from any VM
- Stream logs in real-time or fetch historical entries

#### VM Health Dashboard with Four Golden Signals (#659)
- Real-time monitoring: latency, traffic, errors, saturation
- Actionable health status for each VM

#### `--os` Option for Ubuntu Version Selection (#715)
- Specify Ubuntu version when creating VMs (e.g., `--os 25.10`)
- Full support for Ubuntu 25.10

#### Separate /tmp Disk Support (#686)
- Add dedicated /tmp disks to new or existing VMs
- Configurable size and mount options

#### Compound VM:Session Naming (#607)
- Address VMs with `hostname:session_name` syntax
- Works across all commands (connect, exec, code, etc.)

#### OS Icon and Distro Column in `azlin list` (#728)
- Detects distro from Azure image reference (Ubuntu, Debian, Windows, RHEL, SUSE)
- OS name includes version (e.g., "Ubuntu 25.10", "Ubuntu 22.04 LTS")

#### Session Save/Load and Active Process Monitoring
- Save and restore session state across VM restarts
- Monitor active processes within sessions

### Performance

- Parallelize CLI tool detection: 15s to 5s startup (#641)
- Batch storage quota queries to eliminate N+1 Azure CLI calls (#649)
- Per-VM incremental cache refresh (#639)
- Fix stale cache hiding newly created VMs (#670)

### Security

- Enable NFS RootSquash to prevent privilege escalation (#624)
- Use Azure AD auth instead of storage keys (#629)
- Use append mode for SSH keys per audit requirement (#632)

### Refactoring

- Decompose vm_connector.py from 976 to 492 LOC (#642)
- Split monitoring.py into focused command modules (#635)
- Split connectivity.py into focused command modules (#636)
- Migrate NFS, Bastion, and storage modules to shared validation utilities (#637)
- Extract 48 helper functions from cli.py to cli_helpers.py (#634)
- Decompose monolithic list_command() into focused helpers (#633)

### Bug Fixes

- Fix WSL SSH config sync for `azlin code` (#731)
- Auto-remediate tmux socket dir on Ubuntu 25.10 VMs during connect (#723)
- Fix cloud-init runcmd YAML parsing failure from version logging (#725)
- Make cloud-init work on Ubuntu 25.10 for npm and ripgrep (#727)
- Always measure SSH latency when `--with-latency` is requested (#721)
- Fix `azlin list -q` not showing quota when VMs are cached (#688)
- Add missing `--mount` flag to disk add help text (#706)
- Azure CLI WSL2 detection and auto-fix (#609)
- Tag-based VM discovery for `azlin w/ps/top` (#610)
- Replace remaining `datetime.utcnow()` deprecations (#707, #703)
- Address quality audit findings (debug logging, ANSI sanitization, timeouts, dead code) (#665)
- Remove disabled SSHFS auto-mount dead code (#643)
- Remove broken test imports from shared validation migration (#645)
- Replace XXX placeholders with descriptive webhook URL examples (#640)

### Testing

- Unit tests for cli_helpers.py (#700)
- Unit tests for key_rotator.py (#698)
- Unit tests for orchestrator.py (#699)
- Unit tests for remote_exec.py and batch_executor.py (#702)
- Unit tests for tag_manager.py and service_principal_auth.py (#701)
- Resolve 6 skipped tests by implementing missing features (#711)
- Update 5 stale test skips to match current implementations (#704)
- Register missing pytest markers (#703)
- Correct mock scopes in integration tests (#697, #712)

### Infrastructure

- Add 8 GitHub Agentic Workflows for continuous improvement and maintenance
- Full system upgrade and gh CLI install in cloud-init (#719)
- Add tmux socket directory permissions for Ubuntu 25.10 (#718)
- Version logging for npm and rg during VM provisioning (#717)

## [2.2.2] - 2026-02-11

### CLI Modularization
- Decomposed cli.py into 11 modular command files
- Reduced cli.py from 10,242 to 6,863 lines (33% reduction)
- Preserved exact list command behavior (fixes #604)

### Quality Audit
- Completed comprehensive quality audit
- Created 9 issues for improvements (#595-603)
- Overall codebase score: 8.8/10

## [2.2.1] - 2026-02-10

### Documentation
- Updated README to focus on user-facing features
- Removed emojis from documentation
- Clarified feature benefits and usage examples

## [2.2.0] - 2026-02-10

### Major Features

#### `azlin restore` - Automatic Session Restoration (#583)
- Launches terminal windows for all active azlin sessions with one command
- Smart platform detection (macOS Terminal, Windows Terminal, WSL, Linux)
- Multi-tab support for Windows Terminal
- User-configurable terminal preferences via `~/.azlin/config.toml`
- 49 comprehensive tests with security hardening

#### iOS PWA for Azlin VM Management (#551)
- Progressive Web App for managing VMs from iPhone
- Start/stop VMs, view status, manage tmux sessions
- Quasi-interactive terminal via Azure Run Command API
- Works with private IP VMs (no public IPs required)
- Azure AD authentication with device code flow
- Installable on iPhone home screen
- Complete cost tracking integration

#### Bastion Tunnel Enhancements (#582, #589)
- VS Code launcher now supports Bastion tunnels for private IP VMs
- Retry logic and rate limiting for tunnel creation
- Improved reliability for VMs without public IPs

#### Intelligent Caching System (#553, #563)
- 60-minute cache TTL (up from 5 minutes)
- Background cache refresh after each `azlin list`
- Tiered caching with mutable/immutable separation
- Dramatically reduces Azure API calls and improves performance

#### Separate /home Disk Support (#515)
- Automatic 100GB managed disk for `/home` directory
- Persistent storage isolated from OS disk
- Customizable with `--home-disk-size` and `--no-home-disk` options
- Cost-effective at ~$4.80/month for default configuration

#### Enhanced List Display (#587)
- Added tmux session count column
- Renamed "Size" to "SKU" for clarity
- Rebalanced column widths for better readability

### Changed
- **BREAKING**: Decomposed monolithic cli.py (10,011 lines) into 11 modular command files
  - Reduced cli.py from 10,011 to 2,527 lines (75% reduction)
  - Created self-contained modules following Bricks & Studs architecture
  - All existing CLI commands preserved with backward compatibility
- Default Ubuntu version updated from 22.04 to 24.04 LTS (#559)
- Various timeout improvements for WSL/Windows compatibility

### Added
- New modular command structure in `src/azlin/commands/`:
  - `batch.py`: Batch operations (stop, start, sync, command)
  - `connectivity.py`: SSH connection, VS Code, sync, cp commands
  - `env.py`: Environment variable management
  - `ip_commands.py`: IP diagnostics commands
  - `keys.py`: SSH key management
  - `lifecycle.py`: VM lifecycle (start, stop, kill, destroy)
  - `nlp.py`: Natural language command execution (do command)
  - `provisioning.py`: VM creation (new, vm, create, clone)
  - `snapshots.py`: Snapshot management
  - `templates.py`: Template CRUD operations
  - `web.py`: PWA development server commands
  - `monitoring.py`: Expanded with list, session, w, top, ps, cost commands
- Shared `get_vm_session_pairs()` function for list/restore consistency
- CodeQL configuration to handle intentional lazy imports
- Automatic Claude Code installation during VM provisioning (#570)

### Fixed
- Security: AppleScript injection vulnerability (CWE-94) in restore.py
- Security: Permission race condition (CWE-732) in auth.py with atomic file creation
- Security: Documented SSH StrictHostKeyChecking tradeoff in cli_helpers.py
- Removed 164 lines of dead code (_doit_old_impl)
- Cleaned up `__all__` exports to not include private functions
- Fixed test mock patch locations for decomposed modules
- Session crossing prevention in azlin restore
- List/restore reliability improvements

### Testing
- 74/74 module extraction tests passing (100%)
- Verified backward compatibility for existing test patches
- UVX installation tested and working
- Real Azure integration tested with 6 VMs
- Concurrent command execution tested (3 simultaneous commands)

## [2.1.0] - 2025-10-19

### Added
- 352 comprehensive tests (vm_lifecycle, terminal_launcher, etc.)
- CI/CD pipeline with 6 security scanning tools
- API reference documentation (3,547 lines)

### Fixed
- Path traversal and IP validation security fixes
- Silent exception handling (36 locations)
- Consolidated duplicate VM listing logic

### Removed
- 1,331 lines of dead code (xpia_defense.py)

## [2.0.0] - 2025-09-15

Initial v2.0 release with config management and enhanced CLI.
