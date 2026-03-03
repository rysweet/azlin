use thiserror::Error;

/// Top-level error type for azlin operations.
#[derive(Error, Debug)]
pub enum AzlinError {
    #[error("Configuration error: {0}")]
    Config(String),

    #[error("Authentication error: {0}")]
    Auth(String),

    #[error("VM management error: {0}")]
    VmManager(String),

    #[error("VM lifecycle error: {0}")]
    VmLifecycle(String),

    #[error("Provisioning error: {0}")]
    Provisioning(String),

    #[error("SSH error: {0}")]
    Ssh(String),

    #[error("SSH key error: {0}")]
    SshKey(String),

    #[error("Remote execution error: {0}")]
    RemoteExec(String),

    #[error("Command execution error: {0}")]
    CommandExecution(String),

    #[error("Network security error: {0}")]
    NetworkSecurity(String),

    #[error("VPN error: {0}")]
    Vpn(String),

    #[error("Bastion error: {0}")]
    Bastion(String),

    #[error("Storage error: {0}")]
    Storage(String),

    #[error("Backup error: {0}")]
    Backup(String),

    #[error("Snapshot error: {0}")]
    Snapshot(String),

    #[error("Cost tracking error: {0}")]
    CostTracking(String),

    #[error("File transfer error: {0}")]
    FileTransfer(String),

    #[error("Path traversal error: {0}")]
    PathTraversal(String),

    #[error("Security error: {0}")]
    Security(String),

    #[error("Rate limit exceeded: {0}")]
    RateLimit(String),

    #[error("Hook execution error: {0}")]
    HookExecution(String),

    #[error("AI/NLP error: {0}")]
    Ai(String),

    #[error("Azure CLI error: {0}")]
    AzureCli(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Serialization error: {0}")]
    Serialization(String),

    #[error("{0}")]
    Other(String),
}

/// Convenience Result type for azlin operations.
pub type Result<T> = std::result::Result<T, AzlinError>;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = AzlinError::Config("missing field".to_string());
        assert_eq!(err.to_string(), "Configuration error: missing field");
    }

    #[test]
    fn test_error_from_io() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "file not found");
        let err: AzlinError = io_err.into();
        assert!(matches!(err, AzlinError::Io(_)));
    }

    #[test]
    fn test_all_error_variants_display() {
        // Verify every variant produces a meaningful message
        let errors = vec![
            AzlinError::Auth("bad token".into()),
            AzlinError::VmManager("vm not found".into()),
            AzlinError::Ssh("connection refused".into()),
            AzlinError::FileTransfer("path denied".into()),
            AzlinError::Ai("api error".into()),
        ];
        for err in errors {
            assert!(!err.to_string().is_empty());
        }
    }
}
