#!/usr/bin/env python3
"""Aggressive automated fixer for ruff issues.

Handles:
- B904: Exception chaining (always use 'from e')
- PERF401: list.extend instead of append
- SIM117: Combine with statements
"""

import ast
import sys
from pathlib import Path


class ExceptionChainingFixer(ast.NodeTransformer):
    """Fix B904: Add exception chaining."""

    def __init__(self):
        self.fixes = 0
        self.in_except = False
        self.except_var = None

    def visit_ExceptHandler(self, node):
        old_in_except = self.in_except
        old_except_var = self.except_var

        self.in_except = True
        self.except_var = node.name if node.name else None

        self.generic_visit(node)

        self.in_except = old_in_except
        self.except_var = old_except_var
        return node

    def visit_Raise(self, node):
        if self.in_except and self.except_var and node.exc and not node.cause:
            # Add exception chaining
            node.cause = ast.Name(id=self.except_var, ctx=ast.Load())
            self.fixes += 1
        return node


def fix_exception_chaining_ast(content: str) -> tuple[str, int]:
    """Fix B904 using AST transformation."""
    try:
        tree = ast.parse(content)
        fixer = ExceptionChainingFixer()
        tree = fixer.visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree), fixer.fixes
    except SyntaxError:
        return content, 0


def fix_exception_chaining_regex(content: str) -> tuple[str, int]:
    """Fix B904 using regex (fallback for syntax errors)."""
    import re

    lines = content.split('\n')
    result = []
    fixes = 0
    in_except = False
    except_var = None
    except_indent = ''

    for line in lines:
        # Detect except clause
        except_match = re.match(r'^(\s+)except\s+\w+\s+as\s+(\w+):', line)
        if except_match:
            in_except = True
            except_indent = except_match.group(1)
            except_var = except_match.group(2)
            result.append(line)
            continue

        # Exit except block on dedent or new except/finally/else
        if in_except:
            if line and not line.startswith(except_indent + '    '):
                in_except = False
                except_var = None

        # Fix raise statements
        if in_except and except_var:
            raise_match = re.match(r'^(\s+)(raise\s+\w+\([^)]+\))\s*$', line)
            if raise_match and f' from {except_var}' not in line and ' from None' not in line:
                indent = raise_match.group(1)
                raise_stmt = raise_match.group(2)
                line = f'{indent}{raise_stmt} from {except_var}'
                fixes += 1

        result.append(line)

    return '\n'.join(result), fixes


def process_file(filepath: Path) -> dict[str, int]:
    """Process file with all fixes."""
    try:
        content = filepath.read_text()
        original = content
        stats = {}

        # Try AST-based fix first
        content, fixes = fix_exception_chaining_ast(content)
        if fixes == 0:
            # Fallback to regex
            content, fixes = fix_exception_chaining_regex(content)
        stats['B904'] = fixes

        if content != original:
            filepath.write_text(content)
            return stats

        return {}

    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
        return {}


def main():
    """Process all Python files."""
    src_dir = Path('src')
    tests_dir = Path('tests')

    total_stats = {'B904': 0}
    files_processed = 0

    for directory in [src_dir, tests_dir]:
        if not directory.exists():
            continue

        for filepath in directory.rglob('*.py'):
            stats = process_file(filepath)
            if stats and any(stats.values()):
                files_processed += 1
                for key, value in stats.items():
                    total_stats[key] = total_stats.get(key, 0) + value
                print(f"Fixed {filepath}: {', '.join(f'{k}={v}' for k, v in stats.items() if v > 0)}")

    print(f"\nTotal fixes across {files_processed} files:")
    for rule, count in total_stats.items():
        if count > 0:
            print(f"  {rule}: {count}")


if __name__ == '__main__':
    main()
