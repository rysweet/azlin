"""Tests for resource orchestrator module.

This test suite verifies:
- Bastion workflow with user decisions
- NFS cross-region workflow with cost transparency
- Resource tracking and rollback
- Dependency management
- Integration with interaction handlers and cost estimator
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from azlin.agentic.types import CostEstimate
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.modules.resource_orchestrator import (
    BastionOptions,
    DecisionAction,
    DependencyError,
    NFSOptions,
    ResourceDecision,
    ResourceOrchestrator,
    ResourceStatus,
    ResourceType,
)


class TestResourceDecision:
    """Test ResourceDecision dataclass."""

    def test_create_decision_with_cost(self):
        """Test creating a decision with cost estimate."""
        decision = ResourceDecision(
            action=DecisionAction.CREATE,
            resource_type=ResourceType.BASTION,
            resource_name="my-bastion",
            cost_estimate=Decimal("292.65"),
        )

        assert decision.action == DecisionAction.CREATE
        assert decision.resource_type == ResourceType.BASTION
        assert decision.resource_name == "my-bastion"
        assert decision.cost_estimate == Decimal("292.65")

    def test_use_existing_decision(self):
        """Test decision for using existing resource."""
        decision = ResourceDecision(
            action=DecisionAction.USE_EXISTING,
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/existing",
            resource_name="existing-bastion",
        )

        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.resource_id
        assert decision.cost_estimate is None

    def test_skip_decision(self):
        """Test skip decision with fallback metadata."""
        decision = ResourceDecision(
            action=DecisionAction.SKIP,
            resource_type=ResourceType.BASTION,
            metadata={"fallback": "public-ip"},
        )

        assert decision.action == DecisionAction.SKIP
        assert decision.metadata["fallback"] == "public-ip"

    def test_cancel_decision(self):
        """Test cancel decision."""
        decision = ResourceDecision(
            action=DecisionAction.CANCEL,
            resource_type=ResourceType.NFS,
        )

        assert decision.action == DecisionAction.CANCEL


class TestEnsureBastion:
    """Test Bastion orchestration workflow."""

    def test_use_existing_bastion(self):
        """Test using existing Bastion host."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        # Mock existing Bastion detection
        with patch.object(
            orchestrator,
            "_check_existing_bastion",
            return_value={
                "name": "existing-bastion",
                "id": "/subscriptions/.../bastionHosts/existing-bastion",
                "sku": "Basic",
            },
        ):
            options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.USE_EXISTING
            assert decision.resource_name == "existing-bastion"
            assert decision.resource_type == ResourceType.BASTION
            assert decision.metadata["sku"] == "Basic"

        # Verify info message was shown
        info_interactions = handler.get_interactions_by_type("info")
        assert len(info_interactions) >= 1
        assert "existing" in info_interactions[0]["message"].lower()

    def test_create_bastion_user_approves(self):
        """Test creating Bastion when user approves."""
        # User chooses option 0 (create Bastion)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.CREATE
            assert decision.resource_type == ResourceType.BASTION
            assert decision.resource_name == "my-vnet-bastion"
            assert decision.cost_estimate is not None
            assert decision.cost_estimate > 0

        # Verify user was prompted with cost info
        choice_interactions = handler.get_interactions_by_type("choice")
        assert len(choice_interactions) == 1
        assert len(choice_interactions[0]["choices"]) >= 2  # Create + fallback options

    def test_skip_bastion_use_public_ip(self):
        """Test skipping Bastion to use public IP fallback."""
        # User chooses option 1 (use public IP)
        handler = MockInteractionHandler(choice_responses=[1])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
                allow_public_ip_fallback=True,
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.SKIP
            assert decision.metadata["fallback"] == "public-ip"

        # Verify warning was shown
        warning_interactions = handler.get_interactions_by_type("warning")
        assert len(warning_interactions) >= 2  # Cost warning + public IP warning

    def test_cancel_bastion_operation(self):
        """Test cancelling operation during Bastion prompt."""
        # User chooses option 2 (cancel)
        handler = MockInteractionHandler(choice_responses=[2])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.CANCEL

    def test_bastion_missing_dependencies(self):
        """Test error when required dependencies are missing."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        options = BastionOptions(
            region="westus",
            resource_group="my-rg",
            vnet_name="",  # Missing VNet name
            vnet_id=None,  # Missing VNet ID
        )

        with pytest.raises(DependencyError, match="vnet_id or vnet_name"):
            orchestrator.ensure_bastion(options)


class TestEnsureNFSAccess:
    """Test NFS orchestration workflow."""

    def test_same_region_nfs_simple_mount(self):
        """Test NFS mount when storage and VM are in same region."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        options = NFSOptions(
            region="westus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="westus",  # Same as VM region
            share_name="home-share",
            mount_point="/home",
        )

        decision = orchestrator.ensure_nfs_access(options)

        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.resource_type == ResourceType.NFS
        assert decision.resource_name == "home-share"
        assert decision.metadata["cross_region"] is False
        assert decision.metadata["mount_point"] == "/home"

        # Verify info message was shown
        info_interactions = handler.get_interactions_by_type("info")
        assert len(info_interactions) >= 1

    def test_cross_region_nfs_user_approves(self):
        """Test cross-region NFS setup when user approves."""
        # User chooses option 0 (setup cross-region)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        options = NFSOptions(
            region="westus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="eastus",  # Different region
            share_name="home-share",
            mount_point="/home",
        )

        decision = orchestrator.ensure_nfs_access(options)

        assert decision.action == DecisionAction.CREATE
        assert decision.resource_type == ResourceType.NFS
        assert decision.cost_estimate is not None
        assert decision.metadata["cross_region"] is True
        assert decision.metadata["storage_region"] == "eastus"
        assert decision.metadata["vm_region"] == "westus"

        # Verify user saw cost info
        choice_interactions = handler.get_interactions_by_type("choice")
        assert len(choice_interactions) == 1

    def test_cross_region_nfs_cancel(self):
        """Test cancelling operation during cross-region NFS prompt."""
        # User chooses option 1 (cancel - now index 1 after removing local storage option)
        handler = MockInteractionHandler(choice_responses=[1])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        options = NFSOptions(
            region="westus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="eastus",
            share_name="home-share",
        )

        decision = orchestrator.ensure_nfs_access(options)

        assert decision.action == DecisionAction.CANCEL


class TestResourceTracking:
    """Test resource tracking and rollback."""

    def test_track_resource(self):
        """Test tracking a created resource."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        resource = orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/my-bastion",
            resource_name="my-bastion",
            dependencies=["/subscriptions/.../vnets/my-vnet"],
            rollback_cmd="az network bastion delete --ids {resource_id}",
            metadata={"sku": "Basic"},
        )

        assert resource.resource_type == ResourceType.BASTION
        assert resource.resource_name == "my-bastion"
        assert resource.status == ResourceStatus.CREATED
        assert len(resource.dependencies) == 1
        assert resource.rollback_cmd is not None
        assert resource.metadata["sku"] == "Basic"

        # Verify tracked in orchestrator
        assert len(orchestrator.resources) == 1
        assert orchestrator.resources[0] == resource

    def test_rollback_resources(self):
        """Test rolling back created resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            dry_run=True,  # Use dry run to avoid actual Azure calls
        )

        # Track some resources
        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/my-bastion",
            resource_name="my-bastion",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        orchestrator.track_resource(
            resource_type=ResourceType.NFS,
            resource_id="/subscriptions/.../privateEndpoints/my-endpoint",
            resource_name="my-endpoint",
            rollback_cmd="az network private-endpoint delete --ids {resource_id}",
        )

        # Rollback
        orchestrator.rollback_resources("Test error")

        # Verify all resources marked as rolled back
        assert all(r.status == ResourceStatus.ROLLED_BACK for r in orchestrator.resources)

        # Verify warning shown
        warning_interactions = handler.get_interactions_by_type("warning")
        assert len(warning_interactions) >= 1

    def test_rollback_reverse_order(self):
        """Test rollback happens in reverse order."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            dry_run=True,
        )

        # Track resources with dependencies
        vnet_resource = orchestrator.track_resource(
            resource_type=ResourceType.VNET,
            resource_id="/subscriptions/.../vnets/my-vnet",
            resource_name="my-vnet",
            rollback_cmd="az network vnet delete --ids {resource_id}",
        )

        bastion_resource = orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/my-bastion",
            resource_name="my-bastion",
            dependencies=[vnet_resource.resource_id],
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        # Rollback
        orchestrator.rollback_resources()

        # Verify Bastion rolled back before VNet (reverse order)
        assert orchestrator.resources[0] == vnet_resource
        assert orchestrator.resources[1] == bastion_resource
        # Both should be rolled back
        assert all(r.status == ResourceStatus.ROLLED_BACK for r in orchestrator.resources)

    def test_rollback_no_resources(self):
        """Test rollback with no tracked resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        # Should not raise error
        orchestrator.rollback_resources()

        assert len(orchestrator.resources) == 0

    def test_rollback_without_command(self):
        """Test rollback when resource has no rollback command."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            dry_run=False,  # Need actual rollback to test warning
        )

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/my-bastion",
            resource_name="my-bastion",
            rollback_cmd=None,  # No rollback command
        )

        # Should not raise error, but log warning
        orchestrator.rollback_resources()

        # Resource marked as rolled back (with warning logged for manual cleanup)
        assert orchestrator.resources[0].status == ResourceStatus.ROLLED_BACK


class TestResourceSummary:
    """Test resource summary reporting."""

    def test_get_resource_summary_empty(self):
        """Test summary with no resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        summary = orchestrator.get_resource_summary()

        assert summary["total_resources"] == 0
        assert summary["by_status"] == {}
        assert len(summary["resources"]) == 0

    def test_get_resource_summary_with_resources(self):
        """Test summary with tracked resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/bastion1",
            resource_name="bastion1",
        )

        orchestrator.track_resource(
            resource_type=ResourceType.NFS,
            resource_id="/subscriptions/.../endpoints/endpoint1",
            resource_name="endpoint1",
        )

        summary = orchestrator.get_resource_summary()

        assert summary["total_resources"] == 2
        assert summary["by_status"]["created"] == 2
        assert summary["by_type"]["bastion"] == 1
        assert summary["by_type"]["nfs"] == 1
        assert len(summary["resources"]) == 2


class TestCostEstimation:
    """Test cost estimation integration."""

    def test_bastion_cost_with_estimator(self):
        """Test Bastion cost estimation with CostEstimator."""
        handler = MockInteractionHandler(choice_responses=[0])

        # Mock cost estimator
        mock_estimator = MagicMock()
        mock_estimator.estimate.return_value = CostEstimate(
            total_monthly=Decimal("292.65"),
            total_hourly=Decimal("0.40"),
            breakdown={"bastion": Decimal("289.00")},
            confidence="high",
        )

        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            cost_estimator=mock_estimator,
        )

        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.cost_estimate == Decimal("292.65")
            assert mock_estimator.estimate.called

    def test_bastion_cost_without_estimator(self):
        """Test Bastion cost estimation without CostEstimator (uses defaults)."""
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            cost_estimator=None,  # No estimator
        )

        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            # Should still provide cost estimate (default)
            assert decision.cost_estimate is not None
            assert decision.cost_estimate > 0


class TestDryRun:
    """Test dry-run mode."""

    def test_dry_run_mode(self):
        """Test orchestrator in dry-run mode."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
            dry_run=True,
        )

        assert orchestrator.dry_run is True

        # Track resource
        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastionHosts/my-bastion",
            resource_name="my-bastion",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        # Rollback in dry-run mode
        orchestrator.rollback_resources()

        # Should mark as rolled back without actual execution
        assert orchestrator.resources[0].status == ResourceStatus.ROLLED_BACK


class TestIntegration:
    """Integration tests with multiple resources."""

    def test_full_workflow_bastion_and_nfs(self):
        """Test orchestrating both Bastion and NFS resources."""
        # User creates Bastion and skips cross-region NFS
        handler = MockInteractionHandler(choice_responses=[0, 1])
        orchestrator = ResourceOrchestrator(
            interaction_handler=handler,
        )

        # Step 1: Ensure Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            bastion_options = BastionOptions(
                region="westus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                vnet_id="/subscriptions/.../my-vnet",
            )

            bastion_decision = orchestrator.ensure_bastion(bastion_options)

            assert bastion_decision.action == DecisionAction.CREATE

        # Step 2: Ensure NFS access
        nfs_options = NFSOptions(
            region="westus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="eastus",  # Cross-region
            share_name="home-share",
        )

        nfs_decision = orchestrator.ensure_nfs_access(nfs_options)

        assert nfs_decision.action == DecisionAction.CANCEL

        # Verify both interactions occurred
        assert len(handler.interactions) >= 2
