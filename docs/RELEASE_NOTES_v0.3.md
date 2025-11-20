# Release Notes - azlin v0.3.0

**Release Date**: November 20, 2025
**Previous Version**: 2.0.0 (October 27, 2025)

---

## 🎉 Major Features

### Azure Key Vault SSH Storage
**Issues**: #362, #363, #365

Store SSH keys in Azure Key Vault for seamless multi-host VM access.

**Usage:**
```bash
# System 1
azlin new my-vm          # Auto-stores key in Key Vault

# System 2
azlin connect my-vm      # Auto-retrieves from Key Vault
```

**Features:**
- Fully automatic (no manual setup)
- Auto-creates Key Vault
- Auto-assigns RBAC
- Service Principal support
- Cost: ~$0.03/month

### Remote Commands in Current Terminal
**Issues**: #356, #358

Commands now execute inline instead of opening new windows.

```bash
azlin connect my-vm -- df -h
# Output appears in current terminal ✅
```

### Bastion-Only VM Support
**Issues**: #359, #360

VMs without public IPs now work via Bastion.

```bash
azlin connect private-vm  # Auto-uses Bastion ✅
```

### Enhanced Natural Language Agent
**Issue**: #361

Fixed false claims about azlin capabilities.

```bash
azlin do "connect to my-vm"  # Now works correctly ✅
```

---

## 🔧 All Changes

**Features (10):**
- Key Vault SSH storage
- Auto-setup Key Vault
- Remote command execution
- Bastion private IP
- Multi-context aggregation
- Cost-aware autopilot
- GitHub runner fleet
- Docker Compose orchestration
- VS Code integration
- Distributed commands

**Fixes (18):**
- SSH terminal opening (#358)
- Bastion routing (#359, #360)
- Natural language agent (#361)
- Config protection (#315)
- Subscription switching (#329, #355)
- PTY allocation (#349)
- And 12 more...

---

## 📊 Statistics

- 28 commits
- 6 major features
- 18 bug fixes
- 100% CI coverage

---

## 🚀 Upgrade

```bash
uv cache clean
uvx --from git+https://github.com/rysweet/azlin azlin --version
```

**Breaking Changes**: None (fully backward compatible)

---

Report issues: https://github.com/rysweet/azlin/issues
