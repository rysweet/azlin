# SSH Readiness Wait Behavior

Adaptive SSH readiness checks after `azlin new` that scale timeout by VM size,
show progress during the wait, and degrade gracefully on timeout.

## Overview

When `azlin new` creates a VM, it waits for SSH to become available before
running post-create steps (credential forwarding, repo cloning, cloud-init).
Larger VMs with more cloud-init work need more boot time. The SSH readiness
system automatically scales timeouts, reports progress, and treats timeouts as
warnings rather than errors — the VM was created successfully either way.

## Timeout Scaling by VM Size

| Size Tier | SKU Example        | Cores | SSH Timeout |
|-----------|--------------------|-------|-------------|
| `s`       | Standard_D2s_v3    | 2     | 300s (5m)   |
| `m`       | Standard_D16s_v3   | 16    | 300s (5m)   |
| `l`       | Standard_D32s_v3   | 32    | 450s (7.5m) |
| `xl`      | Standard_D64s_v3   | 64    | 600s (10m)  |
| Custom    | (unknown SKU)      | —     | 300s (5m)   |

Timeout is determined by the resolved VM SKU string. Known patterns are matched
case-insensitively:

- SKUs containing `D2s` or `D4s` → **s/m** tier (300s)
- SKUs containing `D16s` → **m** tier (300s)
- SKUs containing `D32s` → **l** tier (450s)
- SKUs containing `D64s` or `D96s` → **xl** tier (600s)
- Unrecognized SKUs default to 300s

## Progress Reporting

During the SSH wait, azlin prints periodic status updates:

```
Waiting for SSH to be ready on 127.0.0.1:2222...
  Still waiting for SSH... 30s/600s
  Still waiting for SSH... 60s/600s (VM provisioning: Updating)
  Still waiting for SSH... 90s/600s (VM provisioning: Updating)
  Still waiting for SSH... 120s/600s (VM power state: running, provisioning: Succeeded)
  Still waiting for SSH... 150s/600s
SSH ready.
```

- **Every 30 seconds**: elapsed time and total timeout are printed.
- **Every 60 seconds**: Azure provisioning state and power state are checked
  and displayed (if a provisioning check function is available).

## Provisioning State Checks

While waiting for SSH, azlin periodically queries the VM's Azure provisioning
state via `az vm get-instance-view`. This provides early feedback:

| Provisioning State | Action |
|-------------------|--------|
| `Creating` / `Updating` | Continue waiting — VM is still being set up |
| `Succeeded` | Continue waiting for SSH — VM is running but sshd may not be up yet |
| `Failed` | **Bail early** with actionable error: provisioning failed, no point waiting |

If the provisioning check is unavailable (e.g., no Azure CLI access), SSH wait
continues without state checks — the feature is best-effort.

## Timeout Behavior (Graceful Degradation)

When the SSH timeout expires, azlin **does not fail**. Instead:

1. **VM details table is printed** — the VM was created successfully.
2. **Warning message** with recovery steps is displayed:

```
⚠ SSH not ready after 600s — VM is still booting.

The VM was created successfully. Post-create setup (credential forwarding,
repo cloning) was skipped because SSH is not yet available.

Next steps:
  • Wait a few minutes, then connect:  azlin ssh my-vm-1
  • Or connect directly:               ssh azureuser@127.0.0.1 -p 2222
  • Check cloud-init progress:         azlin ssh my-vm-1 -- tail -f /var/log/cloud-init-output.log
```

3. **Post-create steps are skipped**: credential forwarding, repo cloning,
   home directory seeding are all bypassed. `wait_for_cloud_init()` is never
   called — it is structurally unreachable when SSH itself is not available.
4. The command **exits successfully** (exit code 0).

### Pool VMs

When creating a pool (`azlin new --pool 4`), each VM's SSH readiness is
checked independently. If one VM times out, it is reported as a warning and
the next VM proceeds normally. The summary table includes all VMs regardless
of SSH readiness.

## Examples

### Standard small VM (default timeout)

```bash
azlin new --size s --name dev
# SSH timeout: 300s
# Waiting for SSH to be ready on 127.0.0.1:2222...
# SSH ready.
# VM 'dev' created successfully!
```

### Large VM with extended timeout

```bash
azlin new --size xl --name bigbox
# SSH timeout: 600s
# Waiting for SSH to be ready on 127.0.0.1:2222...
#   Still waiting for SSH... 30s/600s
#   Still waiting for SSH... 60s/600s (VM provisioning: Updating)
#   ...
# SSH ready.
# VM 'bigbox' created successfully!
```

### Custom SKU with default timeout

```bash
azlin new --vm-size Standard_E96as_v5 --name custom
# SSH timeout: 300s (unrecognized SKU, using default)
```

### Timeout on a large VM

```bash
azlin new --size xl --name bigbox
# SSH timeout: 600s
# Waiting for SSH to be ready on 127.0.0.1:2222...
#   Still waiting for SSH... 30s/600s
#   ...
#   Still waiting for SSH... 600s/600s
# ⚠ SSH not ready after 600s — VM is still booting.
# ...next steps shown...
# VM 'bigbox' created (SSH pending).
```

### Early bail on provisioning failure

Unlike timeout (exit 0), provisioning failure is a real error (non-zero exit):

```bash
azlin new --size l --name broken
# SSH timeout: 450s
# Waiting for SSH to be ready on 127.0.0.1:2222...
#   Still waiting for SSH... 60s/450s (VM provisioning: Failed)
# Error: VM provisioning failed — SSH wait aborted.
# Check Azure portal for VM 'broken' provisioning details.
# (exit code 1)
```

## API Reference

> **Note:** The signatures below describe the planned implementation. The
> current code uses a simpler `wait_for_post_create_readiness()` with a
> hard-coded 300 s timeout and `anyhow::bail!` on failure. The refactor
> introduces `SshReadiness`, size-based timeouts, and provisioning checks.

### `SshReadiness` Enum

Return type for the internal `wait_for_ssh()` function:

```rust
pub(crate) enum SshReadiness {
    /// SSH is available and authenticated.
    Ready,
    /// SSH did not become available within the timeout.
    /// The VM was created but sshd is not yet responding.
    TimedOut {
        elapsed: Duration,
        timeout: Duration,
    },
}
```

### `ssh_timeout_for_vm_size()`

Computes the SSH readiness timeout based on the resolved VM SKU string:

```rust
pub(crate) fn ssh_timeout_for_vm_size(vm_size: &str) -> Duration
```

**Parameters:**
- `vm_size` — The Azure VM SKU string (e.g., `"Standard_D64s_v3"`).

**Returns:** A `Duration` between 300s and 600s based on size tier matching.

### `wait_for_post_create_readiness()`

Updated signature accepting timeout and optional provisioning check:

```rust
pub(crate) fn wait_for_post_create_readiness(
    ip: &str,
    user: &str,
    bastion_port: Option<u16>,
    key_override: Option<&std::path::Path>,
    interactive_ssh: bool,
    ssh_timeout: Duration,
    provisioning_check: Option<Box<dyn Fn() -> Option<String>>>,
) -> Result<SshReadiness>
```

**Parameters:**
- `ssh_timeout` — Timeout for the SSH readiness wait (from `ssh_timeout_for_vm_size`).
- `provisioning_check` — Optional closure that returns the current VM provisioning
  state as a string (e.g., `"Succeeded"`, `"Failed"`). Called every 60s during wait.
  Return `None` if the state cannot be determined.

**Returns:** `Ok(SshReadiness::Ready)` or `Ok(SshReadiness::TimedOut { .. })`.
Returns `Err` only for real failures (provisioning failure, network error).

## Related

- [Troubleshooting Timeout Issues](../troubleshooting/timeout-issues.md)
- [VM Lifecycle Automation](vm-lifecycle-automation.md)
- [Credential Forwarding](credential-forwarding.md)
