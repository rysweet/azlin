# azlin code

Launch VS Code with Remote-SSH for a VM.

## Synopsis

```bash
azlin code VM_IDENTIFIER [OPTIONS]
```

## Description

One-click VS Code launch that automatically:
- Configures SSH connection in `~/.ssh/config`
- Installs configured extensions from `~/.azlin/vscode/extensions.json`
- Sets up port forwarding from `~/.azlin/vscode/ports.json`
- Launches VS Code Remote-SSH

## Arguments

**VM_IDENTIFIER** - VM to connect to (required)

Can be:
- VM name (requires `--resource-group` or default config)
- Session name (resolved to VM name)
- IP address (direct connection)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Resource group (required for VM name) |
| `--config PATH` | Config file path |
| `--user TEXT` | SSH username (default: azureuser) |
| `--key PATH` | SSH private key path |
| `--no-extensions` | Skip extension installation (faster launch) |
| `--workspace TEXT` | Remote workspace path (default: /home/user) |
| `-h, --help` | Show help message |

## Examples

### Basic Usage

```bash
# Launch VS Code for VM
azlin code my-dev-vm

# Launch with explicit resource group
azlin code my-vm --rg my-resource-group
```

### By Session Name

```bash
# Connect using session name
azlin code my-project
```

Session names are resolved to VM names automatically.

### By IP Address

```bash
# Direct connection by IP
azlin code 20.1.2.3
```

### Custom Workspace

```bash
# Open specific remote directory
azlin code my-vm --workspace /home/azureuser/projects

# Open project folder
azlin code dev-vm --workspace ~/myapp
```

### Skip Extension Installation

```bash
# Faster launch without extensions
azlin code my-vm --no-extensions
```

### Custom SSH Configuration

```bash
# Custom SSH user
azlin code my-vm --user myuser

# Custom SSH key
azlin code my-vm --key ~/.ssh/custom_key

# Combined
azlin code my-vm --user deploy --key ~/.ssh/deploy_key
```

## Configuration

### Extension Auto-Install

Create `~/.azlin/vscode/extensions.json`:

```json
{
  "extensions": [
    "ms-python.python",
    "ms-azuretools.vscode-docker",
    "ms-vscode.Go",
    "rust-lang.rust-analyzer"
  ]
}
```

Extensions install automatically on first connection.

### Port Forwarding

Create `~/.azlin/vscode/ports.json`:

```json
{
  "forwards": [
    {"local": 3000, "remote": 3000},
    {"local": 8080, "remote": 80},
    {"local": 5432, "remote": 5432}
  ]
}
```

Ports forward automatically when VS Code connects.

### Workspace Settings

Create `~/.azlin/vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "editor.formatOnSave": true,
  "files.autoSave": "afterDelay"
}
```

Settings apply to remote workspace.

## Common Workflows

### Remote Development Setup

```bash
# 1. Create VM
azlin new --name dev-vm

# 2. Configure VS Code
mkdir -p ~/.azlin/vscode
cat > ~/.azlin/vscode/extensions.json <<EOF
{
  "extensions": ["ms-python.python", "ms-vscode.Go"]
}
EOF

# 3. Launch VS Code
azlin code dev-vm
```

### Team Collaboration

```bash
# Share VM with team
azlin keys export --output /tmp/azlin-key.pub

# Team member opens in VS Code
azlin code shared-dev-vm --key /path/to/shared-key
```

### Multiple Projects

```bash
# Frontend
azlin code frontend-vm --workspace ~/webapp

# Backend
azlin code backend-vm --workspace ~/api

# Database admin
azlin code db-vm --workspace ~/migrations
```

## Features

### Available in Remote Session

- IntelliSense and code completion
- Integrated terminal on remote VM
- Debugging with breakpoints
- Extensions run on remote VM
- Git operations
- File search and navigation
- Tasks and build commands

### VS Code Server

First connection installs VS Code Server on the VM:
- Initial connection: 30-60 seconds
- Subsequent connections: 5-10 seconds
- Automatic updates

## Troubleshooting

### Connection Failed

```bash
# Verify VM is running
azlin list

# Test SSH connection
azlin connect my-vm

# Check VS Code Remote-SSH extension
code --list-extensions | grep remote-ssh
```

### VS Code Server Issues

```bash
# Remove and reinstall VS Code Server
azlin connect my-vm
rm -rf ~/.vscode-server
exit

# Reconnect from VS Code
azlin code my-vm
```

### Extension Installation Fails

```bash
# Skip auto-install, install manually
azlin code my-vm --no-extensions

# Then install in VS Code
# Press Ctrl+Shift+P > "Extensions: Install Extensions"
```

### SSH Configuration Conflicts

```bash
# Check SSH config
cat ~/.ssh/config | grep -A 10 "Host.*azlin"

# Manual SSH test
ssh -i ~/.ssh/id_rsa_azlin azureuser@<vm-ip>
```

## Performance

| Operation | Time |
|-----------|------|
| Initial connection | 30-60s (VS Code Server install) |
| Subsequent connections | 5-10s |
| File operations | Near-local (network dependent) |
| Extension installation | 10-30s per extension |

## Related Commands

- [azlin connect](../vm/connect.md) - SSH to VM
- [azlin new](../vm/new.md) - Create development VM
- [azlin list](../vm/list.md) - List available VMs

## See Also

- [VS Code Remote-SSH Documentation](https://code.visualstudio.com/docs/remote/ssh)
- [Connecting](../../vm-lifecycle/connecting.md)
- [Advanced Features](../advanced/index.md)
