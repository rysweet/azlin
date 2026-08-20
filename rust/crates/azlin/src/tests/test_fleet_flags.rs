//! Regression tests for the `fleet` half of #1089.
//!
//! `azlin fleet run` declared thirteen flags — `--tag`, `--pattern`, `--all`,
//! `--parallel`, `--if-idle`, `--if-cpu-below`, `--if-mem-below`,
//! `--smart-route`, `--count`, `--retry-failed`, `--show-diff` and
//! `--timeout` — and destructured exactly `command`, `resource_group` and
//! `dry_run`. Every other flag was accepted, printed in `--help` and dropped,
//! so `azlin fleet run 'rm -rf /tmp/x' --pattern staging-*` ran on production
//! and reported success.
//!
//! The gating logic itself is unit-tested in `fleet_select`; these tests drive
//! the real binary to prove the handler now reads the flags at all. They stop
//! at the point azlin would call Azure — rejection happens during argument
//! validation, and `--dry-run` prints the resolved plan — so none needs
//! credentials or the network.

use tempfile::TempDir;

use super::common::run_isolated;

/// A config directory whose `config.toml` names a resource group, so
/// `--dry-run` gets far enough to print the plan.
fn config_dir() -> TempDir {
    let dir = TempDir::new().unwrap();
    std::fs::write(
        dir.path().join("config.toml"),
        "default_resource_group = \"rg-fleet-test\"\n",
    )
    .unwrap();
    dir
}

fn stdout_of(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stdout).to_string()
}

fn combined(out: &std::process::Output) -> String {
    format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    )
}

// ── selection flags ──────────────────────────────────────────────────────

/// `--all` means "every VM", so pairing it with a narrowing filter is
/// ambiguous. Before the fix both were discarded and the run went everywhere.
#[test]
fn fleet_run_rejects_all_combined_with_tag() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["fleet", "run", "uptime", "--all", "--tag", "env=dev"],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

#[test]
fn fleet_run_rejects_all_combined_with_pattern() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["fleet", "run", "uptime", "--all", "--pattern", "web-*"],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

/// An empty `--pattern` reads like a filter and selects nothing; accepting it
/// silently is the same class of lie as discarding it.
#[test]
fn fleet_run_rejects_an_empty_pattern() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["fleet", "run", "uptime", "--pattern", "  "]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--pattern must not be empty"),
        "{}",
        combined(&out)
    );
}

/// A malformed `--tag` used to be discarded outright, so `--tag env` ran the
/// command on the whole resource group.
#[test]
fn fleet_run_rejects_a_malformed_tag() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["fleet", "run", "uptime", "--tag", "env"]);
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(combined(&out).contains("key=value"), "{}", combined(&out));
}

/// The dry-run plan must name the filter it will apply. Before the fix it
/// printed the same line whatever filters were passed.
#[test]
fn fleet_run_dry_run_names_the_tag_filter() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["fleet", "run", "uptime", "--dry-run", "--tag", "env=dev"],
    );
    let text = stdout_of(&out);
    assert!(text.contains("env=dev"), "{text}");
}

#[test]
fn fleet_run_dry_run_names_the_name_pattern() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &["fleet", "run", "uptime", "--dry-run", "--pattern", "web-*"],
    );
    let text = stdout_of(&out);
    assert!(text.contains("web-*"), "{text}");
}

/// With no filter the plan says "no filter" rather than something that reads
/// like a narrow selection.
#[test]
fn fleet_run_dry_run_admits_when_there_is_no_filter() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["fleet", "run", "uptime", "--dry-run"]);
    let text = stdout_of(&out);
    assert!(text.contains("no filter"), "{text}");
}

// ── execution flags ──────────────────────────────────────────────────────

/// `--timeout` and `--parallel` reach the plan, so the user can see the
/// values took effect before committing to a real run.
#[test]
fn fleet_run_dry_run_reports_timeout_and_parallelism() {
    let dir = config_dir();
    let out = run_isolated(
        &dir,
        &[
            "fleet",
            "run",
            "uptime",
            "--dry-run",
            "--timeout",
            "45",
            "--parallel",
            "7",
        ],
    );
    let text = stdout_of(&out);
    assert!(text.contains("45s"), "{text}");
    assert!(text.contains("7 parallel"), "{text}");
}

/// The defaults clap declares (`--timeout 300`, `--parallel 10`) must be the
/// ones the handler uses, not values invented downstream.
#[test]
fn fleet_run_dry_run_reports_the_declared_defaults() {
    let dir = config_dir();
    let out = run_isolated(&dir, &["fleet", "run", "uptime", "--dry-run"]);
    let text = stdout_of(&out);
    assert!(text.contains("300s"), "{text}");
    assert!(text.contains("10 parallel"), "{text}");
}

// ── workflow ─────────────────────────────────────────────────────────────

#[test]
fn fleet_workflow_rejects_all_combined_with_a_filter() {
    let dir = config_dir();
    let wf = dir.path().join("wf.yaml");
    std::fs::write(&wf, "steps:\n  - run: uptime\n").unwrap();
    let out = run_isolated(
        &dir,
        &[
            "fleet",
            "workflow",
            wf.to_str().unwrap(),
            "--all",
            "--pattern",
            "web-*",
        ],
    );
    assert!(!out.status.success(), "{}", combined(&out));
    assert!(
        combined(&out).contains("--all cannot be combined"),
        "{}",
        combined(&out)
    );
}

#[test]
fn fleet_workflow_dry_run_names_the_filter_and_parallelism() {
    let dir = config_dir();
    let wf = dir.path().join("wf.yaml");
    std::fs::write(&wf, "steps:\n  - run: uptime\n").unwrap();
    let out = run_isolated(
        &dir,
        &[
            "fleet",
            "workflow",
            wf.to_str().unwrap(),
            "--dry-run",
            "--pattern",
            "web-*",
            "--parallel",
            "3",
        ],
    );
    let text = stdout_of(&out);
    assert!(text.contains("web-*"), "{text}");
    assert!(text.contains("3 parallel"), "{text}");
}

// ── load probe ───────────────────────────────────────────────────────────

/// The probe is a shell string assembled in Rust and run on a VM, so a quoting
/// slip in it fails at a distance: `--if-idle` would see an unparsable reading,
/// skip every VM, and look like a working filter. Run it here and parse the
/// result with the same function the handler uses.
#[cfg(target_os = "linux")]
#[test]
fn the_load_probe_command_actually_produces_a_reading() {
    let cmd = crate::fleet_select::probe_command();
    let out = std::process::Command::new("sh")
        .arg("-c")
        .arg(&cmd)
        .output()
        .expect("sh is available");
    let stdout = String::from_utf8_lossy(&out.stdout);
    let load = crate::fleet_select::parse_probe(out.status.code().unwrap_or(-1), &stdout);
    assert!(
        load.is_complete(),
        "probe produced no usable reading.\ncommand: {cmd}\nstdout: {stdout:?}\nstderr: {:?}",
        String::from_utf8_lossy(&out.stderr)
    );
    let cpu = load.cpu_percent.unwrap();
    let mem = load.mem_percent.unwrap();
    assert!((0.0..=100.0).contains(&cpu), "cpu out of range: {cpu}");
    assert!((0.0..=100.0).contains(&mem), "mem out of range: {mem}");
}
