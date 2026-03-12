# azlin - Azure Ubuntu VM Provisioning CLI

**One command to create a fully-equipped development VM on Azure**

<div class="grid cards" markdown>

-   :rocket:{ .lg .middle } **Quick Start**

    ---

    Get started in 5 minutes with a fully configured Ubuntu development VM

    [:octicons-arrow-right-24: Getting Started](getting-started/quickstart.md)

-   :material-console:{ .lg .middle } **Command Reference**

    ---

    Complete reference for all 50+ azlin commands

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

azlin automates the tedious process of setting up Azure Ubuntu VMs for development. Written in Rust for blazing-fast startup (75-85x faster than the original Python implementation), it provisions a fully configured VM in one command:

1. Authenticates with Azure
2. Provisions an Ubuntu 24.04 VM
3. Installs 12 essential development tools
4. Sets up SSH with key-based authentication
5. Starts a persistent tmux session
6. Optionally clones a GitHub repository

**Total time**: 4-7 minutes from command to working development environment.

## Quick Example

```bash
# Download pre-built binary (recommended)
curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-linux-x86_64.tar.gz | tar xz -C ~/.local/bin

# Create a VM
azlin new --name myproject

# Fully automated provisioning (zero prompts)
azlin new --name myvm --yes

# Create VM and clone a GitHub repo
azlin new --repo https://github.com/owner/repo

# Keep azlin up to date
azlin self-update
```

## Key Features

### :material-flash: Fast VM Provisioning
Create fully configured development VMs in 4-7 minutes with a single command. Native Rust binary starts in milliseconds.

### :material-tools: 12 Pre-Installed Tools
Every VM includes Docker, Azure CLI, GitHub CLI, Node.js, Python, Rust, Go, .NET, and AI coding assistants (GitHub Copilot CLI, Claude Code, OpenAI Codex CLI).

### :material-monitor: GUI Forwarding
Run graphical applications on your VMs and display them locally. X11 forwarding for lightweight apps, VNC for full desktop sessions.

[:octicons-arrow-right-24: GUI Forwarding Guide](advanced/gui-forwarding.md)

### :material-database: Shared NFS Storage
Create Azure Files NFS storage and mount across multiple VMs for shared data.

### :material-network: Azure Bastion Support
Secure, browser-based SSH access without public IP addresses.

### :material-console-line: Batch Operations
Run commands across entire VM fleets in parallel.

### :material-robot: AI-Powered Features
Natural language VM management with `azlin do` command and autonomous optimization with `azlin autopilot`.

### :material-shield-lock: Secure by Default
SSH key rotation, NFS RootSquash, Azure AD auth for storage, service principal support.

### :material-speedometer: Cost Optimization
Auto-stop idle VMs, quota management, cost tracking and recommendations.

### :material-camera: Snapshots & Backups
Create point-in-time snapshots and schedule automated backups with cross-region replication.

### :material-format-list-group: Compound VM:Session Naming
Address VMs with `hostname:session_name` syntax across all commands for multi-session workflows.

### :material-heart-pulse: Health Dashboard
Real-time monitoring with the Four Golden Signals: latency, traffic, errors, and saturation.

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
    - **.NET** - .NET development framework

=== "AI Tools"

    - **GitHub Copilot CLI** - AI pair programmer
    - **OpenAI Codex CLI** - Advanced AI code generation
    - **Claude Code CLI** - Anthropic's AI coding assistant

## Use Cases

### Development Teams
Share NFS storage and individual VMs for team collaboration.

[:octicons-arrow-right-24: Quick Start](getting-started/quickstart.md)

### CI/CD Runners
Provision ephemeral GitHub Actions runners on demand.

[:octicons-arrow-right-24: GitHub Runners](advanced/github-runners.md)

### Machine Learning
Create GPU-enabled VMs for training workloads.

### Cost Optimization
Auto-stop idle VMs and manage quotas.

[:octicons-arrow-right-24: Cost Tracking](monitoring/cost.md)

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
- **Written in**: Rust (with Python bridge for backward compatibility)
- **Repository**: [rysweet/azlin](https://github.com/rysweet/azlin)
- **Releases**: [GitHub Releases](https://github.com/rysweet/azlin/releases)
- **Version**: 2.6.16

---

*Ready to get started?* Head to the [Quick Start Guide](getting-started/quickstart.md) or dive into [Installation](getting-started/installation.md).
