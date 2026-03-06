use super::*;

/// Validate and split a `KEY=VALUE` string. Returns `None` on bad input.
pub fn split_env_var(input: &str) -> Option<(&str, &str)> {
    let parts: Vec<&str> = input.splitn(2, '=').collect();
    if parts.len() == 2 && !parts[0].is_empty() {
        Some((parts[0], parts[1]))
    } else {
        None
    }
}

/// Validate that an env key contains only safe characters (alphanumeric + underscore).
pub fn validate_env_key(key: &str) -> Result<(), String> {
    if key.is_empty() {
        return Err("Environment variable key must not be empty".into());
    }
    if !key.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
        return Err(format!(
            "Environment variable key '{}' contains invalid characters; only [A-Za-z0-9_] allowed",
            key
        ));
    }
    if key.starts_with(|c: char| c.is_ascii_digit()) {
        return Err(format!(
            "Environment variable key '{}' must not start with a digit",
            key
        ));
    }
    Ok(())
}

/// Build the shell command that upserts `KEY=VALUE` in `~/.profile`.
/// The `escaped_value` must already be shell-escaped (e.g. via `shell_escape`).
pub fn build_env_set_cmd(key: &str, escaped_value: &str) -> String {
    // Validate key to prevent injection through the key name
    if validate_env_key(key).is_err() {
        // Return a harmless no-op rather than an injectable command
        return "true".to_string();
    }
    format!(
        "grep -q '^export {}=' ~/.profile 2>/dev/null && sed -i 's/^export {}=.*/export {}={}/' ~/.profile || echo 'export {}={}' >> ~/.profile",
        key, key, key, escaped_value, key, escaped_value
    )
}

/// Build the shell command that removes a key from `~/.profile`.
pub fn build_env_delete_cmd(key: &str) -> String {
    // Validate key to prevent injection through the key name
    if validate_env_key(key).is_err() {
        // Return a harmless no-op rather than an injectable command
        return "true".to_string();
    }
    format!("sed -i '/^export {}=/d' ~/.profile", key)
}

/// The command used to list environment variables on a remote VM.
pub fn env_list_cmd() -> &'static str {
    "env | sort"
}

/// Parse the output of `env | sort` into `(key, value)` pairs.
pub fn parse_env_output(output: &str) -> Vec<(String, String)> {
    output
        .lines()
        .filter_map(|line| {
            line.split_once('=')
                .map(|(k, v)| (k.to_string(), v.to_string()))
        })
        .collect()
}

/// Build a file body suitable for `env export` (one `KEY=VALUE` per line).
pub fn build_env_file(vars: &[(String, String)]) -> String {
    vars.iter()
        .map(|(k, v)| format!("{}={}", k, v))
        .collect::<Vec<_>>()
        .join("\n")
}

/// Parse a `.env`-style file, skipping blank lines and `#` comments.
pub fn parse_env_file(content: &str) -> Vec<(String, String)> {
    content
        .lines()
        .map(|l| l.trim())
        .filter(|l| !l.is_empty() && !l.starts_with('#'))
        .filter_map(|l| {
            l.split_once('=')
                .map(|(k, v)| (k.to_string(), v.to_string()))
        })
        .collect()
}

/// The command used to clear all custom env vars from `~/.profile`.
pub fn env_clear_cmd() -> &'static str {
    "sed -i '/^export /d' ~/.profile"
}
