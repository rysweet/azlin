# Amplihack Agents

<!-- AMPLIHACK_CONTEXT_START -->

## 🎯 USER PREFERENCES (MANDATORY - MUST FOLLOW)

## Amplihack Copilot Workflow Rules

For any DEV, INVESTIGATE, or HYBRID request, invoke `Skill(skill="dev-orchestrator")` immediately.

After the skill is activated, the next tool call must execute the `smart-orchestrator` recipe via `run_recipe_by_name("smart-orchestrator")`.

Do not follow the workflow manually and do not fall back to legacy `ultrathink` behavior.

<!-- AMPLIHACK_CONTEXT_END -->
