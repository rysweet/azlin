# VM Template Management

Save and reuse VM configurations for consistent provisioning across environments.

## Overview

VM templates store configuration settings (size, region, cloud-init scripts) as reusable YAML files. Standardize deployments, share configurations with teams, and provision VMs rapidly.

## Commands

| Command | Description |
|---------|-------------|
| [`create`](create.md) | Create a new VM template |
| [`list`](list.md) | List all available templates |
| [`delete`](delete.md) | Delete a template |
| [`export`](export.md) | Export template to file |
| [`import`](import.md) | Import template from file |

## Quick Start

```bash
# Create template
azlin template create dev-vm --vm-size Standard_B2s --region westus2

# List templates
azlin template list

# Provision VM from template
azlin new --template dev-vm --name my-instance

# Export for team sharing
azlin template export dev-vm ~/shared/dev-vm.yaml

# Import from file
azlin template import ~/shared/dev-vm.yaml
```

## Common Use Cases

### Multi-Environment Setup

```bash
azlin template create dev --vm-size Standard_B2s --tags env=dev
azlin template create staging --vm-size Standard_D4s_v3 --tags env=staging
azlin template create prod --vm-size Standard_D8s_v3 --tags env=production

azlin new --template dev --name dev-vm-001
azlin new --template staging --name staging-vm-001
azlin new --template prod --name prod-api-001
```

### Team Sharing

```bash
# Export all templates
for t in $(azlin template list --format json | jq -r '.templates[].name'); do
  azlin template export $t /shared/templates/$t.yaml
done

# Team members import
azlin template import /shared/templates/*.yaml
```

## Template Storage

Templates stored in `~/.azlin/templates/` as YAML files.

## Related Documentation

- [VM Provisioning](../vm/new.md)
- [Templates](../../advanced/templates.md)

## See Also

- [VM Management](../vm/index.md)
- [Getting Started Guide](../../getting-started/quickstart.md)
