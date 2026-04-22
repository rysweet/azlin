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
use tracing::{debug, warn};

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

/// Build the JSON body for the token exchange POST request.
pub fn build_token_exchange_body(
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
) -> String {
    let body = serde_json::json!({
        "resourceId": target_resource_id,
        "protocol": "tcptunnel",
        "workloadHostPort": resource_port.to_string(),
        "aztoken": token,
        "token": token,
    });
    body.to_string()
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

// ── Token exchange ───────────────────────────────────────────────────────

async fn exchange_token(
    client: &reqwest::Client,
    endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
) -> Result<BastionTokenResponse, NativeTunnelError> {
    let url = build_token_exchange_url(endpoint);
    let body = build_token_exchange_body(target_resource_id, resource_port, token);

    let resp = client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {}", token))
        .body(body)
        .send()
        .await
        .map_err(|e| NativeTunnelError::TokenExchange(format!("request failed: {e}")))?;

    if !resp.status().is_success() {
        let status = resp.status();
        let body_text = resp.text().await.unwrap_or_default();
        return Err(NativeTunnelError::TokenExchange(format!(
            "HTTP {status}: {body_text}"
        )));
    }

    resp.json::<BastionTokenResponse>()
        .await
        .map_err(|e| NativeTunnelError::TokenExchange(format!("failed to parse response: {e}")))
}

/// Best-effort token cleanup via DELETE.
async fn cleanup_token(
    client: &reqwest::Client,
    endpoint: &str,
    auth_token: &str,
    node_id: &str,
) {
    let url = build_token_cleanup_url(endpoint, auth_token);
    let _ = client
        .delete(&url)
        .header(NODE_ID_HEADER, node_id)
        .send()
        .await;
}

// ── Bidirectional forwarding ─────────────────────────────────────────────

/// Forward data bidirectionally between a TCP stream and a WebSocket connection.
///
/// This is the core forwarding loop: TCP bytes → WSS binary frames, and
/// WSS binary frames → TCP bytes. Runs until either side closes or errors.
pub async fn forward_tcp_to_ws(
    tcp_stream: TcpStream,
    ws_stream: tokio_tungstenite::WebSocketStream<
        tokio_tungstenite::MaybeTlsStream<TcpStream>,
    >,
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
                    if ws_sink
                        .send(Message::Binary(data.into()))
                        .await
                        .is_err()
                    {
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
                Ok(Message::Binary(data)) => {
                    if tcp_writer.write_all(&data).await.is_err() {
                        break;
                    }
                }
                Ok(Message::Close(_)) | Err(_) => break,
                _ => {} // ignore ping/pong/text
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
        WssUrlMode::NodeScoped => build_wss_url_standard(
            &endpoint,
            &token_resp.websocket_token,
            &token_resp.node_id,
        ),
        WssUrlMode::EndpointScoped => build_wss_url_developer(
            &endpoint,
            &token_resp.websocket_token,
        ),
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
        .connect_timeout(timeout)
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
                        handle_client(tcp_stream, client, ep, rid, resource_port, tok, url_mode).await;
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
