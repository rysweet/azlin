# azlin start

**Start stopped or deallocated Azure VMs**

## Description

The `azlin start` command starts a stopped or deallocated Azure VM, restoring it to running state. This is essential for cost optimization workflows where VMs are stopped when not in use and started on-demand.

**Use cases:**
- Resume work on a VM that was stopped overnight
- Start VMs as part of scheduled workloads
- Restore deallocated VMs after cost-saving shutdowns
- Batch start multiple VMs for distributed processing

## Usage

```bash
azlin start [OPTIONS] VM_NAME
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_NAME` | Required. Name of the VM to start |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group containing the VM (default: from config) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Basic Usage

```bash
# Start VM with default resource group
azlin start my-vm

# Start VM with explicit resource group
azlin start my-vm --rg my-resource-group

# Start VM using custom config
azlin start my-vm --config ~/custom-config.toml
```

### Workflow Examples

```bash
# Morning: Start work VM
azlin start work-vm
azlin connect work-vm

# Start VM and check status
azlin start my-vm
azlin status --vm my-vm

# Start multiple VMs
azlin start vm1 && azlin start vm2 && azlin start vm3
```

### Cost Optimization Workflow

```bash
# Evening: Stop VMs (save costs)
azlin stop dev-vm --deallocate
azlin stop test-vm --deallocate

# Morning: Resume work
azlin start dev-vm
azlin start test-vm
```

### Scripting and Automation

```bash
# Start VMs in parallel
for vm in vm1 vm2 vm3; do
    azlin start $vm &
done
wait
echo "All VMs started"

# Conditional start
if azlin status --vm my-vm | grep -q "Stopped"; then
    azlin start my-vm
    echo "VM started"
else
    echo "VM already running"
fi

# Start and wait for cloud-init
azlin start my-vm
azlin connect my-vm -- cloud-init status --wait
```

## VM States

Understanding Azure VM states:

| State | Description | Billing | Can Start? |
|-------|-------------|---------|------------|
| **Running** | VM is powered on and operational | Full | N/A |
| **Stopped** | VM stopped but resources allocated | Compute + Storage | Yes |
| **Deallocated** | VM stopped, resources released | Storage only | Yes |
| **Starting** | VM is booting up | Full (once started) | In progress |

**Key difference:**
- **Stopped**: Still billed for compute, faster restart
- **Deallocated**: No compute billing, slower restart (re-allocation needed)

## Start Time Expectations

| VM State | Typical Start Time |
|----------|-------------------|
| Stopped (not deallocated) | 30-60 seconds |
| Deallocated | 2-5 minutes |

**Why deallocated VMs take longer:**
1. Azure must re-allocate compute resources
2. VM may be placed on different physical hardware
3. Networking configuration must be re-established

## Troubleshooting

### Quota Exceeded Error

**Symptoms:** "QuotaExceeded" or "Not enough cores available" error.

**Solutions:**
```bash
# Check current quota usage
azlin list --show-quota

# Stop other running VMs to free quota
azlin stop other-vm --deallocate

# Request quota increase (Azure portal)
# Or try different region
```

### Start Operation Hangs

**Symptoms:** `azlin start` command doesn't complete after 5+ minutes.

**Solutions:**
```bash
# Check Azure portal for VM status
# VM may be stuck in "Starting" state

# Check for Azure service issues
az vm get-instance-view --name my-vm --resource-group my-rg

# Try stopping and starting again
az vm stop --name my-vm --resource-group my-rg
az vm start --name my-vm --resource-group my-rg
```

### VM Not Found

**Symptoms:** "VM not found" or "Resource not found" error.

**Solutions:**
```bash
# List all VMs to verify name
azlin list --all

# Check if using correct resource group
azlin list --rg my-resource-group

# Verify VM wasn't deleted
azlin list --show-all-vms
```

### Network Configuration Lost

**Symptoms:** VM starts but no IP address or network connectivity.

**Solutions:**
```bash
# Check VM network configuration
az vm show --name my-vm --resource-group my-rg

# Verify network interface is attached
az vm nic list --vm-name my-vm --resource-group my-rg

# Check if public IP was released (deallocated VMs)
azlin status --vm my-vm
```

## Cost Implications

### Starting Stopped VMs
- **Cost impact**: Resume compute billing immediately
- **Resources preserved**: IP addresses, network config, attached disks
- **Best for**: Short breaks (lunch, meetings)

### Starting Deallocated VMs
- **Cost impact**: Re-start compute billing after allocation
- **Resources released**: Public IP may change (unless reserved)
- **Best for**: Overnight, weekends, extended periods

**Cost example:**
```
VM Size: Standard_E32as_v5 (32 vCPUs, 128GB RAM)
Hourly cost: ~$1.50/hour

8-hour workday:  $12/day
24-hour running: $36/day
16 hours stopped (deallocated): Save $24/day = $480/month
```

## Related Commands

- [`azlin stop`](stop.md) - Stop or deallocate VM
- [`azlin status`](status.md) - Check VM power state
- [`azlin list`](list.md) - List all VMs with status
- [`azlin connect`](connect.md) - Connect after starting

## Source Code

- [vm_lifecycle_control.py](https://github.com/rysweet/azlin/blob/main/src/azlin/vm_lifecycle_control.py) - Start/stop logic
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All VM commands](index.md)
- [Cost Tracking](../../monitoring/cost.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
