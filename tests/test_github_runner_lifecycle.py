"""Tests for GitHub Runner Lifecycle Manager module.

Tests cover:
- Ephemeral runner provisioning
- Runner destruction
- Runner rotation
- Health checking
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from azlin.modules.github_runner_lifecycle import (
    EphemeralRunner,
    GitHubRunnerLifecycleManager,
    RunnerLifecycleConfig,
    RunnerLifecycleError,
)
from azlin.modules.github_runner_provisioner import RunnerConfig
from azlin.vm_provisioning import VMConfig, VMDetails


class TestEphemeralRunner:
    """Test EphemeralRunner data model."""

    def test_ephemeral_runner_creation(self):
        """Test creating EphemeralRunner."""
        vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        runner = EphemeralRunner(
            vm_details=vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=0,
            status="registered",
        )

        assert runner.vm_details.name == "runner-vm-001"
        assert runner.runner_id == 12345
        assert runner.runner_name == "runner-001"
        assert runner.jobs_completed == 0
        assert runner.status == "registered"


class TestProvisionEphemeralRunner:
    """Test ephemeral runner provisioning."""

    @patch("azlin.vm_provisioning.VMProvisioner.provision_vm")
    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.get_registration_token")
    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.register_runner")
    def test_provision_ephemeral_runner_success(
        self, mock_register, mock_get_token, mock_provision_vm
    ):
        """Test successful ephemeral runner provisioning."""
        # Mock VM provisioning
        mock_vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )
        mock_provision_vm.return_value = mock_vm_details

        # Mock registration token
        mock_get_token.return_value = "TOKEN123"

        # Mock runner registration
        mock_register.return_value = 12345

        # Create config
        runner_config = RunnerConfig(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_name="runner-001",
            labels=["linux", "docker"],
        )

        vm_config = VMConfig(
            name="runner-vm-001", size="Standard_D2s_v3", region="eastus", resource_group="test-rg"
        )

        lifecycle_config = RunnerLifecycleConfig(
            runner_config=runner_config,
            vm_config=vm_config,
            github_token="ghp_test_token_123",  # noqa: S106
            max_job_count=1,
        )

        # Provision ephemeral runner
        runner = GitHubRunnerLifecycleManager.provision_ephemeral_runner(config=lifecycle_config)

        assert runner.vm_details.name == "runner-vm-001"
        assert runner.runner_id == 12345
        assert runner.runner_name == "runner-001"
        assert runner.status == "active"
        assert runner.jobs_completed == 0

        # Verify calls
        mock_provision_vm.assert_called_once()
        mock_get_token.assert_called_once()
        mock_register.assert_called_once()

    @patch("azlin.vm_provisioning.VMProvisioner.provision_vm")
    def test_provision_ephemeral_runner_vm_failure(self, mock_provision_vm):
        """Test VM provisioning failure."""
        mock_provision_vm.side_effect = Exception("VM provisioning failed")

        runner_config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-001", labels=["linux"]
        )

        vm_config = VMConfig(
            name="runner-vm-001", size="Standard_D2s_v3", region="eastus", resource_group="test-rg"
        )

        lifecycle_config = RunnerLifecycleConfig(
            runner_config=runner_config,
            vm_config=vm_config,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        with pytest.raises(RunnerLifecycleError) as exc_info:
            GitHubRunnerLifecycleManager.provision_ephemeral_runner(config=lifecycle_config)

        assert "Failed to provision ephemeral runner" in str(exc_info.value)

    @patch("azlin.vm_provisioning.VMProvisioner.provision_vm")
    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.get_registration_token")
    def test_provision_ephemeral_runner_token_failure(self, mock_get_token, mock_provision_vm):
        """Test registration token failure."""
        mock_vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )
        mock_provision_vm.return_value = mock_vm_details

        mock_get_token.side_effect = Exception("Token generation failed")

        runner_config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-001", labels=["linux"]
        )

        vm_config = VMConfig(
            name="runner-vm-001", size="Standard_D2s_v3", region="eastus", resource_group="test-rg"
        )

        lifecycle_config = RunnerLifecycleConfig(
            runner_config=runner_config,
            vm_config=vm_config,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        with pytest.raises(RunnerLifecycleError):
            GitHubRunnerLifecycleManager.provision_ephemeral_runner(config=lifecycle_config)


class TestDestroyRunner:
    """Test runner destruction."""

    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.deregister_runner")
    @patch("azlin.vm_lifecycle.VMLifecycleManager.delete_vm")
    def test_destroy_runner_success(self, mock_delete_vm, mock_deregister):
        """Test successful runner destruction."""
        vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        runner = EphemeralRunner(
            vm_details=vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=1,
            status="draining",
        )

        runner_config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-001", labels=["linux"]
        )

        vm_config = VMConfig(
            name="runner-vm-001", size="Standard_D2s_v3", region="eastus", resource_group="test-rg"
        )

        lifecycle_config = RunnerLifecycleConfig(
            runner_config=runner_config,
            vm_config=vm_config,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        GitHubRunnerLifecycleManager.destroy_runner(runner=runner, config=lifecycle_config)

        # Verify deregistration and VM deletion
        mock_deregister.assert_called_once_with(
            repo_owner="testorg",
            repo_name="testrepo",
            runner_id=12345,
            github_token="ghp_test_token_123",  # noqa: S106
        )
        mock_delete_vm.assert_called_once()

    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.deregister_runner")
    @patch("azlin.vm_lifecycle.VMLifecycleManager.delete_vm")
    def test_destroy_runner_deregister_failure(self, mock_delete_vm, mock_deregister):
        """Test runner destruction with deregister failure."""
        mock_deregister.side_effect = Exception("Deregistration failed")

        vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        runner = EphemeralRunner(
            vm_details=vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=1,
            status="draining",
        )

        runner_config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-001", labels=["linux"]
        )

        vm_config = VMConfig(
            name="runner-vm-001", size="Standard_D2s_v3", region="eastus", resource_group="test-rg"
        )

        lifecycle_config = RunnerLifecycleConfig(
            runner_config=runner_config,
            vm_config=vm_config,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        # Should still attempt VM deletion even if deregister fails
        GitHubRunnerLifecycleManager.destroy_runner(runner=runner, config=lifecycle_config)

        mock_delete_vm.assert_called_once()


class TestRotateRunner:
    """Test runner rotation."""

    @patch(
        "azlin.modules.github_runner_lifecycle.GitHubRunnerLifecycleManager.provision_ephemeral_runner"
    )
    @patch("azlin.modules.github_runner_lifecycle.GitHubRunnerLifecycleManager.destroy_runner")
    def test_rotate_runner_success(self, mock_destroy, mock_provision):
        """Test successful runner rotation."""
        # Old runner
        old_vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        old_runner = EphemeralRunner(
            vm_details=old_vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=1,
            status="active",
        )

        # New runner
        new_vm_details = VMDetails(
            name="runner-vm-002",
            public_ip="1.2.3.5",
            private_ip="10.0.0.6",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        new_runner = EphemeralRunner(
            vm_details=new_vm_details,
            runner_id=67890,
            runner_name="runner-002",
            created_at=datetime.now(),
            jobs_completed=0,
            status="active",
        )

        mock_provision.return_value = new_runner

        runner_config = RunnerConfig(
            repo_owner="testorg", repo_name="testrepo", runner_name="runner-002", labels=["linux"]
        )

        vm_config = VMConfig(
            name="runner-vm-002", size="Standard_D2s_v3", region="eastus", resource_group="test-rg"
        )

        lifecycle_config = RunnerLifecycleConfig(
            runner_config=runner_config,
            vm_config=vm_config,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        # Rotate runner
        result = GitHubRunnerLifecycleManager.rotate_runner(
            old_runner=old_runner, config=lifecycle_config
        )

        assert result.runner_id == 67890
        assert result.vm_details.name == "runner-vm-002"

        # Verify provision and destroy were called
        mock_provision.assert_called_once()
        mock_destroy.assert_called_once()


class TestCheckRunnerHealth:
    """Test runner health checking."""

    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.get_runner_info")
    def test_check_runner_health_online(self, mock_get_info):
        """Test health check for online runner."""
        from azlin.modules.github_runner_provisioner import RunnerInfo

        mock_info = RunnerInfo(
            runner_id=12345, runner_name="runner-001", status="online", busy=False, labels=["linux"]
        )
        mock_get_info.return_value = mock_info

        vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        runner = EphemeralRunner(
            vm_details=vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=0,
            status="active",
        )

        is_healthy = GitHubRunnerLifecycleManager.check_runner_health(
            runner=runner,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        assert is_healthy is True

    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.get_runner_info")
    def test_check_runner_health_offline(self, mock_get_info):
        """Test health check for offline runner."""
        from azlin.modules.github_runner_provisioner import RunnerInfo

        mock_info = RunnerInfo(
            runner_id=12345,
            runner_name="runner-001",
            status="offline",
            busy=False,
            labels=["linux"],
        )
        mock_get_info.return_value = mock_info

        vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        runner = EphemeralRunner(
            vm_details=vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=0,
            status="active",
        )

        is_healthy = GitHubRunnerLifecycleManager.check_runner_health(
            runner=runner,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        assert is_healthy is False

    @patch("azlin.modules.github_runner_provisioner.GitHubRunnerProvisioner.get_runner_info")
    def test_check_runner_health_api_error(self, mock_get_info):
        """Test health check with API error."""
        mock_get_info.side_effect = Exception("API error")

        vm_details = VMDetails(
            name="runner-vm-001",
            public_ip="1.2.3.4",
            private_ip="10.0.0.5",
            resource_group="test-rg",
            location="eastus",
            size="Standard_D2s_v3",
            state="Running",
        )

        runner = EphemeralRunner(
            vm_details=vm_details,
            runner_id=12345,
            runner_name="runner-001",
            created_at=datetime.now(),
            jobs_completed=0,
            status="active",
        )

        is_healthy = GitHubRunnerLifecycleManager.check_runner_health(
            runner=runner,
            github_token="ghp_test_token_123",  # noqa: S106
        )

        # Should return False on error, not raise exception
        assert is_healthy is False
