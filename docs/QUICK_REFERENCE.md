# azlin - Quick Reference Guide

**Version:** 2.0.0
**Last Updated:** 2025-10-27

---

## Installation

```bash
# Install azlin using uv (recommended)
uv tool install azlin

# Or install from GitHub
uv tool install git+https://github.com/rysweet/azlin

# Or use pip
pip install azlin
```

---

## Quick Start

### First Time Setup
```bash
# Provision VM with resource group (saves to config)
azlin --rg my-dev-rg

# Config automatically saved to ~/.azlin/config.toml
```

### Daily Usage
```bash
# Just run azlin - shows interactive menu
azlin

# Or list your VMs
azlin list

# Or provision a new VM
azlin --name my-vm
```

---

## Commands

### Main Command
```bash
azlin [OPTIONS]                    # Show help (or no args for help)
```

### Subcommands
```bash
azlin list [OPTIONS]               # List VMs in resource group
azlin w [OPTIONS]                  # Run 'w' command on all VMs
azlin ps [OPTIONS]                 # Run 'ps aux' on all VMs
azlin kill <vm-name> [OPTIONS]     # Delete a VM and all resources
azlin killall [OPTIONS]            # Delete all VMs in resource group
azlin --help                       # Show help
azlin <command> --help             # Command-specific help
```

---

## Common Options

### Resource Group
```bash
--resource-group my-rg             # Full form
--rg my-rg                         # Short form
```

### VM Configuration
```bash
--name my-vm                       # Custom VM name
--vm-size Standard_D4s_v3          # VM size
--region westus2                   # Azure region
```

### Advanced
```bash
--pool 5                           # Create 5 VMs in parallel
--config /path/to/config.toml      # Custom config file
--no-auto-connect                  # Don't auto-connect
```

### GitHub Integration
```bash
--repo https://github.com/user/repo  # Clone repository
```

---

## Feature Examples

### 1. Config Management

**First run - set default resource group:**
```bash
azlin --rg my-dev-rg
```

**Config saved at:** `~/.azlin/config.toml`
```toml
default_resource_group = "my-dev-rg"
default_region = "eastus"
default_vm_size = "Standard_D2s_v3"
```

**Future runs use saved config:**
```bash
azlin  # Uses my-dev-rg automatically
```

---

### 2. List VMs

**List all VMs:**
```bash
azlin list
```

**Output:**
```
Listing VMs in resource group: my-dev-rg

====================================================================================================
NAME                      STATUS    IP              REGION    SIZE              TMUX SESSIONS
====================================================================================================
azlin-20241009-120000     Running   1.2.3.4         eastus    Standard_D2s_v3   main, debug
azlin-20241008-180000     Stopped   N/A             westus2   Standard_B2s      (no sessions)
====================================================================================================

Total: 2 VMs
```

**Visual Styling**: Connected tmux sessions appear in **bold** text, disconnected sessions appear dim. This helps you quickly identify where your active work is located.

**Example**: If session "main" is connected (bold) and "debug" is disconnected (dim), you know someone is actively using the main session.

**List all including stopped:**
```bash
azlin list --all
```

**List specific resource group:**
```bash
azlin list --rg production-rg
```

---

### 3. Interactive Session Selection

**Run azlin with no args:**
```bash
azlin
```

**No VMs - prompt to create:**
```
No VMs found. Create a new one? [Y/n]:
```

**One VM - auto-connect:**
```
Found 1 VM: azlin-vm-123
Status: Running
IP: 1.2.3.4

Connecting...
```

**Multiple VMs - show menu:**
```
============================================================
Available VMs:
============================================================
  1. azlin-vm-123 - Running - 1.2.3.4
  2. azlin-vm-456 - Running - 5.6.7.8
  3. azlin-vm-789 - Running - 9.10.11.12
  n. Create new VM
============================================================

Select VM (number or 'n' for new):
```

---

### 4. Custom VM Names

**Custom name:**
```bash
azlin --name my-dev-vm
```

**Auto-generated (default):**
```bash
azlin
# Creates: azlin-20241009-120000
```

**With command (extracts slug):**
```bash
azlin -- python train.py
# Creates: azlin-20241009-120000-python-train
```

---

### 5. Run 'w' Command

**Run on all VMs:**
```bash
azlin w
```

**Output:**
```
Running 'w' on 2 VMs...

============================================================
VM: 1.2.3.4
============================================================
 12:00:00 up 2 days,  3:45,  1 user,  load average: 0.08, 0.05, 0.01
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   10.0.0.1        11:30    0.00s  0.04s  0.00s w

============================================================
VM: 5.6.7.8
============================================================
 12:00:01 up 5 days, 10:20,  2 users,  load average: 1.23, 1.15, 0.98
USER     TTY      FROM             LOGIN@   IDLE   JCPU   PCPU WHAT
azureuser pts/0   10.0.0.2        08:15   15:30   0.10s  0.05s tmux
```

**Specific resource group:**
```bash
azlin w --rg production-rg
```

---

### 6. Pool Provisioning

**Create 3 VMs in parallel:**
```bash
azlin --pool 3
```

**Pool with custom configuration:**
```bash
azlin --pool 5 --vm-size Standard_D4s_v3 --rg batch-jobs
```

**Warning for large pools (>10):**
```
WARNING: Creating 11 VMs
Estimated cost: ~$1.10/hour
Continue? [y/N]:
```

---

### 7. Remote Command Execution

**Execute command on new VM:**
```bash
azlin -- python train.py
```

**What happens:**
1. Provisions new VM
2. Waits for VM ready
3. Opens new terminal window
4. Executes command via SSH

**Complex command:**
```bash
azlin -- 'cd /tmp && git clone https://github.com/user/repo && make test'
```

**Falls back to inline if terminal launch fails**

---

### 8. Process Monitoring (NEW)

**Run ps aux on all VMs:**
```bash
azlin ps
```

**Output (prefixed format):**
```
Running 'ps aux' on 2 VMs...

[azlin-vm-001] USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
[azlin-vm-001] root         1  0.0  0.1 168820 13312 ?        Ss   Oct08   0:00 /sbin/init
[azlin-vm-001] user      5678  2.1  5.4 987654 54321 ?        Sl   09:30   1:23 python train.py
[azlin-vm-002] USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
[azlin-vm-002] root         1  0.0  0.1 168820 13312 ?        Ss   Oct08   0:00 /sbin/init
```

**Grouped output:**
```bash
azlin ps --grouped
```

**Output:**
```
================================================================================
VM: azlin-vm-001
================================================================================
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.1 168820 13312 ?        Ss   Oct08   0:00 /sbin/init
user      5678  2.1  5.4 987654 54321 ?        Sl   09:30   1:23 python train.py

================================================================================
VM: azlin-vm-002
================================================================================
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
root         1  0.0  0.1 168820 13312 ?        Ss   Oct08   0:00 /sbin/init
```

**Note:** SSH processes are automatically filtered out

---

### 9. VM Deletion (NEW)

**Delete single VM:**
```bash
azlin kill azlin-vm-12345
```

**With confirmation prompt:**
```
VM Details:
  Name:           azlin-vm-12345
  Resource Group: azlin-rg-default
  Status:         Running
  IP:             20.123.45.67
  Size:           Standard_D2s_v3

This will delete the VM and all associated resources (NICs, disks, IPs).
This action cannot be undone.

Are you sure you want to delete this VM? [y/N]:
```

**Skip confirmation:**
```bash
azlin kill my-vm --force
```

**Delete all VMs in resource group:**
```bash
azlin killall
```

**With confirmation:**
```
Found 3 VM(s) in resource group 'azlin-rg-default':
================================================================================
  azlin-vm-001                        Running         20.123.45.67
  azlin-vm-002                        Running         20.123.45.68
  azlin-vm-003                        Stopped         N/A
================================================================================

This will delete all 3 VM(s) and their associated resources.
This action cannot be undone.

Are you sure you want to delete 3 VM(s)? [y/N]:
```

**Delete specific prefix:**
```bash
azlin killall --prefix test-vm
```

**Delete without confirmation (DANGEROUS):**
```bash
azlin killall --force
```

---

### 10. Help Commands

**Main help:**
```bash
azlin --help
```

**Command-specific help:**
```bash
azlin list --help
azlin w --help
```

**Version:**
```bash
azlin --version
```

---

## Configuration File

**Location:** `~/.azlin/config.toml`
**Permissions:** 0600 (owner read/write only)

**Format:**
```toml
default_resource_group = "my-rg"
default_region = "eastus"
default_vm_size = "Standard_D2s_v3"
last_vm_name = "azlin-20241009-120000"
```

**Manual editing:**
```bash
# Edit config
nano ~/.azlin/config.toml

# View config
cat ~/.azlin/config.toml
```

---

## Complete Workflows

### Workflow 1: Quick Development VM
```bash
# One command - uses saved config
azlin
```

### Workflow 2: Named Project VM
```bash
# Create named VM with repo
azlin --name project-alpha --repo https://github.com/user/project
```

### Workflow 3: Batch Processing
```bash
# Create pool for batch job
azlin --pool 10 --rg batch-processing

# Check on all VMs
azlin w --rg batch-processing

# Monitor processes
azlin ps --rg batch-processing

# List VMs
azlin list --rg batch-processing

# Clean up when done
azlin killall --rg batch-processing
```

### Workflow 4: Training Job
```bash
# Provision and run training
azlin --vm-size Standard_NC6 -- python train.py --epochs 100

# Opens in new terminal, shows output
```

### Workflow 5: Multiple Resource Groups
```bash
# Development
azlin --rg dev-rg --name dev-vm

# Production
azlin --rg prod-rg --name prod-vm

# List each
azlin list --rg dev-rg
azlin list --rg prod-rg
```

---

## Tips & Tricks

### Tip 1: Default Resource Group
Set once, use everywhere:
```bash
azlin --rg my-team-rg  # Sets default
azlin                   # Uses my-team-rg
azlin list              # Uses my-team-rg
azlin w                 # Uses my-team-rg
```

### Tip 2: Interactive Menu
Run `azlin` with no args for quick access to existing VMs.

### Tip 3: Parallel Execution
Use `--pool` for multiple VMs:
```bash
azlin --pool 5  # 5x faster than sequential
```

### Tip 4: Command Execution
Execute commands in new terminal:
```bash
azlin -- long-running-job
# Terminal stays open, you can continue working
```

### Tip 5: VM Naming
Use meaningful names:
```bash
azlin --name ml-training-$(date +%Y%m%d)
```

---

## Common Issues & Solutions

### Issue: "No resource group specified"
**Solution:** Set default or use --rg flag
```bash
azlin --rg my-rg
```

### Issue: "No VMs found"
**Solution:** Check resource group
```bash
azlin list --rg <different-rg>
```

### Issue: Terminal launch fails
**Solution:** Command executes inline (automatic fallback)

### Issue: Config file has wrong permissions
**Solution:** Automatically fixed on next use

### Issue: Pool provisioning slow
**Solution:** Normal - Azure takes time. Use fewer VMs or wait.

---

## Azure CLI Commands (for reference)

### Manual VM Operations
```bash
# Stop VM (saves costs)
az vm stop --name <vm-name> --resource-group <rg>

# Start VM
az vm start --name <vm-name> --resource-group <rg>

# Delete VM
az vm delete --name <vm-name> --resource-group <rg> --yes

# Delete entire resource group
az group delete --name <rg> --yes
```

### List Resources
```bash
# List all VMs
az vm list --output table

# List resource groups
az group list --output table
```

---

## File Locations

**Config:** `~/.azlin/config.toml`
**SSH Keys:** `~/.ssh/azlin-key` and `~/.ssh/azlin-key.pub`
**Dotfiles:** `~/.azlin/home/`
**Templates:** `~/.azlin/templates/`
**Auth Profiles:** `~/.azlin/auth/`

---

## Getting Help

**CLI Help:**
```bash
azlin --help
azlin <command> --help
```

**Documentation:**
- `V2_FEATURES.md` - Feature documentation
- `FUTURE_FEATURES.md` - Upcoming features
- `IMPLEMENTATION_COMPLETE.md` - Technical details

**Example Files:**
- All examples in this guide are working examples
- Test with `--help` flags first

---

## Version Information

**Current Version:** 2.0.0
**Last Updated:** 2025-10-27
**Status:** Production Ready

**Key Features:**
- Natural language commands with AI
- Config storage and defaults
- VM listing and filtering
- Interactive selection
- Custom VM names
- Remote command execution
- Pool provisioning
- Process monitoring
- VM deletion and cleanup
- Shared NFS storage
- Snapshot management
- Authentication profiles
- SSH key management
- VM templates

---

## Performance Reference

| Operation | Typical Time |
|-----------|--------------|
| `azlin list` | 2-3 seconds |
| `azlin status` | 3-5 seconds |
| `azlin cost` | 5-10 seconds |
| `azlin new` | 4-7 minutes |
| `azlin clone` | 10-15 minutes |
| `azlin update` | 2-5 minutes |
| `azlin sync` | 30s - 5 minutes |
| `azlin do` | +2s parsing overhead |

**Optimization Tips:**
- Use native commands for frequent operations
- `azlin do` adds 2-3 seconds parsing time
- Batch operations run in parallel
- Pool provisioning parallelized (4-7 min regardless of size)
