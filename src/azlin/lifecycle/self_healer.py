"""Self-Healer - Automatic VM recovery and restart logic.

Philosophy:
- Ruthless simplicity: Policy-based restart decisions
- Single responsibility: Recovery logic only
- Uses Azure CLI directly (proven pattern)
- Self-contained: Complete restart workflow

Public API (Studs):
    SelfHealer - Main self-healing service
    RestartResult - Restart operation result
    SelfHealingError - Self-healing errors
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class SelfHealingError(Exception):
    """Raised when self-healing operations fail."""

    pass


@dataclass
class RestartResult:
    """Result of a VM restart operation."""

    success: bool
    vm_name: str
    timestamp: datetime
    error_message: str | None = None


class SelfHealer:
    """Automatic VM recovery and restart management.

    Implements restart policies and failure threshold logic.

    Example:
        >>> healer = SelfHealer()
        >>> if healer.should_restart("my-vm", failure):
        ...     result = healer.restart_vm("my-vm")
        ...     print(f"Restart: {result.success}")
    """

    def __init__(self, resource_group: str | None = None):
        """Initialize self-healer.

        Args:
            resource_group: Azure resource group. If None, resolved from config.
        """
        self._lifecycle_manager = None
        self._hook_executor = None
        self._resource_group = resource_group

    def _get_resource_group(self) -> str:
        """Get resource group, resolving from config if needed."""
        if self._resource_group:
            return self._resource_group

        from azlin.config_manager import ConfigManager

        rg = ConfigManager.get_resource_group(None, None)
        if not rg:
            raise SelfHealingError("No resource group configured")
        self._resource_group = rg
        return rg

    def _get_lifecycle_manager(self):
        """Lazy-load LifecycleManager."""
        if self._lifecycle_manager is None:
            from azlin.lifecycle.lifecycle_manager import LifecycleManager

            self._lifecycle_manager = LifecycleManager()
        return self._lifecycle_manager

    def _get_hook_executor(self):
        """Lazy-load HookExecutor."""
        if self._hook_executor is None:
            from azlin.lifecycle.hook_executor import HookExecutor

            self._hook_executor = HookExecutor()
        return self._hook_executor

    def should_restart(self, vm_name: str, failure) -> bool:
        """Determine if VM should be restarted based on policy.

        Args:
            vm_name: VM name
            failure: HealthFailure object with failure details

        Returns:
            True if restart should be triggered, False otherwise
        """
        try:
            manager = self._get_lifecycle_manager()
            status = manager.get_monitoring_status(vm_name)
            config = status.config

            restart_policy = config.restart_policy
            failure_threshold = config.ssh_failure_threshold

            if restart_policy == "never":
                return False
            if restart_policy == "always":
                return True
            if restart_policy == "on-failure":
                # Only restart if threshold met or exceeded
                return failure.failure_count >= failure_threshold
            logger.warning(f"Unknown restart policy: {restart_policy}")
            return False

        except Exception as e:
            logger.error(f"Error checking restart policy for {vm_name}: {e}")
            return False

    def restart_vm(self, vm_name: str) -> RestartResult:
        """Restart a VM via Azure CLI.

        Args:
            vm_name: VM name

        Returns:
            RestartResult with success status
        """
        try:
            logger.info(f"Restarting VM: {vm_name}")
            rg = self._get_resource_group()
            cmd = [
                "az", "vm", "restart",
                "--name", vm_name,
                "--resource-group", rg,
                "--no-wait",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, check=False,
            )
            if result.returncode != 0:
                raise SelfHealingError(
                    f"Azure CLI restart failed: {result.stderr.strip()}"
                )

            return RestartResult(
                success=True,
                vm_name=vm_name,
                timestamp=datetime.now(UTC),
            )

        except SelfHealingError:
            raise
        except Exception as e:
            error_msg = f"Failed to restart VM: {e}"
            logger.error(error_msg)
            return RestartResult(
                success=False,
                vm_name=vm_name,
                timestamp=datetime.now(UTC),
                error_message=error_msg,
            )

    def handle_failure(self, vm_name: str, failure) -> None:
        """Handle VM failure event.

        Checks restart policy and executes restart if appropriate.
        Triggers on_restart hook if restart is performed.

        Args:
            vm_name: VM name
            failure: HealthFailure object with failure details
        """
        try:
            # Check if we should restart
            if not self.should_restart(vm_name, failure):
                logger.debug(f"No restart needed for {vm_name} (policy or threshold)")
                return

            # Execute restart
            result = self.restart_vm(vm_name)

            if result.success:
                logger.info(f"Successfully restarted {vm_name}")

                # Trigger on_restart hook
                try:
                    manager = self._get_lifecycle_manager()
                    status = manager.get_monitoring_status(vm_name)
                    if status.config.hooks.get("on_restart"):
                        executor = self._get_hook_executor()
                        context = {
                            "failure_count": failure.failure_count,
                            "reason": failure.reason,
                        }
                        executor.execute_hook("on_restart", vm_name, context)
                except Exception as hook_error:
                    logger.warning(f"Hook execution failed: {hook_error}")
            else:
                logger.error(f"Restart failed for {vm_name}: {result.error_message}")

        except Exception as e:
            logger.error(f"Error handling failure for {vm_name}: {e}")


__all__ = [
    "RestartResult",
    "SelfHealer",
    "SelfHealingError",
]
