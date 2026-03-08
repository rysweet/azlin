/// Extract subscription, tenant, and user from an `az account show` JSON response.
pub fn extract_account_info(acct: &serde_json::Value) -> (String, String, String) {
    (
        acct["name"].as_str().unwrap_or("-").to_string(),
        acct["tenantId"].as_str().unwrap_or("-").to_string(),
        acct["user"]["name"].as_str().unwrap_or("-").to_string(),
    )
}
