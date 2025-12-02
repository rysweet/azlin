"""Budget alerts and forecasting.

Philosophy:
- Ruthless simplicity: Threshold-based alerts with configurable levels
- Zero-BS implementation: Real forecasting from historical data
- Proactive alerting: Warning, critical, and exceeded levels

Public API:
    BudgetAlert: Alert notification
    BudgetAlertManager: Alert management system
    BudgetAlertTrigger: Trigger condition evaluator
    BudgetForecast: Cost projection
    BudgetThreshold: Budget limit definition
    BudgetViolation: Budget breach tracking
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Dict, List, Optional


class BudgetThreshold:
    """Budget threshold definition."""

    def __init__(
        self,
        name: str,
        limit: Decimal,
        warning_percentage: Decimal = Decimal("80"),
        critical_percentage: Decimal = Decimal("95"),
    ):
        """Initialize threshold with validation."""
        # Validate percentages
        if warning_percentage < 0 or warning_percentage > 100:
            raise ValueError("Warning percentage must be between 0 and 100")
        if critical_percentage < 0 or critical_percentage > 100:
            raise ValueError("Critical percentage must be between 0 and 100")
        if warning_percentage >= critical_percentage:
            raise ValueError("Warning percentage must be less than critical percentage")

        self.name = name
        self.limit = limit
        self.warning_percentage = warning_percentage
        self.critical_percentage = critical_percentage

    def get_warning_amount(self) -> Decimal:
        """Calculate warning dollar amount."""
        return self.limit * (self.warning_percentage / 100)

    def get_critical_amount(self) -> Decimal:
        """Calculate critical dollar amount."""
        return self.limit * (self.critical_percentage / 100)


@dataclass
class BudgetAlert:
    """Budget alert notification."""

    threshold_name: str
    severity: str  # "warning", "critical", "exceeded"
    current_cost: Decimal
    limit: Decimal
    percentage_used: Decimal
    triggered_at: datetime

    def is_warning(self) -> bool:
        """Check if this is a warning alert."""
        return self.severity == "warning"

    def is_critical(self) -> bool:
        """Check if this is a critical alert."""
        return self.severity == "critical"

    def is_exceeded(self) -> bool:
        """Check if budget is exceeded."""
        return self.severity == "exceeded"

    def format_message(self) -> str:
        """Format alert message for display."""
        return (
            f"{self.severity.upper()}: Budget '{self.threshold_name}' at "
            f"{self.percentage_used:.1f}% (${self.current_cost:.2f} / ${self.limit:.2f})"
        )

    def get_recommendations(self) -> List[str]:
        """Get cost reduction recommendations."""
        recommendations = []

        if self.is_exceeded():
            recommendations.append("URGENT: Stop or delete non-essential resources immediately")
            recommendations.append("Review all running VMs and stop development/test instances")
            recommendations.append("Check for unattached disks and old snapshots")

        elif self.is_critical():
            recommendations.append("Schedule VMs for business hours only")
            recommendations.append("Downsize oversized VMs")
            recommendations.append("Review resource utilization")

        else:  # warning
            recommendations.append("Monitor spending closely")
            recommendations.append("Review upcoming resource needs")

        return recommendations


class BudgetAlertTrigger:
    """Alert trigger condition evaluator."""

    def __init__(self, threshold: BudgetThreshold, cooldown_minutes: int = 0):
        """Initialize trigger with threshold and optional cooldown."""
        self.threshold = threshold
        self.cooldown_minutes = cooldown_minutes
        self._last_triggered: Optional[datetime] = None

    def evaluate(self, current_cost: Decimal) -> Optional[BudgetAlert]:
        """Evaluate current cost against thresholds."""
        # Check cooldown
        if self._last_triggered and self.cooldown_minutes > 0:
            elapsed = datetime.now() - self._last_triggered
            if elapsed.total_seconds() < self.cooldown_minutes * 60:
                return None

        percentage_used = (current_cost / self.threshold.limit) * 100 if self.threshold.limit > 0 else Decimal("0")

        # Determine severity
        severity = None
        if current_cost >= self.threshold.limit:
            severity = "exceeded"
        elif percentage_used >= self.threshold.critical_percentage:
            severity = "critical"
        elif percentage_used >= self.threshold.warning_percentage:
            severity = "warning"

        if severity:
            self._last_triggered = datetime.now()
            return BudgetAlert(
                threshold_name=self.threshold.name,
                severity=severity,
                current_cost=current_cost,
                limit=self.threshold.limit,
                percentage_used=percentage_used,
                triggered_at=datetime.now(),
            )

        return None

    def reset(self) -> None:
        """Reset trigger state."""
        self._last_triggered = None


class BudgetForecast:
    """Budget forecasting from historical data."""

    def __init__(self, daily_costs: List[Decimal]):
        """Initialize forecast with historical daily costs."""
        self.daily_costs = daily_costs
        self.days = len(daily_costs)

    def get_daily_average(self) -> Decimal:
        """Calculate daily average from history."""
        if not self.daily_costs:
            return Decimal("0")

        return sum(self.daily_costs) / len(self.daily_costs)

    def project_30_days(self) -> Decimal:
        """Project cost for next 30 days."""
        return self.get_daily_average() * 30

    def project_60_days(self) -> Decimal:
        """Project cost for next 60 days."""
        return self.get_daily_average() * 60

    def project_90_days(self) -> Decimal:
        """Project cost for next 90 days."""
        return self.get_daily_average() * 90

    def get_trend(self) -> str:
        """Detect cost trend."""
        if len(self.daily_costs) < 2:
            return "stable"

        # Compare first half to second half
        mid = len(self.daily_costs) // 2
        first_half_avg = sum(self.daily_costs[:mid]) / mid if mid > 0 else Decimal("0")
        second_half_avg = sum(self.daily_costs[mid:]) / (len(self.daily_costs) - mid)

        if second_half_avg > first_half_avg * Decimal("1.1"):
            return "increasing"
        elif second_half_avg < first_half_avg * Decimal("0.9"):
            return "decreasing"
        else:
            return "stable"

    def get_trend_percentage(self) -> Decimal:
        """Calculate trend percentage change."""
        if len(self.daily_costs) < 2:
            return Decimal("0")

        mid = len(self.daily_costs) // 2
        first_half_avg = sum(self.daily_costs[:mid]) / mid if mid > 0 else Decimal("0")
        second_half_avg = sum(self.daily_costs[mid:]) / (len(self.daily_costs) - mid)

        if first_half_avg == 0:
            return Decimal("0")

        return ((second_half_avg - first_half_avg) / first_half_avg) * 100

    def predict_breach_date(self, current_cost: Decimal, budget_limit: Decimal) -> datetime:
        """Predict when budget will be breached."""
        daily_avg = self.get_daily_average()
        remaining_budget = budget_limit - current_cost

        if daily_avg == 0:
            return datetime.now() + timedelta(days=365)  # Far future if no spending

        days_until_breach = int(remaining_budget / daily_avg)
        return datetime.now() + timedelta(days=days_until_breach)


class BudgetAlertManager:
    """Budget alert management system."""

    def __init__(
        self,
        thresholds: List[BudgetThreshold],
        notify_email: Optional[str] = None,
        notification_handler: Optional[Callable] = None,
    ):
        """Initialize manager with thresholds and notification options."""
        self.thresholds = thresholds
        self.notify_email = notify_email
        self.notification_handler = notification_handler
        self._alert_history: Dict[str, List[BudgetAlert]] = {}
        self._triggers = {t.name: BudgetAlertTrigger(t) for t in thresholds}

    def check_budgets(self, current_costs: Dict[str, Decimal]) -> List[BudgetAlert]:
        """Check costs against all thresholds."""
        alerts = []

        for threshold_name, current_cost in current_costs.items():
            trigger = self._triggers.get(threshold_name)
            if not trigger:
                continue

            alert = trigger.evaluate(current_cost)
            if alert:
                alerts.append(alert)
                self._record_alert(alert)

                # Send notifications
                if self.notify_email:
                    self._send_email_notification(alert)

                if self.notification_handler:
                    self.notification_handler(alert)

        return alerts

    def _record_alert(self, alert: BudgetAlert) -> None:
        """Record alert in history."""
        if alert.threshold_name not in self._alert_history:
            self._alert_history[alert.threshold_name] = []

        self._alert_history[alert.threshold_name].append(alert)

    def _send_email_notification(self, alert: BudgetAlert) -> None:
        """Send email notification for alert."""
        # Import here to avoid circular dependency
        try:
            from azlin.costs.notifications import send_email

            body = alert.format_message()
            send_email(self.notify_email, f"Budget Alert: {alert.threshold_name}", body)
        except ImportError:
            pass  # Email module not available

    def get_alert_history(self, threshold_name: str) -> List[BudgetAlert]:
        """Get alert history for threshold."""
        return self._alert_history.get(threshold_name, [])


@dataclass
class BudgetViolation:
    """Budget violation tracking."""

    threshold_name: str
    limit: Decimal
    actual_cost: Decimal
    overage: Decimal
    overage_percentage: Decimal
    detected_at: datetime
    resolved_at: Optional[datetime] = None

    def is_resolved(self) -> bool:
        """Check if violation is resolved."""
        return self.resolved_at is not None

    def mark_resolved(self, resolved_at: datetime) -> None:
        """Mark violation as resolved."""
        self.resolved_at = resolved_at

    def get_remediation_plan(self) -> str:
        """Generate plan to return to budget."""
        return (
            f"Budget Remediation Plan for '{self.threshold_name}':\n"
            f"Current overage: ${self.overage:.2f} ({self.overage_percentage:.1f}%)\n"
            f"Required actions:\n"
            f"1. Reduce spending by ${self.overage:.2f} to return to budget\n"
            f"2. Stop or delete non-essential resources\n"
            f"3. Review all running VMs and downsize where possible\n"
            f"4. Check for unattached disks, old snapshots, and unused resources"
        )


def send_email(to: str, subject: str, body: str) -> None:
    """Mock email sending function for testing."""
    pass


__all__ = [
    "BudgetAlert",
    "BudgetAlertManager",
    "BudgetAlertTrigger",
    "BudgetForecast",
    "BudgetThreshold",
    "BudgetViolation",
]
