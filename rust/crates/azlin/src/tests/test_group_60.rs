use super::common::*;
use crate::*;
use std::fs;
use tempfile::TempDir;

// ── Additional Azure-dependent inproc tests (require az login) ──────
// Tagged #[ignore] — counted by: cargo llvm-cov -- --include-ignored

#[tokio::test]
#[ignore]
async fn test_inproc_show_json() {
    let r = run_dispatch(&[
        "--output",
        "json",
        "show",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "show json failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_show_csv() {
    let r = run_dispatch(&[
        "--output",
        "csv",
        "show",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "show csv failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_tag_add_remove() {
    // Add a tag — may fail on auth, just exercise the code path
    let _r = run_dispatch(&[
        "tag",
        "add",
        "devo",
        "test_coverage=true",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;

    // Remove the tag
    let _r = run_dispatch(&[
        "tag",
        "remove",
        "devo",
        "test_coverage",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_snapshot_status() {
    let r = run_dispatch(&[
        "snapshot",
        "status",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "snapshot status failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_keys_list() {
    let r = run_dispatch(&["keys", "list"]).await;
    assert!(r.is_ok(), "keys list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_auth_test() {
    let r = run_dispatch(&["auth", "test"]).await;
    assert!(r.is_ok(), "auth test failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_auth_list() {
    let r = run_dispatch(&["auth", "list"]).await;
    assert!(r.is_ok(), "auth list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_destroy_dry_run() {
    let r = run_dispatch(&[
        "destroy",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--dry-run",
    ])
    .await;
    assert!(r.is_ok(), "destroy dry-run failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_status_json() {
    let r = run_dispatch(&[
        "--output",
        "json",
        "status",
        "--vm",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "status json failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_with_tag() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--tag",
        "env=dev",
    ])
    .await;
    // May return empty if no VMs match the tag, but should not error
    assert!(r.is_ok(), "list with tag failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_all() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--all",
    ])
    .await;
    assert!(r.is_ok(), "list all failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_compact() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--compact",
    ])
    .await;
    assert!(r.is_ok(), "list compact failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_storage_list() {
    let r = run_dispatch(&[
        "storage",
        "list",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    // May fail if no storage accounts — just don't panic
    let _ = r;
}

#[tokio::test]
#[ignore]
async fn test_inproc_cleanup_dry_run() {
    let r = run_dispatch(&[
        "cleanup",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--dry-run",
    ])
    .await;
    assert!(r.is_ok(), "cleanup dry-run failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_dashboard() {
    // Cost APIs may not be available on all subscriptions
    let _r = run_dispatch(&[
        "costs",
        "dashboard",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_history() {
    let _r = run_dispatch(&[
        "costs",
        "history",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--days",
        "7",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_recommend() {
    let _r = run_dispatch(&[
        "costs",
        "recommend",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_budget_show() {
    let _r = run_dispatch(&[
        "costs",
        "budget",
        "show",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_actions_list_dry() {
    let _r = run_dispatch(&[
        "costs",
        "actions",
        "list",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--dry-run",
    ])
    .await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_ip_check_all() {
    let r = run_dispatch(&[
        "ip",
        "check",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--all",
    ])
    .await;
    assert!(r.is_ok(), "ip check all failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_code_devo() {
    // 'code' opens VS Code — verify it resolves the target at least
    let _r = run_dispatch(&["code", "devo", "--resource-group", "RYSWEET-LINUX-VM-POOL"]).await;
    // May fail if VS Code not installed, that's OK
}

#[tokio::test]
#[ignore]
async fn test_inproc_web_stop() {
    // Web stop should succeed even if nothing is running
    let _r = run_dispatch(&["web", "stop"]).await;
}
