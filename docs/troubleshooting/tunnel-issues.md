# Troubleshooting Tunnel Issues

Diagnosis and resolution guide for `azlin tunnel open` failures.

## Quick Diagnosis

```bash
# Run with verbose logging to see SSH commands
azlin tunnel open myvm 8080 -v
```

## Common Issues

### Tunnel Opens but SSH Dies Immediately

**Symptoms:** `azlin tunnel open` reports success but the forwarded port is
not reachable. `azlin tunnel list` shows no active tunnels (or entries with
dead PIDs).

**Diagnosis:** Run with `-v` and look for SSH exit reasons:

```bash
azlin tunnel open myvm 8080 -v
```

Common causes and fixes:

| SSH Error | Root Cause | Fix |
|-----------|-----------|-----|
| `Permission denied (publickey)` | SSH key not found | Ensure `~/.ssh/azlin_key` exists (created by `azlin new`), or one of `id_ed25519_azlin`, `id_ed25519`, `id_rsa`; or pass `--key` |
| `Host key verification failed` | Stale known_hosts entry for 127.0.0.1 | Bastion tunnels handle this automatically; for direct tunnels, remove the stale entry from `~/.ssh/known_hosts` |
| `Connection refused` | Bastion tunnel not yet established | Increase patience; the bastion takes ~3s to start |

### Wrong Username

**Symptoms:** `Permission denied` despite having the correct key.

**Diagnosis:** The `--user` flag defaults to `azureuser`. Most azlin VMs use
this username, but if your VM was provisioned differently:

```bash
# Check what username the VM expects
azlin list -o json | jq '.[] | select(.name=="myvm") | .admin_username'

# Override explicitly
azlin tunnel open myvm 8080 --user ubuntu
```

Azlin resolves the username from VM metadata when available, so this override
is rarely needed for azlin-provisioned VMs.

### Port Already in Use

**Symptoms:** `Address already in use` error.

**Fix:** Choose a different local port:

```bash
azlin tunnel open myvm 8080 --local-port 9080
```

Or find and close the conflicting process:

```bash
lsof -i :8080
```

### Bastion Tunnel Fails to Start

**Symptoms:** `Failed to spawn az bastion tunnel` error.

**Checklist:**

1. **Azure CLI installed?** — `az --version`
2. **Logged in?** — `az account show` (run `az login` if needed)
3. **Bastion exists?** — The VM's virtual network must have an associated
   Azure Bastion resource
4. **Permissions?** — You need `Microsoft.Network/bastionHosts/connect/action`
   on the bastion resource

### Stale Tunnel State

**Symptoms:** `azlin tunnel list` shows tunnels that are not actually running,
or new tunnels fail because ports appear occupied.

**Fix:** Azlin prunes stale entries automatically, but if the state file is
corrupted:

```bash
rm ~/.azlin/tunnels.json
```

Then kill any orphaned SSH processes manually:

```bash
ps aux | grep 'ssh -N -L' | grep -v grep
# kill <PID> for each orphaned process
```

## Bastion vs Direct Tunnels

Understanding which tunnel type azlin uses helps with diagnosis:

| | Bastion-Routed | Direct |
|--|----------------|--------|
| **When used** | VM has no public IP | VM has public IP |
| **Mechanism** | `az bastion tunnel` + SSH through 127.0.0.1 | SSH directly to VM IP |
| **Host key policy** | `StrictHostKeyChecking=no` (loopback ports are reused) | `StrictHostKeyChecking=accept-new` |
| **Extra dependency** | Azure CLI (`az`) | None |
| **Common failure** | Azure auth expired | Firewall blocking SSH port 22 |

## See Also

- [How to Use Tunnels](../how-to/use-tunnels.md)
- [Troubleshoot Connection Issues](../how-to/troubleshoot-connection-issues.md)
- [Bastion Default Quick Start](../BASTION_DEFAULT_QUICK_START.md)
