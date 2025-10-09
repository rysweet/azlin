"""azlin - Azure Ubuntu VM provisioning CLI

Philosophy:
- Ruthless simplicity
- Brick architecture (self-contained modules)
- Security by design (no credentials in code)
- Fail fast with helpful guidance

The azlin CLI automates the creation of Azure Ubuntu VMs with development tools,
SSH connection, and optional GitHub repository setup.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
