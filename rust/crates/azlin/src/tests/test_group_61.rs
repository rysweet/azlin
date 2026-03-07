use super::common::*;
use crate::*;
use std::fs;
use tempfile::TempDir;

#[tokio::test]
#[ignore]
async fn test_inproc_batch_start() {
    // Batch start with a tag filter that matches nothing — should succeed
    let _r = run_dispatch(&[
        "batch",
        "start",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_snapshot_enable_disable() {
    // Enable snapshot schedule
    let r = run_dispatch(&[
        "snapshot",
        "enable",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--every",
        "24",
        "--keep",
        "3",
    ])
    .await;
    assert!(r.is_ok(), "snapshot enable failed: {:?}", r.err());

    // Check status
    let r = run_dispatch(&[
        "snapshot",
        "status",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok());

    // Disable
    let r = run_dispatch(&[
        "snapshot",
        "disable",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "snapshot disable failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_contexts() {
    let r = run_dispatch(&["list", "--no-tmux", "--all-contexts"]).await;
    // May fail if no contexts configured, but should not panic
    let _ = r;
}

#[tokio::test]
#[ignore]
async fn test_inproc_env_set() {
    let _r = run_dispatch(&[
        "env",
        "set",
        "devo",
        "AZLIN_TEST_COV=true",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_show_dev() {
    let r = run_dispatch(&["show", "dev", "--resource-group", "RYSWEET-LINUX-VM-POOL"]).await;
    assert!(r.is_ok(), "show dev failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_status_all() {
    let r = run_dispatch(&["status", "--resource-group", "RYSWEET-LINUX-VM-POOL"]).await;
    assert!(r.is_ok(), "status all failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_restore() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--restore",
    ])
    .await;
    assert!(r.is_ok(), "list restore failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_snapshot_list_json() {
    let r = run_dispatch(&[
        "--output",
        "json",
        "snapshot",
        "list",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "snapshot list json failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_tag_list_json() {
    let r = run_dispatch(&[
        "--output",
        "json",
        "tag",
        "list",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "tag list json failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_with_health() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--with-health",
    ])
    .await;
    assert!(r.is_ok(), "list with-health failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_quota() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--quota",
    ])
    .await;
    assert!(r.is_ok(), "list quota failed: {:?}", r.err());
}
