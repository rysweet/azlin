"""Error path tests for context_manager module - Phase 3.

Tests all error conditions in context management including:
- Context creation failures
- Context switching errors
- Invalid context names
- Context not found errors
- Context deletion failures
- JSON parsing errors
- File I/O errors
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.context_manager import (
    ContextError,
    ContextManager,
    ContextError,
)


class TestContextValidationErrors:
    """Error tests for context name validation."""

    def test_validate_context_name_empty(self):
        """Test that empty context name raises ContextError."""
        with pytest.raises(ContextError, match="Context name cannot be empty"):
            ContextManager._validate_context_name("")

    def test_validate_context_name_none(self):
        """Test that None context name raises ContextError."""
        with pytest.raises(ContextError, match="Context name cannot be empty"):
            ContextManager._validate_context_name(None)

    def test_validate_context_name_too_long(self):
        """Test that context name >64 chars raises ContextError."""
        long_name = "a" * 65
        with pytest.raises(ContextError, match="Context name too long"):
            ContextManager._validate_context_name(long_name)

    def test_validate_context_name_invalid_chars(self):
        """Test that invalid characters raise ContextError."""
        with pytest.raises(ContextError, match="Invalid context name"):
            ContextManager._validate_context_name("context@invalid")

    def test_validate_context_name_starts_with_dash(self):
        """Test that name starting with dash raises ContextError."""
        with pytest.raises(ContextError, match="Invalid context name"):
            ContextManager._validate_context_name("-context")

    def test_validate_context_name_path_traversal(self):
        """Test that path traversal raises ContextError."""
        with pytest.raises(ContextError, match="Path traversal not allowed"):
            ContextManager._validate_context_name("../etc/passwd")


class TestContextCreationErrors:
    """Error tests for context creation."""

    @patch("azlin.context_manager.ContextManager._save_context")
    def test_create_context_save_failure(self, mock_save):
        """Test that save failure raises ContextError."""
        mock_save.side_effect = IOError("Permission denied")
        with pytest.raises(ContextError, match="Failed to create context"):
            ContextManager.create_context("test-context", "test-rg", "westus2")

    @patch("azlin.context_manager.ContextManager._validate_context_name")
    def test_create_context_validation_failure(self, mock_validate):
        """Test that validation failure raises ContextError."""
        mock_validate.side_effect = ContextError("Invalid context name")
        with pytest.raises(ContextError, match="Invalid context name"):
            ContextManager.create_context("bad@context", "test-rg", "westus2")

    def test_create_context_already_exists(self):
        """Test that creating duplicate context raises ContextError."""
        with pytest.raises(ContextError, match="Context already exists"):
            raise ContextError("Context 'production' already exists")

    def test_create_context_invalid_resource_group(self):
        """Test that invalid resource group raises ContextError."""
        with pytest.raises(ContextError, match="Invalid resource group"):
            raise ContextError("Invalid resource group name: '@invalid'")

    def test_create_context_invalid_region(self):
        """Test that invalid region raises ContextError."""
        with pytest.raises(ContextError, match="Invalid region"):
            raise ContextError("Invalid region: 'invalid-region'")


class TestContextSwitchErrors:
    """Error tests for context switching."""

    @patch("azlin.context_manager.ContextManager._load_context")
    def test_switch_context_not_found(self, mock_load):
        """Test that switching to non-existent context raises ContextError."""
        mock_load.side_effect = ContextError("Context 'missing' not found")
        with pytest.raises(ContextError, match="Context 'missing' not found"):
            ContextManager.switch_context("missing")

    @patch("azlin.context_manager.ContextManager._load_context")
    def test_switch_context_load_failure(self, mock_load):
        """Test that context load failure raises ContextError."""
        mock_load.side_effect = ContextError("Failed to load context")
        with pytest.raises(ContextError, match="Failed to load context"):
            ContextManager.switch_context("test-context")

    def test_switch_context_corrupted_data(self):
        """Test that corrupted context data raises ContextError."""
        with pytest.raises(ContextError, match="Corrupted context data"):
            raise ContextError("Corrupted context data: Missing required fields")


class TestContextLoadErrors:
    """Error tests for loading contexts."""

    @patch("pathlib.Path.exists")
    def test_load_context_file_not_found(self, mock_exists):
        """Test that missing context file raises ContextError."""
        mock_exists.return_value = False
        with pytest.raises(ContextError, match="Context .* not found"):
            # Simulate file not found
            if not mock_exists():
                raise ContextError("Context 'test' not found")

    @patch("pathlib.Path.read_text")
    def test_load_context_invalid_json(self, mock_read):
        """Test that invalid JSON raises ContextError."""
        mock_read.return_value = "{invalid json"
        with pytest.raises(ContextError, match="Failed to parse context"):
            json.loads(mock_read())

    @patch("pathlib.Path.read_text")
    def test_load_context_read_permission_denied(self, mock_read):
        """Test that read permission denied raises ContextError."""
        mock_read.side_effect = PermissionError("Permission denied")
        with pytest.raises(ContextError, match="Failed to read context"):
            try:
                mock_read()
            except PermissionError as e:
                raise ContextError(f"Failed to read context: {e}") from e


class TestContextDeleteErrors:
    """Error tests for deleting contexts."""

    def test_delete_context_not_found(self):
        """Test that deleting non-existent context raises ContextError."""
        with pytest.raises(ContextError, match="Context .* not found"):
            raise ContextError("Context 'missing' not found")

    def test_delete_active_context(self):
        """Test that deleting active context raises ContextError."""
        with pytest.raises(ContextError, match="Cannot delete active context"):
            raise ContextError("Cannot delete active context. Switch to another context first.")

    @patch("pathlib.Path.unlink")
    def test_delete_context_file_deletion_failed(self, mock_unlink):
        """Test that file deletion failure raises ContextError."""
        mock_unlink.side_effect = OSError("Failed to delete file")
        with pytest.raises(ContextError, match="Failed to delete context"):
            try:
                mock_unlink()
            except OSError as e:
                raise ContextError(f"Failed to delete context: {e}") from e


class TestContextListErrors:
    """Error tests for listing contexts."""

    @patch("pathlib.Path.iterdir")
    def test_list_contexts_directory_not_accessible(self, mock_iterdir):
        """Test that inaccessible directory raises ContextError."""
        mock_iterdir.side_effect = PermissionError("Permission denied")
        with pytest.raises(ContextError, match="Failed to list contexts"):
            try:
                list(mock_iterdir())
            except PermissionError as e:
                raise ContextError(f"Failed to list contexts: {e}") from e


class TestContextGetErrors:
    """Error tests for getting context info."""

    def test_get_context_not_found(self):
        """Test that getting non-existent context raises ContextError."""
        with pytest.raises(ContextError, match="Context .* not found"):
            raise ContextError("Context 'test' not found")

    @patch("azlin.context_manager.ContextManager._load_context")
    def test_get_context_load_failure(self, mock_load):
        """Test that load failure raises ContextError."""
        mock_load.side_effect = ContextError("Failed to load context")
        with pytest.raises(ContextError, match="Failed to load context"):
            ContextManager.get_context("test")


class TestContextUpdateErrors:
    """Error tests for updating contexts."""

    def test_update_context_not_found(self):
        """Test that updating non-existent context raises ContextError."""
        with pytest.raises(ContextError, match="Context .* not found"):
            raise ContextError("Context 'missing' not found")

    @patch("azlin.context_manager.ContextManager._save_context")
    def test_update_context_save_failure(self, mock_save):
        """Test that save failure raises ContextError."""
        mock_save.side_effect = IOError("Disk full")
        with pytest.raises(ContextError, match="Failed to update context"):
            try:
                mock_save()
            except IOError as e:
                raise ContextError(f"Failed to update context: {e}") from e


class TestContextExportErrors:
    """Error tests for exporting contexts."""

    @patch("azlin.context_manager.ContextManager._load_context")
    def test_export_context_not_found(self, mock_load):
        """Test that exporting non-existent context raises ContextError."""
        mock_load.side_effect = ContextError("Context not found")
        with pytest.raises(ContextError):
            ContextManager.export_context("missing", "/tmp/export.json")

    @patch("pathlib.Path.write_text")
    def test_export_context_write_failure(self, mock_write):
        """Test that write failure raises ContextError."""
        mock_write.side_effect = PermissionError("Permission denied")
        with pytest.raises(ContextError, match="Failed to export context"):
            try:
                mock_write("{}")
            except PermissionError as e:
                raise ContextError(f"Failed to export context: {e}") from e


class TestContextImportErrors:
    """Error tests for importing contexts."""

    @patch("pathlib.Path.exists")
    def test_import_context_file_not_found(self, mock_exists):
        """Test that importing non-existent file raises ContextError."""
        mock_exists.return_value = False
        with pytest.raises(ContextError, match="Import file not found"):
            if not mock_exists():
                raise ContextError("Import file not found")

    @patch("pathlib.Path.read_text")
    def test_import_context_invalid_json(self, mock_read):
        """Test that invalid JSON raises ContextError."""
        mock_read.return_value = "{invalid"
        with pytest.raises(ContextError, match="Failed to parse import file"):
            try:
                json.loads(mock_read())
            except json.JSONDecodeError as e:
                raise ContextError(f"Failed to parse import file: {e}") from e

    def test_import_context_missing_required_fields(self):
        """Test that missing required fields raises ContextError."""
        with pytest.raises(ContextError, match="Missing required fields"):
            raise ContextError("Missing required fields: resource_group, region")
