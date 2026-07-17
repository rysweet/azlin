# Native Bastion Tunnel

**Issue:** #998
**Status:** Planned

## Overview

Azlin uses a native Rust WebSocket tunnel to connect through Azure Bastion,
replacing the previous `az network bastion tunnel` subprocess. The native
implementation provides faster connection setup, lower resource usage, and
eliminates the dependency on the Azure CLI `bastion` extension at runtime.

The tunnel works by:

1. Binding a local TCP listener on `127.0.0.1`
2. For each inbound TCP connection, exchanging a token with the Bastion API
3. Opening a WSS connection to the Bastion data plane
4. Forwarding bytes bidirectionally between the TCP client and WebSocket

All existing commands (`azlin connect`, `azlin ssh`, `azlin gui`, `azlin sync`)
use the native tunnel transparently — no user-facing changes are required.

## Configuration

### `bastion_tunnel_timeout`

Controls the timeout for tunnel establishment, including the WebSocket
handshake and local port readiness.

| Key                      | Type    | Default | Unit    |
|--------------------------|---------|---------|---------|
| `bastion_tunnel_timeout` | integer | `30`    | seconds |

Set in `~/.azlin/config.toml`:

```toml
bastion_tunnel_timeout = 45
```

This timeout applies to:

- TCP connect timeout when establishing the WSS connection to Bastion
- `wait_for_local_port_listener` timeout after tunnel creation

It does **not** affect `bastion_detection_timeout` (60s), which controls
how long azlin waits to discover the bastion host during VM provisioning.

## Commands

### `azlin bastion sweep`

Cleans up orphaned `az network bastion tunnel` processes left over from
before the native tunnel migration (or from manual CLI usage).

```bash
# List and kill orphaned az bastion tunnel processes
azlin bastion sweep
```

The command:

- Searches for processes owned by the current user matching
  `az network bastion tunnel` in their command line
- Displays each found process (PID and command line) before terminating it
- Only targets `az` subprocesses — never touches native in-process tunnels

This is a one-time cleanup command. After migration to native tunnels, no
new `az` tunnel subprocesses are created by azlin.

## Architecture

### Module: `azlin_azure::native_tunnel`

The core tunnel logic lives in the `azlin-azure` crate:

```
rust/crates/azlin-azure/src/native_tunnel.rs
```

#### Public API

```rust
use azlin_azure::native_tunnel::open_tunnel;
use std::time::Duration;
use tokio::task::JoinHandle;

/// Opens a native bastion tunnel.
///
/// Binds a local TCP listener on 127.0.0.1 with an OS-assigned port.
/// For each accepted TCP connection, performs a Bastion token exchange
/// and opens a WSS connection, then forwards bytes bidirectionally.
///
/// Returns the local port number and a handle to the background task.
/// Dropping or aborting the handle shuts down the tunnel.
pub async fn open_tunnel(
    bastion_endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
    timeout: Duration,
) -> Result<(u16, JoinHandle<()>)>
```

**Parameters:**

| Parameter              | Description                                                    |
|------------------------|----------------------------------------------------------------|
| `bastion_endpoint`     | Resolved Bastion endpoint URL (Standard: `bastion.dnsName`; Developer: data pod URL from `/api/connection`) |
| `target_resource_id`   | Azure resource ID of the target VM                             |
| `resource_port`        | Port on the target VM to tunnel to (typically `22` for SSH)    |
| `token`                | Azure AD bearer token with scope for the Bastion resource      |
| `timeout`              | Maximum time for tunnel establishment (from config `bastion_tunnel_timeout`) |

**Returns:** `Result<(u16, JoinHandle<()>)>` — the local port and a task handle.

**Errors:**

| Error                    | Cause                                                |
|--------------------------|------------------------------------------------------|
| `TokenExchangeFailed`    | Bastion `/api/tokens` POST returned non-200 or invalid JSON |
| `WebSocketConnectFailed` | WSS handshake to Bastion data plane failed           |
| `LocalBindFailed`        | Could not bind TCP listener on 127.0.0.1             |
| `Timeout`                | Tunnel establishment exceeded the configured timeout |
| `InvalidEndpoint`        | Endpoint URL is not `https://` or `wss://`           |

### Protocol Details

The native tunnel implements the same protocol as the Azure CLI `azext_bastion`
extension (MIT licensed):

#### Step 1 — Token Exchange (per TCP connection)

```
POST https://{bastion_endpoint}/api/tokens
Content-Type: application/json

{
  "resourceId": "<target_resource_id>",
  "protocol": "tcptunnel",
  "workloadHostPort": <resource_port>,
  "aztoken": "Bearer <token>"
}
```

Response:

```json
{
  "authToken": "...",
  "nodeId": "...",
  "websocketToken": "..."
}
```

#### Step 2 — WebSocket Connection

For **Standard/Premium** SKU bastions:

```
wss://{bastion_endpoint}/webtunnelv2/{websocketToken}?X-Node-Id={nodeId}
```

For **Developer/QuickConnect** SKU bastions:

```
wss://{bastion_endpoint}/omni/webtunnel/{websocketToken}
```

The SKU path is determined by the shape of the `bastion_endpoint` URL
(data pod URLs from `/api/connection` use the Developer path).

#### Step 3 — Bidirectional Forwarding

Once the WSS connection is established, bytes flow as binary WebSocket frames:

- **TCP → WSS**: Bytes read from the local TCP client are sent as binary frames
- **WSS → TCP**: Binary frames received from the WebSocket are written to the TCP client

No additional framing or length-prefixing is applied.

#### Cleanup

On connection close (either side), azlin sends a best-effort cleanup request:

```
DELETE https://{bastion_endpoint}/api/tokens/{authToken}
X-Node-Id: {nodeId}
```

Failure to clean up is not an error — the Bastion server has its own idle timeout.

### Tunnel Registry

The tunnel registry (`~/.azlin/tunnels/`) tracks active tunnels for reuse and
watchdog pruning. Each entry now includes a `tunnel_type` field:

```json
{
  "bastion_name": "my-bastion",
  "target_resource_id": "/subscriptions/.../vms/my-vm",
  "local_port": 52341,
  "pid": 12345,
  "tunnel_type": "native",
  "created_at": "2026-04-21T19:00:00Z"
}
```

| `tunnel_type` | Meaning                                              |
|---------------|------------------------------------------------------|
| `"native"`    | In-process tokio task; `pid` is the azlin process ID |
| `"legacy"`    | External `az` subprocess; `pid` is the child PID     |

Registry files from before the migration (missing `tunnel_type`) default to
`"legacy"` for backward compatibility.

**Watchdog pruning** behavior per type:

- **legacy**: Checks if `pid` is still running (existing behavior)
- **native**: Checks if the local port is still accepting TCP connections

### BastionTunnel Struct

The in-memory tunnel handle changed from a child process to a tokio task:

```rust
// Before (legacy)
pub struct BastionTunnel {
    pub local_port: u16,
    child: std::process::Child,
}

// After (native)
pub struct BastionTunnel {
    pub local_port: u16,
    task: tokio::task::JoinHandle<()>,
}
```

Dropping a `BastionTunnel` aborts the background task, closing the listener
and all active WebSocket connections.

## Security

| Control | Description |
|---------|-------------|
| **TLS only** | All Bastion API calls use `https://`; all WebSocket connections use `wss://`. Non-TLS endpoints are rejected. |
| **Localhost binding** | The TCP listener binds to `127.0.0.1` only — never `0.0.0.0`. |
| **No token logging** | Azure AD tokens, `websocketToken`, and `authToken` are never logged. Error messages use static context strings. |
| **URL encoding** | All Bastion API response values are URL-encoded before embedding in WSS URLs to prevent path injection. |
| **System CA store** | Uses `rustls-tls-native-roots` for TLS — no custom CA bundles or certificate bypass. |
| **Sweep safety** | `bastion sweep` only targets processes owned by the current user with exact command-line matching. |
| **Registry permissions** | Tunnel registry files retain `0600` permissions. The new `tunnel_type` field contains no sensitive data. |
| **No unsafe code** | The `native_tunnel` module contains zero `unsafe` blocks. |

## Examples

### Basic SSH Connection (unchanged user experience)

```bash
# Connect to a VM — uses native tunnel automatically
azlin connect my-vm

# SSH with X11 forwarding
azlin connect my-vm --gui
```

### Custom Tunnel Timeout

```bash
# For slow networks, increase the tunnel timeout
echo 'bastion_tunnel_timeout = 60' >> ~/.azlin/config.toml

# Now connections have 60s to establish the tunnel
azlin connect my-vm
```

### Cleaning Up Legacy Processes

After upgrading to native tunnels, clean up any orphaned `az` processes:

```bash
azlin bastion sweep
# Output:
# Found 2 orphaned bastion tunnel processes:
#   PID 34521: az network bastion tunnel --name my-bastion ...
#   PID 34588: az network bastion tunnel --name other-bastion ...
# Terminated 2 processes.
```

### Programmatic Tunnel Usage (Rust)

```rust
use azlin_azure::native_tunnel::open_tunnel;
use std::time::Duration;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let (local_port, handle) = open_tunnel(
        "my-bastion.bastion.azure.com",
        "/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        &azure_ad_token,
        Duration::from_secs(30),
    ).await?;

    println!("Tunnel open on 127.0.0.1:{}", local_port);

    // Use the tunnel (e.g., SSH to 127.0.0.1:local_port)
    // ...

    // Shut down
    handle.abort();
    Ok(())
}
```

## Migration Notes

### What Changed

| Before (legacy)                    | After (native)                         |
|------------------------------------|----------------------------------------|
| Spawns `az network bastion tunnel` | In-process tokio WebSocket tunnel      |
| Requires `az` CLI + bastion ext    | No external CLI dependency at runtime  |
| `Child` process handle             | `JoinHandle<()>` task handle           |
| Hardcoded 10s port wait            | Configurable `bastion_tunnel_timeout`  |
| No cleanup for orphaned processes  | `azlin bastion sweep` command          |

### What Didn't Change

- **User-facing commands**: `azlin connect`, `azlin ssh`, `azlin gui`,
  `azlin sync` all work identically
- **`ScopedBastionTunnel` API**: Same `new(bastion_name, resource_group,
  vm_resource_id)` signature; `new()` is now async internally (wraps
  `get_or_create_tunnel`) but callers already use `.await`, so no changes required
- **Registry file location**: Still `~/.azlin/tunnels/`
- **Bastion detection**: The 60s `bastion_detection_timeout` is unchanged

### Backward Compatibility

- Registry entries without `tunnel_type` are treated as `"legacy"`
- The `bastion sweep` command can clean up old `az` processes from any version
- Config files without `bastion_tunnel_timeout` use the 30s default

## Dependencies

Added to `azlin-azure`:

| Crate                | Feature                  | Purpose                    |
|----------------------|--------------------------|----------------------------|
| `tokio-tungstenite`  | `rustls-tls-native-roots`| WebSocket client           |
| `futures-util`       | —                        | `StreamExt` / `SinkExt`    |
| `urlencoding`        | —                        | URL-encode token values    |
| `tokio`              | `rt`, `net`, `macros`    | Async runtime, TCP listener|
| `reqwest`            | (workspace)              | HTTP token exchange        |
