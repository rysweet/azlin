"""Auto mode execution for azdoit."""

import subprocess
import sys
from typing import NoReturn


def check_amplihack_available() -> bool:
    """Check if amplihack is installed and accessible.

    Returns:
        True if amplihack is available, False otherwise
    """
    try:
        result = subprocess.run(
            ["amplihack", "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def execute_auto_mode(prompt: str, max_turns: int = 15) -> NoReturn:
    """Execute amplihack auto mode with the given prompt.

    This function does not return normally - it either:
    - Exits with auto mode's exit code on completion
    - Exits with code 130 on KeyboardInterrupt
    - Exits with code 1 on FileNotFoundError

    Args:
        prompt: The formatted prompt to pass to auto mode
        max_turns: Maximum number of auto mode turns (default: 15)

    Raises:
        SystemExit: Always exits with appropriate code
    """
    cmd = [
        "amplihack",
        "claude",
        "--auto",
        "--max-turns",
        str(max_turns),
        "--",
        "-p",
        prompt
    ]

    try:
        # Don't capture output - let it stream to terminal
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...", file=sys.stderr)
        sys.exit(130)  # Standard exit code for SIGINT

    except FileNotFoundError:
        print(
            "Error: amplihack command not found.\n"
            "Please ensure amplihack is installed and in your PATH.\n"
            "Installation: pip install amplihack",
            file=sys.stderr
        )
        sys.exit(1)
