# azlin top

Run distributed top command on all VMs.

Shows real-time CPU, memory, load, and top processes across all VMs
in a unified dashboard that updates every N seconds.


Examples:
    azlin top                    # Default: 10s refresh
    azlin top -i 5               # 5 second refresh
    azlin top --rg my-rg         # Specific resource group
    azlin top -i 15 -t 10        # 15s refresh, 10s timeout


Press Ctrl+C to exit the dashboard.


## Description

Run distributed top command on all VMs.
Shows real-time CPU, memory, load, and top processes across all VMs
in a unified dashboard that updates every N seconds.

Examples:
azlin top                    # Default: 10s refresh
azlin top -i 5               # 5 second refresh
azlin top --rg my-rg         # Specific resource group
azlin top -i 15 -t 10        # 15s refresh, 10s timeout

Press Ctrl+C to exit the dashboard.

## Usage

```bash
azlin top [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--interval`, `-i` INT (default: `10`) - Refresh interval in seconds (default 10)
- `--timeout`, `-t` INT (default: `5`) - SSH timeout per VM in seconds (default 5)
