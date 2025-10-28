#!/usr/bin/env python3
"""Script to batch-replace duplicated assertions with helper functions."""

import re
from pathlib import Path

# Define replacements
replacements = [
    # Pattern 1: assert "no such option" not in result.output.lower()
    (
        r'assert "no such option" not in result\.output\.lower\(\)',
        'assert_option_accepted(result)'
    ),
    # Pattern 2: assert result.exit_code == 0 (when testing help or success)
    # We'll handle these more carefully in the script

    # Pattern 3: assert result.exit_code != 0 followed by assert "no such option"
    (
        r'assert result\.exit_code != 0\s+assert "no such option" in result\.output\.lower\(\)',
        'assert_option_rejected(result, "<option>")'
    ),

    # Pattern 4: Tautologies already fixed manually

    # Pattern 5: assert result.exit_code != 0 assert "missing argument"
    (
        r'assert result\.exit_code != 0\s+assert "missing argument" in result\.output\.lower\(\) or "usage:" in result\.output\.lower\(\)',
        'assert_missing_argument_error(result)'
    ),
]

def process_file(file_path: Path):
    """Process a single test file."""
    content = file_path.read_text()
    original = content

    # Pattern 1: Replace standalone "no such option not in"
    content = re.sub(
        r'assert "no such option" not in result\.output\.lower\(\)',
        'assert_option_accepted(result)',
        content
    )

    # Pattern 2: Replace "no such option" not in AND missing argument
    content = re.sub(
        r'assert "no such option" not in result\.output\.lower\(\)\s*\n\s*assert "missing argument" not in result\.output\.lower\(\)',
        'assert_option_accepted(result)',
        content
    )

    # Pattern 3: Missing argument errors
    content = re.sub(
        r'assert result\.exit_code != 0\s*\n\s*assert "missing argument" in result\.output\.lower\(\) or "usage:" in result\.output\.lower\(\)',
        'assert_missing_argument_error(result)',
        content
    )

    if content != original:
        file_path.write_text(content)
        print(f"Updated {file_path.name}")
        return True
    return False

def main():
    test_dir = Path("tests/unit/cli")
    files_updated = 0

    for file_path in test_dir.glob("test_*.py"):
        if process_file(file_path):
            files_updated += 1

    print(f"\nProcessed {files_updated} files")

if __name__ == "__main__":
    main()
