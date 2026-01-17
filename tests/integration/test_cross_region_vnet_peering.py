"""Integration test for cross-region VNet peering workflow."""

import json
import subprocess

import pytest


class TestCrossRegionVNetPeeringWorkflow:
    """Test cross-region VNet peering setup workflow."""

    def test_list_vnets_in_subscription(self):
        """Test listing VNets across all regions."""
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

        # List VNets
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
            assert isinstance(vnets, list)

            # Group by region
            vnets_by_region = {}
            for vnet in vnets:
                region = vnet["location"]
                if region not in vnets_by_region:
                    vnets_by_region[region] = []
                vnets_by_region[region].append(vnet)

            # Should be able to group by region
            assert isinstance(vnets_by_region, dict)
        else:
            pytest.skip("Cannot list VNets")

    def test_vnet_peering_prerequisite_checks(self):
        """Test prerequisite checks for VNet peering."""
        # Prerequisites for peering:
        # 1. VNets must exist
        # 2. VNets must not have overlapping address spaces
        # 3. User must have Network Contributor role

        vnet1_address_space = ["10.0.0.0/16"]
        vnet2_address_space = ["10.1.0.0/16"]
        overlapping_address_space = ["10.0.0.0/16"]

        # Check for overlap (simple check)
        has_overlap = vnet1_address_space == overlapping_address_space
        assert has_overlap is True

        no_overlap = vnet1_address_space != vnet2_address_space
        assert no_overlap is True

    def test_vnet_peering_configuration_validation(self):
        """Test validating VNet peering configuration."""
        peering_config = {
            "name": "peer-eastus-to-westus",
            "vnet1": "/subscriptions/sub-id/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1",
            "vnet2": "/subscriptions/sub-id/resourceGroups/rg2/providers/Microsoft.Network/virtualNetworks/vnet2",
            "allow_forwarded_traffic": True,
            "allow_gateway_transit": False,
            "use_remote_gateways": False,
        }

        # Validate required fields
        required_fields = ["name", "vnet1", "vnet2"]
        for field in required_fields:
            assert field in peering_config

        # Validate boolean fields
        assert isinstance(peering_config["allow_forwarded_traffic"], bool)
