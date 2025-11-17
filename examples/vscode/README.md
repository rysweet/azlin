# VS Code Remote Development Configuration Examples

This directory contains example configuration files for `azlin code` command.

## Setup

Copy these files to `~/.azlin/vscode/` to customize your VS Code remote development experience:

```bash
mkdir -p ~/.azlin/vscode
cp extensions.json ~/.azlin/vscode/
cp ports.json ~/.azlin/vscode/
cp settings.json ~/.azlin/vscode/
```

## Configuration Files

### extensions.json

List of VS Code extensions to automatically install on remote VMs.

Format:
```json
{
  "extensions": [
    "publisher.extension-name",
    ...
  ]
}
```

Find extension IDs:
1. Open VS Code
2. Go to Extensions panel (Cmd+Shift+X)
3. Click gear icon on any extension
4. Select "Copy Extension ID"

### ports.json

Port forwarding configuration for common development ports.

Format:
```json
{
  "forwards": [
    {"local": 3000, "remote": 3000},
    ...
  ]
}
```

Common ports:
- 3000: React/Node.js development server
- 8080: HTTP server
- 8000: Django/Flask
- 5432: PostgreSQL
- 6379: Redis
- 27017: MongoDB

### settings.json

VS Code workspace settings applied to remote workspace.

These settings override your local VS Code settings when working on remote VMs.

## Usage

After configuration:

```bash
# Launch VS Code for your VM
azlin code my-dev-vm

# Skip extension installation for faster launch
azlin code my-vm --no-extensions

# Open specific remote directory
azlin code my-vm --workspace /home/azureuser/projects
```

## Notes

- Configuration files are optional - sensible defaults are used if not present
- Extensions are installed once and cached by VS Code
- Port forwards are configured automatically by VS Code Remote-SSH
- Settings sync with your VS Code settings sync if enabled
