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

/// Query exact vCPU and memory specs via `az vm list-sizes`.
/// Results are cached per location. Falls back to `parse_vm_size_specs`
/// if the az CLI query fails or the size is not found.
pub fn query_vm_size_specs(vm_size: &str, location: &str) -> (String, String) {
    let mut cache = VM_SIZE_CACHE.lock().unwrap_or_else(|e| e.into_inner());

    if !cache.contains_key(location) {
        if let Ok((code, stdout, _stderr)) = azlin_azure::run_with_timeout(
            "az",
            &["vm", "list-sizes", "--location", location, "--output", "json"],
            30,
        ) {
            if code == 0 {
                if let Ok(sizes) =
                    serde_json::from_str::<Vec<serde_json::Value>>(&stdout)
                {
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
