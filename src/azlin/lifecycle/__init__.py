"""VM Lifecycle Automation Module.

Provides automated health monitoring, self-healing, and lifecycle event hooks
for Azure VMs managed by azlin.

Core Components:
- LifecycleManager: Configuration and lifecycle management
- HealthMonitor: VM health checking
- SelfHealer: Automatic recovery actions
- HookExecutor: Lifecycle event hook execution
- LifecycleDaemon: Background monitoring process
- DaemonController: Daemon management interface
"""

from .daemon_controller import (
    ControllerError,
    DaemonController,
)
from .health_monitor import (
    HealthCheckError,
    HealthFailure,
    HealthMonitor,
    HealthStatus,
    VMMetrics,
    VMState,
)
from .hook_executor import (
    HookExecutionError,
    HookExecutor,
    HookResult,
    HookType,
)
from .lifecycle_daemon import (
    DaemonError,
    DaemonStatus,
    LifecycleDaemon,
)
from .lifecycle_manager import (
    LIFECYCLE_CONFIG_PATH,
    VALID_HOOK_TYPES,
    VALID_RESTART_POLICIES,
    LifecycleConfigError,
    LifecycleManager,
    MonitoringConfig,
    MonitoringStatus,
)
from .self_healer import (
    RestartResult,
    SelfHealer,
    SelfHealingError,
)

__all__ = [
    "LIFECYCLE_CONFIG_PATH",
    "VALID_HOOK_TYPES",
    "VALID_RESTART_POLICIES",
    "ControllerError",
    "DaemonController",
    "DaemonError",
    "DaemonStatus",
    "HealthCheckError",
    "HealthFailure",
    "HealthMonitor",
    "HealthStatus",
    "HookExecutionError",
    "HookExecutor",
    "HookResult",
    "HookType",
    "LifecycleConfigError",
    "LifecycleDaemon",
    "LifecycleManager",
    "MonitoringConfig",
    "MonitoringStatus",
    "RestartResult",
    "SelfHealer",
    "SelfHealingError",
    "VMMetrics",
    "VMState",
]
