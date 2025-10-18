"""VM updater module.

This module handles updating all development tools installed on azlin VMs.
Updates system packages, programming languages, CLIs, and other dev tools.

Security:
- All commands executed via RemoteExecutor (sanitized)
- No shell=True
- Timeout enforcement
- Proper error handling
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteExecError, RemoteExecutor, RemoteResult

logger = logging.getLogger(__name__)


class VMUpdaterError(Exception):
    """Raised when VM update operation fails."""

    pass


@dataclass
class UpdateResult:
    """Result of updating a single tool."""

    tool_name: str
    success: bool
    message: str
    duration: float


@dataclass
class VMUpdateSummary:
    """Summary of all updates performed on a VM."""

    vm_name: str
    total_updates: int
    successful: list[UpdateResult]
    failed: list[UpdateResult]
    total_duration: float

    @property
    def success_count(self) -> int:
        """Number of successful updates."""
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        """Number of failed updates."""
        return len(self.failed)

    @property
    def all_succeeded(self) -> bool:
        """True if all updates succeeded."""
        return self.failure_count == 0

    @property
    def any_failed(self) -> bool:
        """True if any updates failed."""
        return self.failure_count > 0


class VMUpdater:
    """Update development tools on azlin VMs.

    This class handles updating all tools installed during VM provisioning:
    - System packages (apt)
    - Azure CLI
    - GitHub CLI
    - Node.js & npm
    - NPM global packages (Copilot, Codex, Claude Code)
    - Rust toolchain
    - astral-uv snap package

    Updates run sequentially to avoid conflicts and ensure dependencies
    are updated in the correct order.
    """

    # Timeout for each update operation (in seconds)
    DEFAULT_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        ssh_config: SSHConfig,
        timeout: int = DEFAULT_TIMEOUT,
        progress_callback: Callable[[str], None] | None = None,
    ):
        """Initialize VM updater.

        Args:
            ssh_config: SSH configuration for VM connection
            timeout: Timeout for each update operation in seconds
            progress_callback: Optional callback for progress updates
        """
        self.ssh_config = ssh_config
        self.timeout = timeout
        self.progress_callback = progress_callback

    def _report_progress(self, message: str):
        """Report progress message.

        Args:
            message: Progress message to report
        """
        if self.progress_callback:
            self.progress_callback(message)
        logger.info(message)

    def _execute_remote_command(self, command: str, timeout: int | None = None) -> RemoteResult:
        """Execute command on remote VM.

        Args:
            command: Command to execute
            timeout: Optional timeout override

        Returns:
            RemoteResult object

        Raises:
            RemoteExecError: If execution fails
        """
        timeout = timeout or self.timeout
        return RemoteExecutor.execute_command(self.ssh_config, command, timeout=timeout)

    def _update_system_packages(self) -> UpdateResult:
        """Update system packages via apt.

        Returns:
            UpdateResult for system package updates
        """
        tool_name = "system-packages"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            # Update package lists and upgrade all packages
            command = "sudo apt update && sudo apt upgrade -y"
            result = self._execute_remote_command(command, timeout=600)

            duration = time.time() - start_time

            if result.success:
                message = "System packages updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def _update_azure_cli(self) -> UpdateResult:
        """Update Azure CLI.

        Returns:
            UpdateResult for Azure CLI update
        """
        tool_name = "azure-cli"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            command = "az upgrade --yes"
            result = self._execute_remote_command(command)

            duration = time.time() - start_time

            if result.success:
                message = "Azure CLI updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def _update_github_cli(self) -> UpdateResult:
        """Update GitHub CLI extensions.

        Returns:
            UpdateResult for GitHub CLI update
        """
        tool_name = "github-cli"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            command = "gh extension upgrade --all"
            result = self._execute_remote_command(command)

            duration = time.time() - start_time

            if result.success:
                message = "GitHub CLI extensions updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def _update_npm(self) -> UpdateResult:
        """Update npm package manager.

        Returns:
            UpdateResult for npm update
        """
        tool_name = "npm"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            command = "npm install -g npm@latest"
            result = self._execute_remote_command(command)

            duration = time.time() - start_time

            if result.success:
                message = "npm updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def _update_npm_packages(self) -> UpdateResult:
        """Update npm global packages (Copilot, Codex, Claude Code).

        Returns:
            UpdateResult for npm packages update
        """
        tool_name = "npm-packages"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            command = "npm update -g"
            result = self._execute_remote_command(command)

            duration = time.time() - start_time

            if result.success:
                message = "npm packages updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def _update_rust(self) -> UpdateResult:
        """Update Rust toolchain via rustup.

        Returns:
            UpdateResult for Rust update
        """
        tool_name = "rust"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            # Need to source cargo env first
            command = "source $HOME/.cargo/env && rustup update"
            result = self._execute_remote_command(command)

            duration = time.time() - start_time

            if result.success:
                message = "Rust toolchain updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def _update_astral_uv(self) -> UpdateResult:
        """Update astral-uv snap package.

        Returns:
            UpdateResult for astral-uv update
        """
        tool_name = "astral-uv"
        self._report_progress(f"Updating {tool_name}...")

        start_time = time.time()

        try:
            command = "sudo snap refresh astral-uv"
            result = self._execute_remote_command(command)

            duration = time.time() - start_time

            if result.success:
                message = "astral-uv updated successfully"
                logger.info(f"{tool_name}: {message}")
                return UpdateResult(tool_name, True, message, duration)
            message = f"Failed to update: {result.stderr[:200]}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

        except RemoteExecError as e:
            duration = time.time() - start_time
            message = f"Update failed: {e!s}"
            logger.error(f"{tool_name}: {message}")
            return UpdateResult(tool_name, False, message, duration)

    def update_vm(self) -> VMUpdateSummary:
        """Update all tools on the VM.

        Updates are performed sequentially in dependency order:
        1. System packages (foundation for other tools)
        2. Azure CLI
        3. GitHub CLI
        4. npm (required before npm packages)
        5. npm packages
        6. Rust
        7. astral-uv

        Returns:
            VMUpdateSummary with results of all updates

        Note: Individual update failures don't stop the process.
              All updates are attempted and results are collected.
        """
        self._report_progress(f"Starting VM update on {self.ssh_config.host}...")

        start_time = time.time()
        successful = []
        failed = []

        # Define update sequence (order matters)
        updates = [
            self._update_system_packages,
            self._update_azure_cli,
            self._update_github_cli,
            self._update_npm,
            self._update_npm_packages,
            self._update_rust,
            self._update_astral_uv,
        ]

        # Execute each update
        for update_func in updates:
            try:
                result = update_func()
                if result.success:
                    successful.append(result)
                else:
                    failed.append(result)
            except Exception as e:
                # Catch any unexpected errors
                tool_name = update_func.__name__.replace("_update_", "")
                error_result = UpdateResult(
                    tool_name=tool_name,
                    success=False,
                    message=f"Unexpected error: {e!s}",
                    duration=0.0,
                )
                failed.append(error_result)
                logger.exception(f"Unexpected error updating {tool_name}")

        total_duration = time.time() - start_time

        summary = VMUpdateSummary(
            vm_name=self.ssh_config.host,
            total_updates=len(updates),
            successful=successful,
            failed=failed,
            total_duration=total_duration,
        )

        # Report final status
        if summary.all_succeeded:
            self._report_progress(
                f"✓ All {summary.success_count} updates completed successfully "
                f"in {total_duration:.1f}s"
            )
        elif summary.any_failed:
            self._report_progress(
                f"⚠ Completed with {summary.failure_count} failures: "
                f"{summary.success_count}/{summary.total_updates} succeeded "
                f"in {total_duration:.1f}s"
            )

        return summary


__all__ = ["UpdateResult", "VMUpdateSummary", "VMUpdater", "VMUpdaterError"]
