use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

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
    pub ssh_sync_method: String,
    pub ssh_auto_sync_age_threshold: u64,
    pub ssh_auto_sync_skip_new_vms: bool,
    pub resource_group_auto_detect: bool,
    pub resource_group_cache_ttl: u64,
    pub resource_group_query_timeout: u64,
    pub resource_group_fallback_to_default: bool,
    pub bastion_detection_timeout: u64,
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
            ssh_sync_method: "auto".to_string(),
            ssh_auto_sync_age_threshold: 600,
            ssh_auto_sync_skip_new_vms: true,
            resource_group_auto_detect: true,
            resource_group_cache_ttl: 900,
            resource_group_query_timeout: 30,
            resource_group_fallback_to_default: true,
            bastion_detection_timeout: 60,
        }
    }
}

impl AzlinConfig {
    /// Returns the config directory path (~/.azlin/)
    pub fn config_dir() -> PathBuf {
        dirs::home_dir()
            .expect("Home directory not found")
            .join(".azlin")
    }

    /// Returns the config file path (~/.azlin/config.toml)
    pub fn config_path() -> PathBuf {
        Self::config_dir().join("config.toml")
    }

    /// Load config from disk, returning defaults if file doesn't exist.
    pub fn load() -> crate::Result<Self> {
        let path = Self::config_path();
        if !path.exists() {
            return Ok(Self::default());
        }
        let contents = std::fs::read_to_string(&path).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to read config at {}: {}", path.display(), e))
        })?;
        toml::from_str(&contents).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to parse config: {e}"))
        })
    }

    /// Save config to disk, creating the directory if needed.
    pub fn save(&self) -> crate::Result<()> {
        let dir = Self::config_dir();
        std::fs::create_dir_all(&dir).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to create config dir: {e}"))
        })?;
        let path = Self::config_path();
        let contents = toml::to_string_pretty(self).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to serialize config: {e}"))
        })?;
        std::fs::write(&path, contents).map_err(|e| {
            crate::AzlinError::Config(format!("Failed to write config: {e}"))
        })?;

        // Set file permissions to 600 on Unix
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))
                .map_err(|e| crate::AzlinError::Config(format!("Failed to set permissions: {e}")))?;
        }

        Ok(())
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
        assert_eq!(deserialized.default_resource_group, Some("my-rg".to_string()));
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
}
