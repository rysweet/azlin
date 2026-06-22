// ── list_helpers with VmInfo ────────────────────────────────────

#[test]
fn test_filter_running_keeps_starting() {
    use azlin_core::models::{OsType, PowerState, VmInfo};
    let mut vms = vec![
        VmInfo {
            name: "running-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
        VmInfo {
            name: "starting-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Starting,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
        VmInfo {
            name: "stopped-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Stopped,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
    ];
    crate::list_helpers::filter_running(&mut vms);
    assert_eq!(vms.len(), 2);
    assert!(vms
        .iter()
        .all(|v| v.power_state == PowerState::Running || v.power_state == PowerState::Starting));
}

#[test]
fn test_filter_by_tag_key_only_match() {
    use azlin_core::models::{OsType, PowerState, VmInfo};
    let mut vms = vec![
        VmInfo {
            name: "tagged".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: [("env".to_string(), "prod".to_string())]
                .into_iter()
                .collect(),
            created_time: None,
        },
        VmInfo {
            name: "untagged".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
    ];
    // Key-only filter (no =value)
    crate::list_helpers::filter_by_tag(&mut vms, "env");
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "tagged");
}

#[test]
fn test_apply_filters_include_all_skips_running_filter() {
    use azlin_core::models::{OsType, PowerState, VmInfo};
    let mut vms = vec![VmInfo {
        name: "stopped-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "B2s".to_string(),
        power_state: PowerState::Stopped,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: None,
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    }];
    crate::list_helpers::apply_filters(&mut vms, true, None, None);
    assert_eq!(vms.len(), 1); // stopped VM kept because include_all=true
}

// ── create_helpers ──────────────────────────────────────────────

#[test]
fn test_generate_vm_name_pool_indexing() {
    let name = crate::create_helpers::generate_vm_name(Some("worker"), 0, 3, "20240115");
    assert_eq!(name, "worker-1");
    let name2 = crate::create_helpers::generate_vm_name(Some("worker"), 2, 3, "20240115");
    assert_eq!(name2, "worker-3");
}

#[test]
fn test_generate_vm_name_single_pool_no_index() {
    let name = crate::create_helpers::generate_vm_name(Some("myvm"), 0, 1, "20240115");
    assert_eq!(name, "myvm");
}

#[test]
fn test_generate_vm_name_auto_timestamp() {
    let name = crate::create_helpers::generate_vm_name(None, 0, 1, "20240115120000");
    assert!(name.starts_with("azlin-vm-"));
    assert!(name.contains("20240115120000"));
}

#[test]
fn test_resolve_with_template_sentinel_uses_template() {
    let result = crate::create_helpers::resolve_with_template_default(
        "Standard_B2s",
        "Standard_B2s",
        Some("Standard_D4s_v3".to_string()),
    );
    assert_eq!(result, "Standard_D4s_v3");
}

#[test]
fn test_resolve_with_template_user_override() {
    let result = crate::create_helpers::resolve_with_template_default(
        "Standard_NC6",
        "Standard_B2s",
        Some("Standard_D4s_v3".to_string()),
    );
    assert_eq!(result, "Standard_NC6");
}

#[test]
fn test_resolve_with_template_sentinel_no_template_keeps_default() {
    let result =
        crate::create_helpers::resolve_with_template_default("Standard_B2s", "Standard_B2s", None);
    assert_eq!(result, "Standard_B2s");
}

// ── connect_helpers ─────────────────────────────────────────────

#[test]
fn test_build_ssh_args_with_key_path() {
    let key = std::path::PathBuf::from("/home/user/.ssh/id_ed25519");
    let args = crate::connect_helpers::build_ssh_args("azureuser", "10.0.0.1", Some(key.as_path()));
    assert!(args.contains(&"-i".to_string()));
    assert!(args.contains(&"/home/user/.ssh/id_ed25519".to_string()));
    assert!(args.contains(&"azureuser@10.0.0.1".to_string()));
}

#[test]
fn test_build_ssh_args_no_key_provided() {
    let args = crate::connect_helpers::build_ssh_args("user", "1.2.3.4", None);
    assert!(!args.contains(&"-i".to_string()));
    assert!(args.contains(&"user@1.2.3.4".to_string()));
}

#[test]
fn test_build_vscode_remote_uri_format() {
    let uri = crate::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_build_log_follow_args_has_tail_f() {
    let args =
        crate::connect_helpers::build_log_follow_args("user", "10.0.0.1", "/var/log/syslog", 10);
    assert!(args.iter().any(|a| a.contains("tail -f")));
    assert!(args.iter().any(|a| a.contains("/var/log/syslog")));
}

#[test]
fn test_build_log_tail_args_custom_lines() {
    let args = crate::connect_helpers::build_log_tail_args(
        "user",
        "10.0.0.1",
        100,
        "/var/log/auth.log",
        10,
    );
    assert!(args.iter().any(|a| a.contains("tail -n 100")));
}

// ── update_helpers ──────────────────────────────────────────────

#[test]
fn test_build_dev_update_script_all_sections() {
    let script = crate::update_helpers::build_dev_update_script();
    assert!(script.contains("apt-get update"));
    assert!(script.contains("rustup"));
    assert!(script.contains("pip3"));
    assert!(script.contains("npm"));
}

#[test]
fn test_build_os_update_cmd_format() {
    let cmd = crate::update_helpers::build_os_update_cmd();
    assert!(cmd.contains("apt-get update"));
    assert!(cmd.contains("apt-get upgrade"));
    assert!(cmd.contains("DEBIAN_FRONTEND=noninteractive"));
}

#[test]
fn test_log_type_to_path_all_variants() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("cloud-init"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("auth"),
        "/var/log/auth.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("other"),
        "/var/log/syslog"
    );
}
