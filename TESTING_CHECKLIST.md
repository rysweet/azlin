# Testing Checklist for Issue #499: Tmux Session Connection Status

## Local Testing Requirements

**CRITICAL**: Test this feature with real Azure VMs and tmux sessions before merging.

### Setup Test Environment

1. **Create test VMs with tmux sessions:**
   ```bash
   # On a test VM, create multiple tmux sessions
   tmux new-session -d -s connected-session
   tmux new-session -d -s disconnected-session

   # Attach to one session to make it "connected"
   tmux attach -t connected-session
   # (Detach with Ctrl+B, D)
   ```

2. **Verify tmux version supports new format:**
   ```bash
   tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}"
   ```

### Test Cases

#### Test 1: Basic Functionality
```bash
azlin list --tmux
```

**Expected:**
- Connected sessions appear in **BOLD** text
- Disconnected sessions appear in **DIM** text
- Session names are clearly distinguishable

**Verify:**
- [ ] Connected sessions are visually brighter/bolder
- [ ] Disconnected sessions are visually dimmer
- [ ] Distinction is clear in both light and dark terminal themes

#### Test 2: Mixed Session States
```bash
# Create multiple sessions with different states
tmux new-session -d -s session1
tmux new-session -d -s session2
tmux new-session -d -s session3

# Attach to session2
tmux attach -t session2
# Detach

azlin list --tmux
```

**Expected:**
- session1: DIM (disconnected)
- session2: BOLD (connected - you just attached)
- session3: DIM (disconnected)

**Verify:**
- [ ] Only the attached session appears bold
- [ ] Other sessions appear dim
- [ ] Format is consistent across all VMs

#### Test 3: No Tmux Sessions
```bash
# On a VM with no tmux sessions
tmux kill-server  # (if any exist)

azlin list --tmux
```

**Expected:**
- "No sessions" or "-" displayed
- No errors or crashes

**Verify:**
- [ ] Graceful handling of VMs without tmux
- [ ] No error messages
- [ ] Command completes successfully

####Test 4: Terminal Compatibility
Test in multiple terminal emulators:

**Verify:**
- [ ] iTerm2 (macOS): Bold/dim rendering works
- [ ] Terminal.app (macOS): Bold/dim rendering works
- [ ] Windows Terminal: Bold/dim rendering works
- [ ] VSCode integrated terminal: Bold/dim rendering works

#### Test 5: Performance
```bash
# Time the command with multiple VMs
time azlin list --tmux
```

**Expected:**
- No performance degradation compared to previous version
- <10% overhead acceptable

**Verify:**
- [ ] Command execution time similar to baseline
- [ ] No noticeable delays
- [ ] Scales well with multiple VMs

#### Test 6: Security - Malicious Session Names
```bash
# Test Rich markup injection prevention
tmux new-session -d -s "[red]FAKE[/red]"
tmux new-session -d -s "[link=http://evil.com]click[/link]"

azlin list --tmux
```

**Expected:**
- Markup is displayed literally (escaped)
- No red coloring, no clickable links
- Brackets visible as text

**Verify:**
- [ ] Markup is not interpreted
- [ ] Session names display safely
- [ ] No clickable or styled elements from malicious names

#### Test 7: Old Tmux Version Fallback
```bash
# If possible, test on a VM with older tmux
# (one that doesn't support -F format flag)

azlin list --tmux
```

**Expected:**
- Graceful fallback to old format
- Sessions still displayed (may not have connection status)
- No errors

**Verify:**
- [ ] Works with older tmux versions
- [ ] Degrades gracefully if new format unsupported

### Edge Cases

#### Test 8: Session Name with Special Characters
```bash
tmux new-session -d -s "my-session:name"
tmux new-session -d -s "session with spaces"

azlin list --tmux
```

**Verify:**
- [ ] Special characters handled correctly
- [ ] Spaces in names don't break display
- [ ] Colons in names don't confuse parser

#### Test 9: Many Sessions
```bash
# Create 10+ sessions
for i in {1..15}; do
  tmux new-session -d -s "session$i"
done

azlin list --tmux
```

**Verify:**
- [ ] Handles many sessions without issues
- [ ] Display is readable (may show "+N more")
- [ ] No performance issues

### Regression Testing

**Verify existing functionality still works:**
- [ ] `azlin list` (without --tmux) still works
- [ ] Other azlin commands unaffected
- [ ] No new errors in logs
- [ ] All existing tests still pass

### Documentation

After testing, verify documentation matches behavior:
- [ ] Read `docs/features/tmux-session-status.md`
- [ ] Confirm examples match actual output
- [ ] Check troubleshooting section is accurate

### Test Results

**Record your findings:**
```
Date: ___________
Tester: ___________

Test 1 (Basic): ☐ PASS ☐ FAIL
Test 2 (Mixed States): ☐ PASS ☐ FAIL
Test 3 (No Sessions): ☐ PASS ☐ FAIL
Test 4 (Terminal Compat): ☐ PASS ☐ FAIL
Test 5 (Performance): ☐ PASS ☐ FAIL
Test 6 (Security): ☐ PASS ☐ FAIL
Test 7 (Fallback): ☐ PASS ☐ FAIL
Test 8 (Special Chars): ☐ PASS ☐ FAIL
Test 9 (Many Sessions): ☐ PASS ☐ FAIL

Regressions: ☐ NONE ☐ FOUND (describe below)

Notes:
___________________________________________
___________________________________________
___________________________________________
```

## Sign-off

**I certify that:**
- [ ] All test cases above executed successfully
- [ ] No regressions detected
- [ ] Feature works as documented
- [ ] Ready for merge

**Signature:** ___________  **Date:** ___________
