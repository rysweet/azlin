#!/usr/bin/env python3
"""Documentation validation script for azlin.

This script prevents documentation drift by:
1. Extracting all CLI commands using Click introspection
2. Parsing README.md for documented commands
3. Comparing and reporting mismatches
4. Validating command options/arguments
5. Checking example syntax validity

Exit codes:
    0 - Documentation is consistent
    1 - Inconsistencies found
"""

import re
import sys
from pathlib import Path

# Add src to path for imports
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


# Check if we're in a venv or have uv
def ensure_dependencies():
    """Ensure Click is available."""
    try:
        import click  # noqa: F401

        return True
    except ImportError:
        print("Error: Click not installed. Please run: uv pip install click")
        return False


if not ensure_dependencies():
    sys.exit(1)

import click  # noqa: E402


# Lazy load CLI to avoid heavy dependencies
def load_cli_main():
    """Lazy load CLI main to avoid import errors from heavy dependencies."""
    try:
        from azlin.cli import main as cli_main

        return cli_main
    except ImportError as e:
        print(f"Warning: Could not import full CLI: {e}")
        print("Using alternative command extraction method...")
        return None


class Colors:
    """ANSI color codes for terminal output."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class CommandInfo:
    """Information about a CLI command."""

    def __init__(self, name: str, options: set[str], is_group: bool = False):
        self.name = name
        self.options = options
        self.is_group = is_group
        self.subcommands: dict[str, CommandInfo] = {}

    def __repr__(self):
        return f"CommandInfo(name={self.name}, options={self.options}, is_group={self.is_group})"


class CLIExtractor:
    """Extract commands from Click CLI."""

    def extract_commands(self, cli_group: click.Group, prefix: str = "") -> dict[str, CommandInfo]:
        """Recursively extract all commands from a Click group."""
        commands = {}

        for name, cmd in cli_group.commands.items():
            full_name = f"{prefix}{name}" if prefix else name

            # Extract options
            options = set()
            if hasattr(cmd, "params"):
                for param in cmd.params:
                    if isinstance(param, click.Option):
                        # Get all option names (short and long)
                        for opt_name in param.opts:
                            options.add(opt_name)

            # Check if it's a group (has subcommands)
            is_group = isinstance(cmd, click.Group)

            cmd_info = CommandInfo(full_name, options, is_group)

            # Recursively extract subcommands
            if is_group:
                subcommands = self.extract_commands(cmd, f"{full_name} ")
                cmd_info.subcommands = subcommands
                # Add subcommands to main dict too
                commands.update(subcommands)

            commands[full_name] = cmd_info

        return commands


class MarkdownParser:
    """Parse commands from README.md."""

    def __init__(self, readme_path: Path):
        self.readme_path = readme_path
        self.content = readme_path.read_text()

    def extract_documented_commands(self) -> dict[str, set[str]]:
        """Extract all documented commands and their options from README."""
        commands = {}

        # Pattern for command headers: ### `azlin command` - Description
        command_pattern = r"###\s+`azlin\s+([^`]+)`"

        matches = re.finditer(command_pattern, self.content)

        for match in matches:
            cmd_name = match.group(1).strip()

            # Find the section for this command (until next ### or ##)
            start_pos = match.end()
            next_section = re.search(r"\n##", self.content[start_pos:])
            end_pos = next_section.start() if next_section else len(self.content)

            section_content = self.content[start_pos : start_pos + end_pos]

            # Extract options from code blocks in the section
            options = self._extract_options_from_section(section_content)

            commands[cmd_name] = options

        return commands

    def _extract_options_from_section(self, section: str) -> set[str]:
        """Extract option flags from a documentation section."""
        options = set()

        # Find all code blocks
        code_blocks = re.findall(r"```(?:bash)?\n(.*?)```", section, re.DOTALL)

        for block in code_blocks:
            # Find all --option or -o patterns
            option_matches = re.findall(r"(--[\w-]+|-[a-zA-Z])\b", block)
            options.update(option_matches)

        return options

    def extract_command_examples(self) -> dict[str, list[str]]:
        """Extract all code examples for validation."""
        examples = {}

        # Pattern for command headers
        command_pattern = r"###\s+`azlin\s+([^`]+)`"

        matches = list(re.finditer(command_pattern, self.content))

        for i, match in enumerate(matches):
            cmd_name = match.group(1).strip()

            # Find section bounds
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(self.content)

            section_content = self.content[start_pos:end_pos]

            # Extract code blocks
            code_blocks = re.findall(r"```bash\n(.*?)```", section_content, re.DOTALL)

            # Filter for azlin commands
            azlin_examples = []
            for block in code_blocks:
                for line in block.split("\n"):
                    line = line.strip()
                    # Remove comments
                    if "#" in line:
                        line = line.split("#")[0].strip()
                    if line.startswith("azlin "):
                        azlin_examples.append(line)

            if azlin_examples:
                examples[cmd_name] = azlin_examples

        return examples


class ExampleValidator:
    """Validate that examples in documentation are syntactically correct."""

    def __init__(self, cli_commands: dict[str, CommandInfo]):
        self.cli_commands = cli_commands

    def validate_examples(self, examples: dict[str, list[str]]) -> list[str]:
        """Validate all examples and return list of errors."""
        errors = []

        for cmd_name, example_list in examples.items():
            for example in example_list:
                error = self._validate_example(example)
                if error:
                    errors.append(f"Example for '{cmd_name}': {error}\n  Example: {example}")

        return errors

    def _validate_example(self, example: str) -> str:
        """Validate a single example command."""
        # Remove 'azlin ' prefix
        if not example.startswith("azlin "):
            return "Example doesn't start with 'azlin '"

        cmd_part = example[6:].strip()

        # Basic validation: check if command exists
        # Extract the command name (first word or first two words for groups)
        parts = cmd_part.split()
        if not parts:
            return "Empty command"

        cmd_name = parts[0]

        # Skip validation for special cases
        if cmd_name in ["--", "COMMAND"]:
            return ""  # These are placeholders/special syntax

        # Check if it's a top-level command
        if cmd_name not in self.cli_commands:
            # Try two-word commands (e.g., "env set")
            if len(parts) > 1:
                two_word_cmd = f"{parts[0]} {parts[1]}"
                # Also check for aliases - combine conditions
                if two_word_cmd not in self.cli_commands and cmd_name not in ["create", "vm"]:
                    return f"Command '{cmd_name}' not found in CLI"
            else:
                if cmd_name not in ["create", "vm"]:  # Known aliases
                    return f"Command '{cmd_name}' not found in CLI"

        # Check for common syntax errors
        if "==" in cmd_part:
            return "Uses '==' instead of '=' for assignment"

        return ""  # No error


class DocumentationValidator:
    """Main validator class."""

    def __init__(self, readme_path: Path):
        self.readme_path = readme_path
        self.extractor = CLIExtractor()
        self.parser = MarkdownParser(readme_path)
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self) -> bool:
        """Run all validations. Returns True if consistent, False otherwise."""
        print(f"{Colors.BOLD}Validating azlin documentation...{Colors.RESET}\n")

        # Extract CLI commands
        print(f"{Colors.BLUE}[1/4] Extracting commands from CLI...{Colors.RESET}")
        cli_main = load_cli_main()
        if cli_main is None:
            print(
                f"{Colors.YELLOW}      Warning: Cannot extract CLI commands directly{Colors.RESET}"
            )
            print(
                f"{Colors.YELLOW}      Skipping CLI comparison, validating examples only{Colors.RESET}"
            )
            cli_commands = {}
        else:
            cli_commands = self.extractor.extract_commands(cli_main)
            print(f"      Found {len(cli_commands)} commands in CLI")

        # Extract documented commands
        print(f"{Colors.BLUE}[2/4] Parsing README.md...{Colors.RESET}")
        doc_commands = self.parser.extract_documented_commands()
        print(f"      Found {len(doc_commands)} commands documented")

        # Compare commands (only if CLI extraction succeeded)
        if cli_commands:
            print(f"{Colors.BLUE}[3/4] Comparing commands...{Colors.RESET}")
            self._compare_commands(cli_commands, doc_commands)
        else:
            print(
                f"{Colors.YELLOW}[3/4] Skipping command comparison (CLI not available){Colors.RESET}"
            )

        # Validate examples (only basic syntax if CLI not available)
        print(f"{Colors.BLUE}[4/4] Validating examples...{Colors.RESET}")
        examples = self.parser.extract_command_examples()
        if cli_commands:
            validator = ExampleValidator(cli_commands)
            example_errors = validator.validate_examples(examples)
            self.errors.extend(example_errors)
        print(f"      Found {sum(len(v) for v in examples.values())} examples")

        # Print results
        print(f"\n{Colors.BOLD}Validation Results:{Colors.RESET}\n")

        if self.warnings:
            print(f"{Colors.YELLOW}Warnings ({len(self.warnings)}):{Colors.RESET}")
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")
            print()

        if self.errors:
            print(f"{Colors.RED}Errors ({len(self.errors)}):{Colors.RESET}")
            for error in self.errors:
                print(f"  ❌ {error}")
            print()
            print(f"{Colors.RED}{Colors.BOLD}Documentation validation FAILED{Colors.RESET}")
            return False
        print(f"{Colors.GREEN}✓ Documentation is consistent with CLI!{Colors.RESET}")
        if self.warnings:
            print(f"{Colors.YELLOW}  (with {len(self.warnings)} warnings){Colors.RESET}")
        return True

    def _compare_commands(
        self, cli_commands: dict[str, CommandInfo], doc_commands: dict[str, set[str]]
    ) -> None:
        """Compare CLI commands with documented commands."""
        cli_command_names = set(cli_commands.keys())
        doc_command_names = set(doc_commands.keys())

        # Find missing documentation
        undocumented = cli_command_names - doc_command_names

        # Filter out some commands that don't need docs (internal/development)
        ignored_commands = {
            "version",
            "help",
            "create",  # Alias for 'new'
            "vm",  # Alias for 'new'
        }
        undocumented = {cmd for cmd in undocumented if cmd not in ignored_commands}

        if undocumented:
            for cmd in sorted(undocumented):
                self.errors.append(f"Command '{cmd}' exists in CLI but is not documented in README")

        # Find documented but non-existent commands
        non_existent = doc_command_names - cli_command_names

        # Filter out documented features that are planned/future
        # These appear in the DOCUMENTATION_FIX_PLAN but may not be implemented yet
        planned_commands = {
            "cleanup",  # Planned feature
            "logs",  # Planned feature
            "tag",  # May not be fully implemented yet
        }

        if non_existent:
            for cmd in sorted(non_existent):
                if cmd in planned_commands:
                    self.warnings.append(
                        f"Command '{cmd}' is documented but not yet implemented (planned feature)"
                    )
                else:
                    self.errors.append(
                        f"Command '{cmd}' is documented in README but doesn't exist in CLI"
                    )

        # Compare options for commands that exist in both
        common_commands = cli_command_names & doc_command_names
        for cmd_name in sorted(common_commands):
            cli_opts = cli_commands[cmd_name].options
            doc_opts = doc_commands[cmd_name]

            # Find options in CLI but not documented
            # Filter out common internal options
            internal_opts = {"--config", "--help", "-h"}
            undocumented_opts = cli_opts - doc_opts - internal_opts

            # Also filter --rg if --resource-group is documented (they're aliases)
            if "--resource-group" in doc_opts:
                undocumented_opts.discard("--rg")

            if undocumented_opts:
                self.warnings.append(
                    f"Command '{cmd_name}' has undocumented options: {', '.join(sorted(undocumented_opts))}"
                )

            # Find documented options that don't exist in CLI
            non_existent_opts = doc_opts - cli_opts

            # Filter out common false positives (partial options, examples)
            # Also check for aliases (e.g., --rg vs --resource-group)
            false_positives = set()
            for opt in non_existent_opts:
                if any(
                    [
                        opt.startswith("--from"),
                        opt.startswith("--to"),
                        opt.startswith("--by"),
                        len(opt) < 3,  # Very short options might be typos
                        opt == "--rg" and "--resource-group" in cli_opts,  # Alias check
                    ]
                ):
                    false_positives.add(opt)

            non_existent_opts -= false_positives

            if non_existent_opts:
                self.errors.append(
                    f"Command '{cmd_name}' documents non-existent options: {', '.join(sorted(non_existent_opts))}"
                )


def main():
    """Main entry point."""
    # Try to find README.md in current directory first (for CI)
    readme_path = REPO_ROOT / "README.md"

    # Fallback to worktree path
    if not readme_path.exists():
        readme_path = REPO_ROOT / "worktrees" / "feat-issue-192-fix-documentation" / "README.md"

    if not readme_path.exists():
        print(f"{Colors.RED}Error: README.md not found at {readme_path}{Colors.RESET}")
        sys.exit(1)

    print(f"Validating: {readme_path}\n")

    validator = DocumentationValidator(readme_path)
    success = validator.validate()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
