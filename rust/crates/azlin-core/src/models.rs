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
}
