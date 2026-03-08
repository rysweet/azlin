/// Check whether a path string refers to a remote VM (e.g. `vm-name:/path`).
pub fn is_remote_path(s: &str) -> bool {
    s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
}

/// Classify the transfer direction based on source and destination strings.
pub fn classify_transfer_direction(source: &str, dest: &str) -> &'static str {
    if is_remote_path(source) && !is_remote_path(dest) {
        "remote→local"
    } else if !is_remote_path(source) && is_remote_path(dest) {
        "local→remote"
    } else {
        "local→local"
    }
}

/// Rewrite a `vm_name:path` string to `user@ip:path` for SCP.
pub fn resolve_scp_path(path: &str, vm_part: &str, user: &str, ip: &str) -> String {
    path.replacen(vm_part, &format!("{}@{}", user, ip), 1)
}
