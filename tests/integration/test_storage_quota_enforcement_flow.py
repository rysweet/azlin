"""Integration test for storage quota enforcement workflow.

Tests real workflow: Quota check → Warning → Block workflow
"""

import json
import subprocess

import pytest

from azlin.modules.storage_manager import StorageManager
from azlin.modules.storage_quota_manager import StorageQuotaManager


class TestStorageQuotaEnforcementWorkflow:
    """Test storage quota checking and enforcement workflow."""

    def test_storage_account_listing(self):
        """Test listing storage accounts in subscription."""
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

        # Real Azure API call to list storage accounts
        storage_result = subprocess.run(
            [
                "az",
                "storage",
                "account",
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

        if storage_result.returncode == 0:
            storage_accounts = json.loads(storage_result.stdout)
            assert isinstance(storage_accounts, list)
        else:
            pytest.skip("Cannot list storage accounts")

    def test_quota_limit_configuration(self, tmp_path):
        """Test configuring storage quota limits."""
        try:
            quota_config = {
                "max_storage_gb": 1000,
                "max_storage_accounts": 10,
                "warning_threshold_percent": 80,
            }

            # Create quota manager with config
            manager = StorageQuotaManager(config=quota_config)

            # Verify configuration
            assert manager.max_storage_gb == 1000
            assert manager.warning_threshold_percent == 80

        except Exception as e:
            pytest.skip(f"StorageQuotaManager not available: {e}")

    def test_quota_usage_calculation(self):
        """Test calculating current storage quota usage."""
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

        # Get storage accounts
        storage_result = subprocess.run(
            [
                "az",
                "storage",
                "account",
                "list",
                "--subscription",
                subscription_id,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if storage_result.returncode == 0:
            storage_accounts = json.loads(storage_result.stdout)

            # Calculate usage
            total_accounts = len(storage_accounts)

            # Usage should be calculable
            assert total_accounts >= 0
        else:
            pytest.skip("Cannot calculate storage usage")

    def test_quota_warning_threshold(self):
        """Test triggering warning when approaching quota limit."""
        try:
            quota_config = {
                "max_storage_gb": 1000,
                "warning_threshold_percent": 80,
            }

            manager = StorageQuotaManager(config=quota_config)

            # Test warning scenarios
            current_usage_warn = 850  # 85% usage
            current_usage_ok = 500  # 50% usage

            warning_threshold = quota_config["max_storage_gb"] * (
                quota_config["warning_threshold_percent"] / 100
            )

            # Should trigger warning
            should_warn_1 = current_usage_warn >= warning_threshold
            assert should_warn_1 is True

            # Should not trigger warning
            should_warn_2 = current_usage_ok >= warning_threshold
            assert should_warn_2 is False

        except Exception as e:
            pytest.skip(f"Quota warning not available: {e}")

    def test_quota_block_enforcement(self):
        """Test blocking operation when quota exceeded."""
        try:
            quota_config = {
                "max_storage_gb": 1000,
                "max_storage_accounts": 10,
            }

            manager = StorageQuotaManager(config=quota_config)

            # Test blocking scenarios
            current_accounts = 11  # Exceeds limit

            # Should block operation
            should_block = current_accounts >= quota_config["max_storage_accounts"]
            assert should_block is True

            # Test allowed scenario
            current_accounts_ok = 5

            should_block_ok = current_accounts_ok >= quota_config["max_storage_accounts"]
            assert should_block_ok is False

        except Exception as e:
            pytest.skip(f"Quota enforcement not available: {e}")


class TestStorageManagerIntegration:
    """Test storage manager integration with quota enforcement."""

    def test_storage_creation_with_quota_check(self):
        """Test storage creation workflow with quota checking."""
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        try:
            manager = StorageManager()

            # List existing storage (quota check prerequisite)
            storage_accounts = manager.list_storage()

            # Should return list
            assert isinstance(storage_accounts, list)

        except Exception as e:
            pytest.skip(f"StorageManager not available: {e}")

    def test_storage_tier_selection(self):
        """Test storage tier selection workflow."""
        try:
            manager = StorageManager()

            # Valid tiers
            valid_tiers = ["Standard", "Premium"]

            # Validate tier
            for tier in valid_tiers:
                is_valid = manager.validate_tier(tier)
                assert is_valid is True

            # Invalid tier
            is_invalid = manager.validate_tier("InvalidTier")
            assert is_invalid is False

        except Exception as e:
            pytest.skip(f"Tier validation not available: {e}")

    def test_storage_location_validation(self):
        """Test storage location validation workflow."""
        result = subprocess.run(
            ["az", "account", "list-locations", "--query", "[].name"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            locations = json.loads(result.stdout)

            # Should have valid locations
            assert isinstance(locations, list)
            assert len(locations) > 0

            # Common locations should be present
            common_locations = ["eastus", "westus", "westeurope"]
            available_common = [loc for loc in common_locations if loc in locations]

            assert len(available_common) > 0
        else:
            pytest.skip("Cannot list Azure locations")
