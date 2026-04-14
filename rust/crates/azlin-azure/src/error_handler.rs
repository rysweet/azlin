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
        target: error
            .get("target")
            .and_then(|t| t.as_str())
            .map(|s| s.to_string()),
        details: error
            .get("details")
            .and_then(|d| d.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|d| {
                        Some(AzureError {
                            code: d.get("code")?.as_str()?.to_string(),
                            message: d.get("message")?.as_str()?.to_string(),
                            target: d
                                .get("target")
                                .and_then(|t| t.as_str())
                                .map(|s| s.to_string()),
                            details: vec![],
                        })
                    })
                    .collect()
            })
            .unwrap_or_default(),
    })
}

/// Format Azure error into user-friendly message with actionable suggestions
pub fn format_user_friendly_error(error: &AzureError) -> String {
    let mut msg = String::new();

    // Check for quota errors in details first (e.g. InvalidTemplateDeployment wrapping QuotaExceeded)
    if let Some(quota_detail) = error
        .details
        .iter()
        .find(|d| d.code == "QuotaExceeded" || d.code == "QuotaExceededError")
    {
        return format_quota_error_from_message(&quota_detail.message);
    }

    match error.code.as_str() {
        "QuotaExceeded" | "QuotaExceededError" => {
            return format_quota_error_from_message(&error.message);
        }
        "InvalidTemplateDeployment" => {
            msg.push_str("❌ Azure deployment validation failed.\n");
            if !error.details.is_empty() {
                for detail in &error.details {
                    msg.push_str(&format!(
                        "\n{}",
                        format_user_friendly_error(detail)
                    ));
                }
            } else {
                msg.push_str(&format!("   {}\n", error.message));
            }
            return msg;
        }
        "ResourceGroupNotFound" => {
            msg.push_str(&format!("❌ Resource group not found: {}\n", error.message));
            msg.push_str(
                "💡 Create it with: az group create --name <name> --location <location>\n",
            );
        }
        "AuthorizationFailed" => {
            msg.push_str(&format!("🔒 Authorization failed: {}\n", error.message));
            msg.push_str("💡 Check your Azure RBAC permissions or run: az login\n");
        }
        "Conflict" | "ResourceConflict" => {
            msg.push_str(&format!("⚠️ Resource conflict: {}\n", error.message));
            if error.message.contains("location") || error.message.contains("region") {
                msg.push_str(
                    "💡 The resource exists in a different region. Use --location to match.\n",
                );
            } else {
                msg.push_str(
                    "💡 A resource with this name already exists. Use a different name.\n",
                );
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
            msg.push_str(&format!(
                "❌ Azure error [{}]: {}\n",
                error.code, error.message
            ));
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

/// Format a quota exceeded error message with parsed limits and actionable suggestions.
fn format_quota_error_from_message(message: &str) -> String {
    let mut msg = String::new();
    msg.push_str("❌ Quota exceeded: not enough vCPU cores available.\n");

    // Extract quota details from the message
    let location = extract_field(message, "Location: ");
    let current_limit = extract_field(message, "Current Limit: ");
    let current_usage = extract_field(message, "Current Usage: ");
    let additional_required = extract_field(message, "Additional Required: ");
    let new_limit_required = extract_field(message, "(Minimum) New Limit Required: ");

    if current_limit.is_some() || current_usage.is_some() {
        msg.push('\n');
        if let Some(loc) = &location {
            msg.push_str(&format!("   Region:     {}\n", loc));
        }
        if let Some(limit) = &current_limit {
            msg.push_str(&format!("   Limit:      {} cores\n", limit));
        }
        if let Some(usage) = &current_usage {
            msg.push_str(&format!("   In use:     {} cores\n", usage));
        }
        if let Some(required) = &additional_required {
            msg.push_str(&format!("   Requested:  {} cores\n", required));
        }
        if let (Some(usage), Some(limit)) = (&current_usage, &current_limit) {
            if let (Ok(u), Ok(l)) = (usage.parse::<u64>(), limit.parse::<u64>()) {
                msg.push_str(&format!("   Available:  {} cores\n", l.saturating_sub(u)));
            }
        }
        if let Some(new_limit) = &new_limit_required {
            msg.push_str(&format!("   Need limit: {} cores\n", new_limit));
        }
    }

    msg.push_str("\n💡 Options:\n");
    msg.push_str("   • Use a smaller VM size (--size s or --size m)\n");
    msg.push_str("   • Try a different region (--region eastus2)\n");
    msg.push_str("   • Delete unused VMs to free cores (azlin list, azlin delete <name>)\n");
    msg.push_str(
        "   • Request a quota increase: https://aka.ms/ProdportalCRP\n",
    );

    msg
}

/// Extract a field value from an Azure error message like "Current Limit: 100, Current Usage: 88".
fn extract_field(message: &str, prefix: &str) -> Option<String> {
    let idx = message.find(prefix)?;
    let start = idx + prefix.len();
    let rest = &message[start..];
    // Value ends at comma, period, or end of string
    let end = rest
        .find([',', '.', '\n'])
        .unwrap_or(rest.len());
    let value = rest[..end].trim();
    if value.is_empty() {
        None
    } else {
        Some(value.to_string())
    }
}

/// Parse structured Azure error information from raw `az` CLI stderr output.
///
/// The `az` CLI sometimes crashes while formatting errors (e.g., the
/// `InvalidTemplateDeployment` → `QuotaExceeded` chain triggers an internal
/// `AttributeError` in the CLI's error handler). When this happens, the actual
/// error details are still present in the stderr traceback text. This function
/// extracts them.
pub fn parse_azure_error_from_stderr(stderr: &str) -> Option<AzureError> {
    // Look for parenthesized error codes like "(QuotaExceeded) message..."
    // These appear in az CLI stderr even when the JSON parsing fails internally.
    let mut top_code = None;
    let mut top_message = None;
    let mut details = Vec::new();

    for line in stderr.lines() {
        let trimmed = line.trim();

        // Match lines like "(ErrorCode) Error message text"
        // or "Code: ErrorCode"
        if let Some(parsed) = parse_parenthesized_error(trimmed) {
            if top_code.is_none() {
                top_code = Some(parsed.0.clone());
                top_message = Some(parsed.1.clone());
            }
            // Collect known detail codes separately
            if parsed.0 == "QuotaExceeded"
                || parsed.0 == "QuotaExceededError"
                || parsed.0 == "SkuNotAvailable"
                || parsed.0 == "OverconstrainedAllocationRequest"
            {
                details.push(AzureError {
                    code: parsed.0,
                    message: parsed.1,
                    target: None,
                    details: vec![],
                });
            }
        }
    }

    let code = top_code?;
    let message = top_message.unwrap_or_default();

    Some(AzureError {
        code,
        message,
        target: None,
        details,
    })
}

/// Parse a line like "(ErrorCode) Error message text" into (code, message).
fn parse_parenthesized_error(line: &str) -> Option<(String, String)> {
    // Skip Python traceback lines and noise
    if line.starts_with("File ")
        || line.starts_with("Traceback ")
        || line.starts_with("During handling")
        || line.contains("site-packages/")
    {
        return None;
    }

    // Strip common prefixes like "ERROR: " or "Message: "
    let stripped = line
        .strip_prefix("ERROR: ")
        .or_else(|| line.strip_prefix("Exception Details:"))
        .unwrap_or(line)
        .trim();

    if stripped.starts_with('(') {
        let close = stripped.find(')')?;
        let code = &stripped[1..close];
        // Sanity: codes are PascalCase identifiers, no spaces
        if code.contains(' ') || code.is_empty() {
            return None;
        }
        let message = stripped[close + 1..].trim().to_string();
        Some((code.to_string(), message))
    } else {
        None
    }
}

/// Sanitize sensitive data from Azure CLI command strings for logging.
///
/// Handles both `--param value` and `--param=value` forms, as well as
/// quoted values (`--param "value with spaces"`).
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
        let mut search_from = 0;
        while let Some(rel_idx) = sanitized[search_from..].find(param) {
            let idx = search_from + rel_idx;
            let param_end = idx + param.len();
            let rest = &sanitized[param_end..];

            if rest.starts_with('=') {
                // --param=value form
                let value_start = param_end + 1; // skip '='
                let value_end = find_value_end(&sanitized, value_start);
                sanitized.replace_range(param_end..value_end, "=***REDACTED***");
                search_from = param_end + "=***REDACTED***".len();
            } else if rest.starts_with(' ') || rest.starts_with('\t') {
                // --param value form
                let value_start = param_end
                    + rest
                        .find(|c: char| !c.is_whitespace())
                        .unwrap_or(rest.len());
                let value_end = find_value_end(&sanitized, value_start);
                sanitized.replace_range(param_end..value_end, " ***REDACTED***");
                search_from = param_end + " ***REDACTED***".len();
            } else {
                // param is a prefix of a longer param name, skip past it
                search_from = param_end;
            }
        }
    }
    sanitized
}

/// Find the end of a value, handling quoted strings.
fn find_value_end(s: &str, start: usize) -> usize {
    let rest = &s[start..];
    if rest.is_empty() {
        return start;
    }

    let first = rest.as_bytes()[0];
    if first == b'"' || first == b'\'' {
        // Quoted value: find matching close quote
        let quote = first as char;
        if let Some(end_quote) = rest[1..].find(quote) {
            return start + end_quote + 2; // include both quotes
        }
    }

    // Unquoted: find next whitespace
    match rest.find(|c: char| c.is_whitespace()) {
        Some(space_idx) => start + space_idx,
        None => s.len(),
    }
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
        let json =
            r#"{"error":{"code":"InvalidParameter","message":"bad param","target":"vmSize"}}"#;
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
    fn test_sanitize_equals_form() {
        let cmd = "az vm create --admin-password=MySecret123 --name test";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("MySecret123"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_quoted_value() {
        let cmd = r#"az vm create --admin-password "My Secret 123" --name test"#;
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("My Secret 123"));
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_value_at_end_of_string() {
        let cmd = "az ad sp --client-secret FinalValue";
        let sanitized = sanitize_command_for_logging(cmd);
        assert!(!sanitized.contains("FinalValue"));
        assert!(sanitized.contains("REDACTED"));
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

    #[test]
    fn test_format_quota_exceeded_code_directly() {
        let err = AzureError {
            code: "QuotaExceeded".to_string(),
            message: "Operation could not be completed as it results in exceeding approved Total Regional Cores quota. Additional details - Deployment Model: Resource Manager, Location: westus, Current Limit: 100, Current Usage: 88, Additional Required: 64, (Minimum) New Limit Required: 152.".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Quota exceeded"));
        assert!(msg.contains("100 cores"));
        assert!(msg.contains("88 cores"));
        assert!(msg.contains("64 cores"));
        assert!(msg.contains("12 cores")); // available = 100 - 88
        assert!(msg.contains("westus"));
        assert!(msg.contains("smaller VM size"));
    }

    #[test]
    fn test_format_invalid_template_with_quota_detail() {
        let err = AzureError {
            code: "InvalidTemplateDeployment".to_string(),
            message: "The template deployment is not valid".to_string(),
            target: None,
            details: vec![AzureError {
                code: "QuotaExceeded".to_string(),
                message: "Operation could not be completed as it results in exceeding approved Total Regional Cores quota. Additional details - Deployment Model: Resource Manager, Location: westus, Current Limit: 100, Current Usage: 88, Additional Required: 64, (Minimum) New Limit Required: 152.".to_string(),
                target: None,
                details: vec![],
            }],
        };
        let msg = format_user_friendly_error(&err);
        // Should surface the quota error directly, not the template wrapper
        assert!(msg.contains("Quota exceeded"));
        assert!(msg.contains("100 cores"));
        assert!(msg.contains("smaller VM size"));
    }

    #[test]
    fn test_parse_azure_error_from_stderr_quota() {
        let stderr = r#"WARNING: The default value of '--size' will be changed to 'Standard_D2s_v5'
ERROR: The command failed with an unexpected error.
(InvalidTemplateDeployment) The template deployment 'vm_deploy_xxx' is not valid.
Code: InvalidTemplateDeployment
Message: The template deployment is not valid.
Exception Details:      (QuotaExceeded) Operation could not be completed as it results in exceeding approved Total Regional Cores quota. Additional details - Deployment Model: Resource Manager, Location: westus, Current Limit: 100, Current Usage: 88, Additional Required: 64, (Minimum) New Limit Required: 152.
        Code: QuotaExceeded
        Message: Operation could not be completed
Traceback (most recent call last):
  File "/opt/az/lib/python3.13/site-packages/azure/cli/core/commands/__init__.py", line 706
    result = cmd_copy(params)
RuntimeError: The content for this response was already consumed"#;

        let err = parse_azure_error_from_stderr(stderr).unwrap();
        assert_eq!(err.code, "InvalidTemplateDeployment");
        assert!(!err.details.is_empty());
        assert_eq!(err.details[0].code, "QuotaExceeded");

        // Format should produce clean output
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("Quota exceeded"));
        assert!(msg.contains("westus"));
        assert!(msg.contains("100 cores"));
    }

    #[test]
    fn test_parse_azure_error_from_stderr_no_errors() {
        let stderr = "WARNING: some random warning\nnothing useful here";
        assert!(parse_azure_error_from_stderr(stderr).is_none());
    }

    #[test]
    fn test_parse_azure_error_from_stderr_skips_traceback() {
        let stderr = r#"Traceback (most recent call last):
  File "/opt/az/lib/python3.13/site-packages/azure/cli/core/commands/__init__.py", line 706
During handling of the above exception, another exception occurred:
(AuthorizationFailed) The client does not have authorization"#;

        let err = parse_azure_error_from_stderr(stderr).unwrap();
        assert_eq!(err.code, "AuthorizationFailed");
    }

    #[test]
    fn test_extract_field_basic() {
        let msg = "Location: westus, Current Limit: 100, Current Usage: 88";
        assert_eq!(extract_field(msg, "Location: "), Some("westus".to_string()));
        assert_eq!(
            extract_field(msg, "Current Limit: "),
            Some("100".to_string())
        );
        assert_eq!(
            extract_field(msg, "Current Usage: "),
            Some("88".to_string())
        );
    }

    #[test]
    fn test_extract_field_missing() {
        let msg = "Location: westus";
        assert_eq!(extract_field(msg, "Current Limit: "), None);
    }

    #[test]
    fn test_format_invalid_template_no_details() {
        let err = AzureError {
            code: "InvalidTemplateDeployment".to_string(),
            message: "The template deployment is not valid".to_string(),
            target: None,
            details: vec![],
        };
        let msg = format_user_friendly_error(&err);
        assert!(msg.contains("deployment validation failed"));
        assert!(msg.contains("not valid"));
    }
}
