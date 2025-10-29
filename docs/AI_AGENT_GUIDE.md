# AI Agent Developer Guide

**Target Audience**: AI agents working on azlin development
**Purpose**: Comprehensive guide to understanding and contributing to azlin
**Last Updated**: 2025-10-15

---

## Quick Start for AI Agents

### Essential Reading Order
1. **This document** - Overview and architecture
2. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete system design
3. **[testing/test_strategy.md](testing/test_strategy.md)** - Testing approach
4. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference

### Development Workflow
```bash
# 1. Setup environment
uv sync
source .venv/bin/activate

# 2. Run tests (TDD approach)
pytest tests/unit/ -v        # Fast feedback
pytest tests/ -m "not e2e"   # Skip expensive E2E tests

# 3. Make changes following brick philosophy

# 4. Verify
pytest tests/unit/ -v
ruff check src/
```

---

## Project Philosophy

### Ruthless Simplicity
- **Standard library preference** - Minimize external dependencies
- **Fail fast** - Validate prerequisites before operations
- **Zero credentials in code** - Delegate to external CLIs (az, gh)
- **Explicit over implicit** - Clear contracts, no magic

### Brick Architecture
Each module is a self-contained "brick":
- **Single responsibility** - One clear purpose
- **Explicit public API** - Define `__all__`
- **Comprehensive tests** - Unit, integration, E2E
- **No tight coupling** - Modules can be regenerated independently
- **Standard patterns** - Consistent error handling, logging, validation

---

## Architecture Overview

### The 9 Bricks

| Brick | Module | Purpose | Dependencies |
|-------|--------|---------|--------------|
| 1 | `prerequisites.py` | Verify required tools | stdlib only |
| 2 | `azure_auth.py` | Handle Azure authentication | az CLI |
| 3 | `ssh_keys.py` | Generate SSH keys | ssh-keygen |
| 4 | `vm_provisioning.py` | Create Azure VMs | az CLI |
| 5 | `ssh_connector.py` | SSH connection management | ssh, tmux |
| 6 | `github_setup.py` | Clone repos on VM | gh, git |
| 7 | `npm_config.py` | Configure npm user-local | None |
| 8 | `progress.py` | Show real-time progress | stdlib only |
| 9 | `notifications.py` | Send completion alerts | imessR (optional) |

**Entry Point**: `cli.py` orchestrates all bricks

### Project Structure
```
azlin/
├── src/azlin/
│   ├── cli.py                    # Main entry point
│   ├── azure_auth.py             # Azure authentication
│   ├── vm_provisioning.py        # VM provisioning logic
│   ├── remote_exec.py            # Remote command execution
│   ├── vm_manager.py             # VM lifecycle management
│   ├── vm_lifecycle.py           # VM lifecycle operations
│   ├── config_manager.py         # Configuration management
│   └── modules/                  # Self-contained bricks
│       ├── prerequisites.py
│       ├── ssh_keys.py
│       ├── ssh_connector.py
│       ├── github_setup.py
│       ├── npm_config.py
│       ├── progress.py
│       └── notifications.py
│
├── tests/
│   ├── unit/                     # 60% - Fast, isolated tests
│   ├── integration/              # 30% - Multi-module tests
│   └── e2e/                      # 10% - Full workflow tests
│
├── docs/
│   ├── ARCHITECTURE.md           # Complete system design
│   ├── testing/test_strategy.md          # Testing approach
│   ├── QUICK_REFERENCE.md        # Command reference
│   └── AI_AGENT_GUIDE.md         # This file
│
└── .claude/                      # Claude-specific tools
    ├── agents/                   # Agent definitions
    ├── context/                  # Development patterns
    └── tools/                    # Development tools
```

---

## Security Architecture

### Core Principles
1. **No credentials in code** - EVER
2. **Delegate authentication** - Use az CLI, gh CLI
3. **Validate all inputs** - Prevent injection attacks
4. **Sanitize all outputs** - No credential leaks in logs
5. **Proper file permissions** - SSH keys: 600, public: 644

### Security Features

#### 1. Credential Management
- **Azure**: Delegated to `az login`
- **GitHub**: Delegated to `gh auth login`
- **SSH Keys**: Generated locally, never transmitted
- **No storage**: Zero credentials stored in application

#### 2. Path Validation (7-Layer Defense)
```python
# Example from file_transfer module
1. Reject absolute paths
2. Reject parent directory (..)
3. Reject special files (/dev, /proc)
4. Reject hidden paths (.ssh, .aws)
5. Reject credential paths
6. Validate file extensions
7. Normalize and verify final path
```

#### 3. Command Sanitization
```python
# All subprocess calls are validated
- No arbitrary command execution
- Whitelist of allowed commands
- Parameter validation before execution
- Output sanitization before logging
```

### .gitignore Coverage
Comprehensive protection against credential commits:
- `.env`, `.env.*` (environment variables)
- `*.pem`, `*.key` (private keys)
- `.ssh/`, `.azure/`, `.aws/` (credential directories)
- `secrets.json`, `*.credentials` (credential files)
- 609 lines total covering all secret patterns

---

## Testing Strategy

### TDD Pyramid (60/30/10)

```
     /\
    /E2E\      10% - Real VMs, full workflow
   /------\
  /  INT  \    30% - Multi-module, mocked Azure
 /----------\
/    UNIT   \  60% - Single module, fast
-------------
```

### Test Commands
```bash
# Fast feedback (< 3 seconds)
pytest tests/unit/ -v

# Skip expensive E2E tests
pytest tests/ -m "not e2e"

# Full suite (creates real VMs, 5-10 min)
pytest tests/

# Single test file
pytest tests/unit/test_vm_provisioning.py -v

# Coverage report
pytest tests/unit/ --cov=src/azlin --cov-report=term-missing
```

### Writing Tests (TDD Workflow)
1. **RED**: Write failing test first
2. **GREEN**: Implement minimum code to pass
3. **REFACTOR**: Clean up while keeping tests green

Example:
```python
# tests/unit/test_new_feature.py
def test_feature_does_something():
    """Test that feature does X correctly."""
    # RED: This will fail
    result = new_feature.do_something()
    assert result == expected_value

# src/azlin/new_feature.py
def do_something():
    # GREEN: Implement to make test pass
    return expected_value

# REFACTOR: Clean up implementation
def do_something():
    # Better implementation, tests still pass
    return compute_expected_value()
```

---

## Development Patterns

### 1. Module Structure
```python
"""Module docstring - clear purpose statement.

This module handles X by doing Y.
"""

from typing import List, Optional
from dataclasses import dataclass

__all__ = ["PublicClass", "public_function"]  # Explicit API

@dataclass
class PublicClass:
    """Public class - appears in __all__."""
    field: str

class _PrivateClass:
    """Private class - NOT in __all__."""
    pass

def public_function() -> str:
    """Public function - appears in __all__."""
    return "result"

def _private_function() -> str:
    """Private function - NOT in __all__."""
    return "internal"
```

### 2. Error Handling
```python
# Custom exceptions inherit from base
class AzlinError(Exception):
    """Base exception for azlin."""

class ProvisioningError(AzlinError):
    """Raised when VM provisioning fails."""

# Fail fast with clear messages
def provision_vm(config: VMConfig) -> VMDetails:
    if not config.name:
        raise ProvisioningError("VM name is required")
    # ... rest of implementation
```

### 3. Configuration Management
```python
# Use dataclasses for configuration
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SSHConfig:
    """SSH connection configuration."""
    host: str
    user: str
    key_path: Path
    port: int = 22
```

### 4. Remote Execution Pattern
```python
# Use RemoteExecutor for commands on VMs
from azlin.remote_exec import RemoteExecutor

executor = RemoteExecutor(ssh_config)
result = executor.run_command("ls -la /home/azureuser")
if result.exit_code == 0:
    print(result.stdout)
```

---

## Common Tasks for AI Agents

### Adding a New Module (Brick)

1. **Create module file**: `src/azlin/modules/new_module.py`
2. **Write tests first**: `tests/unit/test_new_module.py`
3. **Implement module** following brick pattern
4. **Update `__init__.py`**: Add to `__all__`
5. **Run tests**: `pytest tests/unit/test_new_module.py -v`
6. **Document**: Add to this guide if needed

### Adding a New CLI Command

1. **Update `cli.py`**: Add `@main.command()`
2. **Write tests**: `tests/unit/test_cli.py`
3. **Implement command** using existing bricks
4. **Update help text**: Ensure `--help` is clear
5. **Update QUICK_REFERENCE.md**: Document command

### Fixing a Bug

1. **Write failing test** reproducing the bug (RED)
2. **Fix the code** to make test pass (GREEN)
3. **Refactor** if needed (REFACTOR)
4. **Verify** no other tests broke
5. **Commit** with clear message referencing issue

### Adding a Feature

1. **Create GitHub issue** describing feature
2. **Create feature branch**: `feature/feature-name`
3. **Write failing tests** (TDD: RED)
4. **Implement feature** (TDD: GREEN)
5. **Refactor** (TDD: REFACTOR)
6. **Update documentation** (README, docs/)
7. **Create PR** with clear description
8. **Address review** feedback
9. **Merge** when approved

---

## Azure Integration

### VM Provisioning Flow
```
1. Prerequisites Check → 2. Azure Auth → 3. SSH Key Gen
                                              ↓
4. Cloud-Init Script ← 5. VM Creation ← 6. Resource Group
                              ↓
7. Wait for VM Ready → 8. Get Public IP → 9. SSH Connect
```

### Cloud-Init Configuration
- **Location**: `vm_provisioning.py._generate_cloud_init()`
- **Purpose**: Automate VM setup on first boot
- **Installs**: Docker, Azure CLI, GitHub CLI, Git, Node.js, Python, Rust, Go, .NET, AI CLI tools
- **Configures**: npm user-local, SSH, tmux

### VM Lifecycle Commands
- `azlin` - Provision new VM or connect to existing
- `azlin list` - List all VMs
- `azlin status` - Show detailed VM status
- `azlin start <name>` - Start stopped VM
- `azlin stop <name>` - Deallocate VM (save costs)
- `azlin kill <name>` - Delete VM and resources
- `azlin killall` - Delete all VMs in resource group

---

## Success Criteria

### Functional Requirements
- ✅ `azlin` creates VM and connects via SSH with tmux
- ✅ `azlin --repo <url>` clones repo on VM
- ✅ All development tools installed on VM
- ✅ SSH key-based authentication works
- ✅ Tmux session persists across reconnects
- ✅ npm configured for user-local installs
- ✅ AI CLI tools (Copilot, Codex, Claude) pre-installed

### Non-Functional Requirements
- ✅ Total provisioning time < 7 minutes
- ✅ Test coverage > 80%
- ✅ Zero credentials in logs or code
- ✅ Works on macOS, Linux, WSL, Windows
- ✅ Proper error messages for all failures

### Code Quality Requirements
- ✅ All modules follow brick philosophy
- ✅ Clear public API contracts (`__all__`)
- ✅ Comprehensive test suite (TDD pyramid)
- ✅ Standard library preference
- ✅ Security best practices followed

---

## Troubleshooting

### Common Issues

#### Import Errors
```bash
# Ensure src/ is in PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:${PWD}/src"

# Or use editable install
uv pip install -e .
```

#### Test Failures
```bash
# Run specific test with verbose output
pytest tests/unit/test_module.py::test_function -vv

# Show stdout/stderr
pytest tests/unit/test_module.py -s

# Stop on first failure
pytest tests/unit/ -x
```

#### Azure CLI Issues
```bash
# Check Azure login status
az account show

# Re-authenticate
az login

# Set subscription
az account set --subscription "subscription-id"
```

---

## Resources

### Internal Documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete system design
- **[testing/test_strategy.md](testing/test_strategy.md)** - Testing guidelines
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference
- **[UV_USAGE.md](UV_USAGE.md)** - uv package manager guide

### External Resources
- **Azure CLI**: https://docs.microsoft.com/cli/azure/
- **GitHub CLI**: https://cli.github.com/manual/
- **Python Testing**: https://docs.pytest.org/
- **uv Documentation**: https://docs.astral.sh/uv/

### Development Tools
- **pytest**: Testing framework
- **ruff**: Fast Python linter
- **pyright**: Type checker
- **uv**: Package manager
- **pre-commit**: Git hooks

---

## Contributing Guidelines

### For AI Agents

1. **Always use TDD**: Write tests first (RED → GREEN → REFACTOR)
2. **Follow brick philosophy**: Self-contained, single responsibility
3. **Explicit public APIs**: Define `__all__` in every module
4. **Comprehensive docstrings**: Explain purpose, parameters, returns
5. **Security first**: Never store credentials, validate all inputs
6. **Update documentation**: Keep this guide and others current

### Commit Messages
```
feat: Add new feature
fix: Fix bug in module
docs: Update documentation
test: Add tests for feature
refactor: Improve code structure
chore: Maintenance tasks
```

### Pull Request Process
1. Create feature branch from main
2. Implement with TDD (tests first)
3. Ensure all tests pass
4. Update documentation
5. Create PR with clear description
6. Address review feedback
7. Merge when approved

---

## Glossary

- **Brick**: Self-contained module with single responsibility
- **Cloud-Init**: First-boot VM configuration system
- **Delegation Pattern**: Authentication handled by external tools (az, gh)
- **E2E**: End-to-end tests (expensive, use real resources)
- **TDD**: Test-Driven Development (RED → GREEN → REFACTOR)
- **VM**: Virtual Machine on Azure
- **uvx**: Tool for running Python packages without installation

---

**Last Updated**: 2025-10-15
**Maintainer**: azlin project
**License**: MIT
