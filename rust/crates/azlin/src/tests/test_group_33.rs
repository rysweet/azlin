// ── create_helpers tests ────────────────────────────────────────

#[test]
fn test_generate_vm_name_with_base_pool_1() {
    let name = crate::create_helpers::generate_vm_name(Some("my-vm"), 0, 1, "20240101");
    assert_eq!(name, "my-vm");
}

#[test]
fn test_generate_vm_name_with_base_pool_multiple() {
    let n1 = crate::create_helpers::generate_vm_name(Some("my-vm"), 0, 3, "20240101");
    let n2 = crate::create_helpers::generate_vm_name(Some("my-vm"), 1, 3, "20240101");
    let n3 = crate::create_helpers::generate_vm_name(Some("my-vm"), 2, 3, "20240101");
    assert_eq!(n1, "my-vm-1");
    assert_eq!(n2, "my-vm-2");
    assert_eq!(n3, "my-vm-3");
}

#[test]
fn test_generate_vm_name_no_base_uses_timestamp() {
    let name = crate::create_helpers::generate_vm_name(None, 0, 1, "20240315-120000");
    assert_eq!(name, "azlin-vm-20240315-120000");
}

#[test]
fn test_resolve_with_template_default_user_value() {
    let result = crate::create_helpers::resolve_with_template_default(
        "Standard_D8s_v3",
        "Standard_D4s_v3",
        Some("Standard_D2s_v3".to_string()),
    );
    assert_eq!(result, "Standard_D8s_v3");
}

#[test]
fn test_resolve_with_template_default_uses_template() {
    let result = crate::create_helpers::resolve_with_template_default(
        "Standard_D4s_v3",
        "Standard_D4s_v3",
        Some("Standard_D16s_v3".to_string()),
    );
    assert_eq!(result, "Standard_D16s_v3");
}

#[test]
fn test_resolve_with_template_default_no_template() {
    let result = crate::create_helpers::resolve_with_template_default(
        "Standard_D4s_v3",
        "Standard_D4s_v3",
        None,
    );
    assert_eq!(result, "Standard_D4s_v3");
}

#[test]
fn test_build_clone_cmd_https() {
    let cmd = crate::create_helpers::build_clone_cmd("https://github.com/user/repo.git").unwrap();
    assert!(cmd.contains("git clone"));
    assert!(cmd.contains("https://github.com/user/repo.git"));
    assert!(cmd.contains("~/src/$(basename"));
}

#[test]
fn test_build_ssh_connect_args() {
    let args = crate::create_helpers::build_ssh_connect_args("azureuser", "10.0.0.1");
    assert_eq!(
        args,
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "azureuser@10.0.0.1".to_string(),
        ]
    );
}

#[test]
fn test_create_build_snapshot_name() {
    let name = crate::create_helpers::build_snapshot_name("my-vm", "20240315");
    assert_eq!(name, "my-vm_clone_snap_20240315");
}

#[test]
fn test_build_clone_name() {
    assert_eq!(
        crate::create_helpers::build_clone_name("source-vm", 0),
        "source-vm-clone-1"
    );
    assert_eq!(
        crate::create_helpers::build_clone_name("source-vm", 4),
        "source-vm-clone-5"
    );
}

#[test]
fn test_build_disk_name() {
    assert_eq!(
        crate::create_helpers::build_disk_name("my-vm"),
        "my-vm_OsDisk"
    );
}

// ── connect_helpers tests ───────────────────────────────────────

#[test]
fn test_build_ssh_args_without_key() {
    let args = crate::connect_helpers::build_ssh_args("azureuser", "10.0.0.5", None);
    assert_eq!(
        args,
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "azureuser@10.0.0.5".to_string(),
        ]
    );
}

#[test]
fn test_build_ssh_args_with_key() {
    use std::path::Path;
    let key = Path::new("/home/user/.ssh/id_ed25519");
    let args = crate::connect_helpers::build_ssh_args("admin", "192.168.1.1", Some(key));
    assert_eq!(
        args,
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "-i".to_string(),
            "/home/user/.ssh/id_ed25519".to_string(),
            "admin@192.168.1.1".to_string(),
        ]
    );
}

#[test]
fn test_build_vscode_remote_uri() {
    let uri = crate::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_build_log_follow_args() {
    let args = crate::connect_helpers::build_log_follow_args(
        "azureuser",
        "10.0.0.5",
        "/var/log/syslog",
        10,
    );
    assert_eq!(args.len(), 6);
    assert_eq!(args[4], "azureuser@10.0.0.5");
    assert_eq!(args[5], "sudo tail -f /var/log/syslog");
}

#[test]
fn test_build_log_tail_args() {
    let args = crate::connect_helpers::build_log_tail_args(
        "admin",
        "10.0.0.1",
        100,
        "/var/log/auth.log",
        10,
    );
    assert_eq!(args.len(), 6);
    assert!(args[5].contains("tail -n 100"));
    assert!(args[5].contains("/var/log/auth.log"));
}

// ── update_helpers tests ────────────────────────────────────────

#[test]
fn test_build_dev_update_script_contains_sections() {
    let script = crate::update_helpers::build_dev_update_script();
    assert!(script.starts_with("#!/bin/bash"));
    assert!(script.contains("set -e"));
    assert!(script.contains("apt-get update"));
    assert!(script.contains("rustup update"));
    assert!(script.contains("pip3 install"));
    assert!(script.contains("npm install"));
}

#[test]
fn test_build_os_update_cmd() {
    let cmd = crate::update_helpers::build_os_update_cmd();
    assert!(cmd.contains("apt-get update"));
    assert!(cmd.contains("apt-get upgrade"));
    assert!(cmd.contains("DEBIAN_FRONTEND=noninteractive"));
}

#[test]
fn test_log_type_to_path_cloud_init() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("cloud-init"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
}

#[test]
fn test_log_type_to_path_syslog() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
}

#[test]
fn test_log_type_to_path_auth() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("auth"),
        "/var/log/auth.log"
    );
    assert_eq!(
        crate::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
}

#[test]
fn test_log_type_to_path_unknown_defaults_syslog() {
    assert_eq!(
        crate::update_helpers::log_type_to_path("something-else"),
        "/var/log/syslog"
    );
}

// ── compose_helpers tests ───────────────────────────────────────

#[test]
fn test_resolve_compose_file_default() {
    let f = crate::compose_helpers::resolve_compose_file(None);
    assert_eq!(f, "docker-compose.yml");
}

#[test]
fn test_resolve_compose_file_custom() {
    let f = crate::compose_helpers::resolve_compose_file(Some("compose.prod.yaml"));
    assert_eq!(f, "compose.prod.yaml");
}

#[test]
fn test_build_compose_cmd_up() {
    let cmd = crate::compose_helpers::build_compose_cmd("up -d", "docker-compose.yml");
    assert_eq!(cmd, "docker compose -f docker-compose.yml up -d");
}

#[test]
fn test_build_compose_cmd_down() {
    let cmd = crate::compose_helpers::build_compose_cmd("down", "compose.prod.yaml");
    assert_eq!(cmd, "docker compose -f compose.prod.yaml down");
}
