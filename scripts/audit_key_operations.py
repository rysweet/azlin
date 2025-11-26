#!/usr/bin/env python3
"""Audit script for SSH key operations.

Scans Python and shell scripts for unsafe SSH key operations that could
replace authorized_keys file instead of appending to it.

Security requirement: SSH keys must ALWAYS be appended (>>) never replaced (>).

Exit codes:
    0: All operations are safe (append-only)
    1: Unsafe operations detected

Usage:
    python scripts/audit_key_operations.py [directory]
    python scripts/audit_key_operations.py  # Scans current directory
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


# Patterns that indicate UNSAFE operations (file replacement)
UNSAFE_PATTERNS = [
    (r"[^>]>\s*[^\s>]*authorized_keys", "Single > operator (replaces file)"),
    (r"\bcp\s+[^\s]+\s+.*authorized_keys", "cp command (replaces file)"),
    (r"\bmv\s+[^\s]+\s+.*authorized_keys", "mv command (replaces file)"),
    (r"\btee\s+(?!-a).*authorized_keys", "tee without -a flag (replaces)"),
]

# Patterns that are SAFE (these should NOT trigger violations)
SAFE_PATTERNS = [
    r">>\s*.*authorized_keys",  # Append operator
    r"tee\s+-a\s+.*authorized_keys",  # tee with append flag
]


class Violation:
    """Represents a code violation."""

    def __init__(self, file_path: Path, line_num: int, line_content: str, reason: str):
        self.file_path = file_path
        self.line_num = line_num
        self.line_content = line_content.strip()
        self.reason = reason

    def __str__(self) -> str:
        return (
            f"\n{self.file_path}:{self.line_num}\n"
            f"  Reason: {self.reason}\n"
            f"  Code: {self.line_content}"
        )


def is_comment_only(line: str, position: int) -> bool:
    """Check if position in line is within a comment (not a string).

    We want to detect unsafe patterns even in strings because strings
    might contain shell commands that will be executed.
    """
    stripped = line.lstrip()

    # Check for comment lines
    if stripped.startswith(("#", "//")):
        return True

    # Check if position is after # comment marker (not inside string)
    comment_pos = line.find("#")
    if comment_pos != -1 and comment_pos < position:
        before_comment = line[:comment_pos]
        if before_comment.count('"') % 2 == 0 and before_comment.count("'") % 2 == 0:
            return True

    return False


def scan_file(file_path: Path) -> List[Violation]:
    """Scan a single file for unsafe key operations."""
    violations = []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line_num, line in enumerate(lines, start=1):
            if not line.strip():
                continue

            # Skip lines with safe patterns
            if any(re.search(pattern, line) for pattern in SAFE_PATTERNS):
                continue

            # Check each unsafe pattern
            for pattern, reason in UNSAFE_PATTERNS:
                for match in re.finditer(pattern, line):
                    if not is_comment_only(line, match.start()):
                        violations.append(Violation(file_path, line_num, line, reason))

    except Exception as e:
        print(f"Warning: Could not scan {file_path}: {e}", file=sys.stderr)

    return violations


def scan_directory(directory: Path, recursive: bool = True) -> List[Violation]:
    """Scan directory for unsafe key operations."""
    extensions = {".py", ".sh", ".bash"}
    glob_method = directory.rglob if recursive else directory.glob
    files = [f for f in glob_method("*") if f.is_file() and f.suffix in extensions]

    all_violations = []
    for file_path in sorted(files):
        all_violations.extend(scan_file(file_path))

    return all_violations


def main():
    """Main entry point."""
    violations = []

    # If files provided as arguments (pre-commit mode), scan them individually
    if len(sys.argv) > 1:
        files_to_scan = [Path(arg) for arg in sys.argv[1:]]

        # Check if all arguments are files (pre-commit mode)
        if all(f.is_file() for f in files_to_scan if f.exists()):
            # Pre-commit mode: scan individual files
            for file_path in files_to_scan:
                if file_path.suffix in {".py", ".sh", ".bash"}:
                    violations.extend(scan_file(file_path))
        else:
            # Directory mode (original behavior)
            scan_dir = files_to_scan[0]

            if not scan_dir.exists():
                print(f"Error: Directory not found: {scan_dir}", file=sys.stderr)
                sys.exit(1)

            if not scan_dir.is_dir():
                print(f"Error: Not a directory: {scan_dir}", file=sys.stderr)
                sys.exit(1)

            print(f"Auditing SSH key operations in: {scan_dir}")
            print("=" * 70)
            violations = scan_directory(scan_dir, recursive=True)
    else:
        # No arguments: scan current directory
        scan_dir = Path.cwd()
        print(f"Auditing SSH key operations in: {scan_dir}")
        print("=" * 70)
        violations = scan_directory(scan_dir, recursive=True)

    if not violations:
        # Success message (no output needed in pre-commit mode)
        return 0

    # Report violations
    print(f"✗ FAILED: Found {len(violations)} unsafe operation(s)\n")

    for violation in violations:
        print(violation)

    print("\n" + "=" * 70)
    print("SSH keys must ALWAYS use append operator (>>) never replace (>)")
    print("Fix these violations before committing.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
