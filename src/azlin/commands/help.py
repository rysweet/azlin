"""Help command for azlin CLI.

This module provides the help command for displaying command help.
"""

import click


def register_help_command(main: click.Group) -> None:
    """Register help command with main CLI group.

    Args:
        main: The main CLI group to register commands with
    """

    @main.command(name="help")
    @click.argument("command_name", required=False, type=str)
    @click.pass_context
    def help_command(ctx: click.Context, command_name: str | None) -> None:
        """Show help for commands.

        Display general help or help for a specific command.

        \b
        Examples:
            azlin help              # Show general help
            azlin help connect      # Show help for connect command
            azlin help list         # Show help for list command
        """
        if command_name is None:
            click.echo(ctx.parent.get_help())
        else:
            # Show help for specific command
            cmd = ctx.parent.command.commands.get(command_name)  # type: ignore[union-attr]

            if cmd is None:
                click.echo(f"Error: No such command '{command_name}'.", err=True)
                ctx.exit(1)

            # Create a context for the command and show its help
            cmd_ctx = click.Context(cmd, info_name=command_name, parent=ctx.parent)  # type: ignore[arg-type]
            click.echo(cmd.get_help(cmd_ctx))  # type: ignore[union-attr]
