# azlin template export

Export a VM template to a file for sharing or version control.

## Description

Export templates to share with team members, back up configurations, or store in Git repositories.

## Usage

```bash
azlin template export TEMPLATE_NAME OUTPUT_FILE [OPTIONS]
```

## Arguments

- `TEMPLATE_NAME` - Template to export
- `OUTPUT_FILE` - Destination file path

## Options

| Option | Description |
|--------|-------------|
| `--format FORMAT` | Export format: `yaml`, `json` (default: `yaml`) |
| `--overwrite` | Overwrite existing file |
| `-h, --help` | Show help message |

## Examples

### Export Template to File

```bash
azlin template export dev-vm ~/templates/dev-vm.yaml
```

**Output:**
```
Exporting template 'dev-vm'...
  Source: ~/.azlin/templates/dev-vm.yaml
  Destination: ~/templates/dev-vm.yaml

✓ Template exported successfully!
```

### Export to JSON

```bash
azlin template export prod ~/backups/prod-template.json --format json
```

### Export All Templates

```bash
mkdir -p ~/azlin-templates-backup
for template in $(azlin template list --format json | jq -r '.templates[].name'); do
  azlin template export $template ~/azlin-templates-backup/$template.yaml
done
```

## Common Workflows

### Team Sharing

```bash
# Export template
azlin template export team-dev /shared/templates/team-dev.yaml

# Team members import
azlin template import /shared/templates/team-dev.yaml
```

### Version Control

```bash
# Export all templates to Git repo
mkdir -p ~/git/azlin-templates
cd ~/git/azlin-templates
git init

for template in $(azlin template list --format json | jq -r '.templates[].name'); do
  azlin template export $template $template.yaml
done

git add *.yaml
git commit -m "Export azlin templates"
git push
```

## Related Commands

- [`azlin template import`](import.md) - Import template
- [`azlin template create`](create.md) - Create template
- [`azlin template list`](list.md) - List templates

## See Also

- [Template Management Overview](index.md)
