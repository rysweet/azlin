//! Reading and writing the auth profiles under `~/.azlin/profiles/`.
//!
//! Profiles were write-only. `azlin auth setup` saved one, `azlin auth list`
//! and `auth show` printed it back, and nothing else in azlin ever read one:
//! `--auth-profile` was declared on `ask`, `code` and `show` and discarded by
//! all three (#1089), and `azlin auth test --profile prod` ran
//! `az account show` and reported "Authentication successful!" about whatever
//! the CLI happened to be logged into — a success message for a profile it
//! never touched.
//!
//! What a profile can and cannot do
//! --------------------------------
//! A profile stores a tenant, a client id and a subscription id. It stores no
//! secret and no token, so it cannot *perform* a login; azlin has no way to
//! become a service principal from what is on disk. What it can do is pin the
//! subscription and tenant a command runs against, which is the same thing an
//! azlin context does and uses the same verified switch
//! ([`azlin_azure::AzureAuth::for_subscription`]).
//!
//! That is deliberately less than the flag's help implies, and the commands
//! say so rather than implying more.

use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

/// One stored authentication profile.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct AuthProfile {
    pub name: String,
    pub tenant_id: Option<String>,
    pub client_id: Option<String>,
    pub subscription_id: Option<String>,
    /// `--use-certificate`: recorded so the profile describes how the
    /// principal authenticates, even though azlin does not perform the login.
    pub use_certificate: bool,
    /// `--certificate-path`, validated at write time.
    pub certificate_path: Option<PathBuf>,
}

/// Where profiles live, given the azlin home directory.
pub fn profiles_dir(azlin_dir: &Path) -> PathBuf {
    azlin_dir.join("profiles")
}

/// The file backing one profile.
pub fn profile_path(azlin_dir: &Path, name: &str) -> PathBuf {
    profiles_dir(azlin_dir).join(format!("{}.json", name))
}

/// Parse a profile from its stored JSON.
///
/// Unknown fields are ignored and missing ones are `None` rather than an
/// error: a profile written by an older azlin has to keep working, and the
/// caller decides which fields it actually needs.
pub fn parse(name: &str, json: &serde_json::Value) -> AuthProfile {
    let string = |key: &str| {
        json.get(key)
            .and_then(|v| v.as_str())
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
    };
    AuthProfile {
        name: name.to_string(),
        tenant_id: string("tenant_id"),
        client_id: string("client_id"),
        subscription_id: string("subscription_id"),
        use_certificate: json
            .get("use_certificate")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
        certificate_path: string("certificate_path").map(PathBuf::from),
    }
}

/// Render a profile for storage.
///
/// Certificate fields are only written when a certificate is in use, so a
/// password-based profile does not carry a `"certificate_path": null` that
/// reads like a missing value rather than an inapplicable one.
pub fn to_json(profile: &AuthProfile) -> serde_json::Value {
    let mut map = serde_json::Map::new();
    for (key, value) in [
        ("tenant_id", profile.tenant_id.as_deref()),
        ("client_id", profile.client_id.as_deref()),
        ("subscription_id", profile.subscription_id.as_deref()),
    ] {
        if let Some(value) = value {
            map.insert(key.to_string(), serde_json::Value::from(value));
        }
    }
    if profile.use_certificate {
        map.insert("use_certificate".to_string(), serde_json::Value::Bool(true));
        if let Some(path) = &profile.certificate_path {
            map.insert(
                "certificate_path".to_string(),
                serde_json::Value::from(path.to_string_lossy().to_string()),
            );
        }
    }
    serde_json::Value::Object(map)
}

/// Names of the profiles on disk, sorted.
pub fn list_names(azlin_dir: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(profiles_dir(azlin_dir)) else {
        return Vec::new();
    };
    let mut names: Vec<String> = entries
        .flatten()
        .filter_map(|e| {
            let name = e.file_name().to_string_lossy().to_string();
            name.strip_suffix(".json").map(str::to_string)
        })
        .collect();
    names.sort();
    names
}

/// The error for a profile that is not there.
///
/// Lists what *is* there. "Profile 'prod' not found" with no list is a dead
/// end when the profile is called `production`.
pub fn not_found_message(name: &str, available: &[String]) -> String {
    if available.is_empty() {
        format!(
            "Authentication profile '{name}' not found, and no profiles exist. \
             Create one with `azlin auth setup --profile {name}`."
        )
    } else {
        format!(
            "Authentication profile '{name}' not found. Available: {}. \
             Create it with `azlin auth setup --profile {name}`.",
            available.join(", ")
        )
    }
}

/// Load one profile by name.
pub fn load(azlin_dir: &Path, name: &str) -> Result<AuthProfile> {
    crate::name_validation::validate_name(name)
        .map_err(|e| anyhow::anyhow!("Invalid profile name: {}", e))?;
    let path = profile_path(azlin_dir, name);
    if !path.exists() {
        anyhow::bail!("{}", not_found_message(name, &list_names(azlin_dir)));
    }
    let content = std::fs::read_to_string(&path)
        .with_context(|| format!("Failed to read auth profile '{}'", name))?;
    let json: serde_json::Value = serde_json::from_str(&content)
        .with_context(|| format!("Failed to parse auth profile '{}'", name))?;
    Ok(parse(name, &json))
}

/// The subscription a profile pins, or an error saying why it cannot pin one.
///
/// A profile with no `subscription_id` is not a usable target: switching to
/// "nothing" would silently leave the command on whatever subscription was
/// already selected, which is the failure `--auth-profile` exists to prevent.
pub fn require_subscription(profile: &AuthProfile) -> Result<&str> {
    profile.subscription_id.as_deref().ok_or_else(|| {
        anyhow::anyhow!(
            "Authentication profile '{}' records no subscription_id, so it cannot say \
             which subscription to run against. Re-run `azlin auth setup --profile {}` \
             with --subscription-id.",
            profile.name,
            profile.name
        )
    })
}

/// Validate the certificate flags of `azlin auth setup`.
///
/// Both were accepted and discarded, so `--use-certificate` produced a profile
/// indistinguishable from a password-based one and `--certificate-path` to a
/// file that did not exist was recorded as success.
pub fn validate_certificate_flags(
    use_certificate: bool,
    certificate_path: Option<&Path>,
) -> Result<()> {
    match (use_certificate, certificate_path) {
        (false, Some(path)) => anyhow::bail!(
            "--certificate-path {} was given without --use-certificate. Add \
             --use-certificate, or drop the path.",
            path.display()
        ),
        (true, None) => anyhow::bail!(
            "--use-certificate needs --certificate-path pointing at the certificate file."
        ),
        (true, Some(path)) => {
            if !path.exists() {
                anyhow::bail!(
                    "--certificate-path {} does not exist. A profile recorded against a \
                     missing certificate cannot authenticate, and nothing would say so \
                     until it was used.",
                    path.display()
                );
            }
            if path.is_dir() {
                anyhow::bail!(
                    "--certificate-path {} is a directory, not a certificate file.",
                    path.display()
                );
            }
            Ok(())
        }
        (false, None) => Ok(()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn json(s: &str) -> serde_json::Value {
        serde_json::from_str(s).unwrap()
    }

    #[test]
    fn parses_the_fields_azlin_writes() {
        let p = parse(
            "prod",
            &json(
                r#"{"tenant_id":"t","client_id":"c","subscription_id":"s",
                    "use_certificate":true,"certificate_path":"/tmp/cert.pem"}"#,
            ),
        );
        assert_eq!(p.name, "prod");
        assert_eq!(p.tenant_id.as_deref(), Some("t"));
        assert_eq!(p.subscription_id.as_deref(), Some("s"));
        assert!(p.use_certificate);
        assert_eq!(p.certificate_path, Some(PathBuf::from("/tmp/cert.pem")));
    }

    /// A profile written by an older azlin has none of the certificate fields
    /// and must keep working.
    #[test]
    fn an_older_profile_still_parses() {
        let p = parse("old", &json(r#"{"tenant_id":"t","client_id":"c"}"#));
        assert_eq!(p.tenant_id.as_deref(), Some("t"));
        assert_eq!(p.subscription_id, None);
        assert!(!p.use_certificate);
    }

    /// An empty string is not a value. Treating `"subscription_id": ""` as a
    /// subscription would produce a switch to nothing.
    #[test]
    fn blank_fields_are_absent_not_empty() {
        let p = parse(
            "blank",
            &json(r#"{"subscription_id":"   ","tenant_id":""}"#),
        );
        assert_eq!(p.subscription_id, None);
        assert_eq!(p.tenant_id, None);
    }

    #[test]
    fn round_trips_through_json() {
        let p = AuthProfile {
            name: "prod".into(),
            tenant_id: Some("t".into()),
            client_id: Some("c".into()),
            subscription_id: Some("s".into()),
            use_certificate: true,
            certificate_path: Some(PathBuf::from("/tmp/cert.pem")),
        };
        assert_eq!(parse("prod", &to_json(&p)), p);
    }

    /// A password-based profile must not carry certificate keys at all: a
    /// `"certificate_path": null` reads as a missing value rather than an
    /// inapplicable one, and `auth show` would print it.
    #[test]
    fn a_password_profile_carries_no_certificate_keys() {
        let p = AuthProfile {
            name: "dev".into(),
            tenant_id: Some("t".into()),
            ..Default::default()
        };
        let rendered = to_json(&p);
        assert!(rendered.get("use_certificate").is_none());
        assert!(rendered.get("certificate_path").is_none());
    }

    #[test]
    fn a_missing_profile_names_the_ones_that_exist() {
        let msg = not_found_message("prod", &["dev".to_string(), "staging".to_string()]);
        assert!(msg.contains("dev, staging"), "{msg}");
        assert!(msg.contains("azlin auth setup"), "{msg}");
        let empty = not_found_message("prod", &[]);
        assert!(empty.contains("no profiles exist"), "{empty}");
    }

    /// Switching to "nothing" would leave the command on whatever subscription
    /// was already selected — the failure `--auth-profile` exists to prevent.
    #[test]
    fn a_profile_with_no_subscription_cannot_pin_one() {
        let p = AuthProfile {
            name: "dev".into(),
            ..Default::default()
        };
        let err = require_subscription(&p).unwrap_err().to_string();
        assert!(err.contains("records no subscription_id"), "{err}");
        assert!(err.contains("--subscription-id"), "{err}");
    }

    // ── `auth setup` certificate flags ───────────────────────────────

    #[test]
    fn a_certificate_path_without_the_flag_is_rejected() {
        let err = validate_certificate_flags(false, Some(Path::new("/tmp/cert.pem")))
            .unwrap_err()
            .to_string();
        assert!(err.contains("--use-certificate"), "{err}");
    }

    #[test]
    fn the_flag_without_a_path_is_rejected() {
        let err = validate_certificate_flags(true, None)
            .unwrap_err()
            .to_string();
        assert!(err.contains("--certificate-path"), "{err}");
    }

    /// A profile recorded against a certificate that is not there cannot
    /// authenticate, and nothing would say so until it was used.
    #[test]
    fn a_missing_certificate_file_is_rejected() {
        let err = validate_certificate_flags(true, Some(Path::new("/nonexistent/cert.pem")))
            .unwrap_err()
            .to_string();
        assert!(err.contains("does not exist"), "{err}");
    }

    #[test]
    fn a_real_certificate_file_is_accepted_and_neither_flag_is_fine() {
        let dir = tempfile::tempdir().unwrap();
        let cert = dir.path().join("cert.pem");
        std::fs::write(&cert, "not really a certificate").unwrap();
        assert!(validate_certificate_flags(true, Some(&cert)).is_ok());
        assert!(validate_certificate_flags(false, None).is_ok());
        // A directory is not a certificate.
        assert!(validate_certificate_flags(true, Some(dir.path())).is_err());
    }
}
