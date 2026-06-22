use std::fs;
use tempfile::TempDir;

// ── list_helpers tests ──────────────────────────────────────

fn make_vm(name: &str, state: azlin_core::models::PowerState) -> azlin_core::models::VmInfo {
    azlin_core::models::VmInfo {
        name: name.to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_B2s".to_string(),
        power_state: state,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: Some("10.0.0.1".to_string()),
        private_ip: None,
        admin_username: Some("azureuser".to_string()),
        tags: std::collections::HashMap::new(),
        created_time: None,
    }
}

fn make_tagged_vm(name: &str, tags: Vec<(&str, &str)>) -> azlin_core::models::VmInfo {
    let mut vm = make_vm(name, azlin_core::models::PowerState::Running);
    for (k, v) in tags {
        vm.tags.insert(k.to_string(), v.to_string());
    }
    vm
}

#[test]
fn test_filter_running_removes_stopped() {
    let mut vms = vec![
        make_vm("running-vm", azlin_core::models::PowerState::Running),
        make_vm("stopped-vm", azlin_core::models::PowerState::Stopped),
        make_vm("starting-vm", azlin_core::models::PowerState::Starting),
        make_vm("dealloc-vm", azlin_core::models::PowerState::Deallocated),
    ];
    crate::list_helpers::filter_running(&mut vms);
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].name, "running-vm");
    assert_eq!(vms[1].name, "starting-vm");
}

#[test]
fn test_filter_running_empty_list() {
    let mut vms: Vec<azlin_core::models::VmInfo> = vec![];
    crate::list_helpers::filter_running(&mut vms);
    assert!(vms.is_empty());
}

#[test]
fn test_filter_by_tag_key_value() {
    let mut vms = vec![
        make_tagged_vm("vm1", vec![("env", "prod")]),
        make_tagged_vm("vm2", vec![("env", "dev")]),
        make_tagged_vm("vm3", vec![("team", "infra")]),
    ];
    crate::list_helpers::filter_by_tag(&mut vms, "env=prod");
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm1");
}

#[test]
fn test_filter_by_tag_key_only() {
    let mut vms = vec![
        make_tagged_vm("vm1", vec![("env", "prod")]),
        make_tagged_vm("vm2", vec![("env", "dev")]),
        make_tagged_vm("vm3", vec![("team", "infra")]),
    ];
    crate::list_helpers::filter_by_tag(&mut vms, "env");
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].name, "vm1");
    assert_eq!(vms[1].name, "vm2");
}

#[test]
fn test_filter_by_tag_no_match() {
    let mut vms = vec![make_tagged_vm("vm1", vec![("env", "prod")])];
    crate::list_helpers::filter_by_tag(&mut vms, "env=staging");
    assert!(vms.is_empty());
}

#[test]
fn test_filter_by_tag_nonexistent_key() {
    let mut vms = vec![make_tagged_vm("vm1", vec![("env", "prod")])];
    crate::list_helpers::filter_by_tag(&mut vms, "region");
    assert!(vms.is_empty());
}

#[test]
fn test_filter_by_pattern_simple() {
    let mut vms = vec![
        make_vm("web-server-01", azlin_core::models::PowerState::Running),
        make_vm("db-server-01", azlin_core::models::PowerState::Running),
        make_vm("web-server-02", azlin_core::models::PowerState::Running),
    ];
    crate::list_helpers::filter_by_pattern(&mut vms, "web");
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].name, "web-server-01");
    assert_eq!(vms[1].name, "web-server-02");
}

#[test]
fn test_filter_by_pattern_with_glob() {
    let mut vms = vec![
        make_vm("web-server-01", azlin_core::models::PowerState::Running),
        make_vm("db-server-01", azlin_core::models::PowerState::Running),
    ];
    crate::list_helpers::filter_by_pattern(&mut vms, "*web*");
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "web-server-01");
}

#[test]
fn test_filter_by_pattern_no_match() {
    let mut vms = vec![make_vm(
        "web-server",
        azlin_core::models::PowerState::Running,
    )];
    crate::list_helpers::filter_by_pattern(&mut vms, "cache");
    assert!(vms.is_empty());
}

#[test]
fn test_apply_filters_all_disabled() {
    let mut vms = vec![
        make_vm("vm1", azlin_core::models::PowerState::Running),
        make_vm("vm2", azlin_core::models::PowerState::Stopped),
    ];
    crate::list_helpers::apply_filters(&mut vms, true, None, None);
    assert_eq!(vms.len(), 2);
}

#[test]
fn test_apply_filters_exclude_stopped() {
    let mut vms = vec![
        make_vm("vm1", azlin_core::models::PowerState::Running),
        make_vm("vm2", azlin_core::models::PowerState::Stopped),
    ];
    crate::list_helpers::apply_filters(&mut vms, false, None, None);
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm1");
}

#[test]
fn test_apply_filters_combined() {
    let mut vms = vec![
        make_tagged_vm("web-prod", vec![("env", "prod")]),
        make_tagged_vm("web-dev", vec![("env", "dev")]),
        make_tagged_vm("db-prod", vec![("env", "prod")]),
    ];
    crate::list_helpers::apply_filters(&mut vms, true, Some("env=prod"), Some("web"));
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "web-prod");
}

// ── batch_helpers tests ─────────────────────────────────────

#[test]
fn test_parse_vm_ids_normal() {
    let ids = crate::batch_helpers::parse_vm_ids("/sub/1/rg/test/vm/vm1\n/sub/1/rg/test/vm/vm2\n");
    assert_eq!(ids.len(), 2);
    assert_eq!(ids[0], "/sub/1/rg/test/vm/vm1");
    assert_eq!(ids[1], "/sub/1/rg/test/vm/vm2");
}

#[test]
fn test_parse_vm_ids_empty() {
    let ids = crate::batch_helpers::parse_vm_ids("");
    assert!(ids.is_empty());
}

#[test]
fn test_parse_vm_ids_blank_lines() {
    let ids = crate::batch_helpers::parse_vm_ids("\n\n/sub/vm1\n\n");
    assert_eq!(ids.len(), 1);
    assert_eq!(ids[0], "/sub/vm1");
}

#[test]
fn test_build_batch_args_deallocate() {
    let ids = vec!["/sub/vm1", "/sub/vm2"];
    let args = crate::batch_helpers::build_batch_args("deallocate", &ids);
    assert_eq!(
        args,
        vec!["vm", "deallocate", "--ids", "/sub/vm1", "/sub/vm2"]
    );
}

#[test]
fn test_build_batch_args_start() {
    let ids = vec!["/sub/vm1"];
    let args = crate::batch_helpers::build_batch_args("start", &ids);
    assert_eq!(args, vec!["vm", "start", "--ids", "/sub/vm1"]);
}

#[test]
fn test_summarise_batch_success() {
    let msg = crate::batch_helpers::summarise_batch("stop", "my-rg", true);
    assert_eq!(msg, "Batch stop completed for resource group 'my-rg'");
}

#[test]
fn test_summarise_batch_failure() {
    let msg = crate::batch_helpers::summarise_batch("start", "my-rg", false);
    assert_eq!(msg, "Batch start failed. Run commands individually.");
}

#[test]
fn test_summarise_batch_other_action() {
    let msg = crate::batch_helpers::summarise_batch("restart", "prod-rg", true);
    assert!(msg.contains("restart"));
    assert!(msg.contains("prod-rg"));
}

// ── all_contexts tests ────────────────────────────────────────

#[test]
fn test_read_context_resource_group_with_rg() {
    let tmp = TempDir::new().unwrap();
    let ctx_path = tmp.path().join("dev.toml");
    fs::write(
        &ctx_path,
        "name = \"dev\"\nresource_group = \"dev-rg\"\nregion = \"westus2\"\n",
    )
    .unwrap();

    let (name, rg) = crate::contexts::read_context_resource_group(&ctx_path).unwrap();
    assert_eq!(name, "dev");
    assert_eq!(rg, Some("dev-rg".to_string()));
}

#[test]
fn test_read_context_resource_group_without_rg() {
    let tmp = TempDir::new().unwrap();
    let ctx_path = tmp.path().join("minimal.toml");
    fs::write(&ctx_path, "name = \"minimal\"\n").unwrap();

    let (name, rg) = crate::contexts::read_context_resource_group(&ctx_path).unwrap();
    assert_eq!(name, "minimal");
    assert_eq!(rg, None);
}

#[test]
fn test_read_context_resource_group_falls_back_to_filename() {
    let tmp = TempDir::new().unwrap();
    let ctx_path = tmp.path().join("staging.toml");
    fs::write(&ctx_path, "resource_group = \"staging-rg\"\n").unwrap();

    let (name, rg) = crate::contexts::read_context_resource_group(&ctx_path).unwrap();
    assert_eq!(name, "staging");
    assert_eq!(rg, Some("staging-rg".to_string()));
}
