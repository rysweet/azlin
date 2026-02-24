"""Unit tests for azlin.cli_helpers module.

Tests the public API of cli_helpers.py, the most critical untested module
used by every CLI command. Organized by category:

1. Pure logic (no external deps): generate_vm_name, _resolve_tmux_session,
   _validate_config_path, _select_vms_by_criteria, _validate_batch_selection
2. SSHConfigBuilder: has_direct_connectivity, is_reachable, filter_reachable_vms,
   build_for_vm, build_for_vms
3. Display functions: _display_killall_results, _display_batch_summary,
   _print_routing_summary
4. Mock-based: execute_command_on_vm, _is_valid_vm_name, _generate_clone_configs,
   _confirm_batch_operation, _handle_delete_resource_group
"""

from pathlib import Path
from unittest.mock import Mock, patch

import click
import pytest

from azlin.vm_manager import VMInfo

# ============================================================================
# HELPERS: Factory functions for test data
# ============================================================================


def make_vm_info(
    name: str = "test-vm",
    resource_group: str = "test-rg",
    location: str = "eastus",
    power_state: str = "VM running",
    public_ip: str | None = "20.1.2.3",
    private_ip: str | None = "10.0.0.4",
    vm_size: str | None = "Standard_B2s",
    session_name: str | None = None,
    tags: dict | None = None,
) -> VMInfo:
    """Create a VMInfo with sensible defaults for testing."""
    return VMInfo(
        name=name,
        resource_group=resource_group,
        location=location,
        power_state=power_state,
        public_ip=public_ip,
        private_ip=private_ip,
        vm_size=vm_size,
        session_name=session_name,
        tags=tags,
    )


# ============================================================================
# 1. PURE LOGIC TESTS
# ============================================================================


class TestGenerateVmName:
    """Tests for generate_vm_name - VM name generation logic."""

    @patch("azlin.cli_helpers.RemoteExecutor")
    def test_custom_name_returned_as_is(self, mock_re):
        from azlin.cli_helpers import generate_vm_name

        result = generate_vm_name(custom_name="my-special-vm")
        assert result == "my-special-vm"

    @patch("azlin.cli_helpers.RemoteExecutor")
    def test_no_args_returns_timestamped_name(self, mock_re):
        from azlin.cli_helpers import generate_vm_name

        result = generate_vm_name()
        assert result.startswith("azlin-")
        # Format: azlin-YYYYMMDD-HHMMSS
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS

    @patch("azlin.cli_helpers.RemoteExecutor")
    def test_with_command_includes_slug(self, mock_re):
        from azlin.cli_helpers import generate_vm_name

        mock_re.extract_command_slug.return_value = "npm-test"
        result = generate_vm_name(command="npm test")
        assert result.startswith("azlin-")
        assert result.endswith("-npm-test")
        mock_re.extract_command_slug.assert_called_once_with("npm test")

    @patch("azlin.cli_helpers.RemoteExecutor")
    def test_custom_name_takes_precedence_over_command(self, mock_re):
        from azlin.cli_helpers import generate_vm_name

        result = generate_vm_name(custom_name="priority-name", command="npm test")
        assert result == "priority-name"
        mock_re.extract_command_slug.assert_not_called()


class TestResolveTmuxSession:
    """Tests for _resolve_tmux_session - tmux session name resolution."""

    def test_no_tmux_returns_none(self):
        from azlin.cli_helpers import _resolve_tmux_session

        result = _resolve_tmux_session("vm-1", tmux_session=None, no_tmux=True, config=None)
        assert result is None

    def test_explicit_session_name_returned(self):
        from azlin.cli_helpers import _resolve_tmux_session

        result = _resolve_tmux_session(
            "vm-1", tmux_session="my-session", no_tmux=False, config=None
        )
        assert result == "my-session"

    def test_default_session_is_azlin(self):
        from azlin.cli_helpers import _resolve_tmux_session

        result = _resolve_tmux_session("vm-1", tmux_session=None, no_tmux=False, config=None)
        assert result == "azlin"

    def test_no_tmux_overrides_explicit_session(self):
        from azlin.cli_helpers import _resolve_tmux_session

        result = _resolve_tmux_session("vm-1", tmux_session="my-session", no_tmux=True, config=None)
        assert result is None


class TestValidateConfigPath:
    """Tests for _validate_config_path - Click parameter validator."""

    def test_none_value_passes_through(self):
        from azlin.cli_helpers import _validate_config_path

        result = _validate_config_path(ctx=None, param=None, value=None)
        assert result is None

    def test_valid_path_passes_through(self, tmp_path):
        from azlin.cli_helpers import _validate_config_path

        config_file = str(tmp_path / "config.toml")
        result = _validate_config_path(ctx=None, param=None, value=config_file)
        assert result == config_file

    def test_nonexistent_parent_raises_bad_parameter(self):
        from azlin.cli_helpers import _validate_config_path

        with pytest.raises(click.BadParameter, match="Parent directory does not exist"):
            _validate_config_path(
                ctx=None,
                param=None,
                value="/nonexistent/path/config.toml",
            )


class TestValidateBatchSelection:
    """Tests for _validate_batch_selection - mutual exclusion of batch options."""

    def test_no_selection_exits(self):
        from azlin.cli_helpers import _validate_batch_selection

        with pytest.raises(SystemExit):
            _validate_batch_selection(tag=None, vm_pattern=None, select_all=False)

    def test_multiple_selections_exits(self):
        from azlin.cli_helpers import _validate_batch_selection

        with pytest.raises(SystemExit):
            _validate_batch_selection(tag="web", vm_pattern="azlin-*", select_all=False)

    def test_single_tag_passes(self):
        from azlin.cli_helpers import _validate_batch_selection

        # Should not raise
        _validate_batch_selection(tag="web", vm_pattern=None, select_all=False)

    def test_single_pattern_passes(self):
        from azlin.cli_helpers import _validate_batch_selection

        _validate_batch_selection(tag=None, vm_pattern="azlin-*", select_all=False)

    def test_select_all_passes(self):
        from azlin.cli_helpers import _validate_batch_selection

        _validate_batch_selection(tag=None, vm_pattern=None, select_all=True)


class TestSelectVmsByCriteria:
    """Tests for _select_vms_by_criteria - VM filtering logic."""

    def test_select_all_returns_all_vms(self):
        from azlin.cli_helpers import _select_vms_by_criteria

        vms = [make_vm_info(name="vm-1"), make_vm_info(name="vm-2")]
        selected, desc = _select_vms_by_criteria(vms, tag=None, vm_pattern=None, select_all=True)
        assert selected is vms
        assert desc == "all VMs"

    @patch("azlin.cli_helpers.BatchSelector")
    def test_select_by_tag(self, mock_selector):
        from azlin.cli_helpers import _select_vms_by_criteria

        all_vms = [make_vm_info(name="vm-1"), make_vm_info(name="vm-2")]
        mock_selector.select_by_tag.return_value = [all_vms[0]]

        selected, desc = _select_vms_by_criteria(
            all_vms, tag="web", vm_pattern=None, select_all=False
        )
        assert len(selected) == 1
        assert desc == "tag 'web'"
        mock_selector.select_by_tag.assert_called_once_with(all_vms, "web")

    @patch("azlin.cli_helpers.BatchSelector")
    def test_select_by_pattern(self, mock_selector):
        from azlin.cli_helpers import _select_vms_by_criteria

        all_vms = [make_vm_info(name="azlin-1"), make_vm_info(name="other-vm")]
        mock_selector.select_by_pattern.return_value = [all_vms[0]]

        selected, desc = _select_vms_by_criteria(
            all_vms, tag=None, vm_pattern="azlin-*", select_all=False
        )
        assert len(selected) == 1
        assert desc == "pattern 'azlin-*'"


# ============================================================================
# 2. SSHConfigBuilder TESTS
# ============================================================================


class TestSSHConfigBuilderHasDirectConnectivity:
    """Tests for SSHConfigBuilder.has_direct_connectivity."""

    def test_vm_with_public_ip_has_direct(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(public_ip="20.1.2.3")
        assert SSHConfigBuilder.has_direct_connectivity(vm) is True

    def test_vm_without_public_ip_no_direct(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(public_ip=None)
        assert SSHConfigBuilder.has_direct_connectivity(vm) is False

    def test_vm_with_empty_public_ip_no_direct(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(public_ip="")
        assert SSHConfigBuilder.has_direct_connectivity(vm) is False

    def test_vm_with_whitespace_public_ip_no_direct(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(public_ip="   ")
        assert SSHConfigBuilder.has_direct_connectivity(vm) is False


class TestSSHConfigBuilderIsReachable:
    """Tests for SSHConfigBuilder.is_reachable."""

    def test_running_vm_with_public_ip_is_reachable(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM running", public_ip="20.1.2.3")
        assert SSHConfigBuilder.is_reachable(vm) is True

    def test_running_vm_with_private_ip_only_is_reachable(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM running", public_ip=None, private_ip="10.0.0.4")
        assert SSHConfigBuilder.is_reachable(vm) is True

    def test_stopped_vm_is_not_reachable(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM stopped", public_ip="20.1.2.3")
        assert SSHConfigBuilder.is_reachable(vm) is False

    def test_deallocated_vm_is_not_reachable(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM deallocated", public_ip="20.1.2.3")
        assert SSHConfigBuilder.is_reachable(vm) is False

    def test_running_vm_no_ips_is_not_reachable(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM running", public_ip=None, private_ip=None)
        assert SSHConfigBuilder.is_reachable(vm) is False


class TestSSHConfigBuilderFilterReachable:
    """Tests for SSHConfigBuilder.filter_reachable_vms."""

    def test_filters_to_running_with_ip(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vms = [
            make_vm_info(name="running-pub", power_state="VM running", public_ip="20.1.2.3"),
            make_vm_info(name="stopped", power_state="VM stopped", public_ip="20.1.2.4"),
            make_vm_info(
                name="running-priv", power_state="VM running", public_ip=None, private_ip="10.0.0.5"
            ),
            make_vm_info(name="no-ip", power_state="VM running", public_ip=None, private_ip=None),
        ]
        result = SSHConfigBuilder.filter_reachable_vms(vms)
        names = [vm.name for vm in result]
        assert "running-pub" in names
        assert "running-priv" in names
        assert "stopped" not in names
        assert "no-ip" not in names

    def test_empty_list_returns_empty(self):
        from azlin.cli_helpers import SSHConfigBuilder

        assert SSHConfigBuilder.filter_reachable_vms([]) == []


class TestSSHConfigBuilderBuildForVm:
    """Tests for SSHConfigBuilder.build_for_vm."""

    def test_direct_ssh_for_public_ip_vm(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM running", public_ip="20.1.2.3")
        key_path = Path("/tmp/test_key")

        config = SSHConfigBuilder.build_for_vm(vm, key_path)
        assert config.host == "20.1.2.3"
        assert config.port == 22
        assert config.user == "azureuser"
        assert config.key_path == key_path

    def test_raises_for_stopped_vm(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM stopped", public_ip="20.1.2.3")
        with pytest.raises(ValueError, match="not running"):
            SSHConfigBuilder.build_for_vm(vm, Path("/tmp/key"))

    def test_raises_for_vm_with_no_ips(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM running", public_ip=None, private_ip=None)
        with pytest.raises(ValueError, match="no IP addresses"):
            SSHConfigBuilder.build_for_vm(vm, Path("/tmp/key"))

    def test_raises_for_private_only_vm_without_bastion(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(power_state="VM running", public_ip=None, private_ip="10.0.0.4")
        with pytest.raises(ValueError, match="Bastion manager required"):
            SSHConfigBuilder.build_for_vm(vm, Path("/tmp/key"), bastion_manager=None)

    def test_bastion_tunnel_for_private_only_vm(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vm = make_vm_info(
            name="priv-vm",
            resource_group="test-rg",
            power_state="VM running",
            public_ip=None,
            private_ip="10.0.0.4",
        )
        mock_bastion = Mock()
        mock_tunnel = Mock()
        mock_tunnel.local_port = 2222
        mock_bastion.create_tunnel.return_value = mock_tunnel

        config = SSHConfigBuilder.build_for_vm(vm, Path("/tmp/key"), bastion_manager=mock_bastion)
        assert config.host == "127.0.0.1"
        assert config.port == 2222
        mock_bastion.create_tunnel.assert_called_once()


class TestSSHConfigBuilderBuildForVms:
    """Tests for SSHConfigBuilder.build_for_vms - batch config building."""

    def test_builds_configs_for_reachable_vms_only(self):
        from azlin.cli_helpers import SSHConfigBuilder

        vms = [
            make_vm_info(name="good", power_state="VM running", public_ip="20.1.2.3"),
            make_vm_info(name="stopped", power_state="VM stopped", public_ip="20.1.2.4"),
        ]
        configs = SSHConfigBuilder.build_for_vms(vms, Path("/tmp/key"))
        assert len(configs) == 1
        assert configs[0].host == "20.1.2.3"

    def test_empty_vms_returns_empty(self):
        from azlin.cli_helpers import SSHConfigBuilder

        configs = SSHConfigBuilder.build_for_vms([], Path("/tmp/key"))
        assert configs == []


# ============================================================================
# 3. DISPLAY FUNCTION TESTS (verify output, not internals)
# ============================================================================


class TestDisplayKillallResults:
    """Tests for _display_killall_results - output formatting."""

    def test_displays_summary_counts(self, capsys):
        from azlin.cli_helpers import _display_killall_results
        from azlin.vm_lifecycle import DeletionResult, DeletionSummary

        summary = DeletionSummary(
            total=3,
            succeeded=2,
            failed=1,
            results=[
                DeletionResult(vm_name="vm-1", success=True, message="deleted"),
                DeletionResult(vm_name="vm-2", success=True, message="deleted"),
                DeletionResult(vm_name="vm-3", success=False, message="timeout"),
            ],
        )
        _display_killall_results(summary)
        output = capsys.readouterr().out

        assert "Total VMs:     3" in output
        assert "Succeeded:     2" in output
        assert "Failed:        1" in output
        assert "vm-1" in output
        assert "vm-3" in output
        assert "timeout" in output


class TestDisplayBatchSummary:
    """Tests for _display_batch_summary - batch operation output."""

    def test_displays_operation_name(self, capsys):
        from azlin.cli_helpers import _display_batch_summary

        mock_result = Mock()
        mock_result.format_summary.return_value = "2 succeeded, 0 failed"
        mock_result.failed = 0
        mock_result.get_failures.return_value = []

        _display_batch_summary(mock_result, "restart")
        output = capsys.readouterr().out

        assert "Batch restart Summary" in output
        assert "2 succeeded, 0 failed" in output

    def test_displays_failures(self, capsys):
        from azlin.cli_helpers import _display_batch_summary

        failure = Mock()
        failure.vm_name = "bad-vm"
        failure.message = "connection refused"

        mock_result = Mock()
        mock_result.format_summary.return_value = "1 succeeded, 1 failed"
        mock_result.failed = 1
        mock_result.get_failures.return_value = [failure]

        _display_batch_summary(mock_result, "stop")
        output = capsys.readouterr().out

        assert "bad-vm" in output
        assert "connection refused" in output


class TestPrintRoutingSummary:
    """Tests for _print_routing_summary - routing decision output."""

    def test_empty_lists_produce_no_output(self, capsys):
        from azlin.cli_helpers import _print_routing_summary

        _print_routing_summary([], [])
        output = capsys.readouterr().out
        assert output == ""

    def test_reachable_direct_count(self, capsys):
        from azlin.cli_helpers import _print_routing_summary

        route = Mock()
        route.routing_method = "direct"
        _print_routing_summary([route], [])
        output = capsys.readouterr().out
        assert "1 reachable" in output
        assert "1 direct" in output

    def test_unreachable_shows_reason(self, capsys):
        from azlin.cli_helpers import _print_routing_summary

        unreachable = Mock()
        unreachable.vm_name = "bad-vm"
        unreachable.skip_reason = "No IP"
        _print_routing_summary([], [unreachable])
        output = capsys.readouterr().out
        assert "1 unreachable" in output
        assert "bad-vm" in output
        assert "No IP" in output


# ============================================================================
# 4. MOCK-BASED TESTS (functions that call external services)
# ============================================================================


class TestExecuteCommandOnVm:
    """Tests for execute_command_on_vm - SSH command execution."""

    def test_returns_1_if_vm_not_running(self, capsys):
        from azlin.cli_helpers import execute_command_on_vm

        vm = make_vm_info(power_state="VM stopped")
        result = execute_command_on_vm(vm, "ls", Path("/tmp/key"))
        assert result == 1
        assert "not running" in capsys.readouterr().err

    def test_returns_1_if_vm_no_public_ip(self, capsys):
        from azlin.cli_helpers import execute_command_on_vm

        vm = make_vm_info(power_state="VM running", public_ip=None)
        result = execute_command_on_vm(vm, "ls", Path("/tmp/key"))
        assert result == 1
        assert "no public IP" in capsys.readouterr().err

    @patch("azlin.cli_helpers.SSHConnector")
    @patch("azlin.cli_helpers.subprocess.run")
    def test_returns_exit_code_from_subprocess(self, mock_run, mock_connector, capsys):
        from azlin.cli_helpers import execute_command_on_vm

        mock_connector.build_ssh_command.return_value = ["ssh", "args"]
        mock_run.return_value = Mock(returncode=42)

        vm = make_vm_info(power_state="VM running", public_ip="20.1.2.3")
        result = execute_command_on_vm(vm, "exit 42", Path("/tmp/key"))
        assert result == 42

    @patch("azlin.cli_helpers.SSHConnector")
    @patch("azlin.cli_helpers.subprocess.run")
    def test_returns_0_on_success(self, mock_run, mock_connector, capsys):
        from azlin.cli_helpers import execute_command_on_vm

        mock_connector.build_ssh_command.return_value = ["ssh", "args"]
        mock_run.return_value = Mock(returncode=0)

        vm = make_vm_info(power_state="VM running", public_ip="20.1.2.3")
        result = execute_command_on_vm(vm, "echo hello", Path("/tmp/key"))
        assert result == 0
        assert "successfully" in capsys.readouterr().out

    @patch("azlin.cli_helpers.SSHConnector")
    @patch("azlin.cli_helpers.subprocess.run")
    def test_returns_1_on_exception(self, mock_run, mock_connector, capsys):
        from azlin.cli_helpers import execute_command_on_vm

        mock_connector.build_ssh_command.return_value = ["ssh", "args"]
        mock_run.side_effect = OSError("connection refused")

        vm = make_vm_info(power_state="VM running", public_ip="20.1.2.3")
        result = execute_command_on_vm(vm, "echo hello", Path("/tmp/key"))
        assert result == 1
        assert "Error executing" in capsys.readouterr().err


class TestIsValidVmName:
    """Tests for _is_valid_vm_name - VM name existence check."""

    @patch("azlin.cli_helpers.VMManager")
    @patch("azlin.cli_helpers.ConfigManager")
    def test_returns_true_for_existing_vm(self, mock_config, mock_vmm):
        from azlin.cli_helpers import _is_valid_vm_name

        mock_config.get_resource_group.return_value = "my-rg"
        mock_vmm.get_vm.return_value = make_vm_info()
        assert _is_valid_vm_name("test-vm", None) is True

    @patch("azlin.cli_helpers.VMManager")
    @patch("azlin.cli_helpers.ConfigManager")
    def test_returns_false_for_nonexistent_vm(self, mock_config, mock_vmm):
        from azlin.cli_helpers import _is_valid_vm_name

        mock_config.get_resource_group.return_value = "my-rg"
        mock_vmm.get_vm.return_value = None
        assert _is_valid_vm_name("ghost-vm", None) is False

    @patch("azlin.cli_helpers.ConfigManager")
    def test_returns_false_when_no_resource_group(self, mock_config):
        from azlin.cli_helpers import _is_valid_vm_name

        mock_config.get_resource_group.return_value = None
        assert _is_valid_vm_name("vm-1", None) is False

    @patch("azlin.cli_helpers.ConfigManager")
    def test_returns_false_on_exception(self, mock_config):
        from azlin.cli_helpers import _is_valid_vm_name

        mock_config.get_resource_group.side_effect = RuntimeError("boom")
        assert _is_valid_vm_name("vm-1", None) is False


class TestGenerateCloneConfigs:
    """Tests for _generate_clone_configs - clone VM config generation."""

    def test_generates_correct_number_of_configs(self):
        from azlin.cli_helpers import _generate_clone_configs

        source = make_vm_info(
            name="source-vm",
            resource_group="my-rg",
            location="westus2",
            vm_size="Standard_D4s_v3",
        )
        configs = _generate_clone_configs(source, num_replicas=3, vm_size=None, region=None)
        assert len(configs) == 3

    def test_uses_source_attributes_when_no_overrides(self):
        from azlin.cli_helpers import _generate_clone_configs

        source = make_vm_info(
            resource_group="my-rg",
            location="westus2",
            vm_size="Standard_D4s_v3",
        )
        configs = _generate_clone_configs(source, num_replicas=1, vm_size=None, region=None)
        assert configs[0].size == "Standard_D4s_v3"
        assert configs[0].location == "westus2"
        assert configs[0].resource_group == "my-rg"

    def test_overrides_size_and_region(self):
        from azlin.cli_helpers import _generate_clone_configs

        source = make_vm_info(
            resource_group="my-rg",
            location="westus2",
            vm_size="Standard_D4s_v3",
        )
        configs = _generate_clone_configs(
            source, num_replicas=1, vm_size="Standard_B1s", region="eastus"
        )
        assert configs[0].size == "Standard_B1s"
        assert configs[0].location == "eastus"

    def test_vm_names_are_unique(self):
        from azlin.cli_helpers import _generate_clone_configs

        source = make_vm_info(resource_group="rg")
        configs = _generate_clone_configs(source, num_replicas=5, vm_size=None, region=None)
        names = [c.name for c in configs]
        assert len(set(names)) == 5  # all unique

    def test_vm_names_follow_naming_convention(self):
        from azlin.cli_helpers import _generate_clone_configs

        source = make_vm_info(resource_group="rg")
        configs = _generate_clone_configs(source, num_replicas=2, vm_size=None, region=None)
        for config in configs:
            assert config.name.startswith("azlin-vm-")

    def test_defaults_to_standard_b2s_when_source_has_no_size(self):
        from azlin.cli_helpers import _generate_clone_configs

        source = make_vm_info(resource_group="rg", vm_size=None)
        configs = _generate_clone_configs(source, num_replicas=1, vm_size=None, region=None)
        assert configs[0].size == "Standard_B2s"


class TestConfirmBatchOperation:
    """Tests for _confirm_batch_operation - user confirmation logic."""

    def test_auto_confirm_returns_true(self):
        from azlin.cli_helpers import _confirm_batch_operation

        # confirm=True means --yes flag was passed, skip prompt
        result = _confirm_batch_operation(num_vms=5, operation="restart", confirm=True)
        assert result is True

    @patch("builtins.input", return_value="y")
    def test_user_confirms_returns_true(self, mock_input):
        from azlin.cli_helpers import _confirm_batch_operation

        result = _confirm_batch_operation(num_vms=5, operation="restart", confirm=False)
        assert result is True

    @patch("builtins.input", return_value="n")
    def test_user_declines_returns_false(self, mock_input):
        from azlin.cli_helpers import _confirm_batch_operation

        result = _confirm_batch_operation(num_vms=5, operation="restart", confirm=False)
        assert result is False


class TestHandleDeleteResourceGroup:
    """Tests for _handle_delete_resource_group - dry run and deletion."""

    def test_dry_run_does_not_delete(self, capsys):
        from azlin.cli_helpers import _handle_delete_resource_group

        _handle_delete_resource_group(rg="my-rg", vm_name="vm-1", force=False, dry_run=True)
        output = capsys.readouterr().out
        assert "[DRY RUN]" in output
        assert "my-rg" in output

    @patch("azlin.cli_helpers.subprocess.run")
    @patch("builtins.input", return_value="my-rg")
    def test_confirmed_deletion_runs_az_command(self, mock_input, mock_run, capsys):
        from azlin.cli_helpers import _handle_delete_resource_group

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        _handle_delete_resource_group(rg="my-rg", vm_name="vm-1", force=False, dry_run=False)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "az" in cmd
        assert "group" in cmd
        assert "delete" in cmd

    @patch("builtins.input", return_value="wrong-name")
    def test_mismatched_name_cancels(self, mock_input, capsys):
        from azlin.cli_helpers import _handle_delete_resource_group

        _handle_delete_resource_group(rg="my-rg", vm_name="vm-1", force=False, dry_run=False)
        output = capsys.readouterr().out
        assert "Cancelled" in output

    @patch("azlin.cli_helpers.subprocess.run")
    def test_force_skips_confirmation(self, mock_run, capsys):
        from azlin.cli_helpers import _handle_delete_resource_group

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        _handle_delete_resource_group(rg="my-rg", vm_name="vm-1", force=True, dry_run=False)
        mock_run.assert_called_once()
        output = capsys.readouterr().out
        assert "Success" in output


class TestHandleVmDryRun:
    """Tests for _handle_vm_dry_run - VM deletion dry run."""

    @patch("azlin.cli_helpers.VMManager")
    def test_displays_vm_info_on_dry_run(self, mock_vmm, capsys):
        from azlin.cli_helpers import _handle_vm_dry_run

        mock_vmm.get_vm.return_value = make_vm_info(
            name="my-vm", public_ip="20.1.2.3", vm_size="Standard_B2s"
        )
        _handle_vm_dry_run("my-vm", "my-rg")
        output = capsys.readouterr().out
        assert "[DRY RUN]" in output
        assert "my-vm" in output
        assert "Associated NICs" in output

    @patch("azlin.cli_helpers.VMManager")
    def test_exits_if_vm_not_found(self, mock_vmm):
        from azlin.cli_helpers import _handle_vm_dry_run

        mock_vmm.get_vm.return_value = None
        with pytest.raises(SystemExit):
            _handle_vm_dry_run("ghost-vm", "my-rg")


class TestGetSshConfigsForVms:
    """Tests for get_ssh_configs_for_vms - batch SSH config resolution."""

    def test_empty_vms_returns_empty(self):
        from azlin.cli_helpers import get_ssh_configs_for_vms

        configs, routes = get_ssh_configs_for_vms([], ssh_key_path=Path("/tmp/key"))
        assert configs == []
        assert routes == []

    @patch("azlin.cli_helpers._print_routing_summary")
    @patch("azlin.cli_helpers.SSHRoutingResolver")
    def test_returns_configs_for_reachable_vms(self, mock_resolver, mock_print):
        from azlin.cli_helpers import get_ssh_configs_for_vms
        from azlin.modules.ssh_connector import SSHConfig

        mock_config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/tmp/key"))
        mock_route = Mock()
        mock_route.ssh_config = mock_config
        mock_route.routing_method = "direct"

        mock_resolver.resolve_routes_batch.return_value = [mock_route]

        vms = [make_vm_info(name="vm-1")]
        configs, routes = get_ssh_configs_for_vms(
            vms, ssh_key_path=Path("/tmp/key"), show_summary=True
        )
        assert len(configs) == 1
        assert configs[0].host == "20.1.2.3"


class TestAutoSyncHomeDirectory:
    """Tests for _auto_sync_home_directory - silent sync before SSH."""

    @patch("azlin.cli_helpers.HomeSyncManager")
    def test_silent_success(self, mock_sync):
        from azlin.cli_helpers import _auto_sync_home_directory
        from azlin.modules.ssh_connector import SSHConfig

        mock_result = Mock()
        mock_result.success = True
        mock_result.files_synced = 3
        mock_sync.sync_to_vm.return_value = mock_result

        config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/tmp/key"))
        # Should not raise
        _auto_sync_home_directory(config)
        mock_sync.sync_to_vm.assert_called_once_with(config, dry_run=False)

    @patch("azlin.cli_helpers.HomeSyncManager")
    def test_silent_failure_does_not_raise(self, mock_sync):
        from azlin.cli_helpers import _auto_sync_home_directory
        from azlin.modules.ssh_connector import SSHConfig

        mock_sync.sync_to_vm.side_effect = RuntimeError("network error")

        config = SSHConfig(host="20.1.2.3", user="azureuser", key_path=Path("/tmp/key"))
        # Should NOT raise - failures are silent
        _auto_sync_home_directory(config)
