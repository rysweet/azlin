# VM Logs Viewer

View VM system logs and cloud-init output without needing SSH access.

## Overview

The `azlin logs` command provides access to VM system logs and cloud-init output through Azure's diagnostics infrastructure, allowing you to troubleshoot issues even when SSH access is unavailable. This is particularly useful for debugging provisioning failures, boot issues, or investigating problems with VMs that won't start.

Unlike traditional SSH-based log viewing, `azlin logs` retrieves logs directly from Azure's backend infrastructure, making it invaluable for troubleshooting connectivity problems.

## Basic Usage

```bash
# View recent logs for a VM
azlin logs my-vm

# View boot logs
azlin logs my-vm --boot

# Follow logs in real-time
azlin logs my-vm --follow

# View cloud-init logs
azlin logs my-vm --cloud-init
```

## Command Options

| Option | Short | Description |
|--------|-------|-------------|
| `--boot` | | Show boot logs |
| `--follow` | `-f` | Follow logs in real-time |
| `--cloud-init` | | Show cloud-init provisioning logs |
| `--lines` | `-n` | Number of lines to show (default: 100) |
| `--resource-group` | `--rg` | Resource group |
| `--help` | `-h` | Show help message |

## Examples

### View Recent System Logs

Check the most recent system logs for a VM:

```bash
azlin logs my-dev-vm
```

**Output:**
```
Nov 24 14:23:45 my-dev-vm systemd[1]: Started Session 42 of user azureuser.
Nov 24 14:24:12 my-dev-vm sshd[1234]: Accepted publickey for azureuser
Nov 24 14:25:03 my-dev-vm kernel: [UFW BLOCK] IN=eth0 OUT=
Nov 24 14:26:15 my-dev-vm systemd[1]: Starting Docker Application Container...
Nov 24 14:26:18 my-dev-vm dockerd[5678]: time="2025-11-24T14:26:18Z" level=info
```

**Use Case:** Quick health check of a running VM.

### Debug Boot Issues

When a VM won't start or SSH isn't available, check boot logs:

```bash
azlin logs problem-vm --boot
```

**Output:**
```
[    0.000000] Linux version 5.15.0-1052-azure
[    0.000000] Command line: BOOT_IMAGE=/boot/vmlinuz
[    0.521043] Booting paravirtualized kernel on bare hardware
[    1.234567] systemd[1]: Reached target Basic System
[    2.345678] cloud-init[892]: Cloud-init v. 23.4 running 'init'
[    3.456789] sshd[1234]: Server listening on 0.0.0.0 port 22
```

**Use Case:** Diagnose why a VM is failing to boot or become accessible.

### Monitor Cloud-Init Provisioning

Watch cloud-init setup in real-time during VM provisioning:

```bash
azlin logs new-vm --cloud-init --follow
```

**Output:**
```
Cloud-init v. 23.4 running 'init' at Nov 24 14:20:12
Running module: write-files
Writing /etc/environment... done
Running module: package-update-upgrade-install
Reading package lists... Done
Installing: git, docker.io, tmux, neovim
Setting up docker.io (24.0.5-0ubuntu1) ...
Running module: runcmd
Cloning dotfiles repository...
Configuring shell environment...
Cloud-init v. 23.4 finished at Nov 24 14:23:45. Datasource DataSourceAzure
```

**Use Case:** Debug provisioning scripts or package installation issues.

### View More Log Lines

Get more context by viewing more lines:

```bash
azlin logs my-vm --lines 500
```

**Use Case:** Investigate issues that require more historical context.

### Follow Logs in Real-Time

Watch logs as they're generated:

```bash
azlin logs my-vm --follow
```

Press `Ctrl+C` to stop following.

**Use Case:** Monitor ongoing processes, watch for errors during deployments.

## Common Use Cases

### 1. Troubleshoot SSH Connection Failures

When you can't connect to a VM, check logs without SSH:

```bash
# Check if SSH service started
azlin logs problem-vm | grep sshd

# View full boot sequence
azlin logs problem-vm --boot

# Check cloud-init completion
azlin logs problem-vm --cloud-init
```

**What to Look For:**
- `sshd[PID]: Server listening` - SSH service started
- Cloud-init finish message - Provisioning completed
- Error messages related to networking or authentication

### 2. Debug Provisioning Failures

When a new VM doesn't provision correctly:

```bash
# Watch provisioning in real-time
azlin logs new-vm --cloud-init --follow

# After failure, check what went wrong
azlin logs new-vm --cloud-init --lines 1000
```

**What to Look For:**
- Package installation failures
- Git clone errors
- Network connectivity issues
- Permissions problems

### 3. Investigate Application Crashes

When an application crashes, check system logs:

```bash
# View recent logs
azlin logs app-server --lines 200

# Look for OOM killer
azlin logs app-server | grep -i "out of memory"

# Check for segfaults
azlin logs app-server | grep -i "segmentation fault"
```

**What to Look For:**
- Out of memory (OOM) killer messages
- Segmentation faults
- Application-specific error messages

### 4. Monitor Scheduled Tasks

Watch logs for cron jobs or systemd timers:

```bash
# Follow logs to see when tasks run
azlin logs worker-vm --follow

# Check for specific cron job
azlin logs worker-vm | grep CRON
```

### 5. Security Audit

Review authentication attempts and security events:

```bash
# Check SSH authentication attempts
azlin logs bastion-vm | grep "sshd.*authentication"

# Look for sudo usage
azlin logs admin-vm | grep sudo

# Check firewall blocks
azlin logs gateway-vm | grep "UFW BLOCK"
```

## Log Types and Sources

### System Logs (Default)

Standard syslog messages from all services:
- Authentication (sshd, sudo)
- System services (systemd, dockerd)
- Kernel messages
- Application logs

```bash
azlin logs my-vm
```

### Boot Logs

Kernel and early boot messages:
- Kernel initialization
- Hardware detection
- systemd target progression
- Service startup sequence

```bash
azlin logs my-vm --boot
```

### Cloud-Init Logs

Azure provisioning and customization:
- Package installation
- User/group setup
- File writes
- Command execution
- Custom script output

```bash
azlin logs my-vm --cloud-init
```

## Understanding Log Output

### Timestamp Format
```
Nov 24 14:23:45 my-vm ...
```
- Month, day, time (24-hour)
- VM hostname
- Log message

### Common Log Prefixes

**systemd:**
```
systemd[1]: Started Docker Application Container
```
System service manager events

**sshd:**
```
sshd[1234]: Accepted publickey for azureuser
```
SSH server authentication and connection events

**kernel:**
```
kernel: [UFW BLOCK] IN=eth0 OUT=
```
Kernel-level events and firewall

**cloud-init:**
```
cloud-init[892]: Running module: write-files
```
Provisioning script execution

## Troubleshooting

### "Cannot Retrieve Logs" Error

**Symptom:** Error when trying to fetch logs.

**Causes:**
1. VM doesn't exist or is in failed state
2. Boot diagnostics not enabled
3. Azure backend issue

**Solution:**
```bash
# Verify VM exists
azlin list | grep my-vm

# Check VM status
azlin status my-vm

# Enable boot diagnostics
az vm boot-diagnostics enable --name my-vm --resource-group my-rg
```

### No Recent Logs

**Symptom:** Logs are old or missing recent entries.

**Cause:** Log collection lag or VM not generating logs.

**Solution:**
```bash
# Try SSH to check if VM is actually running
azlin connect my-vm

# Increase lines to see older logs
azlin logs my-vm --lines 500
```

### "VM Not Running" Message

**Symptom:** Cannot get logs because VM is stopped.

**Cause:** VM is deallocated or stopped.

**Solution:**
```bash
# Start the VM first
azlin start my-vm

# Wait for it to boot
sleep 30

# Then check logs
azlin logs my-vm
```

### Logs Don't Update with --follow

**Symptom:** `--follow` mode doesn't show new logs.

**Cause:** Azure log collection delay (typically 1-2 minutes).

**Solution:**
- Logs through Azure infrastructure have inherent delay
- For real-time logs, use SSH: `azlin connect my-vm -c "tail -f /var/log/syslog"`

## Tips and Best Practices

### 1. Use Logs When SSH Fails First

Before troubleshooting SSH issues the hard way, check logs:

```bash
# Can't SSH? Check logs without SSH
azlin logs problem-vm --boot
azlin logs problem-vm --cloud-init
```

### 2. Combine with Status Command

Get full picture by checking status and logs:

```bash
# Check VM state
azlin status my-vm

# Then check logs
azlin logs my-vm
```

### 3. Save Logs for Analysis

Capture logs for later analysis or sharing:

```bash
# Save recent logs
azlin logs my-vm --lines 1000 > my-vm-logs.txt

# Save cloud-init for debugging
azlin logs my-vm --cloud-init > cloud-init.log
```

### 4. Use Grep for Filtering

Pipe to grep to find specific events:

```bash
# Find errors
azlin logs my-vm | grep -i error

# Find specific service
azlin logs my-vm | grep dockerd

# Find time range (requires timestamps)
azlin logs my-vm | grep "Nov 24 14:"
```

### 5. Check Logs After Provisioning

Always verify successful provisioning:

```bash
# Create VM
azlin new --name my-vm

# Wait for provisioning
sleep 120

# Verify cloud-init finished
azlin logs my-vm --cloud-init | tail
```

## Comparison: Logs vs SSH

### When to Use `azlin logs`

- SSH is not responding
- VM is in a failed state
- Debugging boot issues
- VM just created, waiting for SSH
- Quick log check without establishing SSH session

### When to Use SSH

- Need real-time logs (no delay)
- Need to run log analysis tools
- Need to view multiple log files
- Need to correlate with system commands

```bash
# Via logs command (no SSH needed)
azlin logs my-vm

# Via SSH (more powerful, requires connection)
azlin connect my-vm -c "tail -f /var/log/syslog"
```

## Integration with Other Commands

### With Status Command

```bash
# Check status first
azlin status my-vm

# Then investigate with logs
azlin logs my-vm --boot
```

### With New/Clone

```bash
# Create VM
azlin new --name dev-vm

# Monitor provisioning
azlin logs dev-vm --cloud-init --follow
```

### With Batch Operations

```bash
# After batch command fails
azlin batch command --tag env=dev "systemctl restart app"

# Check logs on specific VMs
azlin logs failing-vm
```

## See Also

- [Status Command](status.md) - VM status overview
- [W Command](w.md) - See who is logged in
- [PS Command](ps.md) - View running processes
- [Connect Command](../vm-lifecycle/connecting.md) - SSH access
- [Troubleshooting Connection Issues](../troubleshooting/connection.md)
- [Troubleshooting Common Issues](../troubleshooting/common-issues.md)

---

*Documentation last updated: 2025-11-24*
