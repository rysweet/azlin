# azlin killall

Delete every VM in a resource group whose name starts with `--prefix`.

## Synopsis

```bash
azlin killall [OPTIONS]
```

## Description

Deletes the VMs in the resource group whose names start with `--prefix`
(default: `azlin`) along with their associated resources. Use with caution!

VMs created with an explicit `--name` that does not start with the prefix are
**not** deleted. For example `azlin new --name smoke-test` creates a VM that
`azlin killall` skips by default; delete it with
`azlin killall --prefix smoke-test`, or pass `--prefix ''` to match every VM in
the resource group.

## Options

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation |
| `--prefix TEXT` | Only delete VMs whose name starts with this prefix (default: `azlin`). Use `''` to match every VM |
| `--rg TEXT` | Resource group |
| `-h, --help` | Show help |

## Examples

### Delete the default `azlin`-prefixed VMs (with confirmation)
```bash
azlin killall
```

### Delete VMs with a custom name prefix
```bash
azlin killall --prefix smoke-test
```

### Delete every VM in the resource group
```bash
azlin killall --prefix ''
```

### Force delete without confirmation
```bash
azlin killall --force
```

### Delete in specific resource group
```bash
azlin killall --rg test-rg --force
```

## Output Example

```
Delete these 2 VM(s) with prefix 'azlin' in 'my-rg'? This cannot be undone.
  azlin-vm-1760000000
  azlin-vm-1760000001
 [y/N]: y

Deleted azlin-vm-1760000000 and 4 associated resource(s)
Deleted azlin-vm-1760000001 and 4 associated resource(s)
Deleted 2 VMs with prefix 'azlin'
```

Each VM is torn down individually, so its disks, NIC, Public IP and NSG go
with it rather than being orphaned.

When nothing matches the prefix but the resource group is not empty, `killall`
says so instead of silently doing nothing:

```
No VMs matched prefix 'azlin' in 'my-rg'. Nothing was deleted.
2 VM(s) exist in this resource group but do not start with 'azlin':
  smoke-test
  other-vm
Target them with --prefix, for example:
  azlin killall --prefix 'smoke-test'
  azlin killall --prefix ''   # every VM in the resource group
```

## Safety Features

- Requires explicit confirmation
- Names the exact VMs that will be deleted before confirming
- Only deletes VMs matching `--prefix` (default `azlin`)
- Reports non-matching VMs instead of silently deleting nothing
- Deletes only the VMs it named, even if a new one appears while you decide
- Warns about irreversibility

## Use Cases

- Clean up test environments
- Reset development resource groups
- Tear down temporary infrastructure

## Related Commands

- [azlin kill](kill.md) - Delete single VM
- [azlin prune](../util/prune.md) - Delete only idle VMs
- [azlin destroy](destroy.md) - Delete with dry-run option
