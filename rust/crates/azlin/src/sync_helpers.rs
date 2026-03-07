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

/// Build rsync argument list for the `sync` command (multiple source files,
/// `-avz --progress`, destination `user@ip:~/`).
pub fn build_sync_rsync_args<'a>(
    dotfile_paths: &'a [String],
    user: &str,
    ip: &str,
) -> (Vec<&'a str>, String) {
    let mut args: Vec<&str> = vec!["-avz", "--progress"];
    for f in dotfile_paths {
        args.push(f.as_str());
    }
    let dest = format!("{}@{}:~/", user, ip);
    (args, dest)
}

/// Format the dry-run message for the `sync` command.
pub fn format_sync_dry_run(sync_dir: &str, target_name: &str, rg: &str) -> String {
    format!("Would sync {} to {} in '{}'", sync_dir, target_name, rg)
}

/// Build the `tail` command string used to fetch remote logs.
pub fn build_tail_command(lines: u32, log_path: &str) -> String {
    format!("sudo tail -n {} {}", lines, log_path)
}

/// Map a log type name to its filesystem path on the remote VM.
pub fn log_path_for_type(log_type: &str) -> &'static str {
    match log_type {
        "cloud-init" | "CloudInit" => "/var/log/cloud-init-output.log",
        "syslog" | "Syslog" => "/var/log/syslog",
        "auth" | "Auth" => "/var/log/auth.log",
        _ => "/var/log/syslog",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── default_dotfiles ─────────────────────────────────────────

    #[test]
    fn test_default_dotfiles_nonempty() {
        let df = default_dotfiles();
        assert!(!df.is_empty());
        assert!(df.contains(&".bashrc"));
    }

    // ── validate_sync_source ─────────────────────────────────────

    #[test]
    fn test_validate_sync_source_ok() {
        assert!(validate_sync_source("/home/user/file.txt").is_ok());
        assert!(validate_sync_source("./relative").is_ok());
    }

    #[test]
    fn test_validate_sync_source_forbidden() {
        assert!(validate_sync_source("/etc/passwd").is_err());
        assert!(validate_sync_source("/var/secret").is_err());
        assert!(validate_sync_source("/proc/1/maps").is_err());
    }

    #[test]
    fn test_validate_sync_source_traversal() {
        assert!(validate_sync_source("foo/../../../etc").is_err());
        assert!(validate_sync_source("foo/..").is_err());
        assert!(validate_sync_source("..").is_err());
    }

    // ── build_rsync_args ─────────────────────────────────────────

    #[test]
    fn test_build_rsync_args_structure() {
        let args = build_rsync_args("/tmp/file", "admin", "10.0.0.1", "dest");
        assert_eq!(args.len(), 5);
        assert_eq!(args[0], "-az");
        assert!(args[2].contains("StrictHostKeyChecking"));
        assert_eq!(args[3], "/tmp/file");
        assert_eq!(args[4], "admin@10.0.0.1:~/dest");
    }

    // ── build_sync_rsync_args ────────────────────────────────────

    #[test]
    fn test_build_sync_rsync_args_structure() {
        let files = vec!["/home/u/.bashrc".to_string(), "/home/u/.vimrc".to_string()];
        let (args, dest) = build_sync_rsync_args(&files, "admin", "10.0.0.1");
        assert_eq!(args[0], "-avz");
        assert_eq!(args[1], "--progress");
        assert_eq!(args[2], "/home/u/.bashrc");
        assert_eq!(args[3], "/home/u/.vimrc");
        assert_eq!(dest, "admin@10.0.0.1:~/");
    }

    #[test]
    fn test_build_sync_rsync_args_empty_files() {
        let files: Vec<String> = vec![];
        let (args, dest) = build_sync_rsync_args(&files, "u", "1.2.3.4");
        assert_eq!(args.len(), 2); // just -avz and --progress
        assert_eq!(dest, "u@1.2.3.4:~/");
    }

    // ── format_sync_dry_run ──────────────────────────────────────

    #[test]
    fn test_format_sync_dry_run_all() {
        let msg = format_sync_dry_run("/home/u/.azlin/home", "all VMs", "my-rg");
        assert!(msg.contains("/home/u/.azlin/home"));
        assert!(msg.contains("all VMs"));
        assert!(msg.contains("my-rg"));
    }

    #[test]
    fn test_format_sync_dry_run_single() {
        let msg = format_sync_dry_run("/dir", "vm-01", "rg1");
        assert!(msg.contains("vm-01"));
    }

    // ── build_tail_command ───────────────────────────────────────

    #[test]
    fn test_build_tail_command_basic() {
        let cmd = build_tail_command(100, "/var/log/syslog");
        assert_eq!(cmd, "sudo tail -n 100 /var/log/syslog");
    }

    #[test]
    fn test_build_tail_command_custom_lines() {
        let cmd = build_tail_command(500, "/var/log/auth.log");
        assert!(cmd.contains("500"));
        assert!(cmd.contains("/var/log/auth.log"));
    }

    // ── log_path_for_type ────────────────────────────────────────

    #[test]
    fn test_log_path_for_type_cloud_init() {
        assert_eq!(
            log_path_for_type("CloudInit"),
            "/var/log/cloud-init-output.log"
        );
        assert_eq!(
            log_path_for_type("cloud-init"),
            "/var/log/cloud-init-output.log"
        );
    }

    #[test]
    fn test_log_path_for_type_syslog() {
        assert_eq!(log_path_for_type("Syslog"), "/var/log/syslog");
        assert_eq!(log_path_for_type("syslog"), "/var/log/syslog");
    }

    #[test]
    fn test_log_path_for_type_auth() {
        assert_eq!(log_path_for_type("Auth"), "/var/log/auth.log");
        assert_eq!(log_path_for_type("auth"), "/var/log/auth.log");
    }

    #[test]
    fn test_log_path_for_type_unknown_defaults() {
        assert_eq!(log_path_for_type("something"), "/var/log/syslog");
    }
}
