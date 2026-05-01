use std::path::{Path, PathBuf};

/// Result of ensuring an SSH keypair exists.
pub struct SshKeypair {
    /// Path to the private key.
    pub private_key: PathBuf,
    /// Path to the public key.
    pub public_key: PathBuf,
    /// True when the key was just generated (caller may need to push it to a VM).
    pub generated: bool,
}

/// Well-known private key basenames (no `.pub` suffix).
pub const KNOWN_PRIVATE_KEYS: &[&str] = &[
    "azlin_key",
    "id_ed25519_azlin",
    "id_ed25519",
    "id_rsa",
    "id_ecdsa",
    "id_dsa",
];

/// Priority-ordered SSH key stems shared by both public and private resolution.
pub const PREFERRED_KEY_STEMS: &[&str] = &["azlin_key", "id_ed25519_azlin", "id_ed25519", "id_rsa"];

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
/// (the preferred azlin key pair plus any file whose name starts with `id_`).
pub fn is_key_backup_candidate(name: &str) -> bool {
    matches!(name, "azlin_key" | "azlin_key.pub") || name.starts_with("id_")
}

/// Find the first preferred public key that exists inside `ssh_dir`.
pub fn find_preferred_pubkey(ssh_dir: &Path) -> Option<std::path::PathBuf> {
    PREFERRED_KEY_STEMS
        .iter()
        .map(|stem| ssh_dir.join(format!("{stem}.pub")))
        .find(|p| p.exists())
}

/// Find the first preferred private key that exists inside `ssh_dir`.
pub fn find_preferred_private_key(ssh_dir: &Path) -> Option<std::path::PathBuf> {
    PREFERRED_KEY_STEMS
        .iter()
        .map(|stem| ssh_dir.join(stem))
        .find(|p| p.exists())
}

/// Return the preferred public key filenames in priority order for display.
pub fn preferred_pubkey_names() -> Vec<String> {
    PREFERRED_KEY_STEMS
        .iter()
        .map(|stem| format!("{stem}.pub"))
        .collect()
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

/// Ensure an SSH keypair exists, generating one if necessary.
///
/// Returns the paths to the private and public keys, plus a flag indicating
/// whether the keypair was freshly generated (so the caller can push the
/// public key to a VM).
pub fn ensure_ssh_keypair() -> Result<SshKeypair, String> {
    let ssh_dir = dirs::home_dir()
        .ok_or_else(|| "Cannot determine home directory".to_string())?
        .join(".ssh");

    // Check for an existing keypair (both private + public must exist).
    if let Some(private) = find_preferred_private_key(&ssh_dir) {
        let public = private.with_extension("pub");
        // If only the private key exists, derive a .pub manually isn't
        // feasible, but we should still check before claiming success.
        if public.exists() {
            return Ok(SshKeypair {
                private_key: private,
                public_key: public,
                generated: false,
            });
        }
        // Private exists but .pub is missing — try to regenerate the .pub
        let regen = std::process::Command::new("ssh-keygen")
            .args(["-y", "-f"])
            .arg(&private)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .output();
        if let Ok(out) = regen {
            if out.status.success() {
                let _ = std::fs::write(&public, &out.stdout);
                if public.exists() {
                    return Ok(SshKeypair {
                        private_key: private,
                        public_key: public,
                        generated: false,
                    });
                }
            }
        }
    }

    // No usable keypair — generate a new one.
    std::fs::create_dir_all(&ssh_dir).map_err(|e| format!("Cannot create ~/.ssh: {e}"))?;

    let key_path = ssh_dir.join("id_ed25519_azlin");
    let key_path_str = key_path.to_string_lossy().to_string();

    eprintln!(
        "No SSH key found. Generating {}...",
        key_path.display()
    );

    let keygen_args = build_keygen_args(&key_path_str);
    let status = std::process::Command::new("ssh-keygen")
        .args(&keygen_args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .status()
        .map_err(|e| format!("Failed to run ssh-keygen: {e}"))?;

    if !status.success() {
        return Err("ssh-keygen failed to generate a new key pair".to_string());
    }

    // Fix permissions on the private key
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&key_path, std::fs::Permissions::from_mode(0o600));
    }

    let pub_path = ssh_dir.join("id_ed25519_azlin.pub");
    if !pub_path.exists() {
        return Err("ssh-keygen ran but public key file was not created".to_string());
    }

    eprintln!("SSH key pair generated successfully.");

    Ok(SshKeypair {
        private_key: key_path,
        public_key: pub_path,
        generated: true,
    })
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
        assert!(is_known_key_name("azlin_key"));
        assert!(is_known_key_name("id_ed25519_azlin"));
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
        assert!(is_key_backup_candidate("azlin_key"));
        assert!(is_key_backup_candidate("azlin_key.pub"));
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

    #[test]
    fn test_find_preferred_pubkey_uses_priority_order() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("azlin_key.pub"), "k0").unwrap();
        std::fs::write(temp.path().join("id_rsa.pub"), "k1").unwrap();
        std::fs::write(temp.path().join("id_ed25519.pub"), "k2").unwrap();
        std::fs::write(temp.path().join("id_ed25519_azlin.pub"), "k3").unwrap();

        let p = find_preferred_pubkey(temp.path()).unwrap();
        assert!(p.ends_with("azlin_key.pub"));
    }

    #[test]
    fn test_find_preferred_private_key_uses_priority_order() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("azlin_key"), "k0").unwrap();
        std::fs::write(temp.path().join("id_rsa"), "k1").unwrap();
        std::fs::write(temp.path().join("id_ed25519"), "k2").unwrap();
        std::fs::write(temp.path().join("id_ed25519_azlin"), "k3").unwrap();

        let p = find_preferred_private_key(temp.path()).unwrap();
        assert!(p.ends_with("azlin_key"));
    }
}
