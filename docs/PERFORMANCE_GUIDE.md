# Azure CLI Performance Guide

## Overview

This guide documents performance characteristics of azlin commands and best practices for minimizing Azure API costs and latency.

## Command Performance Matrix

| Command | Default Latency | API Calls | Cacheable | Optimization |
|---------|----------------|-----------|-----------|--------------|
| `azlin list` | 0.5-1s | 1 (single RG) | No | Use default RG |
| `azlin list --show-all-vms` | 10-30s | N (all RGs) | No | Avoid unless needed |
| `azlin list --show-quota` | +2-8s | 1 per region | Yes (5min) | Use `--no-quota` for speed |
| `azlin list --show-tmux` | +1-3s | 1 per VM | No | Use `--no-tmux` for speed |
| `azlin new` | 3-5min | ~10-15 | No | Cannot optimize |
| `azlin connect` | <1s | 0 | No | Already fast |

## Performance Best Practices

### 1. Use Configured Resource Group

**Fast** ✅:
```bash
# Set default RG once
echo 'default_resource_group = "my-rg"' >> ~/.azlin/config.toml

# Fast queries forever
azlin list  # 0.5-1s
```

**Slow** ❌:
```bash
# No configured RG, forced to use --show-all-vms
azlin list --show-all-vms  # 10-30s every time
```

### 2. Disable Quota Fetching for Dev/Test

**Fast** ✅:
```bash
azlin list --no-quota  # Skip 2-8s of quota API calls
```

**Use quota only when needed**:
```bash
azlin list --show-quota  # When capacity planning
```

### 3. Disable Tmux Queries for Quick Checks

**Fast** ✅:
```bash
azlin list --no-tmux  # Skip 1-3s of SSH connections
```

### 4. Combine Optimizations

**Fastest possible list**:
```bash
azlin list --no-quota --no-tmux  # 0.3-0.5s
```

**Default (balanced)**:
```bash
azlin list  # 2-4s with quota & tmux
```

## API Call Breakdown

### azlin list (Default)
1. `az vm list --resource-group <rg> --show-details` (0.5-1s)
2. `az network public-ip list --resource-group <rg>` (0.3-0.5s, batched)
3. If `--show-quota` (default): `az vm list-usage --location <region>` per region (1-3s each)
4. If `--show-tmux` (default): SSH to each running VM (0.5-1s each, parallel max 10)

**Total**: 2-8s depending on number of VMs and regions

### azlin list --show-all-vms
1. `az vm list` (NO --resource-group) (10-30s for large subscriptions)
2. `az vm show` for each VM to get tags (N API calls)
3. Same quota & tmux overhead as default

**Total**: 10-60s depending on subscription size

## Quota Fetching Performance

### Implementation Details
- **Parallelization**: ThreadPoolExecutor with max_workers=10
- **Cache**: 5-minute TTL per region:quota pair
- **API**: `az vm list-usage --location <region>`

### Cost Analysis

| Scenario | Regions | API Calls | Latency | Cached Benefit |
|----------|---------|-----------|---------|----------------|
| Single region | 1 | 1 | 1-2s | 5 min reuse |
| Multi-region | 3 | 3 (parallel) | 2-3s | 5 min reuse |
| Many regions | 5+ | 5+ (parallel, max 10) | 3-8s | 5 min reuse |

### When Quota is Useful
- ✅ Capacity planning near limits
- ✅ Multi-region deployments
- ✅ Team quota monitoring
- ❌ Dev/test with abundant quota (most users)

### Recommendation
For most dev/test users (95%+ of quota available):
```bash
# Add to your shell alias
alias azl='azlin list --no-quota --no-tmux'  # Fast 0.3-0.5s
```

## Future Optimizations

See open issues:
- [#217](https://github.com/rysweet/azlin/issues/217): Change --show-quota default to False
- [#218](https://github.com/rysweet/azlin/issues/218): Remove dead code from vm_manager.py

## Measuring Your Performance

```bash
# Time a command
time azlin list

# Compare with optimizations
time azlin list --no-quota --no-tmux
```

## Cost Impact

Azure API calls are free (within rate limits), but latency impacts developer productivity:

| Daily Lists | Default (3s) | Optimized (0.5s) | Time Saved |
|-------------|--------------|------------------|------------|
| 10 | 30s | 5s | 25s/day |
| 50 | 150s (2.5min) | 25s | 125s/day |
| 100 | 300s (5min) | 50s | 250s/day (4min) |

For teams checking VMs frequently, optimizations save significant time!
