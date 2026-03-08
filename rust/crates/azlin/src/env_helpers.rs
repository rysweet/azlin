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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_split_env_var_valid() {
        assert_eq!(split_env_var("FOO=bar"), Some(("FOO", "bar")));
    }

    #[test]
    fn test_split_env_var_value_with_equals() {
        assert_eq!(split_env_var("FOO=bar=baz"), Some(("FOO", "bar=baz")));
    }

    #[test]
    fn test_split_env_var_empty_value() {
        assert_eq!(split_env_var("FOO="), Some(("FOO", "")));
    }

    #[test]
    fn test_split_env_var_no_equals() {
        assert_eq!(split_env_var("FOOBAR"), None);
    }

    #[test]
    fn test_split_env_var_empty_key() {
        assert_eq!(split_env_var("=value"), None);
    }

    #[test]
    fn test_validate_env_key_valid() {
        assert!(validate_env_key("MY_VAR_123").is_ok());
    }

    #[test]
    fn test_validate_env_key_empty() {
        assert!(validate_env_key("").is_err());
    }

    #[test]
    fn test_validate_env_key_starts_with_digit() {
        assert!(validate_env_key("1BAD").is_err());
    }

    #[test]
    fn test_validate_env_key_special_chars() {
        assert!(validate_env_key("BAD-KEY").is_err());
    }

    #[test]
    fn test_build_env_set_cmd_valid() {
        let cmd = build_env_set_cmd("MY_VAR", "'hello'");
        assert!(cmd.contains("MY_VAR"));
        assert!(cmd.contains("'hello'"));
    }

    #[test]
    fn test_build_env_set_cmd_invalid_key() {
        let cmd = build_env_set_cmd("BAD-KEY!", "'val'");
        assert_eq!(cmd, "true"); // Returns no-op
    }

    #[test]
    fn test_build_env_delete_cmd_valid() {
        let cmd = build_env_delete_cmd("MY_VAR");
        assert!(cmd.contains("MY_VAR"));
        assert!(cmd.contains("sed"));
    }

    #[test]
    fn test_build_env_delete_cmd_invalid_key() {
        let cmd = build_env_delete_cmd("BAD;KEY");
        assert_eq!(cmd, "true");
    }

    #[test]
    fn test_env_list_cmd() {
        assert_eq!(env_list_cmd(), "env | sort");
    }

    #[test]
    fn test_parse_env_output_basic() {
        let output = "HOME=/home/user\nPATH=/usr/bin\n";
        let result = parse_env_output(output);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], ("HOME".to_string(), "/home/user".to_string()));
        assert_eq!(result[1], ("PATH".to_string(), "/usr/bin".to_string()));
    }

    #[test]
    fn test_parse_env_output_empty() {
        assert!(parse_env_output("").is_empty());
    }

    #[test]
    fn test_parse_env_output_value_with_equals() {
        let output = "FOO=bar=baz\n";
        let result = parse_env_output(output);
        assert_eq!(result[0], ("FOO".to_string(), "bar=baz".to_string()));
    }

    #[test]
    fn test_build_env_file() {
        let vars = vec![
            ("A".to_string(), "1".to_string()),
            ("B".to_string(), "2".to_string()),
        ];
        let out = build_env_file(&vars);
        assert_eq!(out, "A=1\nB=2");
    }

    #[test]
    fn test_build_env_file_empty() {
        let out = build_env_file(&[]);
        assert_eq!(out, "");
    }

    #[test]
    fn test_parse_env_file_with_comments() {
        let content = "# comment\nFOO=bar\n\n# another comment\nBAZ=qux\n";
        let result = parse_env_file(content);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], ("FOO".to_string(), "bar".to_string()));
        assert_eq!(result[1], ("BAZ".to_string(), "qux".to_string()));
    }

    #[test]
    fn test_parse_env_file_empty() {
        assert!(parse_env_file("").is_empty());
    }

    #[test]
    fn test_parse_env_file_only_comments() {
        assert!(parse_env_file("# comment\n# another").is_empty());
    }

    #[test]
    fn test_env_clear_cmd() {
        assert!(env_clear_cmd().contains("sed"));
    }
}
