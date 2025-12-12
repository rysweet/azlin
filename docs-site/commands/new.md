# azlin new

Provision a new Azure VM with development tools.

SSH keys are automatically stored in Azure Key Vault for cross-system access.

Creates a new Ubuntu VM in Azure with all development tools pre-installed.
Optionally connects via SSH and clones a GitHub repository.


EXAMPLES:
    # Provision basic VM (uses size 'l' = 128GB RAM)
    $ azlin new

    # Provision with size tier (s=8GB, m=64GB, l=128GB, xl=256GB)
    $ azlin new --size m     # Medium: 64GB RAM
    $ azlin new --size s     # Small: 8GB RAM (original default)
    $ azlin new --size xl    # Extra-large: 256GB RAM

    # Provision with exact VM size (overrides --size)
    $ azlin new --vm-size Standard_E8as_v5

    # Provision with custom name
    $ azlin new --name my-dev-vm --size m

    # Provision and clone repository
    $ azlin new --repo https://github.com/owner/repo

    # Provision 5 VMs in parallel
    $ azlin new --pool 5 --size l

    # Provision from template
    $ azlin new --template dev-vm

    # Provision with NFS storage for shared home directory
    $ azlin new --nfs-storage myteam-shared --name worker-1

    # Provision and execute command
    $ azlin new --size xl -- python train.py


## Description

Provision a new Azure VM with development tools.
SSH keys are automatically stored in Azure Key Vault for cross-system access.
Creates a new Ubuntu VM in Azure with all development tools pre-installed.
Optionally connects via SSH and clones a GitHub repository.

EXAMPLES:
# Provision basic VM (uses size 'l' = 128GB RAM)
$ azlin new
# Provision with size tier (s=8GB, m=64GB, l=128GB, xl=256GB)
$ azlin new --size m     # Medium: 64GB RAM
$ azlin new --size s     # Small: 8GB RAM (original default)
$ azlin new --size xl    # Extra-large: 256GB RAM
# Provision with exact VM size (overrides --size)
$ azlin new --vm-size Standard_E8as_v5
# Provision with custom name
$ azlin new --name my-dev-vm --size m
# Provision and clone repository
$ azlin new --repo https://github.com/owner/repo
# Provision 5 VMs in parallel
$ azlin new --pool 5 --size l
# Provision from template
$ azlin new --template dev-vm
# Provision with NFS storage for shared home directory
$ azlin new --nfs-storage myteam-shared --name worker-1
# Provision and execute command
$ azlin new --size xl -- python train.py

## Usage

```bash
azlin new [OPTIONS]
```

## Options

- `--repo` TEXT (default: `Sentinel.UNSET`) - GitHub repository URL to clone
- `--size` CHOICE(s|m|l|xl) (default: `Sentinel.UNSET`) - VM size tier: s(mall), m(edium), l(arge), xl (default: l)
- `--vm-size` TEXT (default: `Sentinel.UNSET`) - Azure VM size (overrides --size)
- `--region` TEXT (default: `Sentinel.UNSET`) - Azure region
- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Azure resource group
- `--name` TEXT (default: `Sentinel.UNSET`) - Custom VM name
- `--pool` INT (default: `Sentinel.UNSET`) - Number of VMs to create in parallel
- `--no-auto-connect` - Do not auto-connect via SSH
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--template` TEXT (default: `Sentinel.UNSET`) - Template name to use for VM configuration
- `--nfs-storage` TEXT (default: `Sentinel.UNSET`) - NFS storage account name to mount as home directory
- `--no-nfs` - Skip NFS storage mounting (use local home directory only)
- `--no-bastion` - Skip bastion auto-detection and always create public IP
- `--bastion-name` TEXT (default: `Sentinel.UNSET`) - Explicit bastion host name to use for private VM
- `--yes`, `-y` - Accept all defaults and confirmations (non-interactive mode)
