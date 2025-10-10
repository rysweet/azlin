# azlin Documentation

This directory contains comprehensive documentation for azlin - Azure VM provisioning CLI.

## Documentation by Audience

### For Users

- **[../README.md](../README.md)** - Project overview, quick start, and installation
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Command reference and examples
- **[UV_USAGE.md](UV_USAGE.md)** - Using azlin with uv package manager

### For Developers

- **[ARCHITECTURE_SUMMARY.md](ARCHITECTURE_SUMMARY.md)** - High-level system overview
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete architecture specification
- **[TEST_STRATEGY.md](TEST_STRATEGY.md)** - Testing approach and strategy

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
1. Read [ARCHITECTURE_SUMMARY.md](ARCHITECTURE_SUMMARY.md) for system overview
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design
3. Follow [TEST_STRATEGY.md](TEST_STRATEGY.md) for testing approach

**Using uv**
- See [UV_USAGE.md](UV_USAGE.md) for fast uv-based workflows

## Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── QUICK_REFERENCE.md           # Command reference for daily use
├── UV_USAGE.md                  # uv package manager workflows
├── ARCHITECTURE_SUMMARY.md      # System overview for developers
├── ARCHITECTURE.md              # Complete architecture spec
├── TEST_STRATEGY.md             # Testing strategy
└── archive/                     # Historical implementation docs
    ├── IMPLEMENTATION_COMPLETE.md
    ├── V2_FEATURES.md
    └── FEATURES_10_11_12.md
```

## Contributing

See the main [README.md](../README.md) for contribution guidelines and development philosophy.

---

**Quick Links:**
[Main README](../README.md) |
[Quick Reference](QUICK_REFERENCE.md) |
[Architecture](ARCHITECTURE.md) |
[Testing](TEST_STRATEGY.md)
