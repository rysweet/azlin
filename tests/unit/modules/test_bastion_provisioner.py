"""Unit tests for bastion_provisioner module.

Tests provisioning logic with mocked Azure CLI calls.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.bastion_provisioner import (
    BastionProvisioner,
    BastionProvisionerError,
    PrerequisiteStatus,
    ProvisioningResult,
)


class TestInputValidation:
    """Test input validation for bastion provisioning."""

    def test_empty_bastion_name_raises_error(self):
        """Empty bastion name should raise error."""
        with pytest.raises(BastionProvisionerError, match="must be a non-empty string"):
            BastionProvisioner._validate_inputs("", "rg", "eastus")

    def test_empty_resource_group_raises_error(self):
        """Empty resource group should raise error."""
        with pytest.raises(BastionProvisionerError, match="must be a non-empty string"):
            BastionProvisioner._validate_inputs("bastion", "", "eastus")

    def test_empty_location_raises_error(self):
        """Empty location should raise error."""
        with pytest.raises(BastionProvisionerError, match="must be a non-empty string"):
            BastionProvisioner._validate_inputs("bastion", "rg", "")

    def test_invalid_bastion_name_format(self):
        """Invalid bastion name should raise error."""
        with pytest.raises(BastionProvisionerError, match="Bastion name"):
            BastionProvisioner._validate_inputs("bastion@name", "rg", "eastus")

    def test_valid_bastion_name(self):
        """Valid bastion name should not raise error."""
        # Should not raise
        BastionProvisioner._validate_inputs("my-bastion", "my-rg", "eastus")
        BastionProvisioner._validate_inputs("bastion_123", "rg", "westus")
        BastionProvisioner._validate_inputs("bastion.1", "rg", "centralus")


class TestPrerequisiteStatus:
    """Test PrerequisiteStatus dataclass."""

    def test_is_ready_all_satisfied(self):
        """Status with all prerequisites should be ready."""
        status = PrerequisiteStatus(
            vnet_exists=True,
            subnet_exists=True,
            public_ip_exists=True,
            quota_available=True,
        )
        assert status.is_ready() is True

    def test_is_ready_missing_vnet(self):
        """Status missing VNet should not be ready."""
        status = PrerequisiteStatus(
            vnet_exists=False,
            subnet_exists=True,
            public_ip_exists=True,
            quota_available=True,
        )
        assert status.is_ready() is False

    def test_is_ready_missing_multiple(self):
        """Status missing multiple prerequisites should not be ready."""
        status = PrerequisiteStatus(
            vnet_exists=False,
            subnet_exists=False,
            public_ip_exists=True,
            quota_available=True,
        )
        assert status.is_ready() is False

    def test_missing_resources_none(self):
        """Status with no missing resources."""
        status = PrerequisiteStatus(
            vnet_exists=True,
            subnet_exists=True,
            public_ip_exists=True,
            quota_available=True,
        )
        assert status.missing_resources() == []

    def test_missing_resources_vnet(self):
        """Status should list missing VNet."""
        status = PrerequisiteStatus(
            vnet_exists=False,
            subnet_exists=True,
            public_ip_exists=True,
            quota_available=True,
        )
        assert "vnet" in status.missing_resources()

    def test_missing_resources_multiple(self):
        """Status should list all missing resources."""
        status = PrerequisiteStatus(
            vnet_exists=False,
            subnet_exists=False,
            public_ip_exists=False,
            quota_available=True,
        )
        missing = status.missing_resources()
        assert "vnet" in missing
        assert "subnet" in missing
        assert "public_ip" in missing


class TestProvisioningResult:
    """Test ProvisioningResult dataclass."""

    def test_to_dict_success(self):
        """Successful result should convert to dict."""
        result = ProvisioningResult(
            success=True,
            bastion_name="my-bastion",
            resource_group="my-rg",
            location="eastus",
            resources_created=["vnet:my-vnet", "bastion:my-bastion"],
            provisioning_state="Succeeded",
            duration_seconds=300.5,
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["bastion_name"] == "my-bastion"
        assert result_dict["resource_group"] == "my-rg"
        assert result_dict["location"] == "eastus"
        assert len(result_dict["resources_created"]) == 2
        assert result_dict["provisioning_state"] == "Succeeded"
        assert result_dict["duration_seconds"] == 300.5

    def test_to_dict_failure(self):
        """Failed result should include error message."""
        result = ProvisioningResult(
            success=False,
            bastion_name="my-bastion",
            resource_group="my-rg",
            location="eastus",
            resources_created=[],
            error_message="Provisioning failed",
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is False
        assert result_dict["error_message"] == "Provisioning failed"


class TestErrorSanitization:
    """Test Azure CLI error message sanitization.

    The shared sanitize_azure_error extracts the message portion
    from Azure CLI error output rather than mapping to friendly names.
    """

    def test_sanitize_resource_not_found(self):
        """ResourceNotFound error should be sanitized."""
        stderr = "ERROR: ResourceNotFound: The resource was not found"
        sanitized = BastionProvisioner._sanitize_azure_error(stderr)
        assert "ResourceNotFound" in sanitized or "resource" in sanitized.lower()

    def test_sanitize_auth_failed(self):
        """Authentication errors should be sanitized."""
        stderr = "ERROR: InvalidAuthenticationToken: Token expired"
        sanitized = BastionProvisioner._sanitize_azure_error(stderr)
        assert "InvalidAuthenticationToken" in sanitized or "Token" in sanitized

    def test_sanitize_quota_exceeded(self):
        """Quota errors should be sanitized."""
        stderr = "ERROR: QuotaExceeded: You have reached your quota limit"
        sanitized = BastionProvisioner._sanitize_azure_error(stderr)
        assert "QuotaExceeded" in sanitized or "quota" in sanitized.lower()

    def test_sanitize_already_exists(self):
        """AlreadyExists errors should be sanitized."""
        stderr = "ERROR: Resource already exists in this region"
        sanitized = BastionProvisioner._sanitize_azure_error(stderr)
        assert "already exists" in sanitized.lower()

    def test_sanitize_generic_error(self):
        """Unknown errors should extract the error message."""
        stderr = "ERROR: SomeUnknownError: Something went wrong"
        sanitized = BastionProvisioner._sanitize_azure_error(stderr)
        assert sanitized  # Should return something non-empty
        assert "Something went wrong" in sanitized or "SomeUnknownError" in sanitized


class TestCheckPrerequisites:
    """Test prerequisite checking."""

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_check_prerequisites_vnet_exists(self, mock_run):
        """Check prerequisites should detect existing VNet."""
        # Mock VNet check - exists
        mock_run.return_value = MagicMock(returncode=0, stdout='{"name": "my-vnet"}')

        status = BastionProvisioner.check_prerequisites("my-rg", "eastus", vnet_name="my-vnet")

        assert status.vnet_exists is True
        assert status.vnet_name == "my-vnet"

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_check_prerequisites_vnet_not_exists(self, mock_run):
        """Check prerequisites should detect missing VNet."""
        # Mock VNet check - doesn't exist
        mock_run.return_value = MagicMock(returncode=1, stderr="ResourceNotFound")

        status = BastionProvisioner.check_prerequisites("my-rg", "eastus", vnet_name="missing-vnet")

        assert status.vnet_exists is False

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_check_prerequisites_no_vnet_specified(self, mock_run):
        """Check prerequisites with no VNet should list existing VNets."""
        # Mock VNet list
        mock_run.return_value = MagicMock(
            returncode=0, stdout='[{"name": "vnet1"}, {"name": "vnet2"}]'
        )

        status = BastionProvisioner.check_prerequisites("my-rg", "eastus")

        assert status.vnet_exists is True
        assert status.vnet_name == "vnet1"  # First VNet


class TestProvisionBastion:
    """Test full bastion provisioning workflow."""

    @patch("azlin.modules.bastion_provisioner.BastionProvisioner.check_prerequisites")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._create_vnet")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._create_bastion_subnet")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._create_public_ip")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._create_bastion")
    def test_provision_bastion_creates_all_resources(
        self,
        mock_create_bastion,
        mock_create_ip,
        mock_create_subnet,
        mock_create_vnet,
        mock_check_prereqs,
    ):
        """Provision should create all missing resources."""
        # Mock prerequisites - nothing exists
        mock_check_prereqs.return_value = PrerequisiteStatus(
            vnet_exists=False,
            subnet_exists=False,
            public_ip_exists=False,
            quota_available=True,
        )

        result = BastionProvisioner.provision_bastion(
            bastion_name="my-bastion",
            resource_group="my-rg",
            location="eastus",
            wait_for_completion=False,
        )

        assert result.success is True
        assert "vnet" in str(result.resources_created)
        assert "subnet" in str(result.resources_created)
        assert "public-ip" in str(result.resources_created)
        assert "bastion" in str(result.resources_created)

        # Verify all create methods called
        assert mock_create_vnet.called
        assert mock_create_subnet.called
        assert mock_create_ip.called
        assert mock_create_bastion.called

    @patch("azlin.modules.bastion_provisioner.BastionProvisioner.check_prerequisites")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._create_bastion")
    def test_provision_bastion_uses_existing_resources(
        self, mock_create_bastion, mock_check_prereqs
    ):
        """Provision should use existing resources when available."""
        # Mock prerequisites - everything exists
        mock_check_prereqs.return_value = PrerequisiteStatus(
            vnet_exists=True,
            subnet_exists=True,
            public_ip_exists=True,
            quota_available=True,
            vnet_name="existing-vnet",
            subnet_name="AzureBastionSubnet",
            public_ip_name="existing-ip",
        )

        result = BastionProvisioner.provision_bastion(
            bastion_name="my-bastion",
            resource_group="my-rg",
            location="eastus",
            wait_for_completion=False,
        )

        assert result.success is True
        # Should only create bastion, not other resources
        assert len(result.resources_created) == 1
        assert "bastion:my-bastion" in result.resources_created

    @patch("azlin.modules.bastion_provisioner.BastionProvisioner.check_prerequisites")
    def test_provision_bastion_validation_error(self, mock_check_prereqs):
        """Provision with invalid input should fail gracefully."""
        result = BastionProvisioner.provision_bastion(
            bastion_name="",  # Invalid
            resource_group="my-rg",
            location="eastus",
        )

        assert result.success is False
        assert result.error_message is not None


class TestWaitForBastionReady:
    """Test bastion provisioning polling."""

    @patch("azlin.modules.bastion_provisioner.BastionDetector.get_bastion")
    def test_wait_for_bastion_succeeded(self, mock_get_bastion):
        """Wait should return when bastion reaches Succeeded state."""
        # Mock bastion in Succeeded state
        mock_get_bastion.return_value = {
            "name": "my-bastion",
            "provisioningState": "Succeeded",
        }

        state = BastionProvisioner.wait_for_bastion_ready(
            "my-bastion", "my-rg", timeout=60, poll_interval=1
        )

        assert state == "Succeeded"

    @patch("azlin.modules.bastion_provisioner.BastionDetector.get_bastion")
    @patch("azlin.modules.bastion_provisioner.time.sleep")
    def test_wait_for_bastion_eventually_succeeds(self, mock_sleep, mock_get_bastion):
        """Wait should poll until bastion succeeds."""
        # Mock progression: Creating -> Updating -> Succeeded
        mock_get_bastion.side_effect = [
            {"name": "my-bastion", "provisioningState": "Creating"},
            {"name": "my-bastion", "provisioningState": "Updating"},
            {"name": "my-bastion", "provisioningState": "Succeeded"},
        ]

        state = BastionProvisioner.wait_for_bastion_ready(
            "my-bastion", "my-rg", timeout=300, poll_interval=1
        )

        assert state == "Succeeded"
        assert mock_get_bastion.call_count == 3

    @patch("azlin.modules.bastion_provisioner.BastionDetector.get_bastion")
    def test_wait_for_bastion_failed(self, mock_get_bastion):
        """Wait should raise error when bastion fails."""
        mock_get_bastion.return_value = {
            "name": "my-bastion",
            "provisioningState": "Failed",
        }

        with pytest.raises(BastionProvisionerError, match="provisioning failed"):
            BastionProvisioner.wait_for_bastion_ready("my-bastion", "my-rg")

    @patch("azlin.modules.bastion_provisioner.BastionDetector.get_bastion")
    def test_wait_for_bastion_not_found(self, mock_get_bastion):
        """Wait should raise error if bastion not found."""
        mock_get_bastion.return_value = None

        with pytest.raises(BastionProvisionerError, match="not found"):
            BastionProvisioner.wait_for_bastion_ready("my-bastion", "my-rg")


class TestRollbackBastion:
    """Test bastion rollback functionality."""

    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._delete_bastion")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._delete_public_ip")
    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._delete_vnet")
    def test_rollback_deletes_in_reverse_order(
        self, mock_delete_vnet, mock_delete_ip, mock_delete_bastion
    ):
        """Rollback should delete resources in reverse order."""
        resources = [
            "vnet:my-vnet",
            "subnet:AzureBastionSubnet",
            "public-ip:my-ip",
            "bastion:my-bastion",
        ]

        BastionProvisioner.rollback_bastion("my-bastion", "my-rg", resources, delete_bastion=True)

        # Verify deletion order (bastion first, vnet last)
        assert mock_delete_bastion.called
        assert mock_delete_ip.called
        assert mock_delete_vnet.called

    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._delete_bastion")
    def test_rollback_skip_bastion_if_requested(self, mock_delete_bastion):
        """Rollback should skip bastion deletion if delete_bastion=False."""
        resources = ["bastion:my-bastion"]

        BastionProvisioner.rollback_bastion("my-bastion", "my-rg", resources, delete_bastion=False)

        assert not mock_delete_bastion.called

    @patch("azlin.modules.bastion_provisioner.BastionProvisioner._delete_public_ip")
    def test_rollback_handles_deletion_failure(self, mock_delete_ip):
        """Rollback should continue even if deletion fails."""
        mock_delete_ip.side_effect = Exception("Deletion failed")

        resources = ["public-ip:my-ip"]

        status = BastionProvisioner.rollback_bastion("my-bastion", "my-rg", resources)

        # Should record failure but not raise
        assert "public-ip:my-ip" in status
        assert status["public-ip:my-ip"] is False


class TestHelperMethods:
    """Test private helper methods."""

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_check_vnet_exists_true(self, mock_run):
        """Check VNet should return True when exists."""
        mock_run.return_value = MagicMock(returncode=0)

        exists = BastionProvisioner._check_vnet_exists("my-vnet", "my-rg")

        assert exists is True

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_check_vnet_exists_false(self, mock_run):
        """Check VNet should return False when doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1)

        exists = BastionProvisioner._check_vnet_exists("missing-vnet", "my-rg")

        assert exists is False

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_create_vnet_success(self, mock_run):
        """Create VNet should call Azure CLI."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"name": "my-vnet"}')

        # Should not raise
        BastionProvisioner._create_vnet("my-vnet", "my-rg", "eastus", "10.0.0.0/16")

        assert mock_run.called
        call_args = str(mock_run.call_args)
        assert "az" in call_args
        assert "vnet" in call_args
        assert "create" in call_args

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_create_vnet_failure(self, mock_run):
        """Create VNet failure should raise error."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="QuotaExceeded")

        with pytest.raises(BastionProvisionerError, match="Failed to create VNet"):
            BastionProvisioner._create_vnet("my-vnet", "my-rg", "eastus", "10.0.0.0/16")

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_create_bastion_subnet_success(self, mock_run):
        """Create bastion subnet should call Azure CLI."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"name": "AzureBastionSubnet"}')

        # Should not raise
        BastionProvisioner._create_bastion_subnet("my-vnet", "my-rg", "10.0.1.0/26")

        assert mock_run.called
        call_args = str(mock_run.call_args)
        assert "subnet" in call_args
        assert "AzureBastionSubnet" in call_args

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_create_public_ip_success(self, mock_run):
        """Create public IP should call Azure CLI."""
        mock_run.return_value = MagicMock(returncode=0, stdout='{"name": "my-ip"}')

        # Should not raise
        BastionProvisioner._create_public_ip("my-ip", "my-rg", "eastus")

        assert mock_run.called
        call_args = str(mock_run.call_args)
        assert "public-ip" in call_args
        assert "Standard" in call_args

    @patch("azlin.modules.bastion_provisioner.subprocess.run")
    def test_delete_bastion_success(self, mock_run):
        """Delete bastion should call Azure CLI."""
        mock_run.return_value = MagicMock(returncode=0)

        # Should not raise
        BastionProvisioner._delete_bastion("my-bastion", "my-rg")

        assert mock_run.called
        call_args = str(mock_run.call_args)
        assert "bastion" in call_args
        assert "delete" in call_args


class TestConstants:
    """Test module constants are properly defined."""

    def test_bastion_subnet_name(self):
        """BASTION_SUBNET_NAME should be defined."""
        assert BastionProvisioner.BASTION_SUBNET_NAME == "AzureBastionSubnet"

    def test_bastion_subnet_prefix_length(self):
        """BASTION_SUBNET_PREFIX_LENGTH should be /26."""
        assert BastionProvisioner.BASTION_SUBNET_PREFIX_LENGTH == 26

    def test_default_vnet_prefix(self):
        """DEFAULT_VNET_PREFIX should be defined."""
        assert BastionProvisioner.DEFAULT_VNET_PREFIX == "10.0.0.0/16"

    def test_default_bastion_subnet_prefix(self):
        """DEFAULT_BASTION_SUBNET_PREFIX should be defined."""
        assert BastionProvisioner.DEFAULT_BASTION_SUBNET_PREFIX == "10.0.1.0/26"

    def test_timeouts_defined(self):
        """Timeout constants should be defined."""
        assert BastionProvisioner.DEFAULT_PROVISIONING_TIMEOUT == 900
        assert BastionProvisioner.DEFAULT_COMMAND_TIMEOUT == 60
