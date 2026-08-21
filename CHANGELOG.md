# Changelog

All notable changes to azlin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
