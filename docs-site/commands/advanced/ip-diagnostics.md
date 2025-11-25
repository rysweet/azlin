# azlin ip (IP Diagnostics)

Troubleshoot IP connectivity issues and diagnose network problems across azlin VMs.

## Description

The `azlin ip` command provides comprehensive IP diagnostics including connectivity tests, DNS resolution checks, firewall rule verification, and network path analysis.

## Usage

```bash
azlin ip [COMMAND] [OPTIONS]
```

## Commands

| Command | Description |
|---------|-------------|
| `check` | Check VM IP connectivity |
| `diagnose` | Run comprehensive diagnostics |
| `test` | Test connectivity to specific IP |
| `trace` | Trace network path |

## Examples

### Check VM IP Status

```bash
azlin ip check my-vm
```

**Output:**
```
IP Diagnostics for 'my-vm':

VM Status: Running
Public IP: 20.12.34.56
Private IP: 10.0.1.5
Region: eastus

Connectivity Tests:
✓ VM is reachable
✓ SSH port (22) is open
✓ DNS resolution working
✓ Internet connectivity confirmed

Network Configuration:
  VNet: azlin-vnet
  Subnet: default
  NSG: azlin-vm-001-nsg

No issues detected.
```

### Run Full Diagnostics

```bash
azlin ip diagnose my-vm
```

**Output includes:**
- VM network configuration
- Public/private IP status
- SSH connectivity test
- DNS resolution check
- Firewall rules
- Network security group (NSG) rules
- Route table analysis
- Internet connectivity test

### Test Specific Connectivity

```bash
# Test if VM can reach external service
azlin ip test my-vm --target 8.8.8.8
azlin ip test my-vm --target github.com
```

### Trace Network Path

```bash
# Trace route to external destination
azlin ip trace my-vm --target google.com
```

**Output:**
```
Tracing route from my-vm (20.12.34.56) to google.com:

Hop 1: 10.0.1.1 (0.8 ms) - Gateway
Hop 2: 172.16.0.1 (2.3 ms) - Azure backbone
Hop 3: 142.250.185.78 (15.4 ms) - google.com

Route is healthy.
```

## Common Workflows

### Cannot Connect to VM

```bash
# Step 1: Check basic connectivity
azlin ip check my-vm

# Step 2: If issues found, run full diagnostics
azlin ip diagnose my-vm

# Step 3: Common fixes shown:
# - Start VM if stopped
# - Check NSG rules
# - Verify firewall settings
```

### Debug Application Connectivity

```bash
# Check if VM can reach database
azlin ip test my-vm --target db-server.azure.com --port 5432

# Check outbound internet
azlin ip test my-vm --target api.github.com --port 443
```

### Network Security Audit

```bash
# Check all VMs
for vm in $(azlin list --format json | jq -r '.[].name'); do
  azlin ip diagnose $vm >> /tmp/network-audit.txt
done
```

## Troubleshooting Scenarios

### SSH Connection Refused

**Problem:** Cannot SSH to VM.

**Diagnosis:**
```bash
azlin ip check my-vm
```

**Common causes:**
- VM is stopped
- NSG blocks port 22
- Public IP not assigned
- Firewall rules blocking SSH

### VM Cannot Reach Internet

**Problem:** VM has no outbound connectivity.

**Diagnosis:**
```bash
azlin ip test my-vm --target 8.8.8.8
azlin ip diagnose my-vm
```

**Common causes:**
- NSG outbound rules blocking traffic
- Route table misconfiguration
- DNS resolution failure

### Slow Network Performance

**Diagnosis:**
```bash
azlin ip trace my-vm --target target-server.com
```

Look for:
- High latency hops
- Packet loss
- Routing issues

## Related Commands

- [`azlin connect`](../vm/connect.md) - SSH to VM
- [`azlin status`](../vm/status.md) - VM status
- [`azlin bastion`](../bastion/index.md) - Secure access

## Deep Links

- [IP diagnostics implementation](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L3000-L3100)
- [Network troubleshooting spec](https://github.com/rysweet/azlin/blob/main/docs/specs/ip-check-command-spec.md)

## See Also

- [Connection Issues](../../troubleshooting/connection.md)
- [What is Bastion](../../bastion/overview.md)
