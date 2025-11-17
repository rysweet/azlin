"""Unit tests for interaction_handler module.

Tests CLI and Mock handlers for user interaction abstraction.
"""

from unittest.mock import patch

import pytest

from azlin.modules.interaction_handler import (
    CLIInteractionHandler,
    MockInteractionHandler,
)


class TestCLIInteractionHandler:
    """Test CLI interaction handler."""

    def test_instantiation(self):
        """CLI handler should instantiate without errors."""
        handler = CLIInteractionHandler()
        assert handler is not None

    @patch("azlin.modules.interaction_handler.click.prompt")
    @patch("azlin.modules.interaction_handler.click.echo")
    @patch("azlin.modules.interaction_handler.click.secho")
    def test_prompt_choice_valid_selection(self, mock_secho, mock_echo, mock_prompt):
        """Valid choice selection should return correct index."""
        mock_prompt.return_value = "2"

        handler = CLIInteractionHandler()
        choices = [
            ("small", "Small instance", 10.0),
            ("medium", "Medium instance", 20.0),
            ("large", "Large instance", 30.0),
        ]

        result = handler.prompt_choice("Select size:", choices)

        assert result == 1  # Zero-indexed
        assert mock_echo.called
        assert mock_secho.called

    @patch("azlin.modules.interaction_handler.click.prompt")
    @patch("azlin.modules.interaction_handler.click.echo")
    @patch("azlin.modules.interaction_handler.click.secho")
    def test_prompt_choice_first_option(self, mock_secho, mock_echo, mock_prompt):
        """Selecting first option should return index 0."""
        mock_prompt.return_value = "1"

        handler = CLIInteractionHandler()
        choices = [("a", "Option A", 5.0), ("b", "Option B", 10.0)]

        result = handler.prompt_choice("Choose:", choices)

        assert result == 0

    @patch("azlin.modules.interaction_handler.click.prompt")
    @patch("azlin.modules.interaction_handler.click.echo")
    @patch("azlin.modules.interaction_handler.click.secho")
    def test_prompt_choice_last_option(self, mock_secho, mock_echo, mock_prompt):
        """Selecting last option should return correct index."""
        mock_prompt.return_value = "3"

        handler = CLIInteractionHandler()
        choices = [("a", "A", 0.0), ("b", "B", 0.0), ("c", "C", 0.0)]

        result = handler.prompt_choice("Choose:", choices)

        assert result == 2

    def test_prompt_choice_empty_choices_raises_error(self):
        """Empty choices should raise ValueError."""
        handler = CLIInteractionHandler()

        with pytest.raises(ValueError, match="choices cannot be empty"):
            handler.prompt_choice("Choose:", [])

    @patch("azlin.modules.interaction_handler.click.confirm")
    def test_confirm_default_true(self, mock_confirm):
        """Confirm with default True should work."""
        mock_confirm.return_value = True

        handler = CLIInteractionHandler()
        result = handler.confirm("Continue?", default=True)

        assert result is True
        assert mock_confirm.called

    @patch("azlin.modules.interaction_handler.click.confirm")
    def test_confirm_default_false(self, mock_confirm):
        """Confirm with default False should work."""
        mock_confirm.return_value = False

        handler = CLIInteractionHandler()
        result = handler.confirm("Delete?", default=False)

        assert result is False

    @patch("azlin.modules.interaction_handler.click.secho")
    def test_show_warning(self, mock_secho):
        """Show warning should call click.secho with yellow."""
        handler = CLIInteractionHandler()
        handler.show_warning("This is a warning")

        mock_secho.assert_called_once()
        call_args = mock_secho.call_args
        assert "Warning: This is a warning" in str(call_args)
        assert call_args[1]["fg"] == "yellow"
        assert call_args[1]["err"] is True

    @patch("azlin.modules.interaction_handler.click.secho")
    def test_show_info(self, mock_secho):
        """Show info should call click.secho with green."""
        handler = CLIInteractionHandler()
        handler.show_info("This is info")

        mock_secho.assert_called_once()
        call_args = mock_secho.call_args
        assert "This is info" in str(call_args)
        assert call_args[1]["fg"] == "green"


class TestMockInteractionHandler:
    """Test mock interaction handler for testing."""

    def test_instantiation_empty(self):
        """Mock handler should instantiate with empty responses."""
        handler = MockInteractionHandler()
        assert handler is not None
        assert handler.choice_responses == []
        assert handler.confirm_responses == []
        assert handler.interactions == []

    def test_instantiation_with_responses(self):
        """Mock handler should store provided responses."""
        handler = MockInteractionHandler(
            choice_responses=[0, 1, 2],
            confirm_responses=[True, False],
        )
        assert handler.choice_responses == [0, 1, 2]
        assert handler.confirm_responses == [True, False]

    def test_prompt_choice_returns_programmed_response(self):
        """Prompt choice should return pre-programmed response."""
        handler = MockInteractionHandler(choice_responses=[1])

        choices = [("a", "Option A", 0.0), ("b", "Option B", 10.0)]
        result = handler.prompt_choice("Choose:", choices)

        assert result == 1

    def test_prompt_choice_tracks_interaction(self):
        """Prompt choice should track the interaction."""
        handler = MockInteractionHandler(choice_responses=[0])

        choices = [("a", "Option A", 5.0)]
        handler.prompt_choice("Select:", choices)

        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "choice"
        assert handler.interactions[0]["message"] == "Select:"
        assert handler.interactions[0]["response"] == 0

    def test_prompt_choice_multiple_calls(self):
        """Multiple prompt_choice calls should use sequential responses."""
        handler = MockInteractionHandler(choice_responses=[0, 2, 1])

        choices = [("a", "A", 0.0), ("b", "B", 0.0), ("c", "C", 0.0)]

        assert handler.prompt_choice("Q1", choices) == 0
        assert handler.prompt_choice("Q2", choices) == 2
        assert handler.prompt_choice("Q3", choices) == 1

    def test_prompt_choice_no_responses_raises_error(self):
        """Prompt choice with no responses should raise IndexError."""
        handler = MockInteractionHandler()

        choices = [("a", "A", 0.0)]

        with pytest.raises(IndexError, match="No more choice responses"):
            handler.prompt_choice("Choose:", choices)

    def test_prompt_choice_exhausted_responses_raises_error(self):
        """Exhausted responses should raise IndexError."""
        handler = MockInteractionHandler(choice_responses=[0])

        choices = [("a", "A", 0.0)]

        handler.prompt_choice("Q1", choices)  # Uses the only response

        with pytest.raises(IndexError, match="No more choice responses"):
            handler.prompt_choice("Q2", choices)

    def test_prompt_choice_invalid_response_raises_error(self):
        """Invalid pre-programmed response should raise ValueError."""
        handler = MockInteractionHandler(choice_responses=[5])

        choices = [("a", "A", 0.0), ("b", "B", 0.0)]  # Only 2 choices

        with pytest.raises(ValueError, match="Invalid pre-programmed response"):
            handler.prompt_choice("Choose:", choices)

    def test_prompt_choice_empty_choices_raises_error(self):
        """Empty choices should raise ValueError."""
        handler = MockInteractionHandler(choice_responses=[0])

        with pytest.raises(ValueError, match="choices cannot be empty"):
            handler.prompt_choice("Choose:", [])

    def test_confirm_returns_programmed_response(self):
        """Confirm should return pre-programmed response."""
        handler = MockInteractionHandler(confirm_responses=[True])

        result = handler.confirm("Continue?")

        assert result is True

    def test_confirm_tracks_interaction(self):
        """Confirm should track the interaction."""
        handler = MockInteractionHandler(confirm_responses=[False])

        handler.confirm("Delete?", default=True)

        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "confirm"
        assert handler.interactions[0]["message"] == "Delete?"
        assert handler.interactions[0]["default"] is True
        assert handler.interactions[0]["response"] is False

    def test_confirm_multiple_calls(self):
        """Multiple confirm calls should use sequential responses."""
        handler = MockInteractionHandler(confirm_responses=[True, False, True])

        assert handler.confirm("Q1") is True
        assert handler.confirm("Q2") is False
        assert handler.confirm("Q3") is True

    def test_confirm_no_responses_raises_error(self):
        """Confirm with no responses should raise IndexError."""
        handler = MockInteractionHandler()

        with pytest.raises(IndexError, match="No more confirm responses"):
            handler.confirm("Continue?")

    def test_show_warning_tracks_interaction(self):
        """Show warning should track the message."""
        handler = MockInteractionHandler()

        handler.show_warning("Warning message")

        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "warning"
        assert handler.interactions[0]["message"] == "Warning message"

    def test_show_info_tracks_interaction(self):
        """Show info should track the message."""
        handler = MockInteractionHandler()

        handler.show_info("Info message")

        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "info"
        assert handler.interactions[0]["message"] == "Info message"

    def test_reset_clears_interactions(self):
        """Reset should clear interaction history."""
        handler = MockInteractionHandler(choice_responses=[0, 1])

        choices = [("a", "A", 0.0), ("b", "B", 0.0)]
        handler.prompt_choice("Q1", choices)

        assert len(handler.interactions) == 1

        handler.reset()

        assert len(handler.interactions) == 0

    def test_reset_resets_response_indices(self):
        """Reset should reset response indices to 0."""
        handler = MockInteractionHandler(choice_responses=[0, 1])

        choices = [("a", "A", 0.0), ("b", "B", 0.0)]
        handler.prompt_choice("Q1", choices)  # Uses index 0

        handler.reset()

        result = handler.prompt_choice("Q2", choices)  # Should use index 0 again
        assert result == 0

    def test_get_interactions_by_type_choice(self):
        """Get interactions by type should filter correctly."""
        handler = MockInteractionHandler(choice_responses=[0], confirm_responses=[True])

        choices = [("a", "A", 0.0)]
        handler.prompt_choice("Q1", choices)
        handler.confirm("Confirm?")
        handler.show_info("Info")

        choice_interactions = handler.get_interactions_by_type("choice")

        assert len(choice_interactions) == 1
        assert choice_interactions[0]["type"] == "choice"

    def test_get_interactions_by_type_confirm(self):
        """Get confirm interactions should work."""
        handler = MockInteractionHandler(confirm_responses=[True, False])

        handler.confirm("Q1")
        handler.confirm("Q2")
        handler.show_warning("Warning")

        confirm_interactions = handler.get_interactions_by_type("confirm")

        assert len(confirm_interactions) == 2
        assert all(i["type"] == "confirm" for i in confirm_interactions)

    def test_get_interactions_by_type_warning(self):
        """Get warning interactions should work."""
        handler = MockInteractionHandler()

        handler.show_warning("Warn 1")
        handler.show_info("Info")
        handler.show_warning("Warn 2")

        warning_interactions = handler.get_interactions_by_type("warning")

        assert len(warning_interactions) == 2
        assert all(i["type"] == "warning" for i in warning_interactions)

    def test_get_interactions_by_type_info(self):
        """Get info interactions should work."""
        handler = MockInteractionHandler()

        handler.show_info("Info 1")
        handler.show_warning("Warn")
        handler.show_info("Info 2")
        handler.show_info("Info 3")

        info_interactions = handler.get_interactions_by_type("info")

        assert len(info_interactions) == 3
        assert all(i["type"] == "info" for i in info_interactions)

    def test_complex_interaction_flow(self):
        """Test complex interaction flow with multiple types."""
        handler = MockInteractionHandler(
            choice_responses=[0, 1],
            confirm_responses=[True, False],
        )

        choices = [("a", "A", 0.0), ("b", "B", 0.0)]

        handler.show_info("Starting")
        handler.prompt_choice("Choose 1", choices)
        handler.show_warning("Warning")
        handler.confirm("Confirm 1")
        handler.prompt_choice("Choose 2", choices)
        handler.confirm("Confirm 2")
        handler.show_info("Done")

        assert len(handler.interactions) == 7
        assert len(handler.get_interactions_by_type("choice")) == 2
        assert len(handler.get_interactions_by_type("confirm")) == 2
        assert len(handler.get_interactions_by_type("info")) == 2
        assert len(handler.get_interactions_by_type("warning")) == 1
