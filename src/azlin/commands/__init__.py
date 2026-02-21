"""Command modules for azlin CLI.

This package contains modular command implementations organized by functionality.
"""

from __future__ import annotations

# Additional command groups
from .ask import ask_command, ask_group
from .auth import auth as auth_group
from .autopilot import autopilot_group
from .bastion import bastion_group

# Batch
from .batch import batch
from .compose import compose_group

# Connectivity
from .connectivity import code_command, connect, cp, sync, sync_keys
from .context import context_group
from .costs import cost, costs_group
from .doit import do, doit_group

# Environment
from .env import _get_ssh_config_for_vm, env
from .fleet import fleet_group
from .github_runner import github_runner_group

# IP Commands
from .ip_commands import ip

# Keys
from .keys import keys_group

# Lifecycle
from .lifecycle import destroy, kill, killall, prune, start, stop

# Monitoring
from .monitoring import list_command, ps, session_command, status, top, w

# NLP
from .nlp import azdoit_main

# Provisioning
from .provisioning import clone, create, new, vm
from .restore import restore_command
from .sessions import session_group

# Snapshots
from .snapshots import snapshot
from .storage import storage_group
from .system import help_command, os_update, update
from .tag import tag_group

# Templates
from .templates import template

# Web
from .web import web

__all__ = [
    # Environment
    "_get_ssh_config_for_vm",
    # Additional command groups
    "ask_command",
    "ask_group",
    "auth_group",
    "autopilot_group",
    # NLP
    "azdoit_main",
    "bastion_group",
    # Batch
    "batch",
    # Lifecycle
    "clone",
    # Connectivity
    "code_command",
    "compose_group",
    "connect",
    "context_group",
    "cost",
    "costs_group",
    "cp",
    "create",
    "destroy",
    "do",
    "doit_group",
    "env",
    "fleet_group",
    "github_runner_group",
    # System
    "help_command",
    # IP Commands
    "ip",
    # Keys
    "keys_group",
    "kill",
    "killall",
    # Monitoring
    "list_command",
    "new",
    # System
    "os_update",
    "prune",
    "ps",
    "restore_command",
    "session_command",
    "session_group",
    # Snapshots
    "snapshot",
    "start",
    "status",
    "stop",
    "storage_group",
    "sync",
    "sync_keys",
    "tag_group",
    # Templates
    "template",
    "top",
    # System
    "update",
    "vm",
    "w",
    # Web
    "web",
]
