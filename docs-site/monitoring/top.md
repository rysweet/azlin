# Distributed Top

Real-time resource monitoring across all VMs in your fleet with a unified dashboard.

## Overview

The `azlin top` command runs a distributed `top` command across all VMs in your resource group, showing real-time CPU, memory, load averages, and top processes in a unified dashboard that updates every N seconds. This is invaluable for monitoring fleet-wide resource utilization and identifying performance bottlenecks.

Unlike SSH-ing into each VM individually, `azlin top` provides a centralized view that aggregates metrics from all VMs simultaneously.

## Basic Usage

```bash
# Start distributed top with default settings (10s refresh)
azlin top

# Use 5 second refresh interval
azlin top -i 5

# Monitor specific resource group
azlin top --rg production-vms

# Custom refresh and timeout
azlin top -i 15 -t 10
```

Press `Ctrl+C` to exit the dashboard.

## Command Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--resource-group` | `--rg` | Resource group to monitor | Current context RG |
| `--interval` | `-i` | Refresh interval in seconds | 10 |
| `--timeout` | `-t` | SSH timeout per VM in seconds | 5 |
| `--config` | | Config file path | `~/.azlin/config.toml` |
| `--help` | `-h` | Show help message | |

## Examples

### Monitor Default Resource Group

Monitor all VMs in your default resource group with 10-second updates:

```bash
azlin top
```

**Output:**
```
=== VM: azlin-dev-1 (10.0.1.4) ===
top - 14:23:45 up 2 days, 3:15, 1 user, load average: 0.52, 0.45, 0.38
Tasks: 142 total, 1 running, 141 sleeping
%Cpu(s): 12.3 us, 4.2 sy, 0.0 ni, 83.1 id
MiB Mem: 16384 total, 8192 free, 4096 used, 4096 buff/cache

PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM
1234 azureuser 20   0  4.2g   1.1g   128m S  45.0   7.1  node
5678 azureuser 20   0  2.8g   512m    64m S  12.3   3.2  python3

=== VM: azlin-dev-2 (10.0.1.5) ===
top - 14:23:46 up 5 days, 12:42, 2 users, load average: 0.15, 0.20, 0.18
...

[Updating every 10s. Press Ctrl+C to exit]
```

### Fast Refresh for Active Debugging

Use a 5-second refresh when actively debugging performance issues:

```bash
azlin top -i 5
```

This provides near-real-time updates ideal for watching the immediate impact of changes.

### Monitor Production Fleet

Monitor your production VMs with a longer timeout for slower networks:

```bash
azlin top --rg production-fleet -i 15 -t 10
```

**Use Case:** Production VMs behind Azure Bastion or with higher latency may need longer timeouts.

### Development Environment Monitoring

Quick check of development VMs with fast refresh:

```bash
azlin top --rg dev-team -i 3
```

**Use Case:** During active development, see immediate resource usage from build processes, tests, or local servers.

## Understanding the Output

The dashboard shows for each VM:

### Header Line
```
=== VM: azlin-dev-1 (10.0.1.4) ===
```
- VM name
- Private IP address

### System Summary
```
top - 14:23:45 up 2 days, 3:15, 1 user, load average: 0.52, 0.45, 0.38
```
- Current time
- Uptime
- Number of logged-in users
- Load averages (1, 5, 15 minutes)

### Task Statistics
```
Tasks: 142 total, 1 running, 141 sleeping
```
- Total processes
- Running vs sleeping states

### CPU Usage
```
%Cpu(s): 12.3 us, 4.2 sy, 0.0 ni, 83.1 id
```
- `us`: User space CPU %
- `sy`: System/kernel CPU %
- `ni`: Nice (low priority) CPU %
- `id`: Idle CPU %

### Memory Usage
```
MiB Mem: 16384 total, 8192 free, 4096 used, 4096 buff/cache
```
- Total memory available
- Free memory
- Used memory
- Buffer/cache memory

### Top Processes
Shows the most resource-intensive processes with:
- PID, user, priority, virtual/resident memory
- CPU and memory percentage
- Command name

## Common Use Cases

### 1. Fleet-Wide Performance Monitoring

Monitor all VMs to ensure balanced workload distribution:

```bash
azlin top --rg compute-cluster -i 10
```

**What to Look For:**
- Load averages > number of CPUs (overloaded)
- Memory usage > 90% (need more RAM)
- One VM with high load while others idle (poor distribution)

### 2. Build Process Monitoring

Watch resource usage during parallel builds across your build farm:

```bash
azlin top --rg build-farm -i 5
```

**What to Look For:**
- CPU spikes during compilation
- Memory leaks in build processes
- I/O bottlenecks

### 3. Application Performance Tuning

Monitor resource usage while load testing your application:

```bash
azlin top --rg app-servers -i 3
```

**What to Look For:**
- CPU saturation under load
- Memory growth patterns
- Process count explosions

### 4. Cost Optimization Discovery

Identify underutilized VMs that could be downsized:

```bash
azlin top --rg all-vms -i 30
```

**What to Look For:**
- Consistently low CPU usage (< 10%)
- Large amounts of free memory
- VMs that could be combined or reduced

## Performance Considerations

### Refresh Interval

- **Fast (3-5s)**: Real-time debugging, high network load
- **Medium (10s)**: Default, balanced monitoring
- **Slow (15-30s)**: Low-impact monitoring, trend watching

### SSH Timeout

- **Short (5s)**: Local network, Azure VMs in same region
- **Medium (10s)**: Cross-region, Bastion connections
- **Long (15-30s)**: High latency networks, VPN connections

### Network Impact

Each refresh makes SSH connections to all VMs. For large fleets (20+ VMs):
- Use longer refresh intervals (15-30s)
- Increase timeout to prevent false failures
- Consider splitting into multiple resource groups

## Troubleshooting

### Some VMs Not Appearing

**Symptom:** Not all VMs show up in the dashboard.

**Causes:**
1. VMs are stopped or deallocated
2. SSH timeout too short for Bastion connections
3. Network connectivity issues

**Solution:**
```bash
# Check VM status first
azlin list --rg my-rg

# Increase timeout for Bastion VMs
azlin top --rg my-rg -t 15

# Check specific VM connectivity
azlin connect my-vm
```

### "Connection Timeout" Errors

**Symptom:** `SSH connection timeout` messages for VMs.

**Causes:**
1. VM is starting up
2. SSH service not responding
3. Network latency too high for timeout

**Solution:**
```bash
# Increase SSH timeout
azlin top -t 20

# Check VM status
azlin status

# Test direct connection
azlin connect problem-vm
```

### Dashboard Updates Slowly

**Symptom:** Long pauses between updates with many VMs.

**Cause:** Sequential SSH connections to many VMs take time.

**Solution:**
```bash
# Use longer refresh interval
azlin top -i 30

# Split into smaller resource groups
azlin top --rg team-a -i 10
# In another terminal:
azlin top --rg team-b -i 10
```

### High Load But Low CPU

**Symptom:** Load average high but CPU idle percentage is also high.

**Cause:** Processes waiting for I/O (disk, network).

**Action:**
- Check disk I/O with `azlin ps | grep D` (uninterruptible sleep)
- Review storage performance
- Consider faster disk tiers

## Tips and Best Practices

### 1. Use Appropriate Refresh Intervals

Don't use very fast refresh (< 5s) unless actively debugging. It creates unnecessary SSH connections and network traffic.

```bash
# Good for monitoring
azlin top -i 10

# Only when debugging
azlin top -i 3
```

### 2. Monitor During Key Operations

Run `azlin top` during deployments, migrations, or load tests to see real-time impact:

```bash
# Terminal 1: Run deployment
./deploy.sh

# Terminal 2: Watch resources
azlin top -i 5
```

### 3. Combine with Other Monitoring

Use `azlin top` alongside other monitoring commands:

```bash
# Check who's logged in
azlin w

# See all processes
azlin ps

# View distributed top
azlin top
```

### 4. Create Resource Group Aliases

For frequently monitored groups, set up shell aliases:

```bash
alias top-prod='azlin top --rg production-fleet -i 15'
alias top-dev='azlin top --rg dev-team -i 5'
```

### 5. Watch for Patterns Over Time

Run `azlin top` at different times to understand usage patterns:
- Morning: User activity peaks
- Midday: Background jobs
- Night: Scheduled tasks, backups

## Integration with Other Tools

### With Cost Tracking

Identify expensive, underutilized resources:

```bash
# Find idle VMs
azlin top -i 60  # Watch for consistent low usage

# Check their costs
azlin cost --by-vm
```

### With Batch Operations

Stop idle VMs discovered through monitoring:

```bash
# Identify idle VMs via top
azlin top --rg all-vms

# Stop the idle ones
azlin batch stop --tag env=dev
```

### With Fleet Management

Monitor fleet-wide command execution:

```bash
# Terminal 1: Execute fleet command
azlin fleet run update-packages

# Terminal 2: Watch resource impact
azlin top -i 5
```

## See Also

- [W Command](w.md) - See who is logged in
- [PS Command](ps.md) - View all processes
- [Status Command](status.md) - VM status overview
- [Cost Tracking](cost.md) - Cost analysis and optimization
- [Fleet Management](../batch/fleet.md) - Distributed command execution
- [Troubleshooting Connection Issues](../troubleshooting/connection.md)

---

*Documentation last updated: 2025-11-24*
