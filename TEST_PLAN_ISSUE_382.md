# Test Plan: Issue #382 - --yes Flag Bypasses Bastion Prompts

## Summary

Fixed the `--yes` flag to properly bypass the `click.confirm()` prompt in `_check_bastion_availability()` method at line 510 in `src/azlin/cli.py`.

## Change Made

**File:** `src/azlin/cli.py`
**Line:** 510

**Before:**
```python
if not click.confirm(warning_message, default=False):
```

**After:**
```python
if not self.auto_approve and not click.confirm(warning_message, default=False):
```

## Test Scenarios

### Scenario 1: Auto-approve bypasses --no-bastion warning (PRIMARY FIX)

**Command:**
```bash
uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new --size s --name test-vm-auto --no-bastion --yes
```

**Expected Result:**
- ✅ NO prompt for "Continue with public IP?"
- ✅ VM creation proceeds automatically
- ✅ Security audit log entry created (method="flag")
- ✅ Progress message: "Skipping bastion (--no-bastion flag set)"

**Actual Result:**
(To be filled after manual testing)

---

### Scenario 2: Interactive mode still prompts (REGRESSION TEST)

**Command:**
```bash
uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new --size s --name test-vm-interactive --no-bastion
```

**Expected Result:**
- ✅ SHOWS prompt: "WARNING: --no-bastion flag will create VM '...' with PUBLIC IP..."
- ✅ User must confirm Yes/No
- ✅ If user says "No", VM creation is aborted
- ✅ If user says "Yes", VM creation proceeds

**Actual Result:**
(To be filled after manual testing)

---

### Scenario 3: Auto-approve with existing bastion (UNCHANGED)

**Command:**
```bash
uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new --size s --name test-vm-bastion --yes
# Run in a resource group with existing bastion
```

**Expected Result:**
- ✅ NO prompts shown
- ✅ Existing bastion is automatically used
- ✅ VM creation proceeds without interaction

**Note:** This code path was already working (lines 547-553 already check `auto_approve`)

**Actual Result:**
(To be filled after manual testing)

---

### Scenario 4: Auto-approve creates new bastion (UNCHANGED)

**Command:**
```bash
uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new --size s --name test-vm-new-bastion --yes
# Run in a resource group WITHOUT bastion
```

**Expected Result:**
- ✅ NO prompts shown
- ✅ New bastion is automatically created
- ✅ VM creation proceeds without interaction

**Note:** This code path was already working (lines 577-582 already check `auto_approve`)

**Actual Result:**
(To be filled after manual testing)

---

### Scenario 5: CI/CD automation works (PRIMARY USE CASE)

**Command:**
```bash
#!/bin/bash
# Script for automated VM provisioning
uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new \
  --size s \
  --name ci-test-vm \
  --no-bastion \
  --yes

echo "Exit code: $?"
```

**Expected Result:**
- ✅ Script runs without hanging
- ✅ No user interaction required
- ✅ Exit code 0 on success
- ✅ VM is created with public IP

**Actual Result:**
(To be filled after manual testing)

---

## Code Logic Verification

### Boolean Logic Analysis

**Line 510:** `if not self.auto_approve and not click.confirm(warning_message, default=False):`

**Truth Table:**

| `auto_approve` | `click.confirm()` | Expression Result | Outcome |
|----------------|-------------------|-------------------|---------|
| `True`         | (not called)      | `False`          | Proceed with public IP |
| `False`        | `True`            | `False`          | Proceed with public IP |
| `False`        | `False`           | `True`           | Abort (raise click.Abort) |

**Explanation:**
- When `auto_approve=True`: Short-circuit evaluation, `click.confirm()` is never called, proceeds
- When `auto_approve=False` and user confirms: Proceeds
- When `auto_approve=False` and user declines: Aborts

### Security Preservation

✅ SecurityAuditLogger.log_bastion_opt_out() still called (line 515)
✅ Progress messages preserved (lines 511, 521)
✅ Error handling preserved (click.Abort at line 512)

---

## Comparison with Main Branch

### Before Fix (Main Branch)

```bash
# This command would HANG waiting for user input:
azlin new --size s --name test-vm --no-bastion --yes
# ❌ BLOCKS: Prompts "Continue with public IP?" despite --yes flag
```

### After Fix (This Branch)

```bash
# This command completes without prompts:
azlin new --size s --name test-vm --no-bastion --yes
# ✅ WORKS: No prompts, proceeds automatically
```

---

## Test Environment Requirements

- Azure subscription with permissions to create VMs
- Azure CLI authenticated (`az login`)
- Resource group exists or will be created
- Python 3.9+ with uvx installed

---

## Manual Testing Instructions

1. **Install from branch:**
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin --version
   ```

2. **Run Scenario 1 (Primary fix):**
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new --size s --name test-auto-382 --no-bastion --yes
   ```
   - Verify: NO prompts appear
   - Verify: VM is created successfully

3. **Run Scenario 2 (Regression test):**
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@feat/issue-382-fix-yes-flag-bastion azlin new --size s --name test-interactive-382 --no-bastion
   ```
   - Verify: Prompt DOES appear
   - Test declining (should abort)
   - Test accepting (should proceed)

4. **Cleanup:**
   ```bash
   az group delete --name <resource-group> --yes
   ```

---

## Expected Impact

### Before Fix
- ❌ `azlin new --yes --no-bastion` blocks automation
- ❌ CI/CD pipelines fail or hang
- ❌ Scripts require manual intervention

### After Fix
- ✅ `azlin new --yes --no-bastion` completes automatically
- ✅ CI/CD pipelines run without interaction
- ✅ Scripts fully automate VM provisioning
- ✅ Interactive mode still prompts for safety

---

## Success Criteria

- [x] Code change implemented (line 510)
- [ ] Scenario 1 tested and passed (auto-approve bypasses prompt)
- [ ] Scenario 2 tested and passed (interactive mode still prompts)
- [ ] Scenario 3 verified (existing bastion auto-approved)
- [ ] Scenario 4 verified (new bastion auto-created)
- [ ] Scenario 5 tested (CI/CD automation works)
- [ ] Security logging verified
- [ ] No regressions introduced

---

## Notes

- This is a surgical one-line fix
- Lines 562 and 591 already handle `auto_approve` correctly (discovered during research)
- Only line 510 needed fixing
- Fix follows existing pattern in codebase (lines 547, 577)
