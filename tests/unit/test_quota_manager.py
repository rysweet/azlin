"""Unit tests for QuotaManager module.

This module tests VM quota management functionality:
- Fetching regional vCPU quotas from Azure
- Parsing quota API responses
- Handling missing quota data
- Handling API failures
- Caching quota data

All tests should FAIL initially (TDD approach).
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.quota_manager import (
    QuotaInfo,
    QuotaManager,
    QuotaManagerError,
)


class TestQuotaInfo:
    """Tests for QuotaInfo dataclass."""

    def test_quota_info_creation(self):
        """Test creating QuotaInfo with all fields."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=8,
            limit=20,
        )

        assert quota.region == "eastus"
        assert quota.quota_name == "standardDSv3Family"
        assert quota.current_usage == 8
        assert quota.limit == 20

    def test_quota_info_available(self):
        """Test calculating available quota."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=8,
            limit=20,
        )

        assert quota.available() == 12

    def test_quota_info_available_when_full(self):
        """Test available quota when at limit."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=20,
            limit=20,
        )

        assert quota.available() == 0

    def test_quota_info_is_available_with_space(self):
        """Test is_available when quota has space."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=15,
            limit=20,
        )

        assert quota.is_available(vcpus=4) is True

    def test_quota_info_is_available_insufficient(self):
        """Test is_available when insufficient quota."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=18,
            limit=20,
        )

        assert quota.is_available(vcpus=4) is False

    def test_quota_info_is_available_exact(self):
        """Test is_available with exact remaining quota."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=16,
            limit=20,
        )

        assert quota.is_available(vcpus=4) is True

    def test_quota_info_usage_percentage(self):
        """Test calculating usage percentage."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=15,
            limit=20,
        )

        assert quota.usage_percentage() == 75.0

    def test_quota_info_usage_percentage_zero_limit(self):
        """Test usage percentage with zero limit (edge case)."""
        quota = QuotaInfo(
            region="eastus",
            quota_name="standardDSv3Family",
            current_usage=0,
            limit=0,
        )

        assert quota.usage_percentage() == 0.0


@pytest.mark.unit
class TestQuotaManagerGetQuota:
    """Tests for QuotaManager.get_quota method."""

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_success(self, mock_run):
        """Test successful quota retrieval."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 20,
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family")

        assert quota is not None
        assert quota.region == "eastus"
        assert quota.quota_name == "standardDSv3Family"
        assert quota.current_usage == 8
        assert quota.limit == 20

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_subprocess_called_correctly(self, mock_run):
        """Test that subprocess is called with correct Azure CLI command."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 20,
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "az" in call_args
        assert "vm" in call_args
        assert "list-usage" in call_args
        assert "--location" in call_args
        assert "eastus" in call_args

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_api_failure(self, mock_run):
        """Test handling of Azure CLI API failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["az"], stderr="AuthorizationFailed: Insufficient permissions"
        )

        with pytest.raises(QuotaManagerError, match="Failed to fetch quotas"):
            QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_timeout(self, mock_run):
        """Test handling of subprocess timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=30)

        with pytest.raises(QuotaManagerError, match="Quota query timed out"):
            QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_invalid_json(self, mock_run):
        """Test handling of invalid JSON response."""
        mock_run.return_value = Mock(returncode=0, stdout="invalid json {", stderr="")

        with pytest.raises(QuotaManagerError, match="Failed to parse quota response"):
            QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_empty_response(self, mock_run):
        """Test handling of empty response (quota not found)."""
        mock_run.return_value = Mock(returncode=0, stdout="[]", stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="nonexistentQuota")

        assert quota is None

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_missing_fields(self, mock_run):
        """Test handling of response with missing fields."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    # Missing limit and currentValue
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        # Since get_all_quotas skips malformed entries, this returns None
        quota = QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)
        assert quota is None

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_negative_values(self, mock_run):
        """Test handling of negative quota values (edge case)."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": -1,  # Unlimited quota indicated by -1
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

        assert quota is not None
        assert quota.limit == -1
        assert quota.current_usage == 8

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_zero_limit(self, mock_run):
        """Test handling of zero quota limit."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 0,
                    "currentValue": 0,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

        assert quota is not None
        assert quota.limit == 0
        assert quota.current_usage == 0

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_invalid_region(self, mock_run):
        """Test handling of invalid region."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["az"], stderr="InvalidLocation: Location 'invalid-region' not found"
        )

        with pytest.raises(QuotaManagerError, match="Failed to fetch quotas"):
            QuotaManager.get_quota(region="invalid-region", quota_name="standardDSv3Family", use_cache=False)


@pytest.mark.unit
class TestQuotaManagerCache:
    """Tests for QuotaManager caching functionality."""

    @patch("azlin.quota_manager.subprocess.run")
    def test_quota_cached_on_first_call(self, mock_run):
        """Test that quota is cached after first retrieval."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 20,
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        # Clear cache before test
        QuotaManager.clear_cache()

        # First call
        quota1 = QuotaManager.get_quota(
            region="eastus", quota_name="standardDSv3Family", use_cache=True
        )

        # Second call should use cache
        quota2 = QuotaManager.get_quota(
            region="eastus", quota_name="standardDSv3Family", use_cache=True
        )

        # Should only call subprocess once
        assert mock_run.call_count == 1
        assert quota1.current_usage == quota2.current_usage

    @patch("azlin.quota_manager.subprocess.run")
    def test_quota_cache_bypass(self, mock_run):
        """Test bypassing cache with use_cache=False."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 20,
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        # Clear cache before test
        QuotaManager.clear_cache()

        # First call
        QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

        # Second call with cache disabled
        QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=False)

        # Should call subprocess twice
        assert mock_run.call_count == 2

    @patch("azlin.quota_manager.subprocess.run")
    @patch("azlin.quota_manager.time.time")
    def test_quota_cache_expiration(self, mock_time, mock_run):
        """Test that cache expires after TTL."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 20,
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        # Clear cache before test
        QuotaManager.clear_cache()

        # First call at t=0
        mock_time.return_value = 0
        QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=True)

        # Second call at t=301 (past 5-minute TTL)
        mock_time.return_value = 301
        QuotaManager.get_quota(region="eastus", quota_name="standardDSv3Family", use_cache=True)

        # Should call subprocess twice (cache expired)
        assert mock_run.call_count == 2

    def test_clear_cache(self):
        """Test clearing quota cache."""
        # This test verifies the clear_cache method exists and works
        QuotaManager.clear_cache()
        # No exception should be raised


@pytest.mark.unit
class TestQuotaManagerBatchQueries:
    """Tests for querying multiple quotas."""

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_all_quotas_for_region(self, mock_run):
        """Test fetching all quotas for a region."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standardDSv3Family"},
                    "limit": 20,
                    "currentValue": 8,
                },
                {
                    "name": {"value": "standardDv3Family"},
                    "limit": 100,
                    "currentValue": 50,
                },
                {
                    "name": {"value": "cores"},
                    "limit": 200,
                    "currentValue": 58,
                },
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        quotas = QuotaManager.get_all_quotas(region="eastus")

        assert len(quotas) == 3
        assert quotas[0].quota_name == "standardDSv3Family"
        assert quotas[1].quota_name == "standardDv3Family"
        assert quotas[2].quota_name == "cores"

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_all_quotas_empty_region(self, mock_run):
        """Test fetching quotas for region with no quotas."""
        mock_run.return_value = Mock(returncode=0, stdout="[]", stderr="")

        quotas = QuotaManager.get_all_quotas(region="westus")

        assert len(quotas) == 0

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_all_quotas_api_failure(self, mock_run):
        """Test handling API failure when fetching all quotas."""
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["az"], stderr="AuthorizationFailed: Insufficient permissions"
        )

        with pytest.raises(QuotaManagerError, match="Failed to fetch quotas"):
            QuotaManager.get_all_quotas(region="eastus")


@pytest.mark.unit
class TestQuotaManagerEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_with_special_characters(self, mock_run):
        """Test quota name with special characters."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "standard-DSv3-Family"},
                    "limit": 20,
                    "currentValue": 8,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="standard-DSv3-Family")

        assert quota is not None
        assert quota.quota_name == "standard-DSv3-Family"

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_empty_region_name(self, mock_run):
        """Test with empty region name."""
        with pytest.raises(QuotaManagerError, match="Region cannot be empty"):
            QuotaManager.get_quota(region="", quota_name="standardDSv3Family")

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_empty_quota_name(self, mock_run):
        """Test with empty quota name."""
        mock_run.return_value = Mock(returncode=0, stdout="[]", stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="")

        assert quota is None

    @patch("azlin.quota_manager.subprocess.run")
    def test_get_quota_very_large_values(self, mock_run):
        """Test with very large quota values."""
        mock_output = json.dumps(
            [
                {
                    "name": {"value": "cores"},
                    "limit": 1000000,
                    "currentValue": 999999,
                }
            ]
        )
        mock_run.return_value = Mock(returncode=0, stdout=mock_output, stderr="")

        quota = QuotaManager.get_quota(region="eastus", quota_name="cores")

        assert quota is not None
        assert quota.limit == 1000000
        assert quota.current_usage == 999999
        assert quota.available() == 1
