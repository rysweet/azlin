use super::common::*;

// ── Non-auth dispatch tests (no Azure required) ────────────────────
// These test dispatch_command branches that operate locally (filesystem, config,
// pure output). NOT #[ignore] so they run in every `cargo test`.

#[tokio::test]
async fn test_dispatch_version() {
    let r = run_dispatch(&["version"]).await;
    assert!(r.is_ok(), "version dispatch failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_config_show() {
    let r = run_dispatch(&["config", "show"]).await;
    assert!(r.is_ok(), "config show dispatch failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_config_get_default_region() {
    let r = run_dispatch(&["config", "get", "default_region"]).await;
    assert!(r.is_ok(), "config get dispatch failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_config_get_unknown_key() {
    // Unknown key prints to stderr but does not error
    let r = run_dispatch(&["config", "get", "nonexistent_key_xyz"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_completions_bash() {
    let r = run_dispatch(&["completions", "bash"]).await;
    assert!(r.is_ok(), "completions bash failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_completions_zsh() {
    let r = run_dispatch(&["completions", "zsh"]).await;
    assert!(r.is_ok(), "completions zsh failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_completions_fish() {
    let r = run_dispatch(&["completions", "fish"]).await;
    assert!(r.is_ok(), "completions fish failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_azlin_help_no_command() {
    let r = run_dispatch(&["azlin-help"]).await;
    assert!(r.is_ok(), "azlin-help dispatch failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_azlin_help_with_command() {
    let r = run_dispatch(&["azlin-help", "list"]).await;
    assert!(r.is_ok(), "azlin-help list failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_azlin_help_connect() {
    let r = run_dispatch(&["azlin-help", "connect"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_azlin_help_unknown() {
    let r = run_dispatch(&["azlin-help", "nonexistent"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_template_list() {
    let r = run_dispatch(&["template", "list"]).await;
    assert!(r.is_ok(), "template list failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_template_create_show_delete() {
    // Create
    let r = run_dispatch(&[
        "template",
        "create",
        "test-coverage-tpl",
        "--vm-size",
        "Standard_D2s_v3",
        "--region",
        "eastus",
        "--description",
        "Coverage test template",
    ])
    .await;
    assert!(r.is_ok(), "template create failed: {:?}", r.err());

    // Show
    let r = run_dispatch(&["template", "show", "test-coverage-tpl"]).await;
    assert!(r.is_ok(), "template show failed: {:?}", r.err());

    // Apply
    let r = run_dispatch(&["template", "apply", "test-coverage-tpl"]).await;
    assert!(r.is_ok(), "template apply failed: {:?}", r.err());

    // Delete with --force
    let r = run_dispatch(&["template", "delete", "test-coverage-tpl", "--force"]).await;
    assert!(r.is_ok(), "template delete failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_template_show_not_found() {
    let r = run_dispatch(&["template", "show", "nonexistent-template-xyz"]).await;
    assert!(r.is_err());
}

#[tokio::test]
async fn test_dispatch_template_apply_not_found() {
    let r = run_dispatch(&["template", "apply", "nonexistent-template-xyz"]).await;
    assert!(r.is_err());
}

#[tokio::test]
async fn test_dispatch_template_export_import() {
    // Create a template first
    let r = run_dispatch(&[
        "template",
        "create",
        "test-export-tpl",
        "--vm-size",
        "Standard_B2s",
    ])
    .await;
    assert!(r.is_ok());

    // Export
    let export_path = "/tmp/azlin-test-template-export.toml";
    let r = run_dispatch(&["template", "export", "test-export-tpl", export_path]).await;
    assert!(r.is_ok(), "template export failed: {:?}", r.err());
    assert!(std::path::Path::new(export_path).exists());

    // Import
    let r = run_dispatch(&["template", "import", export_path]).await;
    assert!(r.is_ok(), "template import failed: {:?}", r.err());

    // Cleanup
    let _ = std::fs::remove_file(export_path);
    let _ = run_dispatch(&["template", "delete", "test-export-tpl", "--force"]).await;
}

#[tokio::test]
async fn test_dispatch_context_list() {
    let r = run_dispatch(&["context", "list"]).await;
    assert!(r.is_ok(), "context list failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_context_show() {
    let r = run_dispatch(&["context", "show"]).await;
    // May say "No context selected" which is fine
    assert!(r.is_ok());
}

/// Context CRUD through the real binary, isolated to a temp state directory.
///
/// This ran in-process against the developer's real `~/.azlin` before #1090.
/// That was already the #1079 hazard, and became sharper once `context use`
/// started calling `az account set`: an in-process run would have repointed the
/// developer's actual Azure CLI. A subprocess with `AZLIN_CONFIG_DIR` set
/// cannot.
///
/// `use` is deliberately exercised on a context that pins no subscription, so
/// the step is deterministic without Azure. The subscription-pinned path is
/// covered by `tests::test_context_switch`.
#[test]
fn test_context_create_use_rename_delete_isolated() {
    let dir = tempfile::TempDir::new().unwrap();

    let out = run_isolated(
        &dir,
        &[
            "context",
            "create",
            "test-cov-ctx",
            "--resource-group",
            "test-rg",
            "--region",
            "westus2",
        ],
    );
    assert_isolated_ok(&out, "context create");

    let out = run_isolated(&dir, &["context", "use", "test-cov-ctx"]);
    assert_isolated_ok(&out, "context use");
    assert_eq!(
        std::fs::read_to_string(dir.path().join("active-context"))
            .unwrap()
            .trim(),
        "test-cov-ctx"
    );

    let out = run_isolated(
        &dir,
        &["context", "rename", "test-cov-ctx", "test-cov-ctx-renamed"],
    );
    assert_isolated_ok(&out, "context rename");

    let out = run_isolated(&dir, &["context", "show"]);
    assert_isolated_ok(&out, "context show");
    assert!(String::from_utf8_lossy(&out.stdout).contains("test-cov-ctx-renamed"));

    let out = run_isolated(
        &dir,
        &["context", "delete", "test-cov-ctx-renamed", "--force"],
    );
    assert_isolated_ok(&out, "context delete");
}

#[tokio::test]
async fn test_dispatch_context_use_not_found() {
    let r = run_dispatch(&["context", "use", "nonexistent-context-xyz"]).await;
    assert!(r.is_err());
}

#[tokio::test]
async fn test_dispatch_context_create_invalid_name() {
    let r = run_dispatch(&["context", "create", "../traversal"]).await;
    assert!(r.is_err());
}

#[tokio::test]
async fn test_dispatch_sessions_list() {
    let r = run_dispatch(&["sessions", "list"]).await;
    assert!(r.is_ok(), "sessions list failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_sessions_save_load_delete() {
    // Save — requires resource-group, provide it explicitly
    let r = run_dispatch(&[
        "sessions",
        "save",
        "test-cov-session",
        "--resource-group",
        "test-rg",
        "--vms",
        "vm1",
        "vm2",
    ])
    .await;
    assert!(r.is_ok(), "sessions save failed: {:?}", r.err());

    // Load
    let r = run_dispatch(&["sessions", "load", "test-cov-session"]).await;
    assert!(r.is_ok(), "sessions load failed: {:?}", r.err());

    // Delete
    let r = run_dispatch(&["sessions", "delete", "test-cov-session", "--force"]).await;
    assert!(r.is_ok(), "sessions delete failed: {:?}", r.err());
}

#[tokio::test]
async fn test_dispatch_sessions_load_not_found() {
    let r = run_dispatch(&["sessions", "load", "nonexistent-session-xyz"]).await;
    assert!(r.is_err());
}
