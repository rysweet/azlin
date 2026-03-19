"""Example manager for loading command examples from YAML files.

This module loads and manages command examples stored in YAML format.
Examples are organized by command name and include title, description,
command, and optional output.

Philosophy:
- Simple YAML loading
- Standard library + PyYAML
- Self-contained and regeneratable
"""

import re
from pathlib import Path

import yaml

from .models import CommandExample, DocumentationError

# Pre-compiled pattern for command name validation (compiled once at import time)
_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class ExampleManager:
    """Manages command examples from YAML files.

    This class loads examples from YAML files organized by command name.
    Each YAML file contains examples for a specific command.
    """

    def __init__(self, examples_dir: str):
        """Initialize example manager.

        Args:
            examples_dir: Directory containing example YAML files
        """
        self.examples_dir = Path(examples_dir)

    def _sanitize_command_name(self, command_name: str) -> str:
        """Sanitize command name to prevent path traversal attacks.

        Args:
            command_name: Raw command name from user input

        Returns:
            Sanitized command name

        Raises:
            ValueError: If command name contains invalid characters

        Example:
            >>> manager = ExampleManager("scripts/examples/")
            >>> manager._sanitize_command_name("mount")
            'mount'
            >>> manager._sanitize_command_name("../etc/passwd")
            Traceback (most recent call last):
            ValueError: Invalid command name: ../etc/passwd
        """
        # Only allow alphanumeric, dash, and underscore
        if not _VALID_NAME_RE.match(command_name):
            raise ValueError(f"Invalid command name: {command_name}")
        return command_name

    def load_examples(self, command_name: str) -> list[CommandExample]:
        """Load examples for a specific command.

        Args:
            command_name: Name of the command (e.g., "mount")

        Returns:
            List of CommandExample objects

        Example:
            >>> manager = ExampleManager("scripts/examples/")
            >>> examples = manager.load_examples("mount")
            >>> for ex in examples:
            ...     print(ex.title)
        """
        # Sanitize command name to prevent path traversal.
        # ValueError propagates to the caller — silent swallowing is #878.
        safe_command_name = self._sanitize_command_name(command_name)

        # Try to find YAML file for this command
        yaml_file = self.examples_dir / f"{safe_command_name}.yaml"

        if not yaml_file.exists():
            # Try with underscores instead of hyphens
            yaml_file = (
                self.examples_dir / f"{safe_command_name.replace('-', '_')}.yaml"
            )

        if not yaml_file.exists():
            return []

        return self._load_from_file(yaml_file)

    def load_all_examples(self) -> dict[str, list[CommandExample]]:
        """Load all examples from the examples directory.

        Returns:
            Dictionary mapping command names to lists of examples

        Example:
            >>> manager = ExampleManager("scripts/examples/")
            >>> all_examples = manager.load_all_examples()
            >>> print(f"Found examples for {len(all_examples)} commands")
        """
        all_examples = {}

        if not self.examples_dir.exists():
            return all_examples

        for yaml_file in self.examples_dir.glob("**/*.yaml"):
            examples = self._load_from_file(yaml_file)
            if examples:
                # Extract command name from first example
                # or use filename
                command_name = yaml_file.stem
                all_examples[command_name] = examples

        return all_examples

    def _load_from_file(self, yaml_file: Path) -> list[CommandExample]:
        """Load examples from a YAML file.

        Args:
            yaml_file: Path to YAML file

        Returns:
            List of CommandExample objects

        YAML format:
            command: command-name
            examples:
              - title: Example title
                description: What it demonstrates
                command: azlin command --option value
                output: |
                  Expected output here
        """
        try:
            with open(yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "examples" not in data:
                return []

            examples = []
            for ex_data in data["examples"]:
                command = ex_data.get("command")
                if not command:
                    raise DocumentationError(
                        f"Example entry in '{yaml_file}' is missing required field 'command'"
                    )
                example = CommandExample(
                    title=ex_data.get("title", ""),
                    description=ex_data.get("description", ""),
                    command=command,
                    output=ex_data.get("output"),
                )
                examples.append(example)

            return examples

        except FileNotFoundError:
            return []
        except DocumentationError:
            raise
        except Exception as e:
            raise DocumentationError(
                f"Failed to load examples for command '{yaml_file.stem}'"
            ) from e

    def save_examples(self, command_name: str, examples: list[CommandExample]) -> bool:
        """Save examples to a YAML file.

        Args:
            command_name: Name of the command
            examples: List of examples to save

        Returns:
            True if save succeeded.

        Raises:
            DocumentationError: If the file cannot be written due to I/O or
                other unexpected errors.

        Example:
            >>> manager = ExampleManager("scripts/examples/")
            >>> examples = [CommandExample(
            ...     title="Basic usage",
            ...     description="Shows basic command",
            ...     command="azlin mount storage",
            ... )]
            >>> manager.save_examples("mount", examples)
            True
        """
        # Sanitize command name to prevent path traversal.
        # ValueError propagates to the caller — consistent with load_examples (#878).
        safe_command_name = self._sanitize_command_name(command_name)

        try:
            yaml_file = self.examples_dir / f"{safe_command_name}.yaml"
            yaml_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "command": command_name,
                "examples": [
                    {
                        "title": ex.title,
                        "description": ex.description,
                        "command": ex.command,
                        "output": ex.output,
                    }
                    for ex in examples
                ],
            }

            with open(yaml_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    data,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

            return True

        except Exception as e:
            raise DocumentationError(
                f"Failed to save examples for '{safe_command_name}': {e}"
            ) from e


__all__ = ["ExampleManager"]
