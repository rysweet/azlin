"""Custom Click group with automatic help display on errors.

This module provides a custom Click Group class that automatically
displays contextual help when syntax errors occur.
"""

import sys
from typing import Any

import click


class AzlinGroup(click.Group):
    """Custom Click group that handles -- delimiter and auto-displays help on errors."""

    def main(self, *args: Any, **kwargs: Any) -> Any:
        """Override main to handle -- delimiter and auto-display help on errors."""
        # Check if -- is in sys.argv BEFORE Click processes anything
        if "--" in sys.argv:
            delimiter_idx = sys.argv.index("--")
            # Store the command for later
            passthrough_args = sys.argv[delimiter_idx + 1 :]
            if passthrough_args:
                # Remove everything from -- onwards so Click doesn't see it
                sys.argv = sys.argv[:delimiter_idx]
                # We'll pass this through the context
                if not hasattr(self, "_passthrough_command"):
                    self._passthrough_command = " ".join(passthrough_args)

        try:
            return super().main(*args, **kwargs)
        except (
            click.exceptions.UsageError,
            click.exceptions.BadParameter,
            click.exceptions.MissingParameter,
        ) as e:
            # Show the error message first
            click.echo(f"Error: {e.format_message()}", err=True)

            # Try to get the most specific context for help
            ctx = e.ctx if hasattr(e, "ctx") and e.ctx else None

            if ctx:
                # Show the help for the current context
                click.echo("")  # Add spacing
                click.echo(ctx.get_help())
                # Use ctx.exit() to properly handle Click's testing mode
                ctx.exit(e.exit_code if hasattr(e, "exit_code") else 1)
                return None  # Explicit return for code clarity (never reached)
            # No context available, use sys.exit
            sys.exit(e.exit_code if hasattr(e, "exit_code") else 1)
            return None  # Explicit return for code clarity (never reached)
        except click.exceptions.ClickException:
            # For other Click exceptions, use default handling
            raise

    def invoke(self, ctx: click.Context) -> Any:
        """Pass the passthrough command to the context and handle errors with auto-help."""
        if hasattr(self, "_passthrough_command"):
            ctx.obj = {"passthrough_command": self._passthrough_command}

        try:
            return super().invoke(ctx)
        except (
            click.exceptions.UsageError,
            click.exceptions.BadParameter,
            click.exceptions.MissingParameter,
        ) as e:
            # Show the error message first
            click.echo(f"Error: {e.format_message()}", err=True)

            # Get the most specific context for help (the subcommand context if available)
            error_ctx = e.ctx if hasattr(e, "ctx") and e.ctx else ctx

            # Show the help for the error context
            click.echo("")  # Add spacing
            click.echo(error_ctx.get_help())

            # Exit with error code - use ctx.exit() for Click compatibility
            error_ctx.exit(e.exit_code if hasattr(e, "exit_code") else 1)
            return None  # Explicit return for code clarity (never reached)
        except click.exceptions.ClickException:
            # For other Click exceptions, use default handling
            raise

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        """Override to show help when command is not found."""
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            # Only handle command-not-found errors here
            # Let parameter errors (MissingParameter, BadParameter) propagate
            # so they can be handled by invoke() with proper error messages
            if isinstance(e, click.exceptions.MissingParameter | click.exceptions.BadParameter):
                raise
            # Command not found - show error and help
            click.echo(f"Error: {e.format_message()}", err=True)
            click.echo("")
            click.echo(ctx.get_help())
            ctx.exit(1)
            return None, None, []  # Explicit return for code clarity (never reached)


# Set group_class so that subgroups created with @main.group() also use AzlinGroup
AzlinGroup.group_class = AzlinGroup
