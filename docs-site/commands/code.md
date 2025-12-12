# azlin code

Launch VS Code with Remote-SSH for a VM.

One-click VS Code launch that automatically:
- Configures SSH connection in ~/.ssh/config
- Installs configured extensions from ~/.azlin/vscode/extensions.json
- Sets up port forwarding from ~/.azlin/vscode/ports.json
- Launches VS Code Remote-SSH

VM_IDENTIFIER can be:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)

Configuration:
Create ~/.azlin/vscode/ directory with optional files:
- extensions.json: {"extensions": ["ms-python.python", ...]}
- ports.json: {"forwards": [{"local": 3000, "remote": 3000}, ...]}
- settings.json: VS Code workspace settings


Examples:
    # Launch VS Code for VM
    azlin code my-dev-vm

    # Launch with explicit resource group
    azlin code my-vm --rg my-resource-group

    # Launch by session name
    azlin code my-project

    # Launch by IP address
    azlin code 20.1.2.3

    # Skip extension installation (faster)
    azlin code my-vm --no-extensions

    # Open specific remote directory
    azlin code my-vm --workspace /home/azureuser/projects

    # Custom SSH user
    azlin code my-vm --user myuser

    # Custom SSH key
    azlin code my-vm --key ~/.ssh/custom_key


## Description

Launch VS Code with Remote-SSH for a VM.
One-click VS Code launch that automatically:
- Configures SSH connection in ~/.ssh/config
- Installs configured extensions from ~/.azlin/vscode/extensions.json
- Sets up port forwarding from ~/.azlin/vscode/ports.json
- Launches VS Code Remote-SSH
VM_IDENTIFIER can be:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)
Configuration:
Create ~/.azlin/vscode/ directory with optional files:
- extensions.json: {"extensions": ["ms-python.python", ...]}
- ports.json: {"forwards": [{"local": 3000, "remote": 3000}, ...]}
- settings.json: VS Code workspace settings

Examples:
# Launch VS Code for VM
azlin code my-dev-vm
# Launch with explicit resource group
azlin code my-vm --rg my-resource-group
# Launch by session name
azlin code my-project
# Launch by IP address
azlin code 20.1.2.3
# Skip extension installation (faster)
azlin code my-vm --no-extensions
# Open specific remote directory
azlin code my-vm --workspace /home/azureuser/projects
# Custom SSH user
azlin code my-vm --user myuser
# Custom SSH key
azlin code my-vm --key ~/.ssh/custom_key

## Usage

```bash
azlin code VM_IDENTIFIER [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group (required for VM name)
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--user` TEXT (default: `azureuser`) - SSH username (default: azureuser)
- `--key` PATH (default: `Sentinel.UNSET`) - SSH private key path
- `--no-extensions` - Skip extension installation (faster launch)
- `--workspace` TEXT (default: `Sentinel.UNSET`) - Remote workspace path (default: /home/user)
