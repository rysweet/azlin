# CLI Command Reference — Python Parity

This document covers all CLI flags and defaults that match the original Python CLI behavior. The Rust CLI provides full parity with the Python CLI that was replaced in v2.3.0-rust.

## Commands

- [code](#code) — Launch VS Code Remote-SSH
- [clone](#clone) — Clone a VM
- [list](#list) — List VMs
- [batch stop](#batch-stop) — Batch stop/deallocate VMs
- [disk add](#disk-add) — Attach managed disk to VM
- [fleet run](#fleet-run) — Execute commands across fleet
- [restore](#restore) — Restore terminal sessions
- [autopilot enable](#autopilot-enable) — Enable autopilot scheduling
- [logs](#logs) — View VM logs
- [doit destroy / doit delete](#doit-destroy--doit-delete) — Autonomous cleanup

---

## code

Launch VS Code with Remote-SSH for a VM.

```
azlin code <VM_IDENTIFIER> [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `VM_IDENTIFIER` | **Yes** | VM name, session name, or IP address |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |
| `--user` | `TEXT` | the VM's admin user | SSH username for the connection |
| `--key` | `PATH` | — | SSH private key path |
| `--no-extensions` | flag | `false` | **Not implemented** — see below |
| `--workspace` | `TEXT` | `/home/azureuser` | Remote workspace directory to open |

### Examples

```bash
# Launch VS Code for a VM (uses default user and workspace)
azlin code my-dev-vm

# Connect as a different user with a specific key
azlin code my-dev-vm --user ubuntu --key ~/.ssh/custom_key

# Open a specific workspace directory
azlin code my-dev-vm --workspace /home/azureuser/projects

# Explicit resource group
azlin code my-dev-vm --rg my-resource-group
```

### Bastion tunnel lifetime

For bastion-routed VMs, `azlin code` establishes a **persistent** bastion
tunnel that outlives the command. The tunnel is owned by a detached
`__tunnel-host` helper process (not by `azlin code` itself), so VS Code's
multiple long-lived Remote-SSH connections keep working after `azlin code`
returns to the shell. The tunnel is reused across invocations and closed with
`azlin tunnel close <vm>`. That reuse is the "pool" that
`azlin connect --disable-bastion-pool` opts out of: a connection with the flag
neither reuses a live tunnel nor registers the one it opens, so it gets its own
tunnel and leaves everyone else's alone. See
[Persistent Bastion Tunnel for `azlin code`](../features/vscode-persistent-bastion-tunnel.md).

### `--user`

Defaults to the VM's own admin user, read from Azure — not to the literal
`azureuser`, which is only the fallback when Azure does not report one. Until
this flag was wired it was discarded entirely, so a VM with a different admin
user worked by accident and `--user deploy` did nothing at all.

`azlin connect --user` had the same flag and a different bug: it was read, and
then lost every time, because the VM's admin username was preferred over it and
Azure reports one for every VM azlin creates. Both now mean the same thing — an
explicit `--user` wins, and omitting it uses the VM's admin user.

> **Session names are not scoped by resource group.** `azlin session` stores
> them keyed by VM name alone, so two VMs called `dev` in different resource
> groups share one name. Tracked as
> [#1122](https://github.com/rysweet/azlin/issues/1122); `azlin session
> --resource-group` is accepted and discarded until it is fixed.

### `--no-extensions` and `~/.azlin/vscode/` are not implemented

`azlin code` opens a `vscode-remote://` URI and installs nothing. VS Code's own
Remote-SSH decides which extensions to install on a host, from **its** settings;
azlin is not part of that conversation, so there is no install for
`--no-extensions` to skip.

This section used to document `~/.azlin/vscode/extensions.json`, `ports.json`
and `settings.json` as files azlin reads. It does not read them, and never did
in the Rust CLI — creating them has no effect. They are documented here as
absent rather than quietly dropped, because a user who built those files
deserves to know why nothing happened. Tracked with the flag under #1089.

---

## clone

Clone an existing VM to create one or more replicas with the same configuration.

```
azlin clone <SOURCE_VM> [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `SOURCE_VM` | **Yes** | Name of the VM to clone |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--num-replicas` | `INT` | `1` | Number of clones to create |
| `--session-prefix` | `TEXT` | — | Session name prefix for clones |
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--vm-size` | `TEXT` | same as source | VM size for clones |
| `--region` | `TEXT` | same as source | Azure region for clones |
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |

### Behaviour notes

> **Clones now match the source's size.** Until these flags were wired, `--vm-size` was
> discarded *and* its documented default was not implemented: `azlin clone web` produced a VM at
> **Azure's** default SKU, not the source's. A clone of a `Standard_D8s_v5` now comes back as a
> `Standard_D8s_v5` — roughly eight times the machine, and eight times the bill, compared with
> what the same command produced before. That is what `--help` has always promised; pass
> `--vm-size` explicitly if you were relying on getting a small clone.

- `--vm-size` defaults to the source VM's own size, read from Azure. A source whose size cannot
  be read is an error naming `--vm-size` rather than a silent fall back to Azure's default.
- `--region` sends the clone elsewhere. The snapshot is created **incremental** and referenced by
  its resource id, which is what Azure requires for a cross-region copy; support still varies by
  disk type and region pair, and a refusal arrives after the snapshot has been created and is
  billing. azlin says so before it starts.
- `--session-prefix` sets the `azlin-session` tag, so clones appear as a session in `azlin list`.
  With a prefix and more than one replica the group is numbered (`canary-1`, `canary-2`); a single
  clone takes the prefix unnumbered; without a prefix each clone's own name is its session.
- A clone that fails exits **non-zero** and names the snapshot left behind, which is still billing.
  Every clone's error is printed first, so a partial failure never hides the ones that worked.

### Examples

```bash
# Clone a VM (single replica, same size and region as the source)
azlin clone my-existing-vm

# Clone 3 replicas as one numbered session group
azlin clone my-existing-vm --num-replicas 3 --session-prefix test-batch

# Clone to a different VM size and region
azlin clone my-existing-vm --vm-size Standard_D4s_v3 --region westus2
```

---

## list

List VMs in a resource group with status, IP, size, and session information.

```
azlin list [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--all` | flag | `false` | Show all VMs including stopped |
| `--tag` | `TEXT` | — | Filter VMs by tag (format: key or key=value) |
| `--show-tmux` | flag | `true` | Show active tmux sessions (use `--no-tmux` to disable) |
| `--no-tmux` | flag | `false` | Disable tmux session checking |
| `--with-latency` | flag | `false` | Show SSH latency for each VM |
| `--show-procs` | flag | `false` | Show top processes on each VM |
| `--with-health` | flag | `false` | Show VM health metrics (CPU, memory, disk) |
| `-w`, `--wide` | flag | `false` | Wide output (don't truncate VM names) |
| `-c`, `--compact` | flag | `false` | Compact output |
| `--no-cache` | flag | `false` | Skip cache, fetch fresh data |
| `-q`, `--quota` | flag | `false` | Show vCPU quota summary |
| `-a`, `--show-all-vms` | flag | `false` | Scan all resource groups |
| `--vm-pattern` | `TEXT` | — | Filter VMs by name pattern (glob) |
| `--include-stopped` | flag | `false` | Include stopped/deallocated VMs (alias for `--all`) |
| `--all-contexts` | flag | `false` | List VMs across all contexts |
| `--contexts` | `TEXT` | — | Filter contexts by glob pattern (e.g., "prod*") |
| `-r`, `--restore` | flag | `false` | Restore tmux sessions after listing |
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |
| `--verbose` | flag | `false` | Enable verbose output |

### Examples

```bash
# List running VMs
azlin list

# List all VMs including stopped ones
azlin list --include-stopped

# Filter by name pattern with verbose output
azlin list --vm-pattern "dev-*" --verbose

# List VMs in a specific resource group
azlin list --rg production-rg
```

---

## batch stop

Stop and deallocate multiple VMs simultaneously.

```
azlin batch stop [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--tag` | `TEXT` | — | Filter VMs by tag (`key=value`) |
| `--vm-pattern` | `TEXT` | — | Filter VMs by name pattern (glob) |
| `--all` | flag | `false` | Select all VMs in the resource group |
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |
| `--no-deallocate` | flag | `false` | Stop without deallocating (continues billing) |
| `--max-workers` | `INT` | `10` | Maximum parallel workers |
| `--yes`, `-y` | flag | `false` | Skip confirmation prompt |

By default, stopped VMs are **deallocated** (no compute billing). Use `--no-deallocate` to keep the VM allocated for faster restart at the cost of continued billing.

### Selection and concurrency across `batch`

These apply to `batch stop`, `batch start`, `batch command` and `batch sync` alike.

- `--tag` and `--vm-pattern` both narrow; passing both requires a VM to match both. A malformed `--tag` (no `=`) is rejected rather than discarded.
- `--all` means "every VM" and cannot be combined with `--tag` or `--vm-pattern`; the combination is rejected rather than silently resolved.
- For `batch command` and `batch sync`, a selector that matches **no** running VM is an error, not a quiet success — a scripted run must not go green having touched no host.
- `--max-workers` is a real concurrency limit. Each VM costs a full `az` process start even with `--no-wait`, so the default of 10 is what keeps a fifty-VM stop from spending a minute and a half in Python startup. Results are reported in input order whatever order the operations finish in.
- Independently of `--max-workers`, `batch stop` and `batch start` pace their ARM writes to 10/second with a burst of 10. `--no-wait` returns immediately, so a high worker count would otherwise put that many writes in flight and keep them coming; ARM's write limits are per-subscription and shared with everything else you are running.
- For `batch command` and `batch sync`, **a selector that matches no running VM now exits non-zero.** Previously it printed "no VMs matched" and exited 0. A scheduled job whose filter matches nothing on a quiet week will start failing; that is the intended behaviour — the alternative is a green run that touched no host.
- `batch command --timeout` is enforced **on the VM** (`timeout(1)`), so a runaway process is killed rather than orphaned, and each VM that hits it is named on stderr.
- `batch sync` exits non-zero when any dotfile transfer fails, instead of printing "Sync complete." under a wall of rsync errors.

### Examples

```bash
# Stop and deallocate all dev VMs (default: deallocate=true)
azlin batch stop --tag 'env=dev'

# Stop VMs matching a pattern without deallocating
azlin batch stop --vm-pattern 'test-*' --no-deallocate

# Stop all VMs, skip confirmation
azlin batch stop --all --yes
```

---

## disk add

Attach a new managed disk to an existing VM, then format and mount it.

```
azlin disk add <VM_NAME> --size <GB> [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `VM_NAME` | **Yes** | Name of the target VM |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--size` | `INT` | — (**required**) | Disk size in GB |
| `--mount` | `TEXT` | `/tmp` | Mount point on the VM |
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |
| `--sku` | `CHOICE` | `Standard_LRS` | Storage SKU |

### SKU Options

| SKU | Description | Use Case |
|-----|-------------|----------|
| `Standard_LRS` | Standard HDD (default) | Cost-effective general storage |
| `Premium_LRS` | Premium SSD | High-performance workloads |
| `StandardSSD_LRS` | Standard SSD | Balanced price/performance |

### Examples

```bash
# Add a 64GB disk at the default mount point (/tmp)
azlin disk add my-vm --size 64

# Add a 128GB disk at a custom mount point
azlin disk add my-vm --size 128 --mount /data

# Add a premium SSD disk
azlin disk add my-vm --size 256 --mount /fast-storage --sku Premium_LRS
```

---

## fleet run

Execute a command across multiple VMs with conditional scheduling.

```
azlin fleet run <COMMAND> [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `COMMAND` | **Yes** | Shell command to execute on each VM |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--tag` | `TEXT` | — | Filter VMs by tag (`key=value`) |
| `--pattern` | `TEXT` | — | Filter VMs by name pattern (glob) |
| `--all` | flag | `false` | Run on all VMs |
| `--parallel` | `INT` | `10` | Maximum parallel workers |
| `--if-idle` | flag | `false` | Only run on idle VMs |
| `--if-cpu-below` | `INT` | — | Only run if CPU usage below threshold (%) |
| `--if-mem-below` | `FLOAT` | — | Only run if memory usage below threshold (%) |
| `--smart-route` | flag | `false` | Route to least-loaded VMs first |
| `--count` | `INT` | — | Maximum number of VMs to target |
| `--retry-failed` | flag | `false` | Retry failed executions |
| `--show-diff` | flag | `false` | Show diff of command outputs |
| `--timeout` | `INT` | `300` | Command timeout in seconds |
| `--dry-run` | flag | `false` | Show what would be executed |

The `--if-mem-below` flag accepts a float value representing a memory usage percentage. VMs with memory usage at or above this threshold are skipped.

### Selection semantics

- `--tag` and `--pattern` both narrow the selection; passing both requires a VM to match both.
- `--all` means "every running VM" and cannot be combined with `--tag` or `--pattern`; the combination is rejected rather than silently resolved in favour of one of them.
- With no selector at all, `fleet run` targets every running VM in the resource group and says so in its banner.
- A selector that matches **no** running VM is an error, not a quiet success: the command exits non-zero rather than reporting green having run on nothing.
- `--if-idle`, `--if-cpu-below` and `--if-mem-below` need a load reading, taken from a real one-second interval sample (not `top`'s since-boot average). A VM whose load cannot be sampled is **skipped and named**, not assumed idle. Nothing surviving the gates is a result, not an error, and exits 0.
- `--smart-route` orders targets least-loaded first; a VM with no usable reading sorts last. Combined with `--count N` this picks the N least-loaded VMs.
- `--timeout` is enforced on the VM (`timeout(1)`), so a runaway process is killed rather than orphaned, and the transport is given a longer budget so the remote limit is the one that fires.
- `--show-diff` groups VMs by identical `(exit status, output)`, largest group first, instead of opening the per-VM tab view. Two VMs that both printed nothing are only grouped together if they also exited the same way.
- `--parallel` is a real concurrency limit. On bastion-routed VMs each worker is a separate `az network bastion ssh` process, so the default of 10 means ten Azure CLI processes at once; pass a lower `--parallel` on a small control machine.

### Examples

```bash
# Run tests on all idle VMs
azlin fleet run "npm test" --if-idle --parallel 5

# Deploy to web servers with retry
azlin fleet run "deploy.sh" --tag role=web --retry-failed

# Run on VMs with memory below 80%
azlin fleet run "heavy-job.sh" --if-mem-below 80.0

# Execute on the 3 least-loaded VMs
azlin fleet run "backup.sh" --smart-route --count 3
```

---

## restore

Restore all active azlin sessions by launching new terminal windows.

```
azlin restore [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--resource-group`, `--rg` | `TEXT` | config default | Filter to specific resource group |
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |
| `--skip-health-check` | flag | `false` | Skip VM health checks |
| `--force` | flag | `false` | Force restore even if VMs are stopped |
| `--terminal` | `TEXT` | auto-detected | Override terminal launcher |
| `--exclude` | `TEXT` | — | Exclude VMs by name pattern |
| `--dry-run` | flag | `false` | Show what would happen without launching terminals |
| `--no-multi-tab` | flag | `false` | Disable multi-tab mode (Windows Terminal only) |
| `--verbose` | flag | `false` | Enable verbose output |

### Terminal Launchers

| Launcher | Platform | Description |
|----------|----------|-------------|
| `macos_terminal` | macOS | Terminal.app (default on macOS) |
| `windows_terminal` | Windows/WSL | Windows Terminal wt.exe (default on Windows/WSL) |
| `linux_gnome` | Linux | gnome-terminal (default on Linux) |
| `linux_xterm` | Linux | xterm (fallback on Linux) |

### Examples

```bash
# Restore all sessions
azlin restore

# Preview what would happen
azlin restore --dry-run

# Restore without multi-tab, verbose output
azlin restore --no-multi-tab --verbose

# Restore sessions from specific resource group
azlin restore --rg my-dev-rg
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All sessions restored |
| `1` | Partial failure (some sessions failed) |
| `2` | Total failure (no sessions restored) |

---

## autopilot enable

Enable autopilot scheduling for automatic VM start/stop based on usage patterns.

```
azlin autopilot enable [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--idle-threshold` | `INT` | `120` | Idle time in minutes before auto-stop |
| `--cpu-threshold` | `INT` | `20` | CPU percentage below which VM is considered idle |
| ~~`--schedule`~~ | — | — | *Removed — not implemented in Rust CLI* |

### Examples

```bash
# Enable with defaults (stop after 120min idle, CPU < 20%)
azlin autopilot enable

# Custom thresholds: stop after 60min idle at CPU < 5%
azlin autopilot enable --idle-threshold 60 --cpu-threshold 5

# Enable for a specific resource group
azlin autopilot enable --rg dev-rg
```

---

## logs

View or stream log files from a VM.

```
azlin logs <VM_IDENTIFIER> [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `VM_IDENTIFIER` | Yes | VM name, session name, or IP address |

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--lines`, `-n` | `INT` | `100` | Number of lines to display |
| `--follow`, `-f` | flag | `false` | Stream logs in real-time (`tail -f`) |
| `--type`, `-t` | `TEXT` | `syslog` | Log type: `syslog`, `cloud-init`, `auth`, `azlin`, `all` |
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |

### Log Types

| Type | Log File |
|------|----------|
| `syslog` | `/var/log/syslog` |
| `cloud-init` | `/var/log/cloud-init-output.log` |
| `auth` | `/var/log/auth.log` |
| `azlin` | `/var/log/azlin/azlin.log` |
| `all` | All four log files |

> **Note**: `--type all` with `--follow` produces interleaved output from all four files. For easier reading, use `--type all` without `--follow` for a snapshot, or target a specific log type when streaming.

### Examples

```bash
# View last 100 lines of syslog (defaults)
azlin logs my-vm

# Stream syslog in real-time
azlin logs my-vm --follow

# View cloud-init provisioning logs
azlin logs my-vm --type cloud-init

# View last 50 lines of auth logs
azlin logs my-vm --type auth --lines 50

# Snapshot of all log types
azlin logs my-vm --type all
```

---

## github-runner enable

Provision a pool of self-hosted GitHub Actions runner VMs.

```
azlin github-runner enable [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--repo` | `TEXT` | — | Repository the pool serves (recorded in tags and config) |
| `--pool` | `TEXT` | — | Pool name; VMs are `azlin-runner-<pool>-<n>` |
| `--count` | `INT` | — | How many runner VMs to create |
| `--labels` | `TEXT` | `self-hosted` | Runner labels (recorded in config) |
| `--vm-size` | `TEXT` | `Standard_B2s` | VM size |
| `--resource-group`, `--rg` | `TEXT` | config default | Azure resource group |
| `--auto-scale` | flag | `false` | **Not implemented** — see below |
| `--yes` | flag | `false` | Create the region's bastion and NAT gateway without asking |

### Runners have no public IP

> **This changed.** Until #1123, this command built its own `az vm create`
> invocation instead of going through azlin's shared creation path — and
> inherited Azure's default, which is a **public IP on every VM**. Every runner
> the command has ever created is reachable from the internet, and the output
> said only `Provisioned VM 'azlin-runner-ci-1'`.
>
> Runners are now created the same way `azlin new` creates VMs: no public IP,
> on the region's bastion VNet. **Existing runner VMs are not changed** —
> `azlin github-runner disable` and re-enabling the pool replaces them.

Because a bastion is inbound only, a private VM with no NAT gateway can be
reached and cannot reach anything — and a runner that cannot reach github.com
is not a runner. Enabling a pool therefore ensures both the bastion
infrastructure and the NAT gateway for the region before any VM is created.
Both are regional and shared with every other azlin VM in that region.

**Creating either is asked for first**, because both are billed monthly for as
long as they exist — the same consent `azlin new` asks for. Only what is
actually missing is offered, so enabling a second pool in a region that is
already set up asks nothing. `--yes` gives consent up front; without a terminal
and without the flag, the command refuses rather than provisioning.

(The bastion and the NAT gateway each carry a public IP of their own; that is
what they are. The change here is that the *runner VMs* no longer do.)

The region comes from `default_region` in the config and is recorded in the
pool's TOML file, so `status` and `disable` can tell which region a pool lives
in. A pool lives in exactly one region: re-running `enable` for an existing pool
after changing `default_region` is **refused**, because the second run would
create VMs with the same names in a different region of the same resource group.
Disable the pool first, or set the region back.

### Runners stay on Ubuntu 22.04

The command has always created 22.04 runners, and there is no `--image` flag to
ask for anything else. Routing this path through azlin's shared VM creation made
it tempting to take that path's default — now 26.04 — which would have moved
every re-enabled pool four releases forward silently. `azlin new` defaults to
26.04; runner pools do not.

### A pool that partly fails now exits non-zero

`azlin github-runner enable --count 5` with five failures used to print five
errors and exit 0. It now exits non-zero, naming the VMs that did not come up —
after writing the pool config and reporting every VM, so a partial failure
never hides the runners that did come up. The message says plainly that the
config was still written and that `status` will report the pool as enabled with
fewer runners than requested.

### `--auto-scale` is not implemented

`enable` provisions `--count` VMs once and writes a TOML file. Nothing watches a
queue, nothing creates or removes a runner afterwards, and no process is left
running to do either. Wiring the flag means building a scaler — a service, not a
flag. Tracked under #1089.

---

## doit deploy

Ask the model for a plan of `az` commands and run them.

```
azlin doit deploy <REQUEST> [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--output-dir` | `PATH` | — | Write the plan and a transcript of the run here |
| `--max-iterations` | `INT` | `50` | Most commands a plan may contain (`0` = no limit) |
| `--dry-run` | flag | `false` | Show the plan without running it |
| `--quiet` | flag | `false` | Suppress progress; failures are still reported |
| `--yes` | flag | `false` | Skip the confirmation prompt |

### Behaviour notes

All three of `--output-dir`, `--max-iterations` and `--quiet` were accepted and
discarded until #1089. The middle one is the one that mattered: **nothing
bounded how many commands a model could hand back to be executed against a live
subscription**, while `--help` advertised a limit of 50.

- A plan over the limit is **refused whole, not truncated**. Running the first
  50 of 80 commands leaves the subscription in a state neither the user nor the
  model intended, and half a deployment is worse than none. The refusal comes
  before the confirmation prompt, so nobody approves a plan that will then be
  rejected.
- `--max-iterations 0` means no limit, the same reading every other azlin
  numeric limit gives zero.
- The flag says "iterations" and counts **commands**. They are the same number
  because each command in a plan runs exactly once — no retries, no loops, no
  second pass. If that ever changes, the name and the behaviour part company,
  so it is written down here and at the check itself.
- `--output-dir` writes `plan.txt` (before anything runs) and `transcript.txt`
  (one line per command, recording how each ended). A command killed by a
  signal is recorded as a failure, not as a success with no exit code. The
  directory is created before the model is called, so a path that cannot be
  written is an error you can fix rather than one that arrives after paying for
  a plan.
- `--quiet` suppresses progress only. Failures, the over-limit refusal, and the
  confirmation prompt are not progress — a quiet flag that hides why a
  deployment stopped is worse than a loud one.

---

Autonomous cleanup of previously deployed infrastructure. Both `destroy` and `delete` are aliases that perform identical cleanup operations.

```
azlin doit destroy [OPTIONS]
azlin doit delete [OPTIONS]
```

### Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--force` | flag | `false` | Skip confirmation prompt |
| `--dry-run` | flag | `false` | Show what would be deleted without deleting |
| `--username` | `TEXT` | — | Filter cleanup to resources created by a specific user |

Both subcommands are aliases for the existing `doit cleanup` handler, removing infrastructure resources tagged with `created_by: "azlin-doit"`. Resources originally deployed via `azlin doit deploy` are targeted for removal.

### Examples

```bash
# Interactive cleanup with confirmation
azlin doit destroy

# Preview what would be cleaned up
azlin doit delete --dry-run

# Force cleanup without confirmation
azlin doit destroy --force

# Clean up resources for a specific user
azlin doit delete --username rysweet --force
```

---

## Default Values Reference

All default values match the original Python CLI:

| Command | Flag | Default |
|---------|------|---------|
| `code` | `--user` | `azureuser` |
| `code` | `--workspace` | `/home/user` |
| `disk add` | `--sku` | `Standard_LRS` |
| `disk add` | `--mount` | `/tmp` |
| `autopilot enable` | `--idle-threshold` | `120` (minutes) |
| `autopilot enable` | `--cpu-threshold` | `20` (percent) |
| `batch stop` | deallocate behavior | `true` (use `--no-deallocate` to override) |
| `fleet run` | `--parallel` | `10` |
| `restore` | `--force` | `false` (force restore) |
| `logs` | `--lines` | `100` |
| `logs` | `--type` | `syslog` |
| `connect` | `--yes` | `false` (prompt for confirmation) |

---

## Migration Notes

Users migrating from the Python CLI will find identical flag names and defaults. Behavioral differences:

- **Global `-v`**: The global `--verbose` / `-v` flag applies to all commands. Command-specific verbose flags (on `list` and `restore`) use `--verbose` (long form only) to avoid conflict with the global short flag.
- **`code` VM identifier**: The `VM_IDENTIFIER` argument is required (not optional). Omitting it produces a clear error message.
- **Output format**: Use `-o json` or `--output json` (global flag, default `table`) for machine-readable output. Also supports `csv`.

## See Also

- [Quick Reference](../QUICK_REFERENCE.md) — Common command patterns
- [Configuration Reference](./configuration-reference.md) — Config file options
- [Logs Command Reference](./logs-command.md) — Detailed logs command docs
- [Restore Help](./cli-help-restore.md) — Detailed restore command docs
- [Destroy Command](./destroy-command.md) — Detailed destroy command docs
