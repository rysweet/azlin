#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) fn handle_bastion_list(resource_group: Option<String>) -> Result<()> {
    println!("Listing Bastion hosts...");
    let mut cmd = std::process::Command::new("az");
    cmd.args(["network", "bastion", "list", "-o", "json"]);
    if let Some(rg) = &resource_group {
        cmd.args(["--resource-group", rg]);
    }
    let output = cmd.output()?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Error listing Bastion hosts: {}",
            azlin_core::sanitizer::sanitize(&err)
        );
    }
    let bastions: Vec<serde_json::Value> =
        serde_json::from_slice(&output.stdout).context("Failed to parse Bastion host list JSON")?;
    if bastions.is_empty() {
        if let Some(rg) = &resource_group {
            println!("No Bastion hosts found in resource group: {}", rg);
        } else {
            println!("No Bastion hosts found in subscription");
        }
    } else {
        println!("\nFound {} Bastion host(s):\n", bastions.len());
        for b in &bastions {
            let (name, rg, location, sku, state) = crate::bastion_helpers::bastion_summary(b);
            println!("  {}", name);
            println!("    Resource Group: {}", rg);
            println!("    Location: {}", location);
            println!("    SKU: {}", sku);
            println!("    State: {}", state);
            println!();
        }
    }
    Ok(())
}

pub(crate) fn handle_bastion_status(name: &str, resource_group: &str) -> Result<()> {
    println!("Checking Bastion host: {}...", name);
    let output = std::process::Command::new("az")
        .args([
            "network",
            "bastion",
            "show",
            "--name",
            name,
            "--resource-group",
            resource_group,
            "-o",
            "json",
        ])
        .output()?;
    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Bastion host not found: {} in {}: {}",
            name,
            resource_group,
            azlin_core::sanitizer::sanitize(&err)
        );
    }
    let b: serde_json::Value = serde_json::from_slice(&output.stdout)?;
    println!(
        "\nBastion Host: {}",
        b["name"].as_str().unwrap_or("unknown")
    );
    println!(
        "Resource Group: {}",
        b["resourceGroup"].as_str().unwrap_or("unknown")
    );
    println!("Location: {}", b["location"].as_str().unwrap_or("unknown"));
    println!("SKU: {}", b["sku"]["name"].as_str().unwrap_or("Standard"));
    println!(
        "Provisioning State: {}",
        b["provisioningState"].as_str().unwrap_or("Unknown")
    );
    println!("DNS Name: {}", b["dnsName"].as_str().unwrap_or("N/A"));
    let ip_config_list = crate::bastion_helpers::extract_ip_configs(&b);
    if !ip_config_list.is_empty() {
        println!("\nIP Configurations: {}", ip_config_list.len());
        for (idx, (subnet_short, pip_short)) in ip_config_list.iter().enumerate() {
            println!("  [{}] Subnet: {}", idx + 1, subnet_short);
            println!("      Public IP: {}", pip_short);
        }
    }
    Ok(())
}

pub(crate) fn handle_bastion_configure(
    vm_name: &str,
    bastion_name: &str,
    resource_group: Option<String>,
    bastion_resource_group: Option<String>,
    disable: bool,
) -> Result<()> {
    let vm_rg = resolve_resource_group(resource_group)?;
    let bastion_rg = bastion_resource_group.unwrap_or_else(|| vm_rg.clone());

    let config_dir = home_dir()?.join(".azlin");
    std::fs::create_dir_all(&config_dir)?;
    let config_path = config_dir.join("bastion_config.json");

    let mut config: serde_json::Value = if config_path.exists() {
        let data = std::fs::read_to_string(&config_path)?;
        serde_json::from_str(&data).unwrap_or(serde_json::json!({"mappings": {}}))
    } else {
        serde_json::json!({"mappings": {}})
    };

    let mappings = config["mappings"]
        .as_object_mut()
        .ok_or_else(|| anyhow::anyhow!("Invalid bastion config format"))?;

    if disable {
        mappings.remove(vm_name);
        std::fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
        println!("Disabled Bastion mapping for: {}", vm_name);
    } else {
        mappings.insert(
            vm_name.to_string(),
            serde_json::json!({
                "bastion_name": bastion_name,
                "vm_resource_group": vm_rg,
                "bastion_resource_group": bastion_rg,
            }),
        );
        std::fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
        println!("Configured {} to use Bastion: {}", vm_name, bastion_name);
        println!("  VM RG: {}", vm_rg);
        println!("  Bastion RG: {}", bastion_rg);
        println!("\nConnection will now route through Bastion automatically.");
    }
    Ok(())
}
