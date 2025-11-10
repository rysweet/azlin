"""Request clarification for ambiguous natural language commands.

This module implements a two-phase approach to handling complex or ambiguous requests:
1. Clarify the user's intent by rewriting the request into clear, declarative steps
2. Get user confirmation before proceeding to command generation

This improves the success rate of complex requests by ensuring Claude has a clear
understanding before generating specific azlin commands.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import anthropic  # type: ignore[import-untyped]
import click


class RequestClarificationError(Exception):
    """Error during request clarification."""


@dataclass
class ClarificationResult:
    """Result of request clarification process.

    Attributes:
        needed: Whether clarification was needed
        original_request: The original user request
        clarified_request: The clarified request (None if clarification not needed)
        steps: List of clarified steps (None if clarification not needed)
        confidence: Confidence score (0.0-1.0) from initial analysis
        estimated_operations: Estimated number of Azure operations (None if not applicable)
        user_confirmed: Whether user confirmed the clarification (None if not asked)
    """

    needed: bool
    original_request: str
    clarified_request: str | None = None
    steps: list[str] | None = None
    confidence: float | None = None
    estimated_operations: int | None = None
    user_confirmed: bool | None = None


class RequestClarifier:
    """Clarifies ambiguous or complex natural language requests.

    This class uses Claude API to analyze user requests and rewrite them into
    clear, structured steps that can be more reliably converted into commands.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize request clarifier.

        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.

        Raises:
            ValueError: If API key is not provided and not in environment
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable or api_key parameter required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def should_clarify(
        self, request: str, confidence: float | None = None, commands_empty: bool = False
    ) -> bool:
        """Determine if a request needs clarification.

        Args:
            request: The user's natural language request
            confidence: Optional confidence score from initial parsing (0.0-1.0)
            commands_empty: Whether the initial parse produced no commands

        Returns:
            True if clarification is needed, False otherwise

        Example:
            >>> clarifier = RequestClarifier()
            >>> clarifier.should_clarify("create 23 blobs", confidence=0.3)
            True
            >>> clarifier.should_clarify("list my VMs", confidence=0.95)
            False
        """
        # Always clarify if initial parse produced no commands
        if commands_empty:
            return True

        # Clarify if confidence is low
        if confidence is not None and confidence < 0.7:
            return True

        # Quick heuristic check for complex requests
        request_lower = request.lower()

        # Check for multiple operations
        multi_op_keywords = ["and then", "after that", "followed by", "also", "then"]
        if any(keyword in request_lower for keyword in multi_op_keywords):
            return True

        # Check for numeric quantities suggesting bulk operations
        numbers = re.findall(r"\b(\d+)\b", request)
        if numbers and any(int(n) > 5 for n in numbers):
            return True

        # Check for complex Azure operations
        complex_keywords = ["blob", "container", "terraform", "pipeline", "deploy", "configure"]
        if any(keyword in request_lower for keyword in complex_keywords):
            # Only clarify complex keywords if they appear in potentially ambiguous contexts
            simple_patterns = [
                "list",
                "show",
                "get",
                "status",
                "info",
            ]
            if not any(pattern in request_lower for pattern in simple_patterns):
                return True

        return False

    def clarify(
        self, request: str, context: dict[str, Any] | None = None, auto_confirm: bool = False
    ) -> ClarificationResult:
        """Clarify a complex or ambiguous request.

        Args:
            request: The user's natural language request
            context: Optional context about current state (VMs, storage, etc.)
            auto_confirm: If True, skip user confirmation (for testing)

        Returns:
            ClarificationResult with clarification details

        Raises:
            RequestClarificationError: If clarification fails

        Example:
            >>> clarifier = RequestClarifier()
            >>> result = clarifier.clarify("create 23 storage blobs with data")
            >>> if result.user_confirmed:
            ...     print(f"Proceeding with {len(result.steps)} steps")
        """
        try:
            system_prompt = self._build_clarification_prompt(context)
            user_message = self._build_user_message(request)

            # Call Claude API
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract and parse response
            response_text = message.content[0].text  # type: ignore[attr-defined]  # TextBlock always has .text
            clarification_data = self._extract_json(response_text)

            # Validate response structure
            self._validate_clarification(clarification_data)

            # Display clarification to user
            if not auto_confirm:
                self._display_clarification(request, clarification_data)

            # Get user confirmation
            user_confirmed = auto_confirm or self._get_user_confirmation()

            # Build result
            result = ClarificationResult(
                needed=True,
                original_request=request,
                clarified_request=clarification_data.get("clarified_request"),
                steps=clarification_data.get("steps", []),
                confidence=clarification_data.get("confidence"),
                estimated_operations=clarification_data.get("estimated_operations"),
                user_confirmed=user_confirmed,
            )

            return result

        except anthropic.APIError as e:
            raise RequestClarificationError(f"Claude API error: {e}") from e
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise RequestClarificationError(f"Failed to parse clarification response: {e}") from e

    def _build_clarification_prompt(self, context: dict[str, Any] | None) -> str:
        """Build system prompt for clarification."""
        base_prompt = """You are an expert at understanding and clarifying Azure infrastructure requests.

Your task is to take potentially ambiguous natural language requests and rewrite them into
clear, step-by-step plans that specify exactly what Azure operations are needed.

Focus on:
- Breaking complex requests into discrete, ordered steps
- Making implicit assumptions explicit
- Identifying resource names, quantities, and configurations
- Estimating the number of Azure API operations needed
- Highlighting any ambiguities or decisions made

Output Format (JSON only, no explanation):
{
    "clarified_request": "Single paragraph summary of what will be done",
    "steps": [
        "Step 1: Create Azure Storage Account (if not exists)",
        "Step 2: Create 23 blob containers named 'container-01' through 'container-23'",
        "Step 3: For each container: Create and upload data.txt with content '42'"
    ],
    "confidence": 0.0-1.0,
    "estimated_operations": 25,
    "assumptions": [
        "Storage account will be created in current resource group",
        "Container names will follow pattern 'container-NN'"
    ],
    "clarifications_needed": [
        "Do you want the containers in an existing storage account or a new one?"
    ]
}

CRITICAL:
- Be specific about resource names, patterns, and quantities
- Make reasonable defaults for unspecified details
- List any assumptions you make
- Estimate Azure operations realistically
- If truly ambiguous, note what needs clarification"""

        if context:
            base_prompt += f"\n\nCurrent Context:\n{json.dumps(context, indent=2)}"

        return base_prompt

    def _build_user_message(self, request: str) -> str:
        """Build user message for Claude."""
        return f"Clarify this Azure request: {request}"

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """Extract JSON from Claude's response."""
        # Claude might wrap JSON in markdown code blocks
        text = response_text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]  # Remove ```json
        elif text.startswith("```"):
            text = text[3:]  # Remove ```

        if text.endswith("```"):
            text = text[:-3]  # Remove closing ```

        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
            raise

    def _validate_clarification(self, data: dict[str, Any]) -> None:
        """Validate clarification response structure."""
        required_fields = ["clarified_request", "steps", "confidence"]

        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(data["steps"], list):
            raise ValueError("steps must be a list")

        if not 0.0 <= data["confidence"] <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

    def _display_clarification(self, original_request: str, data: dict[str, Any]) -> None:
        """Display clarification to user with nice formatting."""
        # Use Unicode box drawing characters for clean display
        box_top = "━" * 80
        box_bottom = "━" * 80

        click.echo("\n" + click.style("[Clarification]", fg="cyan", bold=True))
        click.echo(box_top)

        # Original request
        click.echo(click.style("Your request:", fg="yellow", bold=True))
        click.echo(f'  "{original_request}"')
        click.echo()

        # Clarified interpretation
        click.echo(click.style("I understand this as:", fg="green", bold=True))
        for i, step in enumerate(data["steps"], 1):
            click.echo(f"  {i}. {step}")
        click.echo()

        # Estimated operations
        if "estimated_operations" in data and data["estimated_operations"]:
            click.echo(f"Estimated: ~{data['estimated_operations']} Azure operations")

        # Assumptions (if any)
        if "assumptions" in data and data["assumptions"]:
            click.echo()
            click.echo(click.style("Assumptions:", fg="blue"))
            for assumption in data["assumptions"]:
                click.echo(f"  • {assumption}")

        # Clarifications needed (if any)
        if "clarifications_needed" in data and data["clarifications_needed"]:
            click.echo()
            click.echo(click.style("Note:", fg="yellow"))
            for clarification in data["clarifications_needed"]:
                click.echo(f"  • {clarification}")

        click.echo(box_bottom)
        click.echo()

    def _get_user_confirmation(self) -> bool:
        """Get user confirmation for clarification.

        Returns:
            True if user confirms, False otherwise
        """
        return click.confirm("Does this match your intent?")
