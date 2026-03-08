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

#[cfg(test)]
mod tests {
    use super::*;

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
}
