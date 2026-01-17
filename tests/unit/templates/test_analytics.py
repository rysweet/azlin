"""Unit tests for template usage analytics.

Test coverage: Template usage analytics (SQLite tracking)

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest


class TestAnalyticsDatabase:
    """Test analytics database initialization and operations."""

    def test_database_initialization(self):
        """Test creating analytics database."""
        import tempfile

        from azlin.templates.analytics import AnalyticsDB

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "analytics.db"
            db = AnalyticsDB(db_path)

            assert db_path.exists()
            assert db.is_connected()

    def test_database_schema_creation(self):
        """Test database schema is created properly."""
        import tempfile

        from azlin.templates.analytics import AnalyticsDB

        with tempfile.TemporaryDirectory() as tmpdir:
            db = AnalyticsDB(Path(tmpdir) / "analytics.db")

            # Check tables exist
            tables = db.get_tables()
            assert "usage_events" in tables
            assert "template_stats" in tables
            assert "user_activity" in tables

    def test_database_connection_pooling(self):
        """Test database connection pooling for performance."""
        import tempfile

        from azlin.templates.analytics import AnalyticsDB

        with tempfile.TemporaryDirectory() as tmpdir:
            db = AnalyticsDB(Path(tmpdir) / "analytics.db", pool_size=5)

            # Multiple concurrent operations should work
            for i in range(10):
                db.execute_query(f"SELECT {i}")

            assert db.is_connected()

    def test_database_close(self):
        """Test properly closing database connection."""
        import tempfile

        from azlin.templates.analytics import AnalyticsDB

        with tempfile.TemporaryDirectory() as tmpdir:
            db = AnalyticsDB(Path(tmpdir) / "analytics.db")
            db.close()

            assert not db.is_connected()


class TestUsageTracking:
    """Test tracking template usage events."""

    def test_record_template_use(self):
        """Test recording a template usage event."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            event_id = tracker.record_usage(
                template_name="vm-basic", user_id="user1", timestamp=datetime.now()
            )

            assert event_id is not None
            assert isinstance(event_id, int)

    def test_record_usage_with_metadata(self):
        """Test recording usage with additional metadata."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            event_id = tracker.record_usage(
                template_name="vm-basic",
                user_id="user1",
                timestamp=datetime.now(),
                metadata={"region": "eastus", "success": True, "duration_seconds": 45.2},
            )

            event = tracker.get_usage_event(event_id)
            assert event.metadata["region"] == "eastus"
            assert event.metadata["success"] is True

    def test_get_usage_count(self):
        """Test getting usage count for a template."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Record multiple uses
            for i in range(5):
                tracker.record_usage(
                    template_name="vm-basic", user_id=f"user{i}", timestamp=datetime.now()
                )

            count = tracker.get_usage_count("vm-basic")
            assert count == 5

    def test_get_usage_count_by_date_range(self):
        """Test getting usage count within date range."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            now = datetime.now()
            yesterday = now - timedelta(days=1)
            last_week = now - timedelta(days=7)

            # Record uses at different times
            tracker.record_usage("vm-basic", "user1", last_week)
            tracker.record_usage("vm-basic", "user2", yesterday)
            tracker.record_usage("vm-basic", "user3", now)

            # Count only recent uses
            count = tracker.get_usage_count("vm-basic", start_date=yesterday, end_date=now)

            assert count == 2  # Only yesterday and today

    def test_get_unique_users(self):
        """Test getting unique user count for a template."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Same user uses template multiple times
            tracker.record_usage("vm-basic", "user1", datetime.now())
            tracker.record_usage("vm-basic", "user1", datetime.now())
            tracker.record_usage("vm-basic", "user2", datetime.now())

            unique_users = tracker.get_unique_users("vm-basic")
            assert unique_users == 2


class TestUsageStatistics:
    """Test usage statistics calculations."""

    def test_get_most_used_templates(self):
        """Test getting most used templates."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Record different usage counts
            for i in range(5):
                tracker.record_usage("template-a", "user1", datetime.now())
            for i in range(3):
                tracker.record_usage("template-b", "user1", datetime.now())
            tracker.record_usage("template-c", "user1", datetime.now())

            most_used = tracker.get_most_used_templates(limit=2)

            assert len(most_used) == 2
            assert most_used[0].name == "template-a"
            assert most_used[0].usage_count == 5
            assert most_used[1].name == "template-b"

    def test_get_trending_templates(self):
        """Test getting trending templates (increasing usage)."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            now = datetime.now()
            week_ago = now - timedelta(days=7)

            # Template A: increasing trend
            tracker.record_usage("template-a", "user1", week_ago)
            for i in range(5):
                tracker.record_usage("template-a", f"user{i}", now)

            # Template B: flat trend
            tracker.record_usage("template-b", "user1", week_ago)
            tracker.record_usage("template-b", "user2", now)

            trending = tracker.get_trending_templates(days=7, limit=1)

            assert len(trending) >= 1
            assert trending[0].name == "template-a"

    def test_get_usage_by_region(self):
        """Test getting usage statistics by region."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Record uses in different regions
            tracker.record_usage("vm-basic", "user1", datetime.now(), metadata={"region": "eastus"})
            tracker.record_usage("vm-basic", "user2", datetime.now(), metadata={"region": "eastus"})
            tracker.record_usage("vm-basic", "user3", datetime.now(), metadata={"region": "westus"})

            by_region = tracker.get_usage_by_region("vm-basic")

            assert by_region["eastus"] == 2
            assert by_region["westus"] == 1

    def test_get_success_rate(self):
        """Test calculating template success rate."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Record successes and failures
            tracker.record_usage("vm-basic", "user1", datetime.now(), metadata={"success": True})
            tracker.record_usage("vm-basic", "user2", datetime.now(), metadata={"success": True})
            tracker.record_usage("vm-basic", "user3", datetime.now(), metadata={"success": False})

            success_rate = tracker.get_success_rate("vm-basic")

            assert success_rate == pytest.approx(66.67, rel=0.1)

    def test_get_average_duration(self):
        """Test calculating average template execution duration."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Record different durations
            durations = [30.0, 45.0, 60.0]
            for duration in durations:
                tracker.record_usage(
                    "vm-basic", "user1", datetime.now(), metadata={"duration_seconds": duration}
                )

            avg_duration = tracker.get_average_duration("vm-basic")

            assert avg_duration == 45.0


class TestUserActivityTracking:
    """Test tracking individual user activity."""

    def test_get_user_template_history(self):
        """Test getting user's template usage history."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # User uses multiple templates
            tracker.record_usage("template-a", "user1", datetime.now())
            tracker.record_usage("template-b", "user1", datetime.now())
            tracker.record_usage("template-a", "user1", datetime.now())

            history = tracker.get_user_history("user1")

            assert len(history) == 3
            assert history[0].template_name in ["template-a", "template-b"]

    def test_get_user_favorite_templates(self):
        """Test getting user's most frequently used templates."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # User has preferences
            for i in range(5):
                tracker.record_usage("template-a", "user1", datetime.now())
            for i in range(2):
                tracker.record_usage("template-b", "user1", datetime.now())

            favorites = tracker.get_user_favorites("user1", limit=1)

            assert len(favorites) == 1
            assert favorites[0].name == "template-a"

    def test_get_user_activity_timeline(self):
        """Test getting user's activity over time."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            now = datetime.now()
            yesterday = now - timedelta(days=1)

            tracker.record_usage("template-a", "user1", yesterday)
            tracker.record_usage("template-b", "user1", now)

            timeline = tracker.get_user_timeline("user1", days=7)

            assert len(timeline) == 2
            assert timeline[0].timestamp < timeline[1].timestamp


class TestAnalyticsReporting:
    """Test analytics report generation."""

    def test_generate_template_report(self):
        """Test generating comprehensive template report."""
        import tempfile

        from azlin.templates.analytics import AnalyticsReporter

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AnalyticsReporter(db_path=Path(tmpdir) / "analytics.db")

            # Record some data
            reporter.tracker.record_usage("vm-basic", "user1", datetime.now())
            reporter.tracker.record_usage("vm-basic", "user2", datetime.now())

            report = reporter.generate_template_report("vm-basic")

            assert "vm-basic" in report.template_name
            assert report.total_uses >= 2
            assert report.unique_users >= 2

    def test_generate_summary_report(self):
        """Test generating summary report for all templates."""
        import tempfile

        from azlin.templates.analytics import AnalyticsReporter

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AnalyticsReporter(db_path=Path(tmpdir) / "analytics.db")

            # Record data for multiple templates
            reporter.tracker.record_usage("template-a", "user1", datetime.now())
            reporter.tracker.record_usage("template-b", "user1", datetime.now())

            report = reporter.generate_summary_report()

            assert report.total_templates >= 2
            assert report.total_uses >= 2

    def test_export_report_to_json(self):
        """Test exporting report to JSON format."""
        import tempfile

        from azlin.templates.analytics import AnalyticsReporter

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AnalyticsReporter(db_path=Path(tmpdir) / "analytics.db")

            reporter.tracker.record_usage("vm-basic", "user1", datetime.now())

            report = reporter.generate_template_report("vm-basic")
            json_data = report.to_json()

            assert "template_name" in json_data
            assert "total_uses" in json_data
            assert json_data["template_name"] == "vm-basic"

    def test_export_report_to_csv(self):
        """Test exporting report to CSV format."""
        import tempfile

        from azlin.templates.analytics import AnalyticsReporter

        with tempfile.TemporaryDirectory() as tmpdir:
            reporter = AnalyticsReporter(db_path=Path(tmpdir) / "analytics.db")

            reporter.tracker.record_usage("template-a", "user1", datetime.now())
            reporter.tracker.record_usage("template-b", "user2", datetime.now())

            csv_path = Path(tmpdir) / "report.csv"
            reporter.export_summary_to_csv(csv_path)

            assert csv_path.exists()
            content = csv_path.read_text()
            assert "template_name" in content
            assert "template-a" in content


class TestAnalyticsPrivacy:
    """Test privacy and data handling in analytics."""

    def test_anonymize_user_data(self):
        """Test anonymizing user data for privacy."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db", anonymize_users=True)

            tracker.record_usage("vm-basic", "user1@example.com", datetime.now())

            # User ID should be hashed
            history = tracker.get_user_history("user1@example.com")
            assert len(history) > 0
            # But actual user ID not stored in plaintext

    def test_data_retention_policy(self):
        """Test automatic data cleanup based on retention policy."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db", retention_days=7)

            old_date = datetime.now() - timedelta(days=30)
            tracker.record_usage("vm-basic", "user1", old_date)

            # Apply retention policy
            tracker.cleanup_old_data()

            # Old data should be removed
            count = tracker.get_usage_count("vm-basic")
            assert count == 0

    def test_opt_out_tracking(self):
        """Test user opt-out from tracking."""
        import tempfile

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # User opts out
            tracker.set_user_opt_out("user1", opt_out=True)

            # Usage should not be recorded
            event_id = tracker.record_usage("vm-basic", "user1", datetime.now())

            assert event_id is None  # Not recorded


class TestAnalyticsPerformance:
    """Test analytics performance with large datasets."""

    def test_bulk_insert_performance(self):
        """Test performance of bulk insert operations."""
        import tempfile
        import time

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Bulk insert
            events = [("template-a", f"user{i}", datetime.now()) for i in range(1000)]

            start = time.time()
            tracker.bulk_record_usage(events)
            duration = time.time() - start

            # Should complete in reasonable time (< 1 second)
            assert duration < 1.0
            assert tracker.get_usage_count("template-a") == 1000

    def test_query_performance_with_indexes(self):
        """Test query performance with proper indexing."""
        import tempfile
        import time

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Insert large dataset
            for i in range(10000):
                tracker.record_usage(f"template-{i % 10}", f"user{i}", datetime.now())

            # Query should be fast with indexes
            start = time.time()
            count = tracker.get_usage_count("template-0")
            duration = time.time() - start

            assert duration < 0.1  # Should be very fast with indexes
            assert count == 1000

    def test_aggregation_performance(self):
        """Test performance of aggregation queries."""
        import tempfile
        import time

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Insert data
            for i in range(5000):
                tracker.record_usage(f"template-{i % 100}", f"user{i}", datetime.now())

            # Complex aggregation
            start = time.time()
            most_used = tracker.get_most_used_templates(limit=10)
            duration = time.time() - start

            assert duration < 0.5  # Aggregation should be fast
            assert len(most_used) == 10
