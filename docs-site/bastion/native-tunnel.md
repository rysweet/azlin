# Native Bastion Tunnel

Azlin connects to VMs through Azure Bastion using a native Rust WebSocket tunnel.
This replaces the previous `az network bastion tunnel` subprocess approach,
providing faster connections and eliminating the runtime dependency on the Azure CLI bastion extension.

## How It Works

When you run `azlin connect my-vm`, azlin:

1. Resolves the Bastion host for your VM
2. Opens a local TCP listener on `127.0.0.1`
3. For each connection, exchanges tokens with the Bastion API and opens a WebSocket
4. Forwards traffic bidirectionally between the local TCP socket and the WebSocket

This happens transparently — no user action is required.

## One Tunnel Per Target VM

A tunnel is opened against a *single* VM's ARM resource id and forwards to that
VM alone. A regional bastion usually fronts many VMs, but its tunnels are not
interchangeable: sending traffic for VM B down VM A's tunnel reaches VM A.

Azlin's tunnel registry therefore keys tunnels by the target VM's resource id,
and every caller that decides which host a command runs on — `azlin connect`,
and the tmux, health and process columns of `azlin list` — looks up its port by
that resource id. VM names are used for display only. Names are unique within a
resource group but not across one subscription, and a name-keyed port map is
what caused `azlin list` to report every bastion-only VM behind a shared bastion
except one as having no tmux sessions (fixed in `v2.6.126-rust.12ccf60`).

Reusing an existing tunnel is safe and is what the registry is for; reusing
*another VM's* tunnel is not, and the resource-id key is what makes the
difference unspellable.

The loopback listener sets `StrictHostKeyChecking=no` — every tunnel presents as
`127.0.0.1` on a fresh port, so host keys cannot be pinned. SSH consequently
cannot tell you it reached the wrong machine. The resource-id key is the only
control that prevents it.

## Configuration

Add to `~/.azlin/config.toml`:

```toml
# Tunnel establishment timeout (default: 30 seconds)
bastion_tunnel_timeout = 45
```

This controls how long azlin waits for the WebSocket handshake and local port
to become ready. Increase it on slow or high-latency networks.

!!! note
    This is separate from `bastion_detection_timeout` (60s), which controls
    bastion host discovery during VM provisioning.

## Cleaning Up Legacy Processes

If you previously used azlin with the `az` CLI tunnel subprocess, orphaned
processes may remain after upgrading. Clean them up with:

```bash
azlin bastion sweep
```

This finds and terminates any `az network bastion tunnel` processes owned by
your user. It only needs to be run once after upgrading.

## Troubleshooting

### Tunnel timeout errors

If connections fail with timeout errors:

1. Check your network connectivity to Azure
2. Increase the timeout: `bastion_tunnel_timeout = 60` in `~/.azlin/config.toml`
3. Verify your Bastion host is healthy in the Azure portal

### Connection refused on local port

The tunnel listener binds to `127.0.0.1` only. If connecting from a container
or WSL2 guest, ensure you're connecting to `127.0.0.1`, not `localhost`
(which may resolve to `::1`).

### Legacy `az` processes still running

Run `azlin bastion sweep` to clean up. If processes persist, check that they
are owned by your user and match `az network bastion tunnel` in their command line.
