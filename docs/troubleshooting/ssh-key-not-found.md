# Troubleshooting: SSH Key Not Found

Diagnosis and resolution guide for SSH key issues during `azlin connect` and `azlin new`.

## Quick Diagnosis

```bash
# Check which keys azlin would find:
ls -la ~/.ssh/{azlin_key,id_ed25519_azlin,id_ed25519,id_rsa}* 2>/dev/null

# Run with verbose logging:
azlin connect myvm -v
```

## Common Issues

### ssh-keygen Not Installed

**Symptom:** `Failed to run ssh-keygen: No such file or directory`

**Cause:** The `ssh-keygen` binary is not on your PATH. This can happen in minimal containers or stripped-down OS images.

**Fix:**

```bash
# Ubuntu/Debian
sudo apt-get install openssh-client

# RHEL/Fedora
sudo dnf install openssh-clients

# Alpine
apk add openssh-keygen

# macOS (usually pre-installed)
brew install openssh
```

### Permission Denied Writing to ~/.ssh

**Symptom:** `Cannot create ~/.ssh: Permission denied`

**Cause:** The `~/.ssh` directory or its parent has incorrect ownership or permissions.

**Fix:**

```bash
# Ensure correct ownership
sudo chown -R "$USER:$USER" ~/.ssh

# Ensure correct permissions
chmod 700 ~/.ssh
```

### Private Key Exists but Public Key Missing

**Symptom:** azlin finds a private key (e.g., `id_ed25519`) but the `.pub` file is missing. azlin attempts to regenerate it automatically, but this can fail if the private key is passphrase-protected.

**Fix:** Regenerate the public key manually:

```bash
ssh-keygen -y -f ~/.ssh/id_ed25519 > ~/.ssh/id_ed25519.pub
```

If the key has a passphrase, you'll be prompted to enter it.

### Key Generated but VM Connection Still Fails

**Symptom:** azlin reports "SSH key pair generated successfully" but the connection still fails with `Permission denied (publickey)`.

**Possible causes:**

1. **Public key not yet pushed to VM** — If the VM was created before the key was generated, the VM doesn't know about the new key. Re-run the connect command; azlin pushes the key automatically when `generated: true`.

2. **Key Vault mismatch** — The VM may expect a key stored in Azure Key Vault that differs from the local key. See [Auto-Sync Keys](../features/auto-sync-keys.md).

3. **VM authorized_keys permissions** — The remote `~/.ssh/authorized_keys` file may have incorrect permissions:

```bash
# On the VM (if you can access it via Azure serial console):
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
```

### Wrong Key Selected

**Symptom:** azlin uses `id_rsa` when you want it to use `id_ed25519_azlin`.

**Cause:** Key discovery follows a priority order. If a higher-priority key exists, it takes precedence.

**Priority order:**
1. `azlin_key`
2. `id_ed25519_azlin`
3. `id_ed25519`
4. `id_rsa`

**Fix:** Either remove the unwanted key, or pass `--key` to override:

```bash
azlin connect myvm --key ~/.ssh/id_ed25519_azlin
```

### Key Generation Fails

**Symptom:** `Failed to generate SSH keypair` or `ssh-keygen exited with non-zero status`.

**Possible causes:**

1. **Disk full** — No space to write the key files. Free disk space and retry.
2. **Read-only filesystem** — `~/.ssh` is on a read-only mount (common in some container setups). Mount a writable volume at `~/.ssh` or use `--key` to point to a writable location.
3. **`~/.ssh` is a file, not a directory** — Remove or rename the file and retry.

**Fix:**

```bash
# Check available disk space
df -h ~

# Verify ~/.ssh is a directory
file ~/.ssh

# If it's a file, move it and let azlin recreate:
mv ~/.ssh ~/.ssh.bak
```

### Race Condition with Parallel azlin Instances

**Symptom:** Two parallel `azlin new` commands both try to generate keys simultaneously.

**Mitigation:** `ssh-keygen` writes atomically. The second instance will find the key already exists on its discovery pass. No data corruption occurs, though you may see a duplicate "Generating..." message in logs.

## Diagnostic Commands

```bash
# Verify key file permissions (private key must be 0600)
stat -c '%a %n' ~/.ssh/id_ed25519_azlin 2>/dev/null

# Test that the keypair matches
diff <(ssh-keygen -y -f ~/.ssh/id_ed25519_azlin) ~/.ssh/id_ed25519_azlin.pub

# Check which key azlin will use (verbose mode)
azlin connect myvm -v 2>&1 | grep -i "key\|ssh"
```

## Related Documentation

- [SSH Auto-Keygen Feature](../features/ssh-auto-keygen.md) — How automatic key generation works
- [Auto-Sync Keys](../features/auto-sync-keys.md) — Automatic key synchronization with Azure Key Vault
- [Tunnel Issues](tunnel-issues.md) — Troubleshooting SSH tunnel problems
