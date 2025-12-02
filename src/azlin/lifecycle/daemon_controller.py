"""Daemon Controller - CLI interface for daemon management.

Philosophy:
- Ruthless simplicity: Direct process management via PID file
- Single responsibility: Daemon control only
- Standard library: os and signal for process control
- Self-contained: Complete daemon lifecycle control

Public API (Studs):
    DaemonController - Daemon management interface
    ControllerError - Daemon control errors
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ControllerError(Exception):
    """Raised when daemon control operations fail."""
    pass


class DaemonController:
    """Control interface for lifecycle daemon.

    Provides start, stop, restart, and status operations.

    Example:
        >>> controller = DaemonController()
        >>> controller.start_daemon()
        >>> status = controller.daemon_status()
        >>> print(f"Running: {status.running}")
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize daemon controller.

        Args:
            config_path: Path to lifecycle config file
        """
        from azlin.lifecycle.lifecycle_manager import LifecycleManager, LIFECYCLE_CONFIG_PATH

        self.config_path = config_path or LIFECYCLE_CONFIG_PATH
        self.lifecycle_manager = LifecycleManager(self.config_path)

        # Get daemon config
        config = self.lifecycle_manager._read_config()
        daemon_config = config.get("daemon", {})
        self.pid_file = Path(daemon_config.get("pid_file", Path.home() / ".azlin" / "lifecycle-daemon.pid"))
        self.log_file = Path(daemon_config.get("log_file", Path.home() / ".azlin" / "lifecycle-daemon.log"))

    def _get_daemon_pid(self) -> Optional[int]:
        """Get daemon PID from PID file.

        Returns:
            PID if daemon is running, None otherwise
        """
        if not self.pid_file.exists():
            return None

        try:
            pid = int(self.pid_file.read_text().strip())

            # Check if process is actually running
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return pid
            except ProcessLookupError:
                # Process doesn't exist, remove stale PID file
                logger.warning(f"Removing stale PID file for PID {pid}")
                self.pid_file.unlink()
                return None

        except (ValueError, Exception) as e:
            logger.error(f"Error reading PID file: {e}")
            return None

    def _is_daemon_running(self) -> bool:
        """Check if daemon is currently running.

        Returns:
            True if daemon is running, False otherwise
        """
        return self._get_daemon_pid() is not None

    def start_daemon(self, foreground: bool = False) -> None:
        """Start the lifecycle daemon.

        Args:
            foreground: Run in foreground (for testing/debugging)

        Raises:
            ControllerError: If daemon is already running or start fails
        """
        # Check if already running
        if self._is_daemon_running():
            pid = self._get_daemon_pid()
            raise ControllerError(f"Daemon already running with PID {pid}")

        logger.info("Starting lifecycle daemon...")

        if foreground:
            # Run in foreground (blocking)
            from azlin.lifecycle.lifecycle_daemon import LifecycleDaemon
            daemon = LifecycleDaemon(self.config_path)
            daemon.start()
        else:
            # Run as background process
            try:
                # Get the Python interpreter path
                python_exe = sys.executable

                # Construct command to run daemon
                # We need to import and run the daemon module
                cmd = [
                    python_exe,
                    "-c",
                    "from azlin.lifecycle.lifecycle_daemon import LifecycleDaemon; "
                    f"daemon = LifecycleDaemon(); daemon.start()",
                ]

                # Start daemon process
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,  # Detach from parent
                )

                # Give it a moment to start
                time.sleep(2)

                # Check if it's running
                if not self._is_daemon_running():
                    raise ControllerError("Daemon failed to start")

                pid = self._get_daemon_pid()
                logger.info(f"Daemon started with PID {pid}")
                logger.info(f"Logs: {self.log_file}")

            except Exception as e:
                raise ControllerError(f"Failed to start daemon: {e}") from e

    def stop_daemon(self, timeout: int = 10) -> None:
        """Stop the lifecycle daemon.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown

        Raises:
            ControllerError: If daemon is not running or stop fails
        """
        pid = self._get_daemon_pid()
        if pid is None:
            raise ControllerError("Daemon is not running")

        logger.info(f"Stopping daemon (PID {pid})...")

        try:
            # Send SIGTERM for graceful shutdown
            os.kill(pid, signal.SIGTERM)

            # Wait for daemon to stop
            start_time = time.time()
            while time.time() - start_time < timeout:
                if not self._is_daemon_running():
                    logger.info("Daemon stopped successfully")
                    return
                time.sleep(0.5)

            # If still running, force kill
            logger.warning(f"Daemon didn't stop gracefully, sending SIGKILL")
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)

            if self._is_daemon_running():
                raise ControllerError("Failed to stop daemon")

            logger.info("Daemon forcefully stopped")

        except ProcessLookupError:
            # Process already gone
            logger.info("Daemon already stopped")
        except Exception as e:
            raise ControllerError(f"Failed to stop daemon: {e}") from e

    def restart_daemon(self) -> None:
        """Restart the lifecycle daemon.

        Raises:
            ControllerError: If restart fails
        """
        logger.info("Restarting daemon...")

        # Stop if running
        if self._is_daemon_running():
            self.stop_daemon()

        # Wait a moment
        time.sleep(1)

        # Start
        self.start_daemon()

        logger.info("Daemon restarted successfully")

    def daemon_status(self):
        """Get daemon status.

        Returns:
            DaemonStatus with current state
        """
        from azlin.lifecycle.lifecycle_daemon import DaemonStatus
        from datetime import datetime, timedelta

        pid = self._get_daemon_pid()
        running = pid is not None

        # Calculate uptime if running
        uptime = None
        if running and self.pid_file.exists():
            try:
                # Use PID file mtime as start time approximation
                stat = self.pid_file.stat()
                start_time = datetime.fromtimestamp(stat.st_mtime)
                uptime = datetime.now() - start_time
            except Exception as e:
                logger.debug(f"Failed to calculate uptime: {e}")

        # Get monitored VMs
        monitored_vms = []
        try:
            monitored_vms = self.lifecycle_manager.list_monitored_vms()
        except Exception as e:
            logger.error(f"Failed to get monitored VMs: {e}")

        return DaemonStatus(
            running=running,
            pid=pid,
            uptime=uptime,
            monitored_vms=monitored_vms,
        )

    def show_logs(self, lines: int = 50, follow: bool = False) -> None:
        """Show daemon logs.

        Args:
            lines: Number of lines to show
            follow: Follow log output (like tail -f)

        Raises:
            ControllerError: If log file doesn't exist
        """
        if not self.log_file.exists():
            raise ControllerError(f"Log file not found: {self.log_file}")

        if follow:
            # Follow logs with tail -f
            try:
                subprocess.run(["tail", "-f", str(self.log_file)])
            except KeyboardInterrupt:
                pass
        else:
            # Show last N lines
            try:
                result = subprocess.run(
                    ["tail", "-n", str(lines), str(self.log_file)],
                    capture_output=True,
                    text=True,
                )
                print(result.stdout)
            except Exception as e:
                raise ControllerError(f"Failed to read logs: {e}") from e


__all__ = [
    "DaemonController",
    "ControllerError",
]
