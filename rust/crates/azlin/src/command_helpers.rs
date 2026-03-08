/// Check whether a command string is allowed for execution.
/// Currently only allows commands starting with `"az "`.
pub fn is_allowed_command(cmd: &str) -> bool {
    cmd.trim().starts_with("az ")
}

/// Classify a command and return a user-facing skip reason, or `None` if it's allowed.
pub fn skip_reason(cmd: &str) -> Option<String> {
    let trimmed = cmd.trim();
    if trimmed.is_empty() {
        Some("empty command".to_string())
    } else if !is_allowed_command(trimmed) {
        Some(format!("Skipping non-Azure command: {}", trimmed))
    } else {
        None
    }
}
