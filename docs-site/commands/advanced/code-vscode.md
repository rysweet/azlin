# azlin code (VS Code Integration)

Seamless VS Code Remote-SSH integration with azlin VMs.

## Description

Connect VS Code to azlin VMs using Remote-SSH extension. Edit code directly on VMs, use remote terminals, debug remotely, and maintain consistent development environments.

## Usage

```bash
azlin code VM_NAME [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--folder PATH` | Open specific folder on remote VM |
| `--wait` | Wait for window to close |
| `--new-window` | Open in new VS Code window |
| `-h, --help` | Show help message |

## Examples

### Open VM in VS Code

```bash
# Open VM in VS Code
azlin code my-dev-vm
```

**What happens:**
1. VS Code launches
2. Remote-SSH connects to VM
3. VS Code Server installs on VM (first time)
4. Opens remote workspace

### Open Specific Folder

```bash
# Open project folder directly
azlin code my-vm --folder ~/projects/myapp
```

### Multiple VS Code Windows

```bash
# Open different VMs in separate windows
azlin code vm1 --new-window --folder ~/frontend
azlin code vm2 --new-window --folder ~/backend
azlin code vm3 --new-window --folder ~/database
```

## Prerequisites

Install VS Code and Remote-SSH extension:

```bash
# macOS
brew install --cask visual-studio-code

# Install Remote-SSH extension
code --install-extension ms-vscode-remote.remote-ssh
```

## Common Workflows

### Remote Development Setup

```bash
# 1. Create development VM
azlin new --name dev-vm --vm-size Standard_D4s_v3

# 2. Clone repository
azlin connect dev-vm
git clone https://github.com/owner/project.git
exit

# 3. Open in VS Code
azlin code dev-vm --folder ~/project
```

### Multi-Project Development

```bash
# Frontend in one VM
azlin code frontend-vm --folder ~/webapp

# Backend in another VM
azlin code backend-vm --folder ~/api

# Database admin in third VM
azlin code db-vm --folder ~/migrations
```

### Team Pair Programming

```bash
# Share VM with team member
azlin keys export --output /tmp/azlin-key.pub
# Send key to team member

# Team member connects
azlin connect shared-dev-vm

# Or opens in VS Code
azlin code shared-dev-vm
```

## Features

### Available in Remote Session

- ✓ IntelliSense and code completion
- ✓ Integrated terminal on remote VM
- ✓ Debugging with breakpoints
- ✓ Extensions run on remote VM
- ✓ Git operations
- ✓ File search and navigation
- ✓ Tasks and build commands

### Extensions

Install extensions on remote VM:

```bash
# Extensions install automatically when needed
# Or pre-install:
azlin connect dev-vm
code --install-extension ms-python.python
code --install-extension ms-azuretools.vscode-docker
```

## Troubleshooting

### Connection Failed

```bash
# Verify VM is running
azlin list

# Test SSH connection
azlin connect my-vm --no-tmux

# Check VS Code Remote-SSH
code --list-extensions | grep remote-ssh
```

### VS Code Server Installation Issues

```bash
# SSH into VM and reinstall
azlin connect my-vm
rm -rf ~/.vscode-server
# Try connecting again from VS Code
```

## Configuration

Add to `~/.ssh/config` for custom settings:

```
Host azlin-*
  User azureuser
  IdentityFile ~/.ssh/id_rsa_azlin
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
```

## Performance

| Operation | Time |
|-----------|------|
| Initial connection | 30-60s (VS Code Server install) |
| Subsequent connections | 5-10s |
| File operations | Near-local (depends on network) |

## Related Commands

- [`azlin connect`](../vm/connect.md) - SSH to VM
- [`azlin new`](../vm/new.md) - Create development VM
- [`azlin list`](../vm/list.md) - List available VMs

## See Also

- [VS Code Remote-SSH Documentation](https://code.visualstudio.com/docs/remote/ssh)
- [Connecting](../../vm-lifecycle/connecting.md)
