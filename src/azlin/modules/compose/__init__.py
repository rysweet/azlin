"""Docker Compose multi-VM orchestration module.

This module provides lightweight Kubernetes-alternative functionality for
deploying multi-container applications across multiple Azure VMs.

Philosophy:
- Extend standard docker-compose.yml with VM targeting
- Reuse existing azlin VM management infrastructure
- 80% of Kubernetes capability with 20% of operational complexity
- Zero-BS: All code functional, no placeholders

Public API:
    ComposeOrchestrator: Main orchestration controller
    ComposeNetworkManager: Inter-service networking setup
    ServiceConfig: Service configuration dataclass
    DeploymentResult: Deployment operation result
    DeployedService: Deployed service information
    VMInfo: VM information for placement
"""

from azlin.modules.compose.models import (
    DeployedService,
    DeploymentResult,
    ServiceConfig,
    ServicePlacement,
    VMInfo,
)
from azlin.modules.compose.network import ComposeNetworkManager
from azlin.modules.compose.orchestrator import ComposeOrchestrator

__all__ = [
    "ComposeNetworkManager",
    "ComposeOrchestrator",
    "DeployedService",
    "DeploymentResult",
    "ServiceConfig",
    "ServicePlacement",
    "VMInfo",
]
