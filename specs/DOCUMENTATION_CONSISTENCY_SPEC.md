# Documentation Consistency and Testing Specification

## Specification Type: Refactoring

**Version**: 1.0
**Created**: 2025-10-27
**Status**: READY FOR IMPLEMENTATION
**Estimated Complexity**: Complex (3-5 days)

---

## 1. Objective

Ensure 100% consistency between CLI help text, command syntax, and all documentation by:
1. Identifying all inconsistencies across help text, README, and docs/
2. Creating exhaustive command syntax tests
3. Updating all documentation to match actual implementation
4. Establishing validation mechanisms to prevent future drift

**Success Metric**: Zero discrepancies found when comparing help text, command behavior, and documentation.

---

## 2. Problem Statement

### Current Issues

Users have reported inconsistencies between:
- CLI help text (from Click decorators)
- Actual command syntax/behavior
- README.md command examples
- Documentation in /docs/ directory

### Impact

- User confusion and frustration
- Incorrect command usage
- Wasted time debugging "why doesn't this work?"
- Erosion of trust in documentation
- Support burden

---

## 3. Scope Definition

### 3.1 Commands In Scope

Based on `azlin --help` output, these commands MUST be documented and tested:

#### Primary CLI: `azlin`

**Natural Language**:
- `azlin do` - AI-powered natural language commands

**VM Lifecycle**:
- `azlin new` (aliases: `vm`, `create`)
- `azlin clone`
- `azlin list`
- `azlin session`
- `azlin status`
- `azlin start`
- `azlin stop`
- `azlin connect`
- `azlin update`
- `azlin tag`

**Environment Management**:
- `azlin env set`
- `azlin env list`
- `azlin env delete`
- `azlin env export`
- `azlin env import`
- `azlin env clear`

**Snapshot Management**:
- `azlin snapshot create`
- `azlin snapshot list`
- `azlin snapshot restore`
- `azlin snapshot delete`

**Storage Commands**:
- `azlin storage create`
- `azlin storage list`
- `azlin storage status`
- `azlin storage mount`
- `azlin storage unmount`
- `azlin storage delete`

**Monitoring**:
- `azlin w`
- `azlin ps`
- `azlin cost`
- `azlin logs`
- `azlin top`

**Deletion**:
- `azlin kill`
- `azlin destroy`
- `azlin killall`
- `azlin cleanup`

**SSH Key Management**:
- `azlin keys rotate`
- `azlin keys list`
- `azlin keys export`
- `azlin keys backup`

**Authentication**:
- `azlin auth setup`
- `azlin auth test`
- `azlin auth list`
- `azlin auth show`
- `azlin auth remove`

**File Operations**:
- `azlin sync`
- `azlin cp`

**Maintenance**:
- `azlin os-update`
- `azlin prune`
- `azlin template`

#### Secondary CLI: `azdoit`

- `azdoit [REQUEST]` - Standalone natural language Azure automation
- `azdoit --version`
- `azdoit --max-turns N`

**Total Commands**: 52 commands/subcommands

### 3.2 Documentation Files In Scope

All documentation that references commands or syntax:

**Root Level**:
- `/Users/ryan/src/azlin/README.md` (primary user-facing doc)

**docs/ Directory**:
- `/Users/ryan/src/azlin/docs/QUICK_REFERENCE.md`
- `/Users/ryan/src/azlin/docs/AZDOIT.md`
- `/Users/ryan/src/azlin/docs/AZDOIT_README.md`
- `/Users/ryan/src/azlin/docs/README.md`
- `/Users/ryan/src/azlin/docs/STORAGE_README.md`
- `/Users/ryan/src/azlin/docs/API_REFERENCE.md`
- `/Users/ryan/src/azlin/docs/AI_AGENT_GUIDE.md`
- `/Users/ryan/src/azlin/docs/AZLIN.md`
- `/Users/ryan/src/azlin/docs/ARCHITECTURE.md`

**Tests**:
- `/Users/ryan/src/azlin/tests/README.md`
- `/Users/ryan/src/azlin/tests/README_AZDOIT.md`

**Total Documentation Files**: 11 files

### 3.3 Help Text Sources

- Click command decorators in `/Users/ryan/src/azlin/src/azlin/cli.py`
- Click command decorators in `/Users/ryan/src/azlin/src/azlin/azdoit/cli.py`
- Click command decorators in `/Users/ryan/src/azlin/src/azlin/commands/storage.py`
- Docstrings in command functions

### 3.4 Out of Scope

- Historical documentation in `docs/archive/` (explicitly excluded)
- Worktree documentation in `/Users/ryan/src/azlin/worktrees/` (excluded)
- Specs directory `/Users/ryan/src/azlin/specs/` (design docs, not user-facing)
- Internal architecture documentation not referenced in user workflows

---

## 4. Explicit Success Criteria

### 4.1 Consistency Criteria

For EACH of the 52 commands:

- [ ] **Help Text Match**: `azlin COMMAND --help` output matches all documentation examples
- [ ] **Syntax Match**: Command syntax in docs matches actual Click implementation
- [ ] **Options Match**: All documented options exist and work as described
- [ ] **Aliases Match**: All documented aliases work correctly
- [ ] **Examples Work**: Every code example in docs executes without error (or is marked as example-only)
- [ ] **Descriptions Match**: Command purpose descriptions are identical across all docs

### 4.2 Completeness Criteria

- [ ] **All Commands Documented**: Every command in `azlin --help` has documentation
- [ ] **All Options Documented**: Every option for every command is documented
- [ ] **All Aliases Documented**: Every command alias is documented
- [ ] **No Ghost Commands**: No commands documented that don't exist
- [ ] **No Ghost Options**: No options documented that don't exist

### 4.3 Testing Criteria (Exhaustive Definition)

"Exhaustive tests" means:

For EACH command:
1. **Syntax Tests**:
   - [ ] Command runs with no arguments (if allowed)
   - [ ] Command runs with minimal required arguments
   - [ ] Command runs with all possible option combinations
   - [ ] Invalid arguments produce appropriate error messages
   - [ ] Help flag works: `azlin COMMAND --help`

2. **Option Tests**:
   - [ ] Each option works independently
   - [ ] Each option produces expected behavior
   - [ ] Conflicting options produce errors
   - [ ] Missing required options produce errors

3. **Alias Tests**:
   - [ ] Each documented alias works identically to main command
   - [ ] Aliases accept same options as main command

4. **Error Tests**:
   - [ ] Invalid command produces clear error
   - [ ] Invalid options produce clear errors
   - [ ] Error messages match documentation

5. **Integration Tests**:
   - [ ] Commands work in documented workflows
   - [ ] Commands work with other commands (pipelines)
   - [ ] Commands work with documented environment variables

### 4.4 Quality Gates

- [ ] **Zero Inconsistencies**: Automated check finds 0 discrepancies
- [ ] **100% Command Coverage**: All 52 commands have tests
- [ ] **100% Documentation Coverage**: All 52 commands documented
- [ ] **All Tests Pass**: Command syntax tests pass
- [ ] **Review Approved**: Human review confirms accuracy

---

## 5. Deliverables

### 5.1 Analysis Report

**Location**: `/Users/ryan/src/azlin/specs/INCONSISTENCIES_REPORT.md`

**Contents**:
```markdown
# Documentation Inconsistencies Report

## Summary
- Total commands analyzed: 52
- Total docs analyzed: 12
- Inconsistencies found: [NUMBER]

## Inconsistencies by Category

### 1. Missing Commands
Commands in help but not in docs:
- [command]: Missing from [files]

### 2. Ghost Commands
Commands in docs but not in help:
- [command]: Referenced in [files] but doesn't exist

### 3. Syntax Mismatches
Commands with incorrect syntax in docs:
- [command]: Doc says "X" but actual is "Y"
  - Files affected: [list]

### 4. Option Mismatches
Options documented but don't exist (or vice versa):
- [command] [option]: [description]
  - Files affected: [list]

### 5. Alias Mismatches
Aliases documented incorrectly:
- [command]: Doc says alias is "X" but actual is "Y"
  - Files affected: [list]

### 6. Description Inconsistencies
Commands with conflicting descriptions:
- [command]:
  - Help: [text]
  - README: [different text]
  - QUICK_REFERENCE: [yet another text]

## Detailed Findings

[Command-by-command breakdown]
```

### 5.2 Test Suite

**Location**: `/Users/ryan/src/azlin/tests/integration/test_command_syntax_complete.py`

**Structure**:
```python
"""Exhaustive command syntax tests.

Tests EVERY command, option, and alias to ensure:
1. Commands work as documented
2. Options work as documented
3. Aliases work as documented
4. Errors are appropriate
"""

import pytest
from click.testing import CliRunner
from azlin.cli import cli

class TestAzlinNew:
    """Test azlin new command and all its options."""

    def test_new_basic(self):
        """Test: azlin new"""

    def test_new_with_name(self):
        """Test: azlin new --name my-vm"""

    def test_new_with_repo(self):
        """Test: azlin new --repo URL"""

    # ... all options

    def test_new_alias_vm(self):
        """Test: azlin vm (alias)"""

    def test_new_alias_create(self):
        """Test: azlin create (alias)"""

class TestAzlinClone:
    """Test azlin clone command."""
    # ...

# ... all 52 commands
```

**Test Count**: Minimum 300+ individual tests (average 6 per command)

### 5.3 Updated Documentation

**All Files Updated**:
1. `/Users/ryan/src/azlin/README.md` - Updated with correct syntax
2. `/Users/ryan/src/azlin/docs/QUICK_REFERENCE.md` - Updated with correct syntax
3. `/Users/ryan/src/azlin/docs/AZDOIT.md` - Updated if needed
4. All other documentation files with inconsistencies fixed

**Documentation Standards**:
- Command syntax MUST use exact option names from Click
- Examples MUST be runnable (or clearly marked as pseudo-code)
- Descriptions MUST match help text verbatim
- All options MUST be documented
- All aliases MUST be documented

### 5.4 Validation Script

**Location**: `/Users/ryan/src/azlin/scripts/validate_documentation.py`

**Purpose**: Automated check for doc consistency

**Features**:
```python
"""Documentation validation script.

Compares:
1. Click help text vs. documentation
2. Command existence vs. documentation
3. Options vs. documentation
4. Examples vs. actual syntax

Usage:
    python scripts/validate_documentation.py

    # CI/CD usage
    python scripts/validate_documentation.py --strict --exit-on-error
"""

def extract_commands_from_cli():
    """Extract all commands from Click CLI."""

def extract_commands_from_docs():
    """Extract all command references from documentation."""

def compare_help_text():
    """Compare Click help vs. documented help."""

def check_examples():
    """Parse and validate code examples in docs."""

def main():
    """Run all validation checks."""
    inconsistencies = []

    # Check 1: Command existence
    # Check 2: Option consistency
    # Check 3: Help text match
    # Check 4: Example validity

    if inconsistencies:
        print(f"Found {len(inconsistencies)} inconsistencies")
        for issue in inconsistencies:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("All documentation is consistent!")
        sys.exit(0)
```

### 5.5 CI/CD Integration

**Location**: `.github/workflows/doc-validation.yml`

```yaml
name: Documentation Validation

on:
  pull_request:
    paths:
      - 'src/azlin/cli.py'
      - 'src/azlin/commands/**'
      - 'README.md'
      - 'docs/**'
  push:
    branches: [main]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e .
      - name: Validate documentation
        run: python scripts/validate_documentation.py --strict
      - name: Run syntax tests
        run: pytest tests/integration/test_command_syntax_complete.py -v
```

---

## 6. Implementation Plan

### Phase 1: Analysis (Day 1)

**Tasks**:
1. Extract all commands from CLI (run `azlin --help`, parse output)
2. Extract all command references from each documentation file
3. Compare and generate inconsistencies report
4. Create prioritized fix list

**Output**: `INCONSISTENCIES_REPORT.md`

### Phase 2: Test Creation (Day 2)

**Tasks**:
1. Create test file structure
2. Write tests for all commands (can be done in parallel)
3. Document test coverage metrics
4. Run initial test suite (many will fail - that's expected)

**Output**: `tests/integration/test_command_syntax_complete.py`

### Phase 3: Help Text Fixes (Day 2-3)

**Tasks**:
1. Update Click decorators to match intended behavior
2. Fix docstrings in command functions
3. Ensure all options are properly documented in Click
4. Re-run tests, fix failures

**Output**: Updated `src/azlin/cli.py` and command files

### Phase 4: Documentation Updates (Day 3-4)

**Tasks**:
1. Update README.md with correct syntax
2. Update QUICK_REFERENCE.md with correct syntax
3. Update all other docs with inconsistencies
4. Add missing commands/options
5. Remove ghost commands/options

**Output**: All documentation files updated

### Phase 5: Validation (Day 4-5)

**Tasks**:
1. Create validation script
2. Run validation script against all docs
3. Fix any remaining issues
4. Add CI/CD workflow
5. Final verification

**Output**: `scripts/validate_documentation.py`, CI workflow

---

## 7. Ambiguities Requiring Clarification

### 7.1 Documentation Philosophy

**Question**: When help text differs from documentation, which is the source of truth?

**Options**:
- A) Help text is truth (update docs to match)
- B) Documentation is truth (update code to match)
- C) Current implementation is truth (update both to match behavior)

**Recommendation**: Option C - Make both match actual behavior

---

### 7.2 Example Validity

**Question**: Should ALL code examples in documentation be runnable?

**Context**: Some examples may be illustrative/pseudo-code

**Options**:
- A) Yes, all examples must run
- B) No, mark non-runnable examples with comment
- C) Separate "Examples" from "Sample Output"

**Recommendation**: Option B with this format:
```bash
# Example (illustration only - customize for your environment)
azlin new --name your-vm-name
```

---

### 7.3 Deprecated Features

**Question**: What to do with documented features that no longer exist?

**Options**:
- A) Remove from docs entirely
- B) Mark as deprecated with migration guide
- C) Keep for historical reference

**Recommendation**: Option A for user docs, Option C for historical docs in archive/

---

### 7.4 Version-Specific Documentation

**Question**: Should documentation specify which version features were added?

**Example**: "New in v2.1: Auto-reconnect feature"

**Options**:
- A) Yes, add version tags
- B) No, document current state only
- C) Yes, but only for major features

**Recommendation**: Option C - Add tags for significant features

---

### 7.5 Testing Depth

**Question**: How deep should option combination testing go?

**Context**: Some commands have 10+ options, testing all combinations = thousands of tests

**Options**:
- A) Test all combinations (exhaustive but slow)
- B) Test each option independently + common combinations
- C) Test documented examples only

**Recommendation**: Option B - Balance between coverage and maintainability

---

## 8. Testing Strategy

### 8.1 Test Categories

**Unit Tests** (existing):
- Module-level tests
- Not changed by this work

**Syntax Tests** (new):
- Command existence
- Option validation
- Alias verification
- Error message validation

**Integration Tests** (enhanced):
- End-to-end workflows from documentation
- Multi-command sequences
- Real Azure operations (where safe)

**Documentation Tests** (new):
- Example extraction and validation
- Help text comparison
- Cross-reference checking

### 8.2 Test Execution Strategy

**Fast Tests** (< 1 second each):
- Syntax validation
- Help text checks
- Example parsing

**Slow Tests** (1-10 seconds):
- Integration tests with mocked Azure
- Workflow validation

**Very Slow Tests** (minutes):
- Real Azure operations
- End-to-end scenarios
- Mark with `@pytest.mark.slow`

### 8.3 CI/CD Strategy

**On Every PR**:
- Fast syntax tests
- Documentation validation script
- Help text consistency checks

**On Main Branch**:
- Full test suite including slow tests

**Nightly**:
- Real Azure integration tests (if configured)

---

## 9. Success Metrics

### 9.1 Quantitative Metrics

- **Documentation Coverage**: 100% of commands documented
- **Test Coverage**: 100% of commands have syntax tests
- **Consistency Score**: 0 inconsistencies in validation report
- **Test Pass Rate**: 100% of syntax tests passing
- **Example Validity**: 100% of marked examples are valid

### 9.2 Qualitative Metrics

- **User Feedback**: Reduced "documentation is wrong" issues
- **Development Velocity**: Faster onboarding (docs are trustworthy)
- **Maintenance Burden**: Easier to keep docs updated (automated checks)

### 9.3 Ongoing Maintenance

**Process**:
1. When adding new command: Update docs + add tests in same PR
2. When changing command: Update docs + update tests in same PR
3. CI blocks merges if validation fails
4. Monthly audit of documentation accuracy

---

## 10. Risk Assessment

### 10.1 Risks

**Risk**: Scope creep - too many edge cases to test
- **Mitigation**: Define clear boundaries for "exhaustive" (see 4.3)
- **Impact**: Medium

**Risk**: Documentation update introduces new inconsistencies
- **Mitigation**: Validation script in CI prevents this
- **Impact**: Low

**Risk**: Tests are too brittle (break on minor changes)
- **Mitigation**: Test documented behavior, not implementation details
- **Impact**: Medium

**Risk**: Real Azure tests cost money
- **Mitigation**: Use mocks for most tests, real Azure only for critical paths
- **Impact**: Low

**Risk**: Large documentation changes conflict with other PRs
- **Mitigation**: Do analysis first, coordinate with team
- **Impact**: Medium

### 10.2 Dependencies

- Access to Azure subscription (for testing real commands)
- ANTHROPIC_API_KEY (for testing `azlin do` and `azdoit`)
- No other teams blocked by this work

---

## 11. Complexity Assessment

**Complexity**: Complex (3-5 days)

**Factors**:
- 52 commands to analyze and test
- 12 documentation files to update
- Multiple CLI entry points (azlin, azdoit)
- Requires understanding of Click framework
- Requires careful attention to detail
- Creates foundation for future consistency

**Breakdown**:
- Analysis: 4-6 hours
- Test creation: 8-12 hours
- Help text fixes: 4-6 hours
- Documentation updates: 8-12 hours
- Validation script: 4-6 hours
- Review and refinement: 4-6 hours

**Total**: 32-48 hours (4-6 days)

---

## 12. Notes for Implementation

### 12.1 Command Discovery

To extract all commands programmatically:

```python
from click.testing import CliRunner
from azlin.cli import cli

runner = CliRunner()
result = runner.invoke(cli, ['--help'])
# Parse result.output

# Get subcommands
for name in cli.list_commands(None):
    cmd = cli.get_command(None, name)
    # Extract options, help text, etc.
```

### 12.2 Documentation Parsing

Use regex patterns to extract commands from docs:

```python
# Find bash code blocks
pattern = r'```bash\n(.*?)\n```'

# Find command references
command_pattern = r'`azlin (\w+)[^`]*`'

# Find option references
option_pattern = r'--(\w+[-\w]*)'
```

### 12.3 Help Text Extraction

```python
@click.command()
@click.option('--name', help='VM name')
def new():
    """Provision a new VM."""
    pass

# Access help programmatically:
help_text = new.help  # "Provision a new VM."
options = new.params  # List of Option objects
```

---

## 13. Acceptance Criteria Summary

Implementation is complete when:

1. [ ] Inconsistencies report generated and reviewed
2. [ ] All 52 commands have syntax tests (minimum 300 tests)
3. [ ] All tests pass
4. [ ] All 12 documentation files updated
5. [ ] Validation script created and passes
6. [ ] CI/CD workflow added and passing
7. [ ] Zero inconsistencies found by validation script
8. [ ] Human review confirms accuracy
9. [ ] README.md is accurate and complete
10. [ ] QUICK_REFERENCE.md is accurate and complete

---

## 14. Related Documents

- **Architecture**: `/Users/ryan/src/azlin/docs/ARCHITECTURE.md`
- **Test Strategy**: `/Users/ryan/src/azlin/docs/testing/test_strategy.md`
- **Existing Tests**: `/Users/ryan/src/azlin/tests/`
- **User Feedback**: GitHub issues (when available)

---

## 15. Appendix: Command Reference Matrix

| Command | In Help | In README | In QUICK_REF | Has Tests | Notes |
|---------|---------|-----------|--------------|-----------|-------|
| azlin new | ✓ | ? | ? | ? | To be filled during analysis |
| azlin clone | ✓ | ? | ? | ? | |
| azlin list | ✓ | ? | ? | ? | |
| ... | | | | | |

*This matrix will be populated during Phase 1 analysis*

---

**END OF SPECIFICATION**

---

## Specification Metadata

- **Type**: Refactoring
- **Priority**: High (user-reported issue)
- **Complexity**: Complex
- **Estimated Effort**: 3-5 days
- **Dependencies**: None
- **Blocking**: None
- **Review Required**: Yes (architect review recommended for validation script design)
- **Breaking Changes**: No
- **Documentation Impact**: High (primary deliverable)
- **Test Impact**: High (creates new test suite)
