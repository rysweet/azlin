# Start and Stop VMs

Control VM power state to manage costs and resources.

## Quick Start

```bash
# Stop VM (deallocate to save costs)
azlin stop my-vm

# Start VM
azlin start my-vm

# Check status
azlin status --vm my-vm
```

## Overview

azlin provides simple power management for Azure VMs:

- **`azlin stop`** - Stop and deallocate VM (stops compute billing)
- **`azlin start`** - Start a stopped/deallocated VM
- **`azlin status`** - Check current VM power state

## Stop Command

```bash
azlin stop [OPTIONS] VM_NAME
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `VM_NAME` | Name of VM to stop | Required |
| `--resource-group, --rg TEXT` | Resource group | From config |
| `--deallocate / --no-deallocate` | Deallocate resources | `--deallocate` |

### Examples

```bash
# Stop and deallocate VM (default - saves money)
azlin stop my-vm

# Stop without deallocation (maintains IP, still charges)
azlin stop my-vm --no-deallocate

# Stop VM in specific resource group
azlin stop my-vm --rg production-rg
```

### What Happens

**With `--deallocate` (default):**
1. VM shuts down gracefully
2. Compute resources released
3. **Compute billing stops**
4. Storage still charged (disks remain)
5. Public IP may change on restart

**With `--no-deallocate`:**
1. VM shuts down
2. Compute resources reserved
3. **Compute billing continues**
4. Public IP remains the same
5. Faster restart time

!!! tip "Cost Savings"
    Always use `--deallocate` (default) to stop compute charges. Only use `--no-deallocate` if you need to preserve the exact IP address.

## Start Command

```bash
azlin start [OPTIONS] VM_NAME
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `VM_NAME` | Name of VM to start | Required |
| `--resource-group, --rg TEXT` | Resource group | From config |

### Examples

```bash
# Start VM
azlin start my-vm

# Start VM in specific resource group
azlin start my-vm --rg production-rg
```

### What Happens

1. Allocates compute resources
2. Starts VM from stopped state
3. Resumes from where it left off
4. May get new public IP (if deallocated)
5. Typically takes 2-3 minutes

## Status Command

```bash
azlin status [OPTIONS]
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--resource-group, --rg TEXT` | Resource group | From config |
| `--vm TEXT` | Specific VM to check | All VMs |

### Examples

```bash
# Status of all VMs
azlin status

# Status of specific VM
azlin status --vm my-vm

# Status in specific resource group
azlin status --rg production-rg
```

### Output

```
╭──────────────────┬─────────────────┬────────────────╮
│ VM Name          │ Power State     │ IP Address     │
├──────────────────┼─────────────────┼────────────────┤
│ azlin-vm-12345   │ Running         │ 20.51.23.145   │
│ dev-vm           │ Stopped         │ -              │
│ ml-training      │ Deallocated     │ -              │
╰──────────────────┴─────────────────┴────────────────╯
```

## Common Workflows

### Cost Management

```bash
# Stop VMs at end of work day
azlin stop dev-vm-1
azlin stop dev-vm-2
azlin stop dev-vm-3

# Start in the morning
azlin start dev-vm-1
azlin start dev-vm-2
azlin start dev-vm-3
```

**Savings:** Assuming 16 hours/day stopped * 5 days/week = ~48% cost reduction

### Batch Operations

```bash
# Stop multiple VMs
for vm in $(azlin list --tag env=dev --no-quota --no-tmux | tail -n +2 | awk '{print $1}'); do
  azlin stop $vm
done

# Start multiple VMs
for vm in worker-{1..5}; do
  azlin start $vm
done
```

### Check Before Stopping

```bash
# Verify VM is running
azlin status --vm my-vm

# Stop if running
azlin stop my-vm

# Confirm stopped
azlin status --vm my-vm
```

### Quick Restart

```bash
# Stop and immediately restart
azlin stop my-vm && azlin start my-vm
```

## Power States Explained

| State | Billing | Description |
|-------|---------|-------------|
| **Running** | Compute + Storage | VM is powered on and operational |
| **Stopped** | Compute + Storage | VM shutdown but resources reserved |
| **Deallocated** | Storage only | VM shutdown, compute released |
| **Starting** | Compute + Storage | VM is booting up |
| **Stopping** | Compute + Storage | VM is shutting down |

## Troubleshooting

### VM Won't Start

```bash
# Check quota
azlin quota

# Check VM status
azlin status --vm my-vm

# Try different region
azlin new --region westus
```

### VM Won't Stop

```bash
# Check VM status
azlin status --vm my-vm

# Force stop via Azure CLI
az vm stop -g <rg> -n <vm> --skip-shutdown

# Deallocate if stuck
az vm deallocate -g <rg> -n <vm>
```

### IP Address Changed

```bash
# Use static IP (requires Azure configuration)
az network public-ip update -g <rg> -n <vm-ip> --allocation-method Static

# Or use session names instead of IPs
azlin session my-vm my-project
azlin connect my-project  # Works regardless of IP
```

## Related Commands

- [`azlin list`](listing.md) - View VM status
- [`azlin new`](creating.md) - Create new VM
- [`azlin connect`](connecting.md) - Connect to running VM
- [`azlin delete`](deleting.md) - Permanently delete VM

## Source Code

- [Start Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L600)
- [Stop Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L620)
- [Status Command](https://github.com/rysweet/azlin/blob/main/azlin/cli.py#L640)

---

*Last updated: 2025-11-24*
