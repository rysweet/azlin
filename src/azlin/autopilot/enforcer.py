"""Autopilot budget enforcement and action execution.

This module enforces budget constraints and executes lifecycle actions:
- Budget monitoring
- Action recommendation
- Safe action execution
- Rate limiting and safety checks

Philosophy:
- Safety first (never touch production)
- User confirmation before first action
- Audit trail for all actions
- Rate limiting to prevent runaway automation

Public API:
    BudgetEnforcer: Main enforcement class
    BudgetStatus: Budget status data
    Action: Planned action data
    ActionResult: Action execution result
"""

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from azlin.autopilot.config import AutoPilotConfig
from azlin.autopilot.learner import UsagePattern
from azlin.cost_tracker import CostTracker
from azlin.modules.notifications import NotificationHandler
from azlin.tag_manager import TagManager
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Budget status information.

    Attributes:
        current_monthly_cost: Current monthly cost
        budget_monthly: Budget limit
        projected_monthly_cost: Projected end-of-month cost
        overage: Amount over budget
        overage_percent: Percentage over budget
        needs_action: Whether action is needed
    """

    current_monthly_cost: Decimal
    budget_monthly: Decimal
    projected_monthly_cost: Decimal
    overage: Decimal
    overage_percent: float
    needs_action: bool


@dataclass
class Action:
    """Planned lifecycle action.

    Attributes:
        action_type: Type of action (stop, downsize, alert)
        vm_name: VM name
        reason: Reason for action
        estimated_savings_monthly: Estimated monthly savings
        requires_confirmation: Whether user confirmation needed
        tags: VM tags
    """

    action_type: str
    vm_name: str
    reason: str
    estimated_savings_monthly: Decimal
    requires_confirmation: bool
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Action execution result.

    Attributes:
        action: The action that was executed
        success: Whether action succeeded
        message: Result message
        timestamp: When action was executed
    """

    action: Action
    success: bool
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


class BudgetEnforcer:
    """Enforce budget constraints and execute actions.

    This class:
    - Monitors costs against budget
    - Recommends actions based on patterns
    - Executes actions safely with rate limiting
    - Logs all actions for audit
    """

    def __init__(self) -> None:
        """Initialize budget enforcer."""
        self.action_history: deque = deque(maxlen=100)  # Last 100 actions
        self.max_actions_per_hour = 5
        self.notification_handler = NotificationHandler()

    def check_budget(self, config: AutoPilotConfig, resource_group: str) -> BudgetStatus:
        """Check current budget status.

        Args:
            config: Autopilot configuration
            resource_group: Resource group to check

        Returns:
            BudgetStatus with current information
        """
        logger.info(f"Checking budget for resource group: {resource_group}")

        # Get current costs from CostTracker
        cost_summary = CostTracker.estimate_costs(resource_group)

        current_cost = cost_summary.get_monthly_estimate()
        budget = Decimal(str(config.budget_monthly))

        # Calculate overage
        overage = max(Decimal("0"), current_cost - budget)
        overage_percent = float((overage / budget) * 100) if budget > 0 else 0.0

        # Determine if action needed (over 90% of budget)
        needs_action = current_cost >= (budget * Decimal("0.9"))

        status = BudgetStatus(
            current_monthly_cost=current_cost,
            budget_monthly=budget,
            projected_monthly_cost=current_cost,  # Simplified projection
            overage=overage,
            overage_percent=overage_percent,
            needs_action=needs_action,
        )

        logger.info(
            f"Budget status: ${current_cost:.2f} / ${budget:.2f} "
            f"({overage_percent:.1f}% {'over' if overage > 0 else 'within'} budget)"
        )

        return status

    def recommend_actions(
        self,
        patterns: list[UsagePattern],
        budget_status: BudgetStatus,
        config: AutoPilotConfig,
    ) -> list[Action]:
        """Recommend actions based on patterns and budget.

        Args:
            patterns: VM usage patterns
            budget_status: Current budget status
            config: Autopilot configuration

        Returns:
            List of recommended actions
        """
        if not budget_status.needs_action:
            logger.info("No action needed - within budget")
            return []

        logger.info(f"Recommending actions for {len(patterns)} VMs")

        actions = []

        for pattern in patterns:
            # Skip if VM has protected tags
            if self._is_protected(pattern.vm_name, config):
                logger.debug(f"Skipping protected VM: {pattern.vm_name}")
                continue

            # Check for idle VMs
            if pattern.average_idle_minutes > config.idle_threshold_minutes:
                # Don't stop during work hours
                if not self._is_work_hours(pattern.typical_work_hours):
                    actions.append(
                        Action(
                            action_type="stop",
                            vm_name=pattern.vm_name,
                            reason=f"VM idle for {pattern.average_idle_minutes:.0f} minutes",
                            estimated_savings_monthly=Decimal("50"),  # Estimate
                            requires_confirmation=True,
                            tags={},
                        )
                    )

            # Check for low CPU utilization
            if pattern.cpu_utilization_avg < config.cpu_threshold_percent:
                actions.append(
                    Action(
                        action_type="downsize",
                        vm_name=pattern.vm_name,
                        reason=f"Low CPU utilization ({pattern.cpu_utilization_avg:.1f}%)",
                        estimated_savings_monthly=Decimal("30"),  # Estimate
                        requires_confirmation=True,
                        tags={},
                    )
                )

        # Sort by estimated savings (highest first)
        actions.sort(key=lambda a: a.estimated_savings_monthly, reverse=True)

        logger.info(f"Recommended {len(actions)} actions")
        return actions

    def execute_action(
        self, action: Action, resource_group: str, dry_run: bool = False
    ) -> ActionResult:
        """Execute a single action.

        Args:
            action: Action to execute
            resource_group: Resource group name
            dry_run: If True, don't actually execute

        Returns:
            ActionResult with execution details
        """
        logger.info(
            f"{'[DRY-RUN] ' if dry_run else ''}Executing action: {action.action_type} "
            f"on {action.vm_name}"
        )

        # Check rate limiting
        if not self._check_rate_limit():
            return ActionResult(
                action=action,
                success=False,
                message="Rate limit exceeded (max 5 actions per hour)",
            )

        # Execute based on action type
        try:
            if dry_run:
                message = f"[DRY-RUN] Would {action.action_type} VM: {action.vm_name}"
                success = True
            elif action.action_type == "stop":
                VMManager.stop_vm(action.vm_name, resource_group)
                message = f"Successfully stopped VM: {action.vm_name}"
                success = True
            elif action.action_type == "downsize":
                # TODO: Implement downsize logic
                message = f"Downsize not yet implemented for: {action.vm_name}"
                success = False
            elif action.action_type == "alert":
                self.notification_handler.send_notification(
                    f"Autopilot Alert: {action.reason} for {action.vm_name}"
                )
                message = f"Sent alert for: {action.vm_name}"
                success = True
            else:
                message = f"Unknown action type: {action.action_type}"
                success = False

            result = ActionResult(
                action=action,
                success=success,
                message=message,
            )

            # Log action
            self._log_action(result)

            # Record action for rate limiting
            if not dry_run:
                self.action_history.append(datetime.now())

            return result

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return ActionResult(
                action=action,
                success=False,
                message=f"Execution failed: {e!s}",
            )

    def execute_actions(
        self,
        actions: list[Action],
        resource_group: str,
        dry_run: bool = False,
        require_confirmation: bool = True,
    ) -> list[ActionResult]:
        """Execute multiple actions.

        Args:
            actions: List of actions to execute
            resource_group: Resource group name
            dry_run: If True, don't actually execute
            require_confirmation: If True, ask for user confirmation

        Returns:
            List of action results
        """
        if not actions:
            logger.info("No actions to execute")
            return []

        # Show summary
        logger.info(f"Planning to execute {len(actions)} actions:")
        for action in actions:
            logger.info(f"  - {action.action_type}: {action.vm_name} ({action.reason})")

        # Request confirmation if needed
        if require_confirmation and not dry_run:
            # In production, would show interactive prompt
            # For now, log warning
            logger.warning("Confirmation required - actions not executed")
            return []

        # Execute actions
        results = []
        for action in actions:
            result = self.execute_action(action, resource_group, dry_run)
            results.append(result)

            # Stop if action failed and not in dry-run
            if not result.success and not dry_run:
                logger.warning(f"Action failed, stopping execution: {result.message}")
                break

        # Summary
        successful = sum(1 for r in results if r.success)
        logger.info(f"Executed {len(results)} actions: {successful} successful")

        return results

    def _is_protected(self, vm_name: str, config: AutoPilotConfig) -> bool:
        """Check if VM is protected from autopilot actions.

        Args:
            vm_name: VM name
            config: Autopilot configuration

        Returns:
            True if VM is protected
        """
        try:
            # Check VM tags
            tags = TagManager.get_vm_tags(vm_name)

            # Check if any protected tags present
            for tag_key, tag_value in tags.items():
                if tag_value.lower() in [t.lower() for t in config.protected_tags]:
                    logger.debug(f"VM {vm_name} has protected tag: {tag_key}={tag_value}")
                    return True

            return False

        except Exception as e:
            # If can't get tags, assume protected for safety
            logger.warning(f"Failed to get tags for {vm_name}: {e}")
            return True

    def _is_work_hours(self, work_hours: Any) -> bool:
        """Check if current time is within work hours.

        Args:
            work_hours: WorkHours configuration

        Returns:
            True if currently work hours
        """
        now = datetime.now()
        current_hour = now.hour
        current_day = now.strftime("%a").lower()

        # Check if current day is a work day
        if current_day not in work_hours.days:
            return False

        # Check if current hour is within work hours
        if work_hours.start_hour <= current_hour < work_hours.end_hour:
            return True

        return False

    def _check_rate_limit(self) -> bool:
        """Check if rate limit allows action.

        Returns:
            True if action allowed
        """
        # Count actions in last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_actions = [ts for ts in self.action_history if ts > one_hour_ago]

        if len(recent_actions) >= self.max_actions_per_hour:
            logger.warning(
                f"Rate limit reached: {len(recent_actions)} actions in last hour "
                f"(max: {self.max_actions_per_hour})"
            )
            return False

        return True

    def _log_action(self, result: ActionResult) -> None:
        """Log action to audit trail.

        Args:
            result: Action result to log
        """
        # Log to file
        log_file = Path.home() / ".azlin" / "autopilot_log.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        log_entry = {
            "timestamp": result.timestamp.isoformat(),
            "action_type": result.action.action_type,
            "vm_name": result.action.vm_name,
            "reason": result.action.reason,
            "success": result.success,
            "message": result.message,
        }

        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except OSError as e:
            logger.warning(f"Failed to write action log: {e}")

    @property
    def action_count_last_hour(self) -> int:
        """Get count of actions in last hour."""
        one_hour_ago = datetime.now() - timedelta(hours=1)
        return sum(1 for ts in self.action_history if ts > one_hour_ago)


__all__ = ["Action", "ActionResult", "BudgetEnforcer", "BudgetStatus"]
