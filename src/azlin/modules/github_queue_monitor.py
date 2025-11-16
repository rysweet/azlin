"""GitHub Job Queue Monitor Module

Monitor GitHub Actions job queue depth for scaling decisions.

Security Requirements:
- HTTPS only for API calls
- Input validation
- Timeout on API calls
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

import requests

logger = logging.getLogger(__name__)


@dataclass
class QueueMetrics:
    """Metrics about the GitHub Actions job queue."""

    pending_jobs: int
    in_progress_jobs: int
    queued_jobs: int
    total_jobs: int
    timestamp: datetime

    @property
    def needs_scaling(self) -> bool:
        """Quick check if scaling might be needed."""
        return self.pending_jobs > 0 or self.queued_jobs > 0


class QueueMonitorError(Exception):
    """Failed to monitor queue."""

    pass


class GitHubJobQueueMonitor:
    """Monitor GitHub Actions job queue."""

    API_BASE = "https://api.github.com"
    API_TIMEOUT = 30

    @classmethod
    def get_queue_metrics(
        cls,
        repo_owner: str,
        repo_name: str,
        labels: list[str] | None,
        github_token: str,
    ) -> QueueMetrics:
        """Get current queue metrics for repository.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            labels: Optional labels to filter jobs (ALL must match)
            github_token: GitHub personal access token

        Returns:
            QueueMetrics: Current queue metrics

        Raises:
            QueueMonitorError: If metrics retrieval fails
            ValueError: If inputs are invalid
        """
        # Validate inputs
        cls._validate_repo_owner(repo_owner)
        cls._validate_repo_name(repo_name)
        cls._validate_github_token(github_token)

        timestamp = datetime.now()

        # Get queued jobs
        queued_runs = cls._get_workflow_runs(repo_owner, repo_name, "queued", github_token)

        # Get in_progress jobs
        in_progress_runs = cls._get_workflow_runs(
            repo_owner, repo_name, "in_progress", github_token
        )

        # Filter by labels if specified
        if labels:
            queued_runs = cls._filter_runs_by_labels(queued_runs, labels)
            in_progress_runs = cls._filter_runs_by_labels(in_progress_runs, labels)

        queued_count = len(queued_runs)
        in_progress_count = len(in_progress_runs)
        total_count = queued_count + in_progress_count

        return QueueMetrics(
            pending_jobs=queued_count,  # queued = pending
            in_progress_jobs=in_progress_count,
            queued_jobs=queued_count,
            total_jobs=total_count,
            timestamp=timestamp,
        )

    @classmethod
    def get_pending_job_count(
        cls,
        repo_owner: str,
        repo_name: str,
        labels: list[str] | None,
        github_token: str,
    ) -> int:
        """Get count of pending jobs (convenience method).

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            labels: Optional labels to filter jobs
            github_token: GitHub personal access token

        Returns:
            int: Number of pending jobs
        """
        metrics = cls.get_queue_metrics(repo_owner, repo_name, labels, github_token)
        return metrics.pending_jobs

    @classmethod
    def _get_workflow_runs(
        cls, repo_owner: str, repo_name: str, status: str, github_token: str
    ) -> list[dict]:
        """Get workflow runs with specified status.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            status: Status to filter ("queued", "in_progress", etc.)
            github_token: GitHub personal access token

        Returns:
            list[dict]: List of workflow run objects

        Raises:
            QueueMonitorError: If API call fails
        """
        url = f"{cls.API_BASE}/repos/{repo_owner}/{repo_name}/actions/runs"

        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        params = {"status": status, "per_page": 100}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=cls.API_TIMEOUT)

            if response.status_code == 200:
                data = response.json()
                return data.get("workflow_runs", [])
            error_msg = response.json().get("message", "Unknown error")
            raise QueueMonitorError(
                f"Failed to get queue metrics: {response.status_code} - {error_msg}"
            )

        except requests.RequestException as e:
            raise QueueMonitorError(f"Failed to get queue metrics: {e}") from e

    @classmethod
    def _filter_runs_by_labels(cls, runs: list[dict], required_labels: list[str]) -> list[dict]:
        """Filter workflow runs by required labels.

        A run matches if it has ALL required labels.

        Args:
            runs: List of workflow run objects
            required_labels: Labels that must all be present

        Returns:
            list[dict]: Filtered runs
        """
        filtered = []

        for run in runs:
            run_labels = run.get("labels", [])

            # Convert to set for easier matching
            if isinstance(run_labels, list) and len(run_labels) > 0:
                # Handle both string lists and dict lists
                if isinstance(run_labels[0], dict):
                    run_label_set = {label.get("name", "") for label in run_labels}
                else:
                    run_label_set = set(run_labels)

                required_label_set = set(required_labels)

                # Check if all required labels are present
                if required_label_set.issubset(run_label_set):
                    filtered.append(run)

        return filtered

    @classmethod
    def _validate_repo_owner(cls, repo_owner: str) -> None:
        """Validate repository owner."""
        if not repo_owner:
            raise ValueError("Repository owner cannot be empty")

        if not re.match(r"^[a-zA-Z0-9_-]+$", repo_owner):
            raise ValueError(f"Invalid repository owner: {repo_owner}")

    @classmethod
    def _validate_repo_name(cls, repo_name: str) -> None:
        """Validate repository name."""
        if not repo_name:
            raise ValueError("Repository name cannot be empty")

        if not re.match(r"^[a-zA-Z0-9._-]+$", repo_name):
            raise ValueError(f"Invalid repository name: {repo_name}")

    @classmethod
    def _validate_github_token(cls, github_token: str) -> None:
        """Validate GitHub token."""
        if not github_token:
            raise ValueError("GitHub token cannot be empty")
