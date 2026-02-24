"""Hook Executor - Execute user-defined lifecycle event scripts.

Philosophy:
- Ruthless simplicity: Direct subprocess execution
- Single responsibility: Hook execution only
- Standard library: subprocess for script execution
- Self-contained: Complete with validation

Public API (Studs):
    HookExecutor - Main hook execution service
    HookResult - Hook execution result
    HookType - Lifecycle event types enum
    HookExecutionError - Hook execution errors
"""

import logging
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from subprocess import TimeoutExpired

logger = logging.getLogger(__name__)


class HookType(StrEnum):
    """Lifecycle event types for hooks."""

    ON_START = "on_start"
    ON_STOP = "on_stop"
    ON_FAILURE = "on_failure"
    ON_RESTART = "on_restart"
    ON_DESTROY = "on_destroy"
    ON_HEALTHY = "on_healthy"


class HookExecutionError(Exception):
    """Raised when hook execution fails."""

    pass


@dataclass
class HookResult:
    """Result of hook execution."""

    success: bool
    hook_type: HookType
    vm_name: str
    exit_code: int
    stdout: str
    stderr: str
    timestamp: datetime
    error_message: str | None = None
    pid: int | None = None


class HookExecutor:
    """Execute user-defined lifecycle hooks.

    Runs scripts with environment variables containing event context.

    Example:
        >>> executor = HookExecutor()
        >>> result = executor.execute_hook(HookType.ON_START, "my-vm", {})
        >>> print(f"Hook success: {result.success}")
    """

    def __init__(self, default_timeout: int = 60):
        """Initialize hook executor.

        Args:
            default_timeout: Default timeout in seconds for hook execution
        """
        self.default_timeout = default_timeout

    def validate_hook_script(self, script_path: str) -> bool:
        """Validate that hook script exists and is executable.

        Args:
            script_path: Path to hook script

        Returns:
            True if script is valid, False otherwise
        """
        try:
            path = Path(script_path)
            if not path.exists():
                logger.warning(f"Hook script not found: {script_path}")
                return False

            if not os.access(path, os.X_OK):
                logger.warning(f"Hook script not executable: {script_path}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating hook script: {e}")
            return False

    def _prepare_environment(
        self, hook_type: HookType, vm_name: str, context: dict
    ) -> dict[str, str]:
        """Prepare environment variables for hook execution.

        Args:
            hook_type: Type of hook event
            vm_name: VM name
            context: Additional context data

        Returns:
            Environment variable dict
        """
        env = os.environ.copy()
        env["AZLIN_VM_NAME"] = vm_name
        env["AZLIN_EVENT_TYPE"] = hook_type.value
        env["AZLIN_TIMESTAMP"] = datetime.now(UTC).isoformat()

        # Add context variables
        for key, value in context.items():
            env_key = f"AZLIN_{key.upper()}"
            env[env_key] = str(value)

        return env

    def execute_hook(
        self,
        hook_type: HookType | str,
        vm_name: str,
        context: dict,
        script_path: str | None = None,
        timeout: int | None = None,
    ) -> HookResult:
        """Execute lifecycle hook script.

        Args:
            hook_type: Type of hook event
            vm_name: VM name
            context: Additional context data to pass as env vars
            script_path: Path to script (if not provided, must be in config)
            timeout: Timeout in seconds (default: self.default_timeout)

        Returns:
            HookResult with execution status

        Raises:
            HookExecutionError: If script is invalid or not provided
        """
        # Convert string to enum if needed
        if isinstance(hook_type, str):
            try:
                hook_type = HookType(hook_type)
            except ValueError:
                hook_type = HookType[hook_type.upper()]

        timeout = timeout or self.default_timeout

        # Get script path from config if not provided
        if script_path is None:
            try:
                from azlin.lifecycle.lifecycle_manager import LifecycleManager

                manager = LifecycleManager()
                status = manager.get_monitoring_status(vm_name)
                script_path = status.config.hooks.get(hook_type.value, "")
                if not script_path:
                    raise HookExecutionError(f"No hook configured for {hook_type.value}")
            except Exception as e:
                raise HookExecutionError(f"Failed to get hook script: {e}") from e

        # Validate script
        if not self.validate_hook_script(script_path):
            raise HookExecutionError(f"Script not found or not executable: {script_path}")

        # Prepare environment
        env = self._prepare_environment(hook_type, vm_name, context)

        try:
            logger.info(f"Executing {hook_type.value} hook for {vm_name}: {script_path}")

            # Execute script
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

            success = result.returncode == 0
            if not success:
                logger.warning(
                    f"Hook {hook_type.value} for {vm_name} exited with code {result.returncode}"
                )

            return HookResult(
                success=success,
                hook_type=hook_type,
                vm_name=vm_name,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                timestamp=datetime.now(UTC),
                error_message=None if success else f"Exit code {result.returncode}",
            )

        except TimeoutExpired as e:
            logger.error(f"Hook execution timeout after {timeout}s: {script_path}")
            return HookResult(
                success=False,
                hook_type=hook_type,
                vm_name=vm_name,
                exit_code=-1,
                stdout="",
                stderr="",
                timestamp=datetime.now(UTC),
                error_message=f"Execution timeout after {timeout} seconds",
            )

        except Exception as e:
            logger.error(f"Hook execution failed: {e}")
            return HookResult(
                success=False,
                hook_type=hook_type,
                vm_name=vm_name,
                exit_code=-1,
                stdout="",
                stderr="",
                timestamp=datetime.now(UTC),
                error_message=str(e),
            )

    def execute_hook_async(
        self,
        hook_type: HookType | str,
        vm_name: str,
        context: dict,
        script_path: str | None = None,
    ) -> HookResult:
        """Execute lifecycle hook asynchronously (non-blocking).

        Args:
            hook_type: Type of hook event
            vm_name: VM name
            context: Additional context data
            script_path: Path to script

        Returns:
            HookResult with PID (execution continues in background)

        Raises:
            HookExecutionError: If script is invalid
        """
        # Convert string to enum if needed
        if isinstance(hook_type, str):
            try:
                hook_type = HookType(hook_type)
            except ValueError:
                hook_type = HookType[hook_type.upper()]

        # Get script path from config if not provided
        if script_path is None:
            try:
                from azlin.lifecycle.lifecycle_manager import LifecycleManager

                manager = LifecycleManager()
                status = manager.get_monitoring_status(vm_name)
                script_path = status.config.hooks.get(hook_type.value, "")
                if not script_path:
                    raise HookExecutionError(f"No hook configured for {hook_type.value}")
            except Exception as e:
                raise HookExecutionError(f"Failed to get hook script: {e}") from e

        # Validate script
        if not self.validate_hook_script(script_path):
            raise HookExecutionError(f"Script not found or not executable: {script_path}")

        # Prepare environment
        env = self._prepare_environment(hook_type, vm_name, context)

        try:
            logger.info(f"Executing {hook_type.value} hook async for {vm_name}: {script_path}")

            # Start process in background
            process = subprocess.Popen(
                [script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            return HookResult(
                success=True,
                hook_type=hook_type,
                vm_name=vm_name,
                exit_code=0,
                stdout="",
                stderr="",
                timestamp=datetime.now(UTC),
                pid=process.pid,
            )

        except Exception as e:
            logger.error(f"Async hook execution failed: {e}")
            return HookResult(
                success=False,
                hook_type=hook_type,
                vm_name=vm_name,
                exit_code=-1,
                stdout="",
                stderr="",
                timestamp=datetime.now(UTC),
                error_message=str(e),
            )


__all__ = [
    "HookExecutionError",
    "HookExecutor",
    "HookResult",
    "HookType",
]
