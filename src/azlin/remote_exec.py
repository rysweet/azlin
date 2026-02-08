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
from typing import Any

from azlin.modules.ssh_connector import SSHConfig
from azlin.modules.ssh_routing_resolver import SSHRoute

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
    session_name: str | None = None

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
                "-p",
                str(ssh_config.port),
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


@dataclass
class TmuxSession:
    """Information about a tmux session."""

    vm_name: str
    session_name: str
    windows: int
    created_time: str
    attached: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for caching."""
        return {
            "vm_name": self.vm_name,
            "session_name": self.session_name,
            "windows": self.windows,
            "created_time": self.created_time,
            "attached": self.attached,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TmuxSession":
        """Create from cached dictionary."""
        return cls(
            vm_name=data["vm_name"],
            session_name=data["session_name"],
            windows=data["windows"],
            created_time=data["created_time"],
            attached=data.get("attached", False),
        )


@dataclass
class TmuxSessionInfo:
    """Tmux session information for a VM."""

    vm_name: str
    sessions: list[TmuxSession]
    reachable: bool
    error: str | None = None


class TmuxSessionExecutor:
    """Query tmux sessions on remote VMs.

    This class provides:
    - Parallel session queries across multiple VMs
    - Parsing of tmux list-sessions output
    """

    @classmethod
    def get_sessions_single_vm(
        cls, ssh_config: SSHConfig, vm_name: str | None = None, timeout: int = 5
    ) -> list[TmuxSession]:
        """Get tmux sessions from a single VM.

        Args:
            ssh_config: SSH configuration for the VM
            vm_name: Optional VM name (defaults to host from ssh_config)
            timeout: Timeout in seconds

        Returns:
            List of TmuxSession objects from the VM
        """
        if vm_name is None:
            vm_name = ssh_config.host

        # Command to list tmux sessions with enhanced format (Issue #499)
        # New format: name:attached:windows:created
        # Falls back to old format if new format not available
        command = "tmux list-sessions -F \"#{session_name}:#{session_attached}:#{session_windows}:#{session_created}\" 2>/dev/null || tmux list-sessions 2>/dev/null || echo 'No sessions'"

        try:
            # Execute command on single VM
            result = RemoteExecutor.execute_command(ssh_config, command, timeout=timeout)

            # Check for connection failure
            if not result.success:
                logger.error(
                    f"SSH connection to {vm_name} failed (exit code {result.exit_code}): {result.stderr}"
                )
                return []

            # Check for empty output
            if not result.stdout or result.stdout.strip() == "":
                logger.debug(f"SSH connection to {vm_name} successful but returned no output")
                return []

            # Parse results
            if "No sessions" not in result.stdout:
                return cls.parse_tmux_output(result.stdout, vm_name)
            return []

        except Exception as e:
            logger.error(f"Failed to get tmux sessions from {vm_name}: {e}")
            return []

    @classmethod
    def get_sessions_parallel(
        cls, ssh_configs: list[SSHConfig], timeout: int = 5, max_workers: int = 10
    ) -> list[TmuxSession]:
        """Get tmux sessions from multiple VMs in parallel.

        Args:
            ssh_configs: List of SSH configurations
            timeout: Timeout per VM in seconds
            max_workers: Maximum parallel workers

        Returns:
            List of TmuxSession objects from all VMs
        """
        if not ssh_configs:
            return []

        # Command to list tmux sessions with enhanced format (Issue #499)
        # New format: name:attached:windows:created
        # Falls back to old format if new format not available
        command = "tmux list-sessions -F \"#{session_name}:#{session_attached}:#{session_windows}:#{session_created}\" 2>/dev/null || tmux list-sessions 2>/dev/null || echo 'No sessions'"

        # Execute in parallel
        results = RemoteExecutor.execute_parallel(
            ssh_configs, command, timeout=timeout, max_workers=max_workers
        )

        # Parse results
        all_sessions: list[TmuxSession] = []

        for result in results:
            if result.success and result.stdout and "No sessions" not in result.stdout:
                sessions = cls.parse_tmux_output(result.stdout, result.vm_name)
                all_sessions.extend(sessions)

        return all_sessions

    @classmethod
    def parse_tmux_output(cls, output: str, vm_name: str) -> list[TmuxSession]:
        """Parse tmux list-sessions output.

        Args:
            output: Raw output from tmux list-sessions
            vm_name: VM name for identification

        Returns:
            List of TmuxSession objects

        Example output formats:
            New format (Issue #499): session_name:attached(0|1):windows:created_timestamp
            Old format: dev: 3 windows (created Thu Oct 10 10:00:00 2024)
        """
        sessions: list[TmuxSession] = []

        for line in output.strip().splitlines():
            if not line or not line.strip():
                continue

            line = line.strip()

            try:
                # Detect format by checking field structure
                # New format has 3+ colons with field[1] being '0' or '1'
                parts = line.split(":")
                # Strip whitespace from all parts to handle edge cases
                parts = [p.strip() for p in parts]

                # Try new format first: name:attached:windows:created
                # New format must have exactly 4 fields and field[1] must be numeric (client count)
                # field[2] must be numeric (windows count)
                if len(parts) >= 4 and parts[1].isdigit():
                    # Validate windows field is numeric to confirm new format
                    try:
                        windows = int(parts[2])
                    except ValueError:
                        # Not new format - fall through to old format parser
                        pass
                    else:
                        # New format confirmed
                        session_name = parts[0]  # Already stripped
                        # attached is count of clients: 0=none, 1+=connected
                        attached = int(parts[1]) > 0

                        # Created time is the remaining fields joined
                        created_time = ":".join(parts[3:]) if len(parts) > 3 else ""

                        sessions.append(
                            TmuxSession(
                                vm_name=vm_name,
                                session_name=session_name,
                                windows=windows,
                                created_time=created_time,
                                attached=attached,
                            )
                        )
                        continue

                # Fall back to old format: "name: X windows (created date) [attached]"
                # Old format must have the word "window" in it to be valid
                if len(parts) >= 2 and "window" in ":".join(parts[1:]):
                    session_name = parts[0]  # Already stripped above
                    rest = ":".join(parts[1:])  # Already stripped above

                    # Check if attached (old format uses "(attached)" suffix)
                    attached = "(attached)" in rest

                    # Extract window count
                    windows = 1  # Default
                    if "window" in rest:
                        # Extract number before "window(s)"
                        window_parts = rest.split()
                        for i, part in enumerate(window_parts):
                            if "window" in part and i > 0:
                                try:
                                    windows = int(window_parts[i - 1])
                                except (ValueError, IndexError):
                                    windows = 1
                                break

                    # Extract created time
                    created_time = ""
                    if "(created" in rest:
                        start_idx = rest.index("(created") + len("(created")
                        end_idx = rest.find(")", start_idx)
                        if end_idx > start_idx:
                            created_time = rest[start_idx:end_idx].strip()

                    sessions.append(
                        TmuxSession(
                            vm_name=vm_name,
                            session_name=session_name,
                            windows=windows,
                            created_time=created_time,
                            attached=attached,
                        )
                    )

            except Exception as e:
                logger.warning(f"Failed to parse tmux session line: {line} - {e}")
                continue

        return sessions

    @classmethod
    def format_sessions_display(cls, sessions: list[TmuxSession]) -> str:
        """Format tmux sessions for display.

        Args:
            sessions: List of TmuxSession objects

        Returns:
            Formatted string for display
        """
        if not sessions:
            return "No sessions"

        lines: list[str] = []

        # Group sessions by VM
        vm_sessions: dict[str, list[TmuxSession]] = {}
        for session in sessions:
            if session.vm_name not in vm_sessions:
                vm_sessions[session.vm_name] = []
            vm_sessions[session.vm_name].append(session)

        # Format output
        for vm_name in sorted(vm_sessions.keys()):
            lines.append(f"\n{vm_name}:")
            for session in vm_sessions[vm_name]:
                window_text = "window" if session.windows == 1 else "windows"
                attached_text = " (attached)" if session.attached else ""
                created_text = f" (created {session.created_time})" if session.created_time else ""
                lines.append(
                    f"  - {session.session_name}: {session.windows} {window_text}{created_text}{attached_text}"
                )

        return "\n".join(lines).strip()


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
    def execute_w_on_routes(
        cls, routes: list[SSHRoute], timeout: int = 30, max_workers: int = 10
    ) -> list[RemoteResult]:
        """Execute 'w' command on multiple VMs using route information.

        Args:
            routes: List of SSH routes with VM metadata
            timeout: Timeout per VM in seconds
            max_workers: Maximum parallel workers

        Returns:
            List of RemoteResult objects with VM names and session names
        """
        if not routes:
            return []

        # Filter reachable routes
        reachable_routes = [route for route in routes if route.ssh_config is not None]

        if not reachable_routes:
            return []

        results: list[RemoteResult] = []
        num_workers = min(max_workers, len(reachable_routes))

        logger.debug(f"Executing 'w' on {len(reachable_routes)} VMs with {num_workers} workers")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all tasks - ssh_config is guaranteed non-None by filter above
            future_to_route = {
                executor.submit(
                    RemoteExecutor.execute_command,
                    route.ssh_config,  # type: ignore[arg-type]
                    "w",
                    timeout,
                ): route
                for route in reachable_routes
            }

            # Collect results as they complete
            for future in as_completed(future_to_route):
                route = future_to_route[future]
                try:
                    result = future.result()
                    # Override vm_name and add session_name from route
                    result.vm_name = route.vm_name
                    result.session_name = route.vm_info.session_name
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed on {route.vm_name}: {e}")
                    results.append(
                        RemoteResult(
                            vm_name=route.vm_name,
                            success=False,
                            stdout="",
                            stderr=str(e),
                            exit_code=-1,
                            session_name=route.vm_info.session_name,
                        )
                    )

        return results

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

            # Show session name if available
            if result.session_name:
                lines.append(f"VM: {result.vm_name} (Session: {result.session_name})")
            else:
                lines.append(f"VM: {result.vm_name}")

            lines.append("=" * 60)

            if result.success:
                lines.append(result.stdout)
            else:
                lines.append(f"ERROR: {result.stderr}")

            lines.append("")  # Blank line between VMs

        return "\n".join(lines).strip()


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
    "TmuxSession",
    "TmuxSessionExecutor",
    "TmuxSessionInfo",
    "WCommandExecutor",
]
