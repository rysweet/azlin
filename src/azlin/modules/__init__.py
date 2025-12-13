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
- Parallel Deployer: Deploy VMs to multiple regions concurrently
- Region Failover: Intelligent failover between regions
- Cross Region Sync: Sync data between regions
- Region Context: Region-aware context management
"""

from . import (
    cross_region_sync,
    github_setup,
    interaction_handler,
    key_audit_logger,
    notifications,
    npm_config,
    parallel_deployer,
    prerequisites,
    progress,
    region_context,
    region_failover,
    ssh_connector,
    ssh_keys,
)

__all__ = [
    "cross_region_sync",
    "github_setup",
    "interaction_handler",
    "key_audit_logger",
    "notifications",
    "npm_config",
    "parallel_deployer",
    "prerequisites",
    "progress",
    "region_context",
    "region_failover",
    "ssh_connector",
    "ssh_keys",
]
