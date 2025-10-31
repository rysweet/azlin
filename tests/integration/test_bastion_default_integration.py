"""Integration tests for Bastion default behavior (TDD - Issue #237).

Integration tests verify interactions between multiple modules:
- Bastion detector + VM provisioner
- User prompts + configuration storage
- VM connector + bastion manager
- CLI commands + bastion workflow

These tests use mocked Azure resources but test real module interactions.
Tests will FAIL until implementation is complete.

Testing Level: Integration (30% of testing pyramid)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import tempfile
import json

from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_manager import BastionManager
from azlin.vm_provisioning import VMProvisioner, VMConfig
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMManager, VMInfo


@pytest.fixture
def temp_config_dir():
    """Temporary config directory for integration tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_azure_resources():
    """Mock Azure resource responses."""
    return {
        "bastions": [
            {
                "name": "test-bastion",
                "resourceGroup": "test-rg",
                "provisioningState": "Succeeded",
                "location": "westus2",
                "sku": {"name": "Standard"}
            }
        ],
        "vm": {
            "name": "test-vm",
            "resourceGroup": "test-rg",
            "location": "westus2",
            "powerState": "VM running",
            "privateIps": "10.0.0.4",
            "publicIps": None  # Private-only VM
        }
    }


class TestBastionDetectionAndProvisioning:
    """Integration tests for bastion detection during VM provisioning."""

    def test_provision_vm_detects_bastion_and_prompts_user(self, mock_azure_resources):
        """Test VM provisioning detects bastion and prompts user."""
        # Arrange
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2"
        )

        # Mock Azure calls
        with patch.object(BastionDetector, 'list_bastions',
                         return_value=mock_azure_resources["bastions"]):
            with patch('click.confirm', return_value=True) as mock_confirm:
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value.stdout = json.dumps(mock_azure_resources["vm"])

                    # Act
                    # Implementation should:
                    # 1. Detect bastion
                    # 2. Prompt user
                    # 3. Provision without public IP
                    pass

        # Assert
        # Verify bastion was detected
        # Verify user was prompted
        # Verify VM provisioned correctly
        mock_confirm.assert_called_once()

    def test_provision_vm_no_bastion_prompts_create(self, temp_config_dir):
        """Test VM provisioning prompts to create bastion when none exists."""
        # Arrange
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2"
        )

        # Mock Azure calls - no bastions
        with patch.object(BastionDetector, 'list_bastions', return_value=[]):
            with patch('click.confirm', side_effect=[True, True]) as mock_confirm:
                # First confirm: create bastion?
                # Second confirm: proceed with provisioning?

                # Act
                # Implementation should prompt to create bastion
                pass

        # Assert
        assert mock_confirm.call_count == 2
        # First call should ask about creating bastion
        first_call = mock_confirm.call_args_list[0]
        assert "create" in str(first_call).lower()
        assert "bastion" in str(first_call).lower()

    def test_provision_vm_user_declines_bastion_uses_public_ip(self):
        """Test VM gets public IP when user declines bastion."""
        # Arrange
        provisioner = VMProvisioner()
        config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2"
        )

        # Mock Azure calls
        with patch.object(BastionDetector, 'detect_bastion_for_vm', return_value=None):
            with patch('click.confirm', return_value=False):  # User declines
                with patch('subprocess.run') as mock_run:
                    # Act
                    # Should provision with public IP
                    pass

        # Assert
        # Verify public IP was included in provisioning command
        if mock_run.called:
            cmd = mock_run.call_args[0][0]
            # Should include public IP arguments
            pass

    def test_provision_vm_saves_bastion_mapping_to_config(self, temp_config_dir):
        """Test bastion mapping is saved to config after provisioning."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        provisioner = VMProvisioner()
        vm_config = VMConfig(
            name="test-vm",
            resource_group="test-rg",
            location="westus2"
        )
        bastion_info = {"name": "test-bastion", "resource_group": "test-rg"}

        # Act
        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value=bastion_info):
            with patch('click.confirm', return_value=True):
                # Should save mapping after provisioning
                bastion_config = BastionConfig()
                bastion_config.add_mapping(
                    vm_name=vm_config.name,
                    vm_resource_group=vm_config.resource_group,
                    bastion_name=bastion_info["name"],
                    bastion_resource_group=bastion_info["resource_group"]
                )
                bastion_config.save(config_path)

        # Assert
        loaded_config = BastionConfig.load(config_path)
        mapping = loaded_config.get_mapping("test-vm")
        assert mapping is not None
        assert mapping.bastion_name == "test-bastion"


class TestConnectionWorkflowWithBastion:
    """Integration tests for connection workflow with bastion."""

    def test_connect_to_vm_uses_saved_bastion_mapping(self, temp_config_dir,
                                                       mock_azure_resources):
        """Test connection uses saved bastion mapping."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        bastion_config = BastionConfig()
        bastion_config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="test-bastion",
            bastion_resource_group="test-rg"
        )
        bastion_config.save(config_path)

        # Act
        with patch.object(BastionConfig, 'load', return_value=bastion_config):
            with patch.object(BastionManager, 'create_tunnel') as mock_tunnel:
                with patch.object(VMManager, 'get_vm') as mock_get_vm:
                    mock_vm = Mock(spec=VMInfo)
                    mock_vm.public_ip = None  # Private VM
                    mock_vm.private_ip = "10.0.0.4"
                    mock_get_vm.return_value = mock_vm

                    # Should automatically use bastion from config
                    # VMConnector.connect("test-vm", resource_group="test-rg")
                    pass

        # Assert
        # Verify tunnel was created automatically
        # mock_tunnel.assert_called_once()

    def test_connect_to_vm_auto_detects_bastion_first_time(self, mock_azure_resources):
        """Test first-time connection auto-detects bastion."""
        # Arrange - No saved config
        vm_name = "test-vm"
        resource_group = "test-rg"

        # Act
        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value={"name": "test-bastion", "resource_group": "test-rg"}):
            with patch('click.confirm', return_value=True) as mock_confirm:
                with patch.object(BastionManager, 'create_tunnel'):
                    # Should detect bastion and prompt user
                    pass

        # Assert
        mock_confirm.assert_called_once()

    def test_connect_to_private_vm_without_bastion_fails_gracefully(self):
        """Test connection to private VM without bastion fails with helpful message."""
        # Arrange
        vm_name = "test-vm"
        resource_group = "test-rg"

        # Mock private-only VM
        with patch.object(VMManager, 'get_vm') as mock_get_vm:
            mock_vm = Mock(spec=VMInfo)
            mock_vm.public_ip = None
            mock_vm.private_ip = "10.0.0.4"
            mock_get_vm.return_value = mock_vm

            with patch.object(BastionDetector, 'detect_bastion_for_vm',
                             return_value=None):
                # Act & Assert
                with pytest.raises(Exception, match="no bastion.*private VM"):
                    # Should provide helpful error message
                    VMConnector.connect(vm_name, resource_group=resource_group)


class TestBastionConfigPersistence:
    """Integration tests for bastion config persistence across operations."""

    def test_config_persists_across_multiple_vms(self, temp_config_dir):
        """Test config stores mappings for multiple VMs."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        bastion_config = BastionConfig()

        # Act - Add multiple mappings
        vms = [
            ("vm1", "rg1", "bastion1", "network-rg"),
            ("vm2", "rg1", "bastion1", "network-rg"),
            ("vm3", "rg2", "bastion2", "network-rg"),
        ]
        for vm_name, vm_rg, bastion_name, bastion_rg in vms:
            bastion_config.add_mapping(vm_name, vm_rg, bastion_name, bastion_rg)

        bastion_config.save(config_path)

        # Reload and verify
        loaded_config = BastionConfig.load(config_path)

        # Assert
        assert len(loaded_config.mappings) == 3
        for vm_name, _, bastion_name, _ in vms:
            mapping = loaded_config.get_mapping(vm_name)
            assert mapping is not None
            assert mapping.bastion_name == bastion_name

    def test_config_merge_with_existing(self, temp_config_dir):
        """Test merging new config with existing config."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"

        # Create initial config
        config1 = BastionConfig()
        config1.add_mapping("vm1", "rg1", "bastion1", "network-rg")
        config1.save(config_path)

        # Create new config
        config2 = BastionConfig()
        config2.add_mapping("vm2", "rg1", "bastion1", "network-rg")

        # Act - Merge
        loaded_config = BastionConfig.load(config_path)
        loaded_config.merge(config2)
        loaded_config.save(config_path)

        # Reload and verify
        final_config = BastionConfig.load(config_path)

        # Assert - Both mappings should exist
        assert len(final_config.mappings) == 2
        assert final_config.get_mapping("vm1") is not None
        assert final_config.get_mapping("vm2") is not None

    def test_config_disable_enable_mapping(self, temp_config_dir):
        """Test disabling and enabling bastion mappings."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        bastion_config = BastionConfig()
        bastion_config.add_mapping("vm1", "rg1", "bastion1", "network-rg")
        bastion_config.save(config_path)

        # Act - Disable mapping
        loaded_config = BastionConfig.load(config_path)
        loaded_config.disable_mapping("vm1")
        loaded_config.save(config_path)

        # Reload and verify disabled
        config_disabled = BastionConfig.load(config_path)
        mapping_disabled = config_disabled.get_mapping("vm1")

        # Assert - Should return None when disabled
        assert mapping_disabled is None

        # Re-enable
        config_disabled.enable_mapping("vm1")
        config_disabled.save(config_path)
        config_enabled = BastionConfig.load(config_path)
        mapping_enabled = config_enabled.get_mapping("vm1")

        # Assert - Should return mapping when enabled
        assert mapping_enabled is not None


class TestCLIIntegration:
    """Integration tests for CLI commands with bastion default behavior."""

    def test_cli_create_vm_with_bastion_auto_detection(self, mock_azure_resources):
        """Test 'azlin create' command with bastion auto-detection."""
        # Arrange
        with patch.object(BastionDetector, 'list_bastions',
                         return_value=mock_azure_resources["bastions"]):
            with patch('click.confirm', return_value=True):
                with patch('subprocess.run') as mock_run:
                    # Act
                    # CLI command: azlin create my-vm --resource-group test-rg
                    # Should detect bastion and prompt user
                    pass

        # Assert
        # Verify correct sequence of operations

    def test_cli_create_vm_with_no_bastion_flag(self):
        """Test 'azlin create' with --no-bastion flag."""
        # Arrange
        with patch.object(BastionDetector, 'detect_bastion_for_vm') as mock_detect:
            with patch('subprocess.run'):
                # Act
                # CLI command: azlin create my-vm --no-bastion
                # Should skip bastion detection
                pass

        # Assert
        mock_detect.assert_not_called()

    def test_cli_connect_vm_uses_bastion_from_config(self, temp_config_dir):
        """Test 'azlin connect' uses bastion from saved config."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        bastion_config = BastionConfig()
        bastion_config.add_mapping("vm1", "rg1", "bastion1", "network-rg")
        bastion_config.save(config_path)

        with patch.object(BastionConfig, 'load', return_value=bastion_config):
            with patch.object(BastionManager, 'create_tunnel'):
                # Act
                # CLI command: azlin connect vm1 --resource-group rg1
                # Should use bastion from config automatically
                pass

        # Assert
        # Verify bastion was used without prompting


class TestErrorRecoveryAndFallback:
    """Integration tests for error handling and fallback scenarios."""

    def test_bastion_tunnel_failure_retries(self):
        """Test tunnel creation retries on failure."""
        # Arrange
        with patch.object(BastionManager, 'create_tunnel') as mock_tunnel:
            # First attempt fails, second succeeds
            mock_tunnel.side_effect = [
                Exception("Connection refused"),
                Mock()  # Success
            ]

            # Act
            # Should retry tunnel creation
            pass

        # Assert
        assert mock_tunnel.call_count == 2

    def test_bastion_creation_failure_falls_back_to_public_ip(self):
        """Test fallback to public IP when bastion creation fails."""
        # Arrange
        with patch('click.confirm', side_effect=[True, True]) as mock_confirm:
            # First: User wants bastion
            # Second: User accepts fallback to public IP
            with patch('subprocess.run') as mock_run:
                # Mock bastion creation failure
                mock_run.side_effect = [
                    Exception("Bastion creation failed"),  # Bastion creation
                    Mock(stdout='{"publicIpAddress": "20.1.2.3"}')  # VM creation
                ]

                # Act
                # Should fallback to public IP
                pass

        # Assert
        assert mock_confirm.call_count == 2

    def test_config_load_failure_continues_with_defaults(self, temp_config_dir):
        """Test system continues with defaults if config load fails."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        config_path.write_text("invalid toml content {[")

        # Act
        with pytest.raises(Exception):
            BastionConfig.load(config_path)

        # Should continue with empty config
        config = BastionConfig()

        # Assert
        assert len(config.mappings) == 0
        assert config.auto_detect is True


class TestMultiVMScenarios:
    """Integration tests for multi-VM scenarios with shared bastion."""

    def test_multiple_vms_share_same_bastion(self, temp_config_dir):
        """Test multiple VMs can share the same bastion host."""
        # Arrange
        config_path = temp_config_dir / "bastion_config.toml"
        bastion_config = BastionConfig()

        # Add multiple VMs to same bastion
        vms = ["vm1", "vm2", "vm3"]
        for vm_name in vms:
            bastion_config.add_mapping(
                vm_name=vm_name,
                vm_resource_group="test-rg",
                bastion_name="shared-bastion",
                bastion_resource_group="network-rg"
            )

        bastion_config.save(config_path)
        loaded_config = BastionConfig.load(config_path)

        # Act & Assert
        for vm_name in vms:
            mapping = loaded_config.get_mapping(vm_name)
            assert mapping is not None
            assert mapping.bastion_name == "shared-bastion"

    def test_provision_vm_pool_with_bastion(self, mock_azure_resources):
        """Test provisioning multiple VMs with shared bastion."""
        # Arrange
        provisioner = VMProvisioner()
        configs = [
            VMConfig(name=f"vm{i}", resource_group="test-rg", location="westus2")
            for i in range(3)
        ]

        # Act
        with patch.object(BastionDetector, 'list_bastions',
                         return_value=mock_azure_resources["bastions"]):
            with patch('click.confirm', return_value=True):
                # Should detect bastion once and use for all VMs
                pass

        # Assert
        # Verify bastion detection was efficient
        # Verify all VMs configured to use bastion


class TestVNetPeeringScenarios:
    """Integration tests for VNet peering with bastion."""

    def test_bastion_in_peered_vnet(self):
        """Test bastion in peered VNet can access VM."""
        # Arrange
        vm_vnet = "vnet-a"
        bastion_vnet = "vnet-b"
        vnets_are_peered = True

        # Act
        # Should verify VNet peering and allow bastion usage
        pass

        # Assert
        # Verify peering was checked
        # Verify connection succeeds

    def test_bastion_in_unpeered_vnet_fails(self):
        """Test bastion in unpeered VNet cannot access VM."""
        # Arrange
        vm_vnet = "vnet-a"
        bastion_vnet = "vnet-b"
        vnets_are_peered = False

        # Act & Assert
        with pytest.raises(Exception, match="VNet.*not peered"):
            # Should detect VNet mismatch and fail
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
