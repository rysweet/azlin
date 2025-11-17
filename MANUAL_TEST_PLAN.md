# Manual Test Plan for Issue #310: Two-Phase Intent Clarification

## Prerequisites
- `export ANTHROPIC_API_KEY=your-key-here`
- Azure CLI authenticated (`az login`)
- Active Azure subscription

## Test Scenarios

### 1. Complex Request (Clarification Triggered) - Original Bug Report
```bash
azlin do "create 23 new storage blobs all containing a single integer number in a text file: 42."
```

**Expected Behavior:**
- Should trigger clarification
- Display clear, numbered steps
- Ask for confirmation
- Generate commands successfully
- Confidence should be > 0.7

**Success Criteria:**
- No "empty commands" issue
- Clear clarification displayed
- User can confirm/cancel
- Commands are generated after confirmation

### 2. Simple Request (Fast Path)
```bash
azlin do "list all vms"
```

**Expected Behavior:**
- Should skip clarification (fast path)
- Direct to command generation
- No added latency

**Success Criteria:**
- Clarification not triggered
- Immediate command display
- Normal execution flow

### 3. User Cancels Clarification
```bash
azlin do "create 10 vms with custom settings"
# When prompted, select "n" (no)
```

**Expected Behavior:**
- Clarification displayed
- User cancels
- Clean exit with helpful message

**Success Criteria:**
- No error messages
- Graceful exit
- Suggestion to rephrase

### 4. API Error Fallback
```bash
# Temporarily set invalid API key
export ANTHROPIC_API_KEY=invalid
azlin do "create 5 storage accounts"
```

**Expected Behavior:**
- Clarification fails
- Falls back to direct parsing
- Warning message shown
- Original request still processed

**Success Criteria:**
- No crashes
- Fallback works
- Clear error message

### 5. Verbose Mode
```bash
azlin do "create 3 VMs for testing" --verbose
```

**Expected Behavior:**
- Shows clarification decision process
- Displays "[Clarification needed - analyzing request...]"
- Shows when using clarified request

**Success Criteria:**
- Detailed output shown
- User understands what's happening
- No confusion about process

### 6. With --yes Flag
```bash
azlin do "create 5 blob containers" --yes
```

**Expected Behavior:**
- Clarification happens
- Skips user confirmation (auto-accepts)
- Proceeds directly to execution

**Success Criteria:**
- No interactive prompts
- Commands execute automatically
- Suitable for automation

### 7. Disabled Clarification
```bash
export AZLIN_DISABLE_CLARIFICATION=1
azlin do "create 10 storage accounts"
```

**Expected Behavior:**
- Clarification completely skipped
- Direct parsing even for complex requests
- Original behavior preserved

**Success Criteria:**
- No clarification phase
- Works like old version
- No added latency

## Performance Benchmarks

### Fast Path (Simple Requests)
- Should add < 10ms overhead
- Test: `time azlin do "list vms"`
- Compare with disabled clarification

### Clarification Path (Complex Requests)
- Should complete clarification in < 5 seconds
- Test: `time azlin do "create 20 storage accounts with specific settings"`
- Measure from start to confirmation prompt

## Verification Checklist

- [ ] Original bug (empty commands) is fixed
- [ ] Simple requests remain fast (fast path works)
- [ ] Complex requests show clear clarification
- [ ] User can cancel gracefully
- [ ] Errors fall back to original flow
- [ ] --verbose shows decision process
- [ ] --yes skips confirmation
- [ ] AZLIN_DISABLE_CLARIFICATION=1 disables feature
- [ ] Backward compatibility preserved
- [ ] No regressions in existing functionality

## Test Results (To be filled by tester)

### Test 1: Complex Request
- Status: ___
- Confidence: ___
- Clarification quality: ___
- Commands generated: ___

### Test 2: Simple Request
- Status: ___
- Latency: ___
- Clarification skipped: ___

### Test 3: User Cancels
- Status: ___
- Exit clean: ___

### Test 4: API Error
- Status: ___
- Fallback worked: ___

### Test 5: Verbose Mode
- Status: ___
- Output clear: ___

### Test 6: --yes Flag
- Status: ___
- No prompts: ___

### Test 7: Disabled
- Status: ___
- Skipped: ___
