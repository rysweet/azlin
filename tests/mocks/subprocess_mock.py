"""
Mock subprocess operations for testing.

This module provides utilities for mocking subprocess calls
to simulate command execution without actually running commands.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

from ..fixtures.ssh_configs import (
    SSH_CONNECTION_REFUSED_OUTPUT,
    SSH_CONNECTION_SUCCESS_OUTPUT,
    SSH_CONNECTION_TIMEOUT_OUTPUT,
    SSH_KEYGEN_OUTPUT,
)


class SubprocessCallCapture:
    """Capture and verify subprocess calls.

    This class records all subprocess calls made during tests
    and provides methods to verify they were called correctly.
    """

    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self._responses: dict[str, Mock] = {}
        self._default_response = Mock(returncode=0, stdout="", stderr="")

    def capture(self, cmd: list[str], **kwargs) -> Mock:
        """Capture a subprocess call.

        Args:
            cmd: Command and arguments
            **kwargs: Additional subprocess.run arguments

        Returns:
            Mock result object
        """
        self.calls.append({"cmd": cmd, "kwargs": kwargs})

        # Return configured response if available
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        for pattern, response in self._responses.items():
            if pattern in cmd_str:
                return response

        return self._default_response

    def configure_response(
        self, command_pattern: str, returncode: int = 0, stdout: str = "", stderr: str = ""
    ):
        """Configure response for commands matching pattern.

        Args:
            command_pattern: String to match in command
            returncode: Return code to use
            stdout: Stdout to return
            stderr: Stderr to return
        """
        self._responses[command_pattern] = Mock(returncode=returncode, stdout=stdout, stderr=stderr)

    def assert_called_with_command(self, command: str):
        """Assert that a command was called.

        Args:
            command: Command string to check for

        Raises:
            AssertionError: If command not found
        """
        for call in self.calls:
            cmd_str = " ".join(call["cmd"]) if isinstance(call["cmd"], list) else call["cmd"]
            if command in cmd_str:
                return
        raise AssertionError(
            f"Expected command '{command}' not found in {[' '.join(c['cmd']) for c in self.calls]}"
        )

    def assert_not_called_with_command(self, command: str):
        """Assert that a command was NOT called.

        Args:
            command: Command string to check for

        Raises:
            AssertionError: If command found
        """
        for call in self.calls:
            cmd_str = " ".join(call["cmd"]) if isinstance(call["cmd"], list) else call["cmd"]
            if command in cmd_str:
                raise AssertionError(f"Unexpected command '{command}' was called")

    def assert_call_count(self, expected: int):
        """Assert total number of subprocess calls.

        Args:
            expected: Expected number of calls

        Raises:
            AssertionError: If call count doesn't match
        """
        actual = len(self.calls)
        if actual != expected:
            raise AssertionError(f"Expected {expected} subprocess calls, got {actual}")

    def get_calls_matching(self, pattern: str) -> list[dict[str, Any]]:
        """Get all calls matching a pattern.

        Args:
            pattern: String to match in command

        Returns:
            List of matching calls
        """
        matching = []
        for call in self.calls:
            cmd_str = " ".join(call["cmd"]) if isinstance(call["cmd"], list) else call["cmd"]
            if pattern in cmd_str:
                matching.append(call)
        return matching

    def reset(self):
        """Clear all captured calls."""
        self.calls.clear()


class CommandRouter:
    """Route subprocess calls to different handlers based on command.

    This class allows configuring different responses for different
    commands, simulating complex subprocess interactions.
    """

    def __init__(self):
        self._routes: dict[str, Callable] = {}
        self._default_handler = self._default_success

    def register(self, command_pattern: str, handler: Callable):
        """Register a handler for a command pattern.

        Args:
            command_pattern: String to match in command
            handler: Callable that returns Mock result
        """
        self._routes[command_pattern] = handler

    def route(self, cmd: list[str], **kwargs) -> Mock:
        """Route a command to appropriate handler.

        Args:
            cmd: Command and arguments
            **kwargs: Additional subprocess.run arguments

        Returns:
            Mock result object
        """
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd

        # Check registered routes
        for pattern, handler in self._routes.items():
            if pattern in cmd_str:
                return handler(cmd, **kwargs)

        # Use default handler
        return self._default_handler(cmd, **kwargs)

    def set_default_handler(self, handler: Callable):
        """Set default handler for unmatched commands."""
        self._default_handler = handler

    @staticmethod
    def _default_success(cmd: list[str], **kwargs) -> Mock:
        """Default handler that returns success."""
        return Mock(returncode=0, stdout="", stderr="")


# ============================================================================
# PRE-CONFIGURED COMMAND HANDLERS
# ============================================================================


def ssh_keygen_handler(cmd: list[str], **kwargs) -> Mock:
    """Handle ssh-keygen commands.

    Args:
        cmd: Command and arguments
        **kwargs: Additional arguments

    Returns:
        Mock result simulating ssh-keygen output
    """
    if "ssh-keygen" not in " ".join(cmd):
        return Mock(returncode=1, stderr="command not found")

    # Extract key path from -f argument
    for i, arg in enumerate(cmd):
        if arg == "-f" and i + 1 < len(cmd):
            cmd[i + 1]
            break

    return Mock(returncode=0, stdout=SSH_KEYGEN_OUTPUT, stderr="")


def ssh_connection_handler(cmd: list[str], success: bool = True, timeout: bool = False) -> Mock:
    """Handle SSH connection commands.

    Args:
        cmd: Command and arguments
        success: Whether connection should succeed
        timeout: Whether connection should timeout

    Returns:
        Mock result simulating SSH connection
    """
    if "ssh" not in " ".join(cmd):
        return Mock(returncode=1, stderr="command not found")

    if timeout:
        return Mock(returncode=255, stdout="", stderr=SSH_CONNECTION_TIMEOUT_OUTPUT)

    if success:
        return Mock(returncode=0, stdout=SSH_CONNECTION_SUCCESS_OUTPUT, stderr="")

    return Mock(returncode=255, stdout="", stderr=SSH_CONNECTION_REFUSED_OUTPUT)


def gh_cli_handler(cmd: list[str], authenticated: bool = True) -> Mock:
    """Handle gh CLI commands.

    Args:
        cmd: Command and arguments
        authenticated: Whether user is authenticated

    Returns:
        Mock result simulating gh CLI
    """
    cmd_str = " ".join(cmd)

    if "gh" not in cmd_str:
        return Mock(returncode=1, stderr="command not found")

    if "auth status" in cmd_str:
        if authenticated:
            return Mock(returncode=0, stdout="Logged in to github.com as testuser", stderr="")
        return Mock(returncode=1, stdout="", stderr="You are not logged into any GitHub hosts")

    if "auth login" in cmd_str:
        return Mock(returncode=0, stdout="Logged in as testuser", stderr="")

    if "repo clone" in cmd_str:
        if authenticated:
            return Mock(returncode=0, stdout="", stderr="")
        return Mock(returncode=1, stderr="authentication required")

    return Mock(returncode=0, stdout="", stderr="")


def apt_install_handler(cmd: list[str], **kwargs) -> Mock:
    """Handle apt install commands.

    Args:
        cmd: Command and arguments
        **kwargs: Additional arguments

    Returns:
        Mock result simulating apt install
    """
    cmd_str = " ".join(cmd)

    if "apt" not in cmd_str and "apt-get" not in cmd_str:
        return Mock(returncode=1, stderr="command not found")

    if "install" in cmd_str:
        # Extract package names
        packages = [
            arg
            for arg in cmd
            if not arg.startswith("-") and arg not in ["apt", "apt-get", "install", "sudo"]
        ]

        output = f"Installing {len(packages)} packages...\nDone."
        return Mock(returncode=0, stdout=output, stderr="")

    if "update" in cmd_str:
        return Mock(returncode=0, stdout="Updated package lists", stderr="")

    return Mock(returncode=0, stdout="", stderr="")


def tmux_handler(cmd: list[str], **kwargs) -> Mock:
    """Handle tmux commands.

    Args:
        cmd: Command and arguments
        **kwargs: Additional arguments

    Returns:
        Mock result simulating tmux
    """
    cmd_str = " ".join(cmd)

    if "tmux" not in cmd_str:
        return Mock(returncode=1, stderr="command not found")

    if "new-session" in cmd_str:
        return Mock(returncode=0, stdout="", stderr="")

    if "list-sessions" in cmd_str:
        return Mock(
            returncode=0, stdout="dev: 1 windows (created Thu Oct  9 10:00:00 2024)", stderr=""
        )

    if "attach" in cmd_str:
        return Mock(returncode=0, stdout="", stderr="")

    return Mock(returncode=0, stdout="", stderr="")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_configured_router() -> CommandRouter:
    """Create a CommandRouter with common commands pre-configured.

    Returns:
        CommandRouter with handlers for common commands
    """
    router = CommandRouter()

    router.register("ssh-keygen", ssh_keygen_handler)
    router.register("ssh ", lambda cmd, **kw: ssh_connection_handler(cmd, success=True))
    router.register("gh ", lambda cmd, **kw: gh_cli_handler(cmd, authenticated=True))
    router.register("apt", apt_install_handler)
    router.register("tmux", tmux_handler)

    return router
