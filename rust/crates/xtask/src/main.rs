//! Repository maintenance checks that are cheaper to run as a program than to
//! express as a lint.
//!
//! Usage:
//!
//! ```text
//! cargo run -p xtask -- check-flag-wiring [--verbose]
//! ```
//!
//! Deliberately dependency-light (syn only, no clap): this runs as a CI gate
//! and as a pre-commit hook, so its own build must stay in the seconds.

mod flag_wiring;

use std::path::PathBuf;
use std::process::ExitCode;

const USAGE: &str = "\
xtask — azlin repository checks

USAGE:
    cargo run -p xtask -- <command> [options]

COMMANDS:
    check-flag-wiring    Fail if a CLI flag reaches `--help` but is never read
                         by a handler (issue #1089).

OPTIONS:
    --verbose            Also list the allowlisted known-unwired flags.
    -h, --help           Show this help.
";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let verbose = args.iter().any(|a| a == "--verbose");

    match args.first().map(String::as_str) {
        Some("check-flag-wiring") => check_flag_wiring(verbose),
        Some("-h") | Some("--help") | None => {
            print!("{USAGE}");
            ExitCode::SUCCESS
        }
        Some(other) => {
            eprintln!("xtask: unknown command `{other}`\n");
            print!("{USAGE}");
            ExitCode::FAILURE
        }
    }
}

/// The Rust workspace root, resolved at compile time so the check behaves the
/// same whether it is invoked from `rust/`, from the repo root, or by a
/// pre-commit hook with an arbitrary cwd.
fn workspace_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent() // crates/
        .and_then(|p| p.parent()) // rust/
        .expect("xtask lives at rust/crates/xtask")
        .to_path_buf()
}

fn check_flag_wiring(verbose: bool) -> ExitCode {
    let report = match flag_wiring::run(&workspace_root()) {
        Ok(report) => report,
        Err(e) => {
            eprintln!("check-flag-wiring: {e}");
            return ExitCode::FAILURE;
        }
    };

    println!("CLI flag wiring check");
    println!(
        "  {} declared inputs across {} clap enums in {}",
        report.declared_count,
        report.enum_count,
        flag_wiring::CLI_DEF
    );
    println!(
        "  {} handler files scanned under {}",
        report.scanned_files,
        flag_wiring::HANDLER_DIR
    );
    println!(
        "  {} allowlisted as known-unwired (each with its reason, see {})",
        report.allowed.len(),
        flag_wiring::ALLOWLIST
    );

    if verbose && !report.allowed.is_empty() {
        println!();
        println!("Allowlisted (each one is a flag that currently lies to the user):");
        for (finding, reason) in &report.allowed {
            println!("  {}", finding.invocation);
            println!("      {} — {reason}", finding.key);
        }
    }

    if !report.unwired.is_empty() {
        println!();
        println!(
            "FAIL: {} CLI input(s) reach `--help` but are never read by a handler.",
            report.unwired.len()
        );
        println!("clap accepts each of these and the handler then discards it, so the");
        println!("command silently does something other than what the user asked for.");
        println!();
        for finding in &report.unwired {
            println!("  {}", finding.invocation);
            if finding.help.is_empty() {
                println!("      declared as {}", finding.key);
            } else {
                println!(
                    "      declared as {} — `--help` says \"{}\"",
                    finding.key, finding.help
                );
            }
        }
        println!();
        println!("Fix it one of these ways:");
        println!("  1. Wire it — bind the field in the handler and act on it.");
        println!("  2. Delete it from the clap enum if it is not implemented.");
        println!("  3. Hide it (`#[arg(hide = true)]`) or reject it with a clear error.");
        println!(
            "  4. Last resort: add it to {} with a reason.",
            flag_wiring::ALLOWLIST
        );
        println!("     That is a deliberate, reviewable admission that the flag lies.");
    }

    if !report.stale_allow.is_empty() {
        println!();
        println!(
            "FAIL: {} allowlist entr(ies) no longer describe an unwired flag.",
            report.stale_allow.len()
        );
        println!(
            "Delete them from {} — the backlog shrank, which is the point.",
            flag_wiring::ALLOWLIST
        );
        println!();
        for key in &report.stale_allow {
            println!("  {key}");
        }
    }

    if report.ok() {
        println!();
        println!("OK: every declared CLI input is either read by a handler or allowlisted.");
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}
