"""User interaction abstraction for CLI, testing, and future API support.

This module provides a protocol-based approach to user interaction, allowing
different implementations for CLI (using click), testing (mock responses), and
future API/web interfaces.

Example:
    >>> handler = CLIInteractionHandler()
    >>> choices = [
    ...     ("small", "t3.micro - 1 vCPU, 1GB RAM", 7.30),
    ...     ("medium", "t3.small - 2 vCPU, 2GB RAM", 14.60),
    ...     ("large", "t3.medium - 2 vCPU, 4GB RAM", 29.20)
    ... ]
    >>> choice = handler.prompt_choice("Select instance size:", choices)
    >>> handler.show_info(f"Selected: {choices[choice][0]}")

    Testing example:
    >>> test_handler = MockInteractionHandler(choice_responses=[1], confirm_responses=[True])
    >>> choice = test_handler.prompt_choice("Select:", [("a", "opt a", 0), ("b", "opt b", 10)])
    >>> choice
    1
"""

from typing import Protocol, runtime_checkable

import click


@runtime_checkable
class InteractionHandler(Protocol):
    """Protocol for user interaction.

    This protocol defines the interface for different interaction handlers,
    allowing abstraction over CLI, testing, and future API implementations.
    """

    def prompt_choice(
        self,
        message: str,
        choices: list[tuple[str, str, float]],
    ) -> int:
        """Prompt user to select from multiple choices.

        Args:
            message: Prompt message to display
            choices: List of (label, description, monthly_cost) tuples
                - label: Short identifier (e.g., "small", "medium")
                - description: Detailed description of the option
                - monthly_cost: Estimated monthly cost in USD

        Returns:
            Zero-based index of selected choice

        Raises:
            ValueError: If choices is empty
            click.Abort: If user cancels (CLI implementation)

        Example:
            >>> handler = CLIInteractionHandler()
            >>> choices = [("basic", "Basic tier", 5.0), ("pro", "Pro tier", 15.0)]
            >>> idx = handler.prompt_choice("Select tier:", choices)
            >>> selected_label = choices[idx][0]
        """
        ...

    def confirm(self, message: str, default: bool = True) -> bool:
        """Prompt for yes/no confirmation.

        Args:
            message: Confirmation question to display
            default: Default value if user just presses Enter

        Returns:
            True if confirmed, False otherwise

        Example:
            >>> handler = CLIInteractionHandler()
            >>> if handler.confirm("Deploy to production?", default=False):
            ...     print("Deploying...")
        """
        ...

    def show_warning(self, message: str) -> None:
        """Display a warning message.

        Args:
            message: Warning message to display

        Example:
            >>> handler = CLIInteractionHandler()
            >>> handler.show_warning("This operation cannot be undone")
        """
        ...

    def show_info(self, message: str) -> None:
        """Display an informational message.

        Args:
            message: Information message to display

        Example:
            >>> handler = CLIInteractionHandler()
            >>> handler.show_info("Configuration saved successfully")
        """
        ...


class CLIInteractionHandler:
    """Click-based CLI interaction handler.

    Provides rich terminal-based user interaction using the click library,
    with colored output and formatted choice displays.

    Example:
        >>> handler = CLIInteractionHandler()
        >>> choices = [
        ...     ("dev", "Development environment", 10.0),
        ...     ("prod", "Production environment", 50.0)
        ... ]
        >>> idx = handler.prompt_choice("Select environment:", choices)
        >>> handler.show_info(f"Selected: {choices[idx][0]}")
    """

    def prompt_choice(
        self,
        message: str,
        choices: list[tuple[str, str, float]],
    ) -> int:
        """Prompt user to select from multiple choices with formatted display.

        Displays choices with cost information and colored output:
        - Choice numbers in cyan
        - Descriptions in standard color
        - Costs in yellow

        Args:
            message: Prompt message to display
            choices: List of (label, description, monthly_cost) tuples

        Returns:
            Zero-based index of selected choice

        Raises:
            ValueError: If choices is empty
            click.Abort: If user cancels (Ctrl+C)

        Example:
            >>> handler = CLIInteractionHandler()
            >>> choices = [
            ...     ("small", "t3.micro", 7.30),
            ...     ("large", "t3.medium", 29.20)
            ... ]
            >>> idx = handler.prompt_choice("Select size:", choices)
        """
        if not choices:
            raise ValueError("choices cannot be empty")

        click.echo()
        click.secho(message, fg="green", bold=True)
        click.echo()

        for i, (label, description, cost) in enumerate(choices, 1):
            click.echo(
                f"  {click.style(str(i), fg='cyan')}. {description} "
                f"({click.style(f'~${cost:.2f}/month', fg='yellow')})"
            )

        click.echo()

        while True:
            try:
                choice_str = click.prompt(
                    "Enter choice",
                    type=str,
                    show_default=False,
                )
                choice_num = int(choice_str)

                if 1 <= choice_num <= len(choices):
                    return choice_num - 1
                else:
                    click.secho(
                        f"Please enter a number between 1 and {len(choices)}",
                        fg="red",
                    )
            except ValueError:
                click.secho("Please enter a valid number", fg="red")
            except (KeyboardInterrupt, click.Abort):
                click.echo()
                raise click.Abort()

    def confirm(self, message: str, default: bool = True) -> bool:
        """Prompt for yes/no confirmation with colored output.

        Args:
            message: Confirmation question to display
            default: Default value if user just presses Enter

        Returns:
            True if confirmed, False otherwise

        Example:
            >>> handler = CLIInteractionHandler()
            >>> if handler.confirm("Continue?"):
            ...     print("Continuing...")
        """
        return click.confirm(
            click.style(message, fg="yellow"),
            default=default,
        )

    def show_warning(self, message: str) -> None:
        """Display a warning message in yellow.

        Args:
            message: Warning message to display

        Example:
            >>> handler = CLIInteractionHandler()
            >>> handler.show_warning("Operation may take several minutes")
        """
        click.secho(f"Warning: {message}", fg="yellow", err=True)

    def show_info(self, message: str) -> None:
        """Display an informational message in green.

        Args:
            message: Information message to display

        Example:
            >>> handler = CLIInteractionHandler()
            >>> handler.show_info("Process completed successfully")
        """
        click.secho(message, fg="green")


class MockInteractionHandler:
    """Mock interaction handler for testing with pre-programmed responses.

    Provides deterministic responses for testing without user interaction.
    Tracks all interactions for verification in tests.

    Example:
        >>> handler = MockInteractionHandler(
        ...     choice_responses=[0, 1],
        ...     confirm_responses=[True, False]
        ... )
        >>> handler.prompt_choice("Select:", [("a", "opt a", 0), ("b", "opt b", 10)])
        0
        >>> handler.confirm("Continue?")
        True
        >>> len(handler.interactions)
        2
    """

    def __init__(
        self,
        choice_responses: list[int] | None = None,
        confirm_responses: list[bool] | None = None,
    ):
        """Initialize test handler with pre-programmed responses.

        Args:
            choice_responses: List of choice indices to return in sequence
            confirm_responses: List of boolean confirmation responses in sequence

        Example:
            >>> handler = MockInteractionHandler(
            ...     choice_responses=[1],
            ...     confirm_responses=[True]
            ... )
        """
        self.choice_responses = choice_responses or []
        self.confirm_responses = confirm_responses or []
        self.interactions: list[dict] = []
        self._choice_index = 0
        self._confirm_index = 0

    def prompt_choice(
        self,
        message: str,
        choices: list[tuple[str, str, float]],
    ) -> int:
        """Return next pre-programmed choice response.

        Args:
            message: Prompt message (recorded but not used)
            choices: Available choices (validated but not displayed)

        Returns:
            Next choice index from choice_responses

        Raises:
            ValueError: If choices is empty
            IndexError: If no more choice responses available

        Example:
            >>> handler = MockInteractionHandler(choice_responses=[1])
            >>> handler.prompt_choice("Select:", [("a", "A", 0), ("b", "B", 10)])
            1
        """
        if not choices:
            raise ValueError("choices cannot be empty")

        if self._choice_index >= len(self.choice_responses):
            raise IndexError(
                f"No more choice responses available. "
                f"Provided {len(self.choice_responses)}, "
                f"needed {self._choice_index + 1}"
            )

        response = self.choice_responses[self._choice_index]
        self._choice_index += 1

        # Validate response is in valid range
        if not 0 <= response < len(choices):
            raise ValueError(
                f"Invalid pre-programmed response {response} "
                f"for {len(choices)} choices"
            )

        self.interactions.append(
            {
                "type": "choice",
                "message": message,
                "choices": choices,
                "response": response,
            }
        )

        return response

    def confirm(self, message: str, default: bool = True) -> bool:
        """Return next pre-programmed confirmation response.

        Args:
            message: Confirmation message (recorded but not used)
            default: Default value (recorded but not used)

        Returns:
            Next boolean from confirm_responses

        Raises:
            IndexError: If no more confirm responses available

        Example:
            >>> handler = MockInteractionHandler(confirm_responses=[False])
            >>> handler.confirm("Continue?")
            False
        """
        if self._confirm_index >= len(self.confirm_responses):
            raise IndexError(
                f"No more confirm responses available. "
                f"Provided {len(self.confirm_responses)}, "
                f"needed {self._confirm_index + 1}"
            )

        response = self.confirm_responses[self._confirm_index]
        self._confirm_index += 1

        self.interactions.append(
            {
                "type": "confirm",
                "message": message,
                "default": default,
                "response": response,
            }
        )

        return response

    def show_warning(self, message: str) -> None:
        """Record warning message without displaying.

        Args:
            message: Warning message to record

        Example:
            >>> handler = MockInteractionHandler()
            >>> handler.show_warning("Test warning")
            >>> handler.interactions[-1]["type"]
            'warning'
        """
        self.interactions.append(
            {
                "type": "warning",
                "message": message,
            }
        )

    def show_info(self, message: str) -> None:
        """Record info message without displaying.

        Args:
            message: Info message to record

        Example:
            >>> handler = MockInteractionHandler()
            >>> handler.show_info("Test info")
            >>> handler.interactions[-1]["type"]
            'info'
        """
        self.interactions.append(
            {
                "type": "info",
                "message": message,
            }
        )

    def reset(self) -> None:
        """Reset handler state for reuse in tests.

        Clears interaction history and resets response indices.

        Example:
            >>> handler = MockInteractionHandler(choice_responses=[0, 1])
            >>> handler.prompt_choice("Q1", [("a", "A", 0)])
            0
            >>> handler.reset()
            >>> handler.prompt_choice("Q2", [("b", "B", 0)])
            0
        """
        self.interactions.clear()
        self._choice_index = 0
        self._confirm_index = 0

    def get_interactions_by_type(self, interaction_type: str) -> list[dict]:
        """Get all interactions of a specific type.

        Args:
            interaction_type: Type to filter by ("choice", "confirm", "warning", "info")

        Returns:
            List of interaction dictionaries matching the type

        Example:
            >>> handler = MockInteractionHandler()
            >>> handler.show_info("Info 1")
            >>> handler.show_warning("Warn 1")
            >>> handler.show_info("Info 2")
            >>> len(handler.get_interactions_by_type("info"))
            2
        """
        return [
            interaction
            for interaction in self.interactions
            if interaction["type"] == interaction_type
        ]


# Type alias for convenience
Handler = InteractionHandler
