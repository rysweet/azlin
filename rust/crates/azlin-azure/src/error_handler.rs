use serde_json::Value;

/// Represents a parsed Azure error response
#[derive(Debug, Clone)]
pub struct AzureError {
    pub code: String,
    pub message: String,
    pub target: Option<String>,
    pub details: Vec<AzureError>,
}

/// Parse Azure error JSON response into structured error
pub fn parse_azure_error(body: &str) -> Option<AzureError> {
    let json: Value = serde_json::from_str(body).ok()?;
    let error = json.get("error")?;

    Some(AzureError {
        code: error.get("code")?.as_str()?.to_string(),
        message: error.get("message")?.as_str()?.to_string(),
        target: error.get("target").and_then(|t| t.as_str()).map(|s| s.to_string()),
        details: error.get("details")
            .and_then(|d| d.as_array())
            .map(|arr| arr.iter().filter_map(|d| {
                Some(AzureError {
                    code: d.get("code")?.as_str()?.to_string(),
                    message: d.get("message")?.as_str()?.to_string(),
                    target: d.get("target").and_then(|t| t.as_str()).map(|s| s.to_string()),
                    details: vec![],
                })
            }).collect())
            .unwrap_or_default(),
    })
}

/// Format Azure error into user-friendly message with actionable suggestions
pub fn format_user_friendly_error(error: &AzureError) -> String {
    let mut msg = String::new();

    match error.code.as_str() {
        "ResourceGroupNotFound" => {
            msg.push_str(&format!("❌ Resource group not found: {}\n", error.message));
            msg.push_str("💡 Create it with: az group create --name <name> --location <location>\n");
        }
        "AuthorizationFailed" => {
            msg.push_str(&format!("🔒 Authorization failed: {}\n", error.message));
            msg.push_str("💡 Check your Azure RBAC permissions or run: az login\n");
        }
        "Conflict" | "ResourceConflict" => {
            msg.push_str(&format!("⚠️ Resource conflict: {}\n", error.message));
            if error.message.contains("location") || error.message.contains("region") {
                msg.push_str("💡 The resource exists in a different region. Use --location to match.\n");
            } else {
                msg.push_str("💡 A resource with this name already exists. Use a different name.\n");
            }
        }
        "OperationNotAllowed" => {
            msg.push_str(&format!("🚫 Operation not allowed: {}\n", error.message));
            if error.message.contains("quota") || error.message.contains("Quota") {
                msg.push_str("💡 You've hit a quota limit. Request a quota increase or use a different VM size/region.\n");
            }
        }
        "InvalidParameter" | "InvalidParameterValue" => {
            msg.push_str(&format!("❌ Invalid parameter: {}\n", error.message));
            if let Some(target) = &error.target {
                msg.push_str(&format!("💡 Check the value of: {}\n", target));
            }
        }
        "SubscriptionNotFound" => {
            msg.push_str("❌ Subscription not found.\n");
            msg.push_str("💡 Run: az account list --output table\n");
            msg.push_str("💡 Then: azlin config set subscription_id <id>\n");
        }
        _ => {
            msg.push_str(&format!("❌ Azure error [{}]: {}\n", error.code, error.message));
        }
    }

    if !error.details.is_empty() {
        msg.push_str("\nDetails:\n");
        for detail in &error.details {
            msg.push_str(&format!("  - [{}] {}\n", detail.code, detail.message));
        }
    }

    msg
}

/// Sanitize sensitive data from Azure CLI command strings for logging
pub fn sanitize_command_for_logging(command: &str) -> String {
    let sensitive_params = [
        "--admin-password",
        "--connection-string",
        "--storage-account-key",
        "--sas-token",
        "--client-secret",
    ];

    let mut sanitized = command.to_string();
    for param in &sensitive_params {
        if let Some(idx) = sanitized.find(param) {
            let param_end = idx + param.len();
            // Skip the space between param and its value
            let value_start = param_end + sanitized[param_end..].find(|c: char| !c.is_whitespace()).unwrap_or(0);
            if let Some(space_idx) = sanitized[value_start..].find(' ') {
                let value_end = value_start + space_idx;
                sanitized.replace_range(param_end..value_end, " ***REDACTED***");
            } else {
                sanitized.truncate(param_end);
                sanitized.push_str(" ***REDACTED***");
            }
        }
    }
    sanitized
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_azure_error_basic() {
        let json = r#"{"error":{"code":"ResourceGroupNotFound","message":"Resource group 'rg-test' not found."}}"#;
        let err = parse_azure_error(json).unwrap();
        assert_eq!(err.code, "ResourceGroupNotFound");
        assert!(err.message.contains("rg-test"));
    }

    #[test]
    fn test_parse_azure_error_with_details() {
        let json = r#"{"error":{"code":"Conflict","message":"conflict","details":[{"code":"LocationMismatch","message":"wrong region"}]}}"#;
        let err = parse_azure_error(json).unwrap();
        assert_eq!(err.details.len(), 1);
        assert_eq!(err.details[0].code, "LocationMismatch");
    }

    #[test]
    fn test_parse_azure_error_invalid_json() {
        assert!(parse_azure_error("not json").is_none());
        assert!(parse_azure_error("{}").is_none());
    }

    #[test]
    fn test_format_resource_group_not_found() {
        let err = AzureError {
            code: "ResourceGroupNotFound".to_string(),
            message: "not found".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("az group create"));
    }

    #[test]
    fn test_format_auth_failed() {
        let err = AzureError {
            code: "AuthorizationFailed".to_string(),
            message: "no permissions".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("az login"));
    }

    #[test]
    fn test_format_conflict_location() {
        let err = AzureError {
            code: "Conflict".to_string(),
            message: "Resource exists in different location".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("--location"));
    }

    #[test]
    fn test_format_quota_exceeded() {
        let err = AzureError {
            code: "OperationNotAllowed".to_string(),
            message: "Quota limit exceeded".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("quota"));
    }

    #[test]
    fn test_sanitize_password() {
        let cmd = "az vm create --admin-password MySecret123 --name test";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("MySecret123"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_connection_string() {
        let cmd = "az storage --connection-string DefaultEndpointsProtocol=https;AccountKey=secret";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("AccountKey=secret"));
    }

    #[test]
    fn test_sanitize_no_sensitive_data() {
        let cmd = "az vm list --resource-group rg-test";
        assert_eq!(sanitize_command_for_logging(cmd), cmd);
    }

    #[test]
    fn test_format_conflict_non_location() {
        let err = AzureError {
            code: "Conflict".to_string(),
            message: "Resource already exists".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("already exists"));
        assert!(msg.contains("different name"));
    }

    #[test]
    fn test_format_resource_conflict_code() {
        let err = AzureError {
            code: "ResourceConflict".to_string(),
            message: "naming conflict".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Resource conflict"));
        assert!(msg.contains("different name"));
    }

    #[test]
    fn test_format_conflict_region_message() {
        let err = AzureError {
            code: "Conflict".to_string(),
            message: "Resource exists in wrong region".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("--location"));
    }

    #[test]
    fn test_format_invalid_parameter_with_target() {
        let err = AzureError {
            code: "InvalidParameter".to_string(),
            message: "bad value".to_string(),
            target: Some("vmSize".to_string()),
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Invalid parameter"));
        assert!(msg.contains("vmSize"));
    }

    #[test]
    fn test_format_invalid_parameter_value_no_target() {
        let err = AzureError {
            code: "InvalidParameterValue".to_string(),
            message: "invalid sku".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Invalid parameter"));
        assert!(!msg.contains("Check the value of"));
    }

    #[test]
    fn test_format_subscription_not_found() {
        let err = AzureError {
            code: "SubscriptionNotFound".to_string(),
            message: "sub not found".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Subscription not found"));
        assert!(msg.contains("az account list"));
        assert!(msg.contains("azlin config set"));
    }

    #[test]
    fn test_format_unknown_error_code() {
        let err = AzureError {
            code: "SomeRandomCode".to_string(),
            message: "something went wrong".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("SomeRandomCode"));
        assert!(msg.contains("something went wrong"));
    }

    #[test]
    fn test_format_with_details() {
        let err = AzureError {
            code: "AuthorizationFailed".to_string(),
            message: "auth failed".to_string(),
            target: None,
            details: vec![
                AzureError {
                    code: "RoleAssignment".to_string(),
                    message: "missing role".to_string(),
                    target: None,
                    details: vec![],
                },
                AzureError {
                    code: "PolicyViolation".to_string(),
                    message: "blocked by policy".to_string(),
                    target: None,
                    details: vec![],
                },
            ],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Details:"));
        assert!(msg.contains("[RoleAssignment] missing role"));
        assert!(msg.contains("[PolicyViolation] blocked by policy"));
    }

    #[test]
    fn test_format_operation_not_allowed_no_quota() {
        let err = AzureError {
            code: "OperationNotAllowed".to_string(),
            message: "VM size not available".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Operation not allowed"));
        assert!(!msg.contains("quota"));
    }

    #[test]
    fn test_parse_azure_error_with_target() {
        let json = r#"{"error":{"code":"InvalidParameter","message":"bad param","target":"vmSize"}}"#;
        let err = parse_azure_error(json).unwrap();
        assert_eq!(err.code, "InvalidParameter");
        assert_eq!(err.target, Some("vmSize".to_string()));
    }

    #[test]
    fn test_parse_azure_error_details_with_target() {
        let json = r#"{"error":{"code":"Conflict","message":"conflict","details":[{"code":"Sub","message":"detail msg","target":"field1"}]}}"#;
        let err = parse_azure_error(json).unwrap();
        assert_eq!(err.details.len(), 1);
        assert_eq!(err.details[0].target, Some("field1".to_string()));
    }

    #[test]
    fn test_sanitize_storage_account_key() {
        let cmd = "az storage account --storage-account-key MyKey123 --name test";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("MyKey123"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_sas_token() {
        let cmd = "az storage blob --sas-token sv=2021&sig=secret --name blob1";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("sv=2021"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_client_secret() {
        let cmd = "az ad sp --client-secret SuperSecret123";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("SuperSecret123"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_multiple_sensitive_params() {
        let cmd = "az vm create --admin-password Pass1 --client-secret Secret2 --name vm1";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("Pass1"));
        assert!(!sanitized.contains("Secret2"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_parse_azure_error_missing_code() {
        let json = r#"{"error":{"message":"only message"}}"#;
        assert!(parse_azure_error(json).is_none());
    }

    #[test]
    fn test_parse_azure_error_missing_message() {
        let json = r#"{"error":{"code":"SomeCode"}}"#;
        assert!(parse_azure_error(json).is_none());
    }

    #[test]
    fn test_parse_azure_error_empty_details() {
        let json = r#"{"error":{"code":"Test","message":"msg","details":[]}}"#;
        let err = parse_azure_error(json).unwrap();
        assert!(err.details.is_empty());
    }

    #[test]
    fn test_format_quota_with_capital_q() {
        let err = AzureError {
            code: "OperationNotAllowed".to_string(),
            message: "Quota exceeded for region".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("quota limit"));
    }
}
