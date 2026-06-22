# azlin Documentation

> **Note**: As of v2.6.17, azlin is implemented in Rust. The `azlin` command routes through a Python bridge to the native Rust binary (75-85x faster). The Python CLI remains available as `azlin-py`. See [../README.md](../README.md) for updated installation instructions.

This directory contains comprehensive documentation for azlin - Azure VM provisioning CLI.

## Documentation by Audience

### For Users

- **[../README.md](../README.md)** - Project overview, quick start, and installation
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference and examples
- **[pwa/README.md](pwa/README.md)** - Mobile PWA for managing VMs from iPhone (zero-config setup!)
- **[pwa/getting-started.md](pwa/getting-started.md)** - PWA installation and automatic configuration guide
- **[reference/destroy-command.md](reference/destroy-command.md)** - Complete guide to VM deletion
- **[how-to/restore-sessions.md](how-to/restore-sessions.md)** - Restore all active VM sessions with new terminal windows
- **[tutorials/quick-start-restore.md](tutorials/quick-start-restore.md)** - 5-minute quick start guide for session restore
- **[tutorials/platform-setup-restore.md](tutorials/platform-setup-restore.md)** - Platform-specific setup guide for session restore
- **[reference/configuration-reference.md](reference/configuration-reference.md)** - Complete configuration reference for terminal and restore settings
- **[UV_USAGE.md](UV_USAGE.md)** - Using azlin with uv package manager
- **[how-to/azure-cli-wsl2-setup.md](how-to/azure-cli-wsl2-setup.md)** - Azure CLI detection and auto-fix for WSL2
- **[how-to/troubleshoot-connection-issues.md](how-to/troubleshoot-connection-issues.md)** - Comprehensive troubleshooting guide
- **[tutorials/wsl2-setup-walkthrough.md](tutorials/wsl2-setup-walkthrough.md)** - Step-by-step Azure CLI setup in WSL2
- **[troubleshooting/timeout-issues.md](troubleshooting/timeout-issues.md)** - Timeout troubleshooting for azlin list command
- **[troubleshooting/restore-issues.md](troubleshooting/restore-issues.md)** - Troubleshooting session restore issues
- **[troubleshooting/azure-cli-wsl2-issues.md](troubleshooting/azure-cli-wsl2-issues.md)** - Azure CLI WSL2 troubleshooting
- **[backup-disaster-recovery.md](backup-disaster-recovery.md)** - Automated backup scheduling, cross-region replication, and DR testing
- **[features/azure-cli-wsl2-detection.md](features/azure-cli-wsl2-detection.md)** - Azure CLI WSL2 detection feature overview
- **[features/tmux-session-status.md](features/tmux-session-status.md)** - Visual tmux session connection status in VM listings
- **[features/memory-latency.md](features/memory-latency.md)** - Memory allocation and network latency monitoring
- **[features/session-restore.md](features/session-restore.md)** - Automatic session restore feature overview and architecture
- **[features/credential-forwarding.md](features/credential-forwarding.md)** - Automatic credential forwarding (gh, az, Copilot, Claude) to new VMs
- **[how-to/forward-credentials.md](how-to/forward-credentials.md)** - Forward developer credentials to a VM after creation
- **[reference/credential-forwarding.md](reference/credential-forwarding.md)** - Credential forwarding technical reference (detection, SCP, security)

### For Developers

- **[AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)** - **START HERE for AI agents** - Comprehensive guide to azlin development
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete architecture specification
- **[reference/azure-cli-detection.md](reference/azure-cli-detection.md)** - Azure CLI detection technical reference
- **[testing/test_strategy.md](testing/test_strategy.md)** - Testing approach and strategy
- **[technical/audit-error-handling.md](technical/audit-error-handling.md)** - Audit logging and error handling improvements

### For AI Agents

- **[AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)** - Complete development guide including:
  - Project philosophy (brick architecture, security, TDD)
  - Module structure and patterns
  - Testing strategies and workflows
  - Common development tasks
  - Security architecture
  - Troubleshooting guide

### Historical Documentation

Historical implementation records have been archived. See the project's git history for v2.0 implementation details.

## Quick Navigation

**Getting Started**
```bash
# Download pre-built binary (fastest)
curl -sSL https://github.com/rysweet/azlin/releases/latest/download/azlin-linux-x86_64.tar.gz | tar xz -C ~/.local/bin

# Or run via uvx (auto-migrates to Rust)
uvx --from git+https://github.com/rysweet/azlin azlin --help

# See all commands
azlin --help

# View quick reference
cat docs/QUICK_REFERENCE.md
```

**Development Workflow**
1. Review [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design
2. Follow [testing/test_strategy.md](testing/test_strategy.md) for testing approach

**Using uv**
- See [UV_USAGE.md](UV_USAGE.md) for fast uv-based workflows

## Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── AI_AGENT_GUIDE.md            # **START HERE for AI agents**
├── QUICK_REFERENCE.md           # Command reference for daily use
├── UV_USAGE.md                  # uv package manager workflows
├── ARCHITECTURE.md              # Complete architecture spec
├── backup-disaster-recovery.md  # Backup and DR automation
├── technical/
│   └── audit-error-handling.md  # Audit logging and error handling
└── testing/
    └── test_strategy.md         # Testing strategy
```

## Contributing

See the main [README.md](../README.md) for contribution guidelines and development philosophy.

---

**Quick Links:**
[Main README](../README.md) |
[Quick Reference](QUICK_REFERENCE.md) |
[Architecture](ARCHITECTURE.md) |
[Testing](testing/test_strategy.md)
