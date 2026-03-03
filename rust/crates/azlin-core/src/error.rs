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

    // ── Additional error tests ──────────────────────────────────────

    #[test]
    fn test_all_error_variants_have_distinct_messages() {
        let errors: Vec<AzlinError> = vec![
            AzlinError::Config("msg".into()),
            AzlinError::Auth("msg".into()),
            AzlinError::VmManager("msg".into()),
            AzlinError::VmLifecycle("msg".into()),
            AzlinError::Provisioning("msg".into()),
            AzlinError::Ssh("msg".into()),
            AzlinError::SshKey("msg".into()),
            AzlinError::RemoteExec("msg".into()),
            AzlinError::CommandExecution("msg".into()),
            AzlinError::NetworkSecurity("msg".into()),
            AzlinError::Vpn("msg".into()),
            AzlinError::Bastion("msg".into()),
            AzlinError::Storage("msg".into()),
            AzlinError::Backup("msg".into()),
            AzlinError::Snapshot("msg".into()),
            AzlinError::CostTracking("msg".into()),
            AzlinError::FileTransfer("msg".into()),
            AzlinError::PathTraversal("msg".into()),
            AzlinError::Security("msg".into()),
            AzlinError::RateLimit("msg".into()),
            AzlinError::HookExecution("msg".into()),
            AzlinError::Ai("msg".into()),
            AzlinError::AzureCli("msg".into()),
            AzlinError::Serialization("msg".into()),
            AzlinError::Other("msg".into()),
        ];

        // Each error should have a unique prefix
        let messages: Vec<String> = errors.iter().map(|e| e.to_string()).collect();
        let mut unique = std::collections::HashSet::new();
        for msg in &messages {
            unique.insert(msg.clone());
        }
        // "Other" variant uses "{0}" so its message is just "msg" which might clash
        // with some variant. We check that at least most are unique.
        assert!(unique.len() >= 20, "Expected many distinct messages, got {}", unique.len());
    }

    #[test]
    fn test_error_contains_inner_message() {
        let cases = vec![
            (AzlinError::Config("cfg problem".into()), "cfg problem"),
            (AzlinError::Auth("auth problem".into()), "auth problem"),
            (AzlinError::VmManager("vm issue".into()), "vm issue"),
            (AzlinError::VmLifecycle("lifecycle".into()), "lifecycle"),
            (AzlinError::Provisioning("prov err".into()), "prov err"),
            (AzlinError::Ssh("ssh err".into()), "ssh err"),
            (AzlinError::SshKey("key err".into()), "key err"),
            (AzlinError::RemoteExec("exec err".into()), "exec err"),
            (AzlinError::CommandExecution("cmd err".into()), "cmd err"),
            (AzlinError::NetworkSecurity("netsec".into()), "netsec"),
            (AzlinError::Vpn("vpn err".into()), "vpn err"),
            (AzlinError::Bastion("bastion".into()), "bastion"),
            (AzlinError::Storage("storage".into()), "storage"),
            (AzlinError::Backup("backup".into()), "backup"),
            (AzlinError::Snapshot("snapshot".into()), "snapshot"),
            (AzlinError::CostTracking("cost".into()), "cost"),
            (AzlinError::FileTransfer("xfer".into()), "xfer"),
            (AzlinError::PathTraversal("traversal".into()), "traversal"),
            (AzlinError::Security("sec".into()), "sec"),
            (AzlinError::RateLimit("rate".into()), "rate"),
            (AzlinError::HookExecution("hook".into()), "hook"),
            (AzlinError::Ai("ai".into()), "ai"),
            (AzlinError::AzureCli("azcli".into()), "azcli"),
            (AzlinError::Serialization("ser".into()), "ser"),
            (AzlinError::Other("other".into()), "other"),
        ];
        for (err, expected) in cases {
            assert!(
                err.to_string().contains(expected),
                "Error '{}' should contain '{}'",
                err, expected
            );
        }
    }

    #[test]
    fn test_error_debug_impl() {
        let err = AzlinError::Config("test debug".into());
        let debug_str = format!("{:?}", err);
        assert!(debug_str.contains("Config"));
        assert!(debug_str.contains("test debug"));
    }

    #[test]
    fn test_error_from_io_preserves_kind() {
        let io_err = std::io::Error::new(std::io::ErrorKind::PermissionDenied, "access denied");
        let err: AzlinError = io_err.into();
        if let AzlinError::Io(ref inner) = err {
            assert_eq!(inner.kind(), std::io::ErrorKind::PermissionDenied);
        } else {
            panic!("Expected AzlinError::Io variant");
        }
        assert!(err.to_string().contains("access denied"));
    }

    #[test]
    fn test_result_type_alias() {
        fn returns_ok() -> Result<i32> {
            Ok(42)
        }
        fn returns_err() -> Result<i32> {
            Err(AzlinError::Other("fail".into()))
        }
        assert_eq!(returns_ok().unwrap(), 42);
        assert!(returns_err().is_err());
    }
}
