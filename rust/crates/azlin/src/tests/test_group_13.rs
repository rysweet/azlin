use tempfile::TempDir;

// ── CLI integration: completions content verification ────────

#[test]
fn test_completions_zsh_content() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "zsh"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("compdef") || stdout.len() > 100);
}

#[test]
fn test_completions_powershell() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "powershell"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(out.stdout.len() > 50);
}

#[test]
fn test_completions_elvish() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "elvish"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(out.stdout.len() > 50);
}

// ── CLI integration: graceful failures without Azure ─────────

#[test]
fn test_list_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["list"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    // Should fail gracefully, not crash
    let stderr = String::from_utf8_lossy(&out.stderr);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        !out.status.success()
            || stderr.contains("config")
            || stderr.contains("subscription")
            || stderr.contains("auth")
            || stderr.contains("az login")
            || stdout.contains("No VMs")
    );
}

#[test]
fn test_show_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["show", "nonexistent-vm"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    assert!(!out.status.success() || !String::from_utf8_lossy(&out.stderr).is_empty());
}

#[test]
fn test_health_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["health"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    // Graceful failure or empty result
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success() || !combined.is_empty());
}

#[test]
fn test_status_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["status"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success() || !combined.is_empty());
}

// ── CLI integration: context full lifecycle ──────────────────

#[test]
fn test_context_full_lifecycle() {
    let dir = TempDir::new().unwrap();
    // create
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "context",
            "create",
            "lifecycle-ctx",
            "--subscription-id",
            "sub-123",
            "--resource-group",
            "rg-test",
        ])
        .env("HOME", dir.path())
        .assert()
        .success();
    // list
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
    // use
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "lifecycle-ctx"])
        .env("HOME", dir.path())
        .assert()
        .success();
    // show
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
    // delete
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "delete", "lifecycle-ctx", "--force"])
        .env("HOME", dir.path())
        .assert()
        .success();
}

// ── CLI integration: auth list with temp home ────────────────

#[test]
fn test_auth_list_empty() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("No")
            || stdout.contains("profile")
            || stdout.is_empty()
            || stdout.contains("auth")
    );
}

// ── CLI integration: sessions with temp home ─────────────────

#[test]
fn test_sessions_list_empty_temp() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(out.status.success());
}

// ── CLI integration: template with temp home ─────────────────

#[test]
fn test_template_list_empty_temp() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(out.status.success());
}

// ── CLI integration: verbose flag ────────────────────────────

#[test]
fn test_verbose_version() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--verbose", "version"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(String::from_utf8_lossy(&out.stdout).contains(env!("CARGO_PKG_VERSION")));
}

// ── CLI integration: json output format ──────────────────────

#[test]
fn test_json_output_version() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "json", "version"])
        .output()
        .unwrap();
    assert!(out.status.success());
}

#[test]
fn test_csv_output_version() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "csv", "version"])
        .output()
        .unwrap();
    assert!(out.status.success());
}

// ── CLI integration: invalid subcommand ──────────────────────

#[test]
fn test_invalid_subcommand() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["totally-bogus-command"])
        .output()
        .unwrap();
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("error")
            || stderr.contains("unrecognized")
            || stderr.contains("invalid")
            || !stderr.is_empty()
    );
}

// ── CLI integration: doit examples ───────────────────────────

#[test]
fn test_doit_examples() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "examples"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(out.stdout.len() > 10);
}
