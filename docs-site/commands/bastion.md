# azlin bastion

Manage Azure Bastion hosts for secure VM connections.

Azure Bastion provides secure RDP/SSH connectivity to VMs
without exposing public IPs. These commands help you list,
configure, and use Bastion hosts with azlin.


COMMANDS:
    list         List Bastion hosts
    status       Show Bastion host status
    configure    Configure Bastion for a VM


EXAMPLES:
    # List all Bastion hosts
    $ azlin bastion list

    # List Bastion hosts in a resource group
    $ azlin bastion list --resource-group my-rg

    # Check status of a specific Bastion
    $ azlin bastion status my-bastion --resource-group my-rg

    # Configure VM to use Bastion
    $ azlin bastion configure my-vm --bastion-name my-bastion --resource-group my-rg


## Description

Manage Azure Bastion hosts for secure VM connections.
Azure Bastion provides secure RDP/SSH connectivity to VMs
without exposing public IPs. These commands help you list,
configure, and use Bastion hosts with azlin.

COMMANDS:
list         List Bastion hosts
status       Show Bastion host status
configure    Configure Bastion for a VM

EXAMPLES:
# List all Bastion hosts
$ azlin bastion list
# List Bastion hosts in a resource group
$ azlin bastion list --resource-group my-rg
# Check status of a specific Bastion
$ azlin bastion status my-bastion --resource-group my-rg
# Configure VM to use Bastion
$ azlin bastion configure my-vm --bastion-name my-bastion --resource-group my-rg

## Usage

```bash
azlin bastion
```

## Subcommands

### configure

Configure Bastion connection for a VM.

Creates a mapping between a VM and a Bastion host, so azlin
will automatically use the Bastion when connecting to the VM.


Arguments:
  VM_NAME    VM name to configure


Examples:
  $ azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg
  $ azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --bastion-rg bastion-rg
  $ azlin bastion configure my-vm --bastion-name my-bastion --rg my-rg --disable


**Usage:**
```bash
azlin bastion configure VM_NAME [OPTIONS]
```

**Options:**
- `--bastion-name` - Bastion host name
- `--resource-group`, `--rg` - VM resource group
- `--bastion-resource-group`, `--bastion-rg` - Bastion resource group (defaults to VM RG)
- `--enable` - Enable or disable mapping

### list

List Azure Bastion hosts.

Lists all Bastion hosts in your subscription, optionally
filtered by resource group.


Examples:
  $ azlin bastion list
  $ azlin bastion list --resource-group my-rg


**Usage:**
```bash
azlin bastion list [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Filter by resource group

### status

Show status of a Bastion host.


Arguments:
  NAME    Bastion host name


Examples:
  $ azlin bastion status my-bastion --resource-group my-rg


**Usage:**
```bash
azlin bastion status NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Resource group
