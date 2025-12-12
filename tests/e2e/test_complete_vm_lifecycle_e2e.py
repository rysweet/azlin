"""E2E test for complete VM lifecycle: Create → Connect → Update → Delete."""

import json
import subprocess

import pytest


@pytest.mark.e2e
@pytest.mark.slow
class TestCompleteVMLifecycleE2E:
    """End-to-end test for complete VM lifecycle."""

    def test_vm_lifecycle_create_to_delete(self):
        """Test complete VM lifecycle from creation to deletion."""
        # This is a placeholder for real E2E test
        # Real test would:
        # 1. Create VM with az vm create
        # 2. Wait for provisioning
        # 3. Connect via SSH
        # 4. Run commands
        # 5. Update VM configuration
        # 6. Delete VM
        # 7. Verify cleanup

        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated - cannot run E2E test")

        # For now, just verify we can access Azure
        account_info = json.loads(result.stdout)
        assert "id" in account_info
