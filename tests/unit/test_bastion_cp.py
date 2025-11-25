"""Unit tests for Bastion support in azlin cp command (Issue #415).

Tests for Bastion-routed file transfers including:
- VMSession data model with bastion tunnel info
- SessionManager bastion detection and tunnel creation
- FileTransfer rsync command building with bastion tunnels
- Integration tests for end-to-end transfers
- Tunnel lifecycle and cleanup

These tests follow TDD approach - they will FAIL until implementation is complete.

Requirements Tested:
- FR-1: Bastion Detection (auto-detect when no public IP)
- FR-2: Bastion Tunnel Management (create, bind to localhost, port allocation)
- FR-3: rsync Integration (connect via tunnel, custom port)
- FR-4: Session Manager (return tuple with BastionManager)
- FR-5: VMSession Data Model (bastion_tunnel, ssh_host, ssh_port properties)
- FR-6: Cleanup (close tunnels on success/failure)
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.modules.bastion_detector import BastionInfo
from azlin.modules.bastion_manager import BastionManager, BastionTunnel
from azlin.modules.file_transfer.exceptions import SessionNotFoundError, TransferError
from azlin.modules.file_transfer.file_transfer import FileTransfer, TransferEndpoint
from azlin.modules.file_transfer.session_manager import SessionManager, VMSession

# ============================================================================
# VMSession Data Model Tests (FR-5)
# ============================================================================


class TestVMSessionBastionSupport:
    """Test VMSession data model with bastion tunnel support."""

    def test_vmsession_with_public_ip_direct_connection(self):
        """Test VMSession with public IP (direct connection).

        Validates:
        - Direct connection type
        - ssh_host returns public_ip
        - ssh_port returns 22 (default SSH)
        - bastion_tunnel is None
        """
        # Arrange & Act
        session = VMSession(
            name="test-vm",
            public_ip="203.0.113.42",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Assert
        assert session.connection_type == "direct"
        assert session.ssh_host == "203.0.113.42"
        assert session.ssh_port == 22
        assert session.bastion_tunnel is None

    def test_vmsession_with_bastion_tunnel(self):
        """Test VMSession with bastion tunnel (no public IP).

        Validates:
        - Bastion connection type
        - ssh_host returns localhost (127.0.0.1)
        - ssh_port returns tunnel local_port
        - bastion_tunnel contains tunnel info
        """
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="bastion-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=52000,
            remote_port=22,
            process=None,  # Process not needed for data model test
        )

        # Act
        session = VMSession(
            name="test-vm",
            public_ip=None,  # No public IP - requires bastion
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        # Assert
        assert session.connection_type == "bastion"
        assert session.ssh_host == "127.0.0.1"
        assert session.ssh_port == 52000
        assert session.bastion_tunnel is not None
        assert session.bastion_tunnel.bastion_name == "my-bastion"
        assert session.bastion_tunnel.local_port == 52000

    def test_vmsession_ssh_host_property_with_public_ip(self):
        """Test ssh_host property returns public IP for direct connections."""
        # Arrange
        session = VMSession(
            name="test-vm",
            public_ip="198.51.100.10",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Act & Assert
        assert session.ssh_host == "198.51.100.10"

    def test_vmsession_ssh_host_property_with_bastion(self):
        """Test ssh_host property returns localhost for bastion connections."""
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="bastion-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=53500,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        # Act & Assert
        assert session.ssh_host == "127.0.0.1"

    def test_vmsession_ssh_port_property_direct(self):
        """Test ssh_port property returns 22 for direct connections."""
        # Arrange
        session = VMSession(
            name="test-vm",
            public_ip="198.51.100.10",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Act & Assert
        assert session.ssh_port == 22

    def test_vmsession_ssh_port_property_bastion(self):
        """Test ssh_port property returns tunnel port for bastion connections."""
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="bastion-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=54321,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        # Act & Assert
        assert session.ssh_port == 54321

    def test_vmsession_connection_type_property_direct(self):
        """Test connection_type property returns 'direct' for public IP."""
        # Arrange
        session = VMSession(
            name="test-vm",
            public_ip="198.51.100.10",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Act & Assert
        assert session.connection_type == "direct"

    def test_vmsession_connection_type_property_bastion(self):
        """Test connection_type property returns 'bastion' for tunnel."""
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="bastion-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=54321,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        # Act & Assert
        assert session.connection_type == "bastion"


# ============================================================================
# SessionManager Tests (FR-1, FR-4)
# ============================================================================


class TestSessionManagerBastionDetection:
    """Test SessionManager with bastion detection and tunnel creation."""

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_get_vm_session_with_public_ip_returns_none_for_bastion(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test get_vm_session with public IP returns (VMSession, None).

        Validates FR-4: Backward compatibility - VMs with public IP don't use bastion.
        """
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = "203.0.113.42"  # Has public IP
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Act
        session, bastion_manager = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert
        assert session.name == "test-vm"
        assert session.public_ip == "203.0.113.42"
        assert session.connection_type == "direct"
        assert bastion_manager is None
        # Bastion detection should NOT be called for VMs with public IP
        mock_bastion_detector_cls.detect_bastion_for_vm.assert_not_called()

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_get_vm_session_without_public_ip_detects_bastion(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test get_vm_session without public IP detects and uses bastion.

        Validates FR-1: Auto-detect bastion when VM has no public IP.
        Validates FR-4: Returns (VMSession, BastionManager) tuple.
        """
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None  # No public IP - needs bastion
        mock_vm.location = "westus"
        mock_vm.id = "/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager and tunnel creation
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 52000

        mock_tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm.id,
            local_port=52000,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = mock_tunnel

        # Act
        session, bastion_manager = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert
        assert session.name == "test-vm"
        assert session.public_ip is None
        assert session.connection_type == "bastion"
        assert session.bastion_tunnel is not None
        assert session.bastion_tunnel.local_port == 52000
        assert bastion_manager is not None
        assert isinstance(bastion_manager, BastionManager)

        # Verify bastion detection was called
        mock_bastion_detector_cls.detect_bastion_for_vm.assert_called_once_with(
            vm_name="test-vm",
            resource_group="test-rg",
            vm_location="westus",
        )

        # Verify tunnel creation
        mock_bastion_manager.create_tunnel.assert_called_once()

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    def test_get_vm_session_without_public_ip_no_bastion_raises_error(
        self, mock_bastion_detector_cls
    ):
        """Test get_vm_session without public IP and no bastion raises error.

        Validates FR-1: Clear error when no bastion available.
        """
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None  # No public IP
        mock_vm.location = "westus"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock bastion detection - no bastion found
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = None

        # Act & Assert
        with pytest.raises(
            SessionNotFoundError,
            match="no public IP and no bastion is available",
        ):
            SessionManager.get_vm_session(
                session_name="test-vm",
                resource_group="test-rg",
                vm_manager=mock_vm_manager,
            )

    @patch("azlin.modules.file_transfer.session_manager.VMManager")
    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_get_vm_session_bastion_tunnel_creation_flow(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls, mock_vmmanager_cls
    ):
        """Test complete bastion tunnel creation flow.

        Validates FR-2: Tunnel creation with port allocation and localhost binding.
        """
        # Arrange
        expected_vm_id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "eastus"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock VMManager.get_vm_resource_id
        mock_vmmanager_cls.get_vm_resource_id.return_value = expected_vm_id

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "prod-bastion",
            "resource_group": "test-rg",
            "location": "eastus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 55123

        mock_tunnel = BastionTunnel(
            bastion_name="prod-bastion",
            resource_group="test-rg",
            target_vm_id=expected_vm_id,
            local_port=55123,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = mock_tunnel

        # Act
        session, bastion_manager = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert - Verify tunnel creation parameters
        mock_bastion_manager.create_tunnel.assert_called_once_with(
            bastion_name="prod-bastion",
            resource_group="test-rg",
            target_vm_id=expected_vm_id,
            local_port=55123,
            remote_port=22,
            wait_for_ready=True,
        )

        # Verify session has tunnel info
        assert session.bastion_tunnel.local_port == 55123
        assert session.bastion_tunnel.remote_port == 22
        assert session.ssh_host == "127.0.0.1"
        assert session.ssh_port == 55123

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_get_vm_session_port_allocation_in_range(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test port allocation uses ephemeral range (50000-60000).

        Validates FR-2: Port allocation in safe range.
        """
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "westus"
        mock_vm.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager

        # Port should be in ephemeral range
        allocated_port = 57890
        mock_bastion_manager.get_available_port.return_value = allocated_port

        mock_tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm.id,
            local_port=allocated_port,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = mock_tunnel

        # Act
        session, _ = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert - Port is in ephemeral range
        assert 50000 <= session.ssh_port <= 60000
        assert session.ssh_port == allocated_port


# ============================================================================
# FileTransfer Tests (FR-3)
# ============================================================================


class TestFileTransferBastionSupport:
    """Test FileTransfer rsync command building with bastion support."""

    def test_build_rsync_command_direct_connection(self):
        """Test rsync command for direct connection (public IP).

        Validates: Standard rsync command without custom port.
        """
        # Arrange
        session = VMSession(
            name="test-vm",
            public_ip="203.0.113.42",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        source = TransferEndpoint(path=Path("/local/file.txt"), session=None)
        dest = TransferEndpoint(path=Path("/remote/file.txt"), session=session)

        # Act
        cmd = FileTransfer.build_rsync_command(source, dest)

        # Assert
        assert "rsync" in cmd
        assert "-avz" in cmd
        assert "-e" in cmd

        # Find SSH command argument
        ssh_cmd_idx = cmd.index("-e") + 1
        ssh_cmd = cmd[ssh_cmd_idx]

        assert "ssh" in ssh_cmd
        assert "-i /home/user/.ssh/azlin_key" in ssh_cmd
        assert "-o StrictHostKeyChecking=no" in ssh_cmd

        # Should NOT contain port specification for direct connection
        assert "-p" not in ssh_cmd

        # Verify rsync arguments
        assert "azureuser@203.0.113.42:/remote/file.txt" in cmd

    def test_build_rsync_command_bastion_connection(self):
        """Test rsync command for bastion connection.

        Validates FR-3: rsync connects via localhost tunnel with custom port.
        """
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=52000,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        source = TransferEndpoint(path=Path("/local/data.txt"), session=None)
        dest = TransferEndpoint(path=Path("/remote/data.txt"), session=session)

        # Act
        cmd = FileTransfer.build_rsync_command(source, dest)

        # Assert
        assert "rsync" in cmd
        assert "-avz" in cmd
        assert "-e" in cmd

        # Find SSH command argument
        ssh_cmd_idx = cmd.index("-e") + 1
        ssh_cmd = cmd[ssh_cmd_idx]

        # MUST include custom port for bastion tunnel
        assert "-p 52000" in ssh_cmd or "-p52000" in ssh_cmd
        assert "ssh" in ssh_cmd
        assert "-i /home/user/.ssh/azlin_key" in ssh_cmd

        # MUST disable host key checking for localhost tunnel
        assert "-o StrictHostKeyChecking=no" in ssh_cmd
        assert "-o UserKnownHostsFile=/dev/null" in ssh_cmd

        # MUST connect to localhost, NOT public IP
        assert "azureuser@127.0.0.1:/remote/data.txt" in cmd
        # Should NOT use public IP
        assert "203.0.113" not in " ".join(cmd)

    def test_transfer_endpoint_to_rsync_arg_bastion(self):
        """Test TransferEndpoint.to_rsync_arg with bastion tunnel.

        Validates FR-3: Endpoint uses 127.0.0.1 for bastion connections.
        """
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=53500,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        endpoint = TransferEndpoint(path=Path("/remote/file.txt"), session=session)

        # Act
        rsync_arg = endpoint.to_rsync_arg()

        # Assert
        assert rsync_arg == "azureuser@127.0.0.1:/remote/file.txt"

    def test_transfer_endpoint_to_rsync_arg_direct(self):
        """Test TransferEndpoint.to_rsync_arg with direct connection."""
        # Arrange
        session = VMSession(
            name="test-vm",
            public_ip="198.51.100.10",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        endpoint = TransferEndpoint(path=Path("/remote/file.txt"), session=session)

        # Act
        rsync_arg = endpoint.to_rsync_arg()

        # Assert
        assert rsync_arg == "azureuser@198.51.100.10:/remote/file.txt"

    def test_build_rsync_command_bastion_upload(self):
        """Test rsync command for uploading via bastion."""
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=51234,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        # Local -> Remote (upload)
        source = TransferEndpoint(path=Path("/local/upload.txt"), session=None)
        dest = TransferEndpoint(path=Path("/remote/upload.txt"), session=session)

        # Act
        cmd = FileTransfer.build_rsync_command(source, dest)

        # Assert
        assert cmd[-2] == "/local/upload.txt"  # Local source
        assert cmd[-1] == "azureuser@127.0.0.1:/remote/upload.txt"  # Remote dest via tunnel

    def test_build_rsync_command_bastion_download(self):
        """Test rsync command for downloading via bastion."""
        # Arrange
        tunnel_info = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=51234,
            remote_port=22,
        )

        session = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel_info,
        )

        # Remote -> Local (download)
        source = TransferEndpoint(path=Path("/remote/download.txt"), session=session)
        dest = TransferEndpoint(path=Path("/local/download.txt"), session=None)

        # Act
        cmd = FileTransfer.build_rsync_command(source, dest)

        # Assert
        assert cmd[-2] == "azureuser@127.0.0.1:/remote/download.txt"  # Remote source via tunnel
        assert cmd[-1] == "/local/download.txt"  # Local dest


# ============================================================================
# Integration Tests (FR-6)
# ============================================================================


class TestBastionCpIntegration:
    """Integration tests for end-to-end bastion file transfers."""

    @patch("azlin.modules.file_transfer.file_transfer.subprocess.run")
    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_end_to_end_transfer_via_bastion_success(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls, mock_subprocess_run
    ):
        """Test complete file transfer via bastion with cleanup.

        Validates FR-6: Tunnel cleanup after successful transfer.
        """
        # Arrange - VM without public IP
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "westus"
        mock_vm.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 52000

        mock_tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm.id,
            local_port=52000,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = mock_tunnel

        # Mock successful rsync
        mock_subprocess_run.return_value = Mock(
            returncode=0,
            stdout="sent 1234 bytes",
            stderr="",
        )

        # Act - Get session and perform transfer
        session, bastion_manager = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        source = TransferEndpoint(path=Path("/local/file.txt"), session=None)
        dest = TransferEndpoint(path=Path("/remote/file.txt"), session=session)

        try:
            result = FileTransfer.transfer(source, dest)

            # Assert - Transfer succeeded
            assert result.success is True
            assert result.bytes_transferred > 0
        finally:
            # Cleanup - MUST close tunnel
            bastion_manager.close_all_tunnels()

        # Assert - Tunnel was closed
        mock_bastion_manager.close_all_tunnels.assert_called_once()

    @patch("azlin.modules.file_transfer.session_manager.VMManager")
    @patch("azlin.modules.file_transfer.file_transfer.subprocess.run")
    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_end_to_end_transfer_via_bastion_failure_cleanup(
        self,
        mock_bastion_manager_cls,
        mock_bastion_detector_cls,
        mock_subprocess_run,
        mock_vmmanager_cls,
    ):
        """Test tunnel cleanup when transfer fails.

        Validates FR-6: Tunnel cleanup even on failure (try/finally).
        """
        # Arrange - VM without public IP
        expected_vm_id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"

        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "westus"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock VMManager.get_vm_resource_id
        mock_vmmanager_cls.get_vm_resource_id.return_value = expected_vm_id

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 52000

        mock_tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm.id,
            local_port=52000,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = mock_tunnel

        # Mock failed rsync
        mock_subprocess_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="rsync: connection refused",
        )

        # Act - Get session and attempt transfer
        session, bastion_manager = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        source = TransferEndpoint(path=Path("/local/file.txt"), session=None)
        dest = TransferEndpoint(path=Path("/remote/file.txt"), session=session)

        try:
            result = FileTransfer.transfer(source, dest)

            # Assert - Transfer failed
            assert result.success is False
            assert len(result.errors) > 0
        finally:
            # Cleanup - MUST close tunnel even on failure
            bastion_manager.close_all_tunnels()

        # Assert - Tunnel was closed even though transfer failed
        mock_bastion_manager.close_all_tunnels.assert_called_once()

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_mixed_vms_one_public_one_bastion(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test handling multiple VMs with different connection types.

        Validates: System handles both connection types correctly.
        """
        # Arrange - VM1 with public IP
        mock_vm_manager = Mock()
        mock_vm1 = Mock()
        mock_vm1.name = "vm-public"
        mock_vm1.power_state = "VM running"
        mock_vm1.public_ip = "203.0.113.42"
        mock_vm1.location = "westus"

        # VM2 without public IP
        mock_vm2 = Mock()
        mock_vm2.name = "vm-bastion"
        mock_vm2.power_state = "VM running"
        mock_vm2.public_ip = None
        mock_vm2.location = "westus"
        mock_vm2.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm-bastion"

        # Mock bastion detection - only for VM2
        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 52000

        mock_tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm2.id,
            local_port=52000,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = mock_tunnel

        # Act - Get sessions for both VMs
        mock_vm_manager.list_vms.return_value = [mock_vm1]
        session1, bastion1 = SessionManager.get_vm_session(
            session_name="vm-public",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        mock_vm_manager.list_vms.return_value = [mock_vm2]
        session2, bastion2 = SessionManager.get_vm_session(
            session_name="vm-bastion",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert - VM1 uses direct connection
        assert session1.connection_type == "direct"
        assert session1.ssh_host == "203.0.113.42"
        assert session1.ssh_port == 22
        assert bastion1 is None

        # Assert - VM2 uses bastion
        assert session2.connection_type == "bastion"
        assert session2.ssh_host == "127.0.0.1"
        assert session2.ssh_port == 52000
        assert bastion2 is not None


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestBastionCpEdgeCases:
    """Test edge cases and error conditions for bastion cp."""

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    def test_vm_without_public_ip_no_bastion_clear_error(self, mock_bastion_detector_cls):
        """Test clear error message when VM has no IP and no bastion available.

        Validates FR-1: Clear error message when bastion unavailable.
        """
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "isolated-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "eastus"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # No bastion available
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = None

        # Act & Assert
        with pytest.raises(
            SessionNotFoundError,
            match="(no public IP|bastion|not accessible)",
        ) as exc_info:
            SessionManager.get_vm_session(
                session_name="isolated-vm",
                resource_group="test-rg",
                vm_manager=mock_vm_manager,
            )

        # Error message should be clear and actionable
        error_msg = str(exc_info.value).lower()
        assert "public ip" in error_msg or "bastion" in error_msg

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_bastion_tunnel_creation_timeout(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test handling of bastion tunnel creation timeout."""
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "westus"
        mock_vm.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "slow-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager - tunnel creation fails
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 52000
        mock_bastion_manager.create_tunnel.side_effect = TimeoutError("Tunnel creation timed out")

        # Act & Assert
        with pytest.raises((TimeoutError, TransferError), match="[Tt]imed? out|[Tt]imeout"):
            SessionManager.get_vm_session(
                session_name="test-vm",
                resource_group="test-rg",
                vm_manager=mock_vm_manager,
            )

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_port_already_in_use(self, mock_bastion_manager_cls, mock_bastion_detector_cls):
        """Test handling when allocated port is already in use."""
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "westus"
        mock_vm.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        # Mock bastion detection
        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager - port conflict
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.side_effect = OSError("Address already in use")

        # Act & Assert
        with pytest.raises((OSError, TransferError), match="[Aa]ddress|[Pp]ort"):
            SessionManager.get_vm_session(
                session_name="test-vm",
                resource_group="test-rg",
                vm_manager=mock_vm_manager,
            )

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_multiple_concurrent_bastion_tunnels(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test handling multiple concurrent bastion tunnels.

        Validates: System can manage multiple tunnels simultaneously.
        """
        # Arrange - Two VMs without public IP
        mock_vm_manager = Mock()

        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        # Mock bastion manager with different ports for each VM
        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager

        # Return different ports for each call
        port_counter = [52000]

        def get_next_port():
            port = port_counter[0]
            port_counter[0] += 1
            return port

        mock_bastion_manager.get_available_port.side_effect = get_next_port

        # VM 1
        mock_vm1 = Mock()
        mock_vm1.name = "vm1"
        mock_vm1.power_state = "VM running"
        mock_vm1.public_ip = None
        mock_vm1.location = "westus"
        mock_vm1.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1"

        tunnel1 = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm1.id,
            local_port=52000,
            remote_port=22,
        )

        # VM 2
        mock_vm2 = Mock()
        mock_vm2.name = "vm2"
        mock_vm2.power_state = "VM running"
        mock_vm2.public_ip = None
        mock_vm2.location = "westus"
        mock_vm2.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm2"

        tunnel2 = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm2.id,
            local_port=52001,
            remote_port=22,
        )

        mock_bastion_manager.create_tunnel.side_effect = [tunnel1, tunnel2]

        # Act - Create sessions for both VMs
        mock_vm_manager.list_vms.return_value = [mock_vm1]
        session1, bastion1 = SessionManager.get_vm_session(
            session_name="vm1",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        mock_vm_manager.list_vms.return_value = [mock_vm2]
        session2, bastion2 = SessionManager.get_vm_session(
            session_name="vm2",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert - Each VM has different tunnel port
        assert session1.ssh_port == 52000
        assert session2.ssh_port == 52001
        assert session1.ssh_port != session2.ssh_port

    def test_vmsession_invalid_without_public_ip_or_tunnel(self):
        """Test VMSession validation - must have either public IP or tunnel."""
        # This test validates that VMSession enforces the constraint:
        # Either public_ip OR bastion_tunnel must be set

        # Act & Assert
        with pytest.raises((ValueError, AssertionError), match="public IP|tunnel|connection"):
            VMSession(
                name="invalid-vm",
                public_ip=None,  # No public IP
                user="azureuser",
                key_path="/home/user/.ssh/azlin_key",
                resource_group="test-rg",
                bastion_tunnel=None,  # No tunnel either - INVALID
            )

    @patch("azlin.modules.file_transfer.session_manager.BastionDetector")
    @patch("azlin.modules.file_transfer.session_manager.BastionManager")
    def test_bastion_tunnel_localhost_binding_security(
        self, mock_bastion_manager_cls, mock_bastion_detector_cls
    ):
        """Test that bastion tunnels MUST bind to localhost only (security).

        Validates FR-2: Localhost-only binding for security.
        """
        # Arrange
        mock_vm_manager = Mock()
        mock_vm = Mock()
        mock_vm.name = "test-vm"
        mock_vm.power_state = "VM running"
        mock_vm.public_ip = None
        mock_vm.location = "westus"
        mock_vm.id = "/subscriptions/sub1/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
        mock_vm_manager.list_vms.return_value = [mock_vm]

        bastion_info: BastionInfo = {
            "name": "my-bastion",
            "resource_group": "test-rg",
            "location": "westus",
        }
        mock_bastion_detector_cls.detect_bastion_for_vm.return_value = bastion_info

        mock_bastion_manager = Mock(spec=BastionManager)
        mock_bastion_manager_cls.return_value = mock_bastion_manager
        mock_bastion_manager.get_available_port.return_value = 52000

        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id=mock_vm.id,
            local_port=52000,
            remote_port=22,
        )
        mock_bastion_manager.create_tunnel.return_value = tunnel

        # Act
        session, _ = SessionManager.get_vm_session(
            session_name="test-vm",
            resource_group="test-rg",
            vm_manager=mock_vm_manager,
        )

        # Assert - ssh_host MUST be localhost
        assert session.ssh_host == "127.0.0.1"
        assert session.ssh_host != "0.0.0.0"  # NOT all interfaces  # noqa: S104
        assert session.ssh_host != mock_vm.public_ip  # NOT public IP


# ============================================================================
# Property and Boundary Tests
# ============================================================================


class TestVMSessionProperties:
    """Test VMSession property methods and edge cases."""

    def test_ssh_host_property_exists(self):
        """Test ssh_host property is accessible."""
        session = VMSession(
            name="test-vm",
            public_ip="203.0.113.42",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Property should be accessible
        assert hasattr(session, "ssh_host")
        assert callable(getattr(type(session), "ssh_host", None).__get__)

    def test_ssh_port_property_exists(self):
        """Test ssh_port property is accessible."""
        session = VMSession(
            name="test-vm",
            public_ip="203.0.113.42",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Property should be accessible
        assert hasattr(session, "ssh_port")
        assert callable(getattr(type(session), "ssh_port", None).__get__)

    def test_connection_type_property_exists(self):
        """Test connection_type property is accessible."""
        session = VMSession(
            name="test-vm",
            public_ip="203.0.113.42",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        # Property should be accessible
        assert hasattr(session, "connection_type")
        assert callable(getattr(type(session), "connection_type", None).__get__)

    def test_connection_type_returns_string(self):
        """Test connection_type returns string literal."""
        # Direct connection
        session_direct = VMSession(
            name="test-vm",
            public_ip="203.0.113.42",
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=None,
        )

        assert isinstance(session_direct.connection_type, str)
        assert session_direct.connection_type in ["direct", "bastion"]

        # Bastion connection
        tunnel = BastionTunnel(
            bastion_name="my-bastion",
            resource_group="test-rg",
            target_vm_id="/subscriptions/xxx/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
            local_port=52000,
            remote_port=22,
        )

        session_bastion = VMSession(
            name="test-vm",
            public_ip=None,
            user="azureuser",
            key_path="/home/user/.ssh/azlin_key",
            resource_group="test-rg",
            bastion_tunnel=tunnel,
        )

        assert isinstance(session_bastion.connection_type, str)
        assert session_bastion.connection_type in ["direct", "bastion"]
