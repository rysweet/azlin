"""E2E tests for bastion routing with real Azure resources.

These tests require actual Azure infrastructure and should be run
in a test environment with proper credentials.

Following TDD approach - these tests should FAIL initially and PASS
after implementing bastion routing support.
"""

import subprocess
import time

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestMultiVMCommandsE2E:
    """End-to-end tests for multi-VM commands with bastion routing.

    Requirements:
    - Azure subscription with test resource group
    - At least one VM with public IP
    - At least one VM with only private IP (bastion-only)
    - Bastion host configured for the VNet
    - Azure CLI authenticated
    """

    @pytest.fixture
    def test_resource_group(self):
        """Resource group name for E2E tests."""
        return "azlin-e2e-test-rg"

    @pytest.fixture
    def public_vm_name(self):
        """VM name with public IP."""
        return "azlin-public-test-vm"

    @pytest.fixture
    def private_vm_name(self):
        """VM name with only private IP."""
        return "azlin-private-test-vm"

    def test_w_command_with_bastion_vm(self, test_resource_group, private_vm_name):
        """Test 'azlin w' command includes bastion-only VM."""
        # Run azlin w command
        result = subprocess.run(
            ["azlin", "w", "--rg", test_resource_group],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Output should include the private VM
        assert private_vm_name in result.stdout, (
            f"Expected {private_vm_name} in output but got: {result.stdout}"
        )

        # Should show activity from the VM
        assert "user" in result.stdout.lower() or "load" in result.stdout.lower()

    def test_top_command_with_bastion_vm(self, test_resource_group, private_vm_name):
        """Test 'azlin top' command includes bastion-only VM."""
        # Run azlin top command with single iteration
        # (We'll need to add iteration support for testing)
        result = subprocess.run(
            ["azlin", "top", "--rg", test_resource_group, "-i", "5"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should succeed or fail gracefully with KeyboardInterrupt
        assert result.returncode in [0, 130], f"Unexpected failure: {result.stderr}"

        # Output should mention the private VM
        if result.returncode == 0:
            assert private_vm_name in result.stdout or "Starting distributed top" in result.stdout

    def test_ps_command_with_bastion_vm(self, test_resource_group, private_vm_name):
        """Test 'azlin ps' command includes bastion-only VM."""
        # Run azlin ps command
        result = subprocess.run(
            ["azlin", "ps", "--rg", test_resource_group],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Output should include the private VM
        assert private_vm_name in result.stdout, (
            f"Expected {private_vm_name} in output but got: {result.stdout}"
        )

        # Should show processes from the VM
        assert "azureuser" in result.stdout or "root" in result.stdout

    def test_mixed_vms_all_included(self, test_resource_group, public_vm_name, private_vm_name):
        """Test commands include both public and private VMs."""
        # Run azlin w command
        result = subprocess.run(
            ["azlin", "w", "--rg", test_resource_group],
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Both VMs should be in output
        assert public_vm_name in result.stdout, f"Missing public VM in: {result.stdout}"
        assert private_vm_name in result.stdout, f"Missing private VM in: {result.stdout}"

    def test_connect_to_private_vm_via_bastion(self, test_resource_group, private_vm_name):
        """Test 'azlin connect' works with bastion-only VM."""
        # This is the working reference - should already pass
        result = subprocess.run(
            [
                "azlin",
                "connect",
                private_vm_name,
                "--rg",
                test_resource_group,
                "--",
                "echo",
                "test",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"


@pytest.mark.e2e
@pytest.mark.slow
class TestBastionTunnelPerformance:
    """Test bastion tunnel performance and reliability."""

    def test_multiple_concurrent_connections(self):
        """Test multiple concurrent connections through bastion."""
        # Start multiple commands simultaneously
        processes = []
        for i in range(3):
            proc = subprocess.Popen(
                ["azlin", "w", "--rg", "azlin-e2e-test-rg"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(proc)

        # Wait for all to complete
        results = [p.wait(timeout=120) for p in processes]

        # All should succeed
        assert all(rc == 0 for rc in results), "Some commands failed"

    def test_tunnel_cleanup_after_command(self):
        """Test bastion tunnels are cleaned up after command completes."""
        # Get initial tunnel count
        initial_tunnels = subprocess.run(
            ["az", "network", "bastion", "tunnel", "list"],
            capture_output=True,
            text=True,
        )

        # Run command
        subprocess.run(
            ["azlin", "w", "--rg", "azlin-e2e-test-rg"],
            capture_output=True,
            timeout=60,
        )

        # Wait a bit for cleanup
        time.sleep(5)

        # Check tunnel count
        final_tunnels = subprocess.run(
            ["az", "network", "bastion", "tunnel", "list"],
            capture_output=True,
            text=True,
        )

        # Should be cleaned up (exact check depends on Azure CLI support)
        # This is a placeholder for actual cleanup verification


@pytest.mark.e2e
@pytest.mark.slow
class TestErrorScenarios:
    """Test error handling in E2E scenarios."""

    def test_command_with_no_bastion_available(self):
        """Test graceful failure when bastion not available."""
        # Try to connect to private VM in VNet without bastion
        result = subprocess.run(
            ["azlin", "w", "--rg", "azlin-no-bastion-rg"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should fail with helpful message
        if result.returncode != 0:
            assert (
                "bastion" in result.stderr.lower()
                or "connectivity" in result.stderr.lower()
                or "No reachable VMs" in result.stdout
            )

    def test_command_with_bastion_auth_failure(self):
        """Test handling of bastion authentication failure."""
        # This would require a test setup with invalid credentials
        # Placeholder for actual test implementation
        pass

    def test_command_with_network_timeout(self):
        """Test handling of network timeouts through bastion."""
        # This would require a test setup with forced timeout
        # Placeholder for actual test implementation
        pass
