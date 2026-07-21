use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

/// Default Azure Public IP `--ip-tags` value applied to Bastion public IPs.
///
/// Historically this was hardcoded in `bastion_helpers::build_create_pip_args`.
/// It is retained as the default so existing behavior is byte-identical when
/// no override is configured.
pub const DEFAULT_BASTION_PIP_IP_TAGS: &str = "FirstPartyUsage=/ATEVETNonProd";

/// Environment variable that overrides the persisted `bastion_pip_ip_tags`
/// config field at runtime. Must be a valid `Key=Value` IP tag; invalid values
/// are ignored (with a warning) in favor of the persisted field / default.
pub const ENV_BASTION_PIP_IP_TAGS: &str = "AZLIN_BASTION_PIP_IP_TAGS";

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

/// How `azlin list -r` opens restored tmux sessions in Windows Terminal.
///
/// - `Auto`: detect WT_SESSION env var; fall back to Linux terminal emulators.
/// - `Tab`: force `wt.exe -w 0 new-tab` (reuse existing window).
/// - `Window`: force `wt.exe new-tab` (open a new window per session).
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum RestoreMode {
    #[default]
    Auto,
    Tab,
    Window,
}

impl std::fmt::Display for RestoreMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Auto => write!(f, "auto"),
            Self::Tab => write!(f, "tab"),
            Self::Window => write!(f, "window"),
        }
    }
}

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
    /// Default VM OS image URN (e.g. "Canonical:ubuntu-26_04-lts:server:latest").
    /// When None, falls back to VmImage::default().
    pub default_vm_image: Option<String>,
    pub ssh_auto_sync_keys: bool,
    pub ssh_sync_timeout: u64,
    pub ssh_sync_method: SshSyncMethod,
    pub ssh_auto_sync_age_threshold: u64,
    pub ssh_auto_sync_skip_new_vms: bool,
    pub resource_group_auto_detect: bool,
    pub resource_group_cache_ttl: u64,
    pub resource_group_query_timeout: u64,
    pub bastion_detection_timeout: u64,
    /// Timeout in seconds for native bastion tunnel setup (token exchange + WSS connect).
    /// Default: 30 seconds. Also used as the wait-for-listener timeout.
    pub bastion_tunnel_timeout: u64,
    /// Timeout in seconds for the TCP connect phase of the native bastion tunnel.
    /// Default: 30 seconds. Separated from `bastion_tunnel_timeout` so operators
    /// can fail fast on unreachable bastions (issue #1045) without shortening the
    /// overall setup budget. Backward-compatible: absent configs use the default.
    pub bastion_connect_timeout: u64,
    /// Timeout in seconds for SSH/SCP connect operations.
    /// Default: 30 seconds.
    pub ssh_connect_timeout: u64,
    /// Timeout in seconds for SCP file transfer operations.
    /// Default: 120 seconds. Covers the full transfer, not just the connection.
    pub scp_transfer_timeout: u64,
    /// Timeout in seconds for `az` CLI subprocess calls.
    /// Default: 120 seconds. Increase on Windows/WSL where Azure CLI is slower.
    pub az_cli_timeout: u64,
    /// How `azlin list -r` opens restored sessions: "auto", "tab", or "window".
    pub restore_mode: RestoreMode,
    /// Azure Public IP `--ip-tags` value applied to Bastion public IPs.
    ///
    /// Defaults to [`DEFAULT_BASTION_PIP_IP_TAGS`]. May be overridden at runtime
    /// via the [`ENV_BASTION_PIP_IP_TAGS`] environment variable. Resolve the
    /// effective value with [`AzlinConfig::bastion_pip_ip_tags`].
    pub bastion_pip_ip_tags: String,
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
            default_vm_image: None,
            ssh_auto_sync_keys: true,
            ssh_sync_timeout: 30,
            ssh_sync_method: SshSyncMethod::Auto,
            ssh_auto_sync_age_threshold: 600,
            ssh_auto_sync_skip_new_vms: true,
            resource_group_auto_detect: true,
            resource_group_cache_ttl: 900,
            resource_group_query_timeout: 30,
            bastion_detection_timeout: 60,
            bastion_tunnel_timeout: 30,
            bastion_connect_timeout: 30,
            ssh_connect_timeout: 30,
            scp_transfer_timeout: 120,
            az_cli_timeout: 120,
            restore_mode: RestoreMode::Auto,
            bastion_pip_ip_tags: DEFAULT_BASTION_PIP_IP_TAGS.to_string(),
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
        Self::load_from_path(&path)
    }

    /// Load configuration from a specific file path.
    /// Returns defaults if the file does not exist.
    pub fn load_from(path: &std::path::Path) -> crate::Result<Self> {
        Self::load_from_path(path)
    }

    fn load_from_path(path: &std::path::Path) -> crate::Result<Self> {
        if !path.exists() {
            return Ok(Self::default());
        }
        let contents = std::fs::read_to_string(path).map_err(|e| {
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

    /// Load config, update a single field by key, validate, and save atomically.
    ///
    /// This is the canonical way to update a config field. It ensures the full
    /// load -> validate -> serialize -> write cycle so the config file always
    /// contains valid TOML with all fields.
    ///
    /// # Errors
    ///
    /// Returns an error if the key is unknown, the value fails validation,
    /// or the save operation fails.
    ///
    /// # Examples
    ///
    /// ```no_run
    /// use azlin_core::AzlinConfig;
    ///
    /// AzlinConfig::set_field("az_cli_timeout", "600").unwrap();
    /// let config = AzlinConfig::load().unwrap();
    /// assert_eq!(config.az_cli_timeout, 600);
    /// ```
    pub fn set_field(key: &str, value: &str) -> crate::Result<()> {
        let config = Self::load()?;
        let mut json = serde_json::to_value(&config).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to serialize config to JSON: {e}"))
        })?;

        // Reject unknown keys
        if let Some(obj) = json.as_object() {
            if !obj.contains_key(key) {
                return Err(crate::AzlinError::Config(format!(
                    "Unknown config key: {key}"
                )));
            }
        }

        let validated = Self::validate_field(key, value)?;

        if let Some(obj) = json.as_object_mut() {
            obj.insert(key.to_string(), validated);
        }

        let updated: AzlinConfig = serde_json::from_value(json).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to deserialize updated config: {e}"))
        })?;

        updated.save()?;
        Ok(())
    }

    /// Resolve the effective Bastion public-IP `--ip-tags` value.
    ///
    /// Precedence:
    /// 1. `AZLIN_BASTION_PIP_IP_TAGS` env var, if set to a valid, non-empty tag.
    /// 2. The persisted `bastion_pip_ip_tags` field, if non-empty.
    /// 3. [`DEFAULT_BASTION_PIP_IP_TAGS`].
    ///
    /// An env value that is empty or fails validation is ignored (a warning is
    /// logged) and resolution falls through to the field, then the default.
    /// The returned value is always non-empty and valid.
    pub fn bastion_pip_ip_tags(&self) -> String {
        if let Ok(env_val) = std::env::var(ENV_BASTION_PIP_IP_TAGS) {
            let trimmed = env_val.trim();
            if !trimmed.is_empty() {
                match Self::validate_bastion_pip_ip_tags(trimmed) {
                    Ok(()) => return trimmed.to_string(),
                    Err(e) => {
                        tracing::warn!(
                            env = ENV_BASTION_PIP_IP_TAGS,
                            error = %e,
                            "Ignoring invalid AZLIN_BASTION_PIP_IP_TAGS; \
                             falling back to configured value"
                        );
                    }
                }
            }
        }

        let field = self.bastion_pip_ip_tags.trim();
        if field.is_empty() {
            DEFAULT_BASTION_PIP_IP_TAGS.to_string()
        } else {
            field.to_string()
        }
    }

    /// Validate a Bastion public-IP `--ip-tags` value.
    ///
    /// Enforces an Azure `IpTagType=Tag` shape and guards against argument
    /// injection when the value is later passed to the `az` CLI:
    /// - Must contain `=` with a non-empty key.
    /// - Key must not start with `-` (flag-injection guard).
    /// - No control characters (including newlines).
    /// - Length must be <= 512.
    pub fn validate_bastion_pip_ip_tags(value: &str) -> crate::Result<()> {
        if value.is_empty() {
            return Err(crate::AzlinError::Config(
                "bastion_pip_ip_tags must not be empty (expected 'Key=Value', \
                 e.g. 'FirstPartyUsage=/ATEVETNonProd')"
                    .into(),
            ));
        }
        if value.len() > 512 {
            return Err(crate::AzlinError::Config(format!(
                "bastion_pip_ip_tags is too long ({} chars, max 512)",
                value.len()
            )));
        }
        if value.chars().any(|c| c.is_control()) {
            return Err(crate::AzlinError::Config(
                "bastion_pip_ip_tags must not contain control characters".into(),
            ));
        }
        let Some((key, _tag)) = value.split_once('=') else {
            return Err(crate::AzlinError::Config(format!(
                "bastion_pip_ip_tags must be 'Key=Value' (e.g. \
                 'FirstPartyUsage=/ATEVETNonProd'), got '{}'",
                value
            )));
        };
        if key.is_empty() {
            return Err(crate::AzlinError::Config(
                "bastion_pip_ip_tags key (before '=') must not be empty".into(),
            ));
        }
        if key.starts_with('-') {
            return Err(crate::AzlinError::Config(format!(
                "bastion_pip_ip_tags key must not start with '-' (got '{}')",
                key
            )));
        }
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
        "scp_transfer_timeout",
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

        if key == "default_vm_image" {
            let image = crate::models::VmImage::from_image_spec(value).map_err(|e| {
                crate::AzlinError::Config(format!("Invalid default_vm_image: {}", e))
            })?;
            // Store the resolved full URN
            return Ok(serde_json::Value::String(image.to_string()));
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

        if key == "restore_mode" {
            match value.to_lowercase().as_str() {
                "auto" | "tab" | "window" => {
                    return Ok(serde_json::Value::String(value.to_lowercase()));
                }
                _ => {
                    return Err(crate::AzlinError::Config(format!(
                        "restore_mode must be 'auto', 'tab', or 'window', got '{}'",
                        value
                    )));
                }
            }
        }

        if key == "bastion_pip_ip_tags" {
            Self::validate_bastion_pip_ip_tags(value)?;
            return Ok(serde_json::Value::String(value.to_string()));
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
            "default_vm_image",
            "last_vm_name",
            "notification_command",
            "default_nfs_storage",
            "ssh_sync_method",
            "restore_mode",
            "bastion_pip_ip_tags",
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
    use std::sync::Mutex;

    /// Serializes tests that mutate the process-global `AZLIN_BASTION_PIP_IP_TAGS`
    /// env var, preventing races under the parallel test runner.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

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

    // ── set_field logic tests ──────────────────────────────────────
    // These test the core set_field logic without relying on AZLIN_CONFIG_DIR
    // env var (which causes race conditions in parallel tests).
    // Instead they simulate the same load -> validate -> update -> serialize
    // roundtrip that set_field performs.

    /// Simulate what set_field does: load config, update via JSON, serialize back.
    /// Returns the TOML string and the parsed config.
    fn simulate_set_field(initial: &AzlinConfig, key: &str, value: &str) -> (String, AzlinConfig) {
        let mut json = serde_json::to_value(initial).unwrap();
        assert!(json.as_object().unwrap().contains_key(key), "unknown key");
        let validated = AzlinConfig::validate_field(key, value).unwrap();
        json.as_object_mut()
            .unwrap()
            .insert(key.to_string(), validated);
        let updated: AzlinConfig = serde_json::from_value(json).unwrap();
        let toml_str = toml::to_string_pretty(&updated).unwrap();
        // Verify roundtrip
        let reparsed: AzlinConfig = toml::from_str(&toml_str).unwrap();
        (toml_str, reparsed)
    }

    #[test]
    fn test_set_field_u64_produces_valid_toml() {
        let config = AzlinConfig::default();
        let (toml_str, parsed) = simulate_set_field(&config, "az_cli_timeout", "600");

        assert_eq!(parsed.az_cli_timeout, 600);

        // The raw TOML must NOT contain a bare "600" line (issue #800)
        for line in toml_str.lines() {
            assert_ne!(
                line.trim(),
                "600",
                "TOML must not contain raw '600' line — issue #800"
            );
        }

        // Other fields preserved
        assert_eq!(parsed.default_region, "westus2");
        assert_eq!(parsed.default_vm_size, "Standard_E16as_v5");
    }

    #[test]
    fn test_set_field_string_produces_valid_toml() {
        let config = AzlinConfig::default();
        let (_, parsed) = simulate_set_field(&config, "default_region", "northeurope");
        assert_eq!(parsed.default_region, "northeurope");
        assert_eq!(parsed.az_cli_timeout, 120); // untouched
    }

    #[test]
    fn test_set_field_bool_produces_valid_toml() {
        let config = AzlinConfig::default();
        let (_, parsed) = simulate_set_field(&config, "ssh_auto_sync_keys", "false");
        assert!(!parsed.ssh_auto_sync_keys);
    }

    #[test]
    fn test_set_field_unknown_key_rejected_by_set_field() {
        let config = AzlinConfig::default();
        let json = serde_json::to_value(&config).unwrap();
        assert!(
            !json.as_object().unwrap().contains_key("nonexistent_key"),
            "unknown key should not be in config"
        );
    }

    #[test]
    fn test_set_field_consecutive_sets_produce_valid_toml() {
        let config = AzlinConfig::default();
        let (toml1, c1) = simulate_set_field(&config, "az_cli_timeout", "300");
        // Parse c1 and apply next set
        let c1_reparsed: AzlinConfig = toml::from_str(&toml1).unwrap();
        let (toml2, c2) = simulate_set_field(&c1_reparsed, "default_region", "eastus");
        let c2_reparsed: AzlinConfig = toml::from_str(&toml2).unwrap();
        let (_, c3) = simulate_set_field(&c2_reparsed, "ssh_auto_sync_keys", "false");

        assert_eq!(c3.az_cli_timeout, 300);
        assert_eq!(c3.default_region, "eastus");
        assert!(!c3.ssh_auto_sync_keys);
        // Untouched fields at default
        assert_eq!(c3.default_vm_size, "Standard_E16as_v5");
        assert_eq!(c3.ssh_sync_timeout, 30);
    }

    #[test]
    fn test_set_field_on_default_config_produces_valid_toml() {
        // Simulates set_field on a fresh (default) config
        let config = AzlinConfig::default();
        let (toml_str, parsed) = simulate_set_field(&config, "az_cli_timeout", "600");

        // Must be parseable
        let _: AzlinConfig = toml::from_str(&toml_str).unwrap();
        assert_eq!(parsed.az_cli_timeout, 600);
        assert_eq!(parsed.default_region, "westus2"); // defaults preserved
    }

    #[test]
    fn test_set_field_toml_contains_key_equals_value() {
        let config = AzlinConfig::default();
        let (toml_str, _) = simulate_set_field(&config, "az_cli_timeout", "600");

        // The TOML must contain `az_cli_timeout = 600` (proper key=value format)
        assert!(
            toml_str.contains("az_cli_timeout = 600"),
            "TOML should contain 'az_cli_timeout = 600', got:\n{toml_str}"
        );
    }

    #[test]
    fn test_config_default_vm_image_is_none() {
        let config = AzlinConfig::default();
        assert!(
            config.default_vm_image.is_none(),
            "default_vm_image should be None by default"
        );
    }

    #[test]
    fn test_config_deserialize_without_default_vm_image() {
        // Existing configs without the field should deserialize fine
        let toml_str = r#"
            default_region = "westus2"
            default_vm_size = "Standard_E16as_v5"
        "#;
        let config: AzlinConfig = toml::from_str(toml_str).unwrap();
        assert!(config.default_vm_image.is_none());
    }

    #[test]
    fn test_config_deserialize_with_default_vm_image() {
        let toml_str = r#"
            default_region = "westus2"
            default_vm_size = "Standard_E16as_v5"
            default_vm_image = "Canonical:ubuntu-24_04-lts:server:latest"
        "#;
        let config: AzlinConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(
            config.default_vm_image,
            Some("Canonical:ubuntu-24_04-lts:server:latest".to_string())
        );
    }

    #[test]
    fn test_config_roundtrip_with_default_vm_image() {
        let config = AzlinConfig {
            default_vm_image: Some("Canonical:ubuntu-24_04-lts:server:latest".to_string()),
            ..Default::default()
        };
        let serialized = toml::to_string_pretty(&config).unwrap();
        let deserialized: AzlinConfig = toml::from_str(&serialized).unwrap();
        assert_eq!(
            deserialized.default_vm_image,
            Some("Canonical:ubuntu-24_04-lts:server:latest".to_string())
        );
    }

    #[test]
    fn test_validate_field_default_vm_image_full_urn() {
        let result =
            AzlinConfig::validate_field("default_vm_image", "Canonical:ubuntu-25_10:server:latest");
        assert!(result.is_ok(), "should accept valid URN");
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("Canonical:ubuntu-25_10:server:latest".to_string())
        );
    }

    #[test]
    fn test_validate_field_default_vm_image_shorthand() {
        let result = AzlinConfig::validate_field("default_vm_image", "24.04-lts");
        assert!(result.is_ok(), "should accept valid shorthand");
        // Should store the resolved full URN
        assert_eq!(
            result.unwrap(),
            serde_json::Value::String("Canonical:ubuntu-24_04-lts:server:latest".to_string())
        );
    }

    #[test]
    fn test_validate_field_default_vm_image_invalid() {
        let result = AzlinConfig::validate_field("default_vm_image", "not-a-valid-image");
        assert!(result.is_err(), "should reject invalid image spec");
    }

    #[test]
    fn test_validate_field_default_vm_image_non_canonical() {
        let result = AzlinConfig::validate_field(
            "default_vm_image",
            "MicrosoftWindowsServer:WindowsServer:2022:latest",
        );
        assert!(result.is_err(), "should reject non-Canonical publisher");
    }

    #[test]
    fn test_default_vm_image_in_known_string_fields() {
        // Verify that setting default_vm_image doesn't trigger the unknown-key warning.
        // We test this indirectly: validate_field for a known string field should NOT
        // pass through as a generic string — it should hit the dedicated handler.
        // If default_vm_image is NOT in KNOWN_STRING_FIELDS, it would pass through
        // without validation (just a warning), which is incorrect.
        let result = AzlinConfig::validate_field(
            "default_vm_image",
            "MicrosoftWindowsServer:WindowsServer:2022:latest",
        );
        // This MUST be an error (rejected by from_image_spec).
        // If it passes through as a string, KNOWN_STRING_FIELDS is missing the entry.
        assert!(
            result.is_err(),
            "default_vm_image must be validated, not passed through — add to KNOWN_STRING_FIELDS"
        );
    }

    #[test]
    fn test_set_field_default_vm_image() {
        let config = AzlinConfig::default();
        let (toml_str, _) = simulate_set_field(
            &config,
            "default_vm_image",
            "Canonical:ubuntu-25_10:server:latest",
        );
        assert!(
            toml_str.contains("default_vm_image"),
            "TOML should contain default_vm_image key after set_field"
        );
    }

    // ── bastion_pip_ip_tags (configurable IP tag) tests ──────────────

    #[test]
    fn test_default_bastion_pip_ip_tags_constant() {
        // The default must remain byte-identical to the historically hardcoded
        // value for backward compatibility.
        assert_eq!(
            DEFAULT_BASTION_PIP_IP_TAGS,
            "FirstPartyUsage=/ATEVETNonProd"
        );
    }

    #[test]
    fn test_default_config_bastion_pip_ip_tags_field() {
        let config = AzlinConfig::default();
        assert_eq!(config.bastion_pip_ip_tags, DEFAULT_BASTION_PIP_IP_TAGS);
    }

    #[test]
    fn test_accessor_returns_field_value() {
        // With no env override, the accessor returns the persisted field value.
        let _guard = ENV_LOCK.lock().unwrap();
        std::env::remove_var("AZLIN_BASTION_PIP_IP_TAGS");
        let mut config = AzlinConfig::default();
        config.bastion_pip_ip_tags = "FirstPartyUsage=/CustomTag".to_string();
        assert_eq!(config.bastion_pip_ip_tags(), "FirstPartyUsage=/CustomTag");
    }

    #[test]
    fn test_accessor_empty_field_falls_back_to_default() {
        // An empty/whitespace persisted value normalizes to the default constant.
        let _guard = ENV_LOCK.lock().unwrap();
        std::env::remove_var("AZLIN_BASTION_PIP_IP_TAGS");
        let mut config = AzlinConfig::default();
        config.bastion_pip_ip_tags = "   ".to_string();
        assert_eq!(config.bastion_pip_ip_tags(), DEFAULT_BASTION_PIP_IP_TAGS);
    }

    #[test]
    fn test_accessor_env_override_takes_precedence() {
        let _guard = ENV_LOCK.lock().unwrap();
        let mut config = AzlinConfig::default();
        config.bastion_pip_ip_tags = "FirstPartyUsage=/FieldValue".to_string();
        std::env::set_var("AZLIN_BASTION_PIP_IP_TAGS", "FirstPartyUsage=/FromEnv");
        let resolved = config.bastion_pip_ip_tags();
        std::env::remove_var("AZLIN_BASTION_PIP_IP_TAGS");
        assert_eq!(resolved, "FirstPartyUsage=/FromEnv");
    }

    #[test]
    fn test_accessor_invalid_env_falls_back_to_field() {
        // An invalid env value (fails the validator) is ignored; the accessor
        // falls back to the field value rather than propagating garbage.
        let _guard = ENV_LOCK.lock().unwrap();
        let mut config = AzlinConfig::default();
        config.bastion_pip_ip_tags = "FirstPartyUsage=/FieldValue".to_string();
        std::env::set_var("AZLIN_BASTION_PIP_IP_TAGS", "-badkey=value");
        let resolved = config.bastion_pip_ip_tags();
        std::env::remove_var("AZLIN_BASTION_PIP_IP_TAGS");
        assert_eq!(resolved, "FirstPartyUsage=/FieldValue");
    }

    #[test]
    fn test_accessor_empty_env_falls_back_to_field() {
        let _guard = ENV_LOCK.lock().unwrap();
        let mut config = AzlinConfig::default();
        config.bastion_pip_ip_tags = "FirstPartyUsage=/FieldValue".to_string();
        std::env::set_var("AZLIN_BASTION_PIP_IP_TAGS", "");
        let resolved = config.bastion_pip_ip_tags();
        std::env::remove_var("AZLIN_BASTION_PIP_IP_TAGS");
        assert_eq!(resolved, "FirstPartyUsage=/FieldValue");
    }

    #[test]
    fn test_validate_bastion_pip_ip_tags_accepts_valid() {
        assert!(
            AzlinConfig::validate_bastion_pip_ip_tags("FirstPartyUsage=/ATEVETNonProd").is_ok()
        );
        assert!(AzlinConfig::validate_bastion_pip_ip_tags("FirstPartyUsage=/CustomTag").is_ok());
    }

    #[test]
    fn test_validate_bastion_pip_ip_tags_rejects_invalid() {
        // Missing '=' (no Key=Value form).
        assert!(AzlinConfig::validate_bastion_pip_ip_tags("NoEqualsSign").is_err());
        // Empty key.
        assert!(AzlinConfig::validate_bastion_pip_ip_tags("=value").is_err());
        // Empty string.
        assert!(AzlinConfig::validate_bastion_pip_ip_tags("").is_err());
        // Leading '-' on key (flag-injection guard).
        assert!(AzlinConfig::validate_bastion_pip_ip_tags("-Key=value").is_err());
        // Control characters.
        assert!(AzlinConfig::validate_bastion_pip_ip_tags("Key=va\nlue").is_err());
        // Over-length (>512).
        let long = format!("Key=/{}", "a".repeat(600));
        assert!(AzlinConfig::validate_bastion_pip_ip_tags(&long).is_err());
    }

    #[test]
    fn test_validate_field_routes_bastion_pip_ip_tags() {
        // The field must hit the dedicated validator, not the generic string
        // pass-through: an invalid value must be rejected.
        let ok = AzlinConfig::validate_field("bastion_pip_ip_tags", "FirstPartyUsage=/CustomTag");
        assert_eq!(ok.unwrap(), serde_json::json!("FirstPartyUsage=/CustomTag"));

        let bad = AzlinConfig::validate_field("bastion_pip_ip_tags", "NoEqualsSign");
        assert!(
            bad.is_err(),
            "bastion_pip_ip_tags must be validated, not passed through as a generic string"
        );
    }

    #[test]
    fn test_set_field_bastion_pip_ip_tags_roundtrip() {
        let config = AzlinConfig::default();
        let (toml_str, parsed) =
            simulate_set_field(&config, "bastion_pip_ip_tags", "FirstPartyUsage=/CustomTag");
        assert!(
            toml_str.contains("bastion_pip_ip_tags"),
            "TOML should contain bastion_pip_ip_tags after set_field"
        );
        assert_eq!(parsed.bastion_pip_ip_tags, "FirstPartyUsage=/CustomTag");
    }

    #[test]
    fn test_old_config_without_bastion_pip_ip_tags_deserializes_to_default() {
        // Config files predating this field must deserialize with the default.
        let toml_str = "default_region = \"westus2\"\ndefault_vm_size = \"Standard_E16as_v5\"\n";
        let config: AzlinConfig = toml::from_str(toml_str).unwrap();
        assert_eq!(config.bastion_pip_ip_tags, DEFAULT_BASTION_PIP_IP_TAGS);
    }
}
