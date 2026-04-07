# Credential Forwarding Reference

Technical reference for azlin's credential forwarding system (`auth_forward` module).

## CLI Flags

| Flag | Effect on Credential Forwarding |
|------|-------------------------------|
| `--yes` | Forwards all detected credentials without prompting |
| `--private` | Routes SCP through bastion tunnel automatically |
| `--no-bastion` | Forces direct SCP even when bastion is available |

Credential forwarding is triggered by `azlin new`. There is no standalone forwarding command.

## SSH Readiness Check

Before forwarding, azlin waits for the VM's SSH service to become reachable:

| Parameter | Value |
|-----------|-------|
| Timeout | 300 seconds |
| Poll interval | 5 seconds |
| TCP connect timeout | 3 seconds per attempt |
| Verification | TCP connect + SSH auth handshake |

The check performs two steps per attempt:

1. **TCP connect** — `TcpStream::connect_timeout` to port 22
2. **SSH auth test** — runs `ssh -o BatchMode=yes <host> true` to verify authentication works

Both must succeed before forwarding begins. If the timeout elapses, forwarding is skipped with a warning.

## Cloud-Init Completion Check

After SSH is reachable, azlin waits for cloud-init provisioning to complete before forwarding credentials or connecting the user. This ensures all tools (gh, az, node, rustc, go, dotnet, claude, chromium wrappers) are installed.

| Parameter | Value |
|-----------|-------|
| Timeout | 900 seconds |
| Poll interval | 10 seconds |
| Remote command | `status: azlin-ready` sentinel, otherwise `cloud-init status --long` (or `status: not-installed`) |
| Clean success | `/var/lib/azlin/provisioning-complete` exists and emits `status: azlin-ready` |

Behavior by cloud-init state:

| State | Action |
|-------|--------|
| `status: azlin-ready` | Print success message, proceed |
| `status: done` without sentinel | Keep polling |
| `status: disabled` | Print info message, proceed (cloud-init not active) |
| `status: done` + degraded/error `extended_status` | Treat as provisioning failure |
| `status: error` | Treat as provisioning failure |
| `status: running` | Continue polling |
| Command not found | Print info message, proceed (non-cloud-init VM) |
| Timeout (900s) | Fail readiness check |

Cloud-init readiness now blocks post-create credential forwarding and auto-connect. If provisioning ends in `error`, `degraded done`, or timeout, `azlin new` surfaces that failure instead of silently continuing.

## Credential Detection

Each credential source is detected independently. Only sources that exist locally are offered for forwarding.

### GitHub CLI

| Property | Value |
|----------|-------|
| Detection | `~/.config/gh/hosts.yml` exists |
| Method | Recursive SCP of `~/.config/gh/` |
| Remote path | `~/.config/gh/` |

### GitHub Copilot

| Property | Value |
|----------|-------|
| Detection | `~/.config/github-copilot/` directory exists |
| Method | Recursive SCP of `~/.config/github-copilot/` |
| Remote path | `~/.config/github-copilot/` |

### Claude Code

| Property | Value |
|----------|-------|
| Detection | `~/.claude.json` exists |
| Method | Single-file SCP |
| Remote path | `~/.claude.json` |

### Azure CLI

| Property | Value |
|----------|-------|
| Detection | Any allow-listed file exists in `~/.azure/` |
| Method | Individual SCP per file (not recursive) |
| Remote path | `~/.azure/<filename>` |

**Allow-listed files** (only these are copied):

- `azureProfile.json`
- `config`
- `msal_token_cache.json`
- `msal_token_cache.bin`
- `clouds.config`

Files **excluded** from forwarding:

- `accessTokens.json` — legacy token store
- `servicePrincipalProfile/` — service principal credentials
- Any other file not on the allow-list

## SSH/SCP Configuration

All SSH and SCP commands use these options:

| Option | Value | Purpose |
|--------|-------|---------|
| `StrictHostKeyChecking` | `accept-new` | TOFU — accept on first connect, reject if key changes |
| `BatchMode` | `yes` | Fail cleanly instead of prompting for password |
| `ConnectTimeout` | `10` | Seconds before connection attempt times out |
| `UserKnownHostsFile` | default | Standard known_hosts management |

## Bastion Routing

When a bastion tunnel is active (indicated by a non-`None` `bastion_port`):

| Property | Direct Connection | Bastion Tunnel |
|----------|-------------------|----------------|
| SSH/SCP host | `<vm-ip>` | `127.0.0.1` |
| SSH/SCP port | `22` | `<bastion_port>` |

Bastion detection is automatic. The forwarding code receives the tunnel port from the VM creation flow.

## VM Session Tagging

For a named single-VM create (`azlin new --name <name>` without `--pool`),
the resolved VM name is stored as an Azure tag:

| Tag Key | Tag Value | Purpose |
|---------|-----------|---------|
| `azlin-session` | VM name | Shown in `azlin list` Session column |

This tag is set during VM creation (not during forwarding) and follows Azure
tag requirements (max 256 chars for key, 256 for value).

Named single-VM creates also perform a one-time seed from local
`~/.azlin/home/` after SSH is ready. If that directory is missing or empty,
azlin skips the seed step.

## Error Handling

Credential forwarding is **best-effort**. The error handling model:

| Scenario | Behavior |
|----------|----------|
| SSH never becomes ready during guest-readiness wait | `azlin new` returns an error after resource creation |
| SCP fails for one credential | Warning printed, remaining credentials still attempted |
| All SCP operations fail | Warning printed, VM creation succeeds |
| User declines all prompts | No forwarding, VM creation succeeds |
| Non-TTY environment | All confirmations default to "no" (use `--yes` to override) |
| Bastion tunnel not ready during guest-readiness wait | `azlin new` returns an error if readiness cannot be established |

Forwarding itself remains best-effort. `azlin new` only returns non-zero here when the pre-forwarding guest-readiness gate fails.

## IPv6 Handling

`TcpStream::connect_timeout` requires a `SocketAddr`. IP parsing:

1. If the host contains `:` (IPv6 heuristic), bracket it: `[host]:port`
2. Otherwise parse as `host:port`
3. If parsing fails, fall back to `127.0.0.1:<port>` (preserves the actual port)

In practice, Azure VMs use IPv4 addresses. The fallback exists as a safety net for unexpected address formats.

## Module API

The public credential-forwarding entry point is:

```
forward_auth_credentials(ip, user, force, bastion_port, key_override, interactive_ssh)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `ip` | `&str` | VM IP address |
| `user` | `&str` | SSH username (typically `azureuser`) |
| `force` | `bool` | Skip confirmation prompts (`--yes`) |
| `bastion_port` | `Option<u16>` | Bastion tunnel port, or `None` for direct |
| `key_override` | `Option<&Path>` | Explicit SSH private key for the VM |
| `interactive_ssh` | `bool` | Whether SSH should inherit the caller's TTY behavior |

Internal helpers (not public API):

| Function | Purpose |
|----------|---------|
| `wait_for_ssh()` | Polls TCP + SSH auth until ready |
| `ssh_run()` | Runs a hardcoded command on the VM via SSH. **Security invariant: the command parameter must be a string literal, never user input.** |
| `scp_file()` | Copies a single file via SCP |
| `scp_recursive()` | Copies a directory recursively via SCP |
| `ssh_target()` | Returns `user@host` with bastion routing |
| `scp_target()` | Returns `user@host:path` with bastion routing |
| `confirm()` | Interactive y/N prompt (defaults no, respects `--force`) |

Azure CLI allow-list note: `clouds.config` is forwarded. It is **not** excluded.
