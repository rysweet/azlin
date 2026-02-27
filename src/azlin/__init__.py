"""azlin - Azure Ubuntu VM provisioning CLI

Philosophy:
- Ruthless simplicity
- Brick architecture (self-contained modules)
- Security by design (no credentials in code)
- Fail fast with helpful guidance

The azlin CLI automates the creation of Azure Ubuntu VMs with development tools,
SSH connection, and optional GitHub repository setup.

Version 2.0 Features:
- Config storage with TOML (~/.azlin/config.toml)
- VM listing and status management
- Interactive session selection
- Remote command execution
- Parallel VM provisioning (pools)
- Enhanced CLI with subcommands
"""

__version__ = "2.3.0"
__all__ = ["__version__"]
