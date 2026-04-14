use super::common::*;
use std::sync::LazyLock;

// ── Tunnel help-text correctness tests ─────────────────────────────
// Verify that the tunnel command's help examples use the correct
// `open` subcommand syntax (bug fix regression guard).

/// Cached `azlin tunnel --help` stdout (spawned once across all tests).
static TUNNEL_HELP: LazyLock<String> = LazyLock::new(|| {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tunnel", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "tunnel --help should exit 0");
    String::from_utf8_lossy(&out.stdout).into_owned()
});

fn tunnel_help() -> &'static str {
    &TUNNEL_HELP
}

#[test]
fn test_tunnel_help_examples_use_open_subcommand() {
    let help = tunnel_help();
    for expected in [
        "tunnel open myvm 8080",
        "tunnel open myvm 5432",
        "tunnel open myvm 8080 3000 5432",
    ] {
        assert!(help.contains(expected), "help should contain '{expected}':\n{help}");
    }
}

#[test]
fn test_tunnel_help_no_bare_tunnel_vm_port_examples() {
    let help = tunnel_help();
    for line in help.lines() {
        if line.contains("tunnel myvm") {
            assert!(
                line.contains("tunnel open myvm"),
                "Found bare 'tunnel myvm' without 'open': {line}",
            );
        }
    }
}

#[test]
fn test_tunnel_help_lists_open_close_list_subcommands() {
    let help = tunnel_help();
    for keyword in ["open", "list", "close"] {
        let title = keyword[..1].to_uppercase() + &keyword[1..];
        assert!(
            help.contains(keyword) || help.contains(&title),
            "tunnel help should mention '{keyword}':\n{help}",
        );
    }
}

#[test]
fn test_tunnel_help_close_examples_correct() {
    let help = tunnel_help();
    assert!(
        help.contains("tunnel close myvm") || help.contains("tunnel close --all"),
        "tunnel help should include close examples:\n{help}",
    );
    assert!(help.contains("tunnel list"), "tunnel help should include 'tunnel list':\n{help}");
}

#[test]
fn test_tunnel_open_help_exits_zero() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tunnel", "open", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    assert!(out.status.success(), "tunnel open --help should exit 0");
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("port") || stdout.contains("Port") || stdout.contains("PORT"),
        "tunnel open help should mention ports:\n{stdout}",
    );
}

#[test]
fn test_tunnel_open_cli_parse_valid() {
    let _ = make_cli(&["tunnel", "open", "myvm", "8080"]);
}

#[test]
fn test_tunnel_bare_vm_port_rejected_by_parser() {
    use clap::Parser;
    let result = azlin_cli::Cli::try_parse_from(["azlin", "tunnel", "myvm", "8080"]);
    assert!(result.is_err(), "bare 'tunnel myvm 8080' should be rejected by the parser");
}
