/// Generate cloud-init YAML for VM provisioning
pub fn generate_cloud_init(
    username: &str,
    ssh_public_key: &str,
    packages: &[&str],
    setup_commands: &[String],
) -> String {
    let mut yaml = String::from("#cloud-config\n");
    yaml.push_str(&format!("users:\n  - name: {}\n", username));
    yaml.push_str("    groups: sudo, docker\n");
    yaml.push_str("    shell: /bin/bash\n");
    yaml.push_str("    sudo: ALL=(ALL) NOPASSWD:ALL\n");
    yaml.push_str("    ssh_authorized_keys:\n");
    yaml.push_str(&format!("      - {}\n", ssh_public_key));

    if !packages.is_empty() {
        yaml.push_str("\npackage_update: true\npackage_upgrade: true\npackages:\n");
        for pkg in packages {
            yaml.push_str(&format!("  - {}\n", pkg));
        }
    }

    if !setup_commands.is_empty() {
        yaml.push_str("\nruncmd:\n");
        for cmd in setup_commands {
            yaml.push_str(&format!("  - {}\n", cmd));
        }
    }

    yaml
}

/// Default packages for development VMs
pub fn default_dev_packages() -> Vec<&'static str> {
    vec![
        "git",
        "curl",
        "wget",
        "jq",
        "tmux",
        "vim",
        "build-essential",
        "python3-pip",
        "python3-venv",
        "docker.io",
        "docker-compose",
        "unzip",
        "htop",
        "tree",
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cloud_init_basic() {
        let yaml = generate_cloud_init("azureuser", "ssh-rsa AAAA...", &[], &[]);
        assert!(yaml.starts_with("#cloud-config"));
        assert!(yaml.contains("azureuser"));
        assert!(yaml.contains("ssh-rsa"));
    }

    #[test]
    fn test_cloud_init_with_packages() {
        let yaml = generate_cloud_init("user", "key", &["git", "curl"], &[]);
        assert!(yaml.contains("packages:"));
        assert!(yaml.contains("  - git"));
        assert!(yaml.contains("  - curl"));
    }

    #[test]
    fn test_cloud_init_with_commands() {
        let cmds = vec!["apt update".to_string(), "pip install uv".to_string()];
        let yaml = generate_cloud_init("user", "key", &[], &cmds);
        assert!(yaml.contains("runcmd:"));
        assert!(yaml.contains("  - apt update"));
    }

    #[test]
    fn test_default_dev_packages() {
        let pkgs = default_dev_packages();
        assert!(pkgs.contains(&"git"));
        assert!(pkgs.contains(&"docker.io"));
        assert!(pkgs.contains(&"python3-pip"));
        assert!(pkgs.len() >= 10);
    }

    #[test]
    fn test_cloud_init_includes_sudo() {
        let yaml = generate_cloud_init("dev", "key", &[], &[]);
        assert!(yaml.contains("sudo"));
        assert!(yaml.contains("NOPASSWD"));
    }

    #[test]
    fn test_cloud_init_includes_docker_group() {
        let yaml = generate_cloud_init("dev", "key", &[], &[]);
        assert!(yaml.contains("docker"));
    }
}
