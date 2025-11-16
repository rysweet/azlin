"""Tests for autopilot pattern learning.

Following TDD approach - these tests define the expected behavior
before implementation.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from azlin.autopilot.learner import IdlePeriod, PatternLearner, UsagePattern, WorkHours


class TestWorkHoursDetection:
    """Test work hours detection from VM usage patterns."""

    def test_detect_work_hours_weekday_pattern(self):
        """Test detecting standard weekday work hours."""
        # Mock VM events: active 9am-5pm Mon-Fri
        events = []
        base_date = datetime(2025, 11, 10)  # Monday

        for day_offset in range(5):  # Mon-Fri
            day = base_date + timedelta(days=day_offset)
            # Start at 9am
            events.append(
                {
                    "timestamp": day.replace(hour=9, minute=0),
                    "event_type": "start",
                    "vm_name": "test-vm",
                }
            )
            # Stop at 5pm
            events.append(
                {
                    "timestamp": day.replace(hour=17, minute=0),
                    "event_type": "stop",
                    "vm_name": "test-vm",
                }
            )

        learner = PatternLearner()
        work_hours = learner.detect_work_hours(events)

        assert work_hours.start_hour == 9
        assert work_hours.end_hour == 17
        assert set(work_hours.days) == {"mon", "tue", "wed", "thu", "fri"}
        assert work_hours.confidence >= 0.8

    def test_detect_work_hours_insufficient_data(self):
        """Test work hours detection with insufficient data."""
        # Only 2 events
        events = [
            {
                "timestamp": datetime(2025, 11, 10, 9, 0),
                "event_type": "start",
                "vm_name": "test-vm",
            },
            {
                "timestamp": datetime(2025, 11, 10, 17, 0),
                "event_type": "stop",
                "vm_name": "test-vm",
            },
        ]

        learner = PatternLearner()
        work_hours = learner.detect_work_hours(events)

        assert work_hours.confidence < 0.5  # low confidence

    def test_detect_work_hours_24_7_usage(self):
        """Test detecting 24/7 usage pattern."""
        # VM always running
        events = [
            {
                "timestamp": datetime(2025, 11, 1),
                "event_type": "start",
                "vm_name": "test-vm",
            }
        ]

        learner = PatternLearner()
        work_hours = learner.detect_work_hours(events)

        assert work_hours.start_hour == 0
        assert work_hours.end_hour == 23
        assert len(work_hours.days) == 7


class TestIdlePeriodCalculation:
    """Test idle period calculation."""

    def test_calculate_idle_periods_single_session(self):
        """Test calculating idle time for single work session."""
        events = [
            {
                "timestamp": datetime(2025, 11, 10, 9, 0),
                "event_type": "start",
                "vm_name": "test-vm",
            },
            {
                "timestamp": datetime(2025, 11, 10, 17, 0),
                "event_type": "stop",
                "vm_name": "test-vm",
            },
        ]

        learner = PatternLearner()
        idle_periods = learner.calculate_idle_periods(events)

        assert len(idle_periods) == 1
        # Idle from 5pm to next event (or now)
        assert idle_periods[0].duration_minutes >= 0

    def test_calculate_idle_periods_multiple_sessions(self):
        """Test calculating idle time across multiple sessions."""
        events = [
            # Day 1
            {
                "timestamp": datetime(2025, 11, 10, 9, 0),
                "event_type": "start",
                "vm_name": "test-vm",
            },
            {
                "timestamp": datetime(2025, 11, 10, 17, 0),
                "event_type": "stop",
                "vm_name": "test-vm",
            },
            # Day 2
            {
                "timestamp": datetime(2025, 11, 11, 9, 0),
                "event_type": "start",
                "vm_name": "test-vm",
            },
            {
                "timestamp": datetime(2025, 11, 11, 17, 0),
                "event_type": "stop",
                "vm_name": "test-vm",
            },
        ]

        learner = PatternLearner()
        idle_periods = learner.calculate_idle_periods(events)

        assert len(idle_periods) >= 1
        # Should have ~16 hour idle period between sessions


class TestUsagePatternAnalysis:
    """Test VM usage pattern analysis."""

    @patch("azlin.autopilot.learner.PatternLearner._query_activity_logs")
    @patch("azlin.autopilot.learner.PatternLearner._query_cpu_metrics")
    def test_analyze_vm_history(self, mock_cpu, mock_activity):
        """Test analyzing VM history to generate usage pattern."""
        # Mock Azure activity logs
        mock_activity.return_value = [
            {
                "timestamp": datetime(2025, 11, 10, 9, 0),
                "event_type": "start",
                "vm_name": "test-vm",
            },
            {
                "timestamp": datetime(2025, 11, 10, 17, 0),
                "event_type": "stop",
                "vm_name": "test-vm",
            },
        ]

        # Mock CPU metrics
        mock_cpu.return_value = 15.5  # Average CPU utilization

        learner = PatternLearner()
        pattern = learner.analyze_vm_history("test-rg", "test-vm")

        assert pattern.vm_name == "test-vm"
        assert pattern.cpu_utilization_avg == 15.5
        assert pattern.typical_work_hours is not None
        assert len(pattern.recommendations) > 0

    @patch("azlin.autopilot.learner.PatternLearner._query_activity_logs")
    @patch("azlin.autopilot.learner.PatternLearner._query_cpu_metrics")
    def test_analyze_vm_history_low_utilization(self, mock_cpu, mock_activity):
        """Test recommendations for underutilized VM."""
        mock_activity.return_value = [
            {
                "timestamp": datetime(2025, 11, 1),
                "event_type": "start",
                "vm_name": "test-vm",
            }
        ]

        # Very low CPU utilization
        mock_cpu.return_value = 5.0

        learner = PatternLearner()
        pattern = learner.analyze_vm_history("test-rg", "test-vm")

        # Should recommend downsizing
        assert any("downsize" in rec.lower() for rec in pattern.recommendations)

    @patch("azlin.autopilot.learner.PatternLearner._query_activity_logs")
    @patch("azlin.autopilot.learner.PatternLearner._query_cpu_metrics")
    def test_analyze_vm_history_idle(self, mock_cpu, mock_activity):
        """Test recommendations for idle VM."""
        # VM stopped 3 days ago
        last_stop = datetime.now() - timedelta(days=3)
        mock_activity.return_value = [
            {"timestamp": last_stop, "event_type": "stop", "vm_name": "test-vm"}
        ]

        mock_cpu.return_value = 0.0

        learner = PatternLearner()
        pattern = learner.analyze_vm_history("test-rg", "test-vm")

        # Should recommend stopping or already stopped
        assert pattern.last_active < datetime.now()


class TestPatternLearnerIntegration:
    """Integration tests for pattern learner."""

    def test_analyze_multiple_vms(self):
        """Test analyzing patterns for multiple VMs."""
        learner = PatternLearner()

        # This would use mocked Azure APIs
        with patch.object(learner, "_query_activity_logs") as mock_logs, patch.object(
            learner, "_query_cpu_metrics"
        ) as mock_cpu:

            mock_logs.return_value = []
            mock_cpu.return_value = 20.0

            patterns = learner.analyze_resource_group("test-rg")

            assert isinstance(patterns, list)
            # In real scenario, would have multiple patterns
