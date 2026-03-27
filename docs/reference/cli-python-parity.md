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
| `--user` | `TEXT` | `azureuser` | SSH username for the connection |
| `--key` | `PATH` | — | SSH private key path |
| `--no-extensions` | flag | `false` | Skip VS Code extension installation (faster launch) |
| `--workspace` | `TEXT` | `/home/<user>` | Remote workspace directory to open (resolves `<user>` from `--user`) |

### Examples

```bash
# Launch VS Code for a VM (uses default user and workspace)
azlin code my-dev-vm

# Connect as a different user with a specific key
azlin code my-dev-vm --user ubuntu --key ~/.ssh/custom_key

# Open a specific workspace directory, skip extensions
azlin code my-dev-vm --workspace /home/azureuser/projects --no-extensions

# Explicit resource group
azlin code my-dev-vm --rg my-resource-group
```

### Configuration

VS Code settings are read from `~/.azlin/vscode/`:

| File | Purpose |
|------|---------|
| `extensions.json` | Extensions to install: `{"extensions": ["ms-python.python", ...]}` |
| `ports.json` | Port forwarding: `{"forwards": [{"local": 3000, "remote": 3000}]}` |
| `settings.json` | VS Code workspace settings |

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

### Examples

```bash
# Clone a VM (single replica, same size and region)
azlin clone my-existing-vm

# Clone 3 replicas with a session prefix
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
| `--config` | `PATH` | `~/.azlin/config.toml` | Config file path |
| `--vm-pattern` | `TEXT` | — | Filter VMs by name pattern (glob) |
| `--include-stopped` | flag | `false` | Include stopped/deallocated VMs |
| `--verbose` | flag | `false` | Enable verbose output with extra detail |

The `--verbose` flag shows additional columns and detail in the VM listing, including full resource IDs, disk information, and network details.

> **Note:** Use `--verbose` (long form only). The `-v` short flag is reserved for the global verbose option.

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
| `--mount` | `TEXT` | `/mnt/data` | Mount point on the VM |
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
# Add a 64GB disk at the default mount point (/mnt/data)
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

The `--if-mem-below` flag accepts a float value representing a memory usage percentage. VMs with memory usage at or above this threshold are skipped.

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
| `--terminal` | `TEXT` | auto-detected | Override terminal launcher |
| `--dry-run` | flag | `false` | Show what would happen without launching terminals |
| `--no-multi-tab` | flag | `false` | Disable multi-tab mode (Windows Terminal only) |
| `--timeout` | `INT` | `30` | Timeout per session in seconds |
| `--verbose` | flag | `false` | Enable verbose output |

> **Note:** Use `--verbose` (long form only). The `-v` short flag is reserved for the global verbose option.

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
| `code` | `--workspace` | `/home/<user>` (dynamic) |
| `disk add` | `--sku` | `Standard_LRS` |
| `disk add` | `--mount` | `/mnt/data` |
| `autopilot enable` | `--idle-threshold` | `120` (minutes) |
| `autopilot enable` | `--cpu-threshold` | `20` (percent) |
| `batch stop` | deallocate behavior | `true` (use `--no-deallocate` to override) |
| `fleet run` | `--parallel` | `10` |
| `restore` | `--timeout` | `30` (seconds) |
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
