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
