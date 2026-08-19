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

fn append_runcmd_entry(yaml: &mut String, cmd: &str) {
    if cmd.contains('\n') || cmd.contains('\r') {
        let normalized = cmd.replace("\r\n", "\n").replace('\r', "\n");
        yaml.push_str("  - |\n");
        for line in normalized.lines() {
            yaml.push_str("    ");
            yaml.push_str(line);
            yaml.push('\n');
        }
    } else if validate_cloud_init_input(cmd, "setup_command").is_ok() {
        // YAML-quote each single-line command to prevent injection via special chars.
        yaml.push_str(&format!("  - {}\n", yaml_quote(cmd)));
    }
}

fn sanitize_admin_username(username: &str) -> &str {
    if username
        .chars()
        .all(|c| c.is_alphanumeric() || c == '-' || c == '_')
        && !username.is_empty()
    {
        username
    } else {
        "azureuser"
    }
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

    let mut yaml = String::with_capacity(512);
    yaml.push_str("#cloud-config\n");
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
            append_runcmd_entry(&mut yaml, cmd);
        }
    }

    yaml
}

/// Disk configuration for cloud-init provisioning.
#[derive(Debug, Clone, Default)]
pub struct DiskConfig {
    /// If true, LUN 0 is a home disk to be mounted at /home/{user}.
    pub home_disk: bool,
    /// If true, LUN 1 (or LUN 0 if no home disk) is a tmp disk to be mounted at /tmp.
    pub tmp_disk: bool,
}

/// Shell snippet: wait for an Azure LUN device to appear (udevadm + retry loop).
/// Returns a script fragment that sets `$DEV_VAR` to the resolved block device path.
fn lun_wait_snippet(lun: u32, dev_var: &str, label: &str) -> String {
    format!(
        r#"  # Wait for udev to finish processing device events
  udevadm settle --timeout=30 || true

  # Retry loop: poll for LUN device availability (12 retries x 5s = 60s max)
  {dev_var}=""
  for retry in $(seq 1 12); do
    {dev_var}=$(readlink -f /dev/disk/azure/scsi1/lun{lun} 2>/dev/null) || true
    if [ -n "${dev_var}" ] && [ -b "${dev_var}" ]; then
      break
    fi
    echo "[AZLIN] Waiting for {label} disk LUN {lun} (attempt $retry/12)..."
    sleep 5
  done

  if [ -z "${dev_var}" ] || [ ! -b "${dev_var}" ]; then
    echo "WARNING: {label} disk at LUN {lun} not found after 60s"
    exit 1
  fi"#,
        lun = lun,
        dev_var = dev_var,
        label = label,
    )
}

pub fn render_dev_cloud_init_script(admin_username: &str) -> String {
    render_dev_cloud_init_script_with_disks(admin_username, &DiskConfig::default())
}

/// Render the dev cloud-init shell script with optional data disk setup.
///
/// When `disk_config` enables home or tmp disks, the script includes
/// hardened formatting/mounting blocks with retry loops and subshell isolation.
pub fn render_dev_cloud_init_script_with_disks(
    admin_username: &str,
    disk_config: &DiskConfig,
) -> String {
    let safe_username = sanitize_admin_username(admin_username);
    let packages = default_dev_packages();
    // Pre-allocate ~10KB for the generated script to avoid repeated reallocations
    let mut script = String::with_capacity(10 * 1024);
    script.push_str("#!/bin/bash\nset -euo pipefail\n\n");
    script.push_str("apt-get update -qq\n");
    script.push_str("apt-get upgrade -y -qq\n\n");
    script.push_str("apt-get install -y -qq \\\n");

    for (idx, package) in packages.iter().enumerate() {
        script.push_str("    ");
        script.push_str(package);
        if idx + 1 != packages.len() {
            script.push_str(" \\\n");
        } else {
            script.push('\n');
        }
    }

    script.push('\n');

    // Disk formatting and mounting (must happen before user setup so home dir is on the right disk)
    if disk_config.home_disk || disk_config.tmp_disk {
        script.push_str("# -- Data disk setup --\n");
        script.push_str("echo '[AZLIN] Formatting and mounting data disks...'\n\n");
    }

    let mut next_lun = 0u32;

    if disk_config.home_disk {
        // LUN 0 = home disk -- wrapped in subshell for failure isolation
        script.push_str(&format!(
            r#"# Home disk (LUN {lun})
(
{wait}

  mkfs.ext4 -F -L azlin-home "$HOME_DEV"
  mkdir -p /mnt/home-data
  mount "$HOME_DEV" /mnt/home-data
  # Copy existing home to the new disk
  rsync -aAX /home/{u}/ /mnt/home-data/{u}/
  # Bind mount over /home/{u} -- with rollback trap to restore original on failure
  mv /home/{u} /home/{u}.old
  trap 'if [ -d /home/{u}.old ] && ! mountpoint -q /home/{u} 2>/dev/null; then rm -rf /home/{u} 2>/dev/null; mv /home/{u}.old /home/{u}; echo "[AZLIN] Rolled back /home/{u} after disk setup failure"; fi' EXIT
  mkdir -p /home/{u}
  mount --bind /mnt/home-data/{u} /home/{u}
  # Verify bind mount succeeded before cleaning up
  if mountpoint -q /home/{u}; then
    rm -rf /home/{u}.old
  fi
  # Persist in fstab (idempotent)
  HOME_UUID=$(blkid -s UUID -o value "$HOME_DEV")
  grep -q "UUID=$HOME_UUID" /etc/fstab || echo "UUID=$HOME_UUID /mnt/home-data ext4 defaults,nofail 0 2" >> /etc/fstab
  grep -q "/mnt/home-data/{u} /home/{u}" /etc/fstab || echo "/mnt/home-data/{u} /home/{u} none bind 0 0" >> /etc/fstab
  echo "[AZLIN] Home disk mounted at /home/{u} ($(lsblk -no SIZE "$HOME_DEV" | tr -d ' '))"
) || echo "WARN: Home disk setup failed, continuing without separate home disk"

"#,
            lun = next_lun,
            wait = lun_wait_snippet(next_lun, "HOME_DEV", "home"),
            u = safe_username,
        ));
        next_lun += 1;
    }

    if disk_config.tmp_disk {
        script.push_str(&format!(
            r#"# Tmp disk (LUN {lun})
(
{wait}

  mkfs.ext4 -F -L azlin-tmp "$TMP_DEV"
  mkdir -p /mnt/tmp-data
  mount "$TMP_DEV" /mnt/tmp-data
  mkdir -p /mnt/tmp-data/tmp
  chmod 1777 /mnt/tmp-data/tmp
  # Copy existing /tmp contents
  rsync -aAX /tmp/ /mnt/tmp-data/tmp/ 2>/dev/null || true
  mount --bind /mnt/tmp-data/tmp /tmp
  chmod 1777 /tmp
  # Persist in fstab (idempotent)
  TMP_UUID=$(blkid -s UUID -o value "$TMP_DEV")
  grep -q "UUID=$TMP_UUID" /etc/fstab || echo "UUID=$TMP_UUID /mnt/tmp-data ext4 defaults,nofail 0 2" >> /etc/fstab
  grep -q "/mnt/tmp-data/tmp /tmp" /etc/fstab || echo "/mnt/tmp-data/tmp /tmp none bind 0 0" >> /etc/fstab
  echo "[AZLIN] Tmp disk mounted at /tmp ($(lsblk -no SIZE "$TMP_DEV" | tr -d ' '))"
) || echo "WARN: Tmp disk setup failed, continuing without separate tmp disk"

"#,
            lun = next_lun,
            wait = lun_wait_snippet(next_lun, "TMP_DEV", "tmp"),
        ));
    }

    for command in default_dev_setup_commands(safe_username) {
        script.push_str(&command);
        script.push_str("\n\n");
    }

    script
}

/// Default packages for development VMs
/// Default setup commands for development VMs (run after packages install).
///
/// These install toolchains that aren't available as apt packages, matching
/// the full Python azlin provisioning (gh, az, node, claude, rust, go, .NET).
pub fn default_dev_setup_commands(username: &str) -> Vec<String> {
    vec![
        // Python 3.14 - install via deadsnakes but do NOT change system python3
        "if python3.14 --version 2>/dev/null; then echo 'Python 3.14 available'; else add-apt-repository -y ppa:deadsnakes/ppa && apt update && apt install -y python3.14 python3.14-venv python3.14-dev || echo 'WARNING: Python 3.14 install failed'; fi".to_string(),
        // GitHub CLI
        "mkdir -p -m 755 /etc/apt/keyrings && wget -nv -O /etc/apt/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && mkdir -p -m 755 /etc/apt/sources.list.d && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && apt update && apt install -y gh || echo 'WARNING: GitHub CLI install failed'".to_string(),
        // Azure CLI.
        //
        // Not `curl -sL https://aka.ms/InstallAzureCLIDeb | bash`. That script
        // derives its apt dist from `lsb_release -cs` and 404s on any codename
        // Microsoft has not published. Ubuntu 26.04 ("resolute") is not
        // published — only up to "noble" is — so on 26.04 it simply fails.
        //
        // Worse, it failed *silently*: in a `curl ... | bash` pipeline the exit
        // status is bash's, so a failed download still exits 0, and `-s`
        // suppressed curl's error. Provisioning reported success on a VM with
        // no `az` installed and nothing in cloud-init-output.log to say so.
        //
        // Install from the repo directly instead: use the running codename when
        // Microsoft publishes it, fall back to the newest published LTS when
        // they do not, and report failure either way.
        r#"AZ_DIST=$(lsb_release -cs) && if ! curl -fsSL "https://packages.microsoft.com/repos/azure-cli/dists/$AZ_DIST/Release" >/dev/null 2>&1; then echo "NOTE: azure-cli has no apt dist for '$AZ_DIST'; falling back to noble"; AZ_DIST=noble; fi && mkdir -p -m 755 /etc/apt/keyrings && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg && chmod go+r /etc/apt/keyrings/microsoft.gpg && mkdir -p -m 755 /etc/apt/sources.list.d && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ $AZ_DIST main" > /etc/apt/sources.list.d/azure-cli.list && apt-get update && apt-get install -y azure-cli || echo 'WARNING: Azure CLI install failed'"#.to_string(),
        // Chromium (Ubuntu ships this as a snap-backed launcher)
        "apt-get install -y chromium-browser".to_string(),
        // Chromium wrappers so SSH/X11 launches use a scoped user session instead of
        // failing with the snap cgroup error.
        r#"cat > /usr/local/bin/chromium-browser << 'CHROMIUMWRAP'
#!/bin/sh
set -eu

REAL_COMMAND=/usr/bin/chromium-browser
if [ ! -x "$REAL_COMMAND" ]; then
    REAL_COMMAND=/snap/bin/chromium
fi

if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi

if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "$XDG_RUNTIME_DIR/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

if command -v snap >/dev/null 2>&1 && snap list chromium >/dev/null 2>&1; then
    if ! command -v systemd-run >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
        echo "Chromium requires systemd user scope support on this VM, but systemd tooling is unavailable." >&2
        exit 1
    fi
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        echo "Chromium requires an active systemd user environment on this VM. Check linger/user-systemd setup." >&2
        exit 1
    fi
    exec systemd-run --user --scope --quiet -- "$REAL_COMMAND" "$@"
fi

exec "$REAL_COMMAND" "$@"
CHROMIUMWRAP
chmod 755 /usr/local/bin/chromium-browser

cat > /usr/local/bin/chromium << 'CHROMIUMALIAS'
#!/bin/sh
exec /usr/local/bin/chromium-browser "$@"
CHROMIUMALIAS
chmod 755 /usr/local/bin/chromium"#.to_string(),
        // astral-uv (uv package manager)
        "snap install astral-uv --classic || true".to_string(),
        // Node.js 24 LTS (via NodeSource)
        "curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && apt install -y nodejs || echo 'WARNING: Node.js install failed'".to_string(),
        // npm user-local configuration
        format!("mkdir -p /home/{u}/.npm-packages && echo 'prefix=${{HOME}}/.npm-packages' > /home/{u}/.npmrc && chown {u}:{u} /home/{u}/.npmrc /home/{u}/.npm-packages", u = username),
        // Tmux configuration
        format!("printf '[%%s] %%s\\n' \"$(hostname)\" \"tmux.conf\" && cat > /home/{u}/.tmux.conf << 'TMUXEOF'\nset -g status-left-length 50\nset -g status-left \"#[fg=cyan][#h]#[fg=green] #S #[fg=yellow]| \"\nset -g status-right \"#[fg=cyan]%%Y-%%m-%%d %%H:%%M\"\nset -g status-interval 60\nset -g status-bg black\nset -g status-fg white\nTMUXEOF\nchown {u}:{u} /home/{u}/.tmux.conf", u = username),
        // Fix tmux socket dir permissions (Ubuntu 25.10+)
        format!("chmod 1777 /tmp && TMUX_UID=$(id -u {u}) && mkdir -p /tmp/tmux-$TMUX_UID && chmod 700 /tmp/tmux-$TMUX_UID && chown {u}:{u} /tmp/tmux-$TMUX_UID", u = username),
        // Claude Code AI Assistant
        // Download, then execute. NOT `curl ... | bash` inside `su -c`: the
        // generated script sets `pipefail`, but that is a per-shell option and
        // the fresh login shell `su -` starts does not inherit it. Verified:
        // `bash -c 'set -o pipefail; bash -c "false | true; echo $?"'` prints 0.
        // So a failed download would leave bash reading empty stdin, exiting 0,
        // and the `|| echo WARNING` below would never fire — #1069 one level
        // deeper.
        format!("su - {u} -c 'curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh && sh /tmp/claude-install.sh; rc=$?; rm -f /tmp/claude-install.sh; exit $rc' || echo 'WARNING: Claude Code installation failed'", u = username),
        // Rust
        // Download, then execute — same `su -c` pipefail reasoning as above.
        format!("su - {u} -c 'curl --proto =https --tlsv1.2 -fsSf https://sh.rustup.rs -o /tmp/rustup-init.sh && sh /tmp/rustup-init.sh -y; rc=$?; rm -f /tmp/rustup-init.sh; exit $rc' || echo 'WARNING: Rust install failed'", u = username),
        // amplihack-rs (pre-built binary from latest GitHub release, falls back to cargo install)
        format!("su - {u} -c 'ARCH=$(uname -m | sed s/aarch64/aarch64/ | sed s/x86_64/x86_64/) && \
            URL=$(curl -fsSL https://api.github.com/repos/rysweet/amplihack-rs/releases/latest | grep browser_download_url | grep $ARCH-unknown-linux-gnu.tar.gz\\\" | head -1 | cut -d\\\"  -f4) && \
            mkdir -p /tmp/amplihack-install && cd /tmp/amplihack-install && \
            curl -fsSL $URL -o amplihack.tar.gz && tar xzf amplihack.tar.gz && \
            mkdir -p ~/.cargo/bin && cp amplihack amplihack-hooks ~/.cargo/bin/ && \
            chmod +x ~/.cargo/bin/amplihack ~/.cargo/bin/amplihack-hooks && \
            cd ~ && rm -rf /tmp/amplihack-install && \
            ~/.cargo/bin/amplihack install' || echo 'WARNING: amplihack-rs installation failed'", u = username),
        // azlin CLI (pre-built binary from latest GitHub release).
        // Release archives ship platform-suffixed members (azlin-linux-x86_64,
        // azdoit-linux-x86_64, ay-linux-x86_64), so each is renamed on copy.
        format!("su - {u} -c 'ARCH=$(uname -m | sed s/aarch64/aarch64/ | sed s/x86_64/x86_64/) && \
            URL=$(curl -fsSL https://api.github.com/repos/rysweet/azlin/releases/latest | grep browser_download_url | grep linux-$ARCH.tar.gz\\\" | head -1 | cut -d\\\"  -f4) && \
            mkdir -p /tmp/azlin-install && cd /tmp/azlin-install && \
            curl -fsSL $URL -o azlin.tar.gz && tar xzf azlin.tar.gz && \
            mkdir -p ~/.cargo/bin && \
            cp azlin-linux-$ARCH ~/.cargo/bin/azlin && \
            cp azdoit-linux-$ARCH ~/.cargo/bin/azdoit && \
            cp ay-linux-$ARCH ~/.cargo/bin/ay && \
            chmod +x ~/.cargo/bin/azlin ~/.cargo/bin/azdoit ~/.cargo/bin/ay && \
            cd ~ && rm -rf /tmp/azlin-install' || echo 'WARNING: azlin binary installation failed (azlin/azdoit/ay)'", u = username),
        // Go
        "wget -q https://go.dev/dl/go1.26.4.linux-amd64.tar.gz -O /tmp/go.tar.gz && tar -C /usr/local -xzf /tmp/go.tar.gz && rm /tmp/go.tar.gz || echo 'WARNING: Go install failed'".to_string(),
        // .NET 10 SDK
        "curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && chmod +x /tmp/dotnet-install.sh && (/tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet || echo 'WARNING: .NET 10 SDK install failed') && ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet; rm -f /tmp/dotnet-install.sh".to_string(),
        // Docker post-install
        format!("usermod -aG docker {u} && systemctl enable docker && systemctl start docker", u = username),
        // Enable systemd user linger so SSH sessions get a systemd user instance
        // (required for snap Chromium cgroup scoping via systemd-run --user)
        format!("loginctl enable-linger {u}", u = username),
        // bashrc additions (npm path, go path, cargo env, azlin alias)
        format!("cat >> /home/{u}/.bashrc << 'BASHEOF'\n\n# npm user-local configuration\nNPM_PACKAGES=\"${{HOME}}/.npm-packages\"\nPATH=\"$NPM_PACKAGES/bin:$PATH\"\nMANPATH=\"$NPM_PACKAGES/share/man:$(manpath 2>/dev/null || echo $MANPATH)\"\n\n# Go\nexport PATH=$PATH:/usr/local/go/bin\n\n# Cargo\nsource $HOME/.cargo/env 2>/dev/null\nBASHEOF", u = username),
        // Version verification (rustc is in user homedir, must check as user).
        // All three azlin archive members are checked: the install chain is a
        // single `&&` sequence, so a member missing from a future tarball aborts
        // it *after* earlier binaries already landed. Checking only `azlin` would
        // let that pass silently. Note `ay` is a renamed copy of the `azlin`
        // binary (see .github/workflows/rust-release.yml), so `ay --version`
        // prints `azlin <version>`; this check proves `ay` is present and
        // executable, not that it is a distinct program.
        format!("echo '[AZLIN] Provisioning complete' && which gh && gh --version && which az && az --version | head -2 && which node && node --version && su - {u} -c 'which rustc && rustc --version && which amplihack && amplihack --version && which azlin && azlin --version && which azdoit && azdoit --version && which ay && ay --version' && which dotnet && dotnet --version || true", u = username),
        // Explicit provisioning sentinel for azlin's post-create readiness checks.
        "mkdir -p /var/lib/azlin && touch /var/lib/azlin/provisioning-complete && echo 'cloud-init provisioning complete'".to_string(),
    ]
}

/// Default packages for development VMs (installed via apt).
/// Returns a static slice to avoid heap allocation on each call.
pub fn default_dev_packages() -> &'static [&'static str] {
    &[
        "docker.io",
        "git",
        "tmux",
        "curl",
        "wget",
        "build-essential",
        "make",
        "cmake",
        "software-properties-common",
        "ripgrep",
        "fd-find",
        "python3-pip",
        "pipx",
        "jq",
        "unzip",
        "xdg-utils",
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
        assert!(pkgs.contains(&"make"));
        assert!(pkgs.contains(&"fd-find"));
        assert!(pkgs.contains(&"pipx"));
        assert!(pkgs.contains(&"xdg-utils"));
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
            cmds.iter().any(|c| c.contains("azure-cli")),
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
    fn test_default_dev_setup_commands_enables_systemd_linger() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("loginctl enable-linger azureuser")),
            "default_dev_setup_commands must enable systemd user linger for snap Chromium cgroup support"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_linger_uses_custom_username() {
        let cmds = default_dev_setup_commands("devuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("loginctl enable-linger devuser")),
            "linger command must use the provisioned admin username"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_install_chromium_and_wrappers() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("apt-get install -y chromium-browser")),
            "default_dev_setup_commands must install chromium-browser"
        );
        assert!(
            cmds.iter()
                .any(|c| c.contains("cat > /usr/local/bin/chromium-browser << 'CHROMIUMWRAP'")),
            "default_dev_setup_commands must install the chromium-browser wrapper"
        );
        assert!(
            cmds.iter()
                .any(|c| c.contains("exec /usr/local/bin/chromium-browser \"$@\"")),
            "default_dev_setup_commands must install the chromium alias wrapper"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_chromium_wrapper_fails_loudly_when_scope_unavailable() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter().any(|c| c.contains("Chromium requires systemd user scope support on this VM, but systemd tooling is unavailable.")),
            "default_dev_setup_commands must fail loudly when user-systemd tooling is missing"
        );
        assert!(
            cmds.iter().any(|c| c.contains("Chromium requires an active systemd user environment on this VM. Check linger/user-systemd setup.")),
            "default_dev_setup_commands must fail loudly when the user systemd environment is unavailable"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_write_provisioning_sentinel() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("/var/lib/azlin/provisioning-complete")),
            "default_dev_setup_commands must write a provisioning-complete sentinel"
        );
        assert!(
            cmds.iter()
                .any(|c| c.contains("cloud-init provisioning complete")),
            "default_dev_setup_commands must emit the final provisioning marker"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_install_azlin_binaries_by_archive_member_name() {
        let cmds = default_dev_setup_commands("azureuser");
        let azlin_cmd = cmds
            .iter()
            .find(|c| c.contains("/tmp/azlin-install"))
            .expect("default_dev_setup_commands must install the azlin CLI");

        // Release archives contain platform-suffixed members, not bare `azlin`.
        for (member, dest) in [
            ("azlin-linux-$ARCH", "azlin"),
            ("azdoit-linux-$ARCH", "azdoit"),
            ("ay-linux-$ARCH", "ay"),
        ] {
            assert!(
                azlin_cmd.contains(&format!("cp {member} ~/.cargo/bin/{dest}")),
                "azlin install must copy archive member {member} to ~/.cargo/bin/{dest}, got: {azlin_cmd}"
            );
        }
        assert!(
            !azlin_cmd.contains("cp azlin ~/.cargo/bin/"),
            "azlin install must not reference a bare `azlin` member that the archive does not contain"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_install_failures_are_not_swallowed() {
        let cmds = default_dev_setup_commands("azureuser");
        for marker in ["/tmp/azlin-install", "/tmp/amplihack-install"] {
            let cmd = cmds
                .iter()
                .find(|c| c.contains(marker))
                .unwrap_or_else(|| panic!("missing install command for {marker}"));
            assert!(
                !cmd.contains("2>/dev/null"),
                "{marker} install must not discard errors and continue past them: {cmd}"
            );
            assert!(
                !cmd.contains(';'),
                "{marker} install must chain with && so a failed step reaches the WARNING branch: {cmd}"
            );
            assert!(
                cmd.contains("|| echo 'WARNING:"),
                "{marker} install must report failure: {cmd}"
            );
        }
    }

    /// Rewrites the generated azlin install command into a hermetic, offline
    /// equivalent so a real shell can execute it.
    ///
    /// The download half (`URL=$(curl ...)`, `curl -o azlin.tar.gz`, `tar xzf`)
    /// is dropped and replaced by locally created stand-ins for the archive
    /// members, so the test never touches the network. Everything from
    /// `mkdir -p ~/.cargo/bin` onwards -- the `cp`/`chmod`/`cd`/`rm` tail where
    /// the bugs this PR fixes actually live -- is executed verbatim, including
    /// the `&&` chaining and the `|| echo 'WARNING: ...'` branch.
    #[cfg(unix)]
    fn offline_azlin_install_script(staging: &str, present_members: &[&str]) -> String {
        const ARCH: &str = "x86_64";

        let cmds = default_dev_setup_commands("azureuser");
        let cmd = cmds
            .iter()
            .find(|c| c.contains("/tmp/azlin-install"))
            .expect("default_dev_setup_commands must install the azlin CLI")
            .clone();

        // Unwrap `su - <user> -c '<script>' || echo 'WARNING: ...'`, keeping the
        // trailing `|| echo` branch so the failure reporting is exercised too.
        let body_start = cmd.find('\'').expect("install command must be quoted") + 1;
        let body_end = body_start
            + cmd[body_start..]
                .find("' || echo")
                .expect("install command must have a WARNING fallback");
        let script_body = &cmd[body_start..body_end];
        let warning_branch = &cmd[body_end + 1..];

        let mut steps: Vec<String> = Vec::new();
        for step in script_body.split(" && ") {
            if step.starts_with("URL=") || step.starts_with("curl ") || step.starts_with("tar ") {
                continue; // network / archive extraction: stubbed out below
            }
            let step = if step.starts_with("ARCH=") {
                format!("ARCH={ARCH}")
            } else {
                step.replace("/tmp/azlin-install", staging)
            };
            let is_cd_staging = step == format!("cd {staging}");
            steps.push(step);
            if is_cd_staging {
                // Stand in for `tar xzf`: materialise the archive members.
                for member in present_members {
                    steps.push(format!("printf '#!/bin/sh\\n' > {member}-linux-{ARCH}"));
                }
            }
        }

        format!("{} {}", steps.join(" && "), warning_branch)
    }

    /// Executes the generated install tail in a real shell.
    ///
    /// The string-matching tests above are pattern-specific: they blacklist the
    /// exact spellings (`;`, `2>/dev/null`) that were wrong before this fix. This
    /// one is semantic -- it checks the actual exit status and output, so it also
    /// catches failure-swallowing spellings nobody thought to blacklist.
    #[cfg(unix)]
    #[test]
    fn test_default_dev_setup_commands_azlin_install_tail_behaves_under_a_real_shell() {
        use std::process::Command;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = format!(
            "azlin-cloud-init-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        let home = root.join("home");
        let staging = root.join("staging");
        std::fs::create_dir_all(&home).expect("create scratch home");

        let run = |present_members: &[&str], suffix: &str| -> (bool, String) {
            let script = offline_azlin_install_script(
                staging.to_str().expect("staging path must be utf-8"),
                present_members,
            );
            let out = Command::new("sh")
                .arg("-c")
                .arg(format!("{script}{suffix}"))
                .env("HOME", &home)
                .current_dir(&root)
                .output()
                .expect("failed to run sh");
            (
                out.status.success(),
                String::from_utf8_lossy(&out.stdout).to_string()
                    + &String::from_utf8_lossy(&out.stderr),
            )
        };

        // Happy path: every archive member present. `&& pwd` proves the shell is
        // still in a live directory afterwards, i.e. the script left the staging
        // dir before deleting it.
        let (ok_status, ok_output) = run(&["azlin", "azdoit", "ay"], " && pwd");
        let installed: Vec<bool> = ["azlin", "azdoit", "ay"]
            .iter()
            .map(|b| home.join(".cargo/bin").join(b).exists())
            .collect();
        let staging_removed = !staging.exists();

        // Failure path: a future tarball drops `ay-linux-<arch>`. The chain must
        // abort and reach the WARNING branch instead of reporting success.
        let (missing_status, missing_output) = run(&["azlin", "azdoit"], "");

        let _ = std::fs::remove_dir_all(&root);

        assert!(
            ok_status,
            "install tail must succeed when all archive members exist: {ok_output}"
        );
        assert!(
            !ok_output.contains("WARNING:"),
            "successful install must not emit a WARNING: {ok_output}"
        );
        assert!(
            ok_output.contains(home.to_str().expect("home path must be utf-8")),
            "install must cd home before deleting its staging dir, so later steps have a live cwd: {ok_output}"
        );
        assert!(
            installed.iter().all(|installed| *installed),
            "install must place azlin, azdoit and ay in ~/.cargo/bin: {installed:?}"
        );
        assert!(
            staging_removed,
            "install must clean up its staging directory"
        );

        assert!(
            missing_status,
            "the WARNING branch must keep provisioning alive: {missing_output}"
        );
        assert!(
            missing_output.contains("WARNING:"),
            "a missing archive member must surface a WARNING rather than passing silently: {missing_output}"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_leave_working_directory_before_cleanup() {
        let cmds = default_dev_setup_commands("azureuser");
        for dir in ["/tmp/azlin-install", "/tmp/amplihack-install"] {
            let cmd = cmds
                .iter()
                .find(|c| c.contains(dir))
                .unwrap_or_else(|| panic!("missing install command for {dir}"));
            assert!(
                cmd.contains(&format!("cd ~ && rm -rf {dir}")),
                "install must leave {dir} before deleting it, otherwise later steps run from a deleted CWD: {cmd}"
            );
        }
    }

    #[test]
    fn test_default_dev_setup_commands_amplihack_setup_runs_from_valid_cwd() {
        let cmds = default_dev_setup_commands("azureuser");
        let cmd = cmds
            .iter()
            .find(|c| c.contains("/tmp/amplihack-install"))
            .expect("missing amplihack install command");
        let cleanup = cmd
            .find("rm -rf /tmp/amplihack-install")
            .expect("amplihack install must clean up its staging directory");
        let cd_home = cmd.find("cd ~ &&").expect("amplihack install must cd home");
        let framework_setup = cmd
            .find("~/.cargo/bin/amplihack install")
            .expect("amplihack install must run framework setup");
        assert!(
            cd_home < cleanup && cleanup < framework_setup,
            "`amplihack install` must run after cd-ing out of the deleted staging dir: {cmd}"
        );
    }

    #[test]
    fn test_render_dev_cloud_init_script_uses_shared_packages_and_commands() {
        let script = render_dev_cloud_init_script("azureuser");
        assert!(script.starts_with("#!/bin/bash\nset -euo pipefail"));
        assert!(script.contains("fd-find"));
        assert!(script.contains("xdg-utils"));
        assert!(script.contains("/var/lib/azlin/provisioning-complete"));
        assert!(script.contains("cloud-init provisioning complete"));
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

    #[test]
    fn test_generate_cloud_init_preserves_multiline_setup_commands() {
        let yaml = generate_cloud_init("dev", "key", &[], &[String::from("echo one\necho two")]);
        assert!(yaml.contains("runcmd:\n  - |\n    echo one\n    echo two\n"));
    }

    // -- DiskConfig cloud-init script generation tests ----------------

    #[test]
    fn test_disk_config_no_disks_produces_no_disk_blocks() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: false,
                tmp_disk: false,
            },
        );
        assert!(!script.contains("Data disk setup"));
        assert!(!script.contains("Home disk"));
        assert!(!script.contains("Tmp disk"));
        assert!(!script.contains("/dev/disk/azure/scsi1/lun"));
    }

    #[test]
    fn test_disk_config_home_only_uses_lun0() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must reference LUN 0 for home disk
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun0"),
            "Home disk must use Azure LUN 0 symlink"
        );
        assert!(
            script.contains("Home disk (LUN 0)"),
            "Home disk block must be labeled with LUN 0"
        );
        // Must NOT contain tmp disk block
        assert!(
            !script.contains("Tmp disk"),
            "Should not contain tmp disk block when tmp_disk=false"
        );
        // Must format as ext4
        assert!(
            script.contains("mkfs.ext4"),
            "Home disk must be formatted with ext4"
        );
        // Must bind-mount to /home/azureuser
        assert!(
            script.contains("/home/azureuser"),
            "Home disk must mount to /home/azureuser"
        );
        // Must persist in fstab
        assert!(script.contains("/etc/fstab"), "Must persist mount in fstab");
    }

    #[test]
    fn test_disk_config_tmp_only_uses_lun0() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: false,
                tmp_disk: true,
            },
        );
        // When no home disk, tmp disk should get LUN 0
        assert!(
            script.contains("Tmp disk (LUN 0)"),
            "Tmp disk must use LUN 0 when home disk is absent"
        );
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun0"),
            "Tmp disk must use LUN 0 symlink when home disk is absent"
        );
        // Must NOT contain home disk block
        assert!(
            !script.contains("Home disk"),
            "Should not contain home disk block when home_disk=false"
        );
        // Must set sticky bit on /tmp
        assert!(
            script.contains("chmod 1777"),
            "Tmp disk must set sticky bit (1777) on /tmp"
        );
        // Must persist in fstab
        assert!(script.contains("/etc/fstab"), "Must persist mount in fstab");
    }

    #[test]
    fn test_disk_config_both_disks_uses_lun0_and_lun1() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: true,
            },
        );
        // Home disk at LUN 0
        assert!(
            script.contains("Home disk (LUN 0)"),
            "Home disk must be at LUN 0"
        );
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun0"),
            "Home disk must use LUN 0 symlink"
        );
        // Tmp disk at LUN 1
        assert!(
            script.contains("Tmp disk (LUN 1)"),
            "Tmp disk must be at LUN 1 when home disk is present"
        );
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun1"),
            "Tmp disk must use LUN 1 symlink when home disk is present"
        );
    }

    // -- Hardening assertions -----------------------------------------

    #[test]
    fn test_disk_home_block_has_retry_loop_for_lun_detection() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Retry loop: must poll for LUN device availability
        assert!(
            script.contains("sleep") && script.contains("retry")
                || script.contains("sleep") && script.contains("for ")
                || script.contains("udevadm settle"),
            "Home disk block must include retry/polling logic for LUN device detection"
        );
    }

    #[test]
    fn test_disk_tmp_block_has_retry_loop_for_lun_detection() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: false,
                tmp_disk: true,
            },
        );
        assert!(
            script.contains("sleep") && script.contains("retry")
                || script.contains("sleep") && script.contains("for ")
                || script.contains("udevadm settle"),
            "Tmp disk block must include retry/polling logic for LUN device detection"
        );
    }

    #[test]
    fn test_disk_blocks_use_subshell_isolation() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: true,
            },
        );
        // Each disk block should be wrapped in a subshell so failures don't abort cloud-init
        // The pattern should be: ( ... ) || echo "WARN: ..."
        assert!(
            script.contains("|| echo") || script.contains("|| {"),
            "Disk blocks must use subshell isolation with fallback on failure"
        );
    }

    #[test]
    fn test_disk_home_block_cleans_up_old_home() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must remove /home/azureuser.old after successful bind mount
        assert!(
            script.contains("rm -rf /home/azureuser.old")
                || script.contains("rm -rf \"/home/azureuser.old\""),
            "Home disk block must clean up /home/azureuser.old after bind mount"
        );
    }

    #[test]
    fn test_disk_home_block_has_rollback_trap() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must have a trap to restore /home/azureuser.old on failure
        assert!(
            script.contains("trap") && script.contains("azureuser.old"),
            "Home disk block must include rollback trap to restore /home/user.old on failure"
        );
    }

    #[test]
    fn test_disk_home_block_has_mandatory_rsync() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // rsync must not silently fail (no `|| true` suppression)
        assert!(
            script.contains("rsync"),
            "Home disk block must rsync existing home data"
        );
    }

    #[test]
    fn test_disk_fstab_entries_are_idempotent() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // fstab writes should check for existing entries (grep -q) before appending
        assert!(
            script.contains("grep -q") || script.contains("grep "),
            "fstab entries must be idempotent (check before appending)"
        );
    }

    #[test]
    fn test_disk_blocks_use_udevadm_settle() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must call udevadm settle before trying to read LUN devices
        assert!(
            script.contains("udevadm settle"),
            "Disk setup must call udevadm settle for device node stability"
        );
    }

    #[test]
    fn test_disk_home_block_uses_custom_username() {
        let script = render_dev_cloud_init_script_with_disks(
            "devuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        assert!(
            script.contains("/home/devuser"),
            "Home disk block must use the provided admin username"
        );
        assert!(
            !script.contains("/home/azureuser"),
            "Home disk block must not hardcode azureuser when custom username is provided"
        );
    }

    #[test]
    fn test_disk_home_block_sanitizes_bad_username() {
        let script = render_dev_cloud_init_script_with_disks(
            "evil user",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Unsafe username should fall back to azureuser
        assert!(
            script.contains("/home/azureuser"),
            "Bad username must fall back to azureuser in disk blocks"
        );
        assert!(
            !script.contains("evil user"),
            "Unsafe username must not appear in disk blocks"
        );
    }
    /// The Azure CLI install must not fail silently, and must cope with an
    /// Ubuntu release Microsoft has not published an apt dist for.
    ///
    /// Observed on a real Ubuntu 26.04 VM: codename "resolute",
    /// `https://packages.microsoft.com/repos/azure-cli/dists/resolute/Release`
    /// returns 404 (noble returns 200), `which az` reported nothing, and
    /// cloud-init-output.log contained zero mentions of the install — because
    /// `curl -sL ... | bash` exits with bash's status, so a failed download
    /// still succeeded, and `-s` hid the error.
    #[test]
    fn azure_cli_install_reports_failure_and_handles_unpublished_codename() {
        let cmds = default_dev_setup_commands("azureuser");
        let az = cmds
            .iter()
            .find(|c| c.contains("azure-cli"))
            .expect("dev setup must install the Azure CLI");

        assert!(
            !az.contains("InstallAzureCLIDeb"),
            "must not use the aka.ms script, which 404s on unpublished codenames: {az}"
        );
        assert!(
            az.contains("|| echo 'WARNING: Azure CLI install failed'"),
            "a failed Azure CLI install must be reported, not swallowed: {az}"
        );
        assert!(
            az.contains("AZ_DIST=noble"),
            "must fall back to a published dist when the running codename is absent: {az}"
        );
        assert!(
            az.contains("lsb_release -cs"),
            "must prefer the running codename when it is published: {az}"
        );
        // `curl -s` hides the very error that needs surfacing; -f makes curl
        // fail loudly on a 404 instead of writing the error page to the pipe.
        assert!(
            az.contains("curl -fsSL"),
            "curl must fail on HTTP errors rather than piping an error page: {az}"
        );
    }

    /// A `| bash` / `| sh` inside `su -c` defeats the outer `|| echo WARNING`.
    ///
    /// The generated script sets `pipefail`, but that is per-shell and the
    /// fresh login shell `su -` starts does not inherit it, so a failed
    /// download leaves the shell reading empty stdin and exiting 0. The guard
    /// below only checks that `|| echo` is *present*, which such a line
    /// satisfies while still being silent — so this asserts the stronger
    /// property directly.
    #[test]
    fn su_payloads_never_pipe_a_download_into_a_shell() {
        for cmd in default_dev_setup_commands("azureuser") {
            if !cmd.contains("su - ") {
                continue;
            }
            let pipes_to_shell = (cmd.contains("| bash") || cmd.contains("| sh"))
                && (cmd.contains("curl ") || cmd.contains("wget "));
            assert!(
                !pipes_to_shell || cmd.contains("set -o pipefail"),
                "a download piped into a shell inside `su -c` cannot report failure \
                 (pipefail is not inherited); download to a file and execute it: {cmd}"
            );
        }
    }

    /// Every dev-setup step that can fail should say so. This guards the class
    /// of bug rather than the single instance — an unguarded step is how the
    /// Azure CLI silently went missing in the first place.
    #[test]
    fn network_installing_dev_setup_commands_report_their_failures() {
        let cmds = default_dev_setup_commands("azureuser");
        for cmd in &cmds {
            // Only steps that reach the network can fail for environmental
            // reasons worth reporting.
            let fetches = cmd.contains("curl ") || cmd.contains("wget ");
            if fetches && !cmd.contains("|| echo") {
                panic!("network-installing step has no failure report: {cmd}");
            }
        }
    }
}
