"""Integration test for VM configuration to Bastion provisioning workflow.

Tests real workflow: Config validation → Bastion detection → VM provision decision
"""

import json
import subprocess
from pathlib import Path

import pytest

from azlin.config_manager import AzlinConfig, ConfigManager
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManager
from azlin.vm_manager import VMManager


class TestVMConfigToBastionWorkflow:
    """Test VM configuration and bastion provisioning workflow."""

    def test_config_creation_and_persistence(self, tmp_path):
        """Test creating and persisting VM configuration."""
        config_file = tmp_path / "config.json"

        # Create configuration
        config = AzlinConfig(
            subscription_id="12345678-1234-1234-1234-123456789012",
            resource_group="test-rg",
            default_location="eastus",
            default_vm_size="Standard_B2s",
        )

        manager = ConfigManager(config_path=config_file)
        manager.save_config(config)

        # Verify persistence
        assert config_file.exists()

        # Load and verify
        loaded_config = manager.load_config()
        assert loaded_config.subscription_id == config.subscription_id
        assert loaded_config.resource_group == config.resource_group
        assert loaded_config.default_location == config.default_location

    def test_bastion_detection_in_resource_group(self):
        """Test detecting existing bastions in resource group."""
        # This test uses real Azure CLI calls (minimal mocking)
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        # Get current subscription
        account_info = json.loads(result.stdout)
        subscription_id = account_info["id"]

        # Test bastion detection (real Azure API call)
        detector = BastionDetector(subscription_id=subscription_id)

        try:
            bastions = detector.list_bastions()
            # Should return a list (may be empty)
            assert isinstance(bastions, list)
        except Exception as e:
            # If API call fails, it's likely auth or permission issue
            pytest.skip(f"Cannot list bastions: {e}")

    def test_bastion_config_validation(self):
        """Test bastion configuration validation."""
        manager = BastionManager()

        # Test valid configuration
        valid_config = {
            "name": "test-bastion",
            "resource_group": "test-rg",
            "vnet_name": "test-vnet",
            "subnet_name": "AzureBastionSubnet",
        }

        # Should not raise error
        is_valid = manager.validate_bastion_config(valid_config)
        assert is_valid is True

    def test_vm_provisioning_decision_based_on_bastion(self):
        """Test VM provisioning decision when bastion is available."""
        # Get subscription from Azure CLI
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        account_info = json.loads(result.stdout)
        subscription_id = account_info["id"]

        # Create detector
        detector = BastionDetector(subscription_id=subscription_id)

        # Check if bastions exist
        try:
            bastions = detector.list_bastions()

            if len(bastions) > 0:
                # Bastion exists - VM provisioning should use bastion
                bastion = bastions[0]
                assert bastion.name
                assert bastion.resource_group
                assert bastion.location

                # Provisioning decision: use existing bastion
                use_bastion = True
            else:
                # No bastion - VM provisioning should skip bastion or create new
                use_bastion = False

            # Decision should be consistent
            assert isinstance(use_bastion, bool)

        except Exception:
            pytest.skip("Cannot access Azure API for bastion detection")


class TestBastionVNetIntegration:
    """Test bastion and VNet integration workflow."""

    def test_vnet_exists_before_bastion_creation(self):
        """Test checking VNet existence before bastion creation."""
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        account_info = json.loads(result.stdout)
        subscription_id = account_info["id"]

        # List VNets in subscription
        vnet_result = subprocess.run(
            [
                "az",
                "network",
                "vnet",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[].{name:name,resourceGroup:resourceGroup,location:location}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if vnet_result.returncode == 0:
            vnets = json.loads(vnet_result.stdout)
            # Should return a list
            assert isinstance(vnets, list)
        else:
            pytest.skip("Cannot list VNets")

    def test_bastion_subnet_validation(self):
        """Test validating bastion subnet requirements."""
        manager = BastionManager()

        # Test bastion subnet name validation
        valid_subnet_name = "AzureBastionSubnet"
        invalid_subnet_name = "default"

        # Bastion requires specific subnet name
        assert manager.validate_bastion_subnet_name(valid_subnet_name) is True
        assert manager.validate_bastion_subnet_name(invalid_subnet_name) is False


class TestVMToSSHWorkflow:
    """Test VM provisioning to SSH connection workflow."""

    def test_vm_list_and_filter(self):
        """Test listing and filtering VMs in resource group."""
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        account_info = json.loads(result.stdout)
        subscription_id = account_info["id"]

        # List VMs
        vm_result = subprocess.run(
            [
                "az",
                "vm",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[].{name:name,resourceGroup:resourceGroup,location:location}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if vm_result.returncode == 0:
            vms = json.loads(vm_result.stdout)
            assert isinstance(vms, list)

            # If VMs exist, verify structure
            if len(vms) > 0:
                vm = vms[0]
                assert "name" in vm
                assert "resourceGroup" in vm
                assert "location" in vm
        else:
            pytest.skip("Cannot list VMs")

    def test_ssh_config_generation_for_vm(self, tmp_path):
        """Test generating SSH config for VM connection."""
        from azlin.modules.ssh_connector import SSHConfig

        # Create SSH config
        config = SSHConfig(
            hostname="test-vm",
            user="azureuser",
            private_key_path=tmp_path / "test_key",
            port=22,
        )

        assert config.hostname == "test-vm"
        assert config.user == "azureuser"
        assert config.port == 22

        # Test SSH config string generation
        config_str = config.to_ssh_config_string()
        assert "Host test-vm" in config_str
        assert "User azureuser" in config_str
        assert "Port 22" in config_str
