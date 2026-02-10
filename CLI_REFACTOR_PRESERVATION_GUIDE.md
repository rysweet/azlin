# CLI Refactor Preservation Guide

**Purpose**: Document EXACTLY what must be preserved when redoing the CLI refactor
**Date**: 2026-02-10
**Related Issue**: #604

---

## Critical Code Sections to Preserve

### 1. Tmux Session Collection (MOST CRITICAL!)

**Location**: `src/azlin/cli.py` lines 3176-3229

**Function**: `_collect_tmux_sessions(vms: list[VMInfo]) -> dict[str, list[TmuxSession]]`

**What it does**:
- Classifies VMs into direct SSH (public IP) and Bastion (private IP only)
- Uses `TmuxSessionExecutor.get_sessions_parallel()` to query sessions in parallel
- Handles both connection types with different timeouts:
  - Direct SSH: 5s timeout
  - Bastion: 15s timeout (routing latency)
- Returns dict mapping VM name → list of actual tmux sessions

**CRITICAL**: This function MUST be preserved exactly as-is or refactored WITHOUT breaking functionality.

---

### 2. List Command Structure

**Location**: `src/azlin/cli.py` lines 3593-4150

**Key behaviors**:

#### A. Bastion Hosts Display FIRST (line 3936-3960)
```python
# List Bastion hosts BEFORE VMs table (moved from end)
if rg:
    bastions = BastionDetector.list_bastions(rg)
    if bastions:
        bastion_table = Table(
            title="Azure Bastion Hosts", show_header=True, header_style="bold"
        )
        # ... display bastion table
        console.print(bastion_table)
        console.print()  # Spacing before VM table
```

**CRITICAL**: Bastion hosts MUST appear before VMs, not after.

#### B. Tmux Session Collection (lines 3809-3878)
```python
if show_tmux:
    # Check cache, collect if stale/missing
    tmux_by_vm = _collect_tmux_sessions(vms)
    # Cache the results
```

**CRITICAL**: Must actually call `_collect_tmux_sessions(vms)` not just return empty dict.

#### C. Table Column Layout (lines 3970-4016)

**Default mode** (NOT wide, NOT compact):
1. Session (width 14, cyan)
2. Tmux Sessions (width 40, magenta) - 2nd position!
3. Status (width 8)
4. IP (width 18, yellow)
5. Region (width 8)
6. CPU (width 4, right-justified) - just the number!
7. Mem (width 6, right-justified) - just "X GB"!

**CRITICAL**:
- Tmux Sessions column comes 2nd
- CPU shows just number (e.g., "32"), NOT full SKU
- Mem shows just value (e.g., "256 GB"), NOT verbose format

#### D. Tmux Session Display Logic (lines 4055-4075)
```python
if show_tmux:
    if vm.name in tmux_by_vm:
        sessions = tmux_by_vm[vm.name]
        # Format up to 3 sessions
        # Bold for attached, dim for detached
        session_names = ", ".join(formatted_sessions)
        row_data.append(session_names)
    elif vm.is_running():
        row_data.append("[dim]No sessions[/dim]")  # Only if running and no sessions
    else:
        row_data.append("-")  # Stopped VMs
```

**CRITICAL**: Shows actual session names from `tmux_by_vm` dict.

#### E. IP Display with (Bast) Indicator (lines 4034-4040)
```python
ip = (
    f"{vm.public_ip} (Public)"
    if vm.public_ip
    else f"{vm.private_ip} (Bast)"  # Clean "(Bast)" not "(Private)"!
    if vm.private_ip
    else "N/A"
)
```

**CRITICAL**: Use "(Bast)" for bastion-connected VMs, NOT "(Private)".

---

### 3. Helper Functions to Preserve

**Location**: Lines 3031-3154

These functions MUST be extracted with the list command:

- `_get_config_int()` (line 3044)
- `_get_config_float()` (line 3061)
- `_create_tunnel_with_retry()` (line 3078)
- `get_vm_session_pairs()` (line 3157) - Used by restore command
- `_collect_tmux_sessions()` (line 3176) - **MOST CRITICAL**

---

## What Went Wrong in Previous Refactor

The refactor (commit fd3ce0a) was based on a branch that forked BEFORE these improvements:
- PR #587: Enhanced azlin list display (tmux count, renamed Size→SKU, rebalanced columns)
- PR #592: List/restore reliability improvements (tmux detection, caching)

When the refactor merged, it overwrote the improvements with old code that:
1. Didn't call `_collect_tmux_sessions()` properly
2. Changed table column order (VMs first, Bastion last)
3. Added unwanted columns (VM Name separate from Session, full SKU names)
4. Lost compact CPU/Mem display (32, 256 GB → verbose SKU format)
5. Changed "(Bast)" to "(Private)"
6. Lost tmux session count in summary

---

## Test Checklist for Refactor

Before merging the refactor, verify ALL these behaviors:

### Table Display
- [ ] Bastion hosts table appears FIRST (before VMs)
- [ ] Column order: Session | Tmux Sessions | Status | IP | Region | CPU | Mem
- [ ] CPU shows just number (e.g., "32")
- [ ] Mem shows just value (e.g., "256 GB")
- [ ] IP shows "(Bast)" for bastion-connected VMs
- [ ] Tmux Sessions column width is 40 (not too narrow)

### Tmux Detection
- [ ] Shows ACTUAL tmux session names (azlin, kuzu-blarify, myca, etc.)
- [ ] NOT "No sessions" for VMs that have sessions
- [ ] Uses `_collect_tmux_sessions()` function
- [ ] Handles both direct SSH and Bastion tunneling
- [ ] Formats attached sessions as bold, detached as dim

### Summary Line
- [ ] Includes "X tmux sessions" count
- [ ] Example: "Total: 6 VMs | 10 tmux sessions"

### Cache Behavior
- [ ] Shows "[CACHE HIT]" when using cached data
- [ ] Shows "[CACHE MISS]" when fetching fresh
- [ ] Tmux sessions have 5min TTL
- [ ] VM list has 60min TTL

---

## Refactoring Strategy

### Step 1: Save Working Code
```bash
# Before starting, save the working list command
git checkout main
git show HEAD:src/azlin/cli.py > /tmp/working_list_command.py
# Extract lines 3030-4150 to preserve
```

### Step 2: Create New Branch
```bash
git checkout -b cli-refactor-v2-proper
```

### Step 3: Extract Commands EXCEPT List
First extract all OTHER commands (batch, connectivity, env, keys, lifecycle, nlp, provisioning, snapshots, templates, web) to separate modules.

**DO NOT touch** the list command yet.

### Step 4: Extract List Command Last
Only after all other commands are extracted, carefully extract the list command:

1. Create `src/azlin/commands/monitoring.py`
2. Copy the ENTIRE working list command (lines 3593-4150)
3. Copy ALL helper functions (lines 3030-3176)
4. Import ALL dependencies
5. Test with `/tmp/test-list-behavior.sh`
6. Compare output side-by-side with main branch

### Step 5: Verify No Regressions
```bash
# Run the test script
bash /tmp/test-list-behavior.sh

# Visual comparison
azlin list > /tmp/after-refactor.txt
git stash  # Stash changes temporarily
azlin list > /tmp/before-refactor.txt
git stash pop
diff /tmp/before-refactor.txt /tmp/after-refactor.txt
```

**CRITICAL**: If ANY differences appear, DO NOT merge until fixed.

---

## File Structure After Refactor

```
src/azlin/commands/
├── __init__.py          # Import all commands
├── monitoring.py        # List, status, top, w, ps commands + _collect_tmux_sessions
├── batch.py
├── connectivity.py
├── env.py
├── keys.py
├── lifecycle.py
├── nlp.py
├── provisioning.py
├── snapshots.py
├── templates.py
└── web.py

src/azlin/cli.py         # Reduced from 10K to ~2.5K lines
```

---

## Critical Imports for monitoring.py

When extracting list command to `monitoring.py`, these imports are REQUIRED:

```python
from azlin.modules.bastion_detector import BastionDetector
from azlin.modules.bastion_manager import BastionManagerError
from azlin.network_security.bastion_connection_pool import (
    BastionConnectionPool,
    PooledTunnel,
)
from azlin.modules.ssh_keys import SSHKeyManager, SSHKeyError
from azlin.remote_exec import TmuxSessionExecutor
from azlin.distributed_top import TmuxSession
from azlin.ssh.ssh_config import SSHConfig
from azlin.cache.vm_list_cache import VMListCache
from rich.console import Console
from rich.table import Table
from rich.markup import escape
```

---

## Testing Commands

```bash
# Test default list
azlin list

# Test with tmux (should show actual sessions)
azlin list

# Test wide mode
azlin list -w

# Test compact mode (should exist)
azlin list --compact

# Test cache hit
azlin list  # First call
azlin list  # Second call should show [CACHE HIT]

# Test restore (uses same tmux detection)
azlin list -r
```

---

## Success Criteria

The refactor is ready to merge ONLY when:

1. ✅ All test commands produce IDENTICAL output to main branch (before refactor)
2. ✅ Test script `/tmp/test-list-behavior.sh` passes 100%
3. ✅ Side-by-side diff shows ZERO differences in output
4. ✅ Tmux session detection works for all VMs
5. ✅ Bastion hosts appear at top
6. ✅ Column layout matches exactly
7. ✅ Summary line includes tmux count

---

**DO NOT MERGE** until ALL success criteria are met and verified by the user.
