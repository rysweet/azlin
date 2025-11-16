"""Tests for GitHub Runner AutoScaler module.

Tests cover:
- Scaling decision logic
- Min/max constraints
- Cooldown period
- Various scaling scenarios
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from azlin.modules.github_runner_autoscaler import (
    GitHubRunnerAutoScaler,
    ScalingConfig,
    ScalingDecision,
)
from azlin.modules.github_queue_monitor import QueueMetrics


class TestScalingConfig:
    """Test ScalingConfig data model."""

    def test_scaling_config_defaults(self):
        """Test default ScalingConfig values."""
        config = ScalingConfig()

        assert config.min_runners == 0
        assert config.max_runners == 10
        assert config.jobs_per_runner == 2
        assert config.scale_up_threshold == 2
        assert config.scale_down_threshold == 0
        assert config.cooldown_seconds == 300

    def test_scaling_config_custom(self):
        """Test custom ScalingConfig values."""
        config = ScalingConfig(
            min_runners=2,
            max_runners=20,
            jobs_per_runner=3,
            scale_up_threshold=5,
            scale_down_threshold=2,
            cooldown_seconds=600
        )

        assert config.min_runners == 2
        assert config.max_runners == 20
        assert config.jobs_per_runner == 3


class TestScaleUp:
    """Test scale up scenarios."""

    def test_scale_up_from_zero(self):
        """Test scaling up from zero runners."""
        metrics = QueueMetrics(
            pending_jobs=10,
            in_progress_jobs=0,
            queued_jobs=10,
            total_jobs=10,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2,
            scale_up_threshold=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=0,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "scale_up"
        # 10 pending jobs / 2 jobs per runner = 5 runners
        assert decision.target_runner_count == 5
        assert "pending jobs" in decision.reason.lower()

    def test_scale_up_incremental(self):
        """Test incremental scale up."""
        metrics = QueueMetrics(
            pending_jobs=8,
            in_progress_jobs=4,
            queued_jobs=8,
            total_jobs=12,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2,
            scale_up_threshold=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=2,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "scale_up"
        # 8 pending jobs / 2 jobs per runner = 4 runners
        assert decision.target_runner_count == 4

    def test_scale_up_respects_max(self):
        """Test scale up respects max runners."""
        metrics = QueueMetrics(
            pending_jobs=100,
            in_progress_jobs=0,
            queued_jobs=100,
            total_jobs=100,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=0,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "scale_up"
        # Would be 50 runners, but capped at max
        assert decision.target_runner_count == 10

    def test_scale_up_blocked_by_cooldown(self):
        """Test scale up blocked by cooldown period."""
        metrics = QueueMetrics(
            pending_jobs=10,
            in_progress_jobs=0,
            queued_jobs=10,
            total_jobs=10,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2,
            cooldown_seconds=300
        )

        # Last scaling action was 1 minute ago (within cooldown)
        last_action = datetime.now() - timedelta(seconds=60)

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=0,
            config=config,
            last_scaling_action=last_action
        )

        assert decision.action == "maintain"
        assert "cooldown" in decision.reason.lower()

    def test_scale_up_after_cooldown(self):
        """Test scale up allowed after cooldown expires."""
        metrics = QueueMetrics(
            pending_jobs=10,
            in_progress_jobs=0,
            queued_jobs=10,
            total_jobs=10,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2,
            cooldown_seconds=300
        )

        # Last scaling action was 6 minutes ago (past cooldown)
        last_action = datetime.now() - timedelta(seconds=360)

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=0,
            config=config,
            last_scaling_action=last_action
        )

        assert decision.action == "scale_up"


class TestScaleDown:
    """Test scale down scenarios."""

    def test_scale_down_no_jobs(self):
        """Test scaling down when no jobs pending."""
        metrics = QueueMetrics(
            pending_jobs=0,
            in_progress_jobs=0,
            queued_jobs=0,
            total_jobs=0,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2,
            scale_down_threshold=0
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=5,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "scale_down"
        assert decision.target_runner_count == 0

    def test_scale_down_respects_min(self):
        """Test scale down respects min runners."""
        metrics = QueueMetrics(
            pending_jobs=0,
            in_progress_jobs=0,
            queued_jobs=0,
            total_jobs=0,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=2,
            max_runners=10,
            jobs_per_runner=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=5,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "scale_down"
        assert decision.target_runner_count == 2  # Respects min_runners

    def test_scale_down_incremental(self):
        """Test incremental scale down."""
        metrics = QueueMetrics(
            pending_jobs=2,
            in_progress_jobs=0,
            queued_jobs=2,
            total_jobs=2,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=5,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "scale_down"
        # 2 pending jobs / 2 jobs per runner = 1 runner needed
        assert decision.target_runner_count == 1


class TestMaintain:
    """Test maintain (no action) scenarios."""

    def test_maintain_optimal_count(self):
        """Test maintain when runner count is optimal."""
        metrics = QueueMetrics(
            pending_jobs=4,
            in_progress_jobs=0,
            queued_jobs=4,
            total_jobs=4,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2
        )

        # Current count matches target (4 jobs / 2 per runner = 2 runners)
        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=2,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "maintain"
        assert decision.target_runner_count == 2

    def test_maintain_within_threshold(self):
        """Test maintain when within scale up threshold."""
        metrics = QueueMetrics(
            pending_jobs=5,
            in_progress_jobs=0,
            queued_jobs=5,
            total_jobs=5,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2,
            scale_up_threshold=2  # Need 2 extra pending jobs to scale
        )

        # Target would be 3 runners (5/2 = 2.5 → 3)
        # Current is 2, difference is 1 (below threshold of 2)
        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=2,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "maintain"

    def test_maintain_at_min_runners(self):
        """Test maintain when at min runners with no jobs."""
        metrics = QueueMetrics(
            pending_jobs=0,
            in_progress_jobs=0,
            queued_jobs=0,
            total_jobs=0,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=2,
            max_runners=10,
            jobs_per_runner=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=2,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "maintain"
        assert decision.target_runner_count == 2

    def test_maintain_at_max_runners(self):
        """Test maintain when at max runners."""
        metrics = QueueMetrics(
            pending_jobs=100,
            in_progress_jobs=0,
            queued_jobs=100,
            total_jobs=100,
            timestamp=datetime.now()
        )

        config = ScalingConfig(
            min_runners=0,
            max_runners=10,
            jobs_per_runner=2
        )

        decision = GitHubRunnerAutoScaler.calculate_scaling_decision(
            queue_metrics=metrics,
            current_runner_count=10,
            config=config,
            last_scaling_action=None
        )

        assert decision.action == "maintain"
        assert decision.target_runner_count == 10


class TestEdgeCases:
    """Test edge cases."""

    def test_negative_current_runners(self):
        """Test handling of negative current runner count."""
        metrics = QueueMetrics(
            pending_jobs=5,
            in_progress_jobs=0,
            queued_jobs=5,
            total_jobs=5,
            timestamp=datetime.now()
        )

        config = ScalingConfig()

        with pytest.raises(ValueError):
            GitHubRunnerAutoScaler.calculate_scaling_decision(
                queue_metrics=metrics,
                current_runner_count=-1,
                config=config,
                last_scaling_action=None
            )

    def test_invalid_min_max(self):
        """Test handling of invalid min > max."""
        with pytest.raises(ValueError):
            ScalingConfig(min_runners=10, max_runners=5)

    def test_zero_jobs_per_runner(self):
        """Test handling of zero jobs per runner."""
        with pytest.raises(ValueError):
            ScalingConfig(jobs_per_runner=0)

    def test_negative_cooldown(self):
        """Test handling of negative cooldown."""
        with pytest.raises(ValueError):
            ScalingConfig(cooldown_seconds=-1)
