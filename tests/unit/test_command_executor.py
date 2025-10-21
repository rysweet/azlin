"""Unit tests for agentic command executor module."""

import subprocess
from unittest.mock import Mock, patch

from azlin.agentic import CommandExecutor, ResultValidator


class TestCommandExecutor:
    """Test command executor functionality."""

    def test_init_default(self):
        """Test executor initialization with defaults."""
        executor = CommandExecutor()
        assert executor.dry_run is False
        assert executor.execution_history == []

    def test_init_dry_run(self):
        """Test executor initialization in dry-run mode."""
        executor = CommandExecutor(dry_run=True)
        assert executor.dry_run is True

    def test_execute_dry_run(self):
        """Test command execution in dry-run mode."""
        executor = CommandExecutor(dry_run=True)
        command_spec = {"command": "azlin list", "args": []}

        result = executor.execute(command_spec)

        assert result["success"] is True
        assert result["command"] == "azlin list"
        assert "[DRY RUN]" in result["stdout"]
        assert result["returncode"] == 0

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_success(self, mock_run):
        """Test successful command execution."""
        mock_run.return_value = Mock(stdout="VM list output", stderr="", returncode=0)

        executor = CommandExecutor(dry_run=False)
        command_spec = {"command": "azlin list", "args": []}

        result = executor.execute(command_spec)

        assert result["success"] is True
        assert result["command"] == "azlin list"
        assert result["stdout"] == "VM list output"
        assert result["returncode"] == 0

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_failure(self, mock_run):
        """Test failed command execution."""
        mock_run.return_value = Mock(stdout="", stderr="Error: VM not found", returncode=1)

        executor = CommandExecutor(dry_run=False)
        command_spec = {"command": "azlin status", "args": ["--vm", "nonexistent"]}

        result = executor.execute(command_spec)

        assert result["success"] is False
        assert result["returncode"] == 1
        assert "Error: VM not found" in result["stderr"]

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_with_args(self, mock_run):
        """Test command execution with arguments."""
        mock_run.return_value = Mock(stdout="Success", stderr="", returncode=0)

        executor = CommandExecutor(dry_run=False)
        command_spec = {
            "command": "azlin new",
            "args": ["--name", "test-vm", "--vm-size", "Standard_D2s_v3"],
        }

        result = executor.execute(command_spec)

        # Verify subprocess was called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["azlin", "new", "--name", "test-vm", "--vm-size", "Standard_D2s_v3"]
        assert result["success"] is True

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_timeout(self, mock_run):
        """Test command execution timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="azlin", timeout=300)

        executor = CommandExecutor(dry_run=False)
        command_spec = {"command": "azlin new", "args": ["--name", "test"]}

        result = executor.execute(command_spec)

        assert result["success"] is False
        assert result["returncode"] == -1
        assert "timed out" in result["stderr"]

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_file_not_found(self, mock_run):
        """Test command execution with missing command."""
        mock_run.side_effect = FileNotFoundError("azlin not found")

        executor = CommandExecutor(dry_run=False)
        command_spec = {"command": "azlin", "args": []}

        result = executor.execute(command_spec)

        assert result["success"] is False
        assert result["returncode"] == -1
        assert "Failed to execute" in result["stderr"]

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_permission_error(self, mock_run):
        """Test command execution with permission error."""
        mock_run.side_effect = PermissionError("Permission denied")

        executor = CommandExecutor(dry_run=False)
        command_spec = {"command": "azlin", "args": []}

        result = executor.execute(command_spec)

        assert result["success"] is False
        assert result["returncode"] == -1
        assert "Failed to execute" in result["stderr"]

    def test_execution_history(self):
        """Test that execution history is tracked."""
        executor = CommandExecutor(dry_run=True)

        executor.execute({"command": "azlin list", "args": []})
        executor.execute({"command": "azlin status", "args": []})

        history = executor.get_history()
        assert len(history) == 2
        assert history[0]["command"] == "azlin list"
        assert history[1]["command"] == "azlin status"

    def test_clear_history(self):
        """Test clearing execution history."""
        executor = CommandExecutor(dry_run=True)

        executor.execute({"command": "azlin list", "args": []})
        assert len(executor.get_history()) == 1

        executor.clear_history()
        assert len(executor.get_history()) == 0

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_plan_success(self, mock_run):
        """Test executing multiple commands in sequence."""
        mock_run.return_value = Mock(stdout="Success", stderr="", returncode=0)

        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "azlin list", "args": []},
            {"command": "azlin status", "args": []},
        ]

        results = executor.execute_plan(commands)

        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert mock_run.call_count == 2

    @patch("azlin.agentic.command_executor.subprocess.run")
    def test_execute_plan_stops_on_failure(self, mock_run):
        """Test that execute_plan stops on first failure."""
        # First call succeeds, second fails
        mock_run.side_effect = [
            Mock(stdout="Success", stderr="", returncode=0),
            Mock(stdout="", stderr="Error", returncode=1),
        ]

        executor = CommandExecutor(dry_run=False)
        commands = [
            {"command": "azlin list", "args": []},
            {"command": "azlin kill", "args": ["test-vm"]},
            {"command": "azlin status", "args": []},  # Should not execute
        ]

        results = executor.execute_plan(commands)

        assert len(results) == 2  # Third command not executed
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert mock_run.call_count == 2  # Third call not made

    def test_get_history_returns_copy(self):
        """Test that get_history returns a copy, not the original."""
        executor = CommandExecutor(dry_run=True)
        executor.execute({"command": "azlin list", "args": []})

        history1 = executor.get_history()
        history2 = executor.get_history()

        assert history1 is not history2  # Different objects
        assert history1 == history2  # Same content


class TestResultValidator:
    """Test result validator functionality."""

    def test_init_without_api_key(self, monkeypatch):
        """Test validator initialization without API key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        validator = ResultValidator()
        assert validator.client is None

    def test_init_with_api_key(self):
        """Test validator initialization with API key."""
        validator = ResultValidator(api_key="test-key")
        assert validator.api_key == "test-key"
        assert validator.client is not None

    def test_validate_without_ai_all_success(self):
        """Test validation without AI when all commands succeed."""
        validator = ResultValidator(api_key=None)

        intent = {"intent": "list_vms", "parameters": {}}
        results = [{"success": True, "command": "azlin list", "stdout": "VM1\nVM2"}]

        validation = validator.validate(intent, results)

        assert validation["success"] is True
        assert "successfully" in validation["message"].lower()
        assert "details" in validation

    def test_validate_without_ai_has_failure(self):
        """Test validation without AI when some commands fail."""
        validator = ResultValidator(api_key=None)

        intent = {"intent": "provision_vm", "parameters": {"vm_name": "test"}}
        results = [
            {"success": True, "command": "azlin new", "stdout": "Creating..."},
            {"success": False, "command": "azlin status", "stderr": "VM not found"},
        ]

        validation = validator.validate(intent, results)

        assert validation["success"] is False
        assert "failed" in validation["message"].lower()

    @patch("anthropic.Anthropic")
    def test_validate_with_ai_success(self, mock_anthropic):
        """Test AI-powered validation with successful commands."""
        import json

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {"success": True, "message": "All VMs listed successfully", "issues": []}
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        validator = ResultValidator(api_key="test-key")

        intent = {"intent": "list_vms"}
        results = [{"success": True, "stdout": "VM1\nVM2"}]

        validation = validator.validate(intent, results)

        assert validation["success"] is True
        assert "successfully" in validation["message"].lower()

    @patch("anthropic.Anthropic")
    def test_validate_with_ai_identifies_issues(self, mock_anthropic):
        """Test AI-powered validation that identifies issues."""
        import json

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "success": False,
                        "message": "VM creation failed due to quota limits",
                        "issues": ["Azure quota exceeded", "Try smaller VM size"],
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        validator = ResultValidator(api_key="test-key")

        intent = {"intent": "provision_vm", "parameters": {"vm_name": "test"}}
        results = [{"success": False, "stderr": "QuotaExceeded"}]

        validation = validator.validate(intent, results)

        assert validation["success"] is False
        assert "quota" in validation["message"].lower()
        assert len(validation["issues"]) == 2

    @patch("anthropic.Anthropic")
    def test_validate_with_ai_error_fallback(self, mock_anthropic):
        """Test that validation falls back on AI error."""
        mock_client = Mock()
        mock_request = Mock()
        from anthropic import APIError

        mock_client.messages.create.side_effect = APIError(
            "API Error", request=mock_request, body=None
        )
        mock_anthropic.return_value = mock_client

        validator = ResultValidator(api_key="test-key")

        intent = {"intent": "list_vms"}
        results = [{"success": True, "stdout": "VM1"}]

        validation = validator.validate(intent, results)

        # Should fall back to simple validation
        assert "success" in validation
        assert validation["success"] is True

    @patch("anthropic.Anthropic")
    def test_validate_with_ai_invalid_json_fallback(self, mock_anthropic):
        """Test validation falls back when AI returns invalid JSON."""
        mock_response = Mock()
        mock_response.content = [Mock(text="This is not valid JSON")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        validator = ResultValidator(api_key="test-key")

        intent = {"intent": "list_vms"}
        results = [{"success": True}]

        validation = validator.validate(intent, results)

        # Should fall back to simple validation
        assert validation["success"] is True
