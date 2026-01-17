# DISCOVERIES.md

This file documents non-obvious problems, solutions, and patterns discovered during development. It serves as a living knowledge base.

**Archive**: Entries older than 3 months are moved to [DISCOVERIES_ARCHIVE.md](./DISCOVERIES_ARCHIVE.md).

## Ubuntu Version Update Available - 24.04 LTS Supported (2026-01-17)

### Investigation Summary

Investigated current Ubuntu version used by azlin (22.04) and discovered that Azure now supports **Ubuntu 24.04 LTS (Noble Numbat)**, which is significantly newer and recommended for production use.

### Key Findings

**Current State**: azlin uses Ubuntu 22.04 (Jammy Jellyfish) in three locations
**Available**: Ubuntu 24.04 LTS (Noble Numbat) - latest LTS, released April 2024
**Compatibility**: All post-launch setup scripts (cloud-init) compatible with 24.04

#### Ubuntu Version Locations

Found three hardcoded references to Ubuntu 22.04:

1. **Terraform Strategy** (`src/azlin/agentic/strategies/terraform_strategy.py:481-486`)
   - Current: `offer = "0001-com-ubuntu-server-jammy"`, `sku = "22_04-lts-gen2"`
   - Update to: `offer = "ubuntu-24_04-lts"`, `sku = "server"`

2. **Azure CLI Strategy** (`src/azlin/agentic/strategies/azure_cli.py:413, 445`)
   - Current: `--image Ubuntu2204`
   - Update to: `--image Canonical:ubuntu-24_04-lts:server:latest`

3. **Sample Config/VM Provisioning** (`tests/fixtures/sample_configs.py:22, 119, 174` and `src/azlin/vm_provisioning.py:43`)
   - Current: `"image": "ubuntu-22.04"` and `image: str = "Ubuntu2204"`
   - Update to: `"image": "ubuntu-24.04"` and `image: str = "Ubuntu2404"`

#### Azure Image Details

Ubuntu 24.04 LTS available via:
- **Full URN**: `Canonical:ubuntu-24_04-lts:server:latest`
- **SKUs available**: server, minimal, server-arm64, cvm, ubuntu-pro
- **Recommendation**: Use `server` SKU for standard Gen2 VMs

#### Post-Launch Setup Compatibility Analysis

Reviewed cloud-init script in `vm_provisioning.py:702-799`:
- ✅ All package managers compatible (apt, snap, ppa)
- ✅ All packages available on Ubuntu 24.04
- ✅ Python 3.13 from deadsnakes PPA - works on 24.04
- ✅ GitHub CLI - architecture-independent
- ✅ Azure CLI - supports Ubuntu 24.04
- ✅ Node.js 20.x - supports Ubuntu 24.04
- ✅ Docker - available on 24.04

**Result**: No compatibility issues identified. All setup should work seamlessly.

### Recommendations

1. **Update default image to Ubuntu 24.04 LTS** in all three locations
2. **Test on single VM** before updating defaults
3. **Update documentation** to reflect new Ubuntu version
4. **Consider adding image parameter** to allow users to choose version

### Supporting Evidence

Azure CLI verification:
```bash
$ az vm image list --publisher Canonical --offer ubuntu-24_04-lts --sku server --all
# Returns multiple versions from 24.04.202404230 onwards
```

Available Ubuntu versions in Azure:
- Ubuntu 24.04 LTS (Noble) - **RECOMMENDED** - Latest LTS
- Ubuntu 23.10 (Mantic) - Available but short support
- Ubuntu 23.04 (Lunar) - EOL, not recommended
- Ubuntu 22.04 LTS (Jammy) - **CURRENT** - Still supported but older

### Lessons Learned

1. **Azure image naming conventions changed** - Old format: `0001-com-ubuntu-server-jammy`, New format: `ubuntu-24_04-lts`
2. **Always check cloud provider for newer LTS releases** - 24.04 has been available since April 2024
3. **Cloud-init scripts using standard package managers** are highly portable across Ubuntu versions
