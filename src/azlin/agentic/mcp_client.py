"""MCP (Model Context Protocol) JSON-RPC client.

Implements a basic MCP client for communicating with MCP servers via stdio transport.
Supports tool discovery, invocation, and resource management.
"""

import json
import subprocess
import time
from typing import Any


class MCPError(Exception):
    """Base exception for MCP client errors."""

    pass


class MCPConnectionError(MCPError):
    """MCP server connection error."""

    pass


class MCPTimeoutError(MCPError):
    """MCP request timeout error."""

    pass


class MCPToolNotFoundError(MCPError):
    """MCP tool not found error."""

    pass


class MCPClient:
    """MCP client for JSON-RPC communication with MCP servers.

    Supports stdio transport for MCP server communication.
    Implements tool discovery and invocation.

    Example:
        >>> client = MCPClient("mcp-server-azure")
        >>> if client.connect():
        ...     tools = client.list_tools()
        ...     result = client.call_tool("create_vm", {"name": "test-vm"})
        ...     client.disconnect()
    """

    def __init__(
        self,
        server_command: str | list[str],
        timeout: int = 30,
    ):
        """Initialize MCP client.

        Args:
            server_command: Command to start MCP server (string or list of args)
            timeout: Request timeout in seconds (default: 30)
        """
        self.server_command = (
            server_command if isinstance(server_command, list) else [server_command]
        )
        self.timeout = timeout
        self.process: subprocess.Popen | None = None
        self.request_id = 0
        self._tool_cache: dict[str, dict[str, Any]] | None = None

    def connect(self) -> bool:
        """Connect to MCP server via stdio.

        Returns:
            True if connection successful

        Raises:
            MCPConnectionError: If connection fails
        """
        try:
            # Start MCP server process
            self.process = subprocess.Popen(
                self.server_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Wait a moment for server to initialize
            time.sleep(0.5)

            # Check if process started successfully
            if self.process.poll() is not None:
                # Process already terminated
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise MCPConnectionError(
                    f"MCP server process terminated immediately: {stderr}"
                )

            # Send initialize request
            response = self._send_request("initialize", {"protocolVersion": "0.1.0"})

            if "error" in response:
                raise MCPConnectionError(f"Initialize failed: {response['error']}")

            return True

        except FileNotFoundError as e:
            raise MCPConnectionError(f"MCP server command not found: {self.server_command[0]}") from e
        except Exception as e:
            self.disconnect()
            raise MCPConnectionError(f"Failed to connect to MCP server: {e!s}") from e

    def disconnect(self) -> None:
        """Disconnect from MCP server.

        Terminates the server process if running.
        """
        if self.process:
            try:
                # Send shutdown notification if process is still running
                if self.process.poll() is None:
                    self._send_notification("shutdown")
                    # Give server time to shutdown gracefully
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
            finally:
                self.process = None
                self._tool_cache = None

    def is_connected(self) -> bool:
        """Check if client is connected to MCP server.

        Returns:
            True if connected and server is running
        """
        return self.process is not None and self.process.poll() is None

    def list_tools(self) -> list[dict[str, Any]]:
        """List available MCP tools.

        Returns:
            List of tool descriptors with name, description, and schema

        Raises:
            MCPConnectionError: If not connected
            MCPError: If request fails

        Example:
            >>> tools = client.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool['name']}: {tool['description']}")
        """
        if not self.is_connected():
            raise MCPConnectionError("Not connected to MCP server")

        response = self._send_request("tools/list", {})

        if "error" in response:
            raise MCPError(f"Failed to list tools: {response['error']}")

        tools = response.get("result", {}).get("tools", [])

        # Cache tool schemas
        self._tool_cache = {tool["name"]: tool for tool in tools}

        return tools

    def call_tool(self, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Call an MCP tool with parameters.

        Args:
            tool_name: Name of the tool to call
            parameters: Tool parameters as dictionary

        Returns:
            Tool execution result

        Raises:
            MCPConnectionError: If not connected
            MCPToolNotFoundError: If tool not found
            MCPError: If tool execution fails

        Example:
            >>> result = client.call_tool("create_vm", {
            ...     "name": "test-vm",
            ...     "resource_group": "test-rg"
            ... })
        """
        if not self.is_connected():
            raise MCPConnectionError("Not connected to MCP server")

        # Validate tool exists (use cache if available)
        if self._tool_cache is not None and tool_name not in self._tool_cache:
            raise MCPToolNotFoundError(f"Tool '{tool_name}' not found")

        # Call tool
        response = self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": parameters,
            },
        )

        if "error" in response:
            error_msg = response["error"]
            # Check if it's a tool not found error
            if isinstance(error_msg, dict):
                error_code = error_msg.get("code")
                if error_code == -32601:  # Method not found
                    raise MCPToolNotFoundError(f"Tool '{tool_name}' not found")
            raise MCPError(f"Tool execution failed: {error_msg}")

        return response.get("result", {})

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        """Get schema for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool schema dictionary or None if not found

        Example:
            >>> schema = client.get_tool_schema("create_vm")
            >>> if schema:
            ...     print(schema["inputSchema"])
        """
        # Ensure tool cache is populated
        if self._tool_cache is None:
            self.list_tools()

        return self._tool_cache.get(tool_name) if self._tool_cache else None

    def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send JSON-RPC request to MCP server.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            JSON-RPC response

        Raises:
            MCPConnectionError: If not connected
            MCPTimeoutError: If request times out
            MCPError: If request fails
        """
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise MCPConnectionError("Not connected to MCP server")

        self.request_id += 1

        # Build JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        try:
            # Send request
            request_json = json.dumps(request)
            self.process.stdin.write(request_json + "\n")
            self.process.stdin.flush()

            # Read response with timeout
            start_time = time.time()
            response_line = None

            while time.time() - start_time < self.timeout:
                # Check if process is still running
                if self.process.poll() is not None:
                    stderr = self.process.stderr.read() if self.process.stderr else ""
                    raise MCPConnectionError(f"MCP server terminated unexpectedly: {stderr}")

                # Try to read a line (non-blocking)
                try:
                    response_line = self.process.stdout.readline()
                    if response_line:
                        break
                except Exception:
                    time.sleep(0.1)
                    continue

                time.sleep(0.1)

            if not response_line:
                raise MCPTimeoutError(f"Request timed out after {self.timeout} seconds")

            # Parse response
            response = json.loads(response_line)

            # Validate response ID matches request
            if response.get("id") != self.request_id:
                raise MCPError(
                    f"Response ID mismatch: expected {self.request_id}, got {response.get('id')}"
                )

            return response

        except json.JSONDecodeError as e:
            raise MCPError(f"Invalid JSON response from MCP server: {e!s}") from e
        except Exception as e:
            if isinstance(e, (MCPError, MCPConnectionError, MCPTimeoutError)):
                raise
            raise MCPError(f"Request failed: {e!s}") from e

    def _send_notification(self, method: str) -> None:
        """Send JSON-RPC notification (no response expected).

        Args:
            method: Notification method name
        """
        if not self.process or not self.process.stdin:
            return

        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }

        try:
            notification_json = json.dumps(notification)
            self.process.stdin.write(notification_json + "\n")
            self.process.stdin.flush()
        except Exception:  # noqa: S110
            # Ignore errors in notifications (best effort, non-critical)
            pass

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
