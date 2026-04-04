fn common_ssh_options(connect_timeout: u64) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
    ]
}

/// Build SSH args without a remote command, ending at `user@host`.
pub fn build_ssh_prefix(ip: &str, user: &str, connect_timeout: u64) -> Vec<String> {
    let mut args = common_ssh_options(connect_timeout);
    args.push(format!("{}@{}", user, ip));
    args
}

/// Build SSH args for a local tunneled target, ending at `user@127.0.0.1`.
pub fn build_tunneled_ssh_prefix(user: &str, local_port: u16, connect_timeout: u64) -> Vec<String> {
    let mut args = common_ssh_options(connect_timeout);
    args.push("-p".to_string());
    args.push(local_port.to_string());
    args.push(format!("{}@127.0.0.1", user));
    args
}

/// Build the argument list for a direct SSH command.
/// Returns the args that would be passed to `ssh`.
/// `connect_timeout` is the SSH ConnectTimeout in seconds.
pub fn build_ssh_args(ip: &str, user: &str, cmd: &str, connect_timeout: u64) -> Vec<String> {
    let mut args = build_ssh_prefix(ip, user, connect_timeout);
    args.push(cmd.to_string());
    args
}

/// Inject `-i <key_path>` into an SSH args vector before the `user@host` argument.
///
/// The key is inserted at `len - 2` (or position 0 if len < 2) so the final
/// order is typically: `[options...] -i <key> user@host command`
///
/// # Panics (debug builds only)
///
/// Debug-asserts that `args.len() >= 2`. Release builds handle short vectors
/// gracefully via `saturating_sub`.
pub fn inject_identity_key(args: &mut Vec<String>, key_path: &std::path::Path) {
    debug_assert!(
        args.len() >= 2,
        "SSH args must contain at least user@host and command"
    );
    let insert_pos = args.len().saturating_sub(2);
    args.insert(insert_pos, key_path.display().to_string());
    args.insert(insert_pos, "-i".to_string());
}

/// Inject `-i <key_path>` into an SSH prefix vector before the destination
/// argument, where the last element is `user@host`.
pub fn inject_identity_key_before_destination(args: &mut Vec<String>, key_path: &std::path::Path) {
    debug_assert!(
        !args.is_empty(),
        "SSH prefix must contain at least a destination argument"
    );
    let insert_pos = args.len().saturating_sub(1);
    args.insert(insert_pos, key_path.display().to_string());
    args.insert(insert_pos, "-i".to_string());
}

/// Build the argument list for an `az network bastion ssh` command.
/// Returns the args that would be passed to `az`.
pub fn build_bastion_ssh_args<'a>(
    bastion_name: &'a str,
    resource_group: &'a str,
    vm_resource_id: &'a str,
    user: &'a str,
    ssh_key: Option<&'a str>,
    cmd: &'a str,
) -> Vec<String> {
    let mut args = vec![
        "network".to_string(),
        "bastion".to_string(),
        "ssh".to_string(),
        "--name".to_string(),
        bastion_name.to_string(),
        "--resource-group".to_string(),
        resource_group.to_string(),
        "--target-resource-id".to_string(),
        vm_resource_id.to_string(),
        "--auth-type".to_string(),
        "ssh-key".to_string(),
        "--username".to_string(),
        user.to_string(),
    ];
    if let Some(key) = ssh_key {
        args.push("--ssh-key".to_string());
        args.push(key.to_string());
    }
    args.push("--".to_string());
    args.push(cmd.to_string());
    args
}

/// Build the Azure VM resource ID from its components.
pub fn build_vm_resource_id(subscription_id: &str, resource_group: &str, vm_name: &str) -> String {
    format!(
        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
        subscription_id, resource_group, vm_name
    )
}

/// Classify an agent-status string from `systemctl is-active`.
pub fn classify_agent_status(raw: &str) -> &'static str {
    let trimmed = raw.trim();
    if trimmed == "active" {
        "OK"
    } else if trimmed == "inactive" {
        "Down"
    } else {
        "N/A"
    }
}

/// Determine the IP address to use for SSH, preferring public over private.
/// Returns empty string if neither is available.
pub fn pick_ssh_ip(public_ip: Option<&str>, private_ip: Option<&str>) -> String {
    public_ip.or(private_ip).unwrap_or("").to_string()
}

/// Whether a VM needs bastion routing (has no public IP).
pub fn needs_bastion(public_ip: Option<&str>) -> bool {
    public_ip.is_none()
}

#[cfg(test)]
mod tests {
    use super::*;

    // -- build_ssh_args --

    #[test]
    fn ssh_args_contain_user_at_ip() {
        let args = build_ssh_args("10.0.0.1", "azureuser", "uptime", 10);
        assert!(args.contains(&"azureuser@10.0.0.1".to_string()));
        assert_eq!(args.last().unwrap(), "uptime");
    }

    #[test]
    fn ssh_args_have_security_options() {
        let args = build_ssh_args("1.2.3.4", "admin", "ls", 10);
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"ConnectTimeout=10".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
    }

    #[test]
    fn ssh_args_use_custom_timeout() {
        let args = build_ssh_args("1.2.3.4", "admin", "ls", 30);
        assert!(args.contains(&"ConnectTimeout=30".to_string()));
    }

    #[test]
    fn ssh_args_count() {
        let args = build_ssh_args("1.2.3.4", "user", "cmd", 10);
        // 3 -o pairs (6 args) + user@ip + cmd = 8
        assert_eq!(args.len(), 8);
    }

    // -- build_bastion_ssh_args --

    #[test]
    fn bastion_args_without_key() {
        let args = build_bastion_ssh_args(
            "my-bastion",
            "my-rg",
            "/sub/123/vm",
            "azureuser",
            None,
            "uptime",
        );
        assert!(args.contains(&"my-bastion".to_string()));
        assert!(args.contains(&"my-rg".to_string()));
        assert!(args.contains(&"/sub/123/vm".to_string()));
        assert!(args.contains(&"azureuser".to_string()));
        assert!(!args.contains(&"--ssh-key".to_string()));
        // Last two should be "--" and "uptime"
        let len = args.len();
        assert_eq!(args[len - 2], "--");
        assert_eq!(args[len - 1], "uptime");
    }

    #[test]
    fn bastion_args_with_key() {
        let args = build_bastion_ssh_args(
            "bastion",
            "rg",
            "/rid",
            "user",
            Some("/home/u/.ssh/id_rsa"),
            "ls",
        );
        assert!(args.contains(&"--ssh-key".to_string()));
        assert!(args.contains(&"/home/u/.ssh/id_rsa".to_string()));
    }

    #[test]
    fn bastion_args_end_with_separator_and_cmd() {
        let args = build_bastion_ssh_args("b", "rg", "/r", "u", None, "whoami");
        let separator_idx = args.iter().position(|a| a == "--").unwrap();
        assert_eq!(args[separator_idx + 1], "whoami");
    }

    // -- build_vm_resource_id --

    #[test]
    fn resource_id_format() {
        let rid = build_vm_resource_id("sub-123", "my-rg", "my-vm");
        assert_eq!(
            rid,
            "/subscriptions/sub-123/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm"
        );
    }

    #[test]
    fn resource_id_preserves_special_chars() {
        let rid = build_vm_resource_id("abc-def", "rg with spaces", "vm_name-1");
        assert!(rid.contains("rg with spaces"));
        assert!(rid.contains("vm_name-1"));
    }

    // -- classify_agent_status --

    #[test]
    fn agent_status_active() {
        assert_eq!(classify_agent_status("active\n"), "OK");
    }

    #[test]
    fn agent_status_inactive() {
        assert_eq!(classify_agent_status("inactive\n"), "Down");
    }

    #[test]
    fn agent_status_unknown() {
        assert_eq!(classify_agent_status("failed\n"), "N/A");
    }

    #[test]
    fn agent_status_na_fallback() {
        assert_eq!(classify_agent_status("N/A"), "N/A");
    }

    #[test]
    fn agent_status_empty() {
        assert_eq!(classify_agent_status(""), "N/A");
    }

    // -- pick_ssh_ip --

    #[test]
    fn pick_ip_prefers_public() {
        assert_eq!(pick_ssh_ip(Some("1.2.3.4"), Some("10.0.0.1")), "1.2.3.4");
    }

    #[test]
    fn pick_ip_falls_back_to_private() {
        assert_eq!(pick_ssh_ip(None, Some("10.0.0.1")), "10.0.0.1");
    }

    #[test]
    fn pick_ip_empty_when_none() {
        assert_eq!(pick_ssh_ip(None, None), "");
    }

    // -- needs_bastion --

    #[test]
    fn needs_bastion_when_no_public_ip() {
        assert!(needs_bastion(None));
    }

    #[test]
    fn no_bastion_when_has_public_ip() {
        assert!(!needs_bastion(Some("1.2.3.4")));
    }

    #[test]
    fn ssh_prefix_has_batchmode_and_timeout_without_remote_cmd() {
        let args = build_ssh_prefix("1.2.3.4", "azureuser", 45);
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"ConnectTimeout=45".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
        assert_eq!(args.last().unwrap(), "azureuser@1.2.3.4");
    }

    #[test]
    fn tunneled_ssh_prefix_uses_localhost_and_port() {
        let args = build_tunneled_ssh_prefix("azureuser", 50210, 30);
        assert!(args.contains(&"-p".to_string()));
        assert!(args.contains(&"50210".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
        assert_eq!(args.last().unwrap(), "azureuser@127.0.0.1");
    }

    // -- inject_identity_key --

    #[test]
    fn inject_key_into_ssh_args() {
        let mut args = build_ssh_args("10.0.0.1", "azureuser", "uptime", 10);
        let key = std::path::Path::new("/home/u/.ssh/azlin_key");
        inject_identity_key(&mut args, key);
        // -i and key should appear just before user@host and command
        let i_pos = args.iter().position(|a| a == "-i").unwrap();
        assert_eq!(args[i_pos + 1], "/home/u/.ssh/azlin_key");
        assert_eq!(args[i_pos + 2], "azureuser@10.0.0.1");
        assert_eq!(args.last().unwrap(), "uptime");
    }

    #[test]
    fn inject_key_preserves_all_options() {
        let mut args = build_ssh_args("1.2.3.4", "admin", "ls", 10);
        let original_len = args.len();
        inject_identity_key(&mut args, std::path::Path::new("/tmp/key"));
        assert_eq!(
            args.len(),
            original_len + 2,
            "should add exactly -i and key path"
        );
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
    }

    #[test]
    fn inject_key_into_log_follow_args() {
        let mut args = super::super::connect_helpers::build_log_follow_args(
            "azureuser",
            "10.0.0.1",
            "/var/log/syslog",
            10,
        );
        let key = std::path::Path::new("/home/u/.ssh/azlin_key");
        inject_identity_key(&mut args, key);
        let i_pos = args.iter().position(|a| a == "-i").unwrap();
        assert_eq!(args[i_pos + 1], "/home/u/.ssh/azlin_key");
        assert_eq!(args[i_pos + 2], "azureuser@10.0.0.1");
    }

    #[test]
    fn inject_key_with_minimal_args() {
        let mut args = vec!["user@host".to_string(), "cmd".to_string()];
        inject_identity_key(&mut args, std::path::Path::new("/key"));
        assert_eq!(args, vec!["-i", "/key", "user@host", "cmd"]);
    }
}
