# Agentic "Do It" Mode Architecture Proposals

**Goal:** Enable natural language commands for azlin that are intelligently parsed and executed by AI agents

**Examples:**
- "create a new vm for my repo and call it Sam"
- "sync all of my vms with the latest updates and show me the cost over the last week"
- "provision 3 VMs with GPU support and mount shared storage"

---

## Proposal 1: Embedded Claude Orchestrator (RECOMMENDED)

### Architecture Overview
```
User Input (Natural Language)
    ↓
azlin do "..."
    ↓
[Intent Parser] ← Claude API (classify intent)
    ↓
[Command Planner] ← Claude API (create execution plan)
    ↓
[Action Executor] → Existing azlin commands
    ↓
[Result Validator] ← Claude API (verify success)
    ↓
User Output (Natural Language + Data)
```

### Components

#### 1. Intent Parser
- **Input:** Natural language string
- **Process:** Claude API call to classify intent and extract parameters
- **Output:** Structured action specification

```python
{
    "intent": "provision_vm",
    "parameters": {
        "vm_name": "Sam",
        "repo_url": "<inferred from context>",
        "count": 1
    },
    "confidence": 0.95
}
```

#### 2. Command Planner
- **Input:** Action specification
- **Process:** Claude API call to generate step-by-step execution plan
- **Output:** Ordered list of azlin commands

```python
[
    {"command": "azlin new", "args": {"name": "Sam", "repo": "..."}},
    {"command": "azlin status", "args": {"name": "Sam"}},
]
```

#### 3. Action Executor
- **Input:** Command plan
- **Process:** Execute azlin commands sequentially
- **Output:** Results from each command
- **Error Handling:** Retry with Claude-assisted error recovery

#### 4. Result Validator
- **Input:** Execution results + original intent
- **Process:** Claude API call to verify success criteria met
- **Output:** Success/failure report in natural language

### Advantages
✅ **Leverages existing commands** - No need to reimplement VM logic
✅ **Modular** - Each component is independently testable
✅ **Self-healing** - Can retry with adjusted parameters
✅ **Low coupling** - Doesn't require changes to existing azlin codebase
✅ **Fast iteration** - Prompt engineering vs code changes

### Disadvantages
❌ **API dependency** - Requires Claude API access
❌ **Latency** - Multiple API calls per request (2-4 seconds typical)
❌ **Cost** - Claude API calls (but manageable with caching)

### Implementation Complexity: **MEDIUM**
- New CLI command: `azlin do`
- 4 core modules (~400-600 LOC)
- Integration tests with Claude API
- Prompt templates (~200 lines)

---

## Proposal 2: amplihack Bundle Integration

### Architecture Overview
```
User Input (Natural Language)
    ↓
azlin do "..." --via-amplihack
    ↓
[amplihack CLI Wrapper]
    ↓
amplihack claude --auto -- -p "..."
    ↓
[amplihack agent orchestration]
    ↓
[Tool Execution] → azlin commands as tools
    ↓
User Output
```

### Components

#### 1. amplihack CLI Wrapper
- **Input:** Natural language + azlin context
- **Process:** Format request for amplihack
- **Output:** amplihack invocation

#### 2. Tool Definition
- **What:** Define azlin commands as amplihack tools
- **Format:** `.claude/tools/azlin/*.py` with MCP protocol
- **Example:**

```python
# .claude/tools/azlin/provision_vm.py
def provision_vm(name: str, repo: str = None, size: str = "Standard_D2s_v3"):
    """Provision a new Azure VM with development tools."""
    # Call actual azlin commands
    result = subprocess.run(["azlin", "new", "--name", name, ...])
    return {"vm": name, "ip": parse_ip(result)}
```

#### 3. amplihack Auto Mode
- Uses amplihack's built-in agent orchestration
- Leverages existing agent bundles
- Multi-turn execution with feedback loops

### Advantages
✅ **Proven architecture** - Based on Microsoft Hackathon winner
✅ **Rich agent ecosystem** - architect, builder, reviewer agents
✅ **Multi-turn reasoning** - Can handle complex multi-step tasks
✅ **Extensible** - Easy to add new capabilities via tools

### Disadvantages
❌ **Heavy dependency** - Requires amplihack installation
❌ **Complexity** - Additional layer of indirection
❌ **Setup burden** - Users need amplihack configuration
❌ **Version coupling** - Breaking changes in amplihack affect azlin

### Implementation Complexity: **HIGH**
- amplihack integration layer (~300 LOC)
- Tool definitions for all azlin commands (~800 LOC)
- Configuration management (~200 LOC)
- Testing across two systems

---

## Proposal 3: Hybrid Local Agent (Lightweight)

### Architecture Overview
```
User Input (Natural Language)
    ↓
azlin do "..."
    ↓
[Keyword Matcher] (no AI)
    ↓
[Template Expander]
    ↓
[Existing azlin commands]
    ↓
User Output
```

### Components

#### 1. Keyword Matcher
- **Input:** Natural language string
- **Process:** Regex/keyword matching for common patterns
- **Output:** Matched template or "unknown"

```python
PATTERNS = [
    (r"create.*vm.*named? (\w+)", "provision_vm", {"name": "$1"}),
    (r"sync.*vms?", "sync_all", {}),
    (r"cost.*last (\d+) (day|week|month)", "cost_report", {"period": "$1 $2"}),
]
```

#### 2. Template Expander
- **Input:** Matched template + parameters
- **Process:** Expand to azlin commands
- **Output:** Command invocation

#### 3. Fallback to Claude
- If no pattern matches → Call Claude API for interpretation
- Hybrid: Fast local matching + AI fallback

### Advantages
✅ **Fast** - No API calls for common patterns (< 10ms)
✅ **No API dependency** - Works offline for common tasks
✅ **Simple** - Easy to understand and maintain
✅ **Graceful degradation** - Falls back to Claude when needed

### Disadvantages
❌ **Limited coverage** - Only handles predefined patterns
❌ **Brittle** - Regex matching is fragile
❌ **Manual maintenance** - Need to add patterns for new capabilities
❌ **Not truly agentic** - Template matching, not reasoning

### Implementation Complexity: **LOW**
- Pattern matching (~200 LOC)
- Template expander (~150 LOC)
- Claude fallback (~100 LOC)
- Pattern definitions (~300 lines)

---

## Proposal 4: LangChain + Function Calling

### Architecture Overview
```
User Input (Natural Language)
    ↓
azlin do "..."
    ↓
[LangChain Agent] ← Claude Function Calling API
    ↓
[Tool Registry] (azlin commands as functions)
    ↓
[ReAct Agent Loop]
    ↓
User Output
```

### Components

#### 1. LangChain Agent
- Uses LangChain's Claude integration
- Function calling for tool selection
- ReAct (Reasoning + Acting) pattern

#### 2. Tool Registry
```python
@tool
def provision_vm(name: str, repo: str = None):
    """Provision a new Azure VM."""
    return execute_azlin_command(["new", "--name", name, ...])

@tool
def list_vms():
    """List all VMs in resource group."""
    return execute_azlin_command(["list"])
```

#### 3. ReAct Agent Loop
- **Thought:** "I need to provision a VM named Sam"
- **Action:** Call provision_vm("Sam")
- **Observation:** "VM created at IP 4.155.103.77"
- **Thought:** "Success, task complete"

### Advantages
✅ **Industry standard** - LangChain is widely used
✅ **Rich tooling** - Memory, callbacks, observability
✅ **Function calling** - Native Claude support
✅ **Extensible** - Easy to add new tools

### Disadvantages
❌ **Heavy dependency** - LangChain is large (~50MB)
❌ **Opinionated** - LangChain patterns may not fit azlin
❌ **Version churn** - LangChain changes frequently
❌ **Overkill** - Too complex for current needs

### Implementation Complexity: **HIGH**
- LangChain integration (~400 LOC)
- Tool wrappers (~600 LOC)
- Agent configuration (~200 LOC)
- Observability/logging (~300 LOC)

---

## Evaluation Matrix

| Criteria | Proposal 1 (Embedded) | Proposal 2 (amplihack) | Proposal 3 (Hybrid) | Proposal 4 (LangChain) |
|----------|----------------------|----------------------|--------------------|-----------------------|
| **Simplicity** | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Capabilities** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Performance** | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Maintenance** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Extensibility** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **User Experience** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Cost** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Offline Support** | ⭐ | ⭐ | ⭐⭐⭐⭐ | ⭐ |
| **TOTAL** | **30/40** | **26/40** | **28/40** | **26/40** |

---

## Recommendation: **Proposal 1 - Embedded Claude Orchestrator**

### Why This is Best

1. **Ruthless Simplicity** - Direct integration, no heavy frameworks
2. **Leverages Existing Code** - Uses azlin commands as-is
3. **True Agentic** - Claude does real reasoning, not pattern matching
4. **Fast Time-to-Value** - Can iterate on prompts without code changes
5. **Low Maintenance** - Fewer dependencies to manage
6. **Aligns with Philosophy** - Modular, testable, no over-engineering

### Implementation Plan

**Phase 1: Core (MVP)**
- Intent parser with Claude API
- Simple command executor
- Basic test suite
- ~400 LOC

**Phase 2: Enhancement**
- Command planner for multi-step tasks
- Result validator
- Error recovery
- ~300 LOC

**Phase 3: Polish**
- Streaming responses
- Cost tracking
- Offline fallback (Proposal 3 patterns)
- ~200 LOC

**Total Estimated LOC:** 900-1000 (+ tests)
**Estimated Timeline:** 4-6 hours

---

## Next Steps

1. ✅ Create feature branch: `feat/agentic-do-mode`
2. ✅ Implement intent parser module
3. ✅ Implement command executor module
4. ✅ Add `azlin do` CLI command
5. ✅ Create comprehensive test suite
6. ✅ Test with real natural language examples
7. ✅ Create PR with documentation

Let's build this! 🚀
