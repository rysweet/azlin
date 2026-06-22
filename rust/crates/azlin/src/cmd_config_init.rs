use anyhow::Result;
use console::Style;
use dialoguer::{Confirm, Input, Select};

/// Known Azure regions for autocomplete selection.
const REGIONS: &[&str] = &[
    "eastus",
    "eastus2",
    "westus",
    "westus2",
    "westus3",
    "centralus",
    "northcentralus",
    "southcentralus",
    "northeurope",
    "westeurope",
    "uksouth",
    "ukwest",
    "francecentral",
    "germanywestcentral",
    "switzerlandnorth",
    "swedencentral",
    "eastasia",
    "southeastasia",
    "japaneast",
    "australiaeast",
    "canadacentral",
    "centralindia",
    "koreacentral",
    "brazilsouth",
];

/// Common VM sizes for the picker.
const VM_SIZES: &[&str] = &[
    "Standard_B1ms",
    "Standard_B2ms",
    "Standard_B4ms",
    "Standard_D2s_v3",
    "Standard_D4s_v3",
    "Standard_D8s_v3",
    "Standard_E2as_v5",
    "Standard_E4as_v5",
    "Standard_E8as_v5",
    "Standard_E16as_v5",
    "Standard_E32as_v5",
];

/// Run the interactive first-run configuration wizard.
pub(crate) fn handle_config_init(force: bool) -> Result<()> {
    let config_path = azlin_core::AzlinConfig::config_path()?;
    let bold = Style::new().bold();
    let cyan = Style::new().cyan();
    let green = Style::new().green();

    if config_path.exists() && !force {
        println!(
            "Configuration already exists at {}",
            cyan.apply_to(config_path.display())
        );
        let overwrite = Confirm::new()
            .with_prompt("Re-run setup wizard? This will overwrite your current config")
            .default(false)
            .interact()?;
        if !overwrite {
            println!("Keeping existing configuration.");
            return Ok(());
        }
    }

    println!();
    println!(
        "  {}",
        bold.apply_to("Welcome to azlin! Let's set up your configuration.")
    );
    println!();

    // 1. Azure subscription (optional -- detected from az cli)
    let subscription = detect_subscription();
    if let Some(ref sub) = subscription {
        println!("  Detected Azure subscription: {}", cyan.apply_to(sub));
    }

    // 2. Resource group
    let resource_group: String = Input::new()
        .with_prompt("Default resource group")
        .allow_empty(true)
        .interact_text()?;
    let resource_group = if resource_group.is_empty() {
        None
    } else {
        Some(resource_group)
    };

    // 3. Region selection with fuzzy match
    let region_items: Vec<String> = REGIONS.iter().map(|s| s.to_string()).collect();
    let region_idx = Select::new()
        .with_prompt("Default Azure region")
        .items(&region_items)
        .default(3) // westus2
        .interact()?;
    let region = REGIONS[region_idx].to_string();

    // 4. VM size
    let size_items: Vec<String> = VM_SIZES.iter().map(|s| s.to_string()).collect();
    let size_idx = Select::new()
        .with_prompt("Default VM size")
        .items(&size_items)
        .default(9) // Standard_E16as_v5
        .interact()?;
    let vm_size = VM_SIZES[size_idx].to_string();

    // 5. SSH key selection
    let ssh_key = pick_ssh_key();
    if let Some(ref key) = ssh_key {
        println!("  Using SSH key: {}", cyan.apply_to(key.display()));
    }

    // 6. Build and save config
    let config = azlin_core::AzlinConfig {
        default_resource_group: resource_group,
        default_region: region,
        default_vm_size: vm_size,
        ..azlin_core::AzlinConfig::default()
    };

    config.save()?;

    println!();
    println!(
        "  {} Configuration saved to {}",
        green.apply_to("Done!"),
        cyan.apply_to(config_path.display())
    );
    println!();
    println!("  Quick start:");
    println!("    azlin new              # Create a new VM");
    println!("    azlin list             # List your VMs");
    println!("    azlin connect <name>   # SSH into a VM");
    println!("    azlin config show      # View your configuration");
    println!();

    Ok(())
}

/// Try to detect the current Azure subscription from `az account show`.
fn detect_subscription() -> Option<String> {
    let output = std::process::Command::new("az")
        .args(["account", "show", "--query", "name", "-o", "tsv"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .output()
        .ok()?;

    if output.status.success() {
        let name = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !name.is_empty() {
            return Some(name);
        }
    }
    None
}

/// List SSH keys in ~/.ssh/ and let the user pick one.
fn pick_ssh_key() -> Option<std::path::PathBuf> {
    let ssh_dir = dirs::home_dir()?.join(".ssh");
    if !ssh_dir.exists() {
        return None;
    }

    let mut keys = Vec::new();
    if let Ok(entries) = std::fs::read_dir(&ssh_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                let name = path.file_name()?.to_string_lossy().to_string();
                // Skip .pub files, known_hosts, config, authorized_keys
                if !name.ends_with(".pub")
                    && name != "known_hosts"
                    && name != "known_hosts.old"
                    && name != "config"
                    && name != "authorized_keys"
                {
                    // Quick check: does a matching .pub exist?
                    let pub_path = path.with_extension(
                        path.extension()
                            .map(|e| format!("{}.pub", e.to_string_lossy()))
                            .unwrap_or_else(|| "pub".to_string()),
                    );
                    if pub_path.exists() || name.starts_with("id_") || name.contains("azlin") {
                        keys.push(path);
                    }
                }
            }
        }
    }

    if keys.is_empty() {
        return None;
    }

    let display_names: Vec<String> = keys
        .iter()
        .map(|k| {
            let name = k.file_name().unwrap().to_string_lossy().to_string();
            let fingerprint = get_key_fingerprint(k).unwrap_or_default();
            if fingerprint.is_empty() {
                name
            } else {
                format!("{} ({})", name, fingerprint)
            }
        })
        .collect();

    let selection = Select::new()
        .with_prompt("SSH key to use")
        .items(&display_names)
        .default(0)
        .interact()
        .ok()?;

    Some(keys[selection].clone())
}

/// Get a short fingerprint for an SSH key file.
fn get_key_fingerprint(key_path: &std::path::Path) -> Option<String> {
    let output = std::process::Command::new("ssh-keygen")
        .args(["-l", "-f"])
        .arg(key_path)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .output()
        .ok()?;

    if output.status.success() {
        let line = String::from_utf8_lossy(&output.stdout);
        // Format: "2048 SHA256:... user@host (RSA)"
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() >= 2 {
            let hash = parts[1];
            if hash.len() > 20 {
                return Some(format!("{}...", &hash[..20]));
            }
            return Some(hash.to_string());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_regions_non_empty_and_lowercase() {
        assert!(!REGIONS.is_empty());
        for region in REGIONS {
            assert!(!region.is_empty());
            assert!(
                region
                    .chars()
                    .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit()),
                "region '{}' should be lowercase alphanumeric",
                region
            );
        }
    }

    #[test]
    fn test_vm_sizes_start_with_standard() {
        for size in VM_SIZES {
            assert!(
                size.starts_with("Standard_"),
                "VM size '{}' should start with Standard_",
                size
            );
        }
    }

    #[test]
    fn test_detect_subscription_no_panic() {
        let _result = detect_subscription();
    }
}
