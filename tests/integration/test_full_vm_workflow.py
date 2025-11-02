"""Integration tests for complete VM lifecycle with auto-creation.

Tests end-to-end workflows that integrate all auto-creation features:
- VM creation with Bastion auto-creation
- VM creation with cross-region NFS setup
- VM deletion with orphaned resource cleanup
- Complete lifecycle: create -> use -> delete -> cleanup

These tests verify the full integration of all orchestration modules.
"""

import json
import subprocess
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from azlin.modules.bastion_provisioner import BastionProvisioner
from azlin.modules.cleanup_orchestrator import CleanupOrchestrator
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.modules.nfs_provisioner import NFSProvisioner
from azlin.modules.resource_orchestrator import (
    BastionOptions,
    DecisionAction,
    NFSOptions,
    ResourceOrchestrator,
)
from azlin.vm_manager import VMInfo


class TestVMCreationWithBastionAutoCreation:
    """Test VM creation workflow with automatic Bastion provisioning."""

    @patch("subprocess.run")
    def test_vm_creation_bastion_auto_created(self, mock_run):
        """Test creating VM with Bastion auto-creation."""
        # Arrange
        # User chooses to create Bastion (option 0)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        bastion_options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="test-vnet",
            vnet_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/test-vnet",
        )

        # Mock Azure CLI responses
        mock_run.side_effect = [
            # Check prerequisites
            Mock(returncode=0, stdout='{"name": "test-vnet"}'),  # VNet exists
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),  # Subnet exists
            Mock(returncode=1, stderr="ResourceNotFound"),  # Public IP missing
            # Create public IP
            Mock(returncode=0, stdout='{"name": "test-vnet-bastion-pip"}'),
            # Create Bastion
            Mock(
                returncode=0,
                stdout='{"name": "test-vnet-bastion", "provisioningState": "Creating"}',
            ),
        ]

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act - Step 1: Get user decision
            decision = orchestrator.ensure_bastion(bastion_options)

            # Assert decision
            assert decision.action == DecisionAction.CREATE
            assert decision.resource_name == "test-vnet-bastion"

            # Act - Step 2: Provision Bastion
            if decision.action == DecisionAction.CREATE:
                with patch(
                    "azlin.modules.bastion_provisioner.BastionDetector.get_bastion",
                    return_value={"provisioningState": "Succeeded"},
                ):
                    result = BastionProvisioner.provision_bastion(
                        bastion_name=decision.resource_name,
                        resource_group=bastion_options.resource_group,
                        location=bastion_options.region,
                        vnet_name=bastion_options.vnet_name,
                        wait_for_completion=True,
                        timeout=10,
                    )

                # Assert provisioning
                assert result.success is True
                assert "bastion:test-vnet-bastion" in result.resources_created

                # Track resource for potential rollback
                orchestrator.track_resource(
                    resource_type=result.resource_type if hasattr(result, "resource_type") else "bastion",
                    resource_id=f"/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/bastionHosts/{result.bastion_name}",
                    resource_name=result.bastion_name,
                )

        # Verify user saw cost information
        choice_interactions = handler.get_interactions_by_type("choice")
        assert len(choice_interactions) == 1
        choices = choice_interactions[0]["choices"]
        bastion_choice = choices[0]
        assert bastion_choice[2] > 0  # Cost shown

    @patch("subprocess.run")
    def test_vm_creation_user_skips_bastion(self, mock_run):
        """Test VM creation when user declines Bastion."""
        # Arrange
        # User chooses public IP option (option 1)
        handler = MockInteractionHandler(choice_responses=[1])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        bastion_options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="test-vnet",
            allow_public_ip_fallback=True,
        )

        # Mock no existing Bastion
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            # Act
            decision = orchestrator.ensure_bastion(bastion_options)

        # Assert
        assert decision.action == DecisionAction.SKIP
        assert decision.metadata["fallback"] == "public-ip"

        # Verify warning shown
        warnings = handler.get_interactions_by_type("warning")
        assert any("public IP" in w["message"] for w in warnings)

        # No Azure CLI calls should have been made
        assert mock_run.call_count == 0


class TestVMCreationWithCrossRegionNFS:
    """Test VM creation with cross-region NFS setup."""

    @patch("subprocess.run")
    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    def test_vm_creation_cross_region_nfs_setup(self, mock_get_storage, mock_run):
        """Test VM creation with cross-region NFS access."""
        # Arrange
        mock_get_storage.return_value = Mock(size_gb=100, tier="Premium")

        # User chooses to setup cross-region access (option 0)
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        nfs_options = NFSOptions(
            region="westus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",  # Cross-region
            share_name="home",
        )

        # Mock Azure CLI for private endpoint setup
        mock_run.side_effect = [
            # Private endpoint creation
            Mock(returncode=0, stdout="/subscriptions/.../storage\n"),
            Mock(returncode=0, stdout="/subscriptions/.../subnet\n"),
            Mock(
                returncode=0,
                stdout=json.dumps({
                    "name": "mystorageacct-pe-westus",
                    "provisioningState": "Succeeded",
                    "customDnsConfigs": [{"ipAddresses": ["10.0.1.5"]}],
                }),
            ),
            # DNS configuration
            Mock(returncode=0),  # Create zone
            Mock(returncode=0, stdout="/subscriptions/.../vnet\n"),  # Get VNet
            Mock(returncode=0),  # Link VNet
            Mock(returncode=0),  # Create zone group
        ]

        # Act - Step 1: Get user decision
        decision = orchestrator.ensure_nfs_access(nfs_options)

        # Assert decision
        assert decision.action == DecisionAction.CREATE
        assert decision.metadata["cross_region"] is True
        assert decision.cost_estimate > 0

        # Act - Step 2: Setup private endpoint
        if decision.action == DecisionAction.CREATE:
            endpoint, peering, dns_zone = NFSProvisioner.setup_private_endpoint_access(
                storage_account=nfs_options.storage_account_name,
                storage_resource_group=nfs_options.resource_group,
                target_region=nfs_options.region,
                target_resource_group=nfs_options.resource_group,
                target_vnet="test-vnet",
                target_subnet="default",
            )

            # Assert setup
            assert endpoint.storage_account == "mystorageacct"
            assert dns_zone.name == "privatelink.file.core.windows.net"

    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    def test_vm_creation_same_region_nfs_direct_mount(self, mock_get_storage):
        """Test VM creation with same-region NFS (simple mount)."""
        # Arrange
        handler = MockInteractionHandler()
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        nfs_options = NFSOptions(
            region="eastus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",  # Same region
            share_name="home",
        )

        # Act
        decision = orchestrator.ensure_nfs_access(nfs_options)

        # Assert
        assert decision.action == DecisionAction.USE_EXISTING
        assert decision.metadata["cross_region"] is False
        assert decision.cost_estimate is None  # No additional cost

        # Verify info message
        infos = handler.get_interactions_by_type("info")
        assert len(infos) == 1
        assert "local region" in infos[0]["message"].lower()


class TestVMDeletionWithCleanup:
    """Test VM deletion with orphaned resource cleanup."""

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_vm_deletion_triggers_bastion_cleanup(self, mock_list_vms, mock_run):
        """Test VM deletion that leaves Bastion orphaned."""
        # Arrange - Simulate deleting last VM in region
        mock_list_vms.return_value = []  # No VMs left after deletion

        def run_side_effect(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "bastion list" in cmd_str:
                return Mock(
                    returncode=0,
                    stdout=json.dumps([
                        {
                            "name": "now-orphaned-bastion",
                            "location": "eastus",
                            "provisioningState": "Succeeded",
                            "sku": {"name": "Standard"},
                        }
                    ]),
                )
            elif "bastion delete" in cmd_str:
                return Mock(returncode=0)
            else:
                return Mock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act - Detect orphaned Bastions after VM deletion
        orphaned = orchestrator.detect_orphaned_bastions()

        # Assert
        assert len(orphaned) == 1
        assert orphaned[0].name == "now-orphaned-bastion"
        assert orphaned[0].vm_count == 0
        assert orphaned[0].estimated_monthly_cost > 0

        # Act - Cleanup orphaned Bastion
        results = orchestrator.cleanup_orphaned_bastions(force=True)

        # Assert cleanup
        assert len(results) == 1
        assert results[0].bastion_name == "now-orphaned-bastion"
        assert results[0].estimated_monthly_savings > 0

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_vm_deletion_preserves_bastion_in_use(self, mock_list_vms, mock_run):
        """Test VM deletion doesn't cleanup Bastion still in use."""
        # Arrange - Other VMs still exist in same region
        mock_list_vms.return_value = [
            VMInfo(
                name="remaining-vm",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip=None,  # Using Bastion
                vm_id="/subscriptions/.../remaining-vm",
            )
        ]

        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps([
                {
                    "name": "still-in-use-bastion",
                    "location": "eastus",
                    "provisioningState": "Succeeded",
                }
            ]),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        orphaned = orchestrator.detect_orphaned_bastions()

        # Assert - Bastion should not be detected as orphaned
        assert len(orphaned) == 0


class TestCompleteVMLifecycle:
    """Integration test for complete VM lifecycle with auto-creation."""

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_complete_lifecycle_create_use_delete_cleanup(
        self, mock_list_vms, mock_run
    ):
        """Test complete VM lifecycle: create with Bastion -> use -> delete -> cleanup."""
        # ===== Phase 1: VM Creation with Bastion =====
        # User chooses to create Bastion (option 0)
        creation_handler = MockInteractionHandler(choice_responses=[0])
        resource_orchestrator = ResourceOrchestrator(
            interaction_handler=creation_handler
        )

        bastion_options = BastionOptions(
            region="eastus",
            resource_group="test-rg",
            vnet_name="test-vnet",
            vnet_id="/subscriptions/.../test-vnet",
        )

        # Mock Azure CLI for creation
        creation_calls = [
            # Bastion prerequisite checks
            Mock(returncode=0, stdout='{"name": "test-vnet"}'),
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            Mock(returncode=1, stderr="ResourceNotFound"),  # No public IP
            # Create resources
            Mock(returncode=0, stdout='{"name": "test-vnet-bastion-pip"}'),
            Mock(
                returncode=0,
                stdout='{"name": "test-vnet-bastion", "provisioningState": "Creating"}',
            ),
        ]

        mock_run.side_effect = creation_calls

        # Act - Phase 1: Create Bastion
        with patch.object(
            resource_orchestrator, "_check_existing_bastion", return_value=None
        ):
            decision = resource_orchestrator.ensure_bastion(bastion_options)

            assert decision.action == DecisionAction.CREATE

            with patch(
                "azlin.modules.bastion_provisioner.BastionDetector.get_bastion",
                return_value={"provisioningState": "Succeeded"},
            ):
                result = BastionProvisioner.provision_bastion(
                    bastion_name=decision.resource_name,
                    resource_group="test-rg",
                    location="eastus",
                    vnet_name="test-vnet",
                    wait_for_completion=True,
                    timeout=10,
                )

        # Assert Phase 1
        assert result.success is True
        creation_cost = decision.cost_estimate
        assert creation_cost > 0

        # ===== Phase 2: VM Usage (simulated) =====
        # VM is running and using Bastion...
        # (This would be actual SSH connections, file transfers, etc.)

        # ===== Phase 3: VM Deletion =====
        # Simulate VM deletion by showing no VMs remain
        mock_list_vms.return_value = []

        # Reset mock_run for cleanup phase
        cleanup_calls = [
            # List Bastions
            Mock(
                returncode=0,
                stdout=json.dumps([
                    {
                        "name": "test-vnet-bastion",
                        "location": "eastus",
                        "provisioningState": "Succeeded",
                        "sku": {"name": "Standard"},
                    }
                ]),
            ),
            # Delete Bastion
            Mock(returncode=0),
            # Delete public IP (auto-detect fails, but that's ok)
        ]

        mock_run.side_effect = cleanup_calls

        # ===== Phase 4: Cleanup Orphaned Resources =====
        cleanup_handler = MockInteractionHandler()
        cleanup_orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=cleanup_handler,
        )

        # Act - Phase 4: Detect and cleanup
        orphaned = cleanup_orchestrator.detect_orphaned_bastions()

        assert len(orphaned) == 1
        assert orphaned[0].name == "test-vnet-bastion"

        # Cleanup with force to skip prompt
        cleanup_results = cleanup_orchestrator.cleanup_orphaned_bastions(force=True)

        # Assert Phase 4
        assert len(cleanup_results) == 1
        result = cleanup_results[0]
        assert result.bastion_name == "test-vnet-bastion"
        assert result.was_successful() is True

        # Verify cost savings matches original creation cost
        savings = result.estimated_monthly_savings
        assert savings > 0
        assert float(savings) >= float(creation_cost) * 0.9  # Within 10% (accounting for rounding)

    @patch("subprocess.run")
    @patch("azlin.modules.nfs_provisioner.StorageManager.get_storage")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_complete_lifecycle_with_bastion_and_cross_region_nfs(
        self, mock_list_vms, mock_get_storage, mock_run
    ):
        """Test lifecycle with both Bastion and cross-region NFS."""
        # Arrange
        mock_get_storage.return_value = Mock(size_gb=100, tier="Premium")

        # User chooses to create both Bastion and cross-region NFS (options 0, 0)
        handler = MockInteractionHandler(choice_responses=[0, 0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        bastion_options = BastionOptions(
            region="westus",
            resource_group="test-rg",
            vnet_name="test-vnet",
        )

        nfs_options = NFSOptions(
            region="westus",
            resource_group="test-rg",
            storage_account_name="mystorageacct",
            storage_account_region="eastus",  # Cross-region
            share_name="home",
        )

        # Mock Azure CLI responses
        mock_run.side_effect = [
            # Bastion creation (simplified)
            Mock(returncode=0, stdout='{"name": "test-vnet"}'),
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            Mock(returncode=1),  # No public IP
            Mock(returncode=0),  # Create public IP
            Mock(returncode=0),  # Create Bastion
            # NFS private endpoint setup
            Mock(returncode=0, stdout="/subscriptions/.../storage\n"),
            Mock(returncode=0, stdout="/subscriptions/.../subnet\n"),
            Mock(
                returncode=0,
                stdout=json.dumps({
                    "name": "mystorageacct-pe-westus",
                    "provisioningState": "Succeeded",
                }),
            ),
            Mock(returncode=0),  # DNS zone
            Mock(returncode=0, stdout="/subscriptions/.../vnet\n"),
            Mock(returncode=0),  # Link VNet
            Mock(returncode=0),  # Zone group
        ]

        # Act - Get decisions for both resources
        with patch.object(orchestrator, "_check_existing_bastion", return_value=None):
            bastion_decision = orchestrator.ensure_bastion(bastion_options)
            nfs_decision = orchestrator.ensure_nfs_access(nfs_options)

        # Assert both decisions
        assert bastion_decision.action == DecisionAction.CREATE
        assert nfs_decision.action == DecisionAction.CREATE

        total_cost = bastion_decision.cost_estimate + nfs_decision.cost_estimate
        assert total_cost > 0

        # Verify user saw warnings/info for both
        warnings = handler.get_interactions_by_type("warning")
        assert len(warnings) >= 2  # At least one for each resource


class TestRollbackScenarios:
    """Test rollback scenarios for failed operations."""

    @patch("subprocess.run")
    def test_bastion_provisioning_failure_tracks_partial_resources(self, mock_run):
        """Test rollback tracking when Bastion provisioning fails."""
        # Arrange
        handler = MockInteractionHandler(choice_responses=[0])
        orchestrator = ResourceOrchestrator(interaction_handler=handler)

        # Mock Azure CLI - public IP succeeds, Bastion fails
        mock_run.side_effect = [
            # Prerequisites
            Mock(returncode=0, stdout='{"name": "test-vnet"}'),
            Mock(returncode=0, stdout='{"name": "AzureBastionSubnet"}'),
            Mock(returncode=1),  # No public IP
            # Create public IP - SUCCESS
            Mock(returncode=0, stdout='{"name": "my-pip"}'),
            # Create Bastion - FAILS
            Mock(returncode=1, stderr="QuotaExceeded"),
        ]

        # Act
        result = BastionProvisioner.provision_bastion(
            bastion_name="my-bastion",
            resource_group="test-rg",
            location="eastus",
            vnet_name="test-vnet",
            wait_for_completion=False,
        )

        # Assert
        assert result.success is False
        # Public IP should be in created resources (for potential rollback)
        assert "public-ip:my-pip" in result.resources_created
        # Bastion should not be in created resources
        assert not any("bastion:" in r for r in result.resources_created)

        # Resources are tracked for manual cleanup decision
        assert len(result.resources_created) > 0

    @patch("subprocess.run")
    def test_rollback_after_partial_failure(self, mock_run):
        """Test explicit rollback after partial provisioning failure."""
        # Arrange
        mock_run.side_effect = [
            # Rollback: delete public IP
            Mock(returncode=0),
        ]

        resources_created = ["public-ip:my-pip"]

        # Act
        status = BastionProvisioner.rollback_bastion(
            bastion_name="my-bastion",
            resource_group="test-rg",
            resources_created=resources_created,
            delete_bastion=False,  # Don't delete Bastion (it wasn't created)
        )

        # Assert
        assert status["public-ip:my-pip"] is True
        assert mock_run.call_count == 1
