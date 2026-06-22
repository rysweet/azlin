# Azlin Rust Architecture

Azure VM fleet management CLI. 5-crate workspace, all Azure operations via `az` CLI subprocess.

## Workspace Layout

```
rust/
├── crates/
│   ├── azlin-core/      # Types, config, errors, input sanitizer
│   ├── azlin-azure/     # az CLI wrappers, auth, retry, rate limiting
│   ├── azlin-ai/        # Anthropic Claude API for NLP commands
│   ├── azlin-cli/       # Clap command definitions, table formatting
│   └── azlin/           # Main binary (command handlers, SSH routing)
└── docs/
    └── ARCHITECTURE.md
```

### Crate Dependencies

```
azlin (binary)
├── azlin-cli     (command parsing)
├── azlin-azure   (VM operations)
│   └── azlin-core (types, config)
└── azlin-ai      (NLP commands)
    └── azlin-core
```

## Crate Details

### azlin-core

Shared types with no Azure dependencies.

| File          | Purpose                                    |
|---------------|--------------------------------------------|
| models.rs     | `VmInfo`, `CreateVmParams`, `ProvisioningState` enum |
| config.rs     | `AzlinConfig` (TOML), atomic writes        |
| error.rs      | `AzlinError` enum, `Result<T>` alias       |
| sanitizer.rs  | Input sanitization (YAML injection, shell escapes) |

### azlin-azure

All Azure operations go through `az` CLI subprocess. No Azure Rust SDK in production.

| File               | Purpose                                      |
|--------------------|----------------------------------------------|
| vm.rs              | `VmManager` -- list, get, start, stop, delete, create, tag |
| auth.rs            | `AzureAuth` -- subscription/resource group from az account |
| retry.rs           | Exponential backoff for transient failures   |
| rate_limiter.rs    | Token bucket rate limiter for az CLI calls   |
| cloud_init.rs      | Cloud-init template generation               |
| costs.rs           | VM cost estimation                           |
| orphan_detector.rs | Find orphaned disks/NICs/PIPs                |
| error_handler.rs   | az CLI stderr parsing                        |

**Why no Azure Rust SDK?** `azure_mgmt_*` 0.2 requires `azure_core` 0.2, while `azure_identity` 0.22 requires `azure_core` 0.22. These versions are incompatible. The `CredentialAdapter` bridge was fragile and untestable. The `az` CLI is stable, well-documented, and already authenticated.

### azlin-ai

Single-file crate. Sends NLP commands to Anthropic Claude API, parses structured responses into azlin operations.

### azlin-cli

Clap derive definitions for all commands and subcommands. `table.rs` provides `new_table()` helper for consistent terminal output.

### azlin (main binary)

7.8K LOC `main.rs` with command handlers and 35 helper modules (12 extracted files + 27 inline modules under 50 lines each).

| Extracted File          | Purpose                          |
|-------------------------|----------------------------------|
| display_helpers.rs      | Table formatting, OS detection   |
| list_helpers.rs         | VM list with size/IP enrichment  |
| create_helpers.rs       | Interactive VM creation wizard   |
| templates.rs            | VM template definitions          |
| contexts.rs             | Bastion/region context helpers   |
| sessions.rs             | Tmux session management          |
| health_parse_helpers.rs | Parse health check output        |
| snapshot_helpers.rs     | VM snapshot operations           |
| tests.rs                | Integration tests                |
| env_helpers.rs          | Environment variable helpers     |
| azdoit.rs              | Natural language command execution (separate binary) |

## Azure Operations

### VmManager

All operations are synchronous and use `az_cli_with_timeout()`.

```
VmManager::new(auth)           // default 120s timeout
VmManager::with_timeout(auth, secs)  // configurable timeout

list_vms(rg)          // cached, 60-min TTL
list_vms_no_cache(rg) // bypasses cache (--no-cache flag)
list_all_vms()        // all VMs across resource groups
get_vm(rg, name)      // single VM details
start_vm(rg, name)
stop_vm(rg, name, deallocate)
delete_vm(rg, name)
create_vm(params)
add_tag(rg, name, k, v)
remove_tag(rg, name, k)
list_tags(rg, name)
invalidate_cache()    // static, clears process-level HashMap
```

### az_cli_with_timeout

Runs `az` subprocess with configurable timeout (default 120s). Uses a background thread to drain stdout/stderr pipes, preventing deadlock when output exceeds OS pipe buffer.

## SSH Routing

### VmSshTarget

```rust
struct VmSshTarget {
    ip: String,
    user: String,
    bastion: Option<BastionInfo>,  // name, resource_group
}
```

**Routing logic:**

- **Public IP VMs** -- direct `ssh` subprocess
- **Private IP VMs** -- `az network bastion ssh` with SSH key auth
- **`azlin new --bastion-name`** -- when create-time SSH is bastion-routed, the
  same override is reused for post-create auth forwarding, home seeding, and
  the first auto-connect shell
- **Permission denied on bastion-routed targets** -- can retry after `az vm user update` re-pushes the local public key

**Commands using SSH:** `w`, `ps`, `top`, `health`, `env`, `logs`, `connect`

## List Command Output

### Default Columns

Session | Tmux | OS | Status | IP | Region | CPU | Mem

### Wide Mode (--wide)

Adds: VM Name | SKU

### Layout

1. Bastion host table (if bastions exist in resource group)
2. VM table with enriched data
3. Footer: `Total: N VMs` or `Total: N VMs | M tmux sessions`

### Data Enrichment

- **OS** -- detected from image offer string (Ubuntu codenames, RHEL, Debian, etc.)
- **IP** -- annotated `(Pub)` / `(Bast)` / `N/A`
- **CPU/Mem** -- exact values from `az vm list-sizes` (cached per region)
- **Tmux** -- session count from SSH probe

## Caching

| Data        | TTL    | Storage              | Bypass       |
|-------------|--------|----------------------|--------------|
| VM list     | 60 min | Process-level HashMap | `--no-cache` |
| VM sizes    | 60 min | Per-region HashMap   | N/A          |

Both caches are in-memory only. They reset on process exit.

## Build and Test

```bash
cd rust && cargo build --workspace
RUST_MIN_STACK=8388608 cargo test --workspace
```

The increased stack size is needed because some tests exercise deep call chains through the az CLI parsing code.
