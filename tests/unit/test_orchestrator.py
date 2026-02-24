"""Tests for azlin.orchestrator module.

Tests the CLIOrchestrator class which coordinates the full VM provisioning
workflow. All external dependencies (Azure, SSH, config) are mocked to test
orchestration logic in isolation.

Proportional testing: ~600 LOC tests for ~1,983 LOC implementation (~0.3:1).
Focused on public API, error handling, and dispatch logic.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.home_sync import SyncResult
from azlin.modules.notifications import NotificationResult
from azlin.modules.prerequisites import PrerequisiteResult
from azlin.modules.ssh_keys import SSHKeyPair
from azlin.orchestrator import AzlinError, CLIOrchestrator
from azlin.vm_provisioning import VMDetails

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vm_details_public_ip() -> VMDetails:
    """VM details with a public IP (direct SSH path)."""
    return VMDetails(
        name="azlin-vm-12345",
        resource_group="azlin-rg-12345",
        location="eastus",
        size="Standard_D2s_v3",
        public_ip="10.0.0.1",
        private_ip="192.168.1.10",
        state="Running",
        id="/subscriptions/sub-1/resourceGroups/azlin-rg-12345/providers/Microsoft.Compute/virtualMachines/azlin-vm-12345",
    )


@pytest.fixture
def vm_details_private_only() -> VMDetails:
    """VM details with no public IP (Bastion path)."""
    return VMDetails(
        name="azlin-vm-99999",
        resource_group="azlin-rg-99999",
        location="eastus",
        size="Standard_D2s_v3",
        public_ip=None,
        private_ip="192.168.1.20",
        state="Running",
        id="/subscriptions/sub-1/resourceGroups/azlin-rg-99999/providers/Microsoft.Compute/virtualMachines/azlin-vm-99999",
    )


@pytest.fixture
def ssh_key_pair(tmp_path: Path) -> SSHKeyPair:
    """Create a temporary SSH key pair for tests."""
    private = tmp_path / "id_azlin"
    public = tmp_path / "id_azlin.pub"
    private.write_text("FAKE-PRIVATE-KEY")
    public.write_text("ssh-rsa AAAAB3... test@azlin")
    return SSHKeyPair(
        private_path=private,
        public_path=public,
        public_key_content="ssh-rsa AAAAB3... test@azlin",
    )


@pytest.fixture
def orchestrator() -> CLIOrchestrator:
    """Create a basic CLIOrchestrator with default settings."""
    with (
        patch("azlin.orchestrator.AzureAuthenticator"),
        patch("azlin.orchestrator.VMProvisioner"),
        patch("azlin.orchestrator.ProgressDisplay"),
    ):
        return CLIOrchestrator(
            repo=None,
            vm_size="Standard_D2s_v3",
            region="eastus",
            auto_connect=False,
            no_nfs=True,
            no_bastion=True,
            auto_approve=True,
        )


@pytest.fixture
def orchestrator_with_repo() -> CLIOrchestrator:
    """CLIOrchestrator with a repo configured."""
    with (
        patch("azlin.orchestrator.AzureAuthenticator"),
        patch("azlin.orchestrator.VMProvisioner"),
        patch("azlin.orchestrator.ProgressDisplay"),
    ):
        return CLIOrchestrator(
            repo="https://github.com/test/repo",
            vm_size="Standard_D2s_v3",
            region="eastus",
            auto_connect=False,
            no_nfs=True,
            no_bastion=True,
            auto_approve=True,
        )


# ---------------------------------------------------------------------------
# AzlinError
# ---------------------------------------------------------------------------


class TestAzlinError:
    """Test AzlinError exception class."""

    def test_azlin_error_is_exception(self) -> None:
        err = AzlinError("something broke")
        assert isinstance(err, Exception)
        assert str(err) == "something broke"

    def test_azlin_error_has_exit_code(self) -> None:
        err = AzlinError("fail")
        assert err.exit_code == 1


# ---------------------------------------------------------------------------
# CLIOrchestrator.__init__
# ---------------------------------------------------------------------------


class TestCLIOrchestratorInit:
    """Test CLIOrchestrator initialization and attribute storage."""

    def test_default_attributes(self, orchestrator: CLIOrchestrator) -> None:
        assert orchestrator.repo is None
        assert orchestrator.vm_size == "Standard_D2s_v3"
        assert orchestrator.region == "eastus"
        assert orchestrator.auto_connect is False
        assert orchestrator.no_nfs is True
        assert orchestrator.no_bastion is True
        assert orchestrator.auto_approve is True
        assert orchestrator.vm_details is None
        assert orchestrator.ssh_keys is None
        assert orchestrator.bastion_info is None

    def test_repo_stored(self, orchestrator_with_repo: CLIOrchestrator) -> None:
        assert orchestrator_with_repo.repo == "https://github.com/test/repo"

    def test_session_name_stored(self) -> None:
        with (
            patch("azlin.orchestrator.AzureAuthenticator"),
            patch("azlin.orchestrator.VMProvisioner"),
            patch("azlin.orchestrator.ProgressDisplay"),
        ):
            orch = CLIOrchestrator(session_name="my-session", no_nfs=True)
        assert orch.session_name == "my-session"

    def test_home_disk_attributes(self) -> None:
        with (
            patch("azlin.orchestrator.AzureAuthenticator"),
            patch("azlin.orchestrator.VMProvisioner"),
            patch("azlin.orchestrator.ProgressDisplay"),
        ):
            orch = CLIOrchestrator(home_disk_size=200, no_home_disk=True, no_nfs=True)
        assert orch.home_disk_size == 200
        assert orch.no_home_disk is True

    def test_tmp_disk_attributes(self) -> None:
        with (
            patch("azlin.orchestrator.AzureAuthenticator"),
            patch("azlin.orchestrator.VMProvisioner"),
            patch("azlin.orchestrator.ProgressDisplay"),
        ):
            orch = CLIOrchestrator(tmp_disk_size=128, no_nfs=True)
        assert orch.tmp_disk_size == 128

    def test_nfs_storage_attribute(self) -> None:
        with (
            patch("azlin.orchestrator.AzureAuthenticator"),
            patch("azlin.orchestrator.VMProvisioner"),
            patch("azlin.orchestrator.ProgressDisplay"),
        ):
            orch = CLIOrchestrator(nfs_storage="my-nfs", no_nfs=False)
        assert orch.nfs_storage == "my-nfs"
        assert orch.no_nfs is False

    def test_bastion_name_attribute(self) -> None:
        with (
            patch("azlin.orchestrator.AzureAuthenticator"),
            patch("azlin.orchestrator.VMProvisioner"),
            patch("azlin.orchestrator.ProgressDisplay"),
        ):
            orch = CLIOrchestrator(bastion_name="my-bastion", no_nfs=True)
        assert orch.bastion_name == "my-bastion"


# ---------------------------------------------------------------------------
# CLIOrchestrator._check_prerequisites
# ---------------------------------------------------------------------------


class TestCheckPrerequisites:
    """Test prerequisite checking logic."""

    @patch("azlin.orchestrator.PrerequisiteChecker.check_all")
    def test_passes_when_all_available(
        self, mock_check: MagicMock, orchestrator: CLIOrchestrator
    ) -> None:
        mock_check.return_value = PrerequisiteResult(
            all_available=True,
            missing=[],
            available=["az", "ssh", "git"],
            platform_name="linux",
        )
        # Should not raise
        orchestrator._check_prerequisites()
        mock_check.assert_called_once()

    @patch("azlin.orchestrator.click.echo")
    @patch("azlin.orchestrator.PrerequisiteChecker.format_missing_message")
    @patch("azlin.orchestrator.PrerequisiteChecker.check_all")
    def test_raises_when_missing_tools(
        self,
        mock_check: MagicMock,
        mock_format: MagicMock,
        mock_echo: MagicMock,
        orchestrator: CLIOrchestrator,
    ) -> None:
        mock_check.return_value = PrerequisiteResult(
            all_available=False,
            missing=["az"],
            available=["ssh", "git"],
            platform_name="linux",
        )
        mock_format.return_value = "Missing: az"

        from azlin.modules.prerequisites import PrerequisiteError

        with pytest.raises(PrerequisiteError, match="Missing required tools.*az"):
            orchestrator._check_prerequisites()


# ---------------------------------------------------------------------------
# CLIOrchestrator._authenticate_azure
# ---------------------------------------------------------------------------


class TestAuthenticateAzure:
    """Test Azure authentication flow."""

    def test_returns_subscription_id(self, orchestrator: CLIOrchestrator) -> None:
        orchestrator.auth.check_az_cli_available.return_value = True
        orchestrator.auth.get_subscription_id.return_value = "sub-abc-123"

        result = orchestrator._authenticate_azure()

        assert result == "sub-abc-123"
        orchestrator.auth.get_credentials.assert_called_once()

    def test_raises_when_az_cli_unavailable(self, orchestrator: CLIOrchestrator) -> None:
        orchestrator.auth.check_az_cli_available.return_value = False

        from azlin.azure_auth import AuthenticationError

        with pytest.raises(AuthenticationError, match="Azure CLI not available"):
            orchestrator._authenticate_azure()


# ---------------------------------------------------------------------------
# CLIOrchestrator._setup_ssh_keys
# ---------------------------------------------------------------------------


class TestSetupSSHKeys:
    """Test SSH key setup."""

    @patch("azlin.orchestrator.SSHKeyManager.ensure_key_exists")
    def test_returns_key_pair_and_stores_path(
        self, mock_ensure: MagicMock, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        mock_ensure.return_value = ssh_key_pair

        result = orchestrator._setup_ssh_keys()

        assert result is ssh_key_pair
        assert orchestrator.ssh_keys == ssh_key_pair.private_path


# ---------------------------------------------------------------------------
# CLIOrchestrator._store_key_in_vault_auto
# ---------------------------------------------------------------------------


class TestStoreKeyInVaultAuto:
    """Test Key Vault storage (silent, never blocks provisioning)."""

    @patch("azlin.orchestrator.create_key_vault_manager_with_auto_setup")
    def test_stores_key_successfully(
        self, mock_create: MagicMock, orchestrator: CLIOrchestrator, tmp_path: Path
    ) -> None:
        mock_manager = MagicMock()
        mock_create.return_value = mock_manager
        key_path = tmp_path / "key"
        key_path.write_text("key")

        orchestrator._store_key_in_vault_auto(
            "vm-1", key_path, "sub-1", "tenant-1", "rg-1", "eastus"
        )

        mock_manager.store_key.assert_called_once_with("vm-1", key_path)

    @patch("azlin.orchestrator.create_key_vault_manager_with_auto_setup")
    def test_silently_handles_keyvault_error(
        self, mock_create: MagicMock, orchestrator: CLIOrchestrator, tmp_path: Path
    ) -> None:
        from azlin.modules.ssh_key_vault import KeyVaultError

        mock_create.side_effect = KeyVaultError("vault not found")
        key_path = tmp_path / "key"
        key_path.write_text("key")

        # Should NOT raise
        orchestrator._store_key_in_vault_auto(
            "vm-1", key_path, "sub-1", "tenant-1", "rg-1", "eastus"
        )

    @patch("azlin.orchestrator.create_key_vault_manager_with_auto_setup")
    def test_silently_handles_generic_error(
        self, mock_create: MagicMock, orchestrator: CLIOrchestrator, tmp_path: Path
    ) -> None:
        mock_create.side_effect = RuntimeError("unexpected")
        key_path = tmp_path / "key"
        key_path.write_text("key")

        # Should NOT raise
        orchestrator._store_key_in_vault_auto(
            "vm-1", key_path, "sub-1", "tenant-1", "rg-1", "eastus"
        )


# ---------------------------------------------------------------------------
# CLIOrchestrator._send_notification / _send_notification_error
# ---------------------------------------------------------------------------


class TestNotifications:
    """Test notification sending logic."""

    @patch("azlin.orchestrator.NotificationHandler.send_completion_notification")
    def test_send_notification_success(
        self, mock_send: MagicMock, orchestrator: CLIOrchestrator, vm_details_public_ip: VMDetails
    ) -> None:
        mock_send.return_value = NotificationResult(sent=True, message="ok")

        orchestrator._send_notification(vm_details_public_ip, success=True)

        mock_send.assert_called_once_with(
            vm_details_public_ip.name, vm_details_public_ip.public_ip, success=True
        )

    @patch("azlin.orchestrator.NotificationHandler.send_completion_notification")
    def test_send_notification_uses_unknown_ip_when_no_public_ip(
        self,
        mock_send: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_private_only: VMDetails,
    ) -> None:
        mock_send.return_value = NotificationResult(sent=False, message="no ip")

        orchestrator._send_notification(vm_details_private_only)

        mock_send.assert_called_once_with(vm_details_private_only.name, "unknown", success=True)

    @patch("azlin.orchestrator.NotificationHandler.send_error_notification")
    def test_send_notification_error(
        self, mock_send: MagicMock, orchestrator: CLIOrchestrator
    ) -> None:
        mock_send.return_value = NotificationResult(sent=True, message="sent")

        orchestrator._send_notification_error("boom")

        mock_send.assert_called_once_with("boom")


# ---------------------------------------------------------------------------
# CLIOrchestrator._display_connection_info
# ---------------------------------------------------------------------------


class TestDisplayConnectionInfo:
    """Test connection info display."""

    @patch("azlin.orchestrator.click.echo")
    def test_displays_vm_details(
        self, mock_echo: MagicMock, orchestrator: CLIOrchestrator, vm_details_public_ip: VMDetails
    ) -> None:
        orchestrator._display_connection_info(vm_details_public_ip)

        # Check that click.echo was called multiple times with expected content
        all_output = " ".join(str(call.args[0]) for call in mock_echo.call_args_list if call.args)
        assert "azlin-vm-12345" in all_output
        assert "10.0.0.1" in all_output
        assert "eastus" in all_output

    @patch("azlin.orchestrator.click.echo")
    def test_displays_repo_when_configured(
        self,
        mock_echo: MagicMock,
        orchestrator_with_repo: CLIOrchestrator,
        vm_details_public_ip: VMDetails,
    ) -> None:
        orchestrator_with_repo._display_connection_info(vm_details_public_ip)

        all_output = " ".join(str(call.args[0]) for call in mock_echo.call_args_list if call.args)
        assert "https://github.com/test/repo" in all_output


# ---------------------------------------------------------------------------
# CLIOrchestrator._cleanup_on_failure
# ---------------------------------------------------------------------------


class TestCleanupOnFailure:
    """Test cleanup on failure behavior."""

    @patch("azlin.orchestrator.click.echo")
    def test_displays_cleanup_info_when_vm_exists(
        self,
        mock_echo: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_public_ip: VMDetails,
    ) -> None:
        orchestrator.vm_details = vm_details_public_ip

        orchestrator._cleanup_on_failure()

        all_output = " ".join(str(call.args[0]) for call in mock_echo.call_args_list if call.args)
        assert "azlin-vm-12345" in all_output
        assert "az group delete" in all_output

    @patch("azlin.orchestrator.click.echo")
    def test_noop_when_no_vm(self, mock_echo: MagicMock, orchestrator: CLIOrchestrator) -> None:
        orchestrator.vm_details = None

        orchestrator._cleanup_on_failure()

        mock_echo.assert_not_called()


# ---------------------------------------------------------------------------
# CLIOrchestrator._get_ssh_connection_params
# ---------------------------------------------------------------------------


class TestGetSSHConnectionParams:
    """Test SSH connection parameter resolution."""

    def test_public_ip_returns_direct_ssh(
        self, orchestrator: CLIOrchestrator, vm_details_public_ip: VMDetails
    ) -> None:
        host, port, bastion_mgr = orchestrator._get_ssh_connection_params(vm_details_public_ip)

        assert host == "10.0.0.1"
        assert port == 22
        assert bastion_mgr is None

    def test_no_ips_raises_error(self, orchestrator: CLIOrchestrator) -> None:
        vm = VMDetails(
            name="vm-no-ip",
            resource_group="rg",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip=None,
            private_ip=None,
        )
        from azlin.modules.ssh_connector import SSHConnectionError

        with pytest.raises(SSHConnectionError, match="neither public nor private IP"):
            orchestrator._get_ssh_connection_params(vm)

    @patch("azlin.orchestrator.BastionManager")
    @patch("azlin.orchestrator.BastionDetector.detect_bastion_for_vm")
    def test_private_ip_with_bastion_creates_tunnel(
        self,
        mock_detect: MagicMock,
        mock_bastion_cls: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_private_only: VMDetails,
    ) -> None:
        mock_detect.return_value = {"name": "bastion-1", "resource_group": "rg-1"}
        mock_manager = MagicMock()
        mock_manager.get_available_port.return_value = 54321
        mock_bastion_cls.return_value = mock_manager

        host, port, bastion_mgr = orchestrator._get_ssh_connection_params(vm_details_private_only)

        assert host == "127.0.0.1"
        assert port == 54321
        assert bastion_mgr is mock_manager

    @patch("azlin.orchestrator.BastionDetector.detect_bastion_for_vm")
    def test_private_ip_without_bastion_raises(
        self,
        mock_detect: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_private_only: VMDetails,
    ) -> None:
        mock_detect.return_value = None

        from azlin.modules.ssh_connector import SSHConnectionError

        with pytest.raises(SSHConnectionError, match="no public IP and no Bastion"):
            orchestrator._get_ssh_connection_params(vm_details_private_only)


# ---------------------------------------------------------------------------
# CLIOrchestrator._extract_vnet_info_from_subnet_id
# ---------------------------------------------------------------------------


class TestExtractVnetInfoFromSubnetId:
    """Test subnet ID parsing."""

    def test_valid_subnet_id(self, orchestrator: CLIOrchestrator) -> None:
        subnet_id = (
            "/subscriptions/sub-1/resourceGroups/my-rg/providers/"
            "Microsoft.Network/virtualNetworks/my-vnet/subnets/default"
        )
        vnet_name, rg = orchestrator._extract_vnet_info_from_subnet_id(subnet_id)
        assert vnet_name == "my-vnet"
        assert rg == "my-rg"

    def test_invalid_subnet_id_raises(self, orchestrator: CLIOrchestrator) -> None:
        with pytest.raises(ValueError, match="Invalid subnet ID format"):
            orchestrator._extract_vnet_info_from_subnet_id("not-a-valid-id")


# ---------------------------------------------------------------------------
# CLIOrchestrator._process_sync_result
# ---------------------------------------------------------------------------


class TestProcessSyncResult:
    """Test sync result processing and display."""

    def test_success_with_files(self, orchestrator: CLIOrchestrator) -> None:
        result = SyncResult(
            success=True,
            files_synced=5,
            bytes_transferred=2048,
            duration_seconds=1.5,
        )
        # Should not raise
        orchestrator._process_sync_result(result)

    def test_success_no_files(self, orchestrator: CLIOrchestrator) -> None:
        result = SyncResult(success=True, files_synced=0)
        orchestrator._process_sync_result(result)

    @patch("azlin.orchestrator.click.echo")
    def test_success_with_warnings(
        self, mock_echo: MagicMock, orchestrator: CLIOrchestrator
    ) -> None:
        result = SyncResult(
            success=True,
            files_synced=3,
            bytes_transferred=1024,
            duration_seconds=0.5,
            warnings=["skipped .env", "skipped .secret"],
        )
        orchestrator._process_sync_result(result)

    def test_failure_logs_errors(self, orchestrator: CLIOrchestrator) -> None:
        result = SyncResult(
            success=False,
            errors=["connection reset", "timeout"],
        )
        # Should not raise, just log
        orchestrator._process_sync_result(result)


# ---------------------------------------------------------------------------
# CLIOrchestrator._show_blocked_files_warning
# ---------------------------------------------------------------------------


class TestShowBlockedFilesWarning:
    """Test blocked files warning display."""

    @patch("azlin.orchestrator.click.echo")
    def test_shows_up_to_five_files(
        self, mock_echo: MagicMock, orchestrator: CLIOrchestrator
    ) -> None:
        blocked = [f"file{i}.key" for i in range(3)]
        orchestrator._show_blocked_files_warning(blocked)
        assert mock_echo.call_count >= 4  # header + 3 files + spacing

    @patch("azlin.orchestrator.click.echo")
    def test_truncates_long_list(self, mock_echo: MagicMock, orchestrator: CLIOrchestrator) -> None:
        blocked = [f"file{i}.key" for i in range(10)]
        orchestrator._show_blocked_files_warning(blocked)

        all_output = " ".join(str(call.args[0]) for call in mock_echo.call_args_list if call.args)
        assert "and 5 more" in all_output


# ---------------------------------------------------------------------------
# CLIOrchestrator._check_bastion_availability
# ---------------------------------------------------------------------------


class TestCheckBastionAvailability:
    """Test bastion availability checking."""

    def test_no_bastion_flag_with_auto_approve_returns_false(
        self, orchestrator: CLIOrchestrator
    ) -> None:
        """When --no-bastion is set and auto_approve=True, should skip bastion."""
        orchestrator.no_bastion = True
        orchestrator.auto_approve = True

        with patch("azlin.orchestrator.SecurityAuditLogger.log_bastion_opt_out"):
            use_bastion, info = orchestrator._check_bastion_availability("rg-1", "vm-1")

        assert use_bastion is False
        assert info is None

    def test_explicit_bastion_name_returns_true(self, orchestrator: CLIOrchestrator) -> None:
        """When --bastion-name is provided, use it directly."""
        orchestrator.no_bastion = False
        orchestrator.bastion_name = "my-bastion"

        use_bastion, info = orchestrator._check_bastion_availability("rg-1", "vm-1")

        assert use_bastion is True
        assert info["name"] == "my-bastion"
        assert info["resource_group"] == "rg-1"


# ---------------------------------------------------------------------------
# CLIOrchestrator.run - error handling paths
# ---------------------------------------------------------------------------


class TestRunErrorHandling:
    """Test run() method error handling (exit code dispatch)."""

    def _setup_run_mocks(self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair) -> dict:
        """Set up common mocks for run() to reach specific error paths."""
        mocks = {}

        mocks["check_prereqs"] = patch.object(orchestrator, "_check_prerequisites").start()

        mocks["authenticate"] = patch.object(
            orchestrator, "_authenticate_azure", return_value="sub-abc-123"
        ).start()

        mocks["setup_keys"] = patch.object(
            orchestrator, "_setup_ssh_keys", return_value=ssh_key_pair
        ).start()

        mocks["check_storage"] = patch.object(
            orchestrator, "_check_and_create_storage_if_needed"
        ).start()

        mocks["provision_vm"] = patch.object(orchestrator, "_provision_vm").start()

        mocks["store_key"] = patch.object(orchestrator, "_store_key_in_vault_auto").start()

        mocks["wait_cloud_init"] = patch.object(orchestrator, "_wait_for_cloud_init").start()

        mocks["sync_home"] = patch.object(orchestrator, "_sync_home_directory").start()

        mocks["send_notification"] = patch.object(orchestrator, "_send_notification").start()

        mocks["display_info"] = patch.object(orchestrator, "_display_connection_info").start()

        mocks["cleanup"] = patch.object(orchestrator, "_cleanup_on_failure").start()

        mocks["send_error"] = patch.object(orchestrator, "_send_notification_error").start()

        # Mock auth.get_tenant_id needed before _store_key_in_vault_auto
        orchestrator.auth.get_tenant_id.return_value = "tenant-123"

        return mocks

    def test_prerequisite_error_returns_2(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        from azlin.modules.prerequisites import PrerequisiteError

        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        mocks["check_prereqs"].side_effect = PrerequisiteError("missing az")

        result = orchestrator.run()

        assert result == 2
        patch.stopall()

    def test_authentication_error_returns_3(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        from azlin.azure_auth import AuthenticationError

        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        mocks["authenticate"].side_effect = AuthenticationError("auth failed")

        result = orchestrator.run()

        assert result == 3
        mocks["send_error"].assert_called_once()
        patch.stopall()

    def test_provisioning_error_returns_4(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        from azlin.vm_provisioning import ProvisioningError

        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        vm = VMDetails(
            name="vm-1", resource_group="rg-1", location="eastus", size="Standard_D2s_v3"
        )
        mocks["provision_vm"].side_effect = ProvisioningError("quota exceeded")

        result = orchestrator.run()

        assert result == 4
        mocks["cleanup"].assert_called_once()
        patch.stopall()

    def test_ssh_connection_error_returns_5(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        from azlin.modules.ssh_connector import SSHConnectionError

        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        vm = VMDetails(
            name="vm-1",
            resource_group="rg-1",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip="1.2.3.4",
        )
        mocks["provision_vm"].return_value = vm
        mocks["wait_cloud_init"].side_effect = SSHConnectionError("ssh refused")

        result = orchestrator.run()

        assert result == 5
        # VM should NOT be cleaned up on SSH failure
        mocks["cleanup"].assert_not_called()
        patch.stopall()

    def test_keyboard_interrupt_returns_130(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        mocks["check_prereqs"].side_effect = KeyboardInterrupt()

        result = orchestrator.run()

        assert result == 130
        mocks["cleanup"].assert_called_once()
        patch.stopall()

    def test_generic_exception_returns_1(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        mocks["check_prereqs"].side_effect = RuntimeError("unexpected")

        result = orchestrator.run()

        assert result == 1
        mocks["cleanup"].assert_called_once()
        mocks["send_error"].assert_called_once()
        patch.stopall()

    def test_successful_run_returns_0(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        mocks = self._setup_run_mocks(orchestrator, ssh_key_pair)
        vm = VMDetails(
            name="vm-ok",
            resource_group="rg-ok",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip="5.6.7.8",
        )
        mocks["provision_vm"].return_value = vm

        # Patch validate_azure_vm_name and check_vm_exists to avoid the session_name path
        # (no session name set on the default orchestrator fixture)

        result = orchestrator.run()

        assert result == 0
        mocks["send_notification"].assert_called_once()
        mocks["display_info"].assert_called_once()
        patch.stopall()

    def test_github_setup_error_continues_returns_0(
        self, orchestrator_with_repo: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        """GitHub setup failure is non-fatal; workflow continues."""
        from azlin.modules.github_setup import GitHubSetupError

        mocks = self._setup_run_mocks(orchestrator_with_repo, ssh_key_pair)
        vm = VMDetails(
            name="vm-gh",
            resource_group="rg-gh",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip="9.8.7.6",
        )
        mocks["provision_vm"].return_value = vm

        # Setup github mock that raises
        setup_gh = patch.object(
            orchestrator_with_repo,
            "_setup_github",
            side_effect=GitHubSetupError("gh auth failed"),
        ).start()

        result = orchestrator_with_repo.run()

        assert result == 0
        mocks["display_info"].assert_called()
        patch.stopall()


# ---------------------------------------------------------------------------
# CLIOrchestrator._connect_ssh
# ---------------------------------------------------------------------------


class TestConnectSSH:
    """Test SSH connection dispatch."""

    @patch("azlin.orchestrator.SSHConnector.connect")
    @patch("azlin.orchestrator.click.echo")
    def test_direct_ssh_with_public_ip(
        self,
        mock_echo: MagicMock,
        mock_connect: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_public_ip: VMDetails,
        ssh_key_pair: SSHKeyPair,
    ) -> None:
        mock_connect.return_value = 0

        result = orchestrator._connect_ssh(vm_details_public_ip, ssh_key_pair.private_path)

        assert result == 0
        mock_connect.assert_called_once()

    @patch("azlin.orchestrator.click.echo")
    def test_bastion_connection_without_bastion_info_raises(
        self,
        mock_echo: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_private_only: VMDetails,
        ssh_key_pair: SSHKeyPair,
    ) -> None:
        orchestrator.bastion_info = None

        from azlin.modules.ssh_connector import SSHConnectionError

        with pytest.raises(SSHConnectionError, match="no public IP and no Bastion"):
            orchestrator._connect_ssh(vm_details_private_only, ssh_key_pair.private_path)

    @patch("azlin.orchestrator.VMConnector.connect")
    @patch("azlin.orchestrator.click.echo")
    def test_bastion_connection_with_bastion_info(
        self,
        mock_echo: MagicMock,
        mock_connect: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_private_only: VMDetails,
        ssh_key_pair: SSHKeyPair,
    ) -> None:
        orchestrator.bastion_info = {
            "name": "bastion-1",
            "resource_group": "rg-1",
            "location": "eastus",
        }

        result = orchestrator._connect_ssh(vm_details_private_only, ssh_key_pair.private_path)

        assert result == 0
        mock_connect.assert_called_once()


# ---------------------------------------------------------------------------
# CLIOrchestrator._sync_home_directory edge cases
# ---------------------------------------------------------------------------


class TestSyncHomeDirectory:
    """Test home directory sync edge cases."""

    def test_skips_when_no_ip_at_all(
        self, orchestrator: CLIOrchestrator, ssh_key_pair: SSHKeyPair
    ) -> None:
        vm = VMDetails(
            name="vm-no-ip",
            resource_group="rg",
            location="eastus",
            size="Standard_D2s_v3",
            public_ip=None,
            private_ip=None,
        )
        # Should not raise
        orchestrator._sync_home_directory(vm, ssh_key_pair.private_path)

    @patch("azlin.orchestrator.HomeSyncManager.sync_to_vm")
    @patch("azlin.orchestrator.HomeSyncManager.validate_sync_directory")
    @patch("azlin.orchestrator.HomeSyncManager.get_sync_directory")
    def test_syncs_with_public_ip(
        self,
        mock_get_dir: MagicMock,
        mock_validate: MagicMock,
        mock_sync: MagicMock,
        orchestrator: CLIOrchestrator,
        vm_details_public_ip: VMDetails,
        ssh_key_pair: SSHKeyPair,
        tmp_path: Path,
    ) -> None:
        mock_get_dir.return_value = tmp_path
        mock_validate.return_value = MagicMock(blocked_files=[])
        mock_sync.return_value = SyncResult(success=True, files_synced=2, bytes_transferred=512)

        orchestrator._sync_home_directory(vm_details_public_ip, ssh_key_pair.private_path)

        mock_sync.assert_called_once()


# ---------------------------------------------------------------------------
# CLIOrchestrator run() session name validation
# ---------------------------------------------------------------------------


class TestRunSessionNameValidation:
    """Test session name validation in run()."""

    def test_invalid_session_name_raises_value_error(self, ssh_key_pair: SSHKeyPair) -> None:
        with (
            patch("azlin.orchestrator.AzureAuthenticator"),
            patch("azlin.orchestrator.VMProvisioner") as mock_prov_cls,
            patch("azlin.orchestrator.ProgressDisplay"),
        ):
            orch = CLIOrchestrator(
                session_name="invalid name with spaces!",
                no_nfs=True,
                no_bastion=True,
                auto_approve=True,
            )

        # Mock prerequisites + auth to pass
        with (
            patch.object(orch, "_check_prerequisites"),
            patch.object(orch, "_authenticate_azure", return_value="sub-1"),
            patch.object(orch, "_setup_ssh_keys", return_value=ssh_key_pair),
            patch.object(orch, "_cleanup_on_failure"),
            patch.object(orch, "_send_notification_error"),
            patch(
                "azlin.orchestrator.VMProvisioner.validate_azure_vm_name",
                return_value=(False, "invalid chars"),
            ),
        ):
            result = orch.run()

        # Should fail with provisioning error exit code (ValueError -> caught by generic handler)
        assert result in (1, 4)
