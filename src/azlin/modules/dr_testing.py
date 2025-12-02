"""Disaster recovery testing automation.

Philosophy:
- Single responsibility: DR testing only
- Automated restore validation
- Self-contained and regeneratable
- Security-first: input validation, safe cleanup

Public API (the "studs"):
    DRTestManager: Main DR testing class
    DRTestResult: Test result dataclass
    DRTestConfig: Test configuration
    run_dr_test(): Execute complete DR test
    run_scheduled_tests(): Run all scheduled DR tests
    get_test_history(): Retrieve test results
    get_success_rate(): Calculate DR test success rate
"""

import json
import logging
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from azlin.modules.backup_manager import BackupManager

logger = logging.getLogger(__name__)


class DRTestError(Exception):
    """Raised when DR test operations fail."""

    pass


@dataclass
class DRTestConfig:
    """DR test configuration."""

    vm_name: str
    backup_name: str
    source_resource_group: str
    test_region: str
    test_resource_group: str
    verify_boot: bool = True
    verify_connectivity: bool = True
    cleanup_after_test: bool = True


@dataclass
class DRTestResult:
    """DR test execution result."""

    test_id: int
    vm_name: str
    backup_name: str
    test_region: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    restore_succeeded: bool = False
    boot_succeeded: bool = False
    connectivity_succeeded: bool = False
    cleanup_succeeded: bool = False
    rto_seconds: float | None = None  # Recovery Time Objective
    error_message: str | None = None


class DRTestManager:
    """Disaster recovery testing manager."""

    def __init__(
        self,
        storage_path: Path | None = None,
    ):
        """Initialize DR test manager.

        Args:
            storage_path: Path to SQLite database file (defaults to ~/.azlin/dr_tests.db)

        Raises:
            DRTestError: If database initialization fails
        """
        if storage_path is None:
            storage_path = Path.home() / ".azlin" / "dr_tests.db"
        self.storage_path = storage_path

        # Ensure parent directory exists
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Check write permissions
        if storage_path.exists() and not storage_path.stat().st_mode & 0o200:
            raise DRTestError(f"Cannot write to database: {storage_path}")

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
                CREATE TABLE IF NOT EXISTS dr_tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vm_name TEXT NOT NULL,
                    backup_name TEXT NOT NULL,
                    test_region TEXT NOT NULL,
                    started_at DATETIME NOT NULL,
                    completed_at DATETIME,
                    success BOOLEAN,
                    restore_succeeded BOOLEAN,
                    boot_succeeded BOOLEAN,
                    connectivity_succeeded BOOLEAN,
                    cleanup_succeeded BOOLEAN,
                    rto_seconds REAL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vm_name_test ON dr_tests(vm_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_started_at ON dr_tests(started_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_success_test ON dr_tests(success)")

            conn.commit()
            conn.close()

        except sqlite3.Error as e:
            raise DRTestError(f"Database initialization failed: {e}") from e

    def run_dr_test(
        self,
        config: DRTestConfig,
    ) -> DRTestResult:
        """Execute complete DR test.

        Process:
        1. Restore backup to test VM in target region
        2. Verify VM boots successfully
        3. Verify SSH connectivity
        4. Measure RTO (Recovery Time Objective)
        5. Clean up test resources
        6. Record test results

        Args:
            config: DRTestConfig object

        Returns:
            DRTestResult object

        Raises:
            DRTestError: If test setup fails
        """
        # Input validation
        if not config.vm_name:
            raise DRTestError("Invalid VM name: cannot be empty")
        if not config.backup_name:
            raise DRTestError("Invalid backup name: cannot be empty")

        start_time = time.time()
        now = datetime.now(UTC)

        # Create test result record
        result = DRTestResult(
            test_id=0,  # Will be set after DB insert
            vm_name=config.vm_name,
            backup_name=config.backup_name,
            test_region=config.test_region,
            started_at=now,
        )

        test_vm_name = f"{config.vm_name}-drtest-{int(start_time)}"

        try:
            # Step 1: Restore VM from backup
            logger.info(f"Starting DR test: restoring {config.backup_name} to {config.test_region}")
            self._restore_vm_from_backup(
                config.backup_name,
                test_vm_name,
                config.source_resource_group,
                config.test_resource_group,
                config.test_region,
            )
            result.restore_succeeded = True

            # Step 2: Verify boot (if enabled)
            if config.verify_boot:
                logger.info(f"Verifying VM boot: {test_vm_name}")
                self._verify_vm_boot(test_vm_name, config.test_resource_group)
                result.boot_succeeded = True

            # Step 3: Verify connectivity (if enabled)
            if config.verify_connectivity:
                logger.info(f"Verifying connectivity: {test_vm_name}")
                self._verify_vm_connectivity(test_vm_name, config.test_resource_group)
                result.connectivity_succeeded = True

            # Calculate RTO
            result.rto_seconds = time.time() - start_time

            # Mark as successful
            result.success = True

        except Exception as e:
            result.error_message = str(e)
            logger.error(f"DR test failed: {e}")

        # Step 4: Cleanup (if enabled)
        if config.cleanup_after_test:
            try:
                logger.info(f"Cleaning up test resources: {test_vm_name}")
                self._cleanup_test_vm(test_vm_name, config.test_resource_group)
                result.cleanup_succeeded = True
            except Exception as cleanup_error:
                logger.warning(f"Cleanup failed: {cleanup_error}")
                result.cleanup_succeeded = False

        # Record completion time
        result.completed_at = datetime.now(UTC)

        # Store result in database
        test_id = self._insert_test_result(result)
        result.test_id = test_id

        return result

    def run_scheduled_tests(
        self,
        resource_group: str,
    ) -> list[DRTestResult]:
        """Run DR tests for all VMs with DR enabled.

        Schedule: Weekly DR test for each VM

        Args:
            resource_group: Resource group name

        Returns:
            List of DRTestResult objects

        Raises:
            DRTestError: If operation fails
        """
        try:
            # List all backups (one per VM)
            backups = BackupManager.list_backups("*", resource_group)

            if not backups:
                return []

            # Group backups by VM
            vm_backups = {}
            for backup in backups:
                if backup.vm_name not in vm_backups:
                    vm_backups[backup.vm_name] = backup

            # Run DR test for each VM
            results = []
            for vm_name, backup in vm_backups.items():
                logger.info(f"Running scheduled DR test for {vm_name}")

                config = DRTestConfig(
                    vm_name=vm_name,
                    backup_name=backup.snapshot_name,
                    source_resource_group=resource_group,
                    test_region="westus2",  # Default test region
                    test_resource_group=f"{resource_group}-dr",
                )

                try:
                    result = self.run_dr_test(config)
                    results.append(result)
                except DRTestError as e:
                    logger.error(f"Failed to run DR test for {vm_name}: {e}")
                    # Continue with other VMs

            return results

        except Exception as e:
            raise DRTestError(f"Failed to list backups: {e}") from e

    def get_test_history(
        self,
        vm_name: str | None = None,
        days: int = 30,
    ) -> list[DRTestResult]:
        """Retrieve DR test history.

        Args:
            vm_name: Optional filter by VM name
            days: Number of days to retrieve (default: 30)

        Returns:
            List of DRTestResult objects

        Raises:
            DRTestError: If days is invalid or database error
        """
        # Input validation
        if days <= 0:
            raise DRTestError("days must be positive")

        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            # Calculate date cutoff
            cutoff = datetime.now(UTC) - timedelta(days=days)

            # Build query
            query = """
                SELECT id, vm_name, backup_name, test_region, started_at, completed_at,
                       success, restore_succeeded, boot_succeeded, connectivity_succeeded,
                       cleanup_succeeded, rto_seconds, error_message
                FROM dr_tests
                WHERE started_at >= ?
            """
            params = [cutoff.isoformat()]

            if vm_name:
                query += " AND vm_name = ?"
                params.append(vm_name)

            query += " ORDER BY started_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            # Convert to DRTestResult objects
            results = [
                DRTestResult(
                    test_id=row[0],
                    vm_name=row[1],
                    backup_name=row[2],
                    test_region=row[3],
                    started_at=datetime.fromisoformat(row[4]),
                    completed_at=datetime.fromisoformat(row[5]) if row[5] else None,
                    success=row[6],
                    restore_succeeded=row[7],
                    boot_succeeded=row[8],
                    connectivity_succeeded=row[9],
                    cleanup_succeeded=row[10],
                    rto_seconds=row[11],
                    error_message=row[12],
                )
                for row in rows
            ]

            return results

        except sqlite3.Error as e:
            raise DRTestError(f"Database error: {e}") from e

    def get_success_rate(
        self,
        vm_name: str | None = None,
        days: int = 30,
    ) -> float:
        """Calculate DR test success rate.

        Args:
            vm_name: Optional filter by VM name
            days: Number of days to include (default: 30)

        Returns:
            Success rate (0.0-1.0)

        Raises:
            DRTestError: If days is invalid or database error
        """
        # Input validation
        if days <= 0:
            raise DRTestError("days must be positive")

        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            # Calculate date cutoff
            cutoff = datetime.now(UTC) - timedelta(days=days)

            # Build query
            query = """
                SELECT COUNT(*) as total, SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful
                FROM dr_tests
                WHERE started_at >= ?
            """
            params = [cutoff.isoformat()]

            if vm_name:
                query += " AND vm_name = ?"
                params.append(vm_name)

            cursor.execute(query, params)
            row = cursor.fetchone()
            conn.close()

            total = row[0] or 0
            successful = row[1] or 0

            return successful / total if total > 0 else 0.0

        except sqlite3.Error as e:
            raise DRTestError(f"Database error: {e}") from e

    def _restore_vm_from_backup(
        self,
        backup_name: str,
        test_vm_name: str,
        source_resource_group: str,
        test_resource_group: str,
        test_region: str,
    ) -> None:
        """Restore VM from backup in test region.

        Args:
            backup_name: Backup snapshot name
            test_vm_name: Test VM name
            source_resource_group: Source resource group
            test_resource_group: Test resource group
            test_region: Test region

        Raises:
            DRTestError: If restore fails
        """
        try:
            # Step 1: Create disk from snapshot
            test_disk_name = f"{test_vm_name}-disk"
            create_disk_cmd = [
                "az",
                "disk",
                "create",
                "--name",
                test_disk_name,
                "--resource-group",
                test_resource_group,
                "--location",
                test_region,
                "--source",
                backup_name,
                "--output",
                "json",
            ]

            result = subprocess.run(
                create_disk_cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
                check=True,
            )

            disk_data = json.loads(result.stdout)
            disk_id = disk_data["id"]

            # Step 2: Create VM with restored disk
            create_vm_cmd = [
                "az",
                "vm",
                "create",
                "--name",
                test_vm_name,
                "--resource-group",
                test_resource_group,
                "--location",
                test_region,
                "--attach-os-disk",
                disk_id,
                "--os-type",
                "Linux",
                "--output",
                "json",
            ]

            subprocess.run(
                create_vm_cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
                check=True,
            )

        except subprocess.CalledProcessError as e:
            raise DRTestError(f"Failed to restore VM: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise DRTestError("VM restore timed out") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise DRTestError(f"Failed to parse restore response: {e}") from e
        except FileNotFoundError as e:
            raise DRTestError("Azure CLI not found. Please install Azure CLI.") from e

    def _verify_vm_boot(self, vm_name: str, resource_group: str) -> None:
        """Verify VM has booted successfully.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Raises:
            DRTestError: If VM boot verification fails
        """
        try:
            # Wait for VM to finish provisioning (max 5 minutes)
            max_retries = 30
            retry_delay = 10  # seconds

            for _ in range(max_retries):
                cmd = [
                    "az",
                    "vm",
                    "show",
                    "--name",
                    vm_name,
                    "--resource-group",
                    resource_group,
                    "--query",
                    "{provisioningState:provisioningState, powerState:instanceView.statuses[?starts_with(code, 'PowerState/')].displayStatus | [0]}",
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
                provisioning_state = data.get("provisioningState")
                power_state = data.get("powerState")

                if provisioning_state == "Succeeded" and "running" in (power_state or "").lower():
                    return  # VM is running

                time.sleep(retry_delay)

            # If we get here, VM didn't boot in time
            raise DRTestError("VM failed to boot within timeout period")

        except subprocess.CalledProcessError as e:
            raise DRTestError(f"Failed to verify VM boot: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise DRTestError(f"Failed to parse VM status: {e}") from e

    def _verify_vm_connectivity(self, vm_name: str, resource_group: str) -> None:
        """Verify SSH connectivity to VM.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Raises:
            DRTestError: If connectivity verification fails
        """
        try:
            # Get VM public IP
            ip_cmd = [
                "az",
                "vm",
                "show",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--show-details",
                "--query",
                "publicIps",
                "--output",
                "tsv",
            ]

            result = subprocess.run(
                ip_cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            public_ip = result.stdout.strip()
            if not public_ip:
                raise DRTestError("VM has no public IP address")

            # Test SSH connectivity (with short timeout)
            ssh_cmd = [
                "ssh",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"azureuser@{public_ip}",
                "echo",
                "connected",
            ]

            subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )

        except subprocess.CalledProcessError as e:
            raise DRTestError(f"SSH connectivity test failed: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise DRTestError("SSH connectivity test timed out") from e

    def _cleanup_test_vm(self, vm_name: str, resource_group: str) -> None:
        """Clean up test VM and associated resources.

        Args:
            vm_name: VM name
            resource_group: Resource group name

        Raises:
            DRTestError: If cleanup fails
        """
        try:
            # Delete VM and all associated resources
            cmd = [
                "az",
                "vm",
                "delete",
                "--name",
                vm_name,
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
            raise DRTestError(f"Failed to cleanup test VM: {e.stderr}") from e
        except subprocess.TimeoutExpired as e:
            raise DRTestError("Test VM cleanup timed out") from e

    def _insert_test_result(self, result: DRTestResult) -> int:
        """Insert DR test result into database.

        Args:
            result: DRTestResult object

        Returns:
            Test ID

        Raises:
            DRTestError: If insert fails
        """
        try:
            conn = sqlite3.connect(self.storage_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO dr_tests
                (vm_name, backup_name, test_region, started_at, completed_at,
                 success, restore_succeeded, boot_succeeded, connectivity_succeeded,
                 cleanup_succeeded, rto_seconds, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.vm_name,
                    result.backup_name,
                    result.test_region,
                    result.started_at.isoformat(),
                    result.completed_at.isoformat() if result.completed_at else None,
                    result.success,
                    result.restore_succeeded,
                    result.boot_succeeded,
                    result.connectivity_succeeded,
                    result.cleanup_succeeded,
                    result.rto_seconds,
                    result.error_message,
                ),
            )

            test_id = cursor.lastrowid
            if test_id is None:
                raise DRTestError("Failed to insert DR test result")
            conn.commit()
            conn.close()

            return test_id

        except sqlite3.Error as e:
            raise DRTestError(f"Database error: {e}") from e


__all__ = ["DRTestConfig", "DRTestError", "DRTestManager", "DRTestResult"]
