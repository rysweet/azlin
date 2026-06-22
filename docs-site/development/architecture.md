# azlin Architecture Overview

azlin is written in Rust for fast startup and reliable execution. The CLI is structured as a workspace of focused crates, each handling a specific domain.

## Crate Structure

```
rust/
├── Cargo.toml                  # Workspace root
└── crates/
    ├── azlin-cli/              # CLI entry point and command routing
    ├── azlin-core/             # Shared types, config, caching, output
    ├── azlin-azure/            # Azure API interactions (VMs, storage, bastion)
    ├── azlin-ssh/              # SSH connections, tunneling, key management
    └── azlin-ai/               # AI features (do, doit, autopilot)
```

A Python bridge (`src/azlin/`) exists for backward compatibility. Running `azlin` routes through the bridge to the native Rust binary. The Python CLI is available directly as `azlin-py`.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    azlin CLI (Rust)                       │
│                   (User Entry Point)                      │
└───────────────────────┬─────────────────────────────────┘
                        │
                        v
┌─────────────────────────────────────────────────────────┐
│               Command Router (clap)                      │
│   53 commands, 154 subcommand variants                   │
│   azlin <command> [subcommand] [options]                 │
└───────────────────────┬─────────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
          v             v             v
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  azlin-core  │ │ azlin-azure  │ │  azlin-ssh   │
│              │ │              │ │              │
│ Config       │ │ VM lifecycle │ │ Connections  │
│ Caching      │ │ Storage/NFS  │ │ Tunneling    │
│ Output/Table │ │ Bastion      │ │ Key mgmt     │
│ Types        │ │ Snapshots    │ │ X11/VNC      │
└──────────────┘ └──────────────┘ └──────────────┘
                        │
                        v
┌─────────────────────────────────────────────────────────┐
│                    Azure CLI (az)                         │
│              Subprocess calls for API access              │
└─────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Azure CLI as Backend
azlin delegates all Azure API calls to `az` CLI subprocesses rather than using the Azure SDK directly. This:

- Leverages Azure CLI's authentication and credential management
- Avoids SDK version conflicts
- Keeps the binary self-contained (no native Azure SDK dependencies)

### Custom Table Renderer
The Rust binary includes a custom table renderer with guaranteed single-line truncation for clean terminal output, even with narrow terminals.

### Non-TTY Safe
All confirmation prompts handle piped input gracefully, making azlin safe to use in scripts and automation.

### Caching
VM lists and metadata are cached locally for fast repeated queries. Per-VM incremental cache refresh ensures newly created VMs appear immediately while avoiding full re-fetches.

## Data Flow: Creating a VM

```
User: azlin new --name myvm
         │
         v
┌────────────────────┐
│  Parse Arguments   │  (clap)
│  name, size,       │
│  region, repo, os  │
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Prerequisites     │──> Verify az CLI, SSH client
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Azure Auth        │──> az account show (verify login)
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  SSH Keys          │──> Generate or reuse ~/.ssh/azlin_key
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  VM Provisioning   │──> az vm create (with cloud-init)
│  (4-5 min)         │    Installs 12 dev tools
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  Wait for Ready    │──> Poll SSH + cloud-init status
└──────┬─────────────┘
       │
       v (if --repo)
┌────────────────────┐
│  GitHub Setup      │──> gh auth + git clone on VM
└──────┬─────────────┘
       │
       v
┌────────────────────┐
│  SSH Connection    │──> Interactive tmux session
└────────────────────┘
```

## Security Architecture

- **Credentials**: Delegated entirely to Azure CLI (`~/.azure/`). azlin never stores tokens or passwords.
- **SSH Keys**: Ed25519 keys at `~/.ssh/azlin_key` with 0600 permissions. Key-based auth only, no passwords.
- **NFS Storage**: RootSquash enabled, Azure AD authentication (no storage keys).
- **VNC**: Localhost-only binding with random per-session passwords, all traffic through SSH tunnel.
- **Bastion**: SSH and GUI traffic tunneled through Azure Bastion for private VMs with no public IPs.

## Performance

The Rust rewrite provides 75-85x faster startup compared to the original Python implementation:

- **Cold start**: ~50ms (vs ~4s in Python)
- **`azlin list` (cached)**: ~100ms
- **Parallel CLI tool detection**: 5s startup (down from 15s)
- **Batch storage quota queries**: Eliminates N+1 Azure CLI calls

## Testing

- **2,536 tests** across unit, integration, and orchestration levels
- Tests run with `cargo test` in the Rust workspace
- Python bridge tests in `tests/` directory
- CI runs on every push via GitHub Actions

## Extension Points

- **Templates**: Pre-defined VM configurations for common setups
- **Cloud-init customization**: User-defined tool installation scripts
- **Contexts**: Multiple Azure subscription/region profiles
- **AI commands**: Natural language VM management via `azlin do`
