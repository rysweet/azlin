"""Unit tests for key_rotator module.

Tests verify SSH key rotation security-critical functionality:
- KeyRotationResult dataclass properties
- SSHKeyRotator.rotate_keys full workflow (backup -> generate -> update -> rollback)
- SSHKeyRotator.update_all_vms parallel VM updates
- SSHKeyRotator.update_vm_key single-VM Azure CLI interaction
- SSHKeyRotator.backup_keys filesystem backup with secure permissions
- SSHKeyRotator.list_vm_keys Azure CLI query
- SSHKeyRotator.export_public_key file export
- Error recovery: rollback on partial failure, cleanup on backup failure
- Edge cases: empty resource group, no VMs, network failures, timeouts
"""

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.key_rotator import (
    KeyBackup,
    KeyRotationError,
    KeyRotationResult,
    SSHKeyRotator,
    VMKeyInfo,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_vm(name: str, rg: str = "test-rg") -> MagicMock:
    """Create a lightweight VMInfo-like mock."""
    vm = MagicMock()
    vm.name = name
    vm.resource_group = rg
    return vm


def _make_keypair(
    private_path: Path | None = None,
    public_path: Path | None = None,
    content: str = "ssh-ed25519 AAAA testkey",
) -> MagicMock:
    """Create a lightweight SSHKeyPair-like mock."""
    kp = MagicMock()
    kp.private_path = private_path or Path("/tmp/fake_key")
    kp.public_path = public_path or Path("/tmp/fake_key.pub")
    kp.public_key_content = content
    return kp


@pytest.fixture(autouse=True)
def _reset_audit_logger():
    """Reset the module-level audit logger between tests."""
    import azlin.key_rotator as mod

    mod._audit_logger = None
    yield
    mod._audit_logger = None


@pytest.fixture
def mock_audit():
    """Patch the audit logger to prevent filesystem side-effects."""
    with patch("azlin.key_rotator._get_audit_logger") as mock_fn:
        audit = MagicMock()
        mock_fn.return_value = audit
        yield audit


# ===================================================================
# KeyRotationResult
# ===================================================================


class TestKeyRotationResult:
    """Tests for KeyRotationResult dataclass."""

    def test_all_succeeded_true_when_no_failures(self):
        r = KeyRotationResult(success=True, message="ok", vms_updated=["vm1", "vm2"], vms_failed=[])
        assert r.all_succeeded is True

    def test_all_succeeded_false_when_failures_present(self):
        r = KeyRotationResult(success=True, message="ok", vms_updated=["vm1"], vms_failed=["vm2"])
        assert r.all_succeeded is False

    def test_all_succeeded_false_when_success_flag_false(self):
        r = KeyRotationResult(success=False, message="fail", vms_updated=[], vms_failed=[])
        assert r.all_succeeded is False

    def test_optional_fields_default_to_none(self):
        r = KeyRotationResult(success=True, message="ok", vms_updated=[], vms_failed=[])
        assert r.new_key_path is None
        assert r.backup_path is None


# ===================================================================
# SSHKeyRotator.update_vm_key
# ===================================================================


class TestUpdateVmKey:
    """Tests for single-VM key update via Azure CLI."""

    @patch("azlin.key_rotator.subprocess.run")
    def test_success_returns_true(self, mock_run, mock_audit):
        mock_run.return_value = MagicMock(returncode=0)
        result = SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        assert result is True
        # Verify correct az CLI command
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd[0] == "az"
        assert "--resource-group" in cmd
        assert "rg" in cmd
        assert "--name" in cmd
        assert "vm1" in cmd
        assert "--ssh-key-value" in cmd

    @patch("azlin.key_rotator.subprocess.run")
    def test_called_process_error_returns_false(self, mock_run, mock_audit):
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="auth failed")
        result = SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        assert result is False

    @patch("azlin.key_rotator.subprocess.run")
    def test_timeout_returns_false(self, mock_run, mock_audit):
        mock_run.side_effect = subprocess.TimeoutExpired("az", 120)
        result = SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        assert result is False

    @patch("azlin.key_rotator.subprocess.run")
    def test_unexpected_exception_returns_false(self, mock_run, mock_audit):
        mock_run.side_effect = OSError("network down")
        result = SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        assert result is False

    @patch("azlin.key_rotator.subprocess.run")
    def test_audit_logged_on_success(self, mock_run, mock_audit):
        mock_run.return_value = MagicMock(returncode=0)
        SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        mock_audit.log_vm_key_update.assert_called_once_with(
            vm_name="vm1", resource_group="rg", success=True
        )

    @patch("azlin.key_rotator.subprocess.run")
    def test_audit_logged_on_failure(self, mock_run, mock_audit):
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="permission denied")
        SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        mock_audit.log_vm_key_update.assert_called_once_with(
            vm_name="vm1",
            resource_group="rg",
            success=False,
            error="permission denied",
        )

    @patch("azlin.key_rotator.subprocess.run")
    def test_audit_failure_does_not_crash(self, mock_run, mock_audit):
        """Audit logging failure must not affect the return value."""
        mock_run.return_value = MagicMock(returncode=0)
        mock_audit.log_vm_key_update.side_effect = RuntimeError("audit broken")
        result = SSHKeyRotator.update_vm_key("vm1", "rg", "ssh-ed25519 AAAA")
        assert result is True


# ===================================================================
# SSHKeyRotator.update_all_vms
# ===================================================================


class TestUpdateAllVms:
    """Tests for parallel VM update orchestration."""

    @patch("azlin.key_rotator.AzureAuthenticator")
    @patch("azlin.key_rotator.VMManager")
    @patch.object(SSHKeyRotator, "update_vm_key", return_value=True)
    def test_all_vms_updated_successfully(self, mock_update, mock_vmm, mock_auth):
        vms = [_make_vm("azlin-vm1"), _make_vm("azlin-vm2")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms

        result = SSHKeyRotator.update_all_vms("rg", "ssh-ed25519 AAAA")

        assert result.success is True
        assert len(result.vms_updated) == 2
        assert len(result.vms_failed) == 0
        assert result.all_succeeded is True

    @patch("azlin.key_rotator.AzureAuthenticator")
    @patch("azlin.key_rotator.VMManager")
    @patch.object(SSHKeyRotator, "update_vm_key")
    def test_partial_failure(self, mock_update, mock_vmm, mock_auth):
        vms = [_make_vm("azlin-vm1"), _make_vm("azlin-vm2")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms
        # First succeeds, second fails
        mock_update.side_effect = [True, False]

        result = SSHKeyRotator.update_all_vms("rg", "ssh-ed25519 AAAA")

        assert result.success is False
        assert len(result.vms_updated) == 1
        assert len(result.vms_failed) == 1

    @patch("azlin.key_rotator.AzureAuthenticator")
    @patch("azlin.key_rotator.VMManager")
    def test_no_vms_found(self, mock_vmm, mock_auth):
        mock_vmm.list_vms.return_value = []
        mock_vmm.filter_by_prefix.return_value = []

        result = SSHKeyRotator.update_all_vms("rg", "ssh-ed25519 AAAA")

        assert result.success is True
        assert len(result.vms_updated) == 0
        assert "No VMs found" in result.message

    @patch("azlin.key_rotator.VMManager")
    def test_list_vms_failure(self, mock_vmm):
        mock_vmm.list_vms.side_effect = RuntimeError("Azure API error")

        result = SSHKeyRotator.update_all_vms("rg", "ssh-ed25519 AAAA")

        assert result.success is False
        assert "Failed to list VMs" in result.message

    @patch("azlin.key_rotator.AzureAuthenticator")
    @patch("azlin.key_rotator.VMManager")
    def test_auth_failure(self, mock_vmm, mock_auth_cls):
        vms = [_make_vm("azlin-vm1")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms
        mock_auth_cls.return_value.get_subscription_id.side_effect = RuntimeError("not logged in")

        result = SSHKeyRotator.update_all_vms("rg", "ssh-ed25519 AAAA")

        assert result.success is False
        assert "authentication failed" in result.message.lower()

    @patch("azlin.key_rotator.AzureAuthenticator")
    @patch("azlin.key_rotator.VMManager")
    @patch.object(SSHKeyRotator, "update_vm_key")
    def test_exception_in_future_counts_as_failure(self, mock_update, mock_vmm, mock_auth):
        vms = [_make_vm("azlin-vm1")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms
        mock_update.side_effect = RuntimeError("unexpected boom")

        result = SSHKeyRotator.update_all_vms("rg", "ssh-ed25519 AAAA")

        assert result.success is False
        assert len(result.vms_failed) == 1


# ===================================================================
# SSHKeyRotator.backup_keys
# ===================================================================


class TestBackupKeys:
    """Tests for SSH key backup functionality."""

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_successful_backup(self, mock_skm, tmp_path, mock_audit):
        # Set up real files so shutil.copy2 works
        priv = tmp_path / "azlin_key"
        pub = tmp_path / "azlin_key.pub"
        priv.write_text("PRIVATE")
        pub.write_text("ssh-ed25519 AAAA PUBLIC")

        mock_skm.ensure_key_exists.return_value = _make_keypair(priv, pub)

        backup_base = tmp_path / "backups"
        with patch.object(SSHKeyRotator, "BACKUP_BASE_DIR", backup_base):
            backup = SSHKeyRotator.backup_keys(priv)

        assert isinstance(backup, KeyBackup)
        assert backup.backup_dir.exists()
        assert backup.old_private_key.exists()
        assert backup.old_public_key.exists()
        # Verify private key permission (0o600)
        assert (backup.old_private_key.stat().st_mode & 0o777) == 0o600
        # Verify public key permission (0o644)
        assert (backup.old_public_key.stat().st_mode & 0o777) == 0o644

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_backup_audit_logged(self, mock_skm, tmp_path, mock_audit):
        priv = tmp_path / "azlin_key"
        pub = tmp_path / "azlin_key.pub"
        priv.write_text("PRIVATE")
        pub.write_text("PUBLIC")
        mock_skm.ensure_key_exists.return_value = _make_keypair(priv, pub)

        backup_base = tmp_path / "backups"
        with patch.object(SSHKeyRotator, "BACKUP_BASE_DIR", backup_base):
            SSHKeyRotator.backup_keys(priv)

        mock_audit.log_key_backup.assert_called_once()

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_ensure_key_exists_failure_raises_rotation_error(self, mock_skm):
        mock_skm.ensure_key_exists.side_effect = RuntimeError("no key found")

        with pytest.raises(KeyRotationError, match="Failed to get current key"):
            SSHKeyRotator.backup_keys()

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_backup_dir_cleanup_on_failure(self, mock_skm, tmp_path, mock_audit):
        """If copy fails, the backup dir must be cleaned up."""
        priv = tmp_path / "azlin_key"
        pub = tmp_path / "azlin_key.pub"
        priv.write_text("PRIVATE")
        # Don't create pub file so copy fails
        mock_skm.ensure_key_exists.return_value = _make_keypair(priv, pub)

        backup_base = tmp_path / "backups"
        with patch.object(SSHKeyRotator, "BACKUP_BASE_DIR", backup_base):
            with pytest.raises(KeyRotationError, match="Failed to backup keys"):
                SSHKeyRotator.backup_keys(priv)

        # Backup directory must be cleaned up
        if backup_base.exists():
            assert len(list(backup_base.iterdir())) == 0


# ===================================================================
# SSHKeyRotator.rotate_keys (full workflow)
# ===================================================================


class TestRotateKeys:
    """Tests for the full key rotation workflow."""

    def test_empty_resource_group_raises(self):
        with pytest.raises(KeyRotationError, match="cannot be empty"):
            SSHKeyRotator.rotate_keys("")

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "backup_keys")
    @patch.object(SSHKeyRotator, "update_all_vms")
    def test_successful_rotation(self, mock_update, mock_backup, mock_skm, mock_audit):
        mock_backup.return_value = KeyBackup(
            backup_dir=Path("/tmp/backup"),
            timestamp=datetime.now(),
            old_private_key=Path("/tmp/backup/azlin_key"),
            old_public_key=Path("/tmp/backup/azlin_key.pub"),
        )
        mock_skm.ensure_key_exists.return_value = _make_keypair()
        mock_update.return_value = KeyRotationResult(
            success=True,
            message="Updated 2 VMs",
            vms_updated=["vm1", "vm2"],
            vms_failed=[],
        )

        result = SSHKeyRotator.rotate_keys("test-rg")

        assert result.success is True
        assert len(result.vms_updated) == 2
        assert result.backup_path == Path("/tmp/backup")
        assert result.new_key_path is not None
        mock_audit.log_key_rotation.assert_called_once()

    @patch.object(SSHKeyRotator, "backup_keys")
    def test_backup_failure_returns_error(self, mock_backup, mock_audit):
        mock_backup.side_effect = RuntimeError("disk full")

        result = SSHKeyRotator.rotate_keys("test-rg")

        assert result.success is False
        assert "Backup failed" in result.message

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "backup_keys")
    def test_key_generation_failure_returns_error(self, mock_backup, mock_skm, mock_audit):
        mock_backup.return_value = KeyBackup(
            backup_dir=Path("/tmp/backup"),
            timestamp=datetime.now(),
            old_private_key=Path("/tmp/backup/azlin_key"),
            old_public_key=Path("/tmp/backup/azlin_key.pub"),
        )
        mock_skm.ensure_key_exists.side_effect = RuntimeError("keygen failed")

        result = SSHKeyRotator.rotate_keys("test-rg")

        assert result.success is False
        assert "Key generation failed" in result.message
        assert result.backup_path == Path("/tmp/backup")

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "backup_keys")
    @patch.object(SSHKeyRotator, "update_all_vms")
    def test_partial_failure_triggers_rollback(
        self, mock_update, mock_backup, mock_skm, mock_audit, tmp_path
    ):
        # Create backup with readable public key for rollback
        pub_file = tmp_path / "azlin_key.pub"
        pub_file.write_text("ssh-ed25519 AAAA old-key")

        mock_backup.return_value = KeyBackup(
            backup_dir=tmp_path,
            timestamp=datetime.now(),
            old_private_key=tmp_path / "azlin_key",
            old_public_key=pub_file,
        )
        mock_skm.ensure_key_exists.return_value = _make_keypair()

        # First call: partial failure. Second call (rollback): succeed.
        partial_fail = KeyRotationResult(
            success=False,
            message="1 failed",
            vms_updated=["vm1"],
            vms_failed=["vm2"],
        )
        rollback_ok = KeyRotationResult(
            success=True,
            message="rollback ok",
            vms_updated=["vm1", "vm2"],
            vms_failed=[],
        )
        mock_update.side_effect = [partial_fail, rollback_ok]

        result = SSHKeyRotator.rotate_keys("test-rg", enable_rollback=True)

        # update_all_vms called twice: initial + rollback
        assert mock_update.call_count == 2
        # Second call should use the old key
        rollback_call = mock_update.call_args_list[1]
        assert rollback_call.kwargs.get("new_public_key") == "ssh-ed25519 AAAA old-key"

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "backup_keys")
    @patch.object(SSHKeyRotator, "update_all_vms")
    def test_rollback_disabled_skips_rollback(self, mock_update, mock_backup, mock_skm, mock_audit):
        mock_backup.return_value = KeyBackup(
            backup_dir=Path("/tmp/backup"),
            timestamp=datetime.now(),
            old_private_key=Path("/tmp/backup/azlin_key"),
            old_public_key=Path("/tmp/backup/azlin_key.pub"),
        )
        mock_skm.ensure_key_exists.return_value = _make_keypair()
        mock_update.return_value = KeyRotationResult(
            success=False,
            message="1 failed",
            vms_updated=["vm1"],
            vms_failed=["vm2"],
        )

        result = SSHKeyRotator.rotate_keys("test-rg", enable_rollback=False)

        # Only one call to update_all_vms (no rollback)
        assert mock_update.call_count == 1
        assert result.success is False

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "update_all_vms")
    def test_skip_backup(self, mock_update, mock_skm, mock_audit):
        mock_skm.ensure_key_exists.return_value = _make_keypair()
        mock_update.return_value = KeyRotationResult(
            success=True, message="ok", vms_updated=["vm1"], vms_failed=[]
        )

        result = SSHKeyRotator.rotate_keys("test-rg", create_backup=False)

        assert result.success is True
        assert result.backup_path is None

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "backup_keys")
    @patch.object(SSHKeyRotator, "update_all_vms")
    def test_update_exception_returns_failure(self, mock_update, mock_backup, mock_skm, mock_audit):
        mock_backup.return_value = KeyBackup(
            backup_dir=Path("/tmp/backup"),
            timestamp=datetime.now(),
            old_private_key=Path("/tmp/backup/azlin_key"),
            old_public_key=Path("/tmp/backup/azlin_key.pub"),
        )
        mock_skm.ensure_key_exists.return_value = _make_keypair()
        mock_update.side_effect = RuntimeError("unexpected")

        result = SSHKeyRotator.rotate_keys("test-rg")

        assert result.success is False
        assert "Rotation failed" in result.message

    @patch("azlin.key_rotator.SSHKeyManager")
    @patch.object(SSHKeyRotator, "backup_keys")
    @patch.object(SSHKeyRotator, "update_all_vms")
    def test_audit_failure_does_not_crash_rotation(
        self, mock_update, mock_backup, mock_skm, mock_audit
    ):
        mock_backup.return_value = KeyBackup(
            backup_dir=Path("/tmp/backup"),
            timestamp=datetime.now(),
            old_private_key=Path("/tmp/backup/azlin_key"),
            old_public_key=Path("/tmp/backup/azlin_key.pub"),
        )
        mock_skm.ensure_key_exists.return_value = _make_keypair()
        mock_update.return_value = KeyRotationResult(
            success=True, message="ok", vms_updated=["vm1"], vms_failed=[]
        )
        mock_audit.log_key_rotation.side_effect = RuntimeError("audit DB down")

        result = SSHKeyRotator.rotate_keys("test-rg")

        # Rotation must still succeed despite audit failure
        assert result.success is True


# ===================================================================
# SSHKeyRotator.list_vm_keys
# ===================================================================


class TestListVmKeys:
    """Tests for listing VM SSH keys."""

    @patch("azlin.key_rotator.subprocess.run")
    @patch("azlin.key_rotator.VMManager")
    def test_returns_keys_for_each_vm(self, mock_vmm, mock_run):
        vms = [_make_vm("azlin-vm1"), _make_vm("azlin-vm2")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms
        mock_run.return_value = MagicMock(stdout="ssh-ed25519 AAAA testkey\n", returncode=0)

        keys = SSHKeyRotator.list_vm_keys("test-rg")

        assert len(keys) == 2
        assert all(isinstance(k, VMKeyInfo) for k in keys)
        assert keys[0].public_key == "ssh-ed25519 AAAA testkey"

    @patch("azlin.key_rotator.subprocess.run")
    @patch("azlin.key_rotator.VMManager")
    def test_vm_query_failure_returns_none_key(self, mock_vmm, mock_run):
        vms = [_make_vm("azlin-vm1")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="not found")

        keys = SSHKeyRotator.list_vm_keys("test-rg")

        assert len(keys) == 1
        assert keys[0].public_key is None

    @patch("azlin.key_rotator.VMManager")
    def test_list_vms_failure_returns_empty(self, mock_vmm):
        mock_vmm.list_vms.side_effect = RuntimeError("Azure error")

        keys = SSHKeyRotator.list_vm_keys("test-rg")

        assert keys == []

    @patch("azlin.key_rotator.subprocess.run")
    @patch("azlin.key_rotator.VMManager")
    def test_generic_exception_for_single_vm_still_returns_entry(self, mock_vmm, mock_run):
        vms = [_make_vm("azlin-vm1")]
        mock_vmm.list_vms.return_value = vms
        mock_vmm.filter_by_prefix.return_value = vms
        mock_run.side_effect = OSError("network down")

        keys = SSHKeyRotator.list_vm_keys("test-rg")

        assert len(keys) == 1
        assert keys[0].vm_name == "azlin-vm1"
        assert keys[0].public_key is None


# ===================================================================
# SSHKeyRotator.export_public_key
# ===================================================================


class TestExportPublicKey:
    """Tests for public key export."""

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_successful_export(self, mock_skm, tmp_path):
        mock_skm.ensure_key_exists.return_value = _make_keypair(content="ssh-ed25519 AAAA test")
        output_file = tmp_path / "exported.pub"

        result = SSHKeyRotator.export_public_key(output_file)

        assert result is True
        assert output_file.exists()
        assert output_file.read_text() == "ssh-ed25519 AAAA test\n"
        assert (output_file.stat().st_mode & 0o777) == 0o644

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_creates_parent_directory(self, mock_skm, tmp_path):
        mock_skm.ensure_key_exists.return_value = _make_keypair()
        output_file = tmp_path / "nested" / "dir" / "key.pub"

        result = SSHKeyRotator.export_public_key(output_file)

        assert result is True
        assert output_file.exists()

    @patch("azlin.key_rotator.SSHKeyManager")
    def test_key_not_found_returns_false(self, mock_skm):
        mock_skm.ensure_key_exists.side_effect = RuntimeError("no key")

        result = SSHKeyRotator.export_public_key(Path("/tmp/nope.pub"))

        assert result is False


# ===================================================================
# VMKeyInfo dataclass
# ===================================================================


class TestVMKeyInfo:
    """Tests for VMKeyInfo dataclass defaults."""

    def test_defaults(self):
        info = VMKeyInfo(vm_name="vm1", resource_group="rg")
        assert info.public_key is None
        assert info.key_fingerprint is None

    def test_with_values(self):
        info = VMKeyInfo(
            vm_name="vm1",
            resource_group="rg",
            public_key="ssh-ed25519 AAAA",
            key_fingerprint="SHA256:abc",
        )
        assert info.public_key == "ssh-ed25519 AAAA"
        assert info.key_fingerprint == "SHA256:abc"


# ===================================================================
# _get_audit_logger (lazy singleton)
# ===================================================================


class TestGetAuditLogger:
    """Tests for the lazy audit logger initialization."""

    def test_creates_logger_on_first_call(self):
        import azlin.key_rotator as mod

        mod._audit_logger = None
        with patch("azlin.key_rotator.KeyAuditLogger") as mock_cls:
            mock_cls.return_value = MagicMock()
            logger = mod._get_audit_logger()
            assert logger is not None
            mock_cls.assert_called_once()

    def test_returns_same_instance_on_second_call(self):
        import azlin.key_rotator as mod

        mod._audit_logger = None
        with patch("azlin.key_rotator.KeyAuditLogger") as mock_cls:
            sentinel = MagicMock()
            mock_cls.return_value = sentinel
            first = mod._get_audit_logger()
            second = mod._get_audit_logger()
            assert first is second
            mock_cls.assert_called_once()
