// ── Native bastion tunnel integration tests (test_group_72) ──
//
// TDD tests for:
//   1. TunnelRegistryEntry backward compatibility (tunnel_type field)
//   2. AzlinConfig bastion_tunnel_timeout field
//   3. BastionAction::Sweep CLI variant
//   4. ScopedBastionTunnel async interface
//   5. Registry prune logic for native vs legacy tunnels
//   6. bastion_tunnel_timeout default and override
//   7. Sweep command dispatching

// ═══════════════════════════════════════════════════════════════════════
// 1. TunnelRegistryEntry — tunnel_type field with backward compat
// ═══════════════════════════════════════════════════════════════════════

/// New tunnel_type field must exist on TunnelRegistryEntry.
#[test]
fn test_tunnel_registry_entry_has_tunnel_type_field() {
    let entry = crate::bastion_tunnel::TunnelRegistryEntry {
        vm_resource_id: "test-vm".to_string(),
        bastion_name: "bastion-1".to_string(),
        resource_group: "rg-1".to_string(),
        local_port: 12345,
        pid: 999,
        created_at: 1700000000,
        tunnel_type: "native".to_string(),
    };
    assert_eq!(entry.tunnel_type, "native");
}

/// tunnel_type must default to "legacy" when missing from JSON (backward compat).
#[test]
fn test_tunnel_registry_entry_defaults_tunnel_type_to_legacy() {
    // Simulate a registry file from before the migration (no tunnel_type field)
    let json = r#"{
        "vm_resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        "bastion_name": "bastion-1",
        "resource_group": "rg-1",
        "local_port": 54321,
        "pid": 1234,
        "created_at": 1700000000
    }"#;
    let entry: crate::bastion_tunnel::TunnelRegistryEntry =
        serde_json::from_str(json).expect("must deserialize without tunnel_type");
    assert_eq!(
        entry.tunnel_type, "legacy",
        "missing tunnel_type must default to 'legacy'"
    );
}

/// Full registry with mixed tunnel types must round-trip through JSON.
#[test]
fn test_tunnel_registry_mixed_types_round_trip() {
    let mut registry = crate::bastion_tunnel::TunnelRegistry::default();
    registry.tunnels.insert(
        "vm-native".to_string(),
        crate::bastion_tunnel::TunnelRegistryEntry {
            vm_resource_id: "vm-native".to_string(),
            bastion_name: "bastion-1".to_string(),
            resource_group: "rg-1".to_string(),
            local_port: 10001,
            pid: 100,
            created_at: 1700000000,
            tunnel_type: "native".to_string(),
        },
    );
    registry.tunnels.insert(
        "vm-legacy".to_string(),
        crate::bastion_tunnel::TunnelRegistryEntry {
            vm_resource_id: "vm-legacy".to_string(),
            bastion_name: "bastion-1".to_string(),
            resource_group: "rg-1".to_string(),
            local_port: 10002,
            pid: 200,
            created_at: 1700000000,
            tunnel_type: "legacy".to_string(),
        },
    );

    let json = serde_json::to_string(&registry).expect("must serialize");
    let restored: crate::bastion_tunnel::TunnelRegistry =
        serde_json::from_str(&json).expect("must deserialize");

    assert_eq!(restored.tunnels.len(), 2);
    assert_eq!(restored.tunnels["vm-native"].tunnel_type, "native");
    assert_eq!(restored.tunnels["vm-legacy"].tunnel_type, "legacy");
}

/// Existing registry JSON without any tunnel_type fields must still load.
#[test]
fn test_full_registry_backward_compat_no_tunnel_type() {
    let json = r#"{
        "tunnels": {
            "vm-old": {
                "vm_resource_id": "vm-old",
                "bastion_name": "bastion-1",
                "resource_group": "rg-1",
                "local_port": 55555,
                "pid": 9999,
                "created_at": 1700000000
            }
        }
    }"#;
    let registry: crate::bastion_tunnel::TunnelRegistry =
        serde_json::from_str(json).expect("must load old registry format");
    assert_eq!(registry.tunnels.len(), 1);
    assert_eq!(registry.tunnels["vm-old"].tunnel_type, "legacy");
}

// ═══════════════════════════════════════════════════════════════════════
// 2. AzlinConfig — bastion_tunnel_timeout field
// ═══════════════════════════════════════════════════════════════════════

/// AzlinConfig must have bastion_tunnel_timeout field.
#[test]
fn test_config_has_bastion_tunnel_timeout() {
    let config = azlin_core::AzlinConfig::default();
    assert_eq!(
        config.bastion_tunnel_timeout, 30,
        "bastion_tunnel_timeout must default to 30 seconds"
    );
}

/// bastion_tunnel_timeout must be separate from bastion_detection_timeout.
#[test]
fn test_config_tunnel_timeout_separate_from_detection() {
    let config = azlin_core::AzlinConfig::default();
    assert_ne!(
        config.bastion_tunnel_timeout, config.bastion_detection_timeout,
        "tunnel timeout (30s) must differ from detection timeout (60s)"
    );
}

/// bastion_tunnel_timeout must be loadable from TOML config.
#[test]
fn test_config_tunnel_timeout_from_toml() {
    let toml_str = r#"
        bastion_tunnel_timeout = 45
    "#;
    let config: azlin_core::AzlinConfig =
        toml::from_str(toml_str).expect("must parse toml with bastion_tunnel_timeout");
    assert_eq!(config.bastion_tunnel_timeout, 45);
}

/// bastion_tunnel_timeout defaults to 30 when missing from TOML.
#[test]
fn test_config_tunnel_timeout_defaults_when_missing() {
    let toml_str = r#"
        default_region = "eastus"
    "#;
    let config: azlin_core::AzlinConfig =
        toml::from_str(toml_str).expect("must parse toml without bastion_tunnel_timeout");
    assert_eq!(
        config.bastion_tunnel_timeout, 30,
        "missing bastion_tunnel_timeout must default to 30"
    );
}

// ═══════════════════════════════════════════════════════════════════════
// 3. BastionAction::Sweep CLI variant
// ═══════════════════════════════════════════════════════════════════════

/// BastionAction must have a Sweep variant.
#[test]
fn test_bastion_action_sweep_variant_exists() {
    let action = azlin_cli::BastionAction::Sweep;
    assert!(matches!(action, azlin_cli::BastionAction::Sweep));
}

/// `azlin bastion sweep` must parse from CLI args.
#[test]
fn test_bastion_sweep_cli_parsing() {
    use clap::Parser;
    let cli = azlin_cli::Cli::try_parse_from(["azlin", "bastion", "sweep"]);
    assert!(cli.is_ok(), "must parse 'azlin bastion sweep': {:?}", cli.err());
    let cli = cli.unwrap();
    match cli.command {
        azlin_cli::Commands::Bastion { action } => {
            assert!(
                matches!(action, azlin_cli::BastionAction::Sweep),
                "must parse as Sweep variant"
            );
        }
        _ => panic!("expected Bastion command"),
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 4. Registry native tunnel entry creation
// ═══════════════════════════════════════════════════════════════════════

/// Native tunnel entries must set tunnel_type to "native".
#[test]
fn test_native_tunnel_entry_sets_type() {
    let entry = crate::bastion_tunnel::TunnelRegistryEntry {
        vm_resource_id: "vm-1".to_string(),
        bastion_name: "bastion".to_string(),
        resource_group: "rg".to_string(),
        local_port: 12345,
        pid: std::process::id(),
        created_at: 0,
        tunnel_type: "native".to_string(),
    };
    assert_eq!(entry.tunnel_type, "native");
    assert_eq!(entry.pid, std::process::id(), "native tunnels use own PID");
}

/// Legacy tunnel entries must set tunnel_type to "legacy".
#[test]
fn test_legacy_tunnel_entry_sets_type() {
    let entry = crate::bastion_tunnel::TunnelRegistryEntry {
        vm_resource_id: "vm-2".to_string(),
        bastion_name: "bastion".to_string(),
        resource_group: "rg".to_string(),
        local_port: 12346,
        pid: 9999,
        created_at: 0,
        tunnel_type: "legacy".to_string(),
    };
    assert_eq!(entry.tunnel_type, "legacy");
}

// ═══════════════════════════════════════════════════════════════════════
// 5. bastion_ssh_args still works (no regression)
// ═══════════════════════════════════════════════════════════════════════

/// bastion_ssh_args must still produce correct SSH arguments.
#[test]
fn test_bastion_ssh_args_unchanged() {
    let args = crate::bastion_tunnel::bastion_ssh_args("azureuser", 12345, "whoami", 30);
    assert!(args.contains(&"-p".to_string()));
    assert!(args.contains(&"12345".to_string()));
    assert!(args.contains(&"azureuser@127.0.0.1".to_string()));
    assert!(args.contains(&"whoami".to_string()));
}

/// bastion_scp_args must still produce correct SCP arguments.
#[test]
fn test_bastion_scp_args_unchanged() {
    let args = crate::bastion_tunnel::bastion_scp_args(
        "azureuser",
        12345,
        &["file.txt"],
        "/home/user/",
        30,
        false,
    );
    assert!(args.contains(&"-P".to_string()));
    assert!(args.contains(&"12345".to_string()));
    assert!(args.contains(&"file.txt".to_string()));
}

// ═══════════════════════════════════════════════════════════════════════
// 6. Edge cases
// ═══════════════════════════════════════════════════════════════════════

/// Serializing a TunnelRegistryEntry with tunnel_type produces the field in JSON.
#[test]
fn test_tunnel_type_serialized_in_json() {
    let entry = crate::bastion_tunnel::TunnelRegistryEntry {
        vm_resource_id: "vm".to_string(),
        bastion_name: "b".to_string(),
        resource_group: "rg".to_string(),
        local_port: 1,
        pid: 1,
        created_at: 0,
        tunnel_type: "native".to_string(),
    };
    let json = serde_json::to_string(&entry).unwrap();
    assert!(json.contains("tunnel_type"), "JSON must contain tunnel_type field");
    assert!(json.contains("\"native\""), "JSON must contain native value");
}

/// Zero timeout should still be accepted (but will likely fail immediately).
#[test]
fn test_config_accepts_zero_tunnel_timeout() {
    let toml_str = r#"bastion_tunnel_timeout = 0"#;
    let config: azlin_core::AzlinConfig =
        toml::from_str(toml_str).expect("must parse zero timeout");
    assert_eq!(config.bastion_tunnel_timeout, 0);
}
