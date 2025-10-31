"""Integration tests for security audit logging with CLI orchestrator.

These tests verify that the SecurityAuditLogger is properly integrated
with the CLI bastion decision flow.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.cli import CLIOrchestrator
from azlin.security_audit import SecurityAuditLogger


class TestSecurityAuditIntegrationWithCLI:
    """Test SecurityAuditLogger integration with CLI orchestrator."""

    @pytest.fixture
    def audit_file_path(self, tmp_path, monkeypatch):
        """Create temporary audit file path for testing."""
        audit_dir = tmp_path / ".azlin"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / "security_audit.json"

        # Monkeypatch the AUDIT_FILE class attribute
        monkeypatch.setattr(SecurityAuditLogger, "AUDIT_FILE", audit_file)

        yield audit_file

        # Cleanup
        if audit_file.exists():
            audit_file.unlink()

    @pytest.fixture
    def orchestrator(self):
        """Create CLI orchestrator instance."""
        return CLIOrchestrator(
            resource_group="test-rg",
            no_bastion=False
        )

    def test_check_bastion_availability_logs_flag_opt_out(self, orchestrator, audit_file_path):
        """Test that --no-bastion flag opt-out is logged."""
        # Set no_bastion flag
        orchestrator.no_bastion = True

        # Mock click.confirm to simulate user declining
        with patch("azlin.cli.click.confirm", return_value=True):
            use_bastion, bastion_info = orchestrator._check_bastion_availability(
                resource_group="test-rg",
                vm_name="test-vm"
            )

        # Verify return values
        assert use_bastion is False
        assert bastion_info is None

        # Verify audit log entry
        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == 1
        entry = audit_log[0]
        assert entry["vm_name"] == "test-vm"
        assert entry["method"] == "flag"
        assert entry["security_impact"] == "VM will have public IP exposed to internet"

    def test_check_bastion_availability_logs_existing_decline(self, orchestrator, audit_file_path):
        """Test that declining existing bastion is logged."""
        # Mock bastion detection to return existing bastion
        mock_bastion_info = {
            "name": "my-bastion",
            "resource_group": "test-rg"
        }

        with patch("azlin.cli.BastionDetector.detect_bastion_for_vm", return_value=mock_bastion_info):
            with patch("azlin.cli.click.confirm", return_value=False):  # User declines
                use_bastion, bastion_info = orchestrator._check_bastion_availability(
                    resource_group="test-rg",
                    vm_name="test-vm"
                )

        # Verify return values
        assert use_bastion is False
        assert bastion_info is None

        # Verify audit log entry
        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == 1
        entry = audit_log[0]
        assert entry["vm_name"] == "test-vm"
        assert entry["method"] == "prompt_existing"
        assert entry["security_impact"] == "VM will have public IP exposed to internet"

    def test_check_bastion_availability_logs_create_decline(self, orchestrator, audit_file_path):
        """Test that declining to create bastion is logged."""
        # Mock bastion detection to return None (no bastion found)
        with patch("azlin.cli.BastionDetector.detect_bastion_for_vm", return_value=None):
            with patch("azlin.cli.click.confirm", return_value=False):  # User declines creation
                use_bastion, bastion_info = orchestrator._check_bastion_availability(
                    resource_group="test-rg",
                    vm_name="test-vm"
                )

        # Verify return values
        assert use_bastion is False
        assert bastion_info is None

        # Verify audit log entry
        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == 1
        entry = audit_log[0]
        assert entry["vm_name"] == "test-vm"
        assert entry["method"] == "prompt_create"
        assert entry["security_impact"] == "VM will have public IP exposed to internet"

    def test_check_bastion_availability_accepts_existing_no_log(self, orchestrator, audit_file_path):
        """Test that accepting existing bastion does NOT create audit log."""
        # Mock bastion detection to return existing bastion
        mock_bastion_info = {
            "name": "my-bastion",
            "resource_group": "test-rg"
        }

        with patch("azlin.cli.BastionDetector.detect_bastion_for_vm", return_value=mock_bastion_info):
            with patch("azlin.cli.click.confirm", return_value=True):  # User accepts
                use_bastion, bastion_info = orchestrator._check_bastion_availability(
                    resource_group="test-rg",
                    vm_name="test-vm"
                )

        # Verify return values
        assert use_bastion is True
        assert bastion_info == mock_bastion_info

        # Verify NO audit log entry (secure choice should not be logged)
        assert not audit_file_path.exists()

    def test_multiple_opt_outs_logged_chronologically(self, orchestrator, audit_file_path):
        """Test that multiple opt-out decisions are logged in order."""
        orchestrator.no_bastion = True

        vms = ["vm-1", "vm-2", "vm-3"]

        with patch("azlin.cli.click.confirm", return_value=True):
            for vm_name in vms:
                orchestrator._check_bastion_availability(
                    resource_group="test-rg",
                    vm_name=vm_name
                )

        # Verify all entries logged
        with open(audit_file_path) as f:
            audit_log = json.load(f)

        assert len(audit_log) == 3
        for i, vm_name in enumerate(vms):
            assert audit_log[i]["vm_name"] == vm_name
            assert audit_log[i]["method"] == "flag"

    def test_no_bastion_flag_confirmation_cancel(self, orchestrator, audit_file_path):
        """Test that cancelling --no-bastion confirmation raises Abort."""
        import click

        orchestrator.no_bastion = True

        with patch("azlin.cli.click.confirm", return_value=False):  # User cancels
            with pytest.raises(click.Abort):
                orchestrator._check_bastion_availability(
                    resource_group="test-rg",
                    vm_name="test-vm"
                )

        # Verify NO audit log entry (user cancelled)
        assert not audit_file_path.exists()

    def test_orchestrator_has_bastion_attributes(self):
        """Test that CLIOrchestrator has required bastion attributes."""
        orchestrator = CLIOrchestrator(
            no_bastion=True,
            bastion_name="my-bastion"
        )

        assert hasattr(orchestrator, "no_bastion")
        assert hasattr(orchestrator, "bastion_name")
        assert orchestrator.no_bastion is True
        assert orchestrator.bastion_name == "my-bastion"
