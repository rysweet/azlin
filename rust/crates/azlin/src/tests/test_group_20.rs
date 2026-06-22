use super::common::*;

// ── Env subcommands ─────────────────────────────────────────────

#[test]
fn test_env_set_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "set", "test-vm", "MY_KEY=my_value"]);
}

#[test]
fn test_env_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "list", "test-vm"]);
}

#[test]
fn test_env_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "delete", "test-vm", "MY_KEY"]);
}

#[test]
fn test_env_export_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "export", "test-vm"]);
}

#[test]
fn test_env_import_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "import", "test-vm", "/dev/null"]);
}

#[test]
fn test_env_clear_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "clear", "test-vm", "--force"]);
}

// ── Compose subcommands ─────────────────────────────────────────

#[test]
fn test_compose_ps_graceful_error_no_auth() {
    assert_graceful_auth_error(&["compose", "ps"]);
}

// ── Sessions subcommands ────────────────────────────────────────

#[test]
fn test_sessions_save_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sessions", "save", "test-session"]);
}

#[test]
fn test_sessions_load_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sessions", "load", "nonexistent-session"]);
}

#[test]
fn test_sessions_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sessions", "delete", "nonexistent-session", "--force"]);
}

// ── GitHub Runner subcommands ───────────────────────────────────

#[test]
fn test_github_runner_enable_graceful_error_no_auth() {
    assert_graceful_auth_error(&[
        "github-runner",
        "enable",
        "--pool",
        "test-pool",
        "--count",
        "1",
    ]);
}

// Note: github-runner disable/status/scale are local filesystem operations
// that don't call Azure auth, so they don't use the auth-error pattern.

// ── Template subcommands ────────────────────────────────────────

// Note: template create/save are local filesystem operations that
// don't call Azure auth, so they don't use the auth-error pattern.

#[test]
fn test_template_apply_graceful_error_no_auth() {
    assert_graceful_auth_error(&["template", "apply", "nonexistent-template"]);
}

#[test]
fn test_template_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["template", "delete", "nonexistent-template", "--force"]);
}

// ── Web subcommands ─────────────────────────────────────────────

#[test]
fn test_web_start_graceful_error_no_auth() {
    assert_graceful_auth_error(&["web", "start"]);
}

// Note: web stop is a local PID-file operation that doesn't call
// Azure auth, so it doesn't use the auth-error pattern.

// ── Storage mount/unmount ───────────────────────────────────────

#[test]
fn test_storage_mount_graceful_error_no_auth() {
    assert_graceful_auth_error(&[
        "storage",
        "mount",
        "--storage-name",
        "teststorage",
        "--vm",
        "test-vm",
    ]);
}

#[test]
fn test_storage_unmount_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "unmount", "--vm", "test-vm"]);
}

// ── IP subcommands ──────────────────────────────────────────────

#[test]
fn test_ip_check_graceful_error_no_auth() {
    assert_graceful_auth_error(&["ip", "check", "test-vm"]);
}

// ── Disk subcommands ────────────────────────────────────────────

#[test]
fn test_disk_add_graceful_error_no_auth() {
    assert_graceful_auth_error(&["disk", "add", "test-vm"]);
}

// ── Do (natural language) ───────────────────────────────────────

#[test]
fn test_do_graceful_error_no_auth() {
    assert_graceful_auth_error(&["do", "list all vms"]);
}

// ── Health / w / ps / logs ──────────────────────────────────────

#[test]
fn test_health_graceful_error_no_auth() {
    assert_graceful_auth_error(&["health"]);
}

#[test]
fn test_w_graceful_error_no_auth() {
    assert_graceful_auth_error(&["w", "--vm", "test-vm"]);
}

#[test]
fn test_ps_graceful_error_no_auth() {
    assert_graceful_auth_error(&["ps", "--vm", "test-vm"]);
}

#[test]
fn test_logs_graceful_error_no_auth() {
    assert_graceful_auth_error(&["logs", "test-vm"]);
}

// ── cp / sync / sync-keys ───────────────────────────────────────

#[test]
fn test_cp_graceful_error_no_auth() {
    assert_graceful_auth_error(&["cp", "test-vm:/tmp/file", "/tmp/local"]);
}

#[test]
fn test_sync_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sync"]);
}

#[test]
fn test_sync_keys_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sync-keys", "test-vm"]);
}

// ── Costs subcommands ───────────────────────────────────────────

#[test]
fn test_costs_dashboard_graceful_error_no_auth() {
    assert_graceful_auth_error(&["costs", "dashboard", "--resource-group", "test-rg"]);
}

#[test]
fn test_costs_history_graceful_error_no_auth() {
    assert_graceful_auth_error(&["costs", "history", "--resource-group", "test-rg"]);
}

#[test]
fn test_costs_budget_graceful_error_no_auth() {
    assert_graceful_auth_error(&[
        "costs",
        "budget",
        "--resource-group",
        "test-rg",
        "--action",
        "show",
    ]);
}

#[test]
fn test_costs_recommend_graceful_error_no_auth() {
    assert_graceful_auth_error(&["costs", "recommend", "--resource-group", "test-rg"]);
}
