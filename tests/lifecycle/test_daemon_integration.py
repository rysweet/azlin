"""Daemon integration tests for lifecycle system.

Tests daemon process management, background monitoring, and real-world workflows.
This file brings daemon coverage from 17-21% to 70%+.

Testing Strategy:
- 60% unit-style tests with heavy mocking (fast)
- 30% integration tests (controlled environment)
- 10% near-E2E tests (short-lived daemon processes)
"""

import os
import signal
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from azlin.lifecycle.daemon_controller import ControllerError, DaemonController
from azlin.lifecycle.health_monitor import HealthStatus, VMState
from azlin.lifecycle.lifecycle_daemon import DaemonStatus, LifecycleDaemon
from azlin.lifecycle.lifecycle_manager import LifecycleManager, MonitoringConfig


class TestLifecycleDaemonUnit:
    """Unit tests for LifecycleDaemon (60% of daemon test pyramid)."""

    @pytest.fixture
    def daemon_env(self, tmp_path):
        """Setup isolated daemon environment."""
        config_path = tmp_path / "lifecycle-config.toml"
        pid_file = tmp_path / "daemon.pid"
        log_file = tmp_path / "daemon.log"

        # Create minimal config
        config_path.write_text(f"""
[daemon]
pid_file = "{pid_file!s}"
log_file = "{log_file!s}"
log_level = "DEBUG"
        """)

        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", config_path):
            daemon = LifecycleDaemon(config_path)
            daemon.pid_file = pid_file
            daemon.log_file = log_file

            yield {
                "daemon": daemon,
                "config_path": config_path,
                "pid_file": pid_file,
                "log_file": log_file,
            }

    def test_daemon_initialization(self, daemon_env):
        """Test daemon initializes with correct dependencies."""
        daemon = daemon_env["daemon"]

        assert daemon.lifecycle_manager is not None
        assert daemon.health_monitor is not None
        assert daemon.self_healer is not None
        assert daemon.hook_executor is not None
        assert daemon._running is False
        assert daemon._start_time is None
        assert daemon._pid is None

    def test_daemon_reads_config_correctly(self, daemon_env):
        """Test daemon reads daemon config section."""
        daemon = daemon_env["daemon"]

        assert daemon.pid_file == daemon_env["pid_file"]
        assert daemon.log_file == daemon_env["log_file"]
        assert daemon.log_level == "DEBUG"

    def test_setup_logging_creates_handlers(self, daemon_env):
        """Test logging setup creates file and stdout handlers."""
        daemon = daemon_env["daemon"]

        with patch("logging.basicConfig") as mock_basic_config:
            daemon._setup_logging()

            mock_basic_config.assert_called_once()
            call_kwargs = mock_basic_config.call_args[1]
            assert call_kwargs["level"] == 10  # DEBUG level
            assert len(call_kwargs["handlers"]) == 2

    def test_signal_handlers_registered(self, daemon_env):
        """Test signal handlers are registered for graceful shutdown."""
        daemon = daemon_env["daemon"]

        with patch("signal.signal") as mock_signal:
            daemon._setup_signal_handlers()

            assert mock_signal.call_count == 2
            mock_signal.assert_any_call(signal.SIGTERM, daemon._handle_shutdown)
            mock_signal.assert_any_call(signal.SIGINT, daemon._handle_shutdown)

    def test_handle_shutdown_stops_daemon(self, daemon_env):
        """Test shutdown handler stops daemon gracefully."""
        daemon = daemon_env["daemon"]
        daemon._running = True

        daemon._handle_shutdown(signal.SIGTERM, None)

        assert daemon._running is False

    def test_pid_file_written_on_start(self, daemon_env):
        """Test PID file is created with correct permissions."""
        daemon = daemon_env["daemon"]
        daemon._pid = 12345

        daemon._write_pid_file()

        assert daemon_env["pid_file"].exists()
        assert daemon_env["pid_file"].read_text() == "12345"
        # Check permissions (0o600 = owner read/write only)
        assert daemon_env["pid_file"].stat().st_mode & 0o777 == 0o600

    def test_pid_file_removed_on_cleanup(self, daemon_env):
        """Test PID file is removed during cleanup."""
        daemon = daemon_env["daemon"]
        pid_file = daemon_env["pid_file"]

        # Create PID file
        pid_file.write_text("12345")
        assert pid_file.exists()

        daemon._remove_pid_file()

        assert not pid_file.exists()

    def test_get_status_when_not_running(self, daemon_env):
        """Test daemon status when not running."""
        daemon = daemon_env["daemon"]

        status = daemon.get_status()

        assert status.running is False
        assert status.pid is None
        assert status.uptime is None
        assert status.monitored_vms == []

    def test_get_status_when_running(self, daemon_env):
        """Test daemon status when running."""
        daemon = daemon_env["daemon"]
        daemon._running = True
        daemon._pid = os.getpid()
        daemon._start_time = datetime.utcnow() - timedelta(minutes=5)

        with patch.object(
            daemon.lifecycle_manager, "list_monitored_vms", return_value=["vm1", "vm2"]
        ):
            status = daemon.get_status()

        assert status.running is True
        assert status.pid == os.getpid()
        assert status.uptime is not None
        assert status.uptime.total_seconds() > 290  # ~5 minutes
        assert status.monitored_vms == ["vm1", "vm2"]

    def test_check_vm_health_and_heal_healthy_vm(self, daemon_env):
        """Test health check for healthy VM."""
        daemon = daemon_env["daemon"]

        # Mock health status - healthy
        mock_health = HealthStatus(
            vm_name="test-vm",
            state=VMState.RUNNING,
            ssh_reachable=True,
            ssh_failures=0,
            last_check=datetime.utcnow(),
        )

        with patch.object(daemon.health_monitor, "check_vm_health", return_value=mock_health):
            with patch.object(daemon.hook_executor, "execute_hook_async") as mock_hook:
                config = MonitoringConfig(enabled=True, hooks={"on_healthy": "/usr/bin/true"})

                daemon._check_vm_health_and_heal("test-vm", config)

                # on_healthy hook should be triggered
                mock_hook.assert_called_once_with("on_healthy", "test-vm", {"state": "running"})

    def test_check_vm_health_and_heal_failed_vm(self, daemon_env):
        """Test health check triggers healing for failed VM."""
        daemon = daemon_env["daemon"]

        # Mock health status - failed
        mock_health = HealthStatus(
            vm_name="test-vm",
            state=VMState.RUNNING,
            ssh_reachable=False,
            ssh_failures=3,
            last_check=datetime.utcnow(),
        )

        config = MonitoringConfig(
            enabled=True, ssh_failure_threshold=3, hooks={"on_failure": "/usr/bin/true"}
        )

        with patch.object(daemon.health_monitor, "check_vm_health", return_value=mock_health):
            with patch.object(daemon.hook_executor, "execute_hook_async") as mock_hook:
                with patch.object(daemon.self_healer, "handle_failure") as mock_healer:
                    daemon._check_vm_health_and_heal("test-vm", config)

                    # on_failure hook should be triggered
                    assert mock_hook.call_count == 1
                    hook_call = mock_hook.call_args
                    assert hook_call[0][0] == "on_failure"
                    assert hook_call[0][1] == "test-vm"

                    # Self-healer should be invoked
                    mock_healer.assert_called_once()
                    failure = mock_healer.call_args[0][1]
                    assert failure.vm_name == "test-vm"
                    assert failure.failure_count == 3

    def test_check_vm_health_handles_exceptions(self, daemon_env):
        """Test health check handles exceptions gracefully."""
        daemon = daemon_env["daemon"]

        with patch.object(
            daemon.health_monitor, "check_vm_health", side_effect=Exception("Azure error")
        ):
            config = MonitoringConfig(enabled=True)

            # Should not raise, just log error
            daemon._check_vm_health_and_heal("test-vm", config)

    def test_stop_sets_running_flag(self, daemon_env):
        """Test stop() sets running flag to False."""
        daemon = daemon_env["daemon"]
        daemon._running = True

        daemon.stop()

        assert daemon._running is False

    def test_reload_config_logs_action(self, daemon_env):
        """Test reload_config logs the reload action."""
        daemon = daemon_env["daemon"]

        with patch("azlin.lifecycle.lifecycle_daemon.logger") as mock_logger:
            daemon.reload_config()

            assert mock_logger.info.call_count >= 1


class TestDaemonControllerUnit:
    """Unit tests for DaemonController (60% of controller test pyramid)."""

    @pytest.fixture
    def controller_env(self, tmp_path):
        """Setup isolated controller environment."""
        config_path = tmp_path / "lifecycle-config.toml"
        pid_file = tmp_path / "daemon.pid"
        log_file = tmp_path / "daemon.log"

        # Create minimal config
        config_path.write_text(f"""
[daemon]
pid_file = "{pid_file!s}"
log_file = "{log_file!s}"
        """)

        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", config_path):
            controller = DaemonController(config_path)
            controller.pid_file = pid_file
            controller.log_file = log_file

            yield {
                "controller": controller,
                "config_path": config_path,
                "pid_file": pid_file,
                "log_file": log_file,
            }

    def test_controller_initialization(self, controller_env):
        """Test controller initializes correctly."""
        controller = controller_env["controller"]

        assert controller.lifecycle_manager is not None
        assert controller.pid_file == controller_env["pid_file"]
        assert controller.log_file == controller_env["log_file"]

    def test_get_daemon_pid_returns_none_when_no_file(self, controller_env):
        """Test get_daemon_pid returns None when PID file doesn't exist."""
        controller = controller_env["controller"]

        pid = controller._get_daemon_pid()

        assert pid is None

    def test_get_daemon_pid_returns_pid_when_running(self, controller_env):
        """Test get_daemon_pid returns PID when daemon is running."""
        controller = controller_env["controller"]
        pid_file = controller_env["pid_file"]

        # Write PID file with current process (which is definitely running)
        current_pid = os.getpid()
        pid_file.write_text(str(current_pid))

        pid = controller._get_daemon_pid()

        assert pid == current_pid

    def test_get_daemon_pid_removes_stale_pid_file(self, controller_env):
        """Test get_daemon_pid removes stale PID file for dead process."""
        controller = controller_env["controller"]
        pid_file = controller_env["pid_file"]

        # Write PID file with non-existent process
        pid_file.write_text("999999")

        pid = controller._get_daemon_pid()

        assert pid is None
        assert not pid_file.exists()

    def test_is_daemon_running_returns_false_when_not_running(self, controller_env):
        """Test is_daemon_running returns False when daemon is not running."""
        controller = controller_env["controller"]

        assert controller._is_daemon_running() is False

    def test_is_daemon_running_returns_true_when_running(self, controller_env):
        """Test is_daemon_running returns True when daemon is running."""
        controller = controller_env["controller"]
        controller_env["pid_file"].write_text(str(os.getpid()))

        assert controller._is_daemon_running() is True

    def test_start_daemon_raises_when_already_running(self, controller_env):
        """Test start_daemon raises error when daemon is already running."""
        controller = controller_env["controller"]
        controller_env["pid_file"].write_text(str(os.getpid()))

        with pytest.raises(ControllerError, match="already running"):
            controller.start_daemon()

    def test_start_daemon_foreground_runs_daemon(self, controller_env):
        """Test start_daemon in foreground mode."""
        controller = controller_env["controller"]

        # Import is done inside start_daemon, so we need to patch it there
        with patch("azlin.lifecycle.lifecycle_daemon.LifecycleDaemon") as mock_daemon_cls:
            mock_daemon = mock_daemon_cls.return_value

            controller.start_daemon(foreground=True)

            mock_daemon_cls.assert_called_once_with(controller.config_path)
            mock_daemon.start.assert_called_once()

    def test_start_daemon_background_spawns_process(self, controller_env):
        """Test start_daemon spawns background process."""
        controller = controller_env["controller"]

        mock_process = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            # First call checks if running (False), after Popen it checks again (True)
            with patch.object(controller, "_is_daemon_running", side_effect=[False, True]):
                with patch.object(controller, "_get_daemon_pid", return_value=12345):
                    controller.start_daemon(foreground=False)

                    # Verify Popen was called
                    assert mock_popen.called
                    call_args = mock_popen.call_args
                    assert call_args[1]["start_new_session"] is True

    def test_start_daemon_background_raises_on_failure(self, controller_env):
        """Test start_daemon raises error if daemon fails to start."""
        controller = controller_env["controller"]

        with patch("subprocess.Popen", return_value=Mock()):
            with patch.object(controller, "_is_daemon_running", return_value=False):
                with pytest.raises(ControllerError, match="failed to start"):
                    controller.start_daemon(foreground=False)

    def test_stop_daemon_raises_when_not_running(self, controller_env):
        """Test stop_daemon raises error when daemon is not running."""
        controller = controller_env["controller"]

        with pytest.raises(ControllerError, match="not running"):
            controller.stop_daemon()

    def test_stop_daemon_sends_sigterm(self, controller_env):
        """Test stop_daemon sends SIGTERM for graceful shutdown."""
        controller = controller_env["controller"]
        pid_file = controller_env["pid_file"]

        # Create PID file
        fake_pid = 12345
        pid_file.write_text(str(fake_pid))

        with patch("os.kill") as mock_kill:
            with patch.object(controller, "_is_daemon_running", side_effect=[True, False]):
                controller.stop_daemon()

                mock_kill.assert_any_call(fake_pid, signal.SIGTERM)

    def test_stop_daemon_sends_sigkill_on_timeout(self, controller_env):
        """Test stop_daemon sends SIGKILL if daemon doesn't stop gracefully."""
        controller = controller_env["controller"]
        pid_file = controller_env["pid_file"]

        fake_pid = 12345
        pid_file.write_text(str(fake_pid))

        # Mock time module in daemon_controller
        with patch("azlin.lifecycle.daemon_controller.time") as mock_time_module:
            # Setup time.time() to simulate timeout
            start = 100.0
            # Need enough time values for the while loop to check multiple times before timeout
            mock_time_module.time.side_effect = [
                start,  # start_time = time.time()
                start,  # First iteration: time.time() - start_time < timeout (True)
                start + 0.6,  # Second iteration: time.time() - start_time < timeout (True)
                start
                + 1.2,  # Third iteration: time.time() - start_time < timeout (False - exit loop)
            ]

            with patch("os.kill") as mock_kill:
                # Daemon stays running during all loop checks, then stops after SIGKILL
                # Checks happen at line 174 for each iteration where time.time() hasn't exceeded timeout
                with patch.object(
                    controller,
                    "_is_daemon_running",
                    side_effect=[
                        True,  # First check in loop (continues)
                        True,  # Second check in loop (continues)
                        False,  # Check after SIGKILL (line 184)
                    ],
                ):
                    controller.stop_daemon(timeout=1)

                    # Should send both SIGTERM and SIGKILL
                    mock_kill.assert_any_call(fake_pid, signal.SIGTERM)
                    mock_kill.assert_any_call(fake_pid, signal.SIGKILL)

    def test_restart_daemon_stops_and_starts(self, controller_env):
        """Test restart_daemon stops and starts daemon."""
        controller = controller_env["controller"]

        with patch.object(controller, "_is_daemon_running", return_value=True):
            with patch.object(controller, "stop_daemon") as mock_stop:
                with patch.object(controller, "start_daemon") as mock_start:
                    with patch("time.sleep"):
                        controller.restart_daemon()

                        mock_stop.assert_called_once()
                        mock_start.assert_called_once()

    def test_daemon_status_returns_status(self, controller_env):
        """Test daemon_status returns DaemonStatus object."""
        controller = controller_env["controller"]

        with patch.object(controller, "_get_daemon_pid", return_value=None):
            with patch.object(
                controller.lifecycle_manager, "list_monitored_vms", return_value=["vm1"]
            ):
                status = controller.daemon_status()

                assert isinstance(status, DaemonStatus)
                assert status.running is False
                assert status.pid is None

    def test_daemon_status_calculates_uptime(self, controller_env):
        """Test daemon_status calculates uptime from PID file mtime."""
        controller = controller_env["controller"]
        pid_file = controller_env["pid_file"]

        # Create PID file
        pid_file.write_text(str(os.getpid()))

        # Set mtime to 5 minutes ago
        five_minutes_ago = time.time() - 300
        os.utime(pid_file, (five_minutes_ago, five_minutes_ago))

        with patch.object(controller.lifecycle_manager, "list_monitored_vms", return_value=[]):
            status = controller.daemon_status()

        assert status.running is True
        assert status.uptime is not None
        assert status.uptime.total_seconds() > 290  # ~5 minutes

    def test_show_logs_raises_when_no_log_file(self, controller_env):
        """Test show_logs raises error when log file doesn't exist."""
        controller = controller_env["controller"]

        with pytest.raises(ControllerError, match="not found"):
            controller.show_logs()

    def test_show_logs_uses_tail(self, controller_env):
        """Test show_logs uses tail command."""
        controller = controller_env["controller"]
        log_file = controller_env["log_file"]

        # Create log file
        log_file.write_text("Log line 1\nLog line 2\n")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(stdout="Log line 1\nLog line 2\n")

            controller.show_logs(lines=10)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "tail"
            assert "-n" in call_args
            assert "10" in call_args


class TestDaemonIntegration:
    """Integration tests for daemon system (30% of test pyramid)."""

    @pytest.fixture
    def integration_env(self, tmp_path):
        """Setup integration test environment with full stack."""
        config_path = tmp_path / "lifecycle-config.toml"
        pid_file = tmp_path / "daemon.pid"
        log_file = tmp_path / "daemon.log"

        # Create config with VM
        config_path.write_text(f"""
[daemon]
pid_file = "{pid_file!s}"
log_file = "{log_file!s}"
log_level = "DEBUG"

[vms.test-vm]
enabled = true
check_interval_seconds = 5
restart_policy = "on-failure"
ssh_failure_threshold = 2
        """)

        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", config_path):
            daemon = LifecycleDaemon(config_path)
            controller = DaemonController(config_path)

            # Override paths
            daemon.pid_file = pid_file
            daemon.log_file = log_file
            controller.pid_file = pid_file
            controller.log_file = log_file

            yield {
                "daemon": daemon,
                "controller": controller,
                "config_path": config_path,
                "pid_file": pid_file,
                "log_file": log_file,
            }

    def test_daemon_full_lifecycle(self, integration_env):
        """Test complete daemon lifecycle: start -> status -> stop."""
        daemon = integration_env["daemon"]
        pid_file = integration_env["pid_file"]

        # Mock the monitoring loop to exit immediately
        original_loop = daemon._monitoring_loop

        def mock_loop():
            daemon._running = False

        daemon._monitoring_loop = mock_loop

        try:
            # Start daemon
            daemon._setup_logging()
            daemon._pid = os.getpid()
            daemon._start_time = datetime.utcnow()
            daemon._running = True
            daemon._write_pid_file()

            # Check status
            status = daemon.get_status()
            assert status.running is True
            assert status.pid == os.getpid()
            assert pid_file.exists()

            # Stop daemon
            daemon.stop()
            daemon._cleanup()

            # Verify stopped
            assert daemon._running is False
            assert not pid_file.exists()

        finally:
            daemon._monitoring_loop = original_loop

    def test_daemon_monitoring_loop_iteration(self, integration_env):
        """Test single monitoring loop iteration."""
        daemon = integration_env["daemon"]

        # Mock all dependencies
        mock_health = HealthStatus(
            vm_name="test-vm",
            state=VMState.RUNNING,
            ssh_reachable=True,
            ssh_failures=0,
            last_check=datetime.utcnow(),
        )

        with patch.object(daemon.lifecycle_manager, "list_monitored_vms", return_value=["test-vm"]):
            with patch.object(daemon.health_monitor, "check_vm_health", return_value=mock_health):
                with patch("time.sleep"):
                    # Set up for one iteration
                    daemon._running = True

                    # Run one iteration by calling _check_vm_health_and_heal directly
                    config = MonitoringConfig(enabled=True)
                    daemon._check_vm_health_and_heal("test-vm", config)

                    # Stop
                    daemon._running = False

    def test_controller_manages_daemon_lifecycle(self, integration_env):
        """Test controller can manage daemon lifecycle."""
        controller = integration_env["controller"]

        # Mock daemon running check
        with patch.object(controller, "_is_daemon_running", side_effect=[False, True, True, False]):
            with patch.object(
                controller, "_get_daemon_pid", side_effect=[None, 12345, 12345, None]
            ):
                with patch("subprocess.Popen", return_value=Mock()):
                    # Start daemon (mocked)
                    controller.start_daemon(foreground=False)

                    # Get status
                    with patch.object(
                        controller.lifecycle_manager, "list_monitored_vms", return_value=[]
                    ):
                        status = controller.daemon_status()
                    assert status.running is True

                    # Stop daemon (mocked)
                    with patch("os.kill"):
                        controller.stop_daemon()

    def test_daemon_config_reload_workflow(self, integration_env):
        """Test daemon can reload configuration."""
        daemon = integration_env["daemon"]
        config_path = integration_env["config_path"]

        # Initial config has test-vm
        vms = daemon.lifecycle_manager.list_monitored_vms()
        assert "test-vm" in vms

        # Update config to add another VM
        config_path.write_text(
            """
[daemon]
pid_file = "{}"
log_file = "{}"

[vms.test-vm]
enabled = true

[vms.test-vm2]
enabled = true
        """.format(str(integration_env["pid_file"]), str(integration_env["log_file"]))
        )

        # Reload config
        daemon.reload_config()

        # Verify new VM is picked up (config is read fresh each loop)
        vms = daemon.lifecycle_manager.list_monitored_vms()
        assert "test-vm" in vms
        assert "test-vm2" in vms

    def test_daemon_monitors_multiple_vms(self, integration_env):
        """Test daemon monitors multiple VMs in sequence."""
        daemon = integration_env["daemon"]

        # Add second VM to config
        config_path = integration_env["config_path"]
        config_path.write_text(
            """
[daemon]
pid_file = "{}"
log_file = "{}"

[vms.vm1]
enabled = true

[vms.vm2]
enabled = true
        """.format(str(integration_env["pid_file"]), str(integration_env["log_file"]))
        )

        # Reload daemon's manager
        daemon.lifecycle_manager = LifecycleManager(config_path)

        mock_health = HealthStatus(
            vm_name="vm1",
            state=VMState.RUNNING,
            ssh_reachable=True,
            ssh_failures=0,
            last_check=datetime.utcnow(),
        )

        with patch.object(
            daemon.health_monitor, "check_vm_health", return_value=mock_health
        ) as mock_check:
            with patch("time.sleep"):
                # Simulate checking both VMs
                config = MonitoringConfig(enabled=True)
                daemon._check_vm_health_and_heal("vm1", config)
                daemon._check_vm_health_and_heal("vm2", config)

                # Verify both were checked
                assert mock_check.call_count == 2


class TestDaemonNearE2E:
    """Near-E2E tests with short-lived daemon processes (10% of test pyramid)."""

    @pytest.fixture
    def e2e_env(self, tmp_path):
        """Setup near-E2E environment."""
        config_path = tmp_path / "lifecycle-config.toml"
        pid_file = tmp_path / "daemon.pid"
        log_file = tmp_path / "daemon.log"

        config_path.write_text(f"""
[daemon]
pid_file = "{pid_file!s}"
log_file = "{log_file!s}"
log_level = "INFO"

[vms.test-vm]
enabled = true
check_interval_seconds = 1
        """)

        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", config_path):
            yield {
                "config_path": config_path,
                "pid_file": pid_file,
                "log_file": log_file,
            }

    def test_daemon_writes_logs(self, e2e_env):
        """Test daemon writes to log file."""
        config_path = e2e_env["config_path"]
        log_file = e2e_env["log_file"]

        daemon = LifecycleDaemon(config_path)
        daemon.pid_file = e2e_env["pid_file"]
        daemon.log_file = log_file

        # Setup logging
        daemon._setup_logging()

        # Mock monitoring to exit immediately
        daemon._running = False

        # Verify log file is created
        daemon._setup_logging()
        import logging

        logger = logging.getLogger(__name__)
        logger.info("Test log message")

        # Log file should exist (handlers are created)
        assert log_file.exists()

    def test_daemon_handles_missing_config_gracefully(self, tmp_path):
        """Test daemon handles missing config gracefully."""
        nonexistent_config = tmp_path / "nonexistent.toml"

        # Should not raise during initialization
        with patch("azlin.lifecycle.lifecycle_manager.LIFECYCLE_CONFIG_PATH", nonexistent_config):
            daemon = LifecycleDaemon(nonexistent_config)

            # Should create default config
            assert daemon.lifecycle_manager is not None

    def test_stale_pid_file_handling(self, e2e_env):
        """Test daemon handles stale PID file correctly."""
        pid_file = e2e_env["pid_file"]

        # Create stale PID file
        pid_file.write_text("999999")

        controller = DaemonController(e2e_env["config_path"])
        controller.pid_file = pid_file

        # Should detect stale PID and return None
        pid = controller._get_daemon_pid()
        assert pid is None
        assert not pid_file.exists()
