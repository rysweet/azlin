"""NFS quota monitoring and auto-expansion for Azure Files shares.

Philosophy:
- Check quota during connect/new/status operations
- Alert when <10% free space remaining
- Interactive prompt for quota expansion
- Use az storage share-rm update for expansion
- Show cost transparency (+$15.36/month per 100GB)

Public API:
    NFSQuotaManager: Main quota operations class
    QuotaInfo: Quota and usage information
    QuotaWarning: Warning threshold information
    ExpansionResult: Result of quota expansion
"""

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import ClassVar

logger = logging.getLogger(__name__)


@dataclass
class QuotaInfo:
    """NFS share quota and usage information."""

    storage_account: str
    share_name: str
    resource_group: str
    quota_gb: int  # Total quota
    used_gb: float  # Current usage
    available_gb: float  # Available space
    utilization_percent: float  # Usage percentage


@dataclass
class QuotaWarning:
    """Quota warning threshold information."""

    threshold_percent: float  # Warning threshold (default: 90%)
    is_warning: bool  # True if above threshold
    message: str  # User-facing warning message


@dataclass
class ExpansionResult:
    """Result of quota expansion operation."""

    success: bool
    storage_account: str
    share_name: str
    old_quota_gb: int
    new_quota_gb: int
    expansion_gb: int
    cost_increase_monthly: float
    errors: list[str] = field(default_factory=list)


class NFSQuotaManager:
    """NFS quota monitoring and expansion.

    All methods are classmethods for brick-style API.
    No instance state maintained.
    """

    # Cost constant (Premium tier)
    COST_PER_GB_PREMIUM: ClassVar[float] = 0.1536

    # Warning threshold
    WARNING_THRESHOLD_PERCENT: ClassVar[float] = 90.0

    @classmethod
    def check_vm_nfs_storage(
        cls, vm_name: str, resource_group: str, timeout: int = 60
    ) -> tuple[str, str, str] | None:
        """Check if VM uses NFS storage and return storage info.

        Uses vm run-command to check if /home/azureuser is NFS mounted.

        Args:
            vm_name: VM name
            resource_group: Resource group
            timeout: Command timeout in seconds

        Returns:
            Tuple of (storage_account, share_name, mount_point) if NFS mounted
            None if not using NFS

        Raises:
            subprocess.CalledProcessError: If run-command fails critically
        """
        # Use az vm run-command to check mount status
        check_script = "mount | grep '/home/azureuser' | grep -E 'nfs|file.core.windows.net'"

        cmd = [
            "az",
            "vm",
            "run-command",
            "invoke",
            "--resource-group",
            resource_group,
            "--name",
            vm_name,
            "--command-id",
            "RunShellScript",
            "--scripts",
            check_script,
            "--output",
            "json",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=timeout
            )

            # Parse output to extract NFS endpoint
            # Format: "storageacct.file.core.windows.net:/storageacct/home on /home/azureuser type nfs4 (...)"
            output_data = json.loads(result.stdout)
            stdout_content = output_data.get("value", [{}])[0].get("message", "")

            if "[stdout]" in stdout_content:
                stdout_content = stdout_content.split("[stdout]")[1].split("[stderr]")[0]

            # Extract storage account and share from NFS endpoint
            match = re.search(
                r"([a-z0-9]+)\.file\.core\.windows\.net:/([a-z0-9]+)/([a-z0-9\-]+)",
                stdout_content,
            )
            if match:
                storage_account = match.group(1)
                # Azure Files NFS format: account.file.core.windows.net:/account/sharename
                share_name = match.group(3)  # The share name (usually "home")
                return (storage_account, share_name, "/home/azureuser")

            return None

        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            json.JSONDecodeError,
            KeyError,
        ) as e:
            logger.debug(f"NFS check failed for {vm_name}: {e}")
            return None

    @classmethod
    def get_nfs_quota_info(
        cls, storage_account: str, share_name: str, resource_group: str, timeout: int = 30
    ) -> QuotaInfo:
        """Get NFS share quota and usage information.

        Uses:
        - az storage share-rm show for quota
        - az storage share-rm stats for usage

        Args:
            storage_account: Storage account name
            share_name: Share name
            resource_group: Resource group
            timeout: Command timeout in seconds

        Returns:
            QuotaInfo with quota and usage details

        Raises:
            subprocess.CalledProcessError: If Azure CLI fails
        """
        # Get quota
        quota_cmd = [
            "az",
            "storage",
            "share-rm",
            "show",
            "--storage-account",
            storage_account,
            "--name",
            share_name,
            "--resource-group",
            resource_group,
            "--query",
            "shareQuota",
            "--output",
            "tsv",
        ]

        result = subprocess.run(
            quota_cmd, capture_output=True, text=True, check=True, timeout=timeout
        )
        quota_gb = int(result.stdout.strip())

        # Get usage via share stats
        stats_cmd = [
            "az",
            "storage",
            "share-rm",
            "stats",
            "--storage-account",
            storage_account,
            "--name",
            share_name,
            "--resource-group",
            resource_group,
            "--query",
            "shareUsageBytes",
            "--output",
            "tsv",
        ]

        try:
            result = subprocess.run(
                stats_cmd, capture_output=True, text=True, check=True, timeout=timeout
            )
            used_bytes = int(result.stdout.strip())
            used_gb = used_bytes / (1024**3)
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.warning(f"Could not get usage stats for {storage_account}/{share_name}: {e}")
            # If stats fails, we can't determine usage accurately
            # Set to 0 and let caller handle
            used_gb = 0.0

        available_gb = quota_gb - used_gb
        utilization_percent = (used_gb / quota_gb * 100) if quota_gb > 0 else 0.0

        return QuotaInfo(
            storage_account=storage_account,
            share_name=share_name,
            resource_group=resource_group,
            quota_gb=quota_gb,
            used_gb=used_gb,
            available_gb=available_gb,
            utilization_percent=utilization_percent,
        )

    @classmethod
    def check_quota_warning(cls, quota_info: QuotaInfo) -> QuotaWarning:
        """Check if quota usage exceeds warning threshold.

        Args:
            quota_info: Quota information

        Returns:
            QuotaWarning with threshold status and message
        """
        is_warning = quota_info.utilization_percent >= cls.WARNING_THRESHOLD_PERCENT

        if is_warning:
            message = (
                f"⚠️  NFS quota warning: {quota_info.utilization_percent:.1f}% used "
                f"({quota_info.used_gb:.1f}GB / {quota_info.quota_gb}GB)\n"
                f"   Available: {quota_info.available_gb:.1f}GB remaining"
            )
        else:
            message = ""

        return QuotaWarning(
            threshold_percent=cls.WARNING_THRESHOLD_PERCENT,
            is_warning=is_warning,
            message=message,
        )

    @classmethod
    def prompt_and_expand_quota(
        cls, quota_info: QuotaInfo, expansion_gb: int = 100
    ) -> bool:
        """Prompt user and expand quota if confirmed.

        Args:
            quota_info: Current quota information
            expansion_gb: Amount to expand (default: 100GB)

        Returns:
            True if user confirmed and expansion initiated
            False if user declined
        """
        import click

        # Calculate cost
        cost_increase = expansion_gb * cls.COST_PER_GB_PREMIUM
        new_quota = quota_info.quota_gb + expansion_gb

        click.echo(f"\nNFS Storage Quota Expansion:")
        click.echo(f"  Storage: {quota_info.storage_account}/{quota_info.share_name}")
        click.echo(f"  Current: {quota_info.quota_gb}GB")
        click.echo(f"  New: {new_quota}GB (+{expansion_gb}GB)")
        click.echo(f"  Cost increase: +${cost_increase:.2f}/month")
        click.echo()

        return click.confirm("Expand quota now?", default=True)

    @classmethod
    def expand_nfs_quota(
        cls,
        storage_account: str,
        share_name: str,
        resource_group: str,
        new_quota_gb: int,
        timeout: int = 60,
    ) -> ExpansionResult:
        """Expand NFS share quota.

        Uses: az storage share-rm update --quota <new_quota>

        Args:
            storage_account: Storage account name
            share_name: Share name
            resource_group: Resource group
            new_quota_gb: New quota in GB
            timeout: Command timeout in seconds

        Returns:
            ExpansionResult with expansion details
        """
        # Get current quota first
        try:
            quota_info = cls.get_nfs_quota_info(
                storage_account, share_name, resource_group, timeout
            )
            old_quota = quota_info.quota_gb
        except Exception as e:
            return ExpansionResult(
                success=False,
                storage_account=storage_account,
                share_name=share_name,
                old_quota_gb=0,
                new_quota_gb=new_quota_gb,
                expansion_gb=0,
                cost_increase_monthly=0.0,
                errors=[f"Failed to get current quota: {e}"],
            )

        # Validate new quota is larger
        if new_quota_gb <= old_quota:
            return ExpansionResult(
                success=False,
                storage_account=storage_account,
                share_name=share_name,
                old_quota_gb=old_quota,
                new_quota_gb=new_quota_gb,
                expansion_gb=0,
                cost_increase_monthly=0.0,
                errors=[
                    f"New quota ({new_quota_gb}GB) must be larger than current ({old_quota}GB)"
                ],
            )

        # Expand quota
        expansion_gb = new_quota_gb - old_quota
        cost_increase = expansion_gb * cls.COST_PER_GB_PREMIUM

        cmd = [
            "az",
            "storage",
            "share-rm",
            "update",
            "--storage-account",
            storage_account,
            "--name",
            share_name,
            "--resource-group",
            resource_group,
            "--quota",
            str(new_quota_gb),
            "--output",
            "json",
        ]

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)

            logger.info(
                f"Expanded quota for {storage_account}/{share_name}: {old_quota}GB -> {new_quota_gb}GB"
            )

            return ExpansionResult(
                success=True,
                storage_account=storage_account,
                share_name=share_name,
                old_quota_gb=old_quota,
                new_quota_gb=new_quota_gb,
                expansion_gb=expansion_gb,
                cost_increase_monthly=cost_increase,
                errors=[],
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            return ExpansionResult(
                success=False,
                storage_account=storage_account,
                share_name=share_name,
                old_quota_gb=old_quota,
                new_quota_gb=new_quota_gb,
                expansion_gb=expansion_gb,
                cost_increase_monthly=cost_increase,
                errors=[f"Expansion failed: {error_msg}"],
            )


# Public API
__all__ = [
    "NFSQuotaManager",
    "QuotaInfo",
    "QuotaWarning",
    "ExpansionResult",
]
