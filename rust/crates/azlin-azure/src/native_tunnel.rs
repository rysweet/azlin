//! Native WebSocket bastion tunnel implementation.
//!
//! Replaces `az network bastion tunnel` subprocess with a direct WSS connection.
//! Protocol derived from the azext_bastion Python extension (MIT licensed).
//!
//! ## Protocol
//!
//! 1. **Token exchange**: `POST https://{endpoint}/api/tokens` with resource ID,
//!    protocol, port, and Azure AD token. Returns `authToken`, `nodeId`, `websocketToken`.
//! 2. **WSS connect**: Standard SKU uses `wss://{endpoint}/webtunnelv2/{wsToken}?X-Node-Id={nodeId}`.
//!    Developer SKU uses `wss://{endpoint}/omni/webtunnel/{wsToken}`.
//! 3. **Bidirectional forwarding**: Binary frames between TCP client and WSS.
//! 4. **Cleanup**: `DELETE https://{endpoint}/api/tokens/{authToken}` with `X-Node-Id` header.

use futures_util::future::BoxFuture;
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener as TokioTcpListener;
use tokio::net::TcpStream;
use tokio::sync::Mutex as AsyncMutex;
use tokio::task::JoinHandle;
use tokio_tungstenite::tungstenite::Message;
use tracing::{debug, instrument, warn};

/// Header name for node ID in cleanup requests.
pub const NODE_ID_HEADER: &str = "X-Node-Id";

/// Determines which WebSocket URL shape the tunnel uses.
///
/// Models the transport behavior, not the Azure Bastion marketing SKU.
/// Standard/Premium bastions use a node-scoped path (`/webtunnelv2/{token}?X-Node-Id={id}`).
/// Developer/QuickConnect bastions use an endpoint-scoped path (`/omni/webtunnel/{token}`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WssUrlMode {
    /// Node-scoped path used by Standard and Premium SKU bastions.
    NodeScoped,
    /// Endpoint-scoped path used by Developer/QuickConnect SKU bastions.
    EndpointScoped,
}

// ── Error types ──────────────────────────────────────────────────────────

/// Errors from native bastion tunnel operations.
#[derive(Debug, thiserror::Error)]
pub enum NativeTunnelError {
    #[error("token exchange failed: {0}")]
    TokenExchange(String),

    #[error("WebSocket error: {0}")]
    WebSocket(String),

    #[error("tunnel timed out after {0:?}")]
    Timeout(Duration),

    #[error("invalid endpoint: {0}")]
    InvalidEndpoint(String),

    #[error("tunnel I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("HTTP request failed: {0}")]
    Http(String),
}

// ── Adaptive token cache (issue #1059) ───────────────────────────────────
//
// ROOT CAUSE (#1059): the tunnel captured the ARM access token ONCE at creation
// and cloned that static string into every per-connection token exchange. Azure
// AD access tokens expire (~60-90 min), so a long-lived in-process tunnel kept
// its loopback listener up but every NEW connection failed the `aztoken`
// exchange, surfacing as `kex_exchange_identification: read: Connection reset by
// peer` on `azlin connect`.
//
// FIX: the tunnel takes a `TokenProvider` (an async, cheap-to-clone closure the
// `azlin` crate supplies — it knows how to shell out to `az account
// get-access-token`, keeping `azlin-azure` CLI-agnostic). The token is cached
// with its expiry in a `TokenCache`. Each connection calls `get_valid_token()`
// first, which refreshes adaptively when `now + margin >= expires_at`, where
// `margin` is derived from the token's own lifetime (NOT a hardcoded TTL or a
// reconnect cap). Refresh is single-flight (under an async mutex) and the token
// value is NEVER logged.

/// A token value paired with the instants it was issued and expires.
///
/// SECRET SAFETY: this type intentionally derives **no** `Debug`, `Display`,
/// `Serialize`, or `Clone`-into-log path — `value` is a bearer secret and must
/// never be rendered into a `tracing` sink. Fields are public so the `azlin`
/// provider closure can construct it directly.
pub struct TokenWithExpiry {
    /// The ARM bearer token (secret).
    pub value: String,
    /// When the token was issued (monotonic clock).
    pub issued_at: Instant,
    /// When the token expires, if known. `None` means the expiry could not be
    /// determined (e.g. `az` emitted an unparseable `expiresOn`) and the token
    /// is treated as short-lived — refreshed eagerly on next use (fail-safe).
    pub expires_at: Option<Instant>,
}

/// An async, cheap-to-clone source of fresh [`TokenWithExpiry`] values.
///
/// Supplied by the `azlin` crate so `azlin-azure` never shells out to `az`
/// directly (decoupling). Invoked whenever the cached token is about to expire.
pub type TokenProvider =
    Arc<dyn Fn() -> BoxFuture<'static, Result<TokenWithExpiry, NativeTunnelError>> + Send + Sync>;

/// Fraction of a token's own lifetime used as the pre-expiry refresh margin.
///
/// Adaptive by design (proportional to lifetime), NOT an arbitrary fixed cap:
/// a 60-minute token refreshes ~12 minutes early, a 90-minute token ~18 minutes
/// early. This keeps long-lived tunnels working indefinitely without ever
/// forcing a reconnect at a hardcoded interval.
const REFRESH_FRACTION: f64 = 0.2;

/// Absolute floor for the refresh margin, so very short-lived tokens still get a
/// small safety window. This is a lower bound on the *adaptive* margin above,
/// not a fixed TTL.
const MIN_REFRESH_MARGIN: Duration = Duration::from_secs(30);

/// Default upper bound on how long a single provider (`az`) invocation may run
/// while holding the single-flight refresh lock.
///
/// This is a **liveness guard, not a token-lifetime or reconnect cap** (issue
/// #1059 fast-follow): because the refresh runs under the async mutex, a hung
/// provider — e.g. a wedged `az` subprocess — would otherwise hold the lock
/// forever and stall *every* connection, not just the one triggering the
/// refresh. Bounding the await lets one hung refresh fail cleanly (releasing the
/// mutex) while other waiters proceed. Callers may override via
/// [`TokenCache::with_refresh_timeout`].
const DEFAULT_REFRESH_TIMEOUT: Duration = Duration::from_secs(60);

/// Internal cached token state.
struct CachedToken {
    value: String,
    issued_at: Instant,
    expires_at: Option<Instant>,
}

impl CachedToken {
    /// Adaptive pre-expiry margin derived from this token's own lifetime.
    fn refresh_margin(&self, expires_at: Instant) -> Duration {
        let lifetime = expires_at.saturating_duration_since(self.issued_at);
        lifetime.mul_f64(REFRESH_FRACTION).max(MIN_REFRESH_MARGIN)
    }

    /// Whether the token should be refreshed before it is handed out again.
    /// Unknown expiry → always refresh (fail-safe).
    fn needs_refresh(&self) -> bool {
        match self.expires_at {
            None => true,
            Some(expires_at) => {
                let margin = self.refresh_margin(expires_at);
                Instant::now() + margin >= expires_at
            }
        }
    }

    /// Whether the token is past its actual expiry (no margin). Used to decide
    /// whether a still-cached token may be reused when a refresh attempt fails.
    fn hard_expired(&self) -> bool {
        match self.expires_at {
            None => true,
            Some(expires_at) => Instant::now() >= expires_at,
        }
    }
}

/// Caches an ARM access token and refreshes it adaptively via a [`TokenProvider`].
///
/// Cheap to clone (all state is behind `Arc`); clone one into each per-connection
/// task. `get_valid_token()` is single-flight: concurrent callers block on the
/// async mutex, so a batch of connections arriving across the expiry boundary
/// triggers at most one provider (`az`) invocation.
#[derive(Clone)]
pub struct TokenCache {
    provider: TokenProvider,
    inner: Arc<AsyncMutex<Option<CachedToken>>>,
    /// Liveness bound on a single provider invocation (see
    /// [`DEFAULT_REFRESH_TIMEOUT`]). Held-lock refreshes are wrapped in a
    /// `tokio::time::timeout` of this length so a hung provider cannot wedge the
    /// single-flight mutex for every connection.
    refresh_timeout: Duration,
}

impl TokenCache {
    /// Create an empty cache; the first `get_valid_token()` fetches from the
    /// provider to seed it.
    pub fn new(provider: TokenProvider) -> Self {
        Self {
            provider,
            inner: Arc::new(AsyncMutex::new(None)),
            refresh_timeout: DEFAULT_REFRESH_TIMEOUT,
        }
    }

    /// Create a cache pre-seeded with an already-obtained token.
    pub fn with_token(provider: TokenProvider, initial: TokenWithExpiry) -> Self {
        Self {
            provider,
            inner: Arc::new(AsyncMutex::new(Some(CachedToken {
                value: initial.value,
                issued_at: initial.issued_at,
                expires_at: initial.expires_at,
            }))),
            refresh_timeout: DEFAULT_REFRESH_TIMEOUT,
        }
    }

    /// Override the per-refresh liveness timeout (default
    /// [`DEFAULT_REFRESH_TIMEOUT`]).
    ///
    /// Bounds how long a single provider invocation may hold the single-flight
    /// lock before it is abandoned, so a hung provider cannot stall every
    /// connection. Zero is treated as "no timeout would ever fire" and is clamped
    /// up to a 1 ms floor so the bound stays meaningful.
    pub fn with_refresh_timeout(mut self, timeout: Duration) -> Self {
        self.refresh_timeout = timeout.max(Duration::from_millis(1));
        self
    }

    /// Return a valid token value, refreshing via the provider if the cached
    /// token is missing or about to expire.
    ///
    /// Single-flight: the async mutex is held across the provider await, so
    /// concurrent callers that lose the race re-check freshness after acquiring
    /// the lock and reuse the just-refreshed token instead of triggering another
    /// provider call.
    ///
    /// LIVENESS: the provider await is bounded by `refresh_timeout` so a hung
    /// provider cannot hold the single-flight lock indefinitely and stall every
    /// connection (issue #1059 fast-follow). A timeout is handled exactly like a
    /// provider error — the fail-safe path below reuses a not-yet-hard-expired
    /// cached token and only surfaces an error when none remains.
    ///
    /// SECRET SAFETY: the returned `String` is the only place the token value
    /// surfaces; this method never logs the value.
    pub async fn get_valid_token(&self) -> Result<String, NativeTunnelError> {
        let mut guard = self.inner.lock().await;

        // Fast path: a cached token that is still comfortably valid.
        if let Some(cached) = guard.as_ref() {
            if !cached.needs_refresh() {
                return Ok(cached.value.clone());
            }
        }

        // Refresh under the lock (single-flight), bounded by `refresh_timeout`.
        // A hung provider (e.g. a wedged `az` subprocess) that outlasts the bound
        // is abandoned here so the lock is released and other waiters proceed;
        // the dropped future's blocking work (if any) detaches harmlessly.
        let refreshed = match tokio::time::timeout(self.refresh_timeout, (self.provider)()).await {
            Ok(result) => result,
            Err(_elapsed) => Err(NativeTunnelError::Timeout(self.refresh_timeout)),
        };

        match refreshed {
            Ok(fresh) => {
                let value = fresh.value.clone();
                *guard = Some(CachedToken {
                    value: fresh.value,
                    issued_at: fresh.issued_at,
                    expires_at: fresh.expires_at,
                });
                Ok(value)
            }
            Err(e) => {
                // Fail-safe: if we still hold a token that has not hard-expired,
                // reuse it for this connection rather than tearing the tunnel
                // down on a transient `az` hiccup or a single hung refresh. The
                // error is never dropped silently — it is either logged (reuse)
                // or surfaced (no token).
                if let Some(cached) = guard.as_ref() {
                    if !cached.hard_expired() {
                        warn!(
                            "bastion token refresh failed, reusing still-valid cached token: {e}"
                        );
                        return Ok(cached.value.clone());
                    }
                }
                Err(e)
            }
        }
    }
}

// ── Token exchange types ─────────────────────────────────────────────────

/// Response from the bastion token exchange endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BastionTokenResponse {
    #[serde(rename = "authToken")]
    pub auth_token: String,
    #[serde(rename = "nodeId")]
    pub node_id: String,
    #[serde(rename = "websocketToken")]
    pub websocket_token: String,
}

// ── URL builders ─────────────────────────────────────────────────────────

/// Build the token exchange URL: `https://{endpoint}/api/tokens`
pub fn build_token_exchange_url(endpoint: &str) -> String {
    format!("https://{}/api/tokens", endpoint)
}

/// Build WSS URL for Standard/Premium SKU bastions.
/// `wss://{endpoint}/webtunnelv2/{ws_token}?X-Node-Id={node_id}`
///
/// All dynamic values are URL-encoded to prevent path injection (SEC-2).
pub fn build_wss_url_standard(endpoint: &str, ws_token: &str, node_id: &str) -> String {
    format!(
        "wss://{}/webtunnelv2/{}?X-Node-Id={}",
        endpoint,
        urlencoding::encode(ws_token),
        urlencoding::encode(node_id),
    )
}

/// Build WSS URL for Developer/QuickConnect SKU bastions.
/// `wss://{endpoint}/omni/webtunnel/{ws_token}`
pub fn build_wss_url_developer(endpoint: &str, ws_token: &str) -> String {
    format!(
        "wss://{}/omni/webtunnel/{}",
        endpoint,
        urlencoding::encode(ws_token),
    )
}

/// Return a log-safe rendering of a `wss://` bastion tunnel URL with the
/// embedded `websocketToken` replaced by `***` (issue #1056).
///
/// The tunnel URL carries the short-lived `websocketToken` — a bearer secret —
/// as a path segment (`/webtunnelv2/<TOKEN>` for Standard/Premium,
/// `/omni/webtunnel/<TOKEN>` for Developer/QuickConnect). Rendering the raw URL
/// (or a `tungstenite` error that embeds it) into a `tracing` sink leaks that
/// secret into log files and OpenTelemetry exporters.
///
/// This helper masks the token segment while preserving scheme, host, and the
/// non-secret `X-Node-Id` query parameter so logs stay diagnostically useful.
/// It is **fail-closed**: any input that does not match a known tunnel URL shape
/// is masked to the fixed sentinel `wss://<redacted>` rather than echoed back.
///
/// This is a logging-only control. The real, token-bearing URL returned by
/// [`build_wss_url_standard`] / [`build_wss_url_developer`] is still passed
/// verbatim to `connect_async`; `redact_wss_url` takes `&str` and returns a new
/// `String`, so it never mutates the caller's live URL.
pub fn redact_wss_url(url: &str) -> String {
    /// Mask marker substituted for the secret token segment.
    const MASK: &str = "***";
    /// Fixed sentinel returned for any unrecognized / malformed input.
    const REDACTED: &str = "wss://<redacted>";

    // Only `wss://` tunnel URLs of a known shape are structurally redacted.
    let Some(rest) = url.strip_prefix("wss://") else {
        return REDACTED.to_string();
    };

    // Try each known tunnel path marker. `host` is everything before the marker
    // (must be a bare authority with no `/`); the token segment after the marker
    // is dropped and any trailing `?query` (e.g. `X-Node-Id`) is preserved.
    for marker in ["/webtunnelv2/", "/omni/webtunnel/"] {
        if let Some(idx) = rest.find(marker) {
            let host = &rest[..idx];
            if host.is_empty() || host.contains('/') {
                continue;
            }
            let after = &rest[idx + marker.len()..];
            let query = after.find('?').map(|q| &after[q..]).unwrap_or("");
            return format!("wss://{host}{marker}{MASK}{query}");
        }
    }

    // Fail-closed: unrecognized shape → do not echo any part of the input.
    REDACTED.to_string()
}

/// Build the token cleanup URL: `https://{endpoint}/api/tokens/{auth_token}`
pub fn build_token_cleanup_url(endpoint: &str, auth_token: &str) -> String {
    format!(
        "https://{}/api/tokens/{}",
        endpoint,
        urlencoding::encode(auth_token),
    )
}

/// Build the `application/x-www-form-urlencoded` parameters for the token
/// exchange POST request.
///
/// The Azure Bastion data-plane expects a **form-encoded** body, not JSON
/// (mirrors the `azext_bastion` Python extension). The ARM access token is
/// carried in the `aztoken` field; auth is NOT sent as an `Authorization`
/// header. The `token` field (a previously-issued auth token) is omitted on
/// the initial exchange — `azext_bastion` sends `last_token=None`, which the
/// Python `requests` form encoder drops entirely.
pub fn build_token_exchange_form(
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
) -> Vec<(&'static str, String)> {
    vec![
        ("resourceId", target_resource_id.to_string()),
        ("protocol", "tcptunnel".to_string()),
        ("workloadHostPort", resource_port.to_string()),
        ("aztoken", token.to_string()),
    ]
}

// ── Local listener ───────────────────────────────────────────────────────

/// Bind a TCP listener on 127.0.0.1 with an OS-assigned port (SEC-4).
pub fn bind_local_listener() -> Result<std::net::TcpListener, NativeTunnelError> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    Ok(listener)
}

// ── Endpoint validation ──────────────────────────────────────────────────

/// Normalize and validate the bastion endpoint.
/// - Bare hostnames are treated as HTTPS (returned as-is for URL building).
/// - `https://` prefix is stripped to get the bare host.
/// - `http://` and `ws://` are rejected (SEC-3).
fn normalize_endpoint(endpoint: &str) -> Result<String, NativeTunnelError> {
    if endpoint.is_empty() {
        return Err(NativeTunnelError::InvalidEndpoint(
            "endpoint must not be empty".to_string(),
        ));
    }
    if endpoint.starts_with("http://") || endpoint.starts_with("ws://") {
        return Err(NativeTunnelError::InvalidEndpoint(format!(
            "endpoint must use TLS (https/wss), got: {}",
            endpoint
        )));
    }
    if let Some(host) = endpoint.strip_prefix("https://") {
        Ok(host.trim_end_matches('/').to_string())
    } else if let Some(host) = endpoint.strip_prefix("wss://") {
        Ok(host.trim_end_matches('/').to_string())
    } else {
        // Bare hostname — treat as HTTPS
        Ok(endpoint.trim_end_matches('/').to_string())
    }
}

// ── Transport error transparency (issue #1046 hardening) ─────────────────
//
// reqwest's top-level `Display` for a transport failure is opaque
// (`error sending request for url (...)`) and hides the real DNS/TLS/timeout
// cause. `error_chain` walks `std::error::Error::source()` so the underlying
// cause is surfaced in `TokenExchange` errors and cleanup warnings. It only
// reads `Display`/`source()` — it never touches request headers or tokens.
fn error_chain(err: &dyn std::error::Error) -> String {
    let mut chain = err.to_string();
    let mut source = err.source();
    while let Some(cause) = source {
        chain.push_str(": ");
        chain.push_str(&cause.to_string());
        source = cause.source();
    }
    chain
}

// ── Transport failure classification (issue #1045) ───────────────────────
//
// The #1045 incident surfaced as an opaque `token exchange failed: request
// failed: error sending request for url (...)` with no underlying cause
// (`source() == None`) — a TCP connect failure the operator could not act on.
// `TunnelFailureKind` maps transport errors and HTTP statuses to a small,
// actionable set of kinds plus a static, secret-free remediation hint.
//
// The classifier is pure, total, and panic-free: it only reads `Display` /
// `source()` and never touches tokens, headers, or request bodies.

/// Actionable category of a bastion tunnel setup failure.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TunnelFailureKind {
    /// TCP connection could not be established (refused/unreachable), or an
    /// opaque transport failure with no underlying cause. This is the #1045
    /// incident kind.
    Connect,
    /// DNS name resolution failed.
    Dns,
    /// TLS handshake or certificate validation failed.
    Tls,
    /// The operation exceeded its timeout.
    Timeout,
    /// The server returned a non-success HTTP status (non-auth).
    Http,
    /// The server rejected the request with 401/403 (auth/permission).
    Auth,
    /// The response could not be parsed.
    Parse,
}

impl std::fmt::Display for TunnelFailureKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            TunnelFailureKind::Connect => "CONNECT",
            TunnelFailureKind::Dns => "DNS",
            TunnelFailureKind::Tls => "TLS",
            TunnelFailureKind::Timeout => "TIMEOUT",
            TunnelFailureKind::Http => "HTTP",
            TunnelFailureKind::Auth => "AUTH",
            TunnelFailureKind::Parse => "PARSE",
        };
        f.write_str(s)
    }
}

/// A static, secret-free remediation hint for the operator.
///
/// Hints are constant strings — they never interpolate tokens, URLs, or any
/// request data, so they are always safe to log and to embed in error text.
pub fn remediation_hint(kind: TunnelFailureKind) -> &'static str {
    match kind {
        TunnelFailureKind::Connect => {
            "could not reach the bastion data-plane; verify the bastion is running, the target VM is started, and NSG/firewall rules allow the tunnel"
        }
        TunnelFailureKind::Dns => {
            "bastion hostname did not resolve; check DNS/VPN connectivity and that the bastion data-plane FQDN is correct"
        }
        TunnelFailureKind::Tls => {
            "TLS handshake failed; check the system clock, CA trust store, and any TLS-inspecting proxy"
        }
        TunnelFailureKind::Timeout => {
            "the tunnel setup timed out; retry, or raise bastion_tunnel_timeout / bastion_connect_timeout in ~/.azlin/config.toml"
        }
        TunnelFailureKind::Http => {
            "the bastion service returned an error status; retry and check Azure Bastion service health"
        }
        TunnelFailureKind::Auth => {
            "Azure rejected the token; run `az login` and confirm you have access to the bastion and target VM"
        }
        TunnelFailureKind::Parse => {
            "the bastion response could not be parsed; the service may be degraded — retry shortly"
        }
    }
}

/// Classify a transport-layer error from `reqwest`'s `send()` into an
/// actionable [`TunnelFailureKind`].
///
/// Pure and total: it walks the `source()` chain via `Display` only and never
/// panics or inspects secrets. The classification is deliberately conservative
/// — a transport failure is never mapped to [`TunnelFailureKind::Auth`], which
/// is reserved for explicit HTTP 401/403 statuses (see [`classify_http_status`]).
/// Unrecognized transport failures (including the #1045 opaque no-`source()`
/// case) fall through to [`TunnelFailureKind::Connect`].
pub fn classify_transport_error(err: &dyn std::error::Error) -> TunnelFailureKind {
    let chain = error_chain(err).to_lowercase();

    // Order matters: check the most specific signals first.
    if chain.contains("timed out") || chain.contains("timeout") {
        return TunnelFailureKind::Timeout;
    }
    if chain.contains("failed to lookup address")
        || chain.contains("name or service not known")
        || chain.contains("nodename nor servname")
        || chain.contains("dns error")
        || chain.contains("no such host")
        || chain.contains("temporary failure in name resolution")
    {
        return TunnelFailureKind::Dns;
    }
    if chain.contains("tls")
        || chain.contains("ssl")
        || chain.contains("certificate")
        || chain.contains("handshake")
    {
        return TunnelFailureKind::Tls;
    }
    // Connect signals and the #1045 opaque case (generic "error sending
    // request" transport failure with no source) both resolve to Connect.
    TunnelFailureKind::Connect
}

/// Classify a non-success HTTP status code into a [`TunnelFailureKind`].
///
/// Only 401/403 map to [`TunnelFailureKind::Auth`]; every other non-success
/// status maps to [`TunnelFailureKind::Http`].
pub fn classify_http_status(status: u16) -> TunnelFailureKind {
    match status {
        401 | 403 => TunnelFailureKind::Auth,
        _ => TunnelFailureKind::Http,
    }
}

// ── Token exchange ───────────────────────────────────────────────────────

#[instrument(skip(client, token))]
async fn exchange_token(
    client: &reqwest::Client,
    endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
) -> Result<BastionTokenResponse, NativeTunnelError> {
    let url = build_token_exchange_url(endpoint);
    let form = build_token_exchange_form(target_resource_id, resource_port, token);

    // The Bastion data-plane expects `application/x-www-form-urlencoded` with
    // the ARM token in the `aztoken` field (mirrors azext_bastion). Sending
    // JSON or an `Authorization` header makes the service return HTTP 500.
    let resp = client.post(&url).form(&form).send().await.map_err(|e| {
        let kind = classify_transport_error(&e);
        NativeTunnelError::TokenExchange(format!(
            "request failed: {} [{}: {}]",
            error_chain(&e),
            kind,
            remediation_hint(kind),
        ))
    })?;

    if !resp.status().is_success() {
        let status = resp.status();
        let kind = classify_http_status(status.as_u16());
        let body_text = resp.text().await.unwrap_or_default();
        return Err(NativeTunnelError::TokenExchange(format!(
            "HTTP {status}: {body_text} [{}: {}]",
            kind,
            remediation_hint(kind),
        )));
    }

    resp.json::<BastionTokenResponse>().await.map_err(|e| {
        let kind = TunnelFailureKind::Parse;
        NativeTunnelError::TokenExchange(format!(
            "failed to parse response: {e} [{}: {}]",
            kind,
            remediation_hint(kind),
        ))
    })
}

/// Best-effort token cleanup via DELETE.
async fn cleanup_token(client: &reqwest::Client, endpoint: &str, auth_token: &str, node_id: &str) {
    let url = build_token_cleanup_url(endpoint, auth_token);
    // The cleanup URL embeds the auth token as a path segment, and reqwest's
    // error `Display` renders the full request URL (path included). Strip the
    // URL from the error before logging so the token never reaches the log
    // sink; the underlying cause chain is preserved for diagnostics.
    if let Err(e) = client
        .delete(&url)
        .header(NODE_ID_HEADER, node_id)
        .send()
        .await
    {
        warn!(
            "bastion token cleanup failed for node {node_id}: {}",
            error_chain(&e.without_url())
        );
    }
}

// ── Bidirectional forwarding ─────────────────────────────────────────────

/// Forward data bidirectionally between a TCP stream and a WebSocket connection.
///
/// This is the core forwarding loop: TCP bytes → WSS binary frames, and
/// WSS binary frames → TCP bytes. Runs until either side closes or errors.
pub async fn forward_tcp_to_ws(
    tcp_stream: TcpStream,
    ws_stream: tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<TcpStream>>,
) {
    let (mut ws_sink, mut ws_source) = ws_stream.split();
    let (mut tcp_reader, mut tcp_writer) = tcp_stream.into_split();

    let tcp_to_ws = async {
        let mut buf = vec![0u8; 65536];
        loop {
            match tcp_reader.read(&mut buf).await {
                Ok(0) => break,
                Ok(n) => {
                    let data = buf[..n].to_vec();
                    if ws_sink.send(Message::Binary(data.into())).await.is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
        let _ = ws_sink.close().await;
    };

    let ws_to_tcp = async {
        while let Some(msg) = ws_source.next().await {
            match msg {
                Ok(Message::Binary(data)) if tcp_writer.write_all(&data).await.is_err() => {
                    break;
                }
                Ok(Message::Close(_)) | Err(_) => break,
                _ => {} // ignore successful writes and ping/pong/text
            }
        }
    };

    tokio::select! {
        _ = tcp_to_ws => {},
        _ = ws_to_tcp => {},
    }
}

/// Handle a single inbound TCP connection: exchange token, connect WSS, forward.
async fn handle_client(
    tcp_stream: TcpStream,
    client: reqwest::Client,
    endpoint: String,
    target_resource_id: String,
    resource_port: u16,
    token_cache: TokenCache,
    url_mode: WssUrlMode,
) {
    // Step 0: Obtain a valid (refreshed if needed) ARM token. This is what makes
    // long-lived tunnels self-heal (issue #1059): the cache refreshes adaptively
    // instead of reusing the static token captured at tunnel creation.
    let token = match token_cache.get_valid_token().await {
        Ok(t) => t,
        Err(e) => {
            warn!("bastion token refresh failed, dropping connection: {e}");
            return;
        }
    };

    // Step 1: Token exchange
    let token_resp = match exchange_token(
        &client,
        &endpoint,
        &target_resource_id,
        resource_port,
        &token,
    )
    .await
    {
        Ok(r) => r,
        Err(e) => {
            warn!("bastion token exchange failed: {e}");
            return;
        }
    };

    // Step 2: Build WSS URL based on transport mode
    let wss_url = match url_mode {
        WssUrlMode::NodeScoped => {
            build_wss_url_standard(&endpoint, &token_resp.websocket_token, &token_resp.node_id)
        }
        WssUrlMode::EndpointScoped => {
            build_wss_url_developer(&endpoint, &token_resp.websocket_token)
        }
    };

    // Step 3: Connect WSS
    let ws_result = tokio_tungstenite::connect_async(&wss_url).await;
    let (ws_stream, _) = match ws_result {
        Ok(pair) => pair,
        Err(e) => {
            // The `tungstenite` error `Display` embeds the full connect URL,
            // which carries the `websocketToken` secret. Scrub the URL from the
            // rendered error and log the redacted form only (issue #1056).
            let redacted_url = redact_wss_url(&wss_url);
            let safe_err = e.to_string().replace(&wss_url, &redacted_url);
            warn!(url = %redacted_url, "bastion WSS connect failed: {safe_err}");
            // Best-effort cleanup
            cleanup_token(
                &client,
                &endpoint,
                &token_resp.auth_token,
                &token_resp.node_id,
            )
            .await;
            return;
        }
    };

    debug!("bastion WSS connected, forwarding TCP↔WSS");

    // Step 4: Bidirectional forwarding (runs until either side closes)
    forward_tcp_to_ws(tcp_stream, ws_stream).await;

    // Step 5: Best-effort token cleanup
    cleanup_token(
        &client,
        &endpoint,
        &token_resp.auth_token,
        &token_resp.node_id,
    )
    .await;

    debug!("bastion tunnel connection closed");
}

// ── Public API ───────────────────────────────────────────────────────────

/// Open a native bastion tunnel.
///
/// Binds a local TCP listener on 127.0.0.1, returns the port and a background
/// task handle. Each inbound TCP connection triggers a fresh token exchange +
/// WSS connect (matching the Python reference behavior).
///
/// This is a thin wrapper over [`open_tunnel_with_timeouts`] that uses a single
/// `timeout` for both the overall setup and the TCP connect phase. Callers that
/// want a distinct connect timeout should call [`open_tunnel_with_timeouts`].
///
/// # Arguments
/// - `bastion_endpoint` — Bastion DNS name or data pod URL (bare hostname or with scheme)
/// - `target_resource_id` — Full ARM resource ID of the target VM
/// - `resource_port` — Port on the target VM (typically 22 for SSH)
/// - `token` — Azure AD bearer token for the bastion resource
/// - `url_mode` — WebSocket URL shape to use (NodeScoped for Standard/Premium, EndpointScoped for Developer)
/// - `timeout` — Connection timeout for the initial setup
///
/// # Security
/// - SEC-3: Rejects non-TLS endpoints
/// - SEC-4: Binds only to 127.0.0.1
/// - SEC-8: Zero unsafe blocks
pub async fn open_tunnel(
    bastion_endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
    url_mode: WssUrlMode,
    timeout: Duration,
) -> Result<(u16, JoinHandle<()>), NativeTunnelError> {
    // Reject an empty token here so the stable `open_tunnel(&str)` contract keeps
    // its validation. The provider path (below) has no static token to validate.
    if token.is_empty() {
        return Err(NativeTunnelError::InvalidEndpoint(
            "token must not be empty".to_string(),
        ));
    }
    open_tunnel_with_timeouts(
        bastion_endpoint,
        target_resource_id,
        resource_port,
        static_token_provider(token),
        url_mode,
        timeout,
        timeout,
    )
    .await
}

/// Wrap a static token literal in a trivial [`TokenProvider`].
///
/// Used by the stable [`open_tunnel`] wrapper: the token is fixed and cannot be
/// refreshed to anything different, so its expiry is reported as unknown
/// (`None`). Real, refreshable callers pass a live provider to
/// [`open_tunnel_with_timeouts`] instead.
fn static_token_provider(token: &str) -> TokenProvider {
    let token = token.to_string();
    Arc::new(move || {
        let token = token.clone();
        Box::pin(async move {
            let now = Instant::now();
            Ok(TokenWithExpiry {
                value: token,
                issued_at: now,
                expires_at: None,
            })
        })
    })
}

/// Open a native bastion tunnel with separate overall and connect timeouts.
///
/// Identical to [`open_tunnel`], but lets the caller configure the TCP
/// `connect_timeout` independently of the overall request `timeout`. This backs
/// the optional `bastion_connect_timeout` config knob (issue #1045) without
/// changing the stable [`open_tunnel`] signature.
///
/// # Token refresh (issue #1059)
/// Instead of a static token, callers supply a [`TokenProvider`]. The tunnel
/// caches the token with its expiry and refreshes it adaptively, so a long-lived
/// in-process tunnel keeps working past the ARM access token's lifetime instead
/// of failing every new connection's token exchange once the captured token
/// expires.
///
/// # Arguments
/// - `provider` — async source of fresh ARM tokens (supplied by `azlin`)
/// - `connect_timeout` — Timeout for establishing the TCP connection to the
///   bastion data-plane. Defaults (via [`open_tunnel`]) to `timeout`.
///
/// See [`open_tunnel`] for the remaining arguments and security notes.
#[allow(clippy::too_many_arguments)]
pub async fn open_tunnel_with_timeouts(
    bastion_endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    provider: TokenProvider,
    url_mode: WssUrlMode,
    timeout: Duration,
    connect_timeout: Duration,
) -> Result<(u16, JoinHandle<()>), NativeTunnelError> {
    // Validate inputs
    if resource_port == 0 {
        return Err(NativeTunnelError::InvalidEndpoint(
            "resource_port must not be 0".to_string(),
        ));
    }

    let endpoint = normalize_endpoint(bastion_endpoint)?;

    // Bind local listener (SEC-4: loopback only)
    let std_listener = bind_local_listener()?;
    let local_addr: SocketAddr = std_listener.local_addr()?;
    let local_port = local_addr.port();

    // Convert to tokio listener
    std_listener.set_nonblocking(true)?;
    let listener = TokioTcpListener::from_std(std_listener)?;

    // Build HTTP client with timeout
    let client = reqwest::Client::builder()
        .timeout(timeout)
        .connect_timeout(connect_timeout)
        .build()
        .map_err(|e| NativeTunnelError::Http(format!("failed to create HTTP client: {e}")))?;

    // Adaptive token cache shared across every connection (issue #1059). The
    // refresh is bounded by the configured setup timeout so a hung `az` cannot
    // hold the single-flight lock and stall every connection (fast-follow).
    let token_cache = TokenCache::new(provider).with_refresh_timeout(timeout);

    // Verify connectivity with a quick token exchange + cleanup. This also seeds
    // the token cache with a fresh, valid token.
    let verify_cache = token_cache.clone();
    let verify_endpoint = endpoint.clone();
    let verify_client = client.clone();
    let verify_resource_id = target_resource_id.to_string();
    let test_result = tokio::time::timeout(timeout, async move {
        let token = verify_cache.get_valid_token().await?;
        exchange_token(
            &verify_client,
            &verify_endpoint,
            &verify_resource_id,
            resource_port,
            &token,
        )
        .await
    })
    .await;

    match test_result {
        Ok(Ok(resp)) => {
            // Connectivity verified; clean up the test token
            cleanup_token(&client, &endpoint, &resp.auth_token, &resp.node_id).await;
            debug!(
                "bastion tunnel connectivity verified on 127.0.0.1:{}",
                local_port
            );
        }
        Ok(Err(e)) => {
            return Err(e);
        }
        Err(_) => {
            return Err(NativeTunnelError::Timeout(timeout));
        }
    }

    // Spawn the accept loop
    let owned_endpoint = endpoint.clone();
    let owned_resource_id = target_resource_id.to_string();
    let handle = tokio::spawn(async move {
        loop {
            match listener.accept().await {
                Ok((tcp_stream, peer)) => {
                    debug!("bastion tunnel accepted TCP connection from {peer}");
                    let client = client.clone();
                    let ep = owned_endpoint.clone();
                    let rid = owned_resource_id.clone();
                    let cache = token_cache.clone();
                    tokio::spawn(async move {
                        handle_client(tcp_stream, client, ep, rid, resource_port, cache, url_mode)
                            .await;
                    });
                }
                Err(e) => {
                    warn!("bastion tunnel accept error: {e}");
                    break;
                }
            }
        }
    });

    Ok((local_port, handle))
}

// ── Transport error transparency tests (issue #1046 hardening) ───────────────
//
// These tests define the `error_chain` contract (see the implementation above)
// before it exists (TDD): the true DNS/TLS/timeout cause must be visible, and
// the auth token must never leak from the cleanup path.

#[cfg(test)]
mod error_surface_tests {
    use super::*;
    use std::error::Error as StdError;
    use std::fmt;

    #[derive(Debug)]
    struct DnsCause;
    impl fmt::Display for DnsCause {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(
                f,
                "failed to lookup address information: Name or service not known"
            )
        }
    }
    impl StdError for DnsCause {}

    #[derive(Debug)]
    struct SendError(DnsCause);
    impl fmt::Display for SendError {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(
                f,
                "error sending request for url (https://x.bastion.azure.com/api/tokens)"
            )
        }
    }
    impl StdError for SendError {
        fn source(&self) -> Option<&(dyn StdError + 'static)> {
            Some(&self.0)
        }
    }

    #[test]
    fn test_error_chain_surfaces_underlying_dns_cause() {
        let err = SendError(DnsCause);
        let chain = error_chain(&err);
        // The opaque top-level message is still present ...
        assert!(chain.contains("error sending request for url"));
        // ... but the real, previously-hidden cause is now visible.
        assert!(
            chain.contains("Name or service not known"),
            "cause chain must surface the underlying DNS failure, got: {chain}"
        );
    }

    #[test]
    fn test_error_chain_single_error() {
        let chain = error_chain(&DnsCause);
        assert!(chain.contains("Name or service not known"));
    }

    #[test]
    fn test_error_chain_walks_multiple_levels() {
        #[derive(Debug)]
        struct L3;
        impl fmt::Display for L3 {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(f, "connection refused")
            }
        }
        impl StdError for L3 {}

        #[derive(Debug)]
        struct L2(L3);
        impl fmt::Display for L2 {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(f, "tls handshake failed")
            }
        }
        impl StdError for L2 {
            fn source(&self) -> Option<&(dyn StdError + 'static)> {
                Some(&self.0)
            }
        }

        #[derive(Debug)]
        struct L1(L2);
        impl fmt::Display for L1 {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(f, "request failed")
            }
        }
        impl StdError for L1 {
            fn source(&self) -> Option<&(dyn StdError + 'static)> {
                Some(&self.0)
            }
        }

        let chain = error_chain(&L1(L2(L3)));
        assert!(chain.contains("request failed"), "chain: {chain}");
        assert!(chain.contains("tls handshake failed"), "chain: {chain}");
        assert!(chain.contains("connection refused"), "chain: {chain}");
    }

    // Regression test for the cleanup-path token leak: the cleanup URL embeds
    // the auth token as a path segment, and reqwest's error `Display` renders
    // the full URL. `cleanup_token` logs `error_chain(&e.without_url())`, so the
    // token must never appear in the logged string even though it is present in
    // the raw error.
    #[tokio::test]
    async fn test_cleanup_error_without_url_does_not_leak_auth_token() {
        const AUTH_TOKEN: &str = "SUPER-SECRET-AUTH-TOKEN-9f8e7d6c";
        // `.invalid` is reserved (RFC 6761) and guarantees a resolution failure,
        // so `send()` returns a URL-bearing transport error without any network.
        let url = build_token_cleanup_url("host.invalid", AUTH_TOKEN);
        let err = reqwest::Client::new()
            .delete(&url)
            .send()
            .await
            .expect_err("request to a .invalid host must fail");

        // Sanity: the raw error would leak the token (this is exactly what the
        // fix guards against).
        assert!(
            error_chain(&err).contains(AUTH_TOKEN),
            "precondition: raw reqwest error is expected to carry the token in its URL"
        );

        // The logged form strips the URL, so the token must be gone.
        let logged = error_chain(&err.without_url());
        assert!(
            !logged.contains(AUTH_TOKEN),
            "auth token leaked into cleanup log line: {logged}"
        );
    }
}

// ── Transport failure classification tests (issue #1045) ─────────────────────
//
// The 7-case contract matrix for `TunnelFailureKind`. Doubles model the shapes
// reqwest produces without needing a live network: the #1045 incident is an
// opaque transport error with `source() == None`.

#[cfg(test)]
mod classifier_tests {
    use super::*;
    use std::error::Error as StdError;
    use std::fmt;

    /// Error double: a `Display` string with no underlying `source()`.
    #[derive(Debug)]
    struct Opaque(&'static str);
    impl fmt::Display for Opaque {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            f.write_str(self.0)
        }
    }
    impl StdError for Opaque {}

    /// Error double carrying an underlying cause via `source()`.
    #[derive(Debug)]
    struct Wrapped(&'static str, Opaque);
    impl fmt::Display for Wrapped {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            f.write_str(self.0)
        }
    }
    impl StdError for Wrapped {
        fn source(&self) -> Option<&(dyn StdError + 'static)> {
            Some(&self.1)
        }
    }

    // 1. The #1045 incident: opaque transport error, `source() == None` → Connect.
    #[test]
    fn incident_1045_opaque_no_source_is_connect() {
        let err = Opaque("error sending request for url (https://x.bastion.azure.com/api/tokens)");
        assert!(
            err.source().is_none(),
            "incident double must have no source"
        );
        assert_eq!(classify_transport_error(&err), TunnelFailureKind::Connect);
    }

    // 2. DNS resolution failure → Dns.
    #[test]
    fn dns_failure_is_dns() {
        let err = Wrapped(
            "error sending request for url (https://x.bastion.azure.com/api/tokens)",
            Opaque("failed to lookup address information: Name or service not known"),
        );
        assert_eq!(classify_transport_error(&err), TunnelFailureKind::Dns);
    }

    // 3. TLS handshake failure → Tls.
    #[test]
    fn tls_failure_is_tls() {
        let err = Wrapped(
            "error sending request",
            Opaque("invalid certificate: tls handshake eof"),
        );
        assert_eq!(classify_transport_error(&err), TunnelFailureKind::Tls);
    }

    // 4. Timeout → Timeout.
    #[test]
    fn timeout_is_timeout() {
        let err = Opaque("operation timed out");
        assert_eq!(classify_transport_error(&err), TunnelFailureKind::Timeout);
    }

    // 5. Connection refused → Connect.
    #[test]
    fn connection_refused_is_connect() {
        let err = Wrapped(
            "error sending request",
            Opaque("tcp connect error: Connection refused (os error 111)"),
        );
        assert_eq!(classify_transport_error(&err), TunnelFailureKind::Connect);
    }

    // 6. HTTP status mapping; a transport failure is never classified as Auth.
    #[test]
    fn http_status_classification() {
        assert_eq!(classify_http_status(401), TunnelFailureKind::Auth);
        assert_eq!(classify_http_status(403), TunnelFailureKind::Auth);
        assert_eq!(classify_http_status(500), TunnelFailureKind::Http);
        assert_eq!(classify_http_status(404), TunnelFailureKind::Http);
        let err = Opaque("error sending request for url (...)");
        assert_ne!(classify_transport_error(&err), TunnelFailureKind::Auth);
    }

    // 7. Every kind yields a non-empty, secret-free remediation hint, and the
    //    rendered `[KIND: hint]` suffix never contains a token value.
    #[test]
    fn remediation_hints_are_present_and_leak_free() {
        const TOKEN: &str = "SUPER-SECRET-TOKEN-abc123";
        for kind in [
            TunnelFailureKind::Connect,
            TunnelFailureKind::Dns,
            TunnelFailureKind::Tls,
            TunnelFailureKind::Timeout,
            TunnelFailureKind::Http,
            TunnelFailureKind::Auth,
            TunnelFailureKind::Parse,
        ] {
            let hint = remediation_hint(kind);
            assert!(!hint.is_empty(), "hint for {kind} must not be empty");
            let rendered = format!("[{kind}: {hint}]");
            assert!(
                !rendered.contains(TOKEN),
                "rendered hint must be secret-free: {rendered}"
            );
        }
    }
}

// ── WSS URL redaction tests (issue #1056) ────────────────────────────────────
//
// TDD (write-tests-first) contract for `redact_wss_url` and the WSS-connect
// `warn!` scrubbing pipeline. The bastion tunnel URL carries the short-lived
// `websocketToken` bearer secret as a PATH SEGMENT (`/webtunnelv2/<TOKEN>` for
// Standard/Premium, `/omni/webtunnel/<TOKEN>` for Developer/QuickConnect). A
// failed `connect_async` produces a `tungstenite` error whose `Display` can
// embed the full connect URL; rendering it into a `tracing`/OTel sink would
// leak the token. These tests pin the guarantee that the token can NEVER reach
// a log sink regardless of upstream `Display` behaviour:
//
//   * `redact_wss_url` masks the token segment for every known tunnel shape,
//   * it is FAIL-CLOSED: any unrecognized input is masked to the fixed sentinel
//     `wss://<redacted>` and never echoed back (no partial leak),
//   * the call-site scrub (`err.replace(&wss_url, &redact_wss_url(&wss_url))`)
//     removes the token from a rendered error that embeds the raw URL,
//   * host/`X-Node-Id` diagnostics are preserved so logs stay useful.
//
// The token-absence assertions also serve as regression guards: any future
// change that re-introduces the raw token into the redacted/logged output
// turns these RED.
#[cfg(test)]
mod redaction_tests {
    use super::*;

    /// A recognizable, structurally-simple secret so any leak is unambiguous in
    /// assertion output. Contains no URL-reserved characters, so it survives
    /// `urlencoding::encode` verbatim and appears literally in the built URL.
    const TOKEN: &str = "SUPERSECRETwebsocketTOKEN0123456789abcdef";
    const ENDPOINT: &str = "bst-abc123.bastion.azure.com";
    const NODE_ID: &str = "node-42";

    /// Fixed sentinel the fail-closed path must emit for unrecognized input.
    const SENTINEL: &str = "wss://<redacted>";

    // 1. Standard/Premium URL: the token segment is masked while scheme, host,
    //    and the non-secret `X-Node-Id` query parameter survive for diagnostics.
    #[test]
    fn redacts_standard_url_token_but_keeps_host_and_node_id() {
        let url = build_wss_url_standard(ENDPOINT, TOKEN, NODE_ID);
        // Precondition: the raw URL really does carry the secret (guards the test).
        assert!(
            url.contains(TOKEN),
            "precondition: raw standard URL must embed the token"
        );

        let redacted = redact_wss_url(&url);

        assert!(
            !redacted.contains(TOKEN),
            "token leaked into redacted standard URL: {redacted}"
        );
        assert!(
            redacted.contains(ENDPOINT),
            "host must be preserved for diagnostics: {redacted}"
        );
        assert!(
            redacted.contains("X-Node-Id="),
            "non-secret X-Node-Id query must be preserved: {redacted}"
        );
        assert!(
            redacted.starts_with("wss://") && redacted.contains("/webtunnelv2/"),
            "redacted URL must keep its recognizable tunnel shape: {redacted}"
        );
        assert_ne!(redacted, SENTINEL, "a known shape must not fail closed");
    }

    // 2. Developer/QuickConnect URL: the token segment is masked; host survives.
    #[test]
    fn redacts_developer_url_token_but_keeps_host() {
        let url = build_wss_url_developer(ENDPOINT, TOKEN);
        assert!(
            url.contains(TOKEN),
            "precondition: raw developer URL must embed the token"
        );

        let redacted = redact_wss_url(&url);

        assert!(
            !redacted.contains(TOKEN),
            "token leaked into redacted developer URL: {redacted}"
        );
        assert!(
            redacted.contains(ENDPOINT),
            "host must be preserved: {redacted}"
        );
        assert!(
            redacted.contains("/omni/webtunnel/"),
            "redacted URL must keep its recognizable tunnel shape: {redacted}"
        );
        assert_ne!(redacted, SENTINEL, "a known shape must not fail closed");
    }

    // 3. FAIL-CLOSED: a non-`wss://` scheme (e.g. the auth token cleanup URL,
    //    or anything else) is masked to the sentinel with no part echoed back.
    #[test]
    fn non_wss_scheme_fails_closed_to_sentinel() {
        let url = format!("https://{ENDPOINT}/api/tokens/{TOKEN}");
        let redacted = redact_wss_url(&url);
        assert_eq!(
            redacted, SENTINEL,
            "non-wss input must fail closed to the sentinel"
        );
        assert!(
            !redacted.contains(TOKEN) && !redacted.contains(ENDPOINT),
            "fail-closed sentinel must echo NOTHING from the input: {redacted}"
        );
    }

    // 4. FAIL-CLOSED: a `wss://` URL of an UNKNOWN path shape (no known tunnel
    //    marker) must not be partially echoed — it collapses to the sentinel.
    #[test]
    fn unknown_wss_shape_fails_closed_to_sentinel() {
        let url = format!("wss://{ENDPOINT}/some/other/path/{TOKEN}");
        let redacted = redact_wss_url(&url);
        assert_eq!(
            redacted, SENTINEL,
            "unrecognized wss shape must fail closed"
        );
        assert!(
            !redacted.contains(TOKEN),
            "unrecognized wss shape must not leak the token: {redacted}"
        );
    }

    // 5. FAIL-CLOSED against path-injection: if the "host" position contains a
    //    `/` (i.e. the marker was found but the authority is not a bare host),
    //    the input is rejected rather than emitting a malformed/partial URL.
    #[test]
    fn marker_with_non_bare_host_fails_closed() {
        // `/webtunnelv2/` appears but is preceded by a path, so `host` contains `/`.
        let url = format!("wss://{ENDPOINT}/evil/webtunnelv2/{TOKEN}");
        let redacted = redact_wss_url(&url);
        assert_eq!(
            redacted, SENTINEL,
            "a non-bare host before the marker must fail closed"
        );
        assert!(
            !redacted.contains(TOKEN),
            "path-injection shape must not leak the token: {redacted}"
        );
    }

    // 6. Idempotence: redacting an already-redacted URL is stable and never
    //    reintroduces or exposes a secret.
    #[test]
    fn redaction_is_idempotent() {
        let url = build_wss_url_standard(ENDPOINT, TOKEN, NODE_ID);
        let once = redact_wss_url(&url);
        let twice = redact_wss_url(&once);
        assert_eq!(
            once, twice,
            "redaction must be idempotent: {once} != {twice}"
        );
        assert!(!twice.contains(TOKEN), "re-redaction must stay leak-free");
    }

    // 7. Call-site scrub pipeline (native_tunnel WSS-connect `warn!`, line ~528):
    //    a `tungstenite`-style error whose `Display` embeds the full connect URL
    //    must have the raw URL replaced by its redacted form so the rendered,
    //    to-be-logged string carries NO token — regardless of upstream Display.
    #[test]
    fn call_site_scrub_removes_token_from_rendered_error() {
        for url in [
            build_wss_url_standard(ENDPOINT, TOKEN, NODE_ID),
            build_wss_url_developer(ENDPOINT, TOKEN),
        ] {
            // Model the worst case: the transport error Display echoes the URL.
            let raw_error_display =
                format!("WebSocket protocol error: Connection refused for url ({url})");
            assert!(
                raw_error_display.contains(TOKEN),
                "precondition: worst-case error Display embeds the token"
            );

            // This mirrors the exact scrub applied at the `warn!` call site.
            let redacted_url = redact_wss_url(&url);
            let safe_err = raw_error_display.replace(&url, &redacted_url);

            assert!(
                !safe_err.contains(TOKEN),
                "websocket_token leaked into the WSS-connect warn! output: {safe_err}"
            );
            // The diagnostic shell of the error is retained.
            assert!(
                safe_err.contains("Connection refused"),
                "scrub must preserve the non-secret error context: {safe_err}"
            );
        }
    }

    // 8. Defense-in-depth: even if the upstream error Display does NOT contain
    //    the URL at all (so `.replace` is a no-op), the token must still be
    //    absent from what gets logged — i.e. the raw error alone is token-free.
    #[test]
    fn error_without_url_display_is_already_token_free() {
        let url = build_wss_url_standard(ENDPOINT, TOKEN, NODE_ID);
        // A realistic opaque tungstenite error that never renders the URL.
        let raw_error_display = "IO error: Connection reset by peer (os error 104)".to_string();
        let redacted_url = redact_wss_url(&url);
        let safe_err = raw_error_display.replace(&url, &redacted_url);
        assert!(
            !safe_err.contains(TOKEN),
            "token must never appear when the error omits the URL: {safe_err}"
        );
    }
}
