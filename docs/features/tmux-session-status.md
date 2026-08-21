# Tmux Session Connection Status

Instantly identify which tmux sessions are connected or disconnected with visual styling in the `azlin list` command.

## What is Tmux Session Connection Status?

The `azlin list` command now displays tmux session connection status using visual text styling:

1. **Connected Sessions**: Appear in **bold text** to stand out
2. **Disconnected Sessions**: Appear in dim text to de-emphasize
3. **Zero Overhead**: Uses existing SSH connection, no additional network calls

This eliminates the need to SSH into each VM and run `tmux list-sessions` manually to find where your active work is located.

## Why Would I Use It?

Tmux session status monitoring solves several workflow challenges:

### Problem 1: Finding Active Work Sessions

You have multiple VMs with tmux sessions and need to find where your active debugging session is running.

**Without connection status**: SSH into each VM and run `tmux list-sessions` to check connection status.

**With connection status**: Run `azlin list` and connected sessions appear in **bold** - your active work jumps out immediately.

### Problem 2: Identifying Orphaned Sessions

You've disconnected from a VM but can't remember which one still has your tmux session running.

**Without connection status**: Try to remember which VM you were using, or check each one manually.

**With connection status**: Disconnected sessions appear in dim text - quickly scan the list to find orphaned sessions that need attention.

### Problem 3: Multi-VM Workflow Management

You're working across multiple VMs with different tasks in tmux and need to see the overall state at a glance.

**Without connection status**: Keep mental notes or a separate document tracking which sessions are active.

**With connection status**: One `azlin list` command shows the complete picture - bold for active, dim for backgrounded.

### Problem 4: Team Collaboration

Multiple team members are using shared VMs with tmux and you need to see which sessions are currently occupied.

**Without connection status**: Coordinate manually or risk attaching to an active session and disrupting someone's work.

**With connection status**: Connected (bold) sessions indicate someone is actively using them - avoid conflicts.

## How Does It Work?

### Connection Detection

Connection status is detected through an enhanced tmux query that includes attachment information:

```
1. SSH to VM (reuses existing connection)
   └─▶ Already connecting for VM status check - zero additional overhead

2. Run enhanced tmux query
   └─▶ tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"

3. Parse attachment status
   ├─▶ session_attached=1: Session is connected → Apply bold markup
   └─▶ session_attached=0: Session is disconnected → Apply dim markup

4. Apply Rich library styling
   ├─▶ Connected: [bold]session-name[/bold]
   └─▶ Disconnected: [dim]session-name[/dim]
```

**Key Features**:
- **Zero overhead**: Uses existing SSH connection from VM status check
- **Graceful fallback**: If enhanced format fails, parser automatically falls back to old format
- **Terminal-agnostic**: Works across all terminals through Rich library
- **Format-aware**: Detects new vs old tmux output format automatically

### Bastion-Only VMs (No Public IP)

A VM with no public IP is reached through Azure Bastion rather than by direct
SSH. `azlin list` handles this automatically: whenever at least one running VM
in the result set has no public IP, it discovers the bastion hosts in that VM's
resource group and region and opens a tunnel before the tmux probes run. No flag
is required, and this happens in every output format — table, JSON and CSV.

**One tunnel per VM, not one per bastion.** A Bastion tunnel is opened against a
specific VM's ARM resource id and forwards to that VM alone. A single regional
bastion typically fronts many VMs, but its tunnels are not interchangeable, so
`plan_bastion_tunnels` emits one plan per bastion-only VM:

```
Region westus2, bastion `bastion-westus2`, three VMs with no public IP:

  dev-vm-002  ──▶ tunnel on 127.0.0.1:52341  ──▶ /subscriptions/…/dev-vm-002
  dev-vm-004  ──▶ tunnel on 127.0.0.1:52342  ──▶ /subscriptions/…/dev-vm-004
  dev-vm-007  ──▶ tunnel on 127.0.0.1:52343  ──▶ /subscriptions/…/dev-vm-007
```

Each probe uses its own VM's port. Tunnels are created sequentially, because
creating one mutates a shared on-disk registry; the SSH probes that follow run
concurrently.

**Discovery covers every resource group in the listing.** Bastion coordinates
are held in a `BastionMap` keyed by `(resource group, region)`, built by running
`az network bastion list` once per distinct resource group that actually
contains a running VM with no public IP:

- A listing where every VM has a public IP performs no bastion lookup at all.
- The common single-resource-group listing performs exactly one, as before.
- A `--show-all-vms` listing performs one per resource group that needs it.

Discovery used to run against the resource group of whichever VM sorted first,
which made it the same first-iterated-wins bug as the shared tunnel, one call
frame higher: a bastion-only VM in any other resource group had no bastion in
the map and was skipped silently.

Failure is isolated per resource group. Missing
`Microsoft.Network/bastionHosts/read` on one resource group costs that resource
group's private VMs their enrichment columns and leaves the rest of the listing
intact. Coordinates returned by `az` are validated before use — an entry with an
empty name or location, or a name beginning with `-`, is dropped rather than
passed into an argument vector.

A bastion-only VM whose `(resource group, region)` pair has no discovered
bastion is skipped: no tunnel is planned, and `--verbose` reports the skip. The
case that still does not resolve is hub-and-spoke — a bastion in a hub resource
group fronting VMs in spokes. That needs VNet-peering discovery, which azlin
does not do.

**Tunnel fan-out is bounded.** Tmux collection is on by default, so a wide
listing reaches every running private VM in every listed resource group. One
invocation opens a capped number of tunnels; VMs beyond the cap are skipped and
their count is printed on stderr. Silent truncation would read as full coverage.
Narrow the listing with `--rg` or `--tag` to bring a large fleet under the cap.

**Tunnels are identified by resource id, not by name.** The plan's
deduplication key and the port-map lookup used by `collect_tmux_sessions` are
both produced by `build_vm_resource_id`, the same helper that builds the key
`get_or_create_tunnel` stores in the tunnel registry. Using one producer for all
three keeps the registry key, the plan key and the lookup key from drifting
apart — two hand-rolled copies of that format could diverge and leak a fresh
tunnel per VM per invocation.

The rule the code enforces: on the bastion path, the resource id is the only
acceptable identity key. A VM name may key a display map; it may never key a
port, a tunnel, or an exec route. Any lookup that decides *which host a command
runs on* uses the resource id.

**Same-named VMs lose their enrichment columns.** Results are still keyed by VM
*name* for display, and the renderer looks each row up by `vm.name`. Azure only
guarantees name uniqueness within a resource group, so once discovery spans
several resource groups a listing can contain two running VMs called the same
thing — and one VM's sessions would render against the other's row even though
the tunnels themselves are correctly separated.

Rather than display that, `azlin list` detects colliding names up front, omits
`Tmux`, health and `Procs` data for every VM in the colliding set, and prints a
note naming them on stderr:

```
Note: 2 VMs share the name 'build-agent' (resource groups dev-rg, prod-rg);
tmux, health and process details have been omitted for them.
```

The rows still list — only the remotely-collected columns are withheld. This
follows the cross-subscription precedent from #1090: attributing one VM's
processes to another is worse than a blank cell, and a `--output json` consumer
never sees the stderr note at all. Re-keying the display maps by
`(resource group, name)` is tracked as a follow-up.

**A tunnel that cannot be opened is reported, not swallowed.** If tunnel
creation fails — the bastion is missing, RBAC denies it, the tunnel times out —
that VM cannot be probed. `azlin list` prints a warning on stderr and continues
with the remaining VMs. The warning names the VM and carries the first line of
the underlying error, for example:

```
warning: bastion tunnel for dev-vm-002 could not be opened; its tmux sessions
will not be listed (Bastion host 'bastion-westus2' not found in resource group 'dev-rg')
```

Only the first line of the error is included. Run with `--verbose` for the full
error chain. The warning goes to stderr, so `--output json` and `--output csv`
piped to a file are unaffected.

The distinction matters: a VM whose tunnel failed and a VM with genuinely no
tmux sessions both render `-` in the `Tmux` column. The warning is what tells
them apart.

**Bastion-only VMs and session-name lookup.** When the argument to
`azlin connect` does not match any VM name, it is resolved as a tmux session
name against every running VM in the resource group — bastion-only VMs
included, using the same per-VM tunnels. Making those VMs visible to the probe
makes their sessions reachable by bare name.

The lookup refuses to guess when a session name is not unique. If two
*differently named* VMs each run a session called `build`, the lookup reports
the ambiguity rather than picking one:

```bash
azlin connect build
# Error: 'build' is not a known VM, and matches tmux sessions on multiple VMs
# (dev-vm-002, dev-vm-004); use 'azlin connect <vm>:build' to disambiguate
```

Disambiguate with `vm:session` notation:

```bash
azlin connect dev-vm-002:build
```

This ambiguity check predates the bastion work; what changed is that
bastion-only VMs now take part in the lookup, so a session on a private VM can
be found by bare name and can legitimately contend for one. Keying by resource
id makes the lookup fail closed rather than resolve arbitrarily now that the
candidate list can span resource groups.

**Other `azlin list` columns on bastion-only VMs:**

| Flag | Column(s) | Bastion-only VMs |
|------|-----------|------------------|
| `--show-tmux` (default) | `Tmux` | Supported — one tunnel per VM, as described above |
| `--with-health` | `Agent`, `CPU%`, `Mem%`, `Disk%` | Supported — `collect_health_data` uses the bastion path per VM. A VM is skipped only when it has neither a routable address nor a bastion route; it used to be skipped whenever no IP was recorded, which dropped bastion-only VMs that were in fact reachable |
| `--show-procs` | `Procs` (table output only) | Supported — `collect_procs` takes the bastion path. Skipped, like tmux and health, when the listing spans more than one subscription |
| `--with-latency` | `Latency` | Measured only when the VM's address is routable from this machine (a public IP, or a private IP over VPN or peering). Latency is never measured through the tunnel, which would time the tunnel rather than the host |

**How `--show-procs` picks a route.** `proc_route` is a pure function that
decides once, before any connection is attempted, and returns one of three
outcomes:

| VM state | Route |
|----------|-------|
| Has a public IP | `Direct` to the public IP |
| No public IP, a bastion route exists | `Bastion` |
| No public IP, no bastion route, has a private IP | `Direct` to the private IP — the VPN / peered-network case |
| No public IP, no bastion route, no private IP | `Skip` |

There is deliberately no fall back from `Bastion` to `Direct` on failure.
`collect_procs` runs sequentially, so a fallback would cost a second full
`ConnectTimeout` for every unreachable host, serially — a listing with ten
unreachable private VMs would stall for twice as long to produce the same empty
column. Deciding up front also makes the routing unit-testable without a
network. Operators on a VPN keep the behaviour they had through the third row of
the table, not through a retry.

Using `--show-procs` together with `--with-health` resolves the bastion map
twice in one run; the extra `az` calls cost a few hundred milliseconds per
resource group and have no effect on results.

**Process data does not reach JSON or CSV.** `--show-procs` fills the `Procs`
column in table output only; the JSON and CSV renderers carry no process field.
This bounds the disclosure discussed below, but it also means process data
cannot be scripted out of `azlin list`.

**Remote text is sanitised before display.** Session names and process names
come from the listed VMs, and the bastion fix newly routes the least-observed
hosts in a fleet into that path. The two columns are not equally protected, and
only one of them needs work:

- **`Tmux` is already safe.** `parse_session_name` validates every session name
  against an alphanumeric + `_` + `-` allowlist with a 128-character cap, and
  drops anything that fails. An allowlist is strictly stronger than stripping
  control characters — no escape sequence, quote or comma can survive it. This
  predates #1127 and is unchanged.
- **`Procs` is the gap.** Process names come back through
  `String::from_utf8_lossy` and reach the `Procs` cell unvalidated, so a process
  name carrying ANSI escapes could rewrite the operator's screen. Values entering
  the `Procs` column are now stripped of ASCII control characters and
  length-capped.

An allowlist is not usable for `Procs` the way it is for session names: a
process name is an arbitrary executable path, not a name azlin controls the
shape of. Stripping is the appropriate control there.

### Performance Characteristics

| Operation | Overhead | Notes |
|-----------|----------|-------|
| Connection status detection | 0 seconds | Reuses existing SSH connection |
| Tmux query | <50ms per VM | Minimal query overhead |
| Format detection | Automatic | Parser handles both old and new formats |
| Rendering | <1ms | Rich library handles terminal capabilities |

### Graceful Degradation

The feature handles various edge cases elegantly:

1. **Tmux not installed**: No session display (same as before)
2. **Tmux query fails**: Falls back to old parser format
3. **Terminal doesn't support styling**: Falls back to plain text
4. **No tmux sessions**: Clean display with no session data

## Examples

### VM List With the Tmux Column

Basic VM listing with tmux connection status:

```bash
azlin list
```

**Output**:
```
┌────────────┬──────────────┬──────────────────┬─────────┬──────────────┬─────────┬─────┬──────┐
│ Session    │ Tmux         │ OS               │ Status  │ IP           │ Region  │ CPU │  Mem │
├────────────┼──────────────┼──────────────────┼─────────┼──────────────┼─────────┼─────┼──────┤
│ dev-vm-001 │ main, debug  │ Ubuntu 24.04 LTS │ Running │ 20.123.45.67 │ eastus  │   4 │ 16GB │
│ dev-vm-002 │ training     │ Ubuntu 24.04 LTS │ Running │ 20.123.45.68 │ westus2 │   2 │  8GB │
│ dev-vm-003 │ -            │ Ubuntu 24.04 LTS │ Running │ 20.123.45.69 │ eastus  │   2 │  8GB │
└────────────┴──────────────┴──────────────────┴─────────┴──────────────┴─────────┴─────┴──────┘
```

The column is named `Tmux`, and it lists session *names*, not a count.

**Visual Styling** (as seen in terminal):
- `dev-vm-001`: **main** appears bold (connected), `debug` appears dim (disconnected)
- `dev-vm-002`: `training` appears dim (disconnected)
- `dev-vm-003`: no sessions, so the cell shows `-`

### Finding Active Work

You need to find which VM has your active debugging session:

```bash
azlin list
```

**What you see**:
- VM `dev-vm-001` shows session "**debug**" in bold
- Other sessions appear dim
- **Result**: You immediately know `dev-vm-001` has your active session

### Scanning for Disconnected Sessions

You want to clean up orphaned sessions that are no longer needed:

```bash
azlin list
```

**What you see**:
- Multiple VMs with dim session names
- These are all disconnected sessions
- **Result**: Identify cleanup candidates at a glance

### With Latency Measurement

Combine connection status with latency for complete operational view:

```bash
azlin list --with-latency
```

**Output**:
```
┌────────────┬─────────────┬──────────────────┬─────────┬──────────────┬─────────┬─────┬──────┬─────────┐
│ Session    │ Tmux        │ OS               │ Status  │ IP           │ Region  │ CPU │  Mem │ Latency │
├────────────┼─────────────┼──────────────────┼─────────┼──────────────┼─────────┼─────┼──────┼─────────┤
│ dev-vm-001 │ main, debug │ Ubuntu 24.04 LTS │ Running │ 20.123.45.67 │ eastus  │   4 │ 16GB │    45ms │
│ dev-vm-002 │ training    │ Ubuntu 24.04 LTS │ Running │ 20.123.45.68 │ westus2 │   2 │  8GB │   180ms │
└────────────┴─────────────┴──────────────────┴─────────┴──────────────┴─────────┴─────┴──────┴─────────┘
```

`Latency` is appended after `Mem`, not inserted next to `IP`.

**Visual Styling**:
- Low latency VM (45ms) with **bold** session indicates optimal target for interactive work
- High latency VM (180ms) with dim sessions suggests backgrounded work

## Technical Notes

### Implementation Details

The feature enhances the existing tmux query format:

**Old format** (still supported via fallback):
```
tmux list-sessions
# Output: session_name: 3 windows (created Thu Dec 19 10:30:00 2024)
```

**New enhanced format**:
```
tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"
# Output: main:1:3:1734608200
#         debug:0:5:1734611100
```

The parser automatically detects which format is returned and processes accordingly.

### Styling with Rich Library

Styling uses Rich library markup that's terminal-agnostic:

```python
# Connected session (bold)
rich_text = "[bold]session-name[/bold]"

# Disconnected session (dim)
rich_text = "[dim]session-name[/dim]"
```

Rich library automatically:
- Detects terminal capabilities
- Falls back to plain text for unsupported terminals
- Handles color/no-color environments
- Renders consistently across macOS, Linux, Windows

### Compatibility

**Supported tmux versions**: 1.8+ (most common installations)

**Terminal compatibility**: Any terminal that supports:
- Bold text (most modern terminals)
- Dim/faint text (fallback to normal if unsupported)

**Platforms**:
- macOS (Terminal.app, iTerm2, Alacritty, etc.)
- Linux (GNOME Terminal, Konsole, xterm, etc.)
- Windows (Windows Terminal, WSL terminals)

### Performance Impact

**Zero performance impact** because:
1. Query piggybacks on existing SSH connection
2. Enhanced format query has same execution time as old format
3. Rich markup parsing happens locally (no network overhead)
4. Fallback detection adds <1ms parsing time

## Troubleshooting

### Issue: No Visual Difference Between Sessions

**Symptom**: All sessions appear the same without bold/dim styling.

**Cause**: Terminal doesn't support text styling.

**Solution**:
- Use a modern terminal (iTerm2, Windows Terminal, etc.)
- Check terminal color support: `echo $TERM`
- Expected values: `xterm-256color`, `screen-256color`

**Workaround**: Connection status is still accurate, just not visually styled.

---

### Issue: Sessions Show Wrong Status

**Symptom**: A session appears connected (bold) but you're not attached, or vice versa.

**Cause**: Query format mismatch or stale session data.

**Solution**:
```bash
# SSH to the VM and verify manually
ssh azureuser@<vm-ip>
tmux list-sessions

# Check for zombie sessions
tmux kill-session -t <session-name>
```

**Likely causes**:
- Tmux server restart needed
- Network interruption left stale session
- Multiple users on same VM

---

### Issue: Format Fallback Warning

**Symptom**: Parser falls back to old format and logs warning.

**Cause**: Tmux version doesn't support enhanced format query.

**Solution**: Update tmux on the VM:
```bash
# Ubuntu/Debian
sudo apt update && sudo apt install tmux

# RHEL/CentOS
sudo yum update tmux

# macOS
brew upgrade tmux
```

**Impact**: Feature still works but without connection status detection.

---

### Issue: Sessions Not Displayed At All

**Symptom**: The `Tmux` column shows `-` even though sessions exist.

**Cause**: SSH connection unable to query tmux.

**Debugging steps**:
```bash
# Verify tmux is installed
ssh azureuser@<vm-ip> which tmux

# Check if tmux server is running
ssh azureuser@<vm-ip> tmux list-sessions

# Check socket permissions
ssh azureuser@<vm-ip> ls -la /tmp/tmux-*
```

**Common fixes**:
- Restart tmux server: `tmux kill-server && tmux`
- Fix socket permissions: `chmod 700 /tmp/tmux-$(id -u)`

---

### Issue: A Bastion-Only VM Shows No Sessions While Its Neighbour Shows Some

**Symptom**: Two or more VMs with no public IP sit behind the same regional
Azure Bastion. One reports its tmux sessions correctly; the others report none,
consistently, even though `azlin connect <vm>` reaches them and `tmux
list-sessions` there shows sessions.

**Cause**: A Bastion tunnel reaches one target VM only. Sharing a single tunnel
across every VM behind a bastion sends all the probes to one host. This was
fixed in #1127 — `azlin list` now opens one tunnel per VM.

**Solution**: Upgrade to `v2.6.126-rust.12ccf60` or later, the first release
containing the fix. Check the installed version first:

```bash
azlin --version
azlin update
```

**Verifying**: run with `--verbose` and confirm one tunnel is planned per
bastion-only VM, not one per bastion:

```bash
azlin -v list
```

If the tunnel for a VM cannot be opened, you now get an unconditional warning on
stderr naming that VM — see [Bastion-Only VMs](#bastion-only-vms-no-public-ip).
A `-` in the `Tmux` column with no warning means the VM genuinely has no
sessions.

---

### Issue: A Bastion-Only VM in a Non-Default Resource Group Shows No Sessions

**Symptom**: Under `azlin list --show-all-vms`, private VMs in one resource
group report their sessions and private VMs in the others report none. Listing
the affected resource group on its own with `azlin list --rg <rg>` works.

**Cause**: Bastion discovery used to query a single resource group — the one
belonging to whichever VM sorted first in the listing. Bastions in the other
resource groups were never found, so those VMs got no tunnel.

**Solution**: Upgrade. Discovery now runs once per resource group that contains
a running VM with no public IP.

```bash
azlin --version
azlin update
```

**If it persists after upgrading**, check for a hub-and-spoke topology: a
bastion in a hub resource group fronting VMs in spoke resource groups is still
not resolved, because azlin does not walk VNet peerings. Those VMs need a
bastion in their own resource group.

```bash
# What azlin looks for — a bastion in the VM's own resource group
az network bastion list --resource-group <vm-resource-group> -o table
```

---

### Issue: Some Bastion-Only VMs Are Skipped in a Large Listing

**Symptom**: A wide listing reports a count of skipped VMs on stderr and shows
`-` in their `Tmux` columns.

**Cause**: One invocation opens a bounded number of bastion tunnels. Tunnel
creation is sequential and each one costs an Azure API round trip, so a listing
covering more private VMs than the cap stops there rather than running
unbounded.

**Solution**: Narrow the listing so the private VMs you care about fall inside
the cap.

```bash
# Scope to one resource group
azlin list --rg dev-rg

# Or to one project
azlin list --show-all-vms --tag project=myapp
```

---

### Issue: Performance Degradation With Many VMs

**Symptom**: `azlin list` seems slower with 20+ VMs.

**Cause**: SSH connections to many VMs take time (not related to this feature).

**Solution**: Query specific resource groups or regions:
```bash
# Filter by resource group
azlin list --rg dev-rg

# Filter by VM name pattern
azlin list --vm-pattern 'dev-*'

# Skip the tmux probes entirely — they are the slow part
azlin list --no-tmux
```

**Note**: Tmux connection status adds <50ms per VM, negligible compared to SSH connection time (~500ms-2s per VM).

## Related Features

- **[Memory and Latency Monitoring](./memory-latency.md)** - See VM resource allocation and network latency
- **[Native Bastion Tunnel](./native-bastion-tunnel.md)** - The tunnel transport used to reach VMs with no public IP
- **[VM Lifecycle Automation](./vm-lifecycle-automation.md)** - Automatic status checking that enables this feature
- **[Hostname and Session Name in Status Line](../../specs/tmux-status-line-enhancement.md)** - Complementary feature showing VM info in tmux itself

## See Also

- [azlin Quick Reference](../QUICK_REFERENCE.md) - Complete command reference
- [How to Troubleshoot Connection Issues](../how-to/troubleshoot-connection-issues.md) - SSH and tmux debugging
- [API Reference - list command](../API_REFERENCE.md#list-command) - Technical details
