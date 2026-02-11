"""Budget monitoring and alerts for Azure spending.

Tracks costs against configured budgets and provides warnings.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from azlin.agentic.types import CostEstimate

logger = logging.getLogger(__name__)


class BudgetPeriod(StrEnum):
    """Budget tracking period."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class AlertLevel(StrEnum):
    """Budget alert severity."""

    INFO = "info"  # <50% of budget
    WARNING = "warning"  # 50-80% of budget
    CRITICAL = "critical"  # 80-100% of budget
    EXCEEDED = "exceeded"  # >100% of budget


@dataclass
class BudgetConfig:
    """Budget configuration.

    Attributes:
        monthly_limit: Monthly spending limit in USD
        daily_limit: Daily spending limit in USD (optional)
        alert_thresholds: Alert at these percentages [50, 80, 100]
        resource_group_limits: Per-resource-group limits
    """

    monthly_limit: float
    daily_limit: float | None = None
    alert_thresholds: list[int] | None = None
    resource_group_limits: dict[str, float] | None = None

    def __post_init__(self):
        """Set defaults."""
        if self.alert_thresholds is None:
            self.alert_thresholds = [50, 80, 100]


@dataclass
class BudgetAlert:
    """Budget alert.

    Attributes:
        level: Alert severity
        message: Alert message
        current_spend: Current spending
        budget_limit: Budget limit
        percentage_used: Percentage of budget used
        recommended_action: Suggested action
    """

    level: AlertLevel
    message: str
    current_spend: float
    budget_limit: float
    percentage_used: float
    recommended_action: str


class BudgetMonitor:
    """Monitors spending against configured budgets.

    Loads budget configuration from ~/.azlin/config.toml and tracks
    spending to provide alerts before exceeding limits.

    Example:
        >>> monitor = BudgetMonitor()
        >>> estimate = CostEstimate(monthly_cost=150.0, ...)
        >>> alert = monitor.check_budget(estimate, period=BudgetPeriod.MONTHLY)
        >>> if alert and alert.level == AlertLevel.CRITICAL:
        ...     print(f"WARNING: {alert.message}")
    """

    def __init__(self, config_path: Path | None = None):
        """Initialize budget monitor.

        Args:
            config_path: Path to config file (default: ~/.azlin/config.toml)
        """
        if config_path is None:
            config_path = Path.home() / ".azlin" / "config.toml"

        self.config_path = config_path
        self.budget_config = self._load_budget_config()
        self.spending_history_path = Path.home() / ".azlin" / "spending_history.json"

    def _load_budget_config(self) -> BudgetConfig | None:
        """Load budget configuration from config file.

        Returns:
            BudgetConfig if configured, None otherwise
        """
        # For MVP, we'll use a simplified JSON-based config
        # In production, this would read from the TOML config
        budget_file = Path.home() / ".azlin" / "budget.json"

        if not budget_file.exists():
            logger.debug("No budget configuration found at %s", budget_file)
            return None

        try:
            with budget_file.open() as f:
                data = json.load(f)

            return BudgetConfig(
                monthly_limit=data.get("monthly_limit", 1000.0),
                daily_limit=data.get("daily_limit"),
                alert_thresholds=data.get("alert_thresholds", [50, 80, 100]),
                resource_group_limits=data.get("resource_group_limits"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.exception("Failed to load budget config: %s", e)
            return None

    def check_budget(
        self,
        estimate: CostEstimate,
        period: BudgetPeriod = BudgetPeriod.MONTHLY,
        resource_group: str | None = None,
    ) -> BudgetAlert | None:
        """Check if estimated cost is within budget.

        Args:
            estimate: Cost estimate for the operation
            period: Budget period to check against
            resource_group: Resource group name (for RG-specific limits)

        Returns:
            BudgetAlert if there's a concern, None if within budget

        Example:
            >>> alert = monitor.check_budget(estimate, BudgetPeriod.MONTHLY)
            >>> if alert:
            ...     if alert.level == AlertLevel.EXCEEDED:
            ...         raise Exception(f"Budget exceeded: {alert.message}")
        """
        # If no budget configured, return None (no alerts)
        if not self.budget_config:
            return None

        # Get applicable budget limit
        if resource_group and self.budget_config.resource_group_limits:
            budget_limit = self.budget_config.resource_group_limits.get(
                resource_group,
                self.budget_config.monthly_limit,
            )
        elif period == BudgetPeriod.MONTHLY:
            budget_limit = self.budget_config.monthly_limit
        elif period == BudgetPeriod.DAILY and self.budget_config.daily_limit:
            budget_limit = self.budget_config.daily_limit
        else:
            # No applicable budget
            return None

        # Get current spending for this period
        current_spend = self._get_current_spending(period, resource_group)

        # Calculate projected spending after this operation
        if period == BudgetPeriod.MONTHLY:
            projected_spend = current_spend + float(estimate.total_monthly)
        elif period == BudgetPeriod.DAILY:
            projected_spend = current_spend + (float(estimate.total_hourly) * 24)
        else:
            # Weekly
            projected_spend = current_spend + (float(estimate.total_hourly) * 24 * 7)

        # Calculate percentage of budget
        percentage_used = (projected_spend / budget_limit) * 100

        # Determine alert level
        alert_level = self._get_alert_level(percentage_used)

        # Only alert if above INFO threshold
        if alert_level == AlertLevel.INFO:
            return None

        # Generate alert
        return self._create_alert(
            level=alert_level,
            projected_spend=projected_spend,
            budget_limit=budget_limit,
            percentage_used=percentage_used,
            period=period,
            resource_group=resource_group,
        )

    def _get_current_spending(
        self,
        period: BudgetPeriod,
        resource_group: str | None = None,
    ) -> float:
        """Get current spending for the period.

        Args:
            period: Budget period
            resource_group: Resource group filter

        Returns:
            Current spending in USD
        """
        # Load spending history
        if not self.spending_history_path.exists():
            return 0.0

        try:
            with self.spending_history_path.open() as f:
                json.load(f)

            # Filter by period and resource group
            # This is a simplified implementation
            # In production, would query Azure Cost Management API

            # For MVP, just return 0 (no historical tracking yet)
            return 0.0

        except (json.JSONDecodeError, KeyError) as e:
            logger.exception("Failed to load spending history: %s", e)
            return 0.0

    def _get_alert_level(self, percentage: float) -> AlertLevel:
        """Determine alert level from budget percentage.

        Args:
            percentage: Percentage of budget used

        Returns:
            AlertLevel
        """
        if percentage > 100:
            return AlertLevel.EXCEEDED
        if percentage >= 80:
            return AlertLevel.CRITICAL
        if percentage >= 50:
            return AlertLevel.WARNING
        return AlertLevel.INFO

    def _create_alert(
        self,
        level: AlertLevel,
        projected_spend: float,
        budget_limit: float,
        percentage_used: float,
        period: BudgetPeriod,
        resource_group: str | None,
    ) -> BudgetAlert:
        """Create a budget alert.

        Args:
            level: Alert severity
            projected_spend: Projected spending
            budget_limit: Budget limit
            percentage_used: Percentage of budget
            period: Budget period
            resource_group: Resource group (if applicable)

        Returns:
            BudgetAlert
        """
        # Generate message
        scope = f" for resource group '{resource_group}'" if resource_group else ""
        message = (
            f"Projected {period.value} spending${scope} "
            f"(${projected_spend:.2f}) would use {percentage_used:.1f}% "
            f"of your ${budget_limit:.2f} budget"
        )

        # Recommend action based on level
        if level == AlertLevel.EXCEEDED:
            action = (
                "STOP: Budget would be exceeded. Consider using --dry-run or reducing resources."
            )
        elif level == AlertLevel.CRITICAL:
            action = "CAUTION: Very close to budget limit. Review resource requirements carefully."
        else:  # WARNING
            action = "ADVISORY: Approaching budget limit. Monitor spending closely."

        return BudgetAlert(
            level=level,
            message=message,
            current_spend=projected_spend,  # Simplified for MVP
            budget_limit=budget_limit,
            percentage_used=percentage_used,
            recommended_action=action,
        )

    def record_spending(
        self,
        amount: float,
        resource_group: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record actual spending.

        Args:
            amount: Amount spent (monthly cost)
            resource_group: Resource group
            details: Additional details
        """
        # Load or create history
        if self.spending_history_path.exists():
            with self.spending_history_path.open() as f:
                history = json.load(f)
        else:
            history = {"records": []}

        # Add record
        record = {
            "timestamp": datetime.now().isoformat(),
            "amount": amount,
            "resource_group": resource_group,
            "details": details or {},
        }
        history["records"].append(record)

        # Save
        self.spending_history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.spending_history_path.open("w") as f:
            json.dump(history, f, indent=2)

        logger.info(
            "Recorded spending: $%.2f%s", amount, f" ({resource_group})" if resource_group else ""
        )

    def get_spending_summary(self, period: BudgetPeriod = BudgetPeriod.MONTHLY) -> dict[str, Any]:
        """Get spending summary for period.

        Args:
            period: Budget period

        Returns:
            Summary dictionary
        """
        if not self.budget_config:
            return {
                "configured": False,
                "message": "No budget configured",
            }

        current_spend = self._get_current_spending(period, None)

        budget_limit = (
            self.budget_config.monthly_limit
            if period == BudgetPeriod.MONTHLY
            else self.budget_config.daily_limit or 0
        )

        percentage = (current_spend / budget_limit * 100) if budget_limit > 0 else 0

        return {
            "configured": True,
            "period": period.value,
            "current_spend": current_spend,
            "budget_limit": budget_limit,
            "percentage_used": percentage,
            "remaining": budget_limit - current_spend,
        }
