# VM Provisioning & Disk Configuration Exploration Strategy

**Investigation Goal**: Understand azlin's VM provisioning flow from CLI to VM creation, focusing on disk configuration, cloud-init generation, and NFS storage implementation.

**Date**: 2026-01-11
**Branch**: feat/issue-514-separate-home-disk

---

## Executive Summary

This document outlines a systematic exploration strategy fer investigatin' azlin's VM provisioning architecture. The investigation be organized into 3 phases with parallel agent deployment in Phase 3.

**Key Target Areas**:
1. CLI entry points → VM provisioning flow
2. OS disk configuration mechanism
3. Cloud-init script generation
4. VMConfig dataclass usage
5. NFS storage option implementation
6. Storage manager integration

---

## Phase 1: Discovery (Foundation Understanding)

**Objective**: Establish baseline understanding of key files and their roles.

### Priority Files to Examine (in order)

#### 1. Core CLI Entry Point (HIGHEST PRIORITY)
- **File**: `/src/azlin/cli.py` (354KB - large file)
- **Purpose**: Understand CLI commands that trigger VM provisioning
- **Key Questions**:
  - Which commands create VMs?
  - How do CLI arguments flow to provisioning?
  - What options are available for disk configuration?
- **Search Targets**: `@click.command`, `create`, `provision`, `--storage`, `--nfs`, `--os-disk`

#### 2. VM Provisioning Core (HIGHEST PRIORITY)
- **File**: `/src/azlin/vm_provisioning.py` (37KB)
- **Purpose**: Main VM provisioning logic
- **Key Questions**:
  - How does VM creation flow work?
  - Where is OS disk configuration set?
  - How is cloud-init integrated?
  - What is the VMConfig dataclass structure?
- **Search Targets**: `class VMConfig`, `def provision`, `cloud-init`, `os_disk`, `disk_size`

#### 3. Cloud-Init Generation (HIGH PRIORITY)
- **File**: `/src/azlin/template_manager.py` (10KB)
- **Purpose**: Template management for cloud-init scripts
- **Key Questions**:
  - How are cloud-init scripts generated?
  - What templates are available?
  - How are variables substituted?
- **Search Targets**: `cloud-init`, `template`, `render`, `jinja`

#### 4. Storage Management (HIGH PRIORITY)
- **File**: `/src/azlin/modules/storage_manager.py` (29KB)
- **Purpose**: Storage operations and disk management
- **Key Questions**:
  - How does storage attach to VMs?
  - What disk types are supported?
  - How is NFS integrated?
- **Search Targets**: `attach`, `disk`, `nfs`, `mount`

#### 5. NFS Provisioning (MEDIUM PRIORITY)
- **File**: `/src/azlin/modules/nfs_provisioner.py` (39KB)
- **Purpose**: NFS-specific provisioning logic
- **Key Questions**:
  - How is NFS storage provisioned?
  - How does it integrate with VM creation?
  - What configuration options exist?
- **Search Targets**: `provision`, `nfs`, `storage_account`, `file_share`

---

## Phase 2: Deep Dive (Targeted Investigation)

**Objective**: Map data flow and architectural patterns.

### Investigation Tracks (parallel exploration recommended)

#### Track A: CLI → Provisioning Flow
**Files to trace**:
1. `/src/azlin/cli.py` - Command definitions
2. `/src/azlin/cli_helpers.py` - Helper functions
3. `/src/azlin/vm_provisioning.py` - Provisioning logic
4. `/src/azlin/modules/parallel_deployer.py` - Deployment orchestration

**Flow to map**:
```
CLI Command → Argument Parsing → Config Creation → VM Provisioning → Resource Creation
```

#### Track B: Disk Configuration Flow
**Files to trace**:
1. `/src/azlin/vm_provisioning.py` - VMConfig dataclass
2. `/src/azlin/modules/storage_manager.py` - Disk operations
3. `/src/azlin/config_manager.py` - Configuration management

**Flow to map**:
```
CLI Args → VMConfig → Disk Specs → Azure API → OS Disk Creation
```

#### Track C: Cloud-Init Flow
**Files to trace**:
1. `/src/azlin/template_manager.py` - Template rendering
2. `/src/azlin/vm_provisioning.py` - Cloud-init integration
3. `/terraform/azdoit-test/cloud-init.yml` - Example template
4. `/tests/unit/test_vm_provisioning_cloud_init.py` - Test patterns

**Flow to map**:
```
Template Selection → Variable Substitution → Script Generation → VM Custom Data
```

#### Track D: NFS Storage Flow
**Files to trace**:
1. `/src/azlin/modules/nfs_provisioner.py` - NFS provisioning
2. `/src/azlin/modules/nfs_mount_manager.py` - Mount management
3. `/src/azlin/modules/nfs_quota_manager.py` - Quota management
4. `/src/azlin/commands/storage.py` - Storage commands

**Flow to map**:
```
CLI Storage Option → NFS Provisioning → Storage Account → File Share → VM Mount
```

---

## Phase 3: Agent Deployment (Parallel Execution)

**Objective**: Deploy specialized agents in parallel fer comprehensive analysis.

### Agent Deployment Plan

#### Parallel Wave 1: Component Analysis (4 agents)
Deploy these agents simultaneously to analyze independent components:

**Agent 1: CLI Architecture Analyst**
- **Target**: `/src/azlin/cli.py`
- **Focus**: Command structure, argument flow, VM creation commands
- **Deliverable**: CLI command map showing all VM provisioning entry points
- **Time Estimate**: 15-20 minutes

**Agent 2: Provisioning Flow Analyst**
- **Target**: `/src/azlin/vm_provisioning.py`
- **Focus**: VMConfig dataclass, provisioning logic, disk configuration
- **Deliverable**: VMConfig specification and provisioning flow diagram
- **Time Estimate**: 15-20 minutes

**Agent 3: Cloud-Init Specialist**
- **Target**: `/src/azlin/template_manager.py`, cloud-init templates, tests
- **Focus**: Template system, variable substitution, generation mechanism
- **Deliverable**: Cloud-init generation flow and template structure
- **Time Estimate**: 10-15 minutes

**Agent 4: Storage Architecture Analyst**
- **Target**: `/src/azlin/modules/storage_manager.py`, `/src/azlin/modules/nfs_provisioner.py`
- **Focus**: Storage operations, NFS integration, disk attachment
- **Deliverable**: Storage architecture map and NFS provisioning flow
- **Time Estimate**: 20-25 minutes

#### Sequential Wave 2: Integration Analysis (1 agent)
Deploy after Wave 1 completes:

**Agent 5: Integration Synthesizer**
- **Target**: All findings from Wave 1
- **Focus**: How components connect, data flow between modules
- **Deliverable**: End-to-end flow diagram from CLI to VM creation
- **Time Estimate**: 15-20 minutes
- **Dependencies**: Requires Wave 1 completion

---

## Expected Architectural Patterns

Based on project structure and philosophy, expect to find:

### 1. Modular "Brick" Design
- Self-contained modules in `/src/azlin/modules/`
- Clear public APIs (likely using `__all__`)
- Single responsibility per module

### 2. Configuration Dataclass Pattern
- VMConfig dataclass capturing all VM parameters
- Immutable or clearly mutable configuration objects
- Type hints for all fields

### 3. Template-Based Generation
- Jinja2 or similar templating for cloud-init
- Template variables from VMConfig
- Template location in `/src/azlin/templates/` or embedded

### 4. Azure SDK Wrapper Pattern
- Abstraction layer over Azure SDK calls
- Retry logic and error handling
- Command sanitization (security module)

### 5. Storage as Separate Concern
- Storage modules independent of VM provisioning
- NFS provisioning separate from VM creation
- Post-creation attachment pattern

---

## Verification Approach

### Phase 1 Verification: Unit Tests
**Target**: `/tests/unit/test_vm_provisioning_cloud_init.py`
- Examine existing tests to understand expected behavior
- Identify test patterns for cloud-init generation
- Map test coverage gaps

### Phase 2 Verification: Code Tracing
**Method**: Follow data flow with specific examples
1. Pick a specific CLI command (e.g., `azlin create dev-vm --storage nfs`)
2. Trace argument flow through code
3. Identify all transformation points
4. Map VMConfig creation and usage

### Phase 3 Verification: Documentation Cross-Reference
**Target**: `/docs/` directory
- Check if documentation describes provisioning flow
- Verify code matches documented behavior
- Identify doc/code discrepancies

### Phase 4 Verification: Example Scenarios
**Method**: Create test scenarios
1. Scenario A: Basic VM with default OS disk
2. Scenario B: VM with custom OS disk size
3. Scenario C: VM with NFS storage attached
4. Scenario D: VM with cloud-init customization

Map how each scenario flows through the code.

---

## Investigation Priority Matrix

| Question | Priority | Complexity | Files to Examine | Agent Assignment |
|----------|----------|------------|------------------|------------------|
| 1. VM provisioning flow | HIGHEST | High | cli.py, vm_provisioning.py | Agent 1 + 2 |
| 2. OS disk configuration | HIGHEST | Medium | vm_provisioning.py, storage_manager.py | Agent 2 + 4 |
| 3. Cloud-init generation | HIGH | Medium | template_manager.py, templates/ | Agent 3 |
| 4. CLI argument flow | HIGH | Low | cli.py, cli_helpers.py | Agent 1 |
| 5. NFS implementation | MEDIUM | High | nfs_provisioner.py, nfs_mount_manager.py | Agent 4 |
| 6. VMConfig definition | HIGH | Low | vm_provisioning.py | Agent 2 |

---

## Success Criteria

The investigation be considered successful when we can answer:

### Core Questions
- ✓ How does a CLI command trigger VM creation?
- ✓ Where is OS disk size specified and how is it applied?
- ✓ How are cloud-init scripts generated from templates?
- ✓ What is the complete VMConfig dataclass structure?
- ✓ How does NFS storage integrate with VM provisioning?
- ✓ What configuration options are available for disk management?

### Documentation Deliverables
- [ ] Complete CLI → VM creation flow diagram
- [ ] VMConfig dataclass specification
- [ ] Cloud-init generation flow diagram
- [ ] NFS provisioning architecture map
- [ ] Storage manager integration points
- [ ] Example code traces for key scenarios

---

## Next Steps

### Immediate Actions (Phase 1)
1. Read `/src/azlin/cli.py` - identify VM creation commands
2. Read `/src/azlin/vm_provisioning.py` - understand VMConfig and provisioning flow
3. Read `/src/azlin/template_manager.py` - understand cloud-init generation
4. Read `/src/azlin/modules/storage_manager.py` - understand storage operations

### After Phase 1 (Phase 2)
5. Trace CLI arguments through to VMConfig creation
6. Map cloud-init template variables to VMConfig fields
7. Identify storage attachment integration points
8. Document OS disk configuration mechanism

### After Phase 2 (Phase 3)
9. Deploy Agent Wave 1 in parallel
10. Synthesize findings from Agent Wave 1
11. Deploy Agent Wave 2 for integration analysis
12. Create final architecture documentation

---

## Notes

- **File Sizes**: `cli.py` (354KB) is very large - may need focused searches
- **Test Coverage**: Unit tests exist for cloud-init - good verification source
- **Modules Directory**: Well-organized module structure suggests good separation of concerns
- **Branch Context**: On `feat/issue-514-separate-home-disk` - may be relevant changes in progress

---

## Appendix: Key File Reference

### Primary Investigation Targets
```
/src/azlin/cli.py                          # CLI entry points
/src/azlin/vm_provisioning.py              # Core provisioning logic
/src/azlin/template_manager.py             # Cloud-init templates
/src/azlin/modules/storage_manager.py      # Storage operations
/src/azlin/modules/nfs_provisioner.py      # NFS provisioning
/src/azlin/modules/nfs_mount_manager.py    # NFS mounting
/src/azlin/config_manager.py               # Configuration management
```

### Supporting Files
```
/src/azlin/cli_helpers.py                  # CLI utilities
/src/azlin/modules/parallel_deployer.py    # Deployment orchestration
/src/azlin/commands/storage.py             # Storage commands
/tests/unit/test_vm_provisioning_cloud_init.py  # Cloud-init tests
/terraform/azdoit-test/cloud-init.yml      # Example cloud-init template
```

### Configuration Files
```
/src/azlin/config_manager.py               # Main config manager
/src/azlin/cache/config_cache.py           # Config caching
```

---

**End of Strategy Document**
