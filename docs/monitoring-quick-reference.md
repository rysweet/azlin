# Monitoring Quick Reference

Azlin provides monitoring through dedicated subcommands — there is no `azlin monitor` namespace.

## Commands

```bash
# Health Dashboard (Four Golden Signals)
azlin health                                       # All VMs in default RG
azlin health --vm dev-vm-01                        # Single VM
azlin health --tui                                 # Interactive TUI dashboard
azlin health --tui --interval 5                    # TUI with 5s refresh
azlin health --resource-group my-rg                # Filter by RG

# Distributed Real-Time Monitoring
azlin top                                          # Live monitoring dashboard
azlin top --interval 5                             # 5s refresh
azlin top --vm dev-vm-01                           # Single VM
azlin top --ip 10.0.1.4                            # Direct IP (skip Azure lookup)

# Cost Intelligence
azlin costs dashboard                              # Current spending dashboard
azlin costs history                                # Historical cost trends
azlin costs budget                                 # Budget management
azlin costs recommend                              # Optimization recommendations
azlin costs actions                                # Execute cost-saving actions

# VM Status & Processes
azlin status VM_NAME                               # Detailed VM status
azlin w                                            # Who's logged in (all VMs)
azlin ps                                           # Process list (all VMs)

# Logs
azlin logs VM_NAME                                 # View syslog (default, 100 lines)
azlin logs VM_NAME -t auth                         # Auth logs
azlin logs VM_NAME -t cloud-init                   # Cloud-init logs
azlin logs VM_NAME -t azlin                        # Azlin application logs
azlin logs VM_NAME -t all                          # All log sources
azlin logs VM_NAME -f                              # Follow logs (tail -f)
azlin logs VM_NAME -n 500                          # Last 500 lines
```

## Health Dashboard Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--vm` | Check a single VM by name | all VMs |
| `--tui` | Launch interactive TUI dashboard | off |
| `--interval` | Refresh interval in seconds (TUI only) | 5 |
| `--resource-group` | Filter to resource group | default RG |

## Top Dashboard Flags

| Flag | Description | Default |
|------|-------------|---------|
| `-i, --interval` | Refresh interval in seconds | 10 |
| `-t, --timeout` | SSH timeout per VM | 5 |
| `--vm` | Target a single VM | all VMs |
| `--ip` | Direct IP (skip Azure lookup) | — |

## Color Coding

- 🟢 **Green** (<70%): Normal
- 🟡 **Yellow** (70-85%): Elevated
- 🔴 **Red** (>85%): High

## Default Alert Rules

| Rule | Metric | Threshold | Severity |
|------|--------|-----------|----------|
| high_cpu | cpu_percent | >80% | warning |
| critical_cpu | cpu_percent | >95% | critical |
| high_memory | memory_percent | >85% | warning |
| critical_memory | memory_percent | >95% | critical |
| disk_space | disk_percent | >90% | warning |

## Metrics

| Metric | Description | Unit |
|--------|-------------|------|
| cpu_percent | CPU utilization | 0-100% |
| memory_percent | Memory utilization | 0-100% |
| disk_read_bytes | Disk read throughput | Bytes/sec |
| disk_write_bytes | Disk write throughput | Bytes/sec |
| network_in_bytes | Network ingress | Bytes/sec |
| network_out_bytes | Network egress | Bytes/sec |

## Configuration Files

- `~/.azlin/metrics.db` - Historical metrics database
- `~/.azlin/alert_rules.yaml` - Alert rules configuration

## Troubleshooting

```bash
# Check Azure authentication
az account show

# Verify VM access
az vm list --output table

# View VM status
azlin status VM_NAME

# Check health for a single VM
azlin health --vm VM_NAME --verbose
```

## Common Tasks

### Monitor a Specific VM

```bash
# Quick health check
azlin health --vm dev-vm-01

# Live resource monitoring
azlin top --vm dev-vm-01 --interval 5

# View recent logs
azlin logs dev-vm-01 -n 200
```

### Fleet-Wide Overview

```bash
# Health dashboard for all VMs
azlin health --tui

# Cost overview
azlin costs dashboard

# Who's logged in
azlin w
```

## Performance Tips

1. **Increase refresh interval** for many VMs: `azlin top --interval 30`
2. **Filter by resource group** to reduce API calls: `--resource-group my-rg`
3. **Run in screen/tmux** for long-running dashboards
4. **Use `--vm` flag** to focus on a single VM when debugging

## Security Best Practices

- Never commit `alert_rules.yaml` with secrets to version control
- Use environment variables for webhook tokens
- Rotate SMTP passwords regularly using `azlin monitor alert config-email`
- Restrict database file permissions: `chmod 600 ~/.azlin/metrics.db`
