"""Tests for GitHub Runner Provisioner module.

Tests cover:
- Registration token retrieval
- Runner registration on VM
- Runner deregistration
- Runner status checking
- Error handling
"""

from unittest.mock import Mock, patch

import pytest

from azlin.modules.github_runner_provisioner import (
    GitHubRunnerProvisioner,
    RegistrationTokenError,
    RunnerConfig,
    RunnerDeregistrationError,
    RunnerProvisioningError,
    RunnerRegistrationError,
)
from azlin.modules.ssh_connector import SSHConfig


class TestRunnerConfig:
    """Test RunnerConfig data model."""

    def test_runner_config_creation(self):
        """Test creating a RunnerConfig."""
        config = RunnerConfig(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_name="runner-001",
            labels=["linux", "docker"],
        )

        assert config.repo_owner == "testorg"
        assert config.repo_name == "testrepo"
        assert config.runner_name == "runner-001"
        assert config.labels == ["linux", "docker"]
        assert config.runner_group is None

    def test_runner_config_with_group(self):
        """Test RunnerConfig with runner group."""
        config = RunnerConfig(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_name="runner-001",
            labels=["linux"],
            runner_group="ci-group",
        )

        assert config.runner_group == "ci-group"


class TestGetRegistrationToken:
    """Test getting registration token from GitHub API."""

    @patch("requests.post")
    def test_get_registration_token_success(self, mock_post):
        """Test successful token retrieval."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "token": "AABF3JGZDX3P5PMEXLND6TS6FCWO6",
            "expires_at": "2025-11-16T10:00:00Z",
        }
        mock_post.return_value = mock_response

        token = GitHubRunnerProvisioner.get_registration_token(
            repo_owner="testorg",
            repo_name="testrepo",
            github_token="test-token-123",  # noqa: S106
        )

        assert token == "AABF3JGZDX3P5PMEXLND6TS6FCWO6"  # noqa: S105

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert (
            call_args[0][0]
            == "https://api.github.com/repos/testorg/testrepo/actions/runners/registration-token"
        )
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token-123"

    @patch("requests.post")
    def test_get_registration_token_api_error(self, mock_post):
        """Test API error when getting token."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "Forbidden"}
        mock_post.return_value = mock_response

        with pytest.raises(RegistrationTokenError) as exc_info:
            GitHubRunnerProvisioner.get_registration_token(
                repo_owner="testorg",
                repo_name="testrepo",
                github_token="test-invalid-token",  # noqa: S106
            )

        assert "Failed to get registration token" in str(exc_info.value)

    @patch("requests.post")
    def test_get_registration_token_network_error(self, mock_post):
        """Test network error when getting token."""
        mock_post.side_effect = Exception("Connection timeout")

        with pytest.raises(RegistrationTokenError):
            GitHubRunnerProvisioner.get_registration_token(
                repo_owner="testorg",
                repo_name="testrepo",
                github_token="test-token-123",  # noqa: S106
            )

    def test_get_registration_token_empty_owner(self):
        """Test validation for empty repo owner."""
        with pytest.raises(ValueError, match="repo_owner.*cannot be empty"):
            GitHubRunnerProvisioner.get_registration_token(
                repo_owner="",
                repo_name="testrepo",
                github_token="test-token-123",  # noqa: S106
            )

    def test_get_registration_token_empty_token(self):
        """Test validation for empty GitHub token."""
        with pytest.raises(ValueError, match="github_token.*cannot be empty"):
            GitHubRunnerProvisioner.get_registration_token(
                repo_owner="testorg", repo_name="testrepo", github_token=""
            )


class TestRegisterRunner:
    """Test runner registration on VM."""

    @patch("azlin.modules.ssh_connector.SSHConnector.execute_remote_command")
    def test_register_runner_success(self, mock_ssh_exec):
        """Test successful runner registration."""
        mock_ssh_exec.return_value = "Runner successfully registered with ID: 12345"

        ssh_config = SSHConfig(host="10.0.0.5", user="azureuser", private_key_path="/path/to/key")

        config = RunnerConfig(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_name="runner-001",
            labels=["linux", "docker"],
        )

        runner_id = GitHubRunnerProvisioner.register_runner(
            ssh_config=ssh_config,
            config=config,
            registration_token="AABF3JGZDX3P5PMEXLND6TS6FCWO6",  # noqa: S106
        )

        assert runner_id == 12345

        # Verify SSH command was executed
        mock_ssh_exec.assert_called_once()
        call_args = mock_ssh_exec.call_args[0]
        command = call_args[1]

        # Check key components in command
        assert "./config.sh" in command
        assert "--url https://github.com/testorg/testrepo" in command
        assert "--token AABF3JGZDX3P5PMEXLND6TS6FCWO6" in command
        assert "--name runner-001" in command
        assert "--labels linux,docker" in command
        assert "--ephemeral" in command

    @patch("azlin.modules.ssh_connector.SSHConnector.execute_remote_command")
    def test_register_runner_with_runner_group(self, mock_ssh_exec):
        """Test runner registration with runner group."""
        mock_ssh_exec.return_value = "Runner successfully registered with ID: 12345"

        ssh_config = SSHConfig(host="10.0.0.5", user="azureuser", private_key_path="/path/to/key")

        config = RunnerConfig(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_name="runner-001",
            labels=["linux"],
            runner_group="ci-group",
        )

        runner_id = GitHubRunnerProvisioner.register_runner(
            ssh_config=ssh_config,
            config=config,
            registration_token="TOKEN123",  # noqa: S106
        )

        assert runner_id == 12345

        # Verify runner group in command
        call_args = mock_ssh_exec.call_args[0]
        command = call_args[1]
        assert "--runnergroup ci-group" in command

    @patch("azlin.modules.ssh_connector.SSHConnector.execute_remote_command")
    def test_register_runner_ssh_failure(self, mock_ssh_exec):
        """Test SSH failure during registration."""
        mock_ssh_exec.side_effect = Exception("SSH connection failed")

        ssh_config = SSHConfig(host="10.0.0.5", user="azureuser", private_key_path="/path/to/key")

        config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-001", labels=["linux"]
        )

        with pytest.raises(RunnerRegistrationError):
            GitHubRunnerProvisioner.register_runner(
                ssh_config=ssh_config,
                config=config,
                registration_token="TOKEN123",  # noqa: S106
            )

    @patch("azlin.modules.ssh_connector.SSHConnector.execute_remote_command")
    def test_register_runner_config_failure(self, mock_ssh_exec):
        """Test failure during runner configuration."""
        mock_ssh_exec.return_value = "Error: Could not configure runner"

        ssh_config = SSHConfig(host="10.0.0.5", user="azureuser", private_key_path="/path/to/key")

        config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-001", labels=["linux"]
        )

        with pytest.raises(RunnerRegistrationError) as exc_info:
            GitHubRunnerProvisioner.register_runner(
                ssh_config=ssh_config,
                config=config,
                registration_token="TOKEN123",  # noqa: S106
            )

        assert "Failed to register runner" in str(exc_info.value)


class TestDeregisterRunner:
    """Test runner deregistration."""

    @patch("requests.delete")
    def test_deregister_runner_success(self, mock_delete):
        """Test successful runner deregistration."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response

        GitHubRunnerProvisioner.deregister_runner(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_id=12345,
            github_token="test-token-123",  # noqa: S106
        )

        # Verify API call
        mock_delete.assert_called_once()
        call_args = mock_delete.call_args
        assert (
            call_args[0][0] == "https://api.github.com/repos/testorg/testrepo/actions/runners/12345"
        )
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token-123"

    @patch("requests.delete")
    def test_deregister_runner_not_found(self, mock_delete):
        """Test deregistering non-existent runner."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_delete.return_value = mock_response

        with pytest.raises(RunnerDeregistrationError):
            GitHubRunnerProvisioner.deregister_runner(
                repo_owner="testorg",
                repo_name="testrepo",
                runner_id=99999,
                github_token="test-token-123",  # noqa: S106
            )

    @patch("requests.delete")
    def test_deregister_runner_api_error(self, mock_delete):
        """Test API error during deregistration."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"message": "Internal Server Error"}
        mock_delete.return_value = mock_response

        with pytest.raises(RunnerDeregistrationError):
            GitHubRunnerProvisioner.deregister_runner(
                repo_owner="testorg",
                repo_name="testrepo",
                runner_id=12345,
                github_token="test-token-123",  # noqa: S106
            )


class TestGetRunnerInfo:
    """Test getting runner information."""

    @patch("requests.get")
    def test_get_runner_info_online(self, mock_get):
        """Test getting info for online runner."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "name": "runner-001",
            "status": "online",
            "busy": False,
            "labels": [{"name": "self-hosted"}, {"name": "linux"}, {"name": "docker"}],
        }
        mock_get.return_value = mock_response

        runner_info = GitHubRunnerProvisioner.get_runner_info(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_id=12345,
            github_token="test-token-123",  # noqa: S106
        )

        assert runner_info.runner_id == 12345
        assert runner_info.runner_name == "runner-001"
        assert runner_info.status == "online"
        assert runner_info.busy is False
        assert "linux" in runner_info.labels
        assert "docker" in runner_info.labels

    @patch("requests.get")
    def test_get_runner_info_busy(self, mock_get):
        """Test getting info for busy runner."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 12345,
            "name": "runner-001",
            "status": "online",
            "busy": True,
            "labels": [{"name": "self-hosted"}, {"name": "linux"}],
        }
        mock_get.return_value = mock_response

        runner_info = GitHubRunnerProvisioner.get_runner_info(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_id=12345,
            github_token="test-token-123",  # noqa: S106
        )

        assert runner_info.busy is True

    @patch("requests.get")
    def test_get_runner_info_not_found(self, mock_get):
        """Test getting info for non-existent runner."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(RunnerProvisioningError):
            GitHubRunnerProvisioner.get_runner_info(
                repo_owner="testorg",
                repo_name="testrepo",
                runner_id=99999,
                github_token="test-token-123",  # noqa: S106
            )


class TestInputValidation:
    """Test input validation."""

    def test_validate_repo_owner_invalid_chars(self):
        """Test validation rejects invalid characters in repo owner."""
        with pytest.raises(ValueError, match="repo_owner.*invalid"):
            GitHubRunnerProvisioner.get_registration_token(
                repo_owner="test@org",
                repo_name="testrepo",
                github_token="token",  # noqa: S106
            )

    def test_validate_repo_name_invalid_chars(self):
        """Test validation rejects invalid characters in repo name."""
        with pytest.raises(ValueError, match="repo_name.*invalid"):
            GitHubRunnerProvisioner.get_registration_token(
                repo_owner="testorg",
                repo_name="test repo",
                github_token="token",  # noqa: S106
            )

    def test_validate_labels_invalid_chars(self):
        """Test validation rejects invalid characters in labels."""
        ssh_config = SSHConfig(host="10.0.0.5", user="azureuser", private_key_path="/path/to/key")

        config = RunnerConfig(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_name="runner-001",
            labels=["linux", "invalid label!"],  # Space and special char
        )

        with pytest.raises(ValueError, match="label.*invalid"):
            GitHubRunnerProvisioner.register_runner(
                ssh_config=ssh_config,
                config=config,
                registration_token="TOKEN123",  # noqa: S106
            )
