"""Unit tests for agentic intent parser module."""

import json
from unittest.mock import Mock, patch

import pytest

from azlin.agentic import IntentParseError, IntentParser


class TestIntentParser:
    """Test intent parser functionality."""

    def test_init_with_api_key(self):
        """Test parser initialization with API key."""
        parser = IntentParser(api_key="test-key")
        assert parser.api_key == "test-key"
        assert parser.client is not None

    def test_init_without_api_key_raises_error(self, monkeypatch):
        """Test parser initialization without API key raises error."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            IntentParser()

    def test_init_with_env_var(self, monkeypatch):
        """Test parser initialization with environment variable."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        parser = IntentParser()
        assert parser.api_key == "env-key"

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_parse_provision_vm(self, mock_anthropic):
        """Test parsing 'create a vm called Sam' request."""
        # Mock Claude API response
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "intent": "provision_vm",
                        "parameters": {"vm_name": "Sam"},
                        "confidence": 0.95,
                        "azlin_commands": [{"command": "azlin new", "args": ["--name", "Sam"]}],
                        "explanation": "Provision new VM named Sam",
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")
        result = parser.parse("create a new vm called Sam")

        assert result["intent"] == "provision_vm"
        assert result["parameters"]["vm_name"] == "Sam"
        assert result["confidence"] == 0.95
        assert len(result["azlin_commands"]) == 1
        assert result["azlin_commands"][0]["command"] == "azlin new"

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_parse_with_context(self, mock_anthropic):
        """Test parsing with context information."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "intent": "list_vms",
                        "parameters": {},
                        "confidence": 0.99,
                        "azlin_commands": [{"command": "azlin list", "args": []}],
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")
        context = {"resource_group": "test-rg", "current_vms": []}
        _ = parser.parse("list all vms", context=context)

        # Verify context was passed to Claude
        call_args = mock_client.messages.create.call_args
        assert "test-rg" in call_args.kwargs["system"]

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_parse_with_markdown_wrapped_json(self, mock_anthropic):
        """Test parsing when Claude wraps response in markdown code blocks."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text="""```json
{
    "intent": "list_vms",
    "parameters": {},
    "confidence": 0.95,
    "azlin_commands": [{"command": "azlin list", "args": []}]
}
```"""
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")
        result = parser.parse("show me all vms")

        assert result["intent"] == "list_vms"
        assert result["confidence"] == 0.95

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_parse_api_error(self, mock_anthropic):
        """Test handling of Claude API errors."""
        mock_client = Mock()
        # Create a minimal mock request object
        mock_request = Mock()
        from anthropic import APIError

        mock_client.messages.create.side_effect = APIError(
            "API Error", request=mock_request, body=None
        )
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")

        with pytest.raises(IntentParseError, match="Claude API error"):
            parser.parse("create a vm")

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_parse_invalid_json(self, mock_anthropic):
        """Test handling of invalid JSON responses."""
        mock_response = Mock()
        mock_response.content = [Mock(text="This is not valid JSON")]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")

        with pytest.raises(IntentParseError, match="Failed to parse"):
            parser.parse("create a vm")

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_validate_intent_missing_required_field(self, mock_anthropic):
        """Test validation of intent with missing required fields."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "intent": "provision_vm",
                        # Missing 'parameters' field
                        "confidence": 0.95,
                        "azlin_commands": [],
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")

        with pytest.raises(IntentParseError, match="Missing required field"):
            parser.parse("create a vm")

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_validate_intent_invalid_confidence(self, mock_anthropic):
        """Test validation of intent with invalid confidence value."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "intent": "provision_vm",
                        "parameters": {},
                        "confidence": 1.5,  # Invalid: > 1.0
                        "azlin_commands": [],
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")

        with pytest.raises(IntentParseError, match="confidence must be between"):
            parser.parse("create a vm")

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_extract_json_from_text_with_prefix(self, mock_anthropic):
        """Test JSON extraction when response has text before JSON."""
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text="""Here's the parsed intent:

{
    "intent": "list_vms",
    "parameters": {},
    "confidence": 0.95,
    "azlin_commands": []
}"""
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        parser = IntentParser(api_key="test-key")
        result = parser.parse("show vms")

        assert result["intent"] == "list_vms"

    def test_build_system_prompt_without_context(self):
        """Test system prompt building without context."""
        parser = IntentParser(api_key="test-key")
        prompt = parser._build_system_prompt(None)

        assert "azlin" in prompt.lower()
        assert "azlin new" in prompt
        assert "azlin list" in prompt
        assert "Current Context" not in prompt

    def test_build_system_prompt_with_context(self):
        """Test system prompt building with context."""
        parser = IntentParser(api_key="test-key")
        context = {"resource_group": "test-rg", "current_vms": []}
        prompt = parser._build_system_prompt(context)

        assert "azlin" in prompt.lower()
        assert "Current Context" in prompt
        assert "test-rg" in prompt

    def test_build_user_message(self):
        """Test user message building."""
        parser = IntentParser(api_key="test-key")
        message = parser._build_user_message("create a vm")

        assert "Parse this request:" in message
        assert "create a vm" in message


class TestCommandPlanner:
    """Test command planner functionality."""

    def test_init_without_api_key_raises_error(self, monkeypatch):
        """Test planner initialization without API key raises error."""
        from azlin.agentic.intent_parser import CommandPlanner

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            CommandPlanner()

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_plan_in_progress(self, mock_anthropic):
        """Test planning returns next steps."""
        from azlin.agentic.intent_parser import CommandPlanner

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "status": "in_progress",
                        "next_commands": [{"command": "azlin status", "args": ["--vm", "Sam"]}],
                        "reasoning": "Need to verify VM was created",
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        planner = CommandPlanner(api_key="test-key")
        intent = {"intent": "provision_vm", "parameters": {"vm_name": "Sam"}}
        results = [{"success": True, "stdout": "VM created"}]

        plan = planner.plan(intent, results)

        assert plan["status"] == "in_progress"
        assert len(plan["next_commands"]) == 1

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_plan_complete(self, mock_anthropic):
        """Test planning recognizes completion."""
        from azlin.agentic.intent_parser import CommandPlanner

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "status": "complete",
                        "next_commands": [],
                        "reasoning": "All tasks completed successfully",
                    }
                )
            )
        ]

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        planner = CommandPlanner(api_key="test-key")
        intent = {"intent": "provision_vm"}
        results = [{"success": True}]

        plan = planner.plan(intent, results)

        assert plan["status"] == "complete"
        assert len(plan["next_commands"]) == 0

    @patch("azlin.agentic.intent_parser.anthropic.Anthropic")
    def test_plan_with_api_error(self, mock_anthropic):
        """Test planning fallback on API error."""
        from azlin.agentic.intent_parser import CommandPlanner

        mock_client = Mock()
        mock_request = Mock()
        from anthropic import APIError

        mock_client.messages.create.side_effect = APIError(
            "API Error", request=mock_request, body=None
        )
        mock_anthropic.return_value = mock_client

        planner = CommandPlanner(api_key="test-key")
        intent = {"intent": "provision_vm"}
        results = [{"success": True}]

        plan = planner.plan(intent, results)

        assert plan["status"] == "failed"
        assert "Planning error" in plan["reasoning"]
