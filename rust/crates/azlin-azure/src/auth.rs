use anyhow::{Context, Result};
use azure_core::credentials::TokenCredential;
use azure_identity::DefaultAzureCredential;
use std::process::Command;
use std::sync::Arc;
use tracing::debug;
use wait_timeout::ChildExt;

/// Handles Azure authentication via DefaultAzureCredential chain.
///
/// Mirrors the Python `AzureAuthenticator` / `CredentialFactory`:
///   1. AzureCliCredential (most common for dev)
///   2. ManagedIdentityCredential
///   3. Environment / workload credentials
///
/// `DefaultAzureCredential` from the `azure_identity` crate walks through
/// these sources automatically, so we delegate to it.
pub struct AzureAuth {
    credential: Arc<dyn TokenCredential>,
    subscription_id: String,
    tenant_id: Option<String>,
}

impl AzureAuth {
    /// Create a new `AzureAuth` using `DefaultAzureCredential`.
    ///
    /// The subscription ID is read from `az account show`.
    pub fn new() -> Result<Self> {
        let credential =
            DefaultAzureCredential::new().context("Failed to create DefaultAzureCredential")?;

        let (subscription_id, tenant_id) = Self::read_account_info()?;

        Ok(Self {
            credential,
            subscription_id,
            tenant_id: Some(tenant_id),
        })
    }

    /// Create a new `AzureAuth` with an explicit subscription ID.
    pub fn new_with_subscription(subscription_id: &str) -> Result<Self> {
        let credential =
            DefaultAzureCredential::new().context("Failed to create DefaultAzureCredential")?;

        Ok(Self {
            credential,
            subscription_id: subscription_id.to_string(),
            tenant_id: None,
        })
    }

    /// Return the subscription ID.
    pub fn subscription_id(&self) -> &str {
        &self.subscription_id
    }

    /// Return a reference to the underlying credential for SDK calls.
    pub fn credential(&self) -> &dyn TokenCredential {
        self.credential.as_ref()
    }

    /// Return the credential wrapped in an `Arc` (useful for SDK clients).
    pub fn credential_arc(&self) -> Arc<dyn TokenCredential> {
        Arc::clone(&self.credential)
    }

    /// Return the tenant ID, if known.
    pub fn tenant_id(&self) -> Option<&str> {
        self.tenant_id.as_deref()
    }

    /// Read subscription and tenant from `az account show`.
    ///
    /// Includes a 120-second timeout to prevent hangs on unresponsive
    /// Azure CLI (e.g. network issues, auth prompts on Windows/WSL).
    fn read_account_info() -> Result<(String, String)> {
        let mut child = Command::new("az")
            .args(["account", "show", "--output", "json"])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .context("Failed to run `az account show` — is Azure CLI installed?")?;

        let timeout = std::time::Duration::from_secs(120);
        let status = match child.wait_timeout(timeout) {
            Ok(Some(s)) => s,
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                anyhow::bail!("`az account show` timed out after 120s");
            }
            Err(e) => anyhow::bail!("Failed to wait for `az account show`: {e}"),
        };

        let stdout = child
            .stdout
            .take()
            .map(|mut s| {
                let mut buf = Vec::new();
                std::io::Read::read_to_end(&mut s, &mut buf).ok();
                buf
            })
            .unwrap_or_default();
        let stderr = child
            .stderr
            .take()
            .map(|mut s| {
                let mut buf = Vec::new();
                std::io::Read::read_to_end(&mut s, &mut buf).ok();
                buf
            })
            .unwrap_or_default();

        if !status.success() {
            let stderr_str = String::from_utf8_lossy(&stderr);
            anyhow::bail!(
                "`az account show` failed (exit {}): {}",
                status,
                azlin_core::sanitizer::sanitize(stderr_str.trim())
            );
        }

        let account: serde_json::Value = serde_json::from_slice(&stdout)
            .context("Failed to parse `az account show` JSON output")?;

        let subscription_id = account["id"]
            .as_str()
            .context("Missing 'id' in az account show output")?
            .to_string();

        let tenant_id = account["tenantId"]
            .as_str()
            .context("Missing 'tenantId' in az account show output")?
            .to_string();

        debug!(subscription_id = %subscription_id, "Read subscription from az CLI");

        Ok((subscription_id, tenant_id))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_with_subscription_compiles() {
        // DefaultAzureCredential may fail without Azure CLI login,
        // so we just verify the code path compiles and returns an error
        // rather than panicking.
        let result = AzureAuth::new_with_subscription("00000000-0000-0000-0000-000000000000");
        // In CI without Azure login this will be Err; that's fine.
        match result {
            Ok(auth) => {
                assert_eq!(
                    auth.subscription_id(),
                    "00000000-0000-0000-0000-000000000000"
                );
                assert!(auth.tenant_id().is_none());
            }
            Err(e) => {
                // Expected in environments without Azure CLI login
                let msg = format!("{e}");
                assert!(
                    msg.contains("Credential")
                        || msg.contains("credential")
                        || msg.contains("Azure"),
                    "Unexpected error: {msg}"
                );
            }
        }
    }

    #[test]
    fn test_subscription_id_accessor() {
        // If credential creation succeeds, verify accessor works.
        if let Ok(auth) = AzureAuth::new_with_subscription("test-sub-id") {
            assert_eq!(auth.subscription_id(), "test-sub-id");
        }
    }

    #[test]
    fn test_credential_accessor() {
        // Verify credential() returns a trait object (compilation check).
        if let Ok(auth) = AzureAuth::new_with_subscription("test-sub-id") {
            let _cred: &dyn TokenCredential = auth.credential();
            let _arc: Arc<dyn TokenCredential> = auth.credential_arc();
        }
    }

    #[test]
    fn test_new_without_cli_does_not_panic() {
        // AzureAuth::new() depends on `az account show`; it should return
        // Ok or Err — never panic.
        let result = AzureAuth::new();
        // Verify it returns a meaningful result either way
        match result {
            Ok(auth) => {
                assert!(
                    !auth.subscription_id().is_empty(),
                    "subscription_id should not be empty on success"
                );
            }
            Err(e) => {
                let msg = e.to_string();
                assert!(
                    msg.contains("az") || msg.contains("account") || msg.contains("timed out"),
                    "error should mention az CLI: {msg}"
                );
            }
        }
    }

    // ── Subscription ID parsing tests ───────────────────────────────

    #[test]
    fn test_read_account_info_produces_result() {
        // read_account_info runs `az account show`; it either succeeds or
        // returns an error with a descriptive message. It should never panic.
        let result = AzureAuth::read_account_info();
        match result {
            Ok((sub, tenant)) => {
                assert!(!sub.is_empty(), "subscription ID should not be empty");
                assert!(!tenant.is_empty(), "tenant ID should not be empty");
            }
            Err(e) => {
                let msg = e.to_string();
                assert!(
                    msg.contains("az")
                        || msg.contains("account")
                        || msg.contains("CLI")
                        || msg.contains("parse")
                        || msg.contains("failed")
                        || msg.contains("Missing"),
                    "error should be descriptive: {msg}"
                );
            }
        }
    }

    #[test]
    fn test_subscription_id_parsing_from_json() {
        // Simulate the JSON parsing logic from read_account_info
        let json_str = r#"{"id": "12345678-1234-1234-1234-123456789abc", "tenantId": "abcdef00-0000-0000-0000-000000000001"}"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        let sub = account["id"].as_str().unwrap();
        let tenant = account["tenantId"].as_str().unwrap();
        assert_eq!(sub, "12345678-1234-1234-1234-123456789abc");
        assert_eq!(tenant, "abcdef00-0000-0000-0000-000000000001");
    }

    #[test]
    fn test_subscription_id_parsing_missing_id() {
        let json_str = r#"{"tenantId": "abcdef00-0000-0000-0000-000000000001"}"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        assert!(account["id"].as_str().is_none());
    }

    #[test]
    fn test_subscription_id_parsing_missing_tenant() {
        let json_str = r#"{"id": "12345678-1234-1234-1234-123456789abc"}"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        assert!(account["tenantId"].as_str().is_none());
    }

    #[test]
    fn test_tenant_id_accessor_returns_none_for_explicit_sub() {
        if let Ok(auth) = AzureAuth::new_with_subscription("test-sub") {
            assert!(
                auth.tenant_id().is_none(),
                "new_with_subscription should have no tenant_id"
            );
        }
    }

    #[test]
    fn test_new_with_various_subscription_ids() {
        let ids = vec![
            "00000000-0000-0000-0000-000000000000",
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "test-sub-id",
            "",
        ];
        for id in ids {
            let result = AzureAuth::new_with_subscription(id);
            if let Ok(auth) = result {
                assert_eq!(auth.subscription_id(), id);
            } // Azure credential may not be available
        }
    }

    #[test]
    fn test_credential_arc_returns_clone() {
        if let Ok(auth) = AzureAuth::new_with_subscription("test-sub") {
            let arc1 = auth.credential_arc();
            let arc2 = auth.credential_arc();
            // Both should be valid Arc pointers
            assert!(std::sync::Arc::strong_count(&arc1) >= 2);
            drop(arc2);
            assert!(std::sync::Arc::strong_count(&arc1) >= 1);
        }
    }

    // ── JSON parsing edge cases ─────────────────────────────────────

    #[test]
    fn test_account_json_parsing_extra_fields() {
        let json_str = r#"{
            "id": "sub-123",
            "tenantId": "tenant-456",
            "name": "My Subscription",
            "state": "Enabled",
            "user": {"name": "user@example.com"}
        }"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        assert_eq!(account["id"].as_str().unwrap(), "sub-123");
        assert_eq!(account["tenantId"].as_str().unwrap(), "tenant-456");
    }

    #[test]
    fn test_account_json_parsing_null_values() {
        let json_str = r#"{"id": null, "tenantId": "tenant-456"}"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        assert!(account["id"].as_str().is_none());
    }

    #[test]
    fn test_account_json_parsing_empty_strings() {
        let json_str = r#"{"id": "", "tenantId": ""}"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        assert_eq!(account["id"].as_str().unwrap(), "");
        assert_eq!(account["tenantId"].as_str().unwrap(), "");
    }

    #[test]
    fn test_account_json_parsing_uuid_format() {
        let json_str = r#"{
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "tenantId": "12345678-abcd-efgh-ijkl-123456789012"
        }"#;
        let account: serde_json::Value = serde_json::from_str(json_str).unwrap();
        let sub = account["id"].as_str().unwrap();
        assert!(sub.contains('-'));
        assert_eq!(sub.len(), 36);
    }

    #[test]
    fn test_new_with_subscription_empty_string() {
        let result = AzureAuth::new_with_subscription("");
        if let Ok(auth) = result {
            assert_eq!(auth.subscription_id(), "");
        } // Azure credential may not be available
    }
}
