"""Safe subprocess execution with pipe deadlock prevention.

Philosophy:
- Single responsibility: Execute subprocess safely
- Standard library only (no external dependencies)
- Self-contained and regeneratable
- Zero-BS: No stubs or placeholders

Public API (the "studs"):
    SubprocessResult: Result dataclass
    safe_run: Main execution function
"""

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SubprocessResult:
    """Result of subprocess execution."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def safe_run(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int | None = 30,
    env: dict | None = None,
) -> SubprocessResult:
    """
    Execute subprocess with pipe deadlock prevention.

    Uses background threads to drain stdout/stderr pipes,
    preventing buffer overflow that causes deadlocks.

    Args:
        cmd: Command and arguments
        cwd: Working directory
        timeout: Timeout in seconds (None = no timeout)
        env: Environment variables

    Returns:
        SubprocessResult with output and exit code

    Example:
        >>> result = safe_run(["echo", "hello"])
        >>> assert result.returncode == 0
        >>> assert "hello" in result.stdout.lower()
    """
    # Handle command not found
    try:
        # Start process with pipes
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
    except FileNotFoundError:
        # Command not found - return standard exit code 127
        return SubprocessResult(
            returncode=127,
            stdout="",
            stderr=f"Command not found: {cmd[0] if cmd else 'unknown'}",
            timed_out=False,
        )
    except (PermissionError, OSError) as e:
        # Other OS errors
        return SubprocessResult(
            returncode=1,
            stdout="",
            stderr=f"Error executing command: {e!s}",
            timed_out=False,
        )
    except Exception as e:
        # Unexpected errors
        return SubprocessResult(
            returncode=1,
            stdout="",
            stderr=f"Unexpected error: {e!s}",
            timed_out=False,
        )

    # Storage for captured output
    stdout_data = []
    stderr_data = []

    # Define pipe drain functions
    def drain_pipe(pipe, storage):
        """Read from pipe until EOF, store in list."""
        try:
            data = pipe.read()
            if data:
                storage.append(data)
        except OSError:
            # Pipe closed - normal during process termination
            pass

    # Start background threads to drain pipes
    stdout_thread = threading.Thread(target=drain_pipe, args=(process.stdout, stdout_data))
    stderr_thread = threading.Thread(target=drain_pipe, args=(process.stderr, stderr_data))

    stdout_thread.daemon = True
    stderr_thread.daemon = True

    stdout_thread.start()
    stderr_thread.start()

    # Wait for process to complete with timeout
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        # Kill the process
        try:
            process.terminate()
            # Give it a moment to terminate gracefully
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        except Exception:
            pass

    # Wait for drain threads to complete
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)

    # Get final exit code
    returncode = process.returncode if process.returncode is not None else -1

    # Decode output
    stdout = stdout_data[0].decode("utf-8", errors="replace") if stdout_data else ""
    stderr = stderr_data[0].decode("utf-8", errors="replace") if stderr_data else ""

    return SubprocessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
    )


__all__ = ["SubprocessResult", "safe_run"]
