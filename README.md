# azlin - Azure Ubuntu VM Provisioning CLI

**One command to create a fully-equipped development VM on Azure**

```bash
# Create VM with dev tools
azlin

# Create VM and clone GitHub repo
azlin --repo https://github.com/owner/repo
```

## What is azlin?

azlin automates the tedious process of setting up Azure Ubuntu VMs for development. In one command, it:

1. Authenticates with Azure
2. Provisions an Ubuntu 24.04 VM
3. Installs 12 essential development tools
4. Sets up SSH with key-based authentication
5. Starts a persistent tmux session
6. Optionally clones a GitHub repository

**Total time**: 4-7 minutes from command to working development environment.

## Development Tools Installed

Every azlin VM comes pre-configured with:

1. **Docker** - Container runtime
2. **Azure CLI (az)** - Azure management
3. **GitHub CLI (gh)** - GitHub integration
4. **Git** - Version control
5. **Node.js** - JavaScript runtime with user-local npm configuration
6. **Python 3** - Python runtime + pip
7. **Rust** - Systems programming language
8. **Golang** - Go programming language
9. **.NET 10 RC** - .NET development framework
10. **GitHub Copilot CLI** - AI-powered coding assistant
11. **OpenAI Codex CLI** - AI code generation
12. **Claude Code CLI** - AI coding assistant

### AI CLI Tools

Three AI-powered coding assistants are pre-installed and ready to use:

- **GitHub Copilot CLI** (`@github/copilot`) - AI pair programmer from GitHub
- **OpenAI Codex CLI** (`@openai/codex`) - Advanced AI code generation
- **Claude Code CLI** (`@anthropic-ai/claude-code`) - Anthropic's AI coding assistant

These tools are installed using npm's user-local configuration, so they're immediately available in your PATH without requiring sudo permissions.

### npm User-Local Configuration

Node.js is configured for user-local global package installations, which means:
- Install global npm packages **without sudo**: `npm install -g package-name`
- Packages are installed to `~/.npm-packages`
- Automatic PATH and MANPATH configuration
- Clean separation from system Node.js packages

## Prerequisites

Before using azlin, ensure these tools are installed:

- `az` (Azure CLI)
- `gh` (GitHub CLI)
- `git`
- `ssh`
- `tmux`

**macOS**: `brew install azure-cli gh git tmux`
**Linux**: See platform-specific installation in Prerequisites module

## Quick Start

```bash
# Install azlin
pip install azlin

# Create a development VM
azlin

# Create VM and clone a repo
azlin --repo https://github.com/microsoft/vscode

# Sync your dotfiles to existing VMs
azlin sync

# Copy files to/from VMs
azlin cp myfile.txt vm1:~/
azlin cp vm1:~/data.txt ./
```

## New in v2.1.0

### Home Directory Sync

Automatically sync your configuration files from `~/.azlin/home/` to all VMs:

```bash
# Setup: Place your dotfiles in ~/.azlin/home/
mkdir -p ~/.azlin/home
cp ~/.bashrc ~/.vimrc ~/.gitconfig ~/.azlin/home/

# Auto-syncs on VM creation and login
azlin  # Dotfiles automatically synced after provisioning

# Manual sync to specific VM
azlin sync --vm-name my-vm

# Preview what would be synced
azlin sync --dry-run
```

**Security**: Automatically blocks SSH keys, cloud credentials, .env files, and other secrets.

### Bidirectional File Transfer

Copy files between your local machine and VMs:

```bash
# Copy local file to VM
azlin cp report.pdf vm1:~/documents/

# Copy from VM to local
azlin cp vm1:~/results.tar.gz ./

# Preview transfer
azlin cp --dry-run large-dataset.zip vm1:~/
```

**Security**: 7-layer path validation prevents directory traversal and credential exfiltration.

## Architecture Documentation

This project follows the **brick philosophy**: self-contained modules with clear contracts that can be regenerated independently.

### For Users

- **README.md** (this file) - Quick start and usage
- **USAGE.md** - Detailed usage examples (coming soon)

### For Builders

Start here if you're implementing azlin:

1. **[BUILDER_QUICKSTART.md](BUILDER_QUICKSTART.md)** - Start here! 5-minute guide to get building
2. **[ARCHITECTURE_SUMMARY.md](docs/ARCHITECTURE_SUMMARY.md)** - High-level overview of the system
3. **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Complete architecture specification
4. **[MODULE_SPEC_TEMPLATE.md](MODULE_SPEC_TEMPLATE.md)** - Template for implementing each module
5. **[TEST_STRATEGY.md](docs/TEST_STRATEGY.md)** - Comprehensive testing approach

### For Architects

- **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** - Full system design
- **.claude/context/PHILOSOPHY.md** - Development philosophy
- **.claude/context/PATTERNS.md** - Proven patterns and solutions

## Project Structure

```
azlin/
├── src/azlin/                    # Source code
│   ├── cli.py                    # Main entry point
│   └── modules/                  # Self-contained bricks
│       ├── prerequisites.py      # Brick 1: Check required tools
│       ├── azure_auth.py         # Brick 2: Azure authentication
│       ├── ssh_keys.py           # Brick 3: SSH key management
│       ├── vm_provisioner.py     # Brick 4: VM provisioning
│       ├── ssh_connector.py      # Brick 5: SSH connection
│       ├── github_setup.py       # Brick 6: GitHub setup
│       ├── progress.py           # Brick 7: Progress display
│       └── notifications.py      # Brick 8: Notifications
│
├── tests/                        # Test suite (60/30/10 pyramid)
│   ├── unit/                     # 60% - Fast, isolated tests
│   ├── integration/              # 30% - Multi-module tests
│   └── e2e/                      # 10% - Full workflow tests
│
├── docs/                         # Architecture documentation
│   ├── ARCHITECTURE.md           # Complete system design
│   ├── ARCHITECTURE_SUMMARY.md  # Quick reference
│   ├── QUICK_REFERENCE.md        # Command reference
│   ├── README.md                 # Documentation index
│   ├── TEST_STRATEGY.md          # Testing approach
│   ├── UV_USAGE.md               # uv package manager guide
│   └── archive/                  # Historical documentation
│
└── .claude/                      # Claude framework
    ├── agents/                   # Agent definitions
    ├── context/                  # Development patterns
    └── tools/                    # Development tools
```

## Development Philosophy

This project embodies **ruthless simplicity**:

- **Standard library preference** - Minimize external dependencies
- **Brick architecture** - Self-contained, regeneratable modules
- **Security by design** - No credentials in code, comprehensive .gitignore
- **Fail fast** - Check prerequisites before any operations
- **TDD pyramid** - 60% unit, 30% integration, 10% E2E tests

See [PHILOSOPHY.md](.claude/context/PHILOSOPHY.md) for complete philosophy.

## The 9 Bricks

Each module is a self-contained "brick" with:
- Single clear responsibility
- Explicit public API (`__all__`)
- Comprehensive tests
- No tight coupling

| Brick | Purpose | Dependencies |
|-------|---------|--------------|
| Prerequisites | Verify required tools | stdlib only |
| Azure Auth | Handle az login | az CLI |
| SSH Key Manager | Generate SSH keys | ssh-keygen |
| VM Provisioner | Create Azure VM | az CLI |
| SSH Connector | Connect via SSH | ssh, tmux |
| GitHub Setup | Clone repo on VM | gh, git |
| Progress Display | Show real-time progress | stdlib only |
| Notifications | Send completion alerts | imessR (optional) |
| CLI Entry Point | Orchestrate all modules | All bricks |

## Security

azlin follows security best practices:

- **No credentials in code** - All credentials managed by external CLIs (az, gh)
- **SSH keys with correct permissions** - Private keys: 600, Public keys: 644
- **Output sanitization** - All subprocess output sanitized before logging
- **Comprehensive .gitignore** - Prevents accidental credential commits
- **No arbitrary command execution** - All commands validated

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) Security Architecture section for details.

## Testing

The project follows the **TDD pyramid** (60/30/10):

```
     /\
    /E2E\      10% - 6 tests - Real VMs
   /------\
  /  INT  \    30% - 20 tests - Multi-module
 /----------\
/    UNIT   \  60% - 80 tests - Single module
-------------
Total: 106 tests
```

### Running Tests

```bash
# Fast feedback (< 3 seconds)
pytest tests/ -m "not e2e"

# Full suite (5-10 minutes, creates real VMs)
pytest tests/

# Pre-commit hook (< 1 second)
pytest tests/ -m "unit"
```

See [TEST_STRATEGY.md](docs/TEST_STRATEGY.md) for complete testing approach.

## Implementation Status

**Current Phase**: Design Complete

- [x] Architecture design
- [x] Module specifications
- [x] Test strategy
- [x] Security architecture
- [ ] Implementation (In Progress)
- [ ] Integration tests
- [ ] E2E tests
- [ ] Documentation

## Contributing

This project is part of the Microsoft Hackathon 2025 and follows the **amplihack** framework for AI-assisted development.

### For Developers

1. Read [BUILDER_QUICKSTART.md](BUILDER_QUICKSTART.md)
2. Follow TDD approach (write tests first)
3. Use patterns from [PATTERNS.md](.claude/context/PATTERNS.md)
4. Follow brick philosophy (self-contained modules)

### For AI Agents

1. Read architecture documents in order
2. Implement modules following specifications
3. Write tests before implementation (TDD)
4. Update knowledge bases with learnings

## Success Criteria

### Functional
- ✅ `azlin` creates VM and connects via SSH with tmux
- ✅ `azlin --repo <url>` additionally clones repo
- ✅ All 9 dev tools installed on VM
- ✅ SSH key-based authentication works
- ✅ Tmux session persists across reconnects

### Non-Functional
- ✅ Total time < 7 minutes
- ✅ Test coverage > 80%
- ✅ Zero credentials in logs or code
- ✅ Works on macOS, Linux, WSL, Windows

### Code Quality
- ✅ All modules follow brick philosophy
- ✅ Clear contracts for each module
- ✅ Comprehensive test suite (106 tests)
- ✅ Standard library preference
- ✅ TDD pyramid (60/30/10)

## License

[License to be determined]

## Acknowledgments

- Built with [Claude Code](https://claude.com/claude-code)
- Part of Microsoft Hackathon 2025
- Powered by the amplihack framework

---

**Ready to build?** Start with [BUILDER_QUICKSTART.md](BUILDER_QUICKSTART.md)

**Need the big picture?** Read [ARCHITECTURE_SUMMARY.md](docs/ARCHITECTURE_SUMMARY.md)

**Want full details?** See [ARCHITECTURE.md](docs/ARCHITECTURE.md)
