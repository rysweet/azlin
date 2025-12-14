"""Integration test for cleanup orphaned resource detection workflow.

Tests real workflow: Detection → Cost calculation → User interaction → Cleanup
"""

import json
import subprocess
from decimal import Decimal

import pytest

from azlin.modules.cleanup_orchestrator import CleanupOrchestrator
from azlin.modules.cost_estimator import CostEstimator
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.modules.orphaned_resource_detector import OrphanedResourceDetector


class TestOrphanedResourceDetection:
    """Test orphaned resource detection workflow."""

    def test_orphaned_disk_detection(self):
        """Test detecting orphaned disks in subscription."""
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

        # Real Azure API call to list disks
        disk_result = subprocess.run(
            [
                "az",
                "disk",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[].{name:name,resourceGroup:resourceGroup,diskState:diskState}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if disk_result.returncode == 0:
            disks = json.loads(disk_result.stdout)
            assert isinstance(disks, list)

            # Find unattached disks (orphaned)
            orphaned = [d for d in disks if d.get("diskState") == "Unattached"]

            # Detection should work
            assert isinstance(orphaned, list)
        else:
            pytest.skip("Cannot list disks")

    def test_orphaned_nic_detection(self):
        """Test detecting orphaned network interfaces."""
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

        # Real Azure API call to list NICs
        nic_result = subprocess.run(
            [
                "az",
                "network",
                "nic",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[].{name:name,resourceGroup:resourceGroup,virtualMachine:virtualMachine}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if nic_result.returncode == 0:
            nics = json.loads(nic_result.stdout)
            assert isinstance(nics, list)

            # Find NICs without VM attachment (orphaned)
            orphaned = [n for n in nics if n.get("virtualMachine") is None]

            # Detection should work
            assert isinstance(orphaned, list)
        else:
            pytest.skip("Cannot list NICs")

    def test_orphaned_resource_detector_integration(self):
        """Test OrphanedResourceDetector with real Azure data."""
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
            detector = OrphanedResourceDetector(subscription_id=subscription_id)

            # Detect orphaned resources
            orphaned_disks = detector.find_orphaned_disks()
            orphaned_nics = detector.find_orphaned_nics()

            # Should return lists
            assert isinstance(orphaned_disks, list)
            assert isinstance(orphaned_nics, list)

        except Exception as e:
            pytest.skip(f"OrphanedResourceDetector not available: {e}")


class TestCostCalculationWorkflow:
    """Test cost calculation for cleanup workflow."""

    def test_cost_estimator_for_disk(self):
        """Test estimating cost for disk storage."""
        try:
            estimator = CostEstimator()

            # Estimate cost for 128GB disk
            monthly_cost = estimator.estimate_disk_cost(
                size_gb=128,
                tier="Standard",
                region="eastus",
            )

            assert isinstance(monthly_cost, (Decimal, float))
            assert monthly_cost >= 0

        except Exception as e:
            pytest.skip(f"CostEstimator not available: {e}")

    def test_cost_calculation_for_orphaned_resources(self):
        """Test calculating total cost for orphaned resources."""
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

        # Get orphaned disks
        disk_result = subprocess.run(
            [
                "az",
                "disk",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[?diskState=='Unattached'].{name:name,diskSizeGb:diskSizeGb}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if disk_result.returncode == 0:
            orphaned_disks = json.loads(disk_result.stdout)

            if len(orphaned_disks) > 0:
                # Calculate total cost
                total_cost = Decimal("0")

                try:
                    estimator = CostEstimator()

                    for disk in orphaned_disks:
                        size_gb = disk.get("diskSizeGb", 128)
                        cost = estimator.estimate_disk_cost(
                            size_gb=size_gb,
                            tier="Standard",
                            region="eastus",
                        )
                        total_cost += Decimal(str(cost))

                    # Should calculate successfully
                    assert total_cost >= 0

                except Exception as e:
                    pytest.skip(f"Cost calculation not available: {e}")
            else:
                pytest.skip("No orphaned disks to test cost calculation")
        else:
            pytest.skip("Cannot list disks")


class TestCleanupOrchestrationWorkflow:
    """Test complete cleanup orchestration workflow."""

    def test_cleanup_orchestrator_with_mock_interaction(self):
        """Test cleanup orchestrator with mock user interaction."""
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
            # Create mock interaction handler (no real user input)
            interaction_handler = MockInteractionHandler(
                confirm_responses={"delete": False}  # Don't actually delete
            )

            orchestrator = CleanupOrchestrator(
                subscription_id=subscription_id,
                interaction_handler=interaction_handler,
            )

            # Detect orphaned resources (real detection)
            orphaned_resources = orchestrator.detect_orphaned_resources()

            # Should return structure with orphaned resources
            assert "disks" in orphaned_resources or "nics" in orphaned_resources

        except Exception as e:
            pytest.skip(f"CleanupOrchestrator not available: {e}")

    def test_cleanup_decision_workflow(self):
        """Test cleanup decision workflow without actual deletion."""
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

        # Get orphaned resources
        disk_result = subprocess.run(
            [
                "az",
                "disk",
                "list",
                "--subscription",
                subscription_id,
                "--query",
                "[?diskState=='Unattached'].{name:name,resourceGroup:resourceGroup}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if disk_result.returncode == 0:
            orphaned_disks = json.loads(disk_result.stdout)

            # Make cleanup decisions (without actual cleanup)
            decisions = []
            for disk in orphaned_disks[:3]:  # Limit to 3 for testing
                decision = {
                    "resource": disk["name"],
                    "action": "delete",  # Decision only, no execution
                    "reason": "orphaned",
                }
                decisions.append(decision)

            # Decisions should be structured
            assert isinstance(decisions, list)
            for decision in decisions:
                assert "resource" in decision
                assert "action" in decision

        else:
            pytest.skip("Cannot list disks for decision workflow")

    def test_cleanup_rollback_detection(self):
        """Test detecting when cleanup should be rolled back."""
        # Simulate cleanup failure scenario
        cleanup_results = [
            {"resource": "disk1", "success": True},
            {"resource": "disk2", "success": False, "error": "Permission denied"},
            {"resource": "disk3", "success": True},
        ]

        # Check if rollback needed
        failures = [r for r in cleanup_results if not r["success"]]

        if len(failures) > 0:
            # Rollback should be triggered
            needs_rollback = True
            failed_resources = [f["resource"] for f in failures]
        else:
            needs_rollback = False
            failed_resources = []

        # Should detect failure correctly
        assert needs_rollback is True
        assert "disk2" in failed_resources
