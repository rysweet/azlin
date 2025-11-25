# azlin status

**Check detailed VM status, power state, and IP addresses**

## Description

The `azlin status` command displays detailed status information for VMs in a resource group, including power state (Running, Stopped, Deallocated), IP addresses (public and private), location, and VM size. Use this command to verify VM state before connecting or after lifecycle operations.

**Use cases:**
- Verify VM is running before connecting
- Check if VM has public IP address
- Confirm VM started successfully
- Monitor power state after stop/start operations
- Get IP address for direct SSH access

## Usage

```bash
azlin status [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group containing the VMs (default: from config) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--vm TEXT` | Name | Show status for specific VM only (default: all VMs) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Usage

```bash
# Show status of all VMs in default resource group
azlin status

# Show status of all VMs in specific resource group
azlin status --rg my-resource-group

# Show status of single VM
azlin status --vm my-vm

# Show status of single VM with explicit resource group
azlin status --vm my-vm --rg my-resource-group
```

### Workflow Examples

```bash
# Check VM before connecting
azlin status --vm my-vm
azlin connect my-vm

# Verify VM started successfully
azlin start my-vm
sleep 5
azlin status --vm my-vm  # Should show "Running"

# Check if VM has public IP
azlin status --vm my-vm | grep "Public IP"

# Verify VM stopped
azlin stop my-vm --deallocate
azlin status --vm my-vm  # Should show "Deallocated"
```

### Scripting Examples

```bash
# Check if VM is running
if azlin status --vm my-vm | grep -q "Running"; then
    echo "VM is running"
    azlin connect my-vm
else
    echo "VM is not running, starting..."
    azlin start my-vm
fi

# Get public IP
ip=$(azlin status --vm my-vm | grep "Public IP" | awk '{print $3}')
echo "VM IP: $ip"

# Wait for VM to reach running state
while ! azlin status --vm my-vm | grep -q "Running"; do
    echo "Waiting for VM to start..."
    sleep 5
done
echo "VM is running!"
```

## Status Output Format

### All VMs Status

When run without `--vm` flag, displays summary table:

```
┌─────────────────┬───────────┬─────────────────┬───────────────┬──────────────────────┐
│ VM Name         │ Status    │ Public IP       │ Private IP    │ Location             │
├─────────────────┼───────────┼─────────────────┼───────────────┼──────────────────────┤
│ myproject       │ Running   │ 20.123.45.67    │ 10.0.1.4      │ eastus               │
│ backend-dev     │ Running   │ 20.123.45.68    │ 10.0.1.5      │ westus2              │
│ test-vm         │ Stopped   │ -               │ 10.0.1.6      │ eastus               │
│ old-vm          │ Deallocated│ -              │ 10.0.1.7      │ eastus               │
└─────────────────┴───────────┴─────────────────┴───────────────┴──────────────────────┘
```

### Single VM Status

When run with `--vm` flag, displays detailed information:

```
VM: myproject
Status: Running
Public IP: 20.123.45.67
Private IP: 10.0.1.4
Location: eastus
Size: Standard_E32as_v5
Resource Group: my-rg
```

## Power States Explained

| State | Description | Has Public IP? | Can Connect? | Billing |
|-------|-------------|----------------|--------------|---------|
| **Running** | VM is powered on and operational | Yes | Yes | Full (compute + storage) |
| **Stopped** | VM stopped but resources allocated | Yes | No | Full (compute + storage) |
| **Deallocated** | VM stopped, resources released | No | No | Storage only |
| **Starting** | VM is booting up | Maybe | Soon | Full (once started) |
| **Stopping** | VM is shutting down | Yes | No | Full (until stopped) |

**Key insights:**
- **Running**: Ready for work, fully accessible
- **Stopped**: Not accessible but still costing money (use `--deallocate`)
- **Deallocated**: Maximum cost savings, public IP released
- **Starting/Stopping**: Transitional states, wait before connecting

## Understanding IP Addresses

### Public IP
- **Purpose**: Direct internet access to VM
- **When present**: Running and Stopped (not deallocated) VMs
- **When absent**: Deallocated VMs, Bastion-only VMs
- **Format**: IPv4 (e.g., 20.123.45.67)

### Private IP
- **Purpose**: Internal Azure network communication
- **When present**: Always (unless VM deleted)
- **Network**: VNet-internal only
- **Format**: IPv4 from VNet subnet (e.g., 10.0.1.4)

**Connection implications:**
```bash
# Public IP present - direct connection
azlin connect myvm  # Uses public IP

# No public IP - requires bastion
azlin connect myvm  # Prompts for bastion tunnel
```

## Common Status Patterns

### Healthy Running VM
```
VM: myproject
Status: Running
Public IP: 20.123.45.67
Private IP: 10.0.1.4
```
**Action**: Ready to connect

### Deallocated VM (Cost Savings)
```
VM: my-vm
Status: Deallocated
Public IP: -
Private IP: 10.0.1.4
```
**Action**: Start VM before connecting

### Bastion-Only VM
```
VM: secure-vm
Status: Running
Public IP: -
Private IP: 10.0.1.10
```
**Action**: Connect using bastion tunnel

### Starting VM (Wait)
```
VM: my-vm
Status: Starting
Public IP: - (allocating)
Private IP: 10.0.1.4
```
**Action**: Wait 30-60 seconds, check again

## Troubleshooting

### VM Not Found

**Symptoms:** "VM not found" or empty status output.

**Solutions:**
```bash
# Verify VM name
azlin list --all

# Check resource group
azlin status --rg correct-resource-group

# List all VMs across all resource groups
azlin list --show-all-vms
```

### Status Shows "Unknown"

**Symptoms:** Power state shows "Unknown" or "--".

**Solutions:**
```bash
# Refresh Azure CLI cache
az account clear
az login

# Check Azure portal for VM status
# May indicate Azure service issue

# Try Azure CLI directly
az vm get-instance-view --name my-vm --resource-group my-rg
```

### No Public IP on Running VM

**Symptoms:** VM shows "Running" but no public IP address.

**Possible causes:**
1. VM is bastion-only (intentional private VM)
2. Public IP was manually removed
3. VM network configuration issue

**Solutions:**
```bash
# Check if bastion is available
azlin bastion list

# Connect via bastion
azlin connect myvm --yes

# Add public IP (if needed)
az network public-ip create --name myvm-ip --resource-group my-rg
az network nic ip-config update --name ipconfig1 --nic-name myvm-nic \
    --resource-group my-rg --public-ip-address myvm-ip
```

### Different Public IP After Start

**Symptoms:** Public IP changed after stopping/deallocating VM.

**Explanation:** Dynamic public IPs are released when VM is deallocated.

**Solutions:**
```bash
# Accept new IP (normal behavior)
azlin status --vm my-vm  # Note new IP

# Or use reserved public IP (prevents changes)
# Configure during VM provisioning or via Azure portal
```

## Advanced Usage

### Monitoring Scripts

```bash
# Check all VMs and alert on non-running
azlin status | grep -v "Running" | while read vm status _; do
    echo "ALERT: $vm is $status"
done

# Export status to JSON (via Azure CLI)
az vm list --resource-group my-rg --show-details --output json > vm-status.json

# Monitor specific VM until running
while true; do
    status=$(azlin status --vm my-vm | grep "Status" | awk '{print $2}')
    echo "Current status: $status"
    if [ "$status" = "Running" ]; then
        break
    fi
    sleep 5
done
```

### Health Checks

```bash
# Pre-connection health check
check_vm_health() {
    local vm=$1

    # Check power state
    if ! azlin status --vm $vm | grep -q "Running"; then
        echo "ERROR: VM $vm is not running"
        return 1
    fi

    # Check public IP exists
    if ! azlin status --vm $vm | grep -q "Public IP"; then
        echo "WARNING: VM $vm has no public IP (bastion required)"
    fi

    echo "VM $vm is healthy"
    return 0
}

check_vm_health my-vm && azlin connect my-vm
```

### Cost Analysis

```bash
# Find VMs that should be deallocated
azlin status | grep "Stopped" | while read vm _; do
    echo "VM $vm is stopped but not deallocated (still billing)"
    echo "Run: azlin stop $vm --deallocate"
done

# Count VMs by state
echo "Running: $(azlin status | grep -c 'Running')"
echo "Stopped: $(azlin status | grep -c 'Stopped')"
echo "Deallocated: $(azlin status | grep -c 'Deallocated')"
```

## Integration Examples

### CI/CD Pipeline

```bash
# Verify VM is ready before deployment
- name: Check VM Status
  run: |
    azlin status --vm deploy-vm | grep -q "Running"
    if [ $? -ne 0 ]; then
      echo "Starting VM..."
      azlin start deploy-vm
      sleep 60
    fi
```

### Monitoring Dashboards

```bash
# Collect status metrics for Prometheus/Grafana
azlin status | awk 'NR>2 {
    print "vm_status{name=\""$1"\",status=\""$2"\"} 1"
}'
```

### Auto-Scaling Scripts

```bash
# Start additional VMs if load is high
if [ $current_load -gt 80 ]; then
    # Start stopped backup VMs
    azlin status | grep "Deallocated" | head -2 | while read vm _; do
        azlin start $vm
    done
fi
```

## Related Commands

- [`azlin list`](list.md) - List all VMs with summary status
- [`azlin start`](start.md) - Start stopped VM
- [`azlin stop`](stop.md) - Stop or deallocate VM
- [`azlin connect`](connect.md) - Connect after verifying status
- [`azlin bastion status`](../bastion/status.md) - Check bastion availability

## Source Code

- [vm_manager.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_manager.py) - Status checking logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All VM commands](index.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
- [Connection Issues](../../troubleshooting/connection.md)
