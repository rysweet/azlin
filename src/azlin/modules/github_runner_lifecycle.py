"""GitHub Runner Lifecycle Manager Module

Orchestrate complete ephemeral runner lifecycle.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ..vm_lifecycle import VMLifecycleManager
from ..vm_provisioning import VMConfig, VMDetails, VMProvisioner
from .github_runner_provisioner import (
    GitHubRunnerProvisioner,
    RunnerConfig,
)
from .ssh_connector import SSHConfig

logger = logging.getLogger(__name__)


@dataclass
class RunnerLifecycleConfig:
    """Configuration for runner lifecycle management."""

    runner_config: RunnerConfig
    vm_config: VMConfig
    github_token: str
    max_job_count: int = 1  # Ephemeral: 1 job per runner
    rotation_interval_hours: int = 24


@dataclass
class EphemeralRunner:
    """Details of an ephemeral runner."""

    vm_details: VMDetails
    runner_id: int
    runner_name: str
    created_at: datetime
    jobs_completed: int
    status: Literal["provisioning", "registered", "active", "draining", "destroyed"]


class RunnerLifecycleError(Exception):
    """Failed to manage runner lifecycle."""

    pass


class GitHubRunnerLifecycleManager:
    """Manage complete runner lifecycle."""

    @classmethod
    def provision_ephemeral_runner(cls, config: RunnerLifecycleConfig) -> EphemeralRunner:
        """Provision new ephemeral runner.

        Steps:
        1. Provision VM using VMProvisioner
        2. Get registration token
        3. Register runner on VM
        4. Configure as ephemeral (--ephemeral flag)
        5. Start runner service

        Args:
            config: Lifecycle configuration

        Returns:
            EphemeralRunner: Provisioned runner details

        Raises:
            RunnerLifecycleError: If provisioning fails
        """
        try:
            logger.info(f"Provisioning ephemeral runner: {config.runner_config.runner_name}")

            # Step 1: Provision VM
            logger.info("Step 1: Provisioning VM...")
            provisioner = VMProvisioner()
            vm_details = provisioner.provision_vm(config.vm_config)

            # Step 2: Get registration token
            logger.info("Step 2: Getting registration token...")
            registration_token = GitHubRunnerProvisioner.get_registration_token(
                repo_owner=config.runner_config.repo_owner,
                repo_name=config.runner_config.repo_name,
                github_token=config.github_token,
            )

            # Step 3: Register runner on VM
            logger.info("Step 3: Registering runner on VM...")

            # Build SSH config from VM details
            # Use default SSH key path
            from pathlib import Path

            default_key = Path.home() / ".ssh" / "id_rsa"

            # Determine host (prefer public IP, fallback to private)
            host = vm_details.public_ip if vm_details.public_ip else vm_details.private_ip
            if not host:
                raise RunnerLifecycleError("VM has no accessible IP address")

            ssh_config = SSHConfig(
                host=host,
                user="azureuser",  # Default Azure user
                key_path=default_key,  # Default SSH key
            )

            runner_id = GitHubRunnerProvisioner.register_runner(
                ssh_config=ssh_config,
                config=config.runner_config,
                registration_token=registration_token,
            )

            # Step 4: Runner is now active
            logger.info("Runner provisioned and registered successfully")

            return EphemeralRunner(
                vm_details=vm_details,
                runner_id=runner_id,
                runner_name=config.runner_config.runner_name,
                created_at=datetime.now(),
                jobs_completed=0,
                status="active",
            )

        except Exception as e:
            logger.error(f"Failed to provision ephemeral runner: {e}")
            raise RunnerLifecycleError(f"Failed to provision ephemeral runner: {e}") from e

    @classmethod
    def destroy_runner(cls, runner: EphemeralRunner, config: RunnerLifecycleConfig) -> None:
        """Destroy ephemeral runner.

        Steps:
        1. Stop runner service on VM (if still running)
        2. Deregister from GitHub
        3. Delete VM

        Args:
            runner: Runner to destroy
            config: Lifecycle configuration

        Raises:
            RunnerLifecycleError: If destruction fails (non-critical)
        """
        logger.info(f"Destroying runner: {runner.runner_name} (ID: {runner.runner_id})")

        # Step 1: Deregister from GitHub
        try:
            logger.info("Step 1: Deregistering runner from GitHub...")
            GitHubRunnerProvisioner.deregister_runner(
                repo_owner=config.runner_config.repo_owner,
                repo_name=config.runner_config.repo_name,
                runner_id=runner.runner_id,
                github_token=config.github_token,
            )
        except Exception as e:
            # Log but continue - we still want to delete the VM
            logger.warning(f"Failed to deregister runner (continuing): {e}")

        # Step 2: Delete VM
        try:
            logger.info("Step 2: Deleting VM...")
            VMLifecycleManager.delete_vm(
                vm_name=runner.vm_details.name,
                resource_group=runner.vm_details.resource_group,
            )
            logger.info("Runner destroyed successfully")

        except Exception as e:
            logger.error(f"Failed to delete VM: {e}")
            raise RunnerLifecycleError(f"Failed to delete VM: {e}") from e

    @classmethod
    def rotate_runner(
        cls, old_runner: EphemeralRunner, config: RunnerLifecycleConfig
    ) -> EphemeralRunner:
        """Rotate runner for security.

        Steps:
        1. Provision new runner
        2. Wait for new runner to be ready
        3. Destroy old runner

        Args:
            old_runner: Runner to rotate out
            config: Lifecycle configuration

        Returns:
            EphemeralRunner: New runner

        Raises:
            RunnerLifecycleError: If rotation fails
        """
        logger.info(f"Rotating runner: {old_runner.runner_name}")

        try:
            # Step 1: Provision new runner
            logger.info("Provisioning replacement runner...")
            new_runner = cls.provision_ephemeral_runner(config)

            # Step 2: Destroy old runner
            logger.info("Destroying old runner...")
            cls.destroy_runner(old_runner, config)

            logger.info("Runner rotation completed successfully")
            return new_runner

        except Exception as e:
            logger.error(f"Failed to rotate runner: {e}")
            raise RunnerLifecycleError(f"Failed to rotate runner: {e}") from e

    @classmethod
    def check_runner_health(cls, runner: EphemeralRunner, github_token: str) -> bool:
        """Check if runner is healthy.

        Args:
            runner: Runner to check
            github_token: GitHub personal access token

        Returns:
            bool: True if healthy, False otherwise
        """
        try:
            runner_info = GitHubRunnerProvisioner.get_runner_info(
                repo_owner=runner.runner_name.split("/")[0] if "/" in runner.runner_name else "",
                repo_name=runner.runner_name.split("/")[1] if "/" in runner.runner_name else "",
                runner_id=runner.runner_id,
                github_token=github_token,
            )

            # Runner is healthy if online
            is_healthy = runner_info.status == "online"

            if not is_healthy:
                logger.warning(f"Runner {runner.runner_name} is offline")

            return is_healthy

        except Exception as e:
            logger.error(f"Failed to check runner health: {e}")
            return False
