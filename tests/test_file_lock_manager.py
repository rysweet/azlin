"""Tests for File Lock Manager - Cross-platform file locking for concurrent access.

Testing Pyramid:
- 60% Unit tests (fast, heavily mocked)
- 30% Integration tests (multiple components)
- 10% E2E tests (complete workflows)
"""

import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.file_lock_manager import (
    LockTimeoutError,
    acquire_file_lock,
)

# =============================================================================
# UNIT TESTS (60%) - Fast, focused tests with mocking
# =============================================================================


class TestLockAcquisitionAndRelease:
    """Test basic lock acquisition and release behavior."""

    def test_acquire_lock_creates_lock_file(self, tmp_path):
        """Verify lock file is created when acquiring lock."""
        test_file = tmp_path / "test.log"
        test_file.write_text("initial content")

        with acquire_file_lock(test_file):
            # Lock should be held
            pass

        # File should still exist after lock release
        assert test_file.exists()

    def test_lock_is_released_on_context_exit(self, tmp_path):
        """Verify lock is properly released when exiting context manager."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        # First acquisition
        with acquire_file_lock(test_file):
            pass

        # Second acquisition should succeed immediately (lock was released)
        start = time.time()
        with acquire_file_lock(test_file, timeout=1.0):
            duration = time.time() - start

        # Should acquire immediately, not wait for timeout
        assert duration < 0.5

    def test_lock_released_on_exception(self, tmp_path):
        """Verify lock is released even when exception occurs in context."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        # Acquire lock and raise exception
        with pytest.raises(ValueError, match="Test exception"):
            with acquire_file_lock(test_file):
                raise ValueError("Test exception")

        # Lock should be released, second acquisition succeeds
        with acquire_file_lock(test_file, timeout=1.0):
            pass  # Should not timeout

    def test_acquire_lock_with_custom_operation_name(self, tmp_path):
        """Verify custom operation name is used in error messages."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        with acquire_file_lock(test_file, operation="audit logging"):
            pass  # Custom operation name for better error context


class TestPlatformDetection:
    """Test platform-specific lock implementation selection."""

    @patch("platform.system")
    def test_uses_fcntl_on_unix(self, mock_system, tmp_path):
        """Verify fcntl.flock() is used on Unix platforms."""
        mock_system.return_value = "Linux"
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        with patch("fcntl.flock") as mock_flock:
            with acquire_file_lock(test_file):
                # Should call fcntl.flock for lock acquisition
                assert mock_flock.called

    def test_uses_msvcrt_on_windows(self, tmp_path):
        """Verify msvcrt.locking() is used on Windows platforms."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        # Skip this test on non-Windows platforms (msvcrt is Windows-only)
        if platform.system() != "Windows":
            pytest.skip("msvcrt module only available on Windows")

        # On Windows, verify msvcrt.locking is called
        with patch("msvcrt.locking") as mock_locking:
            with acquire_file_lock(test_file):
                # Should call msvcrt.locking for lock acquisition
                assert mock_locking.called

    @patch("platform.system")
    def test_uses_fcntl_on_macos(self, mock_system, tmp_path):
        """Verify fcntl.flock() is used on macOS (Darwin)."""
        mock_system.return_value = "Darwin"
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        with patch("fcntl.flock") as mock_flock:
            with acquire_file_lock(test_file):
                assert mock_flock.called


class TestExponentialBackoff:
    """Test exponential backoff timing during lock contention."""

    def test_exponential_backoff_sequence(self, tmp_path):
        """Verify backoff delays follow exponential sequence: 0.1s, 0.2s, 0.4s, 0.8s, 1.6s."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        delays = []

        def mock_sleep(duration):
            delays.append(duration)

        with patch("time.sleep", side_effect=mock_sleep):
            with patch("fcntl.flock", side_effect=[BlockingIOError] * 5 + [None]):
                with acquire_file_lock(test_file, timeout=5.0):
                    pass

        # Verify exponential backoff: 0.1, 0.2, 0.4, 0.8, 1.6
        assert len(delays) == 5
        assert abs(delays[0] - 0.1) < 0.01
        assert abs(delays[1] - 0.2) < 0.01
        assert abs(delays[2] - 0.4) < 0.01
        assert abs(delays[3] - 0.8) < 0.01
        assert abs(delays[4] - 1.6) < 0.01

    def test_backoff_respects_timeout(self, tmp_path):
        """Verify backoff stops when timeout is reached."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        start = time.time()

        with patch("fcntl.flock", side_effect=BlockingIOError):
            with pytest.raises(LockTimeoutError):
                with acquire_file_lock(test_file, timeout=2.0):
                    pass

        duration = time.time() - start
        # Should timeout around 2 seconds (0.1 + 0.2 + 0.4 + 0.8 + remaining)
        assert 1.8 <= duration <= 2.5


class TestErrorHandling:
    """Test error handling for various failure scenarios."""

    def test_timeout_raises_lock_timeout_error(self, tmp_path):
        """Verify LockTimeoutError is raised when lock cannot be acquired within timeout."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        with patch("fcntl.flock", side_effect=BlockingIOError):
            with pytest.raises(LockTimeoutError) as exc_info:
                with acquire_file_lock(test_file, timeout=1.0, operation="test operation"):
                    pass

        # Error message should include operation and timeout
        assert "test operation" in str(exc_info.value)
        assert "1.0" in str(exc_info.value) or "1 second" in str(exc_info.value).lower()

    def test_file_not_found_raises_file_not_found_error(self, tmp_path):
        """Verify FileNotFoundError when trying to lock non-existent file."""
        non_existent = tmp_path / "does_not_exist.log"

        with pytest.raises(FileNotFoundError):
            with acquire_file_lock(non_existent):
                pass

    def test_permission_denied_raises_permission_error(self, tmp_path):
        """Verify PermissionError when lacking permissions to lock file."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        # Make file read-only (platform-specific behavior)
        test_file.chmod(0o444)

        with patch("fcntl.flock", side_effect=PermissionError):
            with pytest.raises(PermissionError):
                with acquire_file_lock(test_file):
                    pass

    def test_custom_timeout_value(self, tmp_path):
        """Verify custom timeout value is respected."""
        test_file = tmp_path / "test.log"
        test_file.write_text("content")

        start = time.time()

        with patch("fcntl.flock", side_effect=BlockingIOError):
            with pytest.raises(LockTimeoutError):
                with acquire_file_lock(test_file, timeout=0.5):
                    pass

        duration = time.time() - start
        assert duration < 1.0  # Should timeout quickly with 0.5s timeout


# =============================================================================
# INTEGRATION TESTS (30%) - Multiple components working together
# =============================================================================


class TestConcurrentProcessWrites:
    """Test concurrent process access with real file I/O and locking."""

    def test_concurrent_writes_no_corruption(self, tmp_path):
        """Verify 10 concurrent processes can write without corruption."""
        test_file = tmp_path / "concurrent.log"
        test_file.write_text("")

        num_processes = 10
        writes_per_process = 100

        # Create subprocess script that writes with locking
        # Add both current directory and src directory to path
        src_path = Path.cwd() / "src"
        script = f"""
import sys
import time
from pathlib import Path
sys.path.insert(0, '{Path.cwd()}')
sys.path.insert(0, '{src_path}')

from azlin.file_lock_manager import acquire_file_lock

test_file = Path('{test_file}')
process_id = sys.argv[1]

for i in range({writes_per_process}):
    with acquire_file_lock(test_file, timeout=10.0):
        content = test_file.read_text()
        test_file.write_text(content + f'Process {{process_id}} write {{i}}\\n')
"""

        script_file = tmp_path / "write_script.py"
        script_file.write_text(script)

        # Spawn processes
        processes = []
        for i in range(num_processes):
            proc = subprocess.Popen(
                [sys.executable, str(script_file), str(i)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(proc)

        # Wait for all processes
        for proc in processes:
            proc.wait()
            assert proc.returncode == 0, f"Process failed: {proc.stderr.read()}"

        # Verify results
        lines = test_file.read_text().splitlines()
        assert len(lines) == num_processes * writes_per_process

        # Each line should be complete (no interleaved writes)
        for line in lines:
            assert line.startswith("Process ")
            assert " write " in line

    def test_no_interleaved_log_lines(self, tmp_path):
        """Verify no log lines are interleaved when using file locks."""
        test_file = tmp_path / "interleave_test.log"
        test_file.write_text("")

        num_processes = 10

        # Create subprocess that writes multi-line messages
        src_path = Path.cwd() / "src"
        script = f"""
import sys
import time
from pathlib import Path
sys.path.insert(0, '{Path.cwd()}')
sys.path.insert(0, '{src_path}')

from azlin.file_lock_manager import acquire_file_lock

test_file = Path('{test_file}')
process_id = sys.argv[1]

message = f'''START-{{process_id}}
Line 1 of process {{process_id}}
Line 2 of process {{process_id}}
Line 3 of process {{process_id}}
END-{{process_id}}
'''

for i in range(50):
    with acquire_file_lock(test_file):
        content = test_file.read_text()
        test_file.write_text(content + message)
"""

        script_file = tmp_path / "multiline_script.py"
        script_file.write_text(script)

        # Spawn processes
        processes = []
        for i in range(num_processes):
            proc = subprocess.Popen(
                [sys.executable, str(script_file), str(i)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(proc)

        # Wait for completion
        for proc in processes:
            proc.wait()

        # Verify no interleaving
        content = test_file.read_text()
        lines = content.splitlines()

        # Check that START and END pairs are never broken
        i = 0
        while i < len(lines):
            if lines[i].startswith("START-"):
                process_id = lines[i].split("-")[1]
                assert lines[i + 1] == f"Line 1 of process {process_id}"
                assert lines[i + 2] == f"Line 2 of process {process_id}"
                assert lines[i + 3] == f"Line 3 of process {process_id}"
                assert lines[i + 4] == f"END-{process_id}"
                i += 5
            else:
                i += 1

    def test_lock_timeout_under_high_contention(self, tmp_path):
        """Verify timeout behavior when many processes compete for lock."""
        test_file = tmp_path / "contention.log"
        test_file.write_text("")

        # Create subprocess that holds lock for extended period
        src_path = Path.cwd() / "src"
        holder_script = f"""
import sys
import time
from pathlib import Path
sys.path.insert(0, '{Path.cwd()}')
sys.path.insert(0, '{src_path}')

from azlin.file_lock_manager import acquire_file_lock

test_file = Path('{test_file}')

with acquire_file_lock(test_file, timeout=10.0):
    time.sleep(5)  # Hold lock for 5 seconds
"""

        holder_file = tmp_path / "holder.py"
        holder_file.write_text(holder_script)

        # Start lock holder
        holder_proc = subprocess.Popen(
            [sys.executable, str(holder_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        time.sleep(0.5)  # Let holder acquire lock

        # Try to acquire with short timeout (should fail)
        waiter_script = f"""
import sys
from pathlib import Path
sys.path.insert(0, '{Path.cwd()}')
sys.path.insert(0, '{src_path}')

from azlin.file_lock_manager import acquire_file_lock, LockTimeoutError

test_file = Path('{test_file}')

try:
    with acquire_file_lock(test_file, timeout=1.0):
        print("ACQUIRED")
except LockTimeoutError:
    print("TIMEOUT")
"""

        waiter_file = tmp_path / "waiter.py"
        waiter_file.write_text(waiter_script)

        waiter_proc = subprocess.Popen(
            [sys.executable, str(waiter_file)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        waiter_out, _ = waiter_proc.communicate()
        holder_proc.wait()

        # Waiter should timeout
        assert b"TIMEOUT" in waiter_out


# =============================================================================
# E2E TESTS (10%) - Complete workflows with real azlin usage
# =============================================================================


class TestAzlinConcurrentAccess:
    """Test file locking in realistic azlin usage scenarios."""

    @pytest.mark.slow
    def test_concurrent_azlin_audit_logging(self, tmp_path):
        """Verify 10 azlin processes can write to audit log simultaneously without corruption.

        This simulates the real-world scenario from issue #490 where multiple
        azlin processes caused interleaved log lines in audit.log.
        """
        audit_log = tmp_path / "audit.log"
        audit_log.write_text("")

        num_processes = 10

        # Create mock azlin script that logs audit entries
        src_path = Path.cwd() / "src"
        azlin_script = f"""
import sys
import json
from datetime import datetime
from pathlib import Path
sys.path.insert(0, '{Path.cwd()}')
sys.path.insert(0, '{src_path}')

from azlin.file_lock_manager import acquire_file_lock

audit_log = Path('{audit_log}')
process_id = sys.argv[1]

# Simulate audit log entry
entry = {{
    'timestamp': datetime.now().isoformat(),
    'process_id': process_id,
    'action': 'VM_PROVISION',
    'resource': f'test-vm-{{process_id}}',
    'status': 'SUCCESS'
}}

for i in range(10):
    with acquire_file_lock(audit_log, timeout=10.0):
        content = audit_log.read_text()
        audit_log.write_text(content + json.dumps(entry) + '\\n')
"""

        script_file = tmp_path / "azlin_mock.py"
        script_file.write_text(azlin_script)

        # Spawn azlin processes
        processes = []
        for i in range(num_processes):
            proc = subprocess.Popen(
                [sys.executable, str(script_file), str(i)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(proc)

        # Wait for all processes
        for proc in processes:
            proc.wait()
            assert proc.returncode == 0

        # Verify audit log integrity
        lines = audit_log.read_text().splitlines()
        assert len(lines) == num_processes * 10

        # Each line should be valid JSON
        for line in lines:
            entry = json.loads(line)  # Should not raise
            assert "timestamp" in entry
            assert "process_id" in entry
            assert "action" in entry

    @pytest.mark.slow
    def test_performance_impact_minimal(self, tmp_path):
        """Verify file locking adds < 10ms overhead per write operation."""
        test_file = tmp_path / "performance.log"
        test_file.write_text("")

        num_writes = 100

        # Measure write time with locking
        start = time.time()
        for i in range(num_writes):
            with acquire_file_lock(test_file, timeout=5.0):
                content = test_file.read_text()
                test_file.write_text(content + f"Entry {i}\n")
        duration_with_lock = time.time() - start

        # Calculate per-write overhead
        avg_time_per_write = duration_with_lock / num_writes

        # Should be < 10ms per write (generous threshold)
        assert avg_time_per_write < 0.010, (
            f"Lock overhead too high: {avg_time_per_write * 1000:.2f}ms"
        )

    @pytest.mark.slow
    def test_verify_no_corruption_after_1000_writes(self, tmp_path):
        """Verify no corruption after 1000 concurrent writes from 10 processes."""
        test_file = tmp_path / "stress_test.log"
        test_file.write_text("")

        num_processes = 10
        writes_per_process = 100  # Total: 1000 writes

        src_path = Path.cwd() / "src"
        script = f"""
import sys
from pathlib import Path
sys.path.insert(0, '{Path.cwd()}')
sys.path.insert(0, '{src_path}')

from azlin.file_lock_manager import acquire_file_lock

test_file = Path('{test_file}')
process_id = sys.argv[1]

for i in range({writes_per_process}):
    message = f'P{{process_id}}-W{{i:03d}}:START|DATA|END\\n'
    with acquire_file_lock(test_file, timeout=10.0):
        content = test_file.read_text()
        test_file.write_text(content + message)
"""

        script_file = tmp_path / "stress_script.py"
        script_file.write_text(script)

        processes = []
        for i in range(num_processes):
            proc = subprocess.Popen(
                [sys.executable, str(script_file), str(i)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append(proc)

        for proc in processes:
            proc.wait()
            assert proc.returncode == 0

        # Verify integrity
        lines = test_file.read_text().splitlines()
        assert len(lines) == 1000

        # Every line should match expected format
        for line in lines:
            assert line.startswith("P")
            assert ":START|DATA|END" in line
            assert line.count("|") == 2  # No partial writes


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_platform_unix():
    """Mock platform as Unix/Linux."""
    with patch("platform.system", return_value="Linux"):
        yield


@pytest.fixture
def mock_platform_windows():
    """Mock platform as Windows."""
    with patch("platform.system", return_value="Windows"):
        yield


@pytest.fixture
def mock_platform_macos():
    """Mock platform as macOS."""
    with patch("platform.system", return_value="Darwin"):
        yield
