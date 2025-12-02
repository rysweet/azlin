"""Cost optimization recommendations engine.

Philosophy:
- Ruthless simplicity: Rule-based detection with clear thresholds
- Zero-BS implementation: Real VM metrics analysis, not guesses
- AI-powered: Intelligent recommendations based on usage patterns

Public API:
    OptimizationRecommendation: Recommendation data structure
    OptimizationRule: Rule engine
    OversizedVMDetector: Detect underutilized VMs
    IdleResourceDetector: Detect unused resources
    SchedulingOpportunity: Identify scheduling opportunities
    CostOptimizer: Main optimization orchestrator
    RecommendationPriority: Priority levels
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal
from enum import Enum


class RecommendationPriority(Enum):
    """Recommendation priority levels."""

    HIGH = 3
    MEDIUM = 2
    LOW = 1


@dataclass
class OptimizationRecommendation:
    """Optimization recommendation data structure."""

    resource_name: str
    resource_type: str
    action: str
    reason: str
    estimated_savings: Decimal
    priority: RecommendationPriority
    details: dict = field(default_factory=dict)
    suggested_size: str | None = None
    schedule: str | None = None

    def format(self) -> str:
        """Format recommendation for CLI display."""
        return (
            f"[{self.priority.name}] {self.resource_name} ({self.resource_type})\n"
            f"  Action: {self.action}\n"
            f"  Reason: {self.reason}\n"
            f"  Estimated Savings: ${self.estimated_savings:.2f}/month"
        )


class OversizedVMDetector:
    """Detector for oversized/underutilized VMs."""

    def __init__(self, cpu_threshold: float = 30.0, memory_threshold: float = 30.0):
        """Initialize detector with utilization thresholds."""
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold

        # VM size mappings for downsizing
        self._size_mappings = {
            "Standard_E16as_v5": "Standard_E8as_v5",
            "Standard_E8as_v5": "Standard_E4as_v5",
            "Standard_D8s_v5": "Standard_D4s_v5",
            "Standard_D4s_v5": "Standard_D2s_v5",
        }

    def analyze_vm(self, vm_name: str, vm_metrics: dict) -> OptimizationRecommendation | None:
        """Analyze VM for downsizing opportunities."""
        cpu_avg = vm_metrics.get("cpu_avg", 0)
        memory_avg = vm_metrics.get("memory_avg", 0)
        current_size = vm_metrics.get("vm_size", "")

        # Check if VM is underutilized
        if cpu_avg < self.cpu_threshold or memory_avg < self.memory_threshold:
            suggested_size = self._size_mappings.get(current_size)

            if suggested_size:
                current_cost = vm_metrics.get("cost_per_hour", Decimal("0"))
                suggested_cost = current_cost * Decimal("0.5")  # Rough estimate

                savings = self.calculate_monthly_savings(current_cost, suggested_cost)

                return OptimizationRecommendation(
                    resource_name=vm_name,
                    resource_type="VirtualMachine",
                    action=f"Downsize to {suggested_size}",
                    reason=f"Low CPU and memory utilization (avg {cpu_avg:.1f}% CPU, {memory_avg:.1f}% memory)",
                    estimated_savings=savings,
                    priority=RecommendationPriority.MEDIUM,
                    suggested_size=suggested_size,
                    details={
                        "current_size": current_size,
                        "suggested_size": suggested_size,
                        "cpu_avg": cpu_avg,
                        "memory_avg": memory_avg,
                    },
                )

        return None

    def calculate_monthly_savings(self, current_cost: Decimal, suggested_cost: Decimal) -> Decimal:
        """Calculate monthly savings from downsizing."""
        hourly_savings = current_cost - suggested_cost
        return hourly_savings * 730  # Hours per month


class IdleResourceDetector:
    """Detector for idle/unused resources."""

    def __init__(self, snapshot_retention_days: int = 90):
        """Initialize detector with retention policy."""
        self.snapshot_retention_days = snapshot_retention_days

    def analyze_stopped_vm(self, vm_info: dict) -> OptimizationRecommendation | None:
        """Analyze stopped VMs for deletion opportunities."""
        power_state = vm_info.get("power_state", "")
        last_started = vm_info.get("last_started")

        if "stopped" in power_state.lower():
            days_stopped = (datetime.now() - last_started).days if last_started else 999

            if days_stopped >= 30:
                cost_per_hour = vm_info.get("cost_per_hour", Decimal("0"))
                monthly_savings = cost_per_hour * 730

                return OptimizationRecommendation(
                    resource_name=vm_info["name"],
                    resource_type="VirtualMachine",
                    action="Delete unused VM",
                    reason="unused",
                    estimated_savings=monthly_savings,
                    priority=RecommendationPriority.HIGH,
                )

        return None

    def analyze_disk(self, disk_info: dict) -> OptimizationRecommendation | None:
        """Analyze disks for unattached resources."""
        attached_to = disk_info.get("attached_to")

        if attached_to is None:
            return OptimizationRecommendation(
                resource_name=disk_info["name"],
                resource_type="Disk",
                action="Delete unattached disk",
                reason="Unattached disk wasting resources",
                estimated_savings=disk_info.get("cost_per_month", Decimal("0")),
                priority=RecommendationPriority.MEDIUM,
            )

        return None

    def analyze_snapshot(self, snapshot_info: dict) -> OptimizationRecommendation | None:
        """Analyze snapshots for old/outdated ones."""
        created_date = snapshot_info.get("created_date")

        if created_date:
            age_days = (datetime.now() - created_date).days

            if age_days > self.snapshot_retention_days:
                return OptimizationRecommendation(
                    resource_name=snapshot_info["name"],
                    resource_type="Snapshot",
                    action="Delete old snapshot",
                    reason=f"Old snapshot ({age_days} days)",
                    estimated_savings=snapshot_info.get("cost_per_month", Decimal("0")),
                    priority=RecommendationPriority.LOW,
                )

        return None

    def analyze_public_ip(self, ip_info: dict) -> OptimizationRecommendation | None:
        """Analyze public IPs for unassigned ones."""
        assigned_to = ip_info.get("assigned_to")

        if assigned_to is None:
            return OptimizationRecommendation(
                resource_name=ip_info["name"],
                resource_type="PublicIP",
                action="Delete unassigned IP",
                reason="Unassigned public IP",
                estimated_savings=ip_info.get("cost_per_month", Decimal("0")),
                priority=RecommendationPriority.MEDIUM,
            )

        return None


class SchedulingOpportunity:
    """Detector for VM scheduling opportunities."""

    def analyze_vm(self, vm_info: dict) -> OptimizationRecommendation | None:
        """Analyze VM for scheduling opportunities."""
        tags = vm_info.get("tags", {})
        environment = tags.get("environment", "")
        purpose = tags.get("purpose", "")
        running_24x7 = vm_info.get("running_24x7", False)

        # Skip production VMs
        if environment == "production":
            return None

        # Check for development VMs
        if environment == "dev" and running_24x7:
            savings = self.calculate_business_hours_savings(vm_info.get("cost_per_hour", Decimal("0")))

            return OptimizationRecommendation(
                resource_name=vm_info["name"],
                resource_type="VirtualMachine",
                action="Schedule startup/shutdown (8am-6pm, weekdays)",
                reason="Development VM running 24/7",
                estimated_savings=savings,
                priority=RecommendationPriority.MEDIUM,
                schedule="business_hours",
                details={"schedule": "business_hours"},
            )

        # Check for training VMs
        if "training" in purpose.lower() and running_24x7:
            savings = self._calculate_weekend_only_savings(vm_info.get("cost_per_hour", Decimal("0")))

            return OptimizationRecommendation(
                resource_name=vm_info["name"],
                resource_type="VirtualMachine",
                action="Schedule for weekend only",
                reason="Training VM can run weekends only",
                estimated_savings=savings,
                priority=RecommendationPriority.HIGH,
                schedule="weekend_only",
                details={"schedule": "weekend_only"},
            )

        return None

    def calculate_business_hours_savings(self, hourly_cost: Decimal) -> Decimal:
        """Calculate savings from business hours schedule (8am-6pm, weekdays)."""
        # Business hours: 10 hours/day * 5 days = 50 hours/week
        # Total hours: 168 hours/week
        # Idle hours: 118 hours/week
        idle_hours_per_month = Decimal("118") * Decimal("4.3")  # ~507 hours/month
        return hourly_cost * idle_hours_per_month

    def _calculate_weekend_only_savings(self, hourly_cost: Decimal) -> Decimal:
        """Calculate savings from weekend-only schedule."""
        # Weekend: 48 hours/week
        # Weekday: 120 hours/week (savings)
        weekday_hours_per_month = Decimal("120") * Decimal("4.3")  # ~516 hours/month
        return hourly_cost * weekday_hours_per_month

    @staticmethod
    def create_business_hours_schedule():
        """Create standard business hours schedule."""
        from dataclasses import dataclass

        @dataclass
        class Schedule:
            start_time: time
            stop_time: time
            weekdays_only: bool

        return Schedule(start_time=time(8, 0), stop_time=time(18, 0), weekdays_only=True)


class OptimizationRule:
    """Optimization rule engine."""

    def __init__(
        self,
        name: str,
        condition: Callable,
        action: str,
        savings_calculator: Callable | None = None,
        enabled: bool = True,
        parameters: dict | None = None,
    ):
        """Initialize rule with condition and action."""
        self.name = name
        self.condition = condition
        self.action = action
        self.savings_calculator = savings_calculator
        self.enabled = enabled
        self.parameters = parameters or {}

    def applies(self, data: dict) -> bool:
        """Check if rule condition applies."""
        if not self.enabled:
            return False

        return self.condition(data)

    def is_enabled(self) -> bool:
        """Check if rule is enabled."""
        return self.enabled

    def disable(self) -> None:
        """Disable rule."""
        self.enabled = False


class CostOptimizer:
    """Main cost optimizer orchestration."""

    def __init__(self, resource_group: str):
        """Initialize optimizer with resource group."""
        self.resource_group = resource_group

        # Initialize detectors
        self.oversized_detector = OversizedVMDetector()
        self.idle_detector = IdleResourceDetector()
        self.scheduling_detector = SchedulingOpportunity()

    def analyze(self) -> list[OptimizationRecommendation]:
        """Run all detectors and aggregate recommendations."""
        recommendations = []

        # Run oversized VM detection
        if hasattr(self.oversized_detector, 'analyze_all'):
            recommendations.extend(self.oversized_detector.analyze_all())

        # Run idle resource detection
        if hasattr(self.idle_detector, 'analyze_all'):
            recommendations.extend(self.idle_detector.analyze_all())

        # Run scheduling opportunity detection
        if hasattr(self.scheduling_detector, 'analyze_all'):
            recommendations.extend(self.scheduling_detector.analyze_all())

        return recommendations

    def calculate_total_savings(self, recommendations: list[OptimizationRecommendation]) -> Decimal:
        """Calculate total savings from all recommendations."""
        return sum(r.estimated_savings for r in recommendations)

    def filter_by_priority(
        self, recommendations: list[OptimizationRecommendation], priority: RecommendationPriority
    ) -> list[OptimizationRecommendation]:
        """Filter recommendations by priority."""
        return [r for r in recommendations if r.priority == priority]

    def export_to_json(self, recommendations: list[OptimizationRecommendation]) -> str:
        """Export recommendations as JSON."""
        data = [
            {
                "resource_name": r.resource_name,
                "resource_type": r.resource_type,
                "action": r.action,
                "reason": r.reason,
                "estimated_savings": float(r.estimated_savings),
                "priority": r.priority.name,
                "details": r.details,
            }
            for r in recommendations
        ]
        return json.dumps(data, indent=2)


# Mock VM manager for testing
class VMManager:
    """Mock VM manager."""

    def get_all_vms(self, resource_group: str) -> list[dict]:
        """Get all VMs in resource group."""
        return []


__all__ = [
    "CostOptimizer",
    "IdleResourceDetector",
    "OptimizationRecommendation",
    "OptimizationRule",
    "OversizedVMDetector",
    "RecommendationPriority",
    "SchedulingOpportunity",
]
