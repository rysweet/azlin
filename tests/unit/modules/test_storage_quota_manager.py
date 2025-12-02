"""Unit tests for StorageQuotaManager module.

Following TDD approach with 60% unit test coverage target.
These tests are designed to FAIL initially and guide implementation.

Philosophy:
- Test behavior at module boundaries
- Mock external dependencies (Azure CLI)
- Focus on quota calculation logic and enforcement
- Fast execution (<100ms per test)
"""

import json
from dataclasses import asdict
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

# Module under test (will fail import initially)
try:
    from azlin.modules.storage_quota_manager import (
        QuotaCheckResult,
        QuotaConfig,
        QuotaStatus,
        StorageQuotaManager,
    )
except ImportError:
    # Expected to fail initially - TDD approach
    pytest.skip("Module not implemented yet", allow_module_level=True)


class TestQuotaConfigDataModel:
    """Test QuotaConfig data model serialization and validation."""

    def test_quota_config_creation(self):
        """Test basic QuotaConfig creation with valid data."""
        config = QuotaConfig(
            scope="vm",
            name="test-vm",
            quota_gb=500,
            created=datetime.now(),
            last_updated=datetime.now(),
        )
        assert config.scope == "vm"
        assert config.name == "test-vm"
        assert config.quota_gb == 500

    def test_quota_config_invalid_scope(self):
        """Test QuotaConfig rejects invalid scope values."""
        with pytest.raises(ValueError, match="Invalid scope"):
            QuotaConfig(
                scope="invalid",  # Should only allow: vm, team, project
                name="test-vm",
                quota_gb=500,
                created=datetime.now(),
                last_updated=datetime.now(),
            )

    def test_quota_config_negative_quota(self):
        """Test QuotaConfig rejects negative quota values."""
        with pytest.raises(ValueError, match="Quota must be positive"):
            QuotaConfig(
                scope="vm",
                name="test-vm",
                quota_gb=-100,
                created=datetime.now(),
                last_updated=datetime.now(),
            )

    def test_quota_config_serialization(self):
        """Test QuotaConfig can be serialized to JSON."""
        config = QuotaConfig(
            scope="team",
            name="azlin-dev-rg",
            quota_gb=2000,
            created=datetime(2025, 12, 1, 10, 0, 0),
            last_updated=datetime(2025, 12, 1, 10, 0, 0),
        )
        config_dict = asdict(config)
        assert config_dict["scope"] == "team"
        assert config_dict["quota_gb"] == 2000


class TestQuotaStatusDataModel:
    """Test QuotaStatus data model calculations."""

    def test_quota_status_creation(self):
        """Test QuotaStatus creation with usage data."""
        config = QuotaConfig(
            scope="vm",
            name="test-vm",
            quota_gb=500,
            created=datetime.now(),
            last_updated=datetime.now(),
        )
        status = QuotaStatus(
            config=config,
            used_gb=387.5,
            available_gb=112.5,
            utilization_percent=77.5,
            storage_accounts=["storage1"],
            disks=["disk1", "disk2"],
            snapshots=["snap1"],
        )
        assert status.used_gb == 387.5
        assert status.utilization_percent == 77.5

    def test_quota_status_utilization_calculation(self):
        """Test utilization percentage is calculated correctly."""
        config = QuotaConfig(
            scope="vm",
            name="test-vm",
            quota_gb=1000,
            created=datetime.now(),
            last_updated=datetime.now(),
        )
        status = QuotaStatus(
            config=config,
            used_gb=750,
            available_gb=250,
            utilization_percent=75.0,
            storage_accounts=[],
            disks=[],
            snapshots=[],
        )
        # Verify calculation: 750 / 1000 * 100 = 75%
        assert abs(status.utilization_percent - 75.0) < 0.01


class TestQuotaCheckResultDataModel:
    """Test QuotaCheckResult data model."""

    def test_quota_check_result_available(self):
        """Test QuotaCheckResult when quota is available."""
        result = QuotaCheckResult(
            available=True,
            current_usage_gb=400,
            quota_gb=500,
            requested_gb=50,
            remaining_after_gb=50,
            message="Quota available: 50 GB remaining after operation",
        )
        assert result.available is True
        assert result.remaining_after_gb == 50

    def test_quota_check_result_exceeded(self):
        """Test QuotaCheckResult when quota would be exceeded."""
        result = QuotaCheckResult(
            available=False,
            current_usage_gb=480,
            quota_gb=500,
            requested_gb=50,
            remaining_after_gb=-30,
            message="Quota exceeded: Would need 530 GB but quota is 500 GB",
        )
        assert result.available is False
        assert result.remaining_after_gb < 0


class TestStorageQuotaManagerSetQuota:
    """Test StorageQuotaManager.set_quota() method."""

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_set_quota_vm_scope(self, mock_path):
        """Test setting VM-level quota."""
        # Mock file operations
        mock_path.return_value.exists.return_value = False
        mock_path.return_value.parent.mkdir = Mock()
        mock_path.return_value.write_text = Mock()

        result = StorageQuotaManager.set_quota(scope="vm", name="my-dev-vm", quota_gb=500)

        assert isinstance(result, QuotaConfig)
        assert result.scope == "vm"
        assert result.name == "my-dev-vm"
        assert result.quota_gb == 500

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_set_quota_team_scope(self, mock_path):
        """Test setting team-level quota (resource group)."""
        mock_path.return_value.exists.return_value = False
        mock_path.return_value.parent.mkdir = Mock()
        mock_path.return_value.write_text = Mock()

        result = StorageQuotaManager.set_quota(
            scope="team", name="azlin-dev-rg", quota_gb=2000, resource_group="azlin-dev-rg"
        )

        assert result.scope == "team"
        assert result.quota_gb == 2000

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_set_quota_project_scope(self, mock_path):
        """Test setting project-level quota (subscription)."""
        mock_path.return_value.exists.return_value = False
        mock_path.return_value.parent.mkdir = Mock()
        mock_path.return_value.write_text = Mock()

        result = StorageQuotaManager.set_quota(scope="project", name="sub-12345", quota_gb=10000)

        assert result.scope == "project"
        assert result.quota_gb == 10000

    def test_set_quota_invalid_scope(self):
        """Test set_quota rejects invalid scope."""
        with pytest.raises(ValueError, match="Invalid scope"):
            StorageQuotaManager.set_quota(scope="invalid", name="test", quota_gb=100)

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_set_quota_creates_config_file(self, mock_path):
        """Test set_quota creates ~/.azlin/quotas.json."""
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = False
        mock_file.parent.mkdir = Mock()
        mock_file.write_text = Mock()

        StorageQuotaManager.set_quota(scope="vm", name="test-vm", quota_gb=500)

        # Verify directory creation
        mock_file.parent.mkdir.assert_called_once()
        # Verify file write
        mock_file.write_text.assert_called_once()

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_set_quota_updates_existing_quota(self, mock_path):
        """Test set_quota updates existing quota for same scope/name."""
        existing_quotas = {"vm": {"test-vm": {"quota_gb": 300, "created": "2025-11-01T10:00:00"}}}

        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = json.dumps(existing_quotas)
        mock_file.write_text = Mock()

        result = StorageQuotaManager.set_quota(
            scope="vm",
            name="test-vm",
            quota_gb=500,  # Update from 300 to 500
        )

        assert result.quota_gb == 500
        # Verify last_updated changed


class TestStorageQuotaManagerGetQuota:
    """Test StorageQuotaManager.get_quota() method."""

    @patch("azlin.modules.storage_quota_manager.Path")
    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    def test_get_quota_vm_scope(self, mock_subprocess, mock_path):
        """Test getting VM-level quota status."""
        # Mock quota config file
        quotas = {
            "vm": {
                "test-vm": {
                    "quota_gb": 500,
                    "created": "2025-12-01T10:00:00",
                    "last_updated": "2025-12-01T10:00:00",
                }
            }
        }
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = json.dumps(quotas)

        # Mock Azure CLI responses (disks, snapshots)
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {"name": "test-vm_OsDisk", "diskSizeGb": 128},
                    {"name": "test-vm_datadisk_0", "diskSizeGb": 256},
                ]
            ),
        )

        status = StorageQuotaManager.get_quota(scope="vm", name="test-vm", resource_group="test-rg")

        assert isinstance(status, QuotaStatus)
        assert status.config.quota_gb == 500
        # Should include disks in usage calculation
        assert status.used_gb > 0

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_get_quota_nonexistent(self, mock_path):
        """Test get_quota raises error for non-existent quota."""
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = False

        with pytest.raises(ValueError, match="No quota configured"):
            StorageQuotaManager.get_quota(
                scope="vm", name="nonexistent-vm", resource_group="test-rg"
            )


class TestStorageQuotaManagerCheckQuota:
    """Test StorageQuotaManager.check_quota() method."""

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.get_quota")
    def test_check_quota_available(self, mock_get_quota):
        """Test check_quota when enough quota is available."""
        mock_status = QuotaStatus(
            config=QuotaConfig(
                scope="vm",
                name="test-vm",
                quota_gb=500,
                created=datetime.now(),
                last_updated=datetime.now(),
            ),
            used_gb=300,
            available_gb=200,
            utilization_percent=60.0,
            storage_accounts=[],
            disks=[],
            snapshots=[],
        )
        mock_get_quota.return_value = mock_status

        result = StorageQuotaManager.check_quota(
            scope="vm", name="test-vm", requested_gb=100, resource_group="test-rg"
        )

        assert result.available is True
        assert result.remaining_after_gb == 100  # 200 - 100

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.get_quota")
    def test_check_quota_exceeded(self, mock_get_quota):
        """Test check_quota when quota would be exceeded."""
        mock_status = QuotaStatus(
            config=QuotaConfig(
                scope="vm",
                name="test-vm",
                quota_gb=500,
                created=datetime.now(),
                last_updated=datetime.now(),
            ),
            used_gb=480,
            available_gb=20,
            utilization_percent=96.0,
            storage_accounts=[],
            disks=[],
            snapshots=[],
        )
        mock_get_quota.return_value = mock_status

        result = StorageQuotaManager.check_quota(
            scope="vm", name="test-vm", requested_gb=50, resource_group="test-rg"
        )

        assert result.available is False
        assert result.remaining_after_gb == -30  # 20 - 50

    @patch("azlin.modules.storage_quota_manager.StorageQuotaManager.get_quota")
    def test_check_quota_exact_match(self, mock_get_quota):
        """Test check_quota when request exactly matches available."""
        mock_status = QuotaStatus(
            config=QuotaConfig(
                scope="vm",
                name="test-vm",
                quota_gb=500,
                created=datetime.now(),
                last_updated=datetime.now(),
            ),
            used_gb=400,
            available_gb=100,
            utilization_percent=80.0,
            storage_accounts=[],
            disks=[],
            snapshots=[],
        )
        mock_get_quota.return_value = mock_status

        result = StorageQuotaManager.check_quota(
            scope="vm", name="test-vm", requested_gb=100, resource_group="test-rg"
        )

        assert result.available is True
        assert result.remaining_after_gb == 0


class TestStorageQuotaManagerUsageCalculation:
    """Test usage calculation across storage accounts, disks, and snapshots."""

    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    @patch("azlin.modules.storage_quota_manager.StorageManager")
    def test_usage_includes_storage_accounts(self, mock_storage_mgr, mock_subprocess):
        """Test usage calculation includes storage account sizes."""
        # Mock storage accounts
        mock_storage_mgr.list_storage.return_value = [Mock(name="storage1", size_gb=100)]

        # Mock disks and snapshots (empty)
        mock_subprocess.return_value = Mock(returncode=0, stdout=json.dumps([]))

        # Usage calculation should include storage accounts
        # This will be called internally by get_quota
        # Test indirectly through integration tests

    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    def test_usage_includes_managed_disks(self, mock_subprocess):
        """Test usage calculation includes managed disk sizes."""
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {"name": "vm_OsDisk", "diskSizeGb": 128},
                    {"name": "vm_datadisk", "diskSizeGb": 256},
                ]
            ),
        )

        # Usage should sum to 384 GB
        # Test through integration

    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    def test_usage_includes_snapshots(self, mock_subprocess):
        """Test usage calculation includes snapshot sizes."""
        # First call: disks
        # Second call: snapshots
        mock_subprocess.side_effect = [
            Mock(returncode=0, stdout=json.dumps([])),
            Mock(
                returncode=0,
                stdout=json.dumps(
                    [{"name": "snap1", "diskSizeGb": 10}, {"name": "snap2", "diskSizeGb": 5}]
                ),
            ),
        ]

        # Usage should include 15 GB from snapshots


class TestStorageQuotaManagerListQuotas:
    """Test StorageQuotaManager.list_quotas() method."""

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_list_quotas_all_scopes(self, mock_path):
        """Test listing quotas across all scopes."""
        quotas = {
            "vm": {
                "vm1": {
                    "quota_gb": 500,
                    "created": "2025-12-01T10:00:00",
                    "last_updated": "2025-12-01T10:00:00",
                },
                "vm2": {
                    "quota_gb": 300,
                    "created": "2025-12-01T11:00:00",
                    "last_updated": "2025-12-01T11:00:00",
                },
            },
            "team": {
                "rg1": {
                    "quota_gb": 2000,
                    "created": "2025-12-01T09:00:00",
                    "last_updated": "2025-12-01T09:00:00",
                }
            },
            "project": {
                "sub1": {
                    "quota_gb": 10000,
                    "created": "2025-12-01T08:00:00",
                    "last_updated": "2025-12-01T08:00:00",
                }
            },
        }

        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = json.dumps(quotas)

        result = StorageQuotaManager.list_quotas()

        # Should return list of QuotaStatus for all quotas
        assert len(result) == 4  # 2 VMs + 1 team + 1 project

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_list_quotas_empty(self, mock_path):
        """Test list_quotas with no configured quotas."""
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = False

        result = StorageQuotaManager.list_quotas()

        assert result == []

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_list_quotas_filtered_by_resource_group(self, mock_path):
        """Test list_quotas filtered to specific resource group."""
        quotas = {
            "vm": {
                "vm1": {
                    "quota_gb": 500,
                    "created": "2025-12-01T10:00:00",
                    "last_updated": "2025-12-01T10:00:00",
                },
            },
            "team": {
                "azlin-dev-rg": {
                    "quota_gb": 2000,
                    "created": "2025-12-01T09:00:00",
                    "last_updated": "2025-12-01T09:00:00",
                },
                "azlin-prod-rg": {
                    "quota_gb": 5000,
                    "created": "2025-12-01T09:00:00",
                    "last_updated": "2025-12-01T09:00:00",
                },
            },
        }

        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = json.dumps(quotas)

        result = StorageQuotaManager.list_quotas(resource_group="azlin-dev-rg")

        # Should only return quotas for azlin-dev-rg
        assert len(result) == 1


class TestStorageQuotaManagerEdgeCases:
    """Test edge cases and error handling."""

    def test_quota_check_with_zero_quota(self):
        """Test quota check behavior with zero quota configured."""
        # Should always fail
        pass

    def test_quota_check_with_negative_requested(self):
        """Test quota check rejects negative requested amounts."""
        with pytest.raises(ValueError, match="Requested amount must be positive"):
            StorageQuotaManager.check_quota(
                scope="vm", name="test-vm", requested_gb=-10, resource_group="test-rg"
            )

    @patch("azlin.modules.storage_quota_manager.subprocess.run")
    def test_usage_calculation_handles_azure_cli_failure(self, mock_subprocess):
        """Test graceful handling when Azure CLI commands fail."""
        mock_subprocess.return_value = Mock(returncode=1, stderr="Azure CLI error")

        # Should handle error gracefully and return 0 for failed resource types
        # Or raise clear error message

    @patch("azlin.modules.storage_quota_manager.Path")
    def test_corrupted_quota_config_file(self, mock_path):
        """Test handling of corrupted quotas.json file."""
        mock_file = MagicMock()
        mock_path.return_value = mock_file
        mock_file.exists.return_value = True
        mock_file.read_text.return_value = "invalid json{{"

        with pytest.raises(ValueError, match="Corrupted quota configuration"):
            StorageQuotaManager.list_quotas()


class TestStorageQuotaManagerPerformance:
    """Test performance characteristics."""

    def test_quota_check_completes_quickly(self):
        """Test quota check completes in <100ms."""
        # Unit tests should be fast
        # This is a reminder to optimize if needed
        pass

    def test_list_quotas_scales_with_many_quotas(self):
        """Test list_quotas performance with 100+ quotas."""
        # Should still be fast even with many quotas
        pass
