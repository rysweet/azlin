use std::path::PathBuf;

// ── Tunnel auth bug-fix regression tests (test_group_69) ───────────
//
// Guards against the three silent tunnel-auth failures:
//   Bug 1: --user default must be "azureuser" (not local username)
//   Bug 2: SSH key must be auto-resolved when --key omitted
//   Bug 3: Bastion tunnels must use StrictHostKeyChecking=no

// ── Bug 1: CLI --user default is "azureuser" ───────────────────────

#[test]
fn test_tunnel_open_user_defaults_to_azureuser() {
    use clap::Parser;
    let cli = azlin_cli::Cli::parse_from(["azlin", "tunnel", "open", "myvm", "8080"]);
    if let azlin_cli::Commands::Tunnel {
        action: azlin_cli::TunnelAction::Open { user, .. },
    } = cli.command
    {
        assert_eq!(
            user, "azureuser",
            "tunnel open --user must default to 'azureuser', got '{user}'"
        );
    } else {
        panic!("Expected Tunnel Open command");
    }
}

#[test]
fn test_tunnel_open_user_override_respected() {
    use clap::Parser;
    let cli = azlin_cli::Cli::parse_from([
        "azlin", "tunnel", "open", "myvm", "8080", "--user", "custom",
    ]);
    if let azlin_cli::Commands::Tunnel {
        action: azlin_cli::TunnelAction::Open { user, .. },
    } = cli.command
    {
        assert_eq!(user, "custom", "--user override must be honored");
    } else {
        panic!("Expected Tunnel Open command");
    }
}

// ── Bug 2: SSH key auto-resolution ─────────────────────────────────

#[test]
fn test_tunnel_open_key_is_none_when_omitted() {
    use clap::Parser;
    let cli = azlin_cli::Cli::parse_from(["azlin", "tunnel", "open", "myvm", "8080"]);
    if let azlin_cli::Commands::Tunnel {
        action: azlin_cli::TunnelAction::Open { key, .. },
    } = cli.command
    {
        assert!(
            key.is_none(),
            "key should be None when --key not specified, so resolve_ssh_key() can fill it"
        );
    } else {
        panic!("Expected Tunnel Open command");
    }
}

#[test]
fn test_tunnel_open_explicit_key_is_preserved() {
    use clap::Parser;
    let cli = azlin_cli::Cli::parse_from([
        "azlin",
        "tunnel",
        "open",
        "myvm",
        "8080",
        "--key",
        "/tmp/my_key",
    ]);
    if let azlin_cli::Commands::Tunnel {
        action: azlin_cli::TunnelAction::Open { key, .. },
    } = cli.command
    {
        assert_eq!(
            key,
            Some(PathBuf::from("/tmp/my_key")),
            "explicit --key must be preserved"
        );
    } else {
        panic!("Expected Tunnel Open command");
    }
}

#[test]
fn test_resolve_ssh_key_finds_azlin_key_first() {
    // Create a temp dir with multiple keys — azlin_key must win
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(temp.path().join("azlin_key"), "privkey").unwrap();
    std::fs::write(temp.path().join("id_rsa"), "rsa").unwrap();
    std::fs::write(temp.path().join("id_ed25519"), "ed").unwrap();

    let found = crate::key_helpers::find_preferred_private_key(temp.path());
    assert!(found.is_some(), "should find a key");
    assert!(
        found.unwrap().ends_with("azlin_key"),
        "azlin_key must have highest priority"
    );
}

#[test]
fn test_resolve_ssh_key_falls_back_to_ed25519() {
    // Only id_ed25519 present — should still find it
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(temp.path().join("id_ed25519"), "ed").unwrap();

    let found = crate::key_helpers::find_preferred_private_key(temp.path());
    assert!(found.is_some(), "should find id_ed25519 as fallback");
    assert!(found.unwrap().ends_with("id_ed25519"));
}

#[test]
fn test_resolve_ssh_key_returns_none_when_no_keys() {
    let temp = tempfile::tempdir().unwrap();
    let found = crate::key_helpers::find_preferred_private_key(temp.path());
    assert!(found.is_none(), "no keys present should return None");
}

// ── Bug 3: Bastion SSH args use StrictHostKeyChecking=no ───────────

#[test]
fn test_bastion_ssh_args_strict_host_key_checking_no() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(8080, 8080, 50200, "azureuser", None);
    assert!(
        args.contains(&"StrictHostKeyChecking=no".to_string()),
        "bastion tunnel must use StrictHostKeyChecking=no, got: {:?}",
        args
    );
    assert!(
        !args.contains(&"StrictHostKeyChecking=accept-new".to_string()),
        "bastion tunnel must NOT use accept-new"
    );
}

#[test]
fn test_bastion_ssh_args_user_known_hosts_dev_null() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(8080, 8080, 50200, "azureuser", None);
    assert!(
        args.contains(&"UserKnownHostsFile=/dev/null".to_string()),
        "bastion tunnel must set UserKnownHostsFile=/dev/null, got: {:?}",
        args
    );
}

#[test]
fn test_bastion_ssh_args_connects_to_loopback() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(8080, 8080, 50200, "azureuser", None);
    let last = args.last().expect("args should not be empty");
    assert!(
        last.contains("127.0.0.1"),
        "bastion SSH must connect to 127.0.0.1, got: {last}"
    );
    assert!(
        last.starts_with("azureuser@"),
        "bastion SSH user@host should use provided user, got: {last}"
    );
}

#[test]
fn test_bastion_ssh_args_includes_bastion_port() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(3000, 8080, 50201, "testuser", None);
    let port_idx = args.iter().position(|a| a == "-p").expect("-p flag missing");
    assert_eq!(
        args[port_idx + 1], "50201",
        "bastion SSH must use bastion local port"
    );
}

#[test]
fn test_bastion_ssh_args_includes_key_when_provided() {
    let key_path = std::path::Path::new("/home/test/.ssh/azlin_key");
    let args =
        crate::cmd_tunnel::build_bastion_ssh_args(8080, 8080, 50200, "azureuser", Some(key_path));
    let key_idx = args.iter().position(|a| a == "-i").expect("-i flag missing");
    assert_eq!(
        args[key_idx + 1],
        "/home/test/.ssh/azlin_key",
        "bastion SSH must include the resolved key"
    );
}

#[test]
fn test_bastion_ssh_args_no_key_flag_when_none() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(8080, 8080, 50200, "azureuser", None);
    assert!(
        !args.contains(&"-i".to_string()),
        "no -i flag when key is None"
    );
}

#[test]
fn test_bastion_ssh_args_port_forwarding_format() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(3000, 8080, 50200, "azureuser", None);
    assert!(
        args.contains(&"3000:localhost:8080".to_string()),
        "should contain -L 3000:localhost:8080, got: {:?}",
        args
    );
}

// ── Direct tunnel args retain accept-new (no regression) ───────────

#[test]
fn test_direct_ssh_args_strict_host_key_checking_accept_new() {
    let args = crate::cmd_tunnel::build_direct_ssh_args(8080, 8080, "azureuser", "10.0.0.1", None);
    assert!(
        args.contains(&"StrictHostKeyChecking=accept-new".to_string()),
        "direct tunnel must use StrictHostKeyChecking=accept-new, got: {:?}",
        args
    );
    assert!(
        !args.contains(&"StrictHostKeyChecking=no".to_string()),
        "direct tunnel must NOT use StrictHostKeyChecking=no"
    );
}

#[test]
fn test_direct_ssh_args_no_user_known_hosts_dev_null() {
    let args = crate::cmd_tunnel::build_direct_ssh_args(8080, 8080, "azureuser", "10.0.0.1", None);
    assert!(
        !args.contains(&"UserKnownHostsFile=/dev/null".to_string()),
        "direct tunnel must NOT set UserKnownHostsFile=/dev/null"
    );
}

#[test]
fn test_direct_ssh_args_connects_to_real_ip() {
    let args =
        crate::cmd_tunnel::build_direct_ssh_args(8080, 8080, "azureuser", "52.137.100.5", None);
    let last = args.last().expect("args should not be empty");
    assert_eq!(last, "azureuser@52.137.100.5");
}

#[test]
fn test_direct_ssh_args_includes_key_when_provided() {
    let key_path = std::path::Path::new("/home/test/.ssh/azlin_key");
    let args = crate::cmd_tunnel::build_direct_ssh_args(
        8080,
        8080,
        "azureuser",
        "10.0.0.1",
        Some(key_path),
    );
    assert!(args.contains(&"-i".to_string()));
    assert!(args.contains(&"/home/test/.ssh/azlin_key".to_string()));
}

// ── Tunnel state persistence ───────────────────────────────────────

#[test]
fn test_tunnel_entry_roundtrip_json() {
    let entry = crate::cmd_tunnel::TunnelEntry {
        vm_name: "test-vm".to_string(),
        local_port: 8080,
        remote_port: 3000,
        pid: 12345,
    };
    let json = serde_json::to_string(&entry).unwrap();
    let back: crate::cmd_tunnel::TunnelEntry = serde_json::from_str(&json).unwrap();
    assert_eq!(back.vm_name, "test-vm");
    assert_eq!(back.local_port, 8080);
    assert_eq!(back.remote_port, 3000);
    assert_eq!(back.pid, 12345);
}

#[test]
fn test_tunnel_entry_bastion_helper_marker() {
    // Bastion helper entries use remote_port=0 as a sentinel
    let entry = crate::cmd_tunnel::TunnelEntry {
        vm_name: "myvm__bastion__0".to_string(),
        local_port: 50200,
        remote_port: 0,
        pid: 99999,
    };
    assert_eq!(entry.remote_port, 0, "bastion helper uses remote_port=0");
    assert!(
        entry.vm_name.contains("__bastion__"),
        "bastion helper vm_name contains __bastion__ marker"
    );
}

// ── Edge cases ─────────────────────────────────────────────────────

#[test]
fn test_bastion_ssh_args_different_local_and_remote_ports() {
    let args = crate::cmd_tunnel::build_bastion_ssh_args(15432, 5432, 50202, "admin", None);
    assert!(args.contains(&"15432:localhost:5432".to_string()));
    assert_eq!(args[args.iter().position(|a| a == "-p").unwrap() + 1], "50202");
    assert!(args.last().unwrap().starts_with("admin@"));
}

#[test]
fn test_tunnel_open_help_mentions_key_flag() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tunnel", "open", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("--key"),
        "tunnel open help should document --key flag:\n{stdout}"
    );
}

#[test]
fn test_tunnel_open_help_mentions_user_flag() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tunnel", "open", "--help"])
        .timeout(std::time::Duration::from_secs(10))
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("--user"),
        "tunnel open help should document --user flag:\n{stdout}"
    );
}
