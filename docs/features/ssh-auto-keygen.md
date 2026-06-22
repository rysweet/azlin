# SSH Auto-Keygen

Azlin automatically generates an SSH keypair when none exists, eliminating
manual `ssh-keygen` steps and cryptic Azure CLI errors for first-time users.

## Overview

When you run `azlin connect` or `azlin new`, azlin searches `~/.ssh/` for an
existing keypair. If none is found, it generates an `id_ed25519_azlin` key and
(when connecting) pushes the public key to the target VM — all transparently.

### Key Search Priority

Azlin checks these key stems in order, selecting the first match where both
private and public files exist:

| Priority | Private Key          | Public Key               |
|----------|----------------------|--------------------------|
| 1        | `~/.ssh/azlin_key`   | `~/.ssh/azlin_key.pub`   |
| 2        | `~/.ssh/id_ed25519_azlin` | `~/.ssh/id_ed25519_azlin.pub` |
| 3        | `~/.ssh/id_ed25519`  | `~/.ssh/id_ed25519.pub`  |
| 4        | `~/.ssh/id_rsa`      | `~/.ssh/id_rsa.pub`      |

If a private key exists but its `.pub` is missing, azlin regenerates the public
key with `ssh-keygen -y -f <private_key>`.

## Behavior by Command

### `azlin connect`

```
azlin connect myvm
```

1. If `--key` is provided, that key is used directly (no auto-gen).
2. Otherwise, search `~/.ssh/` using the priority table above.
3. If no keypair is found, generate `~/.ssh/id_ed25519_azlin`.
4. If the keypair was just generated, push the public key to the VM via
   `az vm user update --username azureuser`.
5. Connect via bastion tunnel using the selected private key.

### `azlin new`

```
azlin new --name devbox
```

1. Search `~/.ssh/` using the priority table above.
2. If no keypair is found, generate `~/.ssh/id_ed25519_azlin`.
3. Pass the public key content to the ARM template at VM creation time.
4. No separate push step is needed — the key is baked into the VM image.

## Generated Key Properties

| Property    | Value                                |
|-------------|--------------------------------------|
| Algorithm   | Ed25519                              |
| Passphrase  | Empty (no passphrase)                |
| Private key | `~/.ssh/id_ed25519_azlin`            |
| Public key  | `~/.ssh/id_ed25519_azlin.pub`        |
| Comment     | `azlin-rotated`                      |
| Permissions | `0600` (private key, Unix only)      |

## Overriding the Default Key

Use `--key` with `azlin connect` to bypass auto-detection:

```bash
azlin connect myvm --key ~/.ssh/my_custom_key
```

When `--key` is specified, azlin uses that key directly without searching
`~/.ssh/` or generating anything.

## Security Considerations

- **Private key permissions**: Set to `0600` on Unix to prevent group/other
  access. On Windows, filesystem ACLs are not modified.
- **Empty passphrase**: The generated key has no passphrase. This is acceptable
  for ephemeral dev VMs but means the key is unprotected at rest if `~/.ssh/`
  is compromised.
- **AAD-authenticated push**: Public keys are pushed to VMs via
  `az vm user update`, which requires an authenticated Azure CLI session.
- **Hard failure on push**: If the public key push fails during `azlin connect`,
  the command aborts immediately rather than attempting a connection with an
  unknown key state.
- **No key material logged**: Only key file paths appear in diagnostic output;
  key content is never printed.
- **Pre-commit audit**: `scripts/audit_key_operations.py` runs in pre-commit
  hooks to verify no key material is committed to source control.

## Troubleshooting

### "Cannot determine home directory"

Azlin could not resolve `$HOME`. Ensure the `HOME` environment variable is set.

### "Cannot create ~/.ssh"

The `~/.ssh` directory doesn't exist and couldn't be created. Check filesystem
permissions on your home directory.

### "Failed to run ssh-keygen" or "ssh-keygen failed to generate a new key pair"

`ssh-keygen` must be available on `$PATH`. Install OpenSSH:

```bash
# Ubuntu/Debian
sudo apt install openssh-client

# macOS (pre-installed)

# Windows
winget install Microsoft.OpenSSH.Client
```

### "ssh-keygen ran but public key file was not created"

`ssh-keygen` exited successfully but the `.pub` file is missing. Check that
`~/.ssh/` is writable and that disk space is available.

### "Failed to push SSH key to \<vm\>"

The `az vm user update` command failed. Common causes:

- Azure CLI not logged in — run `az login`
- Insufficient permissions on the VM's resource group
- VM is in a deallocated state — start it first with `azlin start <name>`

The error message includes the manual fallback command you can retry.

### Key already exists but connection fails

If you have an existing key that doesn't work with a particular VM, the VM may
have been created with a different public key. Re-push your current key:

```bash
az vm user update \
  --resource-group <rg> \
  --name <vm> \
  --username azureuser \
  --ssh-key-value "$(cat ~/.ssh/id_ed25519_azlin.pub)"
```

## Diagnostic Output

When a key is generated, azlin prints to stderr:

```
No SSH key found. Generating /home/you/.ssh/id_ed25519_azlin...
SSH key pair generated successfully.
```

These messages appear only on generation — existing keys are used silently.

## How It Works (Internals)

The feature is implemented in `key_helpers::ensure_ssh_keypair()`, which returns
an `SshKeypair` struct:

```rust
pub struct SshKeypair {
    pub private_key: PathBuf,  // Path to private key
    pub public_key: PathBuf,   // Path to public key
    pub generated: bool,       // true if just created
}
```

The `generated` flag lets callers decide whether to push the key. In the
`connect` flow (bastion path), a freshly generated key triggers an automatic
push. In the `new` flow, the public key content is embedded in the ARM template
at creation time, so no push is needed.
