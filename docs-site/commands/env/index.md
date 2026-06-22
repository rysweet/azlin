# Environment Commands

Manage environment variables on your Azure VMs.

## Commands

| Command | Description |
|---------|-------------|
| [`azlin env set`](set.md) | Set an environment variable on a VM |
| [`azlin env list`](list.md) | List environment variables on a VM |
| [`azlin env delete`](delete.md) | Delete an environment variable |
| [`azlin env export`](export.md) | Export environment variables to a file |
| [`azlin env import`](import.md) | Import environment variables from a file |
| [`azlin env clear`](clear.md) | Clear all environment variables |

## Quick Examples

```bash
# Set a variable
azlin env set myvm DATABASE_URL="postgres://localhost/mydb"

# List all variables
azlin env list myvm

# Export for backup
azlin env export myvm --output env.json

# Import to another VM
azlin env import myvm2 --input env.json
```

## See Also

- [Environment Best Practices](../../environment/best-practices.md)
- [Import/Export Guide](../../environment/import-export.md)
