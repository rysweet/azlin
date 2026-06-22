#[allow(unused_imports)]
use crate::*;
use std::fs;
use tempfile::TempDir;

// ── contexts::build_context_toml no optional fields ─────────────

#[test]
fn test_context_build_toml_no_optional_fields() {
    let toml_str =
        crate::contexts::build_context_toml("bare", None, None, None, None, None).unwrap();
    let parsed: toml::Value = toml_str.parse().unwrap();
    let tbl = parsed.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "bare");
    // Optional fields should be absent
    assert!(tbl.get("subscription_id").is_none());
    assert!(tbl.get("tenant_id").is_none());
    assert!(tbl.get("resource_group").is_none());
    assert!(tbl.get("region").is_none());
    assert!(tbl.get("key_vault_name").is_none());
}

// ── contexts::read_context_resource_group — name from filestem ───────

#[test]
fn test_context_read_resource_group_name_from_filestem() {
    let tmp = TempDir::new().unwrap();
    // A context TOML without a "name" field — name is derived from the filename
    let path = tmp.path().join("my-ctx.toml");
    fs::write(&path, "resource_group = \"my-rg\"\n").unwrap();

    let (name, rg) = crate::contexts::read_context_resource_group(&path).unwrap();
    assert_eq!(name, "my-ctx");
    assert_eq!(rg, Some("my-rg".to_string()));
}

// ── create_helpers::build_clone_cmd — SSH URL ──────────────────

#[test]
fn test_build_clone_cmd_ssh_url() {
    let cmd = crate::create_helpers::build_clone_cmd("git@github.com:user/repo.git").unwrap();
    assert!(cmd.contains("git clone"));
    assert!(cmd.contains("git@github.com:user/repo.git"));
    assert!(cmd.contains("repo")); // basename extraction
}

// ── health_helpers::format_percentage negative clamping ─────────

#[test]
fn test_format_percentage_negative_clamps_to_zero() {
    assert_eq!(crate::health_helpers::format_percentage(-5.0), "0.0%");
    assert_eq!(crate::health_helpers::format_percentage(-999.0), "0.0%");
}

// ── connect_helpers edge cases ─────────────────────────────────

#[test]
fn test_build_log_follow_args_format() {
    let args =
        crate::connect_helpers::build_log_follow_args("admin", "10.0.0.5", "/var/log/syslog", 10);
    assert_eq!(args.len(), 6);
    assert_eq!(args[0], "-o");
    assert_eq!(args[1], "StrictHostKeyChecking=accept-new");
    assert_eq!(args[4], "admin@10.0.0.5");
    assert!(args[5].contains("tail -f"));
    assert!(args[5].contains("/var/log/syslog"));
}

#[test]
fn test_build_log_tail_args_line_count() {
    let args = crate::connect_helpers::build_log_tail_args(
        "user",
        "192.168.1.1",
        200,
        "/var/log/auth.log",
        10,
    );
    assert_eq!(args.len(), 6);
    assert!(args[5].contains("tail -n 200"));
    assert!(args[5].contains("/var/log/auth.log"));
}

// ── update_helpers::log_type_to_path default branch ────────────

#[test]
fn test_log_type_to_path_capital_variants() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
}

// ── autopilot_helpers::build_autopilot_config no budget ────────

#[test]
fn test_build_autopilot_config_no_budget_field_absent() {
    let config = crate::autopilot_helpers::build_autopilot_config(
        None,
        "conservative",
        60,
        10,
        "2024-01-01T00:00:00Z",
    );
    let tbl = config.as_table().unwrap();
    assert!(tbl.get("budget").is_none());
    assert_eq!(tbl["strategy"].as_str().unwrap(), "conservative");
    assert_eq!(tbl["idle_threshold_minutes"].as_integer().unwrap(), 60);
    assert_eq!(tbl["cpu_threshold_percent"].as_integer().unwrap(), 10);
}

// ── batch_helpers::parse_vm_ids whitespace handling ─────────────

#[test]
fn test_parse_vm_ids_trailing_newlines() {
    let output = "/subscriptions/abc/vms/vm1\n/subscriptions/abc/vms/vm2\n\n\n";
    let ids = crate::batch_helpers::parse_vm_ids(output);
    assert_eq!(ids.len(), 2);
    assert_eq!(ids[0], "/subscriptions/abc/vms/vm1");
    assert_eq!(ids[1], "/subscriptions/abc/vms/vm2");
}

// ── runner_helpers::pool_config_filename ───────────────────────

#[test]
fn test_pool_config_filename_format() {
    assert_eq!(
        crate::runner_helpers::pool_config_filename("default"),
        "default.toml"
    );
    assert_eq!(
        crate::runner_helpers::pool_config_filename("ci-large"),
        "ci-large.toml"
    );
}

// ── compose_helpers edge case ──────────────────────────────────

#[test]
fn test_build_compose_cmd_with_services() {
    let cmd = crate::compose_helpers::build_compose_cmd("up -d", "prod-compose.yml");
    assert_eq!(cmd, "docker compose -f prod-compose.yml up -d");
}

// ── templates::save + load + delete full lifecycle ──────────────

#[test]
fn test_template_full_lifecycle_save_load_list_delete() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();

    // Save two templates
    let tpl1 = crate::templates::build_template_toml(
        "web",
        Some("Web server"),
        Some("Standard_B2s"),
        Some("westus2"),
        None,
    );
    let tpl2 = crate::templates::build_template_toml(
        "gpu",
        Some("GPU worker"),
        Some("Standard_NC6"),
        Some("eastus"),
        Some("#!/bin/bash\nnvidia-smi"),
    );
    crate::templates::save_template(dir, "web", &tpl1).unwrap();
    crate::templates::save_template(dir, "gpu", &tpl2).unwrap();

    // List should return both
    let list = crate::templates::list_templates(dir).unwrap();
    assert_eq!(list.len(), 2);

    // Load one
    let loaded = crate::templates::load_template(dir, "gpu").unwrap();
    assert_eq!(loaded.get("name").unwrap().as_str().unwrap(), "gpu");
    assert!(loaded.get("cloud_init").is_some());

    // Delete one
    crate::templates::delete_template(dir, "web").unwrap();
    let list2 = crate::templates::list_templates(dir).unwrap();
    assert_eq!(list2.len(), 1);

    // Load deleted template should fail
    assert!(crate::templates::load_template(dir, "web").is_err());
}

// ── contexts::rename_context_file on nonexistent ───────────────

#[test]
fn test_context_rename_nonexistent_errors() {
    let tmp = TempDir::new().unwrap();
    let result = crate::contexts::rename_context_file(tmp.path(), "no-such-ctx", "new-name");
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("not found"));
}

// ═══════════════════════════════════════════════════════════════
// NEW COVERAGE TESTS — Batch 2: 35+ tests for 80% target
// ═══════════════════════════════════════════════════════════════
