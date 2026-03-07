//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Keys handlers ───────────────────────────────────────────────────────

/// Build rows for the keys list table from directory entries.
/// Each row: [filename, key_type, size_bytes, modified_date]
pub fn build_key_list_row(name: &str, size: u64, modified: &str) -> Vec<String> {
    let key_type = if name.contains("ed25519") {
        "ed25519"
    } else if name.contains("ecdsa") {
        "ecdsa"
    } else if name.contains("rsa") {
        "rsa"
    } else if name.contains("dsa") {
        "dsa"
    } else {
        "unknown"
    };
    vec![
        name.to_string(),
        key_type.to_string(),
        size.to_string(),
        modified.to_string(),
    ]
}

/// Determine if a file looks like an SSH key based on its name and
/// whether its .pub companion exists.
pub fn is_ssh_key_file(name: &str, has_pub_companion: bool) -> bool {
    name.ends_with(".pub")
        || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name)
        || (!name.starts_with('.') && !name.ends_with(".pub") && has_pub_companion)
}

/// Format the key export success message.
pub fn format_key_exported(source_name: &str, dest: &str) -> String {
    format!("Exported {} to {}", source_name, dest)
}

/// Format the key backup success message.
pub fn format_key_backup(count: u32, dest: &str) -> String {
    format!("Backed up {} key files to {}", count, dest)
}

/// Format the key rotation complete message.
pub fn format_key_rotation_complete() -> &'static str {
    "Key rotation complete."
}
