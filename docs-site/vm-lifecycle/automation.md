# VM Lifecycle Automation

Automated health monitoring, self-healing, and lifecycle management for Azure VMs.

## Overview

azlin v0.4.0 introduces comprehensive VM lifecycle automation that monitors VM health, automatically recovers from failures, and provides extensible hooks for custom automation workflows.

**Key Features:**

- **Health Monitoring**: Continuous monitoring of VM status, connectivity, and resource utilization
- **Self-Healing**: Automatic recovery from common failure scenarios
- **Lifecycle Hooks**: Execute custom scripts at key lifecycle events
- **Proactive Maintenance**: Scheduled health checks and preventive actions
- **Integration**: Works seamlessly with batch operations and multi-region deployments

## Quick Start

### Enable Health Monitoring

```bash
# Enable health monitoring for a VM
azlin autopilot enable myvm --health-checks

# Configure check intervals
azlin autopilot config myvm \
  --health-interval 5m \
  --connectivity-check true \
  --resource-check true
```

**Output**:
```
✓ Health monitoring enabled for 'myvm'
  Check Interval: 5 minutes
  Connectivity Check: Enabled
  Resource Check: Enabled
  Self-Healing: Enabled (default)
```

### View Health Status

```bash
# Check current health status
azlin autopilot status myvm
```

**Output**:
```
VM: myvm
Status: Healthy
Last Check: 2025-12-03 10:30:15
Uptime: 5 days, 3 hours

Health Metrics:
  ✓ Connectivity: OK (latency: 12ms)
  ✓ SSH Access: OK
  ✓ Disk Usage: 45% (healthy)
  ✓ Memory Usage: 62% (healthy)
  ⚠ CPU Usage: 85% (warning threshold)

Self-Healing Actions (Last 24h):
  - Network connectivity restored (10:15 AM)
  - SSH service restarted (9:30 AM)
```

## Health Monitoring

### Monitoring Levels

azlin provides three monitoring levels:

| Level | Checks | Interval | Use Case |
|-------|--------|----------|----------|
| **Basic** | VM status, connectivity | 10 minutes | Standard workloads |
| **Standard** | + SSH access, disk usage | 5 minutes | Production VMs |
| **Advanced** | + resource metrics, logs | 2 minutes | Critical services |

### Configure Monitoring

```bash
# Set monitoring level
azlin autopilot config myvm --level standard

# Custom configuration
azlin autopilot config myvm \
  --health-interval 3m \
  --connectivity-check true \
  --ssh-check true \
  --disk-check true \
  --memory-check true \
  --cpu-check true \
  --log-check false
```

### Health Check Types

#### 1. Connectivity Check

Verifies network connectivity to the VM:

```bash
# Enable connectivity monitoring
azlin autopilot config myvm --connectivity-check true

# Set connectivity timeout
azlin autopilot config myvm --connectivity-timeout 30s
```

**What it checks:**
- ICMP ping response
- Network latency
- Public IP accessibility
- VNet connectivity (if applicable)

#### 2. SSH Access Check

Verifies SSH service availability:

```bash
# Enable SSH monitoring
azlin autopilot config myvm --ssh-check true
```

**What it checks:**
- SSH port (22) is listening
- SSH service is running
- Authentication succeeds
- Shell access works

#### 3. Resource Usage Check

Monitors VM resource consumption:

```bash
# Enable resource monitoring
azlin autopilot config myvm \
  --disk-check true \
  --memory-check true \
  --cpu-check true

# Set warning thresholds
azlin autopilot config myvm \
  --disk-warning 80 \
  --memory-warning 85 \
  --cpu-warning 90
```

**What it checks:**
- Disk usage percentage
- Memory usage percentage
- CPU utilization
- I/O wait time

## Self-Healing

### Automatic Recovery

azlin automatically recovers from these failure scenarios:

| Issue | Detection | Recovery Action |
|-------|-----------|-----------------|
| **Network Disconnect** | Ping timeout | Reset network interface |
| **SSH Unavailable** | Connection refused | Restart SSH service |
| **High Disk Usage** | >95% disk usage | Clean temp files, old logs |
| **VM Stopped** | Power state check | Start VM automatically |
| **Unresponsive VM** | Health checks timeout | Force restart (configurable) |

### Configure Self-Healing

```bash
# Enable self-healing (enabled by default)
azlin autopilot enable myvm --self-healing

# Disable for specific scenarios
azlin autopilot config myvm \
  --auto-restart false \
  --auto-cleanup false \
  --max-recovery-attempts 3

# Configure recovery delays
azlin autopilot config myvm \
  --recovery-delay 30s \
  --restart-delay 2m
```

### Recovery Notifications

Get notified when self-healing actions occur:

```bash
# Configure notifications
azlin autopilot config myvm \
  --notify-email user@example.com \
  --notify-slack https://hooks.slack.com/services/...

# Set notification level
azlin autopilot config myvm \
  --notify-level warnings  # Options: all, warnings, errors, critical
```

### View Recovery History

```bash
# Show recent recovery actions
azlin autopilot status myvm --recovery-history

# Show detailed recovery log
azlin autopilot status myvm --recovery-log --last 7d
```

**Output**:
```
Recovery Actions (Last 7 days):

2025-12-03 10:15:00 - Network Connectivity Restored
  Issue: Ping timeout (no response for 5 minutes)
  Action: Reset network interface (eth0)
  Result: Success (connectivity restored in 15 seconds)

2025-12-03 09:30:00 - SSH Service Restarted
  Issue: SSH connection refused (port 22)
  Action: systemctl restart sshd
  Result: Success (SSH accessible in 5 seconds)

2025-12-02 14:20:00 - Disk Cleanup
  Issue: Disk usage 96% (critical threshold)
  Action: Cleaned /tmp, rotated logs, cleared apt cache
  Result: Success (disk usage reduced to 72%)
```

## Lifecycle Hooks

### What are Lifecycle Hooks?

Lifecycle hooks allow you to execute custom scripts at key VM lifecycle events:

- **pre-start**: Before VM starts
- **post-start**: After VM starts successfully
- **pre-stop**: Before VM stops
- **post-stop**: After VM stops
- **on-failure**: When VM or health check fails
- **on-recovery**: After successful self-healing

### Creating Hooks

Create a hook script:

```bash
# Create hooks directory
mkdir -p ~/.azlin/hooks/myvm

# Create pre-start hook
cat > ~/.azlin/hooks/myvm/pre-start.sh << 'EOF'
#!/bin/bash
echo "Starting VM $(date)"
# Custom pre-start logic here
# - Verify dependencies
# - Check quotas
# - Send notification
EOF

chmod +x ~/.azlin/hooks/myvm/pre-start.sh
```

### Register Hooks

```bash
# Register hook for specific VM
azlin autopilot hooks add myvm pre-start ~/.azlin/hooks/myvm/pre-start.sh

# Register hook for all VMs in context
azlin autopilot hooks add-global pre-start ~/.azlin/hooks/global/pre-start.sh

# List registered hooks
azlin autopilot hooks list myvm
```

**Output**:
```
Hooks for 'myvm':

pre-start:
  - ~/.azlin/hooks/myvm/pre-start.sh
  - ~/.azlin/hooks/global/pre-start.sh (global)

post-start:
  - ~/.azlin/hooks/myvm/post-start.sh

on-failure:
  - ~/.azlin/hooks/myvm/alert.sh
```

### Hook Script Examples

#### Example 1: Send Slack Notification on Failure

```bash
cat > ~/.azlin/hooks/myvm/on-failure.sh << 'EOF'
#!/bin/bash
VM_NAME=$1
FAILURE_REASON=$2
TIMESTAMP=$3

curl -X POST \
  -H 'Content-type: application/json' \
  --data "{\"text\":\"⚠️ VM $VM_NAME failed: $FAILURE_REASON (at $TIMESTAMP)\"}" \
  https://hooks.slack.com/services/YOUR/WEBHOOK/URL
EOF
```

#### Example 2: Log All Start/Stop Events

```bash
cat > ~/.azlin/hooks/myvm/post-start.sh << 'EOF'
#!/bin/bash
VM_NAME=$1
echo "$(date): VM $VM_NAME started" >> ~/.azlin/logs/lifecycle.log
# Could also update a database, send metrics, etc.
EOF
```

#### Example 3: Verify Dependencies Before Start

```bash
cat > ~/.azlin/hooks/myvm/pre-start.sh << 'EOF'
#!/bin/bash
# Check if required storage is mounted
if ! mountpoint -q /mnt/shared; then
  echo "ERROR: Shared storage not mounted"
  exit 1
fi

# Check if required VMs are running
if ! azlin status dependency-vm | grep -q "Running"; then
  echo "ERROR: Dependency VM not running"
  exit 1
fi

echo "Pre-start checks passed"
exit 0
EOF
```

### Hook Environment Variables

Hooks receive these environment variables:

```bash
AZLIN_VM_NAME        # VM name
AZLIN_VM_ID          # Azure VM resource ID
AZLIN_EVENT          # Event type (pre-start, post-start, etc.)
AZLIN_TIMESTAMP      # Event timestamp
AZLIN_REGION         # VM region
AZLIN_RESOURCE_GROUP # Resource group name
```

## Proactive Maintenance

### Scheduled Health Checks

Run comprehensive health checks on a schedule:

```bash
# Enable scheduled maintenance
azlin autopilot config myvm \
  --maintenance-schedule "0 2 * * *"  # Daily at 2 AM

# Configure maintenance actions
azlin autopilot config myvm \
  --maintenance-cleanup true \
  --maintenance-updates true \
  --maintenance-restart false
```

### Maintenance Windows

Define maintenance windows to control when actions can occur:

```bash
# Set maintenance window (UTC)
azlin autopilot config myvm \
  --maintenance-window-start "02:00" \
  --maintenance-window-end "04:00"

# Maintenance will only occur during this window
```

### Preventive Actions

Configure preventive maintenance tasks:

```bash
# Enable preventive cleanup
azlin autopilot config myvm \
  --auto-log-rotation true \
  --auto-package-cleanup true \
  --auto-temp-cleanup true

# Set cleanup thresholds
azlin autopilot config myvm \
  --cleanup-threshold 75  # Clean when disk usage > 75%
```

## Integration with Batch Operations

### Monitor Multiple VMs

```bash
# Enable health monitoring for entire fleet
azlin batch start vm* --autopilot enable

# Check health status for all VMs
azlin batch command vm* "azlin autopilot status"

# View fleet health summary
azlin autopilot status --all
```

**Output**:
```
Fleet Health Summary (15 VMs):

✓ Healthy: 12 VMs (80%)
⚠ Warning: 2 VMs (13%)
  - vm-prod-03: High CPU usage (92%)
  - vm-dev-02: High disk usage (88%)
✗ Critical: 1 VM (7%)
  - vm-test-01: SSH unavailable

Recent Recovery Actions: 8 (last 24h)
Success Rate: 100%
```

### Fleet-Wide Configuration

```bash
# Apply configuration to entire fleet
azlin batch start vm* "azlin autopilot config --level standard"

# Enable self-healing for all production VMs
azlin batch start vm-prod* "azlin autopilot enable --self-healing"
```

## Advanced Configuration

### Configuration File

Store complex configurations in a file:

```yaml
# ~/.azlin/autopilot/myvm.yaml
health_monitoring:
  enabled: true
  interval: 5m
  level: advanced
  checks:
    connectivity: true
    ssh: true
    disk: true
    memory: true
    cpu: true

thresholds:
  disk_warning: 80
  disk_critical: 95
  memory_warning: 85
  memory_critical: 95
  cpu_warning: 90
  cpu_critical: 98

self_healing:
  enabled: true
  max_attempts: 3
  recovery_delay: 30s
  restart_delay: 2m
  actions:
    auto_restart: true
    auto_cleanup: true
    network_reset: true

notifications:
  email:
    - admin@example.com
    - ops@example.com
  slack: https://hooks.slack.com/services/...
  level: warnings

hooks:
  pre_start: ~/.azlin/hooks/myvm/pre-start.sh
  post_start: ~/.azlin/hooks/myvm/post-start.sh
  on_failure: ~/.azlin/hooks/myvm/on-failure.sh

maintenance:
  schedule: "0 2 * * *"
  window_start: "02:00"
  window_end: "04:00"
  cleanup: true
  updates: false
  restart: false
```

Load configuration:

```bash
azlin autopilot config myvm --from-file ~/.azlin/autopilot/myvm.yaml
```

### Monitoring Metrics

Export metrics for external monitoring systems:

```bash
# Export metrics in Prometheus format
azlin autopilot metrics myvm --format prometheus

# Export to JSON
azlin autopilot metrics myvm --format json > metrics.json

# Stream metrics to monitoring system
azlin autopilot metrics myvm --stream --endpoint http://monitoring:9090
```

## Troubleshooting

### Health Checks Failing

**Problem**: Health checks consistently fail but VM appears healthy

**Solution**:
```bash
# Check health check configuration
azlin autopilot config myvm --show

# Run manual health check with verbose output
azlin autopilot status myvm --check-now --verbose

# Adjust thresholds if needed
azlin autopilot config myvm --connectivity-timeout 60s
```

### Self-Healing Not Working

**Problem**: VM failures occur but no automatic recovery

**Solution**:
```bash
# Verify self-healing is enabled
azlin autopilot status myvm | grep "Self-Healing"

# Check recovery history for errors
azlin autopilot status myvm --recovery-log

# Enable verbose logging
azlin autopilot config myvm --debug-logging true
```

### Hook Scripts Not Executing

**Problem**: Lifecycle hooks registered but not running

**Solution**:
```bash
# Verify hook registration
azlin autopilot hooks list myvm

# Check hook execution permissions
chmod +x ~/.azlin/hooks/myvm/*.sh

# Test hook manually
~/.azlin/hooks/myvm/pre-start.sh myvm test $(date)

# Check hook logs
azlin autopilot hooks logs myvm
```

## Best Practices

1. **Start with Basic Monitoring**
   - Begin with basic level for non-critical VMs
   - Increase to standard/advanced for production workloads

2. **Configure Appropriate Thresholds**
   - Set warning thresholds based on workload patterns
   - Leave room between warning and critical thresholds

3. **Test Hooks Thoroughly**
   - Test all hooks in development environment first
   - Ensure hooks can handle failures gracefully
   - Keep hooks fast (< 30 seconds execution time)

4. **Monitor Fleet Health**
   - Use batch commands to monitor multiple VMs
   - Set up centralized alerting for critical issues
   - Review recovery logs weekly

5. **Use Maintenance Windows**
   - Schedule maintenance during low-traffic periods
   - Avoid maintenance during business hours
   - Test maintenance actions in staging first

## API Reference

### Python API

```python
from azlin.modules.vm_lifecycle import VMLif
ecycleManager

# Enable health monitoring
lifecycle = VMLifecycleManager(vm_name="myvm")
lifecycle.enable_health_monitoring(
    interval=300,  # 5 minutes
    level="standard",
    checks=["connectivity", "ssh", "disk"]
)

# Get health status
status = lifecycle.get_health_status()
print(f"VM Health: {status.overall}")
print(f"Last Check: {status.last_check}")

# Configure self-healing
lifecycle.configure_self_healing(
    enabled=True,
    max_attempts=3,
    actions=["auto_restart", "auto_cleanup"]
)

# Register hook
lifecycle.register_hook(
    event="pre-start",
    script_path="/path/to/hook.sh"
)
```

## See Also

- [Autopilot Commands](../commands/autopilot/index.md)
- [VM Management](./index.md)
- [Monitoring](../monitoring/index.md)
- [Batch Operations](../batch/index.md)
- [Multi-Region Orchestration](../advanced/multi-region.md)

---

*Documentation last updated: 2025-12-03*
