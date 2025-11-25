# Batch Command Execution

Execute shell commands across multiple VMs simultaneously with parallel execution and aggregated output.

## Overview

`azlin batch command` runs any shell command on multiple VMs at once, displaying aggregated results. Perfect for fleet-wide updates, health checks, and rapid diagnostics across your entire VM infrastructure.

## Basic Usage

```bash
# Execute on VMs with specific tag
azlin batch command 'uptime' --tag env=dev

# Execute on VMs matching pattern
azlin batch command 'df -h' --vm-pattern 'web-*'

# Execute on all VMs
azlin batch command 'hostname' --all

# Show output from each VM
azlin batch command 'ps aux | grep python' --all --show-output
```

## Command Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tag` | Filter VMs by tag (key=value) | None |
| `--vm-pattern` | Filter VMs by name glob | None |
| `--all` | Select all VMs | False |
| `--show-output` | Show command output from each VM | False |
| `--max-workers` | Parallel execution threads | 10 |
| `--timeout` | Command timeout in seconds | 300 |
| `--resource-group`, `--rg` | Resource group | Current context |

## Examples

### Fleet Health Check

```bash
azlin batch command 'uptime' --all --show-output
```

**Output:**
```
[web-1] 14:23:45 up 5 days, 2:15, 1 user, load average: 0.52, 0.45, 0.38
[web-2] 14:23:46 up 5 days, 2:16, 1 user, load average: 0.15, 0.20, 0.18
[db-1]  14:23:47 up 12 days, 8:42, 1 user, load average: 1.25, 1.30, 1.28

Completed: 3/3 VMs
```

### Update Packages on Development VMs

```bash
azlin batch command 'sudo apt update && sudo apt upgrade -y' \
  --tag env=dev \
  --timeout 600
```

### Check Disk Space

```bash
azlin batch command 'df -h /' --all --show-output
```

### Restart Service on Web Servers

```bash
azlin batch command 'sudo systemctl restart nginx && systemctl status nginx' \
  --vm-pattern 'web-*' \
  --show-output
```

### Run Custom Script

```bash
azlin batch command 'bash /tmp/deploy.sh' \
  --tag project=myapp \
  --timeout 1800
```

## Common Use Cases

### 1. Package Updates

```bash
# Update all dev VMs
azlin batch command 'sudo apt update && sudo apt upgrade -y' \
  --tag env=dev \
  --timeout 900

# Install new package fleet-wide
azlin batch command 'sudo apt install -y htop' --all
```

### 2. Configuration Deploy

```bash
# Restart after config change
azlin batch command 'sudo systemctl restart app && systemctl status app' \
  --vm-pattern 'app-*' \
  --show-output
```

### 3. Health Checks

```bash
# Check service status
azlin batch command 'systemctl is-active nginx' --vm-pattern 'web-*' --show-output

# Check disk usage
azlin batch command 'df -h' --all --show-output

# Check memory
azlin batch command 'free -h' --all --show-output
```

### 4. Log Collection

```bash
# Grab recent errors
azlin batch command 'tail -50 /var/log/app.log | grep ERROR' \
  --all \
  --show-output > errors.log
```

### 5. Security Updates

```bash
# Apply security patches
azlin batch command 'sudo unattended-upgrade' \
  --all \
  --timeout 1200
```

## Parallelism and Performance

### Default Behavior

- 10 concurrent SSH connections
- Queue remaining VMs
- Continue on individual failures

### Adjust for Your Workload

```bash
# Light operations: high parallelism
azlin batch command 'hostname' --all --max-workers 20

# Heavy operations: low parallelism
azlin batch command 'docker build .' --all --max-workers 3
```

## Output Handling

### Without --show-output

Shows only summary:
```
Executing on 5 VMs...
Completed: 5/5 VMs
```

### With --show-output

Shows output from each VM:
```
[vm-1] Command output here
[vm-2] Command output here
Completed: 2/2 VMs
```

## Error Handling

- Failed VMs don't stop execution
- Summary shows successful/failed counts
- Exit code reflects any failures

## Tips

1. **Test on one VM first**: Use `--vm-pattern 'vm-1'` to test
2. **Use timeouts**: Set realistic timeouts for long operations
3. **Capture output**: Use `--show-output > file.log` to save results
4. **Escape properly**: Use single quotes for commands with special characters

## See Also

- [Batch Operations Overview](index.md)
- [Fleet Management](fleet.md)
- [Tags Guide](../advanced/tags.md)

---

*Documentation last updated: 2025-11-24*
