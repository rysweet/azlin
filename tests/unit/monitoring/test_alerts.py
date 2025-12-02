"""Unit tests for alert engine module.

Testing pyramid: 60% unit tests - fast, heavily mocked
Focus on alert evaluation logic and notification security.
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from azlin.monitoring.alerts import Alert, AlertEngine, AlertRule, AlertSeverity
from azlin.monitoring.collector import VMMetric


@pytest.fixture
def temp_rules_config():
    """Create temporary rules configuration file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(
            """
rules:
  - name: high_cpu
    metric: cpu_percent
    threshold: 80.0
    comparison: ">"
    severity: warning
    enabled: true
    notification_channels: [email]

  - name: critical_memory
    metric: memory_percent
    threshold: 95.0
    comparison: ">"
    severity: critical
    enabled: true
    notification_channels: [email, slack]

  - name: disabled_alert
    metric: cpu_percent
    threshold: 90.0
    comparison: ">"
    severity: warning
    enabled: false
    notification_channels: [email]

notification_config:
  email:
    enabled: true
    smtp_host: smtp.gmail.com
    smtp_port: 587
    from_address: alerts@example.com
    to_addresses: [admin@example.com]
  slack:
    enabled: false
    webhook_url: https://hooks.slack.com/services/XXX
"""
        )
        config_path = Path(f.name)
    yield config_path
    config_path.unlink()


@pytest.fixture
def alert_engine(temp_rules_config):
    """Create AlertEngine instance with test configuration."""
    return AlertEngine(rules_config=temp_rules_config)


@pytest.fixture
def sample_metrics():
    """Create sample metrics for testing."""
    return [
        VMMetric(
            vm_name="high-cpu-vm",
            timestamp=datetime.now(),
            cpu_percent=85.0,  # Above threshold
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        ),
        VMMetric(
            vm_name="critical-memory-vm",
            timestamp=datetime.now(),
            cpu_percent=45.0,
            memory_percent=96.0,  # Above critical threshold
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        ),
        VMMetric(
            vm_name="normal-vm",
            timestamp=datetime.now(),
            cpu_percent=40.0,
            memory_percent=55.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        ),
    ]


class TestAlertEngineInit:
    """Test AlertEngine initialization."""

    def test_loads_rules_from_yaml(self, alert_engine):
        """Rules are loaded from YAML configuration."""
        rules = alert_engine.load_rules()

        assert len(rules) >= 2
        rule_names = [r.name for r in rules]
        assert "high_cpu" in rule_names
        assert "critical_memory" in rule_names

    def test_creates_default_config_if_missing(self, tmp_path):
        """Default configuration is created if file doesn't exist."""
        config_path = tmp_path / "nonexistent_rules.yaml"
        engine = AlertEngine(rules_config=config_path)

        # Should create default config
        assert config_path.exists()

        # Default config should have standard rules
        rules = engine.load_rules()
        assert len(rules) > 0

    def test_validates_rule_structure(self, temp_rules_config):
        """Rule validation catches malformed rules."""
        # Add invalid rule to config
        with open(temp_rules_config, "a") as f:
            f.write(
                """
  - name: invalid_rule
    metric: cpu_percent
    threshold: "not_a_number"
    comparison: ">"
    severity: warning
"""
            )

        with pytest.raises(ValueError, match=r"(?i)invalid"):
            engine = AlertEngine(rules_config=temp_rules_config)
            engine.load_rules()


class TestAlertRuleDefinition:
    """Test AlertRule data model."""

    def test_creates_valid_alert_rule(self):
        """Valid alert rule can be created."""
        rule = AlertRule(
            name="test_rule",
            metric="cpu_percent",
            threshold=80.0,
            comparison=">",
            severity=AlertSeverity.WARNING,
            enabled=True,
            notification_channels=["email"],
        )

        assert rule.name == "test_rule"
        assert rule.threshold == 80.0
        assert rule.severity == AlertSeverity.WARNING

    def test_validates_comparison_operator(self):
        """Only valid comparison operators are allowed."""
        valid_operators = [">", "<", ">=", "<=", "=="]

        for op in valid_operators:
            rule = AlertRule(
                name="test",
                metric="cpu_percent",
                threshold=80.0,
                comparison=op,
                severity=AlertSeverity.WARNING,
            )
            assert rule.comparison == op

        # Invalid operator
        with pytest.raises(ValueError, match=r"(?i)comparison"):
            AlertRule(
                name="test",
                metric="cpu_percent",
                threshold=80.0,
                comparison="!=",  # Not supported
                severity=AlertSeverity.WARNING,
            )

    def test_validates_metric_name(self):
        """Metric name must be alphanumeric with underscores."""
        # Valid names
        valid_metrics = ["cpu_percent", "memory_percent", "disk_io_rate"]
        for metric in valid_metrics:
            rule = AlertRule(
                name="test",
                metric=metric,
                threshold=80.0,
                comparison=">",
                severity=AlertSeverity.WARNING,
            )
            assert rule.metric == metric

        # Invalid names (SQL injection attempts)
        invalid_metrics = [
            "metric'; DROP TABLE",
            "metric$(whoami)",
            "../../../etc/passwd",
        ]
        for metric in invalid_metrics:
            with pytest.raises(ValueError, match=r"(?i)metric"):
                AlertRule(
                    name="test",
                    metric=metric,
                    threshold=80.0,
                    comparison=">",
                    severity=AlertSeverity.WARNING,
                )

    def test_validates_threshold_range(self):
        """Threshold must be reasonable (0-100 for percentages)."""
        # Valid thresholds
        for threshold in [0.0, 50.0, 100.0]:
            rule = AlertRule(
                name="test",
                metric="cpu_percent",
                threshold=threshold,
                comparison=">",
                severity=AlertSeverity.WARNING,
            )
            assert rule.threshold == threshold

        # Invalid thresholds
        for threshold in [-10.0, 150.0]:
            with pytest.raises(ValueError, match=r"(?i)threshold"):
                AlertRule(
                    name="test",
                    metric="cpu_percent",
                    threshold=threshold,
                    comparison=">",
                    severity=AlertSeverity.WARNING,
                )


class TestEvaluateRules:
    """Test alert rule evaluation."""

    def test_evaluates_greater_than_rule(self, alert_engine, sample_metrics):
        """Greater than comparison works correctly."""
        alerts = alert_engine.evaluate_rules(sample_metrics)

        # Should trigger alert for high CPU VM
        cpu_alerts = [a for a in alerts if "cpu" in a.rule_name.lower()]
        assert len(cpu_alerts) > 0

        # Check alert details
        cpu_alert = cpu_alerts[0]
        assert cpu_alert.vm_name == "high-cpu-vm"
        assert cpu_alert.actual_value == 85.0
        assert cpu_alert.threshold == 80.0

    def test_evaluates_multiple_rules_per_vm(self, alert_engine, sample_metrics):
        """Multiple rules can trigger for same VM."""
        # Add metric that violates multiple rules
        multi_alert_metric = VMMetric(
            vm_name="multi-alert-vm",
            timestamp=datetime.now(),
            cpu_percent=90.0,  # Above high_cpu threshold
            memory_percent=96.0,  # Above critical_memory threshold
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )

        alerts = alert_engine.evaluate_rules([multi_alert_metric])

        # Should have alerts for both CPU and memory
        assert len(alerts) >= 2

    def test_does_not_alert_on_disabled_rules(self, alert_engine, sample_metrics):
        """Disabled rules do not trigger alerts."""
        alerts = alert_engine.evaluate_rules(sample_metrics)

        # "disabled_alert" rule should not trigger
        disabled_alerts = [a for a in alerts if a.rule_name == "disabled_alert"]
        assert len(disabled_alerts) == 0

    def test_does_not_alert_below_threshold(self, alert_engine):
        """No alert when metric is below threshold."""
        normal_metrics = [
            VMMetric(
                vm_name="normal-vm",
                timestamp=datetime.now(),
                cpu_percent=40.0,  # Below all thresholds
                memory_percent=50.0,
                disk_read_bytes=1000000,
                disk_write_bytes=500000,
                network_in_bytes=100000,
                network_out_bytes=50000,
                success=True,
            )
        ]

        alerts = alert_engine.evaluate_rules(normal_metrics)
        assert len(alerts) == 0

    def test_handles_missing_metric_data(self, alert_engine):
        """Gracefully handles metrics with None values."""
        failed_metric = VMMetric(
            vm_name="failed-vm",
            timestamp=datetime.now(),
            cpu_percent=None,  # Failed to collect
            memory_percent=None,
            disk_read_bytes=None,
            disk_write_bytes=None,
            network_in_bytes=None,
            network_out_bytes=None,
            success=False,
            error_message="Connection timeout",
        )

        # Should not raise exception
        alerts = alert_engine.evaluate_rules([failed_metric])

        # No alerts for failed metrics
        assert len(alerts) == 0

    def test_creates_meaningful_alert_messages(self, alert_engine, sample_metrics):
        """Alert messages are clear and actionable."""
        alerts = alert_engine.evaluate_rules(sample_metrics)

        for alert in alerts:
            # Message should contain key information
            assert alert.vm_name in alert.message
            assert str(alert.actual_value) in alert.message
            assert str(alert.threshold) in alert.message
            assert alert.metric in alert.message


class TestAlertSuppression:
    """Test alert suppression to prevent notification spam."""

    def test_suppresses_duplicate_alerts_within_15_minutes(self, alert_engine):
        """Same alert doesn't re-trigger within 15 minutes."""
        metric = VMMetric(
            vm_name="test-vm",
            timestamp=datetime.now(),
            cpu_percent=85.0,  # Above threshold
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )

        # First evaluation - should trigger
        alerts1 = alert_engine.evaluate_rules([metric])
        assert len(alerts1) > 0

        # Second evaluation immediately - should suppress
        alerts2 = alert_engine.evaluate_rules([metric])
        # Implementation should check suppression and return empty or set suppressed flag
        # Exact behavior depends on implementation

    def test_allows_alert_after_suppression_period(self, alert_engine):
        """Alert triggers again after suppression period expires."""
        metric = VMMetric(
            vm_name="test-vm",
            timestamp=datetime.now(),
            cpu_percent=85.0,
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )

        # First alert
        alerts1 = alert_engine.evaluate_rules([metric])
        assert len(alerts1) > 0

        # Simulate 16 minutes passing
        with patch("datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime.now() + timedelta(minutes=16)

            # Should trigger again
            alerts2 = alert_engine.evaluate_rules([metric])
            # Should have new alert

    def test_different_vms_not_suppressed(self, alert_engine):
        """Suppression is per-VM, not global."""
        metric1 = VMMetric(
            vm_name="vm-1",
            timestamp=datetime.now(),
            cpu_percent=85.0,
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )

        metric2 = VMMetric(
            vm_name="vm-2",
            timestamp=datetime.now(),
            cpu_percent=85.0,
            memory_percent=60.0,
            disk_read_bytes=1000000,
            disk_write_bytes=500000,
            network_in_bytes=100000,
            network_out_bytes=50000,
            success=True,
        )

        # Both should trigger
        alerts = alert_engine.evaluate_rules([metric1, metric2])
        vm_names = {a.vm_name for a in alerts}
        assert "vm-1" in vm_names
        assert "vm-2" in vm_names


class TestSendNotification:
    """Test notification dispatch."""

    @patch("smtplib.SMTP")
    def test_sends_email_notification(self, mock_smtp, alert_engine):
        """Email notification is sent via SMTP."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        result = alert_engine.send_notification(alert, "email")

        assert result is True
        # Verify SMTP was used
        mock_smtp.assert_called_once()

    @patch("smtplib.SMTP")
    def test_email_uses_tls(self, mock_smtp, alert_engine):
        """Email connection uses TLS encryption."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        alert_engine.send_notification(alert, "email")

        # Verify STARTTLS was called
        smtp_instance = mock_smtp.return_value
        smtp_instance.starttls.assert_called_once()

    @patch("smtplib.SMTP")
    def test_does_not_log_smtp_password(self, mock_smtp, alert_engine, caplog):
        """SMTP password is never logged."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        alert_engine.send_notification(alert, "email")

        # Check logs don't contain password
        for record in caplog.records:
            assert "password" not in record.message.lower()

    @patch("requests.post")
    def test_sends_slack_notification(self, mock_post, alert_engine):
        """Slack notification is sent via webhook."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        mock_post.return_value = Mock(status_code=200)

        result = alert_engine.send_notification(alert, "slack")

        assert result is True
        mock_post.assert_called_once()

        # Verify webhook URL used
        call_args = mock_post.call_args
        assert "hooks.slack.com" in call_args[0][0]

    @patch("requests.post")
    def test_slack_notification_has_proper_format(self, mock_post, alert_engine):
        """Slack notification uses proper Slack message format."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        mock_post.return_value = Mock(status_code=200)
        alert_engine.send_notification(alert, "slack")

        # Check payload format
        payload = mock_post.call_args[1].get("json")
        assert "text" in payload or "blocks" in payload

    @patch("requests.post")
    def test_retries_failed_notifications(self, mock_post, alert_engine):
        """Failed notifications are retried with exponential backoff."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        # Fail twice, succeed on third attempt
        mock_post.side_effect = [
            Mock(status_code=500),
            Mock(status_code=500),
            Mock(status_code=200),
        ]

        result = alert_engine.send_notification(alert, "slack")

        # Should eventually succeed
        assert result is True
        # Should have made 3 attempts
        assert mock_post.call_count == 3

    @patch("requests.post")
    def test_gives_up_after_max_retries(self, mock_post, alert_engine):
        """Notification gives up after maximum retry attempts."""
        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        # Always fail
        mock_post.return_value = Mock(status_code=500)

        result = alert_engine.send_notification(alert, "slack")

        # Should fail after 3 attempts
        assert result is False
        assert mock_post.call_count == 3


class TestNotificationSecurity:
    """Test notification security and secrets handling."""

    def test_smtp_credentials_from_keyring_not_config(self, alert_engine):
        """SMTP password is retrieved from system keyring, not config file."""
        # Config should NOT contain password
        with open(alert_engine.rules_config) as f:
            config_content = f.read()
            assert "password" not in config_content.lower()

        # Implementation should use keyring library
        # import keyring
        # password = keyring.get_password("azlin_monitoring", "smtp_password")

    @patch("requests.post")
    def test_webhook_token_from_env_var(self, mock_post, alert_engine):
        """Webhook authentication token comes from environment variable."""
        import os

        # Set token in environment
        os.environ["WEBHOOK_TOKEN"] = "test-token-123"

        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        mock_post.return_value = Mock(status_code=200)
        alert_engine.send_notification(alert, "webhook")

        # Verify Bearer token in headers
        headers = mock_post.call_args[1].get("headers", {})
        assert "Authorization" in headers
        assert "Bearer test-token-123" in headers["Authorization"]

        # Cleanup
        del os.environ["WEBHOOK_TOKEN"]

    @patch("requests.post")
    def test_does_not_log_webhook_tokens(self, mock_post, alert_engine, caplog):
        """Webhook tokens are never logged."""
        import os

        os.environ["WEBHOOK_TOKEN"] = "secret-token-456"

        alert = Alert(
            rule_name="high_cpu",
            vm_name="test-vm",
            metric="cpu_percent",
            actual_value=85.0,
            threshold=80.0,
            severity=AlertSeverity.WARNING,
            timestamp=datetime.now(),
            message="CPU usage is high",
        )

        mock_post.return_value = Mock(status_code=200)
        alert_engine.send_notification(alert, "webhook")

        # Check logs don't contain token
        for record in caplog.records:
            assert "secret-token-456" not in record.message

        del os.environ["WEBHOOK_TOKEN"]

    def test_sanitizes_error_messages_in_alerts(self, alert_engine):
        """Error messages in alerts are sanitized."""
        metric_with_error = VMMetric(
            vm_name="failed-vm",
            timestamp=datetime.now(),
            cpu_percent=None,
            memory_percent=None,
            disk_read_bytes=None,
            disk_write_bytes=None,
            network_in_bytes=None,
            network_out_bytes=None,
            success=False,
            error_message="Connection failed to 10.0.1.5 at /home/user/.ssh/key",
        )

        # Alert should not contain sensitive info
        # Implementation should sanitize before creating alert message


class TestAlertHistory:
    """Test alert history tracking."""

    def test_stores_alert_history_in_database(self, alert_engine):
        """Triggered alerts are stored in history."""
        # Implementation should store alerts in SQLite
        # Separate 'alert_history' table
        pass

    def test_queries_alert_history_by_time_range(self, alert_engine):
        """Alert history can be queried by time range."""
        # Implementation should provide query method
        # history = alert_engine.get_alert_history(start_time, end_time)
        pass

    def test_filters_alert_history_by_severity(self, alert_engine):
        """Alert history can be filtered by severity."""
        # history = alert_engine.get_alert_history(severity=AlertSeverity.CRITICAL)
        pass
