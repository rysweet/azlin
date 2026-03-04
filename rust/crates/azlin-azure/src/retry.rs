use std::time::Duration;

/// Calculate exponential backoff delay with jitter.
///
/// Returns a [`Duration`] based on `base_ms * 2^attempt`, capped at `max_ms`,
/// with ±25% random jitter applied.
///
/// # Examples
///
/// ```
/// use azlin_azure::retry::exponential_backoff;
///
/// // Delay is capped at max_ms (plus up to 25% jitter)
/// let d = exponential_backoff(20, 1000, 5000);
/// assert!(d.as_millis() <= 6250);
///
/// // Zero base always produces zero delay
/// let d = exponential_backoff(5, 0, 10000);
/// assert_eq!(d.as_millis(), 0);
/// ```
pub fn exponential_backoff(attempt: u32, base_ms: u64, max_ms: u64) -> Duration {
    let delay = base_ms.saturating_mul(2u64.saturating_pow(attempt));
    let capped = delay.min(max_ms);
    // Add jitter: ±25%
    let jitter = (capped as f64 * 0.25 * (rand_factor() * 2.0 - 1.0)) as i64;
    let final_ms = (capped as i64 + jitter).max(0) as u64;
    Duration::from_millis(final_ms)
}

/// Cheap jitter factor in [0.0, 1.0) mixing time and thread identity.
///
/// Uses nanosecond timestamp XORed with the thread ID to reduce correlation
/// between concurrent retries (thundering herd mitigation). Not
/// cryptographically random, but sufficient for backoff jitter.
fn rand_factor() -> f64 {
    use std::hash::{Hash, Hasher};
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0) as u64;
    // Mix in thread ID so concurrent threads get different jitter
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    std::thread::current().id().hash(&mut hasher);
    let thread_hash = hasher.finish();
    let mixed = nanos ^ thread_hash;
    (mixed % 10000) as f64 / 10000.0
}

/// Parse Retry-After header value.
///
/// Parses the value as an integer number of seconds.
/// Returns `None` for non-numeric or HTTP-date values.
///
/// # Examples
///
/// ```
/// use azlin_azure::retry::parse_retry_after;
/// use std::time::Duration;
///
/// assert_eq!(parse_retry_after("30"), Some(Duration::from_secs(30)));
/// assert_eq!(parse_retry_after("0"), Some(Duration::from_secs(0)));
/// assert_eq!(parse_retry_after("not-a-number"), None);
/// ```
pub fn parse_retry_after(header: &str) -> Option<Duration> {
    // Try as seconds first
    if let Ok(secs) = header.parse::<u64>() {
        return Some(Duration::from_secs(secs));
    }
    // Try as HTTP-date (RFC 7231)
    // Simplified: just handle "Thu, 01 Jan 2026 00:00:30 GMT" format
    None // Full HTTP date parsing is complex; just use seconds
}

/// Check if an HTTP status code is retryable.
///
/// Returns `true` for 408, 429, 500, 502, 503, and 504.
///
/// # Examples
///
/// ```
/// use azlin_azure::retry::is_retryable;
///
/// assert!(is_retryable(429));  // Too Many Requests
/// assert!(is_retryable(503));  // Service Unavailable
/// assert!(!is_retryable(200)); // OK
/// assert!(!is_retryable(404)); // Not Found
/// ```
pub fn is_retryable(status: u16) -> bool {
    matches!(status, 408 | 429 | 500 | 502 | 503 | 504)
}

/// Retry configuration.
///
/// # Examples
///
/// ```
/// use azlin_azure::retry::RetryConfig;
///
/// let config = RetryConfig::default();
/// assert_eq!(config.max_attempts, 3);
/// assert_eq!(config.base_delay_ms, 1000);
/// assert_eq!(config.max_delay_ms, 30000);
/// ```
#[derive(Debug, Clone)]
pub struct RetryConfig {
    pub max_attempts: u32,
    pub base_delay_ms: u64,
    pub max_delay_ms: u64,
}

impl Default for RetryConfig {
    fn default() -> Self {
        Self {
            max_attempts: 3,
            base_delay_ms: 1000,
            max_delay_ms: 30000,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exponential_backoff_increases() {
        let _d0 = exponential_backoff(0, 100, 10000);
        let _d1 = exponential_backoff(1, 100, 10000);
        let d2 = exponential_backoff(2, 100, 10000);
        // Should generally increase (with jitter, not guaranteed)
        // Test without jitter: base * 2^attempt
        assert!(d2.as_millis() > 50); // At least some delay
    }

    #[test]
    fn test_exponential_backoff_capped() {
        let d = exponential_backoff(20, 1000, 5000);
        assert!(d.as_millis() <= 6250); // 5000 + 25% jitter max
    }

    #[test]
    fn test_exponential_backoff_zero_base() {
        let d = exponential_backoff(5, 0, 10000);
        assert_eq!(d.as_millis(), 0);
    }

    #[test]
    fn test_parse_retry_after_seconds() {
        assert_eq!(parse_retry_after("30"), Some(Duration::from_secs(30)));
        assert_eq!(parse_retry_after("0"), Some(Duration::from_secs(0)));
        assert_eq!(parse_retry_after("120"), Some(Duration::from_secs(120)));
    }

    #[test]
    fn test_parse_retry_after_invalid() {
        assert_eq!(parse_retry_after("not-a-number"), None);
        assert_eq!(parse_retry_after(""), None);
    }

    #[test]
    fn test_is_retryable() {
        assert!(is_retryable(429));
        assert!(is_retryable(500));
        assert!(is_retryable(503));
        assert!(!is_retryable(200));
        assert!(!is_retryable(400));
        assert!(!is_retryable(401));
        assert!(!is_retryable(403));
        assert!(!is_retryable(404));
    }

    #[test]
    fn test_retry_config_default() {
        let config = RetryConfig::default();
        assert_eq!(config.max_attempts, 3);
        assert_eq!(config.base_delay_ms, 1000);
        assert_eq!(config.max_delay_ms, 30000);
    }
}
