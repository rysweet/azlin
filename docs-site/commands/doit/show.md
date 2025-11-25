# azlin doit show

Show detailed information about a doit-created resource.

## Synopsis

```bash
azlin doit show <resource-id>
```

## Description

Displays detailed information about a specific Azure resource including configuration, tags, and relationships.

## Examples

### Show resource details
```bash
azlin doit show /subscriptions/.../resourceGroups/rg-name/providers/Microsoft.Web/sites/my-app
```

## Output

Shows:
- Resource properties
- Tags (including doit metadata)
- Related resources
- Cost estimate
- Generated IaC snippets

## Related Commands

- [azlin doit list](list.md) - List all resources
