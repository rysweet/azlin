# azlin doit list

List all resources created by doit.

## Synopsis

```bash
azlin doit list [OPTIONS]
```

## Description

Shows all Azure resources tagged with `azlin-doit-owner`. Lists resources for current Azure user by default.

## Options

| Option | Description |
|--------|-------------|
| `-u, --username TEXT` | Filter by Azure username |
| `-h, --help` | Show help |

## Examples

### List your resources
```bash
azlin doit list
```

### List another user's resources
```bash
azlin doit list --username user@example.com
```

## Output Example

```
Doit-Created Resources

Resource Group: rg-doit-abc123
  App Service: myapp-web (Standard S1)
  SQL Database: myapp-db (Basic)
  Storage Account: myappstorage (Standard LRS)

Total: 3 resources
Estimated Monthly Cost: $125
```

## Related Commands

- [azlin doit show](show.md) - Show detailed resource info
- [azlin doit cleanup](cleanup.md) - Delete resources
