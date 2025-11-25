# Installation

Install azlin on your system to start provisioning Azure VMs.

## Prerequisites

Before installing azlin, ensure you have:

### Required

- **Python 3.12 or later** - [Download Python](https://www.python.org/downloads/)
- **Azure CLI** - [Install Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- **Azure Subscription** - [Create free account](https://azure.microsoft.com/free/)

### Optional

- **uv** - Fast Python package installer (recommended)
- **Git** - For cloning repositories

## Installation Methods

=== "Using uvx (Recommended)"

    The fastest way to run azlin without installation:

    ```bash
    uvx --from git+https://github.com/rysweet/azlin azlin new
    ```

    This runs azlin directly from GitHub without installing it permanently.

=== "Using uv"

    Install with uv for a permanent installation:

    ```bash
    # Install uv if not already installed
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Install azlin
    uv tool install git+https://github.com/rysweet/azlin
    ```

=== "Using pip"

    Traditional pip installation:

    ```bash
    pip install git+https://github.com/rysweet/azlin
    ```

=== "From Source"

    For development or customization:

    ```bash
    # Clone repository
    git clone https://github.com/rysweet/azlin.git
    cd azlin

    # Install in development mode
    pip install -e .
    ```

## Verify Installation

Check that azlin is installed correctly:

```bash
# Check version
azlin --version

# Should output: azlin version 0.3.2

# View available commands
azlin --help
```

## Azure CLI Setup

azlin requires Azure CLI to be installed and configured:

### Install Azure CLI

=== "macOS"

    ```bash
    brew install azure-cli
    ```

=== "Linux"

    ```bash
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
    ```

=== "Windows"

    Download from [Microsoft Docs](https://docs.microsoft.com/cli/azure/install-azure-cli-windows)

### Login to Azure

```bash
# Interactive browser login
az login

# Or use device code flow
az login --use-device-code
```

### Verify Azure Access

```bash
# List subscriptions
az account list --output table

# Set default subscription (optional)
az account set --subscription "<subscription-id>"
```

## SSH Client

azlin uses SSH to connect to VMs. SSH is pre-installed on macOS and Linux.

### macOS/Linux

SSH is already installed. Verify:

```bash
ssh -V
# Should output: OpenSSH_X.X
```

### Windows

Windows 10/11 includes OpenSSH by default. Verify:

```powershell
ssh -V
```

If not installed, enable it:
```powershell
# Run as Administrator
Add-WindowsCapability -Online -Name OpenSSH.Client
```

## Optional Tools

### uv (Recommended)

uv is a fast Python package installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### GitHub CLI

For GitHub repository integration:

```bash
# macOS
brew install gh

# Linux
sudo apt install gh

# Windows
winget install GitHub.cli
```

## Troubleshooting Installation

### Issue: `command not found: azlin`

**Solution**: Ensure Python's bin directory is in your PATH:

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$HOME/.local/bin:$PATH"

# Reload shell
source ~/.bashrc  # or ~/.zshrc
```

### Issue: `ModuleNotFoundError: No module named 'azlin'`

**Solution**: Reinstall azlin:

```bash
pip uninstall azlin
pip install git+https://github.com/rysweet/azlin
```

### Issue: `az: command not found`

**Solution**: Install Azure CLI (see above) and ensure it's in your PATH.

### Issue: Permission denied

**Solution**: Don't use `sudo` with pip. Install in user directory:

```bash
pip install --user git+https://github.com/rysweet/azlin
```

## Next Steps

Now that azlin is installed:

1. **[Quick Start →](quickstart.md)** - Create your first VM
2. **[Authentication Setup →](../authentication/index.md)** - Configure Azure authentication
3. **[Basic Concepts →](concepts.md)** - Learn how azlin works

## Updating azlin

To update to the latest version:

```bash
# Using uv
uv tool upgrade azlin

# Using pip
pip install --upgrade git+https://github.com/rysweet/azlin
```

## Uninstalling azlin

To remove azlin:

```bash
# Using uv
uv tool uninstall azlin

# Using pip
pip uninstall azlin
```

---

**Installation complete?** Head to the [Quick Start Guide →](quickstart.md)
