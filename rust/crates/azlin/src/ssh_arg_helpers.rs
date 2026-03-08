/// Build the argument list for a direct SSH command.
/// Returns the args that would be passed to `ssh`.
pub fn build_ssh_args<'a>(ip: &'a str, user: &'a str, cmd: &'a str) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        "ConnectTimeout=10".to_string(),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        format!("{}@{}", user, ip),
        cmd.to_string(),
    ]
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
        let args = build_ssh_args("10.0.0.1", "azureuser", "uptime");
        assert!(args.contains(&"azureuser@10.0.0.1".to_string()));
        assert_eq!(args.last().unwrap(), "uptime");
    }

    #[test]
    fn ssh_args_have_security_options() {
        let args = build_ssh_args("1.2.3.4", "admin", "ls");
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"ConnectTimeout=10".to_string()));
        assert!(args.contains(&"BatchMode=yes".to_string()));
    }

    #[test]
    fn ssh_args_count() {
        let args = build_ssh_args("1.2.3.4", "user", "cmd");
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
}
