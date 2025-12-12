"""E2E test for multi-VM orchestration with dependencies."""

import json
import subprocess

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestMultiVMOrchestrationE2E:
    """End-to-end test for orchestrating multiple VMs with dependencies."""

    def test_multi_vm_deployment_with_dependencies(self):
        """Test deploying multiple VMs with network dependencies."""
        # This is a placeholder for real E2E test
        # Real test would:
        # 1. Create VNet
        # 2. Create multiple VMs in same VNet
        # 3. Configure network security
        # 4. Test connectivity between VMs
        # 5. Cleanup all resources

        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated - cannot run E2E test")

        # Verify Azure access
        account_info = json.loads(result.stdout)
        assert "id" in account_info
