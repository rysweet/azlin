use std::path::Path;

/// Well-known private key basenames (no `.pub` suffix).
pub const KNOWN_PRIVATE_KEYS: &[&str] = &["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"];

/// Priority-ordered list of public key filenames tried during export / sync-keys.
pub const PREFERRED_PUBKEYS: &[&str] = &["id_ed25519_azlin.pub", "id_ed25519.pub", "id_rsa.pub"];

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
    name.ends_with(".pub") || KNOWN_PRIVATE_KEYS.contains(&name)
}

/// Return true when a filename should be included in the key-backup set
/// (any file whose name starts with `id_`).
pub fn is_key_backup_candidate(name: &str) -> bool {
    name.starts_with("id_")
}

/// Find the first preferred public key that exists inside `ssh_dir`.
pub fn find_preferred_pubkey(ssh_dir: &Path) -> Option<std::path::PathBuf> {
    PREFERRED_PUBKEYS
        .iter()
        .map(|f| ssh_dir.join(f))
        .find(|p| p.exists())
}

/// Build the argument vector for `ssh-keygen` when generating a new
/// ed25519 key pair for azlin key rotation.
pub fn build_keygen_args(key_path: &str) -> Vec<&str> {
    vec![
        "-t",
        "ed25519",
        "-f",
        key_path,
        "-N",
        "",
        "-C",
        "azlin-rotated",
    ]
}

/// Build the JMESPath query fragment used to filter VMs by name prefix.
/// Returns `None` when `prefix` is empty (meaning "all VMs").
pub fn build_vm_prefix_query(prefix: &str) -> Option<String> {
    if prefix.is_empty() {
        None
    } else {
        Some(format!("[?starts_with(name, '{}')]", prefix))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── detect_key_type ──────────────────────────────────────────

    #[test]
    fn test_detect_key_type_ed25519() {
        assert_eq!(detect_key_type("id_ed25519"), "ed25519");
        assert_eq!(detect_key_type("id_ed25519.pub"), "ed25519");
        assert_eq!(detect_key_type("id_ed25519_azlin.pub"), "ed25519");
    }

    #[test]
    fn test_detect_key_type_rsa() {
        assert_eq!(detect_key_type("id_rsa"), "rsa");
        assert_eq!(detect_key_type("id_rsa.pub"), "rsa");
    }

    #[test]
    fn test_detect_key_type_ecdsa() {
        assert_eq!(detect_key_type("id_ecdsa"), "ecdsa");
    }

    #[test]
    fn test_detect_key_type_dsa() {
        assert_eq!(detect_key_type("id_dsa"), "dsa");
    }

    #[test]
    fn test_detect_key_type_unknown() {
        assert_eq!(detect_key_type("authorized_keys"), "unknown");
        assert_eq!(detect_key_type("config"), "unknown");
    }

    // ── is_known_key_name ────────────────────────────────────────

    #[test]
    fn test_is_known_key_name_pub() {
        assert!(is_known_key_name("id_rsa.pub"));
        assert!(is_known_key_name("custom.pub"));
    }

    #[test]
    fn test_is_known_key_name_private() {
        assert!(is_known_key_name("id_rsa"));
        assert!(is_known_key_name("id_ed25519"));
    }

    #[test]
    fn test_is_known_key_name_other() {
        assert!(!is_known_key_name("config"));
        assert!(!is_known_key_name("known_hosts"));
    }

    // ── is_key_backup_candidate ──────────────────────────────────

    #[test]
    fn test_is_key_backup_candidate_true() {
        assert!(is_key_backup_candidate("id_rsa"));
        assert!(is_key_backup_candidate("id_ed25519.pub"));
        assert!(is_key_backup_candidate("id_ecdsa_custom"));
    }

    #[test]
    fn test_is_key_backup_candidate_false() {
        assert!(!is_key_backup_candidate("config"));
        assert!(!is_key_backup_candidate("known_hosts"));
        assert!(!is_key_backup_candidate("authorized_keys"));
    }

    // ── build_keygen_args ────────────────────────────────────────

    #[test]
    fn test_build_keygen_args_structure() {
        let args = build_keygen_args("/home/user/.ssh/id_ed25519_azlin");
        assert_eq!(args[0], "-t");
        assert_eq!(args[1], "ed25519");
        assert_eq!(args[2], "-f");
        assert_eq!(args[3], "/home/user/.ssh/id_ed25519_azlin");
        assert_eq!(args[4], "-N");
        assert_eq!(args[5], ""); // empty passphrase
        assert_eq!(args[6], "-C");
        assert_eq!(args[7], "azlin-rotated");
    }

    // ── build_vm_prefix_query ────────────────────────────────────

    #[test]
    fn test_build_vm_prefix_query_empty() {
        assert_eq!(build_vm_prefix_query(""), None);
    }

    #[test]
    fn test_build_vm_prefix_query_with_prefix() {
        let q = build_vm_prefix_query("dev-").unwrap();
        assert_eq!(q, "[?starts_with(name, 'dev-')]");
    }

    #[test]
    fn test_build_vm_prefix_query_special_chars() {
        let q = build_vm_prefix_query("vm_test").unwrap();
        assert!(q.contains("vm_test"));
    }
}
