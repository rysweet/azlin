# azlin autopilot run

Manually run autopilot to check and execute optimization actions.

## Synopsis

```bash
azlin autopilot run [OPTIONS]
```

## Description

Manually triggers autopilot to:
1. Scan all VMs for optimization opportunities
2. Analyze usage patterns and costs
3. Recommend or execute actions based on strategy
4. Update budget tracking

By default, shows recommendations without executing. Use without `--dry-run` to execute actions.

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--dry-run` | Show what would be done without executing | `false` |
| `-h, --help` | Show help message | - |

## Examples

### Preview actions (dry-run)

```bash
azlin autopilot run --dry-run
```

Output:
```
Autopilot Run (Dry-Run Mode)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scanning VMs...
Found 8 VMs (5 running, 3 stopped)

Analysis
--------
Current Spend:     $245/month (projected)
Budget:            $500/month
Budget Usage:      49%

Recommendations
---------------
→ Stop vm-test-123 (idle 150 min)
  Savings: $8/month

→ Stop vm-dev-456 (idle 180 min)
  Savings: $12/month

→ Downsize vm-staging-789 (CPU <10%)
  From: Standard_D4s_v3 ($140/month)
  To:   Standard_D2s_v3 ($70/month)
  Savings: $70/month

→ Keep vm-prod-1 (protected tag: production)
→ Keep vm-dev-main (active, CPU 45%)
→ Keep vm-api-server (active sessions)

Total Potential Savings: $90/month
New Projected Cost:      $155/month

Run without --dry-run to execute these actions.
```

### Execute actions

```bash
azlin autopilot run
```

Output:
```
Autopilot Run (Execute Mode)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scanning VMs...
Found 8 VMs (5 running, 3 stopped)

Executing Actions
-----------------
✓ Stopped vm-test-123 (idle 150 min)
✓ Stopped vm-dev-456 (idle 180 min)
✓ Downsized vm-staging-789
  Standard_D4s_v3 → Standard_D2s_v3

Skipped Actions
---------------
→ vm-prod-1: Protected (tag: production)
→ vm-dev-main: Active (CPU 45%)
→ vm-api-server: Active sessions detected

Summary
-------
Actions Executed:  3
Estimated Savings: $90/month
New Projected Cost: $155/month
Budget Remaining:  $345/month (69%)

Run 'azlin autopilot status' to view updated status.
```

## When to Use

### Manual run scenarios:

1. **Testing configuration**: After changing autopilot settings
2. **Immediate cleanup**: Before end of billing period
3. **Budget emergency**: When approaching budget limit
4. **Scheduled tasks**: In cron jobs or automation
5. **Verification**: Check what autopilot would do

## Output Sections

### Scanning

```
Scanning VMs...
Found 8 VMs (5 running, 3 stopped)
```

Lists discovered VMs and their states.

### Analysis

```
Current Spend:     $245/month (projected)
Budget:            $500/month
Budget Usage:      49%
```

Shows current budget situation.

### Recommendations

```
→ Stop vm-test-123 (idle 150 min)
  Savings: $8/month
```

Lists each action with:
- Action type (stop, downsize, keep)
- Reason for action
- Expected savings

### Execution Results (without --dry-run)

```
✓ Stopped vm-test-123 (idle 150 min)
✗ Failed to stop vm-error-1 (Azure API error)
```

Shows success/failure for each action.

### Summary

```
Actions Executed:  3
Estimated Savings: $90/month
New Projected Cost: $155/month
Budget Remaining:  $345/month (69%)
```

Provides overall impact summary.

## Common Workflows

### Test before enabling

```bash
# Enable autopilot
azlin autopilot enable --budget 500 --strategy balanced

# Preview what it would do
azlin autopilot run --dry-run

# If acceptable, execute
azlin autopilot run
```

### Daily automated cleanup

Create a cron job:
```bash
# Run autopilot daily at 6 PM
0 18 * * * azlin autopilot run
```

Or with logging:
```bash
0 18 * * * azlin autopilot run >> ~/.azlin/logs/autopilot.log 2>&1
```

### Budget emergency response

```bash
# Check budget status
azlin autopilot status

# If critical, run immediately
azlin autopilot run

# Verify results
azlin autopilot status
```

### Configuration testing

```bash
# Adjust settings
azlin autopilot config --set idle_threshold=60

# Test with dry-run
azlin autopilot run --dry-run

# If too aggressive, adjust
azlin autopilot config --set idle_threshold=120

# Test again
azlin autopilot run --dry-run

# Execute when satisfied
azlin autopilot run
```

### Pre-deployment cleanup

```bash
# Before creating new VMs, clean up old ones
azlin autopilot run

# Check available budget
azlin autopilot status

# Create new VMs
azlin new --name new-vm-1
azlin new --name new-vm-2
```

## Dry-Run vs Execute Mode

### Dry-Run Mode (--dry-run)

**Behavior:**
- Scans and analyzes VMs
- Generates recommendations
- Shows expected savings
- **Does not change anything**

**Use when:**
- Testing configuration
- Reviewing recommendations
- Before scheduled autopilot runs
- Learning what autopilot would do

### Execute Mode (no --dry-run)

**Behavior:**
- Scans and analyzes VMs
- **Executes recommended actions**
- Stops idle VMs
- Downsizes underutilized VMs
- Updates budget tracking

**Use when:**
- Ready to optimize costs
- Budget approaching limit
- Manual cleanup needed
- Automated runs (cron)

## Action Types

### Stop Actions

Autopilot stops VMs when:
- Idle longer than threshold
- No active SSH sessions
- Not protected by tags
- Budget requires action

### Downsize Actions

Autopilot downsizes VMs when:
- CPU utilization below threshold for 24+ hours
- No named session
- Strategy allows downsizing
- Larger size available to downsize to

### Skip Actions

Autopilot skips VMs when:
- Protected by tags (`production`, `critical`, etc.)
- Named session active
- Recently created (<4 hours)
- Active SSH connections
- High CPU/memory utilization

## Automation

### Systemd timer (Linux/WSL)

Create `~/.config/systemd/user/autopilot.service`:
```ini
[Unit]
Description=azlin autopilot optimization

[Service]
Type=oneshot
ExecStart=/usr/bin/azlin autopilot run
```

Create `~/.config/systemd/user/autopilot.timer`:
```ini
[Unit]
Description=Run azlin autopilot daily

[Timer]
OnCalendar=daily
OnCalendar=18:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
systemctl --user enable --now autopilot.timer
```

### Cron (macOS/Linux)

```bash
# Edit crontab
crontab -e

# Add daily run at 6 PM
0 18 * * * /usr/local/bin/azlin autopilot run
```

### GitHub Actions

```yaml
name: Autopilot Optimization
on:
  schedule:
    - cron: '0 18 * * *'  # Daily at 6 PM UTC
  workflow_dispatch:

jobs:
  optimize:
    runs-on: ubuntu-latest
    steps:
      - name: Run autopilot
        env:
          AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
        run: |
          pipx install azlin
          azlin autopilot run
```

## Troubleshooting

### Autopilot not enabled

```
Error: Autopilot is not enabled
```

**Solution**: Enable autopilot first:
```bash
azlin autopilot enable --budget 500
azlin autopilot run --dry-run
```

### No actions recommended

```
Recommendations
---------------
No actions recommended. All VMs are optimally utilized.
```

**Possible reasons:**
- All VMs are actively used
- Idle threshold too high
- Strategy too conservative

**Solutions:**
```bash
# Check VM activity
azlin status

# Adjust thresholds
azlin autopilot config --set idle_threshold=60

# Try again
azlin autopilot run --dry-run
```

### Actions failed to execute

```
✗ Failed to stop vm-test-123 (Azure API error)
```

**Solutions:**
- Check Azure permissions
- Verify VM exists: `azlin list`
- Check VM state: `azlin status vm-test-123`
- Review logs: `~/.azlin/logs/autopilot.log`
- Try manual action: `azlin stop vm-test-123`

### Protected VMs being targeted

```
→ Stop vm-prod-1 (idle 150 min)
```

**Solution**: Protect the VM:
```bash
# Add protection tag
azlin tag vm-prod-1 --add critical=true

# Configure autopilot to respect it
azlin autopilot config --set protected_tags=critical

# Verify
azlin autopilot run --dry-run
```

## Related Commands

- [azlin autopilot status](status.md) - View status and budget
- [azlin autopilot config](config.md) - Adjust settings
- [azlin cost](../util/cost.md) - View detailed cost breakdown
- [azlin prune](../util/prune.md) - Manual VM cleanup
