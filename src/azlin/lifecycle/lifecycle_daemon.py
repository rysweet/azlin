"""Lifecycle Daemon - Background VM monitoring process.

Philosophy:
- Ruthless simplicity: Simple loop with configurable intervals
- Single responsibility: Monitoring loop orchestration
- Standard library: multiprocessing for daemon process
- Self-contained: Complete daemon lifecycle

Public API (Studs):
    LifecycleDaemon - Background monitoring daemon
    DaemonStatus - Current daemon status
    DaemonError - Daemon operation errors
"""

import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DaemonError(Exception):
    """Raised when daemon operations fail."""
    pass


@dataclass
class DaemonStatus:
    """Current daemon status."""
    running: bool
    pid: Optional[int] = None
    uptime: Optional[timedelta] = None
    monitored_vms: List[str] = None


class LifecycleDaemon:
    """Background VM monitoring daemon.

    Periodically checks health of all enabled VMs and triggers
    self-healing actions when needed.

    Example:
        >>> daemon = LifecycleDaemon()
        >>> daemon.start()  # Runs in background
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize lifecycle daemon.

        Args:
            config_path: Path to lifecycle config file
        """
        from azlin.lifecycle.lifecycle_manager import LifecycleManager
        from azlin.lifecycle.health_monitor import HealthMonitor
        from azlin.lifecycle.self_healer import SelfHealer
        from azlin.lifecycle.hook_executor import HookExecutor

        self.lifecycle_manager = LifecycleManager(config_path)
        self.health_monitor = HealthMonitor()
        self.self_healer = SelfHealer()
        self.hook_executor = HookExecutor()

        self._running = False
        self._start_time: Optional[datetime] = None
        self._pid: Optional[int] = None

        # Load daemon config
        config = self.lifecycle_manager._read_config()
        self.daemon_config = config.get("daemon", {})
        self.pid_file = Path(self.daemon_config.get("pid_file", Path.home() / ".azlin" / "lifecycle-daemon.pid"))
        self.log_file = Path(self.daemon_config.get("log_file", Path.home() / ".azlin" / "lifecycle-daemon.log"))
        self.log_level = self.daemon_config.get("log_level", "INFO")

    def _setup_logging(self):
        """Configure daemon logging."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format=log_format,
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers."""
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()

    def _write_pid_file(self):
        """Write PID file."""
        try:
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.pid_file.write_text(str(self._pid))
            self.pid_file.chmod(0o600)
            logger.info(f"PID file created: {self.pid_file}")
        except Exception as e:
            logger.error(f"Failed to write PID file: {e}")

    def _remove_pid_file(self):
        """Remove PID file."""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
                logger.info("PID file removed")
        except Exception as e:
            logger.error(f"Failed to remove PID file: {e}")

    def _check_vm_health_and_heal(self, vm_name: str, config):
        """Check VM health and trigger healing if needed.

        Args:
            vm_name: VM name
            config: Monitoring configuration
        """
        try:
            # Perform health check
            health = self.health_monitor.check_vm_health(vm_name)

            logger.debug(
                f"Health check {vm_name}: state={health.state}, "
                f"ssh={health.ssh_reachable}, failures={health.ssh_failures}"
            )

            # Trigger on_healthy hook if SSH is reachable
            if health.ssh_reachable and "on_healthy" in config.hooks:
                try:
                    self.hook_executor.execute_hook_async(
                        "on_healthy",
                        vm_name,
                        {"state": health.state.value},
                    )
                except Exception as hook_error:
                    logger.warning(f"on_healthy hook failed for {vm_name}: {hook_error}")

            # Check if failure threshold reached
            if not health.ssh_reachable and health.ssh_failures >= config.ssh_failure_threshold:
                logger.warning(
                    f"VM {vm_name} reached failure threshold: {health.ssh_failures}/{config.ssh_failure_threshold}"
                )

                # Trigger on_failure hook
                if "on_failure" in config.hooks and config.hooks["on_failure"]:
                    try:
                        self.hook_executor.execute_hook_async(
                            "on_failure",
                            vm_name,
                            {
                                "failure_count": health.ssh_failures,
                                "reason": "SSH connectivity lost",
                            },
                        )
                    except Exception as hook_error:
                        logger.warning(f"on_failure hook failed for {vm_name}: {hook_error}")

                # Create failure object for self-healer
                from azlin.lifecycle.health_monitor import HealthFailure
                failure = HealthFailure(
                    vm_name=vm_name,
                    failure_count=health.ssh_failures,
                    reason="SSH connectivity lost",
                )

                # Let self-healer decide and act
                self.self_healer.handle_failure(vm_name, failure)

        except Exception as e:
            logger.error(f"Error checking/healing {vm_name}: {e}")

    def _monitoring_loop(self):
        """Main monitoring loop."""
        logger.info("Monitoring loop started")

        while self._running:
            try:
                # Get all VMs with monitoring enabled
                vm_names = self.lifecycle_manager.list_monitored_vms()

                if not vm_names:
                    logger.debug("No VMs configured for monitoring")
                else:
                    logger.debug(f"Monitoring {len(vm_names)} VMs: {', '.join(vm_names)}")

                    for vm_name in vm_names:
                        if not self._running:
                            break

                        try:
                            # Get VM config
                            status = self.lifecycle_manager.get_monitoring_status(vm_name)
                            if not status.enabled:
                                logger.debug(f"Monitoring disabled for {vm_name}, skipping")
                                continue

                            # Check health and heal if needed
                            self._check_vm_health_and_heal(vm_name, status.config)

                            # Sleep between VMs to avoid overwhelming system
                            time.sleep(1)

                        except Exception as e:
                            logger.error(f"Error monitoring {vm_name}: {e}")
                            continue

                # Sleep for the check interval
                # Use the minimum check interval from all VMs
                min_interval = 60  # Default
                for vm_name in vm_names:
                    try:
                        status = self.lifecycle_manager.get_monitoring_status(vm_name)
                        if status.enabled:
                            min_interval = min(min_interval, status.config.check_interval_seconds)
                    except Exception:
                        continue

                logger.debug(f"Sleeping for {min_interval} seconds until next check")
                time.sleep(min_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(10)  # Back off on errors

        logger.info("Monitoring loop stopped")

    def start(self):
        """Start the monitoring daemon.

        Raises:
            DaemonError: If daemon is already running
        """
        # Check if already running
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text())
                # Check if process exists
                import os
                os.kill(pid, 0)  # Doesn't actually kill, just checks if process exists
                raise DaemonError(f"Daemon already running with PID {pid}")
            except (OSError, ProcessLookupError):
                # Process doesn't exist, remove stale PID file
                logger.warning("Removing stale PID file")
                self.pid_file.unlink()

        # Setup
        self._setup_logging()
        self._setup_signal_handlers()

        # Start daemon
        import os
        self._pid = os.getpid()
        self._start_time = datetime.utcnow()
        self._running = True

        self._write_pid_file()
        logger.info(f"Lifecycle daemon started (PID: {self._pid})")

        # Run monitoring loop
        try:
            self._monitoring_loop()
        finally:
            self._cleanup()

    def stop(self):
        """Stop the monitoring daemon."""
        logger.info("Stopping daemon...")
        self._running = False

    def _cleanup(self):
        """Cleanup daemon resources."""
        self._remove_pid_file()
        logger.info("Daemon stopped")

    def reload_config(self):
        """Reload configuration from disk."""
        logger.info("Reloading configuration...")
        # Config is read on each loop iteration, so no explicit reload needed
        # Just log the action
        logger.info("Configuration reloaded")

    def get_status(self) -> DaemonStatus:
        """Get current daemon status.

        Returns:
            DaemonStatus with current state
        """
        uptime = None
        if self._running and self._start_time:
            uptime = datetime.utcnow() - self._start_time

        monitored_vms = []
        try:
            monitored_vms = self.lifecycle_manager.list_monitored_vms()
        except Exception as e:
            logger.error(f"Failed to get monitored VMs: {e}")

        return DaemonStatus(
            running=self._running,
            pid=self._pid,
            uptime=uptime,
            monitored_vms=monitored_vms,
        )


__all__ = [
    "LifecycleDaemon",
    "DaemonStatus",
    "DaemonError",
]
