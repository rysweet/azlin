use super::common::*;

// ── Live Azure in-process tests (for coverage) ──────────────────────
// These call dispatch_command directly so llvm-cov sees the code paths.
// Tagged #[ignore] — run with: cargo test -- --ignored

#[tokio::test]
#[ignore]
async fn test_inproc_list() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_wide() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--wide",
    ])
    .await;
    assert!(r.is_ok(), "list wide failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_json() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--output",
        "json",
    ])
    .await;
    assert!(r.is_ok(), "list json failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_list_csv() {
    let r = run_dispatch(&[
        "list",
        "--no-tmux",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
        "--output",
        "csv",
    ])
    .await;
    assert!(r.is_ok(), "list csv failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_show() {
    let r = run_dispatch(&["show", "devo", "--resource-group", "RYSWEET-LINUX-VM-POOL"]).await;
    assert!(r.is_ok(), "show failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_status() {
    let r = run_dispatch(&[
        "status",
        "--vm",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "status failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_health() {
    let r = run_dispatch(&[
        "health",
        "--vm",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "health failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_tag_list() {
    let r = run_dispatch(&[
        "tag",
        "list",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "tag list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_start() {
    let r = run_dispatch(&["start", "devo", "--resource-group", "RYSWEET-LINUX-VM-POOL"]).await;
    assert!(r.is_ok(), "start failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_config_show() {
    let r = run_dispatch(&["config", "show"]).await;
    assert!(r.is_ok(), "config show failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_version() {
    let r = run_dispatch(&["version"]).await;
    assert!(r.is_ok(), "version failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_context_list() {
    let r = run_dispatch(&["context", "list"]).await;
    assert!(r.is_ok(), "context list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_bastion_list() {
    let r = run_dispatch(&[
        "bastion",
        "list",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "bastion list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_snapshot_list() {
    let r = run_dispatch(&[
        "snapshot",
        "list",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "snapshot list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_ip_check() {
    let r = run_dispatch(&[
        "ip",
        "check",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "ip check failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_w() {
    let r = run_dispatch(&[
        "w",
        "--vm",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "w failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_ps() {
    let r = run_dispatch(&[
        "ps",
        "--vm",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "ps failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_env_list() {
    let r = run_dispatch(&[
        "env",
        "list",
        "devo",
        "--resource-group",
        "RYSWEET-LINUX-VM-POOL",
    ])
    .await;
    assert!(r.is_ok(), "env list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_cost() {
    // Cost may fail on subscription type — just verify it doesn't panic
    let _r = run_dispatch(&["cost", "--resource-group", "RYSWEET-LINUX-VM-POOL"]).await;
}
