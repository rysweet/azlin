//! End-to-end tests for features that work without Azure auth.
//! These exercise the real binary and validate user-facing behavior.

mod integration;
use integration::{run_azlin, run_azlin_with_env};

#[test]
fn test_full_config_workflow() {
    // Use isolated config dir so we don't mutate real config
    let tmp = tempfile::TempDir::new().unwrap();
    let dir = tmp.path().to_str().unwrap();
    let env = [("AZLIN_CONFIG_DIR", dir)];

    // Show creates default config with expected keys
    let (stdout, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("default_region"),
        "show should list default_region"
    );

    // Set → Get roundtrip
    let (_, _, code) =
        run_azlin_with_env(&["config", "set", "default_vm_size", "Standard_B1ms"], &env);
    assert_eq!(code, 0);

    let (stdout, _, code) = run_azlin_with_env(&["config", "get", "default_vm_size"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Standard_B1ms"),
        "get should return the value we just set, got: {}",
        stdout,
    );

    // Second show still works
    let (stdout, _, code) = run_azlin_with_env(&["config", "show"], &env);
    assert_eq!(code, 0);
    assert!(stdout.contains("Standard_B1ms"));
}

#[test]
fn test_all_help_texts_consistent() {
    let commands = vec![
        "list",
        "start",
        "stop",
        "connect",
        "delete",
        "new",
        "env",
        "snapshot",
        "storage",
        "keys",
        "cost",
        "costs",
        "auth",
        "batch",
        "fleet",
        "compose",
        "health",
        "bastion",
        "template",
        "context",
        "sessions",
        "disk",
        "ip",
        "github-runner",
        "autopilot",
        "tag",
        "logs",
        "cleanup",
        "code",
        "session",
        "w",
        "ps",
        "top",
        "update",
        "os-update",
    ];

    for cmd in commands {
        let (_, _, code) = run_azlin(&[cmd, "--help"]);
        assert_eq!(code, 0, "Failed: {} --help", cmd);
    }
}

#[test]
fn test_completions_all_shells() {
    for shell in ["bash", "zsh", "fish", "elvish", "powershell"] {
        let (stdout, _, code) = run_azlin(&["completions", shell]);
        assert_eq!(code, 0, "Failed: completions {}", shell);
        assert!(!stdout.is_empty(), "Empty completions for {}", shell);
    }
}

#[test]
fn test_version_format() {
    // --version is the clap built-in flag
    let (stdout, _, code) = run_azlin(&["--version"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("azlin"), "should contain binary name");
    assert!(
        stdout.contains(env!("CARGO_PKG_VERSION")),
        "should contain version number"
    );

    // `version` subcommand also works
    let (stdout, _, code) = run_azlin(&["version"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("azlin"));
}

#[test]
fn test_no_panic_on_any_subcommand_without_args() {
    // Every subcommand should either succeed or fail gracefully — never panic
    let commands: Vec<Vec<&str>> = vec![
        vec!["list"],
        vec!["cost"],
        vec!["auth", "list"],
        vec!["template", "list"],
        vec!["sessions", "list"],
        vec!["context", "list"],
        vec!["keys", "list"],
        vec!["storage", "list"],
    ];

    for args in &commands {
        let (stdout, stderr, _) = run_azlin(args);
        let combined = format!("{}{}", stdout, stderr);
        assert!(
            !combined.contains("panicked"),
            "Panic detected in: azlin {}",
            args.join(" "),
        );
        assert!(
            !combined.contains("RUST_BACKTRACE"),
            "Backtrace leak in: azlin {}",
            args.join(" "),
        );
    }
}

#[test]
fn test_error_messages_are_helpful() {
    // Missing VM name should mention what's needed
    let (_, stderr, code) = run_azlin(&["start"]);
    assert_ne!(code, 0);
    let lower = stderr.to_lowercase();
    assert!(
        lower.contains("vm_name") || lower.contains("required") || lower.contains("usage"),
        "start without args should mention VM_NAME requirement, got: {}",
        stderr,
    );
}

#[test]
fn test_keys_list_local() {
    let (stdout, stderr, code) = run_azlin(&["keys", "list"]);
    // Should succeed or fail gracefully if ~/.ssh doesn't exist (CI runners)
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        code == 0
            || combined.contains("SSH")
            || combined.contains("ssh")
            || combined.contains("No"),
        "keys list output unexpected (code {}): {}",
        code,
        combined,
    );
}

#[test]
fn test_config_get_nonexistent_key() {
    let tmp = tempfile::TempDir::new().unwrap();
    let dir = tmp.path().to_str().unwrap();
    let env = [("AZLIN_CONFIG_DIR", dir)];

    let (stdout, stderr, code) = run_azlin_with_env(&["config", "get", "no_such_key"], &env);
    // Should fail or return empty — never panic
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "config get unknown key panicked"
    );
    // Non-zero exit or empty output both acceptable
    assert!(
        code != 0 || stdout.trim().is_empty() || combined.contains("not found"),
        "unexpected result for unknown config key: code={} stdout='{}'",
        code,
        stdout,
    );
}

#[test]
fn test_invalid_command_exits_nonzero() {
    let (_, _, code) = run_azlin(&["not-a-real-command-xyz"]);
    assert_ne!(code, 0, "unknown command should exit non-zero");
}

#[test]
fn test_help_mentions_core_commands() {
    let (stdout, _, code) = run_azlin(&["--help"]);
    assert_eq!(code, 0);
    for cmd in ["list", "start", "stop", "connect", "new", "config", "keys"] {
        assert!(stdout.contains(cmd), "help missing core command: {}", cmd);
    }
}
