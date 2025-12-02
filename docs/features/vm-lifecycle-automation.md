# VM Lifecycle Automation

Automated health monitoring, self-healing, and lifecycle event hooks for Azure VMs.

## Overview

azlin's VM lifecycle automation provides:
- **Continuous health monitoring** of VMs with customizable check intervals
- **Self-healing** with automatic VM restart on failures
- **Lifecycle event hooks** for custom automation workflows
- **Real-time health status** integrated into azlin commands

## Quick Start

```bash
# Enable monitoring for a VM
azlin lifecycle enable my-vm

# Start the monitoring daemon
azlin lifecycle daemon start

# View health status
azlin lifecycle status

# List VMs with health indicators
azlin list
```

## Commands

### Enable Monitoring

Enable automated health monitoring for a VM:

```bash
azlin lifecycle enable my-vm

# Options:
  --interval SECONDS        Check interval (default: 60)
  --restart-policy POLICY   Restart policy: never|on-failure|always (default: never)
  --ssh-threshold COUNT     SSH failures before restart (default: 3)
  --timeout SECONDS         Health check timeout (default: 30)
```

**Examples:**

```bash
# Enable with default settings (no auto-restart)
azlin lifecycle enable my-vm

# Enable with automatic restart on SSH failures
azlin lifecycle enable my-vm --restart-policy on-failure --ssh-threshold 3

# Custom check interval and restart policy
azlin lifecycle enable production-vm \
  --interval 30 \
  --restart-policy on-failure \
  --ssh-threshold 5 \
  --timeout 60
```

### Disable Monitoring

Disable monitoring for a VM:

```bash
azlin lifecycle disable my-vm
```

This removes the VM from monitoring but doesn't stop the daemon.

### View Status

Check monitoring status for one or all VMs:

```bash
# All monitored VMs
azlin lifecycle status

# Specific VM
azlin lifecycle status my-vm
```

**Output:**
```
VM: my-vm
  Monitoring: Enabled
  Policy: on-failure
  Check Interval: 60s
  SSH Failures: 0/3
  Last Check: 2 minutes ago
  Status: Healthy ✓

  Hooks:
    on_failure: /home/user/scripts/alert.sh
    on_restart: /home/user/scripts/notify.sh
```

### Configure Hooks

Set lifecycle event hooks:

```bash
azlin lifecycle hook my-vm on_failure /path/to/alert.sh
azlin lifecycle hook my-vm on_restart /path/to/notify.sh
azlin lifecycle hook my-vm on_start /path/to/startup.sh
```

**Available Hooks:**
- `on_start`: VM started
- `on_stop`: VM stopped
- `on_failure`: Health check failed
- `on_restart`: VM automatically restarted
- `on_destroy`: VM deleted
- `on_healthy`: VM passed health check

**Remove a hook:**
```bash
azlin lifecycle hook my-vm on_failure --clear
```

### Daemon Management

Control the lifecycle monitoring daemon:

```bash
# Start daemon
azlin lifecycle daemon start

# Stop daemon
azlin lifecycle daemon stop

# Restart daemon (reload config)
azlin lifecycle daemon restart

# Check daemon status
azlin lifecycle daemon status

# View daemon logs
azlin lifecycle daemon logs
azlin lifecycle daemon logs --tail 50   # Last 50 lines
azlin lifecycle daemon logs --follow    # Live tail
```

**Daemon Status Output:**
```
Lifecycle Daemon Status:
  Running: Yes
  PID: 12345
  Uptime: 2 hours, 15 minutes
  Monitored VMs: 3
    - my-vm (Healthy ✓)
    - prod-vm (Unhealthy - SSH down ✗)
    - dev-vm (Healthy ✓)
```

## Integration with Existing Commands

### azlin list

Health status appears in the `azlin list` output:

```bash
azlin list
```

**Output:**
```
SESSION  VM NAME     STATUS    IP          REGION   SIZE       HEALTH
proj1    vm-001      Running   1.2.3.4     eastus   D2s_v3     Healthy ✓
proj2    vm-002      Running   1.2.3.5     westus   D2s_v3     Unhealthy (SSH down) ✗
-        vm-003      Stopped   N/A         eastus   B2s        N/A
```

### azlin status

Detailed health information in `azlin status`:

```bash
azlin status my-vm
```

**Output includes:**
```
VM Status:
  Name: my-vm
  State: Running
  IP: 1.2.3.4
  Region: eastus
  Size: Standard_D2s_v3

Lifecycle Monitoring:
  Enabled: Yes
  Policy: on-failure
  Check Interval: 60s
  SSH Failures: 0/3
  Last Check: 30 seconds ago
  Last Status: Healthy ✓

  Hooks:
    on_failure: /home/user/scripts/alert.sh
    on_restart: /home/user/scripts/notify.sh
```

## Configuration

Configuration is stored in `~/.azlin/lifecycle-config.toml`:

```toml
[vms.my-vm]
enabled = true
check_interval_seconds = 60
restart_policy = "never"
ssh_failure_threshold = 3
health_check_timeout = 30

[vms.my-vm.hooks]
on_start = ""
on_stop = ""
on_failure = "/home/user/scripts/alert.sh"
on_restart = "/home/user/scripts/notify.sh"
on_destroy = ""
on_healthy = ""

[daemon]
pid_file = "~/.azlin/lifecycle-daemon.pid"
log_file = "~/.azlin/lifecycle-daemon.log"
log_level = "INFO"
```

### Manual Configuration

You can edit the config file directly:

```bash
# Open config in editor
$EDITOR ~/.azlin/lifecycle-config.toml

# Restart daemon to reload
azlin lifecycle daemon restart
```

## Restart Policies

Three restart policies control self-healing behavior:

### never (Default)

No automatic restart. Safest option - you maintain full control.

```bash
azlin lifecycle enable my-vm --restart-policy never
```

**When to use:**
- Production VMs where manual intervention is required
- Cost-sensitive environments
- When you want monitoring alerts only

### on-failure

Restart only when SSH connectivity fails after reaching the threshold.

```bash
azlin lifecycle enable my-vm --restart-policy on-failure --ssh-threshold 3
```

**When to use:**
- Development VMs that should stay running
- VMs hosting services that can safely restart
- When you want automatic recovery from connectivity issues

**Behavior:**
- Tracks consecutive SSH failures
- Restarts after threshold reached (default: 3)
- Resets counter on successful check

### always

Restart on any health check failure (most aggressive).

```bash
azlin lifecycle enable my-vm --restart-policy always
```

**When to use:**
- Test environments
- Stateless services
- When maximum uptime is critical

**Warning:** May cause restart loops if issues persist. Use with caution.

## Lifecycle Hooks

Hooks are shell scripts executed on your local machine when lifecycle events occur.

### Hook Environment Variables

All hooks receive these environment variables:

- `AZLIN_VM_NAME`: VM name
- `AZLIN_EVENT_TYPE`: Event type (on_start, on_failure, etc.)
- `AZLIN_TIMESTAMP`: ISO 8601 timestamp
- `AZLIN_FAILURE_COUNT`: Number of failures (on_failure only)

### Example Hook Scripts

**Alert on Failure:**
```bash
#!/bin/bash
# alert.sh - Send notification on VM failure

TITLE="azlin Alert: VM Failure"
MESSAGE="VM ${AZLIN_VM_NAME} failed health check (failure #${AZLIN_FAILURE_COUNT})"

# macOS notification
osascript -e "display notification \"${MESSAGE}\" with title \"${TITLE}\""

# Or Slack webhook
curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
  -H 'Content-Type: application/json' \
  -d "{\"text\": \"${MESSAGE}\"}"
```

**Log Restart:**
```bash
#!/bin/bash
# notify.sh - Log VM restarts

LOG_FILE="$HOME/.azlin/restart-log.txt"
echo "[${AZLIN_TIMESTAMP}] VM ${AZLIN_VM_NAME} restarted" >> "${LOG_FILE}"
```

**Pre-Start Setup:**
```bash
#!/bin/bash
# startup.sh - Run commands after VM starts

# Wait for VM to be fully ready
sleep 30

# Deploy latest code
azlin connect ${AZLIN_VM_NAME} -- "cd ~/app && git pull && systemctl restart myservice"
```

### Hook Execution

- Hooks run **asynchronously** (daemon doesn't wait)
- Timeout: 60 seconds (configurable in future)
- Logs: `~/.azlin/lifecycle-daemon.log`
- Errors: Logged but don't stop monitoring

### Hook Security

- Scripts must be executable (`chmod +x script.sh`)
- Run with your user permissions (not elevated)
- No environment variable injection risks
- All executions logged

## Health Checks

The daemon performs three types of health checks:

### 1. VM State (Azure API)

Checks VM power state via Azure API:
- Running
- Stopped
- Deallocated

### 2. SSH Connectivity

Tests SSH connection to VM:
- TCP connection on port 22
- Timeout: configurable (default 30s)
- Failures tracked for self-healing

### 3. System Metrics (Optional)

If SSH is reachable, collects:
- CPU usage (%)
- Memory usage (%)
- Disk usage (%)

**Note:** Metrics are informational only. They don't trigger failures or restarts.

## Use Cases

### 1. Development VM Auto-Recovery

Keep your dev VM running even if network hiccups occur:

```bash
azlin lifecycle enable dev-vm --restart-policy on-failure --ssh-threshold 2
azlin lifecycle daemon start
```

### 2. Cost-Aware Monitoring

Monitor production VMs without automatic restart:

```bash
azlin lifecycle enable prod-vm --restart-policy never
azlin lifecycle hook prod-vm on_failure /path/to/alert.sh
azlin lifecycle daemon start
```

Receive alerts but maintain manual control over restarts.

### 3. Automated Testing Environments

Keep test VMs always available:

```bash
for vm in test-1 test-2 test-3; do
  azlin lifecycle enable $vm --restart-policy always --interval 30
done
azlin lifecycle daemon start
```

### 4. Scheduled Maintenance

Use hooks for automated maintenance:

```bash
# on_healthy hook runs system updates when VM is healthy
azlin lifecycle hook prod-vm on_healthy /path/to/update-check.sh
```

## Troubleshooting

### Daemon Won't Start

Check daemon status and logs:

```bash
azlin lifecycle daemon status
azlin lifecycle daemon logs --tail 50
```

Common issues:
- PID file exists but process is dead: Remove `~/.azlin/lifecycle-daemon.pid`
- Permission errors: Check log file permissions
- Config errors: Validate `~/.azlin/lifecycle-config.toml` syntax

### Health Checks Failing

Check SSH connectivity manually:

```bash
azlin connect my-vm

# If connection fails:
azlin status my-vm  # Check VM is running
```

Verify SSH key in Azure Key Vault:
```bash
azlin keys list
```

### Hooks Not Executing

1. Check script permissions:
   ```bash
   ls -l /path/to/script.sh
   chmod +x /path/to/script.sh  # If needed
   ```

2. Check daemon logs:
   ```bash
   azlin lifecycle daemon logs --follow
   ```

3. Test hook manually:
   ```bash
   AZLIN_VM_NAME=my-vm AZLIN_EVENT_TYPE=on_failure /path/to/script.sh
   ```

### Restart Loops

If a VM keeps restarting:

1. Disable monitoring temporarily:
   ```bash
   azlin lifecycle disable my-vm
   ```

2. Check VM health manually:
   ```bash
   azlin connect my-vm
   ```

3. Fix underlying issue

4. Re-enable with adjusted thresholds:
   ```bash
   azlin lifecycle enable my-vm --restart-policy on-failure --ssh-threshold 5
   ```

## FAQ

**Q: Does the daemon need to run continuously?**

Yes. The daemon process runs in the background to perform periodic health checks. Stop it with `azlin lifecycle daemon stop` when not needed.

**Q: What happens if my machine reboots?**

The daemon stops. You'll need to restart it manually:
```bash
azlin lifecycle daemon start
```

Future versions may support systemd/launchd integration for auto-start.

**Q: Can I monitor VMs across multiple resource groups?**

Yes. The daemon monitors all VMs with monitoring enabled, regardless of resource group.

**Q: Do hooks run on the VM or my local machine?**

Hooks run on your **local machine**. This allows you to control the VM from outside (e.g., restart via Azure API, send notifications).

**Q: How much does this cost?**

The daemon makes periodic Azure API calls (state checks) and SSH connections. Costs are negligible:
- Azure API calls: Free (within quotas)
- Network: Minimal (SSH is lightweight)
- Compute: Only if auto-restart is enabled

**Q: Can I use this in CI/CD?**

Yes. Enable monitoring for ephemeral VMs in test pipelines:
```bash
azlin new --name ci-test
azlin lifecycle enable ci-test --restart-policy on-failure
# Run tests...
azlin destroy ci-test
```

**Q: What's the minimum check interval?**

1 second, but recommended minimum is 30 seconds to avoid API rate limits and unnecessary SSH connections.

## Best Practices

1. **Start with `never` policy** - Monitor first, enable auto-restart after confidence
2. **Test hooks thoroughly** - Run hooks manually before deploying
3. **Use appropriate thresholds** - Higher thresholds (5+) for flaky networks
4. **Monitor daemon logs** - Check logs periodically for issues
5. **Keep it simple** - Start with basic health checks, add complexity only when needed

## See Also

- [Architecture Documentation](../vm-lifecycle-architecture.md)
- [Configuration Reference](../reference/lifecycle-config.md)
- [Hook Examples](../examples/lifecycle-hooks/)
- [azlin status command](../commands/status.md)
- [azlin list command](../commands/list.md)
