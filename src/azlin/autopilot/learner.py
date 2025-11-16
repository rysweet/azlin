"""Autopilot pattern learning from VM usage history.

This module analyzes VM usage patterns to provide recommendations:
- Work hours detection
- Idle period calculation
- CPU utilization analysis
- Cost optimization recommendations

Philosophy:
- Learn from historical data
- Conservative recommendations
- High confidence thresholds
- Clear explanations

Public API:
    PatternLearner: Main pattern analysis class
    UsagePattern: VM usage pattern data
    WorkHours: Work hours configuration
    IdlePeriod: Idle period data
"""

import logging
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkHours:
    """Work hours configuration.

    Attributes:
        start_hour: Start hour (0-23)
        end_hour: End hour (0-23)
        days: Days of week (mon, tue, wed, thu, fri, sat, sun)
        confidence: Confidence score (0.0-1.0)
    """

    start_hour: int
    end_hour: int
    days: list[str]
    confidence: float


@dataclass
class IdlePeriod:
    """Idle period data.

    Attributes:
        start_time: When idle period started
        end_time: When idle period ended (or None if still idle)
        duration_minutes: Duration in minutes
    """

    start_time: datetime
    end_time: datetime | None
    duration_minutes: float


@dataclass
class UsagePattern:
    """VM usage pattern.

    Attributes:
        vm_name: VM name
        typical_work_hours: Detected work hours
        average_idle_minutes: Average idle time
        last_active: Last activity timestamp
        cpu_utilization_avg: Average CPU utilization
        recommendations: List of recommendations
    """

    vm_name: str
    typical_work_hours: WorkHours
    average_idle_minutes: float
    last_active: datetime
    cpu_utilization_avg: float
    recommendations: list[str] = field(default_factory=list)


class PatternLearner:
    """Learn VM usage patterns from Azure history.

    This class analyzes:
    - Azure Activity Logs for VM start/stop events
    - Azure Monitor for CPU metrics
    - Patterns across time to detect work hours
    """

    def __init__(self) -> None:
        """Initialize pattern learner."""
        self.min_events_for_confidence = 10  # Need at least 10 events for good confidence

    def analyze_vm_history(self, resource_group: str, vm_name: str, days: int = 30) -> UsagePattern:
        """Analyze VM usage history.

        Args:
            resource_group: Resource group name
            vm_name: VM name
            days: Number of days to analyze

        Returns:
            UsagePattern with recommendations

        Raises:
            Exception: If Azure queries fail
        """
        logger.info(f"Analyzing usage pattern for VM: {vm_name} (last {days} days)")

        # Query Azure Activity Logs for VM events
        events = self._query_activity_logs(resource_group, vm_name, days)

        # Detect work hours from events
        work_hours = self.detect_work_hours(events)

        # Calculate idle periods
        idle_periods = self.calculate_idle_periods(events)
        avg_idle = mean([p.duration_minutes for p in idle_periods]) if idle_periods else 0

        # Query CPU metrics
        cpu_avg = self._query_cpu_metrics(resource_group, vm_name, days)

        # Determine last active time
        if events:
            last_active = max(e["timestamp"] for e in events)
        else:
            last_active = datetime.now()

        # Generate recommendations
        recommendations = self._generate_recommendations(
            vm_name, work_hours, avg_idle, cpu_avg, events
        )

        pattern = UsagePattern(
            vm_name=vm_name,
            typical_work_hours=work_hours,
            average_idle_minutes=avg_idle,
            last_active=last_active,
            cpu_utilization_avg=cpu_avg,
            recommendations=recommendations,
        )

        logger.info(
            f"Pattern analysis complete for {vm_name}: {len(recommendations)} recommendations"
        )
        return pattern

    def analyze_resource_group(self, resource_group: str) -> list[UsagePattern]:
        """Analyze patterns for all VMs in resource group.

        Args:
            resource_group: Resource group name

        Returns:
            List of usage patterns
        """
        # Query for all VMs in resource group
        vms = self._list_vms(resource_group)

        patterns = []
        for vm_name in vms:
            try:
                pattern = self.analyze_vm_history(resource_group, vm_name)
                patterns.append(pattern)
            except Exception as e:
                logger.warning(f"Failed to analyze {vm_name}: {e}")
                continue

        return patterns

    def detect_work_hours(self, events: list[dict[str, Any]]) -> WorkHours:
        """Detect work hours from VM events.

        Args:
            events: List of VM start/stop events

        Returns:
            WorkHours configuration
        """
        if not events:
            # Default to 24/7 with low confidence
            return WorkHours(
                start_hour=0,
                end_hour=23,
                days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                confidence=0.0,
            )

        # Extract hours and days from start events
        start_events = [e for e in events if e["event_type"] == "start"]

        if not start_events:
            return WorkHours(start_hour=0, end_hour=23, days=[], confidence=0.0)

        # Collect hours
        hours = [e["timestamp"].hour for e in start_events]
        days_of_week = [e["timestamp"].strftime("%a").lower() for e in start_events]

        # Find most common start hour (mode)
        if hours:
            hour_counter = Counter(hours)
            start_hour = hour_counter.most_common(1)[0][0]
        else:
            start_hour = 9  # default

        # Assume 8-hour workday
        end_hour = (start_hour + 8) % 24

        # Find most common days
        if days_of_week:
            day_counter = Counter(days_of_week)
            # Get days with at least 20% of max frequency
            max_freq = day_counter.most_common(1)[0][1]
            threshold = max_freq * 0.2
            common_days = [day for day, count in day_counter.items() if count >= threshold]
        else:
            common_days = ["mon", "tue", "wed", "thu", "fri"]

        # Calculate confidence based on data quantity and consistency
        confidence = min(1.0, len(start_events) / self.min_events_for_confidence)

        return WorkHours(
            start_hour=start_hour,
            end_hour=end_hour,
            days=common_days,
            confidence=confidence,
        )

    def calculate_idle_periods(self, events: list[dict[str, Any]]) -> list[IdlePeriod]:
        """Calculate idle periods from VM events.

        Args:
            events: List of VM start/stop events

        Returns:
            List of idle periods
        """
        if not events:
            return []

        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e["timestamp"])

        idle_periods = []
        last_stop = None

        for event in sorted_events:
            if event["event_type"] == "stop":
                last_stop = event["timestamp"]
            elif event["event_type"] == "start" and last_stop:
                # Calculate idle time
                idle_duration = (event["timestamp"] - last_stop).total_seconds() / 60
                idle_periods.append(
                    IdlePeriod(
                        start_time=last_stop,
                        end_time=event["timestamp"],
                        duration_minutes=idle_duration,
                    )
                )
                last_stop = None

        # If VM currently stopped, calculate idle time to now
        if last_stop:
            idle_duration = (datetime.now() - last_stop).total_seconds() / 60
            idle_periods.append(
                IdlePeriod(
                    start_time=last_stop,
                    end_time=None,
                    duration_minutes=idle_duration,
                )
            )

        return idle_periods

    def _query_activity_logs(
        self, resource_group: str, vm_name: str, days: int
    ) -> list[dict[str, Any]]:
        """Query Azure Activity Logs for VM events.

        Args:
            resource_group: Resource group name
            vm_name: VM name
            days: Number of days to query

        Returns:
            List of VM events
        """
        try:
            # Query Azure Activity Logs
            start_time = (datetime.now() - timedelta(days=days)).isoformat()

            cmd = [
                "az",
                "monitor",
                "activity-log",
                "list",
                "--resource-group",
                resource_group,
                "--start-time",
                start_time,
                "--query",
                f"[?contains(resourceId, '{vm_name}')].{{timestamp:eventTimestamp, operation:operationName.localizedValue}}",
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            import json

            events_raw = json.loads(result.stdout)

            # Parse events
            events = []
            for event in events_raw:
                if "Start" in event["operation"]:
                    event_type = "start"
                elif "Deallocate" in event["operation"] or "Stop" in event["operation"]:
                    event_type = "stop"
                else:
                    continue

                events.append(
                    {
                        "timestamp": datetime.fromisoformat(
                            event["timestamp"].replace("Z", "+00:00")
                        ),
                        "event_type": event_type,
                        "vm_name": vm_name,
                    }
                )

            logger.debug(f"Found {len(events)} VM events for {vm_name}")
            return events

        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to query activity logs: {e}")
            return []

    def _query_cpu_metrics(self, resource_group: str, vm_name: str, days: int) -> float:
        """Query Azure Monitor for CPU metrics.

        Args:
            resource_group: Resource group name
            vm_name: VM name
            days: Number of days to query

        Returns:
            Average CPU utilization percentage
        """
        try:
            # Query Azure Monitor
            start_time = (datetime.now() - timedelta(days=days)).isoformat()

            cmd = [
                "az",
                "monitor",
                "metrics",
                "list",
                "--resource-group",
                resource_group,
                "--resource",
                vm_name,
                "--resource-type",
                "Microsoft.Compute/virtualMachines",
                "--metric",
                "Percentage CPU",
                "--start-time",
                start_time,
                "--aggregation",
                "Average",
                "--interval",
                "PT1H",
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            import json

            metrics_data = json.loads(result.stdout)

            # Extract CPU values
            cpu_values = []
            if metrics_data and "value" in metrics_data:
                for metric in metrics_data["value"]:
                    if "timeseries" in metric:
                        for ts in metric["timeseries"]:
                            if "data" in ts:
                                cpu_values.extend(
                                    [
                                        d["average"]
                                        for d in ts["data"]
                                        if d.get("average") is not None
                                    ]
                                )

            if cpu_values:
                avg_cpu = mean(cpu_values)
                logger.debug(f"Average CPU for {vm_name}: {avg_cpu:.2f}%")
                return avg_cpu

            logger.debug(f"No CPU metrics found for {vm_name}")
            return 0.0

        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to query CPU metrics: {e}")
            return 0.0

    def _list_vms(self, resource_group: str) -> list[str]:
        """List VMs in resource group.

        Args:
            resource_group: Resource group name

        Returns:
            List of VM names
        """
        try:
            cmd = [
                "az",
                "vm",
                "list",
                "--resource-group",
                resource_group,
                "--query",
                "[].name",
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            import json

            vms = json.loads(result.stdout)
            return vms

        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            logger.error(f"Failed to list VMs: {e}")
            return []

    def _generate_recommendations(
        self,
        vm_name: str,
        work_hours: WorkHours,
        avg_idle_minutes: float,
        cpu_avg: float,
        events: list[dict[str, Any]],
    ) -> list[str]:
        """Generate cost optimization recommendations.

        Args:
            vm_name: VM name
            work_hours: Detected work hours
            avg_idle_minutes: Average idle time
            cpu_avg: Average CPU utilization
            events: VM events

        Returns:
            List of recommendation strings
        """
        recommendations = []

        # Check for long idle periods
        if avg_idle_minutes > 180:  # 3 hours
            recommendations.append(
                f"VM is idle for average of {avg_idle_minutes:.0f} minutes. "
                "Consider stopping during idle periods."
            )

        # Check for low CPU utilization
        if cpu_avg > 0 and cpu_avg < 15:
            recommendations.append(
                f"CPU utilization is low ({cpu_avg:.1f}%). Consider downsizing VM."
            )

        # Check if VM hasn't been used recently
        if events:
            last_event = max(e["timestamp"] for e in events)
            days_since_last_event = (datetime.now() - last_event).days
            if days_since_last_event > 7:
                recommendations.append(
                    f"VM has not been used in {days_since_last_event} days. "
                    "Consider deallocating or deleting."
                )

        # Check work hours confidence
        if work_hours.confidence < 0.5:
            recommendations.append(
                "Insufficient data to determine work hours. Consider manual configuration."
            )

        return recommendations


__all__ = ["IdlePeriod", "PatternLearner", "UsagePattern", "WorkHours"]
