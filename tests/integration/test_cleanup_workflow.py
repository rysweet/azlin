"""Integration tests for orphaned resource cleanup workflow.

Tests the complete cleanup orchestration:
- Orphaned Bastion detection
- Cost savings calculation
- User interaction for cleanup decisions
- Resource deletion with rollback safety
- Cleanup result reporting

These tests verify the CleanupOrchestrator with mocked Azure CLI.
"""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

from azlin.modules.cleanup_orchestrator import (
    CleanupOrchestrator,
    OrphanedBastionInfo,
)
from azlin.modules.interaction_handler import MockInteractionHandler
from azlin.vm_manager import VMInfo


class TestOrphanedBastionDetection:
    """Test detection of orphaned Bastion hosts."""

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("subprocess.run")
    def test_detect_orphaned_bastions_none_found(self, mock_run, mock_list_vms):
        """Test detection when all Bastions are in use."""
        # Arrange
        mock_list_vms.return_value = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip=None,  # No public IP = using Bastion
                vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1",
            ),
        ]

        # List Bastions
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "bastion1",
                        "location": "eastus",
                        "provisioningState": "Succeeded",
                        "sku": {"name": "Standard"},
                    }
                ]
            ),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        orphaned = orchestrator.detect_orphaned_bastions()

        # Assert
        assert len(orphaned) == 0  # Bastion is being used by vm1

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("subprocess.run")
    def test_detect_orphaned_bastions_one_found(self, mock_run, mock_list_vms):
        """Test detection of single orphaned Bastion."""
        # Arrange
        # VM is in westus, but Bastion is in eastus (orphaned)
        mock_list_vms.return_value = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="westus",  # Different region
                power_state="VM running",
                public_ip=None,
                vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm1",
            ),
        ]

        # List Bastions
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "orphaned-bastion",
                        "location": "eastus",  # No VMs in this region
                        "provisioningState": "Succeeded",
                        "sku": {"name": "Standard"},
                        "ipConfigurations": [
                            {
                                "subnet": {
                                    "id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/virtualNetworks/my-vnet/subnets/AzureBastionSubnet"
                                },
                                "publicIPAddress": {
                                    "id": "/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Network/publicIPAddresses/bastion-pip"
                                },
                            }
                        ],
                    }
                ]
            ),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        orphaned = orchestrator.detect_orphaned_bastions()

        # Assert
        assert len(orphaned) == 1
        bastion = orphaned[0]
        assert bastion.name == "orphaned-bastion"
        assert bastion.location == "eastus"
        assert bastion.vm_count == 0
        assert bastion.estimated_monthly_cost > 0
        assert bastion.public_ip_name == "bastion-pip"

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("subprocess.run")
    def test_detect_orphaned_bastions_multiple_regions(self, mock_run, mock_list_vms):
        """Test detection across multiple regions."""
        # Arrange
        mock_list_vms.return_value = [
            # VM in westus using Bastion
            VMInfo(
                name="vm-west",
                resource_group="test-rg",
                location="westus",
                power_state="VM running",
                public_ip=None,
                vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm-west",
            ),
            # VM in eastus with public IP (not using Bastion)
            VMInfo(
                name="vm-east",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="20.1.2.3",  # Has public IP
                vm_id="/subscriptions/sub/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/vm-east",
            ),
        ]

        # List Bastions
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "bastion-west",
                        "location": "westus",
                        "provisioningState": "Succeeded",
                        "sku": {"name": "Standard"},
                    },
                    {
                        "name": "bastion-east",
                        "location": "eastus",
                        "provisioningState": "Succeeded",
                        "sku": {"name": "Standard"},
                    },
                ]
            ),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        orphaned = orchestrator.detect_orphaned_bastions()

        # Assert
        # bastion-west is in use, bastion-east is orphaned
        assert len(orphaned) == 1
        assert orphaned[0].name == "bastion-east"

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("subprocess.run")
    def test_detect_orphaned_bastions_skips_non_succeeded(self, mock_run, mock_list_vms):
        """Test detection skips Bastions not in Succeeded state."""
        # Arrange
        mock_list_vms.return_value = []

        # List Bastions with various states
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "bastion-creating",
                        "location": "eastus",
                        "provisioningState": "Creating",  # Not succeeded
                    },
                    {
                        "name": "bastion-failed",
                        "location": "westus",
                        "provisioningState": "Failed",  # Not succeeded
                    },
                ]
            ),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        orphaned = orchestrator.detect_orphaned_bastions()

        # Assert
        # Should skip non-succeeded Bastions
        assert len(orphaned) == 0


class TestOrphanedBastionInfoCost:
    """Test cost calculation for orphaned Bastions."""

    def test_calculate_cost_standard_sku(self):
        """Test cost calculation for Standard SKU."""
        # Arrange
        bastion = OrphanedBastionInfo(
            name="my-bastion",
            resource_group="test-rg",
            location="eastus",
            sku="Standard",
        )

        # Act
        bastion.calculate_cost()

        # Assert
        # $140 Bastion + $3.65 public IP
        assert bastion.estimated_monthly_cost == Decimal("143.65")

    def test_calculate_cost_premium_sku(self):
        """Test cost calculation for Premium SKU."""
        # Arrange
        bastion = OrphanedBastionInfo(
            name="my-bastion",
            resource_group="test-rg",
            location="eastus",
            sku="Premium",
        )

        # Act
        bastion.calculate_cost()

        # Assert
        # $230 Bastion + $3.65 public IP
        assert bastion.estimated_monthly_cost == Decimal("233.65")

    def test_calculate_cost_unknown_sku_uses_basic(self):
        """Test cost calculation defaults to Basic for unknown SKU."""
        # Arrange
        bastion = OrphanedBastionInfo(
            name="my-bastion",
            resource_group="test-rg",
            location="eastus",
            sku=None,  # Unknown SKU
        )

        # Act
        bastion.calculate_cost()

        # Assert
        # Should default to Basic pricing: $140 + $3.65
        assert bastion.estimated_monthly_cost == Decimal("143.65")


class TestCleanupDecisionPrompt:
    """Test user prompting for cleanup decisions."""

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("builtins.input")
    def test_cleanup_decision_user_confirms_delete(self, mock_input, mock_list_vms, mock_run):
        """Test user confirms deletion."""
        # Arrange
        mock_list_vms.return_value = []
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "orphaned-bastion",
                        "location": "eastus",
                        "provisioningState": "Succeeded",
                        "sku": {"name": "Standard"},
                    }
                ]
            ),
        )

        mock_input.return_value = "delete"  # User confirms

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        orphaned = [
            OrphanedBastionInfo(
                name="orphaned-bastion",
                resource_group="test-rg",
                location="eastus",
                sku="Standard",
                estimated_monthly_cost=Decimal("143.65"),
            )
        ]

        # Act
        decision = orchestrator._prompt_cleanup_decision(
            orphaned=orphaned,
            total_savings=Decimal("143.65"),
            force=False,
        )

        # Assert
        assert decision.approved is True
        assert "orphaned-bastion" in decision.resources_to_delete
        assert decision.estimated_savings == Decimal("143.65")
        assert decision.cancelled is False

    @patch("builtins.input")
    def test_cleanup_decision_user_cancels(self, mock_input):
        """Test user cancels cleanup."""
        # Arrange
        mock_input.return_value = "cancel"

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        orphaned = [
            OrphanedBastionInfo(
                name="bastion1",
                resource_group="test-rg",
                location="eastus",
            )
        ]

        # Act
        decision = orchestrator._prompt_cleanup_decision(
            orphaned=orphaned,
            total_savings=Decimal("143.65"),
            force=False,
        )

        # Assert
        assert decision.approved is False
        assert decision.cancelled is True

    def test_cleanup_decision_force_flag_skips_prompt(self):
        """Test force flag skips user prompt."""
        # Arrange
        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        orphaned = [
            OrphanedBastionInfo(
                name="bastion1",
                resource_group="test-rg",
                location="eastus",
            )
        ]

        # Act
        decision = orchestrator._prompt_cleanup_decision(
            orphaned=orphaned,
            total_savings=Decimal("100.0"),
            force=True,  # Force approval
        )

        # Assert
        assert decision.approved is True
        assert "bastion1" in decision.resources_to_delete

    def test_cleanup_decision_dry_run_approves_without_prompt(self):
        """Test dry run approves without prompt."""
        # Arrange
        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
            dry_run=True,
        )

        orphaned = [
            OrphanedBastionInfo(
                name="bastion1",
                resource_group="test-rg",
                location="eastus",
            )
        ]

        # Act
        decision = orchestrator._prompt_cleanup_decision(
            orphaned=orphaned,
            total_savings=Decimal("100.0"),
            force=False,
        )

        # Assert
        assert decision.approved is True
        assert decision.dry_run is True


class TestBastionCleanupExecution:
    """Test Bastion cleanup execution."""

    @patch("subprocess.run")
    def test_cleanup_bastion_success(self, mock_run):
        """Test successful Bastion cleanup."""
        # Arrange
        mock_run.side_effect = [
            # Delete Bastion
            Mock(returncode=0),
            # Delete public IP
            Mock(returncode=0),
        ]

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        result = orchestrator.cleanup_bastion(
            bastion_name="my-bastion",
            location="eastus",
            public_ip_name="my-bastion-pip",
        )

        # Assert
        assert result.was_successful() is True
        assert "my-bastion" in result.deleted_resources
        assert "my-bastion-pip" in result.deleted_resources
        assert len(result.failed_resources) == 0
        assert result.estimated_monthly_savings > 0

    @patch("subprocess.run")
    def test_cleanup_bastion_auto_detects_public_ip(self, mock_run):
        """Test cleanup auto-detects public IP name."""
        # Arrange
        mock_run.side_effect = [
            # Auto-detect public IP - try first name pattern
            Mock(returncode=0, stdout=json.dumps({"name": "my-bastionPublicIP"})),
            # Delete Bastion
            Mock(returncode=0),
            # Delete public IP
            Mock(returncode=0),
        ]

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        result = orchestrator.cleanup_bastion(
            bastion_name="my-bastion",
            location="eastus",
            # No public_ip_name provided - should auto-detect
        )

        # Assert
        assert "my-bastion" in result.deleted_resources
        # Should have detected and deleted public IP
        assert len(result.deleted_resources) >= 1

    @patch("subprocess.run")
    def test_cleanup_bastion_partial_failure(self, mock_run):
        """Test partial failure during cleanup."""
        # Arrange
        mock_run.side_effect = [
            # Delete Bastion - success
            Mock(returncode=0),
            # Delete public IP - FAILS
            Mock(returncode=1, stderr="ResourceInUse"),
        ]

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        result = orchestrator.cleanup_bastion(
            bastion_name="my-bastion",
            location="eastus",
            public_ip_name="my-pip",
        )

        # Assert
        assert result.was_successful() is False
        assert "my-bastion" in result.deleted_resources
        assert "my-pip" in result.failed_resources
        assert len(result.errors) > 0

    @patch("subprocess.run")
    def test_cleanup_bastion_dry_run(self, mock_run):
        """Test dry run mode doesn't delete resources."""
        # Arrange
        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
            dry_run=True,
        )

        # Act
        result = orchestrator.cleanup_bastion(
            bastion_name="my-bastion",
            location="eastus",
            public_ip_name="my-pip",
        )

        # Assert
        # Should track what would be deleted
        assert len(result.deleted_resources) > 0
        assert all("[DRY RUN]" in r for r in result.deleted_resources)
        # No actual Azure CLI calls
        assert mock_run.call_count == 0


class TestCleanupOrchestratedWorkflow:
    """Test complete orchestrated cleanup workflow."""

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    @patch("builtins.input")
    def test_cleanup_orphaned_bastions_complete_workflow(self, mock_input, mock_list_vms, mock_run):
        """Test complete workflow: detect -> prompt -> delete -> report."""
        # Arrange
        mock_list_vms.return_value = []  # No VMs

        def run_side_effect(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "bastion list" in cmd_str:
                # List orphaned Bastions
                return Mock(
                    returncode=0,
                    stdout=json.dumps(
                        [
                            {
                                "name": "orphaned-bastion-1",
                                "location": "eastus",
                                "provisioningState": "Succeeded",
                                "sku": {"name": "Standard"},
                                "ipConfigurations": [
                                    {"publicIPAddress": {"id": "/subscriptions/.../pip1"}}
                                ],
                            },
                            {
                                "name": "orphaned-bastion-2",
                                "location": "westus",
                                "provisioningState": "Succeeded",
                                "sku": {"name": "Standard"},
                                "ipConfigurations": [
                                    {"publicIPAddress": {"id": "/subscriptions/.../pip2"}}
                                ],
                            },
                        ]
                    ),
                )
            if "bastion delete" in cmd_str or "public-ip delete" in cmd_str:
                return Mock(returncode=0)
            return Mock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect
        mock_input.return_value = "delete"  # User confirms

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        results = orchestrator.cleanup_orphaned_bastions(force=False)

        # Assert
        assert len(results) == 2
        assert all(r.was_successful() for r in results)
        assert results[0].bastion_name == "orphaned-bastion-1"
        assert results[1].bastion_name == "orphaned-bastion-2"

        # Verify total savings
        total_savings = sum(r.estimated_monthly_savings for r in results)
        assert total_savings > 0

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_cleanup_orphaned_bastions_no_orphans_found(self, mock_list_vms, mock_run):
        """Test workflow when no orphaned Bastions found."""
        # Arrange
        mock_list_vms.return_value = [
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip=None,
                vm_id="/subscriptions/.../vm1",
            )
        ]

        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "bastion1",
                        "location": "eastus",
                        "provisioningState": "Succeeded",
                    }
                ]
            ),
        )

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act
        results = orchestrator.cleanup_orphaned_bastions()

        # Assert
        assert len(results) == 0
        # Should show info message
        infos = handler.get_interactions_by_type("info")
        assert len(infos) > 0


class TestGetVMsUsingBastion:
    """Test getting VMs that use Bastion."""

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_get_vms_using_bastion_filters_by_region(self, mock_list_vms):
        """Test filtering VMs by region."""
        # Arrange
        mock_list_vms.return_value = [
            VMInfo(
                name="vm-east",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip=None,  # No public IP
                vm_id="/subscriptions/.../vm-east",
            ),
            VMInfo(
                name="vm-west",
                resource_group="test-rg",
                location="westus",
                power_state="VM running",
                public_ip=None,
                vm_id="/subscriptions/.../vm-west",
            ),
        ]

        orchestrator = CleanupOrchestrator(resource_group="test-rg")

        # Act
        vms = orchestrator.get_vms_using_bastion(location="eastus")

        # Assert
        assert len(vms) == 1
        assert vms[0].name == "vm-east"

    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_get_vms_using_bastion_excludes_public_ip_vms(self, mock_list_vms):
        """Test excluding VMs with public IPs."""
        # Arrange
        mock_list_vms.return_value = [
            VMInfo(
                name="vm-with-bastion",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip=None,  # Using Bastion
                vm_id="/subscriptions/.../vm1",
            ),
            VMInfo(
                name="vm-with-public-ip",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip="20.1.2.3",  # Not using Bastion
                vm_id="/subscriptions/.../vm2",
            ),
        ]

        orchestrator = CleanupOrchestrator(resource_group="test-rg")

        # Act
        vms = orchestrator.get_vms_using_bastion(location="eastus")

        # Assert
        assert len(vms) == 1
        assert vms[0].name == "vm-with-bastion"


class TestEndToEndCleanupWorkflow:
    """Integration test for complete cleanup workflow."""

    @patch("subprocess.run")
    @patch("azlin.modules.cleanup_orchestrator.VMManager.list_vms")
    def test_complete_cleanup_workflow_with_cost_savings(self, mock_list_vms, mock_run):
        """Test complete cleanup with cost savings reporting."""
        # Arrange
        mock_list_vms.return_value = []  # No VMs

        def run_side_effect(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)

            if "bastion list" in cmd_str:
                return Mock(
                    returncode=0,
                    stdout=json.dumps(
                        [
                            {
                                "name": "expensive-bastion",
                                "location": "eastus",
                                "provisioningState": "Succeeded",
                                "sku": {"name": "Premium"},  # More expensive
                            }
                        ]
                    ),
                )
            if "bastion delete" in cmd_str:
                return Mock(returncode=0)
            return Mock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect

        handler = MockInteractionHandler()
        orchestrator = CleanupOrchestrator(
            resource_group="test-rg",
            interaction_handler=handler,
        )

        # Act - Force approval to skip prompt
        results = orchestrator.cleanup_orphaned_bastions(force=True)

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.bastion_name == "expensive-bastion"
        assert result.estimated_monthly_savings > Decimal("140")  # Premium SKU

        # Verify interaction messages showed savings
        infos = handler.get_interactions_by_type("info")
        assert len(infos) > 0
