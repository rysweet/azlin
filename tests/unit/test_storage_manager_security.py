"""Security tests for storage_manager.py path traversal protection.

Tests verify that storage name validation prevents all path traversal attacks
and enforces Azure naming requirements.
"""

import pytest

from azlin.modules.storage_manager import StorageManager, ValidationError


class TestStorageNamePathTraversalProtection:
    """Test path traversal attack prevention in storage name validation."""

    def test_rejects_parent_directory_traversal(self):
        """Should reject names containing .. (parent directory)."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("../etc")

    def test_rejects_double_dot_in_middle(self):
        """Should reject names with .. in the middle."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("foo..bar")

    def test_rejects_forward_slash(self):
        """Should reject names containing forward slash."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("foo/bar")

    def test_rejects_backslash(self):
        """Should reject names containing backslash."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("foo\\bar")

    def test_rejects_absolute_path_unix(self):
        """Should reject Unix absolute paths."""
        with pytest.raises(ValidationError, match=r"path traversal|alphanumeric"):
            StorageManager._validate_name("/etc/passwd")

    def test_rejects_absolute_path_windows(self):
        """Should reject Windows absolute paths."""
        with pytest.raises(ValidationError, match=r"path traversal|alphanumeric"):
            StorageManager._validate_name("C:\\Windows")

    def test_rejects_complex_traversal(self):
        """Should reject complex traversal patterns."""
        with pytest.raises(ValidationError, match=r"path traversal|alphanumeric"):
            StorageManager._validate_name("foo/../../etc/passwd")

    def test_rejects_url_encoded_traversal(self):
        """Should reject URL-encoded path traversal attempts."""
        # The regex will catch these as they contain non-alphanumeric chars
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo%2e%2e%2fbar")

    def test_rejects_unicode_traversal(self):
        """Should reject Unicode path traversal attempts."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\u2025bar")  # Two dot leader


class TestStorageNameValidation:
    """Test storage name validation against Azure requirements."""

    def test_accepts_valid_lowercase_alphanumeric(self):
        """Should accept valid lowercase alphanumeric names."""
        # Should not raise
        StorageManager._validate_name("validname123")
        StorageManager._validate_name("abc")
        StorageManager._validate_name("123")
        StorageManager._validate_name("a1b2c3")

    def test_rejects_empty_name(self):
        """Should reject empty name."""
        with pytest.raises(ValidationError, match="non-empty string"):
            StorageManager._validate_name("")

    def test_rejects_none_name(self):
        """Should reject None name."""
        with pytest.raises(ValidationError, match="non-empty string"):
            StorageManager._validate_name(None)

    def test_rejects_non_string(self):
        """Should reject non-string name."""
        with pytest.raises(ValidationError, match="non-empty string"):
            StorageManager._validate_name(123)

    def test_rejects_too_short_name(self):
        """Should reject names shorter than 3 characters."""
        with pytest.raises(ValidationError, match="at least 3"):
            StorageManager._validate_name("ab")

    def test_rejects_too_long_name(self):
        """Should reject names longer than 24 characters."""
        with pytest.raises(ValidationError, match="at most 24"):
            StorageManager._validate_name("a" * 25)

    def test_accepts_minimum_length(self):
        """Should accept 3-character name (minimum)."""
        StorageManager._validate_name("abc")

    def test_accepts_maximum_length(self):
        """Should accept 24-character name (maximum)."""
        StorageManager._validate_name("a" * 24)

    def test_rejects_uppercase_letters(self):
        """Should reject uppercase letters."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("MyStorage")

    def test_rejects_hyphens(self):
        """Should reject hyphens (Azure storage accounts don't allow them)."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("my-storage")

    def test_rejects_underscores(self):
        """Should reject underscores."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("my_storage")

    def test_rejects_spaces(self):
        """Should reject spaces."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("my storage")

    def test_rejects_special_characters(self):
        """Should reject special characters."""
        special_chars = "!@#$%^&*()+=[]{}|;:'\",.<>?"
        for char in special_chars:
            with pytest.raises(ValidationError, match="alphanumeric lowercase"):
                StorageManager._validate_name(f"storage{char}name")

    def test_rejects_dots(self):
        """Should reject dots (could be used for domain-like names)."""
        with pytest.raises(ValidationError, match="alphanumeric lowercase"):
            StorageManager._validate_name("storage.name")


class TestStorageNameEdgeCases:
    """Test edge cases in storage name validation."""

    def test_rejects_whitespace_only(self):
        """Should reject whitespace-only name."""
        with pytest.raises(ValidationError, match=r"non-empty string|alphanumeric"):
            StorageManager._validate_name("   ")

    def test_rejects_newline_in_name(self):
        """Should reject names containing newlines."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\nbar")

    def test_rejects_tab_in_name(self):
        """Should reject names containing tabs."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\tbar")

    def test_rejects_null_byte(self):
        """Should reject names containing null bytes."""
        with pytest.raises(ValidationError, match="alphanumeric"):
            StorageManager._validate_name("foo\x00bar")

    def test_all_numbers_valid(self):
        """Should accept all-numeric names."""
        StorageManager._validate_name("123456")

    def test_all_letters_valid(self):
        """Should accept all-letter names."""
        StorageManager._validate_name("abcdefgh")


class TestRealWorldAttackVectors:
    """Test real-world path traversal attack vectors."""

    def test_linux_etc_passwd(self):
        """Should reject attempt to access /etc/passwd."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("../../../etc/passwd")

    def test_windows_system32(self):
        """Should reject attempt to access Windows System32."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("..\\..\\Windows\\System32")

    def test_home_directory_escape(self):
        """Should reject attempt to escape to home directory."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("../../home/user")

    def test_root_directory(self):
        """Should reject attempt to access root directory."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("../../../")

    def test_current_directory_notation(self):
        """Should reject current directory notation."""
        with pytest.raises(ValidationError, match="path traversal"):
            StorageManager._validate_name("./storage")

    def test_mixed_slash_types(self):
        """Should reject mixed forward and backslashes."""
        with pytest.raises(ValidationError):
            StorageManager._validate_name("foo/bar\\baz")
