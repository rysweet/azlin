"""Monitoring module for Azure VM metrics collection and alerting.

This module provides comprehensive monitoring capabilities for Azure VMs:
- Metrics storage (SQLite with retention policies)
- Azure Monitor API integration for metrics collection
- Alert rules engine with notification support
- Dashboard visualization

Public API:
    MetricsStorage: SQLite-based metrics persistence
    MetricsCollector: Azure Monitor API client
    AlertEngine: Alert evaluation and notification
    VMMetric: Metric data model
    Alert: Alert data model
    AlertRule: Alert rule definition
    AlertSeverity: Alert severity levels
"""

from azlin.monitoring.alerts import Alert, AlertEngine, AlertRule, AlertSeverity
from azlin.monitoring.collector import MetricsCollector, VMMetric
from azlin.monitoring.storage import MetricsStorage

__all__ = [
    "Alert",
    "AlertEngine",
    "AlertRule",
    "AlertSeverity",
    "MetricsCollector",
    "MetricsStorage",
    "VMMetric",
]
