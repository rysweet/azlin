# Claude Code Installation in VM Provisioning

## Overview

All new azlin VMs automatically install Claude Code during initial provisioning via cloud-init. This ensures developers have immediate access to AI-powered coding assistance when connecting to VMs.

## Installation Method

Claude Code is installed using the official install script:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

This installation:
- Runs during VM creation (cloud-init phase)
- Executes as the `azureuser` user
- Installs Claude Code to `~/.local/bin/claude`
- Automatically adds Claude Code to PATH
- Completes before the VM is accessible via SSH

## Verification

After SSH'ing into a new VM, verify Claude Code is installed:

```bash
claude --version
```

Expected output:
```
Claude Code CLI version X.Y.Z
```

## Usage

Launch Claude Code interactively:

```bash
claude
```

Or use specific commands:

```bash
claude chat
claude code
```

## Troubleshooting

If `claude` command is not found after VM creation:

1. Check if installation completed successfully:
   ```bash
   tail -100 /var/log/cloud-init-output.log | grep -i claude
   ```

2. Verify binary exists:
   ```bash
   ls -la ~/.local/bin/claude
   ```

3. Check PATH configuration:
   ```bash
   echo $PATH | grep .local/bin
   ```

4. If needed, manually add to PATH:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   ```

## Implementation Details

Location: `src/azlin/vm_provisioning.py`
Method: `_generate_cloud_init()`

The installation command is added to the `runcmd` section of the cloud-init YAML, executed after other development tools (Docker, Azure CLI, GitHub CLI, etc.) are installed.
