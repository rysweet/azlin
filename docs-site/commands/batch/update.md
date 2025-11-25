# azlin batch update

Update development tools on multiple VMs.

## Synopsis

```bash
azlin batch update <vm-selector> [OPTIONS]
```

## Examples

```bash
# Update all VMs
azlin batch update "*"

# Update VMs matching pattern
azlin batch update "prod-*"

# Update specific VMs
azlin batch update "vm1,vm2,vm3"
```

## What Gets Updated

- Azure CLI
- GitHub CLI
- Docker
- Node.js
- Python
- Rust
- Golang
- .NET
- System packages

## Related Commands

- [azlin update](../util/update.md) - Update single VM
- [azlin batch command](command.md) - Execute custom commands
