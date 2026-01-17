"""End-to-end tests for VM provisioning with separate /home disk.

This module tests complete end-to-end workflows:
1. Full azlin new command with home disk
2. Verification that disk is mounted at /home on VM
3. Complete user workflow validation

Test Philosophy:
- E2E tests (10% of test pyramid)
- Test complete user workflows from CLI to VM verification
- Expensive tests - run sparingly
- Validate final user-facing behavior

Testing Pyramid Distribution:
- 60% Unit tests (test_vm_provisioning_home_disk.py) - Fast, heavily mocked
- 30% Integration tests (test_home_disk_integration.py) - Multiple components
- 10% E2E tests (this file) - Complete workflows

Note: These tests use @pytest.mark.e2e decorator
and should be run manually for validation:
  pytest -m e2e --slow
"""

import subprocess
import time

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestHomeDiskE2E:
    """End-to-end tests for home disk functionality.

    These tests provision real VMs and verify the home disk
    is properly configured and mounted.

    WARNING: These tests incur Azure costs and take 5-10 minutes.
    Only run when validating the feature works end-to-end.
    """

    @pytest.fixture(scope="class")
    def test_vm_name(self):
        """Generate unique VM name for E2E test."""
        timestamp = int(time.time())
        return f"azlin-e2e-home-{timestamp}"

    @pytest.fixture(scope="class")
    def test_resource_group(self, test_vm_name):
        """Generate resource group name for E2E test."""
        return f"{test_vm_name}-rg"

    def test_azlin_new_creates_vm_with_home_disk(self, test_vm_name, test_resource_group):
        """Test complete azlin new workflow with home disk.

        Given: azlin new command with default settings (home disk enabled)
        When: Command is executed
        Then: VM is created with home disk attached and mounted at /home

        Note: This test requires Azure credentials and will provision real resources.
        Cleanup happens in teardown.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")

        # This is the actual E2E test implementation (when enabled):
        try:
            # Step 1: Provision VM with home disk
            result = subprocess.run(
                [
                    "azlin",
                    "new",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--location",
                    "westus2",
                    "--size",
                    "Standard_B1s",
                    "--home-disk-size",
                    "10",  # Minimal size for cost
                    "--no-connect",  # Don't auto-connect
                ],
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            assert result.returncode == 0, f"azlin new failed: {result.stderr}"
            assert "provisioned successfully" in result.stdout.lower()

            # Step 2: Wait for VM to be fully ready
            time.sleep(60)

            # Step 3: SSH into VM and verify home disk
            ssh_result = subprocess.run(
                [
                    "azlin",
                    "ssh",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--command",
                    "df -h /home && mount | grep /home",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert ssh_result.returncode == 0, f"SSH verification failed: {ssh_result.stderr}"

            output = ssh_result.stdout

            # Verify /home is mounted
            assert "/home" in output
            assert "ext4" in output

            # Verify it's the data disk (not root partition)
            assert "lun0" in output or "sdc" in output

            # Step 4: Verify disk size
            size_result = subprocess.run(
                [
                    "azlin",
                    "ssh",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--command",
                    "df -BG /home | tail -1 | awk '{print $2}'",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            size_gb = int(size_result.stdout.strip().replace("G", ""))
            assert size_gb >= 9, (
                f"Expected at least 9GB, got {size_gb}GB"
            )  # Allow for filesystem overhead

        finally:
            # Cleanup: Delete resource group (includes VM and disk)
            subprocess.run(
                ["az", "group", "delete", "--name", test_resource_group, "--yes", "--no-wait"],
                capture_output=True,
            )

    def test_azlin_new_with_no_home_disk_flag(self, test_vm_name, test_resource_group):
        """Test azlin new with --no-home-disk flag.

        Given: azlin new command with --no-home-disk flag
        When: Command is executed
        Then: VM is created without home disk
        And: /home is on root partition

        Note: This test requires Azure credentials and will provision real resources.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")

        try:
            # Step 1: Provision VM without home disk
            result = subprocess.run(
                [
                    "azlin",
                    "new",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--location",
                    "westus2",
                    "--size",
                    "Standard_B1s",
                    "--no-home-disk",
                    "--no-connect",
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )

            assert result.returncode == 0, f"azlin new failed: {result.stderr}"

            # Step 2: Wait for VM to be ready
            time.sleep(60)

            # Step 3: Verify /home is on root partition (not separate disk)
            ssh_result = subprocess.run(
                [
                    "azlin",
                    "ssh",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--command",
                    "df /home | tail -1 | awk '{print $1}'",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            device = ssh_result.stdout.strip()

            # Should be root partition (sda1 or similar), not data disk (sdc/lun0)
            assert "sda" in device or "/" in device
            assert "sdc" not in device
            assert "lun0" not in device

        finally:
            # Cleanup
            subprocess.run(
                ["az", "group", "delete", "--name", test_resource_group, "--yes", "--no-wait"],
                capture_output=True,
            )

    def test_azlin_new_with_custom_disk_size(self, test_vm_name, test_resource_group):
        """Test azlin new with custom --home-disk-size.

        Given: azlin new command with --home-disk-size 50
        When: Command is executed
        Then: VM is created with 50GB home disk

        Note: This test requires Azure credentials and will provision real resources.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")

        try:
            # Step 1: Provision VM with custom disk size
            result = subprocess.run(
                [
                    "azlin",
                    "new",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--location",
                    "westus2",
                    "--size",
                    "Standard_B1s",
                    "--home-disk-size",
                    "50",
                    "--no-connect",
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )

            assert result.returncode == 0, f"azlin new failed: {result.stderr}"

            # Step 2: Wait for VM to be ready
            time.sleep(60)

            # Step 3: Verify disk size is approximately 50GB
            ssh_result = subprocess.run(
                [
                    "azlin",
                    "ssh",
                    "--name",
                    test_vm_name,
                    "--resource-group",
                    test_resource_group,
                    "--command",
                    "df -BG /home | tail -1 | awk '{print $2}'",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            size_gb = int(ssh_result.stdout.strip().replace("G", ""))
            assert 48 <= size_gb <= 52, f"Expected ~50GB, got {size_gb}GB"

        finally:
            # Cleanup
            subprocess.run(
                ["az", "group", "delete", "--name", test_resource_group, "--yes", "--no-wait"],
                capture_output=True,
            )


@pytest.mark.e2e
@pytest.mark.slow
class TestHomeDiskPersistence:
    """E2E tests for home disk data persistence.

    These tests verify that data on the home disk persists
    across VM operations (stop/start, resize, etc.).
    """

    def test_home_disk_data_persists_after_vm_stop_start(self):
        """Test that home disk data persists after VM stop/start.

        Given: A VM with home disk and test data written to /home
        When: VM is stopped and started
        Then: Data in /home is still present

        Note: This test requires Azure credentials.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")

    def test_home_disk_can_be_detached_and_reattached(self):
        """Test that home disk can be detached and reattached to different VM.

        Given: A VM with home disk
        When: Disk is detached and attached to new VM
        Then: Data is accessible from new VM

        Note: This test requires Azure credentials.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")


@pytest.mark.e2e
class TestHomeDiskPerformance:
    """E2E tests for home disk performance characteristics.

    These tests validate that the home disk meets performance
    expectations for different SKUs.
    """

    def test_standard_lrs_disk_meets_performance_baseline(self):
        """Test that Standard_LRS disk meets basic performance requirements.

        Given: A VM with Standard_LRS home disk
        When: I/O benchmark is run on /home
        Then: Performance meets Standard_LRS specifications

        Note: This test requires Azure credentials.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")

    def test_premium_ssd_disk_provides_better_performance(self):
        """Test that Premium_LRS disk provides better performance than Standard_LRS.

        Given: VMs with Standard_LRS and Premium_LRS home disks
        When: I/O benchmarks are run
        Then: Premium_LRS shows significantly better performance

        Note: This test requires Azure credentials.
        """
        pytest.skip("E2E test - requires manual execution with Azure credentials")
