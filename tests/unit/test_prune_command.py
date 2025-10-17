"""
Unit tests for azlin prune command.

Tests the VM pruning functionality for identifying and deleting inactive VMs.

Test Coverage:
- VM filtering by age threshold
- VM filtering by idle time threshold
- Excluding running VMs by default
- Excluding named sessions by default
- --include-running flag
- --include-named flag
- --dry-run mode (no actual deletion)
- --force mode (no confirmation prompt)
- Age calculation from creation time
- Idle calculation from last_connected
- Handling VMs without last_connected data
- Config cleanup after deletion
- Partial deletion failures
- No VMs eligible message
- Confirmation prompt behavior
- Table display formatting
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from azlin.vm_manager import VMInfo

# ============================================================================
# VM FILTERING TESTS - AGE AND IDLE THRESHOLDS
# ============================================================================


class TestVMFilteringByAge:
    """Test VM filtering by age threshold."""

    def test_filter_vms_by_age_threshold(self):
        """Test that VMs older than age threshold are included for pruning.

        Validates:
        - VMs created more than age_days ago are included
        - VMs created recently are excluded
        - Age is calculated from created_time field
        """
        from azlin.prune import PruneManager

        # Create VMs with different ages
        now = datetime.utcnow()
        old_vm = VMInfo(
            name="old-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )
        recent_vm = VMInfo(
            name="recent-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=5)).isoformat() + "Z",
        )

        vms = [old_vm, recent_vm]
        age_days = 30

        filtered = PruneManager.filter_by_age(vms, age_days)

        # Only old VM should be included
        assert len(filtered) == 1
        assert filtered[0].name == "old-vm"

    def test_filter_vms_exactly_at_age_threshold(self):
        """Test edge case: VM exactly at age threshold is included.

        Validates:
        - VM created exactly age_days ago is included (>= check)
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        exact_age_vm = VMInfo(
            name="exact-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=30)).isoformat() + "Z",
        )

        filtered = PruneManager.filter_by_age([exact_age_vm], age_days=30)

        assert len(filtered) == 1
        assert filtered[0].name == "exact-vm"

    def test_filter_vms_without_created_time(self):
        """Test handling of VMs without created_time metadata.

        Validates:
        - VMs without created_time are excluded (cannot determine age)
        - No errors are raised
        """
        from azlin.prune import PruneManager

        vm_no_time = VMInfo(
            name="no-time-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=None,
        )

        filtered = PruneManager.filter_by_age([vm_no_time], age_days=30)

        assert len(filtered) == 0


class TestVMFilteringByIdle:
    """Test VM filtering by idle time threshold."""

    def test_filter_vms_by_idle_threshold(self):
        """Test that VMs idle longer than threshold are included.

        Validates:
        - VMs with last_connected > idle_days ago are included
        - Recently connected VMs are excluded
        - Idle is calculated from last_connected timestamp
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        idle_vm = VMInfo(
            name="idle-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
        )
        active_vm = VMInfo(
            name="active-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
        )

        # Mock connection tracking data
        connection_data = {
            "idle-vm": {"last_connected": (now - timedelta(days=20)).isoformat() + "Z"},
            "active-vm": {"last_connected": (now - timedelta(days=2)).isoformat() + "Z"},
        }

        filtered = PruneManager.filter_by_idle(
            [idle_vm, active_vm], idle_days=14, connection_data=connection_data
        )

        assert len(filtered) == 1
        assert filtered[0].name == "idle-vm"

    def test_filter_vms_never_connected(self):
        """Test VMs that have never been connected to.

        Validates:
        - VMs without last_connected data are treated as never used
        - They should be included for pruning if old enough
        """
        from azlin.prune import PruneManager

        never_connected_vm = VMInfo(
            name="never-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
        )

        # Empty connection data
        connection_data = {}

        filtered = PruneManager.filter_by_idle(
            [never_connected_vm], idle_days=14, connection_data=connection_data
        )

        # Never connected VMs should be included (considered maximally idle)
        assert len(filtered) == 1
        assert filtered[0].name == "never-vm"

    def test_filter_combines_age_and_idle(self):
        """Test that both age and idle filters are applied together.

        Validates:
        - VM must be both old enough AND idle long enough
        - Both conditions must be true
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()

        # Old but recently used - should be excluded
        old_active_vm = VMInfo(
            name="old-active-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        # Recent but idle - should be excluded
        recent_idle_vm = VMInfo(
            name="recent-idle-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=5)).isoformat() + "Z",
        )

        # Old and idle - should be included
        prune_candidate_vm = VMInfo(
            name="prune-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        connection_data = {
            "old-active-vm": {"last_connected": (now - timedelta(days=2)).isoformat() + "Z"},
            "recent-idle-vm": {"last_connected": (now - timedelta(days=20)).isoformat() + "Z"},
            "prune-vm": {"last_connected": (now - timedelta(days=35)).isoformat() + "Z"},
        }

        filtered = PruneManager.filter_for_pruning(
            [old_active_vm, recent_idle_vm, prune_candidate_vm],
            age_days=30,
            idle_days=14,
            connection_data=connection_data,
        )

        assert len(filtered) == 1
        assert filtered[0].name == "prune-vm"


# ============================================================================
# EXCLUSION FILTERS - RUNNING VMS AND NAMED SESSIONS
# ============================================================================


class TestRunningVMExclusion:
    """Test exclusion of running VMs by default."""

    def test_exclude_running_vms_by_default(self):
        """Test that running VMs are excluded from pruning by default.

        Validates:
        - VMs with power_state 'VM running' are excluded
        - Only stopped/deallocated VMs are included
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        running_vm = VMInfo(
            name="running-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )
        stopped_vm = VMInfo(
            name="stopped-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        filtered = PruneManager.filter_for_pruning(
            [running_vm, stopped_vm],
            age_days=30,
            idle_days=14,
            connection_data={},
            include_running=False,
        )

        assert len(filtered) == 1
        assert filtered[0].name == "stopped-vm"

    def test_include_running_vms_with_flag(self):
        """Test that --include-running flag includes running VMs.

        Validates:
        - When include_running=True, running VMs are included
        - Useful for aggressive cleanup
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        running_vm = VMInfo(
            name="running-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        filtered = PruneManager.filter_for_pruning(
            [running_vm],
            age_days=30,
            idle_days=14,
            connection_data={},
            include_running=True,
        )

        assert len(filtered) == 1
        assert filtered[0].name == "running-vm"


class TestNamedSessionExclusion:
    """Test exclusion of named sessions by default."""

    @patch("azlin.config_manager.ConfigManager.get_session_name")
    def test_exclude_named_sessions_by_default(self, mock_get_session_name):
        """Test that VMs with session names are excluded by default.

        Validates:
        - VMs with session names in config are excluded
        - Users have explicitly named these, showing intent to keep
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        named_vm = VMInfo(
            name="named-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name=None,  # Will be populated from ConfigManager
        )
        unnamed_vm = VMInfo(
            name="unnamed-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name=None,
        )

        # Mock ConfigManager to return session name for named VM
        def mock_session_lookup(vm_name):
            if vm_name == "named-vm":
                return "my-important-session"
            return None

        mock_get_session_name.side_effect = mock_session_lookup

        filtered = PruneManager.filter_for_pruning(
            [named_vm, unnamed_vm],
            age_days=30,
            idle_days=14,
            connection_data={},
            include_named=False,
        )

        assert len(filtered) == 1
        assert filtered[0].name == "unnamed-vm"

    @patch("azlin.config_manager.ConfigManager.get_session_name")
    def test_include_named_sessions_with_flag(self, mock_get_session_name):
        """Test that --include-named flag includes named sessions.

        Validates:
        - When include_named=True, named sessions are included
        - Allows pruning of all old VMs regardless of naming
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        named_vm = VMInfo(
            name="named-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name=None,  # Will be populated from ConfigManager
        )

        # Mock ConfigManager to return session name
        mock_get_session_name.return_value = "old-session"

        filtered = PruneManager.filter_for_pruning(
            [named_vm],
            age_days=30,
            idle_days=14,
            connection_data={},
            include_named=True,
        )

        assert len(filtered) == 1
        assert filtered[0].name == "named-vm"

    @patch("azlin.config_manager.ConfigManager.get_session_name")
    def test_session_names_populated_from_config_manager(self, mock_get_session_name):
        """Test that session names are populated from ConfigManager before filtering.

        This is the CRITICAL BUG FIX TEST. Previously, session_name was None because
        it wasn't populated from config, causing the filter to fail and named VMs
        to be incorrectly deleted.

        Validates:
        - ConfigManager.get_session_name is called for each VM
        - session_name is set on VMInfo objects before filtering
        - VMs with session names are excluded by default
        - This reproduces the exact bug scenario that deleted active VMs
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()

        # Create VMs WITHOUT session_name set (simulating real Azure data)
        # This is how VMManager.list_vms() returns them - session_name is None
        named_vm = VMInfo(
            name="amplihack",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name=None,  # Initially None - will be populated from config
        )

        unnamed_vm = VMInfo(
            name="unnamed-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name=None,
        )

        # Mock ConfigManager to return session name for named VM only
        def mock_session_lookup(vm_name):
            if vm_name == "amplihack":
                return "production-session"
            return None

        mock_get_session_name.side_effect = mock_session_lookup

        # Filter for pruning
        filtered = PruneManager.filter_for_pruning(
            [named_vm, unnamed_vm],
            age_days=30,
            idle_days=14,
            connection_data={},
            include_named=False,
        )

        # Verify ConfigManager was called for both VMs
        assert mock_get_session_name.call_count == 2
        mock_get_session_name.assert_any_call("amplihack")
        mock_get_session_name.assert_any_call("unnamed-vm")

        # Verify session_name was populated on the VM object
        assert named_vm.session_name == "production-session"
        assert unnamed_vm.session_name is None

        # Verify only unnamed VM is in pruning candidates (CRITICAL: named VM excluded)
        assert len(filtered) == 1
        assert filtered[0].name == "unnamed-vm"

    @patch("azlin.config_manager.ConfigManager.get_session_name")
    def test_session_name_population_happens_before_filtering(self, mock_get_session_name):
        """Test that session names are populated BEFORE any filtering occurs.

        Validates:
        - Session name population is the FIRST step
        - Happens before age, idle, running, or named filters
        - All VMs get session names populated regardless of other criteria
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()

        # Create VMs with different states
        vms = [
            # Old, stopped, will be named
            VMInfo(
                name="vm1",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name=None,
            ),
            # Recent (fails age filter), will be named
            VMInfo(
                name="vm2",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=5)).isoformat() + "Z",
                session_name=None,
            ),
            # Running (fails running filter), will be named
            VMInfo(
                name="vm3",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name=None,
            ),
        ]

        # Mock all VMs to have session names
        mock_get_session_name.side_effect = lambda vm_name: f"{vm_name}-session"

        # Filter for pruning
        filtered = PruneManager.filter_for_pruning(
            vms,
            age_days=30,
            idle_days=14,
            connection_data={},
            include_named=False,
        )

        # All VMs should have ConfigManager.get_session_name called
        # even if they fail other filters
        assert mock_get_session_name.call_count == 3
        mock_get_session_name.assert_any_call("vm1")
        mock_get_session_name.assert_any_call("vm2")
        mock_get_session_name.assert_any_call("vm3")

        # No VMs should pass (all have session names and include_named=False)
        assert len(filtered) == 0


# ============================================================================
# SESSION NAME TABLE DISPLAY TESTS
# ============================================================================


class TestSessionNameTableDisplay:
    """Test session name display in prune table output."""

    def test_table_includes_session_name_column(self):
        """Test that prune table includes session name column.

        Validates:
        - Session Name column appears in table header
        - Named VMs show their session name
        - Unnamed VMs show "-"
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()

        vms = [
            VMInfo(
                name="named-vm",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name="production",
            ),
            VMInfo(
                name="unnamed-vm",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name=None,
            ),
        ]

        table = PruneManager.format_prune_table(vms, connection_data={})

        # Verify table includes session name column header
        assert "Session Name" in table

        # Verify named VM shows session name
        assert "production" in table

        # Verify unnamed VM shows dash
        lines = table.split("\n")
        unnamed_line = [line for line in lines if "unnamed-vm" in line][0]
        # Check that the session name column shows a dash
        assert "-" in unnamed_line

        # Verify both VM names are in table
        assert "named-vm" in table
        assert "unnamed-vm" in table


# ============================================================================
# DRY-RUN MODE TESTS
# ============================================================================


class TestDryRunMode:
    """Test --dry-run mode functionality."""

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.vm_manager.subprocess.run")
    def test_dry_run_shows_vms_without_deleting(self, mock_subprocess, mock_list_vms):
        """Test that --dry-run lists VMs but doesn't delete them.

        Validates:
        - VMs are identified and displayed
        - No deletion commands are executed
        - User can see what would be deleted
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [test_vm]

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=True,
            force=False,
        )

        # Should identify VM
        assert len(result["candidates"]) == 1
        assert result["candidates"][0].name == "test-vm"

        # Should not execute any deletion
        assert result["deleted"] == 0
        # Verify no VM deletion commands were called
        mock_subprocess.assert_not_called()

    @patch("azlin.prune.VMManager.list_vms")
    def test_dry_run_shows_table_output(self, mock_list_vms):
        """Test that --dry-run returns candidates without deleting.

        Validates:
        - Returns candidates in result
        - Clear message indicates dry run
        - No deletion occurs
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [test_vm]

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=True,
        )

        # Verify result contains candidates
        assert len(result["candidates"]) == 1
        assert result["candidates"][0].name == "test-vm"
        assert result["deleted"] == 0
        assert "dry run" in result["message"].lower()


# ============================================================================
# FORCE MODE AND CONFIRMATION TESTS
# ============================================================================


class TestForceMode:
    """Test --force mode and confirmation prompts."""

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.prune.VMLifecycleManager.delete_vm")
    def test_force_mode_skips_confirmation(self, mock_delete, mock_list_vms):
        """Test that --force mode deletes without confirmation.

        Validates:
        - No confirmation prompt is shown
        - Deletion proceeds automatically
        - Useful for scripts and automation
        """
        from azlin.prune import PruneManager
        from azlin.vm_lifecycle import DeletionResult

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [test_vm]
        mock_delete.return_value = DeletionResult(
            vm_name="test-vm", success=True, message="Deleted"
        )

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        # VM should be deleted
        mock_delete.assert_called_once_with("test-vm", "test-rg", force=True)
        assert result["deleted"] == 1

    @patch("azlin.prune.VMManager.list_vms")
    def test_confirmation_required_without_force(self, mock_list_vms):
        """Test that confirmation is required without --force.

        Validates:
        - Returns candidates when force=False
        - Deletion is not executed in prune() method
        - CLI layer handles confirmation
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [test_vm]

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=False,
        )

        # Should return candidates without deleting
        assert len(result["candidates"]) == 1
        assert result["deleted"] == 0
        assert result["message"] == "Confirmation required."

    @patch("azlin.prune.VMManager.list_vms")
    def test_confirmation_rejected_prevents_deletion(self, mock_list_vms):
        """Test that without force flag, deletion doesn't happen in prune().

        Validates:
        - Without force=True, no deletion occurs
        - Returns candidates for CLI to handle
        - Safe default behavior
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [test_vm]

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=False,
        )

        # Should return candidates without deletion
        assert len(result["candidates"]) == 1
        assert result["deleted"] == 0


# ============================================================================
# CONFIG CLEANUP TESTS
# ============================================================================


class TestConfigCleanup:
    """Test config file cleanup after VM deletion."""

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.prune.VMLifecycleManager.delete_vm")
    @patch("azlin.prune.ConfigManager.delete_session_name")
    def test_config_cleaned_after_deletion(self, mock_delete_session, mock_delete, mock_list_vms):
        """Test that config is updated to remove deleted VM entries.

        Validates:
        - Session names for deleted VMs are removed
        - Connection tracking for deleted VMs is removed
        """
        from azlin.prune import PruneManager
        from azlin.vm_lifecycle import DeletionResult

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name="test-session",
        )

        mock_list_vms.return_value = [test_vm]
        mock_delete.return_value = DeletionResult(
            vm_name="test-vm", success=True, message="Deleted"
        )

        PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        # Session name should be removed after deletion
        mock_delete_session.assert_called_once_with("test-vm")

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.prune.VMLifecycleManager.delete_vm")
    @patch("azlin.prune.ConfigManager.delete_session_name")
    def test_multiple_vms_cleaned_from_config(
        self, mock_delete_session, mock_delete_vm, mock_list_vms
    ):
        """Test config cleanup for multiple deleted VMs.

        Validates:
        - Each deleted VM has its config entries removed
        - Cleanup is atomic per VM
        - Partial failures don't corrupt config
        """
        from azlin.prune import PruneManager
        from azlin.vm_lifecycle import DeletionResult

        now = datetime.utcnow()
        vm1 = VMInfo(
            name="vm1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name="session1",
        )
        vm2 = VMInfo(
            name="vm2",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name="session2",
        )

        mock_list_vms.return_value = [vm1, vm2]
        mock_delete_vm.return_value = DeletionResult(
            vm_name="test-vm", success=True, message="Deleted"
        )

        PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        # Both VMs should have session names removed
        assert mock_delete_session.call_count == 2
        mock_delete_session.assert_any_call("vm1")
        mock_delete_session.assert_any_call("vm2")


# ============================================================================
# PARTIAL FAILURE HANDLING
# ============================================================================


class TestPartialDeletionFailures:
    """Test handling of partial deletion failures."""

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.prune.VMLifecycleManager.delete_vm")
    def test_partial_deletion_failure_continues(self, mock_delete, mock_list_vms):
        """Test that failure to delete one VM doesn't stop others.

        Validates:
        - Failed deletion is logged
        - Other VMs are still attempted
        - Final report shows successes and failures
        """
        from azlin.prune import PruneManager
        from azlin.vm_lifecycle import DeletionResult

        now = datetime.utcnow()
        vm1 = VMInfo(
            name="vm1",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )
        vm2 = VMInfo(
            name="vm2",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [vm1, vm2]

        # First deletion fails, second succeeds
        mock_delete.side_effect = [
            Exception("Azure error"),
            DeletionResult(vm_name="test-vm", success=True, message="Deleted"),
        ]

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        # Should attempt both deletions
        assert mock_delete.call_count == 2

        # Should report 1 success, 1 failure
        assert result["deleted"] == 1
        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.prune.VMLifecycleManager.delete_vm")
    def test_deletion_failure_preserves_config(self, mock_delete, mock_list_vms):
        """Test that failed deletion doesn't clean config.

        Validates:
        - If VM deletion fails, config entry is preserved
        - Only successfully deleted VMs have config cleaned
        - Maintains consistency between Azure and config
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        failed_vm = VMInfo(
            name="failed-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
            session_name="important-session",
        )

        mock_list_vms.return_value = [failed_vm]
        mock_delete.side_effect = Exception("Cannot delete VM")

        with patch("azlin.prune.ConfigManager.delete_session_name") as mock_delete_session:
            result = PruneManager.prune(
                resource_group="test-rg",
                age_days=30,
                idle_days=14,
                dry_run=False,
                force=True,
            )

            # Config should NOT be cleaned for failed deletion
            mock_delete_session.assert_not_called()
            assert result["deleted"] == 0
            assert result["failed"] == 1


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("azlin.prune.VMManager.list_vms")
    def test_no_vms_eligible_for_pruning(self, mock_list_vms):
        """Test behavior when no VMs meet pruning criteria.

        Validates:
        - Appropriate message is shown
        - No errors are raised
        - Returns empty result
        """
        from azlin.prune import PruneManager

        # Recent VMs that don't meet criteria
        now = datetime.utcnow()
        recent_vm = VMInfo(
            name="recent-vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            created_time=(now - timedelta(days=5)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [recent_vm]

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        assert len(result["candidates"]) == 0
        assert result["deleted"] == 0
        assert "message" in result
        assert "no vms" in result["message"].lower()

    @patch("azlin.prune.VMManager.list_vms")
    def test_empty_resource_group(self, mock_list_vms):
        """Test behavior with empty resource group.

        Validates:
        - Handles empty VM list gracefully
        - Appropriate message is shown
        - No errors are raised
        """
        from azlin.prune import PruneManager

        mock_list_vms.return_value = []

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        assert len(result["candidates"]) == 0
        assert result["deleted"] == 0

    @patch("azlin.prune.VMManager.list_vms")
    def test_resource_group_not_found(self, mock_list_vms):
        """Test behavior when resource group doesn't exist.

        Validates:
        - Error is handled gracefully
        - Appropriate error message
        - Doesn't crash
        """
        from azlin.prune import PruneManager
        from azlin.vm_manager import VMManagerError

        mock_list_vms.side_effect = VMManagerError("Resource group not found")

        with pytest.raises(VMManagerError):
            PruneManager.prune(
                resource_group="nonexistent-rg",
                age_days=30,
                idle_days=14,
                dry_run=False,
                force=True,
            )


# ============================================================================
# TABLE DISPLAY FORMATTING TESTS
# ============================================================================


class TestTableDisplay:
    """Test detailed information table display."""

    def test_table_shows_vm_details(self):
        """Test that table displays comprehensive VM information.

        Validates:
        - Table includes: name, age, idle time, status, location, size
        - Data is formatted readably
        - Aligned columns
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        test_vm = VMInfo(
            name="test-vm-with-long-name",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            vm_size="Standard_B2s",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        table = PruneManager.format_prune_table([test_vm], connection_data={})

        # Check table output contains key information
        assert "test-vm-with-long-name" in table
        assert "40" in table  # Age in days
        assert "eastus" in table
        assert "Standard_B2s" in table

    def test_table_formats_age_and_idle(self):
        """Test that age and idle time are formatted human-readable.

        Validates:
        - Days are shown with 'd' suffix
        - Large numbers are formatted clearly
        - Never connected shows appropriate indicator
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()
        vm = VMInfo(
            name="vm",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=100)).isoformat() + "Z",
        )

        table = PruneManager.format_prune_table(
            [vm],
            connection_data={},
        )

        assert "100" in table  # Age in days
        assert "days" in table.lower() or "d" in table.lower()

    def test_empty_table_formatting(self):
        """Test table formatting with empty VM list.

        Validates:
        - Handles empty list gracefully
        - Returns appropriate message or empty table
        - No errors raised
        """
        from azlin.prune import PruneManager

        table = PruneManager.format_prune_table([], connection_data={})

        assert table is not None
        assert len(table) > 0  # Should have headers or message


# ============================================================================
# CLI ARGUMENT PARSING TESTS
# ============================================================================


class TestPruneCLIArguments:
    """Test CLI argument parsing for prune command."""

    def test_prune_command_accepts_age_days(self):
        """Test that --age-days argument is accepted.

        Validates:
        - --age-days flag exists
        - Default value is reasonable (e.g., 30)
        - Custom values are accepted
        """
        from azlin.cli import main

        # Test with Click CLI runner
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("azlin.prune.PruneManager.get_candidates") as mock_get_candidates:
            mock_get_candidates.return_value = ([], {})

            result = runner.invoke(main, ["prune", "--age-days", "45", "--force"])

            # Should call get_candidates with custom age_days
            assert mock_get_candidates.called
            call_kwargs = mock_get_candidates.call_args[1]
            assert call_kwargs["age_days"] == 45

    def test_prune_command_accepts_idle_days(self):
        """Test that --idle-days argument is accepted.

        Validates:
        - --idle-days flag exists
        - Default value is reasonable (e.g., 14)
        - Custom values are accepted
        """
        from azlin.cli import main
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("azlin.prune.PruneManager.get_candidates") as mock_get_candidates:
            mock_get_candidates.return_value = ([], {})

            result = runner.invoke(main, ["prune", "--idle-days", "21", "--force"])

            # Should call get_candidates with custom idle_days
            assert mock_get_candidates.called
            call_kwargs = mock_get_candidates.call_args[1]
            assert call_kwargs["idle_days"] == 21

    def test_prune_command_accepts_flags(self):
        """Test that boolean flags are accepted.

        Validates:
        - --dry-run flag
        - --force flag
        - --include-running flag
        - --include-named flag
        """
        from azlin.cli import main
        from click.testing import CliRunner

        runner = CliRunner()

        with patch("azlin.prune.PruneManager.get_candidates") as mock_get_candidates:
            mock_get_candidates.return_value = ([], {})

            result = runner.invoke(
                main, ["prune", "--dry-run", "--include-running", "--include-named"]
            )

            # Should call get_candidates with flags
            assert mock_get_candidates.called
            call_kwargs = mock_get_candidates.call_args[1]
            assert call_kwargs["include_running"] is True
            assert call_kwargs["include_named"] is True


# ============================================================================
# INTEGRATION-STYLE TESTS
# ============================================================================


class TestPruneIntegration:
    """Integration-style tests for complete prune workflow."""

    @patch("azlin.prune.VMManager.list_vms")
    @patch("azlin.prune.VMLifecycleManager.delete_vm")
    def test_full_prune_workflow(self, mock_delete, mock_list_vms):
        """Test complete prune workflow from listing to deletion.

        Validates:
        - List VMs from resource group
        - Filter by age and idle criteria
        - Delete eligible VMs
        - Clean up config
        - Return comprehensive result
        """
        from azlin.prune import PruneManager
        from azlin.vm_lifecycle import DeletionResult

        now = datetime.utcnow()

        # Setup test data
        old_stopped_vm = VMInfo(
            name="prune-me",
            resource_group="test-rg",
            location="eastus",
            power_state="VM deallocated",
            created_time=(now - timedelta(days=40)).isoformat() + "Z",
        )

        recent_vm = VMInfo(
            name="keep-me",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            created_time=(now - timedelta(days=5)).isoformat() + "Z",
        )

        mock_list_vms.return_value = [old_stopped_vm, recent_vm]
        mock_delete.return_value = DeletionResult(
            vm_name="test-vm", success=True, message="Deleted"
        )

        # Execute full workflow
        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=False,
            force=True,
        )

        # Verify workflow
        mock_list_vms.assert_called_once_with("test-rg", include_stopped=True)
        mock_delete.assert_called_once_with("prune-me", "test-rg", force=True)

        # Verify result
        assert result["deleted"] == 1
        assert result["failed"] == 0
        assert len(result["candidates"]) == 1

    @patch("azlin.config_manager.ConfigManager.get_session_name")
    @patch("azlin.prune.VMManager.list_vms")
    def test_prune_respects_all_filters(self, mock_list_vms, mock_get_session_name):
        """Test that all filters work together correctly.

        Validates:
        - Age filter
        - Idle filter
        - Running VM filter
        - Named session filter
        - All applied in correct order
        """
        from azlin.prune import PruneManager

        now = datetime.utcnow()

        vms = [
            # Should be pruned: old, idle, stopped, unnamed
            VMInfo(
                name="prune-candidate",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name=None,
            ),
            # Should be kept: old but running
            VMInfo(
                name="old-running",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name=None,
            ),
            # Should be kept: old but named
            VMInfo(
                name="old-named",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=40)).isoformat() + "Z",
                session_name=None,  # Will be populated from ConfigManager
            ),
            # Should be kept: recent
            VMInfo(
                name="recent",
                resource_group="test-rg",
                location="eastus",
                power_state="VM deallocated",
                created_time=(now - timedelta(days=5)).isoformat() + "Z",
                session_name=None,
            ),
        ]

        # Mock ConfigManager to return session name only for old-named
        def mock_session_lookup(vm_name):
            if vm_name == "old-named":
                return "important"
            return None

        mock_get_session_name.side_effect = mock_session_lookup
        mock_list_vms.return_value = vms

        result = PruneManager.prune(
            resource_group="test-rg",
            age_days=30,
            idle_days=14,
            dry_run=True,
            force=True,
            include_running=False,
            include_named=False,
        )

        # Only one VM should pass all filters
        assert len(result["candidates"]) == 1
        assert result["candidates"][0].name == "prune-candidate"
