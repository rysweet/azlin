"""Unit tests for the azlin logs command.

Tests cover:
- CLI syntax validation (help, options, argument handling)
- Log command building logic
- Error handling for invalid log types
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from azlin.cli import main
from azlin.commands.logs import _build_log_command


class TestLogsCommandSyntax:
    """Test CLI syntax for 'azlin logs' command."""

    def test_logs_help(self):
        """Test 'azlin logs --help' displays usage."""
        runner = CliRunner()
        result = runner.invoke(main, ["logs", "--help"])

        assert result.exit_code == 0
        assert "VM_IDENTIFIER" in result.output
        assert "--lines" in result.output
        assert "--follow" in result.output
        assert "--type" in result.output
        assert "cloud-init" in result.output

    def test_logs_no_args_fails(self):
        """Test 'azlin logs' with no VM identifier fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["logs"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_logs_invalid_type_rejected(self):
        """Test invalid --type value is rejected by click."""
        runner = CliRunner()
        result = runner.invoke(main, ["logs", "myvm", "--type", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()

    def test_logs_valid_types_accepted(self):
        """Test all valid log types are listed in help."""
        runner = CliRunner()
        result = runner.invoke(main, ["logs", "--help"])

        assert "cloud-init" in result.output
        assert "syslog" in result.output
        assert "auth" in result.output


class TestBuildLogCommand:
    """Test the _build_log_command helper."""

    def test_cloud_init_default(self):
        """cloud-init uses cat + tail."""
        cmd = _build_log_command("cloud-init", 50, follow=False)
        assert "cloud-init-output.log" in cmd
        assert "tail -n 50" in cmd

    def test_cloud_init_custom_lines(self):
        """cloud-init respects custom line count."""
        cmd = _build_log_command("cloud-init", 200, follow=False)
        assert "tail -n 200" in cmd

    def test_syslog_uses_journalctl(self):
        """syslog uses journalctl with -n."""
        cmd = _build_log_command("syslog", 100, follow=False)
        assert "journalctl" in cmd
        assert "-n 100" in cmd
        assert "--no-pager" in cmd

    def test_auth_uses_journalctl_ssh(self):
        """auth targets ssh unit in journalctl."""
        cmd = _build_log_command("auth", 50, follow=False)
        assert "journalctl" in cmd
        assert "-u ssh" in cmd
        assert "-n 50" in cmd

    def test_follow_cloud_init(self):
        """Follow mode uses tail -f for cloud-init."""
        cmd = _build_log_command("cloud-init", 50, follow=True)
        assert "tail -f" in cmd
        assert "cloud-init-output.log" in cmd

    def test_follow_syslog(self):
        """Follow mode uses journalctl -f for syslog."""
        cmd = _build_log_command("syslog", 50, follow=True)
        assert "journalctl -f" in cmd

    def test_follow_auth(self):
        """Follow mode uses journalctl -f -u ssh for auth."""
        cmd = _build_log_command("auth", 50, follow=True)
        assert "journalctl -f" in cmd
        assert "-u ssh" in cmd


class TestLogsCommandExecution:
    """Test logs command execution with mocked SSH."""

    @patch("azlin.commands.logs._get_ssh_config_for_vm")
    @patch("azlin.commands.logs.RemoteExecutor")
    def test_logs_fetches_cloud_init_by_default(self, mock_executor_cls, mock_get_ssh):
        """Default invocation fetches cloud-init log."""
        mock_ssh_config = MagicMock()
        mock_get_ssh.return_value = mock_ssh_config

        mock_result = MagicMock()
        mock_result.stdout = "cloud-init log output here"
        mock_result.stderr = ""
        mock_result.success = True
        mock_executor_cls.execute_command.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["logs", "test-vm"])

        assert result.exit_code == 0
        assert "cloud-init log output here" in result.output
        mock_get_ssh.assert_called_once_with("test-vm", None, None)

        # Verify the remote command targets cloud-init
        call_args = mock_executor_cls.execute_command.call_args
        remote_cmd = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("command", "")
        assert "cloud-init" in remote_cmd

    @patch("azlin.commands.logs._get_ssh_config_for_vm")
    @patch("azlin.commands.logs.RemoteExecutor")
    def test_logs_with_syslog_type(self, mock_executor_cls, mock_get_ssh):
        """--type syslog fetches system journal."""
        mock_ssh_config = MagicMock()
        mock_get_ssh.return_value = mock_ssh_config

        mock_result = MagicMock()
        mock_result.stdout = "syslog output"
        mock_result.stderr = ""
        mock_result.success = True
        mock_executor_cls.execute_command.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["logs", "test-vm", "--type", "syslog"])

        assert result.exit_code == 0
        call_args = mock_executor_cls.execute_command.call_args
        remote_cmd = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("command", "")
        assert "journalctl" in remote_cmd

    @patch("azlin.commands.logs._get_ssh_config_for_vm")
    @patch("azlin.commands.logs.RemoteExecutor")
    def test_logs_custom_lines(self, mock_executor_cls, mock_get_ssh):
        """--lines option passes through to remote command."""
        mock_ssh_config = MagicMock()
        mock_get_ssh.return_value = mock_ssh_config

        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.success = True
        mock_executor_cls.execute_command.return_value = mock_result

        runner = CliRunner()
        result = runner.invoke(main, ["logs", "test-vm", "-n", "200"])

        assert result.exit_code == 0
        call_args = mock_executor_cls.execute_command.call_args
        remote_cmd = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("command", "")
        assert "200" in remote_cmd

    @patch("azlin.commands.logs._get_ssh_config_for_vm")
    def test_logs_ssh_key_error(self, mock_get_ssh):
        """SSHKeyError produces a clear error message."""

        mock_get_ssh.side_effect = SystemExit(1)

        runner = CliRunner()
        result = runner.invoke(main, ["logs", "bad-vm"])

        assert result.exit_code != 0
