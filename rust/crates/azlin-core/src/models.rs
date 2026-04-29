use std::collections::HashMap;
use std::path::PathBuf;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// Represents an Azure VM with its current state.
///
/// # Examples
///
/// ```
/// use azlin_core::models::{VmInfo, PowerState, OsType, ProvisioningState};
/// use std::collections::HashMap;
///
/// let vm = VmInfo {
///     name: "dev-vm".to_string(),
///     resource_group: "my-rg".to_string(),
///     location: "westus2".to_string(),
///     vm_size: "Standard_D2s_v3".to_string(),
///     power_state: PowerState::Running,
///     provisioning_state: ProvisioningState::Succeeded,
///     os_type: OsType::Linux,
///     os_offer: None,
///     public_ip: Some("1.2.3.4".to_string()),
///     private_ip: Some("10.0.0.4".to_string()),
///     admin_username: Some("azureuser".to_string()),
///     tags: HashMap::new(),
///     created_time: None,
/// };
///
/// // Check if VM is running via power_state
/// assert_eq!(vm.power_state, PowerState::Running);
/// assert_eq!(vm.power_state.to_string(), "Running");
/// ```
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VmInfo {
    pub name: String,
    pub resource_group: String,
    pub location: String,
    pub vm_size: String,
    pub power_state: PowerState,
    pub provisioning_state: ProvisioningState,
    pub os_type: OsType,
    /// Image offer string from Azure (e.g., "ubuntu-25_10", "WindowsServer").
    /// Used for OS distro display in list output.
    pub os_offer: Option<String>,
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
            PowerState::Running => write!(f, "Running"),
            PowerState::Stopped => write!(f, "Stopped"),
            PowerState::Deallocated => write!(f, "Deallocated"),
            PowerState::Starting => write!(f, "Starting"),
            PowerState::Stopping => write!(f, "Stopping"),
            PowerState::Unknown => write!(f, "Unknown"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum OsType {
    Linux,
    Windows,
}

/// Azure VM provisioning state — the lifecycle of the ARM deployment.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub enum ProvisioningState {
    #[default]
    Succeeded,
    Failed,
    Creating,
    Deleting,
    Updating,
    Migrating,
    /// Any state not in the known set — preserves the raw string.
    #[serde(untagged)]
    Other(String),
}

impl std::fmt::Display for ProvisioningState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Succeeded => write!(f, "Succeeded"),
            Self::Failed => write!(f, "Failed"),
            Self::Creating => write!(f, "Creating"),
            Self::Deleting => write!(f, "Deleting"),
            Self::Updating => write!(f, "Updating"),
            Self::Migrating => write!(f, "Migrating"),
            Self::Other(s) => write!(f, "{s}"),
        }
    }
}

impl From<&str> for ProvisioningState {
    fn from(s: &str) -> Self {
        match s {
            "Succeeded" => Self::Succeeded,
            "Failed" => Self::Failed,
            "Creating" => Self::Creating,
            "Deleting" => Self::Deleting,
            "Updating" => Self::Updating,
            "Migrating" => Self::Migrating,
            other => Self::Other(other.to_string()),
        }
    }
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
    /// Whether to create a public IP. Set to false for bastion-only VMs.
    #[serde(default = "default_true")]
    pub public_ip_enabled: bool,
    /// Optional list of managed-disk resource IDs to attach during creation.
    /// Order matters: first disk = lun0, second = lun1, etc.
    #[serde(default)]
    pub disk_ids: Vec<String>,
    /// Whether a home disk is attached (LUN 0).
    #[serde(default)]
    pub has_home_disk: bool,
    /// Whether a tmp disk is attached (LUN 1 if home disk present, LUN 0 otherwise).
    #[serde(default)]
    pub has_tmp_disk: bool,
}

fn default_true() -> bool {
    true
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
            offer: "ubuntu-25_10".into(),
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

impl VmImage {
    /// Parse an image specification into a `VmImage`.
    ///
    /// Accepts:
    /// - Full URN: `Canonical:ubuntu-25_10:server:latest` (must be Canonical publisher)
    /// - Shorthands: `25.10`, `24.04-lts`, `ubuntu-25.10`, `ubuntu-24.04-lts`
    ///
    /// Returns an error for empty/whitespace input, shell metacharacters, non-Canonical
    /// publishers, malformed URNs, or unrecognized shorthands.
    pub fn from_image_spec(spec: &str) -> Result<Self, String> {
        let spec = spec.trim();
        if spec.is_empty() {
            return Err("Image spec cannot be empty".to_string());
        }

        // Reject dangerous characters (defense-in-depth).
        // All forbidden chars are ASCII, so byte comparison avoids UTF-8 decoding.
        const FORBIDDEN: &[u8] = b"\0\t\n\r;|&$`(){}<>!\\\"' #~?*[]%";
        if spec.as_bytes().iter().any(|b| FORBIDDEN.contains(b)) {
            return Err(format!(
                "Image spec contains invalid characters: {:?}. Use a URN like \
                 'Canonical:ubuntu-25_10:server:latest' or shorthand like '25.10'",
                spec
            ));
        }

        // If it contains colons, treat as a full URN
        if spec.contains(':') {
            return Self::parse_urn(spec);
        }

        // Try shorthand resolution
        Self::resolve_shorthand(spec)
    }

    /// Parse a 4-part colon-delimited URN, restricted to Canonical publisher.
    fn parse_urn(urn: &str) -> Result<Self, String> {
        // Use splitn(5) to detect >4 parts without allocating a Vec.
        let mut it = urn.splitn(5, ':');
        let parts: [&str; 4] = match (it.next(), it.next(), it.next(), it.next()) {
            (Some(a), Some(b), Some(c), Some(d)) if it.next().is_none() => [a, b, c, d],
            _ => {
                let count = urn.split(':').count();
                return Err(format!(
                    "Image URN must have exactly 4 colon-separated parts \
                     (publisher:offer:sku:version), got {} parts in {:?}",
                    count, urn
                ));
            }
        };

        // Validate each segment: only ASCII [a-zA-Z0-9._-]
        for (i, part) in parts.iter().enumerate() {
            if part.is_empty() {
                return Err(format!("Image URN segment {} is empty in {:?}", i, urn));
            }
            if !part
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'_' || b == b'-')
            {
                return Err(format!(
                    "Image URN segment {:?} contains invalid characters \
                     (only alphanumeric, '.', '_', '-' allowed)",
                    part
                ));
            }
        }

        // Restrict to Canonical publisher
        if parts[0] != "Canonical" {
            return Err(format!(
                "Only Canonical publisher is supported for VM images, got {:?}. \
                 Use a URN like 'Canonical:ubuntu-25_10:server:latest'",
                parts[0]
            ));
        }

        Ok(Self {
            publisher: parts[0].to_string(),
            offer: parts[1].to_string(),
            sku: parts[2].to_string(),
            version: parts[3].to_string(),
        })
    }

    /// Resolve a shorthand like "25.10" or "ubuntu-24.04-lts" to a full VmImage.
    fn resolve_shorthand(spec: &str) -> Result<Self, String> {
        // Normalize to lowercase for case-insensitive prefix matching
        let lower = spec.to_ascii_lowercase();
        let version_part = lower
            .strip_prefix("ubuntu-")
            .or_else(|| lower.strip_prefix("ubuntu"))
            .unwrap_or(&lower);

        // Map version shorthands to offer names.
        // Accepts dotted (25.10) and dotless (2510) forms; bare versions
        // (24.04, 2204) resolve to LTS when available.
        let offer = match version_part {
            "26.04-lts" | "26.04" | "2604" => "ubuntu-26_04-lts",
            "25.10" | "2510" => "ubuntu-25_10",
            "24.10" | "2410" => "ubuntu-24_10",
            "24.04-lts" | "24.04" | "2404" => "ubuntu-24_04-lts",
            "22.04-lts" | "22.04" | "2204" => "ubuntu-22_04-lts",
            "20.04-lts" | "20.04" | "2004" => "ubuntu-20_04-lts",
            _ => {
                return Err(format!(
                    "Unknown image shorthand {:?}. Supported shorthands: \
                     26.04-lts, 26.04, 25.10, 24.10, 24.04-lts, 24.04, 22.04-lts, 22.04, 20.04-lts, 20.04. \
                     Or use a full URN like 'Canonical:ubuntu-25_10:server:latest'",
                    spec
                ));
            }
        };

        Ok(Self {
            publisher: "Canonical".to_string(),
            offer: offer.to_string(),
            sku: "server".to_string(),
            version: "latest".to_string(),
        })
    }
}

/// Validate Azure VM name according to Azure rules.
///
/// # Examples
///
/// ```
/// use azlin_core::models::validate_vm_name;
///
/// // Valid names
/// assert!(validate_vm_name("my-vm-01").is_ok());
/// assert!(validate_vm_name("dev.server").is_ok());
/// assert!(validate_vm_name("a").is_ok());
///
/// // Empty name is rejected
/// assert!(validate_vm_name("").is_err());
///
/// // Names exceeding 64 characters are rejected
/// assert!(validate_vm_name(&"a".repeat(65)).is_err());
/// assert!(validate_vm_name(&"a".repeat(64)).is_ok());
///
/// // Cannot start or end with hyphen or period
/// assert!(validate_vm_name("-bad").is_err());
/// assert!(validate_vm_name("bad-").is_err());
///
/// // Only alphanumeric, hyphens, and periods allowed
/// assert!(validate_vm_name("bad@name").is_err());
/// ```
pub fn validate_vm_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("VM name cannot be empty".to_string());
    }
    let bytes = name.as_bytes();
    if bytes.len() > 64 {
        return Err(format!(
            "VM name '{}' exceeds 64 character limit ({})",
            name,
            bytes.len()
        ));
    }
    if matches!(bytes[0], b'-' | b'.') {
        return Err(format!(
            "VM name '{}' cannot start with hyphen or period",
            name
        ));
    }
    if matches!(bytes[bytes.len() - 1], b'-' | b'.') {
        return Err(format!(
            "VM name '{}' cannot end with hyphen or period",
            name
        ));
    }
    if !bytes
        .iter()
        .all(|b| b.is_ascii_alphanumeric() || *b == b'-' || *b == b'.')
    {
        return Err(format!(
            "VM name '{}' can only contain alphanumeric characters, hyphens, and periods",
            name
        ));
    }
    Ok(())
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
        assert_eq!(PowerState::Running.to_string(), "Running");
        assert_eq!(PowerState::Deallocated.to_string(), "Deallocated");
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
            provisioning_state: ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
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
        let json =
            r#"{"vm_name":"vm1","session_name":"dev","windows":3,"created_time":"2024-01-01"}"#;
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
        assert_eq!(img.offer, "ubuntu-25_10");
        assert_eq!(img.sku, "server");
        assert_eq!(img.version, "latest");
    }

    #[test]
    fn test_vm_image_display() {
        let img = VmImage::default();
        assert_eq!(img.to_string(), "Canonical:ubuntu-25_10:server:latest");
    }

    // ── from_image_spec tests (TDD — will fail until implementation) ──

    #[test]
    fn test_from_image_spec_full_urn() {
        let img = VmImage::from_image_spec("Canonical:ubuntu-25_10:server:latest").unwrap();
        assert_eq!(img.publisher, "Canonical");
        assert_eq!(img.offer, "ubuntu-25_10");
        assert_eq!(img.sku, "server");
        assert_eq!(img.version, "latest");
    }

    #[test]
    fn test_from_image_spec_shorthand_25_10() {
        let img = VmImage::from_image_spec("25.10").unwrap();
        assert_eq!(img.publisher, "Canonical");
        assert_eq!(img.offer, "ubuntu-25_10");
        assert_eq!(img.sku, "server");
        assert_eq!(img.version, "latest");
    }

    #[test]
    fn test_from_image_spec_shorthand_24_04_lts() {
        let img = VmImage::from_image_spec("24.04-lts").unwrap();
        assert_eq!(img.publisher, "Canonical");
        assert_eq!(img.offer, "ubuntu-24_04-lts");
        assert_eq!(img.sku, "server");
        assert_eq!(img.version, "latest");
    }

    #[test]
    fn test_from_image_spec_shorthand_ubuntu_prefix() {
        // "ubuntu-25.10" should also resolve
        let img = VmImage::from_image_spec("ubuntu-25.10").unwrap();
        assert_eq!(img.publisher, "Canonical");
        assert_eq!(img.offer, "ubuntu-25_10");
    }

    #[test]
    fn test_from_image_spec_shorthand_dotless_ubuntu2510() {
        // "Ubuntu2510" as documented in --os help text
        let img = VmImage::from_image_spec("Ubuntu2510").unwrap();
        assert_eq!(img.offer, "ubuntu-25_10");
    }

    #[test]
    fn test_from_image_spec_shorthand_dotless_2404() {
        let img = VmImage::from_image_spec("2404").unwrap();
        assert_eq!(img.offer, "ubuntu-24_04-lts");
    }

    #[test]
    fn test_from_image_spec_shorthand_26_04_lts() {
        let img = VmImage::from_image_spec("26.04-lts").unwrap();
        assert_eq!(img.publisher, "Canonical");
        assert_eq!(img.offer, "ubuntu-26_04-lts");
        assert_eq!(img.sku, "server");
        assert_eq!(img.version, "latest");
    }

    #[test]
    fn test_from_image_spec_shorthand_26_04_bare() {
        let img = VmImage::from_image_spec("26.04").unwrap();
        assert_eq!(img.offer, "ubuntu-26_04-lts");
    }

    #[test]
    fn test_from_image_spec_shorthand_dotless_2604() {
        let img = VmImage::from_image_spec("2604").unwrap();
        assert_eq!(img.offer, "ubuntu-26_04-lts");
    }

    #[test]
    fn test_from_image_spec_shorthand_ubuntu_2604() {
        let img = VmImage::from_image_spec("Ubuntu2604").unwrap();
        assert_eq!(img.offer, "ubuntu-26_04-lts");
    }

    #[test]
    fn test_from_image_spec_case_insensitive_uppercase() {
        let img = VmImage::from_image_spec("UBUNTU-25.10").unwrap();
        assert_eq!(img.offer, "ubuntu-25_10");
    }

    #[test]
    fn test_from_image_spec_case_insensitive_title_dash() {
        // "Ubuntu-25.10" — title case with dash
        let img = VmImage::from_image_spec("Ubuntu-25.10").unwrap();
        assert_eq!(img.offer, "ubuntu-25_10");
    }

    #[test]
    fn test_from_image_spec_case_insensitive_no_dash() {
        // "Ubuntu24.04" — title case, no dash
        let img = VmImage::from_image_spec("Ubuntu24.04").unwrap();
        assert_eq!(img.offer, "ubuntu-24_04-lts");
    }

    #[test]
    fn test_from_image_spec_rejects_non_canonical_publisher() {
        let result = VmImage::from_image_spec("MicrosoftWindowsServer:WindowsServer:2022:latest");
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert!(
            err.contains("Canonical"),
            "error should mention Canonical restriction, got: {err}"
        );
    }

    #[test]
    fn test_from_image_spec_rejects_malformed_urn_3_parts() {
        let result = VmImage::from_image_spec("Canonical:ubuntu-25_10:server");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_malformed_urn_5_parts() {
        let result = VmImage::from_image_spec("Canonical:ubuntu-25_10:server:latest:extra");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_empty() {
        let result = VmImage::from_image_spec("");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_whitespace_only() {
        let result = VmImage::from_image_spec("   ");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_shell_metacharacters() {
        let result = VmImage::from_image_spec("Canonical:ubuntu-25_10;rm -rf /:server:latest");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_newlines() {
        let result = VmImage::from_image_spec("Canonical:ubuntu-25_10\n:server:latest");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_null_bytes() {
        let result = VmImage::from_image_spec("Canonical:ubuntu-25_10\0:server:latest");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_rejects_unknown_shorthand() {
        let result = VmImage::from_image_spec("windows-11");
        assert!(result.is_err());
    }

    #[test]
    fn test_from_image_spec_roundtrip_via_display() {
        // Parse a full URN, display it, re-parse — should be identical
        let original = VmImage::from_image_spec("Canonical:ubuntu-24_04-lts:server:latest").unwrap();
        let displayed = original.to_string();
        let reparsed = VmImage::from_image_spec(&displayed).unwrap();
        assert_eq!(original, reparsed);
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
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
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
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
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
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
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
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        let err = params.validate().unwrap_err();
        assert!(err.contains("SSH public key not found"));
    }

    // ── Additional model tests ──────────────────────────────────────

    #[test]
    fn test_power_state_all_variants_display() {
        assert_eq!(PowerState::Running.to_string(), "Running");
        assert_eq!(PowerState::Stopped.to_string(), "Stopped");
        assert_eq!(PowerState::Deallocated.to_string(), "Deallocated");
        assert_eq!(PowerState::Starting.to_string(), "Starting");
        assert_eq!(PowerState::Stopping.to_string(), "Stopping");
        assert_eq!(PowerState::Unknown.to_string(), "Unknown");
    }

    #[test]
    fn test_power_state_equality() {
        assert_eq!(PowerState::Running, PowerState::Running);
        assert_ne!(PowerState::Running, PowerState::Stopped);
        assert_ne!(PowerState::Deallocated, PowerState::Unknown);
    }

    #[test]
    fn test_power_state_serde_roundtrip() {
        for state in &[
            PowerState::Running,
            PowerState::Stopped,
            PowerState::Deallocated,
            PowerState::Starting,
            PowerState::Stopping,
            PowerState::Unknown,
        ] {
            let json = serde_json::to_string(state).unwrap();
            let deserialized: PowerState = serde_json::from_str(&json).unwrap();
            assert_eq!(*state, deserialized);
        }
    }

    #[test]
    fn test_os_type_serde_roundtrip() {
        let json_linux = serde_json::to_string(&OsType::Linux).unwrap();
        assert_eq!(json_linux, "\"linux\"");
        let json_windows = serde_json::to_string(&OsType::Windows).unwrap();
        assert_eq!(json_windows, "\"windows\"");

        let from_json: OsType = serde_json::from_str("\"linux\"").unwrap();
        assert_eq!(from_json, OsType::Linux);
        let from_json: OsType = serde_json::from_str("\"windows\"").unwrap();
        assert_eq!(from_json, OsType::Windows);
    }

    #[test]
    fn test_vm_info_with_tags() {
        let mut tags = HashMap::new();
        tags.insert("env".to_string(), "production".to_string());
        tags.insert("team".to_string(), "platform".to_string());
        let vm = VmInfo {
            name: "tagged-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "Standard_D2s_v3".to_string(),
            power_state: PowerState::Running,
            provisioning_state: ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags,
            created_time: None,
        };
        assert_eq!(vm.tags.get("env").unwrap(), "production");
        assert_eq!(vm.tags.get("team").unwrap(), "platform");
        assert_eq!(vm.tags.len(), 2);
    }

    #[test]
    fn test_vm_info_power_state_check() {
        let make_vm = |state: PowerState| VmInfo {
            name: "vm".to_string(),
            resource_group: "rg".to_string(),
            location: "westus2".to_string(),
            vm_size: "Standard_D2s_v3".to_string(),
            power_state: state,
            provisioning_state: ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: HashMap::new(),
            created_time: None,
        };
        assert_eq!(
            make_vm(PowerState::Running).power_state,
            PowerState::Running
        );
        assert_eq!(
            make_vm(PowerState::Stopped).power_state,
            PowerState::Stopped
        );
        assert_eq!(
            make_vm(PowerState::Deallocated).power_state,
            PowerState::Deallocated
        );
    }

    #[test]
    fn test_create_vm_params_validate_empty_resource_group() {
        let params = CreateVmParams {
            name: "vm".into(),
            resource_group: "".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        let err = params.validate().unwrap_err();
        assert!(err.contains("Resource group"));
    }

    #[test]
    fn test_create_vm_params_validate_empty_region() {
        let params = CreateVmParams {
            name: "vm".into(),
            resource_group: "rg".into(),
            region: "".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        let err = params.validate().unwrap_err();
        assert!(err.contains("Region"));
    }

    #[test]
    fn test_create_vm_params_validate_empty_vm_size() {
        let params = CreateVmParams {
            name: "vm".into(),
            resource_group: "rg".into(),
            region: "westus2".into(),
            vm_size: "".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        let err = params.validate().unwrap_err();
        assert!(err.contains("VM size"));
    }

    #[test]
    fn test_create_vm_params_validate_empty_username() {
        let params = CreateVmParams {
            name: "vm".into(),
            resource_group: "rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "".into(),
            ssh_key_path: PathBuf::from("/tmp/nonexistent.pub"),
            image: VmImage::default(),
            tags: HashMap::new(),
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        let err = params.validate().unwrap_err();
        assert!(err.contains("username"));
    }

    #[test]
    fn test_create_vm_params_validate_valid_with_existing_key() {
        let keyfile = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(keyfile.path(), "ssh-rsa AAAA...").unwrap();
        let params = CreateVmParams {
            name: "good-vm".into(),
            resource_group: "rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: keyfile.path().to_path_buf(),
            image: VmImage::default(),
            tags: HashMap::new(),
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        assert!(params.validate().is_ok());
    }

    #[test]
    fn test_create_vm_params_validate_name_exactly_64_chars() {
        let keyfile = tempfile::NamedTempFile::new().unwrap();
        std::fs::write(keyfile.path(), "ssh-rsa AAAA...").unwrap();
        let params = CreateVmParams {
            name: "a".repeat(64),
            resource_group: "rg".into(),
            region: "westus2".into(),
            vm_size: "Standard_D2s_v3".into(),
            admin_username: "azureuser".into(),
            ssh_key_path: keyfile.path().to_path_buf(),
            image: VmImage::default(),
            tags: HashMap::new(),
            public_ip_enabled: true,
            disk_ids: vec![],
            has_home_disk: false,
            has_tmp_disk: false,
        };
        assert!(params.validate().is_ok());
    }

    #[test]
    fn test_vm_image_custom() {
        let img = VmImage {
            publisher: "MicrosoftWindowsServer".into(),
            offer: "WindowsServer".into(),
            sku: "2022-Datacenter".into(),
            version: "latest".into(),
        };
        assert_eq!(
            img.to_string(),
            "MicrosoftWindowsServer:WindowsServer:2022-Datacenter:latest"
        );
    }

    #[test]
    fn test_vm_image_serde_roundtrip() {
        let img = VmImage::default();
        let json = serde_json::to_string(&img).unwrap();
        let deserialized: VmImage = serde_json::from_str(&json).unwrap();
        assert_eq!(img, deserialized);
    }

    #[test]
    fn test_command_result_exit_codes() {
        for code in [-1, 0, 1, 2, 127, 255] {
            let result = CommandResult {
                exit_code: code,
                stdout: String::new(),
                stderr: String::new(),
                duration_ms: 0,
            };
            assert_eq!(result.success(), code == 0);
        }
    }

    #[test]
    fn test_tmux_session_serialization() {
        let session = TmuxSession {
            vm_name: "vm-1".to_string(),
            session_name: "dev".to_string(),
            windows: 5,
            created_time: "2024-06-01T10:00:00Z".to_string(),
            attached: true,
        };
        let json = serde_json::to_string(&session).unwrap();
        let deserialized: TmuxSession = serde_json::from_str(&json).unwrap();
        assert_eq!(deserialized.vm_name, "vm-1");
        assert_eq!(deserialized.session_name, "dev");
        assert_eq!(deserialized.windows, 5);
        assert!(deserialized.attached);
    }

    #[test]
    fn test_cost_summary_total_matches_sum() {
        let summary = CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: Utc::now(),
            period_end: Utc::now(),
            by_vm: vec![
                VmCost {
                    vm_name: "a".into(),
                    cost: 60.0,
                    currency: "USD".into(),
                },
                VmCost {
                    vm_name: "b".into(),
                    cost: 40.0,
                    currency: "USD".into(),
                },
            ],
        };
        let sum: f64 = summary.by_vm.iter().map(|v| v.cost).sum();
        assert!((summary.total_cost - sum).abs() < f64::EPSILON);
    }

    #[test]
    fn test_validate_vm_name_valid() {
        assert!(validate_vm_name("my-vm-01").is_ok());
        assert!(validate_vm_name("dev.server").is_ok());
        assert!(validate_vm_name("a").is_ok());
    }

    #[test]
    fn test_validate_vm_name_empty() {
        assert!(validate_vm_name("").is_err());
    }

    #[test]
    fn test_validate_vm_name_too_long() {
        assert!(validate_vm_name(&"a".repeat(65)).is_err());
        assert!(validate_vm_name(&"a".repeat(64)).is_ok());
    }

    #[test]
    fn test_validate_vm_name_leading_hyphen() {
        assert!(validate_vm_name("-bad").is_err());
    }

    #[test]
    fn test_validate_vm_name_trailing_hyphen() {
        assert!(validate_vm_name("bad-").is_err());
    }

    #[test]
    fn test_validate_vm_name_special_chars() {
        assert!(validate_vm_name("bad@name").is_err());
        assert!(validate_vm_name("bad name").is_err());
        assert!(validate_vm_name("bad;name").is_err());
    }

    #[test]
    fn test_vm_info_windows_type() {
        let vm = VmInfo {
            name: "win-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "Standard_D2s_v3".to_string(),
            power_state: PowerState::Running,
            provisioning_state: ProvisioningState::Succeeded,
            os_type: OsType::Windows,
            os_offer: None,
            public_ip: Some("1.2.3.4".to_string()),
            private_ip: Some("10.0.0.5".to_string()),
            admin_username: Some("adminuser".to_string()),
            tags: HashMap::new(),
            created_time: Some(Utc::now()),
        };
        assert_eq!(vm.os_type, OsType::Windows);
        assert!(vm.created_time.is_some());
    }

    // ── ProvisioningState tests ────────────────────────────────────────

    #[test]
    fn test_provisioning_state_from_known_strings() {
        assert_eq!(
            ProvisioningState::from("Succeeded"),
            ProvisioningState::Succeeded
        );
        assert_eq!(ProvisioningState::from("Failed"), ProvisioningState::Failed);
        assert_eq!(
            ProvisioningState::from("Creating"),
            ProvisioningState::Creating
        );
        assert_eq!(
            ProvisioningState::from("Deleting"),
            ProvisioningState::Deleting
        );
        assert_eq!(
            ProvisioningState::from("Updating"),
            ProvisioningState::Updating
        );
        assert_eq!(
            ProvisioningState::from("Migrating"),
            ProvisioningState::Migrating
        );
    }

    #[test]
    fn test_provisioning_state_from_unknown() {
        let state = ProvisioningState::from("SomethingNew");
        assert_eq!(state, ProvisioningState::Other("SomethingNew".to_string()));
    }

    #[test]
    fn test_provisioning_state_display() {
        assert_eq!(ProvisioningState::Succeeded.to_string(), "Succeeded");
        assert_eq!(ProvisioningState::Failed.to_string(), "Failed");
        assert_eq!(ProvisioningState::Creating.to_string(), "Creating");
        assert_eq!(
            ProvisioningState::Other("Custom".to_string()).to_string(),
            "Custom"
        );
    }

    #[test]
    fn test_provisioning_state_default() {
        assert_eq!(ProvisioningState::default(), ProvisioningState::Succeeded);
    }

    #[test]
    fn test_provisioning_state_serde_roundtrip() {
        let states = vec![
            ProvisioningState::Succeeded,
            ProvisioningState::Failed,
            ProvisioningState::Creating,
        ];
        for state in states {
            let json = serde_json::to_string(&state).unwrap();
            let deserialized: ProvisioningState = serde_json::from_str(&json).unwrap();
            assert_eq!(state, deserialized);
        }
    }
}
