# Advanced Features

Advanced azlin features for power users and specialized workflows.

## Overview

Advanced commands provide deeper integration with development tools, remote IDE access, multi-VM orchestration, and specialized networking features.

## Available Commands

### Development Integration

- [**azlin code**](code-vscode.md) - VS Code Remote-SSH integration
  - Open VMs in VS Code with Remote-SSH
  - Remote debugging and development
  - Extension management on VMs

### Multi-VM Management

- [**azlin compose**](compose.md) - Multi-VM infrastructure as code
  - Define VM fleets in YAML
  - Coordinated provisioning
  - Environment templates

### CI/CD Integration

- [**azlin github-runner**](github-runner.md) - Self-hosted GitHub Actions runners
  - Deploy runners on azlin VMs
  - Scalable CI/CD infrastructure
  - Cost-effective build agents

### Network Diagnostics

- [**azlin ip diagnostics**](ip-diagnostics.md) - Network troubleshooting
  - IP configuration analysis
  - Connectivity testing
  - DNS resolution checks

## Quick Start Examples

### Open VM in VS Code

```bash
# Launch VS Code connected to VM
azlin code my-dev-vm

# Open specific project folder
azlin code my-vm --folder ~/projects/myapp
```

### Deploy Multi-VM Environment

```bash
# Create compose.yaml
cat > compose.yaml <<EOF
vms:
  - name: web-01
    size: Standard_B2s
  - name: db-01
    size: Standard_D2s_v3
EOF

# Deploy all VMs
azlin compose up
```

### GitHub Actions Runner

```bash
# Deploy runner on VM
azlin github-runner setup my-vm --token ghp_xxx

# Verify runner status
azlin github-runner status my-vm
```

### Network Diagnostics

```bash
# Check VM connectivity
azlin ip diagnostics my-vm

# Test DNS resolution
azlin ip diagnostics my-vm --dns
```

## Use Cases

### Remote Development

Use `azlin code` for seamless remote development with VS Code:

- Edit code directly on powerful Azure VMs
- Run resource-intensive builds remotely
- Consistent development environments
- Easy team collaboration

### Infrastructure as Code

Use `azlin compose` to define VM fleets:

- Version control VM configurations
- Reproducible environments
- Multi-environment deployments
- Template-based provisioning

### CI/CD Pipelines

Use `azlin github-runner` for build infrastructure:

- Cost-effective build agents
- Scalable pipeline capacity
- Self-hosted runner control
- Azure VM performance

### Network Troubleshooting

Use `azlin ip diagnostics` when debugging:

- Connection failures
- DNS issues
- Network configuration problems
- Bastion connectivity

## Feature Comparison

| Feature | Command | Best For |
|---------|---------|----------|
| VS Code Integration | `azlin code` | Development workflows |
| Multi-VM Orchestration | `azlin compose` | Infrastructure management |
| CI/CD Runners | `azlin github-runner` | Build pipelines |
| Network Tools | `azlin ip diagnostics` | Troubleshooting |

## Related Topics

- [AI Commands](../ai/index.md) - Natural language interface
- [Fleet Management](../fleet/index.md) - Distributed operations
- [Batch Operations](../batch/index.md) - Parallel execution
- [VM Management](../vm/index.md) - Core VM operations

## See Also

- [Connecting](../../vm-lifecycle/connecting.md)
- [Fleet Management](../../batch/fleet.md)
- [GitHub Runners](../../advanced/github-runners.md)
