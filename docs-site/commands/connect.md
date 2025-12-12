# azlin connect

Connect to existing VM via SSH.

If VM_IDENTIFIER is not provided, displays an interactive list of available
VMs to choose from, or option to create a new VM.

VM_IDENTIFIER can be either:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)

Use -- to separate remote command from options.

By default, auto-reconnect is ENABLED. If your SSH session disconnects,
you will be prompted to reconnect. Use --no-reconnect to disable this.


Examples:
    # Interactive selection
    azlin connect

    # Connect to VM by name
    azlin connect my-vm

    # Connect to VM by session name
    azlin connect my-project

    # Connect to VM by name with explicit resource group
    azlin connect my-vm --rg my-resource-group

    # Connect by IP address
    azlin connect 20.1.2.3

    # Connect without tmux
    azlin connect my-vm --no-tmux

    # Connect with custom tmux session name
    azlin connect my-vm --tmux-session dev

    # Connect and run command
    azlin connect my-vm -- ls -la

    # Connect with custom SSH user
    azlin connect my-vm --user myuser

    # Connect with custom SSH key
    azlin connect my-vm --key ~/.ssh/custom_key

    # Disable auto-reconnect
    azlin connect my-vm --no-reconnect

    # Set maximum reconnection attempts
    azlin connect my-vm --max-retries 5


## Description

Connect to existing VM via SSH.
If VM_IDENTIFIER is not provided, displays an interactive list of available
VMs to choose from, or option to create a new VM.
VM_IDENTIFIER can be either:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)
Use -- to separate remote command from options.
By default, auto-reconnect is ENABLED. If your SSH session disconnects,
you will be prompted to reconnect. Use --no-reconnect to disable this.

Examples:
# Interactive selection
azlin connect
# Connect to VM by name
azlin connect my-vm
# Connect to VM by session name
azlin connect my-project
# Connect to VM by name with explicit resource group
azlin connect my-vm --rg my-resource-group
# Connect by IP address
azlin connect 20.1.2.3
# Connect without tmux
azlin connect my-vm --no-tmux
# Connect with custom tmux session name
azlin connect my-vm --tmux-session dev
# Connect and run command
azlin connect my-vm -- ls -la
# Connect with custom SSH user
azlin connect my-vm --user myuser
# Connect with custom SSH key
azlin connect my-vm --key ~/.ssh/custom_key
# Disable auto-reconnect
azlin connect my-vm --no-reconnect
# Set maximum reconnection attempts
azlin connect my-vm --max-retries 5

## Usage

```bash
azlin connect [VM_IDENTIFIER] [REMOTE_COMMAND] [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available (optional)
- `REMOTE_COMMAND` - No description available (optional)

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group (required for VM name)
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--no-tmux` - Skip tmux session
- `--tmux-session` TEXT (default: `Sentinel.UNSET`) - Tmux session name (default: azlin)
- `--user` TEXT (default: `azureuser`) - SSH username (default: azureuser)
- `--key` PATH (default: `Sentinel.UNSET`) - SSH private key path
- `--no-reconnect` - Disable auto-reconnect on disconnect
- `--max-retries` INT (default: `3`) - Maximum reconnection attempts (default: 3)
- `--yes`, `-y` - Skip all confirmation prompts (e.g., Bastion)
