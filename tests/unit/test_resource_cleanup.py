"""Unit tests for resource cleanup module.

Tests for detecting and removing orphaned Azure resources:
- Unattached disks
- Orphaned NICs
- Orphaned public IPs
"""

from unittest.mock import Mock, patch

import pytest

# Module to be implemented
from azlin.resource_cleanup import (
    CleanupSummary,
    OrphanedResource,
    ResourceCleanup,
    ResourceCleanupError,
)


class TestOrphanedResourceDetection:
    """Test detection of orphaned resources."""

    @patch("subprocess.run")
    def test_detect_orphaned_disks(self, mock_run):
        """Test detection of unattached disks."""
        # Mock Azure CLI response for disks
        mock_run.return_value = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}, '
            '{"name": "disk2", "diskState": "Attached", "managedBy": "/subscriptions/.../vm1"}, '
            '{"name": "disk3", "managedBy": null, "diskSizeGb": 100, "sku": {"name": "Standard_LRS"}}]',
            stderr="",
        )

        orphaned = ResourceCleanup.detect_orphaned_disks("test-rg")

        # Should find 2 orphaned disks (disk1 and disk3)
        assert len(orphaned) == 2
        assert orphaned[0].name == "disk1"
        assert orphaned[0].resource_type == "disk"
        assert orphaned[1].name == "disk3"

    @patch("subprocess.run")
    def test_detect_orphaned_nics(self, mock_run):
        """Test detection of orphaned NICs."""
        # Mock Azure CLI response for NICs
        mock_run.return_value = Mock(
            returncode=0,
            stdout='[{"name": "nic1", "virtualMachine": null}, '
            '{"name": "nic2", "virtualMachine": {"id": "/subscriptions/.../vm1"}}, '
            '{"name": "nic3", "virtualMachine": null}]',
            stderr="",
        )

        orphaned = ResourceCleanup.detect_orphaned_nics("test-rg")

        # Should find 2 orphaned NICs (nic1 and nic3)
        assert len(orphaned) == 2
        assert orphaned[0].name == "nic1"
        assert orphaned[0].resource_type == "nic"
        assert orphaned[1].name == "nic3"

    @patch("subprocess.run")
    def test_detect_orphaned_public_ips(self, mock_run):
        """Test detection of orphaned public IPs."""
        # Mock Azure CLI response for public IPs
        mock_run.return_value = Mock(
            returncode=0,
            stdout='[{"name": "ip1", "ipConfiguration": null, "ipAddress": "20.1.2.3"}, '
            '{"name": "ip2", "ipConfiguration": {"id": "/subscriptions/.../nic1"}}, '
            '{"name": "ip3", "ipConfiguration": null, "ipAddress": "20.1.2.4"}]',
            stderr="",
        )

        orphaned = ResourceCleanup.detect_orphaned_public_ips("test-rg")

        # Should find 2 orphaned IPs (ip1 and ip3)
        assert len(orphaned) == 2
        assert orphaned[0].name == "ip1"
        assert orphaned[0].resource_type == "public-ip"
        assert orphaned[1].name == "ip3"

    @patch("subprocess.run")
    def test_find_all_orphaned_resources(self, mock_run):
        """Test finding all orphaned resources in a resource group."""
        # Mock responses for disks, NICs, and public IPs
        disk_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(
            returncode=0, stdout='[{"name": "nic1", "virtualMachine": null}]', stderr=""
        )
        ip_response = Mock(
            returncode=0,
            stdout='[{"name": "ip1", "ipConfiguration": null, "ipAddress": "20.1.2.3"}]',
            stderr="",
        )

        mock_run.side_effect = [disk_response, nic_response, ip_response]

        summary = ResourceCleanup.find_orphaned_resources("test-rg")

        # Should find 3 total orphaned resources
        assert summary.total_orphaned == 3
        assert summary.orphaned_disks == 1
        assert summary.orphaned_nics == 1
        assert summary.orphaned_public_ips == 1


class TestDryRunMode:
    """Test dry-run functionality."""

    @patch("subprocess.run")
    def test_dry_run_shows_resources_without_deleting(self, mock_run):
        """Test dry-run mode shows what would be deleted without actually deleting."""
        # Mock finding orphaned resources
        disk_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(returncode=0, stdout="[]", stderr="")

        mock_run.side_effect = [disk_response, nic_response, ip_response]

        summary = ResourceCleanup.cleanup_resources(resource_group="test-rg", dry_run=True)

        # Should show found resources
        assert summary.total_orphaned == 1
        assert summary.deleted_count == 0
        assert summary.dry_run is True

        # Should not call any delete commands
        delete_calls = [c for c in mock_run.call_args_list if "delete" in str(c)]
        assert len(delete_calls) == 0


class TestResourceDeletion:
    """Test actual resource deletion."""

    @patch("subprocess.run")
    @patch("builtins.input", return_value="delete")
    def test_delete_orphaned_resources_with_confirmation(self, mock_input, mock_run):
        """Test deleting orphaned resources with user confirmation."""
        # Mock finding and deleting resources
        disk_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(returncode=0, stdout="[]", stderr="")
        delete_response = Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = [disk_response, nic_response, ip_response, delete_response]

        summary = ResourceCleanup.cleanup_resources(
            resource_group="test-rg", dry_run=False, force=False
        )

        # Should delete 1 resource
        assert summary.deleted_count == 1
        assert summary.failed_count == 0

        # Should have prompted for confirmation
        mock_input.assert_called_once()

    @patch("subprocess.run")
    def test_delete_with_force_skips_confirmation(self, mock_run):
        """Test force flag skips confirmation prompt."""
        # Mock responses
        disk_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(returncode=0, stdout="[]", stderr="")
        delete_response = Mock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = [disk_response, nic_response, ip_response, delete_response]

        with patch("builtins.input") as mock_input:
            summary = ResourceCleanup.cleanup_resources(
                resource_group="test-rg", dry_run=False, force=True
            )

            # Should not prompt for confirmation
            mock_input.assert_not_called()
            assert summary.deleted_count == 1

    @patch("subprocess.run")
    @patch("builtins.input", return_value="cancel")
    def test_delete_cancelled_by_user(self, mock_input, mock_run):
        """Test deletion cancelled by user."""
        # Mock finding resources
        disk_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(returncode=0, stdout="[]", stderr="")

        mock_run.side_effect = [disk_response, nic_response, ip_response]

        summary = ResourceCleanup.cleanup_resources(
            resource_group="test-rg", dry_run=False, force=False
        )

        # Should not delete anything
        assert summary.deleted_count == 0
        assert summary.cancelled is True


class TestErrorHandling:
    """Test error handling."""

    @patch("subprocess.run")
    def test_azure_cli_error_raises_exception(self, mock_run):
        """Test Azure CLI error raises ResourceCleanupError."""
        mock_run.return_value = Mock(
            returncode=1, stdout="", stderr="ERROR: Resource group not found"
        )

        with pytest.raises(ResourceCleanupError, match="Resource group not found"):
            ResourceCleanup.detect_orphaned_disks("nonexistent-rg")

    @patch("subprocess.run")
    def test_partial_deletion_failure(self, mock_run):
        """Test handling of partial deletion failures."""
        # Mock finding resources
        disk1_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 30, "sku": {"name": "Premium_LRS"}}, '
            '{"name": "disk2", "diskState": "Unattached", "diskSizeGb": 50, "sku": {"name": "Premium_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(returncode=0, stdout="[]", stderr="")
        delete_success = Mock(returncode=0, stdout="", stderr="")
        delete_failure = Mock(returncode=1, stdout="", stderr="ERROR: Cannot delete disk")

        mock_run.side_effect = [
            disk1_response,
            nic_response,
            ip_response,
            delete_success,
            delete_failure,
        ]

        summary = ResourceCleanup.cleanup_resources(
            resource_group="test-rg", dry_run=False, force=True
        )

        # Should show partial success
        assert summary.deleted_count == 1
        assert summary.failed_count == 1
        assert len(summary.errors) == 1


class TestCostEstimation:
    """Test cost estimation for orphaned resources."""

    @patch("subprocess.run")
    def test_estimate_savings_from_cleanup(self, mock_run):
        """Test cost estimation for orphaned resources."""
        # Mock finding resources with size/tier information
        disk_response = Mock(
            returncode=0,
            stdout='[{"name": "disk1", "diskState": "Unattached", "diskSizeGb": 128, "sku": {"name": "Premium_LRS"}}, '
            '{"name": "disk2", "diskState": "Unattached", "diskSizeGb": 512, "sku": {"name": "Standard_LRS"}}]',
            stderr="",
        )
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(
            returncode=0,
            stdout='[{"name": "ip1", "ipConfiguration": null, "ipAddress": "20.1.2.3"}]',
            stderr="",
        )

        mock_run.side_effect = [disk_response, nic_response, ip_response]

        summary = ResourceCleanup.find_orphaned_resources("test-rg")

        # Should calculate estimated monthly savings
        assert summary.estimated_monthly_savings > 0
        # Premium 128GB (~$17) + Standard 512GB (~$26) + Public IP (~$3.65) = ~$46.65/month
        assert 40 < summary.estimated_monthly_savings < 50


class TestResourceGroupFiltering:
    """Test resource group filtering."""

    @patch("subprocess.run")
    def test_resource_group_required(self, mock_run):
        """Test that resource group is required."""
        disk_response = Mock(returncode=0, stdout="[]", stderr="")
        nic_response = Mock(returncode=0, stdout="[]", stderr="")
        ip_response = Mock(returncode=0, stdout="[]", stderr="")

        mock_run.side_effect = [disk_response, nic_response, ip_response]

        # Should work with explicit resource group
        summary = ResourceCleanup.find_orphaned_resources(resource_group="test-rg")
        assert summary.total_orphaned == 0


class TestFormattedOutput:
    """Test formatted output for CLI display."""

    def test_format_cleanup_summary(self):
        """Test formatting cleanup summary for display."""
        resources = [
            OrphanedResource(
                name="disk1",
                resource_type="disk",
                resource_group="test-rg",
                size_gb=30,
                tier="Premium_LRS",
            ),
            OrphanedResource(name="nic1", resource_type="nic", resource_group="test-rg"),
        ]

        summary = CleanupSummary(
            total_orphaned=2,
            orphaned_disks=1,
            orphaned_nics=1,
            orphaned_public_ips=0,
            resources=resources,
            estimated_monthly_savings=10.50,
        )

        output = ResourceCleanup.format_summary(summary, dry_run=True)

        # Should contain key information
        assert "2" in output  # total count
        assert "disk1" in output
        assert "nic1" in output
        assert "$10.50" in output or "10.50" in output  # estimated savings
        assert "DRY RUN" in output or "dry run" in output.lower()
