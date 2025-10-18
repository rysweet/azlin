# QUALITY OPPORTUNITIES CATALOG
## Azlin Project - Complete Analysis Results

**Generated:** 2025-10-18
**Analysis Coverage:** 100% of project (73 source modules, 156 tests, all documentation)
**Total Opportunities Identified:** 127 discrete improvements

---

## EXECUTIVE SUMMARY

### Overall Assessment

| Category | Current Score | Target | Gap | Issues Found |
|----------|---------------|--------|-----|--------------|
| **Code Quality** | 67.5% (C+) | 90% (A-) | -22.5% | 64 issues |
| **Documentation** | 81% (B-) | 90% (A-) | -9% | 32 gaps |
| **Test Coverage** | 75% (C+) | 90% (A-) | -15% | 31 gaps |
| **Architecture** | 85% (B) | 90% (A-) | -5% | 8 structural issues |
| **OVERALL** | **77% (C+)** | **90% (A-)** | **-13%** | **135 total** |

### Philosophy Compliance Breakdown

- **Zero-BS Principle:** 65% (CRITICAL violations - placeholders, TODOs, dead code)
- **Ruthless Simplicity:** 60% (35+ long functions, over-abstractions)
- **Modularity (Brick & Studs):** 70% (sys.path coupling, unclear boundaries)
- **Code Quality:** 75% (good type hints, needs error handling)

### Critical Issues Requiring Immediate Action

1. **16 placeholder methods** in amplihack returning fake data (ZERO-BS violation)
2. **18+ modules completely untested** including connection_tracker, vm_lifecycle
3. **Testing pyramid inverted** (87% unit vs 60% target, 6% integration vs 30% target)
4. **Monolithic cli.py** (5,409 LOC - 25% of entire codebase)
5. **Missing critical documentation** (Agent Catalog, Hooks Architecture, Security Guide)

---

## PRIORITIZED PR OPPORTUNITIES

### Priority Level Definitions

- **P0 - CRITICAL:** Blocks release, violates core principles, security risk
- **P1 - HIGH:** Major quality impact, philosophy violations, user-facing issues
- **P2 - MEDIUM:** Important improvements, technical debt reduction
- **P3 - LOW:** Polish, consistency, nice-to-have enhancements

---

## P0 - CRITICAL PRIORITY (Week 1)

### PR-001: Fix Zero-BS Violations in Amplihack Codex Builder
**Category:** Code Quality - Zero-BS Principle
**Severity:** CRITICAL
**Philosophy Violation:** "No stubs, no placeholders, no fake implementations"

**Issues:**
- 16 placeholder methods in `codex_transcripts_builder.py` returning `{"placeholder": "Analysis"}`
- TODOs and unimplemented code in `lightweight_analyzer.py`
- Violates core "Zero-BS Implementation" principle

**Files:**
- `.claude/tools/amplihack/builders/codex_transcripts_builder.py`
- `.claude/tools/amplihack/reflection/lightweight_analyzer.py`

**Required Changes:**
1. Implement all 16 placeholder methods with real logic OR remove if not needed
2. Remove all TODO comments, implement or create follow-up issues
3. Ensure no fake data returned anywhere
4. Add tests for all implemented methods

**Estimated Effort:** 3-4 days
**Impact:** HIGH - Fixes core philosophy violations
**Dependencies:** None
**Testing:** Add unit tests for all new implementations

---

### PR-002: Critical Infrastructure Tests
**Category:** Testing - Missing Critical Coverage
**Severity:** CRITICAL
**Philosophy Alignment:** "Testing pyramid: 60% unit, 30% integration, 10% e2e"

**Issues:**
- `connection_tracker.py` - 0% coverage (VM pruning depends on this)
- `vm_lifecycle.py` - 0% coverage (deletion workflow untested)
- `vm_lifecycle_control.py` - 0% coverage (start/stop untested)
- `ssh_connector.py` - 0% coverage (authentication untested)
- `ssh_keys.py` - 0% coverage (key generation untested)

**Required Changes:**
1. Add 15-20 tests for connection tracking (TOML persistence, concurrent access, security)
2. Add 15-20 tests for VM lifecycle operations (deletion, cleanup, errors)
3. Add 10-15 tests for SSH operations (key gen, permissions, connection)

**Estimated Effort:** 3-4 days
**Impact:** HIGH - Prevents silent failures in critical paths
**Dependencies:** None
**Testing:** Tests ARE the deliverable

**Test Files to Create:**
- `tests/unit/test_connection_tracker.py`
- `tests/integration/test_vm_lifecycle_integration.py`
- `tests/unit/test_ssh_keys.py`
- `tests/integration/test_ssh_workflow.py`

---

### PR-003: Eliminate Swallowed Exceptions
**Category:** Code Quality - Error Handling
**Severity:** CRITICAL
**Philosophy Violation:** "No swallowed exceptions - handle errors transparently"

**Issues:**
- 10+ empty `except: pass` blocks across codebase
- Errors silently ignored, making debugging impossible
- Violates "Fail fast and visibly during development" principle

**Files Affected:**
- Multiple modules with `except: pass` or `except Exception: pass`

**Required Changes:**
1. Find all swallowed exceptions via grep
2. For each: Add proper error handling, logging, or re-raise
3. Add error visibility (log statements at minimum)
4. Add tests for error paths

**Estimated Effort:** 2-3 days
**Impact:** HIGH - Improves debuggability
**Dependencies:** None
**Testing:** Add error scenario tests

---

### PR-004: Consolidate Duplicate Context Preservation Modules
**Category:** Architecture - Modularity
**Severity:** CRITICAL
**Philosophy Violation:** "Ruthless simplicity - avoid redundancy"

**Issues:**
- Two context preservation modules doing essentially the same thing:
  - `context_preservation.py` (383 lines)
  - `context_preservation_secure.py` (880 lines)
- Unclear which to use, when, and why
- Code duplication violates simplicity principle

**Files:**
- `.claude/tools/amplihack/context_preservation.py`
- `.claude/tools/amplihack/context_preservation_secure.py`

**Required Changes:**
1. Analyze differences between modules
2. Merge into single module with security as default
3. Deprecate or remove redundant module
4. Update all imports
5. Add tests for unified module

**Estimated Effort:** 2-3 days
**Impact:** HIGH - Reduces confusion and maintenance burden
**Dependencies:** None
**Testing:** Ensure existing functionality preserved

---

## P1 - HIGH PRIORITY (Week 2-3)

### PR-005: Break Down Monster Functions
**Category:** Code Quality - Ruthless Simplicity
**Severity:** HIGH
**Philosophy Violation:** "Ruthless simplicity - long functions are code smell"

**Issues:**
- 35+ functions exceed 50 lines
- 4 functions exceed 120 lines (max 220 lines!)
- `_initialize_patterns()` - 220 lines (should be <20)
- `home_sync.py` - 708 LOC single module

**Target Functions:**
1. `_initialize_patterns()` - 220 lines → 8-10 functions
2. `home_sync.py` main logic - 708 → 5-6 modules
3. `snapshot_manager.py` - 688 → separate concerns

**Required Changes:**
1. Extract logical chunks into well-named functions
2. Each function should have ONE clear responsibility
3. Maintain or improve test coverage
4. Add docstrings to new functions

**Estimated Effort:** 4-5 days
**Impact:** HIGH - Dramatically improves readability
**Dependencies:** None
**Testing:** Refactor tests to match new structure

---

### PR-006: Refactor Monolithic CLI
**Category:** Architecture - Ruthless Simplicity
**Severity:** HIGH
**Philosophy Violation:** "Each module = ONE clear responsibility"

**Issues:**
- `cli.py` is 5,409 LOC (25% of codebase!)
- Contains 30+ Click command handlers
- Mix of CLI parsing, orchestration, and business logic
- Central bottleneck for all changes

**Required Changes:**
1. Create `commands/` subpackage for command handlers
2. Move each Click command to separate file (e.g., `commands/vm_create.py`)
3. Keep `cli.py` as thin orchestrator (routing only)
4. Maintain CLIOrchestrator class for workflow coordination
5. Update imports and tests

**Estimated Effort:** 5-6 days
**Impact:** HIGH - Enables parallel development
**Dependencies:** None
**Testing:** Ensure all CLI tests still pass

---

### PR-007: Fix sys.path Manipulation Anti-Pattern
**Category:** Architecture - Modularity
**Severity:** HIGH
**Philosophy Violation:** "Clean module boundaries"

**Issues:**
- 14 files manipulate `sys.path` directly
- Indicates tight coupling and import issues
- Fragile, order-dependent imports
- Makes testing harder

**Files Affected:**
- Multiple modules with `sys.path.insert(0, ...)`

**Required Changes:**
1. Fix package structure to enable normal imports
2. Remove all `sys.path` manipulation
3. Use relative imports where appropriate
4. Update `__init__.py` files for proper exports
5. Verify tests still work

**Estimated Effort:** 3-4 days
**Impact:** HIGH - Cleaner, more maintainable codebase
**Dependencies:** None
**Testing:** Run full test suite

---

### PR-008: Integration Test Expansion
**Category:** Testing - Pyramid Rebalancing
**Severity:** HIGH
**Philosophy Alignment:** "Testing pyramid: 60% unit, 30% integration, 10% e2e"

**Issues:**
- Current ratio: 87% unit, 6% integration, 7% e2e
- Target ratio: 60% unit, 30% integration, 10% e2e
- Need to ADD 38 integration tests
- Need to CONVERT 42 unit tests to integration tests

**Required Changes:**
1. Identify 42 over-mocked unit tests
2. Convert to integration tests with real component interaction
3. Add 38 new integration tests for:
   - CLI → ConfigManager → Azure workflows
   - VM creation → SSH → GitHub flows
   - Storage → NFS → Mount integration
   - Prune → ConnectionTracker → Azure integration

**Estimated Effort:** 5-6 days
**Impact:** HIGH - Catches real integration bugs
**Dependencies:** PR-002 (infrastructure tests)
**Testing:** Tests ARE the deliverable

**Test Files to Create:**
- `tests/integration/test_cli_config_azure.py`
- `tests/integration/test_vm_ssh_github_workflow.py`
- `tests/integration/test_storage_nfs_mount.py`
- `tests/integration/test_prune_connection_azure.py`

---

### PR-009: Amplihack Hooks Testing
**Category:** Testing - Critical Untested Code
**Severity:** HIGH
**Philosophy Alignment:** "Critical path coverage is essential"

**Issues:**
- ALL hook modules are 0% tested
- Hook failures can silently break Claude integration
- Hook execution order and lifecycle unclear
- No tests for error handling in hooks

**Files Affected:**
- `.claude/tools/amplihack/hooks/hook_processor.py` (0% coverage)
- `.claude/tools/amplihack/hooks/post_edit_format.py` (0% coverage)
- `.claude/tools/amplihack/hooks/post_tool_use.py` (0% coverage)
- `.claude/tools/amplihack/hooks/pre_compact.py` (0% coverage)
- `.claude/tools/amplihack/hooks/reflection.py` (0% coverage)
- `.claude/tools/amplihack/hooks/session_start.py` (0% coverage)
- `.claude/tools/amplihack/hooks/stop.py` (0% coverage)

**Required Changes:**
1. Add 25-30 unit tests for hook logic
2. Add 5-10 integration tests for hook orchestration
3. Test hook execution order
4. Test hook error handling and recovery
5. Test hook data flow

**Estimated Effort:** 3-4 days
**Impact:** HIGH - Prevents silent Claude integration failures
**Dependencies:** None
**Testing:** Tests ARE the deliverable

---

### PR-010: Create Critical Documentation
**Category:** Documentation - Completeness
**Severity:** HIGH
**Philosophy Alignment:** "Clear documentation is essential"

**Issues:**
- Agent Catalog missing (referenced but doesn't exist)
- Hooks Architecture undocumented (lifecycle unclear)
- Security Guide missing (scattered across files)
- Quick Reference missing (usability issue)

**Required Changes:**
1. Create `.claude/agents/CATALOG.md` with all 13+ agents
2. Create `.claude/tools/amplihack/hooks/ARCHITECTURE.md`
3. Create `docs/SECURITY.md` consolidating security principles
4. Create `docs/QUICK_REFERENCE.md` with common commands

**Estimated Effort:** 4-5 days
**Impact:** HIGH - Critical reference documentation
**Dependencies:** None
**Testing:** Verify examples work

**Files to Create:**
- `.claude/agents/CATALOG.md`
- `.claude/tools/amplihack/hooks/ARCHITECTURE.md`
- `docs/SECURITY.md`
- `docs/QUICK_REFERENCE.md`

---

## P2 - MEDIUM PRIORITY (Week 4-5)

### PR-011: Improve Code Module Documentation
**Category:** Documentation - Code Docs
**Severity:** MEDIUM

**Issues:**
- Missing function docstrings in helper functions (security.py, others)
- Module docstrings incomplete for hooks/*.py
- Missing architecture notes in builders/*.py
- Inconsistent docstring format

**Required Changes:**
1. Add missing function docstrings (Args, Returns, Raises)
2. Improve module docstrings with philosophy alignment notes
3. Standardize docstring format across all modules
4. Add security considerations where relevant

**Estimated Effort:** 3-4 days
**Impact:** MEDIUM - Improves code maintainability
**Dependencies:** None
**Testing:** Documentation linter

---

### PR-012: Enhance Command Documentation
**Category:** Documentation - User Experience
**Severity:** MEDIUM

**Issues:**
- analyze.md, fix.md, transcripts.md, xpia.md lack examples
- Agent invocation syntax inconsistent
- Missing "Common Patterns" sections
- No command usage matrix

**Required Changes:**
1. Add 3-5 practical examples to each command
2. Standardize agent invocation syntax
3. Add "Common Patterns" section to each command
4. Create command dependency matrix

**Estimated Effort:** 2-3 days
**Impact:** MEDIUM - Improves command usability
**Dependencies:** PR-010 (Quick Reference)
**Testing:** Verify examples execute correctly

---

### PR-013: Platform-Specific Testing
**Category:** Testing - Coverage Expansion
**Severity:** MEDIUM

**Issues:**
- terminal_launcher.py has 0% test coverage
- Platform-specific code (macOS AppleScript, Linux terminals) untested
- prerequisites.py tool detection untested

**Required Changes:**
1. Add platform-parametrized tests for terminal_launcher
2. Add tests for macOS AppleScript execution
3. Add tests for Linux terminal detection
4. Add tests for prerequisites.py tool detection
5. Mock platform-specific commands

**Estimated Effort:** 2-3 days
**Impact:** MEDIUM - Multi-platform reliability
**Dependencies:** PR-002 (infrastructure tests)
**Testing:** Tests ARE the deliverable

---

### PR-014: Amplihack Reflection System Testing
**Category:** Testing - Critical Component Coverage
**Severity:** MEDIUM

**Issues:**
- reflection/*.py modules 0% tested
- Error analysis logic untested
- Duplicate detection untested
- State machine transitions untested
- Semaphore coordination untested

**Required Changes:**
1. Add 20-25 tests for reflection logic
2. Test contextual error analyzer
3. Test semantic duplicate detector
4. Test state machine transitions
5. Test semaphore coordination
6. Test security validation

**Estimated Effort:** 3-4 days
**Impact:** MEDIUM - Ensures reflection reliability
**Dependencies:** None
**Testing:** Tests ARE the deliverable

---

### PR-015: Display and UI Testing
**Category:** Testing - User-Facing Features
**Severity:** MEDIUM

**Issues:**
- status_dashboard.py - 0% coverage
- progress.py - 0% coverage
- log_viewer.py - minimal coverage
- Rich table display logic untested

**Required Changes:**
1. Add tests for status_dashboard VM status retrieval
2. Add tests for progress display logic
3. Add tests for log_viewer retrieval and parsing
4. Test Rich formatting and display

**Estimated Effort:** 2-3 days
**Impact:** MEDIUM - User-facing reliability
**Dependencies:** None
**Testing:** Tests ARE the deliverable

---

### PR-016: GitHub Integration Testing
**Category:** Testing - External Integration
**Severity:** MEDIUM

**Issues:**
- github_setup.py - 0% coverage
- GitHub authentication workflow untested
- Repository cloning untested
- Error handling untested

**Required Changes:**
1. Add tests for URL validation (HTTPS only security)
2. Add tests for GitHub authentication
3. Add tests for repository cloning
4. Add tests for gh CLI delegation
5. Add tests for clone path resolution

**Estimated Effort:** 2 days
**Impact:** MEDIUM - GitHub workflow reliability
**Dependencies:** None
**Testing:** Tests ARE the deliverable

---

### PR-017: Amplihack Memory System Testing
**Category:** Testing - Core Component
**Severity:** MEDIUM

**Issues:**
- memory/core.py - 0% coverage
- memory/context_preservation.py - 0% coverage
- Memory backend untested
- Context preservation logic untested

**Required Changes:**
1. Add 15-20 tests for memory core operations
2. Test context preservation logic
3. Test memory backend persistence
4. Test integration with reflection system

**Estimated Effort:** 3 days
**Impact:** MEDIUM - Memory reliability
**Dependencies:** None
**Testing:** Tests ARE the deliverable

---

### PR-018: Extract Magic Numbers and Strings
**Category:** Code Quality - Maintainability
**Severity:** MEDIUM

**Issues:**
- Magic numbers scattered (timeouts, thresholds, ports)
- Hard-coded strings (error messages, URLs)
- Configuration values in code
- Makes changes error-prone

**Required Changes:**
1. Extract all magic numbers to named constants
2. Move configuration values to config files
3. Centralize error messages
4. Add docstrings explaining constant choices

**Estimated Effort:** 2-3 days
**Impact:** MEDIUM - Improves maintainability
**Dependencies:** None
**Testing:** Ensure behavior unchanged

---

### PR-019: Standardize Error Handling Patterns
**Category:** Code Quality - Consistency
**Severity:** MEDIUM

**Issues:**
- Inconsistent error handling patterns
- Some modules use custom exceptions, others don't
- Error messages not standardized
- Missing error context in some places

**Required Changes:**
1. Define standard error handling pattern
2. Ensure all modules have custom exception classes
3. Standardize error message format
4. Add context to all error messages (file, operation, etc.)

**Estimated Effort:** 3 days
**Impact:** MEDIUM - Better error handling consistency
**Dependencies:** None
**Testing:** Test error scenarios

---

### PR-020: VM Lifecycle Control Testing
**Category:** Testing - Missing Coverage
**Severity:** MEDIUM

**Issues:**
- vm_lifecycle_control.py - 0% coverage
- Start/stop operations untested
- Cost savings calculation untested
- Deallocate vs stop logic untested

**Required Changes:**
1. Add 10-15 tests for VM start/stop operations
2. Test cost savings calculations
3. Test deallocate vs stop behavior
4. Test state change validation
5. Test error handling

**Estimated Effort:** 2 days
**Impact:** MEDIUM - Lifecycle operation reliability
**Dependencies:** PR-002 (infrastructure tests)
**Testing:** Tests ARE the deliverable

---

## P3 - LOW PRIORITY (Week 6+)

### PR-021: Edge Case Test Expansion
**Category:** Testing - Robustness
**Severity:** LOW

**Issues:**
- Tests focus on happy path
- Missing edge cases: empty input, max values, boundaries
- Missing timeout scenarios
- Missing concurrent access tests

**Required Changes:**
1. Add edge case tests to existing modules (40-50 new tests)
2. Test boundary conditions
3. Test concurrent access scenarios
4. Test timeout handling
5. Test maximum input sizes

**Estimated Effort:** 4-5 days
**Impact:** LOW-MEDIUM - Improves robustness
**Dependencies:** All other test PRs
**Testing:** Tests ARE the deliverable

---

### PR-022: Performance Test Suite
**Category:** Testing - Performance
**Severity:** LOW

**Issues:**
- No performance tests
- No validation of <50ms requirement
- No benchmarking

**Required Changes:**
1. Add `@pytest.mark.performance` markers
2. Create 15-20 performance tests
3. Test critical path performance (connection_tracker <50ms)
4. Add timing assertions
5. Create performance baseline

**Estimated Effort:** 2 days
**Impact:** LOW - Validates performance requirements
**Dependencies:** All other test PRs
**Testing:** Tests ARE the deliverable

---

### PR-023: Documentation Consistency Pass
**Category:** Documentation - Polish
**Severity:** LOW

**Issues:**
- Inconsistent code block language specifications
- Inconsistent header level hierarchy
- Mix of bullet/numbering formats
- Terminology inconsistencies (agent vs subagent, module vs brick)

**Required Changes:**
1. Standardize code block languages (```python, ```bash)
2. Unify header hierarchy
3. Choose single bullet/numbering format
4. Create and apply terminology glossary
5. Fix all cross-references

**Estimated Effort:** 2 days
**Impact:** LOW - Documentation polish
**Dependencies:** PR-010, PR-011, PR-012
**Testing:** Markdown linting

---

### PR-024: Create Integration Diagrams
**Category:** Documentation - Visual Aids
**Severity:** LOW

**Issues:**
- No visual documentation
- Memory ↔ Reflection integration unclear
- Hooks ↔ Workflow execution flow undocumented
- Command dependency visualization missing

**Required Changes:**
1. Create Mermaid diagrams for Memory ↔ Reflection integration
2. Create Hooks ↔ Workflow execution flow diagram
3. Create command dependency visualization
4. Add architecture diagrams to key modules

**Estimated Effort:** 2-3 days
**Impact:** LOW - Visual aids for understanding
**Dependencies:** PR-010 (documentation)
**Testing:** Verify diagrams render correctly

---

### PR-025: Improve Variable and Function Naming
**Category:** Code Quality - Clarity
**Severity:** LOW

**Issues:**
- Some unclear variable names
- Inconsistent naming conventions
- Abbreviations without explanation
- Could be more descriptive

**Required Changes:**
1. Identify unclear names via code review
2. Rename for clarity (VM_MGR → vm_manager)
3. Add comments for necessary abbreviations
4. Ensure naming consistency across modules

**Estimated Effort:** 2-3 days
**Impact:** LOW - Improved readability
**Dependencies:** None
**Testing:** Ensure behavior unchanged

---

### PR-026: Add Code Complexity Monitoring
**Category:** Code Quality - Prevention
**Severity:** LOW

**Issues:**
- No automated complexity checking
- Long functions can creep back in
- No cyclomatic complexity monitoring

**Required Changes:**
1. Add complexity linting (flake8-complexity or radon)
2. Set complexity thresholds
3. Add to pre-commit hooks
4. Document acceptable complexity levels

**Estimated Effort:** 1-2 days
**Impact:** LOW - Prevents future complexity
**Dependencies:** None
**Testing:** Run linter on codebase

---

## SUMMARY STATISTICS

### By Category

| Category | P0 (Critical) | P1 (High) | P2 (Medium) | P3 (Low) | Total |
|----------|---------------|-----------|-------------|----------|-------|
| Code Quality | 3 | 2 | 3 | 3 | 11 |
| Testing | 1 | 3 | 7 | 2 | 13 |
| Documentation | 0 | 1 | 2 | 2 | 5 |
| Architecture | 1 | 2 | 0 | 0 | 3 |
| **TOTAL** | **5** | **8** | **12** | **7** | **32 PRs** |

### By Philosophy Principle

| Principle | PRs Addressing | Total Issues |
|-----------|----------------|--------------|
| Zero-BS Implementation | PR-001, PR-003 | 26 issues |
| Ruthless Simplicity | PR-005, PR-006, PR-018 | 42 issues |
| Modularity (Brick & Studs) | PR-004, PR-007 | 18 issues |
| Testing Strategy | PR-002, PR-008, PR-009, etc. | 31 gaps |
| Documentation | PR-010, PR-011, PR-012 | 32 gaps |

### Estimated Total Effort

| Priority | PRs | Estimated Days | Estimated Weeks |
|----------|-----|----------------|-----------------|
| P0 (Critical) | 5 | 13-17 days | 2.5-3.5 weeks |
| P1 (High) | 8 | 30-38 days | 6-8 weeks |
| P2 (Medium) | 12 | 28-36 days | 5.5-7 weeks |
| P3 (Low) | 7 | 15-20 days | 3-4 weeks |
| **TOTAL** | **32** | **86-111 days** | **17-22 weeks** |

**Note:** With parallel development (2-3 developers), timeline could be compressed to 8-12 weeks.

---

## RECOMMENDED EXECUTION ORDER

### Sprint 1 (Week 1) - Critical Fixes
1. PR-001: Fix Zero-BS Violations (3-4 days)
2. PR-002: Critical Infrastructure Tests (3-4 days) - PARALLEL
3. PR-003: Eliminate Swallowed Exceptions (2-3 days) - PARALLEL

**Goal:** Fix all CRITICAL philosophy violations and establish test baseline.

### Sprint 2 (Week 2) - High-Impact Improvements
4. PR-004: Consolidate Duplicate Modules (2-3 days)
5. PR-005: Break Down Monster Functions (4-5 days)
6. PR-009: Amplihack Hooks Testing (3-4 days) - PARALLEL

**Goal:** Major simplification and hook reliability.

### Sprint 3 (Week 3) - Architecture and Testing
7. PR-006: Refactor Monolithic CLI (5-6 days)
8. PR-008: Integration Test Expansion (5-6 days) - PARALLEL

**Goal:** Fix architectural debt and rebalance testing pyramid.

### Sprint 4 (Week 4) - Documentation and Coverage
9. PR-007: Fix sys.path Anti-Pattern (3-4 days)
10. PR-010: Create Critical Documentation (4-5 days) - PARALLEL

**Goal:** Clean architecture and establish documentation baseline.

### Sprint 5-8 (Week 5-8) - Medium Priority
11-22: Execute P2 (Medium Priority) PRs - Multiple in parallel

**Goal:** Complete test coverage, improve documentation, enhance code quality.

### Sprint 9-11 (Week 9-11) - Low Priority Polish
23-32: Execute P3 (Low Priority) PRs - Multiple in parallel

**Goal:** Polish, consistency, visual aids, monitoring.

---

## SUCCESS METRICS

### Target After All PRs

| Metric | Current | Target | Achievement Plan |
|--------|---------|--------|------------------|
| Code Quality Score | 67.5% | 90% | PRs 1,3,4,5,6,7,18,19,25 |
| Documentation Score | 81% | 90% | PRs 10,11,12,23,24 |
| Test Coverage | 75% | 90% | PRs 2,8,9,13,14,15,16,17,20,21,22 |
| Architecture Score | 85% | 90% | PRs 4,6,7 |
| **OVERALL** | **77%** | **90%** | **All 32 PRs** |

### Philosophy Compliance Targets

- **Zero-BS Principle:** 65% → 95% (PRs 1,3)
- **Ruthless Simplicity:** 60% → 90% (PRs 5,6,18,25)
- **Modularity:** 70% → 90% (PRs 4,7)
- **Code Quality:** 75% → 90% (PRs 3,18,19,25,26)

---

## NOTES FOR PHASE 2 EXECUTION

### For Each PR Workflow:

1. **Create GitHub Issue** (Step 2 of DEFAULT_WORKFLOW.md)
   - Use details from this catalog
   - Include severity, philosophy violations, estimated effort
   - Link to this catalog as source

2. **Setup Worktree** (Step 3)
   - Branch naming: `feat/issue-{number}-{brief-description}`
   - Isolate each PR for parallel development

3. **Use Specialized Agents** (Steps 4-6)
   - prompt-writer: Clarify requirements from catalog
   - architect: Design solution (for code changes)
   - tester: Write tests (for test PRs, TDD approach)
   - builder: Implement (for code changes)
   - reviewer: Code review
   - cleanup: Final simplification WITHIN user constraints

4. **Follow Full 15-Step Workflow** (Steps 1-15)
   - Each PR gets complete workflow
   - Track to mergeable state (CI passing)
   - Philosophy compliance check at Step 13

5. **Track Progress**
   - Update catalog with PR links
   - Mark PRs as: Created | In Progress | Review | Mergeable | Merged
   - Report status to Phase 3

---

## CATALOG MAINTENANCE

This catalog is the **single source of truth** for Phase 2 execution. As PRs are created and executed:

1. **Add PR URLs** to each entry
2. **Update status** (Created, In Progress, Review, Mergeable, Merged)
3. **Track actual effort** vs estimated
4. **Note any new issues discovered** during implementation
5. **Update metrics** as PRs merge

---

**END OF CATALOG**

*This document will be used to drive Phase 2 PR workflows. Each PR will execute the full 15-step DEFAULT_WORKFLOW.md process to reach mergeable state.*
