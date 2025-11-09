"""Intent parser for natural language azlin commands.

This module uses Claude API to parse natural language into structured azlin commands.
"""

import json
import os
from typing import Any

import anthropic  # type: ignore[import-untyped]

from azlin.agentic.types import ExecutionHistoryEvent, Intent


class IntentParseError(Exception):
    """Error parsing natural language intent."""


class IntentParser:
    """Parses natural language into structured azlin command intents."""

    def __init__(self, api_key: str | None = None):
        """Initialize intent parser.

        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable or api_key parameter required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def parse(self, natural_language: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Parse natural language into structured intent.

        Args:
            natural_language: User's natural language request
            context: Optional context about current state (VMs, storage, etc.)

        Returns:
            Structured intent with command details

        Example:
            >>> parser = IntentParser()
            >>> result = parser.parse("create a new vm called Sam")
            >>> print(result)
            {
                "intent": "provision_vm",
                "parameters": {"vm_name": "Sam"},
                "confidence": 0.95,
                "azlin_commands": [
                    {"command": "azlin new", "args": ["--name", "Sam"]}
                ]
            }
        """
        system_prompt = self._build_system_prompt(context)
        user_message = self._build_user_message(natural_language)

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract JSON response from Claude
            response_text = message.content[0].text  # type: ignore[attr-defined]  # TextBlock always has .text
            parsed_intent = self._extract_json(response_text)

            # Validate response structure
            self._validate_intent(parsed_intent)

            return parsed_intent

        except Exception as e:
            # Check if it's an anthropic API error by class name
            if e.__class__.__name__ == "APIError":
                raise IntentParseError(f"Claude API error: {e}") from e
            # Handle JSON and validation errors
            if isinstance(e, json.JSONDecodeError | KeyError | ValueError):
                raise IntentParseError(f"Failed to parse Claude response: {e}") from e
            # Re-raise unexpected exceptions
            raise

    def _build_system_prompt(self, context: dict[str, Any] | None) -> str:
        """Build system prompt for Claude."""
        base_prompt = """You are an expert at parsing natural language commands for azlin, an Azure VM management CLI.

Your task is to convert user requests into structured azlin command specifications.

Available azlin commands:
- azlin new: Provision new VM (--name, --repo, --vm-size, --region, --nfs-storage)
- azlin list: List VMs
- azlin status: Show VM status
- azlin sync: Sync files to VM (--vm-name)
- azlin cp: Copy files (source destination)
- azlin start: Start VM (vm_name)
- azlin stop: Stop VM (vm_name)
- azlin kill: Delete VM (vm_name)
- azlin cost: Show cost estimates (optional: --by-vm for breakdown). DO NOT use --from/--to parameters
- azlin storage create: Create NFS storage (name --size)
- azlin storage list: List storage accounts
- azlin storage status: Show storage status (name)
- azlin update: Update VM tools (vm_name)

Output Format (JSON only, no explanation):
{
    "intent": "provision_vm | list_vms | sync_vms | cost_report | ...",
    "parameters": {
        "vm_name": "string (if applicable)",
        "count": "number (if multiple VMs)",
        "repo_url": "string (if applicable)",
        "storage_name": "string (if applicable)",
        ...
    },
    "confidence": 0.0-1.0,
    "azlin_commands": [
        {
            "command": "azlin new",
            "args": ["--name", "Sam", "--repo", "https://..."]
        }
    ],
    "explanation": "Brief explanation of the plan"
}

CRITICAL:
- Always include exact azlin command syntax in "azlin_commands"
- Use --name for VM names, never positional arguments
- If request is ambiguous, include multiple possible interpretations
- Set confidence < 0.7 if uncertain"""

        if context:
            base_prompt += f"\n\nCurrent Context:\n{json.dumps(context, indent=2)}"

        return base_prompt

    def _build_user_message(self, natural_language: str) -> str:
        """Build user message for Claude."""
        return f"Parse this request: {natural_language}"

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

    def _validate_intent(self, intent: dict[str, Any]) -> None:
        """Validate parsed intent structure.

        This method validates the raw dict has required fields before
        creating the Intent dataclass. The Intent.__post_init__ will
        perform detailed validation of types and structure.
        """
        required_fields = ["intent", "parameters", "confidence", "azlin_commands"]

        for field in required_fields:
            if field not in intent:
                raise ValueError(f"Missing required field: {field}")

        # Create Intent object to leverage its validation
        # The Intent.__post_init__ will validate:
        # - confidence range (0.0-1.0)
        # - parameters is dict
        # - azlin_commands is list of dicts with 'command' and 'args'
        Intent(
            intent=intent["intent"],
            parameters=intent["parameters"],
            confidence=intent["confidence"],
            azlin_commands=intent["azlin_commands"],
            explanation=intent.get("explanation"),
        )


class CommandPlanner:
    """Plans multi-step execution for complex intents."""

    def __init__(self, api_key: str | None = None):
        """Initialize command planner."""
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def plan(
        self, intent: dict[str, Any], execution_results: list[ExecutionHistoryEvent]
    ) -> dict[str, Any]:
        """Create or refine execution plan based on results.

        This enables multi-turn execution where the agent can adapt based on
        intermediate results.

        Args:
            intent: Original parsed intent
            execution_results: Results from previous command executions

        Returns:
            Updated plan with next steps
        """
        system_prompt = """You are planning azlin command execution.

Given the original intent and results so far, determine the next steps.

Output JSON only:
{
    "status": "in_progress | complete | failed",
    "next_commands": [
        {"command": "azlin ...", "args": [...]}
    ],
    "reasoning": "Why these next steps"
}"""

        user_message = {
            "intent": intent,
            "results": execution_results,
        }

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps(user_message)}],
            )

            response_text = message.content[0].text  # type: ignore[attr-defined]  # TextBlock always has .text
            # Extract JSON from response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response_text[start:end])

            raise ValueError("No JSON found in response")

        except (anthropic.APIError, json.JSONDecodeError, ValueError) as e:
            # Fallback: assume complete if we hit an error
            return {
                "status": "failed",
                "next_commands": [],
                "reasoning": f"Planning error: {e}",
            }
