"""Unit tests for cleanup_orchestrator module.

Tests orphan detection, cleanup decisions, and resource deletion.
"""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.cleanup_orchestrator import (
    BastionCleanupError,
    BastionCleanupResult,
    CleanupDecision,
    CleanupOrchestrator,
    OrphanedBastionInfo,
)
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.vm_manager import VMInfo


class TestOrphanedBastionInfo:
    """Test OrphanedBastionInfo dataclass."""

    def test_calculate_cost_basic_sku(self):
        """Basic SKU cost calculation."""
        bastion = OrphanedBastionInfo(
            name="my-bastion",
            resource_group="my-rg",
            location="eastus",
            sku="Basic",
        )

        bastion.calculate_cost()

        assert bastion.estimated_monthly_cost == Decimal("143.65")  # 140 + 3.65

    def test_calculate_cost_standard_sku(self):
        """Standard SKU cost calculation."""
        bastion = OrphanedBastionInfo(
            name="my-bastion",
            resource_group="my-rg",
            location="eastus",
            sku="Standard",
        )

        bastion.calculate_cost()

        assert bastion.estimated_monthly_cost == Decimal("292.65")  # 289 + 3.65

    def test_calculate_cost_no_sku(self):
        """No SKU should default to Basic cost."""
        bastion = OrphanedBastionInfo(
            name="my-bastion",
            resource_group="my-rg",
            location="eastus",
        )

        bastion.calculate_cost()

        assert bastion.estimated_monthly_cost == Decimal("143.65")


class TestCleanupDecision:
    """Test CleanupDecision dataclass."""

    def test_approved_decision(self):
        """Approved cleanup decision."""
        decision = CleanupDecision(
            approved=True,
            resources_to_delete=["bastion1", "bastion2"],
            estimated_savings=Decimal("287.30"),
        )

        assert decision.approved is True
        assert len(decision.resources_to_delete) == 2

    def test_cancelled_decision(self):
        """Cancelled cleanup decision."""
        decision = CleanupDecision(cancelled=True)

        assert decision.cancelled is True
        assert decision.approved is False


class TestBastionCleanupResult:
    """Test BastionCleanupResult dataclass."""

    def test_successful_cleanup(self):
        """Successful cleanup result."""
        result = BastionCleanupResult(
            bastion_name="my-bastion",
            resource_group="my-rg",
            deleted_resources=["my-bastion", "my-bastion-pip"],
            estimated_monthly_savings=Decimal("143.65"),
        )

        assert result.was_successful() is True
        assert len(result.deleted_resources) == 2

    def test_partial_cleanup(self):
        """Partial cleanup with some failures."""
        result = BastionCleanupResult(
            bastion_name="my-bastion",
            resource_group="my-rg",
            deleted_resources=["my-bastion"],
            failed_resources=["my-bastion-pip"],
            estimated_monthly_savings=Decimal("143.65"),
        )

        assert result.was_successful() is False
        assert len(result.failed_resources) == 1

    def test_cleanup_with_errors(self):
        """Cleanup with error messages."""
        result = BastionCleanupResult(
            bastion_name="my-bastion",
            resource_group="my-rg",
            errors=["Failed to delete public IP"],
        )

        assert result.was_successful() is False


class TestDetectOrphanedBastions:
    """Test orphaned Bastion detection."""

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._list_bastions")
    def test_detect_orphaned_no_vms(self, mock_list_bastions, mock_list_vms):
        """Bastion with no VMs should be detected as orphaned."""
        # No VMs
        mock_list_vms.return_value = []

        # One Bastion
        mock_list_bastions.return_value = [
            {
                "name": "orphaned-bastion",
                "location": "eastus",
                "provisioningState": "Succeeded",
                "sku": {"name": "Basic"},
            }
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        orphaned = orchestrator.detect_orphaned_bastions()

        assert len(orphaned) == 1
        assert orphaned[0].name == "orphaned-bastion"
        assert orphaned[0].vm_count == 0

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._list_bastions")
    def test_detect_bastion_with_vms_not_orphaned(self, mock_list_bastions, mock_list_vms):
        """Bastion with VMs should not be detected as orphaned."""
        # VM without public IP (uses Bastion)
        mock_list_vms.return_value = [
            VMInfo(
                name="vm1",
                resource_group="my-rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,  # No public IP = uses Bastion
                private_ip="10.0.0.4",
            )
        ]

        # One Bastion in same region
        mock_list_bastions.return_value = [
            {
                "name": "active-bastion",
                "location": "eastus",
                "provisioningState": "Succeeded",
                "sku": {"name": "Basic"},
            }
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        orphaned = orchestrator.detect_orphaned_bastions()

        assert len(orphaned) == 0

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._list_bastions")
    def test_detect_bastion_different_region_orphaned(self, mock_list_bastions, mock_list_vms):
        """Bastion in different region from VMs should be orphaned."""
        # VM in eastus
        mock_list_vms.return_value = [
            VMInfo(
                name="vm1",
                resource_group="my-rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.0.4",
            )
        ]

        # Bastion in westus (different region)
        mock_list_bastions.return_value = [
            {
                "name": "westus-bastion",
                "location": "westus",
                "provisioningState": "Succeeded",
                "sku": {"name": "Basic"},
            }
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        orphaned = orchestrator.detect_orphaned_bastions()

        assert len(orphaned) == 1
        assert orphaned[0].name == "westus-bastion"
        assert orphaned[0].vm_count == 0

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._list_bastions")
    def test_detect_skips_failed_bastions(self, mock_list_bastions, mock_list_vms):
        """Failed Bastions should be skipped."""
        mock_list_vms.return_value = []

        # Bastion in Failed state
        mock_list_bastions.return_value = [
            {
                "name": "failed-bastion",
                "location": "eastus",
                "provisioningState": "Failed",  # Not Succeeded
                "sku": {"name": "Basic"},
            }
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        orphaned = orchestrator.detect_orphaned_bastions()

        assert len(orphaned) == 0


class TestCleanupBastion:
    """Test individual Bastion cleanup."""

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._delete_bastion")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._delete_public_ip")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._detect_bastion_public_ip")
    def test_cleanup_bastion_success(self, mock_detect_ip, mock_delete_ip, mock_delete_bastion):
        """Successful Bastion cleanup."""
        mock_detect_ip.return_value = "my-bastion-pip"
        mock_delete_bastion.return_value = True
        mock_delete_ip.return_value = True

        orchestrator = CleanupOrchestrator("my-rg")
        result = orchestrator.cleanup_bastion("my-bastion", "eastus")

        assert result.was_successful() is True
        assert "my-bastion" in result.deleted_resources
        assert "my-bastion-pip" in result.deleted_resources
        assert result.estimated_monthly_savings > 0

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator._delete_bastion")
    def test_cleanup_bastion_deletion_fails(self, mock_delete_bastion):
        """Failed Bastion deletion should be recorded."""
        mock_delete_bastion.return_value = False

        orchestrator = CleanupOrchestrator("my-rg")
        result = orchestrator.cleanup_bastion("my-bastion", "eastus")

        assert result.was_successful() is False
        assert "my-bastion" in result.failed_resources

    def test_cleanup_bastion_dry_run(self):
        """Dry run should not delete resources."""
        orchestrator = CleanupOrchestrator("my-rg", dry_run=True)
        result = orchestrator.cleanup_bastion("my-bastion", "eastus")

        # Should mark as deleted but with [DRY RUN] prefix
        assert len(result.deleted_resources) > 0
        assert "[DRY RUN]" in str(result.deleted_resources)


class TestCleanupOrphanedBastions:
    """Test full orphaned Bastion cleanup workflow."""

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.detect_orphaned_bastions")
    def test_cleanup_no_orphaned_bastions(self, mock_detect):
        """No orphaned Bastions should return empty results."""
        mock_detect.return_value = []

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator("my-rg", interaction_handler=handler)

        results = orchestrator.cleanup_orphaned_bastions()

        assert len(results) == 0

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.detect_orphaned_bastions")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.cleanup_bastion")
    @patch("builtins.input")
    def test_cleanup_user_confirms_deletion(self, mock_input, mock_cleanup_bastion, mock_detect):
        """User confirming should delete Bastions."""
        # Mock orphaned Bastion
        orphaned_bastion = OrphanedBastionInfo(
            name="orphaned-bastion",
            resource_group="my-rg",
            location="eastus",
            sku="Basic",
        )
        orphaned_bastion.calculate_cost()
        mock_detect.return_value = [orphaned_bastion]

        # User types "delete"
        mock_input.return_value = "delete"

        # Mock successful cleanup
        mock_cleanup_bastion.return_value = BastionCleanupResult(
            bastion_name="orphaned-bastion",
            resource_group="my-rg",
            deleted_resources=["orphaned-bastion", "orphaned-bastion-pip"],
            estimated_monthly_savings=Decimal("143.65"),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator("my-rg", interaction_handler=handler)

        results = orchestrator.cleanup_orphaned_bastions()

        assert len(results) == 1
        assert mock_cleanup_bastion.called

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.detect_orphaned_bastions")
    @patch("builtins.input")
    def test_cleanup_user_cancels(self, mock_input, mock_detect):
        """User canceling should not delete anything."""
        orphaned_bastion = OrphanedBastionInfo(
            name="orphaned-bastion",
            resource_group="my-rg",
            location="eastus",
        )
        orphaned_bastion.calculate_cost()
        mock_detect.return_value = [orphaned_bastion]

        # User types "cancel"
        mock_input.return_value = "cancel"

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator("my-rg", interaction_handler=handler)

        results = orchestrator.cleanup_orphaned_bastions()

        assert len(results) == 0

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.detect_orphaned_bastions")
    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.cleanup_bastion")
    def test_cleanup_force_skips_confirmation(self, mock_cleanup_bastion, mock_detect):
        """Force flag should skip confirmation."""
        orphaned_bastion = OrphanedBastionInfo(
            name="orphaned-bastion",
            resource_group="my-rg",
            location="eastus",
        )
        orphaned_bastion.calculate_cost()
        mock_detect.return_value = [orphaned_bastion]

        mock_cleanup_bastion.return_value = BastionCleanupResult(
            bastion_name="orphaned-bastion",
            resource_group="my-rg",
            deleted_resources=["orphaned-bastion"],
            estimated_monthly_savings=Decimal("143.65"),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator("my-rg", interaction_handler=handler)

        results = orchestrator.cleanup_orphaned_bastions(force=True)

        assert len(results) == 1
        assert mock_cleanup_bastion.called


class TestGetVMsUsingBastion:
    """Test VM filtering by Bastion usage."""

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_get_vms_using_bastion_no_public_ip(self, mock_list_vms):
        """VMs without public IP should be returned."""
        mock_list_vms.return_value = [
            VMInfo(
                name="vm1",
                resource_group="my-rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,  # No public IP
                private_ip="10.0.0.4",
            ),
            VMInfo(
                name="vm2",
                resource_group="my-rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip="20.1.2.3",  # Has public IP
                private_ip="10.0.0.5",
            ),
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        bastion_vms = orchestrator.get_vms_using_bastion("eastus")

        assert len(bastion_vms) == 1
        assert bastion_vms[0].name == "vm1"

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_get_vms_filters_by_region(self, mock_list_vms):
        """Should filter VMs by region."""
        mock_list_vms.return_value = [
            VMInfo(
                name="vm-eastus",
                resource_group="my-rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.0.4",
            ),
            VMInfo(
                name="vm-westus",
                resource_group="my-rg",
                location="westus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.0.5",
            ),
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        eastus_vms = orchestrator.get_vms_using_bastion("eastus")

        assert len(eastus_vms) == 1
        assert eastus_vms[0].name == "vm-eastus"


class TestHelperMethods:
    """Test private helper methods."""

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_list_bastions_success(self, mock_run):
        """List Bastions should parse JSON output."""
        bastions_json = json.dumps(
            [
                {"name": "bastion1", "location": "eastus"},
                {"name": "bastion2", "location": "westus"},
            ]
        )
        mock_run.return_value = MagicMock(returncode=0, stdout=bastions_json)

        orchestrator = CleanupOrchestrator("my-rg")
        bastions = orchestrator._list_bastions()

        assert len(bastions) == 2
        assert bastions[0]["name"] == "bastion1"

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_list_bastions_error(self, mock_run):
        """List Bastions error should raise exception."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")

        orchestrator = CleanupOrchestrator("my-rg")

        with pytest.raises(BastionCleanupError):
            orchestrator._list_bastions()

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_delete_bastion_success(self, mock_run):
        """Delete Bastion should return True on success."""
        mock_run.return_value = MagicMock(returncode=0)

        orchestrator = CleanupOrchestrator("my-rg")
        success = orchestrator._delete_bastion("my-bastion")

        assert success is True

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_delete_bastion_failure(self, mock_run):
        """Delete Bastion should return False on failure."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error")

        orchestrator = CleanupOrchestrator("my-rg")
        success = orchestrator._delete_bastion("my-bastion")

        assert success is False

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_delete_public_ip_success(self, mock_run):
        """Delete public IP should return True on success."""
        mock_run.return_value = MagicMock(returncode=0)

        orchestrator = CleanupOrchestrator("my-rg")
        success = orchestrator._delete_public_ip("my-ip")

        assert success is True

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_detect_bastion_public_ip_found(self, mock_run):
        """Detect public IP should find common naming patterns."""
        # First attempt succeeds
        mock_run.return_value = MagicMock(returncode=0)

        orchestrator = CleanupOrchestrator("my-rg")
        ip_name = orchestrator._detect_bastion_public_ip("my-bastion")

        assert ip_name == "my-bastionPublicIP"

    @patch("azlin.modules.cleanup_orchestrator.subprocess.run")
    def test_detect_bastion_public_ip_not_found(self, mock_run):
        """Detect public IP should return None if not found."""
        # All attempts fail
        mock_run.return_value = MagicMock(returncode=1)

        orchestrator = CleanupOrchestrator("my-rg")
        ip_name = orchestrator._detect_bastion_public_ip("my-bastion")

        assert ip_name is None


class TestCleanupAllOrphanedResources:
    """Test comprehensive cleanup of all resource types."""

    @patch("azlin.modules.cleanup_orchestrator.CleanupOrchestrator.cleanup_orphaned_bastions")
    @patch("azlin.modules.cleanup_orchestrator.ResourceCleanup.cleanup_resources")
    def test_cleanup_all_resources(self, mock_resource_cleanup, mock_cleanup_bastions):
        """Should cleanup both Bastions and other resources."""
        # Mock Bastion cleanup
        mock_cleanup_bastions.return_value = [
            BastionCleanupResult(
                bastion_name="bastion1",
                resource_group="my-rg",
                deleted_resources=["bastion1"],
                estimated_monthly_savings=Decimal("143.65"),
            )
        ]

        # Mock other resource cleanup
        mock_resource_cleanup.return_value = MagicMock(
            deleted_count=3,
            failed_count=0,
            estimated_monthly_savings=20.0,
        )

        orchestrator = CleanupOrchestrator("my-rg")
        results = orchestrator.cleanup_all_orphaned_resources()

        assert results["total_deleted"] == 4  # 1 bastion + 3 other
        assert results["total_savings"] > 0
        assert mock_cleanup_bastions.called
        assert mock_resource_cleanup.called


class TestGroupVMsByRegion:
    """Test VM grouping by region."""

    def test_group_vms_by_region(self):
        """VMs should be grouped by region."""
        vms = [
            VMInfo(
                name="vm1",
                resource_group="rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.0.4",
            ),
            VMInfo(
                name="vm2",
                resource_group="rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.0.5",
            ),
            VMInfo(
                name="vm3",
                resource_group="rg",
                location="westus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.1.4",
            ),
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        grouped = orchestrator._group_vms_by_region(vms)

        assert len(grouped["eastus"]) == 2
        assert len(grouped["westus"]) == 1

    def test_group_vms_filters_public_ip(self):
        """VMs with public IP should be excluded."""
        vms = [
            VMInfo(
                name="vm-no-ip",
                resource_group="rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip=None,
                private_ip="10.0.0.4",
            ),
            VMInfo(
                name="vm-with-ip",
                resource_group="rg",
                location="eastus",
                power_state="running",
                vm_size="Standard_B2s",
                public_ip="20.1.2.3",
                private_ip="10.0.0.5",
            ),
        ]

        orchestrator = CleanupOrchestrator("my-rg")
        grouped = orchestrator._group_vms_by_region(vms)

        assert len(grouped["eastus"]) == 1
        assert grouped["eastus"][0].name == "vm-no-ip"
