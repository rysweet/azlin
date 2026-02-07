"""Unit tests for Bastion tunnel retry logic.

Tests for the retry and rate limiting functionality added to
_collect_tmux_sessions() to improve reliability when restoring 10+ VMs.

Issue: #588 - Bastion tunnel creation fails during restore with 10+ VMs

These tests follow TDD approach - they will FAIL until implementation is complete.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.bastion_manager import BastionManagerError


class TestGetConfigHelpers:
    """Test configuration helper functions."""

    def test_get_config_int_returns_default_when_not_set(self):
        """Test _get_config_int returns default when env var not set."""
        from azlin.cli import _get_config_int

        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            result = _get_config_int("AZLIN_TEST_VAR", 42)
            assert result == 42

    def test_get_config_int_returns_env_value_when_set(self):
        """Test _get_config_int returns env var value when set."""
        from azlin.cli import _get_config_int

        with patch.dict(os.environ, {"AZLIN_TEST_VAR": "100"}):
            result = _get_config_int("AZLIN_TEST_VAR", 42)
            assert result == 100

    def test_get_config_int_returns_default_on_invalid_value(self):
        """Test _get_config_int returns default when env var is invalid."""
        from azlin.cli import _get_config_int

        with patch.dict(os.environ, {"AZLIN_TEST_VAR": "not_a_number"}):
            result = _get_config_int("AZLIN_TEST_VAR", 42)
            assert result == 42

    def test_get_config_float_returns_default_when_not_set(self):
        """Test _get_config_float returns default when env var not set."""
        from azlin.cli import _get_config_float

        with patch.dict(os.environ, {}, clear=True):
            result = _get_config_float("AZLIN_TEST_VAR", 1.5)
            assert result == 1.5

    def test_get_config_float_returns_env_value_when_set(self):
        """Test _get_config_float returns env var value when set."""
        from azlin.cli import _get_config_float

        with patch.dict(os.environ, {"AZLIN_TEST_VAR": "2.5"}):
            result = _get_config_float("AZLIN_TEST_VAR", 1.5)
            assert result == 2.5

    def test_get_config_float_returns_default_on_invalid_value(self):
        """Test _get_config_float returns default when env var is invalid."""
        from azlin.cli import _get_config_float

        with patch.dict(os.environ, {"AZLIN_TEST_VAR": "not_a_number"}):
            result = _get_config_float("AZLIN_TEST_VAR", 1.5)
            assert result == 1.5


class TestCreateTunnelWithRetry:
    """Test _create_tunnel_with_retry function."""

    @pytest.fixture
    def mock_pool(self):
        """Create mock BastionConnectionPool."""
        pool = MagicMock()
        pool.get_or_create_tunnel.return_value = MagicMock()
        return pool

    @pytest.fixture
    def mock_vm(self):
        """Create mock VMInfo."""
        vm = MagicMock()
        vm.name = "test-vm"
        return vm

    @pytest.fixture
    def bastion_info(self):
        """Create sample bastion info."""
        return {"name": "test-bastion", "resource_group": "test-rg"}

    def test_create_tunnel_success_first_attempt(self, mock_pool, mock_vm, bastion_info):
        """Test tunnel creation succeeds on first attempt."""
        from azlin.cli import _create_tunnel_with_retry

        mock_pooled_tunnel = MagicMock()
        mock_pooled_tunnel.tunnel.local_port = 50000
        mock_pool.get_or_create_tunnel.return_value = mock_pooled_tunnel

        result = _create_tunnel_with_retry(
            pool=mock_pool,
            vm=mock_vm,
            bastion_info=bastion_info,
            vm_resource_id="/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            max_attempts=3,
        )

        assert result == mock_pooled_tunnel
        assert mock_pool.get_or_create_tunnel.call_count == 1

    def test_create_tunnel_retries_on_transient_failure(self, mock_pool, mock_vm, bastion_info):
        """Test tunnel creation retries on transient failure."""
        from azlin.cli import _create_tunnel_with_retry

        mock_pooled_tunnel = MagicMock()
        mock_pooled_tunnel.tunnel.local_port = 50000

        # Fail first two attempts, succeed on third
        mock_pool.get_or_create_tunnel.side_effect = [
            BastionManagerError("Network connectivity issue"),
            BastionManagerError("Tunnel creation failed"),
            mock_pooled_tunnel,
        ]

        result = _create_tunnel_with_retry(
            pool=mock_pool,
            vm=mock_vm,
            bastion_info=bastion_info,
            vm_resource_id="/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            max_attempts=3,
        )

        assert result == mock_pooled_tunnel
        assert mock_pool.get_or_create_tunnel.call_count == 3

    def test_create_tunnel_raises_after_max_attempts(self, mock_pool, mock_vm, bastion_info):
        """Test tunnel creation raises BastionManagerError after max attempts exhausted."""
        from azlin.cli import _create_tunnel_with_retry

        # Fail all attempts
        mock_pool.get_or_create_tunnel.side_effect = BastionManagerError("Persistent failure")

        with pytest.raises(BastionManagerError) as exc_info:
            _create_tunnel_with_retry(
                pool=mock_pool,
                vm=mock_vm,
                bastion_info=bastion_info,
                vm_resource_id="/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
                max_attempts=3,
            )

        assert mock_pool.get_or_create_tunnel.call_count == 3
        # Error message includes VM name and attempt count
        assert "test-vm" in str(exc_info.value)
        assert "3 attempts" in str(exc_info.value)

    def test_create_tunnel_uses_exponential_backoff(self, mock_pool, mock_vm, bastion_info):
        """Test tunnel creation uses exponential backoff between retries."""
        from azlin.cli import _create_tunnel_with_retry

        mock_pooled_tunnel = MagicMock()
        call_times = []

        def side_effect(*args, **kwargs):
            call_times.append(time.time())
            if len(call_times) < 3:
                raise BastionManagerError("Transient failure")
            return mock_pooled_tunnel

        mock_pool.get_or_create_tunnel.side_effect = side_effect

        _create_tunnel_with_retry(
            pool=mock_pool,
            vm=mock_vm,
            bastion_info=bastion_info,
            vm_resource_id="/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            max_attempts=3,
        )

        # Verify backoff occurred (at least 1s between calls, allowing for jitter)
        if len(call_times) >= 2:
            delay1 = call_times[1] - call_times[0]
            assert delay1 >= 0.5, f"First delay {delay1}s should be at least 0.5s"

        if len(call_times) >= 3:
            delay2 = call_times[2] - call_times[1]
            assert delay2 >= delay1 * 0.5, f"Second delay {delay2}s should be longer than first"


class TestCollectTmuxSessionsRateLimiting:
    """Test rate limiting in _collect_tmux_sessions."""

    @patch("azlin.cli.BastionDetector")
    @patch("azlin.cli.BastionManager")
    @patch("azlin.cli.BastionConnectionPool")
    @patch("azlin.cli._create_tunnel_with_retry")
    @patch("azlin.cli.TmuxSessionExecutor")
    @patch("azlin.cli.AzureAuthenticator")
    @patch("azlin.cli.SSHKeyManager")
    def test_rate_limiting_delay_between_tunnels(
        self,
        mock_ssh_key_mgr,
        mock_auth,
        mock_tmux,
        mock_create_tunnel,
        mock_pool_cls,
        mock_bastion_mgr,
        mock_detector,
    ):
        """Test rate limiting adds delay between tunnel creations."""
        from azlin.cli import _collect_tmux_sessions

        # Setup mocks
        mock_ssh_key_mgr.ensure_key_exists.return_value = MagicMock(private_path="/path/to/key")
        mock_auth_instance = MagicMock()
        mock_auth_instance.get_subscription_id.return_value = "test-sub"
        mock_auth.return_value = mock_auth_instance

        mock_detector.detect_bastion_for_vm.return_value = {
            "name": "bastion",
            "resource_group": "rg",
        }

        mock_pooled_tunnel = MagicMock()
        mock_pooled_tunnel.tunnel.local_port = 50000
        mock_create_tunnel.return_value = mock_pooled_tunnel

        mock_tmux.get_sessions_parallel.return_value = []

        # Create mock VMs (bastion-only: private IP, no public IP)
        vms = []
        for i in range(3):
            vm = MagicMock()
            vm.name = f"vm-{i}"
            vm.public_ip = None
            vm.private_ip = f"10.0.0.{i}"
            vm.is_running.return_value = True
            vm.resource_group = "test-rg"
            vm.location = "eastus"
            vm.get_resource_id.return_value = f"/subscriptions/test/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm-{i}"
            vms.append(vm)

        # Configure rate limiting
        with patch.dict(os.environ, {"AZLIN_BASTION_RATE_LIMIT": "0.1"}):  # Fast for test
            start_time = time.time()
            _collect_tmux_sessions(vms)
            elapsed = time.time() - start_time

        # Should have at least 0.2s total delay (0.1s * 2 gaps between 3 VMs)
        assert elapsed >= 0.15, f"Expected at least 0.15s delay, got {elapsed}s"
        assert mock_create_tunnel.call_count == 3


class TestEnvironmentVariableConfiguration:
    """Test environment variable configuration for bastion tunnel behavior."""

    def test_default_retry_attempts(self):
        """Test default retry attempts is 3."""
        from azlin.cli import _get_config_int

        with patch.dict(os.environ, {}, clear=True):
            result = _get_config_int("AZLIN_BASTION_RETRY_ATTEMPTS", 3)
            assert result == 3

    def test_default_rate_limit(self):
        """Test default rate limit is 0.5 seconds."""
        from azlin.cli import _get_config_float

        with patch.dict(os.environ, {}, clear=True):
            result = _get_config_float("AZLIN_BASTION_RATE_LIMIT", 0.5)
            assert result == 0.5

    def test_default_max_tunnels(self):
        """Test default max tunnels is 10."""
        from azlin.cli import _get_config_int

        with patch.dict(os.environ, {}, clear=True):
            result = _get_config_int("AZLIN_BASTION_MAX_TUNNELS", 10)
            assert result == 10

    def test_default_idle_timeout(self):
        """Test default idle timeout is 300 seconds."""
        from azlin.cli import _get_config_int

        with patch.dict(os.environ, {}, clear=True):
            result = _get_config_int("AZLIN_BASTION_IDLE_TIMEOUT", 300)
            assert result == 300

    def test_custom_retry_attempts_from_env(self):
        """Test custom retry attempts from environment variable."""
        from azlin.cli import _get_config_int

        with patch.dict(os.environ, {"AZLIN_BASTION_RETRY_ATTEMPTS": "5"}):
            result = _get_config_int("AZLIN_BASTION_RETRY_ATTEMPTS", 3)
            assert result == 5

    def test_custom_rate_limit_from_env(self):
        """Test custom rate limit from environment variable."""
        from azlin.cli import _get_config_float

        with patch.dict(os.environ, {"AZLIN_BASTION_RATE_LIMIT": "2.0"}):
            result = _get_config_float("AZLIN_BASTION_RATE_LIMIT", 0.5)
            assert result == 2.0
