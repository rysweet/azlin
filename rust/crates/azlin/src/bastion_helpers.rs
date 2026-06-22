// ── Bastion naming conventions ────────────────────────────────────────

/// Return the canonical bastion host name for a given Azure region.
pub fn bastion_name_for_region(region: &str) -> String {
    format!("azlin-bastion-{}", region.to_lowercase())
}

/// Return the canonical bastion VNet name for a given Azure region.
pub fn bastion_vnet_name(region: &str) -> String {
    format!("azlin-bastion-{}-vnet", region.to_lowercase())
}

/// Return the canonical bastion public IP name for a given Azure region.
pub fn bastion_pip_name(region: &str) -> String {
    format!("azlin-bastion-{}-pip", region.to_lowercase())
}

// ── Bastion existence check ──────────────────────────────────────────

/// Check if any detected bastion host matches the given region (case-insensitive).
/// `bastions` is the output of `detect_bastion_hosts()`: Vec of (name, location, sku).
pub fn bastion_exists_in_region(bastions: &[(String, String, String)], region: &str) -> bool {
    let region_lower = region.to_lowercase();
    bastions.iter().any(|(_, loc, _)| loc.to_lowercase() == region_lower)
}

// ── Az CLI command builders for bastion infrastructure ────────────────

/// Build `az network vnet create` arguments for the bastion VNet.
pub fn build_create_vnet_args(resource_group: &str, region: &str) -> Vec<String> {
    let vnet = bastion_vnet_name(region);
    vec![
        "network".into(), "vnet".into(), "create".into(),
        "--resource-group".into(), resource_group.into(),
        "--name".into(), vnet,
        "--location".into(), region.to_lowercase(),
        "--address-prefix".into(), "10.0.0.0/16".into(),
        "--subnet-name".into(), "default".into(),
        "--subnet-prefix".into(), "10.0.0.0/24".into(),
        "--output".into(), "none".into(),
    ]
}

/// Build `az network vnet subnet create` arguments for AzureBastionSubnet.
pub fn build_create_bastion_subnet_args(resource_group: &str, region: &str) -> Vec<String> {
    let vnet = bastion_vnet_name(region);
    vec![
        "network".into(), "vnet".into(), "subnet".into(), "create".into(),
        "--resource-group".into(), resource_group.into(),
        "--vnet-name".into(), vnet,
        "--name".into(), "AzureBastionSubnet".into(),
        "--address-prefix".into(), "10.0.1.0/26".into(),
        "--output".into(), "none".into(),
    ]
}

/// Build `az network public-ip create` arguments for the bastion public IP.
pub fn build_create_pip_args(resource_group: &str, region: &str) -> Vec<String> {
    let pip = bastion_pip_name(region);
    vec![
        "network".into(), "public-ip".into(), "create".into(),
        "--resource-group".into(), resource_group.into(),
        "--name".into(), pip,
        "--location".into(), region.to_lowercase(),
        "--sku".into(), "Standard".into(),
        "--allocation-method".into(), "Static".into(),
        "--output".into(), "none".into(),
    ]
}

/// Build `az network bastion create` arguments for the bastion host.
pub fn build_create_bastion_args(resource_group: &str, region: &str) -> Vec<String> {
    let bastion = bastion_name_for_region(region);
    let vnet = bastion_vnet_name(region);
    let pip = bastion_pip_name(region);
    vec![
        "network".into(), "bastion".into(), "create".into(),
        "--resource-group".into(), resource_group.into(),
        "--name".into(), bastion,
        "--location".into(), region.to_lowercase(),
        "--vnet-name".into(), vnet,
        "--public-ip-address".into(), pip,
        "--sku".into(), "Standard".into(),
        "--enable-tunneling".into(), "true".into(),
        "--output".into(), "none".into(),
    ]
}

/// Build `az network vnet show` arguments to check VNet existence.
pub fn build_check_vnet_args(resource_group: &str, region: &str) -> Vec<String> {
    let vnet = bastion_vnet_name(region);
    vec![
        "network".into(), "vnet".into(), "show".into(),
        "--resource-group".into(), resource_group.into(),
        "--name".into(), vnet,
        "--output".into(), "none".into(),
    ]
}

/// Build `az network vnet subnet show` arguments to check AzureBastionSubnet existence.
pub fn build_check_bastion_subnet_args(resource_group: &str, region: &str) -> Vec<String> {
    let vnet = bastion_vnet_name(region);
    vec![
        "network".into(), "vnet".into(), "subnet".into(), "show".into(),
        "--resource-group".into(), resource_group.into(),
        "--vnet-name".into(), vnet,
        "--name".into(), "AzureBastionSubnet".into(),
        "--output".into(), "none".into(),
    ]
}

// ── Orchestrator: ensure bastion infrastructure exists ────────────────

/// Run an `az` CLI command and return its output.
fn run_az(args: &[String]) -> anyhow::Result<std::process::Output> {
    Ok(std::process::Command::new("az")
        .args(args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()?)
}

/// Run an `az` CLI command and bail with a contextual message on failure.
fn run_az_or_bail(args: &[String], context: &str) -> anyhow::Result<()> {
    let output = run_az(args)?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "{}: {}",
            context,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

/// Ensure the bastion VNet, AzureBastionSubnet, public IP, and bastion host
/// all exist in the target region. Creates only what is missing (idempotent).
///
/// Uses `penguin_spinner` (via the supplied callback) for user feedback during
/// long-running operations.
pub fn ensure_bastion_infrastructure(
    resource_group: &str,
    region: &str,
) -> anyhow::Result<()> {
    // Normalize region once to avoid repeated to_lowercase() in every helper call.
    let region = &region.to_lowercase();

    // Pre-compute names once (each would otherwise call to_lowercase again).
    let vnet = bastion_vnet_name(region);
    let pip = bastion_pip_name(region);
    let bastion = bastion_name_for_region(region);

    // 1. Check / create VNet
    let vnet_exists = run_az(&build_check_vnet_args(resource_group, region))?.status.success();
    let vnet_created = if !vnet_exists {
        eprintln!("Creating bastion VNet '{vnet}' in {region}...");
        run_az_or_bail(
            &build_create_vnet_args(resource_group, region),
            &format!("Failed to create bastion VNet in {region}"),
        )?;
        eprintln!("  ✓ VNet created (includes default subnet)");
        true
    } else {
        eprintln!("  ✓ VNet '{vnet}' already exists");
        false
    };

    // 2. Check / create AzureBastionSubnet.
    //    Skip the existence check when VNet was just created — the bastion
    //    subnet cannot exist yet, saving one az CLI round-trip (~2-3 s).
    let subnet_exists = if vnet_created {
        false
    } else {
        run_az(&build_check_bastion_subnet_args(resource_group, region))?.status.success()
    };
    if !subnet_exists {
        eprintln!("Creating AzureBastionSubnet...");
        run_az_or_bail(
            &build_create_bastion_subnet_args(resource_group, region),
            "Failed to create AzureBastionSubnet",
        )?;
        eprintln!("  ✓ AzureBastionSubnet created (10.0.1.0/26)");
    } else {
        eprintln!("  ✓ AzureBastionSubnet already exists");
    }

    // 3. Create public IP (idempotent — `az network public-ip create` is a
    //    create-or-update operation)
    eprintln!("Ensuring public IP '{pip}'...");
    run_az_or_bail(
        &build_create_pip_args(resource_group, region),
        &format!("Failed to create bastion public IP in {region}"),
    )?;
    eprintln!("  ✓ Public IP ready");

    // 4. Create bastion host (this is the slow step: ~5-10 min)
    eprintln!("Creating Azure Bastion '{bastion}' (Standard SKU, tunneling enabled)...");
    eprintln!("  This typically takes 5-10 minutes. Please wait...");
    run_az_or_bail(
        &build_create_bastion_args(resource_group, region),
        &format!("Failed to create Azure Bastion in {region}"),
    )?;
    eprintln!("  ✓ Azure Bastion provisioned and ready");

    Ok(())
}

// ── Existing functions ───────────────────────────────────────────────

/// Extract display fields from a Bastion host JSON value.
pub fn bastion_summary(b: &serde_json::Value) -> (String, String, String, String, String) {
    (
        b["name"].as_str().unwrap_or("unknown").to_string(),
        b["resourceGroup"].as_str().unwrap_or("unknown").to_string(),
        b["location"].as_str().unwrap_or("unknown").to_string(),
        b["sku"]["name"].as_str().unwrap_or("Standard").to_string(),
        b["provisioningState"]
            .as_str()
            .unwrap_or("unknown")
            .to_string(),
    )
}

/// Extract the short name from the end of an Azure resource ID.
pub fn shorten_resource_id(id: &str) -> &str {
    if id == "N/A" {
        return "N/A";
    }
    id.rsplit('/').next().unwrap_or("N/A")
}

/// Extract IP configuration details from a Bastion JSON value.
/// Returns Vec of (subnet_short, public_ip_short).
pub fn extract_ip_configs(b: &serde_json::Value) -> Vec<(String, String)> {
    let mut result = Vec::new();
    if let Some(configs) = b["ipConfigurations"].as_array() {
        for config in configs {
            let subnet_id = config["subnet"]["id"].as_str().unwrap_or("N/A");
            let public_ip_id = config["publicIPAddress"]["id"].as_str().unwrap_or("N/A");
            result.push((
                shorten_resource_id(subnet_id).to_string(),
                shorten_resource_id(public_ip_id).to_string(),
            ));
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── Naming convention tests ──────────────────────────────────────

    #[test]
    fn test_bastion_name_for_region_lowercase() {
        assert_eq!(bastion_name_for_region("eastus2"), "azlin-bastion-eastus2");
    }

    #[test]
    fn test_bastion_name_for_region_normalizes_case() {
        assert_eq!(bastion_name_for_region("EastUS2"), "azlin-bastion-eastus2");
    }

    #[test]
    fn test_bastion_vnet_name() {
        assert_eq!(bastion_vnet_name("westus"), "azlin-bastion-westus-vnet");
    }

    #[test]
    fn test_bastion_pip_name() {
        assert_eq!(bastion_pip_name("westus"), "azlin-bastion-westus-pip");
    }

    // ── Bastion existence check tests ────────────────────────────────

    #[test]
    fn test_bastion_exists_in_region_found() {
        let bastions = vec![
            ("azlin-bastion-eastus2".into(), "eastus2".into(), "Standard".into()),
            ("azlin-bastion-westus".into(), "westus".into(), "Standard".into()),
        ];
        assert!(bastion_exists_in_region(&bastions, "eastus2"));
    }

    #[test]
    fn test_bastion_exists_in_region_not_found() {
        let bastions = vec![
            ("azlin-bastion-eastus2".into(), "eastus2".into(), "Standard".into()),
        ];
        assert!(!bastion_exists_in_region(&bastions, "westus"));
    }

    #[test]
    fn test_bastion_exists_in_region_case_insensitive() {
        let bastions = vec![
            ("azlin-bastion-eastus2".into(), "EastUS2".into(), "Standard".into()),
        ];
        assert!(bastion_exists_in_region(&bastions, "eastus2"));
        assert!(bastion_exists_in_region(&bastions, "EASTUS2"));
    }

    #[test]
    fn test_bastion_exists_in_region_empty_list() {
        let bastions: Vec<(String, String, String)> = vec![];
        assert!(!bastion_exists_in_region(&bastions, "eastus2"));
    }

    // ── Command builder tests ────────────────────────────────────────

    #[test]
    fn test_build_create_vnet_args_contains_required_fields() {
        let args = build_create_vnet_args("my-rg", "eastus2");
        assert!(args.contains(&"network".to_string()));
        assert!(args.contains(&"vnet".to_string()));
        assert!(args.contains(&"create".to_string()));
        assert!(args.contains(&"my-rg".to_string()));
        assert!(args.contains(&"azlin-bastion-eastus2-vnet".to_string()));
        assert!(args.contains(&"10.0.0.0/16".to_string()));
        assert!(args.contains(&"default".to_string()));
        assert!(args.contains(&"10.0.0.0/24".to_string()));
    }

    #[test]
    fn test_build_create_bastion_subnet_args_has_correct_subnet_name() {
        let args = build_create_bastion_subnet_args("my-rg", "eastus2");
        assert!(args.contains(&"AzureBastionSubnet".to_string()));
        assert!(args.contains(&"10.0.1.0/26".to_string()));
        assert!(args.contains(&"azlin-bastion-eastus2-vnet".to_string()));
    }

    #[test]
    fn test_build_create_pip_args_uses_standard_sku() {
        let args = build_create_pip_args("my-rg", "westus");
        assert!(args.contains(&"azlin-bastion-westus-pip".to_string()));
        assert!(args.contains(&"Standard".to_string()));
        assert!(args.contains(&"Static".to_string()));
    }

    #[test]
    fn test_build_create_bastion_args_enables_tunneling() {
        let args = build_create_bastion_args("my-rg", "eastus2");
        assert!(args.contains(&"azlin-bastion-eastus2".to_string()));
        assert!(args.contains(&"azlin-bastion-eastus2-vnet".to_string()));
        assert!(args.contains(&"azlin-bastion-eastus2-pip".to_string()));
        assert!(args.contains(&"Standard".to_string()));
        // Tunneling must be enabled for SSH access
        let tunnel_idx = args.iter().position(|a| a == "--enable-tunneling").unwrap();
        assert_eq!(args[tunnel_idx + 1], "true");
    }

    #[test]
    fn test_build_create_bastion_args_normalizes_region_case() {
        let args = build_create_bastion_args("my-rg", "EastUS2");
        assert!(args.contains(&"azlin-bastion-eastus2".to_string()));
        assert!(args.contains(&"eastus2".to_string())); // location arg
    }

    #[test]
    fn test_build_check_vnet_args() {
        let args = build_check_vnet_args("my-rg", "eastus2");
        assert!(args.contains(&"show".to_string()));
        assert!(args.contains(&"azlin-bastion-eastus2-vnet".to_string()));
        assert!(args.contains(&"my-rg".to_string()));
    }

    #[test]
    fn test_build_check_bastion_subnet_args() {
        let args = build_check_bastion_subnet_args("my-rg", "eastus2");
        assert!(args.contains(&"subnet".to_string()));
        assert!(args.contains(&"show".to_string()));
        assert!(args.contains(&"AzureBastionSubnet".to_string()));
        assert!(args.contains(&"azlin-bastion-eastus2-vnet".to_string()));
    }

    // ── Existing function tests ──────────────────────────────────────

    #[test]
    fn test_shorten_resource_id_extracts_last_segment() {
        assert_eq!(
            shorten_resource_id("/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/bastionHosts/my-bastion"),
            "my-bastion"
        );
    }

    #[test]
    fn test_shorten_resource_id_na_passthrough() {
        assert_eq!(shorten_resource_id("N/A"), "N/A");
    }
}
