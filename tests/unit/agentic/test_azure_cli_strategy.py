"""Tests for AzureCLIStrategy.

Tests Azure CLI command generation, execution, and error handling.
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.agentic.strategies.azure_cli import AzureCLIStrategy
from azlin.agentic.types import ExecutionContext, FailureType, Intent, Strategy


@pytest.fixture
def intent_provision_vm():
    """Intent for provisioning a VM."""
    return Intent(
        intent="provision_vm",
        parameters={"vm_name": "test-vm"},
        confidence=0.9,
        azlin_commands=[{"command": "new", "args": ["--name", "test-vm"]}],
    )


@pytest.fixture
def intent_list_vms():
    """Intent for listing VMs."""
    return Intent(
        intent="list_vms",
        parameters={},
        confidence=0.9,
        azlin_commands=[{"command": "list", "args": []}],
    )


@pytest.fixture
def execution_context(intent_provision_vm):
    """Execution context for testing."""
    return ExecutionContext(
        objective_id="obj_test",
        intent=intent_provision_vm,
        strategy=Strategy.AZURE_CLI,
        resource_group="test-rg",
    )


class TestCanHandle:
    """Tests for can_handle method."""

    @patch("subprocess.run")
    def test_can_handle_simple_vm(self, mock_run):
        """Can handle simple VM provisioning."""
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=0),  # az account show
        ]

        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        assert strategy.can_handle(context) is True

    def test_can_handle_code_generation(self):
        """Cannot handle code generation."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="generate_code",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        assert strategy.can_handle(context) is False

    @patch("subprocess.run")
    def test_can_handle_complex_aks(self, mock_run):
        """Prefers not to handle complex AKS."""
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=0),  # az account show
        ]

        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_aks_cluster",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        assert strategy.can_handle(context) is False


class TestValidate:
    """Tests for validation."""

    @patch("subprocess.run")
    def test_validate_success(self, mock_run):
        """Validation passes when az CLI is installed and authenticated."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="azure-cli 2.50.0"),  # az --version
            Mock(returncode=0, stdout='{"id": "..."}'),  # az account show
        ]

        strategy = AzureCLIStrategy()
        context = ExecutionContext(
            objective_id="test",
            intent=Intent(intent="test", parameters={}, confidence=0.9, azlin_commands=[{"command": "azlin", "args": []}]),
            strategy=Strategy.AZURE_CLI,
        )

        valid, error = strategy.validate(context)

        assert valid is True
        assert error is None

    @patch("subprocess.run")
    def test_validate_az_not_installed(self, mock_run):
        """Validation fails when az CLI not installed."""
        mock_run.side_effect = FileNotFoundError()

        strategy = AzureCLIStrategy()
        context = ExecutionContext(
            objective_id="test",
            intent=Intent(intent="test", parameters={}, confidence=0.9, azlin_commands=[{"command": "azlin", "args": []}]),
            strategy=Strategy.AZURE_CLI,
        )

        valid, error = strategy.validate(context)

        assert valid is False
        assert "not found" in error.lower()

    @patch("subprocess.run")
    def test_validate_not_authenticated(self, mock_run):
        """Validation fails when not authenticated."""
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=1, stderr="Please run 'az login'"),  # az account show
        ]

        strategy = AzureCLIStrategy()
        context = ExecutionContext(
            objective_id="test",
            intent=Intent(intent="test", parameters={}, confidence=0.9, azlin_commands=[{"command": "azlin", "args": []}]),
            strategy=Strategy.AZURE_CLI,
        )

        valid, error = strategy.validate(context)

        assert valid is False
        assert "authenticated" in error.lower()


class TestExecute:
    """Tests for execute method."""

    @patch("subprocess.run")
    def test_execute_dry_run(self, mock_run, execution_context):
        """Dry run shows commands without executing."""
        # Mock validation calls
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=0),  # az account show
        ]

        execution_context.dry_run = True

        strategy = AzureCLIStrategy()
        result = strategy.execute(execution_context)

        assert result.success is True
        assert "DRY RUN" in result.output
        assert result.metadata["dry_run"] is True
        # Only validation calls, no actual command execution
        assert mock_run.call_count == 2  # Just validation

    @patch("subprocess.run")
    def test_execute_success(self, mock_run):
        """Successful execution."""
        # Validation calls
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=0),  # az account show
            # Actual command execution
            Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "id": "/subscriptions/.../resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
                    }
                ),
                stderr="",
            ),
        ]

        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test-vm"},
            confidence=0.9,
            azlin_commands=[{"command": "new", "args": ["--name", "test-vm"]}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
            resource_group="test-rg",
        )

        result = strategy.execute(context)

        assert result.success is True
        assert result.strategy == Strategy.AZURE_CLI
        assert len(result.resources_created) > 0
        assert result.duration_seconds is not None

    @patch("subprocess.run")
    def test_execute_command_failure(self, mock_run):
        """Command execution fails."""
        # Validation calls
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=0),  # az account show
            # Failed command execution
            Mock(
                returncode=1,
                stdout="",
                stderr="Error: QuotaExceeded - Maximum number of VMs reached",
            ),
        ]

        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test-vm"},
            confidence=0.9,
            azlin_commands=[{"command": "new", "args": ["--name", "test-vm"]}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
            resource_group="test-rg",
        )

        result = strategy.execute(context)

        assert result.success is False
        assert result.failure_type == FailureType.QUOTA_EXCEEDED
        assert "quota" in result.error.lower()

    @patch("subprocess.run")
    def test_execute_timeout(self, mock_run):
        """Command times out."""
        # Validation calls
        mock_run.side_effect = [
            Mock(returncode=0),  # az --version
            Mock(returncode=0),  # az account show
            # Timeout during execution
            subprocess.TimeoutExpired(cmd="az vm create", timeout=600),
        ]

        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test-vm"},
            confidence=0.9,
            azlin_commands=[{"command": "new", "args": ["--name", "test-vm"]}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
            resource_group="test-rg",
        )

        result = strategy.execute(context)

        assert result.success is False
        assert "timed out" in result.error.lower()


class TestCommandGeneration:
    """Tests for command generation."""

    def test_convert_azlin_new_to_az(self):
        """Convert azlin new to az vm create."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test-vm"},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
            resource_group="test-rg",
        )

        az_cmd = strategy._convert_azlin_to_az("new", [], context)

        assert "az vm create" in az_cmd
        assert "test-vm" in az_cmd
        assert "test-rg" in az_cmd

    def test_convert_azlin_list_to_az(self):
        """Convert azlin list to az vm list."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="list_vms",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        az_cmd = strategy._convert_azlin_to_az("list", [], context)

        assert "az vm list" in az_cmd

    def test_convert_azlin_kill_to_az(self):
        """Convert azlin kill to az vm delete."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="delete_vm",
            parameters={"vm_name": "old-vm"},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
            resource_group="test-rg",
        )

        az_cmd = strategy._convert_azlin_to_az("kill", [], context)

        assert "az vm delete" in az_cmd
        assert "old-vm" in az_cmd

    def test_infer_commands_provision_vm(self):
        """Infer az commands for VM provisioning."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "new-vm"},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
            resource_group="test-rg",
        )

        commands = strategy._infer_commands_from_intent(context)

        assert len(commands) > 0
        assert "az vm create" in commands[0]

    def test_infer_commands_list_vms(self):
        """Infer az commands for listing VMs."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="list_vms",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        commands = strategy._infer_commands_from_intent(context)

        assert len(commands) > 0
        assert "az vm list" in commands[0]


class TestResourceExtraction:
    """Tests for extracting resource IDs."""

    def test_extract_resources_from_json(self):
        """Extract resource ID from JSON output."""
        strategy = AzureCLIStrategy()
        output = json.dumps(
            {
                "id": "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
            }
        )

        resources = strategy._extract_resources(output, "az vm create")

        assert len(resources) == 1
        assert "virtualMachines/vm1" in resources[0]

    def test_extract_resources_from_text(self):
        """Extract resource ID from text output."""
        strategy = AzureCLIStrategy()
        output = "Created VM: /subscriptions/abc-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        resources = strategy._extract_resources(output, "az vm create")

        assert len(resources) >= 1
        # Should find the resource ID pattern
        assert any("virtualMachines/test-vm" in r for r in resources)

    def test_extract_resources_no_matches(self):
        """No resources extracted from plain text."""
        strategy = AzureCLIStrategy()
        output = "Operation completed successfully"

        resources = strategy._extract_resources(output, "az vm create")

        assert len(resources) == 0


class TestFailureClassification:
    """Tests for classifying failure types."""

    def test_classify_quota_exceeded(self):
        """Classify quota exceeded error."""
        strategy = AzureCLIStrategy()
        error = "Error: QuotaExceeded - Maximum number of VMs has been exceeded"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.QUOTA_EXCEEDED

    def test_classify_resource_not_found(self):
        """Classify resource not found error."""
        strategy = AzureCLIStrategy()
        error = "Error: Resource 'vm-123' does not exist"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.RESOURCE_NOT_FOUND

    def test_classify_permission_denied(self):
        """Classify permission error."""
        strategy = AzureCLIStrategy()
        error = "Error: Unauthorized - You do not have permission to perform this action"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.PERMISSION_DENIED

    def test_classify_timeout(self):
        """Classify timeout error."""
        strategy = AzureCLIStrategy()
        error = "Error: Operation timed out after 600 seconds"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.TIMEOUT

    def test_classify_network_error(self):
        """Classify network error."""
        strategy = AzureCLIStrategy()
        error = "Error: Network connection failed"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.NETWORK_ERROR

    def test_classify_validation_error(self):
        """Classify validation error."""
        strategy = AzureCLIStrategy()
        error = "Error: Invalid VM size 'Standard_INVALID'"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.VALIDATION_ERROR

    def test_classify_unknown_error(self):
        """Classify unknown error."""
        strategy = AzureCLIStrategy()
        error = "Error: Something unexpected happened"

        failure_type = strategy._classify_failure(error)

        assert failure_type == FailureType.UNKNOWN


class TestEstimateDuration:
    """Tests for duration estimation."""

    def test_estimate_duration_provision_vm(self):
        """Estimate duration for VM provisioning."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        duration = strategy.estimate_duration(context)

        # VM provisioning takes 5-10 minutes
        assert duration >= 300  # At least 5 minutes

    def test_estimate_duration_list_vms(self):
        """Estimate duration for listing VMs."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="list_vms",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        duration = strategy.estimate_duration(context)

        # Listing is fast
        assert duration <= 30

    def test_estimate_duration_delete_vm(self):
        """Estimate duration for deleting VM."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="delete_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        duration = strategy.estimate_duration(context)

        # Deletion is moderate speed
        assert duration >= 60
        assert duration <= 300


class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_strategy_type(self):
        """Get strategy type."""
        strategy = AzureCLIStrategy()

        assert strategy.get_strategy_type() == Strategy.AZURE_CLI

    def test_get_prerequisites(self):
        """Get prerequisites list."""
        strategy = AzureCLIStrategy()

        prereqs = strategy.get_prerequisites()

        assert len(prereqs) > 0
        assert any("az cli" in p.lower() for p in prereqs)

    def test_supports_dry_run(self):
        """Supports dry run."""
        strategy = AzureCLIStrategy()

        assert strategy.supports_dry_run() is True

    def test_get_cost_factors_vm(self):
        """Get cost factors for VM."""
        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test", "vm_size": "Standard_D4s_v3"},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        factors = strategy.get_cost_factors(context)

        assert "vm_size" in factors
        assert factors["vm_size"] == "Standard_D4s_v3"

    @patch("subprocess.run")
    def test_cleanup_on_failure(self, mock_run):
        """Cleanup resources on failure."""
        mock_run.return_value = Mock(returncode=0)

        strategy = AzureCLIStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{"command": "azlin", "args": []}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.AZURE_CLI,
        )

        resources = ["/subscriptions/.../virtualMachines/test-vm"]

        # Should not raise exception
        strategy.cleanup_on_failure(context, resources)

        # Should attempt to delete resource
        mock_run.assert_called()
        call_args = mock_run.call_args[0][0]
        assert "az resource delete" in " ".join(call_args)
