use std::path::Path;

/// Build SSH command arguments for connecting to a VM.
pub fn build_ssh_args(username: &str, ip: &str, key: Option<&Path>) -> Vec<String> {
    let mut args = vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
    ];
    if let Some(key_path) = key {
        args.push("-i".to_string());
        args.push(key_path.display().to_string());
    }
    args.push(format!("{}@{}", username, ip));
    args
}

/// Build a VS Code remote SSH URI for a VM.
#[allow(dead_code)]
pub fn build_vscode_remote_uri(user: &str, ip: &str) -> String {
    format!("ssh-remote+{}@{}", user, ip)
}

/// Build SSH args for streaming logs via `tail -f`.
pub fn build_log_follow_args(username: &str, ip: &str, log_path: &str) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        "ConnectTimeout=10".to_string(),
        format!("{}@{}", username, ip),
        format!("sudo tail -f {}", log_path),
    ]
}

/// Build SSH args for fetching a specific number of log lines.
#[allow(dead_code)]
pub fn build_log_tail_args(username: &str, ip: &str, lines: u32, log_path: &str) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        "ConnectTimeout=10".to_string(),
        format!("{}@{}", username, ip),
        format!("sudo tail -n {} {}", lines, log_path),
    ]
}
