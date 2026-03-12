# azlin update

Update the azlin CLI itself to the latest release.

!!! tip "Startup version notification"
    azlin checks for a newer version of itself at startup and prints a one-line notice when an update is available. See [Startup Version Check](./util/version-check.md) for configuration options including how to disable the check.

## Description

`azlin update` downloads and installs the latest azlin binary from GitHub releases.
This command updates **azlin itself** — not your VMs or the development tools on them.

To update development tools on a VM, see [`azlin os-update`](./util/os-update.md).

## Usage

```bash
azlin update
```

No arguments required.

## Examples

### Update azlin

```bash
azlin update
```

**Output:**
```
Checking for updates...
Current version: v2.6.1-rust.def5678
Latest version:  v2.7.0-rust.abc1234

Downloading v2.7.0-rust.abc1234...
✓ Download complete
✓ azlin updated to v2.7.0-rust.abc1234
```

### Check current version before updating

```bash
azlin version
# azlin v2.6.1-rust.def5678

azlin update

azlin version
# azlin v2.7.0-rust.abc1234
```

### Suppress the startup notice after updating

The startup notice disappears automatically after you update — the cached version is written fresh. If you want to confirm you are current:

```bash
azlin update && azlin version
```

## What Gets Updated

`azlin update` replaces the azlin binary in-place. It does not modify:

- Your VMs or their contents
- Development tools on VMs (use `azlin os-update <vm>` for those)
- Ubuntu system packages on VMs (also `azlin os-update <vm>`)
- Your azlin configuration (`~/.config/azlin/`)

## After Updating

The startup version check cache is refreshed on the next run. The update notice will not appear until a newer version is available.

## Related Commands

- [`azlin os-update`](./util/os-update.md) - Update Ubuntu system packages and development tools on a VM
- [`azlin version`](./util/help.md) - Show current azlin version

## See Also

- [Startup Version Check](./util/version-check.md) - How azlin detects and notifies you about updates
