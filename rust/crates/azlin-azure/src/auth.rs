use anyhow::{Context, Result};
use azure_core::credentials::TokenCredential;
use azure_identity::DefaultAzureCredential;
use std::process::Command;
use std::sync::Arc;
use tracing::debug;

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
    fn read_account_info() -> Result<(String, String)> {
        let output = Command::new("az")
            .args(["account", "show", "--output", "json"])
            .output()
            .context("Failed to run `az account show` — is Azure CLI installed?")?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!(
                "`az account show` failed (exit {}): {}",
                output.status,
                stderr.trim()
            );
        }

        let account: serde_json::Value = serde_json::from_slice(&output.stdout)
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
        // Err rather than panic when CLI is unavailable.
        let _result = AzureAuth::new();
    }
}
