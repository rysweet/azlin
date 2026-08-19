use anyhow::{Context, Result};
use tracing::debug;

/// Handles Azure authentication by reading subscription and tenant info
/// from `az account show`. All VM operations use the `az` CLI directly,
/// so no SDK credential object is needed.
pub struct AzureAuth {
    subscription_id: String,
    tenant_id: Option<String>,
}

impl AzureAuth {
    /// Create a new `AzureAuth` by reading subscription info from `az account show`.
    pub fn new() -> Result<Self> {
        let (subscription_id, tenant_id) = Self::read_account_info()?;

        Ok(Self {
            subscription_id,
            tenant_id: Some(tenant_id),
        })
    }

    /// Create a new `AzureAuth` with an explicit subscription ID.
    ///
    /// This *asserts* a subscription without checking it against the CLI. Use
    /// [`AzureAuth::for_subscription`] when the value came from user state
    /// (an azlin context) and commands will act on it.
    pub fn new_with_subscription(subscription_id: &str) -> Result<Self> {
        Ok(Self {
            subscription_id: subscription_id.to_string(),
            tenant_id: None,
        })
    }

    /// Point the Azure CLI at `subscription_id` and confirm it took effect.
    ///
    /// azlin runs every Azure operation by shelling out to `az`, and `az`
    /// resolves the subscription from its own profile unless each invocation
    /// passes `--subscription`. There are ~350 such invocations, so the
    /// tractable place to apply an azlin context is the CLI's active
    /// subscription itself.
    ///
    /// The switch is therefore `az account set --subscription <id>` — but it is
    /// never *assumed* to have worked. `az account show` is read back
    /// afterwards and a still-mismatched subscription is a hard error. That is
    /// the whole point of #1090: the previous code asserted a switch it never
    /// performed, and `destroy` ran in the wrong subscription while the user
    /// held a confirmation that it would not.
    pub fn for_subscription(subscription_id: &str) -> Result<Self> {
        let subscription_id = subscription_id.trim();
        if subscription_id.is_empty() {
            anyhow::bail!("Refusing to switch to an empty subscription id");
        }

        let (current, tenant) = Self::read_account_info()?;
        if current == subscription_id {
            return Ok(Self {
                subscription_id: current,
                tenant_id: Some(tenant),
            });
        }

        debug!(
            from = %current,
            to = %subscription_id,
            "Switching az CLI subscription for the active azlin context"
        );
        Self::set_cli_subscription(subscription_id)?;

        let (effective, tenant) = Self::read_account_info()?;
        if effective != subscription_id {
            anyhow::bail!(
                "Refusing to run: asked the Azure CLI to use subscription {subscription_id} \
                 but `az account show` still reports {effective}.\n\
                 Commands would act on the wrong subscription. Check \
                 `az account list --output table` and that you are logged in to the \
                 tenant owning {subscription_id}."
            );
        }
        Ok(Self {
            subscription_id: effective,
            tenant_id: Some(tenant),
        })
    }

    /// Run `az account set --subscription <id>`.
    fn set_cli_subscription(subscription_id: &str) -> Result<()> {
        let (code, _stdout, stderr) = crate::subprocess::run_with_timeout(
            "az",
            &["account", "set", "--subscription", subscription_id],
            120,
        )
        .context("Failed to run `az account set` — is Azure CLI installed?")?;

        if code != 0 {
            anyhow::bail!(
                "`az account set --subscription {subscription_id}` failed (exit {code}): {}",
                azlin_core::sanitizer::sanitize(stderr.trim())
            );
        }
        Ok(())
    }

    /// Read the subscription and tenant the Azure CLI is *currently* on.
    ///
    /// Exposed so `azlin context show` can display the effective subscription
    /// rather than assuming the context's value is in force.
    pub fn effective_account() -> Result<(String, String)> {
        Self::read_account_info()
    }

    /// Return the subscription ID.
    pub fn subscription_id(&self) -> &str {
        &self.subscription_id
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
        let (code, stdout, stderr) = crate::subprocess::run_with_timeout(
            "az",
            &["account", "show", "--output", "json"],
            120,
        )
        .context("Failed to run `az account show` — is Azure CLI installed?")?;

        if code != 0 {
            anyhow::bail!(
                "`az account show` failed (exit {}): {}",
                code,
                azlin_core::sanitizer::sanitize(stderr.trim())
            );
        }

        let account: serde_json::Value = serde_json::from_str(&stdout)
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
    fn test_new_with_subscription() {
        let auth = AzureAuth::new_with_subscription("00000000-0000-0000-0000-000000000000")
            .expect("new_with_subscription should not fail");
        assert_eq!(
            auth.subscription_id(),
            "00000000-0000-0000-0000-000000000000"
        );
        assert!(auth.tenant_id().is_none());
    }

    #[test]
    fn test_for_subscription_rejects_empty_id() {
        // Guard rail before any subprocess runs: an empty/blank subscription
        // must never reach `az account set`.
        for id in ["", "   ", "\n"] {
            let err = match AzureAuth::for_subscription(id) {
                Ok(_) => panic!("blank subscription id {id:?} must be refused"),
                Err(e) => e.to_string(),
            };
            assert!(
                err.contains("empty subscription"),
                "expected empty-subscription refusal, got: {err}"
            );
        }
    }

    #[test]
    fn test_subscription_id_accessor() {
        let auth = AzureAuth::new_with_subscription("test-sub-id").expect("should not fail");
        assert_eq!(auth.subscription_id(), "test-sub-id");
    }

    #[test]
    fn test_new_without_cli_does_not_panic() {
        // AzureAuth::new() depends on `az account show`; it should return
        // Ok or Err — never panic.
        let result = AzureAuth::new();
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

    #[test]
    fn test_read_account_info_produces_result() {
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
        let auth = AzureAuth::new_with_subscription("test-sub").expect("should not fail");
        assert!(
            auth.tenant_id().is_none(),
            "new_with_subscription should have no tenant_id"
        );
    }

    #[test]
    fn test_new_with_various_subscription_ids() {
        for id in ["00000000-0000-0000-0000-000000000000", "test-sub-id", ""] {
            let auth = AzureAuth::new_with_subscription(id).expect("should not fail");
            assert_eq!(auth.subscription_id(), id);
        }
    }

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
}
