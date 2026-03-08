#[allow(unused_imports)]
use crate::*;
use std::fs;
use tempfile::TempDir;

// ── Context CRUD lifecycle ──────────────────────────────────────

#[test]
fn test_context_full_crud_lifecycle() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path();

    // Create
    let toml_str = crate::contexts::build_context_toml(
        "myctx",
        Some("sub-123"),
        Some("tenant-456"),
        Some("myrg"),
        Some("eastus"),
        None,
    )
    .unwrap();
    fs::write(ctx_dir.join("myctx.toml"), &toml_str).unwrap();

    // List
    let contexts = crate::contexts::list_contexts(ctx_dir, "myctx").unwrap();
    assert_eq!(contexts.len(), 1);
    assert_eq!(contexts[0].0, "myctx");
    assert!(contexts[0].1); // is_active

    // Show (read resource group)
    let (name, rg) =
        crate::contexts::read_context_resource_group(&ctx_dir.join("myctx.toml")).unwrap();
    assert_eq!(name, "myctx");
    assert_eq!(rg, Some("myrg".to_string()));

    // Delete
    fs::remove_file(ctx_dir.join("myctx.toml")).unwrap();
    let contexts = crate::contexts::list_contexts(ctx_dir, "myctx").unwrap();
    assert!(contexts.is_empty());
}

#[test]
fn test_context_list_multiple_with_active() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path();

    for name in &["alpha", "beta", "gamma"] {
        let toml_str =
            crate::contexts::build_context_toml(name, None, None, Some("rg-1"), None, None)
                .unwrap();
        fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
    }

    let contexts = crate::contexts::list_contexts(ctx_dir, "beta").unwrap();
    assert_eq!(contexts.len(), 3);
    let active_count = contexts.iter().filter(|(_, a)| *a).count();
    assert_eq!(active_count, 1);
    let beta = contexts.iter().find(|(n, _)| n == "beta").unwrap();
    assert!(beta.1);
}

#[test]
fn test_context_rename_success_with_verify() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path();

    let toml_str =
        crate::contexts::build_context_toml("old-ctx", None, None, Some("myrg"), None, None)
            .unwrap();
    fs::write(ctx_dir.join("old-ctx.toml"), &toml_str).unwrap();

    crate::contexts::rename_context_file(ctx_dir, "old-ctx", "new-ctx").unwrap();

    assert!(!ctx_dir.join("old-ctx.toml").exists());
    assert!(ctx_dir.join("new-ctx.toml").exists());

    let (name, _) =
        crate::contexts::read_context_resource_group(&ctx_dir.join("new-ctx.toml")).unwrap();
    assert_eq!(name, "new-ctx");
}

#[test]
fn test_context_build_all_optional_fields() {
    let toml_str = crate::contexts::build_context_toml(
        "full-ctx",
        Some("sub-id"),
        Some("tenant-id"),
        Some("my-rg"),
        Some("westus2"),
        Some("my-vault"),
    )
    .unwrap();
    assert!(toml_str.contains("subscription_id"));
    assert!(toml_str.contains("tenant_id"));
    assert!(toml_str.contains("resource_group"));
    assert!(toml_str.contains("region"));
    assert!(toml_str.contains("key_vault_name"));
    assert!(toml_str.contains("full-ctx"));
}

// ── Session management lifecycle ────────────────────────────────

#[test]
fn test_session_full_lifecycle_save_list_load_delete() {
    let tmp = TempDir::new().unwrap();
    let sessions_dir = tmp.path();

    // Save
    let session = crate::sessions::build_session_toml(
        "test-session",
        "my-rg",
        &["vm1".to_string(), "vm2".to_string()],
    );
    let content = toml::to_string_pretty(&session).unwrap();
    fs::write(sessions_dir.join("test-session.toml"), &content).unwrap();

    // List
    let names = crate::sessions::list_session_names(sessions_dir).unwrap();
    assert_eq!(names.len(), 1);
    assert_eq!(names[0], "test-session");

    // Load — parse_session_toml returns (rg, vms, created)
    let loaded_content = fs::read_to_string(sessions_dir.join("test-session.toml")).unwrap();
    let (rg, vms, _created) = crate::sessions::parse_session_toml(&loaded_content).unwrap();
    assert_eq!(rg, "my-rg");
    assert_eq!(vms, vec!["vm1".to_string(), "vm2".to_string()]);

    // Delete
    fs::remove_file(sessions_dir.join("test-session.toml")).unwrap();
    let names = crate::sessions::list_session_names(sessions_dir).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_session_save_empty_vms_lifecycle() {
    let session = crate::sessions::build_session_toml("empty-sess", "rg", &[]);
    let content = toml::to_string_pretty(&session).unwrap();
    let (rg, vms, _created) = crate::sessions::parse_session_toml(&content).unwrap();
    assert_eq!(rg, "rg");
    assert!(vms.is_empty());
}

#[test]
fn test_session_list_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let missing = tmp.path().join("no-such-dir");
    let names = crate::sessions::list_session_names(&missing).unwrap();
    assert!(names.is_empty());
}

// ── Template lifecycle ──────────────────────────────────────────

#[test]
fn test_template_save_load_roundtrip_all_fields() {
    let tmp = TempDir::new().unwrap();
    let tpl = crate::templates::build_template_toml(
        "gpu-box",
        Some("GPU development template"),
        Some("Standard_NC6s_v3"),
        Some("eastus2"),
        Some("#!/bin/bash\napt-get install -y cuda"),
    );
    crate::templates::save_template(tmp.path(), "gpu-box", &tpl).unwrap();

    let loaded = crate::templates::load_template(tmp.path(), "gpu-box").unwrap();
    assert_eq!(loaded["name"].as_str(), Some("gpu-box"));
    assert_eq!(loaded["vm_size"].as_str(), Some("Standard_NC6s_v3"));
    assert_eq!(loaded["region"].as_str(), Some("eastus2"));
    assert!(loaded["cloud_init"].as_str().unwrap().contains("cuda"));
}

#[test]
fn test_template_list_multiple() {
    let tmp = TempDir::new().unwrap();
    for name in &["dev", "prod", "test"] {
        let tpl = crate::templates::build_template_toml(name, None, None, None, None);
        crate::templates::save_template(tmp.path(), name, &tpl).unwrap();
    }

    let list = crate::templates::list_templates(tmp.path()).unwrap();
    assert_eq!(list.len(), 3);
}

#[test]
fn test_template_load_nonexistent_errors() {
    let tmp = TempDir::new().unwrap();
    let result = crate::templates::load_template(tmp.path(), "nope");
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("not found"));
}

#[test]
fn test_template_delete_then_verify_gone() {
    let tmp = TempDir::new().unwrap();
    let tpl = crate::templates::build_template_toml("deleteme", None, None, None, None);
    crate::templates::save_template(tmp.path(), "deleteme", &tpl).unwrap();
    assert!(tmp.path().join("deleteme.toml").exists());

    crate::templates::delete_template(tmp.path(), "deleteme").unwrap();
    assert!(!tmp.path().join("deleteme.toml").exists());
}

#[test]
fn test_template_import_with_extra_fields() {
    let tmp = TempDir::new().unwrap();
    let content = r#"
name = "custom"
vm_size = "Standard_B1s"
region = "northeurope"
custom_field = "extra"
"#;
    let name = crate::templates::import_template(tmp.path(), content).unwrap();
    assert_eq!(name, "custom");
    let loaded = crate::templates::load_template(tmp.path(), "custom").unwrap();
    assert_eq!(loaded["custom_field"].as_str(), Some("extra"));
}

// ── Autopilot config tests ──────────────────────────────────────

#[test]
fn test_autopilot_config_all_fields() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        Some(500),
        "aggressive",
        15,
        10,
        "2024-01-15T10:00:00Z",
    );
    let table = config.as_table().unwrap();
    assert_eq!(table["enabled"].as_bool(), Some(true));
    assert_eq!(table["budget"].as_integer(), Some(500));
    assert_eq!(table["strategy"].as_str(), Some("aggressive"));
    assert_eq!(table["idle_threshold_minutes"].as_integer(), Some(15));
    assert_eq!(table["cpu_threshold_percent"].as_integer(), Some(10));
    assert_eq!(table["updated"].as_str(), Some("2024-01-15T10:00:00Z"));
}

#[test]
fn test_autopilot_config_serializes_to_valid_toml() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        None,
        "conservative",
        30,
        5,
        "2024-06-01T00:00:00Z",
    );
    let toml_str = toml::to_string_pretty(&config).unwrap();
    let parsed: toml::Value = toml_str.parse().unwrap();
    assert_eq!(parsed["enabled"].as_bool(), Some(true));
    assert!(parsed.get("budget").is_none());
}
