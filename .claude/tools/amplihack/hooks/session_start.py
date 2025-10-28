#!/usr/bin/env python3
"""
Claude Code hook for session start.
Uses unified HookProcessor for common functionality.
"""

# Import the base processor
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Clean import structure
sys.path.insert(0, str(Path(__file__).parent))
from hook_processor import HookProcessor

# Clean imports through package structure
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from amplihack.utils.paths import FrameworkPathResolver
    from context_preservation import ContextPreserver
    from paths import get_project_root
except ImportError:
    # Fallback imports for standalone execution
    get_project_root = None
    ContextPreserver = None
    FrameworkPathResolver = None


class SessionStartHook(HookProcessor):
    """Hook processor for session start events."""

    def __init__(self):
        super().__init__("session_start")

    def process(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process session start event.

        Args:
            input_data: Input from Claude Code

        Returns:
            Additional context to add to the session
        """
        # Extract prompt
        prompt = input_data.get("prompt", "")
        self.log(f"Prompt length: {len(prompt)}")

        # Save metric
        self.save_metric("prompt_length", len(prompt))

        # Capture original request for substantial prompts
        original_request_context = ""
        original_request_captured = False

        # Simple check for substantial requests
        substantial_keywords = [
            "implement",
            "create",
            "build",
            "add",
            "fix",
            "update",
            "all",
            "every",
            "each",
            "complete",
            "comprehensive",
        ]
        is_substantial = len(prompt) > 20 or any(
            word in prompt.lower() for word in substantial_keywords
        )

        if ContextPreserver and is_substantial:
            try:
                # Create context preserver with current session ID
                session_id = self.get_session_id()
                preserver = ContextPreserver(session_id)

                # Extract and save original request
                original_request = preserver.extract_original_request(prompt)

                # Simple verification and context formatting
                session_dir = self.project_root / ".claude" / "runtime" / "logs" / session_id
                original_request_captured = (session_dir / "ORIGINAL_REQUEST.md").exists()

                if original_request_captured:
                    self.log(
                        f"✅ Original request captured: {original_request.get('target', 'Unknown')}"
                    )
                    original_request_context = preserver.format_agent_context(original_request)
                else:
                    self.log("⚠️ Original request extraction failed", "WARNING")

                self.save_metric("original_request_captured", original_request_captured)

            except Exception as e:
                self.log(f"Failed to capture original request: {e}", "ERROR")
                self.save_metric("original_request_captured", False)

        # UVX staging if available
        try:
            from amplihack.utils.uvx_staging import is_uvx_deployment, stage_uvx_framework

            if is_uvx_deployment():
                staged = stage_uvx_framework()
                self.save_metric("uvx_staging_success", staged)
        except ImportError:
            pass

        # Build context if needed
        context_parts = []
        preference_enforcement = []

        # Add project context
        context_parts.append("## Project Context")
        context_parts.append("This is the Microsoft Hackathon 2025 Agentic Coding project.")
        context_parts.append("Focus on building AI-powered development tools.")

        # Check for recent discoveries
        discoveries_file = self.project_root / ".claude" / "context" / "DISCOVERIES.md"
        if discoveries_file.exists():
            context_parts.append("\n## Recent Learnings")
            context_parts.append("Check .claude/context/DISCOVERIES.md for recent insights.")

        # Simplified preference file resolution
        preferences_file = (
            FrameworkPathResolver.resolve_preferences_file()
            if FrameworkPathResolver
            else self.project_root / ".claude" / "context" / "USER_PREFERENCES.md"
        )

        if preferences_file and preferences_file.exists():
            try:
                with open(preferences_file) as f:
                    full_prefs_content = f.read()
                self.log(f"Successfully read preferences from: {preferences_file}")

                # Inject FULL preferences content with MANDATORY enforcement
                context_parts.append("\n## 🎯 USER PREFERENCES (MANDATORY - MUST FOLLOW)")
                context_parts.append("\nThe following preferences are REQUIRED and CANNOT be ignored:\n")
                context_parts.append(full_prefs_content)

                self.log("Injected full USER_PREFERENCES.md content into session")

            except Exception as e:
                self.log(f"Could not read preferences: {e}", "WARNING")
                # Fail silently - don't break session start

        # Add workflow information at startup with UVX support
        context_parts.append("\n## 📝 Default Workflow")
        context_parts.append("The 13-step workflow is automatically followed by `/ultrathink`")

        # Use FrameworkPathResolver for workflow path
        workflow_file = None
        if FrameworkPathResolver:
            workflow_file = FrameworkPathResolver.resolve_workflow_file()

        if workflow_file:
            context_parts.append(f"• To view the workflow: Read {workflow_file}")
            context_parts.append("• To customize: Edit the workflow file directly")
        else:
            context_parts.append(
                "• To view the workflow: Use FrameworkPathResolver.resolve_workflow_file() (UVX-compatible)"
            )
            context_parts.append("• To customize: Edit the workflow file directly")
        context_parts.append(
            "• Steps include: Requirements → Issue → Branch → Design → Implement → Review → Merge"
        )

        # Add verbosity instructions
        context_parts.append("\n## 🎤 Verbosity Mode")
        context_parts.append("• Current setting: balanced")
        context_parts.append(
            "• To enable verbose: Use TodoWrite tool frequently and provide detailed explanations"
        )
        context_parts.append("• Claude will adapt to your verbosity preference in responses")

        # Build response
        output = {}
        if context_parts:
            # Create comprehensive startup context
            full_context = "\n".join(context_parts)

            # Build a visible startup message (even though Claude Code may not display it)
            startup_msg_parts = ["🚀 AmplifyHack Session Initialized", "━" * 40]

            # Add preference summary if any exist
            if len([p for p in context_parts if "**" in p and ":" in p]) > 0:
                startup_msg_parts.append("🎯 Active preferences loaded and enforced")

            startup_msg_parts.extend(
                [
                    "",
                    "📝 Workflow: Use `/ultrathink` for the 13-step process",
                    "⚙️  Customize: Edit the workflow file (use FrameworkPathResolver for UVX compatibility)",
                    "🎯 Preferences: Loaded from USER_PREFERENCES.md",
                    "",
                    "Type `/help` for available commands",
                ]
            )

            startup_message = "\n".join(startup_msg_parts)

            # CRITICAL: Inject original request context at top priority
            if original_request_context:
                full_context = original_request_context + "\n\n" + full_context

            # Use correct SessionStart hook protocol format
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": full_context,
                }
            }
            self.log(
                f"Session initialized - Original request: {'✅' if original_request_captured else '❌'}"
            )
            self.log(f"Injected {len(full_context)} characters of context")

        return output


def main():
    """Entry point for the session start hook."""
    hook = SessionStartHook()
    hook.run()


if __name__ == "__main__":
    main()
