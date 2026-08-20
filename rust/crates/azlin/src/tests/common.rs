//! Shared test helpers used across multiple test groups.

use anyhow::Result;
use tempfile::TempDir;

/// Build a Cli struct from command-line args (for in-process dispatch tests).
pub(super) fn make_cli(args: &[&str]) -> azlin_cli::Cli {
    use clap::Parser;
    let mut full_args = vec!["azlin"];
    full_args.extend_from_slice(args);
    azlin_cli::Cli::parse_from(full_args)
}

/// Run dispatch_command in-process for coverage.
pub(super) async fn run_dispatch(args: &[&str]) -> Result<()> {
    let cli = make_cli(args);
    crate::dispatch::dispatch_command(cli).await
}

/// Run azlin as a subprocess with its config state isolated to `dir`.
///
/// Config-mutating commands (`config set`, `session <vm> <name>`) persist to
/// the directory named by `AZLIN_CONFIG_DIR`, defaulting to `~/.azlin`. Driving
/// them through [`run_dispatch`] runs them *in-process*, so they read and write
/// the developer's real `~/.azlin/config.toml`. That is destructive on its own —
/// the save/restore dance those tests perform is best-effort and leaves the file
/// modified if an assertion fails in between — and under `cargo test`'s default
/// thread parallelism two such tests interleave their read-modify-write cycles
/// and can corrupt the file outright (issue #1079: a duplicate `[vm_storage]`
/// table appended at EOF, plus `Failed to rename config` from the racing side).
///
/// A subprocess gets its own copy of the environment, so pointing it at a temp
/// dir needs no process-global mutation and therefore cannot race with tests
/// running concurrently in other threads. This mirrors the isolation already
/// used by `tests/config_integration.rs`.
pub(super) fn run_isolated(dir: &TempDir, args: &[&str]) -> std::process::Output {
    assert_binary_is_not_stale();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("AZLIN_CONFIG_DIR", dir.path())
        .timeout(std::time::Duration::from_secs(30))
        .output()
        .unwrap()
}

/// Fail loudly when `target/debug/azlin` predates the sources under test.
///
/// These tests run the *binary*, not the code they were compiled alongside.
/// `cargo test -p azlin --bin azlin` builds the bin's test harness; whether it
/// also refreshes the plain `target/debug/azlin` that `assert_cmd` invokes
/// depends on what else has been built and when. Switch branches, run
/// `cargo build` on one and `cargo test` on the other, and every assertion
/// here is made against yesterday's binary.
///
/// That has already produced a run of phantom failures in this work — three
/// tests "failing" against behaviour that was correct in the tree and absent
/// from the binary. A confusing red is worse than a slow red, so this says
/// which it is.
///
/// Modification times, not content hashes. A fresh clone or a branch switch
/// stamps every source with the checkout time, so the first run afterwards
/// demands a rebuild — which is genuinely needed. The reverse case, a source
/// dated in the future by clock skew or a bad archive, wedges this until
/// somebody touches the file; that is not fixable with mtime and is not worth
/// a content hash of the whole tree to avoid.
fn assert_binary_is_not_stale() {
    // Computed once: `run_isolated` has around a hundred call sites in this
    // suite, the answer cannot change during a test process, and the walk stats
    // every `.rs` file under `crates/`.
    static VERDICT: std::sync::OnceLock<Option<String>> = std::sync::OnceLock::new();
    let stale = VERDICT.get_or_init(|| {
        let binary = binary_mtime()?;
        let (newest_source, path) = newest_source_mtime()?;
        if binary >= newest_source {
            return None;
        }
        Some(format!(
            "target/debug/azlin is older than {}. These tests run the binary, not \
             the compiled-in code, so every assertion below would be made against a \
             stale build. Run `cargo build -p azlin` and try again.",
            path.display()
        ))
    });
    assert!(stale.is_none(), "{}", stale.as_deref().unwrap_or_default());
}

fn binary_mtime() -> Option<std::time::SystemTime> {
    let path = assert_cmd::cargo::cargo_bin("azlin");
    std::fs::metadata(path).ok()?.modified().ok()
}

/// The most recently modified `.rs` file that the binary is built from, and
/// its path.
///
/// Test-only files are excluded, and the exclusion is the difference between a
/// useful guard and one everybody turns off. `src/tests/` is behind
/// `#[cfg(test)]`, so it is not an input to the non-test build at all: cargo
/// correctly declines to relink the binary when one changes, and a guard that
/// counted it would demand a rebuild that cargo would refuse to perform. Files
/// that mix production code with an inline `#[cfg(test)] mod tests` are
/// deliberately *not* excluded — cargo recompiles the whole file either way, so
/// the binary's mtime moves with them.
fn newest_source_mtime() -> Option<(std::time::SystemTime, std::path::PathBuf)> {
    // CARGO_MANIFEST_DIR is `<repo>/rust/crates/azlin`; the workspace sources
    // are its grandparent.
    let crates = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent()?;
    let mut newest: Option<(std::time::SystemTime, std::path::PathBuf)> = None;
    let mut stack = vec![crates.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Ok(meta) = entry.metadata() else { continue };
            if meta.is_dir() {
                // `target` can live inside the workspace and is not a source;
                // `tests` directories are test-only.
                if path
                    .file_name()
                    .is_some_and(|n| n == "target" || n == "tests")
                {
                    continue;
                }
                stack.push(path);
            } else if path.extension().is_some_and(|e| e == "rs")
                && !path
                    .file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| n.ends_with("_tests.rs"))
            {
                if let Ok(modified) = meta.modified() {
                    if newest.as_ref().is_none_or(|(t, _)| modified > *t) {
                        newest = Some((modified, path));
                    }
                }
            }
        }
    }
    newest
}

/// Assert an isolated azlin invocation succeeded, showing output when it did not.
pub(super) fn assert_isolated_ok(out: &std::process::Output, what: &str) {
    assert!(
        out.status.success(),
        "{what} failed (exit {:?})\nstdout: {}\nstderr: {}",
        out.status.code(),
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr),
    );
}

/// Run azlin as a subprocess with `$HOME` redirected to `dir`.
///
/// Some state does not honour `AZLIN_CONFIG_DIR` and resolves straight from
/// `dirs::home_dir()` — `autopilot.toml` is the current example. Those tests
/// need the home directory itself isolated, or they read, delete and rewrite
/// the developer's real `~/.azlin/autopilot.toml` (issue #1079).
///
/// That `autopilot` ignores `AZLIN_CONFIG_DIR` while `config` honours it is an
/// inconsistency in the production code, not something this helper fixes; it is
/// worked around here so the tests stop being destructive.
pub(super) fn run_isolated_home(dir: &TempDir, args: &[&str]) -> std::process::Output {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("HOME", dir.path())
        .timeout(std::time::Duration::from_secs(30))
        .output()
        .unwrap()
}

/// Helper: run azlin with no Azure config and verify graceful failure.
pub(super) fn assert_graceful_auth_error(args: &[&str]) {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .env_remove("AZURE_CLIENT_ID")
        .env_remove("AZURE_CLIENT_SECRET")
        .env_remove("AZURE_TENANT_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&out.stderr);
    let stdout = String::from_utf8_lossy(&out.stdout);
    let combined = format!("{}{}", stdout, stderr);
    // Must not panic
    assert!(
        !combined.contains("thread 'main' panicked"),
        "Command {:?} panicked: {}",
        args,
        combined
    );
    // Should either fail with non-zero exit OR contain an error/auth message
    let has_error_msg = combined.contains("auth")
        || combined.contains("Auth")
        || combined.contains("config")
        || combined.contains("login")
        || combined.contains("subscription")
        || combined.contains("error")
        || combined.contains("Error")
        || combined.contains("az login")
        || combined.contains("Usage")
        || combined.contains("required");
    assert!(
        !out.status.success() || has_error_msg,
        "Command {:?} should fail or show error message, got success with: {}",
        args,
        combined
    );
}
