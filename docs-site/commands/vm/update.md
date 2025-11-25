# azlin update

**Update development tools on a VM**

## Description

The `azlin update` command updates all development tools and programming languages that were installed during VM provisioning. This includes Node.js packages, Rust toolchain, Python tools, Docker, Azure CLI, GitHub CLI, and AI CLI assistants.

Note: This updates development tools, NOT operating system packages. For OS updates, use [`azlin os-update`](../util/os-update.md).

## Usage

```bash
azlin update [OPTIONS] VM_IDENTIFIER
```

## Arguments

| Argument | Description |
|----------|-------------|
| `VM_IDENTIFIER` | VM name, session name, or IP address (required) |

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Azure resource group |
| `--config PATH` | Path | Config file path |
| `--timeout INTEGER` | Seconds | Timeout per update in seconds (default: 300) |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Update by VM Name

```bash
azlin update my-vm
```

### Update by Session Name

```bash
azlin update my-project
```

### Update by IP Address

```bash
azlin update 20.1.2.3
```

### Update with Custom Timeout

```bash
# Allow 10 minutes per tool update
azlin update my-vm --timeout 600
```

### Update with Explicit Resource Group

```bash
azlin update my-vm --rg my-resource-group
```

## What Gets Updated

- **Node.js**: npm packages, global npm tools
- **Python**: pip, uv, astral-uv
- **Rust**: rustc, cargo (via rustup)
- **Go**: go toolchain
- **.NET**: dotnet SDK and runtime
- **Docker**: docker engine and CLI
- **GitHub CLI**: gh command
- **Azure CLI**: az command
- **AI Tools**: GitHub Copilot CLI, OpenAI Codex CLI, Claude Code CLI

## Troubleshooting

### Update Timeout

**Symptoms:** Update times out

**Solutions:**
```bash
# Increase timeout
azlin update my-vm --timeout 900

# Or update manually via SSH
azlin connect my-vm
npm update -g
rustup update
pip install --upgrade pip uv
```

### Specific Tool Fails

**Symptoms:** One tool fails to update

**Solutions:**
```bash
# SSH to VM and update manually
azlin connect my-vm

# Update specific tools
npm update -g  # Node.js
rustup update  # Rust
pip install --upgrade pip uv  # Python
```

## Related Commands

- [`azlin os-update`](../util/os-update.md) - Update OS packages
- [`azlin connect`](connect.md) - SSH to VM
- [`azlin new`](new.md) - Provision VM with latest tools

## Source Code

- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - Command definition

## See Also

- [All VM commands](index.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
