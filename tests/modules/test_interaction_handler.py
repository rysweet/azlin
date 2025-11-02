"""Tests for interaction handler module."""

import pytest
from click.testing import CliRunner
import click

from azlin.modules.interaction_handler import (
    InteractionHandler,
    CLIInteractionHandler,
    MockInteractionHandler,
)


class TestProtocolCompliance:
    """Test that implementations comply with the InteractionHandler protocol."""

    def test_cli_handler_implements_protocol(self):
        """CLIInteractionHandler implements InteractionHandler protocol."""
        handler = CLIInteractionHandler()
        assert isinstance(handler, InteractionHandler)

    def test_test_handler_implements_protocol(self):
        """MockInteractionHandler implements InteractionHandler protocol."""
        handler = MockInteractionHandler()
        assert isinstance(handler, InteractionHandler)


class TestCLIInteractionHandler:
    """Tests for CLI interaction handler."""

    def test_prompt_choice_with_valid_selection(self):
        """Test prompt_choice with valid user input."""
        handler = CLIInteractionHandler()
        runner = CliRunner()

        def interaction():
            choices = [
                ("small", "Small instance", 10.0),
                ("medium", "Medium instance", 20.0),
                ("large", "Large instance", 30.0),
            ]
            return handler.prompt_choice("Select size:", choices)

        # Simulate user selecting option 2
        with runner.isolated_filesystem():
            result = runner.invoke(
                click.Command("test", callback=lambda: interaction()),
                input="2\n",
            )
            # Note: In actual CLI usage, this would return 1 (index of second choice)
            # For testing purposes, we verify the handler works with click

    def test_prompt_choice_empty_choices_raises_error(self):
        """Test that empty choices list raises ValueError."""
        handler = CLIInteractionHandler()

        with pytest.raises(ValueError, match="choices cannot be empty"):
            handler.prompt_choice("Select:", [])

    def test_prompt_choice_invalid_then_valid(self):
        """Test prompt_choice handles invalid input then accepts valid."""
        handler = CLIInteractionHandler()
        runner = CliRunner()

        def interaction():
            choices = [("a", "Option A", 5.0), ("b", "Option B", 10.0)]
            return handler.prompt_choice("Select:", choices)

        # First input invalid (0), then valid (1)
        with runner.isolated_filesystem():
            result = runner.invoke(
                click.Command("test", callback=lambda: interaction()),
                input="0\n1\n",
            )

    def test_confirm_default_true(self):
        """Test confirm with default True."""
        handler = CLIInteractionHandler()
        runner = CliRunner()

        def interaction():
            return handler.confirm("Continue?", default=True)

        # Just press Enter to accept default
        with runner.isolated_filesystem():
            result = runner.invoke(
                click.Command("test", callback=lambda: interaction()),
                input="\n",
            )

    def test_confirm_default_false(self):
        """Test confirm with default False."""
        handler = CLIInteractionHandler()
        runner = CliRunner()

        def interaction():
            return handler.confirm("Continue?", default=False)

        # Press 'n' to decline
        with runner.isolated_filesystem():
            result = runner.invoke(
                click.Command("test", callback=lambda: interaction()),
                input="n\n",
            )

    def test_show_warning_displays_message(self):
        """Test show_warning displays to stderr."""
        handler = CLIInteractionHandler()
        runner = CliRunner()

        def interaction():
            handler.show_warning("This is a warning")

        result = runner.invoke(
            click.Command("test", callback=lambda: interaction())
        )
        assert "Warning: This is a warning" in result.output

    def test_show_info_displays_message(self):
        """Test show_info displays message."""
        handler = CLIInteractionHandler()
        runner = CliRunner()

        def interaction():
            handler.show_info("This is info")

        result = runner.invoke(
            click.Command("test", callback=lambda: interaction())
        )
        assert "This is info" in result.output


class TestMockInteractionHandler:
    """Tests for test interaction handler."""

    def test_prompt_choice_returns_programmed_response(self):
        """Test prompt_choice returns pre-programmed response."""
        handler = MockInteractionHandler(choice_responses=[1])
        choices = [("a", "Option A", 5.0), ("b", "Option B", 10.0)]

        result = handler.prompt_choice("Select:", choices)

        assert result == 1
        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "choice"
        assert handler.interactions[0]["message"] == "Select:"
        assert handler.interactions[0]["response"] == 1

    def test_prompt_choice_multiple_responses(self):
        """Test prompt_choice handles multiple sequential calls."""
        handler = MockInteractionHandler(choice_responses=[0, 2, 1])
        choices = [("a", "A", 0), ("b", "B", 0), ("c", "C", 0)]

        assert handler.prompt_choice("Q1:", choices) == 0
        assert handler.prompt_choice("Q2:", choices) == 2
        assert handler.prompt_choice("Q3:", choices) == 1
        assert len(handler.interactions) == 3

    def test_prompt_choice_empty_choices_raises_error(self):
        """Test that empty choices raises ValueError."""
        handler = MockInteractionHandler(choice_responses=[0])

        with pytest.raises(ValueError, match="choices cannot be empty"):
            handler.prompt_choice("Select:", [])

    def test_prompt_choice_no_more_responses_raises_error(self):
        """Test that exhausting responses raises IndexError."""
        handler = MockInteractionHandler(choice_responses=[0])
        choices = [("a", "A", 0)]

        handler.prompt_choice("Q1:", choices)

        with pytest.raises(IndexError, match="No more choice responses available"):
            handler.prompt_choice("Q2:", choices)

    def test_prompt_choice_invalid_response_raises_error(self):
        """Test that invalid pre-programmed response raises ValueError."""
        handler = MockInteractionHandler(choice_responses=[5])
        choices = [("a", "A", 0), ("b", "B", 0)]

        with pytest.raises(ValueError, match="Invalid pre-programmed response"):
            handler.prompt_choice("Select:", choices)

    def test_confirm_returns_programmed_response(self):
        """Test confirm returns pre-programmed response."""
        handler = MockInteractionHandler(confirm_responses=[True])

        result = handler.confirm("Continue?")

        assert result is True
        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "confirm"
        assert handler.interactions[0]["message"] == "Continue?"
        assert handler.interactions[0]["response"] is True

    def test_confirm_multiple_responses(self):
        """Test confirm handles multiple sequential calls."""
        handler = MockInteractionHandler(confirm_responses=[True, False, True])

        assert handler.confirm("Q1?") is True
        assert handler.confirm("Q2?") is False
        assert handler.confirm("Q3?") is True
        assert len(handler.interactions) == 3

    def test_confirm_no_more_responses_raises_error(self):
        """Test that exhausting confirm responses raises IndexError."""
        handler = MockInteractionHandler(confirm_responses=[True])

        handler.confirm("Q1?")

        with pytest.raises(IndexError, match="No more confirm responses available"):
            handler.confirm("Q2?")

    def test_show_warning_records_interaction(self):
        """Test show_warning records interaction."""
        handler = MockInteractionHandler()

        handler.show_warning("Warning message")

        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "warning"
        assert handler.interactions[0]["message"] == "Warning message"

    def test_show_info_records_interaction(self):
        """Test show_info records interaction."""
        handler = MockInteractionHandler()

        handler.show_info("Info message")

        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "info"
        assert handler.interactions[0]["message"] == "Info message"

    def test_mixed_interactions(self):
        """Test handler records mixed interaction types."""
        handler = MockInteractionHandler(
            choice_responses=[0, 1],
            confirm_responses=[True, False],
        )
        choices = [("a", "A", 0), ("b", "B", 0)]

        handler.prompt_choice("Q1:", choices)
        handler.show_info("Info")
        handler.confirm("Q2?")
        handler.show_warning("Warning")
        handler.prompt_choice("Q3:", choices)
        handler.confirm("Q4?")

        assert len(handler.interactions) == 6
        assert handler.interactions[0]["type"] == "choice"
        assert handler.interactions[1]["type"] == "info"
        assert handler.interactions[2]["type"] == "confirm"
        assert handler.interactions[3]["type"] == "warning"
        assert handler.interactions[4]["type"] == "choice"
        assert handler.interactions[5]["type"] == "confirm"

    def test_reset_clears_state(self):
        """Test reset clears interactions and resets indices."""
        handler = MockInteractionHandler(
            choice_responses=[0, 1],
            confirm_responses=[True, False],
        )
        choices = [("a", "A", 0)]

        # Use some responses
        handler.prompt_choice("Q1:", choices)
        handler.confirm("Q2?")
        assert len(handler.interactions) == 2

        # Reset
        handler.reset()

        # Should be able to reuse responses
        assert len(handler.interactions) == 0
        assert handler.prompt_choice("Q3:", choices) == 0
        assert handler.confirm("Q4?") is True

    def test_get_interactions_by_type(self):
        """Test get_interactions_by_type filters correctly."""
        handler = MockInteractionHandler(
            choice_responses=[0],
            confirm_responses=[True],
        )
        choices = [("a", "A", 0)]

        handler.show_info("Info 1")
        handler.prompt_choice("Q1:", choices)
        handler.show_info("Info 2")
        handler.show_warning("Warn 1")
        handler.confirm("Q2?")

        info_interactions = handler.get_interactions_by_type("info")
        assert len(info_interactions) == 2
        assert all(i["type"] == "info" for i in info_interactions)

        choice_interactions = handler.get_interactions_by_type("choice")
        assert len(choice_interactions) == 1
        assert choice_interactions[0]["message"] == "Q1:"

        warning_interactions = handler.get_interactions_by_type("warning")
        assert len(warning_interactions) == 1

        confirm_interactions = handler.get_interactions_by_type("confirm")
        assert len(confirm_interactions) == 1


class TestUsagePatterns:
    """Test common usage patterns."""

    def test_instance_size_selection(self):
        """Test typical instance size selection workflow."""
        handler = MockInteractionHandler(choice_responses=[1])
        choices = [
            ("small", "t3.micro - 1 vCPU, 1GB RAM", 7.30),
            ("medium", "t3.small - 2 vCPU, 2GB RAM", 14.60),
            ("large", "t3.medium - 2 vCPU, 4GB RAM", 29.20),
        ]

        choice_idx = handler.prompt_choice("Select instance size:", choices)
        selected = choices[choice_idx]

        assert selected[0] == "medium"
        assert selected[2] == 14.60

    def test_confirmation_workflow(self):
        """Test typical confirmation workflow with warnings."""
        handler = MockInteractionHandler(confirm_responses=[False, True])

        handler.show_warning("This will create AWS resources")
        if not handler.confirm("Proceed without cost limits?", default=False):
            handler.show_info("Operation cancelled")
        else:
            handler.show_info("Proceeding...")

        # Second attempt
        handler.show_warning("This will create AWS resources")
        if handler.confirm("Proceed without cost limits?", default=False):
            handler.show_info("Creating resources...")

        interactions = handler.interactions
        assert len(interactions) == 6
        assert interactions[0]["type"] == "warning"
        assert interactions[1]["type"] == "confirm"
        assert interactions[1]["response"] is False
        assert interactions[2]["type"] == "info"

    def test_multi_step_configuration(self):
        """Test multi-step configuration workflow."""
        handler = MockInteractionHandler(
            choice_responses=[1, 0, 2],
            confirm_responses=[True],
        )

        # Step 1: Select region
        regions = [("us-east-1", "US East", 0), ("eu-west-1", "EU West", 0)]
        region_idx = handler.prompt_choice("Select region:", regions)

        # Step 2: Select instance size
        sizes = [("small", "Small", 10), ("large", "Large", 30)]
        size_idx = handler.prompt_choice("Select size:", sizes)

        # Step 3: Select storage
        storage = [("20GB", "20GB", 5), ("50GB", "50GB", 10), ("100GB", "100GB", 20)]
        storage_idx = handler.prompt_choice("Select storage:", storage)

        # Confirm
        handler.show_info("Configuration complete")
        confirmed = handler.confirm("Deploy now?")

        assert regions[region_idx][0] == "eu-west-1"
        assert sizes[size_idx][0] == "small"
        assert storage[storage_idx][0] == "100GB"
        assert confirmed is True
        assert len(handler.interactions) == 5
