#!/usr/bin/env python3
"""Extract commands from cli.py into separate modules.

Usage:
    python3 extract_module.py monitoring list status session w top ps
"""
import sys
import re
from pathlib import Path
from typing import List, Tuple, Set

def extract_command_code(cli_path: Path, cmd_name: str) -> Tuple[List[str], int, int]:
    """Extract the code for a specific command including decorators."""
    with open(cli_path, 'r') as f:
        lines = f.readlines()

    # Find the command
    i = 0
    while i < len(lines):
        line = lines[i]
        if '@main.command' in line:
            # Check if this is our command
            decorator_match = re.search(r'name="([^"]+)"', line)

            # Find function definition
            j = i + 1
            while j < len(lines) and 'def ' not in lines[j]:
                j += 1

            if j < len(lines):
                func_match = re.search(r'def (\w+)\(', lines[j])
                if func_match:
                    func_name = func_match.group(1)
                    found_cmd_name = decorator_match.group(1) if decorator_match else func_name

                    if found_cmd_name == cmd_name or func_name == cmd_name:
                        # Found it! Now extract the entire command including decorators
                        start = i

                        # Find end of function
                        k = j + 1
                        indent_level = None
                        paren_depth = 0

                        while k < len(lines):
                            # Stop at next @main.command or main.add_command
                            if k > j and ('@main.command' in lines[k] or 'main.add_command' in lines[k]):
                                break

                            # Track function body
                            if indent_level is None:
                                # Look for first statement in function body
                                stripped = lines[k].strip()
                                if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith("'''"):
                                    # Skip docstring
                                    if '"""' not in lines[k-1] and "'''" not in lines[k-1]:
                                        indent_level = len(lines[k]) - len(lines[k].lstrip())
                            elif indent_level is not None:
                                current_line = lines[k]
                                if current_line.strip():
                                    current_indent = len(current_line) - len(current_line.lstrip())
                                    # Check for dedent (end of function)
                                    if current_indent < indent_level and not current_line.strip().startswith(')'):
                                        break

                            k += 1

                        return lines[start:k], start, k

        i += 1

    raise ValueError(f"Command '{cmd_name}' not found in cli.py")

def find_helper_functions(cli_path: Path) -> List[Tuple[str, List[str], int, int]]:
    """Find all helper functions (non-@main.command functions) in cli.py."""
    with open(cli_path, 'r') as f:
        lines = f.readlines()

    helpers = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for function definitions that aren't Click commands
        if line.startswith('def ') and 'def main(' not in line:
            # Make sure this isn't a Click command
            # Check previous lines for @main.command
            is_command = False
            for j in range(max(0, i-10), i):
                if '@main.command' in lines[j]:
                    is_command = True
                    break

            if not is_command:
                # This is a helper function
                func_match = re.search(r'def (\w+)\(', line)
                if func_match:
                    func_name = func_match.group(1)
                    start = i

                    # Find end of function
                    k = i + 1
                    indent_level = len(line) - len(line.lstrip())

                    while k < len(lines):
                        current_line = lines[k]
                        if current_line.strip():
                            current_indent = len(current_line) - len(current_line.lstrip())
                            # Dedent indicates end of function
                            if current_indent <= indent_level and not current_line.strip().startswith(')'):
                                if current_line.startswith('def ') or current_line.startswith('@') or current_line.startswith('class '):
                                    break
                        k += 1

                    helpers.append((func_name, lines[start:k], start, k))

        i += 1

    return helpers

def analyze_dependencies(code_lines: List[str]) -> Set[str]:
    """Analyze code to find function dependencies."""
    deps = set()
    for line in code_lines:
        # Look for function calls to potential helper functions
        # Match patterns like: function_name( or _function_name(
        matches = re.findall(r'\b([a-z_][a-z0-9_]*)\s*\(', line)
        for match in matches:
            if match.startswith('_') or match[0].islower():
                deps.add(match)
    return deps

def create_module(module_name: str, commands: List[str], cli_path: Path):
    """Create a new command module with extracted commands."""
    module_path = cli_path.parent / 'commands' / f'{module_name}.py'

    print(f"Creating {module_path}...")

    # Extract all specified commands
    all_code = []
    all_deps = set()

    for cmd_name in commands:
        try:
            code, start, end = extract_command_code(cli_path, cmd_name)
            all_code.append((cmd_name, code))

            # Analyze dependencies
            deps = analyze_dependencies(code)
            all_deps.update(deps)

            print(f"  ✓ Extracted {cmd_name} ({end-start} lines)")
        except ValueError as e:
            print(f"  ✗ {e}")

    # Find all helper functions
    print(f"\nFinding helper functions...")
    all_helpers = find_helper_functions(cli_path)

    # Determine which helpers are needed
    needed_helpers = []
    for helper_name, helper_code, start, end in all_helpers:
        if helper_name in all_deps:
            needed_helpers.append((helper_name, helper_code))
            print(f"  ✓ Including helper: {helper_name} ({end-start} lines)")

    # Generate module content
    lines = []

    # Module docstring
    lines.append(f'"""CLI commands for {module_name}.')
    lines.append('')
    lines.append(f'Extracted from cli.py as part of Issue #423 decomposition.')
    lines.append('"""')
    lines.append('')

    # Imports (we'll need to copy these from cli.py)
    lines.append('import click')
    lines.append('from rich.console import Console')
    lines.append('from rich.table import Table')
    lines.append('')
    lines.append('# TODO: Add specific imports based on dependencies')
    lines.append('')

    # Helper functions first
    if needed_helpers:
        lines.append('# Helper functions')
        lines.append('')
        for helper_name, helper_code in needed_helpers:
            lines.extend(helper_code)
            lines.append('')

    # Commands
    lines.append('# Commands')
    lines.append('')

    for cmd_name, code in all_code:
        # Replace @main.command with @click.command
        modified_code = []
        for line in code:
            if '@main.command' in line:
                # Convert to standalone click command
                modified_code.append(line.replace('@main.command', '@click.command'))
            else:
                modified_code.append(line)

        lines.extend(modified_code)
        lines.append('')

    # Write module file
    module_path.parent.mkdir(parents=True, exist_ok=True)
    with open(module_path, 'w') as f:
        f.writelines(lines)

    print(f"\n✅ Created {module_path} ({len(lines)} lines)")
    print(f"   Commands: {', '.join([c for c, _ in all_code])}")
    print(f"   Helpers: {', '.join([h for h, _ in needed_helpers])}")
    print(f"\nNEXT STEPS:")
    print(f"1. Review and fix imports in {module_path}")
    print(f"2. Test the extracted commands")
    print(f"3. Update cli.py to import and register these commands")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 extract_module.py <module_name> <command1> [command2] ...")
        print("\nExample:")
        print("  python3 extract_module.py monitoring list status session w top ps")
        sys.exit(1)

    module_name = sys.argv[1]
    commands = sys.argv[2:]

    cli_path = Path('src/azlin/cli.py')
    if not cli_path.exists():
        print(f"Error: {cli_path} not found")
        sys.exit(1)

    create_module(module_name, commands, cli_path)
