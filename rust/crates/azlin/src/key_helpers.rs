/// Detect the SSH key type from a filename.
pub fn detect_key_type(name: &str) -> &'static str {
    if name.contains("ed25519") {
        "ed25519"
    } else if name.contains("ecdsa") {
        "ecdsa"
    } else if name.contains("rsa") {
        "rsa"
    } else if name.contains("dsa") {
        "dsa"
    } else {
        "unknown"
    }
}

/// Determine whether a filename looks like an SSH key (without filesystem checks).
/// Returns true for `.pub` files and known private key names.
pub fn is_known_key_name(name: &str) -> bool {
    name.ends_with(".pub") || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name)
}
