# SSH Key Not Found Errors

## Problem

Previously, running `azlin connect` or `azlin new` without any SSH key in
`~/.ssh/` produced a confusing Azure CLI error about missing key files.

## Solution

As of the current version, azlin **automatically generates** an
`id_ed25519_azlin` keypair when no SSH key is found. No manual action is
required.

If you still encounter SSH key errors, see
[SSH Auto-Keygen](../features/ssh-auto-keygen.md) for details on the key
search priority, override options, and further troubleshooting.

## Related

- [SSH Auto-Keygen Feature](../features/ssh-auto-keygen.md)
- [Troubleshoot Connection Issues](../how-to/troubleshoot-connection-issues.md)
