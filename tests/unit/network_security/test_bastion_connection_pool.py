"""Unit tests for Bastion connection pooling.

Tests the BastionConnectionPool class that manages reusable Bastion tunnels.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- Tunnel reuse logic
- Pool size limits enforcement
- Idle timeout cleanup
- Health checking
- Thread safety
- Eviction policies
"""

import threading
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

# Mark all tests as TDD RED phase (expected to fail)
pytestmark = [pytest.mark.unit, pytest.mark.tdd_red]


class TestPooledTunnelDataclass:
    """Test PooledTunnel dataclass and its methods."""

    def test_pooled_tunnel_creation(self):
        """PooledTunnel should be created with required fields."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import PooledTunnel

        mock_tunnel = Mock(spec=BastionTunnel)
        now = datetime.now()

        pooled = PooledTunnel(tunnel=mock_tunnel, created_at=now, last_used=now, idle_timeout=300)

        assert pooled.tunnel == mock_tunnel
        assert pooled.created_at == now
        assert pooled.last_used == now
        assert pooled.use_count == 0
        assert pooled.idle_timeout == 300

    def test_is_expired_returns_true_when_idle_timeout_exceeded(self):
        """PooledTunnel should be expired when idle timeout exceeded."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import PooledTunnel

        mock_tunnel = Mock(spec=BastionTunnel)
        now = datetime.now()
        old_time = now - timedelta(seconds=400)  # 400 seconds ago

        pooled = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=old_time,
            last_used=old_time,
            idle_timeout=300,  # 5 minutes
        )

        assert pooled.is_expired() is True

    def test_is_expired_returns_false_when_within_idle_timeout(self):
        """PooledTunnel should not be expired when within idle timeout."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import PooledTunnel

        mock_tunnel = Mock(spec=BastionTunnel)
        now = datetime.now()
        recent_time = now - timedelta(seconds=100)  # 100 seconds ago

        pooled = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=recent_time,
            last_used=recent_time,
            idle_timeout=300,
        )

        assert pooled.is_expired() is False

    def test_is_healthy_delegates_to_manager(self):
        """PooledTunnel.is_healthy should delegate to BastionManager."""
        from azlin.bastion_manager import BastionManager, BastionTunnel
        from azlin.network_security.bastion_connection_pool import PooledTunnel

        mock_tunnel = Mock(spec=BastionTunnel)
        mock_manager = Mock(spec=BastionManager)
        mock_manager.check_tunnel_health.return_value = True

        pooled = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=datetime.now(),
            last_used=datetime.now(),
            idle_timeout=300,
        )

        result = pooled.is_healthy(mock_manager)

        assert result is True
        mock_manager.check_tunnel_health.assert_called_once_with(mock_tunnel)


class TestBastionConnectionPoolCreation:
    """Test BastionConnectionPool initialization and configuration."""

    def test_pool_creation_with_defaults(self):
        """Pool should be created with default configuration."""
        from azlin.bastion_manager import BastionManager
        from azlin.network_security.bastion_connection_pool import BastionConnectionPool

        mock_manager = Mock(spec=BastionManager)
        pool = BastionConnectionPool(mock_manager)

        assert pool.manager == mock_manager
        assert pool.max_tunnels == BastionConnectionPool.DEFAULT_MAX_TUNNELS
        assert pool.idle_timeout == BastionConnectionPool.DEFAULT_IDLE_TIMEOUT
        assert len(pool.pool) == 0

    def test_pool_creation_with_custom_limits(self):
        """Pool should accept custom max_tunnels and idle_timeout."""
        from azlin.bastion_manager import BastionManager
        from azlin.network_security.bastion_connection_pool import BastionConnectionPool

        mock_manager = Mock(spec=BastionManager)
        pool = BastionConnectionPool(mock_manager, max_tunnels=5, idle_timeout=600)

        assert pool.max_tunnels == 5
        assert pool.idle_timeout == 600


class TestBastionConnectionPoolTunnelReuse:
    """Test tunnel reuse logic - the core optimization."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_get_or_create_tunnel_creates_new_when_pool_empty(self, mock_manager_class):
        """When pool is empty, new tunnel should be created."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import BastionConnectionPool

        mock_manager = Mock()
        mock_tunnel = Mock(spec=BastionTunnel)
        mock_manager.create_tunnel.return_value = mock_tunnel
        mock_manager.get_available_port.return_value = 50000

        pool = BastionConnectionPool(mock_manager)

        result = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        assert result.tunnel == mock_tunnel
        assert result.use_count == 0
        mock_manager.create_tunnel.assert_called_once()

    @patch("azlin.bastion_manager.BastionManager")
    def test_get_or_create_tunnel_reuses_healthy_tunnel(self, mock_manager_class):
        """Healthy tunnel in pool should be reused."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        mock_tunnel = Mock(spec=BastionTunnel)

        # Pre-populate pool with healthy tunnel
        pool = BastionConnectionPool(mock_manager)
        key = ("test-bastion", "/subscriptions/test/vm1", 22)
        pool.pool[key] = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=datetime.now(),
            last_used=datetime.now(),
            use_count=1,
            idle_timeout=300,
        )

        # Mock health check to return True
        mock_manager.check_tunnel_health.return_value = True

        result = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        assert result.tunnel == mock_tunnel
        assert result.use_count == 2  # Incremented
        mock_manager.create_tunnel.assert_not_called()  # No new tunnel created

    @patch("azlin.bastion_manager.BastionManager")
    def test_get_or_create_tunnel_recreates_unhealthy_tunnel(self, mock_manager_class):
        """Unhealthy tunnel should be closed and recreated."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        old_tunnel = Mock(spec=BastionTunnel)
        new_tunnel = Mock(spec=BastionTunnel)

        # Pre-populate pool with unhealthy tunnel
        pool = BastionConnectionPool(mock_manager)
        key = ("test-bastion", "/subscriptions/test/vm1", 22)
        pool.pool[key] = PooledTunnel(
            tunnel=old_tunnel,
            created_at=datetime.now(),
            last_used=datetime.now(),
            use_count=5,
            idle_timeout=300,
        )

        # Mock health check to return False (unhealthy)
        mock_manager.check_tunnel_health.return_value = False
        mock_manager.create_tunnel.return_value = new_tunnel
        mock_manager.get_available_port.return_value = 50001

        result = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        assert result.tunnel == new_tunnel
        assert result.use_count == 0  # Reset for new tunnel
        mock_manager.close_tunnel.assert_called_once_with(old_tunnel)
        mock_manager.create_tunnel.assert_called_once()


class TestBastionConnectionPoolLimits:
    """Test connection limit enforcement and eviction policies."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_pool_enforces_max_tunnels_limit(self, mock_manager_class):
        """Pool should not exceed max_tunnels limit."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, max_tunnels=2)

        # Fill pool to max capacity
        for i in range(2):
            mock_tunnel = Mock(spec=BastionTunnel)
            key = (f"bastion-{i}", f"/vm{i}", 22)
            pool.pool[key] = PooledTunnel(
                tunnel=mock_tunnel,
                created_at=datetime.now(),
                last_used=datetime.now(),
                use_count=1,
                idle_timeout=300,
            )

        # Try to add one more - should trigger eviction
        mock_manager.get_available_port.return_value = 50003
        mock_manager.create_tunnel.return_value = Mock(spec=BastionTunnel)

        pool.get_or_create_tunnel(
            bastion_name="bastion-3",
            resource_group="test-rg",
            target_vm_id="/vm3",
            remote_port=22,
        )

        # Pool size should still be at max
        assert len(pool.pool) == 2

    @patch("azlin.bastion_manager.BastionManager")
    def test_evict_idle_tunnel_removes_oldest(self, mock_manager_class):
        """Eviction should remove the oldest idle tunnel."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, max_tunnels=3)

        now = datetime.now()
        tunnels = []

        # Add 3 tunnels with different last_used times
        for i in range(3):
            mock_tunnel = Mock(spec=BastionTunnel)
            tunnels.append(mock_tunnel)
            key = (f"bastion-{i}", f"/vm{i}", 22)
            pool.pool[key] = PooledTunnel(
                tunnel=mock_tunnel,
                created_at=now,
                last_used=now - timedelta(seconds=i * 100),  # Oldest is i=2
                use_count=1,
                idle_timeout=300,
            )

        # Evict oldest
        pool._evict_idle_tunnel()

        # Oldest tunnel (i=2) should be closed
        mock_manager.close_tunnel.assert_called_once_with(tunnels[2])
        assert len(pool.pool) == 2


class TestBastionConnectionPoolCleanup:
    """Test cleanup of expired tunnels."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_cleanup_expired_removes_expired_tunnels(self, mock_manager_class):
        """Expired tunnels should be removed from pool."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, idle_timeout=300)

        now = datetime.now()

        # Add 2 expired tunnels and 1 active tunnel
        for i in range(3):
            mock_tunnel = Mock(spec=BastionTunnel)
            key = (f"bastion-{i}", f"/vm{i}", 22)

            if i < 2:
                # Expired (last used 400 seconds ago)
                last_used = now - timedelta(seconds=400)
            else:
                # Active (last used 100 seconds ago)
                last_used = now - timedelta(seconds=100)

            pool.pool[key] = PooledTunnel(
                tunnel=mock_tunnel,
                created_at=now,
                last_used=last_used,
                use_count=1,
                idle_timeout=300,
            )

        expired_count = pool.cleanup_expired()

        assert expired_count == 2
        assert len(pool.pool) == 1  # Only 1 active tunnel remains
        assert mock_manager.close_tunnel.call_count == 2

    @patch("azlin.bastion_manager.BastionManager")
    def test_cleanup_expired_returns_zero_when_none_expired(self, mock_manager_class):
        """Cleanup should return 0 when no tunnels are expired."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, idle_timeout=300)

        # Add active tunnel (last used 100 seconds ago)
        mock_tunnel = Mock(spec=BastionTunnel)
        key = ("bastion-0", "/vm0", 22)
        pool.pool[key] = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=datetime.now(),
            last_used=datetime.now() - timedelta(seconds=100),
            use_count=1,
            idle_timeout=300,
        )

        expired_count = pool.cleanup_expired()

        assert expired_count == 0
        assert len(pool.pool) == 1
        mock_manager.close_tunnel.assert_not_called()


class TestBastionConnectionPoolCloseAll:
    """Test closing all tunnels in pool."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_close_all_closes_all_tunnels(self, mock_manager_class):
        """close_all should close all tunnels and clear pool."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager)

        # Add 3 tunnels
        tunnels = []
        for i in range(3):
            mock_tunnel = Mock(spec=BastionTunnel)
            tunnels.append(mock_tunnel)
            key = (f"bastion-{i}", f"/vm{i}", 22)
            pool.pool[key] = PooledTunnel(
                tunnel=mock_tunnel,
                created_at=datetime.now(),
                last_used=datetime.now(),
                use_count=1,
                idle_timeout=300,
            )

        pool.close_all()

        assert len(pool.pool) == 0
        assert mock_manager.close_tunnel.call_count == 3


class TestBastionConnectionPoolThreadSafety:
    """Test thread safety of connection pool operations."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_concurrent_get_or_create_is_thread_safe(self, mock_manager_class):
        """Multiple threads should be able to safely access pool."""
        from azlin.bastion_manager import BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
        )

        mock_manager = Mock()
        mock_manager.get_available_port.return_value = 50000
        mock_manager.create_tunnel.return_value = Mock(spec=BastionTunnel)
        mock_manager.check_tunnel_health.return_value = True

        pool = BastionConnectionPool(mock_manager)

        # Concurrent access from 10 threads
        def get_tunnel():
            pool.get_or_create_tunnel(
                bastion_name="test-bastion",
                resource_group="test-rg",
                target_vm_id="/vm1",
                remote_port=22,
            )

        threads = [threading.Thread(target=get_tunnel) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Pool should have only 1 tunnel (same key)
        assert len(pool.pool) == 1


class TestBastionCleanupDaemon:
    """Test background cleanup daemon for automatic maintenance."""

    def test_daemon_starts_and_stops(self):
        """Cleanup daemon should start and stop cleanly."""
        from azlin.bastion_manager import BastionManager
        from azlin.network_security.bastion_connection_pool import (
            BastionCleanupDaemon,
            BastionConnectionPool,
        )

        mock_manager = Mock(spec=BastionManager)
        pool = BastionConnectionPool(mock_manager)
        daemon = BastionCleanupDaemon(pool, interval=1)

        daemon.start()
        assert daemon.running is True

        time.sleep(0.5)  # Let it run briefly

        daemon.stop()
        assert daemon.running is False

    def test_daemon_cleans_up_expired_tunnels_periodically(self):
        """Daemon should periodically cleanup expired tunnels."""
        from azlin.bastion_manager import BastionManager, BastionTunnel
        from azlin.network_security.bastion_connection_pool import (
            BastionCleanupDaemon,
            BastionConnectionPool,
            PooledTunnel,
        )

        mock_manager = Mock(spec=BastionManager)
        pool = BastionConnectionPool(mock_manager, idle_timeout=1)

        # Add expired tunnel
        mock_tunnel = Mock(spec=BastionTunnel)
        key = ("bastion-0", "/vm0", 22)
        pool.pool[key] = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=datetime.now() - timedelta(seconds=10),
            last_used=datetime.now() - timedelta(seconds=10),
            use_count=1,
            idle_timeout=1,  # 1 second timeout
        )

        daemon = BastionCleanupDaemon(pool, interval=1)
        daemon.start()

        time.sleep(2)  # Wait for cleanup to run

        daemon.stop()

        # Expired tunnel should be cleaned up
        assert len(pool.pool) == 0
        mock_manager.close_tunnel.assert_called()
