use super::common::*;

#[tokio::test]
async fn test_dispatch_autopilot_full_lifecycle() {
    // Save any existing config
    let ap_path = dirs::home_dir()
        .unwrap()
        .join(".azlin")
        .join("autopilot.toml");
    let backup = std::fs::read_to_string(&ap_path).ok();

    // Status when not configured
    let _ = std::fs::remove_file(&ap_path);
    let r = run_dispatch(&["autopilot", "status"]).await;
    assert!(r.is_ok());

    // Config show when no file
    let r = run_dispatch(&["autopilot", "config", "--show"]).await;
    assert!(r.is_ok());

    // Config set when no file — creates new
    let r = run_dispatch(&["autopilot", "config", "--set", "test_key=test_val"]).await;
    assert!(r.is_ok());
    let _ = std::fs::remove_file(&ap_path);

    // Enable
    let r = run_dispatch(&[
        "autopilot",
        "enable",
        "--strategy",
        "aggressive",
        "--idle-threshold",
        "15",
        "--cpu-threshold",
        "5",
    ])
    .await;
    assert!(r.is_ok(), "autopilot enable failed: {:?}", r.err());

    // Status
    let r = run_dispatch(&["autopilot", "status"]).await;
    assert!(r.is_ok());

    // Config show
    let r = run_dispatch(&["autopilot", "config", "--show"]).await;
    assert!(r.is_ok());

    // Config set
    let r = run_dispatch(&["autopilot", "config", "--set", "max_vms=10"]).await;
    assert!(r.is_ok());

    // Disable (keep config)
    let r = run_dispatch(&["autopilot", "disable", "--keep-config"]).await;
    assert!(r.is_ok());

    // Status after disable
    let r = run_dispatch(&["autopilot", "status"]).await;
    assert!(r.is_ok());

    // Enable with budget
    let r = run_dispatch(&[
        "autopilot",
        "enable",
        "--budget",
        "100",
        "--strategy",
        "conservative",
    ])
    .await;
    assert!(r.is_ok());

    // Disable (remove config)
    let r = run_dispatch(&["autopilot", "disable"]).await;
    assert!(r.is_ok());

    // Restore original config
    if let Some(content) = backup {
        let _ = std::fs::write(&ap_path, content);
    }
}

#[tokio::test]
async fn test_dispatch_config_set_and_restore() {
    // Get current region
    use azlin_core::AzlinConfig;
    let orig = AzlinConfig::load().unwrap();
    let orig_region = orig.default_region.clone();

    // Set a different region
    let r = run_dispatch(&["config", "set", "default_region", "northeurope"]).await;
    assert!(r.is_ok(), "config set failed: {:?}", r.err());

    // Verify it was set
    let updated = AzlinConfig::load().unwrap();
    assert_eq!(updated.default_region, "northeurope");

    // Restore
    let r = run_dispatch(&["config", "set", "default_region", &orig_region]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_config_set_unknown_key() {
    let r = run_dispatch(&["config", "set", "nonexistent_key_xyz", "value"]).await;
    assert!(r.is_err());
}

#[tokio::test]
async fn test_dispatch_session_set_get_clear() {
    // Set session for a VM
    let r = run_dispatch(&["session", "test-vm-cov", "my-session"]).await;
    assert!(r.is_ok(), "session set failed: {:?}", r.err());

    // Get session
    let r = run_dispatch(&["session", "test-vm-cov"]).await;
    assert!(r.is_ok(), "session get failed: {:?}", r.err());

    // Clear session
    let r = run_dispatch(&["session", "test-vm-cov", "--clear"]).await;
    assert!(r.is_ok(), "session clear failed: {:?}", r.err());

    // Get again (should say no session)
    let r = run_dispatch(&["session", "test-vm-cov"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_template_list_json() {
    let r = run_dispatch(&["--output", "json", "template", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_template_list_csv() {
    let r = run_dispatch(&["--output", "csv", "template", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_sessions_list_json() {
    let r = run_dispatch(&["--output", "json", "sessions", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_context_list_json() {
    let r = run_dispatch(&["--output", "json", "context", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_verbose_version() {
    let r = run_dispatch(&["--verbose", "version"]).await;
    assert!(r.is_ok());
}
