/// Build the full development tools update script.
pub fn build_dev_update_script() -> &'static str {
    concat!(
        "#!/bin/bash\n",
        "set -e\n",
        "echo 'Updating system packages...'\n",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq\n",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq\n",
        "echo 'Updating Rust toolchain...'\n",
        "if command -v rustup &>/dev/null; then rustup update 2>/dev/null || true; fi\n",
        "echo 'Updating Python packages...'\n",
        "if command -v pip3 &>/dev/null; then pip3 install --upgrade pip 2>/dev/null || true; fi\n",
        "echo 'Updating Node.js packages...'\n",
        "if command -v npm &>/dev/null; then sudo npm install -g npm 2>/dev/null || true; fi\n",
        "echo 'Development tools updated.'\n",
    )
}

/// Build the OS-only update command.
pub fn build_os_update_cmd() -> &'static str {
    "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq"
}

/// Map a log type name to its file path on the remote VM.
#[allow(dead_code)]
pub fn log_type_to_path(log_type: &str) -> &'static str {
    match log_type {
        "cloud-init" | "CloudInit" => "/var/log/cloud-init-output.log",
        "syslog" | "Syslog" => "/var/log/syslog",
        "auth" | "Auth" => "/var/log/auth.log",
        _ => "/var/log/syslog",
    }
}
