use super::super::*;
use super::common::*;
use azlin_core::models::PowerState;
use std::collections::HashMap;

// ── List footer tests ───────────────────────────────────────────

#[test]
fn test_format_list_footer_no_tmux() {
    let out = format_list_footer(5, 0);
    assert_eq!(out, "Total: 5 VMs");
    assert!(!out.contains("tmux"));
}

#[test]
fn test_format_list_footer_with_tmux() {
    let out = format_list_footer(3, 7);
    assert!(out.contains("3 VMs"));
    assert!(out.contains("7 tmux sessions"));
}

#[test]
fn test_build_list_json_basic() {
    let vms = vec![make_test_vm("vm-1", PowerState::Running)];
    let tmux = HashMap::from([("vm-1".to_string(), vec!["main".to_string()])]);
    let json = build_list_json(&vms, &tmux);
    let arr = json.as_array().unwrap();
    assert_eq!(arr.len(), 1);
    assert_eq!(arr[0]["name"], "vm-1");
    assert_eq!(arr[0]["tmux_sessions"][0], "main");
}

#[test]
fn test_build_list_json_empty() {
    let json = build_list_json(&[], &HashMap::new());
    assert!(json.as_array().unwrap().is_empty());
}

// ── Snapshot formatting tests ───────────────────────────────────

#[test]
fn test_format_snapshot_rows_basic() {
    let snaps = vec![serde_json::json!({
        "name": "vm1_snapshot_20260301",
        "diskSizeGb": 128,
        "timeCreated": "2026-03-01T10:00:00Z",
        "provisioningState": "Succeeded"
    })];
    let rows = format_snapshot_rows(&snaps);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "vm1_snapshot_20260301");
    assert_eq!(rows[0].1, "128");
    assert!(rows[0].2.contains("2026-03-01"));
    assert_eq!(rows[0].3, "Succeeded");
}

#[test]
fn test_format_snapshot_rows_empty() {
    assert!(format_snapshot_rows(&[]).is_empty());
}

#[test]
fn test_build_snapshot_name() {
    let name = build_snapshot_name("my-vm", "20260301_120000");
    assert_eq!(name, "my-vm_snapshot_20260301_120000");
}

#[test]
fn test_build_snapshot_schedule_info() {
    let info = build_snapshot_schedule_info("vm-1", "rg-1", 6, 10, true, "2026-03-01");
    assert_eq!(info.vm_name, "vm-1");
    assert_eq!(info.every_hours, 6);
    assert_eq!(info.keep_count, 10);
    assert!(info.enabled);
}

// ── Storage formatting tests ────────────────────────────────────

#[test]
fn test_format_storage_status_basic() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "westus2",
        "kind": "FileStorage",
        "sku": {"name": "Premium_LRS"},
        "provisioningState": "Succeeded",
        "primaryEndpoints": {"file": "https://mystorage.file.core.windows.net/"}
    });
    let rows = format_storage_status(&acct);
    assert_eq!(rows.len(), 6);
    assert_eq!(rows[0], ("Name".to_string(), "mystorage".to_string()));
    assert_eq!(rows[1], ("Location".to_string(), "westus2".to_string()));
    assert!(rows[5].1.contains("mystorage.file.core.windows.net"));
}

#[test]
fn test_format_storage_status_missing_fields() {
    let acct = serde_json::json!({});
    let rows = format_storage_status(&acct);
    assert_eq!(rows.len(), 6);
    // All values should be "-"
    for (_, v) in &rows {
        assert_eq!(v, "-");
    }
}

#[test]
fn test_build_nfs_mount_command() {
    let cmd = build_nfs_mount_command("mystorage", "/mnt/data");
    assert!(cmd.contains("sudo mkdir -p /mnt/data"));
    assert!(cmd.contains("mystorage.file.core.windows.net"));
    assert!(cmd.contains("mount -t nfs"));
}

#[test]
fn test_build_cifs_mount_options() {
    let opts = build_cifs_mount_options("/home/user/.azlin/.mount_creds_acct");
    assert!(opts.contains("vers=3.0"));
    assert!(opts.contains("credentials=/home/user/.azlin/.mount_creds_acct"));
}

#[test]
fn test_build_azure_files_unc() {
    let unc = build_azure_files_unc("mystorage", "myshare");
    assert_eq!(unc, "//mystorage.file.core.windows.net/myshare");
}

// ── Cost dashboard tests ────────────────────────────────────────

#[test]
fn test_format_cost_dashboard() {
    let out = format_cost_dashboard("my-rg", 123.45, "USD", "2026-03-01", "2026-03-07");
    assert!(out.contains("Cost Dashboard for 'my-rg':"));
    assert!(out.contains("$123.45 USD"));
    assert!(out.contains("2026-03-01 to 2026-03-07"));
}

#[test]
fn test_build_cost_management_scope() {
    let scope = build_cost_management_scope("sub-123", "my-rg");
    assert_eq!(scope, "/subscriptions/sub-123/resourceGroups/my-rg");
}

#[test]
fn test_build_budget_name() {
    assert_eq!(build_budget_name("my-rg"), "azlin-budget-my-rg");
}

#[test]
fn test_format_budget_created() {
    let msg = format_budget_created(100.0, "my-rg", 80);
    assert!(msg.contains("$100.00/month"));
    assert!(msg.contains("my-rg"));
    assert!(msg.contains("80%"));
}

#[test]
fn test_build_cost_history_dates() {
    let (start, end) = build_cost_history_dates(7);
    // Both should be valid date strings with T separator
    assert!(start.contains("T00:00:00"));
    assert!(end.contains("T23:59:59"));
}
