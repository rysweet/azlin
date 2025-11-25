# azlin batch command

Execute shell commands on multiple VMs simultaneously.

## Synopsis

```bash
azlin batch command COMMAND [OPTIONS]
```

## Description

Execute a shell command on multiple VMs in parallel. Filter VMs by tags, name patterns, or run on all VMs. Output can be shown inline or summarized.

## Arguments

**COMMAND** - Shell command to execute (required)

## Options

| Option | Description |
|--------|-------------|
| `--tag TEXT` | Filter VMs by tag (format: key=value) |
| `--vm-pattern TEXT` | Filter VMs by name pattern (glob) |
| `--all` | Select all VMs in resource group |
| `--resource-group, --rg TEXT` | Resource group |
| `--config PATH` | Config file path |
| `--max-workers INTEGER` | Maximum parallel workers (default: 10) |
| `--timeout INTEGER` | Command timeout in seconds (default: 300) |
| `--show-output` | Show command output from each VM |
| `-h, --help` | Show help message |

## Examples

### Execute on All VMs

```bash
# Run command on all VMs
azlin batch command 'uptime' --all

# Show detailed output
azlin batch command 'df -h' --all --show-output
```

### Filter by Tag

```bash
# Run on VMs with specific tag
azlin batch command 'git pull' --tag 'env=dev'

# Multiple filters (OR logic)
azlin batch command 'systemctl restart nginx' --tag 'app=web'
```

### Filter by Pattern

```bash
# Wildcard patterns
azlin batch command 'docker ps' --vm-pattern 'web-*'

# Multiple patterns
azlin batch command 'uptime' --vm-pattern '*-prod'
```

### Resource Group

```bash
# Specific resource group
azlin batch command 'free -h' --all --rg production-rg
```

### Parallelism Control

```bash
# More parallel workers (faster)
azlin batch command 'apt update' --all --max-workers 20

# Sequential execution
azlin batch command 'systemctl restart app' --all --max-workers 1
```

### Timeout Control

```bash
# Longer timeout for slow commands
azlin batch command 'npm install' --all --timeout 600

# Short timeout
azlin batch command 'hostname' --all --timeout 10
```

## Use Cases

### Code Deployment

```bash
# Pull latest code on all app servers
azlin batch command 'cd ~/myapp && git pull origin main' --tag 'app=web' --show-output
```

### Service Management

```bash
# Restart service across fleet
azlin batch command 'sudo systemctl restart myapp' --all

# Check service status
azlin batch command 'systemctl status myapp' --all --show-output
```

### System Administration

```bash
# Update packages
azlin batch command 'sudo apt update && sudo apt upgrade -y' --all --timeout 900

# Check disk space
azlin batch command 'df -h | grep -E "/$|/home"' --all --show-output

# Clear temp files
azlin batch command 'sudo rm -rf /tmp/*' --all
```

### Monitoring

```bash
# Check running processes
azlin batch command 'ps aux | grep myapp' --all --show-output

# Network connectivity
azlin batch command 'ping -c 3 google.com' --all --show-output

# Check logs
azlin batch command 'tail -20 /var/log/myapp.log' --tag 'env=prod' --show-output
```

### Configuration Management

```bash
# Copy config file
azlin batch command 'cp /tmp/new-config.json /etc/myapp/config.json' --all

# Verify configuration
azlin batch command 'cat /etc/myapp/config.json | jq .version' --all --show-output

# Reload configuration
azlin batch command 'sudo systemctl reload myapp' --all
```

## Output Formats

### Summary (Default)

```bash
$ azlin batch command 'uptime' --all
```

**Output:**
```
Executing on 3 VMs...

✓ web-01: Success (0.3s)
✓ web-02: Success (0.2s)
✗ web-03: Failed (connection timeout)

2/3 succeeded
```

### Detailed Output

```bash
$ azlin batch command 'hostname' --all --show-output
```

**Output:**
```
=== web-01 ===
web-01.internal

=== web-02 ===
web-02.internal

=== web-03 ===
web-03.internal

3/3 succeeded
```

## Selection Methods

### All VMs

```bash
# Every VM in resource group
azlin batch command 'uptime' --all
```

### By Tag

```bash
# VMs matching tag
azlin batch command 'git pull' --tag 'env=production'
azlin batch command 'systemctl status' --tag 'app=api'
```

Tags set via: `azlin tag my-vm --add env=production`

### By Pattern

```bash
# Glob patterns
azlin batch command 'uptime' --vm-pattern 'api-*'
azlin batch command 'df -h' --vm-pattern '*-test'
azlin batch command 'free -m' --vm-pattern 'web-*-prod'
```

Patterns support wildcards: `*`, `?`, `[abc]`

## Performance

| Workers | Best For | Notes |
|---------|----------|-------|
| 1 | Sequential operations requiring order | Slowest, most controlled |
| 10 (default) | General use | Good balance |
| 20-50 | Fast operations on many VMs | May hit SSH limits |

## Error Handling

### Connection Failures

Failed VMs are logged but don't stop execution:

```
✓ vm-01: Success
✗ vm-02: Connection timeout
✓ vm-03: Success

2/3 succeeded
```

### Command Failures

Non-zero exit codes are reported:

```
✓ vm-01: Success
✗ vm-02: Command failed (exit code 1)
✓ vm-03: Success
```

## Troubleshooting

### No VMs Selected

```bash
# Check VMs exist
azlin list

# Verify tags
azlin list --tag 'env=dev'

# Test pattern
azlin list | grep 'web-*'
```

### Timeouts

```bash
# Increase timeout
azlin batch command 'slow-command' --all --timeout 900

# Test connectivity
azlin w
```

### SSH Errors

```bash
# Verify SSH access
azlin connect test-vm

# Check keys
azlin keys list
```

## Best Practices

### Test First

```bash
# Test on one VM
azlin connect test-vm --command 'mycommand'

# Then batch
azlin batch command 'mycommand' --all
```

### Use Show-Output for Verification

```bash
# Always use --show-output for important operations
azlin batch command 'critical-command' --all --show-output
```

### Control Parallelism

```bash
# Sequential for order-dependent operations
azlin batch command 'db-migration' --all --max-workers 1

# Parallel for independent operations
azlin batch command 'git pull' --all --max-workers 20
```

### Set Appropriate Timeouts

```bash
# Quick commands: short timeout
azlin batch command 'hostname' --all --timeout 10

# Long operations: long timeout
azlin batch command 'npm install' --all --timeout 900
```

## Related Commands

- [azlin batch sync](sync.md) - Sync files to VMs
- [azlin batch start](start.md) - Start multiple VMs
- [azlin batch stop](stop.md) - Stop multiple VMs
- [azlin w](../util/w.md) - Who's logged in
- [azlin ps](../util/ps.md) - Running processes

## See Also

- [Fleet Management](../fleet/index.md)
- [Batch Operations](../../batch/index.md)
- [Fleet Management](../../batch/fleet.md)
