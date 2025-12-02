# Natural Language Enhancement Requirements

**Issue**: #443
**Workstream**: WS9 - Natural Language Enhancements
**Branch**: feat/issue-443-nl-enhance

## Problem Statement

The current `azlin do` and `azlin doit` commands provide basic natural language command execution, but lack context awareness, multi-step workflow support, and advanced error recovery capabilities that would make them truly conversational and intelligent.

## Current Implementation Analysis

### Existing Components

1. **IntentParser** (`src/azlin/agentic/intent_parser.py`)
   - Parses natural language requests using Claude AI (Sonnet 4.5)
   - Returns structured intent with azlin commands
   - Context-aware (can receive VM list, resource group info)
   - Stateless - no memory of previous interactions

2. **RequestClarifier** (`src/azlin/agentic/request_clarifier.py`)
   - Handles ambiguous requests
   - Asks clarifying questions
   - Single-turn clarification only

3. **CommandExecutor** (`src/azlin/agentic/command_executor.py`)
   - Executes azlin commands sequentially
   - Stops on first failure
   - No retry logic

4. **ResultValidator**
   - Validates execution results
   - Basic success/failure reporting

5. **CLI Entry Points**
   - `azlin do <request>` - Direct NL command execution
   - `azdoit <objective>` - Delegates to amplihack auto mode

### Current Limitations

1. **No Context Awareness**
   - Each command is independent
   - Cannot reference previous commands ("start it", "the vm I just created")
   - No session state management

2. **Limited Multi-Step Support**
   - Can generate multiple commands but executes sequentially
   - No workflow management
   - No conditional execution based on results

3. **Basic Error Recovery**
   - Stops on first error
   - Generic error messages
   - No intelligent retry or alternative suggestions

4. **Query Limitations**
   - Cannot answer questions about state ("what vms are running?")
   - All requests must result in commands

5. **No Voice Support**
   - Text-only interface

## Required Enhancements

### 1. Context-Aware Parsing (Priority: HIGH)

**Goal**: Remember recent commands and understand pronouns/references.

**Requirements**:
- Session state management (in-memory, persistent optional)
- Track last N commands (N=10 default, configurable)
- Track referenced entities (VM names, resource groups, regions)
- Resolve pronouns: "it", "that vm", "those", "the one I just created"
- Maintain context across command invocations within session

**Success Criteria**:
- Can execute: `azlin do "create vm called test-vm"` followed by `azlin do "start it"`
- 95% accuracy on pronoun resolution
- Context preserved for 10 commands or 1 hour (whichever comes first)

### 2. Multi-Step Workflow Support (Priority: HIGH)

**Goal**: Execute complex workflows from single command.

**Requirements**:
- Parse complex requests into workflow steps
- Execute steps with dependencies (sequential or parallel where possible)
- Handle conditional execution ("if VM creation succeeds, then sync files")
- Progress reporting for long-running workflows
- Rollback support on critical failures

**Success Criteria**:
- Can execute: `azlin do "create 3 vms and sync my code to all of them"`
- 80% success rate on multi-step workflows
- Clear progress indication for each step

### 3. Improved Error Recovery (Priority: MEDIUM)

**Goal**: Better suggestions when commands fail.

**Requirements**:
- Analyze error messages and suggest fixes
- Offer alternative approaches when primary fails
- Context-aware error messages (reference what user was trying to do)
- Retry logic with exponential backoff for transient errors
- Suggest related documentation links

**Success Criteria**:
- 70% of errors result in actionable suggestions
- <5s error analysis time
- Suggestions include specific commands to try

### 4. Natural Language Query (Priority: MEDIUM)

**Goal**: Answer questions about VM status and metrics conversationally.

**Requirements**:
- Support query intents (not just commands)
- Fetch current state and present in natural language
- Handle comparisons ("which vm is using most memory?")
- Support aggregations ("total cost this month")
- Format responses appropriately (tables, lists, or prose)

**Success Criteria**:
- Can answer: "what vms are running?", "show me costs by vm", "which vm has most disk"
- Response time <3s for simple queries
- 90% accuracy on query intent recognition

### 5. Voice Command Support (Priority: LOW, Experimental)

**Goal**: Accept voice input via Whisper API.

**Requirements**:
- Integrate OpenAI Whisper API for transcription
- Accept audio file input
- Optional: Real-time microphone input
- Graceful fallback to text if transcription fails
- Clear indication when voice mode is active

**Success Criteria**:
- Top 20 operations work via voice
- <5s transcription time
- 85% accuracy on technical terms (VM names, commands)

## Technical Approach

### Architecture Principles

1. **Modular Design** (Brick Philosophy)
   - Each enhancement is a self-contained module
   - Clear interfaces between components
   - Regeneratable from specifications

2. **Backward Compatibility**
   - Existing `azlin do` behavior preserved
   - New features opt-in via flags or detected automatically

3. **Ruthless Simplicity**
   - Start with minimal working implementation
   - Add complexity only when justified
   - Avoid over-engineering

### Proposed Module Structure

```
src/azlin/agentic/
├── intent_parser.py          # [ENHANCE] Add context parameter
├── request_clarifier.py      # [ENHANCE] Multi-turn support
├── command_executor.py       # [ENHANCE] Workflow and retry logic
├── result_validator.py       # [KEEP] Current implementation
├── session_manager.py        # [NEW] Session state management
├── context_resolver.py       # [NEW] Pronoun and reference resolution
├── workflow_planner.py       # [NEW] Multi-step workflow planning
├── error_analyzer.py         # [NEW] Intelligent error analysis
├── query_handler.py          # [NEW] Natural language query support
└── voice/                    # [NEW] Voice command support
    ├── __init__.py
    ├── transcriber.py        # Whisper API integration
    └── audio_handler.py      # Audio file handling
```

### Integration Points

1. **CLI Layer** (`src/azlin/cli.py::_do_impl`)
   - Add session management
   - Detect query vs command intent
   - Handle voice input flag

2. **IntentParser**
   - Accept session context
   - Use ContextResolver for pronoun resolution

3. **CommandExecutor**
   - Use WorkflowPlanner for multi-step execution
   - Use ErrorAnalyzer for failure recovery

### Data Models

```python
@dataclass
class SessionState:
    """Session state for context-aware parsing."""
    session_id: str
    commands: list[ExecutedCommand]  # Last N commands
    entities: dict[str, str]  # name -> type mapping
    created_at: datetime
    last_used: datetime

@dataclass
class ExecutedCommand:
    """Record of executed command."""
    request: str  # Original NL request
    intent: dict  # Parsed intent
    commands: list[dict]  # Azlin commands executed
    results: list[dict]  # Execution results
    timestamp: datetime

@dataclass
class WorkflowStep:
    """Single step in multi-step workflow."""
    step_id: str
    description: str
    commands: list[dict]
    dependencies: list[str]  # Step IDs that must complete first
    on_failure: str  # "stop" | "continue" | "rollback"
```

### Testing Strategy

1. **Unit Tests** (60%)
   - SessionManager: Context tracking and resolution
   - WorkflowPlanner: Step dependency analysis
   - ErrorAnalyzer: Suggestion generation
   - Voice transcriber: Whisper API integration

2. **Integration Tests** (30%)
   - End-to-end context resolution
   - Multi-step workflow execution
   - Error recovery flows

3. **End-to-End Tests** (10%)
   - Real azlin commands with context
   - Voice-to-execution pipeline
   - Complex workflow scenarios

## Implementation Phases

### Phase 1: Foundation (Session Management)
1. Implement SessionManager
2. Implement ContextResolver
3. Integrate with IntentParser
4. Tests: Context tracking and pronoun resolution

### Phase 2: Workflows
1. Implement WorkflowPlanner
2. Enhance CommandExecutor with workflow support
3. Tests: Multi-step execution

### Phase 3: Error Recovery
1. Implement ErrorAnalyzer
2. Integrate with CommandExecutor
3. Tests: Error suggestion accuracy

### Phase 4: Query Support
1. Implement QueryHandler
2. Enhance CLI to detect query intent
3. Tests: Query accuracy and response format

### Phase 5: Voice (Experimental)
1. Implement Whisper transcriber
2. Add voice input flag to CLI
3. Tests: Transcription accuracy

## Success Metrics

1. **Context Awareness**: 95% pronoun resolution accuracy
2. **Multi-Step**: 80% workflow success rate
3. **Error Recovery**: 70% actionable suggestions
4. **Query Support**: 90% query intent recognition
5. **Voice**: 85% transcription accuracy (top 20 operations)
6. **Performance**: <2s for parsing, <5s for voice transcription
7. **Test Coverage**: >75%

## Risks and Mitigations

### Risk 1: Context State Complexity
**Mitigation**: Start with simple in-memory state, add persistence only if needed

### Risk 2: Whisper API Latency
**Mitigation**: Make voice support optional and async

### Risk 3: Backward Compatibility
**Mitigation**: Feature flags and careful integration testing

### Risk 4: Error Recovery Accuracy
**Mitigation**: Start with pattern matching, enhance with AI analysis gradually

## Open Questions

1. Should session state persist across terminal sessions?
2. How long should context be retained?
3. Should voice support be a separate command (`azlin voice`) or flag (`azlin do --voice`)?
4. What is the rollback strategy for failed multi-step workflows?

## Next Steps

1. Architect review and design specification
2. Create module specifications
3. Write failing tests (TDD)
4. Implement Phase 1 (Foundation)
5. Iterate through remaining phases
