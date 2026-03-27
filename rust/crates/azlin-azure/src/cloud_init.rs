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
/// These install toolchains that aren't available as apt packages, matching
/// the full Python azlin provisioning (gh, az, node, claude, rust, go, .NET).
pub fn default_dev_setup_commands(username: &str) -> Vec<String> {
    vec![
        // Full system upgrade (apt-get upgrade is safer than full-upgrade: never removes packages)
        "apt-get update && apt-get upgrade -y && apt-get autoremove -y && apt-get autoclean -y".to_string(),
        // Python 3.13+ — use deadsnakes PPA only on LTS that needs it
        "if python3 --version 2>&1 | grep -qE '3\\.1[3-9]|3\\.[2-9][0-9]'; then echo 'Python 3.13+ available'; else add-apt-repository -y ppa:deadsnakes/ppa && apt update && apt install -y python3.13 python3.13-venv python3.13-dev && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 && update-alternatives --set python3 /usr/bin/python3.13; fi".to_string(),
        "curl -sS https://bootstrap.pypa.io/get-pip.py | python3".to_string(),
        // GitHub CLI
        "mkdir -p -m 755 /etc/apt/keyrings && wget -nv -O /etc/apt/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && mkdir -p -m 755 /etc/apt/sources.list.d && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && apt update && apt install -y gh".to_string(),
        // Azure CLI
        "curl -sL https://aka.ms/InstallAzureCLIDeb | bash".to_string(),
        // astral-uv (uv package manager)
        "snap install astral-uv --classic || true".to_string(),
        // Node.js 22 LTS (via NodeSource)
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt install -y nodejs".to_string(),
        // npm user-local configuration
        format!("mkdir -p /home/{u}/.npm-packages && echo 'prefix=${{HOME}}/.npm-packages' > /home/{u}/.npmrc && chown {u}:{u} /home/{u}/.npmrc /home/{u}/.npm-packages", u = username),
        // Tmux configuration
        format!("printf '[%%s] %%s\\n' \"$(hostname)\" \"tmux.conf\" && cat > /home/{u}/.tmux.conf << 'TMUXEOF'\nset -g status-left-length 50\nset -g status-left \"#[fg=cyan][#h]#[fg=green] #S #[fg=yellow]| \"\nset -g status-right \"#[fg=cyan]%%Y-%%m-%%d %%H:%%M\"\nset -g status-interval 60\nset -g status-bg black\nset -g status-fg white\nTMUXEOF\nchown {u}:{u} /home/{u}/.tmux.conf", u = username),
        // Fix tmux socket dir permissions (Ubuntu 25.10+)
        format!("chmod 1777 /tmp && TMUX_UID=$(id -u {u}) && mkdir -p /tmp/tmux-$TMUX_UID && chmod 700 /tmp/tmux-$TMUX_UID && chown {u}:{u} /tmp/tmux-$TMUX_UID", u = username),
        // Claude Code AI Assistant
        format!("su - {u} -c 'curl -fsSL https://claude.ai/install.sh | bash' || echo 'WARNING: Claude Code installation failed'", u = username),
        // Rust
        format!("su - {u} -c 'curl --proto =https --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y'", u = username),
        // Go
        "wget -q https://go.dev/dl/go1.21.5.linux-amd64.tar.gz -O /tmp/go.tar.gz && tar -C /usr/local -xzf /tmp/go.tar.gz && rm /tmp/go.tar.gz".to_string(),
        // .NET 10 SDK
        "curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && chmod +x /tmp/dotnet-install.sh && (/tmp/dotnet-install.sh --channel 10.0 --quality preview --install-dir /usr/share/dotnet || /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet || echo 'WARNING: .NET 10 SDK install failed') && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet; rm -f /tmp/dotnet-install.sh".to_string(),
        // Docker post-install
        format!("usermod -aG docker {u} && systemctl enable docker && systemctl start docker", u = username),
        // bashrc additions (npm path, go path, cargo env, azlin alias)
        format!("cat >> /home/{u}/.bashrc << 'BASHEOF'\n\n# npm user-local configuration\nNPM_PACKAGES=\"${{HOME}}/.npm-packages\"\nPATH=\"$NPM_PACKAGES/bin:$PATH\"\nMANPATH=\"$NPM_PACKAGES/share/man:$(manpath 2>/dev/null || echo $MANPATH)\"\n\n# Go\nexport PATH=$PATH:/usr/local/go/bin\n\n# Cargo\nsource $HOME/.cargo/env 2>/dev/null\nBASHEOF", u = username),
        // Version verification (rustc is in user homedir, must check as user)
        format!("echo '[AZLIN] Provisioning complete' && which gh && gh --version && which az && az --version | head -2 && which node && node --version && su - {u} -c 'which rustc && rustc --version' && which dotnet && dotnet --version || true", u = username),
    ]
}

/// Default packages for development VMs (installed via apt)
pub fn default_dev_packages() -> Vec<&'static str> {
    vec![
        "docker.io",
        "git",
        "tmux",
        "curl",
        "wget",
        "build-essential",
        "software-properties-common",
        "ripgrep",
        "python3-pip",
        "pipx",
        "jq",
        "unzip",
        "htop",
        "tree",
        "vim",
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
        assert!(pkgs.contains(&"ripgrep"));
        assert!(pkgs.contains(&"pipx"));
        assert!(pkgs.contains(&"software-properties-common"));
        assert!(pkgs.len() >= 10);
    }

    #[test]
    fn test_default_dev_setup_commands() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter().any(|c| c.contains("rustup.rs")),
            "Missing Rust install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("dotnet-install.sh")),
            "Missing .NET install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("apt install -y gh")),
            "Missing GitHub CLI install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("InstallAzureCLIDeb")),
            "Missing Azure CLI install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("nodesource.com")),
            "Missing Node.js install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("claude.ai/install.sh")),
            "Missing Claude Code install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("go.dev")),
            "Missing Go install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("usermod -aG docker")),
            "Missing Docker post-install command"
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
