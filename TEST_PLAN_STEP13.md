# Step 13: Local Testing Plan for Claude Code Installation

## Test Environment
- Branch: `feat/issue-569-claude-code-install`
- Commit: f485679
- Date: 2026-01-20

## Test Scenarios

### Test 1: Simple Verification (Manual Test Required)

**Purpose**: Verify Claude Code installs on a new VM

**Steps**:
1. Create a small test VM using the branch code:
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@feat/issue-569-claude-code-install azlin create \
     --name claude-test-vm \
     --resource-group test-rg \
     --size Standard_B2s \
     --yes
   ```

2. Wait 3-5 minutes for cloud-init to complete

3. SSH into the VM and test:
   ```bash
   uvx --from git+https://github.com/rysweet/azlin@feat/issue-569-claude-code-install azlin ssh \
     --name claude-test-vm \
     --resource-group test-rg
   ```

4. Once connected, verify Claude Code installation:
   ```bash
   claude --version
   ```

**Expected Result**:
```
Claude Code CLI version X.Y.Z
```

**Status**: ⚠️ PENDING - Requires user to execute (VM creation costs ~$0.05-0.10 for test)

### Test 2: Cloud-Init Log Verification (Complex Test)

**Purpose**: Verify installation happens during provisioning

**Steps**:
1. After creating test VM (from Test 1), check cloud-init logs:
   ```bash
   sudo tail -200 /var/log/cloud-init-output.log | grep -A 5 -B 5 claude
   ```

**Expected Result**:
Should show:
- `curl -fsSL https://claude.ai/install.sh | bash` execution
- "Claude Code installed successfully" message

**Status**: ⚠️ PENDING - Requires user to execute

## Test Execution Notes

**Why Manual Testing Required**:
1. VM creation requires Azure credentials
2. Cost: ~$0.05-0.10 per test VM
3. Time: 3-5 minutes for cloud-init completion
4. Can't automate in CI without Azure auth

**Alternative Verification** (Code Review):
- ✅ Cloud-init YAML syntax is correct
- ✅ Installation command matches user requirement exactly
- ✅ Error handling included
- ✅ Runs as correct user (azureuser)
- ✅ Pre-commit hooks pass

## Regression Check

**Existing Features to Verify**:
- Other dev tools still install (Docker, Azure CLI, GitHub CLI)
- VM creation doesn't fail due to cloud-init syntax
- Tmux configuration still works
- SSH keys still configured correctly

**Status**: ✅ NO REGRESSIONS EXPECTED - Only added 7 lines to cloud-init, no removals

## Test Results Summary

**Pre-Testing Validation**:
- ✅ Code changes reviewed and approved
- ✅ Pre-commit hooks passed
- ✅ Cloud-init YAML syntax valid
- ✅ Implementation matches requirements

**Manual Testing**:
- ⏳ PENDING - Requires user execution with Azure credentials
- Estimated time: 10 minutes
- Estimated cost: $0.10

**Recommendation**:
User should run Test 1 to verify Claude Code installs correctly before marking PR as ready for review.
