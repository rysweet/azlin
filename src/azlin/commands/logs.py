"""Logs command for azlin.

View VM logs (cloud-init, syslog, auth) without a persistent SSH connection.

Commands:
    logs - View logs from a VM
"""

import logging
import subprocess
import sys

import click

from azlin.cli_helpers import _get_ssh_config_for_vm
from azlin.config_manager import ConfigError
from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_keys import SSHKeyError
from azlin.remote_exec import RemoteExecError, RemoteExecutor
from azlin.vm_manager import VMManagerError

logger = logging.getLogger(__name__)

# Map of log type to the remote command that fetches it.
LOG_TYPE_COMMANDS: dict[str, str] = {
    "cloud-init": "sudo cat /var/log/cloud-init-output.log",
    "syslog": "sudo journalctl --no-pager",
    "auth": "sudo journalctl --no-pager -u ssh",
}

# Follow-mode commands (streaming, never terminates on its own).
LOG_TYPE_FOLLOW_COMMANDS: dict[str, str] = {
    "cloud-init": "sudo tail -f /var/log/cloud-init-output.log",
    "syslog": "sudo journalctl -f",
    "auth": "sudo journalctl -f -u ssh",
}

VALID_LOG_TYPES = list(LOG_TYPE_COMMANDS.keys())


def _build_log_command(log_type: str, lines: int, follow: bool) -> str:
    """Build the remote command string for the requested log type.

    Args:
        log_type: One of cloud-init, syslog, auth.
        lines: Number of trailing lines to show.
        follow: Whether to stream new lines continuously.

    Returns:
        Shell command string to execute on the remote VM.
    """
    if follow:
        return LOG_TYPE_FOLLOW_COMMANDS[log_type]

    base = LOG_TYPE_COMMANDS[log_type]

    # Pipe through tail to limit output.
    if log_type == "cloud-init":
        return f"{base} | tail -n {lines}"
    # journalctl supports -n natively.
    return f"{base} -n {lines}"


def _stream_ssh_output(ssh_config: SSHConfig, command: str) -> int:
    """Run an SSH command and stream stdout/stderr to the terminal in real time.

    Used for --follow mode where output never terminates on its own.

    Returns:
        Process exit code (130 on KeyboardInterrupt).
    """
    ssh_cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=10",
        "-i",
        str(ssh_config.key_path),
        "-p",
        str(ssh_config.port),
        f"{ssh_config.user}@{ssh_config.host}",
        command,
    ]

    process = subprocess.Popen(
        ssh_cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    try:
        process.wait(timeout=3600)
        return process.returncode
    except subprocess.TimeoutExpired:
        logger.warning("SSH process timed out after 3600 seconds, terminating")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 124
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        click.echo()  # Newline after ^C
        return 130


@click.command(name="logs")
@click.argument("vm_identifier", type=str)
@click.option(
    "--lines",
    "-n",
    default=50,
    show_default=True,
    help="Number of log lines to show.",
    type=int,
)
@click.option(
    "--follow",
    "-f",
    is_flag=True,
    default=False,
    help="Follow log output (like tail -f). Press Ctrl+C to stop.",
)
@click.option(
    "--type",
    "-t",
    "log_type",
    default="cloud-init",
    show_default=True,
    type=click.Choice(VALID_LOG_TYPES, case_sensitive=False),
    help="Type of log to view.",
)
@click.option("--resource-group", "--rg", help="Resource group", type=str)
@click.option("--config", help="Config file path", type=click.Path())
def logs(
    vm_identifier: str,
    lines: int,
    follow: bool,
    log_type: str,
    resource_group: str | None,
    config: str | None,
) -> None:
    """View VM logs (cloud-init, syslog, auth).

    Connects to the VM via SSH and retrieves the requested log output.

    VM_IDENTIFIER can be:
    - Session name (resolved to VM)
    - VM name (requires --resource-group or default config)
    - IP address (direct connection)

    \b
    Examples:
        azlin logs my-vm                          # Last 50 lines of cloud-init log
        azlin logs my-vm -n 200                   # Last 200 lines
        azlin logs my-vm --type syslog            # System journal
        azlin logs my-vm --type auth              # SSH / auth journal
        azlin logs my-vm --follow                 # Stream cloud-init log
        azlin logs my-vm -t syslog -f             # Stream system journal
    """
    try:
        ssh_config = _get_ssh_config_for_vm(vm_identifier, resource_group, config)

        remote_command = _build_log_command(log_type, lines, follow)

        if follow:
            click.echo(f"Streaming {log_type} logs from {vm_identifier} (Ctrl+C to stop)...")
            exit_code = _stream_ssh_output(ssh_config, remote_command)
            sys.exit(exit_code)
        else:
            click.echo(f"Fetching {log_type} logs from {vm_identifier} (last {lines} lines)...\n")
            result = RemoteExecutor.execute_command(
                ssh_config,
                remote_command,
                timeout=30,
            )

            if result.stdout:
                click.echo(result.stdout)
            if result.stderr:
                click.echo(result.stderr, err=True)

            if not result.success:
                sys.exit(result.exit_code)

    except RemoteExecError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except SSHKeyError as e:
        click.echo(f"SSH key error: {e}", err=True)
        sys.exit(1)
    except VMManagerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ConfigError as e:
        click.echo(f"Config error: {e}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nCancelled.")
        sys.exit(130)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


__all__ = ["logs"]
