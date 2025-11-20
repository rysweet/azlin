# Release Notes - azlin v0.3.0

**Release Date**: November 20, 2025
**Previous Version**: 2.0.0 (October 27, 2025)

---

## 🎉 Major Features

### Azure Key Vault SSH Storage (Multi-Tenant)
**Issues**: #362, #363, #365

Store SSH keys in Azure Key Vault for seamless multi-host VM access with **full multi-context/multi-tenant support**.

**Usage:**
```bash
# System 1
azlin new my-vm          # Auto-stores key in Key Vault

# System 2
azlin connect my-vm      # Auto-retrieves from Key Vault
```

**Multi-Context Support:**
- Each context gets its own Key Vault
- Keys isolated per subscription/tenant
- Service Principal auth per context
- Verified with 2 contexts, 7 VMs

**Features:**
- Fully automatic (no manual setup)
- Auto-creates Key Vault per context
- Auto-assigns RBAC for each tenant
- Works across different Azure tenants
- Cost: ~$0.03/month per context

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
- Key Vault SSH storage (multi-tenant)
- Auto-setup Key Vault
- Remote command execution
- Bastion private IP
- Multi-context aggregation (#327, #328, #333, #346, #351, #352)
- Cost-aware autopilot (#336, #344)
- GitHub runner fleet (#338)
- Docker Compose orchestration (#339, #342)
- VS Code integration (#337, #343)
- Distributed commands (#335, #341)

**Fixes (19):**
- SSH terminal opening (#358)
- Bastion routing (#359, #360)
- Natural language agent (#361)
- Config protection (#315)
- Subscription switching (#329, #355)
- PTY allocation (#349)
- Tmux session name default (#366, #367)
- And 12 more...

---

## 📊 Statistics

- 28 commits in last week
- 6 major features
- 19 bug fixes
- 100% CI coverage maintained
- 7 VMs across 2 contexts with Key Vault

---

## 🚀 Upgrade

```bash
uv cache clean
uvx --from git+https://github.com/rysweet/azlin azlin --version
# Should show: azlin, version 0.3.0
```

**Breaking Changes**: None (fully backward compatible)

---

## 🔐 Multi-Tenant Verification

Tested and verified with:
- **Context 1** (defenderatevet17): 4 VMs, Key Vault azlin-kv-cec8c6
- **Context 2** (defenderatevet12): 3 VMs, Key Vault azlin-kv-c3a1a6
- Service Principal auth configured for both contexts

---

Report issues: https://github.com/rysweet/azlin/issues
