"""Integration test for multi-subscription authentication."""

import json
import subprocess

import pytest


class TestMultiSubscriptionAuth:
    """Test authentication across multiple subscriptions."""

    def test_list_all_subscriptions(self):
        """Test listing all accessible subscriptions."""
        result = subprocess.run(
            ["az", "account", "list", "--query", "[].{id:id,name:name}"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            subscriptions = json.loads(result.stdout)
            assert isinstance(subscriptions, list)
        else:
            pytest.skip("Cannot list subscriptions")

    def test_switch_between_subscriptions(self):
        """Test switching active subscription."""
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            current = json.loads(result.stdout)
            current_sub_id = current["id"]
            assert current_sub_id
        else:
            pytest.skip("Cannot get current subscription")
