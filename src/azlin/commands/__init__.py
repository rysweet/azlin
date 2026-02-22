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

# Connectivity (split modules - Issue #1799)
from .connect import connect
from .context import context_group
from .costs import cost, costs_group
from .doit import do, doit_group

# Environment
from .env import _get_ssh_config_for_vm, env
from .file_transfer import cp, sync, sync_keys
from .fleet import fleet_group
from .github_runner import github_runner_group
from .ide import code_command

# IP Commands
from .ip_commands import ip

# Keys
from .keys import keys_group

# Lifecycle
from .lifecycle import destroy, kill, killall, prune, start, stop

# Logs
from .logs import logs

# Monitoring (split into focused modules - Issue #423)
from .monitoring_list import get_vm_session_pairs, list_command
from .monitoring_ps import ps
from .monitoring_session import session_command
from .monitoring_status import status
from .monitoring_top import top
from .monitoring_w import w

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
    "get_vm_session_pairs",
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
    # Logs
    "logs",
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
