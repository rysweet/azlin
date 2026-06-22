use std::path::Path;

/// Validate a config file path doesn't escape the expected config directory.
pub fn validate_config_path(path: &str) -> Result<(), String> {
    let p = Path::new(path);
    // Reject traversal components
    for component in p.components() {
        if let std::path::Component::ParentDir = component {
            return Err(format!(
                "Config path '{}' contains parent directory traversal",
                path
            ));
        }
    }
    Ok(())
}
