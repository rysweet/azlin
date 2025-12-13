"""Unit tests for fleet query parser."""

import json
from unittest.mock import Mock, patch

import pytest

from azlin.agentic.fleet_query_parser import (
    FleetQueryError,
    FleetQueryParser,
    ResultSynthesizer,
)


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client."""
    with patch("azlin.agentic.fleet_query_parser.anthropic.Anthropic") as mock:
        yield mock


class TestFleetQueryParser:
    """Test FleetQueryParser functionality."""

    def test_init_without_api_key_raises_error(self):
        """Test that initialization without API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                FleetQueryParser()

    def test_init_with_api_key(self, mock_anthropic_client):
        """Test initialization with API key."""
        parser = FleetQueryParser(api_key="test-key")
        assert parser.api_key == "test-key"
        mock_anthropic_client.assert_called_once_with(api_key="test-key")

    def test_parse_query_cost_analysis(self, mock_anthropic_client):
        """Test parsing cost analysis query."""
        # Setup mock response
        mock_message = Mock()
        mock_message.content = [
            Mock(
                text=json.dumps(
                    {
                        "query_type": "cost_analysis",
                        "metric": "cost",
                        "commands": [
                            {
                                "description": "Get VM costs",
                                "azlin_command": "azlin cost --by-vm",
                                "target": "all",
                            }
                        ],
                        "aggregation": "sort_by_value",
                        "top_n": 5,
                        "confidence": 0.95,
                        "explanation": "Sort VMs by monthly cost",
                        "requires_cost_data": True,
                        "requires_vm_metrics": False,
                    }
                )
            )
        ]

        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.return_value = mock_message

        parser = FleetQueryParser(api_key="test-key")
        result = parser.parse_query("which VMs cost the most?")

        # Assertions
        assert result["query_type"] == "cost_analysis"
        assert result["metric"] == "cost"
        assert result["confidence"] == 0.95
        assert result["requires_cost_data"] is True
        assert len(result["commands"]) == 1

    def test_parse_query_resource_usage(self, mock_anthropic_client):
        """Test parsing resource usage query."""
        mock_message = Mock()
        mock_message.content = [
            Mock(
                text=json.dumps(
                    {
                        "query_type": "resource_usage",
                        "metric": "disk",
                        "filter": {"threshold": "80%"},
                        "commands": [
                            {
                                "description": "Get disk usage",
                                "remote_command": "df -h / | tail -1 | awk '{print $5}'",
                                "target": "all",
                            }
                        ],
                        "aggregation": "filter_above_threshold",
                        "confidence": 0.92,
                        "explanation": "Find VMs using >80% disk",
                        "requires_cost_data": False,
                        "requires_vm_metrics": True,
                    }
                )
            )
        ]

        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.return_value = mock_message

        parser = FleetQueryParser(api_key="test-key")
        result = parser.parse_query("show VMs using more than 80% disk")

        assert result["query_type"] == "resource_usage"
        assert result["metric"] == "disk"
        assert result["filter"]["threshold"] == "80%"
        assert "df -h" in result["commands"][0]["remote_command"]

    def test_parse_query_version_check(self, mock_anthropic_client):
        """Test parsing version check query."""
        mock_message = Mock()
        mock_message.content = [
            Mock(
                text=json.dumps(
                    {
                        "query_type": "version_check",
                        "metric": "version",
                        "commands": [
                            {
                                "description": "Get Python version",
                                "remote_command": "python3 --version",
                                "target": "all",
                            }
                        ],
                        "aggregation": "group_by_result",
                        "confidence": 0.98,
                        "explanation": "List Python versions across fleet",
                    }
                )
            )
        ]

        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.return_value = mock_message

        parser = FleetQueryParser(api_key="test-key")
        result = parser.parse_query("what Python versions are installed?")

        assert result["query_type"] == "version_check"
        assert "python3 --version" in result["commands"][0]["remote_command"]

    def test_parse_query_with_context(self, mock_anthropic_client):
        """Test parsing query with context."""
        mock_message = Mock()
        mock_message.content = [
            Mock(
                text=json.dumps(
                    {
                        "query_type": "idle_detection",
                        "metric": "login_time",
                        "commands": [
                            {
                                "description": "Get last login",
                                "remote_command": "last -1",
                                "target": "all",
                            }
                        ],
                        "aggregation": "filter_by_time",
                        "confidence": 0.90,
                    }
                )
            )
        ]

        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.return_value = mock_message

        parser = FleetQueryParser(api_key="test-key")
        context = {"vm_count": 10, "vms": [{"name": "vm-1"}]}
        result = parser.parse_query("show idle VMs", context=context)

        assert result["query_type"] == "idle_detection"
        assert mock_client.messages.create.called

    def test_validate_query_missing_fields(self):
        """Test query validation with missing fields."""
        parser = FleetQueryParser(api_key="test-key")

        # Missing required fields
        with pytest.raises(ValueError, match="Missing required field"):
            parser._validate_query({"query_type": "cost"})

    def test_validate_query_invalid_confidence(self):
        """Test query validation with invalid confidence."""
        parser = FleetQueryParser(api_key="test-key")

        query = {
            "query_type": "cost",
            "commands": [{"command": "test"}],
            "aggregation": "sort",
            "confidence": 1.5,  # Invalid
        }

        with pytest.raises(ValueError, match="Confidence must be"):
            parser._validate_query(query)

    def test_validate_query_empty_commands(self):
        """Test query validation with empty commands."""
        parser = FleetQueryParser(api_key="test-key")

        query = {
            "query_type": "cost",
            "commands": [],  # Empty
            "aggregation": "sort",
            "confidence": 0.9,
        }

        with pytest.raises(ValueError, match="Commands must be a non-empty list"):
            parser._validate_query(query)

    def test_extract_json_from_markdown(self):
        """Test JSON extraction from markdown code blocks."""
        parser = FleetQueryParser(api_key="test-key")

        # JSON wrapped in markdown
        text = """```json
        {"query_type": "test", "value": 123}
        ```"""

        result = parser._extract_json(text)
        assert result["query_type"] == "test"
        assert result["value"] == 123

    def test_extract_json_plain(self):
        """Test JSON extraction from plain text."""
        parser = FleetQueryParser(api_key="test-key")

        text = '{"query_type": "test", "value": 456}'
        result = parser._extract_json(text)

        assert result["query_type"] == "test"
        assert result["value"] == 456

    def test_parse_query_api_error(self, mock_anthropic_client):
        """Test handling of API errors."""
        mock_client = mock_anthropic_client.return_value

        # Simulate generic exception (could be API error)
        mock_client.messages.create.side_effect = Exception("API failed")

        parser = FleetQueryParser(api_key="test-key")

        # Should raise some kind of error
        with pytest.raises(Exception):
            parser.parse_query("test query")


class TestResultSynthesizer:
    """Test ResultSynthesizer functionality."""

    def test_init_without_api_key(self):
        """Test initialization without API key raises error."""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                ResultSynthesizer()

    def test_synthesize_basic(self, mock_anthropic_client):
        """Test basic result synthesis."""
        mock_message = Mock()
        mock_message.content = [
            Mock(
                text=json.dumps(
                    {
                        "summary": "5 VMs analyzed, 2 are high cost",
                        "results": [
                            {"vm_name": "vm-1", "value": "$150", "status": "warning"},
                            {"vm_name": "vm-2", "value": "$200", "status": "critical"},
                        ],
                        "insights": ["vm-2 costs twice the average"],
                        "recommendations": ["Consider downsizing vm-2"],
                        "total_analyzed": 5,
                        "critical_count": 1,
                        "warning_count": 1,
                    }
                )
            )
        ]

        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.return_value = mock_message

        synthesizer = ResultSynthesizer(api_key="test-key")

        query = "which VMs cost the most?"
        query_plan = {"query_type": "cost_analysis"}
        results = [
            {"vm_name": "vm-1", "value": "$150"},
            {"vm_name": "vm-2", "value": "$200"},
        ]

        synthesis = synthesizer.synthesize(query, query_plan, results)

        assert "summary" in synthesis
        assert len(synthesis["results"]) == 2
        assert len(synthesis["insights"]) > 0
        assert len(synthesis["recommendations"]) > 0

    def test_synthesize_with_error(self, mock_anthropic_client):
        """Test synthesis fallback on error."""
        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.side_effect = Exception("API failed")

        synthesizer = ResultSynthesizer(api_key="test-key")

        query = "test"
        query_plan = {"query_type": "test"}
        results = [{"vm_name": "vm-1", "value": "test"}]

        synthesis = synthesizer.synthesize(query, query_plan, results)

        # Should return fallback
        assert "summary" in synthesis
        assert "error" in synthesis
        assert len(synthesis["results"]) == 1

    def test_synthesize_empty_results(self, mock_anthropic_client):
        """Test synthesis with empty results."""
        mock_message = Mock()
        mock_message.content = [
            Mock(
                text=json.dumps(
                    {
                        "summary": "No VMs match criteria",
                        "results": [],
                        "insights": [],
                        "recommendations": [],
                        "total_analyzed": 0,
                    }
                )
            )
        ]

        mock_client = mock_anthropic_client.return_value
        mock_client.messages.create.return_value = mock_message

        synthesizer = ResultSynthesizer(api_key="test-key")

        synthesis = synthesizer.synthesize("test", {}, [])

        assert synthesis["total_analyzed"] == 0
        assert len(synthesis["results"]) == 0
