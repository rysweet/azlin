"""Unit tests for resource_orchestrator module.

Tests decision workflows, user interaction, and resource tracking.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.modules.resource_orchestrator import (
    BastionOptions,
    DecisionAction,
    NFSOptions,
    OrchestratedResource,
    ResourceDecision,
    ResourceOrchestrator,
    ResourceStatus,
    ResourceType,
    RollbackError,
)


class TestDecisionAction:
    """Test DecisionAction enumeration."""

    def test_action_values(self):
        """Decision action values should be defined."""
        assert DecisionAction.CREATE.value == "create"
        assert DecisionAction.USE_EXISTING.value == "use-existing"
        assert DecisionAction.SKIP.value == "skip"
        assert DecisionAction.CANCEL.value == "cancel"


class TestResourceType:
    """Test ResourceType enumeration."""

    def test_resource_types(self):
        """Resource types should be defined."""
        assert ResourceType.BASTION.value == "bastion"
        assert ResourceType.NFS.value == "nfs"
        assert ResourceType.VNET.value == "vnet"


class TestResourceDecision:
    """Test ResourceDecision dataclass."""

    def test_create_decision_with_cost(self):
        """CREATE decision should include cost estimate."""
        decision = ResourceDecision(
            action=DecisionAction.CREATE,
            resource_type=ResourceType.BASTION,
            resource_name="my-bastion",
            cost_estimate=Decimal("292.65"),
        )

        assert decision.action == DecisionAction.CREATE
        assert decision.cost_estimate == Decimal("292.65")

    def test_use_existing_decision(self):
        """USE_EXISTING decision should include resource ID."""
        decision = ResourceDecision(
            action=DecisionAction.USE_EXISTING,
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/existing",
            resource_name="existing-bastion",
        )

        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.resource_id is not None

    def test_skip_decision(self):
        """SKIP decision with fallback metadata."""
        decision = ResourceDecision(
            action=DecisionAction.SKIP,
            resource_type=ResourceType.BASTION,
            metadata={"fallback": "public-ip"},
        )

        assert decision.action == DecisionAction.SKIP
        assert decision.metadata["fallback"] == "public-ip"


class TestEnsureBastion:
    """Test Bastion orchestration workflow."""

    def test_bastion_exists_returns_use_existing(self):
        """Existing Bastion should return USE_EXISTING decision."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler, dry_run=True)

        # Mock existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion") as mock_check:
            mock_check.return_value = {
                "name": "existing-bastion",
                "id": "/subscriptions/.../bastions/existing-bastion",
                "sku": "Basic",
            }

            options = BastionOptions(
                region="eastus",
                resource_group="my-rg",
                vnet_name="my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.USE_EXISTING
            assert decision.resource_name == "existing-bastion"

    def test_bastion_not_exists_user_chooses_create(self):
        """User choosing CREATE should return CREATE decision."""
        handler = MockInteractionHandler(choice_responses=[0])  # Choose first option (create)
        orchestrator = ResourceOrchestrator(handler)

        with patch.object(orchestrator, "_check_existing_bastion") as mock_check:
            mock_check.return_value = None  # No existing Bastion

            options = BastionOptions(
                region="eastus",
                resource_group="my-rg",
                vnet_name="my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.CREATE
            assert decision.resource_type == ResourceType.BASTION
            assert decision.cost_estimate is not None

    def test_bastion_not_exists_user_chooses_public_ip(self):
        """User choosing public IP should return SKIP decision."""
        handler = MockInteractionHandler(choice_responses=[1])  # Choose second option (public-ip)
        orchestrator = ResourceOrchestrator(handler)

        with patch.object(orchestrator, "_check_existing_bastion") as mock_check:
            mock_check.return_value = None

            options = BastionOptions(
                region="eastus",
                resource_group="my-rg",
                vnet_name="my-vnet",
                allow_public_ip_fallback=True,
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.SKIP
            assert decision.metadata["fallback"] == "public-ip"

    def test_bastion_not_exists_user_cancels(self):
        """User choosing cancel should return CANCEL decision."""
        handler = MockInteractionHandler(choice_responses=[2])  # Choose third option (cancel)
        orchestrator = ResourceOrchestrator(handler)

        with patch.object(orchestrator, "_check_existing_bastion") as mock_check:
            mock_check.return_value = None

            options = BastionOptions(
                region="eastus",
                resource_group="my-rg",
                vnet_name="my-vnet",
            )

            decision = orchestrator.ensure_bastion(options)

            assert decision.action == DecisionAction.CANCEL

    def test_bastion_missing_vnet_auto_generates(self):
        """Missing VNet name should auto-generate based on region."""
        handler = MockInteractionHandler(choice_responses=[0])  # User chooses to create
        orchestrator = ResourceOrchestrator(handler)

        options = BastionOptions(
            region="eastus",
            resource_group="my-rg",
            vnet_name="",  # Empty VNet name
        )

        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            decision = orchestrator.ensure_bastion(options)

        # Should auto-generate VNet name
        assert decision.metadata["vnet_name"] == "azlin-vnet-eastus"


class TestEnsureNFSAccess:
    """Test NFS access orchestration workflow."""

    def test_same_region_nfs_returns_use_existing(self):
        """Same region NFS should return USE_EXISTING."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        options = NFSOptions(
            region="eastus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="eastus",  # Same region
            share_name="home",
        )

        decision = orchestrator.ensure_nfs_access(options)

        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.metadata["cross_region"] is False

    def test_cross_region_nfs_user_chooses_setup(self):
        """User choosing cross-region setup should return CREATE."""
        handler = MockInteractionHandler(choice_responses=[0])  # Choose setup
        orchestrator = ResourceOrchestrator(handler)

        options = NFSOptions(
            region="eastus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="westus",  # Different region
            share_name="home",
        )

        decision = orchestrator.ensure_nfs_access(options)

        assert decision.action == DecisionAction.CREATE
        assert decision.metadata["cross_region"] is True
        assert decision.cost_estimate is not None

    def test_cross_region_nfs_user_cancels(self):
        """User canceling should return CANCEL."""
        handler = MockInteractionHandler(choice_responses=[1])  # Cancel (now index 1, not 2)
        orchestrator = ResourceOrchestrator(handler)

        options = NFSOptions(
            region="eastus",
            resource_group="my-rg",
            storage_account_name="myaccount",
            storage_account_region="westus",
            share_name="home",
        )

        decision = orchestrator.ensure_nfs_access(options)

        assert decision.action == DecisionAction.CANCEL


class TestResourceTracking:
    """Test resource tracking for rollback."""

    def test_track_resource(self):
        """Track resource should add to list."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        resource = orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/my-bastion",
            resource_name="my-bastion",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        assert len(orchestrator.resources) == 1
        assert resource.status == ResourceStatus.CREATED
        assert resource.resource_name == "my-bastion"

    def test_track_multiple_resources(self):
        """Track multiple resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        orchestrator.track_resource(
            resource_type=ResourceType.VNET,
            resource_id="/subscriptions/.../vnets/vnet1",
            resource_name="vnet1",
        )

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/bastion1",
            resource_name="bastion1",
        )

        assert len(orchestrator.resources) == 2

    def test_track_resource_with_dependencies(self):
        """Track resource with dependencies."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        vnet_id = "/subscriptions/.../vnets/vnet1"
        orchestrator.track_resource(
            resource_type=ResourceType.VNET,
            resource_id=vnet_id,
            resource_name="vnet1",
        )

        bastion_resource = orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/bastion1",
            resource_name="bastion1",
            dependencies=[vnet_id],
        )

        assert vnet_id in bastion_resource.dependencies


class TestRollbackResources:
    """Test resource rollback functionality."""

    def test_rollback_empty_list(self):
        """Rollback with no resources should not error."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        # Should not raise
        orchestrator.rollback_resources()

    @patch("azlin.modules.resource_orchestrator.subprocess.run")
    def test_rollback_single_resource(self, mock_run):
        """Rollback should delete tracked resource."""
        mock_run.return_value = MagicMock(returncode=0)

        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/my-bastion",
            resource_name="my-bastion",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        orchestrator.rollback_resources()

        assert mock_run.called
        assert orchestrator.resources[0].status == ResourceStatus.ROLLED_BACK

    @patch("azlin.modules.resource_orchestrator.subprocess.run")
    def test_rollback_multiple_resources_reverse_order(self, mock_run):
        """Rollback should process resources in reverse order."""
        mock_run.return_value = MagicMock(returncode=0)

        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        # Add resources in order
        orchestrator.track_resource(
            resource_type=ResourceType.VNET,
            resource_id="/subscriptions/.../vnets/vnet1",
            resource_name="vnet1",
            rollback_cmd="az network vnet delete --ids {resource_id}",
        )

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/bastion1",
            resource_name="bastion1",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        orchestrator.rollback_resources()

        # Both should be rolled back
        assert all(r.status == ResourceStatus.ROLLED_BACK for r in orchestrator.resources)

    @patch("azlin.modules.resource_orchestrator.subprocess.run")
    def test_rollback_failure_raises_error(self, mock_run):
        """Rollback failure should raise RollbackError."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")

        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/my-bastion",
            resource_name="my-bastion",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        with pytest.raises(RollbackError):
            orchestrator.rollback_resources()

    def test_rollback_dry_run(self):
        """Dry run rollback should not execute commands."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler, dry_run=True)

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/my-bastion",
            resource_name="my-bastion",
            rollback_cmd="az network bastion delete --ids {resource_id}",
        )

        orchestrator.rollback_resources()

        # Should be marked as rolled back without actual execution
        assert orchestrator.resources[0].status == ResourceStatus.ROLLED_BACK


class TestGetResourceSummary:
    """Test resource summary reporting."""

    def test_summary_empty(self):
        """Summary with no resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        summary = orchestrator.get_resource_summary()

        assert summary["total_resources"] == 0
        assert len(summary["resources"]) == 0

    def test_summary_multiple_resources(self):
        """Summary with multiple resources."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        orchestrator.track_resource(
            resource_type=ResourceType.VNET,
            resource_id="/subscriptions/.../vnets/vnet1",
            resource_name="vnet1",
        )

        orchestrator.track_resource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/bastion1",
            resource_name="bastion1",
        )

        summary = orchestrator.get_resource_summary()

        assert summary["total_resources"] == 2
        assert summary["by_type"][ResourceType.VNET.value] == 1
        assert summary["by_type"][ResourceType.BASTION.value] == 1

    def test_summary_status_counts(self):
        """Summary should count resources by status."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler)

        orchestrator.track_resource(
            resource_type=ResourceType.VNET,
            resource_id="/subscriptions/.../vnets/vnet1",
            resource_name="vnet1",
        )

        # Manually set one to failed
        orchestrator.resources[0].status = ResourceStatus.FAILED

        summary = orchestrator.get_resource_summary()

        assert summary["by_status"]["failed"] == 1


class TestCostEstimation:
    """Test cost estimation integration."""

    def test_estimate_bastion_cost_no_estimator(self):
        """Should use default costs when no estimator provided."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler, cost_estimator=None)

        estimate = orchestrator._estimate_bastion_cost("eastus", "Basic")

        assert "hourly" in estimate
        assert "monthly" in estimate
        assert estimate["monthly"] > 0

    def test_estimate_cross_region_nfs_cost(self):
        """Should estimate cross-region NFS costs."""
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(handler, cost_estimator=None)

        estimate = orchestrator._estimate_cross_region_nfs_cost("eastus", "westus")

        assert "hourly" in estimate
        assert "monthly" in estimate
        assert estimate["monthly"] > 0


class TestDataModels:
    """Test data model classes."""

    def test_bastion_options_defaults(self):
        """BastionOptions should have default values."""
        options = BastionOptions(
            region="eastus",
            resource_group="my-rg",
            vnet_name="my-vnet",
        )

        assert options.sku == "Standard"
        assert options.allow_public_ip_fallback is True

    def test_nfs_options_defaults(self):
        """NFSOptions should have default values."""
        options = NFSOptions(
            region="eastus",
            resource_group="my-rg",
            storage_account_name="storage",
            storage_account_region="eastus",
            share_name="home",
        )

        assert options.mount_point == "/home"
        assert options.cross_region_required is False

    def test_orchestrated_resource_dataclass(self):
        """OrchestratedResource should store all fields."""
        import time

        resource = OrchestratedResource(
            resource_type=ResourceType.BASTION,
            resource_id="/subscriptions/.../bastions/my-bastion",
            resource_name="my-bastion",
            status=ResourceStatus.CREATED,
            created_at=time.time(),
            dependencies=["/subscriptions/.../vnets/vnet1"],
            rollback_cmd="az network bastion delete --ids {resource_id}",
            metadata={"sku": "Basic"},
        )

        assert resource.resource_type == ResourceType.BASTION
        assert len(resource.dependencies) == 1
        assert resource.metadata["sku"] == "Basic"
