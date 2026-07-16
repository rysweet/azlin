# azlin vm update-tools

**Update development tools on a VM**

## Description

The `azlin vm update-tools` command refreshes the development toolchains that were installed during VM provisioning. It upgrades system packages, the Rust toolchain, and the Python and Node.js package managers.

Note: This updates development tools, NOT operating system packages. For OS updates, use [`azlin os-update`](../util/os-update.md).

## Usage

```bash
azlin vm update-tools [OPTIONS] VM_IDENTIFIER
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
azlin vm update-tools my-vm
```

### Update by Session Name

```bash
azlin vm update-tools my-project
```

### Update by IP Address

```bash
azlin vm update-tools 20.1.2.3
```

### Update with Custom Timeout

```bash
# Allow 10 minutes per tool update
azlin vm update-tools my-vm --timeout 600
```

### Update with Explicit Resource Group

```bash
azlin vm update-tools my-vm --rg my-resource-group
```

## What Gets Updated

- **System packages**: `apt-get update && apt-get upgrade`
- **Rust**: `rustup update` (rustc, cargo)
- **Python**: `pip install --upgrade pip`
- **Node.js**: `npm install -g npm`

## Troubleshooting

### Update Timeout

**Symptoms:** Update times out

**Solutions:**
```bash
# Increase timeout
azlin vm update-tools my-vm --timeout 900

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

- [update_helpers.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/update_helpers.rs) - Update script definition

## See Also

- [All VM commands](index.md)
- [VM Lifecycle](../../vm-lifecycle/index.md)
