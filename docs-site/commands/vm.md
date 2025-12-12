# azlin vm

Alias for 'new' command. Provision a new Azure VM.

## Description

Alias for 'new' command. Provision a new Azure VM.

## Usage

```bash
azlin vm [OPTIONS]
```

## Options

- `--repo` TEXT (default: `Sentinel.UNSET`) - GitHub repository URL to clone
- `--vm-size` TEXT (default: `Sentinel.UNSET`) - Azure VM size
- `--region` TEXT (default: `Sentinel.UNSET`) - Azure region
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Azure resource group
- `--name` TEXT (default: `Sentinel.UNSET`) - Custom VM name
- `--pool` INT (default: `Sentinel.UNSET`) - Number of VMs to create in parallel
- `--no-auto-connect` - Do not auto-connect via SSH
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--template` TEXT (default: `Sentinel.UNSET`) - Template name to use for VM configuration
- `--nfs-storage` TEXT (default: `Sentinel.UNSET`) - NFS storage account name to mount as home directory
- `--no-bastion` - Skip bastion auto-detection and always create public IP
- `--bastion-name` TEXT (default: `Sentinel.UNSET`) - Explicit bastion host name to use for private VM
