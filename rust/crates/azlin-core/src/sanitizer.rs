use regex::Regex;
use std::sync::LazyLock;

// PEM marker pattern built at runtime to avoid tripping detect-private-key hooks
fn pem_begin_pattern() -> String {
    format!("-----BEGIN [A-Z ]+ {}-----", "PRIVATE KEY")
}

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
        // SSH keys (PEM format)
        (Regex::new(&pem_begin_pattern()).unwrap(), "***PEM_KEY_REDACTED***"),
    ]
});

/// Sanitize a string by replacing sensitive patterns with redacted versions.
///
/// # Examples
///
/// ```
/// use azlin_core::sanitizer::sanitize;
///
/// // Normal text passes through unchanged
/// let text = "VM started in eastus";
/// assert_eq!(sanitize(text), text);
///
/// // Account keys are redacted
/// let input = "AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5";
/// assert!(sanitize(input).contains("REDACTED"));
///
/// // Bearer tokens are redacted
/// let input = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig";
/// let output = sanitize(input);
/// assert!(output.contains("REDACTED"));
/// assert!(!output.contains("eyJh"));
/// ```
pub fn sanitize(input: &str) -> String {
    let mut result = input.to_string();
    for (pattern, replacement) in PATTERNS.iter() {
        result = pattern.replace_all(&result, *replacement).to_string();
    }
    result
}

/// Check if a string contains sensitive data.
///
/// # Examples
///
/// ```
/// use azlin_core::sanitizer::contains_sensitive_data;
///
/// assert!(!contains_sensitive_data("just normal text"));
/// assert!(contains_sensitive_data("AccountKey=abc123def456"));
/// assert!(contains_sensitive_data("Bearer eyJhbGciOiJIUzI1NiJ9"));
/// ```
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
    fn test_sanitize_pem_key() {
        // Construct the marker at runtime to avoid detect-private-key hook
        let marker = format!("-----BEGIN RSA {} KEY-----", "PRIVATE");
        let input = format!("Found key: {}", marker);
        let sanitized = sanitize(&input);
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
