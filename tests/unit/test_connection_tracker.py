"""Unit tests for connection_tracker module."""

from datetime import UTC, datetime
from unittest.mock import Mock, mock_open, patch

import pytest

from azlin.connection_tracker import ConnectionTracker, ConnectionTrackerError


class TestEnsureConnectionsDir:
    """Tests for ensure_connections_dir method."""

    @patch("azlin.connection_tracker.Path.mkdir")
    @patch("azlin.connection_tracker.os.chmod")
    def test_ensure_connections_dir_creates_with_secure_permissions(self, mock_chmod, mock_mkdir):
        """Test that connections directory is created with 0700 permissions."""
        result = ConnectionTracker.ensure_connections_dir()

        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_chmod.assert_called_once_with(ConnectionTracker.DEFAULT_CONNECTIONS_DIR, 0o700)
        assert result == ConnectionTracker.DEFAULT_CONNECTIONS_DIR

    @patch("azlin.connection_tracker.Path.mkdir")
    def test_ensure_connections_dir_error_handling(self, mock_mkdir):
        """Test error handling when directory creation fails."""
        mock_mkdir.side_effect = PermissionError("Cannot create directory")

        with pytest.raises(ConnectionTrackerError) as exc_info:
            ConnectionTracker.ensure_connections_dir()

        assert "Failed to create connections directory" in str(exc_info.value)


class TestLoadConnections:
    """Tests for load_connections method."""

    @patch("azlin.connection_tracker.Path.exists")
    def test_load_connections_returns_empty_dict_when_file_missing(self, mock_exists):
        """Test that load_connections returns empty dict when file doesn't exist."""
        mock_exists.return_value = False

        result = ConnectionTracker.load_connections()

        assert result == {}

    @patch("azlin.connection_tracker.Path.exists")
    @patch("azlin.connection_tracker.Path.stat")
    @patch("azlin.connection_tracker.os.chmod")
    @patch("builtins.open", new_callable=mock_open, read_data=b"")
    @patch("azlin.connection_tracker.tomli.load")
    def test_load_connections_fixes_insecure_permissions(
        self, mock_tomli, mock_file, mock_chmod, mock_stat, mock_exists
    ):
        """Test that insecure file permissions are automatically fixed."""
        mock_exists.return_value = True

        # Mock file with insecure permissions (0o644)
        mock_stat_result = Mock()
        mock_stat_result.st_mode = 0o100644  # Regular file with 0644
        mock_stat.return_value = mock_stat_result

        mock_tomli.return_value = {"vm1": {"last_connected": "2024-10-18T10:00:00Z"}}

        result = ConnectionTracker.load_connections()

        # Should fix permissions to 0600
        mock_chmod.assert_called_once_with(ConnectionTracker.DEFAULT_CONNECTIONS_FILE, 0o600)
        assert result == {"vm1": {"last_connected": "2024-10-18T10:00:00Z"}}

    @patch("azlin.connection_tracker.Path.exists")
    @patch("azlin.connection_tracker.Path.stat")
    @patch("azlin.connection_tracker.os.chmod")
    @patch("builtins.open", new_callable=mock_open, read_data=b"")
    @patch("azlin.connection_tracker.tomli.load")
    def test_load_connections_parses_valid_toml(
        self, mock_tomli, mock_file, mock_chmod, mock_stat, mock_exists
    ):
        """Test successful parsing of valid TOML file."""
        mock_exists.return_value = True

        # Mock file with secure permissions (0o600)
        mock_stat_result = Mock()
        mock_stat_result.st_mode = 0o100600  # Regular file with 0600
        mock_stat.return_value = mock_stat_result

        expected_data = {
            "vm1": {"last_connected": "2024-10-18T10:00:00Z"},
            "vm2": {"last_connected": "2024-10-17T15:30:00Z"},
        }
        mock_tomli.return_value = expected_data

        result = ConnectionTracker.load_connections()

        # Should NOT fix permissions (already secure)
        mock_chmod.assert_not_called()
        assert result == expected_data

    @patch("azlin.connection_tracker.Path.exists")
    @patch("azlin.connection_tracker.Path.stat")
    @patch("builtins.open", new_callable=mock_open, read_data=b"invalid toml content")
    @patch("azlin.connection_tracker.tomli.load")
    def test_load_connections_handles_corrupted_toml(
        self, mock_tomli, mock_file, mock_stat, mock_exists
    ):
        """Test graceful handling of corrupted TOML file."""
        mock_exists.return_value = True

        mock_stat_result = Mock()
        mock_stat_result.st_mode = 0o100600
        mock_stat.return_value = mock_stat_result

        # Simulate TOML parsing error
        mock_tomli.side_effect = Exception("Invalid TOML syntax")

        result = ConnectionTracker.load_connections()

        # Should return empty dict and log warning
        assert result == {}


class TestSaveConnections:
    """Tests for save_connections method."""

    @patch("azlin.connection_tracker.ConnectionTracker.ensure_connections_dir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("azlin.connection_tracker.tomli_w.dump")
    @patch("azlin.connection_tracker.os.chmod")
    @patch("azlin.connection_tracker.Path.replace")
    def test_save_connections_atomic_write_with_temp_file(
        self, mock_replace, mock_chmod, mock_dump, mock_file, mock_ensure_dir
    ):
        """Test that save_connections uses atomic write with temp file."""
        connections = {"vm1": {"last_connected": "2024-10-18T10:00:00Z"}}

        ConnectionTracker.save_connections(connections)

        # Should write to temp file first
        temp_path = ConnectionTracker.DEFAULT_CONNECTIONS_FILE.with_suffix(".tmp")
        mock_file.assert_called_once_with(temp_path, "wb")
        mock_dump.assert_called_once_with(connections, mock_file())

        # Should set secure permissions on temp file
        mock_chmod.assert_called_once_with(temp_path, 0o600)

        # Should atomically replace original file
        mock_replace.assert_called_once_with(ConnectionTracker.DEFAULT_CONNECTIONS_FILE)

    @patch("azlin.connection_tracker.ConnectionTracker.ensure_connections_dir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("azlin.connection_tracker.tomli_w.dump")
    @patch("azlin.connection_tracker.os.chmod")
    @patch("azlin.connection_tracker.Path.replace")
    def test_save_connections_sets_secure_permissions(
        self, mock_replace, mock_chmod, mock_dump, mock_file, mock_ensure_dir
    ):
        """Test that saved file has secure 0600 permissions."""
        connections = {"vm1": {"last_connected": "2024-10-18T10:00:00Z"}}

        ConnectionTracker.save_connections(connections)

        temp_path = ConnectionTracker.DEFAULT_CONNECTIONS_FILE.with_suffix(".tmp")
        mock_chmod.assert_called_once_with(temp_path, 0o600)

    @patch("azlin.connection_tracker.ConnectionTracker.ensure_connections_dir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("azlin.connection_tracker.tomli_w.dump")
    @patch("azlin.connection_tracker.Path.exists")
    @patch("azlin.connection_tracker.Path.unlink")
    def test_save_connections_cleanup_on_failure(
        self, mock_unlink, mock_exists, mock_dump, mock_file, mock_ensure_dir
    ):
        """Test that temp file is cleaned up on save failure."""
        mock_dump.side_effect = Exception("Write failed")
        mock_exists.return_value = True

        with pytest.raises(ConnectionTrackerError):
            ConnectionTracker.save_connections({})

        # Should clean up temp file
        mock_unlink.assert_called_once()

    @patch("azlin.connection_tracker.ConnectionTracker.ensure_connections_dir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("azlin.connection_tracker.tomli_w.dump")
    def test_save_connections_raises_error_on_failure(self, mock_dump, mock_file, mock_ensure_dir):
        """Test that ConnectionTrackerError is raised on save failure."""
        mock_dump.side_effect = OSError("Disk full")

        with pytest.raises(ConnectionTrackerError) as exc_info:
            ConnectionTracker.save_connections({})

        assert "Failed to save connections" in str(exc_info.value)


class TestRecordConnection:
    """Tests for record_connection method."""

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    @patch("azlin.connection_tracker.datetime")
    def test_record_connection_default_timestamp(self, mock_datetime, mock_save, mock_load):
        """Test recording connection with default (current) timestamp."""
        mock_load.return_value = {}

        # Mock current time
        fixed_time = datetime(2024, 10, 18, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = fixed_time

        ConnectionTracker.record_connection("test-vm")

        # Should save with current timestamp
        expected_timestamp = fixed_time.isoformat() + "Z"
        mock_save.assert_called_once_with({"test-vm": {"last_connected": expected_timestamp}})

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    def test_record_connection_custom_timestamp(self, mock_save, mock_load):
        """Test recording connection with custom timestamp."""
        mock_load.return_value = {}

        custom_time = datetime(2024, 10, 15, 14, 30, 0, tzinfo=UTC)
        ConnectionTracker.record_connection("test-vm", timestamp=custom_time)

        expected_timestamp = custom_time.isoformat() + "Z"
        mock_save.assert_called_once_with({"test-vm": {"last_connected": expected_timestamp}})

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    @patch("azlin.connection_tracker.datetime")
    def test_record_connection_creates_new_entry(self, mock_datetime, mock_save, mock_load):
        """Test creating new connection entry for VM."""
        mock_load.return_value = {"existing-vm": {"last_connected": "2024-10-17T10:00:00Z"}}

        fixed_time = datetime(2024, 10, 18, 10, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = fixed_time

        ConnectionTracker.record_connection("new-vm")

        expected_timestamp = fixed_time.isoformat() + "Z"
        mock_save.assert_called_once_with(
            {
                "existing-vm": {"last_connected": "2024-10-17T10:00:00Z"},
                "new-vm": {"last_connected": expected_timestamp},
            }
        )

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    @patch("azlin.connection_tracker.datetime")
    def test_record_connection_updates_existing_entry(self, mock_datetime, mock_save, mock_load):
        """Test updating existing connection entry."""
        mock_load.return_value = {"test-vm": {"last_connected": "2024-10-17T10:00:00Z"}}

        fixed_time = datetime(2024, 10, 18, 15, 0, 0, tzinfo=UTC)
        mock_datetime.now.return_value = fixed_time

        ConnectionTracker.record_connection("test-vm")

        expected_timestamp = fixed_time.isoformat() + "Z"
        mock_save.assert_called_once_with({"test-vm": {"last_connected": expected_timestamp}})


class TestGetLastConnection:
    """Tests for get_last_connection method."""

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_last_connection_returns_none_for_missing_vm(self, mock_load):
        """Test that get_last_connection returns None for missing VM."""
        mock_load.return_value = {"other-vm": {"last_connected": "2024-10-18T10:00:00Z"}}

        result = ConnectionTracker.get_last_connection("missing-vm")

        assert result is None

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_last_connection_parses_iso_format(self, mock_load):
        """Test correct parsing of ISO format timestamp with Z suffix."""
        timestamp_str = "2024-10-18T10:30:45Z"
        mock_load.return_value = {"test-vm": {"last_connected": timestamp_str}}

        result = ConnectionTracker.get_last_connection("test-vm")

        expected = datetime(2024, 10, 18, 10, 30, 45, tzinfo=UTC)
        assert result == expected

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_last_connection_handles_parse_error(self, mock_load):
        """Test graceful handling of timestamp parse errors."""
        mock_load.return_value = {"test-vm": {"last_connected": "invalid-timestamp"}}

        result = ConnectionTracker.get_last_connection("test-vm")

        # Should return None and log warning
        assert result is None

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_last_connection_handles_missing_timestamp_field(self, mock_load):
        """Test handling of connection entry without timestamp field."""
        mock_load.return_value = {"test-vm": {}}

        result = ConnectionTracker.get_last_connection("test-vm")

        assert result is None


class TestGetAllConnections:
    """Tests for get_all_connections method."""

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_all_connections_returns_dict(self, mock_load):
        """Test that get_all_connections returns dict of all VMs."""
        mock_load.return_value = {
            "vm1": {"last_connected": "2024-10-18T10:00:00Z"},
            "vm2": {"last_connected": "2024-10-17T15:30:00Z"},
        }

        result = ConnectionTracker.get_all_connections()

        assert len(result) == 2
        assert "vm1" in result
        assert "vm2" in result
        assert isinstance(result["vm1"], datetime)
        assert isinstance(result["vm2"], datetime)

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_all_connections_skips_invalid_timestamps(self, mock_load):
        """Test that invalid timestamps are skipped with warning."""
        mock_load.return_value = {
            "vm1": {"last_connected": "2024-10-18T10:00:00Z"},
            "vm2": {"last_connected": "invalid-timestamp"},
            "vm3": {"last_connected": "2024-10-17T15:30:00Z"},
        }

        result = ConnectionTracker.get_all_connections()

        # Should only include valid timestamps
        assert len(result) == 2
        assert "vm1" in result
        assert "vm3" in result
        assert "vm2" not in result

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    def test_get_all_connections_handles_load_error(self, mock_load):
        """Test graceful handling when load_connections fails."""
        mock_load.side_effect = Exception("Failed to load")

        result = ConnectionTracker.get_all_connections()

        # Should return empty dict and log warning
        assert result == {}


class TestRemoveConnection:
    """Tests for remove_connection method."""

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    def test_remove_connection_returns_true_when_removed(self, mock_save, mock_load):
        """Test successful removal of connection entry."""
        mock_load.return_value = {
            "vm1": {"last_connected": "2024-10-18T10:00:00Z"},
            "vm2": {"last_connected": "2024-10-17T15:30:00Z"},
        }

        result = ConnectionTracker.remove_connection("vm1")

        assert result is True
        # Should save without the removed VM
        mock_save.assert_called_once_with({"vm2": {"last_connected": "2024-10-17T15:30:00Z"}})

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    def test_remove_connection_returns_false_when_not_found(self, mock_save, mock_load):
        """Test removal of non-existent VM returns False."""
        mock_load.return_value = {"vm1": {"last_connected": "2024-10-18T10:00:00Z"}}

        result = ConnectionTracker.remove_connection("missing-vm")

        assert result is False
        # Should not save changes
        mock_save.assert_not_called()

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    def test_remove_connection_persists_changes(self, mock_save, mock_load):
        """Test that removal is persisted to disk."""
        initial_connections = {
            "vm1": {"last_connected": "2024-10-18T10:00:00Z"},
            "vm2": {"last_connected": "2024-10-17T15:30:00Z"},
        }
        mock_load.return_value = initial_connections.copy()

        ConnectionTracker.remove_connection("vm1")

        # Verify save was called with updated connections
        saved_connections = mock_save.call_args[0][0]
        assert "vm1" not in saved_connections
        assert "vm2" in saved_connections

    @patch("azlin.connection_tracker.ConnectionTracker.load_connections")
    @patch("azlin.connection_tracker.ConnectionTracker.save_connections")
    def test_remove_connection_handles_save_error(self, mock_save, mock_load):
        """Test graceful handling of save errors during removal."""
        mock_load.return_value = {"vm1": {"last_connected": "2024-10-18T10:00:00Z"}}
        mock_save.side_effect = Exception("Disk full")

        result = ConnectionTracker.remove_connection("vm1")

        # Should return False and log warning
        assert result is False
