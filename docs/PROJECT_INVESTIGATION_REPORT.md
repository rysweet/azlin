# azlin: Comprehensive Project Investigation Report

## Executive Summary

azlin is a Python-based CLI tool for provisioning and managing Azure Ubuntu VMs optimized for development workflows. The project demonstrates sophisticated engineering with ~19,000 lines of code across 49 Python modules, implementing a complete VM lifecycle management system.

### Key Metrics
- **Language**: Python 3.11+ with full type hints
- **Codebase**: 49 modules, ~19,000 LOC
- **Architecture**: Modular design with clear separation of concerns
- **Testing**: 604 tests (unit, integration, e2e)
- **CLI**: 20+ commands via Click framework
- **Dependencies**: Minimal (click, pyyaml, tomli/tomli-w)

## 1. Project Architecture

### 1.1 Core Design Patterns

**Orchestration Pattern**: The `CLIOrchestrator` class in `cli.py` (176KB, largest file) orchestrates the entire VM provisioning workflow:
- Azure authentication
- VM provisioning
- Development tools installation
- Home directory synchronization
- NFS storage mounting
- GitHub integration
- SSH connection management

**Module Boundary Pattern ("Bricks & Studs")**:
- Clean interfaces between modules
- No circular dependencies
- Each module has single responsibility
- Well-defined public APIs

### 1.2 Module Organization

```
src/azlin/
├── cli.py (main orchestrator, 176KB)
├── vm_provisioning.py (Azure VM creation logic)
├── vm_manager.py (VM lifecycle operations)
├── azure_auth.py (Azure authentication)
├── config_manager.py (configuration persistence)
├── commands/ (command implementations)
│   ├── __init__.py
│   ├── storage.py (NFS storage commands)
│   └── [other command modules]
└── modules/ (shared functionality)
    ├── home_sync.py (home directory sync)
    ├── storage_manager.py (Azure Files NFS)
    ├── nfs_mount_manager.py (NFS mounting)
    ├── ssh_connector.py (SSH operations)
    ├── github_setup.py (GitHub integration)
    ├── notifications.py (notification system)
    ├── progress.py (progress tracking)
    ├── ssh_reconnect.py (auto-reconnect)
    ├── npm_config.py (Node.js setup)
    └── file_transfer/ (SCP functionality)
        ├── file_transfer.py
        ├── path_parser.py
        ├── session_manager.py
        └── exceptions.py
```

### 1.3 Key Design Decisions

1. **Azure SDK via CLI**: Uses `az` CLI commands instead of Azure Python SDK
   - Simpler dependency management
   - Leverages existing authentication
   - Shell-out pattern with subprocess

2. **SSH-based Operations**: All VM operations over SSH
   - Key-based authentication (no passwords)
   - Secure key storage in `~/.ssh/`
   - Auto-reconnect capability

3. **Home Directory Sync**: rsync for file synchronization
   - Security: Path validation, symlink protection
   - Exclusion patterns for large directories
   - Fallback to NFS for shared storage

4. **Configuration**: TOML-based configuration
   - File: `~/.azlin/config.toml`
   - Stores: defaults, session names, VM-storage mappings
   - Secure permissions (0600)

## 2. Feature Analysis

### 2.1 Core Features

#### VM Provisioning (`azlin new`)
- Ubuntu 24.04 LTS base image
- 12 development tools pre-installed:
  - Docker, Azure CLI, GitHub CLI, Git
  - Node.js, Python 3.12+, Rust, Go, .NET 10
  - AI tools: GitHub Copilot CLI, OpenAI Codex, Claude Code
- cloud-init for automated setup
- Persistent tmux session
- Optional GitHub repo cloning

#### VM Management
- `azlin list`: List VMs with status
- `azlin connect`: SSH with tmux
- `azlin start/stop`: Power management
- `azlin destroy`: VM cleanup
- `azlin status`: Resource dashboard

#### Advanced Features
- `azlin storage`: Azure Files NFS management
- `azlin clone`: Clone VM configuration
- `azlin update`: Update VM software
- `azlin snapshot`: VM snapshots
- `azlin template`: VM templates
- `azlin batch`: Parallel operations
- `azlin prune`: Cleanup old resources

### 2.2 NFS Storage Integration (Recent Addition)

**Azure Files NFS Support**:
- Premium/Standard tiers
- NFS 4.1 protocol
- VNet-only access (secure)
- Shared home directories across VMs
- Auto-detection with single storage
- Config-based defaults

**Implementation** (Issue #66, #72):
- `StorageManager`: Azure Files operations
- `NFSMountManager`: Mount/unmount operations
- Auto-detection logic in CLI orchestrator
- Configuration persistence

### 2.3 Security Features

1. **SSH Key Management**:
   - Generated per VM
   - Stored securely in `~/.ssh/azlin_key*`
   - No password authentication

2. **Home Sync Security**:
   - Path validation (prevent directory traversal)
   - Symlink safety (`--safe-links`)
   - Content scanning (excludes secrets)
   - Secure exclude patterns

3. **Network Security**:
   - NSG rules for SSH only
   - NFS storage VNet-scoped
   - No public IPs (optional)

## 3. Technology Stack

### 3.1 Core Dependencies

**Runtime** (minimal dependencies):
- `click>=8.1.0`: CLI framework
- `pyyaml>=6.0.0`: YAML parsing
- `tomli/tomli-w`: TOML config

**Development**:
- `pytest`: Testing framework
- `pytest-cov`: Coverage reporting
- `pytest-mock`: Mocking
- `pytest-xdist`: Parallel testing
- `pyright`: Static type checking
- `ruff`: Linting and formatting
- `pre-commit`: Git hooks

### 3.2 External Tools

**Required** (must be installed):
- `az`: Azure CLI
- `gh`: GitHub CLI
- `git`: Version control
- `ssh`: Remote access
- `tmux`: Terminal multiplexer
- `rsync`: File synchronization
- `uv` (or `pip`): Package management

### 3.3 Python Features

- **Python 3.11+** (3.12 recommended)
- Type hints throughout
- Dataclasses for configuration
- Pathlib for file operations
- Context managers for resources
- Async not used (synchronous operations)

## 4. Development Practices

### 4.1 Testing Strategy

**604 Total Tests**:
- Unit tests: Fast, isolated
- Integration tests: Azure API mocking
- E2E tests: Real VM provisioning (expensive)

**Test Markers**:
```python
@pytest.mark.unit
@pytest.mark.integration
@pytest.mark.e2e
```

**Coverage**: Configured in pyproject.toml
- Source: `src/`
- Omit: `tests/`, `test_*.py`

### 4.2 Code Quality

**Pre-commit Hooks**:
```yaml
- ruff (linting)
- ruff-format (formatting)
- pyright (type checking)
```

**Philosophy**: "Ruthless Simplicity"
- No stubs or TODOs allowed
- Quality over speed
- Complete features only
- Clear module boundaries

### 4.3 Git Workflow

**Branching Strategy**:
- `main`: Stable releases
- `feat/issue-N-description`: Feature branches
- `fix/description`: Bug fixes
- Git worktrees for parallel development

**Workflow** (defined in `.claude/workflow/DEFAULT_WORKFLOW.md`):
1. Create GitHub issue
2. Setup worktree + branch
3. Research & design (TDD)
4. Implement
5. Refactor
6. Test + pre-commit
7. Commit + push
8. Open PR
9. Review
10. Implement feedback
11. Philosophy check
12. Ensure mergeable
13. Final cleanup
14. Merge

## 5. Key Workflows

### 5.1 VM Provisioning Workflow

```
azlin new --repo https://github.com/user/repo

1. Prerequisites Check
   ├── az CLI authenticated
   ├── gh CLI authenticated
   ├── ssh, git, tmux installed
   └── uv available

2. Azure Authentication
   └── Check/refresh az login

3. Resource Group Setup
   ├── Use existing or create new
   └── Store in config

4. SSH Key Generation
   ├── Generate key pair
   └── Store in ~/.ssh/azlin_key*

5. VM Provisioning
   ├── Create VM with cloud-init
   ├── Apply NSG rules
   ├── Configure network
   └── Wait for boot (cloud-init)

6. Development Tools Setup
   ├── Wait for cloud-init completion
   └── Verify tools installed (Docker, az, gh, etc.)

7. Storage Setup (if configured)
   ├── Resolve NFS storage (auto-detect/explicit/config)
   ├── Mount NFS to home directory
   └── Skip rsync if NFS used

8. Home Directory Sync (if no NFS)
   ├── rsync ~/.azlin/home/ to VM
   └── Exclude patterns applied

9. GitHub Setup (if --repo)
   ├── Clone repository
   ├── Setup credentials
   └── Create tmux session in repo

10. SSH Connection
    ├── Display connection info
    └── Auto-connect with tmux
```

### 5.2 NFS Storage Workflow

```
azlin storage create myteam-shared --size 100 --tier Premium

1. Create Storage Account
   ├── Name validation (3-24 chars, lowercase)
   ├── Region selection
   ├── Premium/Standard tier
   └── NFS 4.1 enabled

2. Create File Share
   ├── Size allocation
   ├── NFS protocol
   └── VNet integration

3. Update Configuration
   ├── Store storage details
   └── Set as default (optional)

---

azlin new --nfs-storage myteam-shared

1. NFS Resolution
   ├── Check --nfs-storage option
   ├── Check config default_nfs_storage
   ├── Auto-detect if single storage
   └── Error if multiple without choice

2. Mount NFS
   ├── Install nfs-common on VM
   ├── Create mount point
   ├── Mount NFS share to /home/azureuser
   ├── Update fstab for persistence
   └── Verify mount successful

3. Skip Home Sync
   └── NFS provides home directory content
```

## 6. Recent Development Activity

### 6.1 Completed Features

**Issue #66: Azure Files NFS CLI** (Merged)
- Full Azure Files NFS support
- CLI commands: create, list, status, delete, mount, unmount
- StorageManager module
- NFSMountManager module
- Documentation

**Issue #72: NFS Home Directory** (In Progress - PR #74)
- Auto-detection logic
- Config default support
- Priority system (explicit > config > auto-detect)
- Integration with azlin new
- Tests for auto-detection
- Currently awaiting CI/merge

**Home Sync Bug Fix** (Completed)
- Fixed rsync buffer overflow with large file sets
- Replaced --delete-excluded with --partial and --inplace
- Improved reliability with 50k+ files
- Documented in BUG_FIX_HOME_SYNC.md

### 6.2 Technical Debt Assessment

**Strengths**:
- Clean architecture
- Comprehensive testing
- Type safety
- Good documentation
- Security-conscious

**Areas for Improvement**:
1. **Test File Type Errors**: Some test files have pyright errors (not critical)
2. **CLI File Size**: cli.py is 176KB (5000+ lines) - could be split
3. **Error Handling**: Some silent failures in optional features
4. **Progress Reporting**: Could be more granular for long operations
5. **Azure SDK**: Could migrate from az CLI to Azure Python SDK for better error handling

## 7. Project Philosophy

### 7.1 Core Principles

**Ruthless Simplicity**:
- Remove unnecessary abstractions
- Single responsibility per module
- Clear public APIs
- No "just in case" code

**Zero-BS Implementation**:
- No stubs or TODOs
- No placeholder implementations
- No "planned" features in docs
- Complete features or nothing

**Bricks & Studs Pattern**:
- Well-defined module boundaries
- Clean interfaces between modules
- No circular dependencies
- Easy to test in isolation

**Quality Over Speed**:
- TDD approach
- Comprehensive testing
- Code review required
- Philosophy compliance checks

### 7.2 Implementation Standards

1. **All features must be fully functional** before merge
2. **No partial implementations** or stubs
3. **Tests must pass** (all 604 tests)
4. **Type checking must pass** (pyright)
5. **Code must be formatted** (ruff)
6. **Documentation must be current** (no "planned" features)
7. **CLI must be complete** (not partial)

## 8. User Experience

### 8.1 Installation

**Zero-install with uvx** (recommended for trying):
```bash
uvx --from git+https://github.com/rysweet/azlin azlin new
```

**Install with uv**:
```bash
uv tool install git+https://github.com/rysweet/azlin
```

**Install with pip**:
```bash
pip install git+https://github.com/rysweet/azlin
```

### 8.2 Quick Start

```bash
# Authenticate
az login
gh auth login

# Create VM
azlin new

# Create with GitHub repo
azlin new --repo https://github.com/user/repo

# Create with NFS storage
azlin new --nfs-storage myteam-shared

# List VMs
azlin list

# Connect to VM
azlin connect

# Destroy VM
azlin destroy my-vm
```

### 8.3 User Value Proposition

**Time Savings**:
- Manual setup: 30-60 minutes
- azlin: 4-7 minutes
- **Savings: ~85% time reduction**

**Convenience**:
- One command for full setup
- No manual tool installation
- Pre-configured development environment
- Auto-reconnect on disconnect
- Persistent tmux sessions

**Cost Efficiency**:
- Start/stop VMs easily
- Prune old resources
- Cost tracking
- Default to affordable VM sizes

**Collaboration**:
- NFS shared home directories
- Consistent environments
- Template sharing
- Batch operations

## 9. Competitive Analysis

### 9.1 Similar Tools

**Cloud Development Environments**:
1. **GitHub Codespaces**: Browser-based, GitHub-integrated
2. **AWS Cloud9**: AWS-specific, browser-based
3. **GitPod**: Git-integrated, browser-based
4. **Coder**: Self-hosted, enterprise-focused

**VM Management Tools**:
1. **Vagrant**: Local VMs, multi-provider
2. **Multipass**: Ubuntu VMs, lightweight
3. **Docker**: Containers, not full VMs
4. **Terraform**: Infrastructure as code

**azlin Differentiation**:
- Azure-optimized
- CLI-first (not browser)
- Development tools pre-installed
- Home directory synchronization
- NFS shared storage
- tmux integration
- GitHub CLI integration
- Cost-conscious defaults

### 9.2 Target Users

**Primary**:
- Developers needing cloud compute
- Azure users
- Python/Node/Rust/Go developers
- Teams needing shared environments
- CLI power users

**Secondary**:
- Data scientists (GPU workloads)
- DevOps engineers
- Cloud learners
- Hackathon participants

## 10. Recommendations

### 10.1 Immediate Priorities

1. **Complete Issue #72**: Merge PR #74 for NFS home directory support
2. **Documentation Update**: Ensure README reflects all current features
3. **CI/CD**: Ensure all tests pass in CI
4. **Release**: Tag v2.0.0 with NFS features

### 10.2 Future Enhancements (See FEATURE_ROADMAP.md)

**High Priority**:
1. **GPU VM Support**: For ML/AI workloads
2. **Multi-region Support**: Deploy across regions
3. **Cost Optimization**: Auto-stop idle VMs
4. **Backup/Restore**: VM state management

**Medium Priority**:
1. **Web UI**: Optional web dashboard
2. **Team Management**: Role-based access
3. **Logging**: Centralized log aggregation
4. **Metrics**: Performance monitoring

**Low Priority**:
1. **Multi-cloud**: AWS, GCP support
2. **Custom Images**: User-defined base images
3. **Plugins**: Extension system
4. **API**: REST API for automation

## 11. Conclusion

azlin is a mature, well-engineered CLI tool that solves real developer pain points. The codebase demonstrates excellent software engineering practices with strong type safety, comprehensive testing, and a clear architectural vision.

The recent addition of Azure Files NFS support enables shared development environments, opening new use cases for team collaboration and distributed computing workflows. The project follows a rigorous development workflow and maintains high quality standards.

**Project Status**: **Production-Ready** with active development

---

*Report generated: October 18, 2025*
*Codebase version: main branch (commit 1ebe79f)*
*Total investigation time: ~1 hour*
