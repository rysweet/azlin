//! Live Azure integration tests — exercise commands against real Azure.
//!
//! These tests require `az login` and access to the RYSWEET-LINUX-VM-POOL
//! resource group. Run with: `cargo test --test azure_live_integration -- --ignored`

mod integration;
use integration::run_azlin;

const RG: &str = "RYSWEET-LINUX-VM-POOL";
const VM: &str = "devo";

fn has_azure_login() -> bool {
    let (_, _, code) = run_azlin(&["--version"]);
    if code != 0 {
        return false;
    }
    let output = std::process::Command::new("az")
        .args(["account", "show", "--output", "json"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output();
    matches!(output, Ok(o) if o.status.success())
}

// ── List command ────────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_list_default() {
    if !has_azure_login() {
        return;
    }
    let (stdout, stderr, code) = run_azlin(&["list", "--no-tmux", "--resource-group", RG]);
    assert_eq!(code, 0, "list failed: {stderr}");
    assert!(stdout.contains("Session"), "missing Session column");
    assert!(stdout.contains("OS"), "missing OS column");
    assert!(stdout.contains("Status"), "missing Status column");
    assert!(stdout.contains("Total:"), "missing footer");
    assert!(stdout.contains("Hints:"), "missing hints");
}

#[test]
#[ignore]
fn test_live_list_wide() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["list", "--no-tmux", "--resource-group", RG, "--wide"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("VM Name"), "wide mode should show VM Name");
    assert!(stdout.contains("SKU"), "wide mode should show SKU");
}

#[test]
#[ignore]
fn test_live_list_json() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&[
        "list",
        "--no-tmux",
        "--resource-group",
        RG,
        "--output",
        "json",
    ]);
    assert_eq!(code, 0);
    let vms: Vec<serde_json::Value> = serde_json::from_str(&stdout).expect("invalid JSON");
    assert!(!vms.is_empty(), "should have at least one VM");
    assert!(vms[0]["name"].is_string(), "VM should have name");
}

#[test]
#[ignore]
fn test_live_list_csv() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&[
        "list",
        "--no-tmux",
        "--resource-group",
        RG,
        "--output",
        "csv",
    ]);
    assert_eq!(code, 0);
    let lines: Vec<&str> = stdout.lines().collect();
    assert!(lines.len() >= 2, "CSV should have header + data");
    assert!(
        lines[0].contains("Session"),
        "CSV header should contain Session"
    );
}

#[test]
#[ignore]
fn test_live_list_compact() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["list", "--no-tmux", "--resource-group", RG, "--compact"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Total:"),
        "compact should still have footer"
    );
}

#[test]
#[ignore]
fn test_live_list_bastion_table() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["list", "--no-tmux", "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Azure Bastion Hosts"),
        "should show bastion table"
    );
}

#[test]
#[ignore]
fn test_live_list_os_detection() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["list", "--no-tmux", "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(stdout.contains("Ubuntu"), "should detect Ubuntu OS");
}

#[test]
#[ignore]
fn test_live_list_ip_annotation() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["list", "--no-tmux", "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("(Bast)") || stdout.contains("(Pub)"),
        "IPs should have Bast or Pub annotation"
    );
}

// ── Show command ────────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_show() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["show", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(stdout.contains("Name:"), "should show Name");
    assert!(stdout.contains(VM), "should show VM name");
    assert!(stdout.contains("Power State:"), "should show power state");
    assert!(stdout.contains("Running"), "VM should be running");
}

// ── Status command ──────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_status() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["status", "--vm", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(stdout.contains(VM), "should show VM name");
    assert!(stdout.contains("Running"), "should show Running");
}

// ── Tag commands ────────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_tag_roundtrip() {
    if !has_azure_login() {
        return;
    }
    // Add
    let (_, _, code) = run_azlin(&[
        "tag",
        "add",
        VM,
        "integration-test=live",
        "--resource-group",
        RG,
    ]);
    assert_eq!(code, 0, "tag add failed");

    // Verify
    let (stdout, _, code) = run_azlin(&["tag", "list", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(stdout.contains("integration-test"), "tag should be present");

    // Remove
    let (_, _, code) = run_azlin(&[
        "tag",
        "remove",
        VM,
        "integration-test",
        "--resource-group",
        RG,
    ]);
    assert_eq!(code, 0, "tag remove failed");
}

// ── Health command ──────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_health() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["health", "--vm", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Four Golden Signals"),
        "should show health header"
    );
    assert!(stdout.contains(VM), "should show VM name");
    assert!(stdout.contains("Agent"), "should show Agent column");
    assert!(stdout.contains("Errors"), "should show Errors column");
    assert!(stdout.contains("Signals:"), "should show signals footer");
    assert!(
        stdout.contains("Thresholds:"),
        "should show thresholds footer"
    );
}

// ── SSH commands via bastion ────────────────────────────────────────

#[test]
#[ignore]
fn test_live_w() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["w", "--vm", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("load average"),
        "w should show load average"
    );
}

#[test]
#[ignore]
fn test_live_ps() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["ps", "--vm", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("PID") || stdout.contains("COMMAND"),
        "ps should show process info"
    );
}

#[test]
#[ignore]
fn test_live_env_list() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["env", "list", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(stdout.contains("HOME"), "env should contain HOME");
}

// ── Context commands ────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_context_list() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["context", "list"]);
    assert_eq!(code, 0);
}

// ── Config commands ─────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_config_show() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["config", "show"]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("az_cli_timeout"),
        "config should show timeout"
    );
}

// ── Start command (safe on running VM) ──────────────────────────────

#[test]
#[ignore]
fn test_live_start_running_vm() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["start", VM, "--resource-group", RG]);
    assert_eq!(code, 0, "start on running VM should succeed (no-op)");
}

// ── Cost command ────────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_cost() {
    if !has_azure_login() {
        return;
    }
    // Cost may fail on subscription type — that's OK, just verify it runs
    let (_, _, _code) = run_azlin(&["cost", "--resource-group", RG]);
    // Don't assert code==0 since subscription may not support consumption API
}

// ── Bastion commands ────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_bastion_list() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["bastion", "list", "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Bastion") || stdout.contains("bastion"),
        "should list bastions"
    );
}

// ── Snapshot commands ───────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_snapshot_list() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["snapshot", "list", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
}

// ── IP check ────────────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_ip_check() {
    if !has_azure_login() {
        return;
    }
    let (stdout, _, code) = run_azlin(&["ip", "check", VM, "--resource-group", RG]);
    assert_eq!(code, 0);
    assert!(stdout.contains("10.0.0."), "should show private IP");
}

// ── Storage commands ────────────────────────────────────────────────

#[test]
#[ignore]
fn test_live_storage_list() {
    if !has_azure_login() {
        return;
    }
    let (_, _, code) = run_azlin(&["storage", "list", "--resource-group", RG]);
    assert_eq!(code, 0);
}
