"""Markdown documentation generator from CLI metadata.

This module generates markdown documentation from CLIMetadata objects.
It creates structured, consistent documentation following the project's
documentation format.

Philosophy:
- Simple string formatting (no Jinja2)
- Standard library only
- Self-contained and regeneratable
"""

from .models import CLIArgument, CLIMetadata, CLIOption, CommandExample


class DocGenerator:
    """Generates markdown documentation from CLI metadata.

    This class takes CLIMetadata objects and generates formatted markdown
    documentation suitable for MkDocs or other documentation systems.
    """

    def generate(self, metadata: CLIMetadata, examples: list[CommandExample] | None = None) -> str:
        """Generate complete markdown documentation for a command.

        Args:
            metadata: CLI metadata extracted from command
            examples: List of command examples to include

        Returns:
            Formatted markdown string

        Example:
            >>> generator = DocGenerator()
            >>> markdown = generator.generate(metadata, examples)
            >>> print(markdown)
        """
        examples = examples or []

        sections = []

        # Header
        sections.append(self._generate_header(metadata))

        # Description
        if metadata.description:
            sections.append("## Description\n")
            sections.append(metadata.description)
            sections.append("")

        # Usage
        sections.append(self._generate_usage(metadata))

        # Arguments
        if metadata.arguments:
            sections.append(self._generate_arguments(metadata.arguments))

        # Options
        if metadata.options:
            sections.append(self._generate_options(metadata.options))

        # Subcommands
        if metadata.subcommands:
            sections.append(self._generate_subcommands(metadata.subcommands))

        # Examples
        if examples:
            sections.append(self._generate_examples(examples))

        return "\n".join(sections)

    def _generate_header(self, metadata: CLIMetadata) -> str:
        """Generate command header."""
        # Use full_path for nested commands (e.g., "storage mount")
        # Otherwise use name
        command_path = metadata.full_path or metadata.name
        header = f"# azlin {command_path}\n"

        if metadata.help_text:
            header += f"\n{metadata.help_text}\n"

        return header

    def _generate_usage(self, metadata: CLIMetadata) -> str:
        """Generate usage section."""
        usage_parts = ["azlin", metadata.full_path or metadata.name]

        # Add arguments
        for arg in metadata.arguments:
            if arg.required:
                usage_parts.append(arg.name.upper())
            else:
                usage_parts.append(f"[{arg.name.upper()}]")

        # Add options placeholder
        if metadata.options:
            usage_parts.append("[OPTIONS]")

        usage_line = " ".join(usage_parts)

        return f"## Usage\n\n```bash\n{usage_line}\n```\n"

    def _generate_arguments(self, arguments: list[CLIArgument]) -> str:
        """Generate arguments section."""
        lines = ["## Arguments\n"]

        for arg in arguments:
            arg_name = arg.name.upper()
            required = "" if arg.required else " (optional)"
            help_text = arg.help_text or "No description available"
            lines.append(f"- `{arg_name}` - {help_text}{required}")

        lines.append("")
        return "\n".join(lines)

    def _generate_options(self, options: list[CLIOption]) -> str:
        """Generate options section."""
        lines = ["## Options\n"]

        for opt in options:
            # Format option names (e.g., "--config, -c")
            opt_names = ", ".join(f"`{name}`" for name in opt.names)

            # Type info
            type_info = ""
            if not opt.is_flag:
                type_info = f" {opt.type}"

            # Default value
            default_info = ""
            if opt.default is not None and not opt.is_flag:
                default_info = f" (default: `{opt.default}`)"

            # Required marker
            required_info = " **[required]**" if opt.required else ""

            # Help text
            help_text = opt.help_text or "No description available"

            lines.append(f"- {opt_names}{type_info}{default_info}{required_info} - {help_text}")

        lines.append("")
        return "\n".join(lines)

    def _generate_subcommands(self, subcommands: list[CLIMetadata]) -> str:
        """Generate subcommands section."""
        lines = ["## Subcommands\n"]

        for subcmd in subcommands:
            lines.append(f"### {subcmd.name}\n")
            if subcmd.help_text:
                lines.append(f"{subcmd.help_text}\n")

            # Usage for subcommand
            if subcmd.arguments or subcmd.options:
                usage_parts = ["azlin", subcmd.full_path]
                usage_parts.extend(arg.name.upper() for arg in subcmd.arguments)
                if subcmd.options:
                    usage_parts.append("[OPTIONS]")

                usage = " ".join(usage_parts)
                lines.append("**Usage:**")
                lines.append(f"```bash\n{usage}\n```\n")

            # Subcommand options
            if subcmd.options:
                lines.append("**Options:**")
                for opt in subcmd.options:
                    opt_names = ", ".join(f"`{name}`" for name in opt.names)
                    help_text = opt.help_text or "No description"
                    lines.append(f"- {opt_names} - {help_text}")
                lines.append("")

        return "\n".join(lines)

    def _generate_examples(self, examples: list[CommandExample]) -> str:
        """Generate examples section."""
        lines = ["## Examples\n"]

        for example in examples:
            # Example title
            lines.append(f"### {example.title}\n")

            # Description
            if example.description:
                lines.append(f"{example.description}\n")

            # Command
            lines.append("```bash")
            lines.append(example.command)
            lines.append("```\n")

            # Output
            if example.output:
                lines.append("**Output:**")
                lines.append("```")
                lines.append(example.output.strip())
                lines.append("```\n")

        return "\n".join(lines)


__all__ = ["DocGenerator"]
