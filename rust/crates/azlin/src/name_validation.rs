/// Reject names that don't match the positive allowlist.
///
/// A valid name consists only of ASCII alphanumerics, hyphens, underscores,
/// and dots (but not `..`).  This enforces the allowlist rather than
/// blocklisting specific characters, preventing injection into JMESPath
/// queries, filenames, and shell arguments.
pub fn validate_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("Name must not be empty".into());
    }
    if name.contains("..") {
        return Err(format!("Name '{}' contains '..' (path traversal)", name));
    }
    if let Some(ch) = name.chars().find(|c| {
        !c.is_ascii_alphanumeric() && *c != '-' && *c != '_' && *c != '.'
    }) {
        return Err(format!(
            "Name '{}' contains invalid character '{}' (only a-z, A-Z, 0-9, hyphen, underscore, dot allowed)",
            name, ch
        ));
    }
    Ok(())
}
