# How to View VM Logs

View and stream log files from your azlin VMs without SSH-ing in manually.

## View recent system logs

```bash
azlin logs my-vm
```

Shows the last 100 lines of `/var/log/syslog` (the default log type).

## Stream logs in real-time

```bash
azlin logs my-vm --follow
```

Streams syslog continuously until you press Ctrl+C. Useful for watching deployments or debugging live issues.

## View a specific log type

```bash
azlin logs my-vm --type cloud-init    # Provisioning output
azlin logs my-vm --type auth          # SSH logins, sudo events
azlin logs my-vm --type azlin         # Azlin agent activity
```

## Control how many lines to show

```bash
azlin logs my-vm --lines 20           # Last 20 lines
azlin logs my-vm --type auth -n 500   # Last 500 auth log lines
```

## View all log types at once

```bash
azlin logs my-vm --type all
```

This shows the last 100 lines from each of the four log files: syslog, cloud-init, auth, and azlin.

> **Tip**: Avoid combining `--type all` with `--follow`. Streaming four files simultaneously produces interleaved output that is hard to read. Instead, target the specific log type you need when using `--follow`.

## Check provisioning issues on a new VM

```bash
azlin logs my-new-vm --type cloud-init --lines 200
```

Cloud-init logs contain the full output of VM provisioning, including tool installation and configuration. Check here first when a newly created VM isn't behaving as expected.

## View logs from a VM in a specific resource group

```bash
azlin logs my-vm --type syslog --rg production-rg
```

## See Also

- [Logs Command Reference](../reference/logs-command.md) — Full flag and option details
- [CLI Command Reference](../reference/cli-python-parity.md) — All CLI flags and defaults
- [Troubleshoot Connection Issues](./troubleshoot-connection-issues.md) — When logs won't load
