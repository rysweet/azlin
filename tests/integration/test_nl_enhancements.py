"""Integration tests for Natural Language Enhancements.

Tests the complete workflow:
1. SessionContext tracks entities
2. IntentParser uses session context for pronoun resolution
3. CommandExecutor provides progress and error enhancement
4. ErrorAnalyzer provides actionable suggestions
"""

from azlin.agentic.command_executor import CommandExecutor
from azlin.agentic.error_analyzer import ErrorAnalyzer
from azlin.agentic.session_context import SessionContext


class TestSessionContextIntegration:
    """Test SessionContext integration with full workflow."""

    def test_session_context_basic_flow(self):
        """Test basic session context tracking."""
        # Create session
        session = SessionContext()

        # Simulate user creating a VM
        session.add_command("create vm test-vm", {"vm": ["test-vm"], "resource_group": ["my-rg"]})

        # Get context for next command
        context = session.get_context()

        # Verify context contains last entities
        assert context["last_entities"]["vm"] == "test-vm"
        assert context["last_entities"]["resource_group"] == "my-rg"
        assert len(context["recent_commands"]) == 1
        assert "create vm test-vm" in context["recent_commands"]

    def test_pronoun_resolution_flow(self):
        """Test pronoun resolution in context."""
        session = SessionContext()

        # User creates a VM
        session.add_command("create vm my-test-vm", {"vm": ["my-test-vm"]})

        # User says "start it"
        resolved_vm = session.resolve_pronoun("it", "vm")
        assert resolved_vm == "my-test-vm"

        # User says "THAT" (case insensitive)
        resolved_vm = session.resolve_pronoun("THAT", "vm")
        assert resolved_vm == "my-test-vm"

    def test_multiple_commands_in_session(self):
        """Test session tracking across multiple commands."""
        session = SessionContext(max_history=5)

        # Sequence of commands
        session.add_command("create vm vm1", {"vm": ["vm1"]})
        session.add_command("start vm1", {"vm": ["vm1"]})
        session.add_command("create vm vm2", {"vm": ["vm2"]})

        # Last VM should be vm2
        assert session.last_entities["vm"] == "vm2"

        # Recent commands should include all 3
        context = session.get_context()
        assert len(context["recent_commands"]) == 3

    def test_session_expiry(self):
        """Test session expiry detection."""
        from datetime import datetime, timedelta

        session = SessionContext()
        session.add_command("test", {"vm": ["test"]})

        # Not expired immediately
        assert not session.is_expired(timeout_hours=1.0)

        # Simulate 2 hours passing
        session.last_used = datetime.now() - timedelta(hours=2)
        assert session.is_expired(timeout_hours=1.0)


class TestWorkflowExecutionIntegration:
    """Test workflow execution with progress and error handling."""

    def test_workflow_with_progress(self):
        """Test complete workflow with progress reporting."""
        executor = CommandExecutor(dry_run=True)

        commands = [
            {"command": "azlin list", "args": []},
            {"command": "azlin status", "args": []},
            {"command": "azlin cost", "args": []},
        ]

        progress_log = []

        def log_progress(current, total, description):
            progress_log.append(f"[{current}/{total}] {description}")

        results = executor.execute_workflow(commands, progress_callback=log_progress)

        # All commands succeeded
        assert all(r["success"] for r in results)

        # Progress was reported for each
        assert len(progress_log) == 3
        assert "[1/3] Executing azlin list" in progress_log
        assert "[2/3] Executing azlin status" in progress_log
        assert "[3/3] Executing azlin cost" in progress_log

    def test_workflow_with_error_enhancement(self):
        """Test workflow with error analysis."""
        executor = CommandExecutor(dry_run=False)

        # Command that will fail
        commands = [{"command": "nonexistent_cmd_xyz", "args": []}]

        results = executor.execute_workflow(commands)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "error_enhanced" in results[0]

    def test_workflow_stop_on_error_integration(self):
        """Test stop_on_error behavior in workflow."""
        executor = CommandExecutor(dry_run=False)

        commands = [
            {"command": "echo", "args": ["first"]},
            {"command": "nonexistent_xyz", "args": []},  # Will fail
            {"command": "echo", "args": ["third"]},
        ]

        # Stop on error
        results_stop = executor.execute_workflow(commands, stop_on_error=True)
        assert len(results_stop) == 2  # Stopped after failure

        # Clear history for next test
        executor.clear_history()

        # Continue on error
        results_continue = executor.execute_workflow(commands, stop_on_error=False)
        assert len(results_continue) == 3  # Executed all


class TestErrorAnalyzerIntegration:
    """Test ErrorAnalyzer integration with real-world scenarios."""

    def test_analyzer_with_common_azure_errors(self):
        """Test analyzer recognizes and enhances common errors."""
        analyzer = ErrorAnalyzer()

        # Test various error scenarios
        error_cases = [
            ("azlin new", "AuthenticationFailed", "az login"),
            ("azlin new", "ResourceGroupNotFound", "azlin config set-rg"),
            ("azlin start vm1", "VMNotFound", "azlin list"),
            ("azlin new", "QuotaExceeded", "different region"),
            ("azlin storage create test", "StorageAccountAlreadyExists", "globally unique"),
        ]

        for command, error_pattern, expected_suggestion in error_cases:
            stderr = f"ERROR: {error_pattern}: some details here"
            result = analyzer.analyze(command, stderr)

            # Check that suggestion is present and relevant
            assert "Suggestion:" in result
            assert expected_suggestion in result

    def test_analyzer_fallback_for_unknown_errors(self):
        """Test analyzer provides fallback for unknown errors."""
        analyzer = ErrorAnalyzer()

        stderr = "CompletePlatelyUnknownError: This is not a recognized Azure error"
        result = analyzer.analyze("azlin test", stderr)

        # Should include original error
        assert "CompletePlatelyUnknownError" in result
        # Should include generic suggestion
        assert "Suggestion:" in result
        assert "--help" in result


class TestEndToEndNLWorkflow:
    """End-to-end tests simulating real user workflows."""

    def test_create_then_start_workflow(self):
        """Test 'create vm' then 'start it' workflow."""
        # Initialize components
        session = SessionContext()
        executor = CommandExecutor(dry_run=True)

        # Step 1: User creates a VM (simulated)
        session.add_command("create vm test-vm", {"vm": ["test-vm"]})

        # Step 2: User says "start it" - would resolve to test-vm
        vm_name = session.resolve_pronoun("it", "vm")
        assert vm_name == "test-vm"

        # Step 3: Execute start command with progress
        commands = [{"command": "azlin start", "args": [vm_name]}]

        progress_log = []

        def log_progress(current, total, description):
            progress_log.append(description)

        results = executor.execute_workflow(commands, progress_callback=log_progress)

        # Verify execution
        assert results[0]["success"] is True
        assert "test-vm" in results[0]["command"]
        assert len(progress_log) == 1

    def test_multi_vm_workflow_with_context(self):
        """Test workflow with multiple VMs and context switching."""
        session = SessionContext()

        # Create multiple VMs
        session.add_command("create vm vm1", {"vm": ["vm1"]})
        session.add_command("create vm vm2", {"vm": ["vm2"]})
        session.add_command("create vm vm3", {"vm": ["vm3"]})

        # Context should track last VM
        assert session.last_entities["vm"] == "vm3"

        # Recent commands should be limited to last 5
        context = session.get_context()
        assert len(context["recent_commands"]) == 3

    def test_workflow_with_error_and_recovery(self):
        """Test workflow with error, then recovery."""
        session = SessionContext()
        executor = CommandExecutor(dry_run=False)
        analyzer = ErrorAnalyzer()

        # Step 1: Try to start non-existent VM
        commands = [{"command": "azlin", "args": ["invalid_subcommand"]}]
        results = executor.execute_workflow(commands)

        # Should fail with enhanced error
        assert results[0]["success"] is False
        assert "error_enhanced" in results[0]

        # Step 2: Simulate user following suggestion (listing VMs)
        commands_recovery = [{"command": "echo", "args": ["list"]}]  # Simulated
        results_recovery = executor.execute_workflow(commands_recovery)

        assert results_recovery[0]["success"] is True


class TestPerformanceCharacteristics:
    """Test performance aspects of NL enhancements."""

    def test_session_context_performance(self):
        """Test that SessionContext handles many commands efficiently."""
        import time

        session = SessionContext(max_history=100)

        start_time = time.time()

        # Add 1000 commands
        for i in range(1000):
            session.add_command(f"command {i}", {"vm": [f"vm{i}"]})

        elapsed = time.time() - start_time

        # Should be very fast (<0.1s for 1000 commands)
        assert elapsed < 0.1

        # Should only keep last 100
        context = session.get_context()
        assert len(context["recent_commands"]) == 5  # get_context limits to 5

    def test_error_analyzer_performance(self):
        """Test that ErrorAnalyzer is fast."""
        import time

        analyzer = ErrorAnalyzer()

        # Test with various error messages
        errors = [
            "AuthenticationFailed: Auth failed",
            "ResourceGroupNotFound: RG not found",
            "VMNotFound: VM not found",
            "QuotaExceeded: Quota exceeded",
            "Unknown error message",
        ]

        start_time = time.time()

        # Analyze 1000 errors
        for _ in range(200):
            for error in errors:
                analyzer.analyze("azlin test", error)

        elapsed = time.time() - start_time

        # Should be fast (<1s for 1000 analyses)
        assert elapsed < 1.0

    def test_workflow_execution_performance(self):
        """Test workflow execution is efficient."""
        import time

        executor = CommandExecutor(dry_run=True)

        # Create 50 commands
        commands = [{"command": "azlin list", "args": []} for _ in range(50)]

        start_time = time.time()

        results = executor.execute_workflow(commands)

        elapsed = time.time() - start_time

        # Should be fast in dry-run mode (<0.5s)
        assert elapsed < 0.5
        assert len(results) == 50


class TestEdgeCasesIntegration:
    """Test edge cases in integrated workflow."""

    def test_empty_session_context(self):
        """Test workflow with empty session context."""
        session = SessionContext()

        # No commands added yet
        context = session.get_context()

        assert len(context["last_entities"]) == 0
        assert len(context["recent_commands"]) == 0

        # Should handle pronoun resolution gracefully
        result = session.resolve_pronoun("it", "vm")
        assert result is None

    def test_workflow_with_none_entities(self):
        """Test session handles None entities."""
        session = SessionContext()

        # Add command with None entities
        session.add_command("list vms", None)

        # Should not crash
        context = session.get_context()
        assert len(context["recent_commands"]) == 1

    def test_error_analyzer_with_empty_error(self):
        """Test error analyzer handles empty error gracefully."""
        analyzer = ErrorAnalyzer()

        result = analyzer.analyze("azlin test", "")
        assert "Command failed with no error message" in result

    def test_workflow_with_malformed_commands(self):
        """Test workflow handles malformed command specs."""
        executor = CommandExecutor(dry_run=True)

        # Command without args key
        commands = [{"command": "azlin list"}]

        # Should handle gracefully
        results = executor.execute_workflow(commands)
        assert len(results) == 1
