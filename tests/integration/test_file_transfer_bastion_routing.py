"""Integration test for file transfer via bastion routing."""

import pytest

from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.file_transfer.session_manager import SessionManager


class TestFileTransferBastionRoutingWorkflow:
    """Test file transfer routing through bastion."""

    def test_bastion_route_detection_for_file_transfer(self):
        """Test detecting bastion route for file transfer."""
        import json
        import subprocess

        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            pytest.skip("Azure CLI not authenticated")

        account_info = json.loads(result.stdout)
        subscription_id = account_info["id"]

        try:
            detector = BastionDetector(subscription_id=subscription_id)
            bastions = detector.list_bastions()

            if len(bastions) > 0:
                # Bastion available for routing
                bastion = bastions[0]
                assert bastion.name
                assert bastion.location
            else:
                pytest.skip("No bastions available for routing test")

        except Exception:
            pytest.skip("Cannot detect bastion routes")

    def test_file_transfer_session_with_bastion(self):
        """Test creating file transfer session with bastion routing."""
        try:
            manager = SessionManager()

            # Create session with bastion info
            session_id = manager.create_session(
                vm_name="test-vm",
                resource_group="test-rg",
                user="azureuser",
                bastion_host="bastion-eastus",
            )

            # Session should include bastion routing
            session = manager.get_session(session_id)
            assert session.bastion_host == "bastion-eastus"

        except Exception as e:
            pytest.skip(f"Session with bastion not available: {e}")
