/// Build the full development tools update script.
/// The updates `azlin vm update-tools` performs, in order, one per step.
///
/// Kept as a list rather than one string so `--timeout` can mean what its help
/// says — "Timeout **per update** in seconds" — instead of a single budget for
/// the whole script.
const DEV_UPDATE_STEPS: [(&str, &str); 4] = [
    (
        "Updating system packages...",
        "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
         sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq",
    ),
    (
        "Updating Rust toolchain...",
        "if command -v rustup &>/dev/null; then rustup update 2>/dev/null || true; fi",
    ),
    (
        "Updating Python packages...",
        "if command -v pip3 &>/dev/null; then pip3 install --upgrade pip 2>/dev/null || true; fi",
    ),
    (
        "Updating Node.js packages...",
        "if command -v npm &>/dev/null; then sudo npm install -g npm 2>/dev/null || true; fi",
    ),
];

/// How many steps the script runs. The caller sizes the transport budget from
/// this, because a per-step limit says nothing about the total.
pub fn dev_update_step_count() -> u32 {
    DEV_UPDATE_STEPS.len() as u32
}

/// Build the dev-tools update script, bounding **each step** by `timeout_secs`.
///
/// `timeout_secs == 0` disables the bound, matching `timeout(1)`'s own reading
/// of 0 and the rest of azlin's timeout flags.
///
/// `set -e` means a step killed by `timeout` ends the script with 124, which
/// is what the caller reports as a timeout. The three optional steps keep
/// their `|| true`, so a missing rustup is still not an error — only a step
/// that hangs is.
pub fn build_dev_update_script(timeout_secs: u32) -> String {
    let mut script = String::from("#!/bin/bash\nset -e\n");
    for (banner, command) in DEV_UPDATE_STEPS {
        script.push_str(&format!("echo '{}'\n", banner));
        if timeout_secs == 0 {
            script.push_str(command);
        } else {
            script.push_str(&format!(
                "timeout {} bash -c {}",
                timeout_secs,
                quote(command)
            ));
        }
        script.push('\n');
    }
    script.push_str("echo 'Development tools updated.'\n");
    script
}

/// Single-quote a string for POSIX `sh`.
fn quote(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
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
