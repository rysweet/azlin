"""CLI metadata extraction from Click commands.

This module extracts metadata from Click command definitions using runtime
inspection. It loads Click commands and extracts their options, arguments,
help text, and other metadata needed for documentation generation.

Philosophy:
- Runtime inspection of Click commands
- Standard library + Click only
- Self-contained and regeneratable
"""

import importlib
import sys

import click

from .models import CLIArgument, CLIMetadata, CLIOption


class CLIExtractor:
    """Extracts metadata from Click commands.

    This class uses runtime inspection to extract command metadata from
    Click decorators and function signatures.
    """

    # Whitelist of allowed modules to prevent arbitrary code execution
    ALLOWED_MODULES = [
        "azlin.cli",
        "azlin.storage",
        "azlin.context",
    ]

    def extract_command(self, module_path: str, command_name: str) -> CLIMetadata | None:
        """Extract metadata from a single command.

        Args:
            module_path: Python module path (e.g., "azlin.cli")
            command_name: Name of the Click command to extract

        Returns:
            CLIMetadata object or None if command not found

        Example:
            >>> extractor = CLIExtractor()
            >>> metadata = extractor.extract_command("azlin.cli", "storage")
            >>> print(metadata.name)
            'storage'
        """
        try:
            # Validate module path against whitelist
            if module_path not in self.ALLOWED_MODULES:
                print(
                    f"Warning: Module '{module_path}' not in whitelist. "
                    f"Allowed modules: {', '.join(self.ALLOWED_MODULES)}",
                    file=sys.stderr,
                )
                return None

            # Import the module
            module = importlib.import_module(module_path)

            # Find the command
            command = getattr(module, command_name, None)
            if command is None or not isinstance(command, click.Command):
                return None

            return self._extract_from_click_command(command)

        except Exception as e:
            # Log error but fail gracefully
            print(f"Warning: Failed to extract command '{command_name}': {e}", file=sys.stderr)
            return None

    def extract_all_commands(self, module_path: str) -> list[CLIMetadata]:
        """Extract metadata from all commands in a module.

        Args:
            module_path: Python module path (e.g., "azlin.cli")

        Returns:
            List of CLIMetadata objects for all found commands

        Example:
            >>> extractor = CLIExtractor()
            >>> commands = extractor.extract_all_commands("azlin.cli")
            >>> for cmd in commands:
            ...     print(cmd.name)
        """
        try:
            # Validate module path against whitelist
            if module_path not in self.ALLOWED_MODULES:
                print(
                    f"Warning: Module '{module_path}' not in whitelist. "
                    f"Allowed modules: {', '.join(self.ALLOWED_MODULES)}",
                    file=sys.stderr,
                )
                return []

            module = importlib.import_module(module_path)
            commands = []

            # Inspect all module attributes
            for name in dir(module):
                attr = getattr(module, name)

                # Check if it's a Click command or group
                if isinstance(attr, (click.Command, click.Group)):
                    metadata = self._extract_from_click_command(attr)
                    if metadata:
                        commands.append(metadata)

            return commands

        except Exception as e:
            # Log error but fail gracefully
            print(
                f"Warning: Failed to extract commands from module '{module_path}': {e}",
                file=sys.stderr,
            )
            return []

    def _extract_from_click_command(
        self, command: click.Command, parent_path: str = ""
    ) -> CLIMetadata | None:
        """Extract metadata from a Click command object.

        Args:
            command: Click command or group
            parent_path: Path of parent commands (e.g., "storage")

        Returns:
            CLIMetadata object
        """
        try:
            name = command.name or ""
            full_path = f"{parent_path} {name}".strip() if parent_path else name

            # Extract help text and description
            help_text = command.help or ""
            docstring = self._get_docstring(command)
            description = self._extract_description(docstring)

            # Extract arguments
            arguments = self._extract_arguments(command)

            # Extract options
            options = self._extract_options(command)

            # Extract subcommands if it's a group
            subcommands = []
            if isinstance(command, click.Group):
                for subcmd_name in command.list_commands(None):
                    subcmd = command.get_command(None, subcmd_name)
                    if subcmd:
                        sub_metadata = self._extract_from_click_command(subcmd, full_path)
                        if sub_metadata:
                            subcommands.append(sub_metadata)

            return CLIMetadata(
                name=name,
                full_path=full_path,
                help_text=help_text or description.split("\n")[0],
                description=description,
                arguments=arguments,
                options=options,
                subcommands=subcommands,
            )

        except Exception as e:
            # Log error but fail gracefully
            command_name = getattr(command, "name", "unknown")
            print(
                f"Warning: Failed to extract metadata from command '{command_name}': {e}",
                file=sys.stderr,
            )
            return None

    def _get_docstring(self, command: click.Command) -> str:
        """Extract docstring from command callback function."""
        if command.callback and command.callback.__doc__:
            return command.callback.__doc__.strip()
        return ""

    def _extract_description(self, docstring: str) -> str:
        """Extract description from docstring.

        Args:
            docstring: Full docstring text

        Returns:
            Cleaned description text
        """
        if not docstring:
            return ""

        # Split into lines and clean
        lines = docstring.split("\n")
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()
            # Stop at common docstring section markers
            if stripped.lower().startswith(
                ("args:", "arguments:", "returns:", "raises:", "example:")
            ):
                break
            if stripped:
                cleaned_lines.append(stripped)

        return "\n".join(cleaned_lines)

    def _extract_arguments(self, command: click.Command) -> list[CLIArgument]:
        """Extract positional arguments from Click command."""
        arguments = []

        for param in command.params:
            if isinstance(param, click.Argument):
                arg = CLIArgument(
                    name=param.name,
                    type=self._get_param_type(param),
                    required=param.required,
                    help_text=param.help or "",
                )
                arguments.append(arg)

        return arguments

    def _extract_options(self, command: click.Command) -> list[CLIOption]:
        """Extract options and flags from Click command."""
        options = []

        for param in command.params:
            if isinstance(param, click.Option):
                # Get option names (both long and short forms)
                names = list(param.opts) if param.opts else []

                option = CLIOption(
                    names=names,
                    type=self._get_param_type(param),
                    default=param.default,
                    required=param.required,
                    help_text=param.help or "",
                    is_flag=param.is_flag,
                )
                options.append(option)

        return options

    def _get_param_type(self, param: click.Parameter) -> str:
        """Get string representation of parameter type."""
        if param.is_flag:
            return "FLAG"

        param_type = param.type
        if isinstance(param_type, click.STRING):
            return "TEXT"
        if isinstance(param_type, click.INT):
            return "INT"
        if isinstance(param_type, click.FLOAT):
            return "FLOAT"
        if isinstance(param_type, click.BOOL):
            return "BOOL"
        if isinstance(param_type, click.Path):
            return "PATH"
        if isinstance(param_type, click.Choice):
            choices = "|".join(param_type.choices) if param_type.choices else ""
            return f"CHOICE({choices})"
        return "TEXT"


__all__ = ["CLIExtractor"]
