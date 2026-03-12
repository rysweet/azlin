# Startup Update Check — Requirements Specification

**Date:** 2026-03-12
**Classification:** Feature
**Complexity:** Low
**Status:** Requirements Clarified

## Task Summary

Move version check to startup (pre-command) in azlin, displaying a non-blocking update notification before command execution using existing update_check infrastructure.

## Background

Currently, `update_check::check_for_updates()` is called **after** the command completes (line 708 of `main.rs`). This means users only see the update notification after their command has already run. The feature request is to move this check to **startup** so the notification appears before or concurrent with command execution.

### Existing Infrastructure (No New Code Required for Check Logic)

| File | Purpose |
|------|---------|
| `crates/azlin/src/update_check.rs` (230 lines) | Background version check — reuse as-is |
| `crates/azlin/src/cmd_self_update.rs` (213 lines) | Self-update command handler |
| `crates/azlin/src/main.rs` line 708 | Current call site (post-command) — move to pre-command |

The `update_check::check_for_updates()` function already handles:
- GitHub API query via `gh` CLI (with curl fallback)
- 24-hour cooldown cache at `~/.config/azlin/last_update_check`
- `AZLIN_NO_UPDATE_CHECK=1` suppression
- Yellow ANSI stderr notification: `"A newer version of azlin is available (v{}). Run 'azlin update' to upgrade."`
- Silent failure on network errors

## Explicit Requirements (Must-Have)

1. Check for new versions **at startup** (before or concurrent with command dispatch), not post-command as currently implemented
2. Use existing `update_check::check_for_updates()` infrastructure — GitHub API via `gh` CLI with curl fallback, 24-hour cooldown cache, `AZLIN_NO_UPDATE_CHECK` suppression
3. Notification must be **non-blocking** — must not delay or prevent the user's actual command from executing
4. Display notification to stderr with yellow ANSI color (consistent with existing `\x1b[33m...\x1b[0m` pattern)
5. Notification message must reference `azlin update` command (preserve existing message format)
6. Preserve existing 24-hour cooldown mechanism (`~/.config/azlin/last_update_check` cache file)
7. Preserve `AZLIN_NO_UPDATE_CHECK=1` environment variable suppression
8. Notification must appear before command output, not after

## Acceptance Criteria

- [ ] When a newer version exists and 24 hours have elapsed since last check, a yellow warning appears on stderr **before** the command's output
- [ ] The user's requested command executes and completes normally regardless of update check result
- [ ] Update check completes within existing timeout budget (5s for `gh`, 3s connect + 5s max for curl) without blocking the command
- [ ] When `AZLIN_NO_UPDATE_CHECK=1` is set, no check is performed and no notification appears
- [ ] When checked within the last 24 hours, no network request is made (cooldown respected)
- [ ] When network is unavailable, the command runs normally with no error output (silent failure preserved)
- [ ] Running `azlin update` does NOT trigger a startup version check (avoid redundant check)
- [ ] Running `azlin version` does NOT trigger a startup version check (avoid redundant check)

## Out of Scope

- Changing the update download/install logic in `cmd_self_update.rs`
- Modifying the GitHub API query logic or version comparison algorithm
- Adding interactive prompts asking the user to update (notification only, no blocking prompt)
- Adding new configuration options beyond existing `AZLIN_NO_UPDATE_CHECK`
- Changing the cooldown duration (remains 24 hours)
- Modifying the cache file format or location
- Auto-updating without user consent

## Implementation Approach

### Minimal Change (Recommended)

The implementation requires changes to **one file only**: `crates/azlin/src/main.rs`

**Current flow (post-command):**
```rust
dispatch::dispatch_command(cli).await?;
update_check::check_for_updates().await;  // line 708 — runs AFTER command
```

**New flow (pre-command, concurrent):**
```rust
// Skip check for update/version commands to avoid redundancy
let skip_check = matches!(cli.command, Commands::Update | Commands::Version);

let update_handle = if !skip_check {
    Some(tokio::spawn(async { update_check::check_for_updates().await }))
} else {
    None
};

// Await the update check before dispatching so notification appears first
if let Some(handle) = update_handle {
    let _ = handle.await;  // errors are silently ignored
}

dispatch::dispatch_command(cli).await?;
// Remove old post-command call
```

### Trade-offs

| Approach | Notification Position | Command Delay |
|----------|----------------------|---------------|
| Await before dispatch (recommended) | Before command output | Up to timeout (5s worst case, but cooldown means usually 0ms) |
| Spawn + don't await | May interleave | Zero |
| Spawn + await before dispatch | Before command output | Only when check actually runs (24h cooldown means rare) |

The recommended approach awaits the spawned task before dispatch, ensuring the notification appears before command output. Since the 24-hour cooldown means the check only runs once per day, the delay is negligible for normal usage.

## Assumptions

1. Non-blocking means: spawn as a concurrent async task using `tokio::spawn` so command dispatch begins immediately in parallel
2. The simplest correct approach: spawn `check_for_updates()` at startup, await before `dispatch_command` so notification appears first
3. `azlin update` and `azlin version` commands skip the startup check to avoid redundancy
4. The existing `check_for_updates()` function is reused with no modifications — only the call site in `main.rs` changes

## Questions Resolved Autonomously

| Question | Resolution |
|----------|-----------|
| Should the check block startup? | No — spawn concurrently with `tokio::spawn` |
| Should notification appear before or after command output? | Before — await spawned check task before calling `dispatch_command` |
| Should all commands trigger the check? | No — skip for `azlin update` and `azlin version` |
| Is this a new check or moving the existing one? | Moving — remove post-command call, add pre-command concurrent call |

## Related Documents

- `docs/DESIGN_UPDATE_COMMAND.md` — existing update command design
- `crates/azlin/src/update_check.rs` — current implementation to reuse
- `crates/azlin/src/main.rs` — entry point where call site changes
