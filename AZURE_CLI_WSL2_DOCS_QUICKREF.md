# Azure CLI WSL2 Detection - Documentation Quick Reference

## 🎯 Quick Links

| Need | Document | Size |
|------|----------|------|
| **Overview** | [Feature Overview](docs/features/azure-cli-wsl2-detection.md) | 8.2 KB |
| **Setup** | [How-To Guide](docs/how-to/azure-cli-wsl2-setup.md) | 4.8 KB |
| **Learning** | [Tutorial Walkthrough](docs/tutorials/wsl2-setup-walkthrough.md) | 17 KB |
| **Problems** | [Troubleshooting](docs/troubleshooting/azure-cli-wsl2-issues.md) | 13 KB |
| **Technical** | [Reference](docs/reference/azure-cli-detection.md) | 19 KB |

## 📖 Documentation by User Journey

### First Time User
1. Read: [How-To Guide](docs/how-to/azure-cli-wsl2-setup.md) (Quick Start section)
2. Try: Run `azlin list` and follow prompts
3. If problems: [Troubleshooting](docs/troubleshooting/azure-cli-wsl2-issues.md)

### Learning User
1. Work through: [Tutorial Walkthrough](docs/tutorials/wsl2-setup-walkthrough.md)
2. All 5 scenarios with step-by-step instructions
3. Complete workflow example at the end

### Troubleshooting User
1. Quick fix: [Troubleshooting Guide](docs/troubleshooting/azure-cli-wsl2-issues.md)
2. Run diagnostics: `azlin --debug list 2>&1 | grep -i "azure cli\|wsl2"`
3. 7 common issues with symptoms → diagnosis → solution

### Developer
1. Architecture: [Technical Reference](docs/reference/azure-cli-detection.md)
2. Components: cli_detector.py, cli_installer.py, subprocess_helper.py
3. Testing: Unit tests, integration tests, manual scenarios

### Product Manager
1. Overview: [Feature Overview](docs/features/azure-cli-wsl2-detection.md)
2. Benefits, user experience, performance metrics, FAQ
3. Known limitations and future enhancements

## 🔍 Find by Topic

| Topic | Document | Section |
|-------|----------|---------|
| Automatic detection | How-To Guide | "How It Works" |
| Installation steps | Tutorial | Scenario 1 |
| Subprocess deadlock | Feature Overview | "Why This Matters" |
| Configuration | How-To Guide | "Configuration Options" |
| Environment variables | Reference | "Environment Variables" |
| Error codes | Reference | "Error Codes" |
| PATH priority | Tutorial | Scenario 3 |
| Network errors | Troubleshooting | Issue 2 |
| Permission errors | Troubleshooting | Issue 3 |
| Architecture | Reference | "Architecture Overview" |
| API reference | Reference | "API Reference" |
| Testing | Reference | "Testing Strategy" |

## 🚀 Quick Start (30 seconds)

```bash
# 1. Run azlin in WSL2
azlin list

# 2. If prompted, press Y
# Installation takes 30-60 seconds

# 3. Done! azlin now works
```

## 🔧 Quick Fix (Hung Commands)

```bash
# Install Linux Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Verify
which az  # Should show /usr/bin/az (NOT az.cmd)

# Test
azlin list  # Should work without hanging
```

## 📊 Quick Diagnostics

```bash
# Check environment
uname -r | grep -i microsoft  # WSL2?

# Check CLI
which -a az  # All Azure CLI installations

# Debug azlin
azlin --debug list 2>&1 | head -20
```

## 🎓 Example Scenarios

| Scenario | Document | Time |
|----------|----------|------|
| First-time setup | Tutorial Scenario 1 | 5 min |
| Manual install | Tutorial Scenario 2 | 3 min |
| PATH issues | Tutorial Scenario 3 | 2 min |
| Network error | Tutorial Scenario 4 | 5 min |
| Advanced config | Tutorial Scenario 5 | 3 min |
| Complete workflow | Tutorial (end) | 10 min |

## 🆘 Common Problems

| Problem | Solution | Document |
|---------|----------|----------|
| Commands hang | Install Linux CLI | Troubleshooting Issue 1 |
| Network error | Configure proxy | Troubleshooting Issue 2 |
| Permission denied | Check sudo access | Troubleshooting Issue 3 |
| Wrong CLI found | Fix PATH order | Troubleshooting Issue 4 |
| No detection | Verify WSL2 | Troubleshooting Issue 5 |
| Timeout errors | Increase timeout | Troubleshooting Issue 6 |
| CLI not found | Update config | Troubleshooting Issue 7 |

## 🏗️ Architecture Quick Reference

```
┌─────────────────────────────────────────────────────┐
│                   azlin Startup                      │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│              CLI Detector (cli_detector.py)          │
│  • Detect WSL2 environment                           │
│  • Detect Azure CLI installations                    │
│  • Determine compatibility                           │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  CLI Installer (cli_installer.py)                    │
│  • Interactive prompts                               │
│  • Automatic installation                            │
│  • Verification                                      │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│       Subprocess Helper (subprocess_helper.py)       │
│  • Explicit CLI path usage                           │
│  • Pipe draining (deadlock prevention)               │
│  • Error handling                                    │
└─────────────────────────────────────────────────────┘
```

## 📝 Documentation Standards

All documents follow:
- ✓ Eight Rules of Good Documentation
- ✓ Diataxis Framework (Tutorial/How-To/Reference/Explanation)
- ✓ Real runnable examples (50+ code blocks)
- ✓ Cross-linked for discoverability
- ✓ No temporal content (status/progress)
- ✓ Ruthless simplicity

## 📦 Files Created

```
docs/
├── README.md (updated)
├── features/
│   └── azure-cli-wsl2-detection.md    [NEW]
├── how-to/
│   └── azure-cli-wsl2-setup.md        [NEW]
├── reference/
│   └── azure-cli-detection.md         [NEW]
├── troubleshooting/
│   └── azure-cli-wsl2-issues.md       [NEW]
└── tutorials/
    └── wsl2-setup-walkthrough.md      [NEW]
```

---

**Total Documentation**: 5 documents, 62 KB, 100% complete
**Coverage**: All user journeys, all Diataxis types, all Eight Rules
**Status**: Production ready ✓
