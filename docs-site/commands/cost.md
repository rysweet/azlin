# azlin cost

Show cost estimates for VMs.

Displays cost estimates based on VM size and uptime.
Costs are approximate based on Azure pay-as-you-go pricing.


Examples:
    azlin cost
    azlin cost --by-vm
    azlin cost --from 2025-01-01 --to 2025-01-31
    azlin cost --estimate
    azlin cost --rg my-resource-group --by-vm


## Description

Show cost estimates for VMs.
Displays cost estimates based on VM size and uptime.
Costs are approximate based on Azure pay-as-you-go pricing.

Examples:
azlin cost
azlin cost --by-vm
azlin cost --from 2025-01-01 --to 2025-01-31
azlin cost --estimate
azlin cost --rg my-resource-group --by-vm

## Usage

```bash
azlin cost [OPTIONS]
```

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--by-vm` - Show per-VM breakdown
- `--from` TEXT (default: `Sentinel.UNSET`) - Start date (YYYY-MM-DD)
- `--to` TEXT (default: `Sentinel.UNSET`) - End date (YYYY-MM-DD)
- `--estimate` - Show monthly cost estimate
