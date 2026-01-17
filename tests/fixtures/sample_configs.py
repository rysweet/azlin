"""
Sample configuration files for testing.

This module provides sample azlin configuration files and data
for testing configuration loading, validation, and merging.
"""

from typing import Any

# ============================================================================
# COMPLETE CONFIGURATIONS
# ============================================================================

MINIMAL_CONFIG: dict[str, Any] = {"vm": {"size": "Standard_D2s_v3", "region": "eastus"}}


COMPLETE_CONFIG: dict[str, Any] = {
    "vm": {
        "name": "dev-vm",
        "size": "Standard_D2s_v3",
        "region": "eastus",
        "image": "ubuntu-24.04",
        "resource_group": "azlin-rg",
        "admin_username": "azureuser",
    },
    "tools": ["git", "gh", "python3", "node", "docker", "tmux", "vim", "zsh", "fzf"],
    "ssh": {
        "key_path": "~/.ssh/azlin_rsa",
        "key_type": "rsa",
        "key_size": 4096,
        "auto_connect": True,
        "connection_timeout": 300,
    },
    "tmux": {"session_name": "dev", "auto_attach": True, "config_file": "~/.tmux.conf"},
    "github": {"auto_clone": True, "setup_gh_auth": True, "default_branch": "main"},
    "notifications": {
        "imessr_enabled": True,
        "imessr_endpoint": "https://imessr.example.com/api/send",
    },
    "azure": {
        "subscription_id": "12345678-1234-1234-1234-123456789012",
        "tenant_id": "87654321-4321-4321-4321-210987654321",
    },
}


CONFIG_WITH_CUSTOM_TOOLS: dict[str, Any] = {
    "vm": {"size": "Standard_D4s_v3", "region": "westus2"},
    "tools": [
        "git",
        "gh",
        "python3",
        "poetry",
        "rust",
        "cargo",
        "tmux",
        "neovim",
        "ripgrep",
        "fd-find",
        "bat",
        "exa",
    ],
    "tool_config": {
        "python": {"version": "3.11", "packages": ["pytest", "black", "ruff"]},
        "rust": {"install_method": "rustup"},
    },
}


CONFIG_WITHOUT_GITHUB: dict[str, Any] = {
    "vm": {"size": "Standard_D2s_v3", "region": "eastus"},
    "tools": ["git", "python3", "docker", "tmux"],
    "github": {"auto_clone": False, "setup_gh_auth": False},
}


# ============================================================================
# INVALID CONFIGURATIONS
# ============================================================================

INVALID_VM_SIZE_CONFIG: dict[str, Any] = {"vm": {"size": "InvalidSize", "region": "eastus"}}


INVALID_REGION_CONFIG: dict[str, Any] = {
    "vm": {"size": "Standard_D2s_v3", "region": "invalid-region"}
}


MISSING_REQUIRED_FIELDS_CONFIG: dict[str, Any] = {
    "vm": {
        "size": "Standard_D2s_v3"
        # Missing 'region'
    }
}


INVALID_TOOLS_CONFIG: dict[str, Any] = {
    "vm": {"size": "Standard_D2s_v3", "region": "eastus"},
    "tools": "git,python3,docker",  # Should be list, not string
}


# ============================================================================
# CONFIGURATION FILES (YAML/JSON FORMAT)
# ============================================================================

MINIMAL_CONFIG_YAML = """
vm:
  size: Standard_D2s_v3
  region: eastus
"""


COMPLETE_CONFIG_YAML = """
vm:
  name: dev-vm
  size: Standard_D2s_v3
  region: eastus
  image: ubuntu-24.04
  resource_group: azlin-rg
  admin_username: azureuser

tools:
  - git
  - gh
  - python3
  - node
  - docker
  - tmux
  - vim
  - zsh
  - fzf

ssh:
  key_path: ~/.ssh/azlin_rsa
  key_type: rsa
  key_size: 4096
  auto_connect: true
  connection_timeout: 300

tmux:
  session_name: dev
  auto_attach: true
  config_file: ~/.tmux.conf

github:
  auto_clone: true
  setup_gh_auth: true
  default_branch: main

notifications:
  imessr_enabled: true
  imessr_endpoint: https://imessr.example.com/api/send

azure:
  subscription_id: 12345678-1234-1234-1234-123456789012
  tenant_id: 87654321-4321-4321-4321-210987654321
"""


MINIMAL_CONFIG_JSON = """{
  "vm": {
    "size": "Standard_D2s_v3",
    "region": "eastus"
  }
}"""


COMPLETE_CONFIG_JSON = """{
  "vm": {
    "name": "dev-vm",
    "size": "Standard_D2s_v3",
    "region": "eastus",
    "image": "ubuntu-24.04",
    "resource_group": "azlin-rg",
    "admin_username": "azureuser"
  },
  "tools": [
    "git",
    "gh",
    "python3",
    "node",
    "docker",
    "tmux",
    "vim",
    "zsh",
    "fzf"
  ],
  "ssh": {
    "key_path": "~/.ssh/azlin_rsa",
    "key_type": "rsa",
    "key_size": 4096,
    "auto_connect": true,
    "connection_timeout": 300
  },
  "tmux": {
    "session_name": "dev",
    "auto_attach": true,
    "config_file": "~/.tmux.conf"
  },
  "github": {
    "auto_clone": true,
    "setup_gh_auth": true,
    "default_branch": "main"
  },
  "notifications": {
    "imessr_enabled": true,
    "imessr_endpoint": "https://imessr.example.com/api/send"
  },
  "azure": {
    "subscription_id": "12345678-1234-1234-1234-123456789012",
    "tenant_id": "87654321-4321-4321-4321-210987654321"
  }
}"""


# ============================================================================
# ENVIRONMENT VARIABLE OVERRIDES
# ============================================================================

ENV_VAR_OVERRIDES = {
    "AZLIN_VM_SIZE": "Standard_D4s_v3",
    "AZLIN_VM_REGION": "westus2",
    "AZLIN_RESOURCE_GROUP": "custom-rg",
    "AZLIN_SSH_KEY_PATH": "~/.ssh/custom_key",
    "AZLIN_AUTO_CONNECT": "false",
    "AZLIN_IMESSR_ENABLED": "true",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_config(
    vm_size: str = "Standard_D2s_v3",
    region: str = "eastus",
    tools: list | None = None,
    auto_connect: bool = True,
    auto_clone: bool = True,
) -> dict[str, Any]:
    """Create a custom configuration with specified parameters.

    Args:
        vm_size: Azure VM size
        region: Azure region
        tools: List of tools to install (defaults to standard 9 tools)
        auto_connect: Whether to auto-connect via SSH
        auto_clone: Whether to auto-clone GitHub repo

    Returns:
        Configuration dictionary
    """
    if tools is None:
        tools = ["git", "gh", "python3", "node", "docker", "tmux", "vim", "zsh", "fzf"]

    return {
        "vm": {"size": vm_size, "region": region},
        "tools": tools,
        "ssh": {"auto_connect": auto_connect},
        "github": {"auto_clone": auto_clone},
    }
