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
    ensure_ssh_keypair_in(&ssh_dir)
}

/// Core logic for [`ensure_ssh_keypair`], parameterised on `ssh_dir` so it
/// can be tested with a temp directory.
pub fn ensure_ssh_keypair_in(ssh_dir: &Path) -> Result<SshKeypair, String> {
    // Check for an existing keypair (both private + public must exist).
    if let Some(private) = find_preferred_private_key(ssh_dir) {
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
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .output();
        if let Ok(out) = regen {
            if out.status.success() {
                if let Err(e) = std::fs::write(&public, &out.stdout) {
                    eprintln!("Warning: could not write regenerated .pub: {e}");
                    let _ = std::fs::remove_file(&public);
                } else if public.exists() {
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
    std::fs::create_dir_all(ssh_dir).map_err(|e| format!("Cannot create ~/.ssh: {e}"))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(ssh_dir, std::fs::Permissions::from_mode(0o700))
            .map_err(|e| format!("Cannot set ~/.ssh permissions to 0700: {e}"))?;
    }

    let key_path = ssh_dir.join("id_ed25519_azlin");

    if key_path.exists() {
        return Err(format!(
            "Key file {} already exists but was not recognized as a valid pair. Remove it and retry.",
            key_path.display()
        ));
    }

    eprintln!(
        "No SSH key found. Generating {}...",
        key_path.display()
    );

    let key_path_str = key_path.to_string_lossy().to_string();
    let keygen_args = build_keygen_args(&key_path_str);
    let output = std::process::Command::new("ssh-keygen")
        .args(&keygen_args)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::piped())
        .output()
        .map_err(|e| format!("Failed to run ssh-keygen: {e}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("ssh-keygen failed: {}", stderr.trim()));
    }

    // Fix permissions on the private key
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Err(e) = std::fs::set_permissions(&key_path, std::fs::Permissions::from_mode(0o600))
        {
            eprintln!("Warning: could not set private key permissions to 0600: {e}");
        }
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

    // ── preferred_pubkey_names ────────────────────────────────────

    #[test]
    fn test_preferred_pubkey_names_matches_stems() {
        let names = preferred_pubkey_names();
        assert_eq!(names.len(), PREFERRED_KEY_STEMS.len());
        for (name, stem) in names.iter().zip(PREFERRED_KEY_STEMS.iter()) {
            assert_eq!(name, &format!("{stem}.pub"));
        }
    }

    // ── find_preferred_pubkey edge cases ─────────────────────────

    #[test]
    fn test_find_preferred_pubkey_none_when_empty() {
        let temp = tempfile::tempdir().unwrap();
        assert!(find_preferred_pubkey(temp.path()).is_none());
    }

    #[test]
    fn test_find_preferred_pubkey_skips_non_preferred() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("id_dsa.pub"), "k").unwrap();
        assert!(find_preferred_pubkey(temp.path()).is_none());
    }

    #[test]
    fn test_find_preferred_private_key_none_when_empty() {
        let temp = tempfile::tempdir().unwrap();
        assert!(find_preferred_private_key(temp.path()).is_none());
    }

    // ── ensure_ssh_keypair_in: existing pair found ───────────────

    #[test]
    fn test_ensure_finds_existing_azlin_key_pair() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("azlin_key"), "PRIV").unwrap();
        std::fs::write(temp.path().join("azlin_key.pub"), "PUB").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(!kp.generated);
        assert!(kp.private_key.ends_with("azlin_key"));
        assert!(kp.public_key.ends_with("azlin_key.pub"));
    }

    #[test]
    fn test_ensure_finds_existing_ed25519_pair() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("id_ed25519"), "PRIV").unwrap();
        std::fs::write(temp.path().join("id_ed25519.pub"), "PUB").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(!kp.generated);
        assert!(kp.private_key.ends_with("id_ed25519"));
    }

    #[test]
    fn test_ensure_finds_existing_rsa_pair() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("id_rsa"), "PRIV").unwrap();
        std::fs::write(temp.path().join("id_rsa.pub"), "PUB").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(!kp.generated);
        assert!(kp.private_key.ends_with("id_rsa"));
    }

    #[test]
    fn test_ensure_respects_priority_when_multiple_pairs_exist() {
        let temp = tempfile::tempdir().unwrap();
        // Lower priority
        std::fs::write(temp.path().join("id_rsa"), "PRIV").unwrap();
        std::fs::write(temp.path().join("id_rsa.pub"), "PUB").unwrap();
        // Higher priority
        std::fs::write(temp.path().join("id_ed25519_azlin"), "PRIV2").unwrap();
        std::fs::write(temp.path().join("id_ed25519_azlin.pub"), "PUB2").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(!kp.generated);
        assert!(kp.private_key.ends_with("id_ed25519_azlin"));
    }

    #[test]
    fn test_ensure_returns_generated_false_for_existing() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("azlin_key"), "PRIV").unwrap();
        std::fs::write(temp.path().join("azlin_key.pub"), "PUB").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(!kp.generated, "should not mark existing key as generated");
    }

    // ── ensure_ssh_keypair_in: generation (requires ssh-keygen) ──

    #[test]
    fn test_ensure_generates_key_when_empty_dir() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert!(kp.generated, "key should be marked generated");
        assert!(kp.private_key.ends_with("id_ed25519_azlin"));
        assert!(kp.public_key.ends_with("id_ed25519_azlin.pub"));
        assert!(kp.private_key.exists(), "private key file must exist");
        assert!(kp.public_key.exists(), "public key file must exist");
    }

    #[test]
    fn test_ensure_generated_key_is_ed25519() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        let pub_content = std::fs::read_to_string(&kp.public_key).unwrap();
        assert!(
            pub_content.starts_with("ssh-ed25519 "),
            "generated key should be ed25519, got: {}",
            &pub_content[..pub_content.len().min(40)]
        );
    }

    #[test]
    fn test_ensure_generated_key_has_azlin_comment() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        let pub_content = std::fs::read_to_string(&kp.public_key).unwrap();
        assert!(
            pub_content.contains("azlin-rotated"),
            "generated key should have azlin-rotated comment"
        );
    }

    #[cfg(unix)]
    #[test]
    fn test_ensure_generated_private_key_has_0600_perms() {
        use std::os::unix::fs::PermissionsExt;
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        let perms = std::fs::metadata(&kp.private_key).unwrap().permissions();
        assert_eq!(
            perms.mode() & 0o777,
            0o600,
            "private key should have 0600 permissions"
        );
    }

    #[test]
    fn test_ensure_creates_ssh_dir_if_missing() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("nonexistent_ssh");

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert!(kp.generated);
        assert!(ssh_dir.exists(), "ssh_dir should be created");
    }

    #[test]
    fn test_ensure_created_ssh_dir_has_0700_perms() {
        use std::os::unix::fs::PermissionsExt;
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("new_ssh_dir");

        let _kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        let perms = std::fs::metadata(&ssh_dir).unwrap().permissions();
        assert_eq!(
            perms.mode() & 0o777,
            0o700,
            "created .ssh dir should have 0700 permissions"
        );
    }

    #[test]
    fn test_ensure_idempotent_second_call_finds_generated_key() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp1 = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert!(kp1.generated);

        let kp2 = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert!(!kp2.generated, "second call should find existing key");
        assert_eq!(kp2.private_key, kp1.private_key);
    }

    // ── ensure_ssh_keypair_in: .pub regeneration ─────────────────

    #[test]
    fn test_ensure_regenerates_missing_pub_from_private() {
        // Generate a real key first, then delete .pub
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert!(kp.generated);
        let pub_path = kp.public_key.clone();

        // Remove .pub
        std::fs::remove_file(&pub_path).unwrap();
        assert!(!pub_path.exists());

        // Second call should regenerate .pub without generating=true
        let kp2 = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert!(!kp2.generated, "should regenerate .pub, not generate new key");
        assert!(pub_path.exists(), ".pub should be regenerated");
    }

    // ── ensure_ssh_keypair_in: private-only with bogus data ──────

    #[test]
    fn test_ensure_with_bogus_private_key_generates_new() {
        let temp = tempfile::tempdir().unwrap();
        // Write a non-SSH-key file as "id_ed25519"
        std::fs::write(temp.path().join("id_ed25519"), "not a real key").unwrap();
        // No .pub file

        // ssh-keygen -y will fail on the bogus file, so ensure should
        // fall through to generating a new id_ed25519_azlin
        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(kp.generated);
        assert!(kp.private_key.ends_with("id_ed25519_azlin"));
    }

    // ── SshKeypair struct ────────────────────────────────────────

    #[test]
    fn test_ssh_keypair_paths_are_absolute_when_input_is_absolute() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("azlin_key"), "P").unwrap();
        std::fs::write(temp.path().join("azlin_key.pub"), "P").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        assert!(kp.private_key.is_absolute());
        assert!(kp.public_key.is_absolute());
    }

    // ── gap-filling: edge cases & error paths ────────────────────

    #[test]
    fn test_detect_key_type_azlin_key_is_unknown() {
        // "azlin_key" contains none of ed25519/rsa/ecdsa/dsa
        assert_eq!(detect_key_type("azlin_key"), "unknown");
    }

    #[test]
    fn test_is_known_key_name_id_dsa() {
        assert!(is_known_key_name("id_dsa"));
        assert!(is_known_key_name("id_dsa.pub"));
    }

    #[test]
    fn test_is_known_key_name_id_ecdsa() {
        assert!(is_known_key_name("id_ecdsa"));
        assert!(is_known_key_name("id_ecdsa.pub"));
    }

    #[test]
    fn test_find_preferred_pubkey_single_lowest_priority() {
        let temp = tempfile::tempdir().unwrap();
        // Only id_rsa (lowest preferred priority) present
        std::fs::write(temp.path().join("id_rsa.pub"), "k").unwrap();
        let p = find_preferred_pubkey(temp.path()).unwrap();
        assert!(p.ends_with("id_rsa.pub"));
    }

    #[test]
    fn test_find_preferred_private_key_skips_non_preferred() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("id_dsa"), "k").unwrap();
        assert!(find_preferred_private_key(temp.path()).is_none());
    }

    #[test]
    fn test_ensure_generated_key_pub_priv_are_siblings() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        assert_eq!(
            kp.private_key.parent(),
            kp.public_key.parent(),
            "private and public keys must be in the same directory"
        );
    }

    #[test]
    fn test_ensure_skips_lower_priority_complete_pair_when_higher_has_bogus_private() {
        // Scenario: id_ed25519 (higher priority) has bogus private + no pub,
        //           id_rsa (lower priority) has valid pair.
        // Expected: code tries id_ed25519 first, regen fails, falls through
        //           to generate NEW key (does NOT fall back to id_rsa pair).
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("id_ed25519"), "bogus").unwrap();
        std::fs::write(temp.path().join("id_rsa"), "PRIV").unwrap();
        std::fs::write(temp.path().join("id_rsa.pub"), "PUB").unwrap();

        let kp = ensure_ssh_keypair_in(temp.path()).unwrap();
        // The code finds id_ed25519 first (higher priority), fails regen,
        // then generates a brand new id_ed25519_azlin instead of using id_rsa.
        assert!(kp.generated, "should generate new key, not fall back to id_rsa");
        assert!(
            kp.private_key.ends_with("id_ed25519_azlin"),
            "should generate azlin key, got: {:?}",
            kp.private_key
        );
    }

    #[cfg(unix)]
    #[test]
    fn test_ensure_error_when_ssh_dir_is_a_file() {
        let temp = tempfile::tempdir().unwrap();
        // Create a regular file where the "ssh_dir" should be a directory
        let fake_dir = temp.path().join("not_a_dir");
        std::fs::write(&fake_dir, "I am a file").unwrap();

        let result = ensure_ssh_keypair_in(&fake_dir);
        // find_preferred_private_key returns None (not a dir), then
        // create_dir_all fails because a file exists at that path
        assert!(result.is_err(), "should fail when ssh_dir is a file");
    }

    #[test]
    fn test_ensure_public_key_content_is_nonempty_after_generation() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        let content = std::fs::read_to_string(&kp.public_key).unwrap();
        assert!(!content.trim().is_empty(), "public key must have content");
    }

    #[test]
    fn test_ensure_private_key_content_is_nonempty_after_generation() {
        let temp = tempfile::tempdir().unwrap();
        let ssh_dir = temp.path().join("dot_ssh");
        std::fs::create_dir_all(&ssh_dir).unwrap();

        let kp = ensure_ssh_keypair_in(&ssh_dir).unwrap();
        let content = std::fs::read_to_string(&kp.private_key).unwrap();
        assert!(!content.trim().is_empty(), "private key must have content");
    }
}
