# Persistent Bastion Tunnel for `azlin code`

**Issue:** #1063
**Status:** Implemented

## Overview

`azlin code <vm>` launches VS Code Remote-SSH against a VM that is reachable
only through Azure Bastion. Because VS Code detaches immediately and then opens
**multiple, long-lived** SSH connections (server install, file sync, terminals,
extension host), the loopback tunnel it connects to must stay alive **after
`azlin code` returns to the shell**.

Azlin guarantees this by owning the bastion tunnel in a **detached, long-lived
helper process** rather than in the short-lived `azlin code` process. The
helper opens the native in-process bastion tunnel (see
[Native Bastion Tunnel](native-bastion-tunnel.md)), records **its own pid** in
the bastion tunnel registry, and keeps the `127.0.0.1:<port>` listener open
until the tunnel is explicitly closed or pruned.

```
azlin code my-vm
        │
        ├─ reuse live tunnel from registry ─────────────┐ (if one exists)
        │                                                │
        └─ else spawn DETACHED `azlin __tunnel-host` ────┤
                                                         ▼
                                    ┌──────────────────────────────────┐
                                    │  azlin __tunnel-host (detached)   │
                                    │  • opens native bastion tunnel     │
                                    │  • binds 127.0.0.1:<port>          │
                                    │  • records OWN pid in registry     │
                                    │  • blocks until SIGTERM / close    │
                                    └──────────────────────────────────┘
        │                                                ▲
        ├─ wait for 127.0.0.1:<port> to LISTEN ──────────┘
        ├─ write VS Code SSH config (Host azlin-my-vm → 127.0.0.1:<port>)
        ├─ launch `code --folder-uri ...`
        └─ EXIT (tunnel stays up in the detached host)
```

### Why this changed

Before this fix, `azlin code` opened the native tunnel **in its own process**
via `ScopedBastionTunnel`. The native tunnel is a `tokio` accept-loop task kept
alive only for the lifetime of the owning process (its handle is
`std::mem::forget`-ed, and the registry records `pid = std::process::id()`).
When `azlin code` printed "VS Code opened" and exited, the process died, the
in-process task died with it, and the loopback listener closed. VS Code
Remote-SSH then connected to a **dead port** and failed with errors like:

```
Connection to 127.0.0.1 closed by remote host.
$PLATFORM is undefined.
Failed to parse remote port from server output.
```

`azlin connect` was unaffected because it stays alive for the whole interactive
SSH session, keeping its in-process tunnel up. The fix makes `azlin code` behave
like a long-lived owner **without** blocking your shell — by delegating tunnel
ownership to the detached `__tunnel-host` process.

This changes **only tunnel lifetime** (and the `azlin tunnel` management surface
described below). Byte forwarding, SSH config generation, and token refresh are
unchanged.

## Scope of Changes

This feature is intentionally small and focused on tunnel lifetime:

| File | Change |
|------|--------|
| `rust/crates/azlin-cli/src/lib.rs` | New hidden CLI variant `__tunnel-host` (`hide = true`; args `--bastion-name`, `--resource-group`, `--vm-resource-id`). |
| `rust/crates/azlin/src/dispatch.rs` | Route `__tunnel-host` to its handler. |
| `rust/crates/azlin/src/cmd_session.rs` | Rewrite the `Code` bastion branch to reuse-or-spawn the detached host and wait for the port to LISTEN. |
| `rust/crates/azlin/src/bastion_tunnel.rs` | Detached-spawn primitive (Unix `setsid()` in a `pre_exec` hook + null stdio; Windows `DETACHED_PROCESS \| CREATE_NEW_PROCESS_GROUP \| CREATE_NO_WINDOW` + null stdio) and the `__tunnel-host` blocking loop (`run_tunnel_host`). |
| `rust/crates/azlin/src/cmd_tunnel.rs` | Extend `list`/`close` to also cover the **native bastion registry** so the detached host is manageable via `azlin tunnel` (see [Managing the tunnel](#managing-the-tunnel)). |

Reverting the native-tunnel migration (commit `e7368cd5`), data-forwarding
logic, SSH config generation, token refresh, and `azlin connect` are all **out
of scope**.

## Usage

No new flags or workflow. `azlin code` works exactly as before — it just leaves
a working tunnel behind:

```bash
# Open VS Code Remote-SSH against a bastion-routed VM
azlin code my-vm

# With options (unchanged)
azlin code my-vm --user ubuntu --workspace /home/azureuser/projects
```

After the command returns, the tunnel is still listening. VS Code can now open
and re-open connections to `127.0.0.1:<port>` for the duration of your editing
session.

## Managing the Tunnel

The detached host is a registry-tracked native bastion tunnel. `azlin tunnel`
manages it directly:

```bash
# List active tunnels, including detached __tunnel-host owners
azlin tunnel list
# VM                     LOCAL PORT   REMOTE PORT       PID
# ----------------------------------------------------------
# my-vm                       35329            22     48210

# Close the tunnel for a VM (terminates the __tunnel-host by its registry pid)
azlin tunnel close my-vm

# Close everything
azlin tunnel close --all
```

To deliver this UX, this feature extends `cmd_tunnel.rs` so that `list` and
`close` read **both** tunnel stores:

- `~/.azlin/tunnels.json` — the existing `ssh -N -L` port-forward registry used
  by `azlin tunnel open` (keyed by friendly `vm_name`).
- `~/.azlin/tunnels/registry.json` — the **native bastion registry** where
  `get_or_create_tunnel` (and therefore the `__tunnel-host`) records itself,
  keyed by `vm_resource_id`.

`azlin tunnel close <vm>` resolves the friendly VM name to its `vm_resource_id`,
matches the bastion-registry entry, sends `SIGTERM` to the recorded host pid
(clean shutdown), and removes the entry.

> **Fallback / debugging.** You can always inspect and terminate the host
> directly:
>
> ```bash
> cat ~/.azlin/tunnels/registry.json | jq '.tunnels'
> # { ".../my-vm": { "local_port": 35329, "pid": 48210, "tunnel_type": "native", ... } }
>
> PID=$(jq -r '.tunnels[] | select(.local_port==35329) | .pid' ~/.azlin/tunnels/registry.json)
> kill "$PID"   # host handles SIGTERM cleanly and removes its registry entry
> ```

Closing VS Code does **not** automatically close the tunnel — this is
intentional so that re-opening a window or reconnecting keeps working. Use
`azlin tunnel close` when you are done, or let the watchdog prune it (see
[Lifecycle](#lifecycle)).

## Lifecycle

Azlin deliberately avoids arbitrary fixed time-to-live caps. A detached tunnel
host lives until one of the following ends it:

| Trigger | Behavior |
|---------|----------|
| **Reuse** | A subsequent `azlin code <same-vm>` (or any bastion command for the same VM) reuses the existing live tunnel instead of spawning a new host. No duplicate hosts accumulate. |
| **Explicit close** | `azlin tunnel close <vm>` / `--all` resolves the VM to its bastion-registry entry and sends the host `SIGTERM` via its recorded pid. The host aborts the tunnel task, removes its registry entry, and exits `0`. |
| **Watchdog prune** | The existing tunnel watchdog prunes registry entries whose owning pid is no longer running (`process_is_running(pid)` is false). It prunes **dead** hosts only — it never kills a live one. |

There is **no idle self-exit and no fixed TTL** in this version. Reliably
counting *established* loopback connections is fragile and platform-specific;
an over-eager idle timeout could kill VS Code mid-session (worse than a
short-lived orphan). Reuse plus explicit close plus watchdog pruning keeps the
number of hosts bounded without risking a live editing session.

### Token refresh for long sessions

The detached host runs current azlin code, so it inherits the adaptive
token-refresh introduced in v2.6.94 (see
[Bastion Tunnel Token Refresh](../BASTION_TUNNEL_TOKEN_REFRESH.md)). Long-lived
VS Code sessions keep working past the original Azure token expiry because the
host refreshes the bearer token before the WebSocket data plane rejects it.

## Reuse Semantics

Before spawning a host, `azlin code` checks the bastion registry for a live
entry for the target VM:

1. **Live tunnel found** (`process_is_running(pid)` is true) → reuse its
   `local_port` directly. No new host is spawned. The SSH config is (re)written
   to point at the existing port.
2. **No live tunnel** → spawn a detached `azlin __tunnel-host`, wait for its
   port to listen, then continue.

This means opening VS Code for the same VM twice does not create two tunnels,
and `azlin connect` / `azlin code` share a tunnel when both are active.

## The `__tunnel-host` Internal Command

`azlin code` spawns a hidden internal subcommand that owns the tunnel. It is
`hide = true` in the CLI (not shown in `--help`) and is not intended for direct
use, but is documented here for operators and debugging.

```
azlin __tunnel-host --bastion-name <NAME> --resource-group <RG> --vm-resource-id <ID>
```

### Arguments

| Flag | Required | Description |
|------|----------|-------------|
| `--bastion-name` | **Yes** | Name of the Azure Bastion host to route through |
| `--resource-group` | **Yes** | Resource group containing the VM |
| `--vm-resource-id` | **Yes** | Full ARM resource ID of the target VM |

### Behavior

1. Calls `get_or_create_tunnel(...)`, which opens (or reuses) the native
   bastion tunnel, binds `127.0.0.1:<port>`, and records the entry in the
   registry with `pid = std::process::id()` — i.e. **the host's own pid**.
2. Installs a `SIGTERM` / Ctrl-C handler for clean shutdown.
3. Blocks awaiting that termination signal (`wait_for_shutdown_signal`), keeping
   the in-process tunnel task alive for the whole session.

On shutdown signal it aborts the tunnel task, best-effort removes its registry
entry, and exits `0`. It is killable at any time via its registry pid, which is
exactly what `azlin tunnel close` does.

### Detached spawn

`azlin code` starts the host fully detached from the parent so that the shell
prompt returns immediately and the child survives parent exit:

| Platform | Detachment | Stdio |
|----------|-----------|-------|
| **Linux / macOS / WSL2** | New session via `setsid()` in a `pre_exec` hook (no controlling terminal, survives parent exit / terminal `SIGHUP`) | `stdin`/`stdout`/`stderr` → `/dev/null` |
| **Windows** | `creation_flags(DETACHED_PROCESS \| CREATE_NEW_PROCESS_GROUP \| CREATE_NO_WINDOW)` — no console window, own process group | `stdin`/`stdout`/`stderr` → null device |

The child never inherits the parent's stdio, so `azlin code` returns cleanly to
the shell and the host produces no terminal output.

## Cross-Platform Support

| Platform | Path | Notes |
|----------|------|-------|
| **Native Windows** | VS Code `ssh.exe` connects to `127.0.0.1:<port>` shared with the detached host on the same machine. | Verified design; requires manual verification (see below). |
| **WSL2** | Windows VS Code reaches the WSL `127.0.0.1:<port>` via WSL localhost forwarding. | Verified working. |
| **Linux** | VS Code and the host share `127.0.0.1`. | Verified working. |
| **macOS** | Same as Linux. | Supported. |

## Configuration

This feature adds **no new configuration keys**. It reuses:

| Key | Role in this feature |
|-----|----------------------|
| `bastion_tunnel_timeout` | Upper bound on how long `azlin code` waits for the detached host's `127.0.0.1:<port>` to become LISTEN-ready before failing (no arbitrary constant). See [Configuration Reference](../reference/configuration-reference.md#bastion_tunnel_timeout). |

The generated VS Code SSH config is **unchanged**:

```ssh-config
Host azlin-my-vm
    HostName 127.0.0.1
    Port 35329
    User azureuser
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null        # NUL on Windows
    ServerAliveInterval 60
```

## Verification

### Linux / WSL2 (automatable)

```bash
# 1. Open VS Code and let azlin exit
azlin code my-vm

# 2. Confirm the tunnel outlived azlin
azlin tunnel list                          # my-vm entry present with a live PID
PORT=$(azlin tunnel list | awk '$1=="my-vm"{print $2}')
ss -ltn | grep ":$PORT"                    # LISTEN present after azlin exited

# 3. Confirm the SSH config port matches the live listener
grep -A5 'Host azlin-my-vm' ~/.ssh/config | grep Port   # == $PORT

# 4. Confirm VS Code's install pattern succeeds through the tunnel
echo 'echo ok' | ssh -T azlin-my-vm sh     # prints: ok

# 5. Close it
azlin tunnel close my-vm                    # listener disappears, host exits
```

Expected: the listener is still present **after** `azlin code` returns, the SSH
config `Port` equals the live listener port, the `ssh -T ... sh` round-trip
succeeds with no truncation, and `azlin tunnel close` removes the listener.

### Windows (manual)

The maintainer cannot directly test native Windows, so verify manually:

1. In PowerShell: `azlin code my-vm`. The prompt returns immediately.
2. `Get-Process azlin` — a background `azlin` (`__tunnel-host`) process is
   present; the foreground `azlin code` process has exited.
3. `azlin tunnel list` shows the `my-vm` entry, and
   `Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1` shows its port
   listening.
4. VS Code opens the Remote-SSH window and finishes installing the server
   without "Connection closed by remote host" errors.
5. `azlin tunnel close my-vm` — the listener disappears and the background
   process exits.

## Testing

Automated tests assert the tunnel **owner outlives the spawning command** and
that config and listener agree:

| Test | Asserts |
|------|---------|
| Owner-outlives-parent | After spawning the detached-host path and dropping/exiting the parent handle, `127.0.0.1:<port>` is still LISTENING. |
| Config-matches-listener | The port written to the VS Code SSH config equals the port of the live listener. |
| Reuse-skips-spawn | With a live registry entry present, the Code branch reuses the port and does **not** spawn a second host. |
| Clean-SIGTERM-exit | The host removes its registry entry and exits `0` on `SIGTERM`. |
| Tunnel-close-kills-host | `azlin tunnel close <vm>` resolves the VM to its bastion-registry entry and terminates the recorded host pid. |
| Loopback-only bind | The host binds `127.0.0.1`, never `0.0.0.0`. |

Tests that require real Azure behavior are gated behind the existing live-test
conventions (see [Real Azure Testing](../REAL_AZURE_TESTING.md)).

## Security

| Control | Description |
|---------|-------------|
| **Loopback-only** | The host binds `127.0.0.1` only — never `0.0.0.0`. Enforced and tested. |
| **Argv-only spawn** | The detached host is started with an argument vector, never a shell string — no command injection. |
| **No secrets on argv** | Only bastion name, resource group, and VM resource ID are passed on the command line. Azure credentials are resolved in the host from the inherited environment/credential chain, never placed in argv. |
| **Null stdio** | The detached host redirects stdio to the null device, preventing diagnostic or auth leakage to the terminal. |
| **File permissions** | The tunnel registry and generated SSH config retain `0600` permissions. |
| **Validated before use** | The port range and pid-owns-listener relationship are verified (via `wait_for_process_tree_listener`) before the SSH config is written or `code` is launched. |
| **Clean shutdown** | `SIGTERM`/Ctrl-C handling keeps the registry consistent (no stale entries). |

## What Didn't Change

- **`azlin code` flags and workflow** — identical CLI surface (see
  [CLI Reference](../reference/cli-python-parity.md#code)).
- **SSH config generation** — same `StrictHostKeyChecking no`,
  `UserKnownHostsFile /dev/null` (`NUL` on Windows), `ServerAliveInterval 60`.
- **Native tunnel byte forwarding** — unchanged; the bug was lifetime, not data.
- **`azlin connect`** — unaffected; it already owns its tunnel for the session.
- **Token refresh** — the same adaptive `TokenCache` refresh applies.

## See Also

- [Native Bastion Tunnel](native-bastion-tunnel.md)
- [Bastion Tunnel Token Refresh](../BASTION_TUNNEL_TOKEN_REFRESH.md)
- [How to Use Tunnels](../how-to/use-tunnels.md)
- [Troubleshoot Tunnel Issues](../troubleshooting/tunnel-issues.md)
- [CLI Reference — `code`](../reference/cli-python-parity.md#code)
