"""Tests for failure analyzer module."""

import json
from unittest.mock import Mock

import pytest

from azlin.agentic.failure_analyzer import (
    DocLink,
    ErrorSignature,
    FailureAnalysis,
    FailureAnalyzer,
)
from azlin.agentic.types import ExecutionResult, FailureType, Strategy


@pytest.fixture
def temp_history_file(tmp_path):
    """Create a temporary history file."""
    history_file = tmp_path / "failure_history.json"
    history_file.write_text("[]")
    return history_file


@pytest.fixture
def mock_ms_learn_client():
    """Create a mock MS Learn client."""
    client = Mock()
    client.search.return_value = [
        {
            "title": "Test Doc",
            "url": "https://example.com",
            "summary": "Test summary",
            "relevance_score": 0.9,
        }
    ]
    return client


class TestErrorSignature:
    """Test ErrorSignature dataclass."""

    def test_from_error_extracts_error_code(self):
        """Test error code extraction."""
        error_msg = 'Error: {"errorCode": "QuotaExceeded"}'
        sig = ErrorSignature.from_error(error_msg)

        assert sig.error_code == "QuotaExceeded"
        assert sig.signature_hash is not None

    def test_from_error_extracts_operation(self):
        """Test operation extraction."""
        error_msg = "Failed creating virtual machine"
        sig = ErrorSignature.from_error(error_msg)

        assert sig.operation == "creating"

    def test_from_error_with_resource_type(self):
        """Test signature with resource type."""
        error_msg = "Permission denied"
        sig = ErrorSignature.from_error(
            error_msg, resource_type="Microsoft.Compute/virtualMachines"
        )

        assert sig.resource_type == "Microsoft.Compute/virtualMachines"
        assert sig.signature_hash is not None

    def test_signature_hash_consistency(self):
        """Test that same error produces same hash."""
        error_msg = "QuotaExceeded for Standard_D4s_v3"
        sig1 = ErrorSignature.from_error(error_msg, "virtualMachines")
        sig2 = ErrorSignature.from_error(error_msg, "virtualMachines")

        assert sig1.signature_hash == sig2.signature_hash

    def test_different_errors_different_hashes(self):
        """Test that different errors produce different hashes."""
        sig1 = ErrorSignature.from_error("QuotaExceeded")
        sig2 = ErrorSignature.from_error("PermissionDenied")

        assert sig1.signature_hash != sig2.signature_hash


class TestFailureAnalysis:
    """Test FailureAnalysis dataclass."""

    def test_to_dict_serialization(self):
        """Test converting analysis to dictionary."""
        error_sig = ErrorSignature(
            error_code="QuotaExceeded",
            resource_type="virtualMachines",
            operation="create",
            signature_hash="abc123",
        )

        analysis = FailureAnalysis(
            failure_type=FailureType.QUOTA_EXCEEDED,
            error_signature=error_sig,
            error_message="Quota exceeded",
            suggested_fixes=["Increase quota"],
            runnable_commands=["az vm list-usage"],
            doc_links=[DocLink("Doc", "https://example.com", "Summary", 0.9)],
            similar_failures=2,
        )

        data = analysis.to_dict()

        assert data["failure_type"] == "quota_exceeded"
        assert data["error_signature"]["error_code"] == "QuotaExceeded"
        assert len(data["suggested_fixes"]) == 1
        assert len(data["runnable_commands"]) == 1
        assert len(data["doc_links"]) == 1
        assert data["similar_failures"] == 2


class TestFailureAnalyzer:
    """Test FailureAnalyzer class."""

    def test_initialization(self, temp_history_file):
        """Test analyzer initialization."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        assert analyzer.history_file == temp_history_file
        assert temp_history_file.exists()

    def test_analyze_quota_exceeded(self, temp_history_file, mock_ms_learn_client):
        """Test analyzing quota exceeded failure."""
        analyzer = FailureAnalyzer(
            history_file=temp_history_file,
            ms_learn_client=mock_ms_learn_client,
        )

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="QuotaExceeded for Standard_D4s_v3 in East US",
            failure_type=FailureType.QUOTA_EXCEEDED,
        )

        analysis = analyzer.analyze_failure(result)

        assert analysis.failure_type == FailureType.QUOTA_EXCEEDED
        assert len(analysis.suggested_fixes) > 0
        assert any("quota" in fix.lower() for fix in analysis.suggested_fixes)
        assert len(analysis.runnable_commands) > 0

    def test_analyze_permission_denied(self, temp_history_file):
        """Test analyzing permission denied failure."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="AuthorizationFailed: User does not have permission",
            failure_type=FailureType.PERMISSION_DENIED,
        )

        analysis = analyzer.analyze_failure(result)

        assert analysis.failure_type == FailureType.PERMISSION_DENIED
        assert any(
            "permission" in fix.lower() or "rbac" in fix.lower() for fix in analysis.suggested_fixes
        )

    def test_analyze_resource_not_found(self, temp_history_file):
        """Test analyzing resource not found failure."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="ResourceNotFound: The Resource 'test-vm' was not found",
            failure_type=FailureType.RESOURCE_NOT_FOUND,
        )

        analysis = analyzer.analyze_failure(result)

        assert analysis.failure_type == FailureType.RESOURCE_NOT_FOUND
        assert len(analysis.suggested_fixes) > 0

    def test_analyze_network_error(self, temp_history_file):
        """Test analyzing network error."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="NetworkError: Connection timeout",
            failure_type=FailureType.NETWORK_ERROR,
        )

        analysis = analyzer.analyze_failure(result)

        assert analysis.failure_type == FailureType.NETWORK_ERROR
        assert any(
            "network" in fix.lower() or "connection" in fix.lower()
            for fix in analysis.suggested_fixes
        )

    def test_analyze_validation_error(self, temp_history_file):
        """Test analyzing validation error."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="ValidationError: Invalid VM name format",
            failure_type=FailureType.VALIDATION_ERROR,
        )

        analysis = analyzer.analyze_failure(result)

        assert analysis.failure_type == FailureType.VALIDATION_ERROR
        assert any(
            "naming" in fix.lower() or "validation" in fix.lower()
            for fix in analysis.suggested_fixes
        )

    def test_find_similar_failures(self, temp_history_file):
        """Test finding similar past failures."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        # Create first failure
        result1 = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="QuotaExceeded for Standard_D4s_v3",
            failure_type=FailureType.QUOTA_EXCEEDED,
        )
        analyzer.analyze_failure(result1)

        # Create similar failure
        result2 = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="QuotaExceeded for Standard_D4s_v3",
            failure_type=FailureType.QUOTA_EXCEEDED,
        )
        analysis2 = analyzer.analyze_failure(result2)

        # Should find the previous failure
        similar = analyzer.find_similar_failures(analysis2.error_signature.signature_hash)
        assert len(similar) >= 1

    def test_suggest_fix_for_each_failure_type(self, temp_history_file):
        """Test that suggestions are provided for each failure type."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        failure_types = [
            FailureType.QUOTA_EXCEEDED,
            FailureType.PERMISSION_DENIED,
            FailureType.RESOURCE_NOT_FOUND,
            FailureType.NETWORK_ERROR,
            FailureType.TIMEOUT,
            FailureType.VALIDATION_ERROR,
            FailureType.DEPENDENCY_FAILED,
            FailureType.UNKNOWN,
        ]

        for failure_type in failure_types:
            suggestions = analyzer.suggest_fix(failure_type, f"Test error for {failure_type.value}")
            assert len(suggestions) > 0, f"No suggestions for {failure_type.value}"

    def test_search_ms_learn_with_client(self, temp_history_file):
        """Test MS Learn search with client."""
        mock_client = Mock()
        mock_client.search.return_value = [
            Mock(
                title="Test Doc", url="https://example.com", summary="Summary", relevance_score=0.9
            )
        ]

        analyzer = FailureAnalyzer(history_file=temp_history_file, ms_learn_client=mock_client)

        docs = analyzer.search_ms_learn("QuotaExceeded", "virtualMachines")

        assert len(docs) > 0
        mock_client.search.assert_called_once()

    def test_search_ms_learn_without_client(self, temp_history_file):
        """Test MS Learn search without client."""
        analyzer = FailureAnalyzer(history_file=temp_history_file, ms_learn_client=None)

        docs = analyzer.search_ms_learn("QuotaExceeded", "virtualMachines")

        assert len(docs) == 0

    def test_extract_resource_type_from_error(self, temp_history_file):
        """Test resource type extraction from error message."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        error_msg = "Failed to create Microsoft.Compute/virtualMachines"
        resource_type = analyzer._extract_resource_type(error_msg, None)

        assert resource_type is not None
        assert "Compute" in resource_type

    def test_extract_resource_type_from_metadata(self, temp_history_file):
        """Test resource type extraction from metadata."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        metadata = {"resource_type": "virtualMachines"}
        resource_type = analyzer._extract_resource_type("Some error", metadata)

        assert resource_type == "virtualMachines"

    def test_generate_commands_quota(self, temp_history_file):
        """Test command generation for quota errors."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        commands = analyzer._generate_commands(
            FailureType.QUOTA_EXCEEDED,
            "QuotaExceeded",
            "virtualMachines",
        )

        assert len(commands) > 0
        assert any("quota" in cmd.lower() or "usage" in cmd.lower() for cmd in commands)

    def test_generate_commands_permission(self, temp_history_file):
        """Test command generation for permission errors."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        commands = analyzer._generate_commands(
            FailureType.PERMISSION_DENIED,
            "AuthorizationFailed",
            None,
        )

        assert len(commands) > 0
        assert any("role" in cmd.lower() or "account" in cmd.lower() for cmd in commands)

    def test_history_persistence(self, temp_history_file):
        """Test that failure history is persisted."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        result = ExecutionResult(
            success=False,
            strategy=Strategy.AZURE_CLI,
            error="Test error",
            failure_type=FailureType.UNKNOWN,
        )

        analyzer.analyze_failure(result)

        # Read history file
        history = json.loads(temp_history_file.read_text())
        assert len(history) == 1
        assert history[0]["error_message"] == "Test error"

    def test_history_limit(self, temp_history_file):
        """Test that history is limited to 100 entries."""
        analyzer = FailureAnalyzer(history_file=temp_history_file)

        # Create 110 failures
        for i in range(110):
            result = ExecutionResult(
                success=False,
                strategy=Strategy.AZURE_CLI,
                error=f"Error {i}",
                failure_type=FailureType.UNKNOWN,
            )
            analyzer.analyze_failure(result)

        # Read history
        history = json.loads(temp_history_file.read_text())

        # Should keep only last 100
        assert len(history) == 100
        # Most recent should be present
        assert history[-1]["error_message"] == "Error 109"
