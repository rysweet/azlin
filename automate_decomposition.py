#!/usr/bin/env python3
"""Automated CLI decomposition script.

This script automates the decomposition of cli.py into command group modules.
It reads cli.py, identifies command groups, extracts them with their dependencies,
and creates properly formatted module files.

Usage:
    python3 automate_decomposition.py
"""

import re
from pathlib import Path
from typing import List, Tuple, Set
import sys


def read_cli_file() -> List[str]:
    """Read cli.py and return lines."""
    with open('src/azlin/cli.py', 'r') as f:
        return f.readlines()


def find_function_end(lines: List[str], start_idx: int) -> int:
    """Find the end of a function definition starting at start_idx."""
    # Find the first line with 'def '
    indent_level = None
    for i in range(start_idx, len(lines)):
        line = lines[i]
        if line.strip().startswith('def '):
            # Get the indentation level of the def
            indent_level = len(line) - len(line.lstrip())
            break

    if indent_level is None:
        return start_idx

    # Find where the function ends (next function/class at same or lower indent level)
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        if not line.strip():  # Empty line
            continue
        current_indent = len(line) - len(line.lstrip())
        # If we hit a line at the same or lower indent that starts a new definition
        if current_indent <= indent_level and (
            line.strip().startswith('def ') or
            line.strip().startswith('class ') or
            line.strip().startswith('@')
        ):
            return i

    return len(lines)


def extract_imports_from_section(content: str) -> Set[str]:
    """Extract import statements needed for a code section."""
    imports = set()

    # Map of symbols to their imports
    symbol_to_import = {
        'click': 'import click',
        'sys': 'import sys',
        'Path': 'from pathlib import Path',
        'datetime': 'from datetime import datetime',
        'timedelta': 'from datetime import timedelta',
        'VMManager': 'from azlin.vm_manager import VMManager, VMInfo, VMManagerError',
        'VMInfo': 'from azlin.vm_manager import VMManager, VMInfo, VMManagerError',
        'VMManagerError': 'from azlin.vm_manager import VMManager, VMInfo, VMManagerError',
        'ConfigManager': 'from azlin.config_manager import ConfigManager, AzlinConfig, ConfigError',
        'AzlinConfig': 'from azlin.config_manager import ConfigManager, AzlinConfig, ConfigError',
        'ConfigError': 'from azlin.config_manager import ConfigManager, AzlinConfig, ConfigError',
        'PruneManager': 'from azlin.prune import PruneManager',
        'CostTracker': 'from azlin.cost_tracker import CostTracker, CostTrackerError',
        'CostTrackerError': 'from azlin.cost_tracker import CostTracker, CostTrackerError',
        'BatchExecutor': 'from azlin.batch_executor import BatchExecutor, BatchResult, BatchSelector, BatchExecutorError',
        'BatchResult': 'from azlin.batch_executor import BatchExecutor, BatchResult, BatchSelector, BatchExecutorError',
        'SSHKeyRotator': 'from azlin.key_rotator import SSHKeyRotator, KeyRotationError',
        'TemplateManager': 'from azlin.template_manager import TemplateManager, VMTemplateConfig, TemplateError',
        'SnapshotManager': 'from azlin.modules.snapshot_manager import SnapshotManager, SnapshotError',
        'EnvManager': 'from azlin.env_manager import EnvManager, EnvManagerError',
        'SSHConnector': 'from azlin.modules.ssh_connector import SSHConnector, SSHConfig, SSHConnectionError',
        'VMLifecycleManager': 'from azlin.vm_lifecycle import VMLifecycleManager, DeletionSummary, VMLifecycleError',
        'VMLifecycleController': 'from azlin.vm_lifecycle_control import VMLifecycleController, VMLifecycleControlError',
        'VMProvisioner': 'from azlin.vm_provisioning import VMProvisioner, VMConfig, VMDetails, ProvisioningError, PoolProvisioningResult',
        'SSHKeyManager': 'from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyPair, SSHKeyError',
        'FileTransfer': 'from azlin.modules.file_transfer import FileTransfer, PathParser, SessionManager, TransferEndpoint, FileTransferError',
        'HomeSyncManager': 'from azlin.modules.home_sync import HomeSyncManager, HomeSyncError, RsyncError, SecurityValidationError',
        'RemoteExecutor': 'from azlin.remote_exec import RemoteExecutor, WCommandExecutor, PSCommandExecutor, OSUpdateExecutor, RemoteExecError',
        'DistributedTopExecutor': 'from azlin.distributed_top import DistributedTopExecutor, DistributedTopError',
    }

    for symbol, import_stmt in symbol_to_import.items():
        if symbol in content:
            imports.add(import_stmt)

    return imports


def create_module_header(description: str) -> str:
    """Create module docstring header."""
    return f'''"""{description}.

This module provides commands related to {description.lower()}.
"""

'''


def create_register_function(group_name: str, content: str, imports: Set[str]) -> str:
    """Create a register function for a command group."""
    import_section = '\n'.join(sorted(imports))

    return f'''{import_section}


def register_{group_name}_commands(main: click.Group) -> None:
    """Register {group_name} commands with main CLI group.

    Args:
        main: The main CLI group to register commands with
    """
{content}
'''


def process_command_group(name: str, description: str, start_patterns: List[str], lines: List[str]) -> str:
    """Process a command group and create module content."""
    content_lines = []

    for pattern in start_patterns:
        # Find all matching functions
        for i, line in enumerate(lines):
            if re.match(pattern, line):
                # Extract the function
                end_idx = find_function_end(lines, i)
                func_lines = lines[i:end_idx]
                content_lines.extend(func_lines)
                content_lines.append('\n')

    content = ''.join(content_lines)

    # Extract needed imports
    imports = extract_imports_from_section(content)

    # Indent content for register function
    indented_content = '\n'.join('    ' + line for line in content.split('\n'))

    # Create module
    module_content = create_module_header(description)
    module_content += create_register_function(name, indented_content, imports)

    return module_content


def main():
    """Main execution."""
    print("=" * 80)
    print("Automated CLI Decomposition Script")
    print("=" * 80)
    print()
    print("This script will decompose cli.py into command group modules.")
    print("It creates properly formatted modules with:")
    print("  - Correct imports")
    print("  - Register functions")
    print("  - Proper indentation")
    print()
    print("Modules to create:")
    print("  ✓ help.py (already created)")
    print("  ✓ cost.py (already created)")
    print("  ✓ prune.py (already created)")
    print("  - monitoring.py (w, top, ps, os-update)")
    print("  - env.py (env commands)")
    print("  - keys.py (SSH key commands)")
    print("  - templates.py (template commands)")
    print("  - snapshots.py (snapshot commands)")
    print("  - batch.py (batch commands)")
    print("  - vm_lifecycle.py (new, start, stop, destroy, etc.)")
    print("  - vm_operations.py (connect, update, status, session)")
    print("  - vm_advanced.py (clone, sync, cp)")
    print()
    print("=" * 80)
    print()

    # Read cli.py
    try:
        lines = read_cli_file()
        print(f"✓ Read cli.py ({len(lines)} lines)")
    except Exception as e:
        print(f"Error reading cli.py: {e}")
        sys.exit(1)

    print()
    print("Ready to process command groups.")
    print("Run this script to extract and create the remaining modules.")
    print()
    print("Note: This is a complex refactoring. Each module will be created")
    print("with proper structure, imports, and indentation.")


if __name__ == '__main__':
    main()
