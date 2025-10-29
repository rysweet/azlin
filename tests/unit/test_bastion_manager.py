"""Unit tests for BastionManager class.

Tests for Azure Bastion tunnel management functionality including:
- Tunnel creation and cleanup
- Port forwarding setup
- Connection lifecycle
- Error handling and edge cases

These tests follow TDD approach - they will FAIL until implementation is complete.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from azlin.modules.bastion_manager import (
    BastionManager,
    BastionManagerError,
    BastionTunnel,
)


class TestBastionTunnel:
    """Test BastionTunnel dataclass."""

    def test_tunnel_creation(self):
        """Test creating BastionTunnel object."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Process still running

        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="my-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            local_port=50022,
            remote_port=22,
            process=mock_process,
        )

        assert tunnel.bastion_name == "my-bastion"
        assert tunnel.resource_group == "my-rg"
        assert tunnel.local_port == 50022
        assert tunnel.remote_port == 22
        assert tunnel.is_active() is True

    def test_tunnel_is_active_with_running_process(self):
        """Test tunnel is active when process is running."""
        mock_process = Mock()
        mock_process.poll.return_value = None  # Still running

        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="my-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            local_port=50022,
            remote_port=22,
            process=mock_process,
        )

        assert tunnel.is_active() is True

    def test_tunnel_is_inactive_with_terminated_process(self):
        """Test tunnel is inactive when process has terminated."""
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Exited

        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="my-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            local_port=50022,
            remote_port=22,
            process=mock_process,
        )

        assert tunnel.is_active() is False


class TestBastionManager:
    """Test BastionManager class."""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess operations."""
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_process.pid = 12345
            mock_popen.return_value = mock_process
            yield mock_popen

    def test_create_tunnel_success(self, mock_subprocess):
        """Test creating Bastion tunnel successfully."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            # Act
            tunnel = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

        # Assert
        assert tunnel is not None
        assert tunnel.bastion_name == "my-bastion"
        assert tunnel.local_port == 50022
        assert tunnel.remote_port == 22
        assert tunnel.is_active() is True

        # Verify az command was called
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert "az" in call_args
        assert "network" in call_args
        assert "bastion" in call_args
        assert "tunnel" in call_args
        assert "--port" in call_args
        assert "22" in call_args

    def test_create_tunnel_with_custom_port(self, mock_subprocess):
        """Test creating tunnel with custom port."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            # Act
            tunnel = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50080,
                remote_port=80,
            )

        # Assert
        assert tunnel.local_port == 50080
        assert tunnel.remote_port == 80

    def test_create_tunnel_port_already_in_use(self, mock_subprocess):
        """Test error when local port is already in use."""
        # Arrange
        manager = BastionManager()
        mock_subprocess.side_effect = OSError("Address already in use")

        # Act & Assert
        with pytest.raises(BastionManagerError, match="Port.*already in use"):
            manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

    def test_create_tunnel_bastion_not_found(self, mock_subprocess):
        """Test error when Bastion host not found."""
        # Arrange
        manager = BastionManager()
        mock_process = Mock()
        mock_process.poll.return_value = 1
        mock_process.communicate.return_value = (b"", b"ResourceNotFound")
        mock_subprocess.return_value = mock_process

        # Act & Assert
        with pytest.raises(BastionManagerError, match="Bastion host not found"):
            manager.create_tunnel(
                bastion_name="nonexistent-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

    def test_create_tunnel_invalid_vm_id(self):
        """Test error with invalid VM resource ID."""
        # Arrange
        manager = BastionManager()

        # Act & Assert
        with pytest.raises(BastionManagerError, match="Invalid VM resource ID"):
            manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="invalid-id",
                local_port=50022,
                remote_port=22,
            )

    def test_close_tunnel_success(self, mock_subprocess):
        """Test closing tunnel successfully."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            tunnel = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

        # Act
        manager.close_tunnel(tunnel)

        # Assert
        tunnel.process.terminate.assert_called_once()
        assert tunnel not in manager.active_tunnels

    def test_close_tunnel_force_kill(self, mock_subprocess):
        """Test force killing tunnel when terminate fails."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            tunnel = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

        # Mock terminate timeout
        tunnel.process.wait.side_effect = subprocess.TimeoutExpired(cmd="az", timeout=5)

        # Act
        manager.close_tunnel(tunnel)

        # Assert
        tunnel.process.terminate.assert_called_once()
        tunnel.process.kill.assert_called_once()

    def test_close_tunnel_already_closed(self, mock_subprocess):
        """Test closing already closed tunnel (idempotent)."""
        # Arrange
        manager = BastionManager()
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Already terminated

        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="my-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            local_port=50022,
            remote_port=22,
            process=mock_process,
        )

        # Act (should not raise error)
        manager.close_tunnel(tunnel)

        # Assert - terminate not called for already dead process
        mock_process.terminate.assert_not_called()

    def test_close_all_tunnels(self, mock_subprocess):
        """Test closing all active tunnels."""
        # Arrange
        manager = BastionManager()

        # Create separate mock processes for each tunnel
        mock_process1 = Mock()
        mock_process1.poll.return_value = None
        mock_process2 = Mock()
        mock_process2.poll.return_value = None
        mock_subprocess.side_effect = [mock_process1, mock_process2]

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            _tunnel1 = manager.create_tunnel(
                bastion_name="bastion1",
                resource_group="rg1",
                target_vm_id="/subscriptions/sub/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1",
                local_port=50022,
                remote_port=22,
            )
            _tunnel2 = manager.create_tunnel(
                bastion_name="bastion2",
                resource_group="rg2",
                target_vm_id="/subscriptions/sub/resourceGroups/rg2/providers/Microsoft.Compute/virtualMachines/vm2",
                local_port=50023,
                remote_port=22,
            )

        # Act
        manager.close_all_tunnels()

        # Assert
        mock_process1.terminate.assert_called_once()
        mock_process2.terminate.assert_called_once()
        assert len(manager.active_tunnels) == 0

    def test_get_tunnel_by_port(self, mock_subprocess):
        """Test finding tunnel by local port."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            tunnel = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

        # Act
        found_tunnel = manager.get_tunnel_by_port(50022)

        # Assert
        assert found_tunnel == tunnel

    def test_get_tunnel_by_port_not_found(self):
        """Test finding tunnel by port when no tunnel exists."""
        # Arrange
        manager = BastionManager()

        # Act
        found_tunnel = manager.get_tunnel_by_port(50022)

        # Assert
        assert found_tunnel is None

    def test_get_available_port(self):
        """Test finding available local port."""
        # Arrange
        manager = BastionManager()

        # Act
        port = manager.get_available_port()

        # Assert
        assert 50000 <= port <= 60000
        assert isinstance(port, int)

    def test_get_available_port_range_exhausted(self, mock_subprocess):
        """Test error when all ports in range are used."""
        # Arrange
        manager = BastionManager()

        # Mock socket to always claim port is in use
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.bind.side_effect = OSError(
                "Address already in use"
            )

            # Act & Assert
            with pytest.raises(BastionManagerError, match="No available ports"):
                manager.get_available_port(start_port=50000, end_port=50005)

    def test_list_active_tunnels(self, mock_subprocess):
        """Test listing all active tunnels."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            _tunnel1 = manager.create_tunnel(
                bastion_name="bastion1",
                resource_group="rg1",
                target_vm_id="/subscriptions/sub/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1",
                local_port=50022,
                remote_port=22,
            )
            _tunnel2 = manager.create_tunnel(
                bastion_name="bastion2",
                resource_group="rg2",
                target_vm_id="/subscriptions/sub/resourceGroups/rg2/providers/Microsoft.Compute/virtualMachines/vm2",
                local_port=50023,
                remote_port=22,
            )

        # Act
        tunnels = manager.list_active_tunnels()

        # Assert
        assert len(tunnels) == 2
        assert tunnel1 in tunnels
        assert tunnel2 in tunnels

    def test_cleanup_inactive_tunnels(self, mock_subprocess):
        """Test cleanup of inactive tunnels."""
        # Arrange
        manager = BastionManager()
        mock_process_dead = Mock()
        mock_process_dead.poll.return_value = 1  # Dead

        dead_tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="my-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            local_port=50022,
            remote_port=22,
            process=mock_process_dead,
        )
        manager.active_tunnels.append(dead_tunnel)

        # Act
        removed_count = manager.cleanup_inactive_tunnels()

        # Assert
        assert removed_count == 1
        assert dead_tunnel not in manager.active_tunnels

    def test_tunnel_health_check(self, mock_subprocess):
        """Test checking tunnel health."""
        # Arrange
        manager = BastionManager()

        # Mock the tunnel readiness check
        with patch.object(manager, "_wait_for_tunnel_ready"):
            tunnel = manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

        # Mock socket connection for health check
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.connect.return_value = None

            # Act
            is_healthy = manager.check_tunnel_health(tunnel)

        # Assert
        assert is_healthy is True

    def test_tunnel_health_check_failed(self, mock_subprocess):
        """Test tunnel health check when tunnel is dead."""
        # Arrange
        manager = BastionManager()
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Dead

        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="my-rg",
            target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
            local_port=50022,
            remote_port=22,
            process=mock_process,
        )

        # Act
        is_healthy = manager.check_tunnel_health(tunnel)

        # Assert
        assert is_healthy is False

    def test_create_tunnel_with_timeout(self, mock_subprocess):
        """Test tunnel creation respects timeout."""
        # Arrange
        manager = BastionManager()
        mock_process = Mock()
        mock_process.poll.return_value = None

        # Mock slow startup
        with patch("time.sleep"):
            with patch("socket.socket") as mock_socket:
                # First 3 attempts fail, 4th succeeds
                mock_socket.return_value.__enter__.return_value.connect.side_effect = [
                    ConnectionRefusedError(),
                    ConnectionRefusedError(),
                    ConnectionRefusedError(),
                    None,
                ]

                # Act
                tunnel = manager.create_tunnel(
                    bastion_name="my-bastion",
                    resource_group="my-rg",
                    target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                    local_port=50022,
                    remote_port=22,
                    wait_for_ready=True,
                    timeout=30,
                )

                # Assert
                assert tunnel is not None

    def test_create_tunnel_timeout_exceeded(self, mock_subprocess):
        """Test error when tunnel creation times out."""
        # Arrange
        manager = BastionManager()

        # Mock connection always failing
        with patch("time.sleep"):
            with patch("socket.socket") as mock_socket:
                mock_socket.return_value.__enter__.return_value.connect.side_effect = (
                    ConnectionRefusedError()
                )

                # Act & Assert
                with pytest.raises(BastionManagerError, match="Tunnel failed to become ready"):
                    manager.create_tunnel(
                        bastion_name="my-bastion",
                        resource_group="my-rg",
                        target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                        local_port=50022,
                        remote_port=22,
                        wait_for_ready=True,
                        timeout=5,
                    )


class TestBastionManagerEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_bastion_name(self):
        """Test error with empty Bastion name."""
        manager = BastionManager()

        with pytest.raises(BastionManagerError, match="Bastion name cannot be empty"):
            manager.create_tunnel(
                bastion_name="",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

    def test_empty_resource_group(self):
        """Test error with empty resource group."""
        manager = BastionManager()

        with pytest.raises(BastionManagerError, match="Resource group cannot be empty"):
            manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=22,
            )

    def test_invalid_port_number_low(self):
        """Test error with port number too low."""
        manager = BastionManager()

        with pytest.raises(BastionManagerError, match="Invalid port"):
            manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=0,
                remote_port=22,
            )

    def test_invalid_port_number_high(self):
        """Test error with port number too high."""
        manager = BastionManager()

        with pytest.raises(BastionManagerError, match="Invalid port"):
            manager.create_tunnel(
                bastion_name="my-bastion",
                resource_group="my-rg",
                target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                local_port=50022,
                remote_port=70000,
            )

    def test_privileged_port_warning(self, caplog):
        """Test warning when using privileged port."""
        manager = BastionManager()

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.poll.return_value = None

            # Mock the tunnel readiness check
            with patch.object(manager, "_wait_for_tunnel_ready"):
                manager.create_tunnel(
                    bastion_name="my-bastion",
                    resource_group="my-rg",
                    target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                    local_port=80,
                    remote_port=22,
                )

            # Check warning was logged
            assert "privileged port" in caplog.text.lower()

    def test_context_manager_cleanup(self):
        """Test BastionManager context manager cleans up tunnels."""
        # Arrange
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            # Act
            with BastionManager() as manager:
                # Mock the tunnel readiness check
                with patch.object(manager, "_wait_for_tunnel_ready"):
                    _tunnel = manager.create_tunnel(
                        bastion_name="my-bastion",
                        resource_group="my-rg",
                        target_vm_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
                        local_port=50022,
                        remote_port=22,
                    )

            # Assert - tunnel should be closed on context exit
            mock_process.terminate.assert_called_once()

    def test_concurrent_tunnel_creation(self):
        """Test creating multiple tunnels concurrently."""
        # Arrange
        manager = BastionManager()

        with patch("subprocess.Popen") as mock_popen:
            mock_process1 = Mock()
            mock_process1.poll.return_value = None
            mock_process2 = Mock()
            mock_process2.poll.return_value = None
            mock_popen.side_effect = [mock_process1, mock_process2]

            # Mock the tunnel readiness check
            with patch.object(manager, "_wait_for_tunnel_ready"):
                # Act
                _tunnel1 = manager.create_tunnel(
                    bastion_name="bastion1",
                    resource_group="rg1",
                    target_vm_id="/subscriptions/sub/resourceGroups/rg1/providers/Microsoft.Compute/virtualMachines/vm1",
                    local_port=50022,
                    remote_port=22,
                )
                _tunnel2 = manager.create_tunnel(
                    bastion_name="bastion2",
                    resource_group="rg2",
                    target_vm_id="/subscriptions/sub/resourceGroups/rg2/providers/Microsoft.Compute/virtualMachines/vm2",
                    local_port=50023,
                    remote_port=22,
                )

            # Assert
            assert tunnel1.local_port != tunnel2.local_port
            assert len(manager.active_tunnels) == 2
