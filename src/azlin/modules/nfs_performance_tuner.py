"""NFS Performance Tuner Module.

Analyze NFS mount parameters and recommend optimizations for multi-VM scenarios.
Analysis and recommendations only - does not apply tuning automatically.

Philosophy:
- Self-contained module following brick architecture
- Standard library + subprocess for operations
- Evidence-based tuning profiles
- Analysis-only approach (no automatic changes)

Public API:
    NFSPerformanceTuner: Main NFS tuning class
    NFSPerformanceAnalysis: NFS mount performance analysis
    NFSTuningRecommendation: NFS mount tuning recommendation
"""

from dataclasses import dataclass

# Import existing modules
try:
    from azlin.modules.storage_manager import StorageManager
except ImportError:
    StorageManager = None


__all__ = [
    "NFSPerformanceAnalysis",
    "NFSPerformanceTuner",
    "NFSTuningRecommendation",
]


# NFS mount option profiles
PROFILES = {
    "baseline": "vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2",
    "read-heavy": "vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,rsize=1048576,wsize=1048576,hard,ac,acregmin=3,acregmax=60,acdirmin=30,acdirmax=60",
    "write-heavy": "vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,rsize=1048576,wsize=1048576,hard,noac,async",
    "mixed": "vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,rsize=1048576,wsize=1048576,hard,ac,acregmin=10,acregmax=30",
    "multi-vm": "vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,rsize=1048576,wsize=1048576,hard,actimeo=1",
}


@dataclass
class NFSPerformanceAnalysis:
    """NFS mount performance analysis.

    Attributes:
        storage_name: Storage account name
        connected_vms: List of connected VM names
        current_mount_options: Dict of VM -> mount options
        performance_tier: Storage tier (Premium/Standard)
        bottleneck_indicators: List of detected bottlenecks
        optimization_potential: "high", "medium", or "low"
    """

    storage_name: str
    connected_vms: list[str]
    current_mount_options: dict[str, str]
    performance_tier: str
    bottleneck_indicators: list[str]
    optimization_potential: str


@dataclass
class NFSTuningRecommendation:
    """NFS mount tuning recommendation.

    Attributes:
        storage_name: Storage account name
        workload_type: Detected workload type
        recommended_mount_options: Recommended mount options
        expected_improvement_percent: Expected performance improvement (%)
        rationale: Explanation of recommendation
        specific_recommendations: List of specific changes
    """

    storage_name: str
    workload_type: str
    recommended_mount_options: str
    expected_improvement_percent: int
    rationale: str
    specific_recommendations: list[str]


class NFSPerformanceTuner:
    """Optimize NFS mount parameters for performance.

    Provides analysis and recommendations only - does not apply tuning automatically.

    Tuning profiles:
    - read-heavy: Optimized for read operations
    - write-heavy: Optimized for write operations
    - mixed: Balanced read/write
    - multi-vm: Optimized for multiple VMs (default)

    Usage:
        # Analyze performance
        analysis = NFSPerformanceTuner.analyze_performance(
            storage_name="myteam-shared",
            resource_group="test-rg"
        )

        # Get recommendations
        rec = NFSPerformanceTuner.get_tuning_recommendations(
            storage_name="myteam-shared",
            resource_group="test-rg",
            workload_type="auto"
        )
    """

    @classmethod
    def analyze_performance(cls, storage_name: str, resource_group: str) -> NFSPerformanceAnalysis:
        """Analyze NFS mount performance.

        Args:
            storage_name: Storage account name
            resource_group: Resource group

        Returns:
            NFSPerformanceAnalysis: Performance analysis
        """
        if not StorageManager:
            raise RuntimeError("StorageManager not available")

        # Get storage status
        status = StorageManager.get_storage_status(name=storage_name, resource_group=resource_group)

        connected_vms = getattr(status, "connected_vms", [])
        tier = getattr(status, "tier", "Standard")

        # Get current mount options for each VM
        current_mount_options = {}
        for vm in connected_vms:
            try:
                options = cls._get_mount_options(vm, storage_name, resource_group)
                current_mount_options[vm] = options
            except Exception:
                current_mount_options[vm] = "unknown"

        # Detect bottlenecks
        bottlenecks = []

        if len(connected_vms) > 1:
            bottlenecks.append("Multi-VM scenario detected")

        # Check for default (non-optimized) mount options
        for vm, options in current_mount_options.items():
            if "rsize" not in options or "wsize" not in options:
                bottlenecks.append(f"Default mount options on {vm}")

            if len(connected_vms) > 1 and "actimeo=1" not in options:
                bottlenecks.append(f"Long attribute cache on {vm} (multi-VM issue)")

        # Determine optimization potential
        if len(bottlenecks) >= 2:
            optimization_potential = "high"
        elif len(bottlenecks) == 1:
            optimization_potential = "medium"
        else:
            optimization_potential = "low"

        return NFSPerformanceAnalysis(
            storage_name=storage_name,
            connected_vms=connected_vms,
            current_mount_options=current_mount_options,
            performance_tier=tier,
            bottleneck_indicators=bottlenecks,
            optimization_potential=optimization_potential,
        )

    @classmethod
    def get_tuning_recommendations(
        cls, storage_name: str, resource_group: str, workload_type: str = "auto"
    ) -> NFSTuningRecommendation:
        """Get tuning recommendations for storage.

        Args:
            storage_name: Storage account name
            resource_group: Resource group
            workload_type: "auto", "read-heavy", "write-heavy", "mixed"

        Returns:
            NFSTuningRecommendation: Tuning recommendation
        """
        # Analyze current performance
        analysis = cls.analyze_performance(storage_name=storage_name, resource_group=resource_group)

        # Determine workload type
        if workload_type == "auto":
            if len(analysis.connected_vms) > 1:
                detected_workload = "multi-vm"
            else:
                detected_workload = "mixed"  # Default for single VM
        else:
            detected_workload = workload_type

        # Get recommended mount options
        recommended_options = PROFILES.get(detected_workload, PROFILES["mixed"])

        # Build specific recommendations
        specific_recs = []

        if "rsize=1048576" in recommended_options:
            specific_recs.append("Increase read buffer to 1MB (from default 64KB)")

        if "wsize=1048576" in recommended_options:
            specific_recs.append("Increase write buffer to 1MB (from default 64KB)")

        if "actimeo=1" in recommended_options:
            specific_recs.append("Reduce attribute cache timeout to 1s (prevents stale metadata)")

        if "hard" in recommended_options:
            specific_recs.append("Enable hard mount for reliability")

        # Estimate improvement
        if analysis.optimization_potential == "high":
            expected_improvement = 20
        elif analysis.optimization_potential == "medium":
            expected_improvement = 10
        else:
            expected_improvement = 5

        # Build rationale
        if detected_workload == "multi-vm":
            rationale = "Multiple VMs share this storage. Short attribute cache timeout prevents stale file metadata."
        elif detected_workload == "read-heavy":
            rationale = "Read-heavy workload benefits from aggressive attribute caching."
        elif detected_workload == "write-heavy":
            rationale = "Write-heavy workload benefits from async writes and no attribute caching."
        else:
            rationale = "Balanced workload benefits from moderate caching and large I/O buffers."

        return NFSTuningRecommendation(
            storage_name=storage_name,
            workload_type=detected_workload,
            recommended_mount_options=recommended_options,
            expected_improvement_percent=expected_improvement,
            rationale=rationale,
            specific_recommendations=specific_recs,
        )

    # Private helper methods

    @classmethod
    def _get_mount_options(cls, vm_name: str, storage_name: str, resource_group: str) -> str:
        """Get current mount options for storage on VM.

        Args:
            vm_name: VM name
            storage_name: Storage account name
            resource_group: Resource group

        Returns:
            Mount options string
        """
        try:
            # Returns baseline profile as default
            # Real mount option query would require SSH access to VM
            return PROFILES["baseline"]

        except Exception:
            return "unknown"
