# Enhanced Monitoring & Alerting - Architecture Specification

## Overview

This specification defines the architecture for comprehensive VM monitoring with real-time dashboards, proactive alerting, historical trend analysis, and resource utilization forecasting.

## Explicit User Requirements (CANNOT BE OPTIMIZED AWAY)

1. **Real-time dashboard** showing all VM metrics (live CPU/memory/disk/network for all VMs)
2. **Alert rules engine** with notifications (Slack/email/webhook, severity levels)
3. **Historical trend analysis** (store metrics for 7/30/90 days, generate charts)
4. **Resource utilization forecasting** (7/30 day predictions, identify VMs approaching limits)
5. **Integration framework** (Slack/email/webhook support, YAML/JSON config)

## Technical Decisions

- **Data Source**: Azure Monitor REST API with Azure CLI auth token
- **Storage**: SQLite for historical metrics (30+ days with hourly aggregation)
- **UI**: Rich/Textual terminal dashboard (CLI-first philosophy)
- **Collection Frequency**: 1-5 minutes (user-configurable)
- **Notifications**: Direct integration for Slack/email with retry logic

## Module Architecture

### 1. Metrics Collector Module (`src/azlin/monitoring/collector.py`)

**Purpose**: Collect VM metrics from Azure Monitor API

**Brick Specification**:
```python
"""Metrics collection from Azure Monitor API.

Philosophy:
- Single responsibility: metrics collection only
- Standard library + Azure CLI for auth
- Self-contained and regeneratable

Public API (the "studs"):
    MetricsCollector: Main collector class
    VMMetric: Metric data model
    collect_metrics(): Collect from single VM
    collect_all_metrics(): Parallel collection from multiple VMs
"""

@dataclass
class VMMetric:
    vm_name: str
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_read_bytes: int
    disk_write_bytes: int
    network_in_bytes: int
    network_out_bytes: int
    success: bool
    error_message: str | None = None

class MetricsCollector:
    """Collect VM metrics from Azure Monitor API."""

    def __init__(
        self,
        resource_group: str,
        timeout: int = 30,
        max_workers: int = 10,
    ):
        """Initialize metrics collector."""

    def collect_metrics(self, vm_name: str) -> VMMetric:
        """Collect metrics from single VM."""

    def collect_all_metrics(self, vm_names: list[str]) -> list[VMMetric]:
        """Collect metrics from multiple VMs in parallel."""
```

**Implementation Notes**:
- Use Azure CLI to get auth token: `az account get-access-token`
- Call Azure Monitor REST API: `https://management.azure.com/...`
- Metrics to collect: CPU percentage, memory percentage, disk I/O, network I/O
- Graceful degradation: Continue if individual VMs fail
- Parallel collection using ThreadPoolExecutor
- Timeout per VM: 30 seconds default

### 2. Storage Module (`src/azlin/monitoring/storage.py`)

**Purpose**: Store and retrieve historical metrics

**Brick Specification**:
```python
"""Historical metrics storage using SQLite.

Philosophy:
- Single responsibility: data persistence only
- Standard library (sqlite3)
- Self-contained and regeneratable

Public API (the "studs"):
    MetricsStorage: Main storage class
    store_metric(): Store single metric
    store_metrics(): Store multiple metrics
    query_metrics(): Retrieve metrics by time range
    aggregate_hourly(): Aggregate metrics by hour
    cleanup_old_data(): Remove data older than retention
"""

class MetricsStorage:
    """SQLite-based metrics storage with retention policies."""

    def __init__(
        self,
        db_path: Path = Path.home() / ".azlin" / "metrics.db",
        retention_days: int = 90,
    ):
        """Initialize storage with database path and retention."""

    def store_metric(self, metric: VMMetric) -> None:
        """Store single metric."""

    def store_metrics(self, metrics: list[VMMetric]) -> None:
        """Store multiple metrics in transaction."""

    def query_metrics(
        self,
        vm_name: str,
        start_time: datetime,
        end_time: datetime,
        aggregation: str = "raw",  # raw, hourly, daily
    ) -> list[VMMetric]:
        """Query metrics by time range."""

    def aggregate_hourly(self) -> None:
        """Aggregate old metrics to hourly averages."""

    def cleanup_old_data(self) -> int:
        """Remove metrics older than retention period. Returns count deleted."""
```

**Database Schema**:
```sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vm_name TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    cpu_percent REAL,
    memory_percent REAL,
    disk_read_bytes INTEGER,
    disk_write_bytes INTEGER,
    network_in_bytes INTEGER,
    network_out_bytes INTEGER,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    aggregation_level TEXT DEFAULT 'raw',  -- raw, hourly, daily
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vm_timestamp ON metrics(vm_name, timestamp);
CREATE INDEX idx_timestamp ON metrics(timestamp);
CREATE INDEX idx_aggregation ON metrics(aggregation_level, timestamp);
```

**Implementation Notes**:
- Store raw metrics for 7 days
- Aggregate to hourly after 7 days
- Aggregate to daily after 30 days
- Delete data older than 90 days
- Run cleanup/aggregation automatically on store_metrics()

### 3. Dashboard Module (`src/azlin/monitoring/dashboard.py`)

**Purpose**: Real-time metrics display using Rich/Textual

**Brick Specification**:
```python
"""Real-time monitoring dashboard using Rich.

Philosophy:
- Single responsibility: display only
- Rich library for terminal UI
- Self-contained and regeneratable

Public API (the "studs"):
    MonitoringDashboard: Main dashboard class
    run(): Launch interactive dashboard
    refresh(): Update metrics display
"""

class MonitoringDashboard:
    """Real-time VM monitoring dashboard."""

    def __init__(
        self,
        collector: MetricsCollector,
        storage: MetricsStorage,
        refresh_interval: int = 60,  # seconds
    ):
        """Initialize dashboard with collector and storage."""

    def run(self) -> None:
        """Launch interactive dashboard (blocking)."""

    def refresh(self) -> None:
        """Refresh metrics from all VMs."""

    def _render_table(self, metrics: list[VMMetric]) -> Table:
        """Render metrics as Rich table."""
```

**Display Layout**:
```
╭─ VM Monitoring Dashboard ─ Updated: 2025-12-01 20:30:15 ─────────────╮
│ VM Name       CPU%   Memory%   Disk R/W (MB/s)   Network I/O (MB/s)   │
├────────────────────────────────────────────────────────────────────────┤
│ dev-vm-01     45.2   62.1      12.3 / 8.5        1.2 / 0.8           │
│ dev-vm-02     78.9   89.2      45.1 / 23.4       5.3 / 3.2           │
│ dev-vm-03     12.4   34.5      3.2 / 1.8         0.4 / 0.2           │
│ dev-vm-04     ----   ERROR: Connection timeout                        │
╰────────────────────────────────────────────────────────────────────────╯

Press 'q' to quit | 'r' to refresh | Next auto-refresh in 45s
```

**Implementation Notes**:
- Use `rich.live.Live` for auto-updating display
- Color coding: green (<70%), yellow (70-85%), red (>85%)
- Show last update timestamp
- Keyboard shortcuts: q=quit, r=refresh now, +=faster, -=slower
- Handle terminal resize gracefully

### 4. Alert Engine Module (`src/azlin/monitoring/alerts.py`)

**Purpose**: Evaluate alert rules and trigger notifications

**Brick Specification**:
```python
"""Alert rules engine and notification dispatch.

Philosophy:
- Single responsibility: alert evaluation and dispatch
- Standard library + requests for webhooks
- Self-contained and regeneratable

Public API (the "studs"):
    AlertEngine: Main alert engine class
    AlertRule: Alert rule definition
    AlertSeverity: Severity levels (info, warning, critical)
    evaluate_rules(): Check metrics against rules
    send_notification(): Dispatch notification
"""

class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class AlertRule:
    name: str
    metric: str  # cpu_percent, memory_percent, etc
    threshold: float
    comparison: str  # >, <, >=, <=
    severity: AlertSeverity
    enabled: bool = True
    notification_channels: list[str] = field(default_factory=list)  # slack, email, webhook

@dataclass
class Alert:
    rule_name: str
    vm_name: str
    metric: str
    actual_value: float
    threshold: float
    severity: AlertSeverity
    timestamp: datetime
    message: str

class AlertEngine:
    """Evaluate alert rules and dispatch notifications."""

    def __init__(
        self,
        rules_config: Path = Path.home() / ".azlin" / "alert_rules.yaml",
        storage: MetricsStorage | None = None,
    ):
        """Initialize alert engine with rules configuration."""

    def load_rules(self) -> list[AlertRule]:
        """Load alert rules from YAML config."""

    def evaluate_rules(self, metrics: list[VMMetric]) -> list[Alert]:
        """Evaluate all rules against metrics."""

    def send_notification(self, alert: Alert, channel: str) -> bool:
        """Send alert notification via specified channel."""
```

**Default Alert Rules** (in `~/.azlin/alert_rules.yaml`):
```yaml
rules:
  - name: high_cpu
    metric: cpu_percent
    threshold: 80.0
    comparison: ">"
    severity: warning
    enabled: true
    notification_channels: [email]

  - name: critical_cpu
    metric: cpu_percent
    threshold: 95.0
    comparison: ">"
    severity: critical
    enabled: true
    notification_channels: [email, slack]

  - name: high_memory
    metric: memory_percent
    threshold: 85.0
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

  - name: disk_space
    metric: disk_percent
    threshold: 90.0
    comparison: ">"
    severity: warning
    enabled: true
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
  webhook:
    enabled: false
    url: https://example.com/alerts
```

**Implementation Notes**:
- Alert suppression: Don't re-alert for same VM+rule within 15 minutes
- Store alert history in SQLite (separate table)
- Retry failed notifications 3 times with exponential backoff
- Email using SMTP with TLS
- Slack using webhook API
- Generic webhook using POST with JSON payload

### 5. Forecasting Module (`src/azlin/monitoring/forecasting.py`)

**Purpose**: Predict resource utilization trends

**Brick Specification**:
```python
"""Resource utilization forecasting using linear regression.

Philosophy:
- Single responsibility: forecasting only
- Standard library (no ML frameworks for simplicity)
- Self-contained and regeneratable

Public API (the "studs"):
    ResourceForecaster: Main forecasting class
    Forecast: Forecast result data model
    forecast_utilization(): Predict future utilization
    identify_at_risk_vms(): Find VMs approaching limits
"""

@dataclass
class Forecast:
    vm_name: str
    metric: str
    current_value: float
    predicted_7d: float
    predicted_30d: float
    trend: str  # increasing, decreasing, stable
    at_risk: bool
    days_until_threshold: int | None

class ResourceForecaster:
    """Forecast resource utilization using linear regression."""

    def __init__(
        self,
        storage: MetricsStorage,
        risk_threshold: float = 90.0,
    ):
        """Initialize forecaster with historical storage."""

    def forecast_utilization(
        self,
        vm_name: str,
        metric: str,
        forecast_days: int = 30,
    ) -> Forecast:
        """Forecast metric for specified days ahead."""

    def identify_at_risk_vms(
        self,
        vm_names: list[str],
        metrics: list[str] = ["cpu_percent", "memory_percent", "disk_percent"],
    ) -> list[Forecast]:
        """Identify VMs approaching resource limits."""
```

**Implementation Notes**:
- Use simple linear regression: y = mx + b
- Require minimum 7 days of historical data
- Calculate trend from hourly aggregated data
- Trend classification:
  - Increasing: slope > 0.5% per day
  - Decreasing: slope < -0.5% per day
  - Stable: -0.5% ≤ slope ≤ 0.5%
- At-risk threshold: predicted to exceed 90% within 30 days
- Return "insufficient data" if < 7 days of history

### 6. CLI Commands Module (`src/azlin/commands/monitor.py`)

**Purpose**: Command-line interface for monitoring features

**Brick Specification**:
```python
"""Monitoring CLI commands.

Philosophy:
- Single responsibility: CLI interface only
- Click framework following azlin patterns
- Self-contained and regeneratable

Public API (the "studs"):
    monitor_group: Click command group
    dashboard(): Launch dashboard command
    alert(): Alert management commands
    history(): Historical query commands
    forecast(): Forecasting commands
"""

@click.group(name="monitor")
def monitor_group():
    """VM monitoring and alerting commands."""
    pass

@monitor_group.command()
@click.option("--refresh-interval", default=60, help="Refresh interval in seconds")
@click.option("--resource-group", help="Filter by resource group")
def dashboard(refresh_interval: int, resource_group: str | None):
    """Launch real-time monitoring dashboard."""

@monitor_group.group()
def alert():
    """Alert management commands."""
    pass

@alert.command("list")
def alert_list():
    """List configured alert rules."""

@alert.command("add")
@click.argument("name")
@click.option("--metric", required=True)
@click.option("--threshold", required=True, type=float)
@click.option("--severity", type=click.Choice(["info", "warning", "critical"]))
def alert_add(name: str, metric: str, threshold: float, severity: str):
    """Add new alert rule."""

@alert.command("enable")
@click.argument("name")
def alert_enable(name: str):
    """Enable alert rule."""

@alert.command("disable")
@click.argument("name")
def alert_disable(name: str):
    """Disable alert rule."""

@monitor_group.command()
@click.argument("vm-name")
@click.option("--days", default=7, help="Number of days to query")
@click.option("--metric", help="Specific metric to query")
@click.option("--export", type=click.Path(), help="Export to CSV file")
def history(vm_name: str, days: int, metric: str | None, export: str | None):
    """Query historical metrics."""

@monitor_group.command()
@click.option("--vm-name", help="Specific VM to forecast")
@click.option("--days", default=30, help="Forecast days ahead")
@click.option("--at-risk-only", is_flag=True, help="Show only at-risk VMs")
def forecast(vm_name: str | None, days: int, at_risk_only: bool):
    """Forecast resource utilization."""
```

**CLI Usage Examples**:
```bash
# Launch dashboard
azlin monitor dashboard
azlin monitor dashboard --refresh-interval 30 --resource-group my-rg

# Manage alerts
azlin monitor alert list
azlin monitor alert add high_cpu --metric cpu_percent --threshold 80 --severity warning
azlin monitor alert enable high_cpu
azlin monitor alert disable high_cpu

# Query history
azlin monitor history dev-vm-01 --days 30
azlin monitor history dev-vm-01 --metric cpu_percent --days 7
azlin monitor history dev-vm-01 --days 30 --export /tmp/metrics.csv

# Forecasting
azlin monitor forecast --days 30
azlin monitor forecast --vm-name dev-vm-01 --days 7
azlin monitor forecast --at-risk-only
```

## Integration with Existing Code

### 1. Leverage Existing Components

- **DistributedTopExecutor** (distributed_top.py): Pattern for parallel VM operations
- **ConfigManager** (config_manager.py): Store monitoring config
- **Azure CLI Auth**: Use existing `az` command patterns

### 2. Add to Main CLI

```python
# In src/azlin/cli.py
from azlin.commands.monitor import monitor_group

cli.add_command(monitor_group)
```

## Testing Strategy

### Unit Tests (60%)

- Test each module's public API independently
- Mock Azure API responses
- Test alert rule evaluation logic
- Test forecasting calculations
- Test storage queries

### Integration Tests (30%)

- Test collector + storage integration
- Test alert engine + notification dispatch
- Test dashboard rendering (snapshot testing)
- Test CLI commands end-to-end

### E2E Tests (10%)

- Test complete monitoring workflow
- Test with real Azure VMs (in test environment)
- Test alert suppression and retry logic
- Test data aggregation and cleanup

## File Structure

```
src/azlin/
├── monitoring/
│   ├── __init__.py
│   ├── collector.py      # Metrics collection
│   ├── storage.py        # SQLite storage
│   ├── dashboard.py      # Rich/Textual UI
│   ├── alerts.py         # Alert engine
│   └── forecasting.py    # Utilization forecasting
├── commands/
│   └── monitor.py        # CLI commands

tests/
├── unit/
│   └── monitoring/
│       ├── test_collector.py
│       ├── test_storage.py
│       ├── test_dashboard.py
│       ├── test_alerts.py
│       └── test_forecasting.py
├── integration/
│   └── monitoring/
│       ├── test_collector_storage.py
│       └── test_alert_dispatch.py
└── e2e/
    └── monitoring/
        └── test_monitoring_workflow.py
```

## Implementation Order

1. **Storage Module** - Foundation for all other modules
2. **Metrics Collector** - Data ingestion
3. **Dashboard Module** - Core user-facing feature
4. **Alert Engine** - Proactive monitoring
5. **Forecasting Module** - Advanced analytics
6. **CLI Commands** - User interface

## Success Criteria Validation

- [ ] Dashboard launches <5 seconds
- [ ] Alerts fire within 2 minutes of threshold breach
- [ ] Historical data queryable for 30+ days
- [ ] Forecasting accuracy within 15% for 7-day predictions
- [ ] Test coverage >75%
- [ ] CI passes
- [ ] Philosophy compliant (ruthless simplicity, zero-BS, modular design)

## Risk Assessment

### High Risk
- **Azure Monitor API Rate Limits**: Mitigate with request throttling and caching
- **Large-scale parallel collection**: Test with 50+ VMs
- **SQLite concurrent access**: Use WAL mode and connection pooling

### Medium Risk
- **Notification delivery failures**: Implement retry logic with exponential backoff
- **Dashboard terminal compatibility**: Test on multiple terminal emulators

### Low Risk
- **Forecasting accuracy**: Simple linear regression, clear limitations documented
- **Storage growth**: Automatic cleanup with configurable retention

## Philosophy Compliance

### Ruthless Simplicity
- Each module has single clear responsibility
- No unnecessary abstractions or frameworks
- Standard library preferred over heavy dependencies

### Zero-BS Implementation
- No stubs or placeholders
- All functions fully implemented
- Real Azure API integration from start

### Modular Design (Bricks & Studs)
- Clear module boundaries with defined contracts
- Each module regeneratable from spec
- Self-contained with all code in module directory
