# Monitoring Quick Reference

## Commands

```bash
# Dashboard
azlin monitor dashboard                           # Launch dashboard (60s refresh)
azlin monitor dashboard --refresh-interval 30     # Faster refresh
azlin monitor dashboard --resource-group my-rg    # Filter by RG

# Alerts
azlin monitor alert list                          # List all alert rules
azlin monitor alert add NAME --metric M --threshold T --severity S
azlin monitor alert enable NAME                   # Enable alert
azlin monitor alert disable NAME                  # Disable alert
azlin monitor alert delete NAME                   # Delete alert

# History
azlin monitor history VM_NAME                     # Last 7 days
azlin monitor history VM_NAME --days 30           # Last 30 days
azlin monitor history VM_NAME --metric cpu_percent
azlin monitor history VM_NAME --export metrics.csv

# Forecast
azlin monitor forecast                            # All VMs, 30 days ahead
azlin monitor forecast --vm-name VM               # Specific VM
azlin monitor forecast --days 7                   # 7 days ahead
azlin monitor forecast --at-risk-only             # Only VMs at risk

# Configuration
azlin monitor alert config-email                  # Configure email notifications
azlin monitor alert config-slack --webhook-url URL
azlin monitor alert config-webhook --url URL --auth-type bearer
```

## Dashboard Keyboard Shortcuts

- `q` - Quit
- `r` - Refresh now
- `+` - Increase refresh rate
- `-` - Decrease refresh rate

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

# Test email notifications
azlin monitor alert test-email

# Test Slack notifications
azlin monitor alert test-slack

# View alert history
azlin monitor alert history --days 7

# Check database
ls -lh ~/.azlin/metrics.db

# View collection status
azlin monitor status
```

## Common Tasks

### Setup Email Alerts

```bash
1. azlin monitor alert config-email
2. Enter SMTP details when prompted
3. azlin monitor alert test-email
4. azlin monitor alert enable high_cpu
```

### Export Metrics to CSV

```bash
# Single VM
azlin monitor history dev-vm-01 --days 30 --export metrics.csv

# All VMs (bash loop)
for vm in $(az vm list --query "[].name" -o tsv); do
  azlin monitor history $vm --days 30 --export "${vm}_metrics.csv"
done
```

### Find At-Risk VMs

```bash
# Quick check
azlin monitor forecast --at-risk-only

# Detailed forecast for specific VM
azlin monitor forecast --vm-name dev-vm-01 --days 7
```

### Custom Alert Rule

```yaml
# Add to ~/.azlin/alert_rules.yaml
- name: custom_network_alert
  metric: network_out_bytes
  threshold: 10000000  # 10 MB/s
  comparison: ">"
  severity: warning
  enabled: true
  notification_channels: [slack]
```

## Performance Tips

1. **Increase refresh interval** for many VMs: `--refresh-interval 120`
2. **Filter by resource group** to reduce API calls: `--resource-group my-rg`
3. **Use aggregated queries** for historical data: `--days 30` (hourly) vs `--days 7` (raw)
4. **Run in screen/tmux** for long-running dashboards

## Security Best Practices

- Never commit `alert_rules.yaml` with secrets to version control
- Use environment variables for webhook tokens
- Rotate SMTP passwords regularly using `azlin monitor alert config-email`
- Restrict database file permissions: `chmod 600 ~/.azlin/metrics.db`
