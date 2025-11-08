"""Tests for MCP client module.

Tests JSON-RPC protocol implementation, tool discovery, and error handling.
"""

import json
from unittest.mock import Mock, patch

import pytest
from azlin.agentic.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)


@pytest.fixture
def mock_process():
    """Mock subprocess.Popen for MCP server."""
    process = Mock()
    process.poll.return_value = None  # Process is running
    process.stdin = Mock()
    process.stdout = Mock()
    process.stderr = Mock()
    return process


@pytest.fixture
def mcp_client():
    """MCP client instance."""
    return MCPClient("mcp-server-test", timeout=5)


class TestConnection:
    """Tests for MCP server connection."""

    @patch("subprocess.Popen")
    def test_connect_success(self, mock_popen, mock_process, mcp_client):
        """Successfully connect to MCP server."""
        mock_popen.return_value = mock_process

        # Mock initialize response
        init_response = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}
        )
        mock_process.stdout.readline.return_value = init_response + "\n"

        result = mcp_client.connect()

        assert result is True
        assert mcp_client.is_connected() is True
        mock_popen.assert_called_once()

    @patch("subprocess.Popen")
    def test_connect_server_not_found(self, mock_popen, mcp_client):
        """Connection fails when server command not found."""
        mock_popen.side_effect = FileNotFoundError()

        with pytest.raises(MCPConnectionError) as exc_info:
            mcp_client.connect()

        assert "not found" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_connect_server_terminates_immediately(self, mock_popen, mock_process, mcp_client):
        """Connection fails when server terminates immediately."""
        mock_process.poll.return_value = 1  # Process already terminated
        mock_process.stderr.read.return_value = "Server startup error"
        mock_popen.return_value = mock_process

        with pytest.raises(MCPConnectionError) as exc_info:
            mcp_client.connect()

        assert "terminated immediately" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_connect_initialize_error(self, mock_popen, mock_process, mcp_client):
        """Connection fails when initialize returns error."""
        mock_popen.return_value = mock_process

        # Mock error response
        error_response = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid request"}}
        )
        mock_process.stdout.readline.return_value = error_response + "\n"

        with pytest.raises(MCPConnectionError) as exc_info:
            mcp_client.connect()

        assert "initialize failed" in str(exc_info.value).lower()

    def test_disconnect(self, mcp_client, mock_process):
        """Disconnect from MCP server."""
        mcp_client.process = mock_process

        mcp_client.disconnect()

        assert mcp_client.process is None
        assert mcp_client.is_connected() is False

    def test_is_connected_not_connected(self, mcp_client):
        """is_connected returns False when not connected."""
        assert mcp_client.is_connected() is False

    @patch("subprocess.Popen")
    def test_context_manager(self, mock_popen, mock_process):
        """MCP client works as context manager."""
        mock_popen.return_value = mock_process

        # Mock initialize response
        init_response = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}
        )
        mock_process.stdout.readline.return_value = init_response + "\n"

        client = MCPClient("mcp-server-test")

        with client as c:
            assert c.is_connected() is True

        # Should disconnect after context
        assert client.is_connected() is False


class TestToolDiscovery:
    """Tests for tool discovery."""

    @patch("subprocess.Popen")
    def test_list_tools_success(self, mock_popen, mock_process, mcp_client):
        """Successfully list available tools."""
        mock_popen.return_value = mock_process

        # Mock initialize and list_tools responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {"name": "azure_vm_create", "description": "Create Azure VM"},
                            {"name": "azure_vm_list", "description": "List Azure VMs"},
                        ]
                    },
                }
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()
        tools = mcp_client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "azure_vm_create"
        assert tools[1]["name"] == "azure_vm_list"

    @patch("subprocess.Popen")
    def test_list_tools_not_connected(self, mock_popen, mcp_client):
        """list_tools fails when not connected."""
        with pytest.raises(MCPConnectionError) as exc_info:
            mcp_client.list_tools()

        assert "not connected" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_list_tools_error(self, mock_popen, mock_process, mcp_client):
        """list_tools handles error response."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "error": {"code": -32603, "message": "Internal error"}}
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()

        with pytest.raises(MCPError) as exc_info:
            mcp_client.list_tools()

        assert "failed to list tools" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_get_tool_schema(self, mock_popen, mock_process, mcp_client):
        """Get schema for specific tool."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {
                                "name": "azure_vm_create",
                                "description": "Create VM",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                }
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()
        mcp_client.list_tools()

        schema = mcp_client.get_tool_schema("azure_vm_create")

        assert schema is not None
        assert schema["name"] == "azure_vm_create"
        assert "inputSchema" in schema

    @patch("subprocess.Popen")
    def test_get_tool_schema_not_found(self, mock_popen, mock_process, mcp_client):
        """get_tool_schema returns None for unknown tool."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()
        mcp_client.list_tools()

        schema = mcp_client.get_tool_schema("unknown_tool")

        assert schema is None


class TestToolInvocation:
    """Tests for tool invocation."""

    @patch("subprocess.Popen")
    def test_call_tool_success(self, mock_popen, mock_process, mcp_client):
        """Successfully call MCP tool."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"content": [{"text": "VM created successfully"}], "isError": False},
                }
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()
        result = mcp_client.call_tool("azure_vm_create", {"name": "test-vm"})

        assert result is not None
        assert "content" in result
        assert result["content"][0]["text"] == "VM created successfully"

    @patch("subprocess.Popen")
    def test_call_tool_not_connected(self, mock_popen, mcp_client):
        """call_tool fails when not connected."""
        with pytest.raises(MCPConnectionError) as exc_info:
            mcp_client.call_tool("azure_vm_create", {})

        assert "not connected" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_call_tool_not_found(self, mock_popen, mock_process, mcp_client):
        """call_tool raises MCPToolNotFoundError when tool not found."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": -32601, "message": "Method not found"},
                }
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()

        with pytest.raises(MCPToolNotFoundError) as exc_info:
            mcp_client.call_tool("unknown_tool", {})

        assert "not found" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_call_tool_with_cached_validation(self, mock_popen, mock_process, mcp_client):
        """call_tool validates against cached tool list."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {"tools": [{"name": "azure_vm_create", "description": "Create VM"}]},
                }
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()
        mcp_client.list_tools()  # Populate cache

        # Tool not in cache
        with pytest.raises(MCPToolNotFoundError):
            mcp_client.call_tool("unknown_tool", {})

    @patch("subprocess.Popen")
    def test_call_tool_execution_error(self, mock_popen, mock_process, mcp_client):
        """call_tool handles execution errors."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "0.1.0"}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "error": {"code": -32000, "message": "Tool execution failed"},
                }
            ),
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()

        with pytest.raises(MCPError) as exc_info:
            mcp_client.call_tool("azure_vm_create", {})

        assert "execution failed" in str(exc_info.value).lower()


class TestJsonRpcProtocol:
    """Tests for JSON-RPC protocol implementation."""

    @patch("subprocess.Popen")
    def test_request_id_increments(self, mock_popen, mock_process, mcp_client):
        """Request IDs increment with each request."""
        mock_popen.return_value = mock_process

        # Track request IDs
        request_ids = []

        def capture_request(*args, **kwargs):
            # Capture the written request
            call_args = mock_process.stdin.write.call_args
            if call_args:
                request_json = call_args[0][0]
                request = json.loads(request_json.strip())
                request_ids.append(request["id"])
            # Return response
            response_id = len(request_ids)
            return json.dumps({"jsonrpc": "2.0", "id": response_id, "result": {}}) + "\n"

        mock_process.stdout.readline.side_effect = capture_request

        mcp_client.connect()
        mcp_client._send_request("test_method", {})

        # IDs should be 1, 2
        assert request_ids == [1, 2]

    @patch("subprocess.Popen")
    def test_response_id_validation(self, mock_popen, mock_process, mcp_client):
        """Response ID must match request ID."""
        mock_popen.return_value = mock_process

        # Mock responses with mismatched IDs
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 999, "result": {}}),  # Wrong ID
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()

        with pytest.raises(MCPError) as exc_info:
            mcp_client._send_request("test_method", {})

        assert "id mismatch" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_timeout_handling(self, mock_popen, mock_process):
        """Request times out after timeout period."""
        mock_popen.return_value = mock_process

        # Mock slow response (never returns)
        mock_process.stdout.readline.return_value = None

        # Mock responses
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        mock_process.stdout.readline.side_effect = [init_response + "\n", None]

        client = MCPClient("mcp-server-test", timeout=1)  # 1 second timeout
        client.connect()

        with pytest.raises(MCPTimeoutError) as exc_info:
            client._send_request("slow_method", {})

        assert "timed out" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_invalid_json_response(self, mock_popen, mock_process, mcp_client):
        """Handle invalid JSON in response."""
        mock_popen.return_value = mock_process

        # Mock responses
        responses = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
            "invalid json{{{",  # Invalid JSON
        ]
        mock_process.stdout.readline.side_effect = [r + "\n" for r in responses]

        mcp_client.connect()

        with pytest.raises(MCPError) as exc_info:
            mcp_client._send_request("test_method", {})

        assert "invalid json" in str(exc_info.value).lower()

    @patch("subprocess.Popen")
    def test_server_terminates_during_request(self, mock_popen, mock_process, mcp_client):
        """Handle server termination during request."""
        mock_popen.return_value = mock_process

        # Mock responses
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        mock_process.stdout.readline.side_effect = [init_response + "\n", ""]

        # Make poll return non-None (terminated) on second call
        mock_process.poll.side_effect = [None, None, 1]  # Running, running, terminated
        mock_process.stderr.read.return_value = "Server crashed"

        mcp_client.connect()

        with pytest.raises(MCPConnectionError) as exc_info:
            mcp_client._send_request("test_method", {})

        assert "terminated unexpectedly" in str(exc_info.value).lower()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_disconnect_when_not_connected(self, mcp_client):
        """Disconnect when already disconnected does nothing."""
        mcp_client.disconnect()  # Should not raise

        assert mcp_client.is_connected() is False

    @patch("subprocess.Popen")
    def test_multiple_disconnects(self, mock_popen, mock_process, mcp_client):
        """Multiple disconnects are safe."""
        mock_popen.return_value = mock_process
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        mock_process.stdout.readline.return_value = init_response + "\n"

        mcp_client.connect()
        mcp_client.disconnect()
        mcp_client.disconnect()  # Should not raise

        assert mcp_client.is_connected() is False

    @patch("subprocess.Popen")
    def test_notification_doesnt_wait_for_response(self, mock_popen, mock_process, mcp_client):
        """Notifications don't wait for responses."""
        mock_popen.return_value = mock_process
        init_response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}})
        mock_process.stdout.readline.return_value = init_response + "\n"

        mcp_client.connect()

        # Should not raise even if stdin fails
        mock_process.stdin.write.side_effect = Exception("Write failed")
        mcp_client._send_notification("test")  # Should not raise

    def test_client_with_list_command(self):
        """Client can be initialized with list of command args."""
        client = MCPClient(["python", "-m", "mcp_server"])

        assert client.server_command == ["python", "-m", "mcp_server"]

    def test_client_with_string_command(self):
        """Client can be initialized with string command."""
        client = MCPClient("mcp-server-azure")

        assert client.server_command == ["mcp-server-azure"]
