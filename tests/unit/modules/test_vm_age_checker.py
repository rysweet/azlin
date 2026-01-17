"""Unit tests for vm_age_checker module.

Tests cover:
- Input validation edge cases
- Cache behavior and TTL logic
- Fail-safe behavior
- Error handling
- Thread safety
"""

import json
import subprocess
import threading
import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from azlin.modules.vm_age_checker import VMAgeChecker


class TestValidateInputs:
    """Test input validation."""

    def test_empty_vm_name_raises_error(self):
        """Test empty VM name raises ValueError."""
        with pytest.raises(ValueError, match="VM name cannot be empty"):
            VMAgeChecker._validate_inputs("", "test-rg")

    def test_whitespace_vm_name_raises_error(self):
        """Test whitespace-only VM name raises ValueError."""
        with pytest.raises(ValueError, match="VM name cannot be empty"):
            VMAgeChecker._validate_inputs("   ", "test-rg")

    def test_empty_resource_group_raises_error(self):
        """Test empty resource group raises ValueError."""
        with pytest.raises(ValueError, match="Resource group cannot be empty"):
            VMAgeChecker._validate_inputs("test-vm", "")

    def test_whitespace_resource_group_raises_error(self):
        """Test whitespace-only resource group raises ValueError."""
        with pytest.raises(ValueError, match="Resource group cannot be empty"):
            VMAgeChecker._validate_inputs("test-vm", "   ")

    def test_invalid_vm_name_format_raises_error(self):
        """Test invalid VM name format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid VM name format"):
            VMAgeChecker._validate_inputs("vm@invalid!", "test-rg")

    def test_vm_name_too_long_raises_error(self):
        """Test VM name exceeding 64 chars raises ValueError."""
        long_name = "a" * 65
        with pytest.raises(ValueError, match="Invalid VM name format"):
            VMAgeChecker._validate_inputs(long_name, "test-rg")

    def test_invalid_resource_group_format_raises_error(self):
        """Test invalid resource group format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid resource group format"):
            VMAgeChecker._validate_inputs("test-vm", "rg@invalid!")

    def test_resource_group_too_long_raises_error(self):
        """Test resource group exceeding 90 chars raises ValueError."""
        long_rg = "a" * 91
        with pytest.raises(ValueError, match="Invalid resource group format"):
            VMAgeChecker._validate_inputs("test-vm", long_rg)

    def test_valid_vm_name_with_hyphen_underscore(self):
        """Test valid VM name with hyphens and underscores."""
        # Should not raise
        VMAgeChecker._validate_inputs("my-test_vm-01", "test-rg")

    def test_valid_resource_group_with_special_chars(self):
        """Test valid resource group with allowed special characters."""
        # Should not raise
        VMAgeChecker._validate_inputs("test-vm", "my-rg_test.group(01)")


class TestGetVMAge:
    """Test VMAgeChecker.get_vm_age()."""

    def setup_method(self):
        """Clear cache before each test."""
        VMAgeChecker.clear_cache()

    def test_successful_vm_age_retrieval(self):
        """Test successful VM age calculation."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")

            assert age_info is not None
            assert age_info.vm_name == "test-vm"
            assert age_info.age_seconds > 0
            assert age_info.created_time is not None

    def test_invalid_input_returns_none(self):
        """Test invalid input returns None with warning."""
        age_info = VMAgeChecker.get_vm_age("", "test-rg")
        assert age_info is None

    def test_azure_cli_error_returns_none(self):
        """Test Azure CLI error returns None."""
        mock_result = Mock(returncode=1, stderr="VM not found")

        with patch("subprocess.run", return_value=mock_result):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is None

    def test_timeout_returns_none(self):
        """Test timeout returns None with warning."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="az", timeout=10)):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is None

    def test_json_decode_error_returns_none(self):
        """Test JSON decode error returns None."""
        mock_result = Mock(returncode=0, stdout="invalid json")

        with patch("subprocess.run", return_value=mock_result):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is None

    def test_missing_time_created_field_returns_none(self):
        """Test missing timeCreated field returns None."""
        mock_result = Mock(returncode=0, stdout=json.dumps(None))

        with patch("subprocess.run", return_value=mock_result):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is None

    def test_unexpected_exception_returns_none(self):
        """Test unexpected exception returns None."""
        with patch("subprocess.run", side_effect=Exception("Unexpected error")):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is None

    def test_custom_timeout_parameter(self):
        """Test custom timeout parameter is passed to subprocess."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            VMAgeChecker.get_vm_age("test-vm", "test-rg", timeout=30)

            # Verify timeout was passed to subprocess
            assert mock_run.call_args[1]["timeout"] == 30


class TestCacheBehavior:
    """Test cache behavior and TTL logic."""

    def setup_method(self):
        """Clear cache before each test."""
        VMAgeChecker.clear_cache()

    def test_cache_hit_returns_cached_result(self):
        """Test cache hit returns cached result."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # First call - should hit Azure
            age_info1 = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert mock_run.call_count == 1

            # Second call - should use cache
            age_info2 = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert mock_run.call_count == 1  # No additional call

            # Both should have same creation time
            assert age_info1.created_time == age_info2.created_time

            # Age should be updated
            assert age_info2.age_seconds >= age_info1.age_seconds

    def test_cache_miss_different_vm(self):
        """Test cache miss for different VM."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # First VM
            VMAgeChecker.get_vm_age("vm1", "test-rg")
            assert mock_run.call_count == 1

            # Different VM - should hit Azure again
            VMAgeChecker.get_vm_age("vm2", "test-rg")
            assert mock_run.call_count == 2

    def test_cache_miss_different_resource_group(self):
        """Test cache miss for different resource group."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # First RG
            VMAgeChecker.get_vm_age("test-vm", "rg1")
            assert mock_run.call_count == 1

            # Different RG - should hit Azure again
            VMAgeChecker.get_vm_age("test-vm", "rg2")
            assert mock_run.call_count == 2

    def test_cache_ttl_expiration(self):
        """Test cache TTL expiration causes refresh."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        # Set very short TTL for testing
        original_ttl = VMAgeChecker._cache_ttl
        VMAgeChecker._cache_ttl = 1  # 1 second

        try:
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                # First call
                VMAgeChecker.get_vm_age("test-vm", "test-rg")
                assert mock_run.call_count == 1

                # Wait for TTL expiration
                time.sleep(1.1)

                # Should refresh from Azure
                VMAgeChecker.get_vm_age("test-vm", "test-rg")
                assert mock_run.call_count == 2
        finally:
            VMAgeChecker._cache_ttl = original_ttl

    def test_clear_cache_removes_all_entries(self):
        """Test clear_cache removes all cached entries."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            # Cache multiple VMs
            VMAgeChecker.get_vm_age("vm1", "test-rg")
            VMAgeChecker.get_vm_age("vm2", "test-rg")
            assert mock_run.call_count == 2

            # Clear cache
            VMAgeChecker.clear_cache()

            # Should hit Azure again
            VMAgeChecker.get_vm_age("vm1", "test-rg")
            assert mock_run.call_count == 3


class TestIsVMReadyForAutoSync:
    """Test VMAgeChecker.is_vm_ready_for_auto_sync()."""

    def setup_method(self):
        """Clear cache before each test."""
        VMAgeChecker.clear_cache()

    def test_new_vm_not_ready(self):
        """Test VM younger than threshold returns False."""
        # VM created 5 minutes ago
        created_time = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result):
            # Threshold is 10 minutes
            is_ready = VMAgeChecker.is_vm_ready_for_auto_sync(
                "test-vm", "test-rg", threshold_seconds=600
            )
            assert is_ready is False

    def test_old_vm_ready(self):
        """Test VM older than threshold returns True."""
        # VM created 20 minutes ago
        from datetime import timedelta

        old_time = (datetime.now(UTC) - timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
        mock_result = Mock(returncode=0, stdout=json.dumps(old_time))

        with patch("subprocess.run", return_value=mock_result):
            # Threshold is 10 minutes
            is_ready = VMAgeChecker.is_vm_ready_for_auto_sync(
                "test-vm", "test-rg", threshold_seconds=600
            )
            assert is_ready is True

    def test_vm_exactly_at_threshold_ready(self):
        """Test VM exactly at threshold returns True."""
        from datetime import timedelta

        threshold_time = (
            (datetime.now(UTC) - timedelta(seconds=600)).isoformat().replace("+00:00", "Z")
        )
        mock_result = Mock(returncode=0, stdout=json.dumps(threshold_time))

        with patch("subprocess.run", return_value=mock_result):
            is_ready = VMAgeChecker.is_vm_ready_for_auto_sync(
                "test-vm", "test-rg", threshold_seconds=600
            )
            assert is_ready is True

    def test_fail_safe_unknown_age_returns_true(self):
        """Test fail-safe: unknown age returns True."""
        mock_result = Mock(returncode=1, stderr="VM not found")

        with patch("subprocess.run", return_value=mock_result):
            # Should return True (fail-safe)
            is_ready = VMAgeChecker.is_vm_ready_for_auto_sync("test-vm", "test-rg")
            assert is_ready is True

    def test_custom_threshold(self):
        """Test custom threshold parameter."""
        # VM created 2 minutes ago
        from datetime import timedelta

        recent_time = (datetime.now(UTC) - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
        mock_result = Mock(returncode=0, stdout=json.dumps(recent_time))

        with patch("subprocess.run", return_value=mock_result):
            # With 1 minute threshold - should be ready
            is_ready = VMAgeChecker.is_vm_ready_for_auto_sync(
                "test-vm", "test-rg", threshold_seconds=60
            )
            assert is_ready is True

            # With 5 minute threshold - should not be ready
            is_ready = VMAgeChecker.is_vm_ready_for_auto_sync(
                "test-vm", "test-rg", threshold_seconds=300
            )
            assert is_ready is False


class TestThreadSafety:
    """Test thread safety of cache operations."""

    def setup_method(self):
        """Clear cache before each test."""
        VMAgeChecker.clear_cache()

    def test_concurrent_get_vm_age_calls(self):
        """Test concurrent get_vm_age calls don't cause race conditions."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        results = []
        errors = []

        def worker():
            try:
                with patch("subprocess.run", return_value=mock_result):
                    age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
                    results.append(age_info)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=worker) for _ in range(10)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0

        # All results should be valid
        assert len(results) == 10
        for result in results:
            assert result is not None
            assert result.vm_name == "test-vm"

    def test_concurrent_cache_clear(self):
        """Test concurrent cache clear operations are safe."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        errors = []

        def worker():
            try:
                with patch("subprocess.run", return_value=mock_result):
                    VMAgeChecker.get_vm_age("test-vm", "test-rg")
                    VMAgeChecker.clear_cache()
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = [threading.Thread(target=worker) for _ in range(5)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Clear cache before each test."""
        VMAgeChecker.clear_cache()

    def test_vm_name_with_unicode_characters(self):
        """Test VM name with unicode characters is rejected."""
        with pytest.raises(ValueError, match="Invalid VM name format"):
            VMAgeChecker._validate_inputs("vm-名前", "test-rg")

    def test_very_old_vm_age(self):
        """Test VM with very old creation time."""
        # VM created 1 year ago
        from datetime import timedelta

        old_time = (datetime.now(UTC) - timedelta(days=365)).isoformat().replace("+00:00", "Z")
        mock_result = Mock(returncode=0, stdout=json.dumps(old_time))

        with patch("subprocess.run", return_value=mock_result):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is not None
            assert age_info.age_seconds > 31536000  # More than 1 year in seconds

    def test_future_creation_time_handles_gracefully(self):
        """Test VM with future creation time (clock skew)."""
        # VM "created" 1 hour in the future
        from datetime import timedelta

        future_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        mock_result = Mock(returncode=0, stdout=json.dumps(future_time))

        with patch("subprocess.run", return_value=mock_result):
            age_info = VMAgeChecker.get_vm_age("test-vm", "test-rg")
            assert age_info is not None
            # Age will be negative, but should not crash
            assert isinstance(age_info.age_seconds, float)

    def test_zero_timeout_parameter(self):
        """Test zero timeout parameter."""
        created_time = "2024-12-18T10:00:00+00:00"
        mock_result = Mock(returncode=0, stdout=json.dumps(created_time))

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            VMAgeChecker.get_vm_age("test-vm", "test-rg", timeout=0)
            assert mock_run.call_args[1]["timeout"] == 0
