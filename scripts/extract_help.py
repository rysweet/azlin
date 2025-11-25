#!/usr/bin/env python3
"""Extract Click command help text and generate MkDocs documentation.

This script introspects the azlin Click CLI to generate comprehensive
documentation for all commands, including:
- Command description
- Usage examples
- Options and arguments
- Deep links to source code
"""

import inspect
import re
from pathlib import Path

import click

# We'll dynamically import azlin CLI when available
try:
    from azlin.cli import cli

    AZLIN_AVAILABLE = True
except ImportError:
    AZLIN_AVAILABLE = False
    print("Warning: azlin not installed. Using mock data for structure.")


class HelpExtractor:
    """Extract and format Click command help text."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.repo_base = "https://github.com/rysweet/azlin/blob/main"
        self.commands_generated = []

    def extract_all_commands(self, group: click.Group, prefix: str = "") -> None:
        """Recursively extract all commands from Click group."""
        if not hasattr(group, "commands"):
            return

        for name, cmd in group.commands.items():
            full_name = f"{prefix}{name}" if prefix else name

            if isinstance(cmd, click.Group):
                # Recursively extract subcommands
                self.extract_all_commands(cmd, f"{full_name} ")
            else:
                # Extract single command
                self.extract_command(cmd, full_name)

    def extract_command(self, cmd: click.Command, full_name: str) -> None:
        """Extract documentation for a single command."""
        # Determine output path based on command name
        parts = full_name.split()

        if len(parts) == 1:
            # Top-level command: commands/util/
            output_file = self.output_dir / "util" / f"{parts[0]}.md"
        else:
            # Subcommand: commands/<group>/<command>.md
            group = parts[0]
            command = parts[-1]
            output_file = self.output_dir / group / f"{command}.md"

        # Create parent directory
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Generate documentation
        content = self._generate_markdown(cmd, full_name)

        # Write to file
        output_file.write_text(content)
        self.commands_generated.append(str(output_file.relative_to(self.output_dir)))
        print(f"Generated: {output_file}")

    def _generate_markdown(self, cmd: click.Command, full_name: str) -> str:
        """Generate Markdown documentation for command."""
        parts = full_name.split()
        title = f"azlin {full_name}"

        # Get command help text
        help_text = cmd.help or "No description available."
        help_text = inspect.cleandoc(help_text)

        # Get source code location
        source_link = self._get_source_link(cmd)

        # Extract usage
        ctx = click.Context(cmd)
        usage = cmd.get_usage(ctx).replace("Usage: ", "")

        # Extract options
        options = self._format_options(cmd)

        # Extract examples from help text
        examples = self._extract_examples(help_text)

        # Build markdown
        md = f"""# {title}

## Description

{help_text}

## Usage

```bash
{usage}
```

{options}

{examples}

## See Also

"""

        # Add related commands
        if len(parts) > 1:
            group = parts[0]
            md += f"- [All {group} commands](index.md)\n"

        # Add source link
        if source_link:
            md += f"\n## Source Code\n\n[View source on GitHub]({source_link}){{: .md-button }}\n"

        return md

    def _get_source_link(self, cmd: click.Command) -> str | None:
        """Generate GitHub source link for command."""
        try:
            callback = cmd.callback
            if callback is None:
                return None

            source_file = inspect.getsourcefile(callback)
            if not source_file:
                return None

            line_number = inspect.getsourcelines(callback)[1]

            # Convert to relative path
            source_path = Path(source_file)
            try:
                # Try to get path relative to src/
                rel_path = source_path.relative_to(Path.cwd() / "src")
                return f"{self.repo_base}/src/{rel_path}#L{line_number}"
            except ValueError:
                try:
                    # Try relative to project root
                    rel_path = source_path.relative_to(Path.cwd())
                    return f"{self.repo_base}/{rel_path}#L{line_number}"
                except ValueError:
                    return None
        except Exception:
            return None

    def _format_options(self, cmd: click.Command) -> str:
        """Format command options as Markdown table."""
        if not cmd.params:
            return ""

        md = "## Options\n\n"
        md += "| Option | Type | Description |\n"
        md += "|--------|------|-------------|\n"

        for param in cmd.params:
            if isinstance(param, click.Option):
                opts = ", ".join(f"`{opt}`" for opt in param.opts)
                param_type = self._format_type(param.type)
                help_text = param.help or ""
                help_text = help_text.replace("|", "\\|")  # Escape pipes
                help_text = help_text.replace("\n", " ")  # Remove newlines
                md += f"| {opts} | {param_type} | {help_text} |\n"

        return md + "\n"

    def _format_type(self, param_type: click.ParamType) -> str:
        """Format Click parameter type for display."""
        if isinstance(param_type, click.Choice):
            choices = ", ".join(param_type.choices[:3])
            if len(param_type.choices) > 3:
                choices += ", ..."
            return "Choice"
        if isinstance(param_type, click.Path):
            return "Path"
        if isinstance(param_type, click.IntRange):
            return "Integer"
        return param_type.name.title()

    def _extract_examples(self, help_text: str) -> str:
        """Extract examples section from help text."""
        # Look for EXAMPLES: or Example: section
        patterns = [r"(?:EXAMPLES?|Usage):(.*?)(?=\n\n[A-Z]+:|$)", r"```bash(.*?)```"]

        for pattern in patterns:
            match = re.search(pattern, help_text, re.DOTALL | re.IGNORECASE)
            if match:
                examples_text = match.group(1).strip()
                if examples_text:
                    return f"## Examples\n\n```bash\n{examples_text}\n```\n"

        return ""

    def generate_index_pages(self) -> None:
        """Generate index.md files for command groups."""
        groups: dict[str, list[Path]] = {}

        # Discover all command groups
        for group_dir in self.output_dir.iterdir():
            if group_dir.is_dir() and group_dir.name != "__pycache__":
                commands = [f for f in group_dir.glob("*.md") if f.name != "index.md"]
                if commands:
                    groups[group_dir.name] = sorted(commands)

        # Generate index for each group
        for group_name, commands in groups.items():
            index_file = self.output_dir / group_name / "index.md"

            # Generate index
            title = group_name.title().replace("-", " ").replace("_", " ")
            md = f"""# {title} Commands

## Available Commands

"""

            for cmd_file in commands:
                cmd_name = cmd_file.stem
                # Try to extract first line of description
                try:
                    content = cmd_file.read_text()
                    desc_match = re.search(
                        r"## Description\n\n(.+?)(?:\n\n|\n#)", content, re.DOTALL
                    )
                    desc = desc_match.group(1).strip()[:100] if desc_match else ""
                    if len(desc) >= 100:
                        desc += "..."
                except Exception:
                    desc = ""

                md += f"- [`azlin {group_name} {cmd_name}`]({cmd_name}.md)"
                if desc:
                    md += f" - {desc}"
                md += "\n"

            index_file.write_text(md)
            print(f"Generated index: {index_file}")

    def generate_main_command_index(self) -> None:
        """Generate main commands/index.md with all command groups."""
        index_file = self.output_dir / "index.md"

        md = """# Command Reference

Complete reference for all azlin commands.

## Command Groups

"""

        # List all command group directories
        groups = [
            group_dir.name
            for group_dir in sorted(self.output_dir.iterdir())
            if group_dir.is_dir() and group_dir.name != "__pycache__"
        ]

        for group in groups:
            title = group.title().replace("-", " ").replace("_", " ")
            md += f"- [{title} Commands]({group}/index.md)\n"

        md += """

## Quick Reference

### VM Lifecycle
- `azlin new` - Create a new VM
- `azlin list` - List all VMs
- `azlin connect` - Connect to a VM
- `azlin start` - Start a stopped VM
- `azlin stop` - Stop a running VM
- `azlin destroy` - Delete a VM

### Storage
- `azlin storage create` - Create Azure Files NFS storage
- `azlin storage mount` - Mount storage on VMs
- `azlin storage list` - List all storage accounts

### Monitoring
- `azlin status` - Show VM status
- `azlin w` - Show who is logged in
- `azlin ps` - Show running processes
- `azlin top` - Distributed resource monitoring

### File Transfer
- `azlin cp` - Copy files to/from VMs
- `azlin sync` - Sync home directory

### Environment
- `azlin env set` - Set environment variables
- `azlin env list` - List environment variables
"""

        index_file.write_text(md)
        print(f"Generated main command index: {index_file}")


def create_mock_commands(output_dir: Path) -> None:
    """Create mock command documentation structure when azlin isn't available."""
    print("Creating mock command structure...")

    # Define command groups and their commands
    command_structure = {
        "vm": ["new", "list", "connect", "start", "stop", "destroy", "clone", "update"],
        "storage": ["create", "mount", "unmount", "list", "delete", "status"],
        "env": ["set", "list", "delete", "export", "import", "clear"],
        "snapshot": ["create", "list", "restore", "delete"],
        "auth": ["setup", "test", "list", "show", "remove"],
        "context": ["create", "list", "use", "show", "delete"],
        "batch": ["exec", "sync"],
        "bastion": ["setup", "connect", "status"],
        "util": ["w", "ps", "top", "cost", "logs", "cp", "sync", "code", "help"],
    }

    for group, commands in command_structure.items():
        group_dir = output_dir / group
        group_dir.mkdir(parents=True, exist_ok=True)

        for cmd in commands:
            cmd_file = group_dir / f"{cmd}.md"
            content = f"""# azlin {group} {cmd}

## Description

Command documentation will be generated automatically from the CLI help text.

## Usage

```bash
azlin {group} {cmd} [OPTIONS]
```

## Options

Options will be extracted automatically.

## Examples

Examples will be extracted from command help text.

## See Also

- [All {group} commands](index.md)
"""
            cmd_file.write_text(content)
            print(f"Created mock: {cmd_file}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract Click command help text to Markdown")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs-site/commands"),
        help="Output directory for generated docs",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Create mock command structure (when azlin not installed)",
    )
    args = parser.parse_args()

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    if args.mock or not AZLIN_AVAILABLE:
        # Create mock structure
        create_mock_commands(args.output)
        extractor = HelpExtractor(args.output)
        extractor.generate_index_pages()
        extractor.generate_main_command_index()
    else:
        # Extract from actual CLI
        extractor = HelpExtractor(args.output)
        extractor.extract_all_commands(cli)
        extractor.generate_index_pages()
        extractor.generate_main_command_index()

    print("\n✅ Command documentation generated successfully!")
    print(f"   Output directory: {args.output}")


if __name__ == "__main__":
    main()
