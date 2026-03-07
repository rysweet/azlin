use super::*;

#[test]
fn test_config_value_display_string() {
    let v = serde_json::json!("hello");
    assert_eq!(config_value_display(&v), "hello");
}

#[test]
fn test_config_value_display_null() {
    let v = serde_json::Value::Null;
    assert_eq!(config_value_display(&v), "null");
}

#[test]
fn test_config_value_display_number() {
    let v = serde_json::json!(42);
    assert_eq!(config_value_display(&v), "42");
}

#[test]
fn test_config_value_display_bool() {
    let v = serde_json::json!(true);
    assert_eq!(config_value_display(&v), "true");
}

#[test]
fn test_truncate_vm_name_short() {
    assert_eq!(truncate_vm_name("abc", 10), "abc");
}

#[test]
fn test_truncate_vm_name_exact() {
    assert_eq!(truncate_vm_name("abcde", 5), "abcde");
}

#[test]
fn test_truncate_vm_name_long() {
    assert_eq!(truncate_vm_name("abcdefghij", 7), "abcd...");
}

#[test]
fn test_truncate_vm_name_max_len_3() {
    // max_len <= 3 returns as-is
    assert_eq!(truncate_vm_name("abcdefg", 3), "abcdefg");
}

#[test]
fn test_format_tmux_sessions_empty() {
    let sessions: Vec<String> = vec![];
    assert_eq!(format_tmux_sessions(&sessions, 3), "-");
}

#[test]
fn test_format_tmux_sessions_few() {
    let sessions = vec!["s1".to_string(), "s2".to_string()];
    assert_eq!(format_tmux_sessions(&sessions, 3), "s1, s2");
}

#[test]
fn test_format_tmux_sessions_many() {
    let sessions = vec![
        "a".to_string(),
        "b".to_string(),
        "c".to_string(),
        "d".to_string(),
    ];
    let out = format_tmux_sessions(&sessions, 2);
    assert!(out.contains("a, b"));
    assert!(out.contains("+2 more"));
}

#[test]
fn test_reconnect_prompt() {
    let out = reconnect_prompt(2, 5);
    assert!(out.contains("2/5"));
    assert!(out.contains("Reconnect"));
}

#[test]
fn test_format_os_display_ubuntu() {
    assert_eq!(
        format_os_display(Some("UbuntuServer"), &azlin_core::models::OsType::Linux),
        "Ubuntu (UbuntuServer)"
    );
}

#[test]
fn test_format_os_display_ubuntu_jammy() {
    assert_eq!(
        format_os_display(
            Some("0001-com-ubuntu-server-jammy"),
            &azlin_core::models::OsType::Linux
        ),
        "Ubuntu 22.04 LTS"
    );
}

#[test]
fn test_format_os_display_ubuntu_version() {
    assert_eq!(
        format_os_display(Some("ubuntu-24_04-lts"), &azlin_core::models::OsType::Linux),
        "Ubuntu 24.04 LTS"
    );
}

#[test]
fn test_format_os_display_ubuntu_non_lts() {
    assert_eq!(
        format_os_display(Some("ubuntu-25_10"), &azlin_core::models::OsType::Linux),
        "Ubuntu 25.10"
    );
}

#[test]
fn test_format_os_display_debian() {
    assert_eq!(
        format_os_display(Some("Debian"), &azlin_core::models::OsType::Linux),
        "Debian"
    );
}

#[test]
fn test_format_os_display_rhel() {
    assert_eq!(
        format_os_display(Some("RHEL"), &azlin_core::models::OsType::Linux),
        "RHEL"
    );
}

#[test]
fn test_format_os_display_centos() {
    assert_eq!(
        format_os_display(Some("CentOS"), &azlin_core::models::OsType::Linux),
        "CentOS"
    );
}

#[test]
fn test_format_os_display_suse() {
    assert_eq!(
        format_os_display(Some("SLES-15"), &azlin_core::models::OsType::Linux),
        "SUSE"
    );
}

#[test]
fn test_format_os_display_alma() {
    assert_eq!(
        format_os_display(Some("AlmaLinux"), &azlin_core::models::OsType::Linux),
        "AlmaLinux"
    );
}

#[test]
fn test_format_os_display_rocky() {
    assert_eq!(
        format_os_display(Some("RockyLinux"), &azlin_core::models::OsType::Linux),
        "Rocky Linux"
    );
}

#[test]
fn test_format_os_display_windows_offer() {
    assert_eq!(
        format_os_display(Some("WindowsServer"), &azlin_core::models::OsType::Windows),
        "Windows"
    );
}

#[test]
fn test_format_os_display_none_linux() {
    assert_eq!(
        format_os_display(None, &azlin_core::models::OsType::Linux),
        "Linux"
    );
}

#[test]
fn test_format_os_display_none_windows() {
    assert_eq!(
        format_os_display(None, &azlin_core::models::OsType::Windows),
        "Windows"
    );
}

#[test]
fn test_format_os_display_unknown_offer() {
    assert_eq!(
        format_os_display(Some("CustomImage"), &azlin_core::models::OsType::Linux),
        "CustomImage"
    );
}

#[test]
fn test_format_os_display_noble() {
    let out = format_os_display(
        Some("0001-com-ubuntu-server-noble"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(out, "Ubuntu 24.04 LTS");
}

#[test]
fn test_format_os_display_focal() {
    let out = format_os_display(
        Some("0001-com-ubuntu-server-focal"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(out, "Ubuntu 20.04 LTS");
}

#[test]
fn test_format_os_display_bionic() {
    let out = format_os_display(
        Some("0001-com-ubuntu-server-bionic"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(out, "Ubuntu 18.04 LTS");
}

#[test]
fn test_format_os_display_plucky() {
    let out = format_os_display(
        Some("0001-com-ubuntu-server-plucky"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(out, "Ubuntu 25.04");
}

#[test]
fn test_format_os_display_oracular() {
    let out = format_os_display(
        Some("0001-com-ubuntu-server-oracular"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(out, "Ubuntu 24.10");
}

#[test]
fn test_format_ip_display_with_public() {
    assert_eq!(
        format_ip_display(Some("1.2.3.4"), Some("10.0.0.1")),
        "1.2.3.4 (Pub)"
    );
}

#[test]
fn test_format_ip_display_private_only() {
    assert_eq!(format_ip_display(None, Some("10.0.0.1")), "10.0.0.1 (Bast)");
}

#[test]
fn test_format_ip_display_none() {
    assert_eq!(format_ip_display(None, None), "N/A");
}

#[test]
fn test_parse_vm_size_specs_d4s() {
    let (cpu, mem) = parse_vm_size_specs("Standard_D4s_v3");
    assert_eq!(cpu, "4");
    assert_eq!(mem, "16 GB");
}

#[test]
fn test_parse_vm_size_specs_e16() {
    let (cpu, mem) = parse_vm_size_specs("Standard_E16as_v5");
    assert_eq!(cpu, "16");
    assert_eq!(mem, "128 GB"); // E-series: 16 * 8
}

#[test]
fn test_parse_vm_size_specs_f2() {
    let (cpu, mem) = parse_vm_size_specs("Standard_F2s_v2");
    assert_eq!(cpu, "2");
    assert_eq!(mem, "4 GB"); // F-series: 2 * 2
}

#[test]
fn test_parse_vm_size_specs_b1() {
    let (cpu, mem) = parse_vm_size_specs("Standard_B1s");
    assert_eq!(cpu, "1");
    assert_eq!(mem, "4 GB"); // B-series: 1 * 4
}

#[test]
fn test_parse_vm_size_specs_unknown() {
    let (cpu, mem) = parse_vm_size_specs("weird");
    assert_eq!(cpu, "-");
    assert_eq!(mem, "-");
}

#[test]
fn test_parse_vm_size_specs_m_series() {
    let (cpu, mem) = parse_vm_size_specs("Standard_M8ms_v2");
    assert_eq!(cpu, "8");
    assert_eq!(mem, "128 GB"); // M-series: 8 * 16
}

#[test]
fn test_parse_vm_size_specs_n_series() {
    let (cpu, mem) = parse_vm_size_specs("Standard_N6");
    assert_eq!(cpu, "6");
    assert_eq!(mem, "36 GB"); // N-series: 6 * 6
}

#[test]
fn test_parse_vm_size_specs_l_series() {
    let (cpu, mem) = parse_vm_size_specs("Standard_L8s_v3");
    assert_eq!(cpu, "8");
    assert_eq!(mem, "64 GB"); // L-series: 8 * 8
}
