# azlin top

Run distributed top command on all VMs.

## Synopsis

```bash
azlin top [OPTIONS]
```

## Description

Shows real-time CPU, memory, load, and top processes across all VMs in a unified dashboard that updates every N seconds.

Displays:
- CPU usage per VM
- Memory usage (used/total)
- Load averages (1, 5, 15 min)
- Top processes by CPU usage
- VM status and connectivity

Press **Ctrl+C** to exit the dashboard.

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Resource group |
| `--config PATH` | Config file path |
| `-i, --interval INTEGER` | Refresh interval in seconds (default: 10) |
| `-t, --timeout INTEGER` | SSH timeout per VM in seconds (default: 5) |
| `-h, --help` | Show help message |

## Examples

### Basic Usage

```bash
# Default: 10 second refresh
azlin top
```

**Output:**
```
=== azlin-vm-12345 (20.1.2.3) ===
CPU: 15.2%  Memory: 2.1GB/8GB  Load: 0.45, 0.38, 0.32

TOP PROCESSES:
  PID   CPU%  MEM%  COMMAND
  1234  12.3  5.2   python app.py
  5678   2.1  3.1   node server.js

=== azlin-vm-67890 (20.1.2.4) ===
CPU: 45.8%  Memory: 6.3GB/16GB  Load: 2.1, 1.8, 1.5

TOP PROCESSES:
  PID   CPU%  MEM%  COMMAND
  9012  38.2  12.5  java -jar app.jar
  3456   5.1   4.2  postgres

Updating in 10s... (Ctrl+C to exit)
```

### Fast Refresh

```bash
# 5 second refresh
azlin top -i 5
```

Updates every 5 seconds for near real-time monitoring.

### Slow Refresh

```bash
# 15 second refresh
azlin top -i 15
```

Reduces load on VMs and network.

### Specific Resource Group

```bash
# Monitor specific resource group
azlin top --rg my-resource-group
```

### Custom Timeout

```bash
# 15s refresh, 10s SSH timeout
azlin top -i 15 -t 10
```

Useful for VMs with slow network connections.

## Use Cases

### Monitor Fleet Performance

```bash
# Watch all VMs
azlin top
```

See which VMs are busy, idle, or overloaded.

### Identify Resource Issues

```bash
# Fast refresh to catch spikes
azlin top -i 5
```

Quickly identify CPU or memory problems.

### Long-Term Monitoring

```bash
# Slow refresh for sustained monitoring
azlin top -i 30
```

Monitor over extended periods without excessive SSH connections.

### Production Monitoring

```bash
# Monitor production VMs
azlin top --rg production-rg
```

Keep eye on production fleet.

## Dashboard Information

### Per-VM Metrics

Each VM displays:

1. **Header** - VM name and IP address
2. **CPU** - Current CPU usage percentage
3. **Memory** - Used/Total memory
4. **Load** - Load averages (1, 5, 15 minutes)
5. **Top Processes** - Top 5 processes by CPU

### VM Status Indicators

- ✓ **Running** - VM responsive, showing metrics
- ⚠ **Warning** - High CPU/memory usage
- ✗ **Error** - Cannot connect to VM
- ⏸ **Stopped** - VM is deallocated

## Performance

| Setting | SSH Connections/Min | Best For |
|---------|---------------------|----------|
| `-i 5` | 12 per VM | Active debugging |
| `-i 10` (default) | 6 per VM | General monitoring |
| `-i 30` | 2 per VM | Long-term observation |

## Interpreting Metrics

### CPU Usage

- **0-30%** - Normal, idle or light load
- **30-70%** - Moderate load
- **70-90%** - High load, monitor closely
- **90-100%** - Saturated, investigate

### Memory

- **< 80%** - Healthy
- **80-90%** - High, watch for trends
- **90-95%** - Very high, may need more RAM
- **> 95%** - Critical, system may swap

### Load Average

For a system with N cores:
- **< N** - CPU has capacity
- **= N** - Fully utilized
- **> N** - Overloaded, processes waiting

## Troubleshooting

### VM Not Responding

```bash
# Increase timeout
azlin top -t 15
```

Some VMs may need longer SSH timeout.

### Connection Errors

```bash
# Verify VM is running
azlin list

# Test connectivity
azlin w
```

### High Refresh Load

```bash
# Reduce refresh frequency
azlin top -i 30
```

Too-frequent refreshes can add load to VMs.

### Missing VMs

```bash
# Check resource group
azlin list --rg my-rg

# Use correct resource group
azlin top --rg my-rg
```

## Comparison with Other Commands

| Command | Purpose | Update Frequency |
|---------|---------|------------------|
| `azlin top` | Real-time dashboard | Every N seconds |
| `azlin ps` | Process snapshot | One-time |
| `azlin w` | User activity | One-time |
| `azlin status` | VM status | One-time |

## Related Commands

- [azlin ps](ps.md) - Process listing
- [azlin w](w.md) - User activity
- [azlin status](../vm/status.md) - VM status
- [azlin cost](cost.md) - Cost estimates

## See Also

- [Monitoring](../../monitoring/index.md)
- [Fleet Management](../fleet/index.md)
- [Monitoring](../../monitoring/index.md)
