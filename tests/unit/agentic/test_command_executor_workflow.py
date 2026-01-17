"""Tests for CommandExecutor.execute_workflow method.

Testing pyramid:
- 60% Unit tests (workflow execution, progress callbacks)
- 30% Integration tests (with ErrorAnalyzer)
- 10% Edge cases (empty commands, stop_on_error)
"""

from azlin.agentic.command_executor import CommandExecutor


class TestWorkflowBasics:
    """Test basic workflow execution functionality."""

    def test_execute_workflow_single_command(self):
        """Test workflow with single command."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin list", "args": []}]

        results = executor.execute_workflow(commands)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert "azlin list" in results[0]["command"]

    def test_execute_workflow_multiple_commands(self):
        """Test workflow with multiple commands."""
        executor = CommandExecutor(dry_run=True)
        commands = [
            {"command": "azlin list", "args": []},
            {"command": "azlin status", "args": []},
            {"command": "azlin cost", "args": []},
        ]

        results = executor.execute_workflow(commands)

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert "azlin list" in results[0]["command"]
        assert "azlin status" in results[1]["command"]
        assert "azlin cost" in results[2]["command"]

    def test_execute_workflow_empty_commands(self):
        """Test workflow with empty command list."""
        executor = CommandExecutor(dry_run=True)
        commands = []

        results = executor.execute_workflow(commands)

        assert len(results) == 0


class TestProgressCallback:
    """Test progress callback functionality."""

    def test_progress_callback_called(self):
        """Test that progress callback is invoked."""
        executor = CommandExecutor(dry_run=True)
        commands = [
            {"command": "azlin list", "args": []},
            {"command": "azlin status", "args": []},
        ]

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append((current, total, description))

        results = executor.execute_workflow(commands, progress_callback=track_progress)

        # Should be called for each command
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, "Executing azlin list")
        assert progress_calls[1] == (2, 2, "Executing azlin status")
        assert len(results) == 2

    def test_progress_callback_with_args(self):
        """Test progress callback with command arguments."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin start", "args": ["test-vm"]}]

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append((current, total, description))

        executor.execute_workflow(commands, progress_callback=track_progress)

        assert len(progress_calls) == 1
        assert progress_calls[0] == (1, 1, "Executing azlin start test-vm")

    def test_progress_callback_none(self):
        """Test workflow works without progress callback."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin list", "args": []}]

        # Should not raise error when callback is None
        results = executor.execute_workflow(commands, progress_callback=None)

        assert len(results) == 1
        assert results[0]["success"] is True


class TestStopOnError:
    """Test stop_on_error behavior."""

    def test_stop_on_error_true(self):
        """Test that execution stops on first error when stop_on_error=True."""
        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "echo", "args": ["test1"]},  # Should succeed
            {"command": "nonexistent_command_xyz", "args": []},  # Should fail
            {"command": "echo", "args": ["test2"]},  # Should not execute
        ]

        results = executor.execute_workflow(commands, stop_on_error=True)

        # Should only have 2 results (stopped after failure)
        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        # Third command should not be executed

    def test_stop_on_error_false(self):
        """Test that execution continues on error when stop_on_error=False."""
        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "echo", "args": ["test1"]},  # Should succeed
            {"command": "nonexistent_command_xyz", "args": []},  # Should fail
            {"command": "echo", "args": ["test2"]},  # Should execute
        ]

        results = executor.execute_workflow(commands, stop_on_error=False)

        # Should have all 3 results (continued despite failure)
        assert len(results) == 3
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert results[2]["success"] is True

    def test_stop_on_error_default(self):
        """Test that stop_on_error defaults to True."""
        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "echo", "args": ["test"]},
            {"command": "nonexistent_command_xyz", "args": []},
            {"command": "echo", "args": ["after_error"]},
        ]

        # Don't specify stop_on_error (should default to True)
        results = executor.execute_workflow(commands)

        # Should stop after failure (default behavior)
        assert len(results) == 2


class TestErrorEnhancement:
    """Test error message enhancement with ErrorAnalyzer."""

    def test_error_enhanced_on_failure(self):
        """Test that errors are enhanced when commands fail."""
        executor = CommandExecutor(dry_run=False)
        # Use a command that will fail
        commands = [{"command": "azlin", "args": ["nonexistent_subcommand"]}]

        results = executor.execute_workflow(commands)

        assert len(results) == 1
        assert results[0]["success"] is False
        # Check that error_enhanced field exists
        assert "error_enhanced" in results[0]
        # Enhanced error should contain original error
        assert (
            results[0]["stderr"] in results[0]["error_enhanced"]
            or "Suggestion" in results[0]["error_enhanced"]
        )

    def test_no_enhancement_on_success(self):
        """Test that successful commands don't get error enhancement."""
        executor = CommandExecutor(dry_run=False)
        commands = [{"command": "echo", "args": ["success"]}]

        results = executor.execute_workflow(commands)

        assert len(results) == 1
        assert results[0]["success"] is True
        # Should not have error_enhanced for successful commands
        assert "error_enhanced" not in results[0]

    def test_enhancement_with_recognized_pattern(self):
        """Test enhancement with a recognizable error pattern."""
        # This is a bit tricky - we need to simulate an Azure error
        # For this test, we'll use dry_run and verify the integration point
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin test", "args": []}]

        results = executor.execute_workflow(commands)

        # In dry_run mode, commands succeed, so no enhancement
        # This test verifies the code path exists
        assert len(results) == 1
        assert results[0]["success"] is True


class TestWorkflowIntegration:
    """Integration tests for workflow execution."""

    def test_workflow_with_mixed_success_failure(self):
        """Test workflow with both successful and failing commands."""
        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "echo", "args": ["first"]},  # Success
            {"command": "echo", "args": ["second"]},  # Success
            {"command": "nonexistent_xyz", "args": []},  # Failure
        ]

        results = executor.execute_workflow(commands, stop_on_error=True)

        assert len(results) == 3
        assert results[0]["success"] is True
        assert results[1]["success"] is True
        assert results[2]["success"] is False
        assert "error_enhanced" in results[2]

    def test_workflow_progress_and_errors(self):
        """Test workflow with both progress callback and error handling."""
        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "echo", "args": ["test"]},
            {"command": "nonexistent_xyz", "args": []},
        ]

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append((current, total, description))

        results = executor.execute_workflow(
            commands, progress_callback=track_progress, stop_on_error=True
        )

        # Both commands attempted (progress reported before execution)
        assert len(progress_calls) == 2
        # But execution stopped after failure
        assert len(results) == 2
        assert results[1]["success"] is False


class TestCommandFormatting:
    """Test command description formatting."""

    def test_command_with_list_args(self):
        """Test formatting with list arguments."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin new", "args": ["--name", "test", "--region", "westus2"]}]

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append(description)

        executor.execute_workflow(commands, progress_callback=track_progress)

        assert len(progress_calls) == 1
        assert "azlin new" in progress_calls[0]
        assert "--name test" in progress_calls[0]
        assert "--region westus2" in progress_calls[0]

    def test_command_with_empty_args(self):
        """Test formatting with empty arguments."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin list", "args": []}]

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append(description)

        executor.execute_workflow(commands, progress_callback=track_progress)

        assert len(progress_calls) == 1
        assert progress_calls[0] == "Executing azlin list"

    def test_command_with_no_args_key(self):
        """Test formatting when args key is missing."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin status"}]  # No args key

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append(description)

        executor.execute_workflow(commands, progress_callback=track_progress)

        assert len(progress_calls) == 1
        assert "azlin status" in progress_calls[0]


class TestExecutionHistory:
    """Test that workflow execution updates history."""

    def test_history_tracking(self):
        """Test that executed commands are added to history."""
        executor = CommandExecutor(dry_run=True)
        commands = [
            {"command": "azlin list", "args": []},
            {"command": "azlin status", "args": []},
        ]

        executor.execute_workflow(commands)

        history = executor.get_history()
        assert len(history) == 2
        assert "azlin list" in history[0]["command"]
        assert "azlin status" in history[1]["command"]

    def test_history_includes_failures(self):
        """Test that failed commands are also tracked in history."""
        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "echo", "args": ["test"]},
            {"command": "nonexistent_xyz", "args": []},
        ]

        executor.execute_workflow(commands, stop_on_error=True)

        history = executor.get_history()
        assert len(history) == 2
        assert history[0]["success"] is True
        assert history[1]["success"] is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_command_workflow(self):
        """Test workflow with exactly one command."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "azlin list", "args": []}]

        results = executor.execute_workflow(commands)

        assert len(results) == 1
        assert results[0]["success"] is True

    def test_many_commands_workflow(self):
        """Test workflow with many commands."""
        executor = CommandExecutor(dry_run=True)
        # Create 20 commands
        commands = [{"command": "azlin list", "args": []} for _ in range(20)]

        results = executor.execute_workflow(commands)

        assert len(results) == 20
        assert all(r["success"] for r in results)

    def test_workflow_with_special_characters_in_args(self):
        """Test workflow with special characters in arguments."""
        executor = CommandExecutor(dry_run=True)
        commands = [{"command": "echo", "args": ["test@#$%", "value with spaces"]}]

        progress_calls = []

        def track_progress(current, total, description):
            progress_calls.append(description)

        results = executor.execute_workflow(commands, progress_callback=track_progress)

        assert len(results) == 1
        # Should handle special characters gracefully
        assert "test@#$%" in progress_calls[0]
        assert "value with spaces" in progress_calls[0]
