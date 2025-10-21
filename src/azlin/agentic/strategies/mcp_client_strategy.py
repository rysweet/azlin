"""MCP Client execution strategy.

Executes Azure operations via Model Context Protocol (MCP) servers.
Provides a standardized interface for AI assistants to interact with Azure tools.
"""

import re
import time
from typing import Any

from azlin.agentic.mcp_client import (
    MCPClient,
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from azlin.agentic.strategies.base_strategy import ExecutionStrategy
from azlin.agentic.types import (
    ExecutionContext,
    ExecutionResult,
    FailureType,
    Strategy,
)


class MCPClientStrategy(ExecutionStrategy):
    """Execute Azure operations via MCP server.

    Uses Model Context Protocol to communicate with MCP servers that provide
    Azure operation capabilities. Automatically discovers available tools and
    translates intents to MCP tool calls.

    Example:
        >>> strategy = MCPClientStrategy("mcp-server-azure")
        >>> context = ExecutionContext(...)
        >>> result = strategy.execute(context)
    """

    def __init__(
        self,
        server_command: str | list[str] = "mcp-server-azure",
        timeout: int = 60,
    ):
        """Initialize MCP client strategy.

        Args:
            server_command: Command to start MCP server
            timeout: Operation timeout in seconds
        """
        self.server_command = server_command
        self.timeout = timeout
        self._client: MCPClient | None = None
        self._available_tools: list[str] | None = None

    def can_handle(self, context: ExecutionContext) -> bool:
        """Check if MCP server can handle this intent.

        Args:
            context: Execution context

        Returns:
            True if MCP server is available and has required tools
        """
        # Validate MCP server is available
        valid, _ = self.validate(context)
        if not valid:
            return False

        # Check if MCP server has tools for this intent
        required_tools = self._get_required_tools(context)
        if not required_tools:
            # Can't determine required tools, assume can't handle
            return False

        # Check if all required tools are available
        available = self._discover_mcp_tools()
        return all(tool in available for tool in required_tools)

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute via MCP server.

        Args:
            context: Execution context with intent and parameters

        Returns:
            ExecutionResult with success status and details
        """
        start_time = time.time()

        try:
            # Validate prerequisites
            valid, error_msg = self.validate(context)
            if not valid:
                return ExecutionResult(
                    success=False,
                    strategy=Strategy.MCP_CLIENT,
                    error=error_msg,
                    failure_type=FailureType.VALIDATION_ERROR,
                )

            # Connect to MCP server
            client = MCPClient(self.server_command, timeout=self.timeout)
            try:
                client.connect()
                self._client = client

                # Translate intent to MCP tool calls
                tool_calls = self._translate_intent_to_mcp(context.intent)

                if context.dry_run:
                    # Dry run: show what would be executed
                    output = "DRY RUN - MCP tool calls:\n"
                    for tool_call in tool_calls:
                        output += f"  Tool: {tool_call['tool']}\n"
                        output += f"  Parameters: {tool_call['params']}\n"
                    return ExecutionResult(
                        success=True,
                        strategy=Strategy.MCP_CLIENT,
                        output=output,
                        duration_seconds=time.time() - start_time,
                        metadata={"tool_calls": tool_calls, "dry_run": True},
                    )

                # Execute tool calls
                resources_created = []
                outputs = []

                for i, tool_call in enumerate(tool_calls, 1):
                    tool_name = tool_call["tool"]
                    params = tool_call["params"]

                    # Call MCP tool
                    result = self._call_mcp_tool(client, tool_name, params)

                    # Check for errors in result
                    if isinstance(result, dict) and result.get("error"):
                        return ExecutionResult(
                            success=False,
                            strategy=Strategy.MCP_CLIENT,
                            output="\n".join(outputs),
                            error=result["error"],
                            failure_type=self._classify_mcp_error(result["error"]),
                            resources_created=resources_created,
                            duration_seconds=time.time() - start_time,
                            metadata={"failed_tool": tool_name, "call_index": i},
                        )

                    # Extract output
                    output = self._format_tool_result(result)
                    outputs.append(output)

                    # Extract created resources
                    created = self._extract_resources_from_result(result, tool_name)
                    resources_created.extend(created)

                # Success
                duration = time.time() - start_time
                return ExecutionResult(
                    success=True,
                    strategy=Strategy.MCP_CLIENT,
                    output="\n".join(outputs),
                    resources_created=resources_created,
                    duration_seconds=duration,
                    metadata={
                        "tool_calls_executed": len(tool_calls),
                        "tool_calls": tool_calls,
                    },
                )

            finally:
                client.disconnect()
                self._client = None

        except MCPConnectionError as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.MCP_CLIENT,
                error=f"MCP connection error: {e!s}",
                failure_type=FailureType.NETWORK_ERROR,
                duration_seconds=time.time() - start_time,
            )

        except MCPTimeoutError as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.MCP_CLIENT,
                error=f"MCP timeout: {e!s}",
                failure_type=FailureType.TIMEOUT,
                duration_seconds=time.time() - start_time,
            )

        except MCPToolNotFoundError as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.MCP_CLIENT,
                error=f"MCP tool not found: {e!s}",
                failure_type=FailureType.VALIDATION_ERROR,
                duration_seconds=time.time() - start_time,
            )

        except MCPError as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.MCP_CLIENT,
                error=f"MCP error: {e!s}",
                failure_type=FailureType.UNKNOWN,
                duration_seconds=time.time() - start_time,
            )

        except Exception as e:
            return ExecutionResult(
                success=False,
                strategy=Strategy.MCP_CLIENT,
                error=f"Unexpected error: {e!s}",
                failure_type=FailureType.UNKNOWN,
                duration_seconds=time.time() - start_time,
            )

    def validate(self, context: ExecutionContext) -> tuple[bool, str | None]:
        """Validate MCP server is available and has required tools.

        Args:
            context: Execution context

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Try to connect to MCP server
        client = MCPClient(self.server_command, timeout=10)
        try:
            client.connect()

            # Discover available tools
            try:
                tools = client.list_tools()
                if not tools:
                    return False, "MCP server has no available tools"
                return True, None
            except MCPError:
                return False, "Failed to list MCP tools"

        except MCPConnectionError as e:
            return False, f"MCP server not available: {e!s}"
        except Exception as e:
            return False, f"MCP validation failed: {e!s}"
        finally:
            client.disconnect()

    def estimate_duration(self, context: ExecutionContext) -> int:
        """Estimate execution duration in seconds.

        Args:
            context: Execution context

        Returns:
            Estimated duration in seconds
        """
        # Base duration: 60 seconds for MCP operations
        base = 60

        # Adjust for number of commands
        command_count = len(context.intent.azlin_commands)
        if command_count > 1:
            base += (command_count - 1) * 20

        # Adjust for complex operations
        intent_type = context.intent.intent.lower()
        if any(
            keyword in intent_type
            for keyword in ["provision", "create vm", "deploy", "aks", "cluster"]
        ):
            base = 300  # 5 minutes for complex operations

        return base

    def get_strategy_type(self) -> Strategy:
        """Get strategy type."""
        return Strategy.MCP_CLIENT

    def get_prerequisites(self) -> list[str]:
        """Get prerequisites for MCP strategy."""
        return [
            "MCP server installed and available",
            f"Server command: {self.server_command}",
            "MCP server supports Azure operations",
        ]

    def supports_dry_run(self) -> bool:
        """MCP strategy supports dry-run."""
        return True

    def get_cost_factors(self, context: ExecutionContext) -> dict[str, Any]:
        """Get cost-related factors.

        Args:
            context: Execution context

        Returns:
            Dictionary of cost factors
        """
        # Extract cost factors from intent parameters
        factors = {}
        params = context.intent.parameters

        if "vm_name" in params or "provision" in context.intent.intent.lower():
            factors["vm_count"] = params.get("count", 1)
            factors["vm_size"] = params.get("vm_size", "Standard_B2s")

        if "storage" in context.intent.intent.lower():
            factors["storage_gb"] = params.get("size_gb", 128)

        return factors

    def _discover_mcp_tools(self) -> list[str]:
        """Discover available MCP tools.

        Returns:
            List of available tool names
        """
        if self._available_tools is not None:
            return self._available_tools

        # Connect and list tools
        client = MCPClient(self.server_command, timeout=10)
        try:
            client.connect()
            tools = client.list_tools()
            self._available_tools = [tool["name"] for tool in tools]
            return self._available_tools
        except Exception:
            return []
        finally:
            client.disconnect()

    def _get_required_tools(self, context: ExecutionContext) -> list[str]:
        """Get required MCP tools for this intent.

        Args:
            context: Execution context

        Returns:
            List of required tool names
        """
        intent_type = context.intent.intent.lower()

        # Map intent types to MCP tools
        tool_mapping = {
            "provision_vm": ["azure_vm_create"],
            "create_vm": ["azure_vm_create"],
            "list_vms": ["azure_vm_list"],
            "list_vm": ["azure_vm_list"],
            "delete_vm": ["azure_vm_delete"],
            "kill_vm": ["azure_vm_delete"],
            "show_vm": ["azure_vm_show"],
            "get_vm": ["azure_vm_show"],
        }

        # Check for exact matches
        if intent_type in tool_mapping:
            return tool_mapping[intent_type]

        # Check for partial matches
        for key, tools in tool_mapping.items():
            if key in intent_type or any(k in intent_type for k in key.split("_")):
                return tools

        return []

    def _translate_intent_to_mcp(self, intent: Any) -> list[dict[str, Any]]:
        """Translate intent to MCP tool calls.

        Args:
            intent: Parsed intent

        Returns:
            List of tool calls with tool name and parameters
        """
        tool_calls = []
        intent_type = intent.intent.lower()
        params = intent.parameters

        # Translate based on intent type
        if "provision" in intent_type or "create_vm" in intent_type:
            tool_calls.append(
                {
                    "tool": "azure_vm_create",
                    "params": {
                        "name": params.get("vm_name", "vm"),
                        "resource_group": params.get("resource_group", "azlin-rg"),
                        "image": params.get("image", "Ubuntu2204"),
                        "size": params.get("vm_size", "Standard_B2s"),
                    },
                }
            )

        elif "list" in intent_type and "vm" in intent_type:
            tool_calls.append(
                {
                    "tool": "azure_vm_list",
                    "params": {
                        "resource_group": params.get("resource_group"),
                    },
                }
            )

        elif "delete" in intent_type or "kill" in intent_type:
            tool_calls.append(
                {
                    "tool": "azure_vm_delete",
                    "params": {
                        "name": params.get("vm_name", ""),
                        "resource_group": params.get("resource_group", "azlin-rg"),
                    },
                }
            )

        elif "show" in intent_type or "get" in intent_type:
            tool_calls.append(
                {
                    "tool": "azure_vm_show",
                    "params": {
                        "name": params.get("vm_name", ""),
                        "resource_group": params.get("resource_group", "azlin-rg"),
                    },
                }
            )

        return tool_calls

    def _call_mcp_tool(
        self, client: MCPClient, tool_name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Call MCP tool via client.

        Args:
            client: Connected MCP client
            tool_name: Tool name
            params: Tool parameters

        Returns:
            Tool result

        Raises:
            MCPError: If tool call fails
        """
        return client.call_tool(tool_name, params)

    def _extract_resources_from_result(
        self, result: dict[str, Any], tool_name: str
    ) -> list[str]:
        """Extract created resource IDs from MCP result.

        Args:
            result: MCP tool result
            tool_name: Tool that was called

        Returns:
            List of resource IDs
        """
        resources = []

        # Extract from common result structures
        if isinstance(result, dict):
            # Check for direct id field
            if "id" in result:
                resources.append(result["id"])
            elif "resourceId" in result:
                resources.append(result["resourceId"])

            # Check for content with resource IDs
            content = result.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        # Extract Azure resource ID patterns
                        pattern = r"/subscriptions/[a-f0-9-]+/resourceGroups/[^/]+/providers/[^/]+/[^/]+/[\w-]+"
                        matches = re.findall(pattern, text)
                        resources.extend(matches)

            # Check for nested data
            if "data" in result and isinstance(result["data"], dict) and "id" in result["data"]:
                resources.append(result["data"]["id"])

        return resources

    def _format_tool_result(self, result: dict[str, Any]) -> str:
        """Format MCP tool result for output.

        Args:
            result: MCP tool result

        Returns:
            Formatted output string
        """
        if not isinstance(result, dict):
            return str(result)

        # Extract content if available
        content = result.get("content", [])
        if isinstance(content, list):
            output_parts = [
                item["text"] for item in content if isinstance(item, dict) and "text" in item
            ]
            if output_parts:
                return "\n".join(output_parts)

        # Fallback to JSON representation
        import json

        return json.dumps(result, indent=2)

    def _classify_mcp_error(self, error: str | dict) -> FailureType:
        """Classify MCP error into FailureType.

        Args:
            error: Error message or object

        Returns:
            FailureType enum
        """
        error_str = str(error).lower()

        if "quota" in error_str or "exceeded" in error_str:
            return FailureType.QUOTA_EXCEEDED

        if "not found" in error_str or "does not exist" in error_str:
            return FailureType.RESOURCE_NOT_FOUND

        if "permission" in error_str or "unauthorized" in error_str or "forbidden" in error_str:
            return FailureType.PERMISSION_DENIED

        if "timeout" in error_str or "timed out" in error_str:
            return FailureType.TIMEOUT

        if "network" in error_str or "connection" in error_str:
            return FailureType.NETWORK_ERROR

        if "invalid" in error_str or "validation" in error_str:
            return FailureType.VALIDATION_ERROR

        return FailureType.UNKNOWN
