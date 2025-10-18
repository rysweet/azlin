#!/usr/bin/env python3
"""
Claude Code hook for stop events.
Checks lock flag and blocks stop if continuous work mode is enabled.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Clean import structure
sys.path.insert(0, str(Path(__file__).parent))
from hook_processor import HookProcessor


class StopHook(HookProcessor):
    """Hook processor for stop events with lock support."""

    def __init__(self):
        super().__init__("stop")
        self.lock_flag = self.project_root / ".claude" / "tools" / "amplihack" / ".lock_active"

    def display_decision_summary(self, session_id: str | None = None) -> str:
        """Display decision records summary at session end.

        Args:
            session_id: Optional session identifier to locate DECISIONS.md

        Returns:
            Formatted decision summary string for display
        """
        try:
            # Locate the DECISIONS.md file
            decisions_file = None

            if session_id:
                # Try session-specific log directory
                session_log_dir = self.project_root / ".claude" / "runtime" / "logs" / session_id
                decisions_file = session_log_dir / "DECISIONS.md"

            # If not found or no session_id, try to find most recent DECISIONS.md
            if not decisions_file or not decisions_file.exists():
                logs_dir = self.project_root / ".claude" / "runtime" / "logs"
                if logs_dir.exists():
                    # Find all DECISIONS.md files
                    decision_files = list(logs_dir.glob("*/DECISIONS.md"))
                    if decision_files:
                        # Get the most recently modified one
                        decisions_file = max(decision_files, key=lambda f: f.stat().st_mtime)

            # If still not found, exit gracefully
            if not decisions_file or not decisions_file.exists():
                return ""

            # Read and parse the decisions file
            try:
                with open(decisions_file, encoding="utf-8") as f:
                    content = f.read()
            except (OSError, PermissionError) as e:
                self.log(f"Cannot read decisions file {decisions_file}: {e}", "ERROR")
                return ""
            except UnicodeDecodeError as e:
                self.log(f"Invalid encoding in decisions file {decisions_file}: {e}", "ERROR")
                return ""

            # Count decisions (lines starting with "## Decision")
            decision_lines = [
                line for line in content.split("\n") if line.startswith("## Decision")
            ]
            decision_count = len(decision_lines)

            # If no decisions, exit gracefully
            if decision_count == 0:
                return ""

            # Get last 3 decisions for preview
            last_decisions = decision_lines[-3:] if len(decision_lines) >= 3 else decision_lines

            # Format the preview (remove "## Decision:" prefix for cleaner display)
            previews = []
            for decision in last_decisions:
                # Remove "## Decision:" prefix and clean up
                preview = decision.replace("## Decision:", "").strip()
                previews.append(preview)

            # Create file:// URL for clickable link
            file_url = f"file://{decisions_file.resolve()}"

            # Build summary as string (for return, not print)
            lines = [
                "\n",
                "═" * 70,
                "Decision Records Summary",
                "═" * 70,
                f"Location: {file_url}",
                f"Total Decisions: {decision_count}",
            ]

            if previews:
                lines.append("\nRecent Decisions:")
                for i, preview in enumerate(previews, 1):
                    # Truncate long decisions for preview
                    if len(preview) > 80:
                        preview = preview[:77] + "..."
                    lines.append(f"  {i}. {preview}")

            lines.append("═" * 70)
            lines.append("\n")

            return "\n".join(lines)

        except FileNotFoundError as e:
            self.log(f"Decisions file not found: {e}", "WARNING")
            return ""
        except PermissionError as e:
            self.log(f"Permission denied reading decisions file: {e}", "ERROR")
            return ""
        except Exception as e:
            # Catch-all for unexpected errors with more detail
            self.log(
                f"Unexpected error displaying decision summary: {type(e).__name__}: {e}", "ERROR"
            )
            return ""

    def extract_learnings(self, messages: list[dict]) -> list[dict]:
        """Extract learnings using the reflection module.

        Args:
            messages: List of conversation messages

        Returns:
            List of potential learnings with improvement suggestions
        """
        try:
            # Import reflection analysis directly
            from reflection import SessionReflector

            # Get patterns from reflection analysis
            reflector = SessionReflector()
            analysis = reflector.analyze_session(messages)

            # If reflection was skipped, fall back to simple extraction
            if analysis.get("skipped"):
                return self.extract_learnings_simple(messages)

            # Convert patterns to learnings format
            patterns = analysis.get("patterns", [])
            return [
                {
                    "type": pattern["type"],
                    "suggestion": pattern.get("suggestion", ""),
                    "priority": pattern.get("priority", "medium"),
                }
                for pattern in patterns
            ]

        except ImportError as e:
            self.log(f"Could not import reflection module: {e}", "WARNING")
            # Fall back to simple keyword extraction
            return self.extract_learnings_simple(messages)
        except Exception as e:
            self.log(f"Error in reflection analysis: {e}", "ERROR")
            return []

    def extract_learnings_simple(self, messages: list[dict]) -> list[dict]:
        """Simple fallback learning extraction.

        Args:
            messages: List of conversation messages

        Returns:
            List of simple keyword-based learnings
        """
        learnings = []
        keywords = ["discovered", "learned", "found that", "issue was", "solution was"]

        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str):
                for keyword in keywords:
                    if keyword.lower() in content.lower():
                        learnings.append({"keyword": keyword, "preview": content[:200]})
                        break
        return learnings

    def get_priority_emoji(self, priority: str) -> str:
        """Get emoji for priority level.

        Args:
            priority: Priority level (high, medium, low)

        Returns:
            Emoji string representing priority
        """
        PRIORITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        return PRIORITY_EMOJI.get(priority.lower(), "⚪")

    def extract_recommendations_from_patterns(
        self, patterns: list[dict], limit: int = 5
    ) -> list[dict]:
        """Extract top N recommendations from reflection patterns.

        Args:
            patterns: List of pattern dictionaries from reflection analysis
            limit: Maximum number of recommendations to return

        Returns:
            List of top recommendations sorted by priority
        """
        if not patterns:
            return []

        # Sort by priority (high > medium > low)
        priority_order = {"high": 3, "medium": 2, "low": 1}
        sorted_patterns = sorted(
            patterns,
            key=lambda p: priority_order.get(p.get("priority", "low").lower(), 0),
            reverse=True,
        )

        # Return top N
        return sorted_patterns[:limit]

    def format_recommendations_message(self, recommendations: list[dict]) -> str:
        """Format recommendations as readable message.

        Args:
            recommendations: List of recommendation dictionaries

        Returns:
            Formatted string for display
        """
        if not recommendations:
            return ""

        lines = ["\n" + "=" * 70, "AI-Detected Improvement Recommendations", "=" * 70]

        for i, rec in enumerate(recommendations, 1):
            priority = rec.get("priority", "medium")
            rec_type = rec.get("type", "unknown")
            suggestion = rec.get("suggestion", "No description available")

            emoji = self.get_priority_emoji(priority)
            lines.append(f"\n{i}. {emoji} [{priority.upper()}] {rec_type}")
            lines.append(f"   {suggestion}")

        lines.append("\n" + "=" * 70)

        return "\n".join(lines)

    def save_session_analysis(self, messages: list[dict]):
        """Save session analysis for later review.

        Args:
            messages: List of conversation messages
        """
        # Generate analysis filename
        analysis_file = (
            self.analysis_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        # Extract stats
        stats = {
            "timestamp": datetime.now().isoformat(),
            "message_count": len(messages),
            "tool_uses": 0,
            "errors": 0,
        }

        # Count tool uses and errors
        for msg in messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if "tool_use" in str(content):
                    stats["tool_uses"] += 1
                if "error" in str(content).lower():
                    stats["errors"] += 1

        # Extract learnings
        learnings = self.extract_learnings(messages)
        if learnings:
            stats["potential_learnings"] = len(learnings)

        # Save analysis
        analysis = {"stats": stats, "learnings": learnings}

        with open(analysis_file, "w") as f:
            json.dump(analysis, f, indent=2)

        self.log(f"Saved session analysis to {analysis_file.name}")

        # Also save metrics
        self.save_metric("message_count", stats["message_count"])
        self.save_metric("tool_uses", stats["tool_uses"])
        self.save_metric("errors", stats["errors"])
        if learnings:
            self.save_metric("potential_learnings", len(learnings))

    def read_transcript(self, transcript_path: str) -> list[dict]:
        """Read and parse transcript file.

        Args:
            transcript_path: Path to transcript file

        Returns:
            List of messages from transcript
        """
        try:
            if not transcript_path:
                self.log("No transcript path provided", "WARNING")
                return []

            transcript_file = Path(transcript_path)
            if not transcript_file.exists():
                self.log(f"Transcript file not found: {transcript_path}", "WARNING")
                return []

            # Allow reading from Claude Code directories and temp directories
            # These are trusted locations where Claude Code stores transcripts
            import tempfile
            allowed_external_paths = [
                Path.home() / ".claude",  # Claude Code's data directory
                Path(tempfile.gettempdir()),  # Temporary files
                Path("/var/folders"),  # macOS temp directory
                Path("/private/var/folders"),  # macOS temp directory (resolved)
            ]

            # Check if the transcript is in an allowed external location
            is_allowed_external = False
            for allowed_path in allowed_external_paths:
                try:
                    transcript_file.resolve().relative_to(allowed_path.resolve())
                    is_allowed_external = True
                    break
                except (ValueError, RuntimeError):
                    continue

            # If not in allowed external location, validate it's within project
            if not is_allowed_external:
                try:
                    self.validate_path_containment(transcript_file)
                except ValueError as e:
                    self.log(f"Transcript path not in allowed locations: {e}", "WARNING")
                # Don't completely fail - just log the issue

            self.log(f"Reading transcript from: {transcript_path}")

            with open(transcript_file, encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                self.log("Transcript file is empty", "WARNING")
                return []

            # Try parsing as JSON first
            try:
                data = json.loads(content)

                # Handle different transcript formats
                if isinstance(data, list):
                    # Direct list of messages
                    self.log(f"Parsed JSON array with {len(data)} items")
                    return data
                if isinstance(data, dict):
                    # Wrapped format
                    if "messages" in data:
                        messages = data["messages"]
                        self.log(f"Found 'messages' key with {len(messages)} messages")
                        return messages
                    if "conversation" in data:
                        conversation = data["conversation"]
                        self.log(f"Found 'conversation' key with {len(conversation)} messages")
                        return conversation
                    self.log(f"Unexpected transcript format: {list(data.keys())}", "WARNING")
                    return []
                self.log(f"Unexpected transcript data type: {type(data)}", "WARNING")
                return []

            except json.JSONDecodeError:
                # Try parsing as JSONL (one JSON object per line) - Claude Code's format
                self.log("Parsing as JSONL format (Claude Code transcript)")
                messages = []
                for line_num, line in enumerate(content.split("\n"), 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)

                        # Claude Code JSONL format has nested message structure
                        if isinstance(entry, dict):
                            # Extract the actual message from Claude Code format
                            if "message" in entry and isinstance(entry["message"], dict):
                                # This is Claude Code format - extract the nested message
                                message = entry["message"]
                                if "role" in message:
                                    messages.append(message)
                            elif "role" in entry:
                                # Direct message format
                                messages.append(entry)
                            elif "type" in entry:
                                # Some entries are metadata - skip them
                                if entry["type"] in ["user", "assistant"]:
                                    # Try to extract message if it exists
                                    if "message" in entry:
                                        messages.append(entry["message"])
                                else:
                                    self.log(
                                        f"Skipping metadata entry with type: {entry.get('type')}",
                                        "DEBUG",
                                    )
                    except json.JSONDecodeError as e:
                        # Log but continue - some lines might be metadata
                        self.log(f"Skipping non-JSON line {line_num}: {str(e)[:100]}", "DEBUG")
                        continue

                self.log(f"Parsed JSONL with {len(messages)} messages")
                return messages

        except Exception as e:
            self.log(f"Error reading transcript: {e}", "ERROR")
            return []

    def find_session_transcript(self, session_id: str) -> Path | None:
        """Find transcript file for a given session ID.

        Args:
            session_id: Session identifier

        Returns:
            Path to transcript file if found
        """
        if not session_id:
            return None

        # Possible transcript locations and naming patterns
        import tempfile
        possible_locations = [
            # Current runtime structure
            self.project_root / ".claude" / "runtime" / "transcripts",
            self.project_root / ".claude" / "runtime" / "sessions",
            self.project_root / ".claude" / "runtime" / "logs" / session_id,
            # Alternative naming patterns
            self.project_root / "transcripts",
            self.project_root / "sessions",
            # Temporary locations
            Path(tempfile.gettempdir()) / "claude" / "transcripts",
        ]

        # Possible file patterns
        patterns = [
            f"{session_id}.json",
            f"{session_id}_transcript.json",
            f"transcript_{session_id}.json",
            f"session_{session_id}.json",
            "transcript.json",
            "messages.json",
            "conversation.json",
        ]

        for location in possible_locations:
            if not location.exists():
                continue

            for pattern in patterns:
                transcript_file = location / pattern
                if transcript_file.exists():
                    self.log(f"Found transcript file: {transcript_file}")
                    return transcript_file

        return None

    def get_session_messages(self, input_data: dict[str, Any]) -> list[dict]:
        """Get session messages using multiple strategies.

        Args:
            input_data: Input from Claude Code

        Returns:
            List of messages from the session
        """
        # Strategy 1: Try transcript_path in input_data
        transcript_path = input_data.get("transcript_path")
        if transcript_path:
            messages = self.read_transcript(transcript_path)
            if messages:
                return messages

        # Strategy 2: Try to find transcript by session_id
        session_id = input_data.get("session_id")
        if session_id:
            transcript_file = self.find_session_transcript(session_id)
            if transcript_file:
                messages = self.read_transcript(str(transcript_file))
                if messages:
                    return messages

        # Strategy 3: Check if messages are directly in input_data
        if "messages" in input_data:
            return input_data["messages"]

        return []

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check lock flag and block stop if active.

        Args:
            input_data: Input from Claude Code

        Returns:
            Dict with decision to block or allow stop
        """
        try:
            lock_exists = self.lock_flag.exists()
        except (PermissionError, OSError) as e:
            self.log(f"Cannot access lock file: {e}", "WARNING")
            # Fail-safe: allow stop if we can't read lock
            return {"decision": "allow", "continue": False}

        if lock_exists:
            # Lock is active - block stop and continue working
            self.log("Lock is active - blocking stop to continue working")
            self.save_metric("lock_blocks", 1)
            return {
                "decision": "block",
                "reason": "we must keep pursuing the user's objective and must not stop the turn - look for any additional TODOs, next steps, or unfinished work and pursue it diligently in as many parallel tasks as you can",
                "continue": True,
            }

        # Not locked - allow stop
        self.log("No lock active - allowing stop")
        return {"decision": "allow", "continue": False}


def main():
    """Entry point for the stop hook."""
    hook = StopHook()
    hook.run()


if __name__ == "__main__":
    main()
