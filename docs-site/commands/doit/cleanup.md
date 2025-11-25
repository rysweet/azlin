# azlin doit cleanup

Delete all doit-created resources.

## Synopsis

```bash
azlin doit cleanup [OPTIONS]
```

## Description

Deletes all Azure resources created by doit. Resources are deleted in dependency order (data resources last).

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `-f, --force` | Skip confirmation | `false` |
| `--dry-run` | Show what would be deleted | `false` |
| `-u, --username TEXT` | Filter by username | current user |
| `-h, --help` | Show help | - |

## Examples

### Preview cleanup
```bash
azlin doit cleanup --dry-run
```

### Delete with confirmation
```bash
azlin doit cleanup
```

### Force delete without confirmation
```bash
azlin doit cleanup --force
```

## Output Example

```
Doit Cleanup

Resources to delete:
  Resource Group: rg-doit-abc123
    App Service: myapp-web
    SQL Database: myapp-db
    Storage Account: myappstorage

Total: 3 resources
Estimated cost savings: $125/month

Continue? [y/N]: y

Deleting resources...
  ✓ Deleted myapp-web
  ✓ Deleted myapp-db
  ✓ Deleted myappstorage
  ✓ Deleted rg-doit-abc123

Cleanup complete!
```

## Safety Features

- Confirmation prompt (unless `--force`)
- Dry-run mode
- Dependency-aware deletion order
- Only deletes doit-tagged resources

## Related Commands

- [azlin doit list](list.md) - List resources before cleanup
- [azlin doit deploy](deploy.md) - Deploy resources
