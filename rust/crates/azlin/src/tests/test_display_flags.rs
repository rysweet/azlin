//! Regression tests for the display third of #1089.
//!
//! Two flags that decided how output was laid out, and were discarded:
//!
//! - `azlin ps --grouped` promised "Group output by VM instead of prefixing"
//!   while every run printed the grouped layout regardless — and the prefixed
//!   layout it names as the alternative had never been built.
//! - `azlin list --show-tmux` defaults to true and was discarded, so
//!   `--show-tmux false` collected tmux sessions over SSH anyway. Only its
//!   sibling `--no-tmux` was read.
//!
//! These drive the real binary and stop where azlin would call Azure.

use tempfile::TempDir;

use super::common::run_isolated;

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-display-test\"\n",
    )
    .unwrap();
    dir
}

fn combined(out: &std::process::Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

/// The flags must still reach `--help`. The cheapest way to make a
/// flag-wiring checker green is to delete the flag rather than wire it.
#[test]
fn the_two_flags_are_still_advertised() {
    let dir = config_dir();
    let ps = combined(&run_isolated(&dir, &["ps", "--help"]));
    assert!(ps.contains("--grouped"), "{}", ps);

    let list = combined(&run_isolated(&dir, &["list", "--help"]));
    assert!(list.contains("--show-tmux"), "{}", list);
    assert!(
        list.contains("--no-tmux"),
        "the sibling that always worked must survive too: {}",
        list
    );
}

/// `--show-tmux` takes a value, which is what made the silence possible:
/// `--show-tmux false` parses cleanly and used to change nothing.
#[test]
fn show_tmux_false_is_accepted_by_the_parser() {
    let dir = config_dir();
    let out = combined(&run_isolated(&dir, &["list", "--show-tmux", "false"]));
    assert!(
        !out.contains("unexpected argument") && !out.contains("invalid value"),
        "--show-tmux false must parse: {}",
        out
    );
}

/// Both spellings of "off" are accepted together. Neither has ever meant
/// "on", so a run that passes both is not a contradiction to resolve.
#[test]
fn no_tmux_and_show_tmux_false_can_be_passed_together() {
    let dir = config_dir();
    let out = combined(&run_isolated(
        &dir,
        &["list", "--no-tmux", "--show-tmux", "false"],
    ));
    assert!(
        !out.contains("cannot be used with") && !out.contains("unexpected argument"),
        "{}",
        out
    );
}

/// `azlin ps` needs Azure to find its VMs, so the binary cannot be driven far
/// enough here to compare layouts. What it can prove is that the flag is
/// parsed and reaches the same place with and without it — the layout choice
/// itself is pinned by the `ps_output` unit tests.
#[test]
fn ps_takes_grouped_without_changing_where_it_stops() {
    let dir = config_dir();
    let plain = combined(&run_isolated(&dir, &["ps"]));
    let grouped = combined(&run_isolated(&dir, &["ps", "--grouped"]));
    assert!(
        !grouped.contains("unexpected argument"),
        "--grouped must parse: {}",
        grouped
    );
    // Both stop at the same Azure boundary; neither panics.
    for out in [&plain, &grouped] {
        assert!(!out.contains("thread 'main' panicked"), "{}", out);
    }
}
