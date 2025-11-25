# azlin template list

List all available VM templates for quick reference and selection.

## Description

The `azlin template list` command displays all VM templates stored in `~/.azlin/templates/`. View template configurations, descriptions, and metadata to select the right template for provisioning.

## Usage

```bash
azlin template list [OPTIONS]
```

## Options

| Option | Description |
|--------|-------------|
| `--verbose, -v` | Show detailed template configuration |
| `--format FORMAT` | Output format: `table`, `json`, `yaml` (default: `table`) |
| `-h, --help` | Show help message |

## Examples

### List All Templates (Default)

```bash
azlin template list
```

**Output:**
```
Available VM Templates (5):

┌─────────────────┬──────────────────┬─────────┬──────────────────────────────────┐
│ NAME            │ VM SIZE          │ REGION  │ DESCRIPTION                      │
├─────────────────┼──────────────────┼─────────┼──────────────────────────────────┤
│ dev-vm          │ Standard_B2s     │ westus2 │ Development VMs                  │
│ staging         │ Standard_D4s_v3  │ westus2 │ Staging environment              │
│ prod            │ Standard_D8s_v3  │ eastus  │ Production servers               │
│ gpu-ml          │ Standard_NC6     │ eastus  │ GPU-enabled ML training          │
│ team-onboarding │ Standard_D4s_v3  │ eastus  │ New team member VM               │
└─────────────────┴──────────────────┴─────────┴──────────────────────────────────┘

Total: 5 templates
Location: ~/.azlin/templates/

Use with:
  azlin new --template TEMPLATE_NAME --name VM_NAME
```

### Verbose Output

```bash
azlin template list --verbose
```

**Output:**
```
Template: dev-vm
  VM Size: Standard_B2s (2 vCPUs, 4GB RAM)
  Region: eastus
  Description: Development VMs
  Tags: env=dev, managed-by=azlin
  Created: 2025-11-20 10:30:22
  Modified: 2025-11-24 14:15:00
  File: ~/.azlin/templates/dev-vm.yaml

Template: gpu-ml
  VM Size: Standard_NC6 (6 vCPUs, 56GB RAM, 1x K80 GPU)
  Region: eastus
  Description: GPU-enabled ML training
  Cloud-Init: Yes (5 lines)
  Tags: workload=ml, gpu=k80
  Created: 2025-11-22 09:15:00
  Modified: 2025-11-22 09:15:00
  File: ~/.azlin/templates/gpu-ml.yaml

Template: team-onboarding
  VM Size: Standard_D4s_v3 (4 vCPUs, 16GB RAM)
  Region: eastus
  Description: New team member VM
  NFS Storage: team-shared
  Cloud-Init: Yes (12 lines)
  Tags: team=engineering
  Created: 2025-11-23 15:00:00
  Modified: 2025-11-23 15:00:00
  File: ~/.azlin/templates/team-onboarding.yaml
```

### JSON Output

```bash
azlin template list --format json
```

**Output:**
```json
{
  "templates": [
    {
      "name": "dev-vm",
      "vm_size": "Standard_B2s",
      "region": "eastus",
      "description": "Development VMs",
      "tags": {"env": "dev"},
      "created_at": "2025-11-20T10:30:22Z",
      "modified_at": "2025-11-24T14:15:00Z",
      "file_path": "~/.azlin/templates/dev-vm.yaml"
    },
    {
      "name": "gpu-ml",
      "vm_size": "Standard_NC6",
      "region": "eastus",
      "description": "GPU-enabled ML training",
      "cloud_init": true,
      "tags": {"workload": "ml", "gpu": "k80"},
      "created_at": "2025-11-22T09:15:00Z",
      "modified_at": "2025-11-22T09:15:00Z",
      "file_path": "~/.azlin/templates/gpu-ml.yaml"
    }
  ],
  "total": 2,
  "location": "~/.azlin/templates/"
}
```

## Common Workflows

### Select Template for Provisioning

```bash
# 1. List templates
azlin template list

# 2. Choose template
azlin new --template dev-vm --name my-dev-instance

# 3. Or review details first
azlin template list --verbose | grep -A 10 "Template: dev-vm"
```

### Find Templates by Criteria

```bash
# Find GPU templates
azlin template list --verbose | grep -B 2 "GPU"

# Find templates by region
azlin template list --format json | jq '.templates[] | select(.region == "eastus")'

# Find templates with cloud-init
azlin template list --format json | jq '.templates[] | select(.cloud_init == true)'
```

### Export Template Inventory

```bash
# Export to JSON for documentation
azlin template list --format json > /tmp/template-inventory.json

# Convert to table for wiki
azlin template list > /tmp/template-inventory.txt

# Generate Markdown documentation
azlin template list --format json | jq -r '.templates[] | "- **\(.name)**: \(.description) (Size: \(.vm_size), Region: \(.region))"'
```

## Related Commands

- [`azlin template create`](create.md) - Create new template
- [`azlin template delete`](delete.md) - Delete template
- [`azlin new`](../vm/new.md) - Provision VM from template

## Deep Links

- [Template listing code](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L2150-L2250)

## See Also

- [Template Management Overview](index.md)
