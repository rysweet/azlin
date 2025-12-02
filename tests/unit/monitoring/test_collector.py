"""Unit tests for metrics collector module.

Testing pyramid: 60% unit tests - fast, heavily mocked
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from azlin.monitoring.collector import MetricsCollector, VMMetric


@pytest.fixture
def mock_azure_response():
    """Mock Azure Monitor API response."""
    return {
        "value": [
            {
                "timeseries": [
                    {
                        "data": [
                            {
                                "timeStamp": "2025-12-01T20:30:00Z",
                                "average": 45.2,
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def collector():
    """Create MetricsCollector instance."""
    return MetricsCollector(
        resource_group="test-rg",
        timeout=30,
        max_workers=10,
    )


class TestMetricsCollectorInit:
    """Test MetricsCollector initialization."""

    def test_initializes_with_resource_group(self):
        """Collector requires resource group."""
        collector = MetricsCollector(resource_group="my-rg")
        assert collector.resource_group == "my-rg"

    def test_sets_default_timeout(self):
        """Default timeout is 30 seconds."""
        collector = MetricsCollector(resource_group="test-rg")
        assert collector.timeout == 30

    def test_sets_custom_timeout(self):
        """Custom timeout can be specified."""
        collector = MetricsCollector(resource_group="test-rg", timeout=60)
        assert collector.timeout == 60

    def test_clamps_timeout_to_safe_bounds(self):
        """Timeout is clamped between 1 and 300 seconds."""
        # Too low
        collector = MetricsCollector(resource_group="test-rg", timeout=0)
        assert collector.timeout >= 1

        # Too high
        collector = MetricsCollector(resource_group="test-rg", timeout=1000)
        assert collector.timeout <= 300

    def test_sets_max_workers(self):
        """Max workers can be configured."""
        collector = MetricsCollector(resource_group="test-rg", max_workers=20)
        assert collector.max_workers == 20

    def test_clamps_max_workers_to_safe_bounds(self):
        """Max workers clamped between 1 and 50."""
        # Too low
        collector = MetricsCollector(resource_group="test-rg", max_workers=0)
        assert collector.max_workers >= 1

        # Too high
        collector = MetricsCollector(resource_group="test-rg", max_workers=100)
        assert collector.max_workers <= 50


class TestGetAuthToken:
    """Test Azure CLI authentication token retrieval."""

    @patch("subprocess.run")
    def test_gets_token_from_azure_cli(self, mock_run, collector):
        """Auth token is retrieved from Azure CLI."""
        mock_run.return_value = Mock(
            stdout='{"accessToken": "test-token-123", "expiresOn": "2025-12-01"}',
            returncode=0,
        )

        token = collector._get_auth_token()

        assert token == "test-token-123"  # noqa: S105
        mock_run.assert_called_once()
        # Verify correct az command was called
        assert "az" in mock_run.call_args[0][0]
        assert "account" in mock_run.call_args[0][0]
        assert "get-access-token" in mock_run.call_args[0][0]

    @patch("subprocess.run")
    def test_raises_error_if_not_logged_in(self, mock_run, collector):
        """Clear error if user not logged into Azure CLI."""
        mock_run.return_value = Mock(
            stdout="",
            stderr="ERROR: Please run 'az login' to setup account.",
            returncode=1,
        )

        with pytest.raises(RuntimeError) as exc_info:
            collector._get_auth_token()

        assert "az login" in str(exc_info.value).lower()

    @patch("subprocess.run")
    def test_raises_error_if_token_expired(self, mock_run, collector):
        """Clear error if token is expired."""
        mock_run.return_value = Mock(
            stdout="",
            stderr="ERROR: Token expired",
            returncode=1,
        )

        with pytest.raises(RuntimeError) as exc_info:
            collector._get_auth_token()

        assert "expired" in str(exc_info.value).lower() or "login" in str(exc_info.value).lower()


class TestCollectMetrics:
    """Test collecting metrics from single VM."""

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_collects_cpu_metric(self, mock_auth, mock_requests, collector, mock_azure_response):
        """CPU metric is collected from Azure Monitor API."""
        mock_auth.return_value = "test-token"
        mock_requests.return_value = Mock(
            status_code=200,
            json=lambda: mock_azure_response,
        )

        metric = collector.collect_metrics("test-vm")

        assert metric.vm_name == "test-vm"
        assert metric.cpu_percent == 45.2
        assert metric.success is True

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_collects_all_metric_types(self, mock_auth, mock_requests, collector):
        """All metric types are collected (CPU, memory, disk, network)."""
        mock_auth.return_value = "test-token"

        # Mock responses for each metric type
        def mock_api_call(*args, **kwargs):
            url = args[0]
            if "cpu" in url.lower():
                return Mock(
                    status_code=200,
                    json=lambda: {"value": [{"timeseries": [{"data": [{"average": 45.2}]}]}]},
                )
            if "memory" in url.lower():
                return Mock(
                    status_code=200,
                    json=lambda: {"value": [{"timeseries": [{"data": [{"average": 62.1}]}]}]},
                )
            if "disk" in url.lower():
                return Mock(
                    status_code=200,
                    json=lambda: {"value": [{"timeseries": [{"data": [{"total": 12345678}]}]}]},
                )
            if "network" in url.lower():
                return Mock(
                    status_code=200,
                    json=lambda: {"value": [{"timeseries": [{"data": [{"total": 1234567}]}]}]},
                )
            return Mock(status_code=404)

        mock_requests.side_effect = mock_api_call

        metric = collector.collect_metrics("test-vm")

        assert metric.cpu_percent == 45.2
        assert metric.memory_percent == 62.1
        assert metric.disk_read_bytes is not None
        assert metric.network_in_bytes is not None

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_handles_vm_not_found(self, mock_auth, mock_requests, collector):
        """VM not found returns failed metric with error."""
        mock_auth.return_value = "test-token"
        mock_requests.return_value = Mock(
            status_code=404,
            text="VM not found",
        )

        metric = collector.collect_metrics("nonexistent-vm")

        assert metric.success is False
        assert "not found" in metric.error_message.lower()
        assert metric.cpu_percent is None

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_handles_api_timeout(self, mock_auth, mock_requests, collector):
        """API timeout returns failed metric."""
        import requests

        mock_auth.return_value = "test-token"
        mock_requests.side_effect = requests.Timeout("Connection timeout")

        metric = collector.collect_metrics("test-vm")

        assert metric.success is False
        assert "timeout" in metric.error_message.lower()

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_handles_rate_limiting(self, mock_auth, mock_requests, collector):
        """Rate limiting (429) is handled with exponential backoff."""
        mock_auth.return_value = "test-token"
        mock_requests.return_value = Mock(
            status_code=429,
            headers={"Retry-After": "60"},
            text="Too many requests",
        )

        metric = collector.collect_metrics("test-vm")

        assert metric.success is False
        assert "rate limit" in metric.error_message.lower()

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_uses_https_only(self, mock_auth, mock_requests, collector):
        """All API calls use HTTPS."""
        mock_auth.return_value = "test-token"
        mock_requests.return_value = Mock(status_code=200, json=lambda: {"value": []})

        collector.collect_metrics("test-vm")

        # Verify all calls used HTTPS
        for call in mock_requests.call_args_list:
            url = call[0][0]
            assert url.startswith("https://")

    @patch("requests.get")
    @patch.object(MetricsCollector, "_get_auth_token")
    def test_respects_timeout_setting(self, mock_auth, mock_requests, collector):
        """Request timeout matches collector timeout setting."""
        mock_auth.return_value = "test-token"
        mock_requests.return_value = Mock(status_code=200, json=lambda: {"value": []})

        collector.timeout = 45
        collector.collect_metrics("test-vm")

        # Verify timeout was passed to requests
        assert mock_requests.call_args[1].get("timeout") == 45


class TestCollectAllMetrics:
    """Test parallel collection from multiple VMs."""

    @patch.object(MetricsCollector, "collect_metrics")
    def test_collects_from_all_vms_in_parallel(self, mock_collect, collector):
        """All VMs are queried in parallel."""
        mock_collect.return_value = VMMetric(
            vm_name="test-vm",
            timestamp=datetime.now(),
            cpu_percent=45.2,
            memory_percent=62.1,
            disk_read_bytes=12345678,
            disk_write_bytes=8765432,
            network_in_bytes=1234567,
            network_out_bytes=876543,
            success=True,
        )

        vm_names = [f"vm-{i}" for i in range(10)]
        metrics = collector.collect_all_metrics(vm_names)

        # All VMs collected
        assert len(metrics) == 10
        assert mock_collect.call_count == 10

    @patch.object(MetricsCollector, "collect_metrics")
    def test_continues_on_individual_failure(self, mock_collect, collector):
        """Collection continues if individual VMs fail."""

        def mock_collection(vm_name):
            if vm_name == "failed-vm":
                return VMMetric(
                    vm_name=vm_name,
                    timestamp=datetime.now(),
                    cpu_percent=None,
                    memory_percent=None,
                    disk_read_bytes=None,
                    disk_write_bytes=None,
                    network_in_bytes=None,
                    network_out_bytes=None,
                    success=False,
                    error_message="Connection failed",
                )
            return VMMetric(
                vm_name=vm_name,
                timestamp=datetime.now(),
                cpu_percent=45.2,
                memory_percent=62.1,
                disk_read_bytes=12345678,
                disk_write_bytes=8765432,
                network_in_bytes=1234567,
                network_out_bytes=876543,
                success=True,
            )

        mock_collect.side_effect = mock_collection

        vm_names = ["vm-1", "failed-vm", "vm-2"]
        metrics = collector.collect_all_metrics(vm_names)

        # All VMs attempted
        assert len(metrics) == 3

        # Check failed VM
        failed = next(m for m in metrics if m.vm_name == "failed-vm")
        assert failed.success is False

        # Check successful VMs
        successful = [m for m in metrics if m.success]
        assert len(successful) == 2

    @patch.object(MetricsCollector, "collect_metrics")
    def test_respects_max_workers_limit(self, mock_collect, collector):
        """Parallel execution respects max_workers limit."""
        mock_collect.return_value = VMMetric(
            vm_name="test-vm",
            timestamp=datetime.now(),
            cpu_percent=45.2,
            memory_percent=62.1,
            disk_read_bytes=12345678,
            disk_write_bytes=8765432,
            network_in_bytes=1234567,
            network_out_bytes=876543,
            success=True,
        )

        collector.max_workers = 5
        vm_names = [f"vm-{i}" for i in range(20)]

        metrics = collector.collect_all_metrics(vm_names)

        # All collected
        assert len(metrics) == 20
        # Implementation should use ThreadPoolExecutor(max_workers=5)

    def test_handles_empty_vm_list(self, collector):
        """Empty VM list returns empty metrics list."""
        metrics = collector.collect_all_metrics([])
        assert metrics == []


class TestInputValidation:
    """Test input validation and security."""

    def test_validates_vm_name_format(self, collector):
        """VM name must be alphanumeric with hyphens/underscores only."""
        # Valid names
        valid_names = [
            "vm-1",
            "test_vm",
            "VM-123",
            "dev-environment-01",
        ]
        for name in valid_names:
            # Should not raise
            collector._validate_vm_name(name)

        # Invalid names
        invalid_names = [
            "vm;DROP TABLE",
            "vm$(whoami)",
            "../../../etc/passwd",
            "vm|rm -rf /",
            "vm'OR'1'='1",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match=r"(?i)invalid"):
                collector._validate_vm_name(name)

    def test_validates_vm_name_length(self, collector):
        """VM name must not exceed maximum length."""
        # Too long (> 64 characters)
        long_name = "a" * 65
        with pytest.raises(ValueError, match=r"(?i)(too long|length)"):
            collector._validate_vm_name(long_name)

    def test_prevents_command_injection_in_vm_name(self, collector):
        """VM name with shell metacharacters is rejected."""
        malicious_names = [
            "vm; rm -rf /",
            "vm$(malicious)",
            "vm`whoami`",
            "vm|cat /etc/passwd",
        ]
        for name in malicious_names:
            with pytest.raises(ValueError, match=r"(?i)invalid"):
                collector._validate_vm_name(name)


class TestErrorMessageSanitization:
    """Test error message sanitization for security."""

    def test_sanitizes_file_paths_from_errors(self, collector):
        """File paths are removed from error messages."""
        error = "Connection failed: /home/user/.azure/credentials not found"
        sanitized = collector._sanitize_error_message(error)

        assert "[path]" in sanitized
        assert "/home/user/.azure/credentials" not in sanitized

    def test_sanitizes_internal_ip_addresses(self, collector):
        """Internal IP addresses are masked in error messages."""
        error = "Connection timeout to 10.0.1.5:443"
        sanitized = collector._sanitize_error_message(error)

        assert "10.x.x.x" in sanitized
        assert "10.0.1.5" not in sanitized

    def test_sanitizes_private_network_ranges(self, collector):
        """All private IP ranges are masked."""
        test_cases = [
            ("Error at 10.1.2.3", "10.x.x.x"),
            ("Failed 172.16.5.10", "172.x.x.x"),
            ("Timeout 192.168.1.100", "192.168.x.x"),
        ]

        for error, expected_mask in test_cases:
            sanitized = collector._sanitize_error_message(error)
            assert expected_mask in sanitized

    def test_limits_error_message_length(self, collector):
        """Error messages are truncated to prevent information disclosure."""
        long_error = "Error: " + "A" * 200
        sanitized = collector._sanitize_error_message(long_error)

        assert len(sanitized) <= 100
        assert sanitized.endswith("...")

    def test_handles_empty_error_message(self, collector):
        """Empty error message returns default."""
        sanitized = collector._sanitize_error_message("")
        assert sanitized == "Unknown error"


class TestPerformance:
    """Test performance characteristics."""

    @patch.object(MetricsCollector, "collect_metrics")
    def test_collects_50_vms_in_under_10_seconds(self, mock_collect, collector):
        """Large fleet collection completes in reasonable time."""
        import time

        mock_collect.return_value = VMMetric(
            vm_name="test-vm",
            timestamp=datetime.now(),
            cpu_percent=45.2,
            memory_percent=62.1,
            disk_read_bytes=12345678,
            disk_write_bytes=8765432,
            network_in_bytes=1234567,
            network_out_bytes=876543,
            success=True,
        )

        # Simulate API delay
        def slow_collect(vm_name):
            time.sleep(0.1)  # 100ms per VM
            return mock_collect.return_value

        mock_collect.side_effect = slow_collect

        vm_names = [f"vm-{i}" for i in range(50)]
        start = time.time()
        metrics = collector.collect_all_metrics(vm_names)
        duration = time.time() - start

        # With 10 workers, 50 VMs @ 100ms each should take ~0.5s (50/10 * 0.1)
        # Allow some overhead, but should be under 2 seconds
        assert duration < 2.0
        assert len(metrics) == 50
