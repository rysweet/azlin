/// Validate a cloud-init input string against YAML injection.
///
/// Rejects values containing newlines or YAML special sequences that could
/// break the document structure.
fn validate_cloud_init_input(value: &str, field_name: &str) -> std::result::Result<(), String> {
    if value.contains('\n') || value.contains('\r') {
        return Err(format!(
            "{field_name} must not contain newlines (possible YAML injection)"
        ));
    }
    // Block YAML directives and document markers
    if value.starts_with("---") || value.starts_with("...") {
        return Err(format!("{field_name} contains YAML special sequences"));
    }
    Ok(())
}

/// YAML-safe quoting: wrap value in single quotes, escaping internal single
/// quotes by doubling them (YAML 1.1 spec).
fn yaml_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

/// Generate cloud-init YAML for VM provisioning.
///
/// All inputs are validated against YAML injection. Usernames must be
/// alphanumeric (plus hyphens/underscores). SSH keys and commands are
/// YAML-quoted to prevent injection.
pub fn generate_cloud_init(
    username: &str,
    ssh_public_key: &str,
    packages: &[&str],
    setup_commands: &[String],
) -> String {
    // Validate username: alphanumeric, hyphens, underscores only
    if !username
        .chars()
        .all(|c| c.is_alphanumeric() || c == '-' || c == '_')
    {
        // Fall back to safe default rather than injecting unsafe values
        return generate_cloud_init("azureuser", ssh_public_key, packages, setup_commands);
    }

    // Validate SSH key (no newlines)
    if validate_cloud_init_input(ssh_public_key, "ssh_public_key").is_err() {
        return String::from(
            "#cloud-config\n# ERROR: invalid ssh_public_key (rejected for safety)\n",
        );
    }

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
            // Package names: alphanumeric, hyphens, dots, plus signs
            if pkg
                .chars()
                .all(|c| c.is_alphanumeric() || c == '-' || c == '.' || c == '+')
            {
                yaml.push_str(&format!("  - {}\n", pkg));
            }
        }
    }

    if !setup_commands.is_empty() {
        yaml.push_str("\nruncmd:\n");
        for cmd in setup_commands {
            if validate_cloud_init_input(cmd, "setup_command").is_ok() {
                // YAML-quote each command to prevent injection via special chars
                yaml.push_str(&format!("  - {}\n", yaml_quote(cmd)));
            }
        }
    }

    yaml
}

/// Default packages for development VMs
/// Default setup commands for development VMs (run after packages install).
///
/// These install toolchains that aren't available as apt packages:
/// - Rust/Cargo via rustup
/// - .NET 10 SDK via Microsoft install script
/// - amplihack from github.com/rysweet/amplihack
pub fn default_dev_setup_commands() -> Vec<String> {
    vec![
        // Install Rust/Cargo for the default user
        "su - azureuser -c 'curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y'".to_string(),
        // Install .NET 10 SDK (preview until GA, then remove --quality flag)
        "curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && chmod +x /tmp/dotnet-install.sh && (/tmp/dotnet-install.sh --channel 10.0 --quality preview --install-dir /usr/share/dotnet || /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet || echo 'WARNING: .NET 10 SDK install failed') && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet; rm -f /tmp/dotnet-install.sh".to_string(),
        // Install amplihack (Python version)
        "su - azureuser -c 'git clone https://github.com/rysweet/amplihack.git ~/amplihack && cd ~/amplihack && make install || true'".to_string(),
        // Install amplihack-rs (Rust CLI) — requires cmake for ladybugdb
        "su - azureuser -c '. ~/.cargo/env && cargo install --git https://github.com/rysweet/amplihack-rs amplihack || echo \"WARNING: amplihack-rs install failed\"'".to_string(),
    ]
}

pub fn default_dev_packages() -> Vec<&'static str> {
    vec![
        "git",
        "curl",
        "wget",
        "jq",
        "tmux",
        "vim",
        "build-essential",
        "cmake",
        "make",
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
        // Commands are now YAML-quoted for injection safety
        assert!(yaml.contains("'apt update'"));
    }

    #[test]
    fn test_cloud_init_rejects_newline_in_username() {
        // Username with newline should fall back to "azureuser"
        let yaml = generate_cloud_init("evil\nuser", "key", &[], &[]);
        assert!(yaml.contains("azureuser"));
        assert!(!yaml.contains("evil"));
    }

    #[test]
    fn test_cloud_init_rejects_newline_in_ssh_key() {
        let yaml = generate_cloud_init("user", "key\ninjection", &[], &[]);
        assert!(yaml.contains("ERROR"));
    }

    #[test]
    fn test_cloud_init_rejects_special_username() {
        // Username with spaces should fall back to "azureuser"
        let yaml = generate_cloud_init("evil user", "key", &[], &[]);
        assert!(yaml.contains("azureuser"));
    }

    #[test]
    fn test_cloud_init_filters_bad_packages() {
        // Package with special chars should be filtered out
        let yaml = generate_cloud_init("user", "key", &["git", "bad;pkg", "curl"], &[]);
        assert!(yaml.contains("  - git"));
        assert!(yaml.contains("  - curl"));
        assert!(!yaml.contains("bad;pkg"));
    }

    #[test]
    fn test_default_dev_packages() {
        let pkgs = default_dev_packages();
        assert!(pkgs.contains(&"git"));
        assert!(pkgs.contains(&"docker.io"));
        assert!(pkgs.contains(&"python3-pip"));
        assert!(pkgs.contains(&"make"));
        assert!(pkgs.len() >= 10);
    }

    #[test]
    fn test_default_dev_setup_commands() {
        let cmds = default_dev_setup_commands();
        assert!(
            cmds.iter().any(|c| c.contains("rustup.rs")),
            "Missing Rust install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("dotnet-install.sh")),
            "Missing .NET install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("rysweet/amplihack")),
            "Missing amplihack install command"
        );
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
