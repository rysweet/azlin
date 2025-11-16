"""Data models for docker-compose multi-VM orchestration.

This module defines the core data structures used throughout the compose
orchestration system.

Philosophy:
- Immutable dataclasses for safety
- Type hints for clarity
- Simple validation at construction time
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ServiceConfig:
    """Configuration for a single service in docker-compose.azlin.yml."""

    name: str
    image: str
    vm_selector: str
    replicas: int = 1
    ports: List[str] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    volumes: List[str] = field(default_factory=list)
    command: Optional[str] = None
    healthcheck: Optional[Dict[str, str]] = None

    def __post_init__(self):
        """Validate service configuration."""
        if not self.name:
            raise ValueError("Service name cannot be empty")
        if not self.image:
            raise ValueError("Service image cannot be empty")
        if not self.vm_selector:
            raise ValueError("Service must specify 'vm' selector")
        if self.replicas < 1:
            raise ValueError("Service replicas must be >= 1")


@dataclass
class ServicePlacement:
    """Represents where a service instance should be deployed."""

    service_name: str
    replica_index: int
    vm_name: str
    vm_ip: str
    container_name: str

    @property
    def deployment_id(self) -> str:
        """Unique identifier for this deployment."""
        return f"{self.service_name}-{self.replica_index}-{self.vm_name}"


@dataclass
class DeployedService:
    """Information about a deployed service instance."""

    service_name: str
    vm_name: str
    vm_ip: str
    container_id: str
    container_name: str
    status: str  # "running", "exited", "error"
    ports: Dict[str, str] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        """Check if service is in healthy state."""
        return self.status == "running"


@dataclass
class DeploymentResult:
    """Result of a compose deployment operation."""

    success: bool
    deployed_services: List[DeployedService] = field(default_factory=list)
    failed_services: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def total_services(self) -> int:
        """Total number of services attempted."""
        return len(self.deployed_services) + len(self.failed_services)

    @property
    def success_rate(self) -> float:
        """Percentage of successfully deployed services."""
        if self.total_services == 0:
            return 0.0
        return len(self.deployed_services) / self.total_services


@dataclass
class VMInfo:
    """VM information for service placement."""

    name: str
    private_ip: str
    resource_group: str
    location: str
    power_state: str = "running"

    @property
    def is_available(self) -> bool:
        """Check if VM is available for deployment."""
        return self.power_state.lower() == "running"


__all__ = [
    "ServiceConfig",
    "ServicePlacement",
    "DeployedService",
    "DeploymentResult",
    "VMInfo",
]
