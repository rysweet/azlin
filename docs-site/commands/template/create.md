# azlin template create

Create reusable VM configuration templates for consistent provisioning across environments.

## Description

The `azlin template create` command saves VM configuration settings (size, region, cloud-init scripts) as a reusable template. This enables:

- **Standardization**: Consistent VM configurations across team
- **Environment-specific configs**: Separate templates for dev/staging/prod
- **Rapid provisioning**: Deploy pre-configured VMs with `azlin new --template`
- **Version control**: Track infrastructure configurations
- **Team sharing**: Distribute templates via Git or shared drives

Templates are stored as YAML files in `~/.azlin/templates/` and can be version-controlled.

## Usage

```bash
azlin template create TEMPLATE_NAME [OPTIONS]
```

## Arguments

- `TEMPLATE_NAME` - Name for the template (required)

## Options

| Option | Description |
|--------|-------------|
| `--vm-size TEXT` | Azure VM size (e.g., Standard_D2s_v3, Standard_B2s) |
| `--region TEXT` | Azure region (e.g., eastus, westus2) |
| `--description TEXT` | Human-readable template description |
| `--cloud-init PATH` | Path to cloud-init YAML file for custom VM setup |
| `--nfs-storage TEXT` | NFS storage account name for shared home directory |
| `--tags KEY=VALUE` | VM tags (can specify multiple times) |
| `--config PATH` | Config file path |
| `-h, --help` | Show help message |

## Examples

### Create Basic Template

```bash
# Create template with defaults (from ~/.azlin/config.toml)
azlin template create dev-vm
```

**Output:**
```
Creating template 'dev-vm'...

Template configuration:
  Name: dev-vm
  VM Size: Standard_D2s_v3 (from config)
  Region: eastus (from config)
  Description: dev-vm template

✓ Template created: ~/.azlin/templates/dev-vm.yaml

Use with:
  azlin new --template dev-vm --name my-instance
```

### Create Template with Custom VM Size

```bash
# Small, cost-effective template
azlin template create small-vm --vm-size Standard_B2s --region westus2
```

**Output:**
```
Creating template 'small-vm'...

Template configuration:
  Name: small-vm
  VM Size: Standard_B2s (burstable, low cost)
  Region: westus2

✓ Template created successfully!
```

### Create GPU-Enabled Template

```bash
# Template for ML/AI workloads
azlin template create gpu-ml \
  --vm-size Standard_NC6 \
  --region eastus \
  --description "GPU-enabled VM for machine learning training"
```

### Create Template with Cloud-Init

```bash
# First, create cloud-init script
cat > ~/ml-setup.yaml << 'EOF'
#cloud-config
packages:
  - nvidia-cuda-toolkit
  - python3-pip

runcmd:
  - pip3 install torch torchvision tensorflow
  - nvidia-smi
EOF

# Create template with custom setup
azlin template create ml-cuda \
  --vm-size Standard_NC6 \
  --cloud-init ~/ml-setup.yaml \
  --description "CUDA ML training environment"
```

**Output:**
```
Creating template 'ml-cuda'...

Template configuration:
  Name: ml-cuda
  VM Size: Standard_NC6 (GPU: 1x K80)
  Region: eastus
  Cloud-Init: /Users/ryan/ml-setup.yaml (included)
  Description: CUDA ML training environment

✓ Template created: ~/.azlin/templates/ml-cuda.yaml

Cloud-init script embedded in template.
```

### Create Template with Shared Storage

```bash
# Template for team collaboration
azlin template create team-dev \
  --vm-size Standard_D4s_v3 \
  --nfs-storage team-shared \
  --description "Team development VM with shared home directory"
```

### Create Template with Tags

```bash
# Template with metadata tags
azlin template create prod-api \
  --vm-size Standard_D8s_v3 \
  --region eastus \
  --tags env=production \
  --tags app=api \
  --tags cost-center=engineering \
  --description "Production API server configuration"
```

### Production-Grade Template

```bash
# Comprehensive production template
azlin template create production \
  --vm-size Standard_D16s_v3 \
  --region eastus2 \
  --cloud-init ~/prod-setup.yaml \
  --tags env=production \
  --tags managed-by=azlin \
  --tags backup=daily \
  --description "Production VM: 16 vCPUs, 64GB RAM, automated backup"
```

## Common Workflows

### Multi-Environment Templates

```bash
# Development environment
azlin template create dev \
  --vm-size Standard_B2s \
  --region westus2 \
  --tags env=dev \
  --description "Development VMs"

# Staging environment
azlin template create staging \
  --vm-size Standard_D4s_v3 \
  --region westus2 \
  --tags env=staging \
  --description "Staging environment"

# Production environment
azlin template create prod \
  --vm-size Standard_D8s_v3 \
  --region eastus \
  --tags env=production \
  --tags backup=daily \
  --description "Production servers"

# Use templates
azlin new --template dev --name dev-vm-001
azlin new --template staging --name staging-vm-001
azlin new --template prod --name prod-api-001
```

### Project-Specific Templates

```bash
# Frontend development
azlin template create frontend-dev \
  --vm-size Standard_D4s_v3 \
  --cloud-init ~/frontend-setup.yaml \
  --tags project=frontend \
  --description "Frontend development with Node.js 20"

# Backend development
azlin template create backend-dev \
  --vm-size Standard_D8s_v3 \
  --cloud-init ~/backend-setup.yaml \
  --tags project=backend \
  --description "Backend development with Python 3.11"

# Database testing
azlin template create db-test \
  --vm-size Standard_D16s_v3 \
  --tags project=database \
  --description "Database testing VM with 64GB RAM"
```

### Team Onboarding Templates

```bash
# Create onboarding template
cat > ~/team-onboarding.yaml << 'EOF'
#cloud-config
packages:
  - docker.io
  - docker-compose
  - postgresql-client

runcmd:
  - git clone https://github.com/company/dev-setup.git /opt/dev-setup
  - /opt/dev-setup/install.sh
  - echo "Welcome to the team!" > /home/azureuser/README.txt
EOF

azlin template create team-onboarding \
  --vm-size Standard_D4s_v3 \
  --cloud-init ~/team-onboarding.yaml \
  --nfs-storage team-shared \
  --tags team=engineering \
  --description "New team member development VM"

# New team member provisions VM
azlin new --template team-onboarding --name alice-dev
```

### Performance Tier Templates

```bash
# Small: Dev/testing
azlin template create small \
  --vm-size Standard_B2s \
  --description "Small: 2 vCPUs, 4GB RAM"

# Medium: Active development
azlin template create medium \
  --vm-size Standard_D4s_v3 \
  --description "Medium: 4 vCPUs, 16GB RAM"

# Large: Builds/CI
azlin template create large \
  --vm-size Standard_D8s_v3 \
  --description "Large: 8 vCPUs, 32GB RAM"

# XLarge: Heavy workloads
azlin template create xlarge \
  --vm-size Standard_D16s_v3 \
  --description "XLarge: 16 vCPUs, 64GB RAM"
```

## Template File Format

Templates are stored as YAML in `~/.azlin/templates/<name>.yaml`:

```yaml
name: dev-vm
description: Development VM template
vm_size: Standard_D2s_v3
region: eastus
created_at: 2025-11-24T14:30:22Z
modified_at: 2025-11-24T14:30:22Z

# Optional: cloud-init script (embedded)
cloud_init: |
  #cloud-config
  packages:
    - build-essential
  runcmd:
    - echo "Hello from cloud-init"

# Optional: NFS storage
nfs_storage: team-shared

# Optional: tags
tags:
  env: development
  managed-by: azlin
```

## Troubleshooting

### Template Already Exists

**Problem**: "Template 'dev-vm' already exists" error.

**Solution**:
```bash
# Option 1: Use different name
azlin template create dev-vm-v2 --vm-size Standard_B2s

# Option 2: Delete existing template
azlin template delete dev-vm
azlin template create dev-vm --vm-size Standard_B2s

# Option 3: Edit template file directly
vi ~/.azlin/templates/dev-vm.yaml
```

### Cloud-Init File Not Found

**Problem**: "Cloud-init file not found" error.

**Solution**:
```bash
# Verify file exists
ls -la ~/ml-setup.yaml

# Use absolute path
azlin template create ml-vm --cloud-init ~/ml-setup.yaml

# Create cloud-init file first
cat > ~/setup.yaml << 'EOF'
#cloud-config
packages:
  - vim
EOF

azlin template create my-vm --cloud-init ~/setup.yaml
```

### Invalid VM Size

**Problem**: "Invalid VM size" error.

**Solution**:
```bash
# List available VM sizes
az vm list-sizes --location eastus --output table

# Common VM sizes:
# - Standard_B1s, Standard_B2s (burstable, economical)
# - Standard_D2s_v3, Standard_D4s_v3 (general purpose)
# - Standard_E4s_v3 (memory optimized)
# - Standard_NC6 (GPU-enabled)

# Create template with valid size
azlin template create my-vm --vm-size Standard_D2s_v3
```

## Best Practices

### Template Naming

```bash
# Use descriptive names
azlin template create frontend-dev         # ✓ Clear purpose
azlin template create gpu-ml-training      # ✓ Indicates specialty
azlin template create prod-api-server      # ✓ Environment + role

# Avoid generic names
azlin template create vm1                  # ✗ Non-descriptive
azlin template create test                 # ✗ Too vague
```

### Version Control

```bash
# Store templates in Git
cd ~/.azlin/templates/
git init
git add *.yaml
git commit -m "Add VM templates"
git remote add origin https://github.com/company/azlin-templates.git
git push

# Share with team
git clone https://github.com/company/azlin-templates.git ~/.azlin/templates/
```

### Documentation

Always add descriptions:

```bash
azlin template create api-server \
  --vm-size Standard_D8s_v3 \
  --description "API Server: 8 vCPUs, 32GB RAM, optimized for REST APIs"
```

## Performance

Template creation is instantaneous (< 1 second):
- Only writes local YAML file
- No Azure API calls
- No network operations

## Related Commands

- [`azlin template list`](list.md) - List all templates
- [`azlin template delete`](delete.md) - Delete a template
- [`azlin template export`](export.md) - Export template to file
- [`azlin template import`](import.md) - Import template from file
- [`azlin new`](../vm/new.md) - Provision VM from template

## Deep Links to Source

- [Template creation logic](https://github.com/rysweet/azlin/blob/main/src/azlin/commands/__init__.py#L2000-L2100)
- [Template YAML schema](https://github.com/rysweet/azlin/blob/main/src/azlin/core/templates.py#L50-L150)
- [Cloud-init embedding](https://github.com/rysweet/azlin/blob/main/src/azlin/core/templates.py#L200-L300)

## See Also

- [VM Template Management Overview](index.md)
- [Templates](../../advanced/templates.md)
- [Creating VMs](../../vm-lifecycle/creating.md)
