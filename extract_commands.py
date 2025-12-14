#!/usr/bin/env python3
"""Script to help extract commands from cli.py into separate modules.

This script analyzes cli.py and generates the structure for command modules.
"""

import re
from pathlib import Path


def find_command_boundaries(filepath: Path) -> list[tuple[str, int, int]]:
    """Find all @main.command functions and their line ranges."""
    with open(filepath) as f:
        lines = f.readlines()

    commands = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "@main.command" in line:
            # Get command name
            cmd_match = re.search(r'name="([^"]+)"', line)

            # Find function definition
            j = i + 1
            while j < len(lines) and "def " not in lines[j]:
                j += 1

            if j < len(lines):
                func_match = re.search(r"def (\w+)\(", lines[j])
                if func_match:
                    func_name = func_match.group(1)
                    cmd_name = cmd_match.group(1) if cmd_match else func_name

                    # Find end of function (next @main.command or main.add_command)
                    k = j + 1
                    indent_level = None
                    while k < len(lines):
                        if "@main.command" in lines[k] or "main.add_command" in lines[k]:
                            break
                        # Track indentation to find function end
                        if (
                            indent_level is None
                            and lines[k].strip()
                            and not lines[k].strip().startswith("#")
                        ):
                            # First non-empty line after def sets the indent
                            indent_level = len(lines[k]) - len(lines[k].lstrip())
                        elif indent_level is not None and lines[k].strip():
                            current_indent = len(lines[k]) - len(lines[k].lstrip())
                            if current_indent < indent_level and not lines[k].strip().startswith(
                                ")"
                            ):
                                # Dedented - end of function
                                break
                        k += 1

                    commands.append((cmd_name, func_name, i, k))
                    i = k
                    continue
        i += 1

    return commands


def categorize_commands(commands: list[tuple[str, int, int]]) -> dict:
    """Categorize commands into logical groups."""

    monitoring = ["list", "status", "session", "w", "top", "ps"]
    lifecycle = ["start", "stop", "kill", "destroy", "killall", "clone"]
    connectivity = ["connect", "code", "cp", "sync"]
    admin = ["prune", "update", "os-update", "cost"]
    provisioning = ["new", "vm", "create"]
    special = ["do", "help"]

    categories = {
        "monitoring": [],
        "lifecycle": [],
        "connectivity": [],
        "admin": [],
        "provisioning": [],
        "special": [],
        "uncategorized": [],
    }

    for cmd_info in commands:
        cmd_name = cmd_info[0]

        if cmd_name in monitoring:
            categories["monitoring"].append(cmd_info)
        elif cmd_name in lifecycle:
            categories["lifecycle"].append(cmd_info)
        elif cmd_name in connectivity:
            categories["connectivity"].append(cmd_info)
        elif cmd_name in admin:
            categories["admin"].append(cmd_info)
        elif cmd_name in provisioning:
            categories["provisioning"].append(cmd_info)
        elif cmd_name in special:
            categories["special"].append(cmd_info)
        else:
            categories["uncategorized"].append(cmd_info)

    return categories


if __name__ == "__main__":
    cli_path = Path("src/azlin/cli.py")
    commands = find_command_boundaries(cli_path)

    print("Commands found in cli.py:")
    print("=" * 80)
    for cmd_name, func_name, start, end in commands:
        print(f"{cmd_name:20} -> {func_name:25} (lines {start + 1}-{end}, {end - start} lines)")

    print(f"\nTotal: {len(commands)} commands")
    print("=" * 80)

    categories = categorize_commands(commands)

    print("\nCommand Categories:")
    print("=" * 80)
    for category, cmds in categories.items():
        if cmds:
            print(f"\n{category.upper()} ({len(cmds)} commands):")
            total_lines = sum(end - start for _, _, start, end in cmds)
            print(f"  Total lines: ~{total_lines}")
            for cmd_name, func_name, start, end in cmds:
                print(f"  - {cmd_name:15} ({end - start:4} lines)")
