# Fleet Management

Orchestrate commands across multiple VMs with parallel execution and intelligent routing.

## Overview

Fleet commands enable distributed operations across VM fleets with pattern matching, parallel execution, and comprehensive error handling.

## Available Commands

### Distributed Operations

- [**Fleet Overview**](overview.md) - Fleet management concepts and patterns
- [**azlin batch command**](../batch/command.md) - Execute commands on multiple VMs
- [**azlin batch sync**](../batch/sync.md) - Sync files to VM fleets
- [**azlin w**](../util/w.md) - Distributed `w` command
- [**azlin ps**](../util/ps.md) - Distributed `ps aux` command

## Quick Start Examples

### Execute on All VMs

```bash
# Run command on every VM
azlin batch exec "*" "docker ps"

# Check disk space across fleet
azlin batch exec "*" "df -h"

# Update all VMs
azlin batch exec "*" "sudo apt update && sudo apt upgrade -y"
```

### Pattern Matching

```bash
# Target specific VM groups
azlin batch exec "api-*" "systemctl restart nginx"
azlin batch exec "db-*" "docker logs postgres"
azlin batch exec "test-*" "rm -rf /tmp/*"

# Multiple patterns
azlin batch exec "web-*,api-*" "git pull origin main"
```

### Specific VM Lists

```bash
# Comma-separated VM names
azlin batch exec "vm1,vm2,vm3" "uptime"

# Tag-based selection
azlin batch exec --tag env=prod "systemctl status myapp"
```

### Monitoring Fleet

```bash
# Who's logged in across fleet
azlin w

# All running processes
azlin ps

# Filter by pattern
azlin w --filter "api-*"
azlin ps --filter "db-*"
```

## Key Features

### Parallel Execution

Execute commands simultaneously across VMs:

```bash
# Parallel updates
azlin batch exec "*" "git pull" --parallel 10

# Sequential for safety
azlin batch exec "*" "systemctl restart app" --sequential
```

### Error Handling

Continue execution even if some VMs fail:

```bash
# Continue on errors
azlin batch exec "*" "risky-command" --continue-on-error

# Stop on first failure
azlin batch exec "*" "critical-command" --stop-on-error
```

### Output Aggregation

Collect and format results:

```bash
# Show all output
azlin batch exec "api-*" "docker ps" --verbose

# Summary only
azlin batch exec "*" "uptime" --summary

# Save to file
azlin batch exec "*" "systemctl status" > fleet-status.txt
```

### File Distribution

Sync files to multiple VMs:

```bash
# Sync to all VMs
azlin batch sync "*" ~/myproject

# Sync to specific pattern
azlin batch sync "web-*" ~/frontend --delete

# Dry-run first
azlin batch sync "*" ~/config --dry-run
```

## Common Workflows

### Deploy Application Update

```bash
# 1. Sync code to all app servers
azlin batch sync "app-*" ~/myapp

# 2. Restart services
azlin batch exec "app-*" "systemctl restart myapp"

# 3. Verify status
azlin batch exec "app-*" "systemctl status myapp"
```

### Fleet Health Check

```bash
# Check system resources
azlin batch exec "*" "df -h && free -h && uptime"

# Check application status
azlin batch exec "*" "systemctl status myapp"

# Check docker containers
azlin batch exec "*" "docker ps && docker stats --no-stream"
```

### Configuration Management

```bash
# Update configuration
azlin batch sync "*" ~/config/nginx.conf /etc/nginx/

# Reload services
azlin batch exec "*" "sudo systemctl reload nginx"

# Verify configuration
azlin batch exec "*" "nginx -t"
```

### Log Collection

```bash
# Collect application logs
azlin batch exec "*" "tail -n 100 /var/log/myapp.log" > all-logs.txt

# Search for errors
azlin batch exec "*" "grep ERROR /var/log/myapp.log"

# Download logs
for vm in $(azlin list --name-only); do
  azlin connect $vm --command "cat /var/log/myapp.log" > logs/${vm}.log
done
```

## Pattern Matching Reference

### Wildcard Patterns

```bash
# All VMs starting with "api-"
azlin batch exec "api-*" "command"

# All VMs ending with "-prod"
azlin batch exec "*-prod" "command"

# All VMs containing "test"
azlin batch exec "*test*" "command"
```

### Multiple Patterns

```bash
# Match multiple patterns (OR)
azlin batch exec "web-*,api-*,db-*" "command"

# Exclude pattern (requires explicit list)
# List all VMs, then filter manually
azlin list --name-only | grep -v "test-" | xargs -I {} azlin connect {} --command "..."
```

### Tag-Based Selection

```bash
# Select by tag
azlin batch exec "*" "command" --tag env=prod

# Multiple tags
azlin batch exec "*" "command" --tag env=prod --tag app=web
```

## Performance Tuning

### Parallelism

```bash
# Default: 5 parallel executions
azlin batch exec "*" "command"

# More parallel (faster, more load)
azlin batch exec "*" "command" --parallel 20

# Sequential (slower, more reliable)
azlin batch exec "*" "command" --sequential
```

### Timeout Control

```bash
# Set timeout per VM
azlin batch exec "*" "long-command" --timeout 300

# No timeout (wait forever)
azlin batch exec "*" "command" --no-timeout
```

### Retry Logic

```bash
# Retry failed commands
azlin batch exec "*" "flaky-command" --retry 3

# Retry delay
azlin batch exec "*" "command" --retry 3 --retry-delay 5
```

## Best Practices

### 1. Test with Dry-Run

```bash
# Always test sync operations
azlin batch sync "*" ~/important-data --dry-run
azlin batch sync "*" ~/important-data
```

### 2. Use Patterns Wisely

```bash
# Good: Specific patterns
azlin batch exec "api-prod-*" "restart-command"

# Risky: Too broad
azlin batch exec "*" "dangerous-command"
```

### 3. Monitor Output

```bash
# Use verbose for important operations
azlin batch exec "*" "critical-command" --verbose

# Save output for auditing
azlin batch exec "*" "command" | tee operation.log
```

### 4. Handle Failures

```bash
# Critical operations: Stop on error
azlin batch exec "*" "database-migration" --stop-on-error

# Best-effort operations: Continue on error
azlin batch exec "*" "optional-update" --continue-on-error
```

## Fleet Monitoring Commands

### System Status

```bash
# Logged-in users
azlin w

# All processes
azlin ps

# System resources
azlin batch exec "*" "top -bn1 | head -20"
```

### Application Status

```bash
# Service status
azlin batch exec "*" "systemctl status myapp"

# Docker containers
azlin batch exec "*" "docker ps"

# Application health
azlin batch exec "*" "curl -sf http://localhost:8080/health"
```

### Logs and Diagnostics

```bash
# Recent logs
azlin batch exec "*" "journalctl -n 50"

# Error logs
azlin batch exec "*" "grep ERROR /var/log/myapp.log | tail -20"

# Disk usage
azlin batch exec "*" "df -h"
```

## Error Handling

### Common Issues

**Connection failures:**
```bash
# Some VMs unreachable
azlin batch exec "*" "command" --continue-on-error
```

**Command failures:**
```bash
# Track which VMs failed
azlin batch exec "*" "command" --verbose 2>&1 | grep ERROR
```

**Timeout issues:**
```bash
# Increase timeout
azlin batch exec "*" "slow-command" --timeout 600
```

## Related Commands

- [azlin batch command](../batch/command.md) - Batch command execution
- [azlin batch sync](../batch/sync.md) - Batch file synchronization
- [azlin w](../util/w.md) - Distributed `w` command
- [azlin ps](../util/ps.md) - Distributed `ps aux` command
- [azlin compose](../advanced/compose.md) - Multi-VM infrastructure

## See Also

- [Fleet Management](../../batch/fleet.md)
- [Fleet Management](../../batch/fleet.md)
- [Monitoring](../../monitoring/index.md)
