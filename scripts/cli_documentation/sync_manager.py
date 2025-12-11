"""Documentation sync orchestration.

This module orchestrates the complete documentation sync process:
- Extract CLI metadata from source
- Load examples from YAML files
- Generate markdown documentation
- Validate generated docs
- Track changes via hashing

Philosophy:
- Orchestration, not implementation
- Delegates to specialized modules
- Self-contained and regeneratable
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from .example_manager import ExampleManager
from .extractor import CLIExtractor
from .generator import DocGenerator
from .hasher import CLIHasher
from .models import CLIMetadata, SyncResult
from .validator import SyncValidator


class DocSyncManager:
    """Orchestrates CLI documentation synchronization.

    This class coordinates all the components needed to sync CLI documentation:
    extracting metadata, loading examples, generating docs, and validating output.
    """

    def __init__(
        self,
        cli_module: str = "azlin.cli",
        examples_dir: str = "scripts/examples",
        output_dir: str = "docs-site/commands",
        hash_file: str = ".cli_doc_hashes.json",
    ):
        """Initialize sync manager.

        Args:
            cli_module: Python module path for CLI (e.g., "azlin.cli")
            examples_dir: Directory containing example YAML files
            output_dir: Directory for generated documentation
            hash_file: File for storing command hashes
        """
        self.cli_module = cli_module
        self.examples_dir = Path(examples_dir)
        self.output_dir = Path(output_dir)

        # Initialize components
        self.extractor = CLIExtractor()
        self.example_manager = ExampleManager(str(examples_dir))
        self.generator = DocGenerator()
        self.validator = SyncValidator()
        self.hasher = CLIHasher(hash_file)

    def sync_all(self, force: bool = False) -> List[SyncResult]:
        """Sync documentation for all commands.

        Args:
            force: If True, regenerate all docs even if unchanged

        Returns:
            List of SyncResult objects for each command

        Example:
            >>> manager = DocSyncManager()
            >>> results = manager.sync_all()
            >>> for result in results:
            ...     if result.success:
            ...         print(f"Generated: {result.output_path}")
        """
        results = []

        # Extract all commands
        commands = self.extractor.extract_all_commands(self.cli_module)

        # Build command dictionary for hash comparison
        command_dict: Dict[str, CLIMetadata] = {cmd.name: cmd for cmd in commands}

        # Determine which commands need syncing
        if force:
            # Regenerate all
            commands_to_sync = commands
        else:
            # Only sync changed commands
            changeset = self.hasher.compare_hashes(command_dict)
            commands_to_sync = [
                cmd
                for cmd in commands
                if cmd.name in changeset.changed or cmd.name in changeset.added
            ]

        # Sync each command
        for command in commands_to_sync:
            result = self.sync_command(command)
            results.append(result)

            # Update hash if successful
            if result.success:
                self.hasher.update_hash(command)

        # Save updated hashes
        self.hasher.save_hashes()

        return results

    def sync_command(
        self, command: CLIMetadata, validate: bool = True
    ) -> SyncResult:
        """Sync documentation for a single command.

        Args:
            command: CLI metadata for the command
            validate: Whether to validate generated documentation

        Returns:
            SyncResult describing the sync operation

        Example:
            >>> manager = DocSyncManager()
            >>> result = manager.sync_command(metadata)
            >>> if result.success:
            ...     print(f"Generated: {result.output_path}")
        """
        try:
            # Load examples for this command
            examples = self.example_manager.load_examples(command.name)

            # Generate markdown
            markdown = self.generator.generate(command, examples)

            # Determine output path
            output_path = self._get_output_path(command)

            # Check if file already exists (update vs create)
            was_updated = output_path.exists()

            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown)

            # Validate if requested
            validation_result = None
            if validate:
                validation_result = self.validator.validate_file(str(output_path))

                if not validation_result.is_valid:
                    return SyncResult(
                        command_name=command.name,
                        output_path=output_path,
                        was_updated=was_updated,
                        validation_result=validation_result,
                        error=f"Validation failed: {validation_result.errors}",
                    )

            return SyncResult(
                command_name=command.name,
                output_path=output_path,
                was_updated=was_updated,
                validation_result=validation_result,
            )

        except Exception as e:
            return SyncResult(
                command_name=command.name,
                error=str(e),
            )

    def sync_command_by_name(self, command_name: str) -> Optional[SyncResult]:
        """Sync documentation for a command by name.

        Args:
            command_name: Name of the command to sync

        Returns:
            SyncResult or None if command not found

        Example:
            >>> manager = DocSyncManager()
            >>> result = manager.sync_command_by_name("mount")
            >>> if result and result.success:
            ...     print(f"Synced {command_name}")
        """
        # Extract the specific command
        metadata = self.extractor.extract_command(self.cli_module, command_name)

        if not metadata:
            return SyncResult(
                command_name=command_name,
                error=f"Command not found: {command_name}",
            )

        return self.sync_command(metadata)

    def _sanitize_path_component(self, component: str) -> str:
        """Sanitize path component to prevent path traversal attacks.

        Args:
            component: Raw path component (command name or part)

        Returns:
            Sanitized component

        Raises:
            ValueError: If component contains invalid characters
        """
        # Only allow alphanumeric, dash, and underscore
        if not re.match(r'^[a-zA-Z0-9_-]+$', component):
            raise ValueError(f"Invalid path component: {component}")
        return component

    def _get_output_path(self, command: CLIMetadata) -> Path:
        """Get output path for a command's documentation.

        Args:
            command: CLI metadata

        Returns:
            Path to output markdown file

        Raises:
            ValueError: If command name contains invalid characters
        """
        # For nested commands (e.g., "storage mount"), create subdirectories
        if " " in command.full_path:
            parts = command.full_path.split()
            # Sanitize each part to prevent path traversal
            safe_parts = [self._sanitize_path_component(part) for part in parts]
            # Create subdirectory for command group
            subdir = self.output_dir / safe_parts[0]
            return subdir / f"{safe_parts[1]}.md"
        else:
            safe_name = self._sanitize_path_component(command.name)
            return self.output_dir / f"{safe_name}.md"


__all__ = ["DocSyncManager"]
