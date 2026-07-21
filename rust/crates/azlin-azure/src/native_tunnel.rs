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

use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener as TokioTcpListener;
use tokio::net::TcpStream;
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
    token: String,
    url_mode: WssUrlMode,
) {
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
            warn!("bastion WSS connect failed: {e}");
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
    open_tunnel_with_timeouts(
        bastion_endpoint,
        target_resource_id,
        resource_port,
        token,
        url_mode,
        timeout,
        timeout,
    )
    .await
}

/// Open a native bastion tunnel with separate overall and connect timeouts.
///
/// Identical to [`open_tunnel`], but lets the caller configure the TCP
/// `connect_timeout` independently of the overall request `timeout`. This backs
/// the optional `bastion_connect_timeout` config knob (issue #1045) without
/// changing the stable [`open_tunnel`] signature.
///
/// # Arguments
/// - `connect_timeout` — Timeout for establishing the TCP connection to the
///   bastion data-plane. Defaults (via [`open_tunnel`]) to `timeout`.
///
/// See [`open_tunnel`] for the remaining arguments and security notes.
#[allow(clippy::too_many_arguments)]
pub async fn open_tunnel_with_timeouts(
    bastion_endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
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
    if token.is_empty() {
        return Err(NativeTunnelError::InvalidEndpoint(
            "token must not be empty".to_string(),
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

    // Verify connectivity with a quick token exchange + cleanup
    let test_result = tokio::time::timeout(
        timeout,
        exchange_token(&client, &endpoint, target_resource_id, resource_port, token),
    )
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
    let owned_token = token.to_string();
    let handle = tokio::spawn(async move {
        loop {
            match listener.accept().await {
                Ok((tcp_stream, peer)) => {
                    debug!("bastion tunnel accepted TCP connection from {peer}");
                    let client = client.clone();
                    let ep = owned_endpoint.clone();
                    let rid = owned_resource_id.clone();
                    let tok = owned_token.clone();
                    tokio::spawn(async move {
                        handle_client(tcp_stream, client, ep, rid, resource_port, tok, url_mode)
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
