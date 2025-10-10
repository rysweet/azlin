"""Unit tests for path_parser module."""

import pytest
from pathlib import Path
from azlin.modules.file_transfer import (
    PathParser,
    PathTraversalError,
    InvalidPathError,
    SymlinkSecurityError
)


class TestPathValidation:
    """Test basic path validation."""

    def test_accepts_valid_relative_path(self):
        """Should accept valid relative paths"""
        path = PathParser.parse_and_validate("test.txt")
        assert path.name == "test.txt"
        assert path.is_absolute()

    def test_accepts_valid_subdirectory_path(self):
        """Should accept paths with subdirectories"""
        path = PathParser.parse_and_validate("subdir/test.txt")
        assert "subdir" in path.parts
        assert path.name == "test.txt"

    def test_rejects_empty_path(self):
        """Should reject empty paths"""
        with pytest.raises(InvalidPathError, match="empty"):
            PathParser.parse_and_validate("")

    def test_rejects_whitespace_only_path(self):
        """Should reject whitespace-only paths"""
        with pytest.raises(InvalidPathError, match="empty"):
            PathParser.parse_and_validate("   ")

    def test_expands_tilde(self):
        """Should expand ~ to HOME"""
        path = PathParser.parse_and_validate("~/test.txt", allow_absolute=True)
        assert path.parts[0] == "/"
        assert "test.txt" in str(path)

    def test_normalizes_path(self):
        """Should normalize paths removing ."""
        path = PathParser.parse_and_validate("./test.txt")
        assert str(path) == str(Path.home() / "test.txt")


class TestAbsolutePathHandling:
    """Test absolute path handling."""

    def test_rejects_absolute_path_by_default(self):
        """Should reject absolute paths when not allowed"""
        with pytest.raises(InvalidPathError, match="Absolute paths not allowed"):
            PathParser.parse_and_validate("/tmp/test.txt")

    def test_accepts_absolute_path_when_allowed(self):
        """Should accept absolute paths when allowed"""
        path = PathParser.parse_and_validate(
            str(Path.home() / "test.txt"),
            allow_absolute=True
        )
        assert path.is_absolute()


class TestBoundaryValidation:
    """Test path boundary validation."""

    def test_accepts_paths_within_home(self):
        """Should accept paths within HOME"""
        path = PathParser.parse_and_validate("Documents/test.txt")
        assert path.is_relative_to(Path.home())

    def test_rejects_paths_outside_home(self):
        """Should reject paths outside HOME"""
        with pytest.raises(PathTraversalError):
            PathParser.parse_and_validate("../../../../etc/passwd")


class TestShellMetacharacters:
    """Test shell metacharacter detection."""

    def test_rejects_semicolon(self):
        """Should reject paths with semicolons"""
        with pytest.raises(InvalidPathError, match="shell metacharacters"):
            PathParser.parse_and_validate("test;rm.txt")

    def test_rejects_pipe(self):
        """Should reject paths with pipes"""
        with pytest.raises(InvalidPathError, match="shell metacharacters"):
            PathParser.parse_and_validate("test|cat.txt")

    def test_rejects_ampersand(self):
        """Should reject paths with ampersands"""
        with pytest.raises(InvalidPathError, match="shell metacharacters"):
            PathParser.parse_and_validate("test&whoami.txt")


class TestCredentialFileBlocking:
    """Test credential file pattern blocking."""

    def test_blocks_ssh_id_rsa(self):
        """Should block SSH private keys"""
        with pytest.raises(InvalidPathError, match="credential file"):
            PathParser.parse_and_validate(
                str(Path.home() / ".ssh/id_rsa"),
                allow_absolute=True
            )

    def test_blocks_ssh_id_ed25519(self):
        """Should block SSH ED25519 keys"""
        with pytest.raises(InvalidPathError, match="credential file"):
            PathParser.parse_and_validate(
                str(Path.home() / ".ssh/id_ed25519"),
                allow_absolute=True
            )

    def test_blocks_ssh_private_key(self):
        """Should block generic SSH private keys"""
        with pytest.raises(InvalidPathError, match="credential file"):
            PathParser.parse_and_validate(
                str(Path.home() / ".ssh/github_key"),
                allow_absolute=True
            )


class TestSymlinkValidation:
    """Test symlink validation."""

    def test_validates_symlink_target_within_home(self):
        """Should accept symlinks pointing within HOME"""
        # Create a file and symlink within HOME directory
        home = Path.home()
        target_file = home / ".azlin_test_target.txt"
        link_file = home / ".azlin_test_link.txt"

        try:
            target_file.touch()
            if link_file.exists():
                link_file.unlink()
            link_file.symlink_to(target_file)

            # Should not raise if both are within HOME
            path = PathParser.parse_and_validate(str(link_file), allow_absolute=True)
            assert path is not None
        finally:
            # Cleanup
            if link_file.exists():
                link_file.unlink()
            if target_file.exists():
                target_file.unlink()


class TestSanitizeForDisplay:
    """Test path sanitization for display."""

    def test_shows_relative_path(self):
        """Should show relative path for display"""
        full_path = Path.home() / "Documents" / "test.txt"
        display = PathParser.sanitize_for_display(full_path)
        assert display == "Documents/test.txt"

    def test_shows_filename_for_non_relative(self):
        """Should show only filename if not relative to base"""
        path = Path("/tmp/test.txt")
        display = PathParser.sanitize_for_display(path)
        assert display == "test.txt"
