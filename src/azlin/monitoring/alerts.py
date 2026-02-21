"""Alert engine module for rule evaluation and notifications.

Philosophy:
- Single responsibility: Evaluate alert rules and send notifications
- Security-first: Sanitize errors, secrets from keyring/env only
- Robust: Retry failed notifications with exponential backoff
- Configurable: YAML-based rules configuration

Public API (the "studs"):
    AlertEngine: Main alert evaluation and notification engine
    AlertRule: Alert rule definition
    Alert: Triggered alert data model
    AlertSeverity: Alert severity levels (info, warning, critical)
"""

import contextlib
import os
import re
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path

import requests
import yaml

from azlin.monitoring.collector import VMMetric


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """Alert rule definition.

    Defines conditions that trigger alerts and how to notify.
    """

    name: str
    metric: str
    threshold: float
    comparison: str  # ">", "<", ">=", "<=", "=="
    severity: AlertSeverity
    enabled: bool = True
    notification_channels: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate rule after initialization."""
        # Validate comparison operator
        valid_ops = [">", "<", ">=", "<=", "=="]
        if self.comparison not in valid_ops:
            raise ValueError(
                f"Invalid comparison operator: {self.comparison}. Must be one of {valid_ops}"
            )

        # Validate metric name (alphanumeric + underscore only)
        if not re.match(r"^[a-zA-Z0-9_]+$", self.metric):
            raise ValueError(
                f"Invalid metric name: {self.metric}. Only alphanumeric and underscore allowed."
            )

        # Validate threshold range for percentage metrics
        if "percent" in self.metric and not 0.0 <= self.threshold <= 100.0:
            raise ValueError(
                f"Invalid threshold for percentage metric: {self.threshold}. Must be 0-100."
            )


@dataclass
class Alert:
    """Triggered alert data model."""

    rule_name: str
    vm_name: str
    metric: str
    actual_value: float
    threshold: float
    severity: AlertSeverity
    timestamp: datetime
    message: str


class AlertEngine:
    """Alert evaluation and notification engine.

    Evaluates alert rules against metrics and sends notifications
    via configured channels (email, Slack, webhooks).
    """

    def __init__(self, rules_config: Path | None = None) -> None:
        """Initialize alert engine.

        Args:
            rules_config: Path to YAML rules configuration file
        """
        self.rules_config = rules_config or Path.home() / ".azlin" / "alert_rules.yaml"

        # Create default config if missing
        if not self.rules_config.exists():
            self._create_default_config()

        # Alert suppression tracking (rule_name + vm_name -> last_alert_time)
        self._alert_history: dict[str, datetime] = {}

        # Suppression period (15 minutes)
        self._suppression_period = timedelta(minutes=15)

    def _create_default_config(self) -> None:
        """Create default alert rules configuration."""
        default_config = {
            "rules": [
                {
                    "name": "high_cpu",
                    "metric": "cpu_percent",
                    "threshold": 80.0,
                    "comparison": ">",
                    "severity": "warning",
                    "enabled": True,
                    "notification_channels": ["email"],
                },
                {
                    "name": "critical_memory",
                    "metric": "memory_percent",
                    "threshold": 95.0,
                    "comparison": ">",
                    "severity": "critical",
                    "enabled": True,
                    "notification_channels": ["email"],
                },
                {
                    "name": "high_memory",
                    "metric": "memory_percent",
                    "threshold": 85.0,
                    "comparison": ">",
                    "severity": "warning",
                    "enabled": True,
                    "notification_channels": ["email"],
                },
            ],
            "notification_config": {
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.gmail.com",
                    "smtp_port": 587,
                    "from_address": "alerts@example.com",
                    "to_addresses": ["admin@example.com"],
                },
                "slack": {
                    "enabled": False,
                    "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                },
            },
        }

        self.rules_config.parent.mkdir(parents=True, exist_ok=True)
        with open(self.rules_config, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)

    def load_rules(self) -> list[AlertRule]:
        """Load alert rules from configuration file.

        Returns:
            List of AlertRule instances

        Raises:
            ValueError: If rules configuration is invalid
        """
        try:
            with open(self.rules_config) as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}") from e

        rules = []
        for rule_data in config.get("rules", []):
            try:
                # Convert severity string to enum
                severity_str = rule_data.get("severity", "warning")
                severity = AlertSeverity(severity_str)

                rule = AlertRule(
                    name=rule_data["name"],
                    metric=rule_data["metric"],
                    threshold=float(rule_data["threshold"]),
                    comparison=rule_data["comparison"],
                    severity=severity,
                    enabled=rule_data.get("enabled", True),
                    notification_channels=rule_data.get("notification_channels", []),
                )
                rules.append(rule)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid rule configuration: {e}") from e

        return rules

    def _evaluate_condition(self, value: float, threshold: float, comparison: str) -> bool:
        """Evaluate alert condition.

        Args:
            value: Actual metric value
            threshold: Threshold value
            comparison: Comparison operator

        Returns:
            True if condition is met, False otherwise
        """
        if comparison == ">":
            return value > threshold
        if comparison == "<":
            return value < threshold
        if comparison == ">=":
            return value >= threshold
        if comparison == "<=":
            return value <= threshold
        if comparison == "==":
            return value == threshold
        return False

    def _is_suppressed(self, rule_name: str, vm_name: str) -> bool:
        """Check if alert is suppressed (recently triggered).

        Args:
            rule_name: Name of alert rule
            vm_name: Name of VM

        Returns:
            True if alert should be suppressed, False otherwise
        """
        key = f"{rule_name}:{vm_name}"
        last_alert = self._alert_history.get(key)

        if last_alert is None:
            return False

        time_since_last = datetime.now() - last_alert
        return time_since_last < self._suppression_period

    def _record_alert(self, rule_name: str, vm_name: str) -> None:
        """Record alert firing time for suppression tracking.

        Args:
            rule_name: Name of alert rule
            vm_name: Name of VM
        """
        key = f"{rule_name}:{vm_name}"
        self._alert_history[key] = datetime.now()

    def evaluate_rules(self, metrics: list[VMMetric]) -> list[Alert]:
        """Evaluate alert rules against collected metrics.

        Args:
            metrics: List of VMMetric instances to evaluate

        Returns:
            List of triggered Alert instances
        """
        rules = self.load_rules()
        alerts = []

        for metric in metrics:
            # Skip failed metrics
            if not metric.success:
                continue

            for rule in rules:
                # Skip disabled rules
                if not rule.enabled:
                    continue

                # Get metric value
                metric_value = getattr(metric, rule.metric, None)
                if metric_value is None:
                    continue

                # Evaluate condition
                if self._evaluate_condition(metric_value, rule.threshold, rule.comparison):
                    # Check suppression
                    if self._is_suppressed(rule.name, metric.vm_name):
                        continue

                    # Create alert
                    message = (
                        f"Alert: {rule.name} triggered for VM {metric.vm_name}. "
                        f"{rule.metric} is {metric_value:.2f} "
                        f"(threshold: {rule.comparison} {rule.threshold})"
                    )

                    alert = Alert(
                        rule_name=rule.name,
                        vm_name=metric.vm_name,
                        metric=rule.metric,
                        actual_value=metric_value,
                        threshold=rule.threshold,
                        severity=rule.severity,
                        timestamp=datetime.now(),
                        message=message,
                    )

                    alerts.append(alert)

                    # Record alert for suppression
                    self._record_alert(rule.name, metric.vm_name)

        return alerts

    def send_notification(self, alert: Alert, channel: str, max_retries: int = 3) -> bool:
        """Send alert notification via specified channel.

        Args:
            alert: Alert to send
            channel: Notification channel ('email', 'slack', 'webhook')
            max_retries: Maximum retry attempts

        Returns:
            True if notification sent successfully, False otherwise
        """
        retry_delay = 1.0  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                if channel == "email":
                    return self._send_email_notification(alert)
                if channel == "slack":
                    return self._send_slack_notification(alert)
                if channel == "webhook":
                    return self._send_webhook_notification(alert)
                return False

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    return False

        return False

    def _send_email_notification(self, alert: Alert) -> bool:
        """Send email notification via SMTP.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        # Load config
        with open(self.rules_config) as f:
            config = yaml.safe_load(f)

        email_config = config.get("notification_config", {}).get("email", {})

        # Get SMTP password from environment (never from config file)
        smtp_password = os.environ.get("AZLIN_SMTP_PASSWORD", "")

        # Create message
        msg = MIMEText(alert.message)
        msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.rule_name}"
        msg["From"] = email_config.get("from_address", "alerts@example.com")
        msg["To"] = ", ".join(email_config.get("to_addresses", []))

        # Send via SMTP (let exceptions propagate for retry logic)
        smtp = smtplib.SMTP(
            email_config.get("smtp_host", "smtp.gmail.com"),
            email_config.get("smtp_port", 587),
        )
        try:
            smtp.starttls()  # Use TLS encryption
            if smtp_password:
                smtp.login(msg["From"], smtp_password)
            smtp.send_message(msg)
            return True
        finally:
            with contextlib.suppress(Exception):
                smtp.quit()

    def _send_slack_notification(self, alert: Alert) -> bool:
        """Send Slack notification via webhook.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        # Load config
        with open(self.rules_config) as f:
            config = yaml.safe_load(f)

        slack_config = config.get("notification_config", {}).get("slack", {})

        webhook_url = slack_config.get("webhook_url")
        if not webhook_url:
            return False

        # Create Slack message payload
        payload = {
            "text": f"*{alert.severity.value.upper()}*: {alert.rule_name}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": alert.message,
                    },
                }
            ],
        }

        # Send webhook request (raise on non-200 for retry logic)
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code != 200:
            raise requests.HTTPError(f"Slack webhook returned {response.status_code}")
        return True

    def _send_webhook_notification(self, alert: Alert) -> bool:
        """Send webhook notification.

        Args:
            alert: Alert to send

        Returns:
            True if sent successfully, False otherwise
        """
        # Get webhook token from environment
        webhook_token = os.environ.get("WEBHOOK_TOKEN", "")
        webhook_url = os.environ.get("WEBHOOK_URL", "https://webhook.example.com/alert")

        if not webhook_url:
            return False

        headers = {}
        if webhook_token:
            headers["Authorization"] = f"Bearer {webhook_token}"

        payload = {
            "alert": {
                "rule_name": alert.rule_name,
                "vm_name": alert.vm_name,
                "metric": alert.metric,
                "actual_value": alert.actual_value,
                "threshold": alert.threshold,
                "severity": alert.severity.value,
                "timestamp": alert.timestamp.isoformat(),
                "message": alert.message,
            }
        }

        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        if response.status_code != 200:
            raise requests.HTTPError(f"Webhook returned {response.status_code}")
        return True


__all__ = ["Alert", "AlertEngine", "AlertRule", "AlertSeverity"]
