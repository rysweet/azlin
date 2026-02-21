"""Connectivity commands (compatibility shim).

DEPRECATED: This module has been split into focused modules:
- connectivity_common.py - Shared helpers
- connect.py - SSH connection command
- file_transfer.py - File copy and sync commands
- ide.py - VS Code Remote launcher

This compatibility shim re-exports commands for backward compatibility.
Issue #1799
"""

# Re-export all commands for backward compatibility
from .connect import connect
from .file_transfer import cp, sync, sync_keys
from .ide import code_command

__all__ = [
    "code_command",
    "connect",
    "cp",
    "sync",
    "sync_keys",
]
