"""Integration tests for Bastion auto-creation workflow.

Tests the complete workflow from detection to provisioning:
- Cost estimation before user decision
- User interaction prompts (mocked)
- Resource orchestrator integration
- BastionProvisioner operations
- Prerequisite checking
- Resource creation and rollback

These tests follow the testing pyramid: focused integration tests
that verify component interactions without full E2E Azure operations.
"""

from unittest.mock import Mock, patch

import pytest

from azlin.modules.bastion_provisioner import (
    BastionProvisioner,
    BastionProvisionerError,
)
from azlin.modules.cost_estimator import CostEstimator
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.modules.resource_orchestrator import (
    BastionOptions,
    DecisionAction,
    ResourceOrchestrator,
    ResourceType,
)


class TestBastionCostEstimation:
    """Test cost estimation for Bastion resources."""

    def test_estimate_bastion_standard_cost(self):
        """Test estimating Standard SKU Bastion cost."""
        # Act
        cost = CostEstimator.estimate_bastion_cost("Standard")

        # Assert
        assert cost == 292.65  # $289 Bastion + $3.65 public IP
        formatted = CostEstimator.format_cost(cost)
        assert formatted == "$292.65/month"

    def test_estimate_bastion_basic_cost(self):
        """Test estimating Basic SKU Bastion cost."""
        # Act
        cost = CostEstimator.estimate_bastion_cost("Basic")

        # Assert
        assert cost == 143.65  # $140 Bastion + $3.65 public IP
        formatted = CostEstimator.format_cost(cost)
        assert formatted == "$143.65/month"

    def test_estimate_bastion_invalid_sku(self):
        """Test error handling for invalid SKU."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid Bastion SKU"):
            CostEstimator.estimate_bastion_cost("InvalidSKU")

    def test_estimate_bastion_case_insensitive(self):
        """Test SKU name is case-insensitive."""
        # Act
        cost1 = CostEstimator.estimate_bastion_cost("STANDARD")
        cost2 = CostEstimator.estimate_bastion_cost("standard")
        cost3 = CostEstimator.estimate_bastion_cost("Standard")

        # Assert
        assert cost1 == cost2 == cost3


class TestInteractionHandlerMock:
    """Test MockInteractionHandler for deterministic testing."""

    def test_mock_choice_response(self):
        """Test pre-programmed choice responses."""
        # Arrange
        handler = MockInteractionHandler(choice_responses=[1])
        choices = [
            ("option1", "First option", 10.0),
            ("option2", "Second option", 20.0),
        ]

        # Act
        choice = handler.prompt_choice("Select option:", choices)

        # Assert
        assert choice == 1
        assert len(handler.interactions) == 1
        assert handler.interactions[0]["type"] == "choice"
        assert handler.interactions[0]["response"] == 1

    def test_mock_confirm_response(self):
        """Test pre-programmed confirm responses."""
        # Arrange
        handler = MockInteractionHandler(confirm_responses=[True, False])

        # Act
        response1 = handler.confirm("Confirm action 1?")
        response2 = handler.confirm("Confirm action 2?")

        # Assert
        assert response1 is True
        assert response2 is False
        assert len(handler.interactions) == 2
        confirms = handler.get_interactions_by_type("confirm")
        assert len(confirms) == 2

    def test_mock_warnings_and_info(self):
        """Test tracking warnings and info messages."""
        # Arrange
        handler = MockInteractionHandler()

        # Act
        handler.show_warning("Warning message")
        handler.show_info("Info message")
        handler.show_warning("Another warning")

        # Assert
        assert len(handler.interactions) == 3
        warnings = handler.get_interactions_by_type("warning")
        infos = handler.get_interactions_by_type("info")
        assert len(warnings) == 2
        assert len(infos) == 1

    def test_mock_exhausted_responses(self):
        """Test error when responses exhausted."""
        # Arrange
        handler = MockInteractionHandler(choice_responses=[0])
        choices = [("a", "Option A", 0)]

        # Act - First call succeeds
        handler.prompt_choice("Q1", choices)

        # Act & Assert - Second call fails
        with pytest.raises(IndexError, match="No more choice responses"):
            handler.prompt_choice("Q2", choices)

    def test_mock_reset(self):
        """Test resetting handler state."""
        # Arrange
        handler = MockInteractionHandler(
            choice_responses=[0, 1],
            confirm_responses=[True],
        )
        choices = [("a", "A", 0), ("b", "B", 0)]

        # Act
        handler.prompt_choice("Q1", choices)
        handler.confirm("C1?")
        assert len(handler.interactions) == 2

        handler.reset()

        # Assert
        assert len(handler.interactions) == 0
        # Can reuse responses
        handler.prompt_choice("Q2", choices)
        assert len(handler.interactions) == 1


class TestBastionPrerequisiteChecking:
    """Test prerequisite checking before Bastion creation."""

    @patch("subprocess.run")
    def test_check_prerequisites_all_exist(self, mock_run):
        """Test when all prerequisites already exist."""
        # Arrange
        mock_run.side_effect = [
            # Check VNet exists
            Mock(returncode=0, stdout='{"name": "my-vnet"}'),
            # Check subnet exists
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            # Check public IP exists
            Mock(returncode=0, stdout='{"name": "my-pip"}'),
        ]

        # Act
        status = BastionProvisioner.check_prerequisites(
            resource_group="test-rg",
            location="eastus",
            vnet_name="my-vnet",
            public_ip_name="my-pip",
        )

        # Assert
        assert status.vnet_exists is True
        assert status.subnet_exists is True
        assert status.public_ip_exists is True
        assert status.quota_available is True
        assert status.is_ready() is True
        assert len(status.missing_resources()) == 0

    @patch("subprocess.run")
    def test_check_prerequisites_missing_all(self, mock_run):
        """Test when all prerequisites are missing."""
        # Arrange
        mock_run.side_effect = [
            # Check VNet - not found
            Mock(returncode=1, stderr="ResourceNotFound"),
            # List VNets - empty
            Mock(returncode=0, stdout="[]"),
        ]

        # Act
        status = BastionProvisioner.check_prerequisites(
            resource_group="test-rg",
            location="eastus",
            vnet_name="my-vnet",
        )

        # Assert
        assert status.vnet_exists is False
        assert status.subnet_exists is False
        assert status.is_ready() is False
        missing = status.missing_resources()
        assert "vnet" in missing
        assert "subnet" in missing

    @patch("subprocess.run")
    def test_check_prerequisites_vnet_exists_no_bastion_subnet(self, mock_run):
        """Test when VNet exists but no Bastion subnet."""
        # Arrange
        mock_run.side_effect = [
            # Check VNet exists
            Mock(returncode=0, stdout='{"name": "my-vnet"}'),
            # Check subnet - not found
            Mock(returncode=1, stderr="ResourceNotFound"),
        ]

        # Act
        status = BastionProvisioner.check_prerequisites(
            resource_group="test-rg",
            location="eastus",
            vnet_name="my-vnet",
        )

        # Assert
        assert status.vnet_exists is True
        assert status.vnet_name == "my-vnet"
        assert status.subnet_exists is False
        assert status.is_ready() is False
        missing = status.missing_resources()
        assert "subnet" in missing
        assert "vnet" not in missing


class TestResourceOrchestratorBastionDecisions:
    """Test ResourceOrchestrator Bastion decision workflows."""

    def test_ensure_bastion_already_exists(self):
        """Test when Bastion already exists - use existing."""
        # Arrange
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="my-vnet",
            vnet_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/my-vnet",
        )

        # Mock existing Bastion detection
        with patch.object(
            orchestrator,
            "_check_existing_bastion",
            return_value={
                "name": "existing-bastion",
                "id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/bastionHosts/existing-bastion",
                "sku": "Standard",
            },
        ):
            # Act
            decision = orchestrator.ensure_bastion(options)

        # Assert
        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.resource_type == ResourceType.BASTION
        assert decision.resource_name == "existing-bastion"
        assert "sku" in decision.metadata
        # Should have shown info message
        infos = handler.get_interactions_by_type("info")
        assert len(infos) == 1
        assert "existing-bastion" in infos[0]["message"]

    def test_ensure_bastion_user_chooses_create(self):
        """Test user chooses to create Bastion."""
        # Arrange
        # User chooses option 0 (create Bastion)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="my-vnet",
            vnet_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/my-vnet",
            sku="Standard",
        )

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act
            decision = orchestrator.ensure_bastion(options)

        # Assert
        assert decision.action == DecisionAction.CREATE
        assert decision.resource_type == ResourceType.BASTION
        assert decision.resource_name == "my-vnet-bastion"
        assert decision.cost_estimate is not None
        assert decision.cost_estimate > 0
        assert decision.metadata["sku"] == "Standard"
        assert decision.metadata["region"] == "eastus"

        # Verify user was prompted
        assert len(handler.interactions) >= 3  # info + warning + choice

    def test_ensure_bastion_user_chooses_public_ip(self):
        """Test user chooses to skip Bastion (use public IP)."""
        # Arrange
        # User chooses option 1 (public IP)
        handler = MockInteractionHandler(choice_responses=[1])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="my-vnet",
            allow_public_ip_fallback=True,
        )

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act
            decision = orchestrator.ensure_bastion(options)

        # Assert
        assert decision.action == DecisionAction.SKIP
        assert decision.resource_type == ResourceType.BASTION
        assert decision.metadata["fallback"] == "public-ip"

        # Should have shown warning about public IP
        warnings = handler.get_interactions_by_type("warning")
        assert any("public IP" in w["message"] for w in warnings)

    def test_ensure_bastion_user_cancels(self):
        """Test user cancels Bastion creation."""
        # Arrange
        # User chooses option 2 (cancel)
        handler = MockInteractionHandler(choice_responses=[2])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="my-vnet",
            allow_public_ip_fallback=True,
        )

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act
            decision = orchestrator.ensure_bastion(options)

        # Assert
        assert decision.action == DecisionAction.CANCEL
        assert decision.resource_type == ResourceType.BASTION

    def test_ensure_bastion_no_vnet_auto_generates(self):
        """Test auto-generation of VNet name when not provided."""
        # Arrange
        handler = MockInteractionHandler(choice_responses=[0])  # User approves creation
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="",  # Missing VNet - should auto-generate
        )

        # Act
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            decision = orchestrator.ensure_bastion(options)

        # Assert - VNet name should be auto-generated
        assert decision.metadata["vnet_name"] == "azlin-vnet-eastus"


class TestBastionProvisioningWorkflow:
    """Test complete Bastion provisioning workflow."""

    @patch("subprocess.run")
    def test_provision_bastion_all_prerequisites_exist(self, mock_run):
        """Test provisioning when all prerequisites exist."""
        # Arrange
        mock_run.side_effect = [
            # Check VNet exists
            Mock(returncode=0, stdout='{"name": "my-vnet"}'),
            # Check subnet exists
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            # Check public IP exists
            Mock(returncode=0, stdout='{"name": "my-pip"}'),
            # Create Bastion
            Mock(
                returncode=0,
                stdout='{"name": "my-bastion", "provisioningState": "Creating"}',
            ),
        ]

        # Mock BastionDetector for status polling
        with patch(
            "azlin.modules.bastion_provisioner.BastionDetector.get_bastion",
            return_value={"provisioningState": "Succeeded"},
        ):
            # Act
            result = BastionProvisioner.provision_bastion(
                bastion_name="my-bastion",
                resource_group="test-rg",
                location="eastus",
                vnet_name="my-vnet",
                public_ip_name="my-pip",
                wait_for_completion=True,
                timeout=10,  # Short timeout for testing
            )

        # Assert
        assert result.success is True
        assert result.bastion_name == "my-bastion"
        assert result.provisioning_state == "Succeeded"
        assert "bastion:my-bastion" in result.resources_created
        assert result.duration_seconds is not None

    @patch("subprocess.run")
    def test_provision_bastion_creates_missing_resources(self, mock_run):
        """Test provisioning creates missing VNet, subnet, and public IP."""
        # Arrange
        mock_run.side_effect = [
            # Check VNet - not found
            Mock(returncode=1, stderr="ResourceNotFound"),
            # List VNets - empty
            Mock(returncode=0, stdout="[]"),
            # Create VNet
            Mock(returncode=0, stdout='{"name": "my-bastion-vnet"}'),
            # Create Bastion subnet
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            # Create public IP
            Mock(returncode=0, stdout='{"name": "my-bastion-pip"}'),
            # Create Bastion
            Mock(
                returncode=0,
                stdout='{"name": "my-bastion", "provisioningState": "Creating"}',
            ),
        ]

        # Mock BastionDetector for status polling
        with patch(
            "azlin.modules.bastion_provisioner.BastionDetector.get_bastion",
            return_value={"provisioningState": "Succeeded"},
        ):
            # Act
            result = BastionProvisioner.provision_bastion(
                bastion_name="my-bastion",
                resource_group="test-rg",
                location="eastus",
                wait_for_completion=True,
                timeout=10,
            )

        # Assert
        assert result.success is True
        # Should have created all resources
        assert "vnet:my-bastion-vnet" in result.resources_created
        assert "subnet:AzureBastionSubnet" in result.resources_created
        assert "public-ip:my-bastion-pip" in result.resources_created
        assert "bastion:my-bastion" in result.resources_created

    @patch("subprocess.run")
    def test_provision_bastion_failure_returns_result(self, mock_run):
        """Test provisioning failure returns result with error details."""
        # Arrange
        mock_run.side_effect = [
            # Check VNet exists
            Mock(returncode=0, stdout='{"name": "my-vnet"}'),
            # Check subnet exists
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            # Check public IP - not found
            Mock(returncode=1, stderr="ResourceNotFound"),
            # Create public IP
            Mock(returncode=0, stdout='{"name": "my-pip"}'),
            # Create Bastion - FAILS
            Mock(returncode=1, stderr="QuotaExceeded"),
        ]

        # Act
        result = BastionProvisioner.provision_bastion(
            bastion_name="my-bastion",
            resource_group="test-rg",
            location="eastus",
            vnet_name="my-vnet",
            wait_for_completion=False,
        )

        # Assert
        assert result.success is False
        assert result.error_message is not None
        assert "quota" in result.error_message.lower()
        # Should have created public IP before failure
        assert "public-ip:my-pip" in result.resources_created
        # Bastion should not be in created list
        assert not any("bastion:" in r for r in result.resources_created)

    @patch("subprocess.run")
    def test_provision_bastion_timeout_during_wait(self, mock_run):
        """Test provisioning timeout while waiting for completion."""
        # Arrange
        mock_run.side_effect = [
            # All prerequisite checks pass
            Mock(returncode=0, stdout='{"name": "my-vnet"}'),
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            Mock(returncode=0, stdout='{"name": "my-pip"}'),
            # Create Bastion succeeds
            Mock(
                returncode=0,
                stdout='{"name": "my-bastion", "provisioningState": "Creating"}',
            ),
        ]

        # Mock BastionDetector that never reaches Succeeded state
        with patch(
            "azlin.modules.bastion_provisioner.BastionDetector.get_bastion",
            return_value={"provisioningState": "Creating"},
        ):
            # Act & Assert
            with pytest.raises(BastionProvisionerError, match="timed out"):
                BastionProvisioner.provision_bastion(
                    bastion_name="my-bastion",
                    resource_group="test-rg",
                    location="eastus",
                    vnet_name="my-vnet",
                    public_ip_name="my-pip",
                    wait_for_completion=True,
                    timeout=1,  # Very short timeout
                )

    def test_provision_bastion_validates_inputs(self):
        """Test input validation before provisioning."""
        # Test empty bastion name
        with pytest.raises(BastionProvisionerError, match="Bastion name"):
            BastionProvisioner.provision_bastion(
                bastion_name="",
                resource_group="test-rg",
                location="eastus",
            )

        # Test invalid characters
        with pytest.raises(BastionProvisionerError, match="Invalid Bastion name"):
            BastionProvisioner.provision_bastion(
                bastion_name="my;bastion",  # Semicolon not allowed
                resource_group="test-rg",
                location="eastus",
            )


class TestBastionRollbackWorkflow:
    """Test rollback of failed Bastion provisioning."""

    @patch("subprocess.run")
    def test_rollback_bastion_deletes_in_reverse_order(self, mock_run):
        """Test rollback deletes resources in reverse creation order."""
        # Arrange
        mock_run.return_value = Mock(returncode=0, stdout="")

        resources_created = [
            "vnet:my-vnet",
            "subnet:AzureBastionSubnet",
            "public-ip:my-pip",
            "bastion:my-bastion",
        ]

        # Act
        status = BastionProvisioner.rollback_bastion(
            bastion_name="my-bastion",
            resource_group="test-rg",
            resources_created=resources_created,
            delete_bastion=True,
        )

        # Assert
        assert len(status) == 4
        assert status["bastion:my-bastion"] is True
        assert status["public-ip:my-pip"] is True
        assert status["vnet:my-vnet"] is True

        # Verify delete commands were called
        calls = [str(call) for call in mock_run.call_args_list]
        assert any("bastion delete" in call for call in calls)
        assert any("public-ip delete" in call for call in calls)
        assert any("vnet delete" in call for call in calls)

    @patch("subprocess.run")
    def test_rollback_bastion_partial_failure(self, mock_run):
        """Test rollback handles partial deletion failures."""

        # Arrange
        def run_side_effect(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd)
            if "bastion delete" in cmd_str:
                return Mock(returncode=0)  # Success
            if "public-ip delete" in cmd_str:
                return Mock(returncode=1, stderr="IP still in use")  # Failure
            return Mock(returncode=0)

        mock_run.side_effect = run_side_effect

        resources_created = [
            "public-ip:my-pip",
            "bastion:my-bastion",
        ]

        # Act
        status = BastionProvisioner.rollback_bastion(
            bastion_name="my-bastion",
            resource_group="test-rg",
            resources_created=resources_created,
            delete_bastion=True,
        )

        # Assert
        assert status["bastion:my-bastion"] is True
        assert status["public-ip:my-pip"] is False


class TestEndToEndBastionAutoCreation:
    """Integration test for complete auto-creation workflow."""

    @patch("subprocess.run")
    def test_complete_workflow_user_approves_creation(self, mock_run):
        """Test complete workflow: detect -> cost estimate -> prompt -> create."""
        # Arrange
        # User chooses to create Bastion (option 0)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            cost_estimator=None,  # Use default estimates
        )

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="my-vnet",
            vnet_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/my-vnet",
            sku="Standard",
        )

        # Mock Azure CLI responses
        mock_run.side_effect = [
            # Check VNet exists
            Mock(returncode=0, stdout='{"name": "my-vnet"}'),
            # Check subnet exists
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            # Check public IP - not found
            Mock(returncode=1, stderr="ResourceNotFound"),
            # Create public IP
            Mock(returncode=0, stdout='{"name": "my-vnet-bastion-pip"}'),
            # Create Bastion
            Mock(
                returncode=0,
                stdout='{"name": "my-vnet-bastion", "provisioningState": "Creating"}',
            ),
        ]

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act - Step 1: Get user decision
            decision = orchestrator.ensure_bastion(options)

            # Assert decision
            assert decision.action == DecisionAction.CREATE
            assert decision.cost_estimate > 0

            # Act - Step 2: Execute provisioning based on decision
            if decision.action == DecisionAction.CREATE:
                with patch(
                    "azlin.modules.bastion_provisioner.BastionDetector.get_bastion",
                    return_value={"provisioningState": "Succeeded"},
                ):
                    result = BastionProvisioner.provision_bastion(
                        bastion_name=decision.resource_name,
                        resource_group=options.resource_group,
                        location=options.region,
                        vnet_name=options.vnet_name,
                        sku=options.sku,
                        wait_for_completion=True,
                        timeout=10,
                    )

                # Assert provisioning result
                assert result.success is True
                assert result.bastion_name == "my-vnet-bastion"

        # Verify user interactions
        choice_interactions = handler.get_interactions_by_type("choice")
        assert len(choice_interactions) == 1
        assert "Bastion" in choice_interactions[0]["message"]

        # Verify cost was shown in choices
        choices = choice_interactions[0]["choices"]
        bastion_choice = choices[0]
        assert bastion_choice[2] > 0  # Cost should be > 0

    @patch("subprocess.run")
    def test_complete_workflow_user_skips_bastion(self, mock_run):
        """Test complete workflow when user chooses public IP instead."""
        # Arrange
        # User chooses public IP option (option 1)
        handler = MockInteractionHandler(choice_responses=[1])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="my-vnet",
            allow_public_ip_fallback=True,
        )

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act
            decision = orchestrator.ensure_bastion(options)

        # Assert
        assert decision.action == DecisionAction.SKIP
        assert decision.metadata["fallback"] == "public-ip"

        # No Azure CLI calls should have been made
        assert mock_run.call_count == 0

        # Verify warning was shown
        warnings = handler.get_interactions_by_type("warning")
        assert any("public IP" in w["message"] for w in warnings)
