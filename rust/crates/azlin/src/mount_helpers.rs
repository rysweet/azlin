/// Validate a mount-point path is safe (no shell metacharacters, no traversal).
pub fn validate_mount_path(path: &str) -> Result<(), String> {
    if path.is_empty() {
        return Err("Mount path must not be empty".into());
    }
    if !path.starts_with('/') {
        return Err(format!("Mount path '{}' must be absolute", path));
    }
    // Reject shell metacharacters
    let bad_chars = [
        ';', '|', '&', '$', '`', '(', ')', '{', '}', '<', '>', '!', '\n', '\0',
    ];
    for c in bad_chars {
        if path.contains(c) {
            return Err(format!(
                "Mount path '{}' contains dangerous character '{}'",
                path, c
            ));
        }
    }
    // Reject traversal
    if path.contains("/../") || path.ends_with("/..") || path == ".." {
        return Err(format!("Mount path '{}' contains path traversal", path));
    }
    Ok(())
}
