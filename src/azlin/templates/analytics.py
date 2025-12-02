"""Template usage analytics with SQLite tracking.

Provides:
- AnalyticsDB: SQLite database connection and schema management
- AnalyticsTracker: Track template usage events
- AnalyticsReporter: Generate analytics reports

Philosophy:
- Zero-BS: All functions work, no stubs
- SQLite for local storage
- Privacy-focused with opt-out and anonymization
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import sqlite3
import json
import hashlib


@dataclass
class UsageEvent:
    """Single template usage event."""
    event_id: int
    template_name: str
    user_id: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TemplateStats:
    """Statistics for a template."""
    name: str
    usage_count: int
    unique_users: int = 0
    average_duration: float = 0.0
    success_rate: float = 0.0


@dataclass
class TemplateReport:
    """Comprehensive template report."""
    template_name: str
    total_uses: int
    unique_users: int
    average_duration: float = 0.0
    success_rate: float = 0.0
    usage_by_region: Dict[str, int] = field(default_factory=dict)

    def to_json(self) -> Dict:
        """Export report to JSON."""
        return {
            "template_name": self.template_name,
            "total_uses": self.total_uses,
            "unique_users": self.unique_users,
            "average_duration": self.average_duration,
            "success_rate": self.success_rate,
            "usage_by_region": self.usage_by_region
        }


@dataclass
class SummaryReport:
    """Summary report for all templates."""
    total_templates: int
    total_uses: int
    templates: List[TemplateStats] = field(default_factory=list)


class AnalyticsDB:
    """SQLite database for analytics storage."""

    def __init__(self, db_path: Path, pool_size: int = 1):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
            pool_size: Connection pool size (unused in SQLite)
        """
        self.db_path = db_path
        self.pool_size = pool_size

        # Ensure parent directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create connection
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

        # Create schema
        self._create_schema()

    def _create_schema(self) -> None:
        """Create database schema if it doesn't exist."""
        cursor = self.conn.cursor()

        # Usage events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Template stats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS template_stats (
                template_name TEXT PRIMARY KEY,
                usage_count INTEGER DEFAULT 0,
                unique_users INTEGER DEFAULT 0,
                last_used TEXT
            )
        """)

        # User activity table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id TEXT,
                template_name TEXT,
                usage_count INTEGER DEFAULT 0,
                last_used TEXT,
                opt_out INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, template_name)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_template_name
            ON usage_events(template_name)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id
            ON usage_events(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON usage_events(timestamp)
        """)

        self.conn.commit()

    def is_connected(self) -> bool:
        """Check if database connection is active."""
        try:
            self.conn.execute("SELECT 1")
            return True
        except:
            return False

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def get_tables(self) -> List[str]:
        """Get list of tables in database."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)
        return [row[0] for row in cursor.fetchall()]

    def execute_query(self, query: str) -> List[Dict]:
        """Execute a query and return results."""
        cursor = self.conn.cursor()
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


class AnalyticsTracker:
    """Track template usage analytics."""

    def __init__(
        self,
        db_path: Path,
        anonymize_users: bool = False,
        retention_days: Optional[int] = None
    ):
        """Initialize analytics tracker.

        Args:
            db_path: Path to analytics database
            anonymize_users: If True, hash user IDs
            retention_days: Days to retain data (None = forever)
        """
        self.db = AnalyticsDB(db_path)
        self.anonymize_users = anonymize_users
        self.retention_days = retention_days

    def _anonymize_user_id(self, user_id: str) -> str:
        """Anonymize user ID by hashing.

        Args:
            user_id: Original user ID

        Returns:
            Hashed user ID
        """
        return hashlib.sha256(user_id.encode()).hexdigest()[:16]

    def _check_opt_out(self, user_id: str) -> bool:
        """Check if user has opted out of tracking.

        Args:
            user_id: User ID to check

        Returns:
            True if user opted out
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT opt_out FROM user_activity
            WHERE user_id = ? AND opt_out = 1
            LIMIT 1
        """, (user_id,))

        result = cursor.fetchone()
        return result is not None

    def set_user_opt_out(self, user_id: str, opt_out: bool) -> None:
        """Set user opt-out preference.

        Args:
            user_id: User ID
            opt_out: True to opt out, False to opt in
        """
        if self.anonymize_users:
            user_id = self._anonymize_user_id(user_id)

        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO user_activity (user_id, template_name, opt_out)
            VALUES (?, '', ?)
        """, (user_id, 1 if opt_out else 0))

        self.db.conn.commit()

    def record_usage(
        self,
        template_name: str,
        user_id: str,
        timestamp: datetime,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """Record a template usage event.

        Args:
            template_name: Name of template used
            user_id: User who used template
            timestamp: When template was used
            metadata: Additional metadata (region, success, duration, etc.)

        Returns:
            Event ID if recorded, None if user opted out
        """
        # Check opt-out
        if self._check_opt_out(user_id):
            return None

        # Anonymize if needed
        if self.anonymize_users:
            user_id = self._anonymize_user_id(user_id)

        # Insert usage event
        cursor = self.db.conn.cursor()
        cursor.execute("""
            INSERT INTO usage_events (template_name, user_id, timestamp, metadata)
            VALUES (?, ?, ?, ?)
        """, (
            template_name,
            user_id,
            timestamp.isoformat(),
            json.dumps(metadata or {})
        ))

        event_id = cursor.lastrowid
        self.db.conn.commit()

        return event_id

    def bulk_record_usage(self, events: List[Tuple[str, str, datetime]]) -> None:
        """Bulk insert usage events for performance.

        Args:
            events: List of (template_name, user_id, timestamp) tuples
        """
        cursor = self.db.conn.cursor()

        for template_name, user_id, timestamp in events:
            if self.anonymize_users:
                user_id = self._anonymize_user_id(user_id)

            cursor.execute("""
                INSERT INTO usage_events (template_name, user_id, timestamp, metadata)
                VALUES (?, ?, ?, ?)
            """, (template_name, user_id, timestamp.isoformat(), "{}"))

        self.db.conn.commit()

    def get_usage_event(self, event_id: int) -> UsageEvent:
        """Get usage event by ID.

        Args:
            event_id: Event ID

        Returns:
            UsageEvent instance
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT * FROM usage_events WHERE event_id = ?
        """, (event_id,))

        row = cursor.fetchone()
        if row:
            return UsageEvent(
                event_id=row["event_id"],
                template_name=row["template_name"],
                user_id=row["user_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                metadata=json.loads(row["metadata"] or "{}")
            )

    def get_usage_count(
        self,
        template_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """Get usage count for a template.

        Args:
            template_name: Template name
            start_date: Start of date range (optional)
            end_date: End of date range (optional)

        Returns:
            Number of uses
        """
        cursor = self.db.conn.cursor()

        if start_date and end_date:
            cursor.execute("""
                SELECT COUNT(*) as count FROM usage_events
                WHERE template_name = ? AND timestamp >= ? AND timestamp <= ?
            """, (template_name, start_date.isoformat(), end_date.isoformat()))
        else:
            cursor.execute("""
                SELECT COUNT(*) as count FROM usage_events
                WHERE template_name = ?
            """, (template_name,))

        result = cursor.fetchone()
        return result["count"] if result else 0

    def get_unique_users(self, template_name: str) -> int:
        """Get count of unique users for a template.

        Args:
            template_name: Template name

        Returns:
            Number of unique users
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) as count FROM usage_events
            WHERE template_name = ?
        """, (template_name,))

        result = cursor.fetchone()
        return result["count"] if result else 0

    def get_most_used_templates(self, limit: int = 10) -> List[TemplateStats]:
        """Get most used templates.

        Args:
            limit: Maximum number of templates to return

        Returns:
            List of TemplateStats sorted by usage count
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT template_name, COUNT(*) as usage_count
            FROM usage_events
            GROUP BY template_name
            ORDER BY usage_count DESC
            LIMIT ?
        """, (limit,))

        results = []
        for row in cursor.fetchall():
            results.append(TemplateStats(
                name=row["template_name"],
                usage_count=row["usage_count"]
            ))

        return results

    def get_trending_templates(self, days: int = 7, limit: int = 10) -> List[TemplateStats]:
        """Get trending templates (increasing usage).

        Args:
            days: Number of days to analyze
            limit: Maximum templates to return

        Returns:
            List of trending templates
        """
        cutoff = datetime.now() - timedelta(days=days)

        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT template_name, COUNT(*) as usage_count
            FROM usage_events
            WHERE timestamp >= ?
            GROUP BY template_name
            ORDER BY usage_count DESC
            LIMIT ?
        """, (cutoff.isoformat(), limit))

        results = []
        for row in cursor.fetchall():
            results.append(TemplateStats(
                name=row["template_name"],
                usage_count=row["usage_count"]
            ))

        return results

    def get_usage_by_region(self, template_name: str) -> Dict[str, int]:
        """Get usage statistics by region.

        Args:
            template_name: Template name

        Returns:
            Dictionary mapping region to usage count
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT metadata FROM usage_events
            WHERE template_name = ?
        """, (template_name,))

        region_counts = {}
        for row in cursor.fetchall():
            metadata = json.loads(row["metadata"] or "{}")
            region = metadata.get("region")
            if region:
                region_counts[region] = region_counts.get(region, 0) + 1

        return region_counts

    def get_success_rate(self, template_name: str) -> float:
        """Calculate template success rate.

        Args:
            template_name: Template name

        Returns:
            Success rate as percentage (0-100)
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT metadata FROM usage_events
            WHERE template_name = ?
        """, (template_name,))

        total = 0
        successes = 0

        for row in cursor.fetchall():
            total += 1
            metadata = json.loads(row["metadata"] or "{}")
            if metadata.get("success", False):
                successes += 1

        if total == 0:
            return 0.0

        return (successes / total) * 100

    def get_average_duration(self, template_name: str) -> float:
        """Calculate average template execution duration.

        Args:
            template_name: Template name

        Returns:
            Average duration in seconds
        """
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT metadata FROM usage_events
            WHERE template_name = ?
        """, (template_name,))

        durations = []

        for row in cursor.fetchall():
            metadata = json.loads(row["metadata"] or "{}")
            duration = metadata.get("duration_seconds")
            if duration is not None:
                durations.append(duration)

        if not durations:
            return 0.0

        return sum(durations) / len(durations)

    def get_user_history(self, user_id: str) -> List[UsageEvent]:
        """Get user's template usage history.

        Args:
            user_id: User ID

        Returns:
            List of UsageEvent instances
        """
        if self.anonymize_users:
            user_id = self._anonymize_user_id(user_id)

        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT * FROM usage_events
            WHERE user_id = ?
            ORDER BY timestamp DESC
        """, (user_id,))

        results = []
        for row in cursor.fetchall():
            results.append(UsageEvent(
                event_id=row["event_id"],
                template_name=row["template_name"],
                user_id=row["user_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                metadata=json.loads(row["metadata"] or "{}")
            ))

        return results

    def get_user_favorites(self, user_id: str, limit: int = 5) -> List[TemplateStats]:
        """Get user's most frequently used templates.

        Args:
            user_id: User ID
            limit: Maximum templates to return

        Returns:
            List of TemplateStats
        """
        if self.anonymize_users:
            user_id = self._anonymize_user_id(user_id)

        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT template_name, COUNT(*) as usage_count
            FROM usage_events
            WHERE user_id = ?
            GROUP BY template_name
            ORDER BY usage_count DESC
            LIMIT ?
        """, (user_id, limit))

        results = []
        for row in cursor.fetchall():
            results.append(TemplateStats(
                name=row["template_name"],
                usage_count=row["usage_count"]
            ))

        return results

    def get_user_timeline(self, user_id: str, days: int = 30) -> List[UsageEvent]:
        """Get user's activity timeline.

        Args:
            user_id: User ID
            days: Number of days to include

        Returns:
            List of UsageEvent instances
        """
        if self.anonymize_users:
            user_id = self._anonymize_user_id(user_id)

        cutoff = datetime.now() - timedelta(days=days)

        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT * FROM usage_events
            WHERE user_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (user_id, cutoff.isoformat()))

        results = []
        for row in cursor.fetchall():
            results.append(UsageEvent(
                event_id=row["event_id"],
                template_name=row["template_name"],
                user_id=row["user_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                metadata=json.loads(row["metadata"] or "{}")
            ))

        return results

    def cleanup_old_data(self) -> None:
        """Clean up old data based on retention policy."""
        if self.retention_days is None:
            return

        cutoff = datetime.now() - timedelta(days=self.retention_days)

        cursor = self.db.conn.cursor()
        cursor.execute("""
            DELETE FROM usage_events
            WHERE timestamp < ?
        """, (cutoff.isoformat(),))

        self.db.conn.commit()


class AnalyticsReporter:
    """Generate analytics reports."""

    def __init__(self, db_path: Path):
        """Initialize reporter.

        Args:
            db_path: Path to analytics database
        """
        self.tracker = AnalyticsTracker(db_path)

    def generate_template_report(self, template_name: str) -> TemplateReport:
        """Generate comprehensive report for a template.

        Args:
            template_name: Template name

        Returns:
            TemplateReport instance
        """
        return TemplateReport(
            template_name=template_name,
            total_uses=self.tracker.get_usage_count(template_name),
            unique_users=self.tracker.get_unique_users(template_name),
            average_duration=self.tracker.get_average_duration(template_name),
            success_rate=self.tracker.get_success_rate(template_name),
            usage_by_region=self.tracker.get_usage_by_region(template_name)
        )

    def generate_summary_report(self) -> SummaryReport:
        """Generate summary report for all templates.

        Returns:
            SummaryReport instance
        """
        templates = self.tracker.get_most_used_templates(limit=1000)

        total_uses = sum(t.usage_count for t in templates)

        return SummaryReport(
            total_templates=len(templates),
            total_uses=total_uses,
            templates=templates
        )

    def export_summary_to_csv(self, output_path: Path) -> None:
        """Export summary report to CSV.

        Args:
            output_path: Path to output CSV file
        """
        summary = self.generate_summary_report()

        # Write CSV
        lines = ["template_name,usage_count\n"]
        for template in summary.templates:
            lines.append(f"{template.name},{template.usage_count}\n")

        output_path.write_text("".join(lines))


__all__ = [
    "AnalyticsDB",
    "AnalyticsTracker",
    "AnalyticsReporter",
    "UsageEvent",
    "TemplateStats",
    "TemplateReport",
    "SummaryReport"
]
