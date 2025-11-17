"""GitHub Runner AutoScaler Module

Make intelligent scaling decisions based on queue metrics.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .github_queue_monitor import QueueMetrics

logger = logging.getLogger(__name__)


@dataclass
class ScalingConfig:
    """Configuration for autoscaling behavior."""

    min_runners: int = 0
    max_runners: int = 10
    jobs_per_runner: int = 2  # Target ratio
    scale_up_threshold: int = 2  # Pending jobs to trigger scale up
    scale_down_threshold: int = 0  # Idle runners to trigger scale down
    cooldown_seconds: int = 300  # Wait between scaling actions

    def __post_init__(self):
        """Validate configuration."""
        if self.min_runners < 0:
            raise ValueError("min_runners cannot be negative")

        if self.max_runners < self.min_runners:
            raise ValueError("max_runners must be >= min_runners")

        if self.jobs_per_runner <= 0:
            raise ValueError("jobs_per_runner must be positive")

        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")


@dataclass
class ScalingDecision:
    """Decision about scaling action."""

    action: Literal["scale_up", "scale_down", "maintain"]
    target_runner_count: int
    current_runner_count: int
    reason: str


class GitHubRunnerAutoScaler:
    """Make scaling decisions for runner fleet."""

    @classmethod
    def calculate_scaling_decision(
        cls,
        queue_metrics: QueueMetrics,
        current_runner_count: int,
        config: ScalingConfig,
        last_scaling_action: datetime | None = None,
    ) -> ScalingDecision:
        """Calculate scaling decision based on metrics.

        Args:
            queue_metrics: Current queue metrics
            current_runner_count: Number of active runners
            config: Scaling configuration
            last_scaling_action: Time of last scaling action

        Returns:
            ScalingDecision: Scaling decision with rationale

        Raises:
            ValueError: If current_runner_count is negative
        """
        if current_runner_count < 0:
            raise ValueError("current_runner_count cannot be negative")

        # Check cooldown period
        if last_scaling_action is not None:
            time_since_last_action = datetime.now() - last_scaling_action
            if time_since_last_action.total_seconds() < config.cooldown_seconds:
                remaining = config.cooldown_seconds - time_since_last_action.total_seconds()
                return ScalingDecision(
                    action="maintain",
                    target_runner_count=current_runner_count,
                    current_runner_count=current_runner_count,
                    reason=f"Cooldown period active (remaining: {remaining:.0f}s)",
                )

        # Calculate target runner count based on pending jobs
        target_runners = cls._calculate_target_runners(queue_metrics.pending_jobs, config)

        # Determine action
        action, reason = cls._determine_action(current_runner_count, target_runners, config)

        return ScalingDecision(
            action=action,
            target_runner_count=target_runners,
            current_runner_count=current_runner_count,
            reason=reason,
        )

    @classmethod
    def _calculate_target_runners(cls, pending_jobs: int, config: ScalingConfig) -> int:
        """Calculate target number of runners.

        Args:
            pending_jobs: Number of pending jobs
            config: Scaling configuration

        Returns:
            int: Target number of runners
        """
        # Calculate based on jobs per runner ratio
        if pending_jobs == 0:
            target = config.min_runners
        else:
            target = math.ceil(pending_jobs / config.jobs_per_runner)

        # Apply min/max constraints
        target = max(config.min_runners, min(config.max_runners, target))

        return target

    @classmethod
    def _determine_action(
        cls, current_count: int, target_count: int, config: ScalingConfig
    ) -> tuple[Literal["scale_up", "scale_down", "maintain"], str]:
        """Determine scaling action.

        Args:
            current_count: Current runner count
            target_count: Target runner count
            config: Scaling configuration

        Returns:
            tuple: (action, reason)
        """
        difference = target_count - current_count

        if difference > config.scale_up_threshold:
            return (
                "scale_up",
                f"Need {difference} more runners to handle pending jobs",
            )

        if difference < -config.scale_down_threshold:
            idle_runners = abs(difference)
            return (
                "scale_down",
                f"Can remove {idle_runners} idle runners",
            )

        return (
            "maintain",
            f"Current runner count ({current_count}) is optimal",
        )
