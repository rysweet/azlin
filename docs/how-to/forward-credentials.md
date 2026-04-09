# How to Forward Credentials to a VM

Copy your local developer credentials to a new azlin VM so tools work immediately after creation.

## Prerequisites

- azlin installed and authenticated with Azure (`az login`)
- At least one supported credential source on your local machine:
  - GitHub CLI (`gh auth login` completed)
  - Azure CLI (`az login` completed)
  - GitHub Copilot CLI configured
  - Claude Code configured

## Forward Credentials Interactively

Credential forwarding runs automatically after VM creation. Confirm each credential individually:

```bash
azlin new --name devbox
```

Output:

```
Creating VM devbox in eastus2...
  ✓ VM created (Standard_D4ds_v5)
  ✓ Waiting for SSH... ready (18s)

  Found credentials:
    • GitHub CLI (~/.config/gh)
    • Azure CLI (~/.azure)

  Forward GitHub CLI credentials? [y/N] y
    ✓ Copied ~/.config/gh → devbox:~/.config/gh

  Forward Azure CLI credentials? [y/N] y
    ✓ Copied 3 files → devbox:~/.azure/
```

## Forward All Credentials Without Prompts

Use `--yes` to skip confirmation prompts and forward everything detected:

```bash
azlin new --name devbox --yes
```

All detected credentials are forwarded automatically. This is useful for scripted VM creation.

## Forward Credentials Through a Bastion

VMs are private (bastion-routed) by default. Credential forwarding automatically routes SCP through the bastion tunnel:

```bash
azlin new --name private-vm
```

No extra flags needed. azlin detects the bastion tunnel and routes SCP through `127.0.0.1` on the tunneled port. Use `--public` or `--no-bastion` to create a VM with a public IP instead.

## Verify Credentials on the VM

After connecting to the VM, verify each tool works:

```bash
# SSH into the VM
azlin connect devbox

# Check GitHub CLI
gh auth status

# Check Azure CLI
az account show

# Check GitHub Copilot
gh copilot --help
```

## Skip Credential Forwarding

Decline all prompts (press Enter at each — default is No), or interrupt with Ctrl+C during the forwarding phase. The VM remains fully functional; you just need to authenticate each tool manually.

## Refresh Expired Credentials

Credential forwarding copies token files as they exist at creation time. If tokens expire:

1. Re-authenticate locally (`gh auth login`, `az login`, etc.)
2. Create a new VM, or manually SCP the updated files:

```bash
# Example: refresh GitHub CLI credentials on an existing VM
scp -r ~/.config/gh/ devbox:~/.config/gh/
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "SSH not ready" timeout | VM still booting or NSG blocking port 22 | Wait and retry; check Azure NSG rules allow SSH |
| "Permission denied" during SCP | SSH key not configured | Verify `azlin connect` works first |
| `gh auth status` fails on VM | Tokens expired before forwarding | Re-run `gh auth login` locally, then SCP `~/.config/gh/` |
| `az account show` fails on VM | Stale MSAL tokens | Run `az login` on the VM directly |
| No credentials detected | Tools not authenticated locally | Run `gh auth login` / `az login` locally first |

See [Credential Forwarding Reference](../reference/credential-forwarding.md) for technical details.
