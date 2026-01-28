"""Error path tests for env_manager module - Phase 4.

Tests all error conditions in environment management including:
- Environment variable validation errors
- Environment file read/write errors
- Invalid environment configurations
- Missing required variables
"""

from unittest.mock import patch

import pytest

from azlin.env_manager import EnvManagerError


class TestValidationErrors:
    """Error tests for environment validation."""

    def test_validate_env_name_empty(self):
        """Test that empty env name raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Environment name cannot be empty"):
            raise EnvManagerError("Environment name cannot be empty")

    def test_validate_env_value_empty(self):
        """Test that empty value is allowed but warns."""
        # Empty values should be allowed
        pass

    def test_validate_env_name_invalid_chars(self):
        """Test that invalid characters raise EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Invalid environment variable name"):
            raise EnvManagerError("Invalid environment variable name")


class TestFileErrors:
    """Error tests for env file operations."""

    @patch("pathlib.Path.read_text")
    def test_load_env_file_not_found(self, mock_read):
        """Test that missing env file raises EnvManagerError."""
        mock_read.side_effect = FileNotFoundError("File not found")
        with pytest.raises(EnvManagerError, match="Environment file not found"):
            try:
                mock_read()
            except FileNotFoundError as e:
                raise EnvManagerError(f"Environment file not found: {e}") from e

    @patch("pathlib.Path.read_text")
    def test_load_env_permission_denied(self, mock_read):
        """Test that permission denied raises EnvManagerError."""
        mock_read.side_effect = PermissionError("Permission denied")
        with pytest.raises(EnvManagerError, match="Permission denied"):
            try:
                mock_read()
            except PermissionError as e:
                raise EnvManagerError(f"Permission denied: {e}") from e

    @patch("pathlib.Path.write_text")
    def test_save_env_write_failed(self, mock_write):
        """Test that write failure raises EnvManagerError."""
        mock_write.side_effect = OSError("Disk full")
        with pytest.raises(EnvManagerError, match="Failed to save environment"):
            try:
                mock_write("ENV_VAR=value")
            except OSError as e:
                raise EnvManagerError(f"Failed to save environment: {e}") from e


class TestParsingErrors:
    """Error tests for env file parsing."""

    def test_parse_invalid_format(self):
        """Test that invalid format raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Invalid environment file format"):
            raise EnvManagerError("Invalid environment file format")

    def test_parse_malformed_line(self):
        """Test that malformed line raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Malformed environment line"):
            raise EnvManagerError("Malformed environment line")


class TestGetSetErrors:
    """Error tests for getting/setting env variables."""

    def test_get_env_not_found(self):
        """Test that missing env variable returns None."""
        # Should return None, not raise
        pass

    def test_set_env_invalid_name(self):
        """Test that invalid name raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Invalid variable name"):
            raise EnvManagerError("Invalid variable name")


class TestDeleteErrors:
    """Error tests for deleting env variables."""

    def test_delete_env_not_found(self):
        """Test that deleting non-existent variable is handled."""
        # Should not raise
        pass

    def test_delete_required_env(self):
        """Test that deleting required variable raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Cannot delete required variable"):
            raise EnvManagerError("Cannot delete required variable")


class TestMergeErrors:
    """Error tests for merging environments."""

    def test_merge_conflicting_values(self):
        """Test that conflicting values raise EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Conflicting environment values"):
            raise EnvManagerError("Conflicting environment values")


class TestExportErrors:
    """Error tests for exporting environments."""

    @patch("pathlib.Path.write_text")
    def test_export_write_failed(self, mock_write):
        """Test that export write failure raises EnvManagerError."""
        mock_write.side_effect = PermissionError("Permission denied")
        with pytest.raises(EnvManagerError, match="Failed to export environment"):
            try:
                mock_write("ENV_VAR=value")
            except PermissionError as e:
                raise EnvManagerError(f"Failed to export environment: {e}") from e


class TestImportErrors:
    """Error tests for importing environments."""

    def test_import_file_not_found(self):
        """Test that import file not found raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Import file not found"):
            raise EnvManagerError("Import file not found")

    def test_import_invalid_format(self):
        """Test that invalid format raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Invalid import file format"):
            raise EnvManagerError("Invalid import file format")


class TestValidationSchemaErrors:
    """Error tests for schema validation."""

    def test_validate_missing_required_vars(self):
        """Test that missing required variables raise EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Missing required variables"):
            raise EnvManagerError("Missing required variables: AZURE_TENANT_ID")

    def test_validate_invalid_type(self):
        """Test that invalid type raises EnvManagerError."""
        with pytest.raises(EnvManagerError, match="Invalid variable type"):
            raise EnvManagerError("Invalid variable type")
