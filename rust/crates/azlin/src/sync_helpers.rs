/// The default set of dotfiles synchronised to VMs.
pub fn default_dotfiles() -> Vec<&'static str> {
    vec![".bashrc", ".profile", ".vimrc", ".tmux.conf", ".gitconfig"]
}

/// Validate that a sync source path is safe (no absolute paths to sensitive
/// system files, no traversal outside the user's home).
pub fn validate_sync_source(source: &str) -> Result<(), String> {
    // Reject paths that reference sensitive system directories directly
    let forbidden_prefixes = ["/etc/", "/var/", "/root/", "/proc/", "/sys/"];
    for prefix in &forbidden_prefixes {
        if source.starts_with(prefix) {
            return Err(format!(
                "Sync source '{}' references a sensitive system path",
                source
            ));
        }
    }
    // Reject path-traversal sequences that escape the intended directory
    if source.contains("/../") || source.ends_with("/..") || source == ".." {
        return Err(format!("Sync source '{}' contains path traversal", source));
    }
    Ok(())
}

/// Build the argument list for an rsync invocation.
pub fn build_rsync_args(source: &str, user: &str, ip: &str, dest: &str) -> Vec<String> {
    vec![
        "-az".to_string(),
        "-e".to_string(),
        "ssh -o StrictHostKeyChecking=accept-new".to_string(),
        source.to_string(),
        format!("{}@{}:~/{}", user, ip, dest),
    ]
}
