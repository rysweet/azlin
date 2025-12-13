"""Integration test for cross-region DNS configuration."""

import json
import subprocess

import pytest


class TestCrossRegionDNSWorkflow:
    """Test DNS zone configuration for cross-region access."""

    def test_list_dns_zones(self):
        """Test listing DNS zones in subscription."""
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

        dns_result = subprocess.run(
            [
                "az",
                "network",
                "dns",
                "zone",
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

        if dns_result.returncode == 0:
            zones = json.loads(dns_result.stdout)
            assert isinstance(zones, list)
        else:
            pytest.skip("Cannot list DNS zones")
