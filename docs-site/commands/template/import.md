# azlin template import

Import a VM template from a file into local template storage.

## Description

Import templates shared by team members or restored from backups.

## Usage

```bash
azlin template import INPUT_FILE [OPTIONS]
```

## Arguments

- `INPUT_FILE` - Template file to import (YAML or JSON)

## Options

| Option | Description |
|--------|-------------|
| `--name TEXT` | Override template name |
| `--overwrite` | Overwrite existing template |
| `-h, --help` | Show help message |

## Examples

### Import Template from File

```bash
azlin template import ~/downloads/prod-template.yaml
```

**Output:**
```
Importing template from ~/downloads/prod-template.yaml...

Template: prod
  VM Size: Standard_D8s_v3
  Region: eastus
  Description: Production servers

✓ Template imported: ~/.azlin/templates/prod.yaml
```

### Import with Custom Name

```bash
azlin template import ~/team-dev.yaml --name dev-customized
```

### Import and Overwrite Existing

```bash
azlin template import ~/updated-template.yaml --overwrite
```

### Bulk Import

```bash
for file in ~/azlin-templates-backup/*.yaml; do
  azlin template import $file --overwrite
done
```

## Common Workflows

### Restore from Backup

```bash
# After system migration
cd ~/azlin-templates-backup
for template in *.yaml; do
  azlin template import $template
done

# Verify
azlin template list
```

### Team Distribution

```bash
# Clone team templates repo
git clone https://github.com/company/azlin-templates.git /tmp/templates

# Import all
cd /tmp/templates
for template in *.yaml; do
  azlin template import $template --overwrite
done
```

## Related Commands

- [`azlin template export`](export.md) - Export template
- [`azlin template create`](create.md) - Create template
- [`azlin template list`](list.md) - List templates

## See Also

- [Template Management Overview](index.md)
