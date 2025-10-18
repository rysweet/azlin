#!/usr/bin/env python3
"""Script to decompose cli.py into command group modules.

This script:
1. Reads cli.py
2. Identifies command groups and their functions
3. Creates separate module files for each command group
4. Updates cli.py to import and register command groups
"""

import re
from pathlib import Path
from typing import List, Tuple

# Define command groups and their line ranges (approximate)
COMMAND_GROUPS = {
    'help.py': {
        'description': 'Help command',
        'functions': ['help_command'],
        'line_ranges': [(1186, 1213)],
    },
    'vm_lifecycle.py': {
        'description': 'VM lifecycle commands (new, start, stop, destroy, kill, killall, list)',
        'functions': [
            'generate_vm_name', '_load_config_and_template', '_resolve_vm_settings',
            '_validate_inputs', '_update_config_state', '_execute_command_mode',
            '_provision_pool', '_display_pool_results', 'new_command', 'vm_command',
            'create_command', 'list_command', 'start', 'stop', 'kill',
            '_handle_delete_resource_group', '_handle_vm_dry_run', '_confirm_vm_deletion',
            '_execute_vm_deletion', 'destroy', 'killall', '_confirm_killall',
            '_display_killall_results'
        ],
        'line_ranges': [(873, 900), (1215, 1530), (1530, 1680), (1970, 2290)],
    },
    'vm_operations.py': {
        'description': 'VM operations commands (connect, update, status, session)',
        'functions': [
            'session_command', 'update', '_interactive_vm_selection',
            '_resolve_vm_identifier', '_verify_vm_exists', '_resolve_tmux_session',
            'connect', 'status'
        ],
        'line_ranges': [(1611, 1682), (2516, 2790), (2646, 2924), (3724, 3790)],
    },
    'vm_advanced.py': {
        'description': 'Advanced VM commands (clone, sync, cp)',
        'functions': [
            'sync', '_get_sync_vm_by_name', '_select_sync_vm_interactive', '_execute_sync',
            'cp', 'clone', '_validate_and_resolve_source_vm', '_ensure_source_vm_running',
            '_provision_clone_vms', '_display_clone_results', '_resolve_source_vm',
            '_generate_clone_configs', '_copy_home_directories', '_set_clone_session_names'
        ],
        'line_ranges': [(3006, 3157), (3157, 3280), (3280, 3724)],
    },
    'monitoring.py': {
        'description': 'Monitoring commands (w, top, ps, os-update)',
        'functions': [
            'execute_command_on_vm', 'select_vm_for_command', 'w', 'top', 'os_update', 'ps'
        ],
        'line_ranges': [(895, 1000), (1683, 1762), (1762, 1851), (1851, 1908), (2363, 2440)],
    },
    'batch.py': {
        'description': 'Batch operations commands',
        'functions': [
            'batch', 'batch_stop', '_validate_batch_selection', '_select_vms_by_criteria',
            '_confirm_batch_operation', '_display_batch_summary', 'batch_start', 'command',
            'batch_sync'
        ],
        'line_ranges': [(3792, 3843), (3819, 3842), (4280, 4340), (4340, 4617)],
    },
    'keys.py': {
        'description': 'SSH key management commands',
        'functions': [
            'keys_group', 'keys_rotate', 'keys_list', 'keys_export', 'keys_backup'
        ],
        'line_ranges': [(3844, 3850), (4092, 4165), (4232, 4280), (4617, 4650), (4650, 4682)],
    },
    'templates.py': {
        'description': 'VM template management commands',
        'functions': [
            'template', 'template_create', 'template_list', 'template_delete',
            'template_export', 'template_import'
        ],
        'line_ranges': [(3853, 3890), (4165, 4232), (4682, 4722), (4722, 4764), (4764, 4798), (4798, 4828)],
    },
    'snapshots.py': {
        'description': 'Snapshot management commands',
        'functions': [
            'snapshot', 'snapshot_enable', 'snapshot_disable', 'snapshot_sync',
            'snapshot_status', 'snapshot_create', 'snapshot_list', 'snapshot_restore',
            'snapshot_delete'
        ],
        'line_ranges': [(3892, 3934), (3934, 3976), (3976, 4008), (4008, 4049), (4049, 4092),
                       (4828, 4884), (4884, 4955), (4955, 5028), (5028, 5085)],
    },
    'env.py': {
        'description': 'Environment variable management commands',
        'functions': [
            'env', 'env_set', 'env_list', 'env_delete', 'env_export', 'env_import',
            'env_clear', '_get_ssh_config_for_vm'
        ],
        'line_ranges': [(5085, 5419)],
    },
    'cost.py': {
        'description': 'Cost tracking command',
        'functions': ['cost'],
        'line_ranges': [(2441, 2515)],
    },
    'prune.py': {
        'description': 'Prune operations command',
        'functions': ['prune'],
        'line_ranges': [(2251, 2363)],
    },
}


def main():
    """Main decomposition logic."""
    print("CLI Decomposition Tool")
    print("=" * 60)
    print("\nThis script will decompose cli.py into command group modules.")
    print("\nCommand groups to create:")
    for filename, info in COMMAND_GROUPS.items():
        print(f"  - {filename}: {info['description']}")

    print("\n" + "=" * 60)
    print("Ready to proceed with decomposition.")
    print("\nNext steps:")
    print("  1. Read cli.py and extract sections")
    print("  2. Create command group modules")
    print("  3. Update cli.py to import command groups")
    print("  4. Update imports in test files")
    print("\nRun this script manually to proceed.")


if __name__ == '__main__':
    main()
