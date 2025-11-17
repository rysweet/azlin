"""Tests for GitHub Job Queue Monitor module.

Tests cover:
- Queue metrics retrieval
- Pending job counting
- Label filtering
- Error handling
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from azlin.modules.github_queue_monitor import (
    GitHubJobQueueMonitor,
    QueueMetrics,
    QueueMonitorError,
)


class TestQueueMetrics:
    """Test QueueMetrics data model."""

    def test_queue_metrics_creation(self):
        """Test creating QueueMetrics."""
        timestamp = datetime.now()
        metrics = QueueMetrics(
            pending_jobs=5, in_progress_jobs=3, queued_jobs=2, total_jobs=10, timestamp=timestamp
        )

        assert metrics.pending_jobs == 5
        assert metrics.in_progress_jobs == 3
        assert metrics.queued_jobs == 2
        assert metrics.total_jobs == 10
        assert metrics.timestamp == timestamp

    def test_needs_scaling_true_pending(self):
        """Test needs_scaling returns True when pending jobs exist."""
        metrics = QueueMetrics(
            pending_jobs=5,
            in_progress_jobs=0,
            queued_jobs=0,
            total_jobs=5,
            timestamp=datetime.now(),
        )

        assert metrics.needs_scaling is True

    def test_needs_scaling_true_queued(self):
        """Test needs_scaling returns True when queued jobs exist."""
        metrics = QueueMetrics(
            pending_jobs=0,
            in_progress_jobs=0,
            queued_jobs=3,
            total_jobs=3,
            timestamp=datetime.now(),
        )

        assert metrics.needs_scaling is True

    def test_needs_scaling_false(self):
        """Test needs_scaling returns False when no pending/queued jobs."""
        metrics = QueueMetrics(
            pending_jobs=0,
            in_progress_jobs=2,
            queued_jobs=0,
            total_jobs=2,
            timestamp=datetime.now(),
        )

        assert metrics.needs_scaling is False


class TestGetQueueMetrics:
    """Test getting queue metrics from GitHub API."""

    @patch("requests.get")
    def test_get_queue_metrics_no_filters(self, mock_get):
        """Test getting metrics without label filters."""
        # Mock queued jobs response
        mock_queued_response = Mock()
        mock_queued_response.status_code = 200
        mock_queued_response.json.return_value = {
            "total_count": 5,
            "workflow_runs": [
                {"id": 1, "status": "queued"},
                {"id": 2, "status": "queued"},
                {"id": 3, "status": "queued"},
                {"id": 4, "status": "queued"},
                {"id": 5, "status": "queued"},
            ],
        }

        # Mock in_progress jobs response
        mock_progress_response = Mock()
        mock_progress_response.status_code = 200
        mock_progress_response.json.return_value = {
            "total_count": 3,
            "workflow_runs": [
                {"id": 6, "status": "in_progress"},
                {"id": 7, "status": "in_progress"},
                {"id": 8, "status": "in_progress"},
            ],
        }

        mock_get.side_effect = [mock_queued_response, mock_progress_response]

        metrics = GitHubJobQueueMonitor.get_queue_metrics(
            repo_owner="testorg",
            repo_name="testrepo",
            labels=None,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        assert metrics.queued_jobs == 5
        assert metrics.in_progress_jobs == 3
        assert metrics.pending_jobs == 5  # queued = pending
        assert metrics.total_jobs == 8

        # Verify API calls
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_get_queue_metrics_with_labels(self, mock_get):
        """Test getting metrics with label filtering."""
        # Mock queued jobs response with label metadata
        mock_queued_response = Mock()
        mock_queued_response.status_code = 200
        mock_queued_response.json.return_value = {
            "total_count": 10,
            "workflow_runs": [
                {"id": 1, "status": "queued", "labels": ["self-hosted", "linux", "docker"]},
                {"id": 2, "status": "queued", "labels": ["self-hosted", "linux"]},
                {"id": 3, "status": "queued", "labels": ["self-hosted", "linux", "docker"]},
            ],
        }

        mock_progress_response = Mock()
        mock_progress_response.status_code = 200
        mock_progress_response.json.return_value = {"total_count": 0, "workflow_runs": []}

        mock_get.side_effect = [mock_queued_response, mock_progress_response]

        metrics = GitHubJobQueueMonitor.get_queue_metrics(
            repo_owner="testorg",
            repo_name="testrepo",
            labels=["linux", "docker"],  # Filter for these labels
            github_token="ghp_test_token_123",  # noqa: S106
        )

        # Should only count jobs with ALL specified labels
        assert metrics.queued_jobs == 2  # Jobs 1 and 3 have both labels

    @patch("requests.get")
    def test_get_queue_metrics_api_error(self, mock_get):
        """Test API error when getting metrics."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "Forbidden"}
        mock_get.return_value = mock_response

        with pytest.raises(QueueMonitorError) as exc_info:
            GitHubJobQueueMonitor.get_queue_metrics(
                repo_owner="testorg",
                repo_name="testrepo",
                labels=None,
                github_token="invalid_token",  # noqa: S106
            )

        assert "Failed to get queue metrics" in str(exc_info.value)

    @patch("requests.get")
    def test_get_queue_metrics_empty_queue(self, mock_get):
        """Test getting metrics when queue is empty."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_count": 0, "workflow_runs": []}
        mock_get.return_value = mock_response

        metrics = GitHubJobQueueMonitor.get_queue_metrics(
            repo_owner="testorg",
            repo_name="testrepo",
            labels=None,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        assert metrics.queued_jobs == 0
        assert metrics.in_progress_jobs == 0
        assert metrics.pending_jobs == 0
        assert metrics.total_jobs == 0
        assert metrics.needs_scaling is False


class TestGetPendingJobCount:
    """Test getting pending job count (convenience method)."""

    @patch("azlin.modules.github_queue_monitor.GitHubJobQueueMonitor.get_queue_metrics")
    def test_get_pending_job_count(self, mock_get_metrics):
        """Test getting pending job count."""
        mock_metrics = QueueMetrics(
            pending_jobs=5,
            in_progress_jobs=3,
            queued_jobs=5,
            total_jobs=8,
            timestamp=datetime.now(),
        )
        mock_get_metrics.return_value = mock_metrics

        count = GitHubJobQueueMonitor.get_pending_job_count(
            repo_owner="testorg",
            repo_name="testrepo",
            labels=["linux"],
            github_token="ghp_test_token_123",  # noqa: S106
        )

        assert count == 5


class TestInputValidation:
    """Test input validation."""

    def test_empty_repo_owner(self):
        """Test validation rejects empty repo owner."""
        with pytest.raises(ValueError, match="repo_owner"):
            GitHubJobQueueMonitor.get_queue_metrics(
                repo_owner="",
                repo_name="testrepo",
                labels=None,
                github_token="token",  # noqa: S106
            )

    def test_empty_repo_name(self):
        """Test validation rejects empty repo name."""
        with pytest.raises(ValueError, match="repo_name"):
            GitHubJobQueueMonitor.get_queue_metrics(
                repo_owner="testorg",
                repo_name="",
                labels=None,
                github_token="token",  # noqa: S106
            )

    def test_empty_github_token(self):
        """Test validation rejects empty GitHub token."""
        with pytest.raises(ValueError, match="github_token"):
            GitHubJobQueueMonitor.get_queue_metrics(
                repo_owner="testorg", repo_name="testrepo", labels=None, github_token=""
            )
