//! Regression tests for the costs-and-deploy third of #1089.
//!
//! - `azlin costs actions --priority` was discarded, so every recommendation
//!   was listed *and applied* whatever the user asked for. `--priority high
//!   apply` deallocated the Low-impact VMs the filter existed to exclude.
//! - `azlin doit deploy --output-dir`, `--max-iterations` and `--quiet` were
//!   discarded. The third is cosmetic; the second is not — nothing bounded how
//!   many commands a model could hand back to be run against a live
//!   subscription, while `--help` said 50.
//!
//! These drive the real binary and stop where azlin would call Azure or the
//! model.

use tempfile::TempDir;

use super::common::run_isolated;

fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-costs-test\"\n",
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
fn the_four_flags_are_still_advertised() {
    let dir = config_dir();
    let costs = combined(&run_isolated(&dir, &["costs", "actions", "--help"]));
    assert!(costs.contains("--priority"), "{}", costs);

    let doit = combined(&run_isolated(&dir, &["doit", "deploy", "--help"]));
    for flag in ["--output-dir", "--max-iterations", "--quiet"] {
        assert!(doit.contains(flag), "{} missing: {}", flag, doit);
    }
}

/// An unrecognised priority is refused before anything runs, rather than
/// filtering every recommendation out and reporting success.
#[test]
fn an_unknown_priority_is_refused_by_name() {
    let dir = config_dir();
    let out = combined(&run_isolated(
        &dir,
        &[
            "costs",
            "actions",
            "list",
            "--rg",
            "rg-x",
            "--priority",
            "urgent",
        ],
    ));
    assert!(
        out.contains("urgent") && out.contains("High, Medium, Low"),
        "the failure must name the value and the options: {}",
        out
    );
}

/// `--max-iterations` is validated by the parser, so a bad value never
/// reaches the model — the expensive half of this command.
#[test]
fn max_iterations_takes_a_number() {
    let dir = config_dir();
    let out = combined(&run_isolated(
        &dir,
        &["doit", "deploy", "do a thing", "--max-iterations", "seven"],
    ));
    assert!(
        out.contains("invalid value") || out.contains("seven"),
        "{}",
        out
    );
}

/// The three deploy flags parse together and nothing panics before the
/// model call.
#[test]
fn the_deploy_flags_parse_together() {
    let dir = config_dir();
    let out_dir = TempDir::new().unwrap();
    let out = combined(&run_isolated(
        &dir,
        &[
            "doit",
            "deploy",
            "do a thing",
            "--dry-run",
            "--quiet",
            "--max-iterations",
            "5",
            "--output-dir",
            out_dir.path().to_str().unwrap(),
        ],
    ));
    assert!(
        !out.contains("unexpected argument") && !out.contains("thread 'main' panicked"),
        "{}",
        out
    );
}
