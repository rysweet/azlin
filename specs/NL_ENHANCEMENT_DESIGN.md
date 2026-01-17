# Natural Language Enhancement Design Specification

**Issue**: #443
**Architect**: Claude (pirate mode)
**Philosophy Check**: SIMPLIFIED from requirements - removed unnecessary complexity

## Executive Summary

The requirements document proposes 5 major features. After architectural review, I'm recommending we **focus on 3 high-value features** and **eliminate 2** that add complexity without proportional benefit.

**KEEP (High Value)**:
1. Context-aware parsing (session state)
2. Multi-step workflow support
3. Improved error recovery

**ELIMINATE (Low Value/High Complexity)**:
4. ~~Natural language query~~ - Already handled by current intent parser
5. ~~Voice command support~~ - Experimental, low ROI, adds OpenAI dependency

## Philosophy Compliance Analysis

### What the Requirements Document Got WRONG

1. **Over-engineered module structure**: Proposed 5 new modules when 2-3 would suffice
2. **Unnecessary QueryHandler**: Current IntentParser already handles queries vs commands
3. **Premature voice support**: Experimental feature before core features proven
4. **Complex workflow rollback**: Not justified for current use cases
5. **Persistent sessions**: In-memory is sufficient to start

### Simplified Approach

Following **Occam's Razor** and **Trust in Emergence**:

- Start with simplest implementation that works
- Build on existing components (IntentParser, CommandExecutor)
- Add ONE focused module per feature
- Defer complexity until it's actually needed

## Problem Decomposition

### Feature 1: Context-Aware Parsing

**Problem**: Commands are stateless. Cannot say "start it" after "create vm called test".

**Core Need**: Remember last N entities created/referenced.

**Simple Solution**: Add a session context dict that tracks:
- Last N VMs mentioned
- Last resource group used
- Last region used

**Implementation**:
- Simple dict in memory
- Passed to IntentParser
- Pronoun resolution in system prompt
- ~100 lines of code

### Feature 2: Multi-Step Workflows

**Problem**: "Create 3 VMs and sync them" executes as one big command list, no structure.

**Core Need**: Group commands into steps, show progress, handle failures gracefully.

**Simple Solution**: Enhance CommandExecutor to:
- Detect command groups (consecutive commands on same resource)
- Show progress per group
- Continue or stop on failure (user choice)

**Implementation**:
- Enhance existing CommandExecutor
- Add progress callback
- ~150 lines of code

### Feature 3: Better Error Messages

**Problem**: Generic "command failed" messages don't help users fix issues.

**Core Need**: Parse Azure CLI errors and suggest fixes.

**Simple Solution**: Pattern matching on common Azure errors + fallback.

**Implementation**:
- Error pattern dict (error regex -> suggestion template)
- Simple string matching
- ~100 lines of code

## Recommended Architecture

### Module 1: SessionContext (NEW)

**Purpose**: Track recent entities for pronoun resolution.

**Public API** ("studs"):
```python
class SessionContext:
    """Simple session context for pronoun resolution."""

    def __init__(self, max_history: int = 10):
        """Initialize with max history size."""

    def add_command(self, request: str, entities: dict[str, list[str]]) -> None:
        """Record a command and its entities."""

    def resolve_pronoun(self, pronoun: str, entity_type: str) -> str | None:
        """Resolve 'it', 'that', 'those' to entity names."""

    def get_context(self) -> dict[str, Any]:
        """Get context dict for IntentParser."""
```

**Internal State**:
```python
{
    "history": [
        {"request": "create vm called test", "entities": {"vm": ["test"]}},
        ...
    ],
    "last_vm": "test",
    "last_resource_group": "my-rg",
    "last_region": "westus2"
}
```

**Location**: `src/azlin/agentic/session_context.py`

**Testing**:
- Unit tests for pronoun resolution
- Test context limit enforcement
- Test entity extraction

### Module 2: WorkflowExecutor (ENHANCE EXISTING)

**Purpose**: Execute commands with progress and better error handling.

**Changes to CommandExecutor**:
```python
class CommandExecutor:
    # Existing methods...

    def execute_workflow(
        self,
        commands: list[dict],
        progress_callback: Callable[[int, int, str], None] | None = None,
        stop_on_error: bool = True
    ) -> list[dict]:
        """Execute commands with progress reporting and error handling.

        Args:
            commands: List of command dicts
            progress_callback: Called with (current, total, description)
            stop_on_error: Whether to stop on first error

        Returns:
            List of result dicts with enhanced error messages
        """
```

**Internal Logic**:
- Group consecutive commands on same resource (simple heuristic)
- Show progress: "Step 1/3: Creating VM..."
- Enhanced error messages using ErrorAnalyzer

**Location**: `src/azlin/agentic/command_executor.py` (enhance existing)

**Testing**:
- Test progress callback invocation
- Test stop_on_error behavior
- Test error message enhancement

### Module 3: ErrorAnalyzer (NEW)

**Purpose**: Parse Azure CLI errors and suggest fixes.

**Public API**:
```python
class ErrorAnalyzer:
    """Analyze Azure CLI errors and suggest fixes."""

    def analyze(self, command: str, stderr: str) -> str:
        """Analyze error and return enhanced message with suggestions.

        Args:
            command: The command that failed
            stderr: Error output from command

        Returns:
            Enhanced error message with actionable suggestions
        """
```

**Internal Logic**:
```python
ERROR_PATTERNS = {
    r"ResourceGroupNotFound": "Resource group '{rg}' not found. Try: azlin config set-rg <name>",
    r"VMNotFound": "VM '{vm}' not found. List VMs with: azlin list",
    r"QuotaExceeded": "Quota exceeded. Try a different region or VM size.",
    r"AuthenticationFailed": "Authentication failed. Run: az login",
    # ... ~20 common patterns
}
```

**Location**: `src/azlin/agentic/error_analyzer.py`

**Testing**:
- Test each error pattern
- Test fallback for unknown errors
- Test suggestion template rendering

## CLI Integration

### Enhanced `azlin do` Flow

```python
def _do_impl(...):
    # 1. Load or create session context
    session = SessionContext.load_or_create()

    # 2. Add session context to parser context
    context = {
        "resource_group": rg,
        "current_vms": vms,
        **session.get_context()  # Add session history
    }

    # 3. Parse with context (existing IntentParser)
    intent = parser.parse(request, context=context)

    # 4. Execute with workflow support
    def show_progress(current, total, desc):
        click.echo(f"[{current}/{total}] {desc}")

    executor = CommandExecutor()
    results = executor.execute_workflow(
        intent["azlin_commands"],
        progress_callback=show_progress,
        stop_on_error=not yes  # Continue if --yes flag
    )

    # 5. Update session context
    entities = extract_entities(intent)  # Helper function
    session.add_command(request, entities)
    session.save()

    # Existing result display logic...
```

### Changes Required

1. **IntentParser system prompt**: Add pronoun resolution instructions
2. **CLI**: Add session management calls
3. **CommandExecutor**: Add `execute_workflow()` method
4. **Error handling**: Use ErrorAnalyzer for stderr

## Data Models

### SessionContext State

```python
@dataclass
class CommandHistoryEntry:
    """Single command in history."""
    request: str
    entities: dict[str, list[str]]  # entity_type -> [names]
    timestamp: datetime

# Session state (in-memory, optionally persisted)
{
    "session_id": "uuid",
    "history": list[CommandHistoryEntry],  # Max 10
    "last_entities": {
        "vm": "test-vm",
        "resource_group": "my-rg",
        "region": "westus2"
    },
    "created_at": "2025-12-01T10:00:00Z",
    "last_used": "2025-12-01T10:15:00Z"
}
```

## Implementation Plan

### Phase 1: Session Context (Day 1)

1. Implement SessionContext class
2. Add pronoun resolution logic
3. Update IntentParser system prompt
4. Write unit tests
5. Manual testing: "create vm test" then "start it"

**Exit Criteria**: Pronouns resolve correctly 95% of time

### Phase 2: Workflow Execution (Day 2)

1. Add execute_workflow() to CommandExecutor
2. Implement command grouping heuristic
3. Add progress callback support
4. Write integration tests

**Exit Criteria**: Multi-step commands show progress

### Phase 3: Error Analysis (Day 3)

1. Implement ErrorAnalyzer with pattern dict
2. Integrate with CommandExecutor
3. Test all error patterns
4. Add documentation for error suggestions

**Exit Criteria**: 70% of errors get actionable suggestions

### Phase 4: Integration & Testing (Day 4)

1. End-to-end testing with real Azure resources
2. Performance testing (<2s parse time)
3. Documentation updates
4. CLI help text updates

**Exit Criteria**: All tests pass, ready for PR

## Testing Strategy

### Unit Tests (60% of effort)

- SessionContext: Pronoun resolution, history management
- ErrorAnalyzer: All error patterns
- Helper functions: Entity extraction

### Integration Tests (30% of effort)

- IntentParser with session context
- CommandExecutor workflow execution
- Error analysis integration

### E2E Tests (10% of effort)

- Full "create then start" workflow
- Multi-step workflow with progress
- Error recovery scenarios

**Target Coverage**: >75%

## What We're NOT Doing (and Why)

### 1. Natural Language Query Support

**Reason**: Current IntentParser already handles queries. No separate QueryHandler needed.

**Example**: "what vms are running?" already works - parser generates `azlin list` command.

**If needed later**: Enhance IntentParser prompt, don't add new module.

### 2. Voice Command Support

**Reasons**:
- Adds OpenAI dependency (Whisper API)
- Experimental feature before core features proven
- Low ROI (how many users will actually use voice?)
- Adds audio handling complexity

**If needed later**: Create as separate `azlin voice` command, don't complicate `azlin do`.

### 3. Persistent Sessions

**Reason**: In-memory sessions sufficient for 90% of use cases.

**If needed later**: Add `session.save()` / `session.load()` methods. 20 lines of code.

### 4. Workflow Rollback

**Reason**: Azure resources don't easily rollback. Better to fail fast and let user fix manually.

**If needed later**: Add rollback strategies per command type. Not now.

### 5. Complex Workflow DAG

**Reason**: Current use cases don't need dependency graphs. Sequential execution sufficient.

**If needed later**: Enhance command grouping logic. Don't build DAG executor yet.

## Success Metrics

### Quantitative

1. **Context Resolution**: 95% pronoun resolution accuracy
2. **Workflow Success**: 80% of multi-step workflows complete successfully
3. **Error Messages**: 70% of errors get actionable suggestions
4. **Performance**: <2s parsing time (no regression)
5. **Test Coverage**: >75%
6. **Code Size**: <500 lines added (not 1000+)

### Qualitative

1. Users can naturally say "start it" after creating a VM
2. Progress is visible for multi-step operations
3. Error messages help users fix problems
4. No major refactoring of existing code
5. Philosophy compliance maintained

## Risk Mitigation

### Risk 1: Session State Complexity

**Mitigation**: Keep in-memory, simple dict. No database, no serialization initially.

### Risk 2: Pronoun Resolution Accuracy

**Mitigation**: Focus on simple cases (it, that). Don't try to solve complex anaphora.

### Risk 3: Backward Compatibility

**Mitigation**: Feature is additive. Existing commands work exactly as before.

### Risk 4: Over-Engineering Temptation

**Mitigation**: This design spec explicitly calls out what NOT to build.

## Open Questions (for Implementation)

1. **Session timeout**: How long to keep session? **Recommendation**: 1 hour idle timeout.
2. **Session storage**: Where to persist? **Recommendation**: `~/.azlin/session.json` if needed.
3. **Progress format**: Plain text or fancy? **Recommendation**: Plain text, no ANSI colors initially.
4. **Error pattern count**: How many patterns? **Recommendation**: Start with 10 most common.

## Conclusion

This design achieves the goals with **~350 lines of new code** instead of the proposed ~1000+.

Key simplifications:
- 3 features instead of 5
- 2 new modules instead of 5
- Enhance existing code rather than rewrite
- In-memory state instead of persistence
- Pattern matching instead of AI error analysis

The result will be **simpler, faster, and more maintainable** while delivering the core value to users.

**Next Steps**:
1. Write failing tests for SessionContext
2. Implement SessionContext
3. Enhance IntentParser prompt
4. Test context-aware parsing
5. Proceed to Phase 2

---

**Philosophy Compliance**: ✅ This design follows ruthless simplicity and brick philosophy.
