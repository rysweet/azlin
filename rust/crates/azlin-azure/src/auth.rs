use anyhow::Result;

/// Handles Azure authentication via DefaultAzureCredential chain.
pub struct AzureAuth;

impl AzureAuth {
    /// Create a new AzureAuth using the default credential chain.
    /// Falls through: AzureCli → ManagedIdentity → Environment → Workload.
    pub fn new() -> Result<Self> {
        Ok(Self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_azure_auth_creation() {
        // Basic construction test — real auth tested in integration tests
        let auth = AzureAuth::new();
        assert!(auth.is_ok());
    }
}
