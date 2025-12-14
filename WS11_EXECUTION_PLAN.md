# WS11 Execution Plan - Pragmatic Approach

## Decision: Phased Implementation

Given the 30-45 hour estimate for complete implementation, I'm taking a phased approach:

### Session 1 (Current): Foundation + Phase 1 Start
**Goal**: Begin Phase 1 (Monitoring Module)  
**Time**: 2-3 hours  
**Deliverables**:
1. Comprehensive analysis (✓ DONE)
2. Execution plan (✓ DONE)
3. Extract 2-3 simpler commands (w, ps, session)
4. Document progress
5. Commit work

### Session 2: Complete Phase 1
**Goal**: Finish monitoring.py
**Time**: 4-5 hours
**Deliverables**:
1. Extract remaining commands (list, top)
2. Move helper functions
3. Full testing
4. Create PR #1

### Session 3: Phase 2 (Lifecycle)
**Goal**: Create lifecycle.py
**Time**: 4-6 hours
**Deliverables**:
1. Extract all 6 lifecycle commands
2. Testing
3. Commit

### Session 4: Phase 5 (Admin)  
**Goal**: Create admin.py
**Time**: 3-4 hours
**Deliverables**:
1. Extract all 4 admin commands
2. Testing
3. Create PR #2 (Lifecycle + Admin)

### Session 5-7: Phases 3, 4, 6
**Goal**: Complete remaining modules + router
**Time**: 10-15 hours
**Deliverables**:
1. provisioning.py
2. connectivity.py
3. Router refactor
4. Final testing
5. Create PR #3

## Current Session Plan

### Step 1: Extract Simple Commands First ✓
Start with easiest commands to build momentum:
- ps (79 lines, simple)
- w (78 lines, simple)  
- session (135 lines, moderate)

### Step 2: Test Extraction Tools
Verify extract_module.py works correctly

### Step 3: Execute Extractions
Use semi-automated process with manual review

### Step 4: Test Each Command
Ensure functionality preserved

### Step 5: Commit Progress
Save work with clear commits

### Step 6: Document Status
Update tracking documents

## Commands Priority Order

### Easy (Do First)
1. ps - Simple process listing
2. w - Simple remote command
3. session - Session name management

### Medium (Do Second)
4. top - Distributed monitoring
5. start/stop/kill - Simple lifecycle

### Hard (Do Last)
6. list - Very complex (378 lines)
7. new - Core provisioning
8. connect - Bastion logic
9. clone - Complex cloning

## Success Metrics

### This Session
- [ ] Extract 3 commands (ps, w, session)
- [ ] All extracted commands tested
- [ ] Commits pushed
- [ ] Progress documented

### Phase 1 Complete
- [ ] monitoring.py with 6 commands
- [ ] All helpers moved
- [ ] Tests passing
- [ ] PR created

### Full Project Complete
- [ ] All 26 commands extracted
- [ ] cli.py < 500 lines
- [ ] 6 modules created
- [ ] 100% tests passing
- [ ] 3 PRs merged

## Risk Mitigation

### After Each Extraction
1. Run: `python -m pytest tests/ -xvs`
2. Manual test: `azlin <command> --help`
3. Check imports
4. Git commit immediately

### If Issues Arise
1. Check extract_module.py output
2. Search for missing helper functions
3. Verify imports in cli.py updated
4. Check command registration

## Next Actions

1. Test extract_module.py script
2. Extract ps command
3. Test ps command
4. Commit
5. Extract w command  
6. Test w command
7. Commit
8. Extract session command
9. Test session command
10. Commit
11. Push all commits
12. Document progress

