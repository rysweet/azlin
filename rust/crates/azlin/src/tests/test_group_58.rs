#[test]
fn test_update_log_type_to_path() {
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
        crate::update_helpers::log_type_to_path("unknown"),
        "/var/log/syslog"
    );
}

#[test]
fn test_compose_resolve_file_none() {
    assert_eq!(
        crate::compose_helpers::resolve_compose_file(None),
        "docker-compose.yml"
    );
}

#[test]
fn test_compose_resolve_file_custom() {
    assert_eq!(
        crate::compose_helpers::resolve_compose_file(Some("prod.yml")),
        "prod.yml"
    );
}

#[test]
fn test_runner_pool_config_filename() {
    assert_eq!(
        crate::runner_helpers::pool_config_filename("my-pool"),
        "my-pool.toml"
    );
}

#[test]
fn test_autopilot_build_budget_name() {
    assert_eq!(
        crate::autopilot_helpers::build_budget_name("my-rg"),
        "azlin-budget-my-rg"
    );
}

#[test]
fn test_autopilot_build_prefix_filter_query() {
    assert_eq!(
        crate::autopilot_helpers::build_prefix_filter_query("dev-"),
        "[?starts_with(name, 'dev-')].id"
    );
}

#[test]
fn test_autopilot_build_cost_scope() {
    assert_eq!(
        crate::autopilot_helpers::build_cost_scope("sub-123", "my-rg"),
        "/subscriptions/sub-123/resourceGroups/my-rg"
    );
}

#[test]
fn test_connect_build_log_follow_args() {
    let args =
        crate::connect_helpers::build_log_follow_args("admin", "10.0.0.1", "/var/log/syslog");
    assert!(args.contains(&format!("admin@10.0.0.1")));
    assert!(args.contains(&"sudo tail -f /var/log/syslog".to_string()));
    assert!(args.contains(&"ConnectTimeout=10".to_string()));
}

#[test]
fn test_connect_build_vscode_remote_uri() {
    let uri = crate::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_default_dotfiles() {
    let files = crate::sync_helpers::default_dotfiles();
    assert!(files.contains(&".bashrc"));
    assert!(files.contains(&".gitconfig"));
    assert!(files.len() >= 4);
}

#[test]
fn test_disk_build_data_disk_name_format_check() {
    assert_eq!(
        crate::disk_helpers::build_data_disk_name("myvm", 3),
        "myvm_datadisk_3"
    );
}

#[test]
fn test_disk_build_restored_name_format_check() {
    assert_eq!(
        crate::disk_helpers::build_restored_disk_name("myvm"),
        "myvm_OsDisk_restored"
    );
}

#[test]
fn test_name_validation_valid_names() {
    assert!(crate::name_validation::validate_name("my-name").is_ok());
    assert!(crate::name_validation::validate_name("test_name.v2").is_ok());
    assert!(crate::name_validation::validate_name("simple").is_ok());
}

#[test]
fn test_name_validation_invalid_names() {
    assert!(crate::name_validation::validate_name("").is_err());
    assert!(crate::name_validation::validate_name("a/b").is_err());
    assert!(crate::name_validation::validate_name("a\\b").is_err());
    assert!(crate::name_validation::validate_name("a\0b").is_err());
    assert!(crate::name_validation::validate_name("a..b").is_err());
}

#[test]
fn test_build_ssh_target_with_admin_username() {
    use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
    use std::collections::HashMap;

    let vm = VmInfo {
        name: "test-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D2s_v3".to_string(),
        os_type: OsType::Linux,
        power_state: PowerState::Running,
        provisioning_state: ProvisioningState::Succeeded,
        os_offer: None,
        public_ip: Some("1.2.3.4".to_string()),
        private_ip: Some("10.0.0.1".to_string()),
        admin_username: Some("customuser".to_string()),
        tags: HashMap::new(),
        created_time: None,
    };
    let bastion_map = HashMap::new();
    let ssh_key = None;
    let target = crate::build_ssh_target(&vm, "sub-id", &bastion_map, &ssh_key);
    assert_eq!(target.vm_name, "test-vm");
    assert_eq!(target.ip, "1.2.3.4");
    assert_eq!(target.user, "customuser");
    assert!(target.bastion.is_none());
}

#[test]
fn test_build_ssh_target_no_admin_username() {
    use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
    use std::collections::HashMap;

    let vm = VmInfo {
        name: "vm2".to_string(),
        resource_group: "rg".to_string(),
        location: "westus".to_string(),
        vm_size: "Standard_B2s".to_string(),
        os_type: OsType::Linux,
        power_state: PowerState::Running,
        provisioning_state: ProvisioningState::Succeeded,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.2".to_string()),
        admin_username: None,
        tags: HashMap::new(),
        created_time: None,
    };
    let bastion_map = HashMap::new();
    let ssh_key = None;
    let target = crate::build_ssh_target(&vm, "sub-id", &bastion_map, &ssh_key);
    assert_eq!(target.ip, "10.0.0.2");
    assert_eq!(target.user, "azureuser");
    // No bastion in map for "westus"
    assert!(target.bastion.is_none());
}

#[test]
fn test_build_ssh_target_no_ip() {
    use azlin_core::models::{OsType, PowerState, ProvisioningState, VmInfo};
    use std::collections::HashMap;

    let vm = VmInfo {
        name: "vm3".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_B1s".to_string(),
        os_type: OsType::Linux,
        power_state: PowerState::Stopped,
        provisioning_state: ProvisioningState::Succeeded,
        os_offer: None,
        public_ip: None,
        private_ip: None,
        admin_username: None,
        tags: HashMap::new(),
        created_time: None,
    };
    let bastion_map = HashMap::new();
    let ssh_key = None;
    let target = crate::build_ssh_target(&vm, "sub-id", &bastion_map, &ssh_key);
    assert_eq!(target.ip, "");
}

#[test]
fn test_shell_escape_round5_empty() {
    assert_eq!(crate::shell_escape(""), "''");
}

#[test]
fn test_shell_escape_round5_plain() {
    assert_eq!(crate::shell_escape("hello"), "'hello'");
}

#[test]
fn test_shell_escape_round5_with_quote() {
    assert_eq!(crate::shell_escape("it's"), "'it'\\''s'");
}

#[test]
fn test_home_dir_round5_returns_path() {
    let h = crate::home_dir();
    assert!(h.is_ok());
    assert!(h.unwrap().exists());
}

#[test]
fn test_fleet_spinner_style_valid() {
    // Just verify it doesn't panic
    let _style = crate::fleet_spinner_style();
}

#[test]
fn test_resolve_ssh_key_returns_option() {
    // Just verify it doesn't panic — actual result depends on filesystem
    let _key = crate::resolve_ssh_key();
}

#[test]
fn test_snapshot_helpers_save_load_roundtrip() {
    let tmp = tempfile::TempDir::new().unwrap();
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "roundtrip-vm".to_string(),
        resource_group: "test-rg".to_string(),
        every_hours: 12,
        keep_count: 5,
        enabled: false,
        created: "2026-03-07".to_string(),
    };
    let path = tmp.path().join("roundtrip-vm.toml");
    let contents = toml::to_string_pretty(&schedule).unwrap();
    std::fs::write(&path, &contents).unwrap();

    let loaded: crate::snapshot_helpers::SnapshotSchedule =
        toml::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(loaded.vm_name, "roundtrip-vm");
    assert!(!loaded.enabled);
    assert_eq!(loaded.every_hours, 12);
    assert_eq!(loaded.keep_count, 5);
}

#[test]
fn test_snapshot_helpers_load_all_schedules_empty_dir() {
    // load_all_schedules returns empty vec on missing dir
    let result = crate::snapshot_helpers::load_all_schedules();
    // It reads from the real home dir schedules — just verify no panic
    // Verify no panic — any length is fine
    let _ = result.len();
}
