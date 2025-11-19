"""GitHub Runner Provisioner Module

Handle GitHub Actions runner registration/deregistration via REST API.

Security Requirements:
- HTTPS only for API calls
- No credential storage
- Input validation
- Timeout on API calls
"""

import logging
import re
import shlex
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import requests

from .ssh_connector import SSHConfig, SSHConnector

logger = logging.getLogger(__name__)


@dataclass
class RunnerConfig:
    """Configuration for a GitHub Actions runner."""

    repo_owner: str
    repo_name: str
    runner_name: str
    labels: list[str]
    runner_group: str | None = None


@dataclass
class RunnerRegistration:
    """Details of a registered runner."""

    runner_id: int
    runner_name: str
    registration_token: str
    token_expires_at: datetime


@dataclass
class RunnerInfo:
    """Runtime information about a runner."""

    runner_id: int
    runner_name: str
    status: Literal["online", "offline"]
    busy: bool
    labels: list[str]


class RunnerProvisioningError(Exception):
    """Base error for runner provisioning."""

    pass


class RegistrationTokenError(RunnerProvisioningError):
    """Failed to get registration token."""

    pass


class RunnerRegistrationError(RunnerProvisioningError):
    """Failed to register runner."""

    pass


class RunnerDeregistrationError(RunnerProvisioningError):
    """Failed to deregister runner."""

    pass


class GitHubRunnerProvisioner:
    """Manage GitHub Actions runner registration via API."""

    API_BASE = "https://api.github.com"
    API_TIMEOUT = 30

    @classmethod
    def get_registration_token(cls, repo_owner: str, repo_name: str, github_token: str) -> str:
        """Get registration token from GitHub API.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            github_token: GitHub personal access token

        Returns:
            str: Registration token (expires in 1 hour)

        Raises:
            RegistrationTokenError: If token retrieval fails
            ValueError: If inputs are invalid
        """
        # Validate inputs
        cls._validate_repo_owner(repo_owner)
        cls._validate_repo_name(repo_name)
        cls._validate_github_token(github_token)

        # Build API URL
        url = f"{cls.API_BASE}/repos/{repo_owner}/{repo_name}/actions/runners/registration-token"

        # Make API request
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            response = requests.post(url, headers=headers, timeout=cls.API_TIMEOUT)

            if response.status_code == 201:
                data = response.json()
                return data["token"]
            error_msg = response.json().get("message", "Unknown error")
            raise RegistrationTokenError(
                f"Failed to get registration token: {response.status_code} - {error_msg}"
            )

        except requests.RequestException as e:
            raise RegistrationTokenError(f"Failed to get registration token: {e}") from e

    @classmethod
    def register_runner(
        cls, ssh_config: SSHConfig, config: RunnerConfig, registration_token: str
    ) -> int:
        """Register runner on VM and return runner ID.

        Args:
            ssh_config: SSH configuration for VM
            config: Runner configuration
            registration_token: Registration token from GitHub

        Returns:
            int: Runner ID

        Raises:
            RunnerRegistrationError: If registration fails
        """
        # Validate labels
        for label in config.labels:
            cls._validate_label(label)

        # Build runner configuration script
        script = cls._build_registration_script(config, registration_token)

        try:
            # Execute registration on VM
            logger.info(f"Registering runner {config.runner_name} on VM...")
            output = SSHConnector.execute_remote_command(ssh_config, script, timeout=300)

            # Extract runner ID from output
            runner_id = cls._extract_runner_id(output)

            if runner_id is None:
                raise RunnerRegistrationError(
                    "Failed to register runner: Could not extract runner ID from output"
                )

            logger.info(f"Runner registered successfully with ID: {runner_id}")
            return runner_id

        except Exception as e:
            raise RunnerRegistrationError(f"Failed to register runner: {e}") from e

    @classmethod
    def deregister_runner(
        cls, repo_owner: str, repo_name: str, runner_id: int, github_token: str
    ) -> None:
        """Remove runner from GitHub.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            runner_id: Runner ID to remove
            github_token: GitHub personal access token

        Raises:
            RunnerDeregistrationError: If deregistration fails
        """
        # Validate inputs
        cls._validate_repo_owner(repo_owner)
        cls._validate_repo_name(repo_name)
        cls._validate_github_token(github_token)

        # Build API URL
        url = f"{cls.API_BASE}/repos/{repo_owner}/{repo_name}/actions/runners/{runner_id}"

        # Make API request
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            response = requests.delete(url, headers=headers, timeout=cls.API_TIMEOUT)

            if response.status_code == 204:
                logger.info(f"Runner {runner_id} deregistered successfully")
                return
            error_msg = response.json().get("message", "Unknown error")
            raise RunnerDeregistrationError(
                f"Failed to deregister runner: {response.status_code} - {error_msg}"
            )

        except requests.RequestException as e:
            raise RunnerDeregistrationError(f"Failed to deregister runner: {e}") from e

    @classmethod
    def get_runner_info(
        cls, repo_owner: str, repo_name: str, runner_id: int, github_token: str
    ) -> RunnerInfo:
        """Get current runner status.

        Args:
            repo_owner: Repository owner
            repo_name: Repository name
            runner_id: Runner ID
            github_token: GitHub personal access token

        Returns:
            RunnerInfo: Runner information

        Raises:
            RunnerProvisioningError: If retrieval fails
        """
        # Validate inputs
        cls._validate_repo_owner(repo_owner)
        cls._validate_repo_name(repo_name)
        cls._validate_github_token(github_token)

        # Build API URL
        url = f"{cls.API_BASE}/repos/{repo_owner}/{repo_name}/actions/runners/{runner_id}"

        # Make API request
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            response = requests.get(url, headers=headers, timeout=cls.API_TIMEOUT)

            if response.status_code == 200:
                data = response.json()

                # Extract labels
                labels = [label["name"] for label in data.get("labels", [])]

                return RunnerInfo(
                    runner_id=data["id"],
                    runner_name=data["name"],
                    status=data["status"],
                    busy=data["busy"],
                    labels=labels,
                )
            raise RunnerProvisioningError(f"Failed to get runner info: {response.status_code}")

        except requests.RequestException as e:
            raise RunnerProvisioningError(f"Failed to get runner info: {e}") from e

    @classmethod
    def _build_registration_script(cls, config: RunnerConfig, registration_token: str) -> str:
        """Build bash script for runner registration.

        Args:
            config: Runner configuration
            registration_token: Registration token from GitHub

        Returns:
            str: Bash script
        """
        # Safe quoting
        repo_url = shlex.quote(f"https://github.com/{config.repo_owner}/{config.repo_name}")
        token = shlex.quote(registration_token)
        name = shlex.quote(config.runner_name)
        labels = shlex.quote(",".join(config.labels))

        script_lines = [
            "set -e",
            "",
            "# Download and install runner if needed",
            "cd ~",
            "if [ ! -d 'actions-runner' ]; then",
            "  mkdir actions-runner && cd actions-runner",
            "  curl -o actions-runner-linux-x64-2.311.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz",
            "  tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz",
            "else",
            "  cd actions-runner",
            "fi",
            "",
            "# Configure runner",
            f"./config.sh --url {repo_url} --token {token} --name {name} --labels {labels} --ephemeral --unattended",
        ]

        # Add runner group if specified
        if config.runner_group:
            group = shlex.quote(config.runner_group)
            script_lines[-1] += f" --runnergroup {group}"

        script_lines.extend(
            [
                "",
                "# Start runner service",
                "./run.sh &",
                "",
                "# Extract runner ID from .runner file",
                "if [ -f '.runner' ]; then",
                "  cat .runner | grep 'runnerId' || echo 'Runner ID not found'",
                "fi",
            ]
        )

        return "\n".join(script_lines)

    @classmethod
    def _extract_runner_id(cls, output: str) -> int | None:
        """Extract runner ID from command output.

        Args:
            output: Command output from registration

        Returns:
            int | None: Runner ID or None if not found
        """
        # Look for "Runner successfully registered with ID: 12345"
        match = re.search(r"with ID:\s*(\d+)", output)
        if match:
            return int(match.group(1))

        # Look for runnerId in JSON-like output
        match = re.search(r'"runnerId["\s:]+(\d+)', output)
        if match:
            return int(match.group(1))

        return None

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

    @classmethod
    def _validate_label(cls, label: str) -> None:
        """Validate runner label."""
        if not re.match(r"^[a-zA-Z0-9._-]+$", label):
            raise ValueError(f"Invalid label: {label}")
