use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

/// Known valid Azure regions (subset — allows any alphanumeric lowercase string
/// that matches the general Azure region pattern).
const VALID_AZURE_REGIONS: &[&str] = &[
    "eastus",
    "eastus2",
    "westus",
    "westus2",
    "westus3",
    "centralus",
    "northcentralus",
    "southcentralus",
    "westcentralus",
    "canadacentral",
    "canadaeast",
    "brazilsouth",
    "brazilsoutheast",
    "northeurope",
    "westeurope",
    "uksouth",
    "ukwest",
    "francecentral",
    "francesouth",
    "germanywestcentral",
    "germanynorth",
    "switzerlandnorth",
    "switzerlandwest",
    "norwayeast",
    "norwaywest",
    "swedencentral",
    "eastasia",
    "southeastasia",
    "japaneast",
    "japanwest",
    "koreacentral",
    "koreasouth",
    "australiaeast",
    "australiasoutheast",
    "australiacentral",
    "centralindia",
    "southindia",
    "westindia",
    "uaenorth",
    "uaecentral",
    "southafricanorth",
    "southafricawest",
    "qatarcentral",
    "polandcentral",
    "italynorth",
];

/// SSH key synchronization method.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum SshSyncMethod {
    #[default]
    Auto,
    Rsync,
    Scp,
}

impl std::fmt::Display for SshSyncMethod {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Auto => write!(f, "auto"),
            Self::Rsync => write!(f, "rsync"),
            Self::Scp => write!(f, "scp"),
        }
    }
}

/// Main azlin configuration, stored at ~/.azlin/config.toml
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct AzlinConfig {
    pub default_resource_group: Option<String>,
    pub default_region: String,
    pub default_vm_size: String,
    pub last_vm_name: Option<String>,
    pub notification_command: Option<String>,
    pub session_names: Option<HashMap<String, String>>,
    pub vm_storage: Option<HashMap<String, String>>,
    pub default_nfs_storage: Option<String>,
    pub github_runner_fleets: Option<HashMap<String, serde_json::Value>>,
    pub ssh_auto_sync_keys: bool,
    pub ssh_sync_timeout: u64,
    pub ssh_sync_method: SshSyncMethod,
    pub ssh_auto_sync_age_threshold: u64,
    pub ssh_auto_sync_skip_new_vms: bool,
    pub resource_group_auto_detect: bool,
    pub resource_group_cache_ttl: u64,
    pub resource_group_query_timeout: u64,
    pub bastion_detection_timeout: u64,
    /// Timeout in seconds for SSH/SCP connect operations.
    /// Default: 10 seconds. Increase on Windows/WSL where network ops are slower.
    pub ssh_connect_timeout: u64,
    /// Timeout in seconds for `az` CLI subprocess calls.
    /// Default: 120 seconds. Increase on Windows/WSL where Azure CLI is slower.
    pub az_cli_timeout: u64,
}

impl Default for AzlinConfig {
    fn default() -> Self {
        Self {
            default_resource_group: None,
            default_region: "westus2".to_string(),
            default_vm_size: "Standard_E16as_v5".to_string(),
            last_vm_name: None,
            notification_command: None,
            session_names: None,
            vm_storage: None,
            default_nfs_storage: None,
            github_runner_fleets: None,
            ssh_auto_sync_keys: true,
            ssh_sync_timeout: 30,
            ssh_sync_method: SshSyncMethod::Auto,
            ssh_auto_sync_age_threshold: 600,
            ssh_auto_sync_skip_new_vms: true,
            resource_group_auto_detect: true,
            resource_group_cache_ttl: 900,
            resource_group_query_timeout: 30,
            bastion_detection_timeout: 60,
            ssh_connect_timeout: 10,
            az_cli_timeout: 120,
        }
    }
}

impl AzlinConfig {
    /// Returns the config directory path.
    ///
    /// Checks `AZLIN_CONFIG_DIR` env var first, falls back to `~/.azlin/`.
    pub fn config_dir() -> crate::Result<PathBuf> {
        if let Ok(dir) = std::env::var("AZLIN_CONFIG_DIR") {
            return Ok(PathBuf::from(dir));
        }
        Ok(dirs::home_dir()
            .ok_or_else(|| crate::AzlinError::Config("Home directory not found".into()))?
            .join(".azlin"))
    }

    /// Returns the config file path (~/.azlin/config.toml)
    pub fn config_path() -> crate::Result<PathBuf> {
        Ok(Self::config_dir()?.join("config.toml"))
    }

    /// Load config from disk, returning defaults if file doesn't exist.
    ///
    /// # Examples
    ///
    /// ```
    /// use azlin_core::AzlinConfig;
    ///
    /// let config = AzlinConfig::load().unwrap();
    /// // Always returns a valid config with non-empty defaults
    /// assert!(!config.default_region.is_empty());
    /// assert!(!config.default_vm_size.is_empty());
    /// ```
    pub fn load() -> crate::Result<Self> {
        let path = Self::config_path()?;
        if !path.exists() {
            return Ok(Self::default());
        }
        let contents = std::fs::read_to_string(&path).map_err(|e| {
            crate::AzlinError::Config(format!(
                "Failed to read config at {}: {}",
                path.display(),
                e
            ))
        })?;
        toml::from_str(&contents)
            .map_err(|e| crate::AzlinError::Config(format!("Failed to parse config: {e}")))
    }

    /// Save config to disk, creating the directory if needed.
    ///
    /// # Examples
    ///
    /// ```
    /// use azlin_core::AzlinConfig;
    ///
    /// // Demonstrates the serialization round-trip that save() performs
    /// let config = AzlinConfig::default();
    /// let toml_str = toml::to_string_pretty(&config).unwrap();
    /// let loaded: AzlinConfig = toml::from_str(&toml_str).unwrap();
    /// assert_eq!(loaded.default_region, config.default_region);
    /// assert_eq!(loaded.default_vm_size, config.default_vm_size);
    /// ```
    pub fn save(&self) -> crate::Result<()> {
        let dir = Self::config_dir()?;
        std::fs::create_dir_all(&dir)
            .map_err(|e| crate::AzlinError::Config(format!("Failed to create config dir: {e}")))?;
        let path = Self::config_path()?;
        let contents = toml::to_string_pretty(self)
            .map_err(|e| crate::AzlinError::Config(format!("Failed to serialize config: {e}")))?;

        // Atomic write: write to temp file, set permissions, then rename.
        // This prevents config corruption if the process is interrupted mid-write,
        // and avoids a brief window where the file is world-readable.
        let tmp_path = path.with_extension("toml.tmp");
        std::fs::write(&tmp_path, &contents)
            .map_err(|e| crate::AzlinError::Config(format!("Failed to write temp config: {e}")))?;

        // Set file permissions to 600 on Unix BEFORE the rename
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&tmp_path, std::fs::Permissions::from_mode(0o600)).map_err(
                |e| {
                    let _ = std::fs::remove_file(&tmp_path);
                    crate::AzlinError::Config(format!("Failed to set permissions: {e}"))
                },
            )?;
        }

        // Verify the serialized TOML is valid before committing the write.
        // This prevents corrupt data from reaching config.toml.
        let _: AzlinConfig = toml::from_str(&contents).map_err(|e| {
            let _ = std::fs::remove_file(&tmp_path);
            crate::AzlinError::Config(format!(
                "BUG: save() produced invalid TOML — not writing: {e}"
            ))
        })?;

        // Atomic rename (on same filesystem, this is atomic on Unix)
        std::fs::rename(&tmp_path, &path).map_err(|e| {
            let _ = std::fs::remove_file(&tmp_path);
            crate::AzlinError::Config(format!("Failed to rename config: {e}"))
        })?;

        Ok(())
    }

    /// Boolean field names in the config.
    const BOOL_FIELDS: &[&str] = &[
        "ssh_auto_sync_keys",
        "ssh_auto_sync_skip_new_vms",
        "resource_group_auto_detect",
    ];

    /// Integer (u64) field names in the config.
    const U64_FIELDS: &[&str] = &[
        "ssh_sync_timeout",
        "ssh_auto_sync_age_threshold",
        "resource_group_cache_ttl",
        "resource_group_query_timeout",
        "bastion_detection_timeout",
        "ssh_connect_timeout",
        "az_cli_timeout",
    ];

    /// Validate a key/value pair before setting it.
    /// Returns `Ok(serde_json::Value)` with the properly typed JSON value,
    /// or an error describing the validation failure.
    ///
    /// # Examples
    ///
    /// ```
    /// use azlin_core::AzlinConfig;
    ///
    /// // Valid Azure region (case-insensitive)
    /// let val = AzlinConfig::validate_field("default_region", "eastus").unwrap();
    /// assert_eq!(val, serde_json::json!("eastus"));
    ///
    /// // Invalid region returns an error
    /// assert!(AzlinConfig::validate_field("default_region", "mars-west1").is_err());
    ///
    /// // VM size must start with "Standard_"
    /// let val = AzlinConfig::validate_field("default_vm_size", "Standard_D2s_v3").unwrap();
    /// assert_eq!(val, serde_json::json!("Standard_D2s_v3"));
    /// assert!(AzlinConfig::validate_field("default_vm_size", "Basic_A1").is_err());
    ///
    /// // Boolean fields accept "true" / "false"
    /// assert_eq!(
    ///     AzlinConfig::validate_field("ssh_auto_sync_keys", "true").unwrap(),
    ///     serde_json::json!(true),
    /// );
    ///
    /// // Integer fields are parsed to u64
    /// assert_eq!(
    ///     AzlinConfig::validate_field("ssh_sync_timeout", "60").unwrap(),
    ///     serde_json::json!(60),
    /// );
    ///
    /// // Unknown keys pass through as strings
    /// assert_eq!(
    ///     AzlinConfig::validate_field("custom_key", "value").unwrap(),
    ///     serde_json::json!("value"),
    /// );
    /// ```
    pub fn validate_field(key: &str, value: &str) -> crate::Result<serde_json::Value> {
        if key == "default_region" {
            let lower = value.to_lowercase();
            if !VALID_AZURE_REGIONS.contains(&lower.as_str()) {
                return Err(crate::AzlinError::Config(format!(
                    "Invalid Azure region '{}'. Examples: eastus, westus2, northeurope",
                    value
                )));
            }
            return Ok(serde_json::Value::String(lower));
        }

        if key == "default_vm_size" {
            if !value.starts_with("Standard_") {
                return Err(crate::AzlinError::Config(format!(
                    "VM size must start with 'Standard_' (e.g., 'Standard_E16as_v5'), got '{}'",
                    value
                )));
            }
            return Ok(serde_json::Value::String(value.to_string()));
        }

        if key == "ssh_sync_method" {
            match value.to_lowercase().as_str() {
                "auto" | "rsync" | "scp" => {
                    return Ok(serde_json::Value::String(value.to_lowercase()));
                }
                _ => {
                    return Err(crate::AzlinError::Config(format!(
                        "ssh_sync_method must be 'auto', 'rsync', or 'scp', got '{}'",
                        value
                    )));
                }
            }
        }

        if Self::BOOL_FIELDS.contains(&key) {
            match value {
                "true" => return Ok(serde_json::Value::Bool(true)),
                "false" => return Ok(serde_json::Value::Bool(false)),
                _ => {
                    return Err(crate::AzlinError::Config(format!(
                        "Field '{}' must be 'true' or 'false', got '{}'",
                        key, value
                    )));
                }
            }
        }

        if Self::U64_FIELDS.contains(&key) {
            let parsed = value.parse::<u64>().map_err(|_| {
                crate::AzlinError::Config(format!(
                    "Field '{}' must be a positive integer, got '{}'",
                    key, value
                ))
            })?;
            return Ok(serde_json::json!(parsed));
        }

        // Warn on unknown keys — helps catch typos like "defualt_region"
        const KNOWN_STRING_FIELDS: &[&str] = &[
            "default_resource_group",
            "default_region",
            "default_vm_size",
            "last_vm_name",
            "notification_command",
            "default_nfs_storage",
            "ssh_sync_method",
        ];
        if !KNOWN_STRING_FIELDS.contains(&key)
            && !Self::BOOL_FIELDS.contains(&key)
            && !Self::U64_FIELDS.contains(&key)
        {
            tracing::warn!(
                key,
                "Unknown config key — will be ignored. Known keys: default_region, \
                 default_vm_size, default_resource_group, ssh_auto_sync_keys, \
                 ssh_sync_timeout, ssh_sync_method, etc."
            );
        }

        // Pass through as string
        Ok(serde_json::Value::String(value.to_string()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = AzlinConfig::default();
        assert_eq!(config.default_region, "westus2");
        assert_eq!(config.default_vm_size, "Standard_E16as_v5");
        assert!(config.ssh_auto_sync_keys);
        assert_eq!(config.ssh_sync_timeout, 30);
        assert!(config.default_resource_group.is_none());
    }

    #[test]
    fn test_config_roundtrip() {
        let config = AzlinConfig {
            default_resource_group: Some("my-rg".to_string()),
            default_region: "eastus".to_string(),
            ..Default::default()
        };
        let serialized = toml::to_string_pretty(&config).unwrap();
        let deserialized: AzlinConfig = toml::from_str(&serialized).unwrap();
        assert_eq!(
            deserialized.default_resource_group,
            Some("my-rg".to_string())
        );
        assert_eq!(deserialized.default_region, "eastus");
    }

    #[test]
    fn test_config_deserialize_partial() {
        let toml_str = r#"
            default_region = "northeurope"
        "#;
        let config: AzlinConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(config.default_region, "northeurope");
        // Defaults should fill in missing fields
        assert_eq!(config.default_vm_size, "Standard_E16as_v5");
        assert!(config.ssh_auto_sync_keys);
    }

    #[test]
    fn test_config_save_load_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.toml");

        let config = AzlinConfig {
            default_resource_group: Some("test-rg".to_string()),
            ..Default::default()
        };

        let contents = toml::to_string_pretty(&config).unwrap();
        std::fs::write(&config_path, &contents).unwrap();

        let loaded: AzlinConfig =
            toml::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert_eq!(loaded.default_resource_group, Some("test-rg".to_string()));
    }

    #[test]
    fn test_validate_field_default_region_valid() {
        let result = AzlinConfig::validate_field("default_region", "eastus");
        assert!(result.is_ok());
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("eastus".to_string())
        );
    }

    #[test]
    fn test_validate_field_default_region_invalid() {
        let result = AzlinConfig::validate_field("default_region", "mars-west1");
        assert!(result.is_err());
        let err = result.unwrap_err().to_string();
        assert!(err.contains("Invalid Azure region"), "got: {err}");
    }

    #[test]
    fn test_validate_field_vm_size_valid() {
        let result = AzlinConfig::validate_field("default_vm_size", "Standard_E16as_v5");
        assert!(result.is_ok());
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("Standard_E16as_v5".to_string())
        );
    }

    #[test]
    fn test_validate_field_vm_size_invalid() {
        let result = AzlinConfig::validate_field("default_vm_size", "Basic_A1");
        assert!(result.is_err());
        let err = result.unwrap_err().to_string();
        assert!(err.contains("Standard_"), "got: {err}");
    }

    #[test]
    fn test_validate_field_bool_true() {
        let result = AzlinConfig::validate_field("ssh_auto_sync_keys", "true");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), serde_json::Value::Bool(true));
    }

    #[test]
    fn test_validate_field_bool_false() {
        let result = AzlinConfig::validate_field("ssh_auto_sync_keys", "false");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), serde_json::Value::Bool(false));
    }

    #[test]
    fn test_validate_field_bool_invalid() {
        let result = AzlinConfig::validate_field("ssh_auto_sync_keys", "yes");
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_field_u64_valid() {
        let result = AzlinConfig::validate_field("ssh_sync_timeout", "60");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), serde_json::json!(60u64));
    }

    #[test]
    fn test_validate_field_u64_invalid() {
        let result = AzlinConfig::validate_field("ssh_sync_timeout", "abc");
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_field_string_passthrough() {
        let result = AzlinConfig::validate_field("ssh_sync_method", "rsync");
        assert!(result.is_ok());
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("rsync".to_string())
        );
    }

    // ── Additional config tests ──────────────────────────────────────

    #[test]
    fn test_config_default_all_fields() {
        let config = AzlinConfig::default();
        assert!(config.last_vm_name.is_none());
        assert!(config.notification_command.is_none());
        assert!(config.session_names.is_none());
        assert!(config.vm_storage.is_none());
        assert!(config.default_nfs_storage.is_none());
        assert!(config.github_runner_fleets.is_none());
        assert_eq!(config.ssh_sync_method, SshSyncMethod::Auto);
        assert_eq!(config.ssh_auto_sync_age_threshold, 600);
        assert!(config.ssh_auto_sync_skip_new_vms);
        assert!(config.resource_group_auto_detect);
        assert_eq!(config.resource_group_cache_ttl, 900);
        assert_eq!(config.resource_group_query_timeout, 30);
        assert_eq!(config.bastion_detection_timeout, 60);
        assert_eq!(config.az_cli_timeout, 120);
    }

    #[test]
    fn test_validate_ssh_sync_method_valid() {
        for method in ["auto", "rsync", "scp"] {
            let result = AzlinConfig::validate_field("ssh_sync_method", method);
            assert!(result.is_ok(), "should accept '{method}'");
        }
    }

    #[test]
    fn test_validate_ssh_sync_method_invalid() {
        let result = AzlinConfig::validate_field("ssh_sync_method", "ftp");
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_az_cli_timeout() {
        let result = AzlinConfig::validate_field("az_cli_timeout", "300");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), serde_json::json!(300));
    }

    #[test]
    fn test_validate_unknown_key_passes_through() {
        // Unknown keys still pass through as strings (with a warning logged)
        let result = AzlinConfig::validate_field("totally_unknown_key", "value");
        assert!(result.is_ok());
    }

    #[test]
    fn test_ssh_sync_method_serde_roundtrip() {
        // Test that SshSyncMethod serializes/deserializes correctly in TOML
        let config = AzlinConfig {
            ssh_sync_method: SshSyncMethod::Rsync,
            ..Default::default()
        };
        let toml_str = toml::to_string_pretty(&config).unwrap();
        assert!(
            toml_str.contains("rsync"),
            "should serialize as lowercase: {toml_str}"
        );
        let loaded: AzlinConfig = toml::from_str(&toml_str).unwrap();
        assert_eq!(loaded.ssh_sync_method, SshSyncMethod::Rsync);
    }

    #[test]
    fn test_config_load_missing_file_returns_default() {
        let dir = tempfile::tempdir().unwrap();
        let missing_path = dir.path().join("nonexistent.toml");
        assert!(!missing_path.exists());
        // Loading from a missing file should produce defaults when using manual load
        let contents = "";
        let config: AzlinConfig = toml::from_str(contents).unwrap();
        assert_eq!(config.default_region, "westus2");
        assert_eq!(config.default_vm_size, "Standard_E16as_v5");
    }

    #[test]
    fn test_config_malformed_toml_returns_error() {
        let bad_toml = "this is not [valid toml {{{{";
        let result: Result<AzlinConfig, _> = toml::from_str(bad_toml);
        assert!(result.is_err(), "malformed TOML should fail to parse");
    }

    #[test]
    fn test_config_partial_toml_uses_defaults() {
        let partial = r#"default_region = "japaneast""#;
        let config: AzlinConfig = toml::from_str(partial).unwrap();
        assert_eq!(config.default_region, "japaneast");
        // All other fields should have defaults
        assert_eq!(config.default_vm_size, "Standard_E16as_v5");
        assert_eq!(config.az_cli_timeout, 120);
        assert_eq!(config.ssh_sync_method, SshSyncMethod::Auto);
    }

    #[test]
    fn test_config_save_load_roundtrip_with_all_fields() {
        let dir = tempfile::tempdir().unwrap();
        let config_path = dir.path().join("config.toml");

        let mut session_names = std::collections::HashMap::new();
        session_names.insert("vm-1".to_string(), "dev".to_string());

        let config = AzlinConfig {
            default_resource_group: Some("my-rg".to_string()),
            default_region: "eastus2".to_string(),
            default_vm_size: "Standard_D4s_v3".to_string(),
            last_vm_name: Some("last-vm".to_string()),
            notification_command: Some("notify-send".to_string()),
            session_names: Some(session_names),
            ssh_auto_sync_keys: false,
            ssh_sync_timeout: 60,
            ssh_sync_method: SshSyncMethod::Rsync,
            ssh_auto_sync_age_threshold: 1200,
            ssh_auto_sync_skip_new_vms: false,
            resource_group_auto_detect: false,
            resource_group_cache_ttl: 1800,
            resource_group_query_timeout: 60,
            bastion_detection_timeout: 120,
            ..Default::default()
        };

        let contents = toml::to_string_pretty(&config).unwrap();
        std::fs::write(&config_path, &contents).unwrap();

        let loaded: AzlinConfig =
            toml::from_str(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
        assert_eq!(loaded.default_resource_group, Some("my-rg".to_string()));
        assert_eq!(loaded.default_region, "eastus2");
        assert_eq!(loaded.default_vm_size, "Standard_D4s_v3");
        assert_eq!(loaded.last_vm_name, Some("last-vm".to_string()));
        assert_eq!(loaded.notification_command, Some("notify-send".to_string()));
        assert!(!loaded.ssh_auto_sync_keys);
        assert_eq!(loaded.ssh_sync_timeout, 60);
        assert_eq!(loaded.ssh_sync_method, SshSyncMethod::Rsync);
        assert!(!loaded.resource_group_auto_detect);
        assert_eq!(loaded.bastion_detection_timeout, 120);
    }

    #[test]
    fn test_config_merge_partial_overrides() {
        let toml_str = r#"
            default_region = "japaneast"
            ssh_sync_timeout = 120
            resource_group_auto_detect = false
        "#;
        let config: AzlinConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(config.default_region, "japaneast");
        assert_eq!(config.ssh_sync_timeout, 120);
        assert!(!config.resource_group_auto_detect);
        // Defaults for unset fields
        assert_eq!(config.default_vm_size, "Standard_E16as_v5");
        assert!(config.ssh_auto_sync_keys);
        assert_eq!(config.bastion_detection_timeout, 60);
    }

    #[test]
    fn test_validate_field_region_case_insensitive() {
        let result = AzlinConfig::validate_field("default_region", "WestUS2");
        assert!(result.is_ok());
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("westus2".to_string())
        );
    }

    #[test]
    fn test_validate_field_all_bool_fields() {
        for field in AzlinConfig::BOOL_FIELDS {
            let ok_true = AzlinConfig::validate_field(field, "true");
            assert!(ok_true.is_ok(), "field {field} should accept 'true'");
            assert_eq!(ok_true.unwrap(), serde_json::Value::Bool(true));

            let ok_false = AzlinConfig::validate_field(field, "false");
            assert!(ok_false.is_ok(), "field {field} should accept 'false'");
            assert_eq!(ok_false.unwrap(), serde_json::Value::Bool(false));

            let bad = AzlinConfig::validate_field(field, "maybe");
            assert!(bad.is_err(), "field {field} should reject 'maybe'");
        }
    }

    #[test]
    fn test_validate_field_all_u64_fields() {
        for field in AzlinConfig::U64_FIELDS {
            let ok = AzlinConfig::validate_field(field, "42");
            assert!(ok.is_ok(), "field {field} should accept '42'");
            assert_eq!(ok.unwrap(), serde_json::json!(42u64));

            let bad = AzlinConfig::validate_field(field, "not-a-number");
            assert!(bad.is_err(), "field {field} should reject 'not-a-number'");
        }
    }

    #[test]
    fn test_validate_field_unknown_key_passthrough() {
        let result = AzlinConfig::validate_field("some_unknown_key", "any-value");
        assert!(result.is_ok());
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("any-value".to_string())
        );
    }

    #[test]
    fn test_validate_field_vm_size_various() {
        // Valid sizes
        for size in &["Standard_D2s_v3", "Standard_E16as_v5", "Standard_B1s"] {
            assert!(AzlinConfig::validate_field("default_vm_size", size).is_ok());
        }
        // Invalid sizes
        for size in &["basic_a1", "D2s_v3", "", "standard_D2s"] {
            assert!(AzlinConfig::validate_field("default_vm_size", size).is_err());
        }
    }

    #[test]
    fn test_validate_field_region_all_known_valid() {
        for region in VALID_AZURE_REGIONS {
            assert!(
                AzlinConfig::validate_field("default_region", region).is_ok(),
                "region {region} should be valid"
            );
        }
    }

    #[test]
    fn test_config_json_roundtrip() {
        let config = AzlinConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        let loaded: AzlinConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(loaded.default_region, config.default_region);
        assert_eq!(loaded.default_vm_size, config.default_vm_size);
    }

    #[test]
    fn test_config_yaml_roundtrip() {
        let config = AzlinConfig {
            default_resource_group: Some("test-rg".to_string()),
            ..Default::default()
        };
        let yaml = serde_yaml::to_string(&config).unwrap();
        let loaded: AzlinConfig = serde_yaml::from_str(&yaml).unwrap();
        assert_eq!(loaded.default_resource_group, Some("test-rg".to_string()));
    }

    #[test]
    fn test_config_ignores_unknown_python_fields() {
        // Python azlin may write fields the Rust version doesn't know about.
        // Verify they are silently ignored (no deny_unknown_fields).
        let toml_with_extras = r#"
            default_region = "westus2"
            default_vm_size = "Standard_B1ms"
            python_only_field = "should be ignored"
            auto_shutdown_time = 1800
            nested_extra = { a = 1, b = "two" }
        "#;
        let config: AzlinConfig = toml::from_str(toml_with_extras).unwrap();
        assert_eq!(config.default_region, "westus2");
        assert_eq!(config.default_vm_size, "Standard_B1ms");
        // Defaults for fields not in the TOML
        assert_eq!(config.az_cli_timeout, 120);
        assert!(config.ssh_auto_sync_keys);
    }
}
