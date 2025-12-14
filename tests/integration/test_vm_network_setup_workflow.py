"""Integration test for VM network setup workflow."""

import json
import subprocess

import pytest


class TestVMNetworkSetupWorkflow:
    """Test network security group and VM network setup workflow."""

    def test_nsg_rule_validation(self):
        """Test validating NSG rule configuration."""
        nsg_rule = {
            "name": "AllowSSH",
            "priority": 1000,
            "direction": "Inbound",
            "access": "Allow",
            "protocol": "Tcp",
            "sourceAddressPrefix": "*",
            "sourcePortRange": "*",
            "destinationAddressPrefix": "*",
            "destinationPortRange": "22",
        }

        # Validate required fields
        required = ["name", "priority", "direction", "access", "protocol"]
        for field in required:
            assert field in nsg_rule

        # Validate priority range (100-4096)
        assert 100 <= nsg_rule["priority"] <= 4096

    def test_list_network_security_groups(self):
        """Test listing NSGs in subscription."""
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

        nsg_result = subprocess.run(
            [
                "az",
                "network",
                "nsg",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[].{name:name,resourceGroup:resourceGroup}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if nsg_result.returncode == 0:
            nsgs = json.loads(nsg_result.stdout)
            assert isinstance(nsgs, list)
        else:
            pytest.skip("Cannot list NSGs")
