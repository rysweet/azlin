# azlin template delete

Delete a VM template from local storage.

## Description

Remove unused or outdated templates. Templates are permanently deleted from `~/.azlin/templates/`.

## Usage

```bash
azlin template delete TEMPLATE_NAME [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--force, -f` | Skip confirmation prompt |
| `-h, --help` | Show help message |

## Examples

### Delete Template (with confirmation)

```bash
azlin template delete old-vm
```

**Output:**
```
Delete template 'old-vm'? [y/N]: y
✓ Template deleted: ~/.azlin/templates/old-vm.yaml
```

### Force Delete (no confirmation)

```bash
azlin template delete old-vm --force
```

### Delete Multiple Templates

```bash
for template in old-vm legacy-config deprecated-setup; do
  azlin template delete $template --force
done
```

## Common Workflows

### Clean Up Old Templates

```bash
# List templates
azlin template list

# Delete unused templates
azlin template delete dev-old --force
azlin template delete staging-legacy --force
azlin template delete test-vm-2023 --force
```

## Troubleshooting

**Template not found:**
```bash
# List available templates
azlin template list

# Delete existing template
azlin template delete <existing-name>
```

## Related Commands

- [`azlin template create`](create.md) - Create template
- [`azlin template list`](list.md) - List templates
- [`azlin template export`](export.md) - Export template

## See Also

- [Template Management Overview](index.md)
