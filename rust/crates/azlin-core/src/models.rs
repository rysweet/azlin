use std::collections::HashMap;
use std::path::PathBuf;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Represents an Azure VM with its current state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VmInfo {
    pub name: String,
    pub resource_group: String,
    pub location: String,
    pub vm_size: String,
    pub power_state: PowerState,
    pub provisioning_state: String,
    pub os_type: OsType,
    pub public_ip: Option<String>,
    pub private_ip: Option<String>,
    pub admin_username: Option<String>,
    pub tags: std::collections::HashMap<String, String>,
    pub created_time: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum PowerState {
    Running,
    Stopped,
    Deallocated,
    Starting,
    Stopping,
    Unknown,
}

impl std::fmt::Display for PowerState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PowerState::Running => write!(f, "running"),
            PowerState::Stopped => write!(f, "stopped"),
            PowerState::Deallocated => write!(f, "deallocated"),
            PowerState::Starting => write!(f, "starting"),
            PowerState::Stopping => write!(f, "stopping"),
            PowerState::Unknown => write!(f, "unknown"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum OsType {
    Linux,
    Windows,
}

/// Represents a tmux session on a remote VM.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TmuxSession {
    pub vm_name: String,
    pub session_name: String,
    pub windows: u32,
    pub created_time: String,
    #[serde(default)]
    pub attached: bool,
}

/// Summary of Azure costs for a resource group.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostSummary {
    pub total_cost: f64,
    pub currency: String,
    pub period_start: DateTime<Utc>,
    pub period_end: DateTime<Utc>,
    pub by_vm: Vec<VmCost>,
}

/// Cost data for an individual VM.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VmCost {
    pub vm_name: String,
    pub cost: f64,
    pub currency: String,
}

/// Parameters for creating a new Azure VM.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreateVmParams {
    pub name: String,
    pub resource_group: String,
    pub region: String,
    pub vm_size: String,
    pub admin_username: String,
    pub ssh_key_path: PathBuf,
    pub image: VmImage,
    pub tags: HashMap<String, String>,
}

impl CreateVmParams {
    /// Validate that all required fields are non-empty and the SSH key exists.
    pub fn validate(&self) -> std::result::Result<(), String> {
        if self.name.is_empty() {
            return Err("VM name cannot be empty".into());
        }
        if self.name.len() > 64 {
            return Err("VM name must be 64 characters or less".into());
        }
        if self.resource_group.is_empty() {
            return Err("Resource group cannot be empty".into());
        }
        if self.region.is_empty() {
            return Err("Region cannot be empty".into());
        }
        if self.vm_size.is_empty() {
            return Err("VM size cannot be empty".into());
        }
        if self.admin_username.is_empty() {
            return Err("Admin username cannot be empty".into());
        }
        if !self.ssh_key_path.exists() {
            return Err(format!(
                "SSH public key not found: {}",
                self.ssh_key_path.display()
            ));
        }
        Ok(())
    }
}

/// OS image specification for VM creation.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct VmImage {
    pub publisher: String,
    pub offer: String,
    pub sku: String,
    pub version: String,
}

impl Default for VmImage {
    fn default() -> Self {
        Self {
            publisher: "Canonical".into(),
            offer: "ubuntu-24_04-lts".into(),
            sku: "server".into(),
            version: "latest".into(),
        }
    }
}

impl std::fmt::Display for VmImage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}:{}:{}:{}",
            self.publisher, self.offer, self.sku, self.version
        )
    }
}

/// Represents a command execution result.
#[derive(Debug, Clone)]
pub struct CommandResult {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub duration_ms: u64,
}

impl CommandResult {
    pub fn success(&self) -> bool {
        self.exit_code == 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_power_state_display() {
        assert_eq!(PowerState::Running.to_string(), "running");
        assert_eq!(PowerState::Deallocated.to_string(), "deallocated");
    }

    #[test]
    fn test_command_result_success() {
        let result = CommandResult {
            exit_code: 0,
            stdout: "ok".to_string(),
            stderr: String::new(),
            duration_ms: 100,
        };
        assert!(result.success());

        let failed = CommandResult {
            exit_code: 1,
            stdout: String::new(),
            stderr: "error".to_string(),
            duration_ms: 50,
        };
        assert!(!failed.success());
    }

    #[test]
    fn test_vm_info_serialization() {
        let vm = VmInfo {
            name: "test-vm".to_string(),
            resource_group: "test-rg".to_string(),
            location: "westus2".to_string(),
            vm_size: "Standard_E16as_v5".to_string(),
            power_state: PowerState::Running,
            provisioning_state: "Succeeded".to_string(),
            os_type: OsType::Linux,
            public_ip: Some("1.2.3.4".to_string()),
            private_ip: Some("10.0.0.4".to_string()),
            admin_username: Some("azureuser".to_string()),
            tags: std::collections::HashMap::new(),
            created_time: None,
        };
        let json = serde_json::to_string(&vm).unwrap();
        let deserialized: VmInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.name, "test-vm");
        assert_eq!(deserialized.power_state, PowerState::Running);
    }

    #[test]
    fn test_tmux_session_defaults() {
        let json = r#"{"vm_name":"vm1","session_name":"dev","windows":3,"created_time":"2024-01-01"}"#;
        let session: TmuxSession = serde_json::from_str(json).unwrap();
        assert!(!session.attached);
    }

    #[test]
    fn test_cost_summary_serialization() {
        let summary = CostSummary {
            total_cost: 42.50,
            currency: "USD".to_string(),
            period_start: Utc::now(),
            period_end: Utc::now(),
            by_vm: vec![
                VmCost {
                    vm_name: "vm-1".to_string(),
                    cost: 25.00,
                    currency: "USD".to_string(),
                },
                VmCost {
                    vm_name: "vm-2".to_string(),
                    cost: 17.50,
                    currency: "USD".to_string(),
                },
            ],
        };
        let json = serde_json::to_string(&summary).unwrap();
        let deserialized: CostSummary = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.total_cost, 42.50);
        assert_eq!(deserialized.currency, "USD");
        assert_eq!(deserialized.by_vm.len(), 2);
    }

    #[test]
    fn test_vm_cost_fields() {
        let vm_cost = VmCost {
            vm_name: "dev-vm".to_string(),
            cost: 10.99,
            currency: "EUR".to_string(),
        };
        let json = serde_json::to_string(&vm_cost).unwrap();
        let deserialized: VmCost = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.vm_name, "dev-vm");
        assert_eq!(deserialized.cost, 10.99);
        assert_eq!(deserialized.currency, "EUR");
    }

    #[test]
    fn test_cost_summary_empty_vms() {
        let summary = CostSummary {
            total_cost: 0.0,
            currency: "USD".to_string(),
            period_start: Utc::now(),
            period_end: Utc::now(),
            by_vm: vec![],
        };
        let json = serde_json::to_string(&summary).unwrap();
        let deserialized: CostSummary = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.total_cost, 0.0);
        assert!(deserialized.by_vm.is_empty());
    }

    #[test]
    fn test_vm_image_default() {
        let img = VmImage::default();
        assert_eq!(img.publisher, "Canonical");
        assert_eq!(img.offer, "ubuntu-24_04-lts");
        assert_eq!(img.sku, "server");
        assert_eq!(img.version, "latest");
    }

    #[test]
    fn test_vm_image_display() {
        let img = VmImage::default();
        assert_eq!(img.to_string(), "Canonical:ubuntu-24_04-lts:server:latest");
    }

    #[test]
    fn test_create_vm_params_validate_empty_name() {
        let params = CreateVmParams {
            name: "".into(),
            resource_group: "test-rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
        };
        assert!(params.validate().is_err());
        assert!(params.validate().unwrap_err().contains("name"));
    }

    #[test]
    fn test_create_vm_params_validate_long_name() {
        let params = CreateVmParams {
            name: "a".repeat(65),
            resource_group: "test-rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
        };
        assert!(params.validate().is_err());
        assert!(params.validate().unwrap_err().contains("64 characters"));
    }

    #[test]
    fn test_create_vm_params_serialization() {
        let params = CreateVmParams {
            name: "test-vm".into(),
            resource_group: "test-rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/home/user/.ssh/id_rsa.pub"),
            image: VmImage::default(),
            tags: HashMap::from([("env".into(), "dev".into())]),
        };
        let json = serde_json::to_string(&params).unwrap();
        let deserialized: CreateVmParams = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.name, "test-vm");
        assert_eq!(deserialized.region, "westus2");
        assert_eq!(deserialized.image, VmImage::default());
        assert_eq!(deserialized.tags.get("env").unwrap(), "dev");
    }

    #[test]
    fn test_create_vm_params_validate_missing_ssh_key() {
        let params = CreateVmParams {
            name: "test-vm".into(),
            resource_group: "test-rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent_key_abc123.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
        };
        let err = params.validate().unwrap_err();
        assert!(err.contains("SSH public key not found"));
    }
}
