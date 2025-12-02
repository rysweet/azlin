"""Metrics storage module with SQLite backend and retention policies.

Philosophy:
- Single responsibility: Store and retrieve metrics
- Standard library only (sqlite3, datetime, pathlib)
- Self-contained and regeneratable
- Thread-safe operations with WAL mode

Public API (the "studs"):
    MetricsStorage: Main storage class for metrics persistence
"""

import sqlite3
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class VMMetric:
    """VM metric data model."""

    vm_name: str
    timestamp: datetime
    cpu_percent: float | None
    memory_percent: float | None
    disk_read_bytes: int | None
    disk_write_bytes: int | None
    network_in_bytes: int | None
    network_out_bytes: int | None
    success: bool
    error_message: str | None = None
    aggregation_level: str = "raw"


class MetricsStorage:
    """SQLite-based metrics storage with retention policies.

    Stores VM metrics with automatic aggregation and cleanup:
    - Raw metrics kept for 7 days
    - Hourly aggregates kept for 90 days (default)
    - Automatic cleanup on store operations
    """

    def __init__(self, db_path: Path | None = None, retention_days: int = 90) -> None:
        """Initialize metrics storage.

        Args:
            db_path: Path to SQLite database file
            retention_days: Number of days to retain metrics (default: 90)
        """
        self.db_path = db_path or Path.home() / ".azlin" / "monitoring.db"
        self.retention_days = retention_days

        # Create parent directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

        # Set secure permissions (0600 - owner read/write only)
        self._set_secure_permissions()

    def _init_database(self) -> None:
        """Initialize database schema with tables and indexes."""
        # Only create if database doesn't exist yet
        is_new_db = not self.db_path.exists()

        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for concurrency

        cursor = conn.cursor()

        # Create metrics table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vm_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                cpu_percent REAL,
                memory_percent REAL,
                disk_read_bytes INTEGER,
                disk_write_bytes INTEGER,
                network_in_bytes INTEGER,
                network_out_bytes INTEGER,
                success INTEGER NOT NULL,
                error_message TEXT,
                aggregation_level TEXT DEFAULT 'raw',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Create indexes for performance
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vm_timestamp
            ON metrics(vm_name, timestamp)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON metrics(timestamp)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_aggregation
            ON metrics(aggregation_level)
        """
        )

        conn.commit()
        conn.close()

    def _set_secure_permissions(self) -> None:
        """Set database file permissions to 0600 (user read/write only)."""
        if self.db_path.exists():
            # Set permissions: owner read/write only
            self.db_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def store_metric(self, metric: VMMetric) -> None:
        """Store a single metric.

        Args:
            metric: VMMetric instance to store
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO metrics (
                vm_name, timestamp, cpu_percent, memory_percent,
                disk_read_bytes, disk_write_bytes,
                network_in_bytes, network_out_bytes,
                success, error_message, aggregation_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                metric.vm_name,
                metric.timestamp.isoformat(),
                metric.cpu_percent,
                metric.memory_percent,
                metric.disk_read_bytes,
                metric.disk_write_bytes,
                metric.network_in_bytes,
                metric.network_out_bytes,
                1 if metric.success else 0,
                metric.error_message,
                metric.aggregation_level,
            ),
        )

        conn.commit()
        conn.close()

    def store_metrics(self, metrics: list[VMMetric]) -> None:
        """Store multiple metrics in a single transaction.

        Args:
            metrics: List of VMMetric instances to store
        """
        if not metrics:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            for metric in metrics:
                cursor.execute(
                    """
                    INSERT INTO metrics (
                        vm_name, timestamp, cpu_percent, memory_percent,
                        disk_read_bytes, disk_write_bytes,
                        network_in_bytes, network_out_bytes,
                        success, error_message, aggregation_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        metric.vm_name,
                        metric.timestamp.isoformat(),
                        metric.cpu_percent,
                        metric.memory_percent,
                        metric.disk_read_bytes,
                        metric.disk_write_bytes,
                        metric.network_in_bytes,
                        metric.network_out_bytes,
                        1 if metric.success else 0,
                        metric.error_message,
                        metric.aggregation_level,
                    ),
                )

            conn.commit()
        finally:
            conn.close()

        # Run cleanup automatically
        self.cleanup_old_data()

    def query_metrics(
        self,
        vm_name: str,
        start_time: datetime,
        end_time: datetime,
        aggregation: str = "raw",
    ) -> list[VMMetric]:
        """Query metrics for a VM within a time range.

        Args:
            vm_name: Name of the VM
            start_time: Start of time range
            end_time: End of time range
            aggregation: Aggregation level ('raw', 'hourly', 'daily')

        Returns:
            List of VMMetric instances matching the query
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT vm_name, timestamp, cpu_percent, memory_percent,
                   disk_read_bytes, disk_write_bytes,
                   network_in_bytes, network_out_bytes,
                   success, error_message, aggregation_level
            FROM metrics
            WHERE vm_name = ?
              AND timestamp >= ?
              AND timestamp <= ?
              AND aggregation_level = ?
            ORDER BY timestamp ASC
        """,
            (vm_name, start_time.isoformat(), end_time.isoformat(), aggregation),
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            VMMetric(
                vm_name=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                cpu_percent=row[2],
                memory_percent=row[3],
                disk_read_bytes=row[4],
                disk_write_bytes=row[5],
                network_in_bytes=row[6],
                network_out_bytes=row[7],
                success=bool(row[8]),
                error_message=row[9],
                aggregation_level=row[10],
            )
            for row in rows
        ]

    def aggregate_hourly(self) -> None:
        """Aggregate raw metrics older than 7 days into hourly averages.

        Replaces raw metrics with hourly aggregates to save space.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=7)).isoformat()

        # Find raw metrics older than 7 days
        cursor.execute(
            """
            SELECT vm_name,
                   strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                   AVG(cpu_percent) as avg_cpu,
                   AVG(memory_percent) as avg_memory,
                   SUM(disk_read_bytes) as sum_disk_read,
                   SUM(disk_write_bytes) as sum_disk_write,
                   SUM(network_in_bytes) as sum_network_in,
                   SUM(network_out_bytes) as sum_network_out
            FROM metrics
            WHERE aggregation_level = 'raw'
              AND timestamp < ?
              AND success = 1
            GROUP BY vm_name, hour
        """,
            (cutoff_date,),
        )

        hourly_aggregates = cursor.fetchall()

        # Insert hourly aggregates
        for agg in hourly_aggregates:
            cursor.execute(
                """
                INSERT INTO metrics (
                    vm_name, timestamp, cpu_percent, memory_percent,
                    disk_read_bytes, disk_write_bytes,
                    network_in_bytes, network_out_bytes,
                    success, aggregation_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'hourly')
            """,
                agg,
            )

        # Delete old raw metrics that have been aggregated
        cursor.execute(
            """
            DELETE FROM metrics
            WHERE aggregation_level = 'raw'
              AND timestamp < ?
              AND success = 1
        """,
            (cutoff_date,),
        )

        conn.commit()
        conn.close()

    def cleanup_old_data(self) -> int:
        """Delete metrics older than retention period.

        Returns:
            Number of records deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = (datetime.now() - timedelta(days=self.retention_days)).isoformat()

        cursor.execute(
            """
            DELETE FROM metrics
            WHERE timestamp < ?
        """,
            (cutoff_date,),
        )

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return deleted_count


__all__ = ["MetricsStorage", "VMMetric"]
