"""Data models for CLI documentation sync system.

This module defines the core data structures used throughout the
CLI documentation system for representing command metadata, options,
arguments, and examples.

Philosophy:
- Ruthlessly simple dataclasses
- Standard library only
- Self-contained and regeneratable
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CLIArgument:
    """Represents a positional command argument.

    Attributes:
        name: Argument name (e.g., "environment")
        type: Type string (TEXT, INT, PATH, etc.)
        required: Whether the argument is required
        help_text: Help description for the argument
    """

    name: str
    type: str = "TEXT"
    required: bool = True
    help_text: str = ""


@dataclass
class CLIOption:
    """Represents a command option or flag.

    Attributes:
        names: List of option names (e.g., ["--config", "-c"])
        type: Type string (TEXT, INT, FLAG, etc.)
        default: Default value if not provided
        required: Whether the option is required
        help_text: Help description for the option
        is_flag: Whether this is a boolean flag
    """

    names: list[str]
    type: str = "TEXT"
    default: Any = None
    required: bool = False
    help_text: str = ""
    is_flag: bool = False

    @property
    def primary_name(self) -> str:
        """Return the primary (longest) option name."""
        return max(self.names, key=len) if self.names else ""

    @property
    def short_name(self) -> str | None:
        """Return the short option name if available."""
        short_opts = [n for n in self.names if len(n) == 2 and n.startswith("-")]
        return short_opts[0] if short_opts else None


@dataclass
class CommandExample:
    """Represents a documented usage example.

    Attributes:
        title: Brief title describing the example
        description: Detailed explanation of what it demonstrates
        command: Full command string with arguments
        output: Expected output (optional)
    """

    title: str
    description: str
    command: str
    output: str | None = None


@dataclass
class CLIMetadata:
    """Complete metadata for a CLI command.

    Attributes:
        name: Command name
        full_path: Full command path for nested commands (e.g., "storage mount")
        help_text: Brief description (first line of docstring)
        description: Complete description from docstring
        arguments: List of positional arguments
        options: List of options and flags
        subcommands: List of subcommand metadata
        examples: List of command examples
        source_file: Path to source file containing the command
    """

    name: str
    full_path: str
    help_text: str
    description: str
    arguments: list[CLIArgument] = field(default_factory=list)
    options: list[CLIOption] = field(default_factory=list)
    subcommands: list["CLIMetadata"] = field(default_factory=list)
    examples: list[CommandExample] = field(default_factory=list)
    source_file: Path | None = None


@dataclass
class ValidationResult:
    """Result of documentation validation.

    Attributes:
        is_valid: Whether validation passed
        file_path: Path to validated file
        errors: List of error messages
        warnings: List of warning messages
    """

    is_valid: bool
    file_path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    """Result of a documentation sync operation.

    Attributes:
        command_name: Name of the command that was synced
        output_path: Path to generated documentation file
        was_updated: Whether the file was updated (vs created new)
        validation_result: Validation result if validation was performed
        error: Error message if sync failed
    """

    command_name: str
    output_path: Path | None = None
    was_updated: bool = False
    validation_result: ValidationResult | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether the sync operation succeeded."""
        return self.error is None


@dataclass
class ChangeSet:
    """Detected changes in CLI commands.

    Attributes:
        changed: Commands with modified signatures
        added: Newly added commands
        removed: Commands that no longer exist
    """

    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """Whether any changes were detected."""
        return bool(self.changed or self.added or self.removed)


__all__ = [
    "CLIArgument",
    "CLIMetadata",
    "CLIOption",
    "ChangeSet",
    "CommandExample",
    "SyncResult",
    "ValidationResult",
]
