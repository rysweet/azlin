"""Security-focused tests for file transfer."""

from pathlib import Path
from typing import Any

import pytest

from azlin.modules.file_transfer import (
    InvalidPathError,
    InvalidSessionNameError,
    PathParser,
    PathTraversalError,
    SessionManager,
    SymlinkSecurityError,
)


class TestPathTraversalPrevention:
    """Test path traversal attack prevention."""

    def test_rejects_parent_directory_traversal(self):
        """Should reject ../../etc/passwd"""
        with pytest.raises(PathTraversalError):
            PathParser.parse_and_validate("../../etc/passwd")

    def test_rejects_absolute_paths_to_system_dirs(self):
        """Should reject /etc/shadow"""
        with pytest.raises(InvalidPathError):
            PathParser.parse_and_validate("/etc/shadow")

    def test_rejects_home_escape(self):
        """Should reject paths that escape HOME"""
        with pytest.raises(PathTraversalError):
            PathParser.parse_and_validate("../../../root/.ssh/id_rsa")

    def test_rejects_double_slash(self):
        """Should normalize // in paths"""
        # This should normalize correctly or reject
        path = PathParser.parse_and_validate("mydir//file.txt")
        assert "//" not in str(path)

    def test_rejects_dot_segments_after_normalization(self):
        """Should reject . and .. segments"""
        with pytest.raises(PathTraversalError):
            PathParser.parse_and_validate("normal/../../../etc/passwd")


class TestCommandInjectionPrevention:
    """Test command injection prevention via session names."""

    def test_rejects_semicolon_in_session_name(self):
        """Should reject session names with semicolons"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("evil;rm -rf /")

    def test_rejects_pipe_in_session_name(self):
        """Should reject session names with pipes"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("test | cat /etc/passwd")

    def test_rejects_backticks_in_session_name(self):
        """Should reject session names with backticks"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("test`whoami`")

    def test_rejects_dollar_substitution(self):
        """Should reject session names with $()"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.validate_session_name("test$(id)")

    def test_accepts_valid_alphanumeric_session(self):
        """Should accept valid session names"""
        valid = SessionManager.validate_session_name("vm-test_123")
        assert valid == "vm-test_123"

    def test_session_path_parsing_prevents_injection(self):
        """Should prevent injection via session:path"""
        with pytest.raises(InvalidSessionNameError):
            SessionManager.parse_session_path("evil;rm:file.txt")


class TestSymlinkAttackPrevention:
    """Test symlink attack prevention."""

    def test_rejects_symlink_to_ssh_keys(self, tmp_path: Any) -> None:
        """Should reject symlink to ~/.ssh/id_rsa via credential file check"""
        # Create symlink
        link = tmp_path / "innocent_link"
        target = Path.home() / ".ssh" / "id_rsa"

        if target.exists():
            link.symlink_to(target)

            # The credential file check catches this before symlink validation (defense in depth)
            with pytest.raises(InvalidPathError, match="credential file"):
                PathParser.parse_and_validate(str(link), allow_absolute=True)

    def test_rejects_symlink_outside_home(self):
        """Should reject symlink pointing outside HOME"""
        # Create a symlink within HOME that points to /etc (outside HOME)
        home = Path.home()
        link = home / ".azlin_test_evil_link"

        # Only test if we're not running as root and /etc exists
        if Path("/etc").exists():
            try:
                if link.exists():
                    link.unlink()
                link.symlink_to("/etc/passwd")

                # Path validation catches this before symlink validation (defense in depth)
                # Both PathTraversalError and SymlinkSecurityError are correct rejections
                with pytest.raises((SymlinkSecurityError, PathTraversalError)):
                    PathParser.parse_and_validate(str(link), allow_absolute=True)
            finally:
                # Cleanup
                if link.exists():
                    link.unlink()


class TestNullByteInjection:
    """Test null byte injection prevention."""

    def test_rejects_null_bytes_in_path(self):
        """Should reject paths with null bytes"""
        with pytest.raises(InvalidPathError):
            PathParser.parse_and_validate("file.txt\x00.sh")


class TestShellMetacharacterPrevention:
    """Test shell metacharacter prevention in paths."""

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`", ">", "<", "\n"])
    def test_rejects_shell_metacharacters(self, char: str) -> None:
        """Should reject paths with shell metacharacters"""
        with pytest.raises(InvalidPathError):
            PathParser.parse_and_validate(f"file{char}test.txt")


class TestCredentialFilePrevention:
    """Test credential file blocking."""

    def test_blocks_ssh_private_key(self):
        """Should block ~/.ssh/id_rsa"""
        ssh_dir = Path.home() / ".ssh"
        key_path = ssh_dir / "id_rsa"

        with pytest.raises(InvalidPathError):
            PathParser.parse_and_validate(str(key_path), allow_absolute=True)

    def test_blocks_aws_credentials(self):
        """Should block ~/.aws/credentials"""
        aws_creds = Path.home() / ".aws" / "credentials"

        with pytest.raises(InvalidPathError):
            PathParser.parse_and_validate(str(aws_creds), allow_absolute=True)
