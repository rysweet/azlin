#!/usr/bin/env python3
"""Script to systematically fix PR #191 review feedback issues.

This script addresses:
1. Remove --help from option validation tests
2. Replace overly permissive exit code assertions
3. Replace code duplication with helper functions
4. Use cli_runner fixture consistently
"""

import re
from pathlib import Path

# Test file paths
TEST_DIR = Path(__file__).parent / "tests" / "unit" / "cli"
TEST_FILES = [
    TEST_DIR / "test_command_syntax.py",
    TEST_DIR / "test_command_syntax_priority2.py",
    TEST_DIR / "test_command_syntax_priority3.py",
    TEST_DIR / "test_command_syntax_priority4.py",
]


def remove_help_from_option_tests(content: str) -> str:
    """Remove --help from option validation tests where it prevents actual testing."""

    # Pattern 1: Single line with --help at end
    # Example: result = runner.invoke(main, ["new", "--repo", "url", "--help"])
    # Replace with: result = runner.invoke(main, ["new", "--repo", "url"])
    pattern1 = r'(result = runner\.invoke\(main, \[([^\]]+)\], "--help"\]\))'

    def replace1(match):
        args_part = match.group(2)
        # Only replace if this is testing an option (not a help test itself)
        if '--help' in args_part or '"help"' in args_part:
            return match.group(0)  # Keep help tests unchanged
        return f'result = runner.invoke(main, [{args_part}])'

    content = re.sub(pattern1, replace1, content)

    # Pattern 2: Multi-line with --help at end
    # More complex - need to remove --help line
    lines = content.split('\n')
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this is an invoke call that might have --help
        if 'runner.invoke(main,' in line:
            # Collect the full invoke statement
            invoke_lines = [line]
            bracket_count = line.count('[') - line.count(']')
            j = i + 1

            while j < len(lines) and (bracket_count > 0 or not lines[j-1].rstrip().endswith(')')):
                invoke_lines.append(lines[j])
                bracket_count += lines[j].count('[') - lines[j].count(']')
                if ')' in lines[j]:
                    break
                j += 1

            # Check if this is an option test (not a help test)
            full_invoke = '\n'.join(invoke_lines)
            is_help_test = 'def test_' in ''.join(result_lines[-5:]) and 'help' in ''.join(result_lines[-5:]).lower()

            if not is_help_test and '"--help"' in full_invoke:
                # Remove the --help argument
                # Find the line with --help and remove it
                new_invoke_lines = []
                for invoke_line in invoke_lines:
                    if '"--help"' in invoke_line and invoke_line.strip() == '"--help",':
                        continue  # Skip this line
                    elif '"--help"' in invoke_line:
                        # Remove just the --help part
                        new_invoke_lines.append(invoke_line.replace(', "--help"', '').replace('"--help",', ''))
                    else:
                        new_invoke_lines.append(invoke_line)

                result_lines.extend(new_invoke_lines)
                i = j
            else:
                result_lines.extend(invoke_lines)
                i = j
        else:
            result_lines.append(line)

        i += 1

    return '\n'.join(result_lines)


def replace_permissive_assertions(content: str) -> str:
    """Replace overly permissive exit code assertions with specific ones."""

    # Pattern: assert result.exit_code in [0, 1, 2, 4]
    # Replace with more specific assertions based on context

    # For config file tests: [0, 2, 4] -> [0, 2]
    content = re.sub(
        r'assert result\.exit_code in \[0, 2, 4\], \(\s*f?"Expected exit code 0 \(success\), 2 \(bad parameter\), or 4 \(runtime error\)',
        'assert result.exit_code in [0, 2], (\n            f"Expected exit code 0 (success with defaults) or 2 (parameter error)',
        content,
        flags=re.MULTILINE
    )

    return content


def replace_duplicate_assertions(content: str) -> str:
    """Replace duplicate assertion patterns with helper functions."""

    # Pattern 1: assert result.exit_code == 0
    # When testing option acceptance, use assert_option_accepted(result)
    # But keep for help tests

    # Pattern 2: Replace direct exit_code checks after option tests
    # This is contextual and harder to automate, so we'll be conservative

    # Look for patterns like:
    # assert result.exit_code == 0
    # Following an invoke with options (not --help)

    lines = content.split('\n')
    result_lines = []

    for i, line in enumerate(lines):
        # Check if this is a simple success assertion
        if line.strip() == 'assert result.exit_code == 0':
            # Look back to see if this is after an option test
            context = '\n'.join(lines[max(0, i-10):i])

            # If we see invoke with options (not help test), replace
            if 'runner.invoke(main,' in context and 'def test_' in context:
                # Check if this is a help test
                is_help_test = any('help' in lines[j].lower() for j in range(max(0, i-5), i) if 'def test_' in lines[j])

                if not is_help_test and '--help' not in context[-200:]:
                    result_lines.append(line.replace('assert result.exit_code == 0', 'assert_option_accepted(result)'))
                else:
                    result_lines.append(line)
            else:
                result_lines.append(line)
        else:
            result_lines.append(line)

    return '\n'.join(result_lines)


def use_cli_runner_fixture(content: str) -> str:
    """Replace 'runner = CliRunner()' with cli_runner fixture usage."""

    # This requires modifying function signatures, which is complex
    # For now, we'll just document it needs manual review
    # The fixture is already available in conftest.py

    return content


def main():
    """Main function to apply all fixes."""

    for test_file in TEST_FILES:
        if not test_file.exists():
            print(f"Skipping {test_file} - not found")
            continue

        print(f"Processing {test_file.name}...")

        # Read the file
        content = test_file.read_text()

        # Apply fixes
        original_content = content

        # 1. Remove --help from option tests
        content = remove_help_from_option_tests(content)

        # 2. Replace permissive assertions
        content = replace_permissive_assertions(content)

        # 3. Replace duplicate assertions (conservative)
        # content = replace_duplicate_assertions(content)  # Commented out - too risky for automation

        # 4. CLI runner fixture - manual review needed
        # content = use_cli_runner_fixture(content)

        if content != original_content:
            # Backup original
            backup_file = test_file.with_suffix('.py.backup')
            backup_file.write_text(original_content)
            print(f"  - Created backup: {backup_file.name}")

            # Write updated content
            test_file.write_text(content)
            print(f"  - Updated {test_file.name}")
        else:
            print(f"  - No changes needed for {test_file.name}")

    print("\n✓ Automated fixes complete!")
    print("\nManual review needed for:")
    print("  - Verify all --help removals are appropriate")
    print("  - Review exit code assertions for specificity")
    print("  - Consider using cli_runner fixture consistently")


if __name__ == "__main__":
    main()
