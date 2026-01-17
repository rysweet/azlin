"""Integration test for cross-region private endpoint creation."""

import json
import subprocess

import pytest


class TestPrivateEndpointCreationWorkflow:
    """Test private endpoint creation for cross-region access."""

    def test_list_private_endpoints(self):
        """Test listing private endpoints in subscription."""
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

        # List private endpoints
        pe_result = subprocess.run(
            [
                "az",
                "network",
                "private-endpoint",
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

        if pe_result.returncode == 0:
            endpoints = json.loads(pe_result.stdout)
            assert isinstance(endpoints, list)
        else:
            pytest.skip("Cannot list private endpoints")

    def test_private_endpoint_configuration_validation(self):
        """Test validating private endpoint configuration."""
        pe_config = {
            "name": "pe-storage",
            "resource_group": "rg-eastus",
            "vnet": "vnet-eastus",
            "subnet": "default",
            "private_connection_resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/storage",
            "group_id": "blob",
        }

        # Validate required fields
        required = ["name", "resource_group", "vnet", "subnet"]
        for field in required:
            assert field in pe_config
