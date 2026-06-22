# Installation

Install azlin on your system to start provisioning Azure VMs.

## Prerequisites

### Required

- **Azure CLI** - [Install Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- **Azure Subscription** - [Create free account](https://azure.microsoft.com/free/)

### Optional

- **Python 3.11+** - Only needed if using the Python bridge (`azlin-py`) or `uvx`
- **Cargo** - Only needed if building from source
- **Git** - For cloning repositories

## Installation Methods

=== "Pre-Built Binary (Recommended)"

    Download the native Rust binary for instant startup:

    ```bash
    # Linux x86_64
    curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-linux-x86_64.tar.gz | tar xz -C ~/.local/bin

    # Linux aarch64
    curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-linux-aarch64.tar.gz | tar xz -C ~/.local/bin

    # macOS x86_64
    curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-macos-x86_64.tar.gz | tar xz -C /usr/local/bin

    # macOS aarch64 (Apple Silicon)
    curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-macos-aarch64.tar.gz | tar xz -C /usr/local/bin
    ```

=== "Build from Source (Cargo)"

    Build from source with the Rust toolchain:

    ```bash
    cargo install --git https://github.com/rysweet/azlin
    ```

=== "Using uvx (No Install)"

    Run directly from GitHub without installing (requires Python and uv):

    ```bash
    uvx --from git+https://github.com/rysweet/azlin azlin new
    ```

    This runs azlin via the Python bridge. For best performance, use the pre-built binary.

=== "Using pip"

    Install the Python bridge permanently:

    ```bash
    pip install git+https://github.com/rysweet/azlin
    ```

    Note: This installs the Python bridge which routes to the native Rust binary if available, or falls back to the Python implementation (`azlin-py`).

## Verify Installation

Check that azlin is installed correctly:

```bash
# Check version
azlin --version

# View available commands
azlin --help
```

## Self-Update

azlin can update itself to the latest release:

```bash
azlin self-update
```

This downloads and replaces the binary with the latest version from GitHub Releases.

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

## Troubleshooting Installation

### Issue: `command not found: azlin`

**Solution**: Ensure the binary location is in your PATH:

```bash
# For pre-built binary in ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# Add to ~/.bashrc or ~/.zshrc for persistence
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Issue: `az: command not found`

**Solution**: Install Azure CLI (see above) and ensure it's in your PATH.

### Issue: Permission denied downloading binary

**Solution**: Ensure the target directory exists and is writable:

```bash
mkdir -p ~/.local/bin
```

## Next Steps

Now that azlin is installed:

1. **[Quick Start →](quickstart.md)** - Create your first VM
2. **[Authentication Setup →](../authentication/service-principal.md)** - Configure Azure authentication
3. **[Basic Concepts →](concepts.md)** - Learn how azlin works

---

**Installation complete?** Head to the [Quick Start Guide →](quickstart.md)
