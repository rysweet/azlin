"""Tests for distributed top functionality."""

from unittest.mock import Mock, patch

import pytest

from azlin.distributed_top import DistributedTopExecutor, VMMetrics
from azlin.modules.ssh_connector import SSHConfig


@pytest.fixture
def ssh_configs(tmp_path):
    """Create test SSH configurations."""
    key1 = tmp_path / "key1"
    key2 = tmp_path / "key2"
    key1.touch()
    key2.touch()
    return [
        SSHConfig(host="10.0.0.1", user="azureuser", key_path=str(key1)),
        SSHConfig(host="10.0.0.2", user="azureuser", key_path=str(key2)),
    ]


@pytest.fixture
def sample_metrics_output():
    """Sample output from uptime + free + top commands."""
    return """19:45:23 up 2 days,  3:42,  1 user,  load average: 0.52, 0.58, 0.59
              total        used        free      shared  buff/cache   available
Mem:           3943        1234        1567          12        1142        2456
Swap:          2047          56        1991
top - 19:45:23 up 2 days,  3:42,  1 user,  load average: 0.52, 0.58, 0.59
Tasks: 123 total,   1 running, 122 sleeping,   0 stopped,   0 zombie
%Cpu(s):  5.2 us,  2.1 sy,  0.0 ni, 92.5 id,  0.2 wa,  0.0 hi,  0.0 si,  0.0 st
MiB Mem :   3943.0 total,   1567.0 free,   1234.0 used,   1142.0 buff/cache
MiB Swap:   2047.0 total,   1991.0 free,     56.0 used.   2456.0 avail Mem

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
   1234 root      20   0  123456  12345   1234 S   5.2   0.3   0:12.34 python3 app.py
   5678 user1     20   0   45678   4567    456 S   2.1   0.1   0:05.67 node server.js
   9012 user2     20   0   23456   2345    234 S   1.0   0.1   0:02.34 ruby worker.rb"""


class TestDistributedTopExecutor:
    """Tests for DistributedTopExecutor class."""

    def test_init(self, ssh_configs):
        """Test executor initialization."""
        executor = DistributedTopExecutor(
            ssh_configs=ssh_configs,
            interval=15,
            max_workers=5,
            timeout=10,
        )

        assert executor.ssh_configs == ssh_configs
        assert executor.interval == 15
        assert executor.max_workers == 5
        assert executor.timeout == 10

    def test_init_defaults(self, ssh_configs):
        """Test executor initialization with defaults."""
        executor = DistributedTopExecutor(ssh_configs=ssh_configs)

        assert executor.interval == 10
        assert executor.max_workers == 10
        assert executor.timeout == 5

    def test_parse_metrics_output_success(self, sample_metrics_output):
        """Test successful parsing of metrics output."""
        load_avg, cpu_percent, mem_used, mem_total, mem_percent, processes = (
            DistributedTopExecutor._parse_metrics_output(sample_metrics_output)
        )

        # Check load average
        assert load_avg == (0.52, 0.58, 0.59)

        # Check memory
        assert mem_total == 3943
        assert mem_used == 1234
        assert abs(mem_percent - 31.3) < 0.1  # Allow small floating point error

        # Check processes
        assert len(processes) == 3
        assert processes[0]["command"] == "python3 app.py"
        assert processes[0]["cpu"] == "5.2"
        assert processes[0]["mem"] == "0.3"

        # Check CPU (sum of top 3)
        assert abs(cpu_percent - 8.3) < 0.1  # 5.2 + 2.1 + 1.0

    def test_parse_metrics_output_empty(self):
        """Test parsing empty output."""
        load_avg, cpu_percent, mem_used, mem_total, mem_percent, processes = (
            DistributedTopExecutor._parse_metrics_output("")
        )

        assert load_avg is None
        assert cpu_percent is None
        assert mem_used is None
        assert mem_total is None
        assert mem_percent is None
        assert processes == []

    def test_parse_metrics_output_malformed(self):
        """Test parsing malformed output."""
        malformed = "some random text\nwithout proper format"

        load_avg, _cpu_percent, mem_used, _mem_total, _mem_percent, processes = (
            DistributedTopExecutor._parse_metrics_output(malformed)
        )

        assert load_avg is None
        assert mem_used is None
        assert processes == []

    @patch("azlin.distributed_top.subprocess.run")
    def test_collect_vm_metrics_success(self, mock_run, sample_metrics_output, ssh_configs):
        """Test successful metric collection from a VM."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = sample_metrics_output
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        metrics = DistributedTopExecutor.collect_vm_metrics(ssh_configs[0], timeout=5)

        assert metrics.success
        assert metrics.vm_name == "10.0.0.1"
        assert metrics.load_avg == (0.52, 0.58, 0.59)
        assert metrics.memory_total_mb == 3943
        assert metrics.memory_used_mb == 1234
        assert len(metrics.top_processes) == 3

    @patch("azlin.distributed_top.subprocess.run")
    def test_collect_vm_metrics_ssh_failure(self, mock_run, ssh_configs):
        """Test metric collection when SSH fails."""
        mock_result = Mock()
        mock_result.returncode = 255
        mock_result.stdout = ""
        mock_result.stderr = "Connection refused"
        mock_run.return_value = mock_result

        metrics = DistributedTopExecutor.collect_vm_metrics(ssh_configs[0], timeout=5)

        assert not metrics.success
        assert metrics.vm_name == "10.0.0.1"
        assert "Connection refused" in metrics.error_message
        assert metrics.load_avg is None

    @patch("azlin.distributed_top.subprocess.run")
    def test_collect_vm_metrics_timeout(self, mock_run, ssh_configs):
        """Test metric collection when SSH times out."""
        mock_run.side_effect = TimeoutError("Command timed out")

        metrics = DistributedTopExecutor.collect_vm_metrics(ssh_configs[0], timeout=5)

        assert not metrics.success
        assert metrics.vm_name == "10.0.0.1"
        assert "Timeout" in metrics.error_message or "timed out" in metrics.error_message.lower()

    @patch("azlin.distributed_top.subprocess.run")
    def test_collect_all_metrics(self, mock_run, sample_metrics_output, ssh_configs):
        """Test collecting metrics from multiple VMs."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = sample_metrics_output
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = DistributedTopExecutor(ssh_configs=ssh_configs, timeout=5)
        metrics_list = executor.collect_all_metrics()

        assert len(metrics_list) == 2
        assert all(m.success for m in metrics_list)
        assert metrics_list[0].vm_name in ["10.0.0.1", "10.0.0.2"]

    @patch("azlin.distributed_top.subprocess.run")
    def test_collect_all_metrics_mixed_results(self, mock_run, sample_metrics_output, ssh_configs):
        """Test collecting metrics when some VMs succeed and some fail."""
        # First call succeeds, second fails
        success_result = Mock()
        success_result.returncode = 0
        success_result.stdout = sample_metrics_output
        success_result.stderr = ""

        failure_result = Mock()
        failure_result.returncode = 255
        failure_result.stdout = ""
        failure_result.stderr = "Connection failed"

        mock_run.side_effect = [success_result, failure_result]

        executor = DistributedTopExecutor(ssh_configs=ssh_configs, timeout=5)
        metrics_list = executor.collect_all_metrics()

        assert len(metrics_list) == 2
        # One should succeed, one should fail
        success_count = sum(1 for m in metrics_list if m.success)
        failure_count = sum(1 for m in metrics_list if not m.success)
        assert success_count == 1
        assert failure_count == 1

    def test_create_dashboard_table(self, ssh_configs):
        """Test creating dashboard table with metrics."""
        metrics = [
            VMMetrics(
                vm_name="10.0.0.1",
                success=True,
                load_avg=(0.5, 0.6, 0.7),
                cpu_percent=10.5,
                memory_used_mb=1000,
                memory_total_mb=4000,
                memory_percent=25.0,
                top_processes=[
                    {"pid": "123", "user": "root", "cpu": "5.2", "mem": "0.3", "command": "python"}
                ],
            ),
            VMMetrics(
                vm_name="10.0.0.2",
                success=False,
                load_avg=None,
                cpu_percent=None,
                memory_used_mb=None,
                memory_total_mb=None,
                memory_percent=None,
                top_processes=None,
                error_message="Connection refused",
            ),
        ]

        executor = DistributedTopExecutor(ssh_configs=ssh_configs, interval=10)
        table = executor._create_dashboard_table(metrics)

        assert table.title == "Distributed VM Metrics (updates every 10s)"
        assert len(table.columns) == 6  # VM, Status, Load, CPU, Memory, Top Process

    @patch("azlin.distributed_top.subprocess.run")
    @patch("azlin.distributed_top.time.sleep")
    def test_run_dashboard_with_iterations(
        self, mock_sleep, mock_run, sample_metrics_output, ssh_configs
    ):
        """Test running dashboard for a fixed number of iterations."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = sample_metrics_output
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = DistributedTopExecutor(ssh_configs=ssh_configs, interval=1)

        # Run for 2 iterations
        executor.run_dashboard(iterations=2)

        # Should collect metrics twice
        assert mock_run.call_count == 4  # 2 VMs * 2 iterations

        # Should sleep once (between iterations)
        assert mock_sleep.call_count == 1

    @patch("azlin.distributed_top.subprocess.run")
    @patch("azlin.distributed_top.time.sleep")
    def test_run_dashboard_keyboard_interrupt(
        self, mock_sleep, mock_run, sample_metrics_output, ssh_configs
    ):
        """Test dashboard handles Ctrl+C gracefully."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = sample_metrics_output
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        # Simulate Ctrl+C after first iteration
        mock_sleep.side_effect = KeyboardInterrupt()

        executor = DistributedTopExecutor(ssh_configs=ssh_configs, interval=1)

        # Should not raise, should exit gracefully
        executor.run_dashboard()

        # Should have collected metrics at least once
        assert mock_run.call_count >= 2  # 2 VMs


class TestVMMetrics:
    """Tests for VMMetrics dataclass."""

    def test_vm_metrics_creation(self):
        """Test creating VMMetrics object."""
        metrics = VMMetrics(
            vm_name="test-vm",
            success=True,
            load_avg=(1.0, 1.5, 2.0),
            cpu_percent=50.0,
            memory_used_mb=2000,
            memory_total_mb=4000,
            memory_percent=50.0,
            top_processes=[{"pid": "123", "command": "test"}],
            timestamp=1.5,
        )

        assert metrics.vm_name == "test-vm"
        assert metrics.success
        assert metrics.load_avg == (1.0, 1.5, 2.0)
        assert metrics.cpu_percent == 50.0
        assert metrics.timestamp == 1.5

    def test_vm_metrics_failure(self):
        """Test creating VMMetrics for failed collection."""
        metrics = VMMetrics(
            vm_name="test-vm",
            success=False,
            load_avg=None,
            cpu_percent=None,
            memory_used_mb=None,
            memory_total_mb=None,
            memory_percent=None,
            top_processes=None,
            error_message="Connection timeout",
        )

        assert not metrics.success
        assert metrics.error_message == "Connection timeout"
        assert metrics.load_avg is None
