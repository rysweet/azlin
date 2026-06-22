/// Map a user-facing storage tier string to the Azure SKU name.
pub fn storage_sku_from_tier(tier: &str) -> &'static str {
    match tier.to_lowercase().as_str() {
        "premium" => "Premium_LRS",
        "standard" => "Standard_LRS",
        _ => "Premium_LRS",
    }
}

/// Extract display columns from a storage account JSON value.
pub fn storage_account_row(acct: &serde_json::Value) -> Vec<String> {
    vec![
        acct["name"].as_str().unwrap_or("-").to_string(),
        acct["location"].as_str().unwrap_or("-").to_string(),
        acct["kind"].as_str().unwrap_or("-").to_string(),
        acct["sku"]["name"].as_str().unwrap_or("-").to_string(),
        acct["provisioningState"]
            .as_str()
            .unwrap_or("-")
            .to_string(),
    ]
}
