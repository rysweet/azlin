# azlin Documentation

This directory contains comprehensive documentation for azlin - Azure VM provisioning CLI.

## Documentation by Audience

### For Users

- **[../README.md](../README.md)** - Project overview, quick start, and installation
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference and examples
- **[UV_USAGE.md](UV_USAGE.md)** - Using azlin with uv package manager

### For Developers

- **[AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)** - **START HERE for AI agents** - Comprehensive guide to azlin development
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete architecture specification
- **[TEST_STRATEGY.md](TEST_STRATEGY.md)** - Testing approach and strategy

### For AI Agents

- **[AI_AGENT_GUIDE.md](AI_AGENT_GUIDE.md)** - Complete development guide including:
  - Project philosophy (brick architecture, security, TDD)
  - Module structure and patterns
  - Testing strategies and workflows
  - Common development tasks
  - Security architecture
  - Troubleshooting guide

### Historical Documentation

Documentation in `archive/` contains implementation records and historical snapshots:

- **[archive/IMPLEMENTATION_COMPLETE.md](archive/IMPLEMENTATION_COMPLETE.md)** - v2.0 implementation checklist
- **[archive/V2_FEATURES.md](archive/V2_FEATURES.md)** - v2.0 feature details
- **[archive/FEATURES_10_11_12.md](archive/FEATURES_10_11_12.md)** - Features 10-12 implementation

## Quick Navigation

**Getting Started**
```bash
# Install azlin
pip install azlin

# See all commands
azlin --help

# View quick reference
cat docs/QUICK_REFERENCE.md
```

**Development Workflow**
1. Review [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design
2. Follow [TEST_STRATEGY.md](TEST_STRATEGY.md) for testing approach

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
└── TEST_STRATEGY.md             # Testing strategy
```

## Contributing

See the main [README.md](../README.md) for contribution guidelines and development philosophy.

---

**Quick Links:**
[Main README](../README.md) |
[Quick Reference](QUICK_REFERENCE.md) |
[Architecture](ARCHITECTURE.md) |
[Testing](TEST_STRATEGY.md)
