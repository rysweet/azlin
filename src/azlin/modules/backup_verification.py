"""Backup verification and integrity checking.

Philosophy:
- Single responsibility: verification only
- Non-disruptive testing (temporary disks)
- Self-contained and regeneratable
- Security-first: input validation, safe operations

Public API (the "studs"):
    VerificationManager: Main verification class
    VerificationResult: Verification outcome dataclass
    verify_backup(): Verify single backup
    verify_all_backups(): Verify all unverified backups
    get_verification_report(): Generate verification report
"""

import json
import logging
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from azlin.modules.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """Raised when verification operations fail."""

    pass


@dataclass
class VerificationResult:
    """Backup verification result."""

    backup_name: str
    vm_name: str
    verified_at: datetime
    success: bool
    disk_readable: bool
    size_matches: bool
    test_disk_created: bool
    test_disk_deleted: bool
    error_message: str | None = None
    verification_time_seconds: float = 0.0


class VerificationManager:
    """Backup verification manager."""

    def __init__(
        self,
        storage_path: Path | None = None,
    ):
        """Initialize verification manager with SQLite tracking.

        Args:
            storage_path: Path to SQLite database file (defaults to ~/.azlin/verification.db)

        Raises:
            VerificationError: If database initialization fails
        """
        if storage_path is None:
            storage_path = Path.home() / ".azlin" / "verification.db"
        self.storage_path = storage_path

        # Ensure parent directory exists
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Check write permissions
        if storage_path.exists() and not storage_path.stat().st_mode & 0o200:
            raise VerificationError(f"Cannot write to database: {storage_path}")

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
                CREATE TABLE IF NOT EXISTS verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_name TEXT NOT NULL,
                    vm_name TEXT NOT NULL,
                    verified_at DATETIME NOT NULL,
                    success BOOLEAN NOT NULL,
                    disk_readable BOOLEAN,
                    size_matches BOOLEAN,
                    test_disk_created BOOLEAN,
                    test_disk_deleted BOOLEAN,
                    error_message TEXT,
                    verification_time_seconds REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create indexes
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_backup_name ON verifications(backup_name)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vm_name ON verifications(vm_name)")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_verified_at ON verifications(verified_at)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_success ON verifications(success)")

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            raise VerificationError(f"Database initialization failed: {e}") from e

    def verify_backup(
        self,
        snapshot_name: str,
        resource_group: str,
    ) -> VerificationResult:
        """Verify backup by creating temporary test disk.

        Process:
        1. Create test disk from snapshot
        2. Verify disk properties (size, status)
        3. Delete test disk immediately
        4. Record verification result

        Args:
            snapshot_name: Snapshot name to verify
            resource_group: Resource group name

        Returns:
            VerificationResult object

        Raises:
            VerificationError: If verification setup fails
        """
        # Input validation
        if not snapshot_name:
            raise VerificationError("Invalid snapshot name: cannot be empty")
        if not resource_group:
            raise VerificationError("Invalid resource group: cannot be empty")

        # Extract VM name from snapshot name
        vm_name = (
            snapshot_name.split("-snapshot-")[0] if "-snapshot-" in snapshot_name else "unknown"
        )

        start_time = time.time()
        now = datetime.now(UTC)

        result = VerificationResult(
            backup_name=snapshot_name,
            vm_name=vm_name,
            verified_at=now,
            success=False,
            disk_readable=False,
            size_matches=False,
            test_disk_created=False,
            test_disk_deleted=False,
        )

        test_disk_name = f"{snapshot_name}-verify-{int(start_time)}"

        try:
            # Step 1: Create test disk from snapshot
            created_disk_size = self._create_test_disk(
                snapshot_name, test_disk_name, resource_group
            )
            result.test_disk_created = True

            # Step 2: Verify disk is readable and size matches
            actual_disk_size = self._verify_disk_readable(test_disk_name, resource_group)
            result.disk_readable = True

            # Check size matches
            if created_disk_size == actual_disk_size:
                result.size_matches = True

            # Step 3: Delete test disk
            self._delete_test_disk(test_disk_name, resource_group)
            result.test_disk_deleted = True

            # Mark as successful if all checks passed
            result.success = result.disk_readable and result.size_matches

        except Exception as e:
            result.error_message = str(e)
            logger.warning(f"Verification failed for {snapshot_name}: {e}")

            # Try to cleanup test disk even if verification failed
            if result.test_disk_created and not result.test_disk_deleted:
                try:
                    self._delete_test_disk(test_disk_name, resource_group)
                    result.test_disk_deleted = True
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup test disk {test_disk_name}: {cleanup_error}")

        # Record verification time
        result.verification_time_seconds = time.time() - start_time

        # Store result in database
        self._insert_verification_result(result)

        return result

    def verify_all_backups(
        self,
        vm_name: str,
        resource_group: str,
        max_parallel: int = 2,
    ) -> list[VerificationResult]:
        """Verify all unverified backups.

        Args:
            vm_name: VM name
            resource_group: Resource group name
            max_parallel: Maximum parallel verification jobs (default: 2)

        Returns:
            List of VerificationResult objects

        Raises:
            VerificationError: If operation fails
        """
        # Input validation
        if max_parallel <= 0:
            raise VerificationError("max_parallel must be positive")

        try:
            # List all backups
            backups = BackupManager.list_backups(vm_name, resource_group)

            if not backups:
                return []

            # Verify in parallel with conservative concurrency
            results = []
            with ThreadPoolExecutor(max_workers=max_parallel) as executor:
                futures = {
                    executor.submit(
                        self.verify_backup,
                        backup.snapshot_name,
                        resource_group,
                    ): backup
                    for backup in backups
                }

                for future in as_completed(futures):
                    backup = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except VerificationError as e:
                        logger.warning(f"Failed to verify {backup.snapshot_name}: {e}")
                        # Continue with other backups

            return results

        except Exception as e:
            raise VerificationError(f"Failed to list backups: {e}") from e

    def get_verification_report(
        self,
        vm_name: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Generate verification report.

        Args:
            vm_name: Optional filter by VM name
            days: Number of days to include in report (default: 7)

        Returns:
            Dictionary with:
            - total_verified: int
            - success_rate: float (0.0-1.0)
            - failures: list[VerificationResult]
            - last_verified: datetime | None

        Raises:
            VerificationError: If days is invalid or database error
        """
        # Input validation
        if days <= 0:
            raise VerificationError("days must be positive")

        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            # Calculate date cutoff
            cutoff = datetime.now(UTC) - timedelta(days=days)

            # Build query
            query = """
                SELECT backup_name, vm_name, verified_at, success, disk_readable,
                       size_matches, test_disk_created, test_disk_deleted,
                       error_message, verification_time_seconds
                FROM verifications
                WHERE verified_at >= ?
            """
            params = [cutoff.isoformat()]

            if vm_name:
                query += " AND vm_name = ?"
                params.append(vm_name)

            query += " ORDER BY verified_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            # Process results
            total_verified = len(rows)
            successful = sum(1 for row in rows if row[3])  # success column
            success_rate = successful / total_verified if total_verified > 0 else 0.0

            # Collect failures
            failures = []
            last_verified = None
            for row in rows:
                if not row[3]:  # not successful
                    failures.append(
                        VerificationResult(
                            backup_name=row[0],
                            vm_name=row[1],
                            verified_at=datetime.fromisoformat(row[2]),
                            success=row[3],
                            disk_readable=row[4],
                            size_matches=row[5],
                            test_disk_created=row[6],
                            test_disk_deleted=row[7],
                            error_message=row[8],
                            verification_time_seconds=row[9] or 0.0,
                        )
                    )

                # Track most recent verification
                if not last_verified and row[2]:
                    last_verified = datetime.fromisoformat(row[2])

            return {
                "total_verified": total_verified,
                "success_rate": success_rate,
                "failures": failures,
                "last_verified": last_verified,
            }

        except sqlite3.Error as e:
            raise VerificationError(f"Database error: {e}") from e

    def _create_test_disk(
        self, snapshot_name: str, test_disk_name: str, resource_group: str
    ) -> int:
        """Create test disk from snapshot.

        Args:
            snapshot_name: Source snapshot name
            test_disk_name: Test disk name
            resource_group: Resource group name

        Returns:
            Disk size in GB

        Raises:
            VerificationError: If disk creation fails
        """
        try:
            cmd = [
                "az",
                "disk",
                "create",
                "--name",
                test_disk_name,
                "--resource-group",
                resource_group,
                "--source",
                snapshot_name,
                "--output",
                "json",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
                check=True,
            )

            data = json.loads(result.stdout)
            disk_size = data.get("diskSizeGb", 0)

            return disk_size

        except subprocess.CalledProcessError as e:
            raise VerificationError(f"Failed to create test disk: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VerificationError("Test disk creation timed out") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise VerificationError(f"Failed to parse disk creation response: {e}") from e
        except FileNotFoundError as e:
            raise VerificationError("Azure CLI not found. Please install Azure CLI.") from e

    def _verify_disk_readable(self, test_disk_name: str, resource_group: str) -> int:
        """Verify test disk is readable and get its size.

        Args:
            test_disk_name: Test disk name
            resource_group: Resource group name

        Returns:
            Disk size in GB

        Raises:
            VerificationError: If disk is not readable
        """
        try:
            cmd = [
                "az",
                "disk",
                "show",
                "--name",
                test_disk_name,
                "--resource-group",
                resource_group,
                "--query",
                "{diskSizeGb:diskSizeGb, diskState:diskState}",
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
            disk_size = data.get("diskSizeGb", 0)

            return disk_size

        except subprocess.CalledProcessError as e:
            raise VerificationError(f"Test disk not readable: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise VerificationError(f"Failed to parse disk info: {e}") from e

    def _delete_test_disk(self, test_disk_name: str, resource_group: str) -> None:
        """Delete test disk.

        Args:
            test_disk_name: Test disk name
            resource_group: Resource group name

        Raises:
            VerificationError: If disk deletion fails
        """
        try:
            cmd = [
                "az",
                "disk",
                "delete",
                "--name",
                test_disk_name,
                "--resource-group",
                resource_group,
                "--yes",
            ]

            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                check=True,
            )

        except subprocess.CalledProcessError as e:
            raise VerificationError(f"Failed to delete test disk: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise VerificationError("Test disk deletion timed out") from e

    def _insert_verification_result(self, result: VerificationResult) -> None:
        """Insert verification result into database.

        Args:
            result: VerificationResult object

        Raises:
            VerificationError: If insert fails
        """
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO verifications
                (backup_name, vm_name, verified_at, success, disk_readable,
                 size_matches, test_disk_created, test_disk_deleted,
                 error_message, verification_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.backup_name,
                    result.vm_name,
                    result.verified_at.isoformat(),
                    result.success,
                    result.disk_readable,
                    result.size_matches,
                    result.test_disk_created,
                    result.test_disk_deleted,
                    result.error_message,
                    result.verification_time_seconds,
                ),
            )

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            raise VerificationError(f"Database error: {e}") from e


__all__ = ["VerificationError", "VerificationManager", "VerificationResult"]
