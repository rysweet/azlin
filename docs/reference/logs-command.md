# CLI Reference — azlin logs

View or stream log files from a VM over SSH (or Azure Bastion).

## Usage

```
azlin logs <VM_IDENTIFIER> [OPTIONS]
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `VM_IDENTIFIER` | Yes | VM name, session name, or IP address |

## Options

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--lines` | `-n` | `INT` | `100` | Number of log lines to display |
| `--follow` | `-f` | flag | `false` | Stream logs continuously (`tail -f`) |
| `--type` | `-t` | `TEXT` | `syslog` | Log type to view (see below) |
| `--resource-group` | `--rg` | `TEXT` | config default | Azure resource group |

## Log Types

| Value | File Path | Description |
|-------|-----------|-------------|
| `syslog` | `/var/log/syslog` | System messages (default) |
| `cloud-init` | `/var/log/cloud-init-output.log` | VM provisioning output |
| `auth` | `/var/log/auth.log` | SSH and authentication events |
| `azlin` | `/var/log/azlin/azlin.log` | Azlin agent activity |
| `all` | All four files above | Combined view of all log types |

## Behavior

- Without `--follow`: runs `sudo tail -n <lines> <log_path>` and exits.
- With `--follow`: runs `sudo tail -f <log_path>` and streams until interrupted (Ctrl+C).
- With `--type all`: expands to all four log file paths. When combined with `--follow`, output from all files is interleaved — use a specific type for cleaner streaming.
- Works over both direct SSH and Azure Bastion tunnels.

## Examples

```bash
# View last 100 lines of syslog (all defaults)
azlin logs my-vm

# Stream syslog in real-time
azlin logs my-vm --follow

# View cloud-init provisioning logs
azlin logs my-vm --type cloud-init

# View last 50 lines of auth logs
azlin logs my-vm --type auth --lines 50

# View last 200 lines of azlin agent logs
azlin logs my-vm --type azlin -n 200

# Snapshot of all log types (recommended over --type all --follow)
azlin logs my-vm --type all

# Specify resource group explicitly
azlin logs my-vm --type syslog --rg production-rg
```

## Configuration Defaults

Override defaults in `~/.azlin/config.toml`:

```toml
[log_viewer]
default_lines = 100      # --lines default
default_type = "syslog"   # --type default
```

## See Also

- [Quick Reference](../QUICK_REFERENCE.md) — Common command patterns
- [CLI Command Reference](./cli-python-parity.md) — All CLI flags and defaults
- [How to View VM Logs](../how-to/view-vm-logs.md) — Task-focused guide
