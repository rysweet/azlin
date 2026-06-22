# VM OS Image Selection

Choose the operating system image for new VMs via the `--os` flag or persistent configuration.

## Overview

By default, `azlin new` provisions VMs with Ubuntu 25.10. You can override this per-command with `--os` or set a persistent default with `azlin config set default_vm_image`.

## Quick Start

```bash
# Use Ubuntu 24.04 LTS for this VM
azlin new --name my-vm --os 24.04-lts

# Set a persistent default
azlin config set default_vm_image "24.04-lts"

# Now all new VMs use Ubuntu 24.04 LTS
azlin new --name my-vm
```

## The `--os` Flag

```bash
azlin new --os <IMAGE_SPEC> [OTHER_OPTIONS]
```

`IMAGE_SPEC` accepts two formats:

### Shorthands

Convenient aliases for common Ubuntu versions:

| Shorthand | Resolved Image URN |
|-----------|-------------------|
| `25.10` | `Canonical:ubuntu-25_10:server:latest` |
| `24.10` | `Canonical:ubuntu-24_10:server:latest` |
| `24.04-lts` | `Canonical:ubuntu-24_04-lts:server:latest` |
| `24.04` | `Canonical:ubuntu-24_04-lts:server:latest` |
| `22.04-lts` | `Canonical:ubuntu-22_04-lts:server:latest` |
| `22.04` | `Canonical:ubuntu-22_04-lts:server:latest` |
| `20.04-lts` | `Canonical:ubuntu-20_04-lts:server:latest` |
| `20.04` | `Canonical:ubuntu-20_04-lts:server:latest` |

Bare version numbers (e.g., `24.04`) resolve to the LTS variant when one exists.

### Full Image URN

Azure image URNs in the format `Publisher:Offer:SKU:Version`:

```bash
azlin new --os "Canonical:ubuntu-24_04-lts:server:latest"
```

Only images from the `Canonical` publisher are accepted. Non-Canonical URNs are rejected because azlin's cloud-init provisioning assumes an Ubuntu base image with `apt`.

## Configuration

### Setting a Default Image

```bash
# Set default using a shorthand
azlin config set default_vm_image "24.04-lts"

# Set default using a full URN
azlin config set default_vm_image "Canonical:ubuntu-24_04-lts:server:latest"

# View current default
azlin config get default_vm_image

# Remove default (revert to built-in Ubuntu 25.10)
azlin config unset default_vm_image
```

The value is validated on `set` — invalid shorthands or malformed URNs are rejected. The resolved full URN is stored in `~/.azlin/config.toml`.

### Config File

```toml
# ~/.azlin/config.toml

# Default OS image for new VMs (full URN or shorthand)
default_vm_image = "Canonical:ubuntu-24_04-lts:server:latest"

# Other defaults
default_region = "westus2"
default_vm_size = "Standard_E16as_v5"
default_resource_group = "azlin-vms"
```

## Priority Chain

When creating a VM, the OS image is resolved in this order (highest priority first):

1. **`--os` flag** — per-command override
2. **`default_vm_image` config** — persistent default in `~/.azlin/config.toml`
3. **Built-in default** — Ubuntu 25.10 (`Canonical:ubuntu-25_10:server:latest`)

```bash
# Uses --os flag (highest priority)
azlin new --os 22.04-lts

# Uses config default_vm_image (if set)
azlin new

# Uses built-in Ubuntu 25.10 (if no config set and no --os)
azlin new
```

## Examples

### Create a VM with Ubuntu 24.04 LTS

```bash
azlin new --name dev-vm --os 24.04-lts
```

### Create a pool with a specific image

```bash
azlin new --pool 3 --name build-fleet --os 22.04-lts
```

### Set team-wide default via config

```bash
# All team members run this once
azlin config set default_vm_image "24.04-lts"

# Then just use azlin new normally
azlin new --name my-vm
```

### Override config default for one VM

```bash
# Config says 24.04-lts, but you need 25.10 for testing
azlin new --name test-vm --os 25.10
```

### Use full URN for a specific image version

```bash
azlin new --name pinned-vm --os "Canonical:ubuntu-24_04-lts:server:24.04.202401010"
```

## Input Validation

Image specifications are validated for safety:

- **Shorthands** must match a known Ubuntu version
- **Full URNs** must have exactly 4 colon-separated segments
- **Publisher** must be `Canonical` (non-Ubuntu images are rejected)
- **Segments** may only contain `[a-zA-Z0-9._-]` characters
- **Shell metacharacters**, newlines, and null bytes are rejected

Invalid input produces a clear error:

```
$ azlin new --os "NotAPublisher:image:sku:latest"
Error: Only Canonical publisher is supported for VM images, got "NotAPublisher".
  Use a URN like 'Canonical:ubuntu-25_10:server:latest'

$ azlin new --os "not-a-version"
Error: Unknown image shorthand "not-a-version". Supported shorthands:
  25.10, 24.10, 24.04-lts, 24.04, 22.04-lts, 22.04, 20.04-lts, 20.04.
  Or use a full URN like 'Canonical:ubuntu-25_10:server:latest'
```

## Troubleshooting

### "Unknown OS image shorthand"

You used a shorthand that isn't recognized. Check the [shorthands table](#shorthands) or use a full URN.

### "Only Canonical (Ubuntu) images are supported"

azlin requires Ubuntu because its cloud-init setup uses `apt`. Use a Canonical image URN or a recognized shorthand.

### Config default not taking effect

Check that `default_vm_image` is set correctly:

```bash
azlin config show
```

Verify the `--os` flag isn't overriding it (it has higher priority).

## See Also

- [Quick Reference](../QUICK_REFERENCE.md) — All CLI flags at a glance
- [Configuration Reference](../reference/config-default-behaviors.md) — All config options
- [Region Fit](region-fit.md) — Auto-find regions with available quota
