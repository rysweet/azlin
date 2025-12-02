"""Integration tests for Bastion connection pooling + cleanup daemon.

Tests the integration between BastionConnectionPool, BastionCleanupDaemon, and BastionManager.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- Pool + daemon working together
- Tunnel reuse across multiple operations
- Automatic cleanup of expired tunnels
- Health monitoring integration
- Resource leak prevention
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Mark all tests as integration and TDD RED phase
pytestmark = [pytest.mark.integration, pytest.mark.tdd_red]


class TestBastionPoolWithDaemon:
    """Test connection pool working with cleanup daemon."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_daemon_cleans_expired_tunnels_from_pool(self, mock_manager_class):
        """Daemon should automatically remove expired tunnels from pool."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            BastionCleanupDaemon,
            PooledTunnel,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, idle_timeout=1)  # 1 second timeout

        # Add expired tunnel
        mock_tunnel = Mock(spec=BastionTunnel)
        key = ("bastion-0", "/vm0", 22)
        pool.pool[key] = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=datetime.now() - timedelta(seconds=10),
            last_used=datetime.now() - timedelta(seconds=10),
            use_count=1,
            idle_timeout=1,
        )

        # Start daemon
        daemon = BastionCleanupDaemon(pool, interval=1)
        daemon.start()

        # Wait for cleanup
        time.sleep(2.5)

        daemon.stop()

        # Verify expired tunnel was cleaned
        assert len(pool.pool) == 0
        mock_manager.close_tunnel.assert_called_once_with(mock_tunnel)

    @patch("azlin.bastion_manager.BastionManager")
    def test_daemon_leaves_active_tunnels_alone(self, mock_manager_class):
        """Daemon should not remove active tunnels."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            BastionCleanupDaemon,
            PooledTunnel,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, idle_timeout=10)  # 10 second timeout

        # Add active tunnel
        mock_tunnel = Mock(spec=BastionTunnel)
        key = ("bastion-0", "/vm0", 22)
        pool.pool[key] = PooledTunnel(
            tunnel=mock_tunnel,
            created_at=datetime.now(),
            last_used=datetime.now(),
            use_count=1,
            idle_timeout=10,
        )

        # Start daemon
        daemon = BastionCleanupDaemon(pool, interval=1)
        daemon.start()

        # Wait for cleanup cycle
        time.sleep(2)

        daemon.stop()

        # Verify active tunnel was NOT cleaned
        assert len(pool.pool) == 1
        mock_manager.close_tunnel.assert_not_called()


class TestBastionPoolTunnelReuse:
    """Test tunnel reuse across multiple SSH operations."""

    @patch("subprocess.run")
    def test_multiple_ssh_operations_reuse_same_tunnel(
        self, mock_run
    ):
        """Multiple SSH operations to same VM should reuse tunnel."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        mock_tunnel = Mock(spec=BastionTunnel)
        mock_tunnel.local_port = 50000

        mock_manager.create_tunnel.return_value = mock_tunnel
        mock_manager.get_available_port.return_value = 50000
        mock_manager.check_tunnel_health.return_value = True

        pool = BastionConnectionPool(mock_manager)

        # First SSH operation
        pooled1 = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        # Second SSH operation (should reuse tunnel)
        pooled2 = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        # Third SSH operation (should reuse tunnel)
        pooled3 = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        # Verify tunnel was created only once
        assert mock_manager.create_tunnel.call_count == 1

        # Verify same tunnel was reused
        assert pooled1.tunnel == pooled2.tunnel == pooled3.tunnel

        # Verify use count incremented
        assert pooled3.use_count == 2  # Created with 0, incremented twice


class TestBastionPoolHealthMonitoring:
    """Test health monitoring and automatic tunnel recreation."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_unhealthy_tunnel_recreated_automatically(self, mock_manager_class):
        """Unhealthy tunnel should be detected and recreated."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        old_tunnel = Mock(spec=BastionTunnel)
        new_tunnel = Mock(spec=BastionTunnel)

        # First call: create old tunnel
        # Second call: create new tunnel
        mock_manager.create_tunnel.side_effect = [old_tunnel, new_tunnel]
        mock_manager.get_available_port.return_value = 50000

        pool = BastionConnectionPool(mock_manager)

        # Create initial tunnel
        mock_manager.check_tunnel_health.return_value = True
        pooled1 = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        assert pooled1.tunnel == old_tunnel

        # Tunnel becomes unhealthy
        mock_manager.check_tunnel_health.return_value = False

        # Next request should detect unhealthy and recreate
        pooled2 = pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/test/vm1",
            remote_port=22,
        )

        # Verify old tunnel was closed
        mock_manager.close_tunnel.assert_called_once_with(old_tunnel)

        # Verify new tunnel was created
        assert pooled2.tunnel == new_tunnel
        assert pooled2.use_count == 0  # Fresh tunnel


class TestBastionPoolResourceLeakPrevention:
    """Test prevention of resource leaks (ports, processes)."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_close_all_on_exit_prevents_leaks(self, mock_manager_class):
        """close_all should cleanup all tunnels to prevent leaks."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager)

        # Create multiple tunnels
        tunnels = []
        for i in range(5):
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

        # Simulate application exit
        pool.close_all()

        # Verify all tunnels were closed
        assert len(pool.pool) == 0
        assert mock_manager.close_tunnel.call_count == 5

        # Verify each tunnel was closed
        for tunnel in tunnels:
            mock_manager.close_tunnel.assert_any_call(tunnel)

    @patch("azlin.bastion_manager.BastionManager")
    def test_eviction_closes_tunnel_to_prevent_leak(self, mock_manager_class):
        """Evicted tunnels should be properly closed."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
            PooledTunnel,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        pool = BastionConnectionPool(mock_manager, max_tunnels=2)

        # Fill pool to capacity
        tunnels = []
        for i in range(2):
            mock_tunnel = Mock(spec=BastionTunnel)
            tunnels.append(mock_tunnel)
            key = (f"bastion-{i}", f"/vm{i}", 22)
            pool.pool[key] = PooledTunnel(
                tunnel=mock_tunnel,
                created_at=datetime.now(),
                last_used=datetime.now() - timedelta(seconds=i * 100),
                use_count=1,
                idle_timeout=300,
            )

        # Add one more tunnel (should trigger eviction)
        new_tunnel = Mock(spec=BastionTunnel)
        mock_manager.create_tunnel.return_value = new_tunnel
        mock_manager.get_available_port.return_value = 50003

        pool.get_or_create_tunnel(
            bastion_name="bastion-3",
            resource_group="test-rg",
            target_vm_id="/vm3",
            remote_port=22,
        )

        # Verify oldest tunnel was closed
        mock_manager.close_tunnel.assert_called_once()


class TestBastionPoolConcurrentAccess:
    """Test thread safety under concurrent load."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_concurrent_tunnel_requests_thread_safe(self, mock_manager_class):
        """Pool should handle concurrent requests safely."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
        )
        from azlin.bastion_manager import BastionTunnel

        mock_manager = Mock()
        mock_manager.get_available_port.return_value = 50000
        mock_manager.check_tunnel_health.return_value = True

        # Each thread gets same tunnel
        created_tunnels = []

        def create_tunnel_side_effect(*args, **kwargs):
            tunnel = Mock(spec=BastionTunnel)
            created_tunnels.append(tunnel)
            return tunnel

        mock_manager.create_tunnel.side_effect = create_tunnel_side_effect

        pool = BastionConnectionPool(mock_manager)

        # Concurrent requests for same VM
        results = []
        errors = []

        def get_tunnel():
            try:
                result = pool.get_or_create_tunnel(
                    bastion_name="test-bastion",
                    resource_group="test-rg",
                    target_vm_id="/subscriptions/test/vm1",
                    remote_port=22,
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_tunnel) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0

        # Verify only 1 tunnel was created (first request)
        assert len(created_tunnels) == 1

        # Verify all requests got the same tunnel
        assert all(r.tunnel == created_tunnels[0] for r in results)


class TestBastionPoolPerformanceImprovement:
    """Test performance improvement from tunnel reuse."""

    @patch("azlin.bastion_manager.BastionManager")
    def test_tunnel_reuse_faster_than_recreation(self, mock_manager_class):
        """Reusing tunnel should be significantly faster than creating new."""
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
        )
        from azlin.bastion_manager import BastionTunnel
        import time

        mock_manager = Mock()
        mock_tunnel = Mock(spec=BastionTunnel)

        # Simulate slow tunnel creation (15 seconds)
        def slow_create(*args, **kwargs):
            time.sleep(0.1)  # Simulated delay
            return mock_tunnel

        mock_manager.create_tunnel.side_effect = slow_create
        mock_manager.get_available_port.return_value = 50000
        mock_manager.check_tunnel_health.return_value = True

        pool = BastionConnectionPool(mock_manager)

        # First request (creates tunnel - slow)
        start = time.time()
        pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/vm1",
            remote_port=22,
        )
        first_duration = time.time() - start

        # Second request (reuses tunnel - fast)
        start = time.time()
        pool.get_or_create_tunnel(
            bastion_name="test-bastion",
            resource_group="test-rg",
            target_vm_id="/vm1",
            remote_port=22,
        )
        second_duration = time.time() - start

        # Verify reuse is significantly faster (at least 10x)
        assert second_duration < first_duration / 10
