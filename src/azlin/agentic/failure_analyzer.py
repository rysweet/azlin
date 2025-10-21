"""Intelligent failure analysis and resolution suggestion.

This module analyzes Azure CLI/Terraform failures and suggests fixes:
- Parse error messages and extract key information
- Classify failures into categories
- Suggest resolution steps
- Search MS Learn documentation
- Track failure history for pattern recognition
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from azlin.agentic.types import ExecutionResult, FailureType

logger = logging.getLogger(__name__)


@dataclass
class ErrorSignature:
    """Unique signature for error pattern matching."""

    error_code: str | None
    resource_type: str | None
    operation: str | None
    signature_hash: str

    @classmethod
    def from_error(cls, error_message: str, resource_type: str | None = None) -> "ErrorSignature":
        """Create signature from error message.

        Args:
            error_message: Error message text
            resource_type: Optional resource type

        Returns:
            ErrorSignature instance
        """
        # Extract error code (e.g., "InvalidParameter", "QuotaExceeded")
        error_code = None
        code_patterns = [
            r"error[Cc]ode[\"']?\s*:\s*[\"']?([A-Za-z0-9_]+)",
            r"([A-Z][a-z]+(?:[A-Z][a-z]+)+)(?:Error|Exception|Failure)",
            r"Code:\s*([A-Za-z0-9_]+)",
        ]
        for pattern in code_patterns:
            match = re.search(pattern, error_message)
            if match:
                error_code = match.group(1)
                break

        # Extract operation (e.g., "create", "delete", "update")
        operation = None
        op_patterns = [
            r"\b(creat(?:e|ing)|delet(?:e|ing)|updat(?:e|ing)|provision(?:ing)?)\b",
        ]
        for pattern in op_patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                operation = match.group(1).lower()
                break

        # Create hash for deduplication
        signature_parts = [
            error_code or "",
            resource_type or "",
            operation or "",
            error_message[:100],  # First 100 chars for context
        ]
        signature_text = "|".join(signature_parts)
        signature_hash = hashlib.sha256(signature_text.encode()).hexdigest()[:16]

        return cls(
            error_code=error_code,
            resource_type=resource_type,
            operation=operation,
            signature_hash=signature_hash,
        )


@dataclass
class DocLink:
    """Link to MS Learn documentation."""

    title: str
    url: str
    summary: str | None = None
    relevance_score: float = 0.0


@dataclass
class FailureAnalysis:
    """Complete failure analysis with suggestions."""

    failure_type: FailureType
    error_signature: ErrorSignature
    error_message: str
    suggested_fixes: list[str] = field(default_factory=list)
    runnable_commands: list[str] = field(default_factory=list)
    doc_links: list[DocLink] = field(default_factory=list)
    similar_failures: int = 0
    analysis_timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "failure_type": self.failure_type.value,
            "error_signature": {
                "error_code": self.error_signature.error_code,
                "resource_type": self.error_signature.resource_type,
                "operation": self.error_signature.operation,
                "signature_hash": self.error_signature.signature_hash,
            },
            "error_message": self.error_message,
            "suggested_fixes": self.suggested_fixes,
            "runnable_commands": self.runnable_commands,
            "doc_links": [
                {
                    "title": doc.title,
                    "url": doc.url,
                    "summary": doc.summary,
                    "relevance_score": doc.relevance_score,
                }
                for doc in self.doc_links
            ],
            "similar_failures": self.similar_failures,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
        }


class FailureAnalyzer:
    """Intelligent failure analysis and resolution suggestion.

    Analyzes execution failures and provides actionable suggestions:
    1. Parses error messages to extract key information
    2. Classifies failure type
    3. Searches for similar past failures
    4. Suggests resolution steps
    5. Finds relevant MS Learn documentation

    Example:
        >>> analyzer = FailureAnalyzer()
        >>> result = ExecutionResult(success=False, error="QuotaExceeded", ...)
        >>> analysis = analyzer.analyze_failure(result)
        >>> print(analysis.suggested_fixes)
    """

    def __init__(self, history_file: Path | None = None, ms_learn_client=None):
        """Initialize failure analyzer.

        Args:
            history_file: Path to failure history JSON file
            ms_learn_client: MS Learn client for doc search (optional)
        """
        self.history_file = history_file or Path.home() / ".azlin" / "failure_history.json"
        self.ms_learn_client = ms_learn_client
        self._ensure_history_dir()

    def _ensure_history_dir(self) -> None:
        """Ensure history directory exists."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_file.exists():
            self.history_file.write_text("[]")
            self.history_file.chmod(0o600)

    def analyze_failure(self, result: ExecutionResult) -> FailureAnalysis:
        """Analyze failure and suggest resolutions.

        Args:
            result: Failed execution result

        Returns:
            FailureAnalysis with suggestions

        Example:
            >>> result = ExecutionResult(
            ...     success=False,
            ...     error="QuotaExceeded for Standard_D4s_v3",
            ...     failure_type=FailureType.QUOTA_EXCEEDED,
            ... )
            >>> analysis = analyzer.analyze_failure(result)
        """
        error_message = result.error or "Unknown error"

        # Extract resource type from error or metadata
        resource_type = self._extract_resource_type(error_message, result.metadata)

        # Create error signature
        error_sig = ErrorSignature.from_error(error_message, resource_type)

        # Find similar failures
        similar_failures = self.find_similar_failures(error_sig.signature_hash)

        # Generate suggestions based on failure type
        suggested_fixes = self.suggest_fix(result.failure_type or FailureType.UNKNOWN, error_message)

        # Generate runnable commands
        runnable_commands = self._generate_commands(result.failure_type or FailureType.UNKNOWN, error_message, resource_type)

        # Search MS Learn (if client available)
        doc_links: list[DocLink] = []
        if self.ms_learn_client and error_sig.error_code:
            doc_links = self.search_ms_learn(error_sig.error_code, resource_type)

        # Create analysis
        analysis = FailureAnalysis(
            failure_type=result.failure_type or FailureType.UNKNOWN,
            error_signature=error_sig,
            error_message=error_message,
            suggested_fixes=suggested_fixes,
            runnable_commands=runnable_commands,
            doc_links=doc_links,
            similar_failures=len(similar_failures),
        )

        # Save to history
        self._save_to_history(analysis)

        return analysis

    def find_similar_failures(self, error_signature: str) -> list[FailureAnalysis]:
        """Find similar past failures from history.

        Args:
            error_signature: Error signature hash

        Returns:
            List of similar failure analyses
        """
        history = self._load_history()
        similar = [
            entry
            for entry in history
            if entry.get("error_signature", {}).get("signature_hash") == error_signature
        ]
        return similar

    def suggest_fix(self, failure_type: FailureType, error_message: str) -> list[str]:
        """Suggest fixes based on failure type.

        Args:
            failure_type: Type of failure
            error_message: Error message text

        Returns:
            List of suggested fix descriptions
        """
        suggestions = []

        if failure_type == FailureType.QUOTA_EXCEEDED:
            suggestions.extend([
                "Request quota increase in Azure Portal under Subscriptions > Usage + quotas",
                "Choose a different VM size with available quota",
                "Try a different Azure region with more capacity",
                "Delete unused resources to free up quota",
            ])

        elif failure_type == FailureType.PERMISSION_DENIED:
            suggestions.extend([
                "Verify you have Contributor or Owner role on the subscription/resource group",
                "Check Azure RBAC permissions: az role assignment list --assignee <your-email>",
                "Ensure you're logged in: az account show",
                "Try re-authenticating: az login",
            ])

        elif failure_type == FailureType.RESOURCE_NOT_FOUND:
            suggestions.extend([
                "Verify the resource name and resource group are correct",
                "Check if the resource was deleted or moved",
                "Ensure you're in the correct subscription: az account set --subscription <name>",
            ])

        elif failure_type == FailureType.NETWORK_ERROR:
            suggestions.extend([
                "Check your internet connection",
                "Verify Azure service status: https://status.azure.com",
                "Try again after a few minutes (transient issue)",
                "Check if firewall/proxy is blocking Azure endpoints",
            ])

        elif failure_type == FailureType.TIMEOUT:
            suggestions.extend([
                "Retry the operation (may be transient)",
                "Check Azure service health for the region",
                "Try a different Azure region",
                "Reduce operation complexity or size",
            ])

        elif failure_type == FailureType.VALIDATION_ERROR:
            # Extract specific validation issues
            if "name" in error_message.lower():
                suggestions.append("Check resource naming rules (alphanumeric, hyphens, length limits)")
            if "location" in error_message.lower() or "region" in error_message.lower():
                suggestions.append("Verify the Azure region/location is valid and available")
            if "size" in error_message.lower() or "sku" in error_message.lower():
                suggestions.append("Verify the VM size/SKU is available in the selected region")

            suggestions.append("Review Azure naming conventions and resource requirements")

        elif failure_type == FailureType.DEPENDENCY_FAILED:
            suggestions.extend([
                "Check if dependent resources exist (VNet, subnet, NSG, etc.)",
                "Verify dependencies are in the same region/subscription",
                "Ensure dependency resources are in a healthy state",
            ])

        else:  # UNKNOWN
            suggestions.extend([
                "Review the full error message for specific details",
                "Check Azure service health and status",
                "Try running with --verbose for more details",
                "Search Azure documentation for the specific error code",
            ])

        return suggestions

    def search_ms_learn(self, error_code: str, resource_type: str | None) -> list[DocLink]:
        """Search MS Learn for relevant docs.

        Args:
            error_code: Error code to search for
            resource_type: Azure resource type

        Returns:
            List of relevant documentation links (top 3)
        """
        if not self.ms_learn_client:
            return []

        try:
            return self.ms_learn_client.search(error_code, resource_type, max_results=3)
        except Exception:
            logger.exception("Failed to search MS Learn")
            return []

    def _extract_resource_type(self, error_message: str, metadata: dict[str, Any] | None) -> str | None:
        """Extract Azure resource type from error or metadata.

        Args:
            error_message: Error message text
            metadata: Result metadata

        Returns:
            Resource type or None
        """
        # Try metadata first
        if metadata:
            if "resource_type" in metadata:
                return metadata["resource_type"]

        # Parse from error message
        resource_patterns = [
            r"Microsoft\.(\w+)/(\w+)",  # Microsoft.Compute/virtualMachines
            r"\b(virtualMachines?|storageAccounts?|networkInterfaces?|publicIPAddresses?)\b",
            r"\b(VM|VNet|NSG|NIC|Storage)\b",
        ]

        for pattern in resource_patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                return match.group(0)

        return None

    def _generate_commands(
        self,
        failure_type: FailureType,
        error_message: str,
        resource_type: str | None,
    ) -> list[str]:
        """Generate runnable commands for fixing the issue.

        Args:
            failure_type: Type of failure
            error_message: Error message
            resource_type: Resource type

        Returns:
            List of runnable commands
        """
        commands = []

        if failure_type == FailureType.QUOTA_EXCEEDED:
            commands.extend([
                "az vm list-usage --location eastus --output table",
                "az account show --query tenantId --output tsv",
            ])

        elif failure_type == FailureType.PERMISSION_DENIED:
            commands.extend([
                "az account show",
                "az ad signed-in-user show",
                "az role assignment list --assignee $(az ad signed-in-user show --query id -o tsv)",
            ])

        elif failure_type == FailureType.RESOURCE_NOT_FOUND:
            commands.extend([
                "az account list --output table",
                "az group list --output table",
            ])

        return commands

    def _load_history(self) -> list[dict[str, Any]]:
        """Load failure history from JSON file.

        Returns:
            List of failure analysis dictionaries
        """
        try:
            return json.loads(self.history_file.read_text())
        except Exception:
            logger.warning("Failed to load failure history")
            return []

    def _save_to_history(self, analysis: FailureAnalysis) -> None:
        """Save analysis to history file.

        Args:
            analysis: Failure analysis to save
        """
        try:
            history = self._load_history()

            # Add new analysis
            history.append(analysis.to_dict())

            # Keep last 100 entries
            if len(history) > 100:
                history = history[-100:]

            # Save
            self.history_file.write_text(json.dumps(history, indent=2))

        except Exception:
            logger.exception("Failed to save to failure history")
