# azlin ip

IP diagnostics and network troubleshooting commands.

Commands to diagnose IP address classification and connectivity issues.


Examples:
    azlin ip check my-vm
    azlin ip check --all


## Description

IP diagnostics and network troubleshooting commands.
Commands to diagnose IP address classification and connectivity issues.

Examples:
azlin ip check my-vm
azlin ip check --all

## Usage

```bash
azlin ip
```

## Subcommands

### check

Check IP address classification and connectivity for VM(s).

Diagnoses IP classification (Public, Private, or Public-Azure) and tests
connectivity. Particularly useful for identifying Azure's public IP range
172.171.0.0/16 which appears private but is actually public.


Examples:
    azlin ip check my-vm                  # Check specific VM
    azlin ip check --all                  # Check all VMs
    azlin ip check my-vm --port 80        # Check different port
    azlin ip check 172.171.118.91         # Check by IP address directly


**Usage:**
```bash
azlin ip check VM_IDENTIFIER [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
- `--config` - Config file path
- `--all` - Check all VMs in resource group
- `--port` - Port to test connectivity (default: 22)
