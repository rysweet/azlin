# azlin killall

Delete all VMs in resource group.

## Synopsis

```bash
azlin killall [OPTIONS]
```

## Description

Deletes ALL VMs in the resource group and their associated resources. Use with caution!

## Options

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation |
| `--rg TEXT` | Resource group |
| `-h, --help` | Show help |

## Examples

### Delete all VMs (with confirmation)
```bash
azlin killall
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
Delete ALL VMs in resource group: my-rg

VMs to delete:
  - vm-test-1
  - vm-test-2
  - vm-prod-1
  - vm-staging

Total: 4 VMs

THIS WILL DELETE ALL VMs AND CANNOT BE UNDONE!

Type 'yes' to confirm: yes

Deleting VMs...
✓ Deleted vm-test-1
✓ Deleted vm-test-2
✓ Deleted vm-prod-1
✓ Deleted vm-staging

All VMs deleted successfully.
```

## Safety Features

- Requires explicit confirmation
- Lists all VMs before deletion
- Shows resource count
- Warns about irreversibility

## Use Cases

- Clean up test environments
- Reset development resource groups
- Tear down temporary infrastructure

## Related Commands

- [azlin kill](kill.md) - Delete single VM
- [azlin prune](../util/prune.md) - Delete only idle VMs
- [azlin destroy](destroy.md) - Delete with dry-run option
