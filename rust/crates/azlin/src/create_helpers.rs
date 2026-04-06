use super::*;

/// Generate a VM name. If a base name is given with pool > 1, appends index.
/// If no base name, generates a timestamped name.
pub fn generate_vm_name(
    base: Option<&str>,
    index: usize,
    pool_count: usize,
    timestamp: &str,
) -> String {
    match base {
        Some(n) if pool_count > 1 => format!("{}-{}", n, index + 1),
        Some(n) => n.to_string(),
        None => format!("azlin-vm-{}", timestamp),
    }
}

/// Resolve final VM size: if the user-supplied size is the default sentinel,
/// use the template override (if any), otherwise keep the user value.
pub fn resolve_with_template_default(
    user_value: &str,
    default_sentinel: &str,
    template_value: Option<String>,
) -> String {
    if user_value == default_sentinel {
        template_value.unwrap_or_else(|| user_value.to_string())
    } else {
        user_value.to_string()
    }
}

/// Build the git clone command to run on a remote VM.
///
/// Returns `Err` if the URL contains shell metacharacters.
pub fn build_clone_cmd(repo_url: &str) -> Result<String, String> {
    super::repo_helpers::validate_repo_url(repo_url)?;
    let quoted = shlex::try_quote(repo_url).map_err(|e| format!("Failed to quote URL: {e}"))?;
    Ok(format!(
        "git clone {} ~/src/$(basename {} .git)",
        quoted, quoted
    ))
}

/// Build SSH connect args (for auto-connect after VM creation).
pub fn build_ssh_connect_args(user: &str, ip: &str) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        format!("{}@{}", user, ip),
    ]
}

/// Resolve the matching private key path for a public key used during VM
/// creation, returning `None` when the derived private key is missing.
pub fn matching_private_key_for_public_key(
    public_key_path: &std::path::Path,
) -> Option<std::path::PathBuf> {
    if public_key_path.extension().and_then(|ext| ext.to_str()) != Some("pub") {
        return public_key_path
            .exists()
            .then(|| public_key_path.to_path_buf());
    }

    let private_key_path = public_key_path.with_extension("");
    private_key_path.exists().then_some(private_key_path)
}

/// Build SSH args for post-create auto-connect, preserving the same routed key
/// selection that provisioning and seeding already use.
pub fn build_auto_connect_ssh_args(
    user: &str,
    ip: &str,
    bastion_port: Option<u16>,
    connect_timeout: u64,
    identity_key: Option<&std::path::Path>,
) -> Vec<String> {
    let mut args = if let Some(port) = bastion_port {
        crate::ssh_arg_helpers::build_tunneled_ssh_prefix(user, port, connect_timeout)
    } else {
        crate::ssh_arg_helpers::build_ssh_prefix(ip, user, connect_timeout)
    };

    if let Some(key_path) = identity_key {
        crate::ssh_arg_helpers::inject_identity_key_before_destination(&mut args, key_path);
    }

    args
}

/// Generate a snapshot name for VM cloning.
pub fn build_snapshot_name(source_vm: &str, timestamp: &str) -> String {
    format!("{}_clone_snap_{}", source_vm, timestamp)
}

/// Generate a clone VM name from the source VM and replica index.
pub fn build_clone_name(source_vm: &str, index: usize) -> String {
    format!("{}-clone-{}", source_vm, index + 1)
}

/// Generate an OS disk name from a VM name.
pub fn build_disk_name(vm_name: &str) -> String {
    format!("{}_OsDisk", vm_name)
}

/// Resolve the session identity written during VM creation.
///
/// Single-VM creates use the final resolved VM name. Pooled creates keep the
/// shared base session name so existing pooled-session behavior is unchanged.
pub fn resolve_session_identity(
    requested_name: Option<&str>,
    resolved_vm_name: &str,
    pool_count: usize,
) -> String {
    if pool_count > 1 {
        requested_name
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| resolved_vm_name.to_string())
    } else {
        resolved_vm_name.to_string()
    }
}

/// Named single-VM creates seed the remote home during create.
pub fn should_seed_remote_home(requested_name: Option<&str>, pool_count: u32) -> bool {
    requested_name.is_some() && pool_count == 1
}

/// Discover the local sources used for create-time remote home seeding.
///
/// Returns `Ok(None)` when the directory is missing or empty so create-time
/// seeding can skip silently.
pub fn collect_home_seed_sources(home_sync_dir: &std::path::Path) -> Result<Option<Vec<String>>> {
    if !home_sync_dir.exists() {
        return Ok(None);
    }

    let sources: Vec<String> = std::fs::read_dir(home_sync_dir)?
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path().display().to_string())
        .collect();

    if sources.is_empty() {
        Ok(None)
    } else {
        Ok(Some(sources))
    }
}

/// Build rsync args for create-time home seeding.
pub fn build_home_seed_rsync_args(
    source_paths: &[String],
    user: &str,
    host: &str,
    ssh_transport: Option<&str>,
) -> Vec<String> {
    let mut args = vec!["-avz".to_string(), "--progress".to_string()];
    if let Some(transport) = ssh_transport {
        args.push("-e".to_string());
        args.push(transport.to_string());
    }
    args.extend(source_paths.iter().cloned());
    args.push(format!("{}@{}:~/", user, host));
    args
}

/// Seed the remote home from local `~/.azlin/home/`, returning `Ok(false)` when
/// the local source directory exists but is empty.
pub fn seed_remote_home_with_runner<F>(
    home_sync_dir: &std::path::Path,
    user: &str,
    host: &str,
    ssh_transport: Option<&str>,
    mut run_rsync: F,
) -> Result<bool>
where
    F: FnMut(&[String]) -> Result<i32>,
{
    let Some(source_paths) = collect_home_seed_sources(home_sync_dir)? else {
        return Ok(false);
    };

    let args = build_home_seed_rsync_args(&source_paths, user, host, ssh_transport);
    let exit_code = run_rsync(&args)?;
    if exit_code != 0 {
        anyhow::bail!(
            "Failed to seed remote home to '{}' (rsync exit {})",
            host,
            exit_code
        );
    }

    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_generate_vm_name_with_base_single() {
        assert_eq!(generate_vm_name(Some("myvm"), 0, 1, "20260101"), "myvm");
    }

    #[test]
    fn test_generate_vm_name_with_base_pool() {
        assert_eq!(generate_vm_name(Some("myvm"), 0, 3, "20260101"), "myvm-1");
        assert_eq!(generate_vm_name(Some("myvm"), 2, 3, "20260101"), "myvm-3");
    }

    #[test]
    fn test_generate_vm_name_no_base() {
        let name = generate_vm_name(None, 0, 1, "20260101");
        assert_eq!(name, "azlin-vm-20260101");
    }

    #[test]
    fn test_resolve_with_template_default_user_value() {
        assert_eq!(
            resolve_with_template_default(
                "Standard_D8s_v3",
                "Standard_D4s_v3",
                Some("Standard_E4s_v3".to_string())
            ),
            "Standard_D8s_v3"
        );
    }

    #[test]
    fn test_resolve_with_template_default_uses_template() {
        assert_eq!(
            resolve_with_template_default(
                "Standard_D4s_v3",
                "Standard_D4s_v3",
                Some("Standard_E4s_v3".to_string())
            ),
            "Standard_E4s_v3"
        );
    }

    #[test]
    fn test_resolve_with_template_default_no_template() {
        assert_eq!(
            resolve_with_template_default("Standard_D4s_v3", "Standard_D4s_v3", None),
            "Standard_D4s_v3"
        );
    }

    #[test]
    fn test_build_ssh_connect_args() {
        let args = build_ssh_connect_args("azureuser", "1.2.3.4");
        assert!(args.contains(&"-o".to_string()));
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"azureuser@1.2.3.4".to_string()));
    }

    #[test]
    fn test_matching_private_key_for_public_key_strips_pub_extension() {
        let temp_dir = TempDir::new().unwrap();
        let public_key = temp_dir.path().join("id_ed25519_azlin.pub");
        let private_key = temp_dir.path().join("id_ed25519_azlin");
        std::fs::write(&public_key, "pub").unwrap();
        std::fs::write(&private_key, "priv").unwrap();

        let resolved = matching_private_key_for_public_key(&public_key);
        assert_eq!(resolved.as_deref(), Some(private_key.as_path()));
    }

    #[test]
    fn test_matching_private_key_for_public_key_returns_none_when_missing() {
        let temp_dir = TempDir::new().unwrap();
        let public_key = temp_dir.path().join("azlin_key.pub");
        std::fs::write(&public_key, "pub").unwrap();

        assert!(matching_private_key_for_public_key(&public_key).is_none());
    }

    #[test]
    fn test_build_auto_connect_ssh_args_direct_includes_identity_and_timeout() {
        let key = std::path::Path::new("/home/user/.ssh/azlin_key");
        let args = build_auto_connect_ssh_args("azureuser", "1.2.3.4", None, 45, Some(key));
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"ConnectTimeout=45".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
        assert!(args.contains(&"-i".to_string()));
        assert!(args.contains(&"/home/user/.ssh/azlin_key".to_string()));
        assert!(args.contains(&"azureuser@1.2.3.4".to_string()));
    }

    #[test]
    fn test_build_auto_connect_ssh_args_bastion_uses_local_port_and_key() {
        let key = std::path::Path::new("/tmp/bastion-key");
        let args =
            build_auto_connect_ssh_args("azureuser", "127.0.0.1", Some(50210), 30, Some(key));
        assert!(args.contains(&"ConnectTimeout=30".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
        assert!(args.contains(&"-p".to_string()));
        assert!(args.contains(&"50210".to_string()));
        assert!(args.contains(&"-i".to_string()));
        assert!(args.contains(&"/tmp/bastion-key".to_string()));
        assert!(args.contains(&"azureuser@127.0.0.1".to_string()));
    }

    #[test]
    fn test_build_snapshot_name() {
        assert_eq!(
            build_snapshot_name("my-vm", "20260301"),
            "my-vm_clone_snap_20260301"
        );
    }

    #[test]
    fn test_build_clone_name() {
        assert_eq!(build_clone_name("source-vm", 0), "source-vm-clone-1");
        assert_eq!(build_clone_name("source-vm", 2), "source-vm-clone-3");
    }

    #[test]
    fn test_build_disk_name() {
        assert_eq!(build_disk_name("my-vm"), "my-vm_OsDisk");
    }

    #[test]
    fn test_resolve_session_identity_uses_resolved_name_for_named_single_vm() {
        assert_eq!(
            resolve_session_identity(Some("Simard"), "simard", 1),
            "simard"
        );
    }

    #[test]
    fn test_resolve_session_identity_preserves_pool_base_name() {
        assert_eq!(
            resolve_session_identity(Some("my-dev-pool"), "my-dev-pool-1", 3),
            "my-dev-pool"
        );
    }

    #[test]
    fn test_should_seed_remote_home_only_for_named_single_vm() {
        assert!(should_seed_remote_home(Some("Simard"), 1));
        assert!(!should_seed_remote_home(None, 1));
        assert!(!should_seed_remote_home(Some("Simard"), 2));
    }

    #[test]
    fn test_collect_home_seed_sources_returns_none_when_directory_missing() {
        let tmp = TempDir::new().unwrap();
        let missing = tmp.path().join(".azlin").join("home");
        let sources = collect_home_seed_sources(&missing).unwrap();
        assert!(sources.is_none());
    }

    #[test]
    fn test_seed_remote_home_with_runner_returns_false_when_directory_missing() {
        let tmp = TempDir::new().unwrap();
        let home_sync_dir = tmp.path().join(".azlin").join("home");

        let mut invoked = false;
        let seeded = seed_remote_home_with_runner(
            &home_sync_dir,
            "azureuser",
            "10.0.0.5",
            None,
            |_args: &[String]| {
                invoked = true;
                Ok(0)
            },
        )
        .unwrap();

        assert!(!seeded);
        assert!(
            !invoked,
            "rsync should not be invoked when the seed dir is missing"
        );
    }

    #[test]
    fn test_collect_home_seed_sources_returns_none_for_empty_directory() {
        let tmp = TempDir::new().unwrap();
        let home_sync_dir = tmp.path().join(".azlin").join("home");
        std::fs::create_dir_all(&home_sync_dir).unwrap();

        let sources = collect_home_seed_sources(&home_sync_dir).unwrap();
        assert!(sources.is_none());
    }

    #[test]
    fn test_seed_remote_home_with_runner_returns_false_for_empty_directory() {
        let tmp = TempDir::new().unwrap();
        let home_sync_dir = tmp.path().join(".azlin").join("home");
        std::fs::create_dir_all(&home_sync_dir).unwrap();

        let mut invoked = false;
        let seeded = seed_remote_home_with_runner(
            &home_sync_dir,
            "azureuser",
            "10.0.0.5",
            None,
            |_args: &[String]| {
                invoked = true;
                Ok(0)
            },
        )
        .unwrap();

        assert!(!seeded);
        assert!(
            !invoked,
            "rsync should not be invoked for an empty seed dir"
        );
    }

    #[test]
    fn test_seed_remote_home_with_runner_succeeds_with_sources() {
        let tmp = TempDir::new().unwrap();
        let home_sync_dir = tmp.path().join(".azlin").join("home");
        std::fs::create_dir_all(&home_sync_dir).unwrap();
        let gitconfig = home_sync_dir.join(".gitconfig");
        std::fs::write(&gitconfig, "[user]\nname = test\n").unwrap();

        let mut captured_args = Vec::new();
        let seeded = seed_remote_home_with_runner(
            &home_sync_dir,
            "azureuser",
            "10.0.0.5",
            Some("ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes"),
            |args: &[String]| {
                captured_args = args.to_vec();
                Ok(0)
            },
        )
        .unwrap();

        assert!(seeded);
        assert!(
            captured_args
                .iter()
                .any(|arg| arg == &gitconfig.display().to_string()),
            "expected source path in rsync args: {:?}",
            captured_args
        );
        assert!(
            captured_args
                .iter()
                .any(|arg| arg == "azureuser@10.0.0.5:~/"),
            "expected remote home destination in args: {:?}",
            captured_args
        );
    }

    #[test]
    fn test_seed_remote_home_with_runner_fails_on_rsync_error() {
        let tmp = TempDir::new().unwrap();
        let home_sync_dir = tmp.path().join(".azlin").join("home");
        std::fs::create_dir_all(&home_sync_dir).unwrap();
        std::fs::write(home_sync_dir.join(".gitconfig"), "[user]\nname = test\n").unwrap();

        let mut captured_args = Vec::new();
        let err = seed_remote_home_with_runner(
            &home_sync_dir,
            "azureuser",
            "10.0.0.5",
            Some("ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes"),
            |args: &[String]| {
                captured_args = args.to_vec();
                Ok(23)
            },
        )
        .unwrap_err();

        assert!(
            captured_args.contains(&"-e".to_string()),
            "expected rsync transport override in args: {:?}",
            captured_args
        );
        assert!(
            captured_args
                .iter()
                .any(|arg| arg == "azureuser@10.0.0.5:~/"),
            "expected remote home destination in args: {:?}",
            captured_args
        );
        assert!(
            err.to_string().contains("Failed to seed remote home"),
            "unexpected error: {err}"
        );
    }
}
