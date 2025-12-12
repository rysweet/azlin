# azlin check

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


## Description

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

## Usage

```bash
azlin check [VM_IDENTIFIER] [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available (optional)

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--all` - Check all VMs in resource group
- `--port` INT (default: `22`) - Port to test connectivity (default: 22)
