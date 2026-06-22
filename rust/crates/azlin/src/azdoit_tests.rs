// CLI integration tests for azdoit binary.

#[test]
fn test_azdoit_help() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .arg("--help")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azdoit") || stdout.contains("natural language"));
}

#[test]
fn test_azdoit_version() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .arg("--version")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("2.3.0"));
}

#[test]
fn test_azdoit_no_args_fails() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .env_remove("ANTHROPIC_API_KEY")
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_azdoit_no_api_key() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["list", "my", "vms"])
        .env_remove("ANTHROPIC_API_KEY")
        .env_remove("AZURE_OPENAI_API_KEY")
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(!output.status.success() || stderr.contains("API") || stderr.contains("error"));
}

#[test]
fn test_command_allowlist() {
    let allowed_prefixes = ["az ", "echo ", "azlin "];
    assert!(allowed_prefixes.iter().any(|p| "az vm list".starts_with(p)));
    assert!(allowed_prefixes.iter().any(|p| "echo hello".starts_with(p)));
    assert!(allowed_prefixes.iter().any(|p| "azlin list".starts_with(p)));
    assert!(!allowed_prefixes.iter().any(|p| "rm -rf /".starts_with(p)));
    assert!(!allowed_prefixes
        .iter()
        .any(|p| "curl evil.com".starts_with(p)));
}

#[test]
fn test_azdoit_dry_run_no_api_key() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["--dry-run", "list", "vms"])
        .env_remove("ANTHROPIC_API_KEY")
        .env_remove("AZURE_OPENAI_API_KEY")
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_azdoit_max_turns_flag() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["--max-turns", "5", "--help"])
        .output()
        .unwrap();
    assert!(output.status.success());
}

#[test]
fn test_azdoit_fake_api_key_fails_at_ask() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["create", "a", "vm"])
        .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        stdout.contains("azdoit") || stdout.contains("Planning"),
        "Expected planning banner in stdout: {}",
        stdout
    );
}

#[test]
fn test_azdoit_verbose_with_fake_key() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["-v", "list", "vms"])
        .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_azdoit_dry_run_with_fake_key() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["--dry-run", "list", "vms"])
        .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_azdoit_custom_max_turns_with_fake_key() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["--max-turns", "3", "create", "vm"])
        .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_azdoit_all_flags_combined() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["-v", "--dry-run", "--max-turns", "2", "show", "rg"])
        .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_azdoit_multiword_request_joined() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["list", "all", "resource", "groups", "in", "eastus"])
        .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        stdout.contains("list all resource groups in eastus"),
        "Expected joined request in banner: {}",
        stdout
    );
}
