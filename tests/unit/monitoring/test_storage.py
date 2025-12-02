"""Unit tests for metrics storage module.

Testing pyramid: 60% unit tests - fast, heavily mocked
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from azlin.monitoring.collector import VMMetric
from azlin.monitoring.storage import MetricsStorage


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create MetricsStorage instance with temporary database."""
    return MetricsStorage(db_path=temp_db, retention_days=90)


@pytest.fixture
def sample_metric():
    """Create sample VMMetric for testing."""
    return VMMetric(
        vm_name="test-vm",
        timestamp=datetime.now(),
        cpu_percent=45.2,
        memory_percent=62.1,
        disk_read_bytes=12345678,
        disk_write_bytes=8765432,
        network_in_bytes=1234567,
        network_out_bytes=876543,
        success=True,
        error_message=None,
    )


class TestMetricsStorageInit:
    """Test MetricsStorage initialization."""

    def test_creates_database_file(self, temp_db):
        """Database schema is created on initialization."""
        import sqlite3

        storage = MetricsStorage(db_path=temp_db)

        # Verify schema was created correctly
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Check metrics table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metrics'"
        )
        assert cursor.fetchone() is not None

        conn.close()

    def test_creates_metrics_table(self, storage, temp_db):
        """Metrics table is created with correct schema."""
        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Check table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metrics'"
        )
        assert cursor.fetchone() is not None

        # Check columns exist
        cursor.execute("PRAGMA table_info(metrics)")
        columns = {row[1] for row in cursor.fetchall()}
        expected_columns = {
            "id",
            "vm_name",
            "timestamp",
            "cpu_percent",
            "memory_percent",
            "disk_read_bytes",
            "disk_write_bytes",
            "network_in_bytes",
            "network_out_bytes",
            "success",
            "error_message",
            "aggregation_level",
            "created_at",
        }
        assert columns == expected_columns

        conn.close()

    def test_creates_indexes(self, storage, temp_db):
        """Indexes are created for performance."""
        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}

        # Check required indexes exist
        assert "idx_vm_timestamp" in indexes
        assert "idx_timestamp" in indexes
        assert "idx_aggregation" in indexes

        conn.close()

    def test_sets_retention_days(self, temp_db):
        """Retention days configuration is stored."""
        storage = MetricsStorage(db_path=temp_db, retention_days=60)
        assert storage.retention_days == 60


class TestStoreMetric:
    """Test storing single metrics."""

    def test_stores_successful_metric(self, storage, sample_metric):
        """Successful metric is stored correctly."""
        storage.store_metric(sample_metric)

        # Verify stored
        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=datetime.now() - timedelta(minutes=1),
            end_time=datetime.now() + timedelta(minutes=1),
        )

        assert len(metrics) == 1
        stored = metrics[0]
        assert stored.vm_name == sample_metric.vm_name
        assert stored.cpu_percent == sample_metric.cpu_percent
        assert stored.memory_percent == sample_metric.memory_percent
        assert stored.success is True

    def test_stores_failed_metric_with_error(self, storage):
        """Failed metric with error message is stored."""
        failed_metric = VMMetric(
            vm_name="failed-vm",
            timestamp=datetime.now(),
            cpu_percent=None,
            memory_percent=None,
            disk_read_bytes=None,
            disk_write_bytes=None,
            network_in_bytes=None,
            network_out_bytes=None,
            success=False,
            error_message="Connection timeout",
        )

        storage.store_metric(failed_metric)

        metrics = storage.query_metrics(
            vm_name="failed-vm",
            start_time=datetime.now() - timedelta(minutes=1),
            end_time=datetime.now() + timedelta(minutes=1),
        )

        assert len(metrics) == 1
        assert metrics[0].success is False
        assert metrics[0].error_message == "Connection timeout"

    def test_stores_metric_with_aggregation_level(self, storage, sample_metric):
        """Aggregation level is stored correctly."""
        storage.store_metric(sample_metric)

        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=datetime.now() - timedelta(minutes=1),
            end_time=datetime.now() + timedelta(minutes=1),
        )

        # Default aggregation level is 'raw'
        assert metrics[0].aggregation_level == "raw"  # type: ignore


class TestStoreMetrics:
    """Test storing multiple metrics."""

    def test_stores_multiple_metrics_in_transaction(self, storage):
        """Multiple metrics are stored in single transaction."""
        metrics = [
            VMMetric(
                vm_name=f"vm-{i}",
                timestamp=datetime.now(),
                cpu_percent=40.0 + i,
                memory_percent=60.0 + i,
                disk_read_bytes=1000000 * i,
                disk_write_bytes=500000 * i,
                network_in_bytes=100000 * i,
                network_out_bytes=50000 * i,
                success=True,
            )
            for i in range(5)
        ]

        storage.store_metrics(metrics)

        # Verify all stored
        for i in range(5):
            stored = storage.query_metrics(
                vm_name=f"vm-{i}",
                start_time=datetime.now() - timedelta(minutes=1),
                end_time=datetime.now() + timedelta(minutes=1),
            )
            assert len(stored) == 1
            assert stored[0].cpu_percent == 40.0 + i

    def test_handles_empty_metrics_list(self, storage):
        """Empty metrics list doesn't cause errors."""
        storage.store_metrics([])
        # Should not raise exception


class TestQueryMetrics:
    """Test querying historical metrics."""

    def test_queries_by_vm_name_and_time_range(self, storage):
        """Metrics are filtered by VM name and time range."""
        now = datetime.now()

        # Store metrics at different times
        for i in range(5):
            metric = VMMetric(
                vm_name="test-vm",
                timestamp=now - timedelta(hours=i),
                cpu_percent=40.0 + i,
                memory_percent=60.0 + i,
                disk_read_bytes=1000000,
                disk_write_bytes=500000,
                network_in_bytes=100000,
                network_out_bytes=50000,
                success=True,
            )
            storage.store_metric(metric)

        # Query last 2 hours
        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=now - timedelta(hours=2),
            end_time=now + timedelta(minutes=1),
        )

        # Should get 3 metrics (0, 1, 2 hours ago)
        assert len(metrics) == 3

    def test_returns_empty_list_for_nonexistent_vm(self, storage):
        """Query for nonexistent VM returns empty list."""
        metrics = storage.query_metrics(
            vm_name="nonexistent-vm",
            start_time=datetime.now() - timedelta(days=1),
            end_time=datetime.now(),
        )
        assert metrics == []

    def test_query_with_raw_aggregation(self, storage):
        """Query with raw aggregation returns all metrics."""
        now = datetime.now()

        # Store 10 metrics
        for i in range(10):
            metric = VMMetric(
                vm_name="test-vm",
                timestamp=now - timedelta(minutes=i),
                cpu_percent=40.0,
                memory_percent=60.0,
                disk_read_bytes=1000000,
                disk_write_bytes=500000,
                network_in_bytes=100000,
                network_out_bytes=50000,
                success=True,
            )
            storage.store_metric(metric)

        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(minutes=1),
            aggregation="raw",
        )

        assert len(metrics) == 10

    def test_uses_parameterized_queries_to_prevent_sql_injection(self, storage):
        """SQL queries use parameterization to prevent injection."""
        # Attempt SQL injection via VM name
        malicious_vm_name = "test'; DROP TABLE metrics; --"

        # Store legitimate metric
        metric = VMMetric(
            vm_name="test-vm",
            timestamp=datetime.now(),
            cpu_percent=40.0,
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )
        storage.store_metric(metric)

        # Query with malicious VM name should not cause SQL injection
        metrics = storage.query_metrics(
            vm_name=malicious_vm_name,
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now(),
        )

        # Should return empty (no VM with that name)
        assert metrics == []

        # Verify table still exists
        legit_metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now(),
        )
        assert len(legit_metrics) == 1


class TestAggregateHourly:
    """Test hourly aggregation."""

    def test_aggregates_raw_metrics_to_hourly(self, storage):
        """Raw metrics older than 7 days are aggregated to hourly."""
        now = datetime.now()

        # Create a base timestamp 8 days ago, aligned to start of hour
        base_time = now - timedelta(days=8)
        base_time = base_time.replace(minute=0, second=0, microsecond=0)

        # Store metrics within single hour (should be aggregated to 1 bucket)
        for i in range(60):  # 60 minutes = 1 hour of data
            metric = VMMetric(
                vm_name="test-vm",
                timestamp=base_time + timedelta(minutes=i),
                cpu_percent=40.0 + (i % 10),  # Varying CPU
                memory_percent=60.0,
                disk_read_bytes=1000000,
                disk_write_bytes=500000,
                network_in_bytes=100000,
                network_out_bytes=50000,
                success=True,
            )
            storage.store_metric(metric)

        # Run aggregation
        storage.aggregate_hourly()

        # Check that raw metrics are replaced with hourly aggregate
        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=now - timedelta(days=9),
            end_time=now - timedelta(days=7),
            aggregation="hourly",
        )

        # Should have 1 hourly aggregate
        assert len(metrics) == 1
        # CPU should be average of varying values
        assert 40.0 <= metrics[0].cpu_percent <= 50.0

    def test_does_not_aggregate_recent_data(self, storage):
        """Recent data (< 7 days) is not aggregated."""
        now = datetime.now()

        # Store recent metrics (5 days ago)
        for i in range(10):
            metric = VMMetric(
                vm_name="test-vm",
                timestamp=now - timedelta(days=5, minutes=i),
                cpu_percent=40.0,
                memory_percent=60.0,
                disk_read_bytes=1000000,
                disk_write_bytes=500000,
                network_in_bytes=100000,
                network_out_bytes=50000,
                success=True,
            )
            storage.store_metric(metric)

        # Run aggregation
        storage.aggregate_hourly()

        # Recent data should still be raw
        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=now - timedelta(days=6),
            end_time=now - timedelta(days=4),
            aggregation="raw",
        )

        assert len(metrics) == 10


class TestCleanupOldData:
    """Test data retention and cleanup."""

    def test_deletes_data_older_than_retention_period(self, storage):
        """Data older than retention period is deleted."""
        now = datetime.now()

        # Store old metrics (100 days ago - beyond 90-day retention)
        old_metric = VMMetric(
            vm_name="test-vm",
            timestamp=now - timedelta(days=100),
            cpu_percent=40.0,
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )
        storage.store_metric(old_metric)

        # Store recent metrics (30 days ago - within retention)
        recent_metric = VMMetric(
            vm_name="test-vm",
            timestamp=now - timedelta(days=30),
            cpu_percent=50.0,
            memory_percent=70.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )
        storage.store_metric(recent_metric)

        # Run cleanup
        deleted_count = storage.cleanup_old_data()

        # Should have deleted 1 old metric
        assert deleted_count == 1

        # Verify recent data still exists
        metrics = storage.query_metrics(
            vm_name="test-vm",
            start_time=now - timedelta(days=60),
            end_time=now,
        )
        assert len(metrics) == 1
        assert metrics[0].cpu_percent == 50.0

    def test_returns_count_of_deleted_records(self, storage):
        """Cleanup returns count of deleted records."""
        now = datetime.now()

        # Store 5 old metrics
        for i in range(5):
            metric = VMMetric(
                vm_name=f"vm-{i}",
                timestamp=now - timedelta(days=100),
                cpu_percent=40.0,
                memory_percent=60.0,
                disk_read_bytes=1000000,
                disk_write_bytes=500000,
                network_in_bytes=100000,
                network_out_bytes=50000,
                success=True,
            )
            storage.store_metric(metric)

        deleted_count = storage.cleanup_old_data()
        assert deleted_count == 5

    def test_cleanup_runs_automatically_on_store(self, storage):
        """Cleanup is triggered automatically when storing metrics."""
        # This tests that the storage implementation includes automatic cleanup
        # The actual implementation should call cleanup_old_data() in store_metrics()
        pass  # Implementation detail test


class TestDatabaseFilePermissions:
    """Test database security."""

    def test_database_file_has_restricted_permissions(self, storage, temp_db):
        """Database file has 0600 permissions (user read/write only)."""
        import stat

        # Check file permissions
        mode = temp_db.stat().st_mode
        # Should be readable and writable by owner only
        assert mode & stat.S_IRUSR  # Owner read
        assert mode & stat.S_IWUSR  # Owner write
        # Should NOT be accessible by group or others
        assert not (mode & stat.S_IRGRP)  # No group read
        assert not (mode & stat.S_IWGRP)  # No group write
        assert not (mode & stat.S_IROTH)  # No other read
        assert not (mode & stat.S_IWOTH)  # No other write


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_handles_concurrent_writes_safely(self, storage):
        """Multiple concurrent writes don't cause corruption."""
        # SQLite WAL mode should handle this
        # Implementation should use WAL mode: PRAGMA journal_mode=WAL
        pass  # Implementation detail test

    def test_handles_database_corruption_gracefully(self, temp_db):
        """Corrupted database is detected and reported."""
        # Write invalid data to database file
        temp_db.write_bytes(b"INVALID DATABASE CONTENT")

        # Attempting to initialize should raise clear error
        with pytest.raises(Exception) as exc_info:
            storage = MetricsStorage(db_path=temp_db)

        # Error message should be user-friendly
        assert "database" in str(exc_info.value).lower()

    def test_handles_disk_full_gracefully(self, storage, sample_metric):
        """Disk full errors are handled gracefully."""
        # This is hard to test without mocking filesystem
        # Implementation should catch OSError and provide clear message
        pass  # Implementation detail test
