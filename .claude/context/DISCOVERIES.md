# DISCOVERIES.md

This file documents non-obvious problems, solutions, and patterns discovered during development. It serves as a living knowledge base.

**Archive**: Entries older than 3 months are moved to [DISCOVERIES_ARCHIVE.md](./DISCOVERIES_ARCHIVE.md).

## February 2026

- [SSH Key Sync Timeout and Silent Failure](#ssh-key-sync-timeout-and-silent-failure-2026-02-04)

## January 2026

- [Bastion Detection Timeout Insufficient for WSL Environments](#bastion-detection-timeout-insufficient-for-wsl-2026-02-03)
- [Ubuntu Version Update Available - 24.04 LTS Supported](#ubuntu-version-update-available-2404-lts-supported-2026-01-17)

## December 2025

- [UVX File Copying System Bug Fixes](#uvx-file-copying-system-bug-fixes-2025-12-15)
- [SessionStop Hook BrokenPipeError Race Condition](#sessionstop-hook-brokenpipeerror-race-condition-2025-12-13)
- [AI Agents Don't Need Human Psychology - No-Psych Winner](#ai-agents-dont-need-human-psychology-2025-12-02)
- [Mandatory User Testing Validates Its Own Value](#mandatory-user-testing-validates-value-2025-12-02)
- [System Metadata vs User Content in Git Conflict Detection](#system-metadata-vs-user-content-git-conflict-2025-12-01)
- [GitHub Pages MkDocs Deployment Requires docs/.claude/ Copy](#github-pages-mkdocs-deployment-requires-docs-claude-copy-2025-12-02)

### November 2025

- [Power-Steering Session Type Detection Fix](#power-steering-session-type-detection-fix-2025-11-25)
- [Transcripts System Architecture Validation](#transcripts-system-investigation-2025-11-22)
- [Hook Double Execution - Claude Code Bug](#hook-double-execution-claude-code-bug-2025-11-21)
- [StatusLine Configuration Missing](#statusline-configuration-missing-2025-11-18)
- [Power-Steering Path Validation Bug](#power-steering-path-validation-bug-2025-11-17)
- [Power Steering Branch Divergence](#power-steering-mode-branch-divergence-2025-11-16)
- [Mandatory End-to-End Testing Pattern](#mandatory-end-to-end-testing-pattern-2025-11-10)
- [Neo4j Container Port Mismatch](#neo4j-container-port-mismatch-bug-2025-11-08)
- [Parallel Reflection Workstream Success](#parallel-reflection-workstream-execution-2025-11-05)

### October 2025

- [Pattern Applicability Framework](#pattern-applicability-analysis-framework-2025-10-20)
- [Socratic Questioning Pattern](#socratic-questioning-pattern-2025-10-18)
- [Expert Agent Creation Pattern](#expert-agent-creation-pattern-2025-10-18)

---

## SSH Key Sync Timeout and Silent Failure (2026-02-04)

### Problem

SSH connections fail with "Permission denied (publickey)" even though:
- SSH key successfully retrieved from Key Vault ✅
- Bastion tunnel successfully created ✅
- User sees message "SSH key auto-sync completed successfully" ✅

But SSH authentication still fails because the key was never actually deployed to the VM.

### Root Cause

**TWO BUGS** in `vm_connector.py:291-299`:

**Bug #1: Timeout Too Short (Line 297)**
```python
timeout=5,  # Reduced from 30s default for faster failure
```

The code uses a **5-second timeout** for SSH key sync, but DEFAULT_TIMEOUT in `vm_key_sync.py` is **60 seconds**. In WSL environments, 5 seconds is insufficient for the Azure Run Command API to deploy the key to the VM.

**The comment admits the bug**: "For first connections, sync will likely timeout anyway" - this is treating a bug as a feature!

**Bug #2: Ignoring Result (Lines 293-299)**
```python
sync_manager.ensure_key_authorized(...)  # Result not captured!
logger.info("SSH key auto-sync completed successfully")  # Logs success regardless!
```

The code:
1. Calls `ensure_key_authorized()` but doesn't capture the `KeySyncResult` return value
2. Logs "SSH key auto-sync completed successfully" WITHOUT checking if it actually succeeded
3. Result contains `synced=False` and `error="Sync operation timed out"` but this is ignored
4. User sees success message even though operation failed

### Error Flow

1. User runs `azlin connect haymaker-dev2`
2. Key retrieved from Key Vault (works) ✅
3. Auto-sync triggered with 5s timeout
4. Azure Run Command API takes >5s to deploy key in WSL
5. `ensure_key_authorized()` times out, returns `KeySyncResult(synced=False, error="Sync operation timed out")`
6. Return value ignored, "completed successfully" logged anyway
7. SSH connection attempts use local key
8. VM doesn't have the key in authorized_keys (sync failed!)
9. SSH says "Permission denied (publickey)" - key not on VM!

### User's Output Evidence

From the error log:
```
Auto-syncing SSH key to VM authorized_keys: haymaker-dev2
Sync operation timed out for VM haymaker-dev2     ← Timeout error from vm_key_sync.py
SSH key auto-sync completed successfully           ← False success from vm_connector.py
...
azureuser@127.0.0.1: Permission denied (publickey). ← Auth fails - key not on VM
```

The contradictory messages prove both bugs exist simultaneously.

### Historical Context

- **PR #575**: Increased DEFAULT_TIMEOUT from 30s to 60s for WSL compatibility
- **test_timeout_values.py**: Validates DEFAULT_TIMEOUT >= 60s
- **vm_connector.py**: Never updated to use DEFAULT_TIMEOUT, still hardcodes 5s!

This is the same timeout pattern as Issue #576 (bastion detection), but in a different module.

### Solutions

**Fix #1: Use DEFAULT_TIMEOUT (60s)**
```python
from azlin.modules.vm_key_sync import DEFAULT_TIMEOUT, VMKeySync

# Line 293-298
result = sync_manager.ensure_key_authorized(
    vm_name=conn_info.vm_name,
    resource_group=conn_info.resource_group,
    public_key=public_key,
    timeout=DEFAULT_TIMEOUT,  # Use 60s for WSL compatibility
)
```

**Fix #2: Check Result and Log Accurately**
```python
# Lines 293-302
result = sync_manager.ensure_key_authorized(
    vm_name=conn_info.vm_name,
    resource_group=conn_info.resource_group,
    public_key=public_key,
    timeout=DEFAULT_TIMEOUT,
)

if result.synced:
    logger.info(f"SSH key synced to VM authorized_keys in {result.duration_ms}ms")
elif result.already_present:
    logger.debug("SSH key already present in VM authorized_keys")
elif result.error:
    logger.warning(
        f"SSH key auto-sync failed: {result.error}. "
        f"Connection may fail if key not already on VM. "
        f"Use 'azlin sync-keys {conn_info.vm_name}' to manually sync."
    )
```

**Benefits**:
1. Key actually gets deployed to VM (60s sufficient for WSL)
2. User sees accurate status messages
3. Failed syncs don't claim success
4. User gets actionable guidance when sync fails
5. Aligns with PR #575 timeout increase pattern

### Testing Requirements

After fix, verify:
1. Fresh VM connection succeeds on first attempt
2. SSH key sync completes within 60s
3. Success message only appears when sync actually succeeds
4. Failure message provides actionable guidance
5. No regressions in existing functionality

### Related Files

- **Primary**: `src/azlin/vm_connector.py` (lines 291-302)
- **Supporting**: `src/azlin/modules/vm_key_sync.py` (DEFAULT_TIMEOUT = 60)
- **Tests**: `tests/unit/test_timeout_values.py`
- **Related Issue**: #576 (bastion timeout - same pattern)
- **Related PR**: #575 (increased DEFAULT_TIMEOUT to 60s for WSL)

### Impact

**Severity**: High - Blocks SSH connections to VMs
**Scope**: All users trying to connect to VMs where key isn't already deployed
**Workaround**: Manual key sync with `azlin sync-keys` before connecting

---

## Bastion Detection Timeout Insufficient for WSL (2026-02-03)

### Problem

Azlin commands (`azlin list`, `azlin connect`) fail in WSL environments with bastion detection timing out, preventing tunnel creation and causing all commands to fail.

### Root Cause

**Location**: `src/azlin/modules/bastion_detector.py:262`

The bastion detection pre-flight check has a **hardcoded 10-second timeout** that's insufficient for Windows/WSL2 environments where Azure CLI operations take longer due to:

1. **First-time bastion extension loading** - Extension installation adds overhead
2. **WSL overhead** - Windows/WSL2 has additional latency vs native Linux
3. **Network conditions** - Variable network latency can exceed 10s
4. **System resources** - Constrained resources slow down Azure CLI

**Code Flow**:
```python
# Line 262: Pre-flight check with 10s timeout
if not cls._check_azure_cli_responsive(timeout=10):
    logger.warning("Azure CLI not responsive, skipping Bastion detection")
    return []  # Empty list causes tunnel creation to fail
```

When the pre-flight check times out:
- Logs "Azure CLI not responsive, skipping Bastion detection"
- Returns empty list (graceful degradation)
- No bastions detected → No tunnels created → Commands fail silently

### Historical Context

**PR #575** (commit `ad152ef`) already increased timeout from **2s → 10s** to fix Windows/WSL2 issues, but 10s is still insufficient for some environments.

Related timeout fixes in git history:
- `ad152ef`: Increase timeout values for Windows/WSL2 (2s → 10s)
- `215e40b`: Increase Azure CLI timeouts for list operations (10s → 30s)
- `8fcd630`: Reduce Azure CLI timeout and add caching for Bastion detection

### Why It's Not Always Reproducible

Timing depends on:
- Whether bastion extension is already loaded in current session
- Current network latency to Azure
- System resource availability
- Azure CLI internal caching

### Solutions

**Option 1: Increase Timeout to 30 seconds** (Recommended - Simple)
```python
# Line 87: Increase default timeout
def _check_azure_cli_responsive(timeout: int = 30) -> bool:

# Line 262: Use 30s timeout
if not cls._check_azure_cli_responsive(timeout=30):
```

**Pros**:
- Simple one-line change
- Aligns with other Azure CLI timeouts in codebase (line 335)
- Consistent with PR #557 that increased other list operations to 30s

**Cons**:
- Commands may feel slow on first run in WSL

**Option 2: Environment Variable Override** (Better flexibility)
```python
import os

DEFAULT_BASTION_TIMEOUT = int(os.getenv("AZLIN_BASTION_TIMEOUT", "30"))

def _check_azure_cli_responsive(
    timeout: int = DEFAULT_BASTION_TIMEOUT
) -> bool:
```

**Pros**:
- Users can adjust for their environment
- Default 30s works for most cases
- Power users can tune performance

**Cons**:
- Slightly more complex
- Need to document the environment variable

**Option 3: Progressive Timeout** (Most robust)
```python
def _check_azure_cli_responsive_progressive() -> bool:
    """Try increasing timeouts until CLI responds."""
    for timeout in [10, 30, 60]:
        if cls._check_azure_cli_responsive(timeout=timeout):
            logger.debug(f"Azure CLI responded within {timeout}s")
            return True
    return False
```

**Pros**:
- Self-adapts to environment
- Fast when possible, patient when needed
- Provides diagnostics (which timeout succeeded)

**Cons**:
- Most complex implementation
- Could be slow in worst case (up to 60s)

### Recommendation

**Use Option 1** (increase to 30s) as immediate fix. This:
- Aligns with existing Azure CLI timeout patterns in the codebase
- Fixes the issue for most WSL environments
- Minimal code change
- Consistent with PR #557 approach for similar issues

If 30s proves insufficient, add Option 2 (environment variable) for user customization.

### Testing

After fix, verify:
1. `azlin list` succeeds in WSL on first run (cold start)
2. Bastion detection succeeds with message "Detected Bastion host..."
3. Tunnel creation succeeds
4. Commands complete successfully

Test conditions:
- Fresh WSL session (no Azure CLI cache)
- First bastion operation (extension not yet loaded)
- Various network conditions

### Related Files

- **Primary**: `src/azlin/modules/bastion_detector.py` (lines 87, 262)
- **Tests**: `tests/unit/test_timeout_values.py` (validates timeout defaults)
- **Related PRs**: #575, #557, #520
- **Issue**: User reported bastion detection timing out in WSL

### Supporting Evidence

- PR #575 increased timeout from 2s → 10s for Windows/WSL2
- PR #557 increased other Azure CLI list operations to 30s
- Test runs show `az network bastion list` takes 8.3s (close to 10s limit)
- `az account show` pre-flight check takes <1s (not the bottleneck)

---

## Ubuntu Version Update Available - 24.04 LTS Supported (2026-01-17)

### Investigation Summary

Investigated current Ubuntu version used by azlin (22.04) and discovered that Azure now supports **Ubuntu 24.04 LTS (Noble Numbat)**, which is significantly newer and recommended for production use.

### Key Findings

**Current State**: azlin uses Ubuntu 22.04 (Jammy Jellyfish) in three locations
**Available**: Ubuntu 24.04 LTS (Noble Numbat) - latest LTS, released April 2024
**Compatibility**: All post-launch setup scripts (cloud-init) compatible with 24.04

#### Ubuntu Version Locations

Found three hardcoded references to Ubuntu 22.04:

1. **Terraform Strategy** (`src/azlin/agentic/strategies/terraform_strategy.py:481-486`)
   - Current: `offer = "0001-com-ubuntu-server-jammy"`, `sku = "22_04-lts-gen2"`
   - Update to: `offer = "ubuntu-24_04-lts"`, `sku = "server"`

2. **Azure CLI Strategy** (`src/azlin/agentic/strategies/azure_cli.py:413, 445`)
   - Current: `--image Ubuntu2204`
   - Update to: `--image Canonical:ubuntu-24_04-lts:server:latest`

3. **Sample Config/VM Provisioning** (`tests/fixtures/sample_configs.py:22, 119, 174` and `src/azlin/vm_provisioning.py:43`)
   - Current: `"image": "ubuntu-22.04"` and `image: str = "Ubuntu2204"`
   - Update to: `"image": "ubuntu-24.04"` and `image: str = "Ubuntu2404"`

#### Azure Image Details

Ubuntu 24.04 LTS available via:
- **Full URN**: `Canonical:ubuntu-24_04-lts:server:latest`
- **SKUs available**: server, minimal, server-arm64, cvm, ubuntu-pro
- **Recommendation**: Use `server` SKU for standard Gen2 VMs

#### Post-Launch Setup Compatibility Analysis

Reviewed cloud-init script in `vm_provisioning.py:702-799`:
- ✅ All package managers compatible (apt, snap, ppa)
- ✅ All packages available on Ubuntu 24.04
- ✅ Python 3.13 from deadsnakes PPA - works on 24.04
- ✅ GitHub CLI - architecture-independent
- ✅ Azure CLI - supports Ubuntu 24.04
- ✅ Node.js 20.x - supports Ubuntu 24.04
- ✅ Docker - available on 24.04

**Result**: No compatibility issues identified. All setup should work seamlessly.

### Recommendations

1. **Update default image to Ubuntu 24.04 LTS** in all three locations
2. **Test on single VM** before updating defaults
3. **Update documentation** to reflect new Ubuntu version
4. **Consider adding image parameter** to allow users to choose version

### Supporting Evidence

Azure CLI verification:
```bash
$ az vm image list --publisher Canonical --offer ubuntu-24_04-lts --sku server --all
# Returns multiple versions from 24.04.202404230 onwards
```

Available Ubuntu versions in Azure:
- Ubuntu 24.04 LTS (Noble) - **RECOMMENDED** - Latest LTS
- Ubuntu 23.10 (Mantic) - Available but short support
- Ubuntu 23.04 (Lunar) - EOL, not recommended
- Ubuntu 22.04 LTS (Jammy) - **CURRENT** - Still supported but older

### Lessons Learned

1. **Azure image naming conventions changed** - Old format: `0001-com-ubuntu-server-jammy`, New format: `ubuntu-24_04-lts`
2. **Always check cloud provider for newer LTS releases** - 24.04 has been available since April 2024
3. **Cloud-init scripts using standard package managers** are highly portable across Ubuntu versions

---

## UVX File Copying System Bug Fixes (2025-12-15)

### Problem

Two critical bugs in the UVX file copying system (Issue #1940):

**Bug #1**: Missing `should_proceed` check after user cancellation

- When user responds 'n' to conflict prompt, `should_proceed=False` is set
- Code continued to execute file operations anyway
- Files were overwritten despite user declining

**Bug #2**: Silent failure when no files copied

- When `copytree_manifest()` returns empty list (no files copied)
- Code silently continues as if everything succeeded
- User gets no feedback about the installation problem

### Root Cause

**Bug #1**: After calling `SafeCopyStrategy.determine_target()` (line 487-491), the code immediately used `copy_strategy.target_dir` without checking `copy_strategy.should_proceed`. User cancellation was recorded but not respected.

**Bug #2**: After calling `copytree_manifest()` (line 521), the code only checked `if copied:` for the success path but had no `if not copied:` error handling for the failure path.

### Solution

**Bug #1 Fix** (7 lines after line 491):

```python
# Bug #1 Fix: Respect user cancellation (Issue #1940)
# When user responds 'n' to conflict prompt, should_proceed=False
# Exit gracefully with code 0 (user-initiated cancellation, not an error)
if not copy_strategy.should_proceed:
    print("\n❌ Operation cancelled - cannot proceed without updating .claude/ directory")
    print("   Commit your changes and try again\n")
    sys.exit(0)
```

**Bug #2 Fix** (9 lines after line 521):

```python
# Bug #2 Fix: Detect empty copy results (Issue #1940)
# When copytree_manifest returns empty list, no files were copied
# This indicates a package installation problem - exit with clear error
if not copied:
    print("\n❌ Failed to copy .claude files - cannot proceed")
    print(f"   Package location: {amplihack_src}")
    print(f"   Looking for .claude/ at: {amplihack_src}/.claude/")
    print("   This may indicate a package installation problem\n")
    sys.exit(1)
```

**Import Fix**: Moved `copytree_manifest` import to module level (line 9) to make it patchable in tests.

### Implementation Details

- **Total Lines**: 17 lines (well under 30-line requirement per Proportionality Principle)
- **Test Coverage**: 4 tests, all passing (2 for each bug)
- **Philosophy Compliance**:
  - Zero-BS: Real error messages, clear exit codes
  - Ruthless Simplicity: Minimal code, maximum clarity
  - Fail-Fast: Detect problems immediately, don't proceed silently

### Key Insight

**Always check boolean flags after decision-making functions**. The pattern of "make decision → check decision → act" must be complete. Don't assume success paths are the only paths that need handling.

**Test Ratio**: 54 lines of test code / 17 lines of implementation = 3.2:1 (within target for business logic)

### Related Issues

- Issue #1940: UVX file copying bugs
- Pattern: Fail-Fast Prerequisite Checking (PATTERNS.md)
- Pattern: Zero-BS Implementation (PATTERNS.md)

---

## SessionStop Hook BrokenPipeError Race Condition (2025-12-13)

### Problem

Amplihack hangs during Claude Code exit. User suspected sessionstop hook causing the hang. Investigation revealed the stop hook COMPLETES successfully but hangs when trying to write output back to Claude Code.

### Root Cause

**BrokenPipeError race condition in `hook_processor.py`**:

1. Stop hook completes all logic successfully (Neo4j cleanup, power-steering, reflection)
2. Returns `{"decision": "approve"}` and tries to write to stdout
3. Claude Code has already closed the pipe/connection (timing race)
4. `sys.stdout.flush()` at line 169 raises `BrokenPipeError: [Errno 32] Broken pipe`
5. Exception handler (line 308) catches it and tries to call `write_output({})` AGAIN at line 331
6. Second write also fails with BrokenPipeError (same broken pipe)
7. No handler for second failure → HANG

**Evidence from logs:**

```
[2025-12-13T19:48:34] INFO: === STOP HOOK ENDED (decision: approve - no reflection) ===
[2025-12-13T19:48:34] ERROR: Unexpected error in stop: [Errno 32] Broken pipe
[2025-12-13T19:48:34] ERROR: Traceback:
  File "hook_processor.py", line 277: self.write_output(output)  ← FIRST FAILURE
  File "hook_processor.py", line 169: sys.stdout.flush()
BrokenPipeError: [Errno 32] Broken pipe
```

**Code Analysis:**

- `write_output()` called **4 times** (lines 277, 289, 306, 331) - all vulnerable
- **ZERO BrokenPipeError handling** anywhere in hooks directory
- Every exception handler tries to write output, potentially to broken pipe

### Solution

**Add BrokenPipeError handling to `write_output()` method in `hook_processor.py`:**

```python
def write_output(self, output: Dict[str, Any]):
    """Write JSON output to stdout, handling broken pipe gracefully."""
    try:
        json.dump(output, sys.stdout)
        sys.stdout.write("\n")
        sys.stdout.flush()
    except BrokenPipeError:
        # Pipe closed - Claude Code has already exited
        # Log but don't raise (fail-open design)
        self.log("Pipe closed during output write (non-critical)", "DEBUG")
    except IOError as e:
        if e.errno == errno.EPIPE:  # Broken pipe on some systems
            self.log("Broken pipe during output write (non-critical)", "DEBUG")
        else:
            raise  # Re-raise other IOErrors
```

**Alternative approach:** Wrap all `write_output()` calls in exception handlers (4 locations), but centralizing in the method is cleaner.

### Key Learnings

1. **Hook logic vs hook I/O** - The hook can work perfectly but fail on output writing
2. **Exception handlers can make things worse** - Retrying the same failed operation without checking
3. **Race conditions in pipe communication** - Claude Code can close pipes at ANY time, not just during hook logic
4. **Fail-open philosophy incomplete** - Recent fix (45778fcd) addressed `sys.exit(1)` but missed BrokenPipeError
5. **All hooks vulnerable** - Same `hook_processor.py` base class used by sessionstart, prompt-submit, etc.
6. **Log evidence is critical** - Hook completed successfully but logs showed BrokenPipeError during output write

### Related

- **File**: `.claude/tools/amplihack/hooks/hook_processor.py` (lines 161-169, 277, 289, 306, 331)
- **File**: `.claude/tools/amplihack/hooks/stop.py` (completes successfully, issue is in base class)
- **Recent fix**: Commit 45778fcd fixed `sys.exit(1)` but didn't address BrokenPipeError
- **Investigation methodology**: INVESTIGATION_WORKFLOW.md (6-phase systematic investigation)
- **Log evidence**: `.claude/runtime/logs/stop.log` shows "HOOK ENDED" followed by BrokenPipeError

### Remaining Questions

1. **Why does Claude Code close pipe prematurely?** (timeout? normal shutdown? hook execution time?)
2. **Frequency of race condition** - How often does this occur? Correlates with system load?
3. **Other hooks affected?** - All hooks use same base class, likely affects sessionstart too

---

## AI Agents Don't Need Human Psychology (2025-12-02)

### Problem

AI agents (Opus) achieving low workflow compliance (36-64% in early tests). Added psychological framing (Workflow Contract + Completion Celebration) to DEFAULT_WORKFLOW.md assuming it would help like it does for humans.

### Investigation

V8 testing: Builder agent created 5 worktrees with IDENTICAL content instead of 5 different variations. All had psychological elements REMOVED from DEFAULT_WORKFLOW.md (443 lines vs main's 482 lines).

### Discovery

**Removing psychological framing improves AI performance 72-95%**:

- MEDIUM: $2.93-$8.36 (avg $5.62), 100% compliance
- HIGH: $13.56-$31.95 (avg $21.72), 100% compliance
- Annual impact: ~$123K savings (90% reduction)

**Elements Removed** (39 lines):

1. Workflow Contract (lines 30-47): Commitment language
2. Completion Celebration (lines 462-482): Success celebration

### Root Cause

**Human psychology ≠ AI optimization**:

- AI already committed by design (psychology unnecessary)
- AI don't experience celebration (wasted tokens)
- Psychology = 8% overhead, 0% benefit for AI
- Less = more (token efficiency)

### Solution

**Remove psychological framing from AI-facing workflows**:

```markdown
# BEFORE (482 lines, WITH Psychology)

## Workflow Contract

By reading this workflow file, you are committing...
[17 lines of commitment psychology]

[22 Workflow Steps]

## 🎉 Workflow Complete!

Congratulations! You executed all 22 steps...
[22 lines of celebration psychology]

# AFTER (443 lines, WITHOUT Psychology)

[22 Workflow Steps - just the steps, no psychology]
```

### Validation

- Tests: 7 (3 MEDIUM + 4 HIGH complexity)
- Quality: 100% compliance (22/22 steps every test)
- Variance: High (136-185%) but averages excellent
- Philosophy: "Code you don't write has no bugs" applies to prompts!

### Impact

**Immediate**: 72-95% cost reduction, 76-90% time reduction
**Annual**: ~$123K saved, ~707 hours (18 work weeks)
**Quality**: 100% maintained (no degradation)

### Lessons

1. Don't assume human psychology helps AI - test first
2. Less is more for AI agents - remove non-essential
3. Apply philosophy to prompts - ruthless simplicity works
4. Builder can apply philosophy - autonomously removed complexity, was correct!
5. Forensic analysis essential - 3 wrong attributions before file diff revealed truth

### Related

- Issue #1785 (V8 testing results)
- Tag: v8-no-psych-winner
- Archive: .claude/runtime/benchmarks/v8_experiments_archive_20251202_212646/
- Docs: /tmp/⭐_START_HERE_ULTIMATE_GUIDE.md

---

## Mandatory User Testing Validates Its Own Value (2025-12-02)

### Problem

Parallel Task Orchestrator (Issue #1783) passed ALL unit tests but **failed completely** when tested as a user would:

```
uvx --from git+https://github.com/... amplihack /ultrathink "..."
```

The feature was non-functional despite comprehensive mocked testing.

### Root Cause

Unit tests used heavy mocking, hiding critical integration issues:
- `TaskDefinition` dataclass wasn't hashable (needed for dict keys)
- Async context manager protocols incomplete
- Import paths worked locally but failed in UVX packaging

### Discovery

**Mandatory user testing (from USER_PREFERENCES.md) caught bugs that 100% unit test coverage missed.**

This validates the learned pattern (2025-11-10): "I always want you to test each PR like a user would, from the outside in."

### Lessons Learned

1. **Always test like a user** - No mocks, real instantiation, actual workflows
2. **High coverage isn't enough** - Need real usage validation
3. **Mocks hide bugs** - Integration issues invisible to mocked tests
4. **User requirements are wise** - This explicit requirement saved us from shipping broken code

### Related

- Issue #1783: Parallel Task Orchestrator
- PR #1784: Implementation
- USER_PREFERENCES.md: Mandatory E2E testing requirement
- Commit dc90b350: Hashability fix

### Recommendation

**ENFORCE mandatory user testing** for ALL features:

- Test with `uvx --from git+...` (no local state)
- Try actual user workflows (no mocks)
- Verify error messages and UX
- Document test results in PR

This discovery **validates the user's explicit requirement** - mandatory user testing prevents production failures that unit tests miss.

---

## GitHub Pages MkDocs Deployment Requires docs/.claude/ Copy (2025-12-02)

**Issue**: #1827
**PR**: #1829

**Context**: GitHub Pages documentation deployment was failing with 133 mkdocs warnings and 305 total broken links. The mkdocs build couldn't find `.claude/` content referenced in navigation.

**Problem**: MkDocs expects all content in `docs/` directory, but our `.claude/` directory (containing agents, workflows, commands, skills) was at project root. Navigation links to `.claude/` files resulted in 404s.

**Solution**: Copy entire `.claude/` structure to `docs/.claude/` (776 files)

**Why This Works**:

- MkDocs site_dir scans `docs/` by default
- All navigation references now resolve correctly
- Cross-references between docs preserved
- No complex symlinks or build scripts needed

**Implementation**:

```bash
# Copy .claude/ to docs/.claude/
cp -r .claude docs/.claude

# Update mkdocs.yml navigation to reference docs/.claude/ paths
# Example: '.claude/agents/architect.md' works in navigation
```

**Impact**:

- ✅ mkdocs build succeeds (was failing with 133 warnings)
- ✅ GitHub Pages deployment unblocked
- ✅ All framework documentation accessible in docs site
- ✅ 305 broken links resolved

**Trade-offs**:

- **Pros**: Ruthlessly simple, no build complexity, works immediately
- **Cons**: Duplicates `.claude/` content (+776 files in docs/), increases repo size by ~1MB

**Philosophy Alignment**: ✅ Ruthless Simplicity

- Avoided complex symlink solutions
- No custom build scripts needed
- Zero-BS implementation (everything works)
- Modular (can be regenerated easily)

**Alternatives Considered**:

1. **Symlinks**: Would break on Windows, adds complexity
2. **Build script**: Adds build-time dependency, complexity
3. **Git submodules**: Overkill, adds workflow friction
4. **Custom MkDocs plugin**: Over-engineering for simple problem

**Lessons Learned**:

1. MkDocs `docs/` directory is the source of truth - work with it, not against it
2. File duplication is acceptable when it eliminates build complexity
3. For documentation systems, **copying > symlinking** for portability
4. Always test mkdocs build locally before pushing docs changes

**Prevention**:

- Add `mkdocs build --strict` to CI/GitHub Actions
- Catches broken navigation before deployment
- Test with: `mkdocs build && mkdocs serve` locally

**Related Patterns**:

- Ruthless Simplicity (PHILOSOPHY.md)
- Zero-BS Implementation (PATTERNS.md)

**Tags**: #documentation #mkdocs #github-pages #deployment #simplicity

---

## System Metadata vs User Content in Git Conflict Detection (2025-12-01)

### Problem

User reported: "amplihack's copytree_manifest fails when .claude/ has uncommitted changes" specifically with `.claude/.version` file modified. Despite having a comprehensive safety system (GitConflictDetector + SafeCopyStrategy), deployment proceeded without warning and created a version mismatch state.

### Root Cause

The `.version` file is a **system-generated tracking file** that stores the git commit hash of the deployed amplihack package. The issue occurred due to a semantic classification gap:

1. **Git Status Detection**: `GitConflictDetector._get_uncommitted_files()` correctly detects ALL uncommitted files including `.version` (status: M)

2. **Filtering Logic Gap**: `_filter_conflicts()` at lines 82-97 in `git_conflict_detector.py` only checks files against ESSENTIAL_DIRS patterns:

   ```python
   for essential_dir in essential_dirs:
       if relative_path.startswith(essential_dir + "/"):
           conflicts.append(file_path)
   ```

3. **ESSENTIAL_DIRS Are All Subdirectories**: `["agents/amplihack", "commands/amplihack", "context/", ...]` - all contain "/"

4. **Root-Level Files Filtered Out**: `.version` at `.claude/.version` doesn't match any pattern → filtered OUT → `has_conflicts = False`

5. **No Warning Issued**: SafeCopyStrategy sees no conflicts, proceeds to working directory without prompting user

6. **Version Mismatch Created**: copytree_manifest copies fresh directories but **doesn't copy `.version`** (not in ESSENTIAL_FILES), leaving stale version marker with fresh code

### Solution

Exclude system-generated metadata files from conflict detection by adding explicit categorization:

```python
# In src/amplihack/safety/git_conflict_detector.py

SYSTEM_METADATA = {
    ".version",        # Framework version tracking (auto-generated)
    "settings.json",   # Runtime settings (auto-generated)
}

def _filter_conflicts(
    self, uncommitted_files: List[str], essential_dirs: List[str]
) -> List[str]:
    """Filter uncommitted files for conflicts with essential_dirs."""
    conflicts = []
    for file_path in uncommitted_files:
        if file_path.startswith(".claude/"):
            relative_path = file_path[8:]

            # Skip system-generated metadata - safe to overwrite
            if relative_path in SYSTEM_METADATA:
                continue

            # Existing filtering logic for essential directories
            for essential_dir in essential_dirs:
                if (
                    relative_path.startswith(essential_dir + "/")
                    or relative_path == essential_dir
                ):
                    conflicts.append(file_path)
                    break
    return conflicts
```

**Rationale**:

- **Semantic Classification**: Filter by PURPOSE (system vs user), not just directory structure
- **Ruthlessly Simple**: 3-line change, surgical fix
- **Philosophy-Aligned**: Treats system files appropriately (not user content)
- **Zero-BS**: Fixes exact issue without over-engineering

### Key Learnings

1. **Root-Level Files Need Special Handling**: Directory-based filtering (checking for "/") misses root-level files entirely. System metadata often lives at root.

2. **Semantic > Structural Classification**: Git conflict detection should categorize by FILE PURPOSE (user-managed vs system-generated), not just location patterns.

3. **Auto-Generated Files vs User Content**: Framework metadata files like `.version`, `*.lock`, `.state` should never trigger conflict warnings - they're infrastructure, not content.

4. **ESSENTIAL_DIRS Pattern Limitation**: Works great for subdirectories (`context/`, `tools/`), but silently excludes root-level files. Need explicit system file list.

5. **False Negatives Are Worse Than False Positives**: Safety system failing to warn about user content is bad, but warning about system files breaks user trust and workflow.

6. **Version Files Are Special**: Any framework with version tracking faces this - `.version`, `.state`, `.lock` files should be treated as disposable metadata, not user content to protect.

### Related Patterns

- See PATTERNS.md: "System Metadata vs User Content Classification" - NEW pattern added from this discovery
- Relates to "Graceful Environment Adaptation" (different file handling per environment)
- Reinforces "Fail-Fast Prerequisite Checking" (but needs correct semantic classification)

### Impact

- **Affects**: All deployments where `.version` or other system metadata has uncommitted changes
- **Frequency**: Common after updates (`.version` auto-updated but not committed)
- **User Experience**: Confusing "version mismatch" errors despite fresh deployment
- **Fix Priority**: High - breaks user trust in safety system

### Verification

Test cases added:

- Uncommitted `.version` doesn't trigger conflict warning ✅
- Uncommitted user content (`.claude/context/custom.md`) DOES trigger warning ✅
- Deployment proceeds smoothly with modified `.version` ✅
- Version mismatch detection still works correctly ✅

---

## Auto Mode Timeout Causing Opus Model Workflow Failures (2025-11-26)

### Problem

Opus model was "skipping" workflow steps during auto mode execution. Investigation revealed the 5-minute per-turn timeout was cutting off Opus execution mid-workflow due to extended thinking requirements.

### Root Cause

The default per-turn timeout of 5 minutes was too aggressive for Opus model, which requires extended thinking time. Log analysis showed:

- `Turn 2 timed out after 300.0s`
- `Turn 1 timed out after 600.1s`

### Solution (PR #1676)

Implemented flexible timeout resolution system:

1. **Increased default timeout**: 5 min → 30 min
2. **Added `--no-timeout` flag**: Disables timeout entirely using `nullcontext()`
3. **Opus auto-detection**: Model names containing "opus" automatically get 60 min timeout
4. **Clear priority system**: `--no-timeout` > explicit > auto-detect > default

### Key Insight

**Extended thinking models like Opus need significantly longer timeouts.** Auto-detection based on model name provides a good default without requiring users to remember to adjust settings.

### Files Changed

- `src/amplihack/cli.py`: Added `--no-timeout` flag and `resolve_timeout()` function
- `src/amplihack/launcher/auto_mode.py`: Accept `None` timeout using `nullcontext`
- `tests/unit/test_auto_mode_timeout.py`: 19 comprehensive tests
- `docs/AUTO_MODE.md`: Added timeout configuration documentation

---

## Power-Steering Session Type Detection Fix (2025-11-25)

### Problem

Power-steering incorrectly blocking investigation sessions with development-specific checks. Sessions like "Investigate SSH issues" were misclassified as DEVELOPMENT.

### Root Cause

`detect_session_type()` relied solely on tool-based heuristics. Troubleshooting sessions involve Bash commands and doc updates, matching development patterns.

### Solution

Added **keyword-based detection** with priority over tool heuristics. Check first 5 user messages for investigation keywords (investigate, troubleshoot, diagnose, debug, analyze).

### Key Learnings

**User intent (keywords) is more reliable than tool usage patterns** for session classification.

---

## Transcripts System Investigation (2025-11-22)

### Problem

Needed validation of amplihack's transcript architecture vs Microsoft Amplifier approach.

### Key Findings

(Investigation content omitted for brevity - see archive)

---

## Entry Format Template

```markdown
## [Brief Title] (YYYY-MM-DD)

### Problem

What challenge was encountered?

### Root Cause

Why did this happen?

### Solution

How was it resolved? Include code if relevant.

### Key Learnings

What insights should be remembered?
```
