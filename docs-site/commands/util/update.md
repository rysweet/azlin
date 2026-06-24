# azlin update

Update the azlin binary itself to the latest release from GitHub Releases.

**Alias:** `azlin self-update`

## Description

The `azlin update` command upgrades your locally installed `azlin` binary to the
latest published release. It detects your platform, downloads the matching
pre-built binary from [GitHub Releases](https://github.com/rysweet/azlin/releases/latest),
and replaces the running executable in place.

If you are already on the latest version, it exits without making changes.

> **Looking to update the development tools _on a VM_?** Use
> [`azlin vm update-tools <vm>`](../vm/update.md) instead. To update the VM's
> operating-system packages, use [`azlin os-update <vm>`](os-update.md).

## Usage

```bash
azlin update
# or, equivalently:
azlin self-update
```

This command takes no positional arguments.

## Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Enable verbose output |
| `-o, --output <FORMAT>` | Output format (`table`, `json`, `csv`; default: `table`) |
| `--auth-profile <NAME>` | Service principal authentication profile to use |
| `-h, --help` | Show help message |

## Examples

### Update to the latest release

```bash
azlin update
```

**Output:**

```
azlin self-update (current: v2.6.74)
New version available: v2.6.74 → v2.7.0
Downloading...
✓ Updated to v2.7.0
```

### Already up to date

```bash
azlin update
```

**Output:**

```
azlin self-update (current: v2.7.0)
Already at the latest version (v2.7.0).
```

## What Happens

1. Reads the current binary version.
2. Queries the latest GitHub release for your platform
   (Linux/macOS, x86_64/aarch64).
3. If a newer version exists, downloads the release archive and replaces the
   current `azlin` binary.
4. If you are already current, exits without changes.

## Troubleshooting

### Unsupported platform

**Problem:** `Unsupported platform for self-update`.

**Solution:** Pre-built binaries are published for Linux and macOS on x86_64 and
aarch64. On other platforms, install from source or via `uvx` (see
[Installation](../../getting-started/installation.md)).

### Permission denied replacing the binary

**Problem:** The update cannot overwrite the installed binary.

**Solution:** Re-run with sufficient permissions for the install location, or
re-install azlin to a user-writable directory.

## Related Commands

- [`azlin vm update-tools`](../vm/update.md) - Update development tools on a VM
- [`azlin os-update`](os-update.md) - Update a VM's OS packages
- [Startup version check](version-check.md) - Automatic update notices at startup

## Source Code

- [cmd_self_update.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/cmd_self_update.rs) - Self-update implementation

## See Also

- [Installation](../../getting-started/installation.md)
- [Utility Commands](index.md)
