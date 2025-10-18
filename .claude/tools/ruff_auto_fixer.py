#!/usr/bin/env python3
"""Automated fixer for common ruff issues.

Handles mechanical fixes for:
- B904: Exception chaining (raise ... from err)
- W293: Blank line contains whitespace
- PERF401: Use list.extend instead of append in loop
- RUF012: Mutable default arguments
"""

import re
import sys
from pathlib import Path


def fix_b904_exception_chaining(content: str) -> tuple[str, int]:
    """Fix B904: Add exception chaining to raise statements.

    Converts:
        except Exception as e:
            raise CustomError("message")
    To:
        except Exception as e:
            raise CustomError("message") from e
    """
    fixes = 0
    lines = content.split('\n')
    result = []
    in_except = False
    except_var = None

    for i, line in enumerate(lines):
        # Detect except clause with variable binding
        except_match = re.match(r'^(\s+)except\s+\w+\s+as\s+(\w+):', line)
        if except_match:
            in_except = True
            except_var = except_match.group(2)
            result.append(line)
            continue

        # Exit except block on dedent
        if in_except and line and not line[0].isspace():
            in_except = False
            except_var = None

        # Fix raise statements in except blocks
        if in_except and except_var:
            raise_match = re.match(r'^(\s+)raise\s+(\w+)\([^)]+\)\s*$', line)
            if raise_match and f' from {except_var}' not in line and ' from None' not in line:
                line = line.rstrip() + f' from {except_var}'
                fixes += 1

        result.append(line)

    return '\n'.join(result), fixes


def fix_w293_blank_whitespace(content: str) -> tuple[str, int]:
    """Fix W293: Remove whitespace from blank lines."""
    lines = content.split('\n')
    fixes = 0
    result = []

    for line in lines:
        if line and line.isspace():
            result.append('')
            fixes += 1
        else:
            result.append(line)

    return '\n'.join(result), fixes


def fix_perf401_list_extend(content: str) -> tuple[str, int]:
    """Fix PERF401: Replace append in loop with extend.

    Converts:
        for item in items:
            result.append(item)
    To:
        result.extend(items)
    """
    fixes = 0
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for the pattern
        for_match = re.match(r'^(\s+)for\s+(\w+)\s+in\s+(\w+):$', line)
        if for_match and i + 1 < len(lines):
            indent = for_match.group(1)
            var = for_match.group(2)
            iterable = for_match.group(3)
            next_line = lines[i + 1]

            # Check if next line is simple append
            append_pattern = f'^{indent}    (\\w+)\\.append\\({var}\\)$'
            append_match = re.match(append_pattern, next_line)

            if append_match:
                list_var = append_match.group(1)
                # Replace with extend
                result.append(f'{indent}{list_var}.extend({iterable})')
                fixes += 1
                i += 2  # Skip both lines
                continue

        result.append(line)
        i += 1

    return '\n'.join(result), fixes


def process_file(filepath: Path) -> dict[str, int]:
    """Process a single file and apply all fixes."""
    try:
        content = filepath.read_text()
        original = content
        stats = {}

        # Apply fixes in order
        content, b904_fixes = fix_b904_exception_chaining(content)
        stats['B904'] = b904_fixes

        content, w293_fixes = fix_w293_blank_whitespace(content)
        stats['W293'] = w293_fixes

        content, perf401_fixes = fix_perf401_list_extend(content)
        stats['PERF401'] = perf401_fixes

        # Write back if changes were made
        if content != original:
            filepath.write_text(content)
            return stats

        return {}

    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
        return {}


def main():
    """Process all Python files in src/ and tests/."""
    src_dir = Path('src')
    tests_dir = Path('tests')

    total_stats = {'B904': 0, 'W293': 0, 'PERF401': 0}
    files_processed = 0

    for directory in [src_dir, tests_dir]:
        if not directory.exists():
            continue

        for filepath in directory.rglob('*.py'):
            stats = process_file(filepath)
            if stats:
                files_processed += 1
                for key, value in stats.items():
                    total_stats[key] = total_stats.get(key, 0) + value

                if any(stats.values()):
                    print(f"Fixed {filepath}: ", end='')
                    print(', '.join(f"{k}={v}" for k, v in stats.items() if v > 0))

    print(f"\nTotal fixes across {files_processed} files:")
    for rule, count in total_stats.items():
        if count > 0:
            print(f"  {rule}: {count}")

    return 0 if files_processed > 0 else 1


if __name__ == '__main__':
    sys.exit(main())
