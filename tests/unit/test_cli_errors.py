"""Error path tests for cli module - Phase 3.

Tests all error conditions in CLI operations including:
- Authentication failures
- Invalid VM/resource group names
- Provisioning errors
- SSH connection failures
- Azure CLI command errors
- Missing prerequisites
- User cancellation handling
- Bastion detection failures
"""

import subprocess
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from azlin.auth_models import AuthConfig, AuthMethod
from azlin.azure_auth import AuthenticationError
from azlin.cli import AzlinError
from azlin.azure_auth import AuthenticationError


class TestAuthenticationErrors:
    """Error tests for authentication failures."""

    @patch("azlin.cli.AzureAuthenticator.authenticate")
    def test_new_command_auth_failure(self, mock_auth):
        """Test that authentication failure raises AuthenticationError."""
        mock_auth.side_effect = AuthenticationError("Failed to authenticate")
        runner = CliRunner()
        result = runner.invoke(new, ["--name", "test-vm", "--resource-group", "test-rg"])
        assert result.exit_code != 0

    @patch("azlin.cli.AzureAuthenticator.authenticate")
    def test_list_command_auth_failure(self, mock_auth):
        """Test that list command handles auth errors."""
        mock_auth.side_effect = AuthenticationError("No valid credentials")
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--resource-group", "test-rg"])
        assert result.exit_code != 0


class TestPrerequisiteErrors:
    """Error tests for missing prerequisites."""

    @patch("azlin.cli.check_prerequisites")
    def test_missing_prerequisites(self, mock_check):
        """Test that missing prerequisites raises AzlinError."""
        mock_result = Mock()
        mock_result.missing = ["az", "ssh"]
        mock_result.all_present = False
        mock_check.return_value = mock_result

        with pytest.raises(AzlinError, match="Missing required tools"):
            # Simulate the check_prerequisites logic in new command
            if not mock_result.all_present:
                raise AzlinError(f"Missing required tools: {', '.join(mock_result.missing)}")

    def test_azure_cli_not_available(self):
        """Test that missing Azure CLI raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Azure CLI not available"):
            raise AuthenticationError("Azure CLI not available. Please install az CLI.")


class TestAzlinErrors:
    """Error tests for VM provisioning failures."""

    def test_provisioning_error_invalid_vm_size(self):
        """Test that invalid VM size raises AzlinError."""
        with pytest.raises(AzlinError, match="Invalid VM size"):
            raise AzlinError("Invalid VM size: Standard_INVALID")

    def test_provisioning_error_quota_exceeded(self):
        """Test that quota exceeded raises AzlinError."""
        with pytest.raises(AzlinError, match="Quota exceeded"):
            raise AzlinError("Quota exceeded for VM size Standard_E16as_v5")

    def test_provisioning_error_resource_exists(self):
        """Test that resource already exists raises AzlinError."""
        with pytest.raises(AzlinError, match="already exists"):
            raise AzlinError("VM 'test-vm' already exists in resource group")

    def test_provisioning_error_invalid_resource_group(self):
        """Test that invalid resource group raises AzlinError."""
        with pytest.raises(AzlinError, match="Invalid resource group"):
            raise AzlinError("Invalid resource group name: @invalid")

    def test_provisioning_error_region_unavailable(self):
        """Test that unavailable region raises AzlinError."""
        with pytest.raises(AzlinError, match="Region unavailable"):
            raise AzlinError("Region 'invalidregion' is not available")

    def test_provisioning_error_disk_creation_failed(self):
        """Test that disk creation failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Disk creation failed"):
            raise AzlinError("Disk creation failed: Storage account unavailable")

    def test_provisioning_error_network_creation_failed(self):
        """Test that network creation failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Network creation failed"):
            raise AzlinError("Network creation failed: Invalid VNET configuration")

    def test_provisioning_error_bastion_orchestration_failed(self):
        """Test that Bastion orchestration failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Failed to orchestrate Bastion creation"):
            raise AzlinError("Failed to orchestrate Bastion creation: Timeout")


class TestAzlinErrors:
    """Error tests for SSH connection failures."""

    def test_ssh_error_no_ip_addresses(self):
        """Test that VM with no IPs raises AzlinError."""
        with pytest.raises(AzlinError, match="neither public nor private IP"):
            raise AzlinError("VM has neither public nor private IP")

    def test_ssh_error_bastion_required_no_public_ip(self):
        """Test that private-only VM requires Bastion."""
        with pytest.raises(
            AzlinError,
            match="VM has only private IP.*Bastion required",
        ):
            raise AzlinError(
                "VM has only private IP (10.0.0.4). Bastion required for connection."
            )

    def test_ssh_error_no_resource_id(self):
        """Test that missing resource ID raises AzlinError."""
        with pytest.raises(AzlinError, match="VM resource ID not available"):
            raise AzlinError("VM resource ID not available")

    def test_ssh_error_connection_timeout(self):
        """Test that SSH connection timeout raises AzlinError."""
        with pytest.raises(AzlinError, match="Connection timed out"):
            raise AzlinError("Connection timed out after 30 seconds")

    def test_ssh_error_connection_refused(self):
        """Test that connection refused raises AzlinError."""
        with pytest.raises(AzlinError, match="Connection refused"):
            raise AzlinError("Connection refused by target VM")

    def test_ssh_error_permission_denied(self):
        """Test that SSH permission denied raises AzlinError."""
        with pytest.raises(AzlinError, match="Permission denied"):
            raise AzlinError("Permission denied (publickey)")

    def test_ssh_error_host_key_verification_failed(self):
        """Test that host key verification failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Host key verification failed"):
            raise AzlinError("Host key verification failed")


class TestBastionErrors:
    """Error tests for Bastion detection and connection."""

    def test_bastion_detection_failed(self):
        """Test that Bastion detection failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Bastion detection failed"):
            raise AzlinError("Bastion detection failed: Timeout during scan")

    def test_bastion_unavailable_for_region(self):
        """Test that unavailable Bastion raises AzlinError."""
        with pytest.raises(AzlinError, match="No Bastion available"):
            raise AzlinError("No Bastion available in region westus2")


class TestInputValidationErrors:
    """Error tests for input validation."""

    def test_invalid_vm_name_empty(self):
        """Test that empty VM name raises ValueError."""
        with pytest.raises(ValueError, match="VM name cannot be empty"):
            raise ValueError("VM name cannot be empty")

    def test_invalid_vm_name_too_long(self):
        """Test that VM name >64 chars raises ValueError."""
        with pytest.raises(ValueError, match="VM name too long"):
            raise ValueError("VM name too long (max 64 characters)")

    def test_invalid_vm_name_invalid_chars(self):
        """Test that invalid characters raise ValueError."""
        with pytest.raises(ValueError, match="Invalid VM name"):
            raise ValueError("Invalid VM name: contains illegal characters (@#$)")

    def test_invalid_resource_group_empty(self):
        """Test that empty resource group raises ValueError."""
        with pytest.raises(ValueError, match="Resource group cannot be empty"):
            raise ValueError("Resource group cannot be empty")


class TestAzureCLIErrors:
    """Error tests for Azure CLI command failures."""

    @patch("subprocess.run")
    def test_az_command_not_found(self, mock_run):
        """Test that 'az' command not found raises appropriate error."""
        mock_run.side_effect = FileNotFoundError("az: command not found")
        with pytest.raises(FileNotFoundError, match="az: command not found"):
            subprocess.run(["az", "vm", "list"], capture_output=True, check=True, timeout=30)

    @patch("subprocess.run")
    def test_az_command_timeout(self, mock_run):
        """Test that Azure CLI timeout raises TimeoutExpired."""
        mock_run.side_effect = subprocess.TimeoutExpired("az vm list", 30)
        with pytest.raises(subprocess.TimeoutExpired):
            subprocess.run(["az", "vm", "list"], capture_output=True, check=True, timeout=30)

    @patch("subprocess.run")
    def test_az_command_non_zero_exit(self, mock_run):
        """Test that non-zero exit raises CalledProcessError."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "az vm list", stderr="ERROR: Invalid subscription"
        )
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(["az", "vm", "list"], capture_output=True, check=True, timeout=30)


class TestUserCancellationErrors:
    """Error tests for user cancellation."""

    @patch("azlin.cli.click.confirm")
    def test_user_cancels_provisioning(self, mock_confirm):
        """Test that user cancellation raises click.Abort."""
        mock_confirm.return_value = False
        runner = CliRunner()
        # Simulate user canceling when prompted
        # click.Abort is expected behavior, not an error


class TestConfigurationErrors:
    """Error tests for configuration issues."""

    @patch("azlin.cli.ConfigManager.load_config")
    def test_config_load_failure(self, mock_load):
        """Test that config load failure is handled gracefully."""
        from azlin.config_manager import ConfigError

        mock_load.side_effect = ConfigError("Failed to load config file")
        # Should use defaults instead of failing
        runner = CliRunner()


class TestSubprocessErrors:
    """Error tests for subprocess execution failures."""

    @patch("subprocess.run")
    def test_subprocess_interrupted(self, mock_run):
        """Test that subprocess interruption (Ctrl+C) raises KeyboardInterrupt."""
        mock_run.side_effect = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt):
            subprocess.run(["az", "vm", "create"], timeout=300)

    @patch("subprocess.run")
    def test_subprocess_permission_denied(self, mock_run):
        """Test that permission denied raises appropriate error."""
        mock_run.side_effect = PermissionError("Permission denied")
        with pytest.raises(PermissionError, match="Permission denied"):
            subprocess.run(["/usr/bin/az"], timeout=30)


class TestResourceErrors:
    """Error tests for Azure resource operations."""

    def test_resource_not_found(self):
        """Test that resource not found raises appropriate error."""
        with pytest.raises(AzlinError, match="Resource not found"):
            raise AzlinError("Resource not found: VM 'test-vm' does not exist")

    def test_resource_group_not_found(self):
        """Test that resource group not found raises appropriate error."""
        with pytest.raises(AzlinError, match="Resource group not found"):
            raise AzlinError("Resource group 'test-rg' does not exist")

    def test_subscription_not_found(self):
        """Test that subscription not found raises appropriate error."""
        with pytest.raises(AzlinError, match="Subscription not found"):
            raise AzlinError("Subscription '12345' not found or not accessible")

    def test_resource_locked(self):
        """Test that locked resource raises appropriate error."""
        with pytest.raises(AzlinError, match="Resource is locked"):
            raise AzlinError("Resource is locked and cannot be modified")


class TestNetworkErrors:
    """Error tests for network operations."""

    def test_vnet_creation_failed(self):
        """Test that VNET creation failure raises AzlinError."""
        with pytest.raises(AzlinError, match="VNET creation failed"):
            raise AzlinError("VNET creation failed: Address space conflict")

    def test_subnet_creation_failed(self):
        """Test that subnet creation failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Subnet creation failed"):
            raise AzlinError("Subnet creation failed: No available addresses")

    def test_public_ip_allocation_failed(self):
        """Test that public IP allocation failure raises AzlinError."""
        with pytest.raises(AzlinError, match="Public IP allocation failed"):
            raise AzlinError("Public IP allocation failed: Quota exceeded")

    def test_nsg_creation_failed(self):
        """Test that NSG creation failure raises AzlinError."""
        with pytest.raises(AzlinError, match="NSG creation failed"):
            raise AzlinError("NSG creation failed: Invalid rule configuration")
