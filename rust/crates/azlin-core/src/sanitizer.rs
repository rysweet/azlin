use regex::Regex;
use std::sync::LazyLock;

static PATTERNS: LazyLock<Vec<(Regex, &str)>> = LazyLock::new(|| {
    vec![
        // Azure storage keys (base64, 88 chars)
        (Regex::new(r#"(?i)(key|password|secret|token|credential)[\s=:]+['""]?(\S{8,})"#).unwrap(), "$1=***REDACTED***"),
        // Connection strings
        (Regex::new(r"(?i)AccountKey=[A-Za-z0-9+/=]+").unwrap(), "AccountKey=***REDACTED***"),
        // SAS tokens
        (Regex::new(r"(?i)sig=[A-Za-z0-9%+/=]+").unwrap(), "sig=***REDACTED***"),
        // Bearer tokens
        (Regex::new(r#"(?i)Bearer\s+[A-Za-z0-9._-]+"#).unwrap(), "Bearer ***REDACTED***"),
        // SSH private keys
        (Regex::new(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----").unwrap(), "***PRIVATE_KEY_REDACTED***"),
    ]
});

/// Sanitize a string by replacing sensitive patterns with redacted versions
pub fn sanitize(input: &str) -> String {
    let mut result = input.to_string();
    for (pattern, replacement) in PATTERNS.iter() {
        result = pattern.replace_all(&result, *replacement).to_string();
    }
    result
}

/// Check if a string contains sensitive data
pub fn contains_sensitive_data(input: &str) -> bool {
    PATTERNS.iter().any(|(pattern, _)| pattern.is_match(input))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_account_key() {
        let input = "AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5IHZhbHVlIGZvciBBenVyZQ==";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
        assert!(!sanitized.contains("dGhpcyB"));
    }

    #[test]
    fn test_sanitize_bearer_token() {
        let input = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
        assert!(!sanitized.contains("eyJh"));
    }

    #[test]
    fn test_sanitize_sas_token() {
        let input = "https://storage.blob.core.windows.net/container?sig=abc123def456%2B";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_password_field() {
        let input = "password=MySecretPass123!";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
        assert!(!sanitized.contains("MySecret"));
    }

    #[test]
    fn test_sanitize_preserves_normal_text() {
        let input = "VM 'my-vm' started successfully in eastus region";
        assert_eq!(sanitize(input), input);
    }

    #[test]
    fn test_sanitize_private_key() {
        let input = "Found key: -----BEGIN RSA PRIVATE KEY-----";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_contains_sensitive_true() {
        assert!(contains_sensitive_data("AccountKey=abc123"));
    }

    #[test]
    fn test_contains_sensitive_false() {
        assert!(!contains_sensitive_data("just normal text"));
    }
}
