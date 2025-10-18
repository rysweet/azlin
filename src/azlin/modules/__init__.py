"""azlin modules - Self-contained bricks following the brick philosophy

Each module is a self-contained component with clear contracts:
- Prerequisites Checker: Verify required tools
- Azure Auth Handler: Handle Azure authentication
- SSH Key Manager: Generate and manage SSH keys
- VM Provisioner: Create Azure VMs with dev tools
- SSH Connector: Connect via SSH and start tmux
- GitHub Setup Handler: Clone repo on VM
- npm Configurator: Configure npm for user-local installations
- Progress Display: Show real-time progress
- Notification Handler: Send optional notifications
"""

__all__ = [
    "github_setup",
    "notifications",
    "npm_config",
    "prerequisites",
    "progress",
    "ssh_connector",
    "ssh_keys",
]
