use crate::*;
use std::fs;
use tempfile::TempDir;

// ── CLI integration: context ─────────────────────────────────

#[test]
fn test_cli_context_list_empty() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No contexts found"));
}

#[test]
fn test_cli_context_create_and_list() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "dev-env"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Created context 'dev-env'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("dev-env"));
}

#[test]
fn test_cli_context_create_with_options() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "context",
            "create",
            "prod-env",
            "--subscription-id",
            "sub-123",
            "--tenant-id",
            "tenant-456",
            "--resource-group",
            "prod-rg",
            "--region",
            "eastus2",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());

    // Verify the TOML file was written with the correct fields
    let ctx_path = dir
        .path()
        .join(".azlin")
        .join("contexts")
        .join("prod-env.toml");
    assert!(ctx_path.exists());
    let content = fs::read_to_string(&ctx_path).unwrap();
    assert!(content.contains("sub-123"));
    assert!(content.contains("tenant-456"));
    assert!(content.contains("prod-rg"));
    assert!(content.contains("eastus2"));
}

#[test]
fn test_cli_context_use_and_show() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "staging"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "staging"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Switched to context 'staging'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("staging"));
}

#[test]
fn test_cli_context_use_nonexistent() {
    let dir = TempDir::new().unwrap();
    fs::create_dir_all(dir.path().join(".azlin").join("contexts")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "nonexistent"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not found"));
}

#[test]
fn test_cli_context_delete_force() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "deleteme"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "delete", "deleteme", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Deleted context 'deleteme'"));
}

#[test]
fn test_cli_context_delete_clears_active() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "active-ctx"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "active-ctx"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "delete", "active-ctx", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    // Active-context file should be removed
    let active_path = dir.path().join(".azlin").join("active-context");
    assert!(!active_path.exists());
}

#[test]
fn test_cli_context_rename() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "old-name", "--region", "westus2"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "rename", "old-name", "new-name"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Renamed context"));

    // Old file should be gone, new file should exist
    let old_path = dir
        .path()
        .join(".azlin")
        .join("contexts")
        .join("old-name.toml");
    let new_path = dir
        .path()
        .join(".azlin")
        .join("contexts")
        .join("new-name.toml");
    assert!(!old_path.exists());
    assert!(new_path.exists());

    // Name field inside the TOML should be updated
    let content = fs::read_to_string(&new_path).unwrap();
    assert!(content.contains("new-name"));
}

#[test]
fn test_cli_context_rename_updates_active() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "rename-active"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "rename-active"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "rename", "rename-active", "renamed-active"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let active = fs::read_to_string(dir.path().join(".azlin").join("active-context")).unwrap();
    assert_eq!(active.trim(), "renamed-active");
}

#[test]
fn test_cli_context_list_marks_active() {
    let dir = TempDir::new().unwrap();
    for name in &["ctx-a", "ctx-b", "ctx-c"] {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", name])
            .env("HOME", dir.path())
            .output()
            .unwrap();
    }

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "ctx-b"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("* ctx-b"));
}

#[test]
fn test_cli_context_show_no_selection() {
    let dir = TempDir::new().unwrap();
    fs::create_dir_all(dir.path().join(".azlin").join("contexts")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No context selected"));
}
