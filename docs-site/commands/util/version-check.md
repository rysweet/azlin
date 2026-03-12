# Startup Version Check

azlin checks for a newer release at startup and prints a one-line notice to stderr when an update is available.

## Contents

- [How It Works](#how-it-works)
- [What You See](#what-you-see)
- [Cache File](#cache-file)
- [Configuration](#configuration)
- [Disabling the Check](#disabling-the-check)
- [Manual Update](#manual-update)
- [Troubleshooting](#troubleshooting)

## How It Works

Every time you run an `azlin` command, the CLI checks whether a newer release exists before executing your command. The check is designed to be invisible when everything is current and non-blocking in all cases.

```
azlin <command>
  │
  ├─ 1. Is AZLIN_NO_UPDATE_CHECK=1? → skip
  ├─ 2. Was cache written less than 24h ago? → use cached result
  ├─ 3. Query GitHub releases API (5s timeout, fail-silent)
  ├─ 4. Write result to cache
  └─ 5. If newer version found → print notice to stderr
         └─ Run your command normally
```

**Key properties:**

| Property | Behavior |
|----------|----------|
| Position | Before your command runs |
| Output stream | stderr only (stdout is clean) |
| Network timeout | 5 seconds |
| Cooldown | 24 hours between live checks |
| On network failure | Silent — your command still runs |
| Cache hit | Sub-millisecond — no network call |

## What You See

When a newer version is available, you see one line on stderr before your command output:

```
A newer version of azlin is available (v2.7.0-rust.abc1234). Run 'azlin update' to upgrade.
```

The notice appears in yellow on terminals that support ANSI colors. It goes to stderr, so piping stdout works as expected:

```bash
# This captures only your command's output, not the update notice
azlin list --json | jq '.[] | .name'
```

When your version is current, or after a recent check (within 24 hours), startup is silent.

## Cache File

The check result is cached at:

```
~/.config/azlin/last_update_check
```

The cache file contains two lines:

```
2.7.0-rust.abc1234
1736700000
```

- Line 1: Latest version tag from GitHub
- Line 2: Unix timestamp of last live network check

azlin reads this file on startup. If the timestamp is less than 24 hours old, it uses the cached version rather than making a network request. If the cache is missing or corrupt, it falls back to a live check.

To force an immediate live check, delete the cache file:

```bash
rm ~/.config/azlin/last_update_check
```

## Configuration

### Environment Variable

| Variable | Value | Effect |
|----------|-------|--------|
| `AZLIN_NO_UPDATE_CHECK` | `1` | Skip the check entirely |

The variable must be set to the value `1`. Other truthy values (`true`, `yes`, `on`) are not recognized — only `AZLIN_NO_UPDATE_CHECK=1` disables the check.

### Network

The check uses two methods in order:

1. **`gh` CLI** (authenticated) — used when `gh` is installed and authenticated
2. **`curl`** (anonymous) — fallback using the GitHub releases API over HTTPS

Both use a maximum 5-second timeout. If both fail (no network, rate limiting, etc.), startup is silent and your command runs normally.

## Disabling the Check

### Per-command

```bash
AZLIN_NO_UPDATE_CHECK=1 azlin list
```

### Session-wide

```bash
export AZLIN_NO_UPDATE_CHECK=1
azlin list
azlin connect myvm
```

### Permanently

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
export AZLIN_NO_UPDATE_CHECK=1
```

### CI/CD pipelines

Set the variable in your pipeline environment to prevent update notices in automated output:

```yaml
# GitHub Actions example
env:
  AZLIN_NO_UPDATE_CHECK: "1"
```

## Manual Update

When you see the update notice, run:

```bash
azlin update
```

This updates azlin itself (the CLI binary). See [azlin update](./update.md) for the full reference.

## Troubleshooting

**Notice appears every time, not just once per 24 hours**

The cache file may be unwritable. Check that `~/.config/azlin/` is writable:

```bash
ls -la ~/.config/azlin/
# Should be writable by your user
```

Create it if missing:

```bash
mkdir -p ~/.config/azlin
```

**Notice never appears even though a newer version exists**

Delete the cache to force a fresh check:

```bash
rm -f ~/.config/azlin/last_update_check
azlin version
```

If the notice still doesn't appear, verify network access to GitHub:

```bash
curl -s "https://api.github.com/repos/rysweet/azlin/releases?per_page=5" | jq '.[0].tag_name'
```

**Suppressing the notice without disabling updates**

The notice goes to stderr. Redirect stderr to suppress it while keeping stdout clean:

```bash
azlin list 2>/dev/null
```

To update silently in a script:

```bash
AZLIN_NO_UPDATE_CHECK=1 azlin list 2>/dev/null
```
