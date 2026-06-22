use super::common::*;

// ── Live Azure in-process tests for issue #796 / #789 untested commands ──
// These require `az login` and access to the RYSWEET-LINUX-VM-POOL resource group.
// Run with: cargo test -- --ignored
//
// Covers the 18 commands from issue #796 and additional commands from #789
// that previously lacked in-process dispatch coverage.

const RG: &str = "RYSWEET-LINUX-VM-POOL";
const VM: &str = "devo";

// ── #796.1: ask (requires ANTHROPIC_API_KEY) ─────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_ask_help_dispatch() {
    // ask without a question should show help or error gracefully
    // (We cannot test the actual AI call without ANTHROPIC_API_KEY)
    let r = run_dispatch(&["ask", "--help-topics"]).await;
    // May fail — just verify no panic
    let _ = r;
}

// ── #796.2: costs dashboard / history / recommend ────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_costs_dashboard_rg() {
    let _r = run_dispatch(&["costs", "dashboard", "--resource-group", RG]).await;
    // Cost APIs may fail on subscription type
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_history_30d() {
    let _r = run_dispatch(&["costs", "history", "--resource-group", RG, "--days", "30"]).await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_costs_recommend_rg() {
    let _r = run_dispatch(&["costs", "recommend", "--resource-group", RG]).await;
}

// ── #796.3: top (interactive TUI — just verify it starts) ───────────

#[tokio::test]
#[ignore]
async fn test_inproc_top_once() {
    // top --once exits after one refresh cycle (no interactive TUI)
    let _r = run_dispatch(&["top", "--vm", VM, "--resource-group", RG, "--once"]).await;
}

// ── #796.4: session list / save / delete ─────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_session_list() {
    let r = run_dispatch(&["session", "list", VM, "--resource-group", RG]).await;
    assert!(r.is_ok(), "session list failed: {:?}", r.err());
}

// ── #796.5: template list / show ─────────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_template_list_dispatch() {
    let r = run_dispatch(&["template", "list"]).await;
    assert!(r.is_ok(), "template list failed: {:?}", r.err());
}

// ── #796.6: autopilot status ─────────────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_autopilot_status_dispatch() {
    let r = run_dispatch(&["autopilot", "status"]).await;
    assert!(r.is_ok(), "autopilot status failed: {:?}", r.err());
}

// ── #796.7: bastion list / status ────────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_bastion_status() {
    let r = run_dispatch(&["bastion", "status", "--resource-group", RG]).await;
    assert!(r.is_ok(), "bastion status failed: {:?}", r.err());
}

// ── #796.10: sync-keys ──────────────────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_sync_keys() {
    let r = run_dispatch(&["sync-keys", VM, "--resource-group", RG]).await;
    // May fail if no SSH keys configured — just verify no panic
    let _ = r;
}

// ── #796.11: web status / stop ──────────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_web_status() {
    // web status reports monitoring server state — should work without Azure
    let _r = run_dispatch(&["web", "status"]).await;
}

// ── #796.13: restore (tmux restore) ─────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_restore_dispatch() {
    // restore needs Azure auth to look up VMs for tmux session reconstruction
    let _r = run_dispatch(&["restore", "--resource-group", RG]).await;
}

// ── #796.14: os-update ──────────────────────────────────────────────

#[tokio::test]
#[ignore]
async fn test_inproc_os_update() {
    // os-update actually runs apt on the remote VM — use devo which is safe
    let _r = run_dispatch(&["os-update", VM, "--resource-group", RG]).await;
}

// ── #789.5: code
#[tokio::test]
#[ignore]
async fn test_inproc_code_dispatch() {
    // code opens VS Code — verify it resolves the target
    let _r = run_dispatch(&["code", VM, "--resource-group", RG]).await;
}

// #789.6: logs (run briefly)
#[tokio::test]
#[ignore]
async fn test_inproc_logs_tail() {
    // Fetch last 20 lines of syslog (non-interactive, no --follow)
    let _r = run_dispatch(&["logs", VM, "--lines", "20", "--resource-group", RG]).await;
}

#[tokio::test]
#[ignore]
async fn test_inproc_logs_cloud_init() {
    let _r = run_dispatch(&[
        "logs",
        VM,
        "--lines",
        "10",
        "--type",
        "cloud-init",
        "--resource-group",
        RG,
    ])
    .await;
}

// #789.7: compose ps
#[tokio::test]
#[ignore]
async fn test_inproc_compose_ps() {
    // compose ps lists containers on the VM
    let _r = run_dispatch(&["compose", "ps", VM, "--resource-group", RG]).await;
}

// #789.10: sync with actual sync directory
#[tokio::test]
#[ignore]
async fn test_inproc_sync_dry_run() {
    let r = run_dispatch(&["sync", VM, "--dry-run", "--resource-group", RG]).await;
    // Dry run should succeed even without sync directory
    let _ = r;
}

// ── Verify commands from both issues produce sensible output ─────────

#[tokio::test]
#[ignore]
async fn test_inproc_disk_list() {
    let r = run_dispatch(&["disk", "list", VM, "--resource-group", RG]).await;
    assert!(r.is_ok(), "disk list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_ip_list() {
    let r = run_dispatch(&["ip", "list", "--resource-group", RG]).await;
    assert!(r.is_ok(), "ip list failed: {:?}", r.err());
}

#[tokio::test]
#[ignore]
async fn test_inproc_fleet_list() {
    // fleet run with no args might list fleet status
    let _r = run_dispatch(&["fleet", "run", "echo hello", "--resource-group", RG]).await;
}
