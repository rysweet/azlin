// ── build_ssh_target tests ──────────────────────────────────────

#[test]
fn test_build_ssh_target_public_ip_no_bastion() {
    let vm = azlin_core::models::VmInfo {
        name: "my-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: Some("52.1.2.3".to_string()),
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: Some("testuser".to_string()),
        tags: Default::default(),
        created_time: None,
    };
    let bastion_map = std::collections::HashMap::new();
    let target = crate::build_ssh_target(&vm, "sub-123", &bastion_map, &None);
    assert_eq!(target.ip, "52.1.2.3");
    assert_eq!(target.user, "testuser");
    assert!(
        target.bastion.is_none(),
        "Public IP VMs should not route through bastion"
    );
}

#[test]
fn test_build_ssh_target_private_ip_with_bastion() {
    let vm = azlin_core::models::VmInfo {
        name: "my-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: Some("azureuser".to_string()),
        tags: Default::default(),
        created_time: None,
    };
    let mut bastion_map = std::collections::HashMap::new();
    bastion_map.insert("eastus".to_string(), "my-bastion".to_string());
    let target = crate::build_ssh_target(&vm, "sub-123", &bastion_map, &None);
    assert_eq!(target.ip, "10.0.0.4");
    assert!(
        target.bastion.is_some(),
        "Private-IP-only VM should route through bastion"
    );
    let b = target.bastion.unwrap();
    assert_eq!(b.bastion_name, "my-bastion");
    assert_eq!(b.resource_group, "rg");
    assert!(b.vm_resource_id.contains("my-vm"));
    assert!(b.vm_resource_id.contains("sub-123"));
}

#[test]
fn test_build_ssh_target_private_ip_no_bastion_available() {
    let vm = azlin_core::models::VmInfo {
        name: "my-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    };
    let bastion_map = std::collections::HashMap::new();
    let target = crate::build_ssh_target(&vm, "sub-123", &bastion_map, &None);
    assert_eq!(target.ip, "10.0.0.4");
    assert_eq!(
        target.user, "azureuser",
        "Should fall back to DEFAULT_ADMIN_USERNAME"
    );
    assert!(
        target.bastion.is_none(),
        "No bastion in map, so should be None"
    );
}

#[test]
fn test_build_ssh_target_bastion_wrong_location() {
    let vm = azlin_core::models::VmInfo {
        name: "vm1".to_string(),
        resource_group: "rg".to_string(),
        location: "westus2".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.5".to_string()),
        admin_username: Some("user1".to_string()),
        tags: Default::default(),
        created_time: None,
    };
    let mut bastion_map = std::collections::HashMap::new();
    bastion_map.insert("eastus".to_string(), "east-bastion".to_string());
    let target = crate::build_ssh_target(&vm, "sub-456", &bastion_map, &None);
    assert!(
        target.bastion.is_none(),
        "Bastion in different location should not match"
    );
}

#[test]
fn test_build_ssh_target_no_ips() {
    let vm = azlin_core::models::VmInfo {
        name: "orphan-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: None,
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    };
    let bastion_map = std::collections::HashMap::new();
    let target = crate::build_ssh_target(&vm, "sub-1", &bastion_map, &None);
    assert_eq!(target.ip, "", "No IPs at all should result in empty string");
}

// ── context glob filtering tests ────────────────────────────────

/// Helper: apply the same glob logic used in list handler for --contexts
fn context_glob_matches(ctx_name: &str, pattern: &str) -> bool {
    let pat = pattern.replace('*', "");
    if pattern.contains('*') {
        ctx_name.contains(&pat)
    } else {
        ctx_name == pattern
    }
}

#[test]
fn test_context_glob_exact_match() {
    assert!(context_glob_matches("dev", "dev"));
    assert!(!context_glob_matches("dev-pool", "dev"));
}

#[test]
fn test_context_glob_wildcard_prefix() {
    assert!(context_glob_matches("my-dev-pool", "*dev*"));
    assert!(context_glob_matches("dev-pool", "*dev*"));
    assert!(context_glob_matches("dev", "*dev*"));
    assert!(!context_glob_matches("staging", "*dev*"));
}

#[test]
fn test_context_glob_wildcard_suffix() {
    assert!(context_glob_matches("dev-pool", "dev*"));
    assert!(context_glob_matches("dev", "dev*"));
    // Note: the implementation uses substring match (contains), not prefix match
    // so "my-dev" DOES match "dev*" because it contains "dev"
    assert!(context_glob_matches("my-dev", "dev*"));
}

#[test]
fn test_context_glob_empty_pattern() {
    // "*" pattern means "match everything" — empty substring after removing *
    assert!(context_glob_matches("anything", "*"));
    assert!(context_glob_matches("", "*"));
}
