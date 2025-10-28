# Documentation Inconsistency Tracker

**Quick Reference Sheet for Fixing Documentation Issues**

---

## P0: Critical Issues (MUST FIX)

| ID | Issue | File | Line | CLI Truth | Doc Status | Fix Action |
|----|-------|------|------|-----------|------------|------------|
| P0-1 | Missing `logs` command | README.md | N/A | `azlin logs` exists | ✗ Missing section | Add full logs documentation |
| P0-2 | Missing `tag` command | README.md | N/A | `azlin tag` exists | ✗ Only examples | Add full tag documentation |
| P0-3 | Missing `cleanup` command | README.md | 1237 | `azlin cleanup` exists | ✗ Mentioned only | Add full cleanup documentation |
| P0-4 | Missing `auth` group | README.md | 1238-1245 | 5 subcommands | ✗ Listed only | Add Authentication section |
| P0-5 | Missing `top` command | README.md | N/A | `azlin top` exists | ✗ Not in README | Add to monitoring section |
| P0-6 | Missing `prune` command | README.md | N/A | `azlin prune` exists | ✗ Not documented | Add prune documentation |
| P0-7 | Missing `batch` group | README.md | N/A | 4 subcommands | ✗ Not documented | Add Batch Operations section |
| P0-8 | Storage options verified | README.md | 834, 843 | Matches CLI | ✓ Correct | No action needed |
| P0-9 | Missing `--all` flag | README.md | 455 | `list --all` | Partial | Add example with --all |
| P0-10 | Missing `--tag` filter | README.md | N/A | `list --tag` | ✗ Missing | Add tag filtering examples |
| P0-11 | `os-update` not in table | README.md | 1121-1142 | Exists | Partial | Add to quick reference |
| P0-12 | `stop` deallocate unclear | README.md | 529 | Default: yes | Unclear | Clarify deallocate behavior |

---

## P1: High Priority Issues (SHOULD FIX)

| ID | Issue | File | Line | CLI Truth | Doc Status | Fix Action |
|----|-------|------|------|-----------|------------|------------|
| P1-1 | Auto-reconnect placement | README.md | 684-704 | Documented | Misplaced | Move to top of section |
| P1-2 | Missing `--session-prefix` | README.md | 422-426 | Used but not explained | Partial | Add option explanation |
| P1-3 | Storage costs disclaimer | README.md | 900-905 | Correct but incomplete | Partial | Add regional variance note |
| P1-4 | Missing `--template` example | README.md | 366-398 | Option exists | ✗ Missing | Add template example |
| P1-5 | Session name scope unclear | README.md | 662 | Works everywhere | Partial | Add note about universal use |
| P1-6 | `kill` vs `destroy` unclear | README.md | 548-568 | Both exist | Confusing | Add comparison table |
| P1-7 | Date format not specified | README.md | 936 | YYYY-MM-DD required | Implicit | Add format requirement |
| P1-8 | Missing `--estimate` flag | README.md | 921-953 | Exists | ✗ Missing | Add estimate example |
| P1-9 | Update timeout default | README.md | 600 | 300s default | In comment only | Add to description |
| P1-10 | Sync security filtering | README.md | 788-823 | Mentioned once | Incomplete | Repeat in sync section |
| P1-11 | `cp` security validation | README.md | 776-781 | Exists | Vague | Explain validation details |
| P1-12 | VM identifier types | README.md | Various | 3 types | Incomplete | Add to all commands |
| P1-13 | Status `--vm` filter | README.md | 489-506 | Exists | ✗ Missing | Add filter example |
| P1-14 | Snapshot subcommands | README.md | 1290-1293 | 8 commands | 3 shown | Document all 8 |
| P1-15 | Env subcommands incomplete | README.md | 1272-1276 | 6 commands | 3 shown | Add remaining 3 |
| P1-16 | Missing `keys` group | README.md | 1240-1244 | 4 subcommands | Listed only | Add SSH Keys section |
| P1-17 | Missing `template` group | README.md | N/A | Full group | ✗ Not documented | Add VM Templates section |
| P1-18 | No performance info | QUICK_REFERENCE.md | N/A | Times vary | ✗ Missing | Add performance section |

---

## P2: Medium Priority Issues (NICE TO FIX)

| ID | Issue | File | Line | CLI Truth | Doc Status | Fix Action |
|----|-------|------|------|-----------|------------|------------|
| P2-1 | Natural language syntax | AZDOIT.md | 88-95 | Both work | Inconsistent | Standardize examples |
| P2-2 | Version number sync | AZDOIT.md | 746 | 2.0.0 | Inconsistent | Add version to README |
| P2-3 | Pool warning threshold | QUICK_REFERENCE.md | 248-254 | >10 triggers | Example off | Use 11 in example |
| P2-6 | `killall` default prefix | README.md | 569 | azlin-* | Not mentioned | Add prefix note |
| P2-7 | Connect `--user` option | README.md | 674-679 | Exists | ✗ Missing | Add custom user example |
| P2-8 | Command ordering | README.md | 350-359 | CLI order | Different | Reorder to match CLI |
| P2-9 | `do` vs `doit` unclear | AZDOIT.md | 98-105 | Different features | Vague | Add comparison table |
| P2-10 | Storage delete `--force` | README.md | 887 | Overrides check | Unclear | Clarify behavior |
| P2-11 | Main command behavior | QUICK_REFERENCE.md | 45-57 | Shows help | Says interactive | Update behavior description |

---

## P3: Low Priority Issues (POLISH)

| ID | Issue | File | Line | CLI Truth | Doc Status | Fix Action |
|----|-------|------|------|-----------|------------|------------|
| P3-1 | Inconsistent `$` prompt | README.md | Throughout | N/A | Inconsistent | Standardize on $ or remove |
| P3-2 | Emoji inconsistency | README.md, AZDOIT.md | Various | N/A | Inconsistent | Decide emoji policy |
| P3-3 | Code fence language tags | Multiple | Throughout | N/A | Inconsistent | Always use `bash` |
| P3-4 | Table formatting varies | README.md, AZDOIT.md | Various | N/A | Inconsistent | Standardize tables |
| P3-5 | Link formatting | README.md, AZDOIT.md | Various | N/A | Inconsistent | Standardize links |
| P3-6 | Header levels | README.md | Throughout | N/A | Inconsistent | Review hierarchy |

---

## Quick Stats

### Issue Distribution
```
P0 Critical:    12 issues (26%)
P1 High:        18 issues (38%)
P2 Medium:      11 issues (23%)
P3 Low:          6 issues (13%)
Total:          47 issues
```

### Status Distribution
```
✗ Missing:      22 issues (47%)
Partial:        16 issues (34%)
Unclear:         6 issues (13%)
Cosmetic:        3 issues (6%)
```

### File Distribution
```
README.md:            31 issues (66%)
QUICK_REFERENCE.md:    8 issues (17%)
AZDOIT.md:            5 issues (11%)
Cross-file:            3 issues (6%)
```

### Command Coverage Status
```
Fully Documented:     14 / 27 (52%)
Partially Documented:  7 / 27 (26%)
Undocumented:          6 / 27 (22%)
```

---

## Fix Priority Workflow

### Phase 1: Critical Missing Commands (P0-1 to P0-7)
**Estimated time:** 4-6 hours
**Impact:** High - Users cannot discover major features

1. Add `logs` command documentation
2. Add `tag` command documentation
3. Add `cleanup` command documentation
4. Add `auth` group documentation (5 subcommands)
5. Add `top` command documentation
6. Add `prune` command documentation
7. Add `batch` group documentation (4 subcommands)

### Phase 2: Command Option Completeness (P0-9 to P0-12, P1-*)
**Estimated time:** 3-4 hours
**Impact:** Medium-High - Existing commands missing important options

1. Add missing flags to documented commands
2. Clarify default behaviors
3. Add VM identifier type explanations
4. Complete subcommand documentation
5. Add comparison tables

### Phase 3: Example Enhancement (P2-*)
**Estimated time:** 2-3 hours
**Impact:** Medium - Improves usability

1. Add missing examples
2. Standardize syntax
3. Update QUICK_REFERENCE.md
4. Fix behavioral descriptions

### Phase 4: Polish and Consistency (P3-*)
**Estimated time:** 1-2 hours
**Impact:** Low - Visual consistency

1. Standardize formatting
2. Fix style inconsistencies
3. Review heading structure
4. Validate links

---

## Testing Checklist

After fixes, validate:

- [ ] All commands from `azlin --help` have documentation
- [ ] All documented examples run without errors
- [ ] All options in docs exist in CLI
- [ ] All CLI options are documented
- [ ] Cross-references work
- [ ] Version numbers match
- [ ] Examples follow consistent style
- [ ] Code blocks have language tags
- [ ] Tables render correctly
- [ ] Links resolve

---

## Automation Opportunities

Prevent future drift:

1. **CLI Help Extraction Test:**
   - Run `azlin <cmd> --help` for all commands
   - Compare against documentation
   - Fail CI if new commands undocumented

2. **Example Validation:**
   - Extract code blocks from docs
   - Run in test environment
   - Verify exit codes and output

3. **Version Sync Check:**
   - Parse version from `pyproject.toml`
   - Check all docs mention same version
   - Update automatically in CI

4. **Command Inventory:**
   - Generate command list from CLI
   - Generate command list from docs
   - Diff and report gaps

---

**Last Updated:** 2025-10-27
**Tracker Version:** 1.0
