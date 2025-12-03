# azlin - Azure Ubuntu VM Provisioning CLI

**One command to create a fully-equipped development VM on Azure**

<div class="grid cards" markdown>

-   :rocket:{ .lg .middle } **Quick Start**

    ---

    Get started in 5 minutes with a fully configured Ubuntu development VM

    [:octicons-arrow-right-24: Getting Started](getting-started/quickstart.md)

-   :material-console:{ .lg .middle } **Command Reference**

    ---

    Complete reference for all 60+ azlin commands

    [:octicons-arrow-right-24: Browse Commands](commands/index.md)

-   :material-shield-check:{ .lg .middle } **Authentication**

    ---

    Configure Azure CLI or Service Principal authentication

    [:octicons-arrow-right-24: Setup Auth](authentication/index.md)

-   :material-database:{ .lg .middle } **Storage & NFS**

    ---

    Create and mount shared Azure Files NFS storage

    [:octicons-arrow-right-24: Learn More](storage/index.md)

</div>

## What is azlin?

azlin automates the tedious process of setting up Azure Ubuntu VMs for development. In one command, it:

1. ✓ Authenticates with Azure
2. ✓ Provisions an Ubuntu 24.04 VM
3. ✓ Installs 12 essential development tools
4. ✓ Sets up SSH with key-based authentication
5. ✓ Starts a persistent tmux session
6. ✓ Optionally clones a GitHub repository

**Total time**: 4-7 minutes from command to working development environment.

## Quick Example

```bash
# Run directly from GitHub (no installation needed)
uvx --from git+https://github.com/rysweet/azlin azlin new

# Create VM with custom name
azlin new --name myproject

# Fully automated provisioning (zero prompts!)
azlin new --name myvm --yes

# Create VM and clone GitHub repo
azlin new --repo https://github.com/owner/repo

# Mount Azure Files locally on macOS
azlin storage mount local --mount-point ~/azure/
```

## Key Features

### :material-flash: Fast VM Provisioning
Create fully configured development VMs in 4-7 minutes with a single command.

### :material-tools: 12 Pre-Installed Tools
Every VM includes Docker, Azure CLI, GitHub CLI, Node.js, Python 3.13, Rust, Go, .NET, and AI coding assistants.

### :material-database: Shared NFS Storage
Create Azure Files NFS storage and mount across multiple VMs for shared data.

### :material-network: Azure Bastion Support
Secure, browser-based SSH access without public IP addresses.

### :material-console-line: Batch Operations
Run commands across entire VM fleets in parallel.

### :material-robot: AI-Powered Features
Natural language VM management with `azlin do` command.

### :material-shield-lock: Secure by Default
SSH key rotation, Azure Key Vault integration, service principal support.

### :material-speedometer: Cost Optimization
Auto-stop idle VMs, quota management, cost tracking.

## What's New in v0.4.0

!!! tip "Latest Release - December 2025"

### 🚀 10 Major New Features

**1. VM Lifecycle Automation**
Automated health monitoring, self-healing, and lifecycle hooks:
```bash
azlin autopilot enable myvm --health-checks --self-healing
```
[:octicons-arrow-right-24: Learn More](vm-lifecycle/automation.md)

**2. Cost Optimization Intelligence**
Real-time cost dashboard, budget alerts, and AI-powered recommendations:
```bash
azlin util cost --detailed
azlin util cost recommendations --apply
```
[:octicons-arrow-right-24: Learn More](monitoring/cost-optimization.md)

**3. Multi-Region Orchestration**
Deploy and manage VMs across multiple regions with automatic failover:
```bash
azlin new myapp --regions eastus,westus,centralus --strategy active-active
```
[:octicons-arrow-right-24: Learn More](advanced/multi-region.md)

**4. Enhanced Monitoring & Alerting**
Comprehensive metrics, intelligent alerts, and cost forecasting:
```bash
azlin monitoring enable myvm --metrics all --alerts smart
```
[:octicons-arrow-right-24: Learn More](monitoring/enhanced-monitoring.md)

**5. Backup & Disaster Recovery**
Automated backups, DR testing, and point-in-time recovery:
```bash
azlin backup enable myvm --schedule daily --retention 30d
azlin dr test production-app
```
[:octicons-arrow-right-24: Learn More](advanced/backup-dr.md)

**6. Network Security Enhancements**
NSG automation, Bastion pooling, and comprehensive audit logging:
```bash
azlin security nsg auto-configure myvm
```
[:octicons-arrow-right-24: Learn More](advanced/network-security.md)

**7. Template System V2**
Versioning, composition, validation, and marketplace:
```bash
azlin template create mytemplate --version 1.0.0
azlin template validate mytemplate
```
[:octicons-arrow-right-24: Learn More](advanced/templates-v2.md)

**8. Storage Management**
Quota management, automated cleanup, and tier optimization:
```bash
azlin storage optimize --auto-tier --cleanup-old
```
[:octicons-arrow-right-24: Learn More](storage/management.md)

**9. Natural Language Enhancements**
Context-aware parsing and intelligent workflow suggestions:
```bash
azlin do "deploy 3 web servers with load balancing across regions"
```
[:octicons-arrow-right-24: Learn More](ai/natural-language.md)

**10. Performance Optimization**
API caching, connection pooling, and intelligent batching:
- 3x faster bulk operations
- 50% reduction in API calls
- Smart request batching

[:octicons-arrow-right-24: Learn More](advanced/performance.md)

[View Full Changelog](changelog.md){ .md-button }

## Development Tools Installed

Every azlin VM comes pre-configured with:

=== "Core Tools"

    - **Docker** - Container runtime
    - **Azure CLI (az)** - Azure management
    - **GitHub CLI (gh)** - GitHub integration
    - **Git** - Version control

=== "Languages"

    - **Node.js** - JavaScript runtime with user-local npm
    - **Python 3.13+** - Latest Python from deadsnakes PPA
    - **Rust** - Systems programming language
    - **Golang** - Go programming language
    - **.NET 10 RC** - .NET development framework

=== "AI Tools"

    - **GitHub Copilot CLI** - AI pair programmer
    - **OpenAI Codex CLI** - Advanced AI code generation
    - **Claude Code CLI** - Anthropic's AI coding assistant

## Use Cases

### Development Teams
Share NFS storage and individual VMs for team collaboration.

[:octicons-arrow-right-24: View Example](examples/dev-team-setup.md)

### CI/CD Runners
Provision ephemeral GitHub Actions runners on demand.

[:octicons-arrow-right-24: View Example](advanced/github-runners.md)

### Machine Learning
Create GPU-enabled VMs for training workloads.

[:octicons-arrow-right-24: View Example](examples/ml-cluster.md)

### Cost Optimization
Auto-stop idle VMs and manage quotas.

[:octicons-arrow-right-24: View Example](examples/cost-optimization.md)

## Getting Help

- **Documentation**: You're here! Browse sections on the left
- **GitHub Issues**: [Report bugs or request features](https://github.com/rysweet/azlin/issues)
- **GitHub Discussions**: [Ask questions](https://github.com/rysweet/azlin/discussions)
- **Command Help**: Run `azlin --help` or `azlin <command> --help`

## Quick Links

<div class="grid cards" markdown>

-   [:material-download: Installation](getting-started/installation.md)
-   [:material-rocket-launch: Quick Start](getting-started/quickstart.md)
-   [:material-book-open-variant: API Reference](api/index.md)
-   [:material-bug: Troubleshooting](troubleshooting/index.md)

</div>

## Project Information

- **License**: MIT
- **Python**: 3.12+
- **Repository**: [rysweet/azlin](https://github.com/rysweet/azlin)
- **PyPI**: [pypi.org/project/azlin](https://pypi.org/project/azlin/)
- **Version**: 0.4.0

---

*Ready to get started?* Head to the [Quick Start Guide](getting-started/quickstart.md) or dive into [Installation](getting-started/installation.md).
