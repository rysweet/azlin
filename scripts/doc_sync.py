#!/usr/bin/env python3
"""CLI documentation sync script.

This script runs the complete documentation sync process:
- Extract CLI metadata from Click commands
- Load examples from YAML files
- Generate markdown documentation
- Validate generated docs
- Report results

Usage:
    python scripts/doc_sync.py              # Sync all commands
    python scripts/doc_sync.py --force      # Force regenerate all
    python scripts/doc_sync.py --validate   # Validate only
    python scripts/doc_sync.py --command mount  # Sync specific command

Philosophy:
- Simple CLI script wrapper
- Delegates to DocSyncManager
- Clear output and error reporting
"""

import sys
from pathlib import Path

import click

# Add parent directory to path to import cli_documentation
sys.path.insert(0, str(Path(__file__).parent))

from cli_documentation import DocSyncManager


@click.command()
@click.option(
    "--force",
    is_flag=True,
    help="Force regenerate all documentation even if unchanged",
)
@click.option(
    "--validate",
    is_flag=True,
    help="Validate existing documentation without regenerating",
)
@click.option(
    "--command",
    "-c",
    help="Sync documentation for specific command only",
)
@click.option(
    "--cli-module",
    default="azlin.cli",
    help="Python module path for CLI commands",
)
@click.option(
    "--examples-dir",
    default="scripts/examples",
    help="Directory containing example YAML files",
)
@click.option(
    "--output-dir",
    default="docs-site/commands",
    help="Directory for generated documentation",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
def main(
    force: bool,
    validate: bool,
    command: str,
    cli_module: str,
    examples_dir: str,
    output_dir: str,
    verbose: bool,
):
    """Sync CLI documentation from source code and examples.

    This script orchestrates the complete documentation sync process:

    \b
    1. Extracts metadata from Click commands
    2. Loads examples from YAML files
    3. Generates markdown documentation
    4. Validates generated docs
    5. Reports results

    Examples:

    \b
        # Sync all commands (incremental)
        python scripts/doc_sync.py

    \b
        # Force regenerate everything
        python scripts/doc_sync.py --force

    \b
        # Validate existing docs
        python scripts/doc_sync.py --validate

    \b
        # Sync specific command
        python scripts/doc_sync.py --command mount
    """
    # Initialize manager
    manager = DocSyncManager(
        cli_module=cli_module,
        examples_dir=examples_dir,
        output_dir=output_dir,
    )

    click.echo("CLI Documentation Sync")
    click.echo("=" * 60)

    try:
        if validate:
            # Validate only mode
            click.echo("Validating existing documentation...")
            validation_results = manager.validator.validate_directory(str(manager.output_dir))

            # Aggregate results
            all_errors = []
            all_warnings = []
            failed_files = []

            for result in validation_results:
                if not result.is_valid:
                    failed_files.append(result.file_path)
                all_errors.extend(result.errors)
                all_warnings.extend(result.warnings)

            is_valid = len(failed_files) == 0

            # Report results
            click.echo(f"\nValidation complete:")
            click.echo(f"  Files checked: {len(validation_results)}")
            click.echo(f"  Status: {'PASSED' if is_valid else 'FAILED'}")
            click.echo(f"  Failed files: {len(failed_files)}")
            click.echo(f"  Total errors: {len(all_errors)}")
            click.echo(f"  Total warnings: {len(all_warnings)}")

            # Show errors
            if all_errors:
                click.echo("\nErrors:")
                for error in all_errors:
                    click.echo(f"  ✗ {error}")

            # Show warnings in verbose mode
            if verbose and all_warnings:
                click.echo("\nWarnings:")
                for warning in all_warnings:
                    click.echo(f"  ⚠ {warning}")

            sys.exit(0 if is_valid else 1)

        elif command:
            # Sync specific command
            click.echo(f"Syncing command: {command}")
            result = manager.sync_command_by_name(command)

            if not result:
                click.echo(f"✗ Command not found: {command}", err=True)
                sys.exit(1)

            if result.success:
                click.echo(f"✓ Generated: {result.output_path}")
                if result.validation_result and result.validation_result.warnings:
                    click.echo(
                        f"  Warnings: {len(result.validation_result.warnings)}"
                    )
                    if verbose:
                        for warning in result.validation_result.warnings:
                            click.echo(f"    - {warning}")
            else:
                click.echo(f"✗ Failed: {result.error}", err=True)
                sys.exit(1)

        else:
            # Sync all commands
            mode = "force" if force else "incremental"
            click.echo(f"Syncing all commands ({mode})...")

            results = manager.sync_all(force=force)

            # Report results
            success_count = sum(1 for r in results if r.success)
            fail_count = len(results) - success_count
            updated_count = sum(1 for r in results if r.was_updated)
            created_count = success_count - updated_count

            click.echo(f"\nSync complete:")
            click.echo(f"  Total: {len(results)} commands")
            click.echo(f"  Success: {success_count}")
            click.echo(f"  Failed: {fail_count}")
            click.echo(f"  Created: {created_count}")
            click.echo(f"  Updated: {updated_count}")

            # Show successful syncs
            if verbose or fail_count == 0:
                click.echo("\nGenerated files:")
                for result in results:
                    if result.success:
                        status = "updated" if result.was_updated else "created"
                        click.echo(f"  ✓ {result.command_name} ({status})")

            # Show failures
            if fail_count > 0:
                click.echo("\nFailed syncs:")
                for result in results:
                    if not result.success:
                        click.echo(f"  ✗ {result.command_name}: {result.error}")

            # Show validation warnings
            if verbose:
                warnings_count = sum(
                    len(r.validation_result.warnings)
                    for r in results
                    if r.validation_result
                )
                if warnings_count > 0:
                    click.echo(f"\nTotal validation warnings: {warnings_count}")

            sys.exit(0 if fail_count == 0 else 1)

    except Exception as e:
        click.echo(f"✗ Sync failed: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
