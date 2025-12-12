# azlin tag

Manage Azure VM tags.

Add, remove, and list tags on Azure VMs. Tags help organize
and categorize VMs for easier management and cost tracking.


COMMANDS:
    add        Add tags to a VM
    remove     Remove tags from a VM
    list       List VM tags


EXAMPLES:
    # Add single tag
    $ azlin tag add my-vm environment=production

    # Add multiple tags
    $ azlin tag add my-vm project=web team=backend

    # List VM tags
    $ azlin tag list my-vm

    # Remove tags
    $ azlin tag remove my-vm environment project


## Description

Manage Azure VM tags.
Add, remove, and list tags on Azure VMs. Tags help organize
and categorize VMs for easier management and cost tracking.

COMMANDS:
add        Add tags to a VM
remove     Remove tags from a VM
list       List VM tags

EXAMPLES:
# Add single tag
$ azlin tag add my-vm environment=production
# Add multiple tags
$ azlin tag add my-vm project=web team=backend
# List VM tags
$ azlin tag list my-vm
# Remove tags
$ azlin tag remove my-vm environment project

## Usage

```bash
azlin tag
```

## Subcommands

### add

Add tags to a VM.

Adds one or more tags to the specified VM. Tags must be in
key=value format.


VM_NAME is the name of the VM to tag.
TAGS are one or more key=value pairs to add.


Tag format:
  - Keys: alphanumeric, underscore, hyphen, period
  - Values: any characters including spaces (quote if needed)


Examples:
  $ azlin tag add my-vm environment=production
  $ azlin tag add my-vm project=web team=backend cost-center=eng
  $ azlin tag add my-vm description="Web server for API"


**Usage:**
```bash
azlin tag add VM_NAME TAGS [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group

### list

List all tags on a VM.

Shows all tags currently set on the specified VM with their
key-value pairs.


VM_NAME is the name of the VM.


Examples:
  $ azlin tag list my-vm
  $ azlin tag list my-vm --resource-group azlin-rg


**Usage:**
```bash
azlin tag list VM_NAME [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group

### remove

Remove tags from a VM.

Removes one or more tags from the specified VM by tag key.


VM_NAME is the name of the VM.
TAG_KEYS are one or more tag keys to remove.


Examples:
  $ azlin tag remove my-vm environment
  $ azlin tag remove my-vm project team cost-center


**Usage:**
```bash
azlin tag remove VM_NAME TAG_KEYS [OPTIONS]
```

**Options:**
- `--resource-group`, `--rg` - Azure resource group
