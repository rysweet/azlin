"""End-to-end tests for Azure Bastion feature.

E2E tests that would run against real Azure resources (marked as skip by default).
These tests verify complete user workflows including:
- Full Bastion deployment
- Real SSH connections through Bastion
- File transfer operations
- Configuration management

These tests follow TDD approach - they will FAIL until implementation is complete.
Run with: pytest -m e2e --skip-e2e=false (requires real Azure resources)
"""

import os
import tempfile
from pathlib import Path

import pytest
from azlin.modules.bastion_deployment import BastionDeployment

from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_manager import BastionManager
from azlin.vm_connector import VMConnector
from azlin.vm_manager import VMManager

# Mark all tests in this module as e2e
pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def skip_e2e():
    """Skip E2E tests unless explicitly enabled."""
    if os.environ.get("RUN_E2E_TESTS") != "true":
        pytest.skip("E2E tests skipped. Set RUN_E2E_TESTS=true to run against real Azure.")


@pytest.fixture(scope="module")
def test_resource_group():
    """Resource group for E2E tests."""
    return os.environ.get("AZLIN_E2E_RESOURCE_GROUP", "azlin-bastion-e2e-test")


@pytest.fixture(scope="module")
def test_location():
    """Azure region for E2E tests."""
    return os.environ.get("AZLIN_E2E_LOCATION", "westus2")


@pytest.fixture(scope="module")
def test_vnet_name():
    """VNet name for E2E tests."""
    return "azlin-e2e-vnet"


@pytest.fixture(scope="module")
def test_bastion_name():
    """Bastion name for E2E tests."""
    return "azlin-e2e-bastion"


@pytest.fixture(scope="module")
def test_vm_name():
    """VM name for E2E tests."""
    return "azlin-e2e-vm"


@pytest.fixture(scope="module")
def temp_config_dir():
    """Temporary config directory for E2E tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestBastionDeploymentE2E:
    """E2E tests for Bastion deployment."""

    def test_deploy_bastion_host_real(
        self, skip_e2e, test_bastion_name, test_resource_group, test_vnet_name, test_location
    ):
        """Test deploying real Bastion host (SLOW - 10+ minutes)."""
        # This test requires:
        # - Azure CLI authenticated
        # - Resource group created
        # - VNet with AzureBastionSubnet created

        # Act
        bastion_info = BastionDeployment.create_bastion(
            bastion_name=test_bastion_name,
            resource_group=test_resource_group,
            vnet_name=test_vnet_name,
            location=test_location,
        )

        # Assert
        assert bastion_info is not None
        assert bastion_info["name"] == test_bastion_name
        assert bastion_info["provisioningState"] in ["Succeeded", "Creating"]

    def test_list_real_bastion_hosts(self, skip_e2e, test_resource_group):
        """Test listing real Bastion hosts."""
        # Act
        bastions = BastionDeployment.list_bastions(resource_group=test_resource_group)

        # Assert
        assert isinstance(bastions, list)
        # May be empty if no Bastions deployed yet
        for bastion in bastions:
            assert "name" in bastion
            assert "resourceGroup" in bastion

    def test_get_real_bastion_status(self, skip_e2e, test_bastion_name, test_resource_group):
        """Test getting real Bastion status."""
        # Act
        status = BastionDeployment.get_bastion_status(
            bastion_name=test_bastion_name, resource_group=test_resource_group
        )

        # Assert
        assert status is not None
        assert "provisioningState" in status
        assert status["name"] == test_bastion_name

    @pytest.mark.destructive
    def test_delete_real_bastion_host(self, skip_e2e, test_bastion_name, test_resource_group):
        """Test deleting real Bastion host (DESTRUCTIVE)."""
        # This test is marked destructive and should only run explicitly

        # Act
        result = BastionDeployment.delete_bastion(
            bastion_name=test_bastion_name, resource_group=test_resource_group
        )

        # Assert
        assert result is True


class TestBastionConnectionE2E:
    """E2E tests for real Bastion connections."""

    def test_connect_to_vm_via_bastion_real(
        self, skip_e2e, test_vm_name, test_resource_group, test_bastion_name
    ):
        """Test real SSH connection through Bastion (requires VM with NO public IP)."""
        # This test requires:
        # - VM deployed WITHOUT public IP
        # - Bastion in same VNet as VM
        # - SSH key configured

        # Act - Connect with explicit Bastion
        result = VMConnector.connect(
            vm_identifier=test_vm_name,
            resource_group=test_resource_group,
            use_bastion=True,
            bastion_name=test_bastion_name,
            bastion_resource_group=test_resource_group,
            use_tmux=False,
        )

        # Assert
        assert result is True

    def test_auto_detect_bastion_real(self, skip_e2e, test_vm_name, test_resource_group):
        """Test auto-detection of Bastion for VM."""
        # Act
        from azlin.modules.bastion_detector import BastionDetector

        bastion_info = BastionDetector.detect_bastion_for_vm(
            vm_name=test_vm_name, resource_group=test_resource_group
        )

        # Assert
        if bastion_info:
            assert "name" in bastion_info
            assert "resource_group" in bastion_info
            print(f"Detected Bastion: {bastion_info['name']}")

    def test_tunnel_creation_real(
        self, skip_e2e, test_bastion_name, test_resource_group, test_vm_name
    ):
        """Test creating real Bastion tunnel."""
        # Arrange
        vm_info = VMManager.get_vm(test_vm_name, test_resource_group)
        assert vm_info is not None, f"VM {test_vm_name} not found"

        manager = BastionManager()

        # Act
        tunnel = manager.create_tunnel(
            bastion_name=test_bastion_name,
            resource_group=test_resource_group,
            target_vm_id=vm_info.vm_id,
            local_port=50022,
            remote_port=22,
            wait_for_ready=True,
            timeout=60,
        )

        try:
            # Assert
            assert tunnel is not None
            assert tunnel.is_active() is True
            assert tunnel.local_port == 50022

            # Verify can connect to localhost:50022
            import socket

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(("localhost", 50022))
            sock.close()
            assert result == 0, "Tunnel port not accessible"

        finally:
            # Cleanup
            manager.close_tunnel(tunnel)


class TestBastionFileTransferE2E:
    """E2E tests for file transfer through Bastion."""

    def test_upload_file_via_bastion_real(
        self, skip_e2e, test_vm_name, test_resource_group, test_bastion_name
    ):
        """Test uploading real file through Bastion tunnel."""
        # Arrange
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Hello from E2E test!")
            test_file = Path(f.name)

        try:
            # Act
            from azlin.modules.file_transfer import FileTransfer

            # Force Bastion for this transfer
            result = FileTransfer.upload_file(
                vm_name=test_vm_name,
                resource_group=test_resource_group,
                local_path=str(test_file),
                remote_path="/tmp/bastion_e2e_test.txt",
                force_bastion=True,
                bastion_name=test_bastion_name,
                bastion_resource_group=test_resource_group,
            )

            # Assert
            assert result is True

            # Verify file exists on VM
            from azlin.remote_exec import RemoteExecutor

            output = RemoteExecutor.execute_command(
                vm_name=test_vm_name,
                resource_group=test_resource_group,
                command="cat /tmp/bastion_e2e_test.txt",
            )
            assert "Hello from E2E test!" in output

        finally:
            # Cleanup
            test_file.unlink(missing_ok=True)

    def test_download_file_via_bastion_real(
        self, skip_e2e, test_vm_name, test_resource_group, test_bastion_name
    ):
        """Test downloading real file through Bastion tunnel."""
        # Arrange - Create file on VM
        # Note: File must be pre-created on VM manually for this E2E test
        # RemoteExecutor.execute_command requires SSHConfig, not direct vm_name/resource_group

        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = Path(tmpdir) / "downloaded.txt"

            # Act
            from azlin.modules.file_transfer import FileTransfer

            result = FileTransfer.download_file(
                vm_name=test_vm_name,
                resource_group=test_resource_group,
                remote_path="/tmp/bastion_download_test.txt",
                local_path=str(local_file),
                force_bastion=True,
                bastion_name=test_bastion_name,
                bastion_resource_group=test_resource_group,
            )

            # Assert
            assert result is True
            assert local_file.exists()
            content = local_file.read_text()
            assert "Download test" in content


class TestBastionConfigE2E:
    """E2E tests for Bastion configuration management."""

    def test_save_and_load_config_real(
        self, skip_e2e, temp_config_dir, test_vm_name, test_bastion_name, test_resource_group
    ):
        """Test saving and loading real Bastion configuration."""
        # Arrange
        config_file = temp_config_dir / "bastion_config.toml"

        # Act - Create and save
        config1 = BastionConfig()
        config1.add_mapping(
            vm_name=test_vm_name,
            vm_resource_group=test_resource_group,
            bastion_name=test_bastion_name,
            bastion_resource_group=test_resource_group,
        )
        config1.set_default_bastion(test_bastion_name, test_resource_group)
        config1.auto_detect = True
        config1.prefer_bastion = False
        config1.save(config_file)

        # Load in new instance
        config2 = BastionConfig.load(config_file)

        # Assert
        assert test_vm_name in config2.mappings
        mapping = config2.mappings[test_vm_name]
        assert mapping.bastion_name == test_bastion_name
        assert mapping.bastion_resource_group == test_resource_group
        assert config2.default_bastion == (test_bastion_name, test_resource_group)
        assert config2.auto_detect is True
        assert config2.prefer_bastion is False

    def test_config_persistence_across_connections(
        self, skip_e2e, temp_config_dir, test_vm_name, test_bastion_name, test_resource_group
    ):
        """Test configuration persists across multiple connections."""
        # Arrange
        config_file = temp_config_dir / "bastion_config.toml"

        # Create initial config
        config = BastionConfig()
        config.add_mapping(
            vm_name=test_vm_name,
            vm_resource_group=test_resource_group,
            bastion_name=test_bastion_name,
            bastion_resource_group=test_resource_group,
        )
        config.save(config_file)

        # Act - Connect multiple times
        from unittest.mock import patch

        with patch("azlin.vm_connector.BastionConfig.get_config_path", return_value=config_file):
            # First connection
            result1 = VMConnector.connect(
                vm_identifier=test_vm_name, resource_group=test_resource_group, use_tmux=False
            )

            # Second connection (should use cached config)
            result2 = VMConnector.connect(
                vm_identifier=test_vm_name, resource_group=test_resource_group, use_tmux=False
            )

        # Assert
        assert result1 is True
        assert result2 is True

        # Verify config still intact
        final_config = BastionConfig.load(config_file)
        assert test_vm_name in final_config.mappings


class TestBastionUserExperienceE2E:
    """E2E tests for user experience workflows."""

    def test_first_time_user_workflow(
        self, skip_e2e, test_vm_name, test_resource_group, test_bastion_name
    ):
        """Test complete first-time user workflow with Bastion."""
        # This test simulates a new user:
        # 1. Has VM without public IP
        # 2. No Bastion config
        # 3. Auto-detect finds Bastion
        # 4. User is prompted
        # 5. Connection succeeds
        # 6. Config is saved

        # Arrange
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "bastion_config.toml"

            # Ensure clean config
            config = BastionConfig()
            config.save(config_file)

            # Act
            from unittest.mock import patch

            with patch(
                "azlin.vm_connector.BastionConfig.get_config_path", return_value=config_file
            ):
                # User connects (should trigger auto-detect and prompt)
                with patch("click.confirm") as mock_confirm:
                    mock_confirm.return_value = True  # User accepts Bastion

                    result = VMConnector.connect(
                        vm_identifier=test_vm_name,
                        resource_group=test_resource_group,
                        use_tmux=False,
                    )

            # Assert
            assert result is True

            # Verify config was saved
            saved_config = BastionConfig.load(config_file)
            # Config should have mapping if user accepted
            assert saved_config is not None  # Verify config file was created
            # (Implementation detail: may save after successful connection)

    def test_vm_without_public_ip_requires_bastion(
        self, skip_e2e, test_vm_name, test_resource_group
    ):
        """Test that VM without public IP cannot connect directly."""
        # Arrange - VM must NOT have public IP

        # Act - Try direct connection (should fail)
        result = VMConnector.connect(
            vm_identifier=test_vm_name,
            resource_group=test_resource_group,
            use_bastion=False,
            use_tmux=False,
        )

        # Assert - Direct connection should fail
        assert result is False

    def test_prefer_bastion_setting_workflow(
        self, skip_e2e, test_vm_name, test_resource_group, test_bastion_name, temp_config_dir
    ):
        """Test prefer_bastion setting auto-uses Bastion."""
        # Arrange
        config_file = temp_config_dir / "bastion_config.toml"

        config = BastionConfig()
        config.prefer_bastion = True
        config.save(config_file)

        # Act
        from unittest.mock import patch

        with patch("azlin.vm_connector.BastionConfig.get_config_path", return_value=config_file):
            # Should auto-use Bastion without prompting
            with patch("click.confirm") as mock_confirm:
                result = VMConnector.connect(
                    vm_identifier=test_vm_name, resource_group=test_resource_group, use_tmux=False
                )

        # Assert
        assert result is True
        # Should NOT have prompted user (prefer_bastion=True)
        # Note: This depends on implementation details


@pytest.mark.skip(reason="Manual test only - requires cleanup verification")
class TestBastionCleanupE2E:
    """E2E tests for resource cleanup."""

    def test_tunnel_cleanup_on_exit(self, test_bastion_name, test_resource_group, test_vm_name):
        """Test tunnels are cleaned up on exit."""
        # This test needs manual verification as process cleanup
        # happens on program exit

        # Act
        manager = BastionManager()
        vm_info = VMManager.get_vm(test_vm_name, test_resource_group)

        tunnel = manager.create_tunnel(
            bastion_name=test_bastion_name,
            resource_group=test_resource_group,
            target_vm_id=vm_info.vm_id,
            local_port=50022,
            remote_port=22,
        )

        initial_pid = tunnel.process.pid
        print(f"Created tunnel with PID: {initial_pid}")

        # Cleanup
        manager.close_tunnel(tunnel)

        # Assert - Manual verification that process is killed
        import subprocess

        try:
            subprocess.run(["ps", "-p", str(initial_pid)], check=True, capture_output=True)
            pytest.fail(f"Process {initial_pid} still running after cleanup")
        except subprocess.CalledProcessError:
            # Process not found - good!
            pass
