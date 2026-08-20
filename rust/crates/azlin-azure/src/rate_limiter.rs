use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Simple token bucket rate limiter for Azure API calls.
///
/// # Examples
///
/// ```
/// use azlin_azure::rate_limiter::RateLimiter;
///
/// let limiter = RateLimiter::new(5.0, 1.0);
/// assert!((limiter.available_tokens() - 5.0).abs() < 0.1);
///
/// // Acquiring a token succeeds (returns None = no wait needed)
/// assert!(limiter.try_acquire().is_none());
/// assert!((limiter.available_tokens() - 4.0).abs() < 0.1);
/// ```
pub struct RateLimiter {
    inner: Mutex<RateLimiterInner>,
}

struct RateLimiterInner {
    tokens: f64,
    max_tokens: f64,
    refill_rate: f64, // tokens per second
    last_refill: Instant,
}

impl RateLimiter {
    pub fn new(max_tokens: f64, refill_rate: f64) -> Self {
        Self {
            inner: Mutex::new(RateLimiterInner {
                tokens: max_tokens,
                max_tokens,
                refill_rate,
                last_refill: Instant::now(),
            }),
        }
    }

    /// Try to acquire a token. Returns wait duration if rate limited.
    ///
    /// # Examples
    ///
    /// ```
    /// use azlin_azure::rate_limiter::RateLimiter;
    ///
    /// let limiter = RateLimiter::new(1.0, 1.0);
    /// // First request is allowed (returns None)
    /// assert!(limiter.try_acquire().is_none());
    /// // Second request is rate limited (returns Some(wait_duration))
    /// assert!(limiter.try_acquire().is_some());
    /// ```
    pub fn try_acquire(&self) -> Option<Duration> {
        let mut inner = self.inner.lock().unwrap_or_else(|e| e.into_inner());
        inner.refill();
        if inner.tokens >= 1.0 {
            inner.tokens -= 1.0;
            None
        } else {
            let wait = Duration::from_secs_f64((1.0 - inner.tokens) / inner.refill_rate);
            Some(wait)
        }
    }

    /// Take a token, sleeping until one is available.
    ///
    /// [`try_acquire`](Self::try_acquire) reports how long a caller would have
    /// to wait; this is for callers that intend to wait anyway. It loops
    /// rather than sleeping once, because several threads waking from the same
    /// reported wait would otherwise all take the one token that refilled.
    ///
    /// # Examples
    ///
    /// ```
    /// use azlin_azure::rate_limiter::RateLimiter;
    ///
    /// let limiter = RateLimiter::new(2.0, 1000.0);
    /// limiter.acquire();
    /// limiter.acquire();
    /// limiter.acquire(); // waits ~1ms for a refill rather than failing
    /// ```
    pub fn acquire(&self) {
        while let Some(wait) = self.try_acquire() {
            std::thread::sleep(wait.max(Duration::from_millis(1)));
        }
    }

    /// Get current token count.
    ///
    /// # Examples
    ///
    /// ```
    /// use azlin_azure::rate_limiter::RateLimiter;
    ///
    /// let limiter = RateLimiter::new(10.0, 1.0);
    /// assert!((limiter.available_tokens() - 10.0).abs() < 0.1);
    /// limiter.try_acquire();
    /// assert!((limiter.available_tokens() - 9.0).abs() < 0.1);
    /// ```
    pub fn available_tokens(&self) -> f64 {
        let mut inner = self.inner.lock().unwrap_or_else(|e| e.into_inner());
        inner.refill();
        inner.tokens
    }
}

impl RateLimiterInner {
    fn refill(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens);
        self.last_refill = now;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rate_limiter_allows_within_limit() {
        let limiter = RateLimiter::new(10.0, 1.0);
        // Should allow 10 immediate requests
        for _ in 0..10 {
            assert!(limiter.try_acquire().is_none());
        }
    }

    #[test]
    fn test_rate_limiter_blocks_at_limit() {
        let limiter = RateLimiter::new(1.0, 1.0);
        assert!(limiter.try_acquire().is_none()); // first allowed
        assert!(limiter.try_acquire().is_some()); // second blocked
    }

    /// Several threads competing for one refilling bucket must all get
    /// through, and none may take a token that is not there. A single sleep of
    /// the reported wait would let every waiter wake together and take the one
    /// token that refilled.
    #[test]
    fn test_acquire_is_safe_under_contention() {
        let limiter = RateLimiter::new(2.0, 2000.0);
        let taken = std::sync::atomic::AtomicUsize::new(0);
        std::thread::scope(|scope| {
            for _ in 0..8 {
                scope.spawn(|| {
                    limiter.acquire();
                    taken.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                });
            }
        });
        assert_eq!(taken.load(std::sync::atomic::Ordering::SeqCst), 8);
    }

    #[test]
    fn test_rate_limiter_refills() {
        let limiter = RateLimiter::new(1.0, 1000.0); // Fast refill for testing
        assert!(limiter.try_acquire().is_none());
        std::thread::sleep(Duration::from_millis(10)); // Wait for refill
        assert!(limiter.try_acquire().is_none()); // Should be available again
    }

    #[test]
    fn test_available_tokens() {
        let limiter = RateLimiter::new(5.0, 1.0);
        assert!((limiter.available_tokens() - 5.0).abs() < 0.1);
        limiter.try_acquire();
        assert!((limiter.available_tokens() - 4.0).abs() < 0.1);
    }
}
