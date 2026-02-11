# VM Monitoring & Alerting

Comprehensive monitoring dashboard with real-time metrics, proactive alerting, historical trend analysis, and resource utilization forecasting for Azure VMs.

## VM Discovery for Monitoring Commands

**All monitoring commands use tag-based VM discovery**, ensuring consistent behavior across `azlin w`, `azlin ps`, `azlin top`, and the monitoring dashboard.

**Key Features:**
- **Tag-based discovery** (primary): Discovers VMs with `azlin-managed=true` tag
- **Name-prefix fallback** (backward compatibility): Falls back to VMs with "azlin-" prefix
- **Custom name support**: Works with any VM name format, including compound names like "hostname:session"
- **Consistent behavior**: Same discovery logic as `azlin list`

**Supported VM Name Formats:**
- Standard: `azlin-vm-1234567890`
- Custom: `myproject`
- Compound: `myhost:dev`, `api-server:prod`

For complete VM discovery documentation, troubleshooting, and migration guide, see [VM Discovery for Monitoring Commands](monitoring-commands-vm-discovery.md).

## Quick Start

```bash
# Launch real-time monitoring dashboard
azlin monitor dashboard

# View configured alerts
azlin monitor alert list

# Check resource forecast
azlin monitor forecast --at-risk-only
```

## Features

### Real-Time Dashboard

Live monitoring dashboard showing CPU, memory, disk, and network metrics for all VMs:

```bash
# Launch with default 60-second refresh
azlin monitor dashboard

# Faster refresh (30 seconds)
azlin monitor dashboard --refresh-interval 30

# Filter by resource group
azlin monitor dashboard --resource-group my-dev-vms
```

**Dashboard Display**:
```
╭─ VM Monitoring Dashboard ─ Updated: 2025-12-01 20:30:15 ─────────────╮
│ VM Name       CPU%   Memory%   Disk R/W (MB/s)   Network I/O (MB/s)   │
├────────────────────────────────────────────────────────────────────────┤
│ dev-vm-01     45.2   62.1      12.3 / 8.5        1.2 / 0.8           │
│ dev-vm-02     78.9   89.2      45.1 / 23.4       5.3 / 3.2           │
│ dev-vm-03     12.4   34.5      3.2 / 1.8         0.4 / 0.2           │
╰────────────────────────────────────────────────────────────────────────╯

Press 'q' to quit | 'r' to refresh | '+' faster | '-' slower
```

**Color Coding**:
- 🟢 Green (<70%): Normal
- 🟡 Yellow (70-85%): Elevated
- 🔴 Red (>85%): High

**Keyboard Shortcuts**:
- `q`: Quit dashboard
- `r`: Refresh immediately
- `+`: Increase refresh rate
- `-`: Decrease refresh rate

### Proactive Alerts

Configure alert rules that trigger notifications when thresholds are breached:

```bash
# List all alert rules
azlin monitor alert list

# Add new alert
azlin monitor alert add high_cpu \
  --metric cpu_percent \
  --threshold 80 \
  --severity warning

# Enable/disable alerts
azlin monitor alert enable high_cpu
azlin monitor alert disable high_cpu

# Delete alert
azlin monitor alert delete high_cpu
```

**Default Alert Rules**:
- `high_cpu`: CPU >80% (warning)
- `critical_cpu`: CPU >95% (critical)
- `high_memory`: Memory >85% (warning)
- `critical_memory`: Memory >95% (critical)
- `disk_space`: Disk >90% (warning)

**Notification Channels**:
- Email (SMTP)
- Slack (webhook)
- Generic webhook (custom integrations)

### Historical Metrics

Query and export historical metrics:

```bash
# View last 7 days for a VM
azlin monitor history dev-vm-01

# View last 30 days
azlin monitor history dev-vm-01 --days 30

# Query specific metric
azlin monitor history dev-vm-01 --metric cpu_percent --days 14

# Export to CSV
azlin monitor history dev-vm-01 --days 30 --export metrics.csv
```

**Historical Data Retention**:
- 7 days: Raw metrics (1-minute intervals)
- 30 days: Hourly aggregated
- 90 days: Daily aggregated

### Resource Forecasting

Predict future resource utilization using trend analysis:

```bash
# Forecast all VMs (30 days ahead)
azlin monitor forecast

# Forecast specific VM (7 days ahead)
azlin monitor forecast --vm-name dev-vm-01 --days 7

# Show only at-risk VMs
azlin monitor forecast --at-risk-only
```

**Forecast Output**:
```
Resource Utilization Forecast (30 days)

VM: dev-vm-01
├─ CPU:     Current: 45%  →  7d: 52%  →  30d: 68%  (📈 Increasing)
├─ Memory:  Current: 62%  →  7d: 64%  →  30d: 70%  (📈 Stable)
└─ Disk:    Current: 35%  →  7d: 38%  →  30d: 48%  (📈 Increasing)

VM: dev-vm-02  ⚠️  AT RISK
├─ CPU:     Current: 78%  →  7d: 85%  →  30d: 95%  (🔴 Critical)
├─ Memory:  Current: 89%  →  7d: 92%  →  30d: 98%  (🔴 Critical)
└─ Disk:    Current: 72%  →  7d: 78%  →  30d: 91%  (🔴 Warning)
   └─ Days until disk limit: 23 days
```

**Trend Classifications**:
- 📈 Increasing: >0.5% per day growth
- 📉 Decreasing: >0.5% per day decline
- ➡️ Stable: -0.5% to +0.5% per day

## Configuration

### Alert Rules Configuration

Alert rules are stored in `~/.azlin/alert_rules.yaml`:

```yaml
rules:
  - name: high_cpu
    metric: cpu_percent
    threshold: 80.0
    comparison: ">"
    severity: warning
    enabled: true
    notification_channels: [email]

  - name: critical_memory
    metric: memory_percent
    threshold: 95.0
    comparison: ">"
    severity: critical
    enabled: true
    notification_channels: [email, slack]

notification_config:
  email:
    enabled: true
    smtp_host: smtp.gmail.com
    smtp_port: 587
    from_address: alerts@example.com
    to_addresses:
      - admin@example.com
    # Password stored securely in system keyring
    # Set with: azlin monitor alert config-email

  slack:
    enabled: false
    webhook_url: https://hooks.slack.com/services/YOUR/WEBHOOK/URL

  webhook:
    enabled: false
    url: https://example.com/alerts
    auth_type: bearer  # none, bearer, basic
    auth_token: ${WEBHOOK_TOKEN}  # From environment variable
```

### Email Notifications Setup

```bash
# Configure email notifications
azlin monitor alert config-email

# You'll be prompted for:
# - SMTP host (e.g., smtp.gmail.com)
# - SMTP port (e.g., 587)
# - From address
# - Password (stored securely in system keyring)
# - Recipient addresses
```

**Gmail Setup**:
1. Enable 2-factor authentication on your Google account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the app password when configuring email

### Slack Notifications Setup

```bash
# 1. Create Slack webhook:
#    https://api.slack.com/messaging/webhooks

# 2. Add webhook to config
azlin monitor alert config-slack --webhook-url https://hooks.slack.com/services/XXX

# 3. Test notification
azlin monitor alert test-slack
```

### Custom Webhook Setup

```bash
# Configure generic webhook
azlin monitor alert config-webhook \
  --url https://example.com/alerts \
  --auth-type bearer \
  --auth-token $WEBHOOK_TOKEN

# Webhook payload format (JSON):
{
  "alert": "high_cpu",
  "vm_name": "dev-vm-01",
  "metric": "cpu_percent",
  "actual_value": 85.2,
  "threshold": 80.0,
  "severity": "warning",
  "timestamp": "2025-12-01T20:30:15Z",
  "message": "CPU usage on dev-vm-01 is 85.2% (threshold: 80%)"
}
```

## Architecture

### Data Collection

- **Source**: Azure Monitor REST API
- **Frequency**: 1-5 minutes (configurable)
- **Method**: Parallel collection using ThreadPoolExecutor
- **Timeout**: 30 seconds per VM
- **Graceful Degradation**: Continues if individual VMs fail

### Data Storage

- **Database**: SQLite at `~/.azlin/metrics.db`
- **Retention**:
  - Raw metrics: 7 days
  - Hourly aggregated: 30 days
  - Daily aggregated: 90 days
- **Automatic Cleanup**: Runs on each collection cycle

### Alert Evaluation

- **Frequency**: Every collection cycle (1-5 minutes)
- **Suppression**: No re-alerts for same VM+rule within 15 minutes
- **Retry**: 3 attempts with exponential backoff for failed notifications

### Forecasting Algorithm

- **Method**: Simple linear regression
- **Data**: Hourly aggregated metrics (minimum 7 days)
- **Accuracy**: Typically within 15% for 7-day predictions
- **Limitations**: Works best for linear trends, not sudden changes

## Metrics Reference

### Collected Metrics

| Metric | Description | Unit | Source |
|--------|-------------|------|--------|
| `cpu_percent` | Average CPU utilization | Percentage (0-100) | Azure Monitor |
| `memory_percent` | Memory utilization | Percentage (0-100) | Azure Monitor |
| `disk_read_bytes` | Disk read throughput | Bytes/second | Azure Monitor |
| `disk_write_bytes` | Disk write throughput | Bytes/second | Azure Monitor |
| `network_in_bytes` | Network ingress | Bytes/second | Azure Monitor |
| `network_out_bytes` | Network egress | Bytes/second | Azure Monitor |

### Alert Severity Levels

| Severity | Description | Use Case |
|----------|-------------|----------|
| `info` | Informational | Non-critical notifications |
| `warning` | Warning | Resource usage elevated, may need attention |
| `critical` | Critical | Immediate attention required |

## Troubleshooting

### Dashboard Not Updating

**Symptoms**: Dashboard shows stale data or no data

**Solutions**:
```bash
# 1. Check Azure CLI authentication
az account show

# 2. Verify VM access
az vm list --output table

# 3. Check metrics database
ls -lh ~/.azlin/metrics.db

# 4. View collection logs
azlin monitor debug --last-collection
```

### Alerts Not Firing

**Symptoms**: No alert notifications despite high resource usage

**Solutions**:
```bash
# 1. Verify alert rules are enabled
azlin monitor alert list

# 2. Check notification config
azlin monitor alert test-email
azlin monitor alert test-slack

# 3. View alert history
azlin monitor alert history --days 7

# 4. Check suppression status
azlin monitor alert suppression-status
```

### Historical Data Missing

**Symptoms**: Query returns no data or gaps in data

**Solutions**:
```bash
# 1. Check database size and location
ls -lh ~/.azlin/metrics.db

# 2. Verify collection is running
azlin monitor status

# 3. Check retention settings
azlin monitor config show

# 4. Manual data integrity check
azlin monitor verify-database
```

### Forecast Inaccurate

**Symptoms**: Predictions don't match actual usage

**Common Causes**:
- Insufficient historical data (need minimum 7 days)
- Recent usage pattern changes
- Non-linear growth (forecast assumes linear trends)
- Seasonal variations not accounted for

**Solutions**:
- Wait for more data (7-14 days minimum)
- Use shorter forecast periods (7 days instead of 30)
- Combine with manual review of trends

## Performance

### Dashboard Performance

- **Launch Time**: <5 seconds (typical)
- **Memory Usage**: ~50 MB (10 VMs)
- **CPU Usage**: <5% during refresh
- **Network**: ~100 KB per refresh cycle

### Collection Performance

- **Throughput**: 10-50 VMs/second (parallel)
- **API Calls**: 6 calls per VM per collection
- **Rate Limits**: Azure Monitor: 12,000 requests/hour

### Storage Performance

- **Database Size**: ~1 MB per VM per month (raw metrics)
- **Query Time**: <100ms for 30-day range
- **Aggregation Time**: ~5 seconds for 90 days of data

## Security

### Authentication

- Uses Azure CLI authentication (`az login`)
- No custom credentials stored
- Leverages Azure RBAC for VM access

### Secrets Management

- SMTP passwords stored in system keyring (not config files)
- Webhook tokens via environment variables
- No plain-text credentials in config

### Data Protection

- Metrics database has restricted permissions (0600)
- Error messages sanitized to prevent information disclosure
- No PII or sensitive data collected

### Required Permissions

```bash
# Azure RBAC role required
az role assignment create \
  --assignee user@example.com \
  --role "Monitoring Reader" \
  --scope /subscriptions/{subscription-id}
```

## Integration Examples

### Integrate with CI/CD

Monitor VMs during deployment and alert on issues:

```yaml
# GitHub Actions example
- name: Monitor deployment VMs
  run: |
    # Start monitoring
    azlin monitor dashboard --refresh-interval 30 &
    MONITOR_PID=$!

    # Deploy application
    ./deploy.sh

    # Check for alerts during deployment
    azlin monitor alert history --last 30min

    # Stop monitoring
    kill $MONITOR_PID
```

### Integrate with Grafana

Export metrics to Grafana for advanced visualization:

```bash
# Export last 30 days to CSV
for vm in $(az vm list --query "[].name" -o tsv); do
  azlin monitor history $vm --days 30 --export "${vm}_metrics.csv"
done

# Import to Grafana using CSV datasource
```

### Integrate with PagerDuty

Forward critical alerts to PagerDuty:

```yaml
# In alert_rules.yaml
notification_config:
  webhook:
    enabled: true
    url: https://events.pagerduty.com/v2/enqueue
    auth_type: bearer
    auth_token: ${PAGERDUTY_TOKEN}

# Webhook payload automatically formatted for PagerDuty Events API
```

## FAQ

### How often are metrics collected?

By default, every 60 seconds. Configurable from 1-5 minutes via `--refresh-interval`.

### Can I monitor VMs in multiple subscriptions?

Yes, but you need to switch subscriptions using `az account set` before launching the dashboard.

### What happens if a VM is unreachable?

The collector gracefully skips unreachable VMs and displays an error in the dashboard. Other VMs continue to be monitored.

### How accurate are the forecasts?

Typically within 15% for 7-day predictions. Accuracy improves with more historical data (14-30 days).

### Can I customize alert thresholds?

Yes, edit `~/.azlin/alert_rules.yaml` or use `azlin monitor alert add` to create custom rules.

### What's the impact on Azure costs?

Minimal. Azure Monitor API calls are free for basic metrics. Storage is negligible (<10 MB/VM/year).

### Can I run the dashboard in the background?

Yes, use `screen` or `tmux` to keep it running:

```bash
screen -S azlin-monitor
azlin monitor dashboard
# Press Ctrl+A, D to detach
# screen -r azlin-monitor to reattach
```

## See Also

- [Azure Monitor Metrics](https://docs.microsoft.com/azure/azure-monitor/platform/data-platform-metrics)
- [azlin distributed top](./distributed_top.md) - Live process monitoring
- [azlin cost tracking](./cost_tracking.md) - Cost estimation and tracking
