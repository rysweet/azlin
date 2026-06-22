/// Azure VM names: 1-64 chars, alphanumeric and hyphens, no leading/trailing hyphen.
pub fn validate_vm_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("VM name must not be empty".into());
    }
    if name.len() > 64 {
        return Err(format!(
            "VM name '{}' exceeds 64 character limit (got {})",
            &name[..32],
            name.len()
        ));
    }
    if name.starts_with('-') {
        return Err(format!("VM name '{}' must not start with a hyphen", name));
    }
    if name.ends_with('-') {
        return Err(format!("VM name '{}' must not end with a hyphen", name));
    }
    if !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        return Err(format!(
            "VM name '{}' contains invalid characters; only [a-zA-Z0-9-] allowed",
            name
        ));
    }
    Ok(())
}
