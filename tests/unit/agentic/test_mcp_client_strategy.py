"""Tests for MCPClientStrategy.

Tests MCP execution strategy, validation, and error handling.
"""

from unittest.mock import Mock, patch

import pytest

from azlin.agentic.mcp_client import (
    MCPConnectionError,
    MCPError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from azlin.agentic.strategies.mcp_client_strategy import MCPClientStrategy
from azlin.agentic.types import ExecutionContext, FailureType, Intent, Strategy


@pytest.fixture
def intent_provision_vm():
    """Intent for provisioning a VM."""
    return Intent(
        intent="provision_vm",
        parameters={"vm_name": "test-vm", "resource_group": "test-rg"},
        confidence=0.9,
        azlin_commands=[{"command": "new", "args": ["--name", "test-vm"]}],
    )


@pytest.fixture
def intent_list_vms():
    """Intent for listing VMs."""
    return Intent(
        intent="list_vms",
        parameters={},
        confidence=0.9,
        azlin_commands=[{"command": "list", "args": []}],
    )


@pytest.fixture
def intent_delete_vm():
    """Intent for deleting a VM."""
    return Intent(
        intent="delete_vm",
        parameters={"vm_name": "old-vm", "resource_group": "test-rg"},
        confidence=0.9,
        azlin_commands=[{"command": "kill", "args": ["--name", "old-vm"]}],
    )


@pytest.fixture
def execution_context(intent_provision_vm):
    """Execution context for testing."""
    return ExecutionContext(
        objective_id="obj_test",
        intent=intent_provision_vm,
        strategy=Strategy.MCP_CLIENT,
        resource_group="test-rg",
    )


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client."""
    with patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient") as mock:
        client = Mock()
        mock.return_value = client
        yield client


class TestCanHandle:
    """Tests for can_handle method."""

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_can_handle_when_tools_available(self, mock_client_class, execution_context):
        """Can handle when MCP server has required tools."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [
            {"name": "azure_vm_create", "description": "Create VM"}
        ]

        strategy = MCPClientStrategy()
        result = strategy.can_handle(execution_context)

        assert result is True

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_can_handle_when_tools_missing(self, mock_client_class, execution_context):
        """Cannot handle when MCP server lacks required tools."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [
            {"name": "azure_storage_create", "description": "Create storage"}
        ]

        strategy = MCPClientStrategy()
        result = strategy.can_handle(execution_context)

        assert result is False

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_can_handle_connection_failure(self, mock_client_class, execution_context):
        """Cannot handle when MCP server connection fails."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.side_effect = MCPConnectionError("Connection failed")

        strategy = MCPClientStrategy()
        result = strategy.can_handle(execution_context)

        assert result is False


class TestValidate:
    """Tests for validation."""

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_validate_success(self, mock_client_class, execution_context):
        """Validation passes when MCP server available with tools."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [
            {"name": "azure_vm_create", "description": "Create VM"}
        ]

        strategy = MCPClientStrategy()
        valid, error = strategy.validate(execution_context)

        assert valid is True
        assert error is None

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_validate_no_tools(self, mock_client_class, execution_context):
        """Validation fails when MCP server has no tools."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = []

        strategy = MCPClientStrategy()
        valid, error = strategy.validate(execution_context)

        assert valid is False
        assert "no available tools" in error.lower()

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_validate_connection_error(self, mock_client_class, execution_context):
        """Validation fails when connection fails."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.side_effect = MCPConnectionError("Server not found")

        strategy = MCPClientStrategy()
        valid, error = strategy.validate(execution_context)

        assert valid is False
        assert "not available" in error.lower()

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_validate_list_tools_error(self, mock_client_class, execution_context):
        """Validation fails when list_tools fails."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.side_effect = MCPError("List failed")

        strategy = MCPClientStrategy()
        valid, error = strategy.validate(execution_context)

        assert valid is False
        assert "failed to list" in error.lower()


class TestExecute:
    """Tests for execute method."""

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_dry_run(self, mock_client_class, execution_context):
        """Dry run shows tool calls without executing."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]

        execution_context.dry_run = True

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is True
        assert "DRY RUN" in result.output
        assert result.metadata["dry_run"] is True
        # Should not call actual tool
        client_instance.call_tool.assert_not_called()

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_success(self, mock_client_class, execution_context):
        """Successful execution via MCP."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]
        client_instance.call_tool.return_value = {
            "content": [{"text": "VM test-vm created successfully"}],
            "id": "/subscriptions/abc/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm",
        }

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is True
        assert result.strategy == Strategy.MCP_CLIENT
        assert "created successfully" in result.output
        assert len(result.resources_created) > 0
        assert result.duration_seconds is not None

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_validation_failure(self, mock_client_class, execution_context):
        """Execution fails when validation fails."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.side_effect = MCPConnectionError("Not available")

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is False
        assert result.failure_type == FailureType.VALIDATION_ERROR

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_tool_error(self, mock_client_class, execution_context):
        """Execution handles tool execution errors."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]
        client_instance.call_tool.return_value = {"error": "QuotaExceeded: Maximum VMs exceeded"}

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is False
        assert result.failure_type == FailureType.QUOTA_EXCEEDED

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_connection_error(self, mock_client_class, execution_context):
        """Execution handles connection errors."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.side_effect = [None, None]  # For validate and execute
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]

        # Connection error during execute (after validation)
        def connect_side_effect():
            if client_instance.connect.call_count > 2:
                raise MCPConnectionError("Connection lost")

        client_instance.connect.side_effect = [None, MCPConnectionError("Connection lost")]

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is False
        assert result.failure_type == FailureType.NETWORK_ERROR

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_timeout_error(self, mock_client_class, execution_context):
        """Execution handles timeout errors."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]
        client_instance.call_tool.side_effect = MCPTimeoutError("Request timed out")

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is False
        assert result.failure_type == FailureType.TIMEOUT

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_tool_not_found(self, mock_client_class, execution_context):
        """Execution handles tool not found errors."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]
        client_instance.call_tool.side_effect = MCPToolNotFoundError("Tool not found")

        strategy = MCPClientStrategy()
        result = strategy.execute(execution_context)

        assert result.success is False
        assert result.failure_type == FailureType.VALIDATION_ERROR

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_disconnects_on_success(self, mock_client_class, execution_context):
        """Execution disconnects after success."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]
        client_instance.call_tool.return_value = {"content": [{"text": "Success"}]}

        strategy = MCPClientStrategy()
        strategy.execute(execution_context)

        client_instance.disconnect.assert_called()

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_execute_disconnects_on_error(self, mock_client_class, execution_context):
        """Execution disconnects even on error."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]
        client_instance.call_tool.side_effect = MCPError("Tool failed")

        strategy = MCPClientStrategy()
        strategy.execute(execution_context)

        client_instance.disconnect.assert_called()


class TestIntentTranslation:
    """Tests for intent to MCP tool translation."""

    def test_translate_provision_vm(self):
        """Translate provision VM intent."""
        strategy = MCPClientStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test-vm", "vm_size": "Standard_D2s_v3"},
            confidence=0.9,
            azlin_commands=[],
        )

        tool_calls = strategy._translate_intent_to_mcp(intent)

        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "azure_vm_create"
        assert tool_calls[0]["params"]["name"] == "test-vm"
        assert tool_calls[0]["params"]["size"] == "Standard_D2s_v3"

    def test_translate_list_vms(self, intent_list_vms):
        """Translate list VMs intent."""
        strategy = MCPClientStrategy()

        tool_calls = strategy._translate_intent_to_mcp(intent_list_vms)

        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "azure_vm_list"

    def test_translate_delete_vm(self, intent_delete_vm):
        """Translate delete VM intent."""
        strategy = MCPClientStrategy()

        tool_calls = strategy._translate_intent_to_mcp(intent_delete_vm)

        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "azure_vm_delete"
        assert tool_calls[0]["params"]["name"] == "old-vm"

    def test_translate_show_vm(self):
        """Translate show VM intent."""
        strategy = MCPClientStrategy()
        intent = Intent(
            intent="show_vm",
            parameters={"vm_name": "my-vm"},
            confidence=0.9,
            azlin_commands=[],
        )

        tool_calls = strategy._translate_intent_to_mcp(intent)

        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "azure_vm_show"


class TestResourceExtraction:
    """Tests for extracting resource IDs from results."""

    def test_extract_resources_from_id_field(self):
        """Extract resource ID from id field."""
        strategy = MCPClientStrategy()
        result = {
            "id": "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
        }

        resources = strategy._extract_resources_from_result(result, "azure_vm_create")

        assert len(resources) == 1
        assert "virtualMachines/vm1" in resources[0]

    def test_extract_resources_from_content(self):
        """Extract resource IDs from content text."""
        strategy = MCPClientStrategy()
        result = {
            "content": [
                {
                    "text": "Created VM: /subscriptions/abc-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm"
                }
            ]
        }

        resources = strategy._extract_resources_from_result(result, "azure_vm_create")

        assert len(resources) >= 1
        assert any("virtualMachines/test-vm" in r for r in resources)

    def test_extract_resources_from_nested_data(self):
        """Extract resource ID from nested data field."""
        strategy = MCPClientStrategy()
        result = {
            "data": {
                "id": "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
            }
        }

        resources = strategy._extract_resources_from_result(result, "azure_vm_create")

        assert len(resources) == 1

    def test_extract_resources_no_matches(self):
        """No resources extracted when none present."""
        strategy = MCPClientStrategy()
        result = {"content": [{"text": "Operation completed"}]}

        resources = strategy._extract_resources_from_result(result, "azure_vm_create")

        assert len(resources) == 0


class TestResultFormatting:
    """Tests for formatting MCP results."""

    def test_format_result_with_content(self):
        """Format result with content array."""
        strategy = MCPClientStrategy()
        result = {"content": [{"text": "Line 1"}, {"text": "Line 2"}]}

        output = strategy._format_tool_result(result)

        assert "Line 1" in output
        assert "Line 2" in output

    def test_format_result_without_content(self):
        """Format result without content as JSON."""
        strategy = MCPClientStrategy()
        result = {"status": "success", "message": "Completed"}

        output = strategy._format_tool_result(result)

        # Should be JSON formatted
        assert "status" in output
        assert "success" in output

    def test_format_non_dict_result(self):
        """Format non-dictionary result."""
        strategy = MCPClientStrategy()
        result = "Simple string result"

        output = strategy._format_tool_result(result)

        assert output == "Simple string result"


class TestErrorClassification:
    """Tests for classifying MCP errors."""

    def test_classify_quota_exceeded(self):
        """Classify quota exceeded error."""
        strategy = MCPClientStrategy()
        error = "QuotaExceeded: Maximum number of VMs exceeded"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.QUOTA_EXCEEDED

    def test_classify_resource_not_found(self):
        """Classify resource not found error."""
        strategy = MCPClientStrategy()
        error = "Resource 'vm-123' does not exist"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.RESOURCE_NOT_FOUND

    def test_classify_permission_denied(self):
        """Classify permission error."""
        strategy = MCPClientStrategy()
        error = "Unauthorized: You do not have permission"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.PERMISSION_DENIED

    def test_classify_timeout(self):
        """Classify timeout error."""
        strategy = MCPClientStrategy()
        error = "Operation timed out after 60 seconds"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.TIMEOUT

    def test_classify_network_error(self):
        """Classify network error."""
        strategy = MCPClientStrategy()
        error = "Network connection failed"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.NETWORK_ERROR

    def test_classify_validation_error(self):
        """Classify validation error."""
        strategy = MCPClientStrategy()
        error = "Invalid VM size specified"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.VALIDATION_ERROR

    def test_classify_unknown_error(self):
        """Classify unknown error."""
        strategy = MCPClientStrategy()
        error = "Something unexpected happened"

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.UNKNOWN

    def test_classify_error_dict(self):
        """Classify error from dictionary."""
        strategy = MCPClientStrategy()
        error = {"code": "QuotaExceeded", "message": "Quota exceeded"}

        failure_type = strategy._classify_mcp_error(error)

        assert failure_type == FailureType.QUOTA_EXCEEDED


class TestHelperMethods:
    """Tests for helper methods."""

    def test_get_strategy_type(self):
        """Get strategy type."""
        strategy = MCPClientStrategy()

        assert strategy.get_strategy_type() == Strategy.MCP_CLIENT

    def test_get_prerequisites(self):
        """Get prerequisites list."""
        strategy = MCPClientStrategy()

        prereqs = strategy.get_prerequisites()

        assert len(prereqs) > 0
        assert any("mcp" in p.lower() for p in prereqs)

    def test_supports_dry_run(self):
        """Supports dry run."""
        strategy = MCPClientStrategy()

        assert strategy.supports_dry_run() is True

    def test_estimate_duration_simple(self):
        """Estimate duration for simple operation."""
        strategy = MCPClientStrategy()
        intent = Intent(
            intent="list_vms",
            parameters={},
            confidence=0.9,
            azlin_commands=[{}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.MCP_CLIENT,
        )

        duration = strategy.estimate_duration(context)

        assert duration > 0
        assert duration < 300  # Less than 5 minutes for simple ops

    def test_estimate_duration_complex(self):
        """Estimate duration for complex operation."""
        strategy = MCPClientStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={},
            confidence=0.9,
            azlin_commands=[{}],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.MCP_CLIENT,
        )

        duration = strategy.estimate_duration(context)

        # VM provisioning takes longer
        assert duration >= 300

    def test_get_cost_factors_vm(self):
        """Get cost factors for VM."""
        strategy = MCPClientStrategy()
        intent = Intent(
            intent="provision_vm",
            parameters={"vm_name": "test", "vm_size": "Standard_D4s_v3"},
            confidence=0.9,
            azlin_commands=[],
        )
        context = ExecutionContext(
            objective_id="test",
            intent=intent,
            strategy=Strategy.MCP_CLIENT,
        )

        factors = strategy.get_cost_factors(context)

        assert "vm_size" in factors
        assert factors["vm_size"] == "Standard_D4s_v3"

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_discover_mcp_tools(self, mock_client_class):
        """Discover available MCP tools."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [
            {"name": "azure_vm_create"},
            {"name": "azure_vm_list"},
        ]

        strategy = MCPClientStrategy()
        tools = strategy._discover_mcp_tools()

        assert len(tools) == 2
        assert "azure_vm_create" in tools
        assert "azure_vm_list" in tools

    @patch("azlin.agentic.strategies.mcp_client_strategy.MCPClient")
    def test_discover_mcp_tools_cached(self, mock_client_class):
        """Discover tools uses cache on subsequent calls."""
        client_instance = Mock()
        mock_client_class.return_value = client_instance
        client_instance.connect.return_value = None
        client_instance.list_tools.return_value = [{"name": "azure_vm_create"}]

        strategy = MCPClientStrategy()
        tools1 = strategy._discover_mcp_tools()
        tools2 = strategy._discover_mcp_tools()

        # Should only connect once due to caching
        assert tools1 == tools2
        assert client_instance.connect.call_count == 1

    def test_get_required_tools_provision(self, intent_provision_vm):
        """Get required tools for provision intent."""
        strategy = MCPClientStrategy()
        context = ExecutionContext(
            objective_id="test",
            intent=intent_provision_vm,
            strategy=Strategy.MCP_CLIENT,
        )

        tools = strategy._get_required_tools(context)

        assert "azure_vm_create" in tools

    def test_get_required_tools_list(self, intent_list_vms):
        """Get required tools for list intent."""
        strategy = MCPClientStrategy()
        context = ExecutionContext(
            objective_id="test",
            intent=intent_list_vms,
            strategy=Strategy.MCP_CLIENT,
        )

        tools = strategy._get_required_tools(context)

        assert "azure_vm_list" in tools

    def test_custom_server_command(self):
        """Strategy accepts custom server command."""
        strategy = MCPClientStrategy(server_command=["python", "-m", "my_mcp_server"])

        assert strategy.server_command == ["python", "-m", "my_mcp_server"]

    def test_custom_timeout(self):
        """Strategy accepts custom timeout."""
        strategy = MCPClientStrategy(timeout=120)

        assert strategy.timeout == 120
