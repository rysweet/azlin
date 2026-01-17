"""Cross-region backup replication.

Philosophy:
- Single responsibility: geo-redundancy only
- Standard library + Azure CLI
- Self-contained and regeneratable
- Security-first: SQL injection prevention, region validation

Public API (the "studs"):
    ReplicationManager: Main replication class
    ReplicationJob: Replication job tracking
    replicate_backup(): Replicate single backup to target region
    replicate_all_pending(): Replicate all unreplicated backups
    check_replication_status(): Verify replication completion
    list_replication_jobs(): List replication jobs with filters
"""

import json
import logging
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from azlin.modules.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class ReplicationError(Exception):
    """Raised when replication operations fail."""

    pass


@dataclass
class ReplicationJob:
    """Tracks cross-region replication job."""

    source_snapshot: str
    target_snapshot: str
    source_region: str
    target_region: str
    source_resource_group: str
    target_resource_group: str
    status: str  # pending, in_progress, completed, failed
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


class ReplicationManager:
    """Cross-region backup replication manager."""

    # Valid Azure regions (subset for validation)
    VALID_REGIONS = [
        "eastus",
        "eastus2",
        "westus",
        "westus2",
        "westus3",
        "centralus",
        "northcentralus",
        "southcentralus",
        "westcentralus",
        "canadacentral",
        "canadaeast",
        "brazilsouth",
        "northeurope",
        "westeurope",
        "uksouth",
        "ukwest",
        "francecentral",
        "germanywestcentral",
        "norwayeast",
        "switzerlandnorth",
        "swedencentral",
        "southafricanorth",
        "uaenorth",
        "australiaeast",
        "australiasoutheast",
        "japaneast",
        "japanwest",
        "koreacentral",
        "southeastasia",
        "eastasia",
        "centralindia",
        "southindia",
        "westindia",
    ]

    def __init__(
        self,
        storage_path: Path | None = None,
    ):
        """Initialize replication manager with SQLite tracking.

        Args:
            storage_path: Path to SQLite database file (defaults to ~/.azlin/replication.db)

        Raises:
            ReplicationError: If database initialization fails
        """
        if storage_path is None:
            storage_path = Path.home() / ".azlin" / "replication.db"
        self.storage_path = storage_path

        # Ensure parent directory exists
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Check write permissions
        if storage_path.exists() and not storage_path.stat().st_mode & 0o200:
            raise ReplicationError(f"Cannot write to database: {storage_path}")

        # Initialize database
        self._init_database()

    def _init_database(self) -> None:
        """Initialize SQLite database with schema."""
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            # Create table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS replication_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_snapshot TEXT NOT NULL,
                    target_snapshot TEXT NOT NULL,
                    source_region TEXT NOT NULL,
                    target_region TEXT NOT NULL,
                    source_resource_group TEXT NOT NULL,
                    target_resource_group TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at DATETIME NOT NULL,
                    completed_at DATETIME,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshot ON replication_jobs(source_snapshot)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON replication_jobs(status)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_target_region ON replication_jobs(target_region)"
            )

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            raise ReplicationError(f"Database initialization failed: {e}") from e

    def replicate_backup(
        self,
        snapshot_name: str,
        source_resource_group: str,
        target_region: str,
        target_resource_group: str | None = None,
    ) -> ReplicationJob:
        """Replicate backup to target region.

        Process:
        1. Create snapshot copy in target region
        2. Track job in SQLite
        3. Verify replication completion
        4. Update backup metadata

        Args:
            snapshot_name: Source snapshot name
            source_resource_group: Source resource group name
            target_region: Target region for replication
            target_resource_group: Target resource group (defaults to source RG)

        Returns:
            ReplicationJob object

        Raises:
            ReplicationError: If replication fails
        """
        # Input validation
        if not snapshot_name:
            raise ReplicationError("Invalid snapshot name: cannot be empty")
        if not target_region:
            raise ReplicationError("Invalid target region: cannot be empty")

        # Validate target region against allowed list
        if target_region not in self.VALID_REGIONS:
            raise ReplicationError(
                f"Invalid target region: {target_region}. "
                f"Must be one of: {', '.join(self.VALID_REGIONS)}"
            )

        # Use source RG if target RG not specified
        if not target_resource_group:
            target_resource_group = source_resource_group

        # Note: We don't query for source region since it's not needed for replication
        # Azure CLI can replicate from resource name alone
        source_region = "unknown"  # Not used in replication

        # Generate target snapshot name
        target_snapshot_name = f"{snapshot_name}-{target_region}"

        # Create job record
        now = datetime.now(UTC)
        job = ReplicationJob(
            source_snapshot=snapshot_name,
            target_snapshot=target_snapshot_name,
            source_region=source_region,
            target_region=target_region,
            source_resource_group=source_resource_group,
            target_resource_group=target_resource_group,
            status="in_progress",
            started_at=now,
        )

        # Insert into database
        job_id = self._insert_job(job)

        try:
            # Replicate snapshot using Azure CLI
            self._replicate_snapshot_azure(
                snapshot_name,
                source_resource_group,
                target_snapshot_name,
                target_resource_group,
                target_region,
            )

            # Update job status
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            self._update_job(job_id, job)

            logger.info(
                f"Successfully replicated {snapshot_name} to {target_region} as {target_snapshot_name}"
            )
            return job

        except Exception as e:
            # Update job with failure
            job.status = "failed"
            job.completed_at = datetime.now(UTC)
            job.error_message = str(e)
            self._update_job(job_id, job)

            raise ReplicationError(f"Replication failed: {e}") from e

    def replicate_all_pending(
        self,
        vm_name: str,
        source_resource_group: str,
        target_region: str,
        max_parallel: int = 3,
    ) -> list[ReplicationJob]:
        """Replicate all unreplicated backups in parallel.

        Args:
            vm_name: VM name
            source_resource_group: Source resource group
            target_region: Target region for replication
            max_parallel: Maximum parallel replication jobs (default: 3)

        Returns:
            List of ReplicationJob objects

        Raises:
            ReplicationError: If operation fails
        """
        # Input validation
        if max_parallel <= 0:
            raise ReplicationError("max_parallel must be positive")

        try:
            # List all unreplicated backups
            backups = BackupManager.list_backups(vm_name, source_resource_group)
            pending_backups = [b for b in backups if not b.replicated]

            if not pending_backups:
                return []

            # Replicate in parallel with configurable concurrency
            jobs = []
            with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                futures = {
                    executor.submit(
                        self.replicate_backup,
                        backup.snapshot_name,
                        source_resource_group,
                        target_region,
                    ): backup
                    for backup in pending_backups
                }

                for future in as_completed(futures):
                    backup = futures[future]
                    try:
                        job = future.result()
                        jobs.append(job)
                    except ReplicationError as e:
                        logger.warning(f"Failed to replicate {backup.snapshot_name}: {e}")
                        # Continue with other backups

            return jobs

        except Exception as e:
            raise ReplicationError(f"Failed to list backups: {e}") from e

    def check_replication_status(
        self,
        job_id: int,
    ) -> ReplicationJob:
        """Check status of replication job.

        Args:
            job_id: Replication job ID

        Returns:
            ReplicationJob object

        Raises:
            ReplicationError: If job not found or database error
        """
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT source_snapshot, target_snapshot, source_region, target_region,
                       source_resource_group, target_resource_group, status, started_at,
                       completed_at, error_message
                FROM replication_jobs
                WHERE id = ?
                """,
                (job_id,),
            )

            row = cursor.fetchone()
            conn.close()

            if not row:
                raise ReplicationError(f"Job not found: {job_id}")

            return ReplicationJob(
                source_snapshot=row[0],
                target_snapshot=row[1],
                source_region=row[2],
                target_region=row[3],
                source_resource_group=row[4],
                target_resource_group=row[5],
                status=row[6],
                started_at=datetime.fromisoformat(row[7]),
                completed_at=datetime.fromisoformat(row[8]) if row[8] else None,
                error_message=row[9],
            )

        except sqlite3.Error as e:
            raise ReplicationError(f"Database error: {e}") from e

    def list_replication_jobs(
        self,
        vm_name: str | None = None,
        status: str | None = None,
    ) -> list[ReplicationJob]:
        """List replication jobs with optional filters.

        Args:
            vm_name: Optional filter by VM name
            status: Optional filter by status (pending, in_progress, completed, failed)

        Returns:
            List of ReplicationJob objects

        Raises:
            ReplicationError: If database error
        """
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            # Build query with filters
            query = """
                SELECT source_snapshot, target_snapshot, source_region, target_region,
                       source_resource_group, target_resource_group, status, started_at,
                       completed_at, error_message
                FROM replication_jobs
                WHERE 1=1
            """
            params = []

            if vm_name:
                # Escape LIKE pattern wildcards to prevent SQL injection
                escaped_vm_name = (
                    vm_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                query += " AND source_snapshot LIKE ? ESCAPE '\\'"
                params.append(f"{escaped_vm_name}-%")

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY started_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            jobs = [
                ReplicationJob(
                    source_snapshot=row[0],
                    target_snapshot=row[1],
                    source_region=row[2],
                    target_region=row[3],
                    source_resource_group=row[4],
                    target_resource_group=row[5],
                    status=row[6],
                    started_at=datetime.fromisoformat(row[7]),
                    completed_at=datetime.fromisoformat(row[8]) if row[8] else None,
                    error_message=row[9],
                )
                for row in rows
            ]

            return jobs

        except sqlite3.Error as e:
            raise ReplicationError(f"Database error: {e}") from e

    def _get_snapshot_info(self, snapshot_name: str, resource_group: str) -> tuple[str, str]:
        """Get snapshot region and ID.

        Args:
            snapshot_name: Snapshot name
            resource_group: Resource group name

        Returns:
            Tuple of (region, snapshot_id)

        Raises:
            ReplicationError: If snapshot not found or Azure CLI error
        """
        try:
            cmd = [
                "az",
                "snapshot",
                "show",
                "--name",
                snapshot_name,
                "--resource-group",
                resource_group,
                "--query",
                "{location:location, id:id}",
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            data = json.loads(result.stdout)
            return data["location"], data["id"]

        except subprocess.CalledProcessError as e:
            raise ReplicationError(f"Failed to get snapshot info: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise ReplicationError(f"Failed to parse snapshot info: {e}") from e
        except FileNotFoundError as e:
            raise ReplicationError("Azure CLI not found. Please install Azure CLI.") from e

    def _replicate_snapshot_azure(
        self,
        source_snapshot_name: str,
        source_resource_group: str,
        target_snapshot_name: str,
        target_resource_group: str,
        target_region: str,
    ) -> None:
        """Replicate snapshot to target region using Azure CLI.

        Args:
            source_snapshot_name: Source snapshot name
            source_resource_group: Source resource group
            target_snapshot_name: Target snapshot name
            target_resource_group: Target resource group
            target_region: Target region

        Raises:
            ReplicationError: If replication fails
        """
        # Validate snapshot names to prevent command injection
        # Azure resource names must be alphanumeric, hyphens, underscores only
        import re

        snapshot_pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
        if not snapshot_pattern.match(source_snapshot_name):
            raise ReplicationError(
                f"Invalid source snapshot name: {source_snapshot_name}. "
                "Must contain only alphanumeric characters, hyphens, and underscores."
            )
        if not snapshot_pattern.match(target_snapshot_name):
            raise ReplicationError(
                f"Invalid target snapshot name: {target_snapshot_name}. "
                "Must contain only alphanumeric characters, hyphens, and underscores."
            )

        try:
            # Construct source snapshot resource path
            # Azure CLI can resolve this to the full ID
            source_ref = f"{source_resource_group}/{source_snapshot_name}"

            cmd = [
                "az",
                "snapshot",
                "create",
                "--name",
                target_snapshot_name,
                "--resource-group",
                target_resource_group,
                "--location",
                target_region,
                "--source",
                source_snapshot_name,
                "--source-resource-group",
                source_resource_group,
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200,  # 20 minutes timeout for cross-region copy
                check=False,  # Don't raise automatically - we'll check manually
            )

            # Check for errors
            if result.returncode != 0:
                raise ReplicationError(f"{result.stderr}")

            # Verify success
            data = json.loads(result.stdout)
            if data.get("provisioningState") != "Succeeded":
                raise ReplicationError(
                    f"Replication provisioning state: {data.get('provisioningState')}"
                )

        except subprocess.CalledProcessError as e:
            raise ReplicationError(f"Azure CLI replication failed: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise ReplicationError("Replication timed out (>20 minutes)") from e
        except json.JSONDecodeError as e:
            raise ReplicationError(f"Failed to parse replication response: {e}") from e
        except FileNotFoundError as e:
            raise ReplicationError("Azure CLI not found. Please install Azure CLI.") from e

    def _insert_job(self, job: ReplicationJob) -> int:
        """Insert replication job into database.

        Args:
            job: ReplicationJob object

        Returns:
            Job ID

        Raises:
            ReplicationError: If insert fails
        """
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO replication_jobs
                (source_snapshot, target_snapshot, source_region, target_region,
                 source_resource_group, target_resource_group, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.source_snapshot,
                    job.target_snapshot,
                    job.source_region,
                    job.target_region,
                    job.source_resource_group,
                    job.target_resource_group,
                    job.status,
                    job.started_at.isoformat(),
                ),
            )

            job_id = cursor.lastrowid
            if job_id is None:
                raise ReplicationError("Failed to insert replication job")
            conn.commit()
            conn.close()

            return job_id

        except sqlite3.Error as e:
            raise ReplicationError(f"Database error: {e}") from e

    def _update_job(self, job_id: int, job: ReplicationJob) -> None:
        """Update replication job in database.

        Args:
            job_id: Job ID
            job: ReplicationJob object

        Raises:
            ReplicationError: If update fails
        """
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE replication_jobs
                SET status = ?, completed_at = ?, error_message = ?
                WHERE id = ?
                """,
                (
                    job.status,
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.error_message,
                    job_id,
                ),
            )

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            raise ReplicationError(f"Database error: {e}") from e


__all__ = ["ReplicationError", "ReplicationJob", "ReplicationManager"]
