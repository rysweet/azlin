# How to Use SSH Tunnels

Forward remote VM ports to your local machine for database access, web
development, API testing, and more.

## Quick Start

```bash
# Forward a single port (remote 8080 → localhost:8080)
azlin tunnel open myvm 8080

# Forward multiple ports at once
azlin tunnel open myvm 8080 3000 5432

# Map to a different local port
azlin tunnel open myvm 5432 --local-port 15432

# List active tunnels
azlin tunnel list

# Close tunnels for a specific VM
azlin tunnel close myvm

# Close all tunnels
azlin tunnel close --all
```

## How It Works

Azlin detects whether a VM is bastion-routed (private, no public IP) or
direct (has a public IP) and spawns the correct SSH tunnel automatically.

| VM Type | Detection | Tunnel Method |
|---------|-----------|---------------|
| **Bastion-routed** | No public IP on VM | `az bastion tunnel` → SSH `-L` via 127.0.0.1 |
| **Direct** | Has public IP | SSH `-L` directly to VM IP |

You do not need to know which type your VM is — `azlin tunnel open` handles
both transparently.

## Authentication

### SSH Username

The `--user` flag defaults to `azureuser`. For most azlin-provisioned VMs this
is correct because the VM metadata stores the admin username and azlin resolves
it automatically:

```
CLI --user default ("azureuser")
        ↓
VM metadata (vm.admin_username)  ← preferred if present
        ↓
Final SSH username
```

Override only if you provisioned the VM with a non-standard username:

```bash
azlin tunnel open myvm 8080 --user ubuntu
```

### SSH Key

When no `--key` is specified, azlin automatically resolves the SSH key using
the same logic as `azlin connect`:

1. `~/.ssh/azlin_key` (preferred — created by `azlin new`)
2. `~/.ssh/id_ed25519_azlin`
3. `~/.ssh/id_ed25519`
4. `~/.ssh/id_rsa`

Azlin checks these in order and uses the first one that exists. If none are
found, SSH is invoked without `-i` and uses its own agent/default key logic.

Override with an explicit path:

```bash
azlin tunnel open myvm 8080 --key ~/.ssh/my_custom_key
```

### Host Key Verification

- **Direct tunnels** use `StrictHostKeyChecking=accept-new` — new keys are
  accepted on first connection; changed keys are rejected (security default).
- **Bastion tunnels** use `StrictHostKeyChecking=no` with a disposable
  known-hosts file — because bastion tunnels reuse local loopback ports
  (`127.0.0.1:50200+`) across different VMs, the host key legitimately changes.
  This is safe because the bastion connection is already authenticated through
  Azure.

## Common Patterns

### Database Access

Forward PostgreSQL from a bastion-routed VM:

```bash
azlin tunnel open db-server 5432 --local-port 15432
psql -h localhost -p 15432 -U myuser mydb
```

### Web Development

Forward a dev server and API:

```bash
azlin tunnel open dev-vm 3000 8080
# Browser: http://localhost:3000
# API:     http://localhost:8080
```

### Jupyter Notebook

```bash
azlin tunnel open ml-vm 8888
# Browser: http://localhost:8888
```

### Custom Local Port

When the remote port conflicts with a local service:

```bash
azlin tunnel open myvm 8080 --local-port 9090
# Access at localhost:9090 instead of localhost:8080
```

> **Note:** `--local-port` only works with a single port. For multiple ports,
> each remote port maps to the same local port number.

## Managing Tunnels

### List Active Tunnels

```bash
azlin tunnel list
```

Output (table format):

```
VM Name     Local Port  Remote Port  PID
dev-vm      8080        8080         12345
dev-vm      3000        3000         12346
db-server   15432       5432         12347
```

JSON output for scripting:

```bash
azlin tunnel list -o json
```

### Close Tunnels

```bash
# Close all tunnels for a VM
azlin tunnel close dev-vm

# Close everything
azlin tunnel close --all
```

Tunnels are also cleaned up when you press `Ctrl+C` in the terminal where
`azlin tunnel open` is running.

### Stale Tunnel Cleanup

Azlin automatically prunes stale tunnel entries (where the SSH process has
exited) whenever you run any tunnel command. No manual cleanup is needed.

## Tunnel State

Active tunnels are tracked in `~/.azlin/tunnels.json`. This file is managed
automatically — you should not need to edit it. If tunnels get into a bad
state, delete the file and any orphaned SSH processes:

```bash
rm ~/.azlin/tunnels.json
# Find and kill orphaned tunnel SSH processes if needed
ps aux | grep 'ssh -N -L'
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Permission denied (publickey)" | Wrong SSH key | Ensure `~/.ssh/azlin_key` (or `id_ed25519`, `id_rsa`) exists, or use `--key` |
| Tunnel opens but connection refused | Remote service not listening | Verify service runs on the remote port |
| "Failed to spawn az bastion tunnel" | Azure CLI not installed/authenticated | Run `az login` |
| Bastion tunnel hangs | Bastion takes time to establish | Wait 5–10s; check `az account show` works |
| Port already in use | Another tunnel or local service on that port | Use `--local-port` to pick a different local port |

See also:
- [Troubleshoot Tunnel Issues](../troubleshooting/tunnel-issues.md)
- [Troubleshoot Connection Issues](troubleshoot-connection-issues.md)

## CLI Reference

```
azlin tunnel open [OPTIONS] <VM_IDENTIFIER> <PORTS>...

Arguments:
  <VM_IDENTIFIER>   VM name, session name, or IP address
  <PORTS>...        Remote port(s) to forward

Options:
  --local-port <PORT>         Local port (single-port forwarding only)
  --user <USER>               SSH username [default: azureuser]
  --key <KEY>                 SSH private key path
  --resource-group <RG>       Resource group
  -v, --verbose               Enable verbose output
  -o, --output <FORMAT>       Output format [default: table]
```
