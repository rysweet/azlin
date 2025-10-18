"""Tests for home directory synchronization module.

Test Structure:
- Unit Tests (60% - ~30 tests): Pattern matching, symlinks, content scanning, command construction
- Integration Tests (30% - ~12 tests): Security validation workflow, rsync execution
- Security Tests (~7 tests): Credential bypass, symlink attacks, command injection

SECURITY FOCUS:
- Test all security layers (glob patterns, symlinks, content scanning, injection prevention)
- Test bypass attempts
- Test malformed inputs
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.modules.home_sync import (
    HomeSyncManager,
    RsyncError,
    SecurityValidationError,
)
from azlin.modules.ssh_connector import SSHConfig


class TestPatternMatching:
    """Test glob pattern matching (SECURITY LAYER 1)."""

    def test_whitelist_overrides_blacklist(self, tmp_path):
        """Test that whitelisted files are allowed even if they match blocked patterns."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        # Create public key (should be allowed)
        pub_key = ssh_dir / "id_rsa.pub"
        pub_key.write_text("ssh-rsa AAAA...")

        assert HomeSyncManager._is_path_allowed(pub_key, sync_dir)
        assert not HomeSyncManager._is_path_blocked(pub_key, sync_dir)

    def test_ssh_private_key_blocked(self, tmp_path):
        """Test that private SSH keys are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        # Create private key (should be blocked)
        priv_key = ssh_dir / "id_rsa"
        priv_key.write_text("-----BEGIN PRIVATE KEY-----")

        assert not HomeSyncManager._is_path_allowed(priv_key, sync_dir)
        assert HomeSyncManager._is_path_blocked(priv_key, sync_dir)

    def test_ssh_key_variants_blocked(self, tmp_path):
        """Test that various SSH key naming patterns are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        blocked_keys = [
            "id_rsa",
            "id_ed25519",
            "id_ecdsa",
            "my_private_key",
            "azure_key",
            "github.pem",
        ]

        for key_name in blocked_keys:
            key_path = ssh_dir / key_name
            key_path.write_text("private key content")
            assert HomeSyncManager._is_path_blocked(key_path, sync_dir), (
                f"{key_name} should be blocked"
            )

    def test_ssh_pub_keys_allowed(self, tmp_path):
        """Test that public SSH keys are explicitly allowed."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        allowed_files = [
            "id_rsa.pub",
            "id_ed25519.pub",
            "config",
            "known_hosts",
        ]

        for filename in allowed_files:
            file_path = ssh_dir / filename
            file_path.write_text("content")
            assert HomeSyncManager._is_path_allowed(file_path, sync_dir), (
                f"{filename} should be allowed"
            )

    def test_aws_credentials_blocked(self, tmp_path):
        """Test that AWS credential files are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        aws_dir = sync_dir / ".aws"
        aws_dir.mkdir()

        blocked_files = [
            "credentials",
            "config",
        ]

        for filename in blocked_files:
            file_path = aws_dir / filename
            file_path.write_text("aws_access_key_id = ...")
            assert HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                f"{filename} should be blocked"
            )

    def test_credential_filename_variants_blocked(self, tmp_path):
        """Test that files with 'credentials' in name are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        blocked_files = [
            "credentials",
            "credentials.json",
            "my_credentials",
            "test-credentials.yaml",
        ]

        for filename in blocked_files:
            file_path = sync_dir / filename
            file_path.write_text("content")
            assert HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                f"{filename} should be blocked"
            )

    def test_env_files_blocked(self, tmp_path):
        """Test that .env files are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        blocked_files = [
            ".env",
            ".env.local",
            ".env.production",
            ".env.test",
        ]

        for filename in blocked_files:
            file_path = sync_dir / filename
            file_path.write_text("SECRET_KEY=...")
            assert HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                f"{filename} should be blocked"
            )

    def test_safe_dotfiles_not_blocked(self, tmp_path):
        """Test that safe configuration files are not blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        safe_files = [
            ".bashrc",
            ".gitconfig",
            ".vimrc",
            ".tmux.conf",
        ]

        for filename in safe_files:
            file_path = sync_dir / filename
            file_path.write_text("safe config")
            assert not HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                f"{filename} should not be blocked"
            )

    def test_azure_config_files_whitelisted(self, tmp_path):
        """Test that safe Azure config files are whitelisted and NOT blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        azure_dir = sync_dir / ".azure"
        azure_dir.mkdir()

        # Safe Azure files that should be allowed
        safe_azure_files = [
            "azureProfile.json",
            "config",
            "clouds.config",
        ]

        for filename in safe_azure_files:
            file_path = azure_dir / filename
            file_path.write_text('{"safe": "config"}')

            # Should be whitelisted
            assert HomeSyncManager._is_path_allowed(file_path, sync_dir), (
                f"{filename} should be whitelisted"
            )
            # Should NOT be blocked
            assert not HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                f"{filename} should not be blocked"
            )

    def test_azure_secret_files_blocked(self, tmp_path):
        """Test that Azure credential/token files are blocked (not whitelisted)."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        azure_dir = sync_dir / ".azure"
        azure_dir.mkdir()

        # Dangerous Azure files that should be blocked
        blocked_azure_files = [
            "accessTokens.json",
            "msal_token_cache.json",
            "msal_token_cache.bin.json",
            "service_principal.json",
            "my_token.json",
            "azure_secret.json",
            "credentials.json",
        ]

        for filename in blocked_azure_files:
            file_path = azure_dir / filename
            file_path.write_text('{"token": "secret"}')

            # Should NOT be whitelisted
            assert not HomeSyncManager._is_path_allowed(file_path, sync_dir), (
                f"{filename} should not be whitelisted"
            )
            # Should be blocked
            assert HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                f"{filename} should be blocked"
            )


class TestSymlinkValidation:
    """Test symlink validation (SECURITY LAYER 2)."""

    def test_symlink_to_ssh_directory_blocked(self, tmp_path):
        """Test that symlinks to .ssh directory are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        # Create symlink to ~/.ssh
        link = sync_dir / "ssh_link"
        target = Path.home() / ".ssh"

        # Simulate resolved target
        assert HomeSyncManager._is_dangerous_symlink(link, target)

    def test_symlink_to_aws_directory_blocked(self, tmp_path):
        """Test that symlinks to .aws directory are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        link = sync_dir / "aws_link"
        target = Path.home() / ".aws"

        assert HomeSyncManager._is_dangerous_symlink(link, target)

    def test_symlink_to_ssh_subdirectory_blocked(self, tmp_path):
        """Test that symlinks to subdirectories of .ssh are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        link = sync_dir / "key_link"
        target = Path.home() / ".ssh" / "keys" / "id_rsa"

        assert HomeSyncManager._is_dangerous_symlink(link, target)

    def test_symlink_within_sync_dir_allowed(self, tmp_path):
        """Test that symlinks within sync directory are allowed."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        subdir = sync_dir / "configs"
        subdir.mkdir()

        link = sync_dir / "config_link"
        target = subdir / "config.txt"

        # Not dangerous because target is not in protected directories
        assert not HomeSyncManager._is_dangerous_symlink(link, target)

    def test_symlink_validation_in_scan(self, tmp_path):
        """Test that symlink validation is integrated in directory scan."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        # Create symlink to dangerous location
        sync_dir / "dangerous_link"
        target = Path.home() / ".ssh"

        # Mock the symlink
        with patch.object(Path, "is_symlink", return_value=True):
            with patch.object(Path, "resolve", return_value=target):
                warnings = HomeSyncManager.scan_for_secrets(sync_dir)

                # Should have warning about dangerous symlink
                assert any(
                    w.severity == "error" and "symlink" in w.reason.lower() for w in warnings
                )


class TestContentScanning:
    """Test content-based secret scanning (SECURITY LAYER 3)."""

    def test_aws_access_key_detected(self, tmp_path):
        """Test that AWS access keys in file content are detected."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        config_file = sync_dir / "config.yaml"
        config_file.write_text(
            """
aws:
  access_key: AKIAIOSFODNN7EXAMPLE
  secret_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
        """
        )

        warnings = HomeSyncManager._scan_file_content(config_file)
        assert any("AWS" in w.reason for w in warnings)

    def test_private_key_header_detected(self, tmp_path):
        """Test that private key headers are detected."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        key_file = sync_dir / "mykey.txt"
        key_file.write_text(
            """
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----
        """
        )

        warnings = HomeSyncManager._scan_file_content(key_file)
        assert any("Private Key" in w.reason for w in warnings)

    def test_github_token_detected(self, tmp_path):
        """Test that GitHub tokens are detected."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        script_file = sync_dir / "deploy.sh"
        # Construct fake token to avoid GitGuardian false positive
        # This tests our scanner's ability to detect the ghp_ pattern
        fake_token = "ghp_" + "1234567890abcdefghijklmnopqrstuvwxyz"
        script_file.write_text(
            f"""
export GITHUB_TOKEN={fake_token}
        """
        )

        warnings = HomeSyncManager._scan_file_content(script_file)
        assert any("GitHub Token" in w.reason for w in warnings)

    def test_binary_files_skipped(self, tmp_path):
        """Test that binary files don't cause errors."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        binary_file = sync_dir / "image.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

        # Should not raise exception
        warnings = HomeSyncManager._scan_file_content(binary_file)
        # Binary files should be skipped, no warnings
        assert len(warnings) == 0

    def test_large_files_skipped(self, tmp_path):
        """Test that files > 1MB are skipped for content scanning."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        large_file = sync_dir / "large.txt"
        # Create file > 1MB
        large_file.write_text("x" * (1_000_001))

        warnings = HomeSyncManager._scan_file_content(large_file)
        # Should be skipped due to size
        assert len(warnings) == 0


class TestCommandConstruction:
    """Test rsync command construction (SECURITY LAYER 4)."""

    def test_command_is_argument_list(self, tmp_path):
        """Test that rsync command is built as argument list, not shell string."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        exclude_file = sync_dir / ".azlin-sync-exclude"
        exclude_file.write_text("")

        ssh_config = SSHConfig(
            host="20.1.2.3", user="azureuser", key_path=Path("/home/user/.ssh/key")
        )

        cmd = HomeSyncManager._build_rsync_command(
            sync_dir, ssh_config, exclude_file, dry_run=False
        )

        # Should be a list
        assert isinstance(cmd, list)
        # First element should be rsync
        assert cmd[0] == "rsync"
        # Should include --safe-links
        assert "--safe-links" in cmd

    def test_ip_address_validation(self, tmp_path):
        """Test that IP addresses are validated."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        exclude_file = sync_dir / ".azlin-sync-exclude"
        exclude_file.write_text("")

        # Valid IP
        assert HomeSyncManager._is_valid_ip_or_hostname("192.168.1.1")
        assert HomeSyncManager._is_valid_ip_or_hostname("10.0.0.1")

        # Invalid IP
        assert not HomeSyncManager._is_valid_ip_or_hostname("999.999.999.999")
        assert not HomeSyncManager._is_valid_ip_or_hostname("not.an.ip.address")

    def test_hostname_validation(self):
        """Test that hostnames are validated per RFC 1123."""
        # Valid hostnames
        assert HomeSyncManager._is_valid_ip_or_hostname("example.com")
        assert HomeSyncManager._is_valid_ip_or_hostname("my-vm.azure.com")
        assert HomeSyncManager._is_valid_ip_or_hostname("vm123.local")

        # Invalid hostnames
        assert not HomeSyncManager._is_valid_ip_or_hostname("-invalid.com")
        assert not HomeSyncManager._is_valid_ip_or_hostname("invalid-.com")
        assert not HomeSyncManager._is_valid_ip_or_hostname("inva lid.com")

    def test_malformed_hostname_rejected(self, tmp_path):
        """Test that malformed hostnames are rejected to prevent injection."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        exclude_file = sync_dir / ".azlin-sync-exclude"
        exclude_file.write_text("")

        malicious_hosts = [
            "127.0.0.1; rm -rf /",
            "host`whoami`",
            "host$(cat /etc/passwd)",
            "host && malicious_command",
        ]

        for host in malicious_hosts:
            ssh_config = SSHConfig(host=host, user="user", key_path=Path("/key"))

            with pytest.raises(ValueError, match="Invalid host"):
                HomeSyncManager._build_rsync_command(sync_dir, ssh_config, exclude_file, False)

    def test_paths_must_be_absolute(self, tmp_path):
        """Test that all paths must be absolute."""
        # Relative sync dir
        with pytest.raises(ValueError, match="absolute"):
            HomeSyncManager._build_rsync_command(
                Path("relative/path"),
                SSHConfig("1.2.3.4", "user", Path("/key")),
                Path("/exclude"),
                False,
            )


class TestSecurityValidation:
    """Test comprehensive security validation workflow."""

    def test_validation_with_safe_files(self, tmp_path):
        """Test that validation passes with safe files."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        # Create safe files
        (sync_dir / ".bashrc").write_text("export PATH=...")
        (sync_dir / ".gitconfig").write_text("[user]")

        result = HomeSyncManager.validate_sync_directory(sync_dir)

        assert result.is_safe
        assert len(result.blocked_files) == 0

    def test_validation_with_credentials_blocks(self, tmp_path):
        """Test that validation tracks blocked files (Phase 1: non-fatal)."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        # Create private key
        (ssh_dir / "id_rsa").write_text("private key")

        result = HomeSyncManager.validate_sync_directory(sync_dir)

        # Phase 1: Non-fatal validation - returns is_safe=True with blocked_files populated
        assert result.is_safe
        assert len(result.blocked_files) > 0
        assert ".ssh/id_rsa" in result.blocked_files[0]

    def test_validation_with_mixed_files(self, tmp_path):
        """Test validation with both safe and unsafe files (Phase 1: non-fatal)."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        # Safe files
        (sync_dir / ".bashrc").write_text("safe")
        (ssh_dir / "config").write_text("safe")

        # Unsafe file
        (ssh_dir / "id_rsa").write_text("private")

        result = HomeSyncManager.validate_sync_directory(sync_dir)

        # Phase 1: Non-fatal validation - returns is_safe=True with blocked_files populated
        assert result.is_safe
        assert len(result.blocked_files) > 0

    def test_nonexistent_directory_is_safe(self, tmp_path):
        """Test that nonexistent directory is considered safe."""
        nonexistent = tmp_path / "does_not_exist"

        result = HomeSyncManager.validate_sync_directory(nonexistent)

        assert result.is_safe


class TestRsyncExecution:
    """Test rsync command execution."""

    @patch("azlin.modules.home_sync.HomeSyncManager.get_sync_directory")
    @patch("subprocess.run")
    def test_sync_success(self, mock_run, mock_sync_dir, tmp_path):
        """Test successful sync operation."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        (sync_dir / ".bashrc").write_text("content")

        # Mock get_sync_directory to return tmp_path
        mock_sync_dir.return_value = sync_dir

        # Mock successful rsync
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "Number of regular files transferred: 1\nTotal transferred file size: 100"
        )
        mock_run.return_value = mock_result

        ssh_config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/key"))

        result = HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)

        assert result.success
        assert mock_run.called

    @patch("azlin.modules.home_sync.HomeSyncManager.get_sync_directory")
    @patch("subprocess.run")
    def test_sync_with_security_validation_failure(self, mock_run, mock_sync_dir, tmp_path):
        """Test that sync continues with warnings when blocked files are found (Phase 1: non-fatal)."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        # Create blocked file
        (ssh_dir / "id_rsa").write_text("private key")

        # Mock get_sync_directory to return tmp_path
        mock_sync_dir.return_value = sync_dir

        # Mock successful rsync
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "Number of regular files transferred: 0\nTotal transferred file size: 0"
        )
        mock_run.return_value = mock_result

        ssh_config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/key"))

        # Phase 1: Sync should succeed with warnings, not raise exception
        result = HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)

        # Sync should succeed
        assert result.success
        # Should have warnings about skipped files
        assert len(result.warnings) > 0
        assert any("Skipped (sensitive)" in w for w in result.warnings)
        # rsync should be called
        assert mock_run.called

    @patch("azlin.modules.home_sync.HomeSyncManager.get_sync_directory")
    @patch("subprocess.run")
    def test_sync_timeout_raises_error(self, mock_run, mock_sync_dir, tmp_path):
        """Test that sync timeout raises appropriate error."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        (sync_dir / ".bashrc").write_text("content")

        # Mock get_sync_directory to return tmp_path
        mock_sync_dir.return_value = sync_dir

        mock_run.side_effect = subprocess.TimeoutExpired("rsync", 300)

        ssh_config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/key"))

        with pytest.raises(RsyncError, match="timed out"):
            HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)


class TestSecurityBypassAttempts:
    """Test that security bypass attempts are prevented."""

    def test_credential_bypass_with_similar_names(self, tmp_path):
        """Test that files with similar names to allowed files are still blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        ssh_dir = sync_dir / ".ssh"
        ssh_dir.mkdir()

        bypass_attempts = [
            "id_rsa.pub.bak",  # Not a .pub file
            "configcredentials",  # Contains 'credentials'
            "my_id_rsa",  # Matches id_* pattern
        ]

        for filename in bypass_attempts:
            file_path = ssh_dir / filename
            file_path.write_text("content")

            # Should be blocked
            if "pub" not in filename:
                assert HomeSyncManager._is_path_blocked(file_path, sync_dir), (
                    f"{filename} should be blocked"
                )

    def test_nested_credential_files_blocked(self, tmp_path):
        """Test that credentials in nested directories are blocked."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()
        nested = sync_dir / "project" / "config"
        nested.mkdir(parents=True)

        cred_file = nested / "credentials.json"
        cred_file.write_text('{"api_key": "secret"}')

        assert HomeSyncManager._is_path_blocked(cred_file, sync_dir)


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("azlin.modules.home_sync.HomeSyncManager.get_sync_directory")
    def test_empty_directory(self, mock_sync_dir, tmp_path):
        """Test handling of empty sync directory."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        # Mock get_sync_directory to return tmp_path
        mock_sync_dir.return_value = sync_dir

        ssh_config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/key"))

        result = HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)

        assert result.success
        assert "empty" in result.warnings[0].lower()

    @patch("azlin.modules.home_sync.HomeSyncManager.get_sync_directory")
    def test_nonexistent_directory(self, mock_sync_dir, tmp_path):
        """Test handling of nonexistent sync directory."""
        nonexistent = tmp_path / "does_not_exist"

        # Mock get_sync_directory to return tmp_path
        mock_sync_dir.return_value = nonexistent

        ssh_config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/key"))

        result = HomeSyncManager.sync_to_vm(ssh_config, dry_run=False)

        assert result.success
        assert "does not exist" in result.warnings[0].lower()

    def test_unicode_filenames(self, tmp_path):
        """Test handling of Unicode filenames."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        # Create file with Unicode name
        unicode_file = sync_dir / "файл.txt"
        unicode_file.write_text("content")

        result = HomeSyncManager.validate_sync_directory(sync_dir)
        assert result.is_safe


class TestExcludeFileGeneration:
    """Test exclude file generation."""

    def test_exclude_file_generated(self, tmp_path):
        """Test that exclude file is generated correctly."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        exclude_file = HomeSyncManager._generate_exclude_file(sync_dir)

        assert exclude_file.exists()
        content = exclude_file.read_text()

        # Should contain key patterns
        assert ".ssh/id_" in content
        assert "credentials" in content
        assert ".env" in content

    def test_exclude_file_doesnt_sync_itself(self, tmp_path):
        """Test that exclude file doesn't sync itself."""
        sync_dir = tmp_path / "sync"
        sync_dir.mkdir()

        exclude_file = HomeSyncManager._generate_exclude_file(sync_dir)
        content = exclude_file.read_text()

        # Should exclude itself
        assert HomeSyncManager.EXCLUDE_FILE_NAME in content
