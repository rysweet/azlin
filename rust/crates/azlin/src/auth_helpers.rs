/// Return a display-safe representation of a profile field value.
/// Secrets (fields whose key contains "secret" or "password") are masked.
pub fn mask_profile_value(key: &str, value: &serde_json::Value) -> String {
    match value {
        serde_json::Value::String(s) => {
            if key.contains("secret") || key.contains("password") {
                "********".to_string()
            } else {
                s.clone()
            }
        }
        other => other.to_string(),
    }
}
