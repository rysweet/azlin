#!/usr/bin/env python3
"""
Script to fix remaining pyright strict mode errors in azlin codebase.
This handles patterns that are difficult to fix with simple edits.
"""

import re
from pathlib import Path


def fix_cli_none_checks(file_path: Path) -> None:
    """Fix None check patterns in cli.py where pyright doesn't narrow types."""

    content = file_path.read_text()

    # Pattern 1: _setup_github - add public_ip variable after None check
    pattern1 = r'(        if not vm_details\.public_ip:\n            raise GitHubSetupError\("VM has no public IP address"\)\n\n)(        self\.progress\.update)'
    replacement1 = (
        r"\1        public_ip: str = vm_details.public_ip  # Type narrowed by check above\n\n\2"
    )
    content = re.sub(pattern1, replacement1, content)

    # Pattern 1b: Replace vm_details.public_ip with public_ip in _setup_github
    pattern1b = r"(def _setup_github.*?public_ip: str = vm_details\.public_ip.*?)(ssh_config = SSHConfig\(host=)(vm_details\.public_ip)"

    def replace_in_setup_github(match):
        full_match = match.group(0)
        return full_match.replace("SSHConfig(host=vm_details.public_ip", "SSHConfig(host=public_ip")

    content = re.sub(pattern1b, replace_in_setup_github, content, flags=re.DOTALL)

    file_path.write_text(content)
    print(f"Fixed {file_path}")


def fix_protected_method_usage(file_path: Path) -> None:
    """Make _is_valid_ip public by removing underscore prefix."""

    content = file_path.read_text()

    # Replace method definition
    content = content.replace("def _is_valid_ip(self, ip: str)", "def is_valid_ip(self, ip: str)")

    # Replace all usages
    content = content.replace("self._is_valid_ip(", "self.is_valid_ip(")
    content = content.replace("IPValidator._is_valid_ip(", "IPValidator.is_valid_ip(")

    file_path.write_text(content)
    print(f"Fixed protected method in {file_path}")


def fix_missing_type_arguments(file_path: Path) -> None:
    """Add generic type arguments where missing."""

    content = file_path.read_text()

    # Pattern: -> list without type argument at end of line before :
    # Look for function return types
    patterns = [
        (r"-> list\):", "-> list[Any]):"),
        (r"-> dict\):", "-> dict[str, Any]):"),
        (r"-> set\):", "-> set[Any]):"),
        (r": list =", ": list[Any] ="),
        (r": dict =", ": dict[str, Any] ="),
        (r": set =", ": set[Any] ="),
    ]

    for pattern, replacement in patterns:
        if pattern in content:
            content = content.replace(pattern, replacement)
            print(f"  Fixed generic type: {pattern} -> {replacement}")

    file_path.write_text(content)


def main():
    """Main entry point."""

    src_dir = Path(__file__).parent / "src" / "azlin"

    # Fix CLI None checks
    cli_file = src_dir / "cli.py"
    if cli_file.exists():
        print(f"\n=== Fixing {cli_file} ===")
        fix_cli_none_checks(cli_file)
        fix_protected_method_usage(cli_file)

    # Fix all Python files for generic types
    print("\n=== Fixing generic type arguments ===")
    for py_file in src_dir.rglob("*.py"):
        if py_file.name != "__init__.py":
            try:
                fix_missing_type_arguments(py_file)
            except Exception as e:
                print(f"  Warning: Could not process {py_file}: {e}")

    print("\n=== Done ===")
    print("\nRun 'npx pyright' to verify fixes.")


if __name__ == "__main__":
    main()
