/// Reject names containing path-traversal or null-byte characters.
///
/// A valid name consists only of ASCII alphanumerics, hyphens, underscores,
/// and dots (but not `..`).  No slashes, backslashes, or null bytes.
pub fn validate_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("Name must not be empty".into());
    }
    if name.contains('/') || name.contains('\\') {
        return Err(format!(
            "Name '{}' contains path separator characters",
            name
        ));
    }
    if name.contains('\0') {
        return Err(format!("Name '{}' contains a null byte", name));
    }
    if name.contains("..") {
        return Err(format!("Name '{}' contains '..' (path traversal)", name));
    }
    Ok(())
}
