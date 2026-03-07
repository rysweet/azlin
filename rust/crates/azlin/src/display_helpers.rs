/// Render a serde_json::Value as a user-friendly string for config display.
/// `Null` → `"null"`, `String` → the raw string, everything else → its JSON representation.
#[allow(dead_code)]
pub fn config_value_display(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Null => "null".to_string(),
        other => other.to_string(),
    }
}

/// Truncate a VM name to `max_len` characters, appending "..." if truncated.
/// Returns the name unchanged if it fits within `max_len`.
pub fn truncate_vm_name(name: &str, max_len: usize) -> String {
    if name.len() > max_len && max_len > 3 {
        let truncated: String = name.chars().take(max_len.saturating_sub(3)).collect();
        format!("{}...", truncated)
    } else {
        name.to_string()
    }
}

/// Format a list of tmux session names for display, collapsing long lists.
/// If the list has more than `max_show` entries, the remainder is summarised
/// as `"+N more"`.
pub fn format_tmux_sessions(sessions: &[String], max_show: usize) -> String {
    if sessions.is_empty() {
        "-".to_string()
    } else if sessions.len() <= max_show {
        sessions.join(", ")
    } else {
        format!(
            "{}, +{} more",
            sessions[..max_show].join(", "),
            sessions.len() - max_show,
        )
    }
}

/// Format the reconnect prompt message for SSH auto-reconnect.
#[allow(dead_code)]
pub fn reconnect_prompt(attempt: u32, max_retries: u32) -> String {
    format!(
        "SSH disconnected. Reconnect? (attempt {}/{}) [Y/n] ",
        attempt, max_retries,
    )
}

/// Format OS offer string into a human-readable distro name.
pub fn format_os_display(os_offer: Option<&str>, os_type: &azlin_core::models::OsType) -> String {
    if let Some(offer) = os_offer {
        let lower = offer.to_lowercase();
        if lower.contains("ubuntu") {
            return format_ubuntu_offer(offer);
        }
        if lower.contains("debian") {
            return "Debian".to_string();
        }
        if lower.contains("rhel") {
            return "RHEL".to_string();
        }
        if lower.contains("centos") {
            return "CentOS".to_string();
        }
        if lower.contains("sles") || lower.contains("suse") {
            return "SUSE".to_string();
        }
        if lower.contains("alma") {
            return "AlmaLinux".to_string();
        }
        if lower.contains("rocky") {
            return "Rocky Linux".to_string();
        }
        if lower.contains("windowsserver") || lower.contains("windows") {
            return "Windows".to_string();
        }
        return offer.to_string();
    }
    match os_type {
        azlin_core::models::OsType::Windows => "Windows".to_string(),
        _ => "Linux".to_string(),
    }
}

/// Parse Ubuntu offer strings into human-readable format.
/// Handles multiple Azure offer formats:
///   "ubuntu-24_04-lts" -> "Ubuntu 24.04 LTS"
///   "ubuntu-25_10" -> "Ubuntu 25.10"
///   "0001-com-ubuntu-server-jammy" -> "Ubuntu 22.04 LTS"
fn format_ubuntu_offer(offer: &str) -> String {
    let lower = offer.to_lowercase();

    // Try version format: ubuntu-XX_YY[-lts]
    // Strip common prefixes
    let stripped = lower
        .strip_prefix("ubuntu-")
        .or_else(|| {
            // Handle 0001-com-ubuntu-* format
            lower.find("ubuntu-").map(|i| &lower[i + 7..])
        })
        .unwrap_or(&lower);

    let is_lts = stripped.contains("lts");
    let version_part = stripped
        .replace("-lts", "")
        .replace("_lts", "")
        .replace("-gen1", "")
        .replace("-gen2", "");

    // Parse XX_YY -> XX.YY
    if let Some((major, minor)) = version_part.split_once('_') {
        if major.chars().all(|c| c.is_numeric()) {
            let suffix = if is_lts { " LTS" } else { "" };
            return format!("Ubuntu {}.{}{}", major, minor, suffix);
        }
    }

    // Codename fallback — search the ENTIRE offer string for codenames
    if lower.contains("plucky") {
        return "Ubuntu 25.04".to_string();
    }
    if lower.contains("oracular") {
        return "Ubuntu 24.10".to_string();
    }
    if lower.contains("noble") {
        return "Ubuntu 24.04 LTS".to_string();
    }
    if lower.contains("jammy") {
        return "Ubuntu 22.04 LTS".to_string();
    }
    if lower.contains("focal") {
        return "Ubuntu 20.04 LTS".to_string();
    }
    if lower.contains("bionic") {
        return "Ubuntu 18.04 LTS".to_string();
    }

    format!("Ubuntu ({})", offer)
}

/// Format IP display with annotation (Pub/Bast/N/A).
pub fn format_ip_display(public_ip: Option<&str>, private_ip: Option<&str>) -> String {
    if let Some(pub_ip) = public_ip {
        format!("{} (Pub)", pub_ip)
    } else if let Some(priv_ip) = private_ip {
        format!("{} (Bast)", priv_ip)
    } else {
        "N/A".to_string()
    }
}

/// Extract vCPU count and estimated memory from Azure VM size name.
/// e.g. "Standard_D4s_v3" -> ("4", "16 GB")
/// This is the fallback used when `az vm list-sizes` is unavailable.
pub fn parse_vm_size_specs(vm_size: &str) -> (String, String) {
    let parts: Vec<&str> = vm_size.split('_').collect();
    if parts.len() >= 2 {
        let size_part = parts[1]; // e.g., "D4s" or "E16as"
        let vcpus: String = size_part
            .chars()
            .skip_while(|c| c.is_alphabetic())
            .take_while(|c| c.is_numeric())
            .collect();
        if let Ok(cpu_count) = vcpus.parse::<u32>() {
            let mem_gb = estimate_memory_gb(size_part, cpu_count);
            return (format!("{}", cpu_count), format!("{} GB", mem_gb));
        }
    }
    ("-".to_string(), "-".to_string())
}

/// Estimate memory in GB based on VM family letter and vCPU count.
fn estimate_memory_gb(size_part: &str, vcpus: u32) -> u32 {
    let family = size_part.chars().next().unwrap_or('D');
    match family.to_ascii_uppercase() {
        'E' => vcpus * 8,          // E-series: memory optimized
        'M' => vcpus * 16,         // M-series: memory optimized (large)
        'F' => (vcpus * 2).max(1), // F-series: compute optimized
        'L' => vcpus * 8,          // L-series: storage optimized
        'N' => vcpus * 6,          // N-series: GPU
        'B' => (vcpus * 4).max(1), // B-series: burstable
        _ => vcpus * 4,            // D-series and default
    }
}

/// Per-location cache of VM size specs: Vec<(name, cores, mem_mb)>.
type VmSizeEntry = (String, u32, u32);
type VmSizeCacheMap = std::collections::HashMap<String, Vec<VmSizeEntry>>;
static VM_SIZE_CACHE: std::sync::LazyLock<std::sync::Mutex<VmSizeCacheMap>> =
    std::sync::LazyLock::new(|| std::sync::Mutex::new(std::collections::HashMap::new()));

#[cfg(test)]
mod tests {
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
}

/// Query exact vCPU and memory specs via `az vm list-sizes`.
/// Results are cached per location. Falls back to `parse_vm_size_specs`
/// if the az CLI query fails or the size is not found.
pub fn query_vm_size_specs(vm_size: &str, location: &str) -> (String, String) {
    let mut cache = VM_SIZE_CACHE.lock().unwrap_or_else(|e| e.into_inner());

    if !cache.contains_key(location) {
        if let Ok((code, stdout, _stderr)) = azlin_azure::run_with_timeout(
            "az",
            &[
                "vm",
                "list-sizes",
                "--location",
                location,
                "--output",
                "json",
            ],
            30,
        ) {
            if code == 0 {
                if let Ok(sizes) = serde_json::from_str::<Vec<serde_json::Value>>(&stdout) {
                    let entries: Vec<(String, u32, u32)> = sizes
                        .iter()
                        .filter_map(|s| {
                            let name = s["name"].as_str()?.to_string();
                            let cores = s["numberOfCores"].as_u64()? as u32;
                            let mem_mb = s["memoryInMB"].as_u64()? as u32;
                            Some((name, cores, mem_mb))
                        })
                        .collect();
                    cache.insert(location.to_string(), entries);
                }
            }
        }
    }

    // Look up the specific size in cached data
    if let Some(sizes) = cache.get(location) {
        if let Some((_, cores, mem_mb)) = sizes.iter().find(|(name, _, _)| name == vm_size) {
            let mem_gb = mem_mb / 1024;
            return (format!("{}", cores), format!("{} GB", mem_gb));
        }
    }

    // Fallback to heuristic estimate if query fails
    parse_vm_size_specs(vm_size)
}
