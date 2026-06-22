# Credential Forwarding

Forward local developer credentials to newly created azlin VMs so tools like `gh`, `az`, GitHub Copilot, and Claude Code work immediately — no manual login required.

## How It Works

After `azlin new` creates a VM and SSH becomes reachable, azlin detects which credential sources exist on your local machine and offers to copy them to the VM via SCP.

```
azlin new --name myproject
  ✓ VM created
  ✓ SSH ready
  Found credentials:
    • GitHub CLI (~/.config/gh)
    • Azure CLI (~/.azure)
    • GitHub Copilot (~/.config/github-copilot)
  Forward GitHub CLI credentials? [y/N] y
    ✓ GitHub CLI credentials forwarded
  Forward Azure CLI credentials? [y/N] y
    ✓ Azure CLI credentials forwarded
  Forward GitHub Copilot credentials? [y/N] n
    ⊘ Skipped
```

## Supported Credentials

| Tool | Local Source | Detection | What Gets Copied |
|------|-------------|-----------|-----------------|
| GitHub CLI | `~/.config/gh/` | `hosts.yml` exists | Entire `~/.config/gh/` directory |
| GitHub Copilot | `~/.config/github-copilot/` | Directory exists | Entire directory |
| Claude Code | `~/.claude.json` | File exists | Single config file |
| Azure CLI | `~/.azure/` | Token files exist | Allow-listed files only (see [Security](#security)) |

## Key Design Principles

**Consent-gated**: Each credential type prompts for confirmation. Nothing is forwarded silently.

**Best-effort**: Forwarding failures print a warning but never block VM creation. Your VM is always usable even if credential forwarding fails.

**SCP-only**: Credentials are copied as files. No tokens are piped through SSH commands or exposed in process arguments.

**Detection-first**: Only credentials that actually exist locally are offered for forwarding. No prompts for tools you don't use.

## Security

Credential forwarding follows a strict security model:

- **Azure CLI allow-list**: Only these files are copied from `~/.azure/`:
  - `azureProfile.json` — subscription metadata
  - `config` — CLI configuration
  - `msal_token_cache.json` — login tokens
  - `msal_token_cache.bin` — binary token cache
  - `clouds.config` — cloud endpoint definitions
  - Service principal credentials (`servicePrincipalProfile`, `accessTokens.json`) are **never** copied.

- **No shell injection**: All SSH/SCP commands use `Command::new()` with argument arrays — never shell interpolation.

- **TOFU SSH**: Uses `StrictHostKeyChecking=accept-new` — accepts the host key on first connect, rejects if it changes later.

- **No password prompts**: `BatchMode=yes` ensures SCP fails cleanly rather than hanging on a password prompt.

- **Non-TTY safety**: When running without a terminal (CI/scripts), all confirmations default to "no". Use `--yes` for scripted forwarding.

## Usage

See [How to Forward Credentials to a VM](../how-to/forward-credentials.md) for step-by-step instructions.

See [Credential Forwarding Reference](../reference/credential-forwarding.md) for CLI flags, environment details, and troubleshooting.
