"""Fleet query parser for natural language fleet queries.

This module extends the IntentParser to handle fleet-specific natural language queries
like "which VMs are costing the most?" or "show idle VMs".
"""

import json
import os
from typing import Any

import anthropic  # type: ignore[import-untyped]


class FleetQueryError(Exception):
    """Error parsing or executing fleet query."""


class FleetQueryParser:
    """Parses natural language fleet queries into executable commands."""

    def __init__(self, api_key: str | None = None):
        """Initialize fleet query parser.

        Args:
            api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable or api_key parameter required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def parse_query(self, query: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Parse natural language query into fleet query plan.

        Args:
            query: Natural language query (e.g., "which VMs cost the most?")
            context: Optional context (current VMs, cost data, etc.)

        Returns:
            Structured query plan with commands to execute

        Example:
            >>> parser = FleetQueryParser()
            >>> result = parser.parse_query("which VMs are using the most disk?")
            >>> print(result)
            {
                "query_type": "resource_usage",
                "metric": "disk",
                "sort_order": "desc",
                "commands": [
                    {"vm": "all", "command": "df -h / | tail -1 | awk '{print $5}'"}
                ],
                "aggregation": "sort_by_usage",
                "confidence": 0.95
            }
        """
        system_prompt = self._build_system_prompt(context)
        user_message = f"Parse this fleet query: {query}"

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            response_text = message.content[0].text  # type: ignore[attr-defined]
            parsed_query = self._extract_json(response_text)

            # Validate response structure
            self._validate_query(parsed_query)

            return parsed_query

        except Exception as e:
            if e.__class__.__name__ == "APIError":
                raise FleetQueryError(f"Claude API error: {e}") from e
            if isinstance(e, json.JSONDecodeError | KeyError | ValueError):
                raise FleetQueryError(f"Failed to parse Claude response: {e}") from e
            raise

    def _build_system_prompt(self, context: dict[str, Any] | None) -> str:
        """Build system prompt for Claude."""
        base_prompt = """You are an expert at parsing natural language fleet queries for azlin.

Your task is to convert user questions about their VM fleet into structured query plans.

Common Query Types:
1. Cost Analysis: "which VMs cost the most?", "show expensive VMs"
2. Resource Usage: "VMs using >80% disk", "high CPU VMs"
3. Version Queries: "VMs with old Python", "show Node.js versions"
4. Idle Detection: "unused VMs", "VMs not accessed in 2 weeks"
5. Comparison: "differences between staging and prod"
6. Package Analysis: "which VMs have Docker installed?"

Available Fleet Commands:
- azlin list: List all VMs
- azlin cost --by-vm: Get per-VM cost breakdown
- azlin fleet run "command" --all: Execute command on all VMs
- azlin fleet run "command" --tag key=value: Execute on tagged VMs
- azlin status --vm name: Get VM status

Common Remote Commands:
- df -h: Disk usage
- free -h: Memory usage
- uptime: Load average
- python --version: Python version
- node --version: Node version
- docker --version: Docker version
- last -1: Last login time
- w: Currently logged users

Output Format (JSON only, no explanation):
{
    "query_type": "cost_analysis | resource_usage | version_check | idle_detection | comparison | package_check",
    "metric": "cost | disk | memory | cpu | login_time | version",
    "filter": {
        "threshold": "80%",
        "time_period": "2 weeks",
        "comparison_targets": ["staging", "prod"]
    },
    "commands": [
        {
            "description": "Get disk usage",
            "azlin_command": "azlin fleet run",
            "remote_command": "df -h / | tail -1 | awk '{print $5}'",
            "target": "all | tag:env=prod | pattern:web-*"
        }
    ],
    "aggregation": "sort_by_value | group_by_result | diff | top_n",
    "top_n": 5,
    "confidence": 0.0-1.0,
    "explanation": "Brief explanation of the query plan",
    "requires_cost_data": true,
    "requires_vm_metrics": false
}

CRITICAL:
- Generate specific remote commands that answer the question
- Use awk/grep/sed for parsing command output
- Set confidence < 0.7 if uncertain
- Include aggregation strategy (how to present results)
- Indicate if cost data or metrics are needed"""

        if context:
            base_prompt += f"\n\nCurrent Context:\n{json.dumps(context, indent=2)}"

        return base_prompt

    def _extract_json(self, response_text: str) -> dict[str, Any]:
        """Extract JSON from Claude's response."""
        text = response_text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

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

    def _validate_query(self, query: dict[str, Any]) -> None:
        """Validate parsed query structure."""
        required_fields = ["query_type", "commands", "aggregation", "confidence"]

        for field in required_fields:
            if field not in query:
                raise ValueError(f"Missing required field: {field}")

        # Validate confidence range
        confidence = query.get("confidence", 0.0)
        if not (0.0 <= confidence <= 1.0):
            raise ValueError(f"Confidence must be 0.0-1.0, got {confidence}")

        # Validate commands list
        if not isinstance(query["commands"], list) or len(query["commands"]) == 0:
            raise ValueError("Commands must be a non-empty list")


class ResultSynthesizer:
    """Synthesize and aggregate fleet query results."""

    def __init__(self, api_key: str | None = None):
        """Initialize result synthesizer."""
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def synthesize(
        self, query: str, query_plan: dict[str, Any], results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Synthesize results into human-readable answer with insights.

        Args:
            query: Original natural language query
            query_plan: Parsed query plan
            results: Raw execution results from fleet commands

        Returns:
            Synthesized answer with insights and recommendations
        """
        system_prompt = """You are analyzing fleet query results and providing insights.

Your task is to:
1. Aggregate and summarize the results
2. Identify patterns and anomalies
3. Provide actionable recommendations

Output Format (JSON only):
{
    "summary": "Brief answer to the user's question",
    "results": [
        {
            "vm_name": "vm-1",
            "value": "85%",
            "status": "warning | ok | critical"
        }
    ],
    "insights": [
        "3 VMs are using >80% disk space",
        "vm-db-01 hasn't been accessed in 3 weeks"
    ],
    "recommendations": [
        "Consider cleaning up /var/log on vm-web-01",
        "Delete or deallocate idle VMs to save costs"
    ],
    "total_analyzed": 10,
    "critical_count": 2,
    "warning_count": 3
}"""

        user_message = {
            "query": query,
            "query_plan": query_plan,
            "results": results,
        }

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": json.dumps(user_message)}],
            )

            response_text = message.content[0].text  # type: ignore[attr-defined]

            # Extract JSON from response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response_text[start:end])

            raise ValueError("No JSON found in response")

        except Exception as e:
            # Fallback: return basic synthesis
            return {
                "summary": f"Executed query on {len(results)} VMs",
                "results": results,
                "insights": [],
                "recommendations": [],
                "error": f"Synthesis error: {e}",
            }


__all__ = ["FleetQueryParser", "FleetQueryError", "ResultSynthesizer"]
