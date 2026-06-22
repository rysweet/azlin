use std::fs;
use tempfile::TempDir;

// ── CLI integration: template ────────────────────────────────

#[test]
fn test_cli_template_save_and_list() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "save", "mytemplate"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Saved template 'mytemplate'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("mytemplate"));
}

#[test]
fn test_cli_template_save_with_options() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "template",
            "save",
            "custom-tpl",
            "--description",
            "A test template",
            "--vm-size",
            "Standard_D8s_v3",
            "--region",
            "eastus",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "show", "custom-tpl"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Standard_D8s_v3"));
    assert!(stdout.contains("eastus"));
    assert!(stdout.contains("A test template"));
}

#[test]
fn test_cli_template_show_nonexistent() {
    let dir = TempDir::new().unwrap();
    // Ensure azlin dir exists
    fs::create_dir_all(dir.path().join(".azlin").join("templates")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "show", "no-such-template"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not found"));
}

#[test]
fn test_cli_template_apply() {
    let dir = TempDir::new().unwrap();
    // First create a template
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "template",
            "save",
            "apply-test",
            "--vm-size",
            "Standard_D2s_v3",
            "--region",
            "westus2",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "apply", "apply-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Standard_D2s_v3"));
    assert!(stdout.contains("westus2"));
}

#[test]
fn test_cli_template_delete_force() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "save", "todelete"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "delete", "todelete", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Deleted template 'todelete'"));

    // Verify it's gone
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "show", "todelete"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_cli_template_export_import() {
    let dir = TempDir::new().unwrap();
    // Create a template
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "template",
            "save",
            "exportme",
            "--vm-size",
            "Standard_D4s_v3",
            "--region",
            "northeurope",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let export_path = dir.path().join("exported.toml");
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "export", "exportme"])
        .arg(&export_path)
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(export_path.exists());

    // Delete the original
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "delete", "exportme", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    // Import it back
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "import"])
        .arg(&export_path)
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Imported template 'exportme'"));
}

#[test]
fn test_cli_template_list_empty_dir() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No templates found"));
}

#[test]
fn test_cli_template_create_alias() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "create", "via-create"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Saved template 'via-create'"));
}

#[test]
fn test_cli_template_list_multiple() {
    let dir = TempDir::new().unwrap();
    for name in &["tpl-a", "tpl-b", "tpl-c"] {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "save", name])
            .env("HOME", dir.path())
            .output()
            .unwrap();
    }
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("tpl-a"));
    assert!(stdout.contains("tpl-b"));
    assert!(stdout.contains("tpl-c"));
}
