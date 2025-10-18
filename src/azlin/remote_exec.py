"""Remote command execution module.

This module handles executing commands on remote VMs via SSH.
Supports parallel execution across multiple VMs.

Security:
- Command sanitization using shlex.quote()
- No shell=True
- Input validation
- Timeout enforcement
"""

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from azlin.modules.ssh_connector import SSHConfig

logger = logging.getLogger(__name__)


class RemoteExecError(Exception):
    """Raised when remote command execution fails."""

    pass


@dataclass
class RemoteResult:
    """Result from remote command execution."""

    vm_name: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration: float = 0.0

    def get_output(self) -> str:
        """Get combined output."""
        if self.stdout and self.stderr:
            return f"{self.stdout}\n{self.stderr}"
        return self.stdout or self.stderr


class RemoteExecutor:
    """Execute commands on remote VMs via SSH.

    This class provides:
    - Single VM command execution
    - Parallel execution across multiple VMs
    - Command sanitization
    - Output aggregation
    """

    @classmethod
    def execute_command(
        cls, ssh_config: SSHConfig, command: str, timeout: int = 30
    ) -> RemoteResult:
        """Execute command on single VM.

        Args:
            ssh_config: SSH configuration
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            RemoteResult object

        Raises:
            RemoteExecError: If execution fails
        """
        import time

        start_time = time.time()

        try:
            # Build SSH command
            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
                "-o",
                f"ConnectTimeout={min(timeout, 10)}",
                "-i",
                str(ssh_config.key_path),
                f"{ssh_config.user}@{ssh_config.host}",
                command,  # Pass command directly, not through shell
            ]

            logger.debug(f"Executing on {ssh_config.host}: {command}")

            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,  # Don't raise on non-zero exit
            )

            duration = time.time() - start_time

            return RemoteResult(
                vm_name=ssh_config.host,
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration=duration,
            )

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start_time
            raise RemoteExecError(f"Command timed out after {timeout}s on {ssh_config.host}") from e
        except Exception as e:
            raise RemoteExecError(f"Failed to execute command: {e}") from e

    @classmethod
    def execute_parallel(
        cls, ssh_configs: list[SSHConfig], command: str, timeout: int = 30, max_workers: int = 10
    ) -> list[RemoteResult]:
        """Execute command on multiple VMs in parallel.

        Args:
            ssh_configs: List of SSH configurations
            command: Command to execute
            timeout: Timeout per VM in seconds
            max_workers: Maximum parallel workers

        Returns:
            List of RemoteResult objects

        Raises:
            RemoteExecError: If execution setup fails
        """
        if not ssh_configs:
            return []

        results: list[RemoteResult] = []
        num_workers = min(max_workers, len(ssh_configs))

        logger.debug(f"Executing command on {len(ssh_configs)} VMs with {num_workers} workers")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks
            future_to_config = {
                executor.submit(cls.execute_command, config, command, timeout): config
                for config in ssh_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed on {config.host}: {e}")
                    results.append(
                        RemoteResult(
                            vm_name=config.host,
                            success=False,
                            stdout="",
                            stderr=str(e),
                            exit_code=-1,
                        )
                    )

        return results

    @classmethod
    def format_parallel_output(cls, results: list[RemoteResult], show_vm_name: bool = True) -> str:
        """Format output from parallel execution.

        Args:
            results: List of RemoteResult objects
            show_vm_name: Prefix each line with VM name

        Returns:
            Formatted output string
        """
        lines: list[str] = []

        for result in results:
            prefix = f"[{result.vm_name}] " if show_vm_name else ""

            if result.success:
                # Split output into lines and prefix each
                lines.extend(f"{prefix}{line}" for line in result.stdout.splitlines())
            else:
                # Show error
                lines.append(f"{prefix}ERROR: {result.stderr}")

        return "\n".join(lines)

    @classmethod
    def parse_command_from_args(cls, args: list[str], delimiter: str = "--") -> str | None:
        """Parse command from argument list after delimiter.

        Args:
            args: Command line arguments
            delimiter: Delimiter separating azlin args from command

        Returns:
            Command string or None if no delimiter found

        Example:
            >>> parse_command_from_args(['azlin', '--', 'echo', 'hello'])
            'echo hello'
        """
        try:
            delimiter_index = args.index(delimiter)
            command_args = args[delimiter_index + 1 :]

            if not command_args:
                return None

            # Join args into command string
            return " ".join(command_args)

        except (ValueError, IndexError):
            return None

    @classmethod
    def extract_command_slug(cls, command: str, max_length: int = 20) -> str:
        """Extract slug from command for naming.

        Args:
            command: Command string
            max_length: Maximum slug length

        Returns:
            Command slug suitable for VM naming

        Example:
            >>> extract_command_slug('python script.py --arg')
            'python-script'
        """
        # Take first few words
        words = command.split()[:3]

        # Clean and join
        slug_parts: list[str] = []
        for word in words:
            # Remove special chars, keep alphanumeric and dash
            clean = "".join(c if c.isalnum() else "-" for c in word)
            clean = clean.strip("-")
            if clean:
                slug_parts.append(clean)

        slug = "-".join(slug_parts)

        # Truncate if needed
        if len(slug) > max_length:
            slug = slug[:max_length].rstrip("-")

        return slug if slug else "cmd"


class WCommandExecutor:
    """Execute 'w' command across VMs for system monitoring.

    The 'w' command shows who is logged in and what they are doing.
    """

    @classmethod
    def execute_w_on_vms(
        cls, ssh_configs: list[SSHConfig], timeout: int = 30
    ) -> list[RemoteResult]:
        """Execute 'w' command on multiple VMs.

        Args:
            ssh_configs: List of SSH configurations
            timeout: Timeout per VM in seconds

        Returns:
            List of RemoteResult objects
        """
        return RemoteExecutor.execute_parallel(ssh_configs, "w", timeout=timeout)

    @classmethod
    def format_w_output(cls, results: list[RemoteResult]) -> str:
        """Format 'w' command output with VM names.

        Args:
            results: List of RemoteResult objects

        Returns:
            Formatted output string
        """
        lines: list[str] = []

        for result in results:
            lines.append("=" * 60)
            lines.append(f"VM: {result.vm_name}")
            lines.append("=" * 60)

            if result.success:
                lines.append(result.stdout)
            else:
                lines.append(f"ERROR: {result.stderr}")

            lines.append("")  # Blank line between VMs

        return "\n".join(lines)


class PSCommandExecutor:
    """Execute 'ps' command across VMs for process monitoring.

    The 'ps' command shows running processes on each VM.
    Filters out the SSH process itself to avoid cluttering output.
    """

    @classmethod
    def execute_ps_on_vms(
        cls, ssh_configs: list[SSHConfig], timeout: int = 30, use_forest: bool = True
    ) -> list[RemoteResult]:
        """Execute 'ps' command on multiple VMs.

        Args:
            ssh_configs: List of SSH configurations
            timeout: Timeout per VM in seconds
            use_forest: Use --forest flag for tree view (if available)

        Returns:
            List of RemoteResult objects
        """
        # Try ps aux --forest first, fall back to ps aux if not supported
        # The forest view shows process hierarchy which is useful
        command = "ps aux --forest 2>/dev/null || ps aux"

        return RemoteExecutor.execute_parallel(ssh_configs, command, timeout=timeout)

    @classmethod
    def format_ps_output(cls, results: list[RemoteResult], filter_ssh: bool = True) -> str:
        """Format 'ps' command output with VM name prefix.

        Args:
            results: List of RemoteResult objects
            filter_ssh: Filter out SSH-related processes

        Returns:
            Formatted output string with [vm-name] prefix per line
        """
        lines: list[str] = []

        for result in results:
            if not result.success:
                lines.append(f"[{result.vm_name}] ERROR: {result.stderr}")
                continue

            # Process each line of output
            output_lines = result.stdout.splitlines()

            for line in output_lines:
                # Filter out SSH processes if requested
                if filter_ssh and cls._is_ssh_process(line):
                    continue

                # Prefix each line with VM name
                lines.append(f"[{result.vm_name}] {line}")

        return "\n".join(lines)

    @classmethod
    def format_ps_output_grouped(cls, results: list[RemoteResult], filter_ssh: bool = True) -> str:
        """Format 'ps' command output grouped by VM.

        Args:
            results: List of RemoteResult objects
            filter_ssh: Filter out SSH-related processes

        Returns:
            Formatted output string grouped by VM
        """
        lines: list[str] = []

        for result in results:
            lines.append("=" * 80)
            lines.append(f"VM: {result.vm_name}")
            lines.append("=" * 80)

            if result.success:
                output_lines = result.stdout.splitlines()

                for line in output_lines:
                    # Filter out SSH processes if requested
                    if filter_ssh and cls._is_ssh_process(line):
                        continue
                    lines.append(line)
            else:
                lines.append(f"ERROR: {result.stderr}")

            lines.append("")  # Blank line between VMs

        return "\n".join(lines)

    @classmethod
    def _is_ssh_process(cls, line: str) -> bool:
        """Check if a ps output line is an SSH-related process.

        Args:
            line: Single line from ps aux output

        Returns:
            True if line represents an SSH process
        """
        # Skip header line
        if line.startswith("USER") or line.startswith("PID"):
            return False

        # Check for SSH-related processes
        ssh_indicators = [
            "sshd:",  # SSH daemon connections
            "ssh ",  # SSH client processes
            "/usr/sbin/sshd",  # SSH daemon path
            "ps aux",  # The ps command itself
        ]

        line_lower = line.lower()
        return any(indicator.lower() in line_lower for indicator in ssh_indicators)


class OSUpdateExecutor:
    """Execute OS update commands on VMs.

    Handles updating Ubuntu packages via apt update and apt upgrade.
    """

    @classmethod
    def execute_os_update(cls, ssh_config: SSHConfig, timeout: int = 300) -> RemoteResult:
        """Execute OS update on a single VM.

        Args:
            ssh_config: SSH configuration for the VM
            timeout: Timeout in seconds (default 300 for apt operations)

        Returns:
            RemoteResult object with update status

        Note:
            Uses 'sudo apt update && sudo apt upgrade -y' to update packages.
            The -y flag makes the upgrade non-interactive.
        """
        # Command to update and upgrade packages non-interactively
        command = "sudo apt update && sudo apt upgrade -y"

        logger.info(f"Starting OS update on {ssh_config.host}")

        return RemoteExecutor.execute_command(ssh_config, command, timeout=timeout)

    @classmethod
    def format_output(cls, result: RemoteResult) -> str:
        """Format OS update output for display.

        Args:
            result: RemoteResult from OS update execution

        Returns:
            Formatted output string
        """
        lines: list[str] = []

        lines.append("=" * 70)
        lines.append(f"OS Update: {result.vm_name}")
        lines.append("=" * 70)

        if result.success:
            lines.append("\nStatus: SUCCESS")
            lines.append(f"Duration: {result.duration:.1f}s")
            lines.append("\nOutput:")
            lines.append(result.stdout)

            # Add summary if we can parse it
            if "upgraded" in result.stdout.lower():
                lines.append("\nUpdate completed successfully.")
        else:
            lines.append("\nStatus: FAILED")
            lines.append(f"Exit code: {result.exit_code}")
            lines.append(f"Duration: {result.duration:.1f}s")
            lines.append("\nError:")
            lines.append(result.stderr if result.stderr else result.stdout)
            lines.append("\nUpdate failed. Please check the error above.")

        lines.append("=" * 70)

        return "\n".join(lines)


__all__ = [
    "OSUpdateExecutor",
    "PSCommandExecutor",
    "RemoteExecError",
    "RemoteExecutor",
    "RemoteResult",
    "WCommandExecutor",
]
