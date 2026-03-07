use super::super::*;
use super::common::*;
use azlin_azure::AzureOps;
use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
use std::collections::HashMap;

// ── Cleanup / orphan classification tests ───────────────────────

#[test]
fn test_classify_orphaned_nics_finds_unattached() {
    let nics = vec![
        serde_json::json!({"name": "nic-orphan", "resourceGroup": "rg1", "virtualMachine": null}),
        serde_json::json!({"name": "nic-attached", "resourceGroup": "rg1", "virtualMachine": {"id": "/sub/vm"}}),
    ];
    let orphans = classify_orphaned_nics(&nics);
    assert_eq!(orphans.len(), 1);
    assert_eq!(orphans[0].name, "nic-orphan");
    assert_eq!(orphans[0].resource_type, "NIC");
}

#[test]
fn test_classify_orphaned_nics_empty() {
    assert!(classify_orphaned_nics(&[]).is_empty());
}

#[test]
fn test_classify_orphaned_ips_finds_unattached() {
    let ips = vec![
        serde_json::json!({"name": "ip-orphan", "resourceGroup": "rg1", "ipConfiguration": null}),
        serde_json::json!({"name": "ip-attached", "resourceGroup": "rg1", "ipConfiguration": {"id": "/sub/nic"}}),
    ];
    let orphans = classify_orphaned_ips(&ips, 3.65);
    assert_eq!(orphans.len(), 1);
    assert_eq!(orphans[0].name, "ip-orphan");
    assert_eq!(orphans[0].resource_type, "Public IP");
    assert!((orphans[0].estimated_monthly_cost - 3.65).abs() < 0.01);
}

#[test]
fn test_classify_orphaned_ips_empty() {
    assert!(classify_orphaned_ips(&[], 3.65).is_empty());
}

#[test]
fn test_classify_orphaned_nsgs_finds_unattached() {
    let nsgs = vec![
        serde_json::json!({"name": "nsg-orphan", "resourceGroup": "rg1", "networkInterfaces": [], "subnets": []}),
        serde_json::json!({"name": "nsg-used", "resourceGroup": "rg1", "networkInterfaces": [{"id": "/sub/nic"}], "subnets": []}),
    ];
    let orphans = classify_orphaned_nsgs(&nsgs);
    assert_eq!(orphans.len(), 1);
    assert_eq!(orphans[0].name, "nsg-orphan");
    assert_eq!(orphans[0].resource_type, "NSG");
}

#[test]
fn test_classify_orphaned_nsgs_with_subnets() {
    let nsgs = vec![
        serde_json::json!({"name": "nsg-subnet", "resourceGroup": "rg1", "networkInterfaces": [], "subnets": [{"id": "/sub/subnet"}]}),
    ];
    let orphans = classify_orphaned_nsgs(&nsgs);
    assert!(orphans.is_empty());
}

#[test]
fn test_build_cleanup_plan_dry_run() {
    let resources = vec![OrphanedResourceInfo {
        name: "nic-1".to_string(),
        resource_type: "NIC".to_string(),
        resource_group: "rg1".to_string(),
        estimated_monthly_cost: 0.0,
    }];
    let plan = build_cleanup_plan(&resources, true);
    assert_eq!(plan.len(), 1);
    assert_eq!(plan[0].action, "would delete");
    assert_eq!(plan[0].resource_name, "nic-1");
}

#[test]
fn test_build_cleanup_plan_real() {
    let resources = vec![
        OrphanedResourceInfo {
            name: "disk-1".to_string(),
            resource_type: "Disk".to_string(),
            resource_group: "rg1".to_string(),
            estimated_monthly_cost: 5.12,
        },
        OrphanedResourceInfo {
            name: "ip-1".to_string(),
            resource_type: "Public IP".to_string(),
            resource_group: "rg1".to_string(),
            estimated_monthly_cost: 3.65,
        },
    ];
    let plan = build_cleanup_plan(&resources, false);
    assert_eq!(plan.len(), 2);
    assert_eq!(plan[0].action, "delete");
    assert_eq!(plan[1].action, "delete");
}

#[test]
fn test_format_orphan_report_empty() {
    let out = format_orphan_report(&[]);
    assert!(out.contains("No orphaned resources found"));
}

#[test]
fn test_format_orphan_report_with_resources() {
    let resources = vec![
        OrphanedResourceInfo {
            name: "disk-old".to_string(),
            resource_type: "Disk".to_string(),
            resource_group: "rg1".to_string(),
            estimated_monthly_cost: 5.12,
        },
        OrphanedResourceInfo {
            name: "ip-old".to_string(),
            resource_type: "Public IP".to_string(),
            resource_group: "rg1".to_string(),
            estimated_monthly_cost: 3.65,
        },
    ];
    let out = format_orphan_report(&resources);
    assert!(out.contains("2 orphaned resource(s)"));
    assert!(out.contains("disk-old"));
    assert!(out.contains("ip-old"));
    assert!(out.contains("$8.77/month"));
}

// ── Snapshot handler tests ──────────────────────────────────────────

#[test]
fn test_build_snapshot_enable_output() {
    let out = build_snapshot_enable_output("dev-vm-1", "test-rg", 6, 3);
    assert!(out.contains("dev-vm-1"));
    assert!(out.contains("every 6h"));
    assert!(out.contains("keep 3"));
}

#[test]
fn test_build_snapshot_disable_output_had_schedule() {
    let out = build_snapshot_disable_output("dev-vm-1", true);
    assert!(out.contains("disabled"));
    assert!(out.contains("dev-vm-1"));
}

#[test]
fn test_build_snapshot_disable_output_no_schedule() {
    let out = build_snapshot_disable_output("dev-vm-1", false);
    assert!(out.contains("No schedule configured"));
}

#[test]
fn test_check_snapshot_sync_needed_recent() {
    let now = chrono::Utc::now();
    let recent = now - chrono::Duration::hours(2);
    let snap = serde_json::json!({
        "timeCreated": recent.to_rfc3339(),
    });
    let snaps = vec![&snap];
    let (needs, msg) = check_snapshot_sync_needed(&snaps, "vm1", 6, now);
    assert!(!needs);
    assert!(msg.unwrap().contains("skipping"));
}

#[test]
fn test_check_snapshot_sync_needed_old() {
    let now = chrono::Utc::now();
    let old = now - chrono::Duration::hours(12);
    let snap = serde_json::json!({
        "timeCreated": old.to_rfc3339(),
    });
    let snaps = vec![&snap];
    let (needs, msg) = check_snapshot_sync_needed(&snaps, "vm1", 6, now);
    assert!(needs);
    assert!(msg.is_none());
}

#[test]
fn test_check_snapshot_sync_needed_empty() {
    let now = chrono::Utc::now();
    let empty: Vec<&serde_json::Value> = vec![];
    let (needs, msg) = check_snapshot_sync_needed(&empty, "vm1", 6, now);
    assert!(needs);
    assert!(msg.is_none());
}

#[test]
fn test_format_snapshot_sync_complete_single() {
    let out = format_snapshot_sync_complete(Some("vm1"));
    assert!(out.contains("vm1"));
}

#[test]
fn test_format_snapshot_sync_complete_all() {
    let out = format_snapshot_sync_complete(None);
    assert!(out.contains("all VMs"));
}

// ── Storage handler tests ───────────────────────────────────────────

#[test]
fn test_format_storage_created() {
    let out = format_storage_created("mystorage", 100, "premium");
    assert!(out.contains("mystorage"));
    assert!(out.contains("100 GB"));
    assert!(out.contains("premium"));
}

#[test]
fn test_format_storage_deleted() {
    let out = format_storage_deleted("mystorage");
    assert!(out.contains("Deleted"));
    assert!(out.contains("mystorage"));
}

#[test]
fn test_format_storage_mounted() {
    let out = format_storage_mounted("share1", "vm1", "/mnt/share1");
    assert!(out.contains("share1"));
    assert!(out.contains("vm1"));
    assert!(out.contains("/mnt/share1"));
}

#[test]
fn test_validate_storage_name_valid() {
    assert!(validate_storage_name("my-storage-1").is_ok());
}

#[test]
fn test_validate_storage_name_invalid() {
    assert!(validate_storage_name("my_storage!").is_err());
}

#[test]
fn test_default_nfs_mount_point() {
    assert_eq!(default_nfs_mount_point("share1"), "/mnt/share1");
}
