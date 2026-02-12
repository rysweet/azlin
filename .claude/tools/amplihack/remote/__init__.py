"""Remote execution module for amplihack.

This module enables executing amplihack commands on remote Azure VMs
using azlin for provisioning and management.

Public API:
    - execute_remote_workflow: Main workflow orchestration
    - ContextPackager: Package project context
    - Orchestrator: VM lifecycle management
    - Executor: Remote command execution
    - Integrator: Result integration
    - Error classes: All remote execution errors

Example:
    >>> from amplihack.remote import execute_remote_workflow
    >>> from pathlib import Path
    >>>
    >>> execute_remote_workflow(
    ...     repo_path=Path.cwd(),
    ...     command='auto',
    ...     prompt='implement feature X',
    ...     max_turns=10,
    ...     vm_options=VMOptions(),
    ...     timeout=120
    ... )
"""

from .cli import execute_remote_workflow, main
from .context_packager import ContextPackager, SecretMatch
from .errors import (
    CleanupError,
    ExecutionError,
    IntegrationError,
    PackagingError,
    ProvisioningError,
    RemoteExecutionError,
    TransferError,
)
from .executor import ExecutionResult, Executor
from .integrator import BranchInfo, IntegrationSummary, Integrator
from .orchestrator import VM, Orchestrator, VMOptions
from .vm_pool import VMPoolEntry, VMPoolManager, VMSize

__all__ = [
    # Data classes
    "VM",
    "BranchInfo",
    "CleanupError",
    # Core components
    "ContextPackager",
    "ExecutionError",
    "ExecutionResult",
    "Executor",
    "IntegrationError",
    "IntegrationSummary",
    "Integrator",
    "Orchestrator",
    "PackagingError",
    "ProvisioningError",
    # Errors
    "RemoteExecutionError",
    "SecretMatch",
    "TransferError",
    "VMOptions",
    "VMPoolEntry",
    "VMPoolManager",
    "VMSize",
    # Main entry points
    "execute_remote_workflow",
    "main",
]

__version__ = "0.1.0"
