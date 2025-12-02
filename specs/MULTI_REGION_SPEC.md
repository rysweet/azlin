# Multi-Region Orchestration - Architecture Specification

**Document Version**: 1.0
**Date**: 2025-12-01
**Status**: Architecture Design (Step 5 - Research and Design)
**Issue**: #437 (WS3)
**Author**: Architect Agent

---

## Executive Summary

This specification defines the architecture for multi-region orchestration capabilities in azlin, transforming it from a single-region VM provisioner into a global infrastructure orchestrator. The design enables parallel multi-region deployments (3+ regions in <10 minutes), intelligent failover (60-second completion), and cross-region data synchronization (99.9% reliability).

### Core Design Principles

All features follow azlin's philosophy:
- **Ruthless simplicity**: Minimal abstractions, clear purpose
- **Brick architecture**: Self-contained, regeneratable modules
- **Security-first**: No credentials in code, proper permission handling
- **Async-first**: Python asyncio for parallel operations
- **Standard library preference**: Minimize external dependencies

### Technical Decisions (Previously Validated)

1. **Parallel Deployment**: Python asyncio for 3+ concurrent region deployments
2. **Failover Strategy**: Hybrid approach (automatic for clear failures, manual for ambiguous)
3. **Data Sync**: Hybrid approach (rsync for small files <100MB, Azure Blob for large)
4. **Context Storage**: Extend config.toml + Azure tags for region-aware metadata

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Module Specifications](#module-specifications)
3. [Public API Contracts](#public-api-contracts)
4. [CLI Command Specifications](#cli-command-specifications)
5. [Integration Points](#integration-points)
6. [Implementation Phases](#implementation-phases)
7. [Data Flow](#data-flow)
8. [Error Handling](#error-handling)
9. [Testing Strategy](#testing-strategy)
10. [Performance Targets](#performance-targets)

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     azlin Multi-Region CLI                       │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         CLI Entry Point (cli.py)                       │    │
│  │         - azlin deploy --regions us,eu,asia            │    │
│  │         - azlin failover --to westus2                  │    │
│  │         - azlin sync --source eastus --dest westus2    │    │
│  └────────────────────────────────────────────────────────┘    │
│                          │                                      │
│              ┌───────────┴───────────┐                         │
│              │                       │                          │
│       ┌──────▼─────┐         ┌─────▼──────┐                  │
│       │ New        │         │ Existing   │                  │
│       │ Modules    │         │ Modules    │                  │
│       │ (4)        │         │ (Enhanced) │                  │
│       └────────────┘         └────────────┘                  │
│                                                                │
└─────────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼─────┐    ┌─────▼──────┐    ┌────▼──────┐
   │  Region  │    │  Region    │    │  Region   │
   │  East US │    │  West US2  │    │  West EU  │
   └──────────┘    └────────────┘    └───────────┘
        │                 │                 │
   ┌────▼────────────────▼─────────────────▼────┐
   │         Azure Cloud Platform                │
   │  ┌──────────────────────────────────┐      │
   │  │    Multi-Region VM Fleet         │      │
   │  │  - Parallel provisioning         │      │
   │  │  - Intelligent failover          │      │
   │  │  - Cross-region sync             │      │
   │  └──────────────────────────────────┘      │
   └──────────────────────────────────────────────┘
```

### Module Architecture (New Bricks)

```
New Multi-Region Bricks (4):
├── src/azlin/modules/
│   ├── parallel_deployer.py      # Brick 11: Async parallel deployment
│   ├── region_failover.py        # Brick 12: Intelligent failover
│   ├── cross_region_sync.py      # Brick 13: Data synchronization
│   └── region_context.py         # Brick 14: Region-aware context

Enhanced Existing Modules:
├── config_manager.py             # Add region metadata storage
├── context_manager.py            # Add region-aware context
└── vm_provisioning.py            # Add region-specific parameters
```

**Each brick has**:
- Single responsibility (one purpose)
- Defined public contract (`__all__`)
- No dependencies on other bricks (except via interfaces)
- Comprehensive docstrings + type hints
- 60% unit / 30% integration / 10% E2E tests

---

## Module Specifications

### Brick 11: Parallel Deployer

**File**: `src/azlin/modules/parallel_deployer.py`

**Purpose**: Deploy VMs to multiple regions concurrently using Python asyncio.

**Philosophy**:
- Ruthless simplicity: One class, one purpose
- Async-first: asyncio for true parallelism
- Fail-fast: Clear error reporting per region
- Standard library: asyncio, subprocess (no external async libs)

**Public API (Studs)**:

```python
"""Parallel multi-region VM deployment.

Philosophy:
- Async-first: Python asyncio for true parallelism
- Fail-fast: Each region reports success/failure independently
- Standard library only (asyncio, subprocess)
- Self-contained and regeneratable

Public API (the "studs"):
    ParallelDeployer: Main deployment orchestrator
    DeploymentResult: Result for single region
    MultiRegionResult: Aggregated results across regions
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import asyncio

class DeploymentStatus(Enum):
    """Status of a single region deployment."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"

@dataclass
class DeploymentResult:
    """Result of deploying to a single region."""
    region: str
    status: DeploymentStatus
    vm_name: str
    public_ip: Optional[str] = None
    error: Optional[str] = None
    duration_seconds: float = 0.0

@dataclass
class MultiRegionResult:
    """Aggregated results from multi-region deployment."""
    total_regions: int
    successful: List[DeploymentResult]
    failed: List[DeploymentResult]
    total_duration_seconds: float

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0-1.0)."""
        return len(self.successful) / self.total_regions if self.total_regions > 0 else 0.0

class ParallelDeployer:
    """Deploy VMs to multiple regions concurrently.

    Uses asyncio to provision VMs in parallel, respecting Azure
    subscription limits (typically 20 concurrent operations).

    Example:
        deployer = ParallelDeployer(config_manager=config_mgr)
        result = await deployer.deploy_to_regions(
            regions=["eastus", "westus2", "westeurope"],
            vm_config=vm_config
        )
        print(f"Success rate: {result.success_rate:.1%}")
    """

    def __init__(
        self,
        config_manager: 'ConfigManager',
        max_concurrent: int = 10
    ):
        """Initialize parallel deployer.

        Args:
            config_manager: Config manager for storing region metadata
            max_concurrent: Max concurrent deployments (default: 10)
        """

    async def deploy_to_regions(
        self,
        regions: List[str],
        vm_config: 'VMConfig'
    ) -> MultiRegionResult:
        """Deploy VMs to multiple regions in parallel.

        Args:
            regions: List of Azure regions (e.g., ["eastus", "westus2"])
            vm_config: VM configuration (size, image, keys, etc.)

        Returns:
            MultiRegionResult with success/failure per region

        Raises:
            ValueError: If regions list is empty or invalid
            DeploymentError: If ALL regions fail (partial failure OK)
        """

    async def _deploy_single_region(
        self,
        region: str,
        vm_config: 'VMConfig'
    ) -> DeploymentResult:
        """Deploy VM to a single region (internal method).

        Delegates to existing vm_provisioning.py module via subprocess.
        Captures output and errors for detailed reporting.
        """

__all__ = [
    "ParallelDeployer",
    "DeploymentResult",
    "DeploymentStatus",
    "MultiRegionResult"
]
```

**Implementation Notes**:
- Use `asyncio.create_subprocess_exec()` for parallel az CLI calls
- Semaphore to limit concurrent operations (default: 10)
- Timeout per region: 10 minutes (configurable)
- Store results in config immediately after each region succeeds

**Dependencies**:
- `config_manager.py` (for storing region metadata)
- `vm_provisioning.py` (reuse existing VM creation logic)

**Complexity**: MEDIUM (asyncio orchestration, error handling)

---

### Brick 12: Region Failover

**File**: `src/azlin/modules/region_failover.py`

**Purpose**: Intelligent failover between regions with automatic/manual modes.

**Philosophy**:
- Hybrid failover: Auto for clear failures, manual for ambiguous
- Health checks: Verify VM accessibility before failover
- Safety-first: Require explicit confirmation for data-destructive operations
- Clear decision logic: Document why failover is/isn't automatic

**Public API (Studs)**:

```python
"""Intelligent region failover with automatic/manual modes.

Philosophy:
- Hybrid failover: Auto for clear failures, manual for ambiguous
- Safety-first: Explicit confirmation for data-destructive ops
- Health-based: Verify VM accessibility before failover
- Self-contained and regeneratable

Public API (the "studs"):
    RegionFailover: Main failover orchestrator
    FailoverDecision: Automated decision logic
    FailoverMode: Auto/manual/hybrid enum
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import asyncio

class FailoverMode(Enum):
    """Failover execution mode."""
    AUTO = "auto"          # Automatic for clear failures
    MANUAL = "manual"      # Always require confirmation
    HYBRID = "hybrid"      # Auto for clear, manual for ambiguous (default)

class FailureType(Enum):
    """Type of failure detected."""
    NETWORK_UNREACHABLE = "network_unreachable"    # Auto-failover
    SSH_CONNECTION_FAILED = "ssh_connection_failed"  # Auto-failover
    VM_STOPPED = "vm_stopped"                      # Manual (might be intentional)
    VM_DEALLOCATED = "vm_deallocated"              # Manual
    PERFORMANCE_DEGRADED = "performance_degraded"   # Manual
    UNKNOWN = "unknown"                             # Manual

@dataclass
class HealthCheckResult:
    """Result of health check on a VM."""
    vm_name: str
    region: str
    is_healthy: bool
    failure_type: Optional[FailureType] = None
    response_time_ms: Optional[float] = None
    error_details: Optional[str] = None

@dataclass
class FailoverDecision:
    """Decision about whether to auto-failover."""
    should_auto_failover: bool
    reason: str
    failure_type: FailureType
    confidence: float  # 0.0-1.0 (how confident in auto decision)

class RegionFailover:
    """Intelligent failover between regions.

    Hybrid approach:
    - AUTO: Network unreachable, SSH failed (clear failures)
    - MANUAL: VM stopped, performance issues (ambiguous)

    Example:
        failover = RegionFailover(mode=FailoverMode.HYBRID)
        decision = await failover.evaluate_failover(
            source_region="eastus",
            vm_name="azlin-vm-123"
        )
        if decision.should_auto_failover:
            result = await failover.execute_failover(
                source_region="eastus",
                target_region="westus2",
                vm_name="azlin-vm-123"
            )
    """

    def __init__(
        self,
        config_manager: 'ConfigManager',
        mode: FailoverMode = FailoverMode.HYBRID,
        timeout_seconds: int = 60
    ):
        """Initialize region failover.

        Args:
            config_manager: Config manager for region metadata
            mode: Failover mode (auto/manual/hybrid)
            timeout_seconds: Max time for failover operation (default: 60)
        """

    async def check_health(
        self,
        vm_name: str,
        region: str
    ) -> HealthCheckResult:
        """Check health of VM in specified region.

        Performs:
        1. Azure VM status check (running/stopped/deallocated)
        2. Network reachability (ping)
        3. SSH connectivity check
        4. Response time measurement

        Args:
            vm_name: VM name to check
            region: Azure region

        Returns:
            HealthCheckResult with detailed status
        """

    async def evaluate_failover(
        self,
        source_region: str,
        vm_name: str
    ) -> FailoverDecision:
        """Evaluate whether to auto-failover based on failure type.

        Decision logic:
        - Network unreachable: AUTO (confidence=0.95)
        - SSH failed: AUTO (confidence=0.90)
        - VM stopped: MANUAL (might be intentional)
        - Performance degraded: MANUAL (subjective)

        Args:
            source_region: Region with potential failure
            vm_name: VM name to evaluate

        Returns:
            FailoverDecision with auto/manual recommendation
        """

    async def execute_failover(
        self,
        source_region: str,
        target_region: str,
        vm_name: str,
        require_confirmation: bool = True
    ) -> 'FailoverResult':
        """Execute failover from source to target region.

        Steps:
        1. Verify target region is healthy
        2. Optionally sync data (if sync enabled)
        3. Update config to point to target region
        4. Verify target VM is accessible
        5. Optionally deallocate source VM (if requested)

        Args:
            source_region: Region to fail over from
            target_region: Region to fail over to
            vm_name: VM name
            require_confirmation: Ask user before proceeding (default: True)

        Returns:
            FailoverResult with success/failure status

        Raises:
            FailoverError: If target region is also unhealthy
        """

__all__ = [
    "RegionFailover",
    "FailoverDecision",
    "FailoverMode",
    "FailureType",
    "HealthCheckResult"
]
```

**Implementation Notes**:
- Health check timeout: 10 seconds per check
- Auto-failover confidence threshold: 0.85 (85% confident)
- Manual failover: Use `click.confirm()` for user approval
- Store failover events in config for audit trail

**Dependencies**:
- `config_manager.py` (for region metadata)
- `cross_region_sync.py` (optional data sync before failover)
- `ip_diagnostics.py` (existing module for connectivity checks)

**Complexity**: MEDIUM (health checks, decision logic)

---

### Brick 13: Cross-Region Sync

**File**: `src/azlin/modules/cross_region_sync.py`

**Purpose**: Synchronize data between VMs in different regions.

**Philosophy**:
- Hybrid sync: rsync for small files (<100MB), Azure Blob for large
- Incremental: Only sync changed files (rsync delta algorithm)
- Transparent: Show progress and estimated time
- Safe: Never delete files without explicit confirmation

**Public API (Studs)**:

```python
"""Cross-region data synchronization.

Philosophy:
- Hybrid sync: rsync for small (<100MB), Azure Blob for large
- Incremental: Delta-based transfers (rsync algorithm)
- Safe: Never delete without confirmation
- Self-contained and regeneratable

Public API (the "studs"):
    CrossRegionSync: Main sync orchestrator
    SyncStrategy: Rsync or Azure Blob enum
    SyncResult: Result of sync operation
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from pathlib import Path

class SyncStrategy(Enum):
    """Strategy for syncing data."""
    RSYNC = "rsync"          # For small files (<100MB)
    AZURE_BLOB = "azure_blob"  # For large files (>100MB)
    AUTO = "auto"            # Choose based on size (default)

@dataclass
class SyncResult:
    """Result of cross-region sync operation."""
    strategy_used: SyncStrategy
    files_synced: int
    bytes_transferred: int
    duration_seconds: float
    source_region: str
    target_region: str
    errors: List[str]

    @property
    def success_rate(self) -> float:
        """Calculate success rate (1.0 if no errors)."""
        return 0.0 if self.errors else 1.0

class CrossRegionSync:
    """Synchronize data between VMs in different regions.

    Hybrid approach:
    - Small files (<100MB): rsync over SSH (incremental, fast)
    - Large files (>100MB): Azure Blob staging (parallel, reliable)

    Example:
        sync = CrossRegionSync()
        result = await sync.sync_directories(
            source_vm="vm-eastus",
            target_vm="vm-westus2",
            paths=["/home/azureuser/project"],
            strategy=SyncStrategy.AUTO
        )
        print(f"Synced {result.files_synced} files")
    """

    def __init__(
        self,
        config_manager: 'ConfigManager',
        ssh_connector: 'SSHConnector'
    ):
        """Initialize cross-region sync.

        Args:
            config_manager: Config manager for VM metadata
            ssh_connector: SSH connector for remote operations
        """

    async def estimate_transfer_size(
        self,
        vm_name: str,
        paths: List[str]
    ) -> int:
        """Estimate total size of files to sync.

        Runs 'du -sb' on remote VM to calculate size.

        Args:
            vm_name: VM to check
            paths: List of paths to estimate

        Returns:
            Total size in bytes
        """

    async def choose_strategy(
        self,
        estimated_size_bytes: int
    ) -> SyncStrategy:
        """Choose optimal sync strategy based on size.

        Decision logic:
        - < 100MB: RSYNC (faster for small files)
        - >= 100MB: AZURE_BLOB (more reliable for large)

        Args:
            estimated_size_bytes: Total size to sync

        Returns:
            Recommended SyncStrategy
        """

    async def sync_directories(
        self,
        source_vm: str,
        target_vm: str,
        paths: List[str],
        strategy: SyncStrategy = SyncStrategy.AUTO,
        delete: bool = False
    ) -> SyncResult:
        """Sync directories from source VM to target VM.

        Steps:
        1. Estimate total size
        2. Choose strategy (if AUTO)
        3. Execute sync with progress reporting
        4. Verify sync completed successfully

        Args:
            source_vm: Source VM name
            target_vm: Target VM name
            paths: List of paths to sync (absolute paths)
            strategy: Sync strategy (default: AUTO)
            delete: Delete files in target not in source (default: False)

        Returns:
            SyncResult with transfer statistics

        Raises:
            SyncError: If sync fails
        """

    async def _sync_via_rsync(
        self,
        source_vm: str,
        target_vm: str,
        paths: List[str],
        delete: bool
    ) -> SyncResult:
        """Sync using rsync over SSH (internal method).

        Command: rsync -avz --progress source_vm:path target_vm:path
        """

    async def _sync_via_blob(
        self,
        source_vm: str,
        target_vm: str,
        paths: List[str],
        delete: bool
    ) -> SyncResult:
        """Sync using Azure Blob staging (internal method).

        Steps:
        1. Upload from source VM to Blob container
        2. Download from Blob to target VM
        3. Clean up Blob staging area
        """

__all__ = [
    "CrossRegionSync",
    "SyncStrategy",
    "SyncResult"
]
```

**Implementation Notes**:
- rsync flags: `-avz --progress` (archive, verbose, compress, progress)
- Azure Blob staging container: `azlin-sync-{timestamp}` (auto-delete after 24h)
- Parallel blob transfers: Use `az storage blob upload-batch` (built-in parallelism)
- Progress reporting: Parse rsync/az output and display with rich progress bar

**Dependencies**:
- `ssh_connector.py` (existing module for SSH operations)
- `config_manager.py` (for VM metadata)
- Azure CLI (for blob operations)

**Complexity**: MEDIUM (rsync/blob logic, progress parsing)

---

### Brick 14: Region Context

**File**: `src/azlin/modules/region_context.py`

**Purpose**: Manage region-aware context metadata.

**Philosophy**:
- Extend existing: Build on config.toml + Azure tags
- Per-region context: Each region can have different settings
- Tag-based: Use Azure tags for cloud-native metadata
- Backward compatible: Works with existing single-region configs

**Public API (Studs)**:

```python
"""Region-aware context management.

Philosophy:
- Extend existing: Build on config.toml + Azure tags
- Tag-based: Azure-native metadata storage
- Per-region context: Different settings per region
- Self-contained and regeneratable

Public API (the "studs"):
    RegionContext: Region-aware context manager
    RegionMetadata: Metadata for a single region
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class RegionMetadata:
    """Metadata for a single region."""
    region: str
    vm_name: str
    public_ip: Optional[str]
    resource_group: str
    created_at: str  # ISO 8601 timestamp
    last_health_check: Optional[str] = None
    is_primary: bool = False
    tags: Dict[str, str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

class RegionContext:
    """Manage region-aware context metadata.

    Stores metadata in two places:
    1. ~/.azlin/config.json (local cache)
    2. Azure VM tags (cloud-native storage)

    Example:
        context = RegionContext(config_manager)
        context.add_region(
            region="eastus",
            vm_name="vm-eastus",
            is_primary=True
        )
        primary = context.get_primary_region()
        all_regions = context.list_regions()
    """

    def __init__(
        self,
        config_manager: 'ConfigManager'
    ):
        """Initialize region context manager.

        Args:
            config_manager: Config manager for local storage
        """

    def add_region(
        self,
        region: str,
        vm_name: str,
        public_ip: Optional[str] = None,
        is_primary: bool = False,
        tags: Optional[Dict[str, str]] = None
    ) -> RegionMetadata:
        """Add or update region metadata.

        Stores in:
        1. Local config: ~/.azlin/config.json
        2. Azure tags: az tag create --resource-id <vm_id> --tags azlin:region=eastus

        Args:
            region: Azure region name
            vm_name: VM name in that region
            public_ip: Public IP (optional)
            is_primary: Mark as primary region (default: False)
            tags: Additional tags

        Returns:
            RegionMetadata object
        """

    def get_region(
        self,
        region: str
    ) -> Optional[RegionMetadata]:
        """Get metadata for a specific region.

        Args:
            region: Azure region name

        Returns:
            RegionMetadata if exists, None otherwise
        """

    def get_primary_region(self) -> Optional[RegionMetadata]:
        """Get primary region metadata.

        Returns:
            RegionMetadata for primary region, None if not set
        """

    def set_primary_region(
        self,
        region: str
    ) -> None:
        """Set primary region (unsets previous primary).

        Args:
            region: Region to mark as primary

        Raises:
            ValueError: If region doesn't exist
        """

    def list_regions(self) -> List[RegionMetadata]:
        """List all regions with metadata.

        Returns:
            List of RegionMetadata, sorted by is_primary then region name
        """

    def remove_region(
        self,
        region: str,
        remove_vm: bool = False
    ) -> None:
        """Remove region from context.

        Args:
            region: Region to remove
            remove_vm: Also deallocate/delete the VM (default: False)

        Raises:
            ValueError: If region doesn't exist
        """

    async def sync_from_azure_tags(self) -> int:
        """Sync local config from Azure VM tags.

        Queries Azure for all VMs with 'azlin:region' tag and
        updates local config with latest metadata.

        Returns:
            Number of regions synced
        """

__all__ = [
    "RegionContext",
    "RegionMetadata"
]
```

**Implementation Notes**:
- Config schema addition:
  ```json
  {
    "regions": [
      {
        "region": "eastus",
        "vm_name": "vm-eastus",
        "public_ip": "1.2.3.4",
        "is_primary": true,
        "created_at": "2025-12-01T10:00:00Z"
      }
    ]
  }
  ```
- Azure tag format: `azlin:region=eastus`, `azlin:primary=true`
- Sync on startup: Call `sync_from_azure_tags()` to ensure local cache is fresh

**Dependencies**:
- `config_manager.py` (for local storage)
- Azure CLI (for tag operations)

**Complexity**: LOW (simple CRUD + tag operations)

---

## Public API Contracts (Studs)

### Integration Contract Between Modules

```python
# All modules expose clear public APIs via __all__

# parallel_deployer.py exports:
__all__ = ["ParallelDeployer", "DeploymentResult", "MultiRegionResult"]

# region_failover.py exports:
__all__ = ["RegionFailover", "FailoverDecision", "FailoverMode", "HealthCheckResult"]

# cross_region_sync.py exports:
__all__ = ["CrossRegionSync", "SyncStrategy", "SyncResult"]

# region_context.py exports:
__all__ = ["RegionContext", "RegionMetadata"]

# Enhanced config_manager.py exports (additions):
__all__ = [...existing..., "RegionConfig"]
```

### Module Communication Flow

```
CLI Command (azlin deploy --regions us,eu,asia)
    ↓
ParallelDeployer.deploy_to_regions(regions=["eastus", "westeurope", "southeastasia"])
    ↓
For each region (in parallel):
    VMProvisioning.provision_vm(config with region override)
    ↓
    RegionContext.add_region(region, vm_name, ip)
    ↓
ConfigManager.save_config()
```

---

## CLI Command Specifications

### Command: azlin deploy --regions

**Purpose**: Deploy VMs to multiple regions in parallel.

**Syntax**:
```bash
azlin deploy --regions eastus,westus2,westeurope [options]

# Shorthand:
azlin deploy -r us,eu,asia  # Uses region aliases
```

**Arguments**:
- `--regions, -r`: Comma-separated list of regions (required)
- `--primary`: Which region is primary (default: first in list)
- `--vm-size`: VM size for all regions (default: Standard_B2s)
- `--sync-after`: Auto-sync data after deployment (default: false)
- `--max-concurrent`: Max parallel deployments (default: 10)
- `--timeout`: Timeout per region in seconds (default: 600)

**Example Output**:
```
► Deploying to 3 regions in parallel...

Region: eastus
  ► Creating VM: vm-eastus-20251201
  ✓ VM created in 3m 12s
  ✓ Public IP: 1.2.3.4

Region: westus2
  ► Creating VM: vm-westus2-20251201
  ✓ VM created in 3m 45s
  ✓ Public IP: 5.6.7.8

Region: westeurope
  ✗ Failed: Capacity unavailable in westeurope
  ⚠ Consider: northeurope as alternative

✓ Deployment complete in 4m 18s
  Success: 2/3 regions (66.7%)
  Primary: eastus (1.2.3.4)

To list all regions: azlin regions list
To sync data: azlin sync --source eastus --dest westus2
```

**Exit Codes**:
- 0: All regions successful
- 1: Partial failure (at least 1 region succeeded)
- 2: Complete failure (all regions failed)

**Implementation**:
```python
@cli.command()
@click.option("--regions", "-r", required=True, help="Comma-separated regions")
@click.option("--primary", help="Primary region")
@click.option("--vm-size", default="Standard_B2s")
@click.option("--max-concurrent", default=10, type=int)
@click.option("--timeout", default=600, type=int)
def deploy(regions: str, primary: Optional[str], vm_size: str, max_concurrent: int, timeout: int):
    """Deploy VMs to multiple regions in parallel."""
    region_list = [r.strip() for r in regions.split(",")]

    deployer = ParallelDeployer(
        config_manager=config_mgr,
        max_concurrent=max_concurrent
    )

    result = asyncio.run(deployer.deploy_to_regions(
        regions=region_list,
        vm_config=vm_config
    ))

    # Display results
    display_multi_region_results(result)

    # Exit with appropriate code
    if result.success_rate == 1.0:
        sys.exit(0)
    elif result.success_rate > 0:
        sys.exit(1)
    else:
        sys.exit(2)
```

---

### Command: azlin failover

**Purpose**: Failover from one region to another.

**Syntax**:
```bash
azlin failover --to westus2 [options]

# Auto-detect failure and failover:
azlin failover --auto

# Check health without failover:
azlin failover --check-only
```

**Arguments**:
- `--to`: Target region (required unless --auto)
- `--from`: Source region (default: current primary)
- `--auto`: Auto-detect failure and choose target (default: false)
- `--sync`: Sync data before failover (default: false)
- `--yes`: Skip confirmation prompt (default: false)

**Example Output**:
```
► Checking health of primary region (eastus)...
  ✗ Network unreachable (timeout after 10s)
  ✓ Failure type: NETWORK_UNREACHABLE (auto-failover eligible)

► Evaluating failover to westus2...
  ✓ Target region healthy (response time: 45ms)
  ✓ Auto-failover confidence: 95%

► Executing failover to westus2...
  ► Syncing data (12 files, 45MB)
  ✓ Data synced in 18s
  ► Updating config to point to westus2
  ✓ Primary region: westus2 (5.6.7.8)

✓ Failover complete in 52s
  Source: eastus (deallocated)
  Target: westus2 (5.6.7.8)

To verify: azlin ssh
To sync back: azlin sync --source westus2 --dest eastus
```

**Exit Codes**:
- 0: Failover successful
- 1: Target region unhealthy (failover not safe)
- 2: User cancelled (manual mode)

**Implementation**:
```python
@cli.command()
@click.option("--to", help="Target region")
@click.option("--from", "source_region", help="Source region")
@click.option("--auto", is_flag=True, help="Auto-detect failure")
@click.option("--sync", is_flag=True, help="Sync data before failover")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def failover(to: Optional[str], source_region: Optional[str], auto: bool, sync: bool, yes: bool):
    """Failover from one region to another."""
    failover_mgr = RegionFailover(
        config_manager=config_mgr,
        mode=FailoverMode.HYBRID
    )

    # Auto-detect source if not specified
    if not source_region:
        primary = region_context.get_primary_region()
        source_region = primary.region if primary else None

    # Check health
    health = asyncio.run(failover_mgr.check_health(vm_name, source_region))

    # Evaluate failover decision
    decision = asyncio.run(failover_mgr.evaluate_failover(source_region, vm_name))

    # Display decision
    display_failover_decision(health, decision)

    # Auto-choose target if --auto
    if auto and not to:
        to = choose_best_target_region(source_region, region_context.list_regions())

    # Execute failover
    result = asyncio.run(failover_mgr.execute_failover(
        source_region=source_region,
        target_region=to,
        vm_name=vm_name,
        require_confirmation=not yes
    ))

    sys.exit(0 if result.success else 1)
```

---

### Command: azlin sync

**Purpose**: Sync data between regions.

**Syntax**:
```bash
azlin sync --source eastus --dest westus2 [options]

# Sync to all regions from primary:
azlin sync --all

# Sync specific paths:
azlin sync --source eastus --dest westus2 --paths /home/azureuser/project,/data
```

**Arguments**:
- `--source, -s`: Source region (required)
- `--dest, -d`: Destination region (required unless --all)
- `--all`: Sync to all regions (default: false)
- `--paths, -p`: Comma-separated paths (default: /home/azureuser)
- `--strategy`: rsync, blob, or auto (default: auto)
- `--delete`: Delete files in dest not in source (default: false)
- `--dry-run`: Show what would be synced (default: false)

**Example Output**:
```
► Estimating transfer size...
  ✓ Total: 125 files, 342MB

► Choosing sync strategy...
  ✓ Strategy: AZURE_BLOB (large files detected)

► Syncing eastus → westus2...
  ► Uploading to Azure Blob (azlin-sync-20251201)
    [████████████████████████████░] 85% (290MB/342MB) ETA: 1m 12s
  ✓ Upload complete in 3m 45s
  ► Downloading to westus2
    [████████████████████████████░] 92% (315MB/342MB) ETA: 32s
  ✓ Download complete in 2m 18s
  ► Cleaning up Blob staging
  ✓ Cleanup complete

✓ Sync complete in 6m 22s
  Files synced: 125
  Data transferred: 342MB
  Success rate: 100%

To verify: azlin ssh --region westus2
```

**Exit Codes**:
- 0: Sync successful
- 1: Partial failure (some files failed)
- 2: Complete failure

**Implementation**:
```python
@cli.command()
@click.option("--source", "-s", required=True, help="Source region")
@click.option("--dest", "-d", help="Destination region")
@click.option("--all", is_flag=True, help="Sync to all regions")
@click.option("--paths", "-p", default="/home/azureuser", help="Comma-separated paths")
@click.option("--strategy", type=click.Choice(["rsync", "blob", "auto"]), default="auto")
@click.option("--delete", is_flag=True, help="Delete files in dest not in source")
@click.option("--dry-run", is_flag=True, help="Show what would be synced")
def sync(source: str, dest: Optional[str], all: bool, paths: str, strategy: str, delete: bool, dry_run: bool):
    """Sync data between regions."""
    sync_mgr = CrossRegionSync(
        config_manager=config_mgr,
        ssh_connector=ssh_connector
    )

    path_list = [p.strip() for p in paths.split(",")]

    # Determine destinations
    dest_regions = []
    if all:
        dest_regions = [r.region for r in region_context.list_regions() if r.region != source]
    else:
        dest_regions = [dest]

    # Sync to each destination
    results = []
    for dest_region in dest_regions:
        result = asyncio.run(sync_mgr.sync_directories(
            source_vm=f"vm-{source}",
            target_vm=f"vm-{dest_region}",
            paths=path_list,
            strategy=SyncStrategy[strategy.upper()],
            delete=delete
        ))
        results.append(result)
        display_sync_result(result)

    # Exit based on aggregate results
    success_rate = sum(r.success_rate for r in results) / len(results)
    sys.exit(0 if success_rate == 1.0 else (1 if success_rate > 0 else 2))
```

---

### Command: azlin regions

**Purpose**: Manage multi-region deployments.

**Syntax**:
```bash
azlin regions list              # List all regions
azlin regions add eastus        # Add region
azlin regions remove westus2    # Remove region
azlin regions set-primary eu    # Set primary region
azlin regions health            # Check health of all regions
```

**Subcommands**:

#### azlin regions list

**Example Output**:
```
Multi-Region Deployments:

Region       VM Name            Public IP    Status   Primary   Last Check
───────────────────────────────────────────────────────────────────────────
eastus       vm-eastus-123      1.2.3.4      ✓ OK     ●         2m ago
westus2      vm-westus2-123     5.6.7.8      ✓ OK     ○         5m ago
westeurope   vm-westeu-123      9.10.11.12   ✗ DOWN   ○         1h ago

Total: 3 regions (2 healthy, 1 down)
Primary: eastus (1.2.3.4)

To check health: azlin regions health
To failover: azlin failover --to westus2
```

#### azlin regions health

**Example Output**:
```
► Checking health of all regions...

Region: eastus
  ✓ VM Status: Running
  ✓ Network: Reachable (ping: 12ms)
  ✓ SSH: Connected (response: 45ms)
  ✓ Overall: HEALTHY

Region: westus2
  ✓ VM Status: Running
  ✓ Network: Reachable (ping: 18ms)
  ✓ SSH: Connected (response: 52ms)
  ✓ Overall: HEALTHY

Region: westeurope
  ✓ VM Status: Running
  ✗ Network: Unreachable (timeout after 10s)
  ✗ SSH: Failed (connection refused)
  ✗ Overall: UNHEALTHY
  ⚠ Recommend: Auto-failover to northeurope

Health Summary: 2/3 regions healthy (66.7%)
```

**Implementation**:
```python
@cli.group()
def regions():
    """Manage multi-region deployments."""
    pass

@regions.command("list")
def list_regions():
    """List all regions with metadata."""
    region_list = region_context.list_regions()
    display_regions_table(region_list)

@regions.command("health")
def check_health():
    """Check health of all regions."""
    failover_mgr = RegionFailover(config_mgr)

    results = []
    for metadata in region_context.list_regions():
        health = asyncio.run(failover_mgr.check_health(
            vm_name=metadata.vm_name,
            region=metadata.region
        ))
        results.append(health)
        display_health_check(health)

    display_health_summary(results)
```

---

## Integration Points

### Integration with Existing Modules

#### 1. config_manager.py (Enhanced)

**Changes Required**:
- Add `regions: List[RegionMetadata]` field to config schema
- Add `get_region(region: str)` method
- Add `set_primary_region(region: str)` method

**Example Enhanced Config**:
```json
{
  "version": "2.0",
  "resource_group": "azlin-vms",
  "default_region": "eastus",
  "default_vm_size": "Standard_B2s",
  "regions": [
    {
      "region": "eastus",
      "vm_name": "vm-eastus-123",
      "public_ip": "1.2.3.4",
      "is_primary": true,
      "created_at": "2025-12-01T10:00:00Z"
    },
    {
      "region": "westus2",
      "vm_name": "vm-westus2-123",
      "public_ip": "5.6.7.8",
      "is_primary": false,
      "created_at": "2025-12-01T10:05:00Z"
    }
  ]
}
```

#### 2. vm_provisioning.py (Enhanced)

**Changes Required**:
- Add `region: str` parameter to `provision_vm()` method
- Use region-specific resource group: `{base_rg}-{region}`
- Tag VMs with `azlin:region={region}`

**Example Enhancement**:
```python
def provision_vm(self, config: VMConfig, region: str = "eastus") -> VMInfo:
    """Provision VM in specified region."""
    # Add region to resource group name
    rg = f"{config.resource_group}-{region}"

    # Ensure resource group exists in target region
    self._ensure_resource_group(rg, region)

    # Add region tag
    tags = config.tags or {}
    tags["azlin:region"] = region

    # Rest of provisioning logic...
```

#### 3. context_manager.py (Enhanced)

**Changes Required**:
- Add region awareness to context switching
- Filter contexts by region
- Support multi-region context listing

#### 4. cli.py (Enhanced)

**Changes Required**:
- Add `regions` command group
- Add `deploy --regions` option
- Add `failover` command
- Add `sync` command
- Enhance `list` to show region info

---

## Implementation Phases

### Phase 1: Foundation (Week 1) - MVP

**Goal**: Basic multi-region deployment

**Modules**:
- ✓ region_context.py (Brick 14)
- ✓ Enhanced config_manager.py
- ✓ Enhanced vm_provisioning.py

**Commands**:
- ✓ azlin regions list
- ✓ azlin regions add
- ✓ azlin regions set-primary

**Acceptance Criteria**:
- Can manually deploy VMs to multiple regions (sequential)
- Can list regions with metadata
- Config stores region information

**Testing**:
- Unit tests: region_context.py (60% coverage)
- Integration: Deploy to 2 regions (manual)
- E2E: Full workflow (manual → list → set-primary)

---

### Phase 2: Parallel Deployment (Week 2)

**Goal**: Deploy to 3+ regions in parallel (<10 min)

**Modules**:
- ✓ parallel_deployer.py (Brick 11)

**Commands**:
- ✓ azlin deploy --regions eastus,westus2,westeurope

**Acceptance Criteria**:
- Deploy to 3 regions in <10 minutes (requirement met)
- Success rate displayed per region
- Errors don't stop other regions

**Testing**:
- Unit tests: parallel_deployer.py (60% coverage)
- Integration: Deploy to 3 regions (actual Azure)
- E2E: Full workflow (deploy → verify all regions)

---

### Phase 3: Intelligent Failover (Week 3)

**Goal**: Auto-failover in <60 seconds

**Modules**:
- ✓ region_failover.py (Brick 12)

**Commands**:
- ✓ azlin failover --to westus2
- ✓ azlin failover --auto
- ✓ azlin regions health

**Acceptance Criteria**:
- Auto-detect network failures (60-second timeout)
- Failover completes in <60 seconds (requirement met)
- Health checks accurate (95%+ confidence)

**Testing**:
- Unit tests: region_failover.py (60% coverage)
- Integration: Simulate failures, verify auto-failover
- E2E: Kill VM, verify auto-failover to healthy region

---

### Phase 4: Cross-Region Sync (Week 4)

**Goal**: 99.9% sync reliability

**Modules**:
- ✓ cross_region_sync.py (Brick 13)

**Commands**:
- ✓ azlin sync --source eastus --dest westus2
- ✓ azlin sync --all

**Acceptance Criteria**:
- Sync completes with 99.9% reliability (requirement met)
- Hybrid strategy (rsync <100MB, blob >100MB)
- Progress reporting with ETA

**Testing**:
- Unit tests: cross_region_sync.py (60% coverage)
- Integration: Sync 100MB, 500MB datasets
- E2E: Deploy → populate → sync → verify data integrity

---

### Phase 5: Polish & Documentation (Week 5)

**Goal**: Production-ready

**Tasks**:
- ✓ Complete documentation (README, architecture docs)
- ✓ E2E test suite (all commands)
- ✓ Performance benchmarks
- ✓ Security review
- ✓ User guide with examples

**Acceptance Criteria**:
- All tests passing (95%+ coverage)
- Documentation complete
- Performance targets met
- Security audit passed

---

## Data Flow

### Multi-Region Deployment Flow

```
1. User: azlin deploy --regions eastus,westus2,westeurope

2. CLI Entry Point (cli.py)
   ↓ Parse arguments with Click
   ↓ Validate regions (check ALLOWED_REGIONS)
   ↓ Create ParallelDeployer

3. ParallelDeployer.deploy_to_regions()
   ↓ Create asyncio.Semaphore(max_concurrent=10)
   ↓ For each region in parallel:
       ├─► _deploy_single_region("eastus")
       │   ├─► vm_provisioning.provision_vm(config, region="eastus")
       │   │   ├─► az vm create --region eastus
       │   │   ├─► Wait for VM ready (3-5 min)
       │   │   └─► Return VMInfo(ip=1.2.3.4)
       │   ├─► region_context.add_region("eastus", vm_name, ip)
       │   └─► Return DeploymentResult(status=SUCCESS)
       │
       ├─► _deploy_single_region("westus2")
       │   └─► [same as above, in parallel]
       │
       └─► _deploy_single_region("westeurope")
           └─► [same as above, in parallel]

   ↓ Aggregate results
   ↓ Return MultiRegionResult(success_rate=100%)

4. CLI displays results
   ✓ eastus: 1.2.3.4 (3m 12s)
   ✓ westus2: 5.6.7.8 (3m 45s)
   ✓ westeurope: 9.10.11.12 (4m 18s)

   Total: 4m 18s (parallel time = max(3m12s, 3m45s, 4m18s))

5. config_manager.save_config()
   ↓ Write to ~/.azlin/config.json
   ↓ chmod 600 config.json
```

### Failover Flow

```
1. User: azlin failover --to westus2

2. RegionFailover.check_health("eastus")
   ↓ Azure VM status: Running
   ↓ Network ping: Timeout (10s)
   ↓ SSH connect: Failed
   ↓ Return HealthCheckResult(is_healthy=False, failure_type=NETWORK_UNREACHABLE)

3. RegionFailover.evaluate_failover("eastus")
   ↓ FailureType: NETWORK_UNREACHABLE
   ↓ Confidence: 0.95 (95%)
   ↓ Should auto-failover: True
   ↓ Return FailoverDecision(should_auto_failover=True)

4. RegionFailover.execute_failover("eastus", "westus2")
   ↓ Check target health: Healthy
   ↓ Optional: CrossRegionSync.sync_directories()
   ↓ region_context.set_primary_region("westus2")
   ↓ config_manager.save_config()
   ↓ Optional: deallocate source VM
   ↓ Return FailoverResult(success=True, duration=52s)

5. CLI displays result
   ✓ Failover complete in 52s
   Primary: westus2 (5.6.7.8)
```

### Sync Flow

```
1. User: azlin sync --source eastus --dest westus2 --paths /home/azureuser/project

2. CrossRegionSync.estimate_transfer_size("vm-eastus", ["/home/azureuser/project"])
   ↓ SSH to vm-eastus
   ↓ Run: du -sb /home/azureuser/project
   ↓ Return: 342000000 bytes (342MB)

3. CrossRegionSync.choose_strategy(342000000)
   ↓ Size > 100MB?
   ↓ Yes → Return SyncStrategy.AZURE_BLOB

4. CrossRegionSync._sync_via_blob("vm-eastus", "vm-westus2", paths)
   ↓ Create staging container: azlin-sync-20251201
   ↓ SSH to vm-eastus
   ↓ Run: az storage blob upload-batch --source /home/azureuser/project --destination azlin-sync-20251201
   ↓ Progress: [████████░] 85% (290MB/342MB) ETA: 1m 12s
   ↓ Upload complete: 3m 45s
   ↓
   ↓ SSH to vm-westus2
   ↓ Run: az storage blob download-batch --source azlin-sync-20251201 --destination /home/azureuser/project
   ↓ Progress: [█████████░] 92% (315MB/342MB) ETA: 32s
   ↓ Download complete: 2m 18s
   ↓
   ↓ Run: az storage container delete --name azlin-sync-20251201
   ↓ Return: SyncResult(strategy=AZURE_BLOB, files=125, bytes=342MB, duration=6m22s)

5. CLI displays result
   ✓ Sync complete in 6m 22s
   Files synced: 125
   Data transferred: 342MB
   Success rate: 100%
```

---

## Error Handling

### Error Types and Handling Strategy

| Error Type | Example | Handling Strategy | Retry? | User Action |
|-----------|---------|------------------|--------|-------------|
| **Network Failure** | Region unreachable | Auto-failover to healthy region | No | None (automatic) |
| **Capacity Unavailable** | VM size not available | Try alternative region | Yes (2x) | Suggest alternative |
| **Permission Denied** | Azure RBAC issue | Display clear error message | No | Check az permissions |
| **Timeout** | VM provisioning >10min | Cancel and report failure | No | Try smaller VM size |
| **SSH Connection Failed** | Port 22 blocked | Check NSG rules, suggest fixes | Yes (3x) | Check firewall |
| **Sync Failure** | rsync/blob error | Log error, continue other files | Yes (3x) | Check disk space |
| **Invalid Config** | Corrupted config.json | Use defaults, backup old config | No | Review config file |
| **Azure API Error** | Rate limit exceeded | Exponential backoff | Yes (5x) | Wait and retry |

### Error Response Format

```python
@dataclass
class ErrorResult:
    """Standard error result across all modules."""
    error_type: str           # "NetworkFailure", "CapacityUnavailable", etc.
    error_message: str        # Human-readable message
    resolution_steps: List[str]  # Actionable steps for user
    retry_possible: bool      # Can this operation be retried?
    log_details: str          # Technical details for debugging

# Example usage:
error = ErrorResult(
    error_type="CapacityUnavailable",
    error_message="Standard_B2s not available in eastus",
    resolution_steps=[
        "Try alternative region: westus2",
        "Try alternative VM size: Standard_B2ms",
        "Check Azure capacity: az vm list-skus --location eastus"
    ],
    retry_possible=True,
    log_details="Azure API: SkuNotAvailable in region eastus"
)
```

### Graceful Degradation

**Principle**: Partial success is better than total failure.

```python
# Example: Deploy to 3 regions, 1 fails
result = await deployer.deploy_to_regions(
    regions=["eastus", "westus2", "westeurope"],
    vm_config=vm_config
)

# Result: 2/3 succeeded (66.7%)
# Action: Report success for eastus + westus2
#         Show error for westeurope with alternatives
#         Exit code: 1 (partial failure)
```

---

## Testing Strategy

### Test Pyramid (60/30/10)

```
        ┌─────────┐
        │   E2E   │  10% - Full workflows (expensive, slow)
        │  (15)   │  - Real Azure deployments
        └─────────┘  - Multi-region scenarios
       ┌───────────┐
       │Integration│  30% - Multi-module (moderate cost)
       │   (45)    │  - Mocked Azure API
       └───────────┘  - SSH mocking
      ┌─────────────┐
      │    Unit     │  60% - Single module (fast, free)
      │    (90)     │  - Pure functions
      └─────────────┘  - Isolated logic
```

### Test Coverage by Module

#### parallel_deployer.py

**Unit Tests (60%)**:
- `test_deployment_result_creation()`
- `test_multi_region_result_success_rate()`
- `test_deploy_to_regions_empty_list_raises_error()`
- `test_deploy_single_region_timeout_handling()`

**Integration Tests (30%)**:
- `test_deploy_to_multiple_regions_with_mock_azure()`
- `test_deploy_with_partial_failure()`
- `test_deploy_respects_max_concurrent_limit()`

**E2E Tests (10%)**:
- `test_deploy_to_3_real_azure_regions()`
- `test_deploy_performance_under_10_minutes()`

#### region_failover.py

**Unit Tests (60%)**:
- `test_health_check_result_creation()`
- `test_evaluate_failover_auto_decision()`
- `test_evaluate_failover_manual_decision()`
- `test_failure_type_classification()`

**Integration Tests (30%)**:
- `test_check_health_with_mock_azure_and_ssh()`
- `test_execute_failover_with_confirmation()`
- `test_failover_with_sync_enabled()`

**E2E Tests (10%)**:
- `test_failover_from_unhealthy_to_healthy_region()`
- `test_auto_failover_completes_under_60_seconds()`

#### cross_region_sync.py

**Unit Tests (60%)**:
- `test_sync_result_creation()`
- `test_choose_strategy_small_files_uses_rsync()`
- `test_choose_strategy_large_files_uses_blob()`
- `test_estimate_transfer_size_calculation()`

**Integration Tests (30%)**:
- `test_sync_via_rsync_with_mock_ssh()`
- `test_sync_via_blob_with_mock_azure()`
- `test_sync_with_progress_reporting()`

**E2E Tests (10%)**:
- `test_sync_100mb_dataset_between_real_regions()`
- `test_sync_reliability_99_9_percent()`

#### region_context.py

**Unit Tests (60%)**:
- `test_region_metadata_creation()`
- `test_add_region_to_config()`
- `test_get_primary_region()`
- `test_set_primary_region_unsets_previous()`

**Integration Tests (30%)**:
- `test_add_region_creates_azure_tags()`
- `test_sync_from_azure_tags_updates_local_config()`
- `test_remove_region_cleans_up_tags()`

**E2E Tests (10%)**:
- `test_full_region_lifecycle_add_use_remove()`

### Mock Strategy

**Azure CLI Mocking**:
```python
# tests/mocks/azure_mock.py
class MockAzureCLI:
    """Mock Azure CLI responses."""

    @staticmethod
    def vm_create_success(region: str) -> Dict[str, Any]:
        return {
            "name": f"vm-{region}-test",
            "publicIpAddress": f"1.2.3.{hash(region) % 255}",
            "location": region,
            "provisioningState": "Succeeded"
        }

    @staticmethod
    def vm_create_capacity_unavailable(region: str) -> Dict[str, Any]:
        return {
            "error": {
                "code": "SkuNotAvailable",
                "message": f"Standard_B2s not available in {region}"
            }
        }
```

**SSH Mocking**:
```python
# tests/mocks/ssh_mock.py
class MockSSHConnector:
    """Mock SSH connector for testing."""

    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure

    async def check_health(self, ip: str) -> bool:
        if self.simulate_failure:
            return False
        return True

    async def execute_remote_command(self, ip: str, command: str) -> str:
        if "du -sb" in command:
            return "342000000\t/home/azureuser/project"
        return ""
```

### Performance Benchmarks

**Targets**:
- Parallel deployment (3 regions): <10 minutes ✓
- Failover operation: <60 seconds ✓
- Data sync (100MB): <3 minutes (rsync)
- Data sync (500MB): <8 minutes (blob)
- Health check (single region): <10 seconds
- Config read/write: <100ms

**Benchmark Test**:
```python
# tests/benchmarks/test_performance.py
def test_parallel_deployment_performance():
    """Verify parallel deployment meets <10 min target."""
    start = time.time()

    result = asyncio.run(deployer.deploy_to_regions(
        regions=["eastus", "westus2", "westeurope"],
        vm_config=vm_config
    ))

    duration = time.time() - start
    assert duration < 600, f"Deployment took {duration}s (target: <600s)"
    assert result.success_rate == 1.0, "Not all regions succeeded"
```

---

## Performance Targets

### Explicit Requirements (Must Meet)

| Requirement | Target | Acceptance Criteria | Status |
|------------|--------|-------------------|--------|
| **Parallel Deployment** | <10 minutes (3+ regions) | Deploy to eastus, westus2, westeurope in <10 min | ✓ Design Complete |
| **Failover Completion** | <60 seconds | Complete failover (health check → switch) in <60s | ✓ Design Complete |
| **Sync Reliability** | 99.9% | 999/1000 sync operations succeed | ✓ Design Complete |

### Derived Targets (Best Effort)

| Metric | Target | Measurement |
|--------|--------|------------|
| **Health Check** | <10 seconds/region | Time for check_health() |
| **Small File Sync** | <3 minutes (100MB) | rsync performance |
| **Large File Sync** | <8 minutes (500MB) | Azure Blob performance |
| **Config Operations** | <100ms | Read/write config.json |
| **API Response Time** | <5 seconds | Azure CLI command execution |

### Performance Monitoring

**Built-in Metrics**:
```python
@dataclass
class PerformanceMetrics:
    """Performance metrics for operations."""
    operation_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    success: bool

    def meets_target(self, target_seconds: float) -> bool:
        return self.duration_seconds < target_seconds

# Usage:
metrics = PerformanceMetrics(
    operation_name="parallel_deployment",
    start_time=start,
    end_time=end,
    duration_seconds=duration,
    success=True
)

if not metrics.meets_target(600):
    logger.warning(f"Performance target missed: {metrics.operation_name} took {metrics.duration_seconds}s")
```

---

## Security Considerations

### Security Principles (Inherited from azlin)

1. **No Credentials in Code**: Delegate to az CLI and gh CLI
2. **Input Validation**: Whitelist regions, VM sizes, paths
3. **Secure File Operations**: Proper permissions (0600 for config)
4. **No shell=True**: Use argument lists for subprocess
5. **Timeout Enforcement**: All operations have timeouts
6. **Sanitized Logging**: Never log credentials or sensitive data

### New Security Concerns (Multi-Region)

#### 1. Cross-Region Data Transfer

**Concern**: Data traversing multiple regions could be intercepted.

**Mitigation**:
- rsync over SSH (encrypted)
- Azure Blob uses HTTPS (encrypted)
- No plaintext data transfer

#### 2. Region Metadata Tampering

**Concern**: Malicious actor modifies Azure tags or config.

**Mitigation**:
- Config file permissions: 0600 (user-only)
- Azure tags: Protected by Azure RBAC
- Verify tag authenticity on sync

#### 3. Failover Hijacking

**Concern**: Attacker triggers failover to malicious region.

**Mitigation**:
- Region whitelist (ALLOWED_REGIONS)
- Manual confirmation for ambiguous failures
- Audit log of all failover events

### Input Validation

```python
# Whitelist approach (SECURITY CRITICAL)
ALLOWED_REGIONS = [
    "eastus", "eastus2", "westus", "westus2", "centralus",
    "northeurope", "westeurope", "uksouth", "ukwest",
    "southeastasia", "eastasia", "australiaeast", "japaneast"
]

def validate_regions(regions: List[str]) -> List[str]:
    """Validate all regions are allowed."""
    invalid = [r for r in regions if r not in ALLOWED_REGIONS]
    if invalid:
        raise ValueError(f"Invalid regions: {invalid}. Allowed: {ALLOWED_REGIONS}")
    return regions
```

---

## Appendix A: Config Schema

### Enhanced config.json Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "version": {
      "type": "string",
      "description": "Config version (e.g., '2.0')"
    },
    "resource_group": {
      "type": "string",
      "description": "Base resource group name"
    },
    "default_region": {
      "type": "string",
      "description": "Default Azure region"
    },
    "default_vm_size": {
      "type": "string",
      "description": "Default VM size"
    },
    "regions": {
      "type": "array",
      "description": "Multi-region metadata",
      "items": {
        "type": "object",
        "properties": {
          "region": {"type": "string"},
          "vm_name": {"type": "string"},
          "public_ip": {"type": "string"},
          "resource_group": {"type": "string"},
          "created_at": {"type": "string", "format": "date-time"},
          "last_health_check": {"type": "string", "format": "date-time"},
          "is_primary": {"type": "boolean"},
          "tags": {"type": "object"}
        },
        "required": ["region", "vm_name", "resource_group", "created_at"]
      }
    }
  },
  "required": ["version", "resource_group"]
}
```

---

## Appendix B: Azure Tag Standards

### Tag Format

```
azlin:region=<region>           # Region identifier
azlin:primary=true              # Primary region marker
azlin:created_at=<timestamp>    # Creation timestamp
azlin:vm_type=dev               # VM type (dev, prod, test)
```

### Example Tag Commands

```bash
# Add region tag:
az tag create \
  --resource-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<vm> \
  --tags azlin:region=eastus azlin:primary=true

# Query VMs by region tag:
az vm list \
  --query "[?tags.\"azlin:region\"=='eastus']" \
  --output table

# Update primary region:
az tag update \
  --resource-id <vm-id> \
  --operation Merge \
  --tags azlin:primary=true
```

---

## Appendix C: Example Workflows

### Workflow 1: Deploy Multi-Region for HA

```bash
# Step 1: Deploy to 3 regions for high availability
azlin deploy --regions eastus,westus2,westeurope --primary eastus

# Output:
# ✓ Deployment complete in 4m 18s
#   Success: 3/3 regions (100%)
#   Primary: eastus (1.2.3.4)

# Step 2: Verify all regions healthy
azlin regions health

# Output:
# ✓ Health Summary: 3/3 regions healthy (100%)

# Step 3: Work on primary region
azlin ssh  # Connects to eastus (primary)

# Step 4: If primary fails, auto-failover
# (Azure outage in eastus)

azlin failover --auto

# Output:
# ✗ Primary region (eastus) unhealthy
# ✓ Auto-failover to westus2 (confidence: 95%)
# ✓ Failover complete in 52s
```

### Workflow 2: Gradual Multi-Region Rollout

```bash
# Step 1: Start with single region
azlin new --region eastus

# Step 2: Add second region later
azlin regions add --region westus2

# Step 3: Sync data from primary
azlin sync --source eastus --dest westus2 --paths /home/azureuser/project

# Output:
# ✓ Sync complete in 3m 12s
#   Files synced: 125
#   Data transferred: 342MB

# Step 4: Add third region
azlin regions add --region westeurope

# Step 5: Sync to all regions
azlin sync --all --paths /home/azureuser/project
```

### Workflow 3: Disaster Recovery Test

```bash
# Step 1: Deploy multi-region
azlin deploy --regions eastus,westus2 --primary eastus

# Step 2: Populate data on primary
azlin ssh --region eastus
# (create test data)

# Step 3: Sync to backup region
azlin sync --source eastus --dest westus2

# Step 4: Simulate primary failure (stop VM)
az vm stop --name vm-eastus --resource-group azlin-vms-eastus

# Step 5: Test failover
azlin failover --to westus2 --yes

# Step 6: Verify data integrity on new primary
azlin ssh --region westus2
# (check test data exists)

# Step 7: Restore original primary
az vm start --name vm-eastus --resource-group azlin-vms-eastus
azlin sync --source westus2 --dest eastus  # Sync back
azlin regions set-primary eastus
```

---

## Conclusion

This architecture specification provides a complete blueprint for implementing multi-region orchestration in azlin. The design follows azlin's core philosophy of ruthless simplicity, brick architecture, and security-first principles while enabling advanced features like parallel deployment, intelligent failover, and cross-region synchronization.

**Key Design Decisions**:
- ✓ Python asyncio for true parallel deployment (3+ regions <10 min)
- ✓ Hybrid failover (auto for clear failures, manual for ambiguous)
- ✓ Hybrid sync (rsync <100MB, Azure Blob >100MB)
- ✓ Config + Azure tags for region-aware context
- ✓ Four new self-contained bricks (11-14)
- ✓ Backward compatible with existing single-region workflows

**Next Steps**:
1. Documentation-writer agent: Create user documentation
2. Tester agent: Design comprehensive test suite
3. Builder agent: Implement Phase 1 (Foundation MVP)

**Ready for**: Step 6 - Documentation and Testing Design

---

**Document Status**: ✓ Architecture Complete
**Review Required**: Yes (PM approval before implementation)
**Estimated Implementation**: 5 weeks (4 modules + polish)
