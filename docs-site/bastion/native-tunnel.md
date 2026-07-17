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
