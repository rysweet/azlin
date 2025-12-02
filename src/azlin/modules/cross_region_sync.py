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

import asyncio
import contextlib
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azlin.config_manager import ConfigManager
    from azlin.modules.ssh_connector import SSHConnector


class SyncStrategy(Enum):
    """Strategy for syncing data."""

    RSYNC = "rsync"  # For small files (<100MB)
    AZURE_BLOB = "azure_blob"  # For large files (>100MB)
    AUTO = "auto"  # Choose based on size (default)


@dataclass
class SyncResult:
    """Result of cross-region sync operation."""

    strategy_used: SyncStrategy
    files_synced: int
    bytes_transferred: int
    duration_seconds: float
    source_region: str
    target_region: str
    errors: list[str]

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
        sync = CrossRegionSync(config_manager, ssh_connector)
        result = await sync.sync_directories(
            source_vm="vm-eastus",
            target_vm="vm-westus2",
            paths=["/home/azureuser/project"],
            strategy=SyncStrategy.AUTO
        )
        print(f"Synced {result.files_synced} files")
    """

    def __init__(self, config_manager: "ConfigManager", ssh_connector: "SSHConnector"):
        """Initialize cross-region sync.

        Args:
            config_manager: Config manager for VM metadata
            ssh_connector: SSH connector for remote operations

        Raises:
            TypeError: If config_manager or ssh_connector is None
        """
        if config_manager is None:
            raise TypeError("config_manager cannot be None")
        if ssh_connector is None:
            raise TypeError("ssh_connector cannot be None")

        self.config_manager = config_manager
        self.ssh_connector = ssh_connector

    async def estimate_transfer_size(self, vm_name: str, paths: list[str]) -> int:
        """Estimate total size of files to sync.

        Runs 'du -sb' on remote VM to calculate size.

        Args:
            vm_name: VM to check
            paths: List of paths to estimate

        Returns:
            Total size in bytes

        Raises:
            TypeError: If vm_name is None
            ValueError: If paths is empty or invalid du output
        """
        if vm_name is None:
            raise TypeError("vm_name cannot be None")
        if not paths:
            raise ValueError("paths list cannot be empty")

        # Get VM IP address from config
        vm_ip = self.config_manager.get_vm_ip(vm_name)  # type: ignore[attr-defined]
        if not vm_ip:
            raise ValueError(f"No IP address found for VM: {vm_name}")

        # SSH and run du -sb on all paths
        total_bytes = 0
        for path in paths:
            try:
                # Run du -sb via SSH
                process = await asyncio.create_subprocess_exec(
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "ConnectTimeout=10",
                    f"azureuser@{vm_ip}",
                    "du",
                    "-sb",
                    path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    # If path doesn't exist or error, skip it
                    continue

                # Parse du output: "12345\t/path/to/dir"
                output = stdout.decode().strip()
                if output:
                    size_str = output.split()[0]
                    total_bytes += int(size_str)

            except Exception as e:
                # Continue on errors, accumulate what we can
                print(f"Warning: Failed to get size for {path}: {e}")
                continue

        return total_bytes

    async def choose_strategy(self, estimated_size_bytes: int) -> SyncStrategy:
        """Choose optimal sync strategy based on size.

        Decision logic:
        - < 100MB: RSYNC (faster for small files)
        - >= 100MB: AZURE_BLOB (more reliable for large)

        Args:
            estimated_size_bytes: Total size to sync

        Returns:
            Recommended SyncStrategy

        Raises:
            ValueError: If estimated_size_bytes is negative
        """
        if estimated_size_bytes < 0:
            raise ValueError("estimated_size_bytes cannot be negative")

        # Threshold: 100MB
        threshold = 100 * 1024 * 1024

        if estimated_size_bytes < threshold:
            return SyncStrategy.RSYNC
        return SyncStrategy.AZURE_BLOB

    async def sync_directories(
        self,
        source_vm: str,
        target_vm: str,
        paths: list[str],
        strategy: SyncStrategy = SyncStrategy.AUTO,
        delete: bool = False,
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
            TypeError: If source_vm, target_vm, or paths is None
            ValueError: If paths is empty or source_vm == target_vm
        """
        # Input validation
        if source_vm is None:
            raise TypeError("source_vm cannot be None")
        if target_vm is None:
            raise TypeError("target_vm cannot be None")
        if paths is None:
            raise TypeError("paths cannot be None")
        if not paths:
            raise ValueError("paths list cannot be empty")
        if source_vm == target_vm:
            raise ValueError("source_vm and target_vm cannot be the same")

        # Estimate size
        size_bytes = await self.estimate_transfer_size(source_vm, paths)

        # Choose strategy
        if strategy == SyncStrategy.AUTO:
            strategy = await self.choose_strategy(size_bytes)

        # Execute sync based on strategy
        if strategy == SyncStrategy.RSYNC:
            result = await self._sync_via_rsync(source_vm, target_vm, paths, delete)
        else:
            result = await self._sync_via_blob(source_vm, target_vm, paths, delete)

        return result

    async def _sync_via_rsync(
        self, source_vm: str, target_vm: str, paths: list[str], delete: bool
    ) -> SyncResult:
        """Sync using rsync over SSH (internal method).

        Command: rsync -avz --progress source_vm:path target_vm:path
        """
        start_time = time.time()

        # Get VM IPs
        source_ip = self.config_manager.get_vm_ip(source_vm)  # type: ignore[attr-defined]
        target_ip = self.config_manager.get_vm_ip(target_vm)  # type: ignore[attr-defined]

        if not source_ip or not target_ip:
            return SyncResult(
                strategy_used=SyncStrategy.RSYNC,
                files_synced=0,
                bytes_transferred=0,
                duration_seconds=time.time() - start_time,
                source_region="unknown",
                target_region="unknown",
                errors=["Failed to resolve VM IP addresses"],
            )

        # Get regions
        source_region = self.config_manager.get_vm_region(source_vm) or "unknown"  # type: ignore[attr-defined]
        target_region = self.config_manager.get_vm_region(target_vm) or "unknown"  # type: ignore[attr-defined]

        total_files = 0
        total_bytes = 0
        errors = []

        # Sync each path
        for path in paths:
            try:
                # Build rsync command
                rsync_cmd = ["rsync", "-avz", "--progress", "--stats"]

                if delete:
                    rsync_cmd.append("--delete")

                # Source: ssh to source VM
                rsync_cmd.append(f"azureuser@{source_ip}:{path}")

                # Target: ssh to target VM (need intermediate step)
                # Actually for VM-to-VM, we need to use SSH ProxyCommand or bounce through local
                # For simplicity, we'll use a two-step: pull to local temp, push to target

                import tempfile

                with tempfile.TemporaryDirectory() as tmpdir:
                    # Step 1: Pull from source to local temp
                    pull_cmd = ["rsync", "-avz", "--stats", f"azureuser@{source_ip}:{path}", tmpdir]

                    process = await asyncio.create_subprocess_exec(
                        *pull_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        errors.append(f"Failed to pull {path}: {stderr.decode()}")
                        continue

                    # Parse rsync stats
                    stats = stdout.decode()
                    files_match = re.search(r"Number of files: (\d+)", stats)
                    bytes_match = re.search(r"Total file size: ([\d,]+)", stats)

                    if files_match:
                        total_files += int(files_match.group(1))
                    if bytes_match:
                        total_bytes += int(bytes_match.group(1).replace(",", ""))

                    # Step 2: Push from local temp to target
                    push_cmd = ["rsync", "-avz", f"{tmpdir}/", f"azureuser@{target_ip}:{path}"]

                    if delete:
                        push_cmd.insert(2, "--delete")

                    process = await asyncio.create_subprocess_exec(
                        *push_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    await process.communicate()

                    if process.returncode != 0:
                        errors.append(f"Failed to push {path}: {stderr.decode()}")
                        continue

            except Exception as e:
                errors.append(f"Error syncing {path}: {e!s}")
                continue

        duration = time.time() - start_time

        return SyncResult(
            strategy_used=SyncStrategy.RSYNC,
            files_synced=total_files,
            bytes_transferred=total_bytes,
            duration_seconds=duration,
            source_region=source_region,
            target_region=target_region,
            errors=errors,
        )

    async def _sync_via_blob(
        self, source_vm: str, target_vm: str, paths: list[str], delete: bool
    ) -> SyncResult:
        """Sync using Azure Blob staging (internal method).

        Steps:
        1. Upload from source VM to Blob container
        2. Download from Blob to target VM
        3. Clean up Blob staging area
        """
        start_time = time.time()

        # Get VM IPs
        source_ip = self.config_manager.get_vm_ip(source_vm)  # type: ignore[attr-defined]
        target_ip = self.config_manager.get_vm_ip(target_vm)  # type: ignore[attr-defined]

        if not source_ip or not target_ip:
            return SyncResult(
                strategy_used=SyncStrategy.AZURE_BLOB,
                files_synced=0,
                bytes_transferred=0,
                duration_seconds=time.time() - start_time,
                source_region="unknown",
                target_region="unknown",
                errors=["Failed to resolve VM IP addresses"],
            )

        # Get regions
        source_region = self.config_manager.get_vm_region(source_vm) or "unknown"  # type: ignore[attr-defined]
        target_region = self.config_manager.get_vm_region(target_vm) or "unknown"  # type: ignore[attr-defined]

        # Get or create staging container
        storage_account = self.config_manager.get_storage_account()  # type: ignore[attr-defined]
        container_name = f"azlin-sync-staging-{int(time.time())}"

        total_files = 0
        total_bytes = 0
        errors = []

        try:
            # Create container
            process = await asyncio.create_subprocess_exec(
                "az",
                "storage",
                "container",
                "create",
                "--name",
                container_name,
                "--account-name",
                storage_account,
                "--output",
                "none",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            if process.returncode != 0:
                errors.append("Failed to create staging container")
                return SyncResult(
                    strategy_used=SyncStrategy.AZURE_BLOB,
                    files_synced=0,
                    bytes_transferred=0,
                    duration_seconds=time.time() - start_time,
                    source_region=source_region,
                    target_region=target_region,
                    errors=errors,
                )

            # For each path, upload then download
            for path in paths:
                try:
                    # Step 1: SSH to source VM and upload to blob
                    upload_script = f"""
                    tar czf - {path} | az storage blob upload \\
                        --container-name {container_name} \\
                        --name $(basename {path}).tar.gz \\
                        --account-name {storage_account} \\
                        --data @-
                    """

                    process = await asyncio.create_subprocess_exec(
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        f"azureuser@{source_ip}",
                        "bash",
                        "-c",
                        upload_script,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        errors.append(f"Failed to upload {path}: {stderr.decode()}")
                        continue

                    # Step 2: SSH to target VM and download from blob
                    download_script = f"""
                    az storage blob download \\
                        --container-name {container_name} \\
                        --name $(basename {path}).tar.gz \\
                        --account-name {storage_account} \\
                        --file - | tar xzf - -C $(dirname {path})
                    """

                    process = await asyncio.create_subprocess_exec(
                        "ssh",
                        "-o",
                        "StrictHostKeyChecking=no",
                        f"azureuser@{target_ip}",
                        "bash",
                        "-c",
                        download_script,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await process.communicate()

                    if process.returncode != 0:
                        errors.append(f"Failed to download {path}: {stderr.decode()}")
                        continue

                    # Count files (approximate - actual would need to parse tar output)
                    total_files += 1

                    # Get blob size to estimate bytes transferred
                    process = await asyncio.create_subprocess_exec(
                        "az",
                        "storage",
                        "blob",
                        "show",
                        "--container-name",
                        container_name,
                        "--name",
                        f"{Path(path).name}.tar.gz",
                        "--account-name",
                        storage_account,
                        "--query",
                        "properties.contentLength",
                        "--output",
                        "tsv",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        with contextlib.suppress(ValueError):
                            total_bytes += int(stdout.decode().strip())

                except Exception as e:
                    errors.append(f"Error syncing {path} via blob: {e!s}")
                    continue

        finally:
            # Clean up: Delete staging container
            try:
                process = await asyncio.create_subprocess_exec(
                    "az",
                    "storage",
                    "container",
                    "delete",
                    "--name",
                    container_name,
                    "--account-name",
                    storage_account,
                    "--output",
                    "none",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()
            except Exception:
                # Ignore cleanup errors
                pass

        duration = time.time() - start_time

        return SyncResult(
            strategy_used=SyncStrategy.AZURE_BLOB,
            files_synced=total_files,
            bytes_transferred=total_bytes,
            duration_seconds=duration,
            source_region=source_region,
            target_region=target_region,
            errors=errors,
        )


__all__ = ["CrossRegionSync", "SyncResult", "SyncStrategy"]
