use std::fs;
use tempfile::TempDir;

// ── template tests ───────────────────────────────────────────

#[test]
fn test_template_list_empty() {
    let tmp = TempDir::new().unwrap();
    let tpl_dir = tmp.path().join("templates");
    fs::create_dir_all(&tpl_dir).unwrap();

    let count = fs::read_dir(&tpl_dir).unwrap().count();
    assert_eq!(count, 0);
}

#[test]
fn test_template_with_cloud_init() {
    let tmp = TempDir::new().unwrap();
    let tpl = serde_json::json!({
        "name": "web-server",
        "vm_size": "Standard_B2s",
        "cloud_init": "#!/bin/bash\napt-get update && apt-get install -y nginx",
    });
    let path = tmp.path().join("web-server.json");
    fs::write(&path, serde_json::to_string_pretty(&tpl).unwrap()).unwrap();

    let loaded: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    assert!(loaded["cloud_init"].as_str().unwrap().contains("nginx"));
}

#[test]
fn test_template_delete() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("ephemeral.json");
    fs::write(&path, r#"{"name":"ephemeral"}"#).unwrap();
    assert!(path.exists());
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}

// ── keys tests ───────────────────────────────────────────────

#[test]
fn test_keys_list_no_ssh_dir() {
    let tmp = TempDir::new().unwrap();
    let nonexistent = tmp.path().join("no_such_dir");
    assert!(fs::read_dir(&nonexistent).is_err());
}

#[test]
fn test_keys_list_filters_non_key_files() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    fs::write(ssh_dir.join("authorized_keys"), "key data").unwrap();
    fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();
    fs::write(ssh_dir.join("config"), "Host *").unwrap();

    let key_files: Vec<String> = fs::read_dir(ssh_dir)
        .unwrap()
        .filter_map(|e| {
            let name = e.ok()?.file_name().to_string_lossy().to_string();
            if name.starts_with("id_") || name.ends_with(".pub") {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    assert!(key_files.is_empty());
}

#[test]
fn test_keys_multiple_key_types() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    for key_type in &["id_rsa", "id_ed25519", "id_ecdsa"] {
        fs::write(ssh_dir.join(key_type), "private").unwrap();
        fs::write(ssh_dir.join(format!("{}.pub", key_type)), "public").unwrap();
    }

    let keys: Vec<String> = fs::read_dir(ssh_dir)
        .unwrap()
        .filter_map(|e| {
            let name = e.ok()?.file_name().to_string_lossy().to_string();
            if name.starts_with("id_") {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    assert_eq!(keys.len(), 6); // 3 private + 3 public
}

// ── resolve_vm_targets tests ─────────────────────────────────

#[tokio::test]
async fn test_resolve_vm_targets_with_ip_flag() {
    let targets = crate::resolve_vm_targets(Some("my-vm"), Some("192.168.1.1"), None)
        .await
        .unwrap();
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0].vm_name, "my-vm");
    assert_eq!(targets[0].ip, "192.168.1.1");
    assert_eq!(targets[0].user, "azureuser");
    assert!(targets[0].bastion.is_none());
}

#[tokio::test]
async fn test_resolve_vm_targets_ip_only_no_vm_name() {
    let targets = crate::resolve_vm_targets(None, Some("10.0.0.1"), None)
        .await
        .unwrap();
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0].vm_name, "10.0.0.1"); // uses IP as display name
    assert_eq!(targets[0].ip, "10.0.0.1");
    assert!(targets[0].bastion.is_none());
}

#[test]
fn test_completions_bash() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "bash"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("_azlin"));
}

#[test]
fn test_completions_zsh() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "zsh"])
        .output()
        .unwrap();
    assert!(output.status.success());
}

#[test]
fn test_completions_fish() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "fish"])
        .output()
        .unwrap();
    assert!(output.status.success());
}

// ── CLI integration: version ─────────────────────────────────

#[test]
fn test_version_command() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .arg("version")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azlin"));
    assert!(stdout.contains(env!("CARGO_PKG_VERSION")));
}

#[test]
fn test_help_flag() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .arg("--help")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azlin"));
}

// ── CLI integration: azlin-help ──────────────────────────────

#[test]
fn test_azlin_help_no_args() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .arg("azlin-help")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azlin"));
}

#[test]
fn test_azlin_help_with_subcommand() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["azlin-help", "list"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("list"));
}
