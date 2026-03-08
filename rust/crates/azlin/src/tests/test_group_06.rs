use std::fs;
use tempfile::TempDir;

// ── CLI integration: sessions ────────────────────────────────

#[test]
fn test_cli_sessions_list_empty() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No saved sessions"));
}

#[test]
fn test_cli_sessions_save_and_list() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "my-session",
            "--resource-group",
            "test-rg",
            "--vms",
            "vm1",
            "vm2",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Saved session 'my-session'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("my-session"));
}

#[test]
fn test_cli_sessions_save_and_load() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "load-test",
            "--resource-group",
            "rg-test",
            "--vms",
            "vm-alpha",
            "vm-beta",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "load-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Loaded session 'load-test'"));
    assert!(stdout.contains("rg-test"));
    assert!(stdout.contains("vm-alpha"));
    assert!(stdout.contains("vm-beta"));
}

#[test]
fn test_cli_sessions_load_nonexistent() {
    let dir = TempDir::new().unwrap();
    fs::create_dir_all(dir.path().join(".azlin").join("sessions")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "nonexistent"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not found"));
}

#[test]
fn test_cli_sessions_delete() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "delete-me",
            "--resource-group",
            "rg1",
            "--vms",
            "vm1",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "delete", "delete-me", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Deleted session"));

    // Verify it's gone
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "delete-me"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_cli_sessions_list_multiple() {
    let dir = TempDir::new().unwrap();
    for name in &["sess-1", "sess-2", "sess-3"] {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                name,
                "--resource-group",
                "rg",
                "--vms",
                "vm1",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();
    }
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("sess-1"));
    assert!(stdout.contains("sess-2"));
    assert!(stdout.contains("sess-3"));
}

#[test]
fn test_cli_sessions_overwrite() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "overwrite-me",
            "--resource-group",
            "rg-old",
            "--vms",
            "vm-old",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "overwrite-me",
            "--resource-group",
            "rg-new",
            "--vms",
            "vm-new",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "overwrite-me"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("rg-new"));
    assert!(stdout.contains("vm-new"));
}
