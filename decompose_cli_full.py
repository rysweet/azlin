#!/usr/bin/env python3
"""Full CLI decomposition script.

This script reads cli.py, extracts command groups, and creates separate module files.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple


def extract_section(content: List[str], start_line: int, end_line: int) -> List[str]:
    """Extract lines from content (1-indexed)."""
    return content[start_line-1:end_line]


def find_imports_needed(section_content: str) -> set:
    """Identify imports needed for a section."""
    imports = set()

    # Look for references to common modules
    patterns = {
        'click': r'click\.',
        'sys': r'\bsys\.',
        'Path': r'\bPath\b',
        'VMManager': r'\bVMManager\b',
        'ConfigManager': r'\bConfigManager\b',
        'VMInfo': r'\bVMInfo\b',
        'AzlinConfig': r'\bAzlinConfig\b',
        'ConfigError': r'\bConfigError\b',
        'VMManagerError': r'\bVMManagerError\b',
    }

    for module, pattern in patterns.items():
        if re.search(pattern, section_content):
            imports.add(module)

    return imports


def create_prune_module():
    """Create prune.py module."""
    print("Creating commands/prune.py...")

    # Read cli.py
    with open('src/azlin/cli.py', 'r') as f:
        lines = f.readlines()

    # Extract prune command (lines 2251-2363)
    prune_section = ''.join(lines[2250:2363])

    content = '''"""Prune operations command for azlin CLI.

This module provides the prune command for cleaning up idle VMs.
"""

import sys
from datetime import datetime, timedelta

import click

from azlin.config_manager import ConfigManager
from azlin.prune import PruneManager
from azlin.vm_manager import VMInfo, VMManager, VMManagerError


def register_prune_command(main: click.Group) -> None:
    """Register prune command with main CLI group.

    Args:
        main: The main CLI group to register commands with
    """

''' + prune_section.replace('@main.command()', '    @main.command()')

    # Indent the entire function
    lines_to_indent = content.split('\n')
    indented = []
    in_function = False
    for line in lines_to_indent:
        if line.strip().startswith('@main.command'):
            in_function = True
            indented.append(line)
        elif in_function and not line.startswith('    ') and line.strip():
            # Add extra indent for function body
            indented.append('    ' + line)
        else:
            indented.append(line)

    with open('src/azlin/commands/prune.py', 'w') as f:
        f.write('\n'.join(indented))

    print("  ✓ commands/prune.py created")


def main():
    """Main execution."""
    print("=" * 70)
    print("CLI Decomposition Script")
    print("=" * 70)

    # Create prune module as test
    create_prune_module()

    print("\n" + "=" * 70)
    print("Phase 1 complete: Sample module created")
    print("\nNext: Review prune.py and create remaining modules")


if __name__ == '__main__':
    main()
