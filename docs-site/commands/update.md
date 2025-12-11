# azlin update

Update all development tools on a VM.

Updates system packages, programming languages, CLIs, and other dev tools
that were installed during VM provisioning.

VM_IDENTIFIER can be:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)

Tools updated:
- System packages (apt)
- Azure CLI
- GitHub CLI
- npm and npm packages (Copilot, Codex, Claude Code)
- Rust toolchain
- astral-uv


Examples:
    # Update VM by name
    azlin update my-vm

    # Update VM by session name
    azlin update my-project

    # Update VM by IP
    azlin update 20.1.2.3

    # Update with custom timeout (default 300s per tool)
    azlin update my-vm --timeout 600

    # Update with explicit resource group
    azlin update my-vm --rg my-resource-group


## Description

Update all development tools on a VM.
Updates system packages, programming languages, CLIs, and other dev tools
that were installed during VM provisioning.
VM_IDENTIFIER can be:
- VM name (requires --resource-group or default config)
- Session name (will be resolved to VM name)
- IP address (direct connection)
Tools updated:
- System packages (apt)
- Azure CLI
- GitHub CLI
- npm and npm packages (Copilot, Codex, Claude Code)
- Rust toolchain
- astral-uv

Examples:
# Update VM by name
azlin update my-vm
# Update VM by session name
azlin update my-project
# Update VM by IP
azlin update 20.1.2.3
# Update with custom timeout (default 300s per tool)
azlin update my-vm --timeout 600
# Update with explicit resource group
azlin update my-vm --rg my-resource-group

## Usage

```bash
azlin update VM_IDENTIFIER [OPTIONS]
```

## Arguments

- `VM_IDENTIFIER` - No description available

## Options

- `--resource-group`, `--rg` TEXT (default: `Sentinel.UNSET`) - Resource group
- `--config` PATH (default: `Sentinel.UNSET`) - Config file path
- `--timeout` INT (default: `300`) - Timeout per update in seconds
