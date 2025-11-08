"""Unit tests for intent parser."""

import json
from unittest.mock import Mock, patch

import anthropic
import pytest

from azlin.agentic.intent_parser import CommandPlanner, IntentParseError, IntentParser


@pytest.fixture
def mock_anthropic_client():
    """Create mock Anthropic client."""
    with patch("azlin.agentic.intent_parser.anthropic") as mock_anthropic:
        # Create mock client
        mock_client = Mock()
        mock_anthropic.Anthropic.return_value = mock_client

        # Create mock message
        mock_message = Mock()
        mock_text_block = Mock()
        mock_text_block.text = json.dumps(
            {
                "intent": "provision_vm",
                "parameters": {"vm_name": "test-vm"},
                "confidence": 0.95,
                "azlin_commands": [{"command": "azlin new", "args": ["--name", "test-vm"]}],
                "explanation": "Create a new VM",
            }
        )
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        yield mock_client


class TestIntentParser:
    """Test IntentParser class."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        parser = IntentParser(api_key="sk-ant-test123")
        assert parser.api_key == "sk-ant-test123"

    def test_init_requires_api_key(self):
        """Test that initialization requires API key."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                IntentParser()

    def test_parse_success(self, mock_anthropic_client):
        """Test successful intent parsing."""
        parser = IntentParser(api_key="test-key")
        result = parser.parse("create a vm called test-vm")

        assert result["intent"] == "provision_vm"
        assert result["parameters"]["vm_name"] == "test-vm"
        assert result["confidence"] == 0.95
        assert len(result["azlin_commands"]) == 1

    def test_parse_with_context(self, mock_anthropic_client):
        """Test parsing with context."""
        parser = IntentParser(api_key="test-key")
        context = {"existing_vms": ["vm1", "vm2"]}
        result = parser.parse("create a vm", context=context)

        assert result is not None
        # Verify context was passed to Claude
        call_args = mock_anthropic_client.messages.create.call_args
        assert "existing_vms" in call_args[1]["system"]

    def test_parse_json_in_markdown(self, mock_anthropic_client):
        """Test parsing JSON wrapped in markdown code blocks."""
        mock_text_block = Mock()
        mock_text_block.text = """```json
{
    "intent": "list_vms",
    "parameters": {},
    "confidence": 1.0,
    "azlin_commands": [{"command": "azlin list", "args": []}]
}
```"""
        mock_message = Mock()
        mock_message.content = [mock_text_block]
        mock_anthropic_client.messages.create.return_value = mock_message

        parser = IntentParser(api_key="test-key")
        result = parser.parse("show me all vms")

        assert result["intent"] == "list_vms"

    def test_parse_api_error(self):
        """Test handling of API errors."""
        with patch("azlin.agentic.intent_parser.anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.Anthropic.return_value = mock_client
            # Create a mock API error that acts like an exception
            api_error = Exception("API error")
            api_error.__class__.__name__ = "APIError"
            mock_anthropic.APIError = Exception
            mock_client.messages.create.side_effect = api_error

            parser = IntentParser(api_key="test-key")
            with pytest.raises(IntentParseError, match="Claude API error"):
                parser.parse("test")

    def test_parse_invalid_json(self, mock_anthropic_client):
        """Test handling of invalid JSON response."""
        mock_text_block = Mock()
        mock_text_block.text = "not json"
        mock_message = Mock()
        mock_message.content = [mock_text_block]
        mock_anthropic_client.messages.create.return_value = mock_message

        parser = IntentParser(api_key="test-key")
        with pytest.raises(IntentParseError, match="Failed to parse"):
            parser.parse("test")

    def test_validate_intent_missing_field(self, mock_anthropic_client):
        """Test validation catches missing required fields."""
        mock_text_block = Mock()
        mock_text_block.text = json.dumps(
            {
                "intent": "provision_vm",
                "parameters": {},
                # Missing confidence and azlin_commands
            }
        )
        mock_message = Mock()
        mock_message.content = [mock_text_block]
        mock_anthropic_client.messages.create.return_value = mock_message

        parser = IntentParser(api_key="test-key")
        with pytest.raises(IntentParseError, match="Missing required field"):
            parser.parse("test")

    def test_validate_intent_invalid_confidence(self, mock_anthropic_client):
        """Test validation catches invalid confidence values."""
        mock_text_block = Mock()
        mock_text_block.text = json.dumps(
            {
                "intent": "provision_vm",
                "parameters": {},
                "confidence": 1.5,  # Invalid: > 1.0
                "azlin_commands": [],
            }
        )
        mock_message = Mock()
        mock_message.content = [mock_text_block]
        mock_anthropic_client.messages.create.return_value = mock_message

        parser = IntentParser(api_key="test-key")
        with pytest.raises(IntentParseError, match="confidence must be between 0 and 1"):
            parser.parse("test")


class TestCommandPlanner:
    """Test CommandPlanner class."""

    def test_init_requires_api_key(self):
        """Test that initialization requires API key."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                CommandPlanner()

    def test_plan_success(self):
        """Test successful command planning."""
        with patch("azlin.agentic.intent_parser.anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.Anthropic.return_value = mock_client

            mock_text_block = Mock()
            mock_text_block.text = json.dumps(
                {
                    "status": "in_progress",
                    "next_commands": [{"command": "azlin status", "args": ["vm1"]}],
                    "reasoning": "Check VM status",
                }
            )
            mock_message = Mock()
            mock_message.content = [mock_text_block]
            mock_client.messages.create.return_value = mock_message

            planner = CommandPlanner(api_key="test-key")
            intent = {"intent": "check_vm", "parameters": {"vm_name": "vm1"}}
            result = planner.plan(intent, [])

            assert result["status"] == "in_progress"
            assert len(result["next_commands"]) == 1

    def test_plan_error_fallback(self):
        """Test fallback behavior on planning errors."""
        with patch("azlin.agentic.intent_parser.anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.Anthropic.return_value = mock_client
            mock_client.messages.create.side_effect = Exception("Test error")

            planner = CommandPlanner(api_key="test-key")
            intent = {"intent": "test"}
            result = planner.plan(intent, [])

            assert result["status"] == "failed"
            assert "error" in result["reasoning"].lower()


class TestExtractJson:
    """Test JSON extraction from various formats."""

    def test_extract_plain_json(self):
        """Test extracting plain JSON."""
        parser = IntentParser(api_key="test-key")
        text = '{"key": "value"}'
        result = parser._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_with_markdown(self):
        """Test extracting JSON from markdown code blocks."""
        parser = IntentParser(api_key="test-key")
        text = '```json\n{"key": "value"}\n```'
        result = parser._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_with_text(self):
        """Test extracting JSON embedded in text."""
        parser = IntentParser(api_key="test-key")
        text = 'Here is the JSON: {"key": "value"} and more text'
        result = parser._extract_json(text)
        assert result == {"key": "value"}

    def test_extract_json_invalid(self):
        """Test handling of invalid JSON."""
        parser = IntentParser(api_key="test-key")
        text = "not json at all"
        with pytest.raises(json.JSONDecodeError):
            parser._extract_json(text)
