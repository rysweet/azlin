//! Unit tests for azlin_azure::native_tunnel module.
//!
//! TDD: These tests define the contract for the native WebSocket bastion tunnel.
//! They will fail until the implementation is complete.
//!
//! Test categories:
//!   1. Module existence and type exports
//!   2. URL construction (Standard vs Developer SKU)
//!   3. Token exchange request building
//!   4. Security invariants (TLS enforcement, localhost binding)
//!   5. Error handling (timeout, bad response, scheme rejection)
//!   6. Bidirectional forwarding (mock WSS ↔ TCP)

// ═══════════════════════════════════════════════════════════════════════
// 1. Module existence and public type exports
// ═══════════════════════════════════════════════════════════════════════

/// The native_tunnel module must exist and be publicly exported.
#[test]
fn test_native_tunnel_module_exists() {
    // This will fail to compile until the module is created and exported.
    let _ = std::any::type_name::<azlin_azure::native_tunnel::NativeTunnelError>();
}

/// NativeTunnelError must be a public error enum.
#[test]
fn test_native_tunnel_error_type_exists() {
    // Must implement std::error::Error + Send + Sync
    fn assert_error<T: std::error::Error + Send + Sync>() {}
    assert_error::<azlin_azure::native_tunnel::NativeTunnelError>();
}

/// open_tunnel function must have the expected async signature.
/// We verify it exists by referencing it (compilation test).
#[tokio::test]
async fn test_open_tunnel_function_signature_exists() {
    // Verify the function exists and is callable with correct arg types.
    // We pass invalid inputs so it returns an error immediately (no real bastion needed).
    let result = azlin_azure::native_tunnel::open_tunnel(
        "", // empty endpoint → InvalidEndpoint error
        "test-resource-id",
        22,
        "test-token",
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(1),
    )
    .await;
    assert!(result.is_err(), "empty endpoint should error");
}

// ═══════════════════════════════════════════════════════════════════════
// 2. URL construction
// ═══════════════════════════════════════════════════════════════════════

/// Token exchange URL must be https://{endpoint}/api/tokens
#[test]
fn test_token_exchange_url_construction() {
    let url = azlin_azure::native_tunnel::build_token_exchange_url("bastion-host.example.com");
    assert_eq!(url, "https://bastion-host.example.com/api/tokens");
}

/// Standard/Premium SKU WSS URL: wss://{endpoint}/webtunnelv2/{ws_token}?X-Node-Id={node_id}
#[test]
fn test_standard_sku_wss_url_construction() {
    let url = azlin_azure::native_tunnel::build_wss_url_standard(
        "bastion-host.example.com",
        "ws-token-abc123",
        "node-xyz",
    );
    assert_eq!(
        url,
        "wss://bastion-host.example.com/webtunnelv2/ws-token-abc123?X-Node-Id=node-xyz"
    );
}

/// Developer/QuickConnect SKU WSS URL: wss://{endpoint}/omni/webtunnel/{ws_token}
#[test]
fn test_developer_sku_wss_url_construction() {
    let url = azlin_azure::native_tunnel::build_wss_url_developer(
        "datapod.example.com",
        "ws-token-def456",
    );
    assert_eq!(
        url,
        "wss://datapod.example.com/omni/webtunnel/ws-token-def456"
    );
}

/// Token cleanup URL must be https://{endpoint}/api/tokens/{auth_token}
#[test]
fn test_token_cleanup_url_construction() {
    let url = azlin_azure::native_tunnel::build_token_cleanup_url(
        "bastion-host.example.com",
        "auth-token-789",
    );
    assert_eq!(
        url,
        "https://bastion-host.example.com/api/tokens/auth-token-789"
    );
}

/// URL-encode special characters in ws_token to prevent path injection (SEC-2).
#[test]
fn test_wss_url_encodes_special_chars_in_token() {
    let url = azlin_azure::native_tunnel::build_wss_url_standard(
        "bastion.example.com",
        "token/with/../traversal",
        "node-1",
    );
    // The token part must be URL-encoded so slashes become %2F
    assert!(!url.contains("token/with"));
    assert!(url.contains("token%2Fwith"));
}

/// URL-encode special characters in node_id.
#[test]
fn test_wss_url_encodes_special_chars_in_node_id() {
    let url = azlin_azure::native_tunnel::build_wss_url_standard(
        "bastion.example.com",
        "normal-token",
        "node&id=bad",
    );
    assert!(!url.contains("node&id=bad"));
    assert!(url.contains("node%26id%3Dbad"));
}

// ═══════════════════════════════════════════════════════════════════════
// 3. Token exchange request building
// ═══════════════════════════════════════════════════════════════════════

/// Token exchange request must be form-encoded with the correct fields.
#[test]
fn test_token_exchange_request_body() {
    let form = azlin_azure::native_tunnel::build_token_exchange_form(
        "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        22,
        "bearer-token-xyz",
    );

    let get = |k: &str| {
        form.iter()
            .find(|(key, _)| *key == k)
            .map(|(_, v)| v.as_str())
    };

    assert_eq!(
        get("resourceId"),
        Some("/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1")
    );
    assert_eq!(get("protocol"), Some("tcptunnel"));
    assert_eq!(get("workloadHostPort"), Some("22"));
    // The ARM token is carried in `aztoken`, NOT an Authorization header.
    assert_eq!(get("aztoken"), Some("bearer-token-xyz"));
    // The `token` field is omitted on the initial exchange (mirrors azext_bastion,
    // which sends last_token=None). It must never carry the ARM bearer token.
    assert_eq!(get("token"), None);
}

/// BastionTokenResponse must deserialize from the expected JSON shape.
#[test]
fn test_bastion_token_response_deserialization() {
    let json = r#"{
        "authToken": "auth-abc",
        "nodeId": "node-123",
        "websocketToken": "ws-def"
    }"#;
    let resp: azlin_azure::native_tunnel::BastionTokenResponse =
        serde_json::from_str(json).expect("must deserialize BastionTokenResponse");
    assert_eq!(resp.auth_token, "auth-abc");
    assert_eq!(resp.node_id, "node-123");
    assert_eq!(resp.websocket_token, "ws-def");
}

/// BastionTokenResponse must handle missing fields gracefully.
#[test]
fn test_bastion_token_response_rejects_missing_fields() {
    let json = r#"{"authToken": "auth-abc"}"#;
    let result: Result<azlin_azure::native_tunnel::BastionTokenResponse, _> =
        serde_json::from_str(json);
    assert!(
        result.is_err(),
        "BastionTokenResponse must require all three fields"
    );
}

// ═══════════════════════════════════════════════════════════════════════
// 4. Security invariants
// ═══════════════════════════════════════════════════════════════════════

/// SEC-3: Reject non-TLS endpoint URLs at open_tunnel entry.
#[tokio::test]
async fn test_reject_http_endpoint() {
    let result = azlin_azure::native_tunnel::open_tunnel(
        "http://bastion.example.com", // http:// not https://
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        "token",
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(5),
    )
    .await;
    assert!(result.is_err(), "must reject non-TLS endpoint");
    let err = result.unwrap_err();
    let msg = format!("{}", err);
    assert!(
        msg.to_lowercase().contains("tls")
            || msg.to_lowercase().contains("https")
            || msg.to_lowercase().contains("scheme"),
        "error message should mention TLS/HTTPS requirement, got: {}",
        msg
    );
}

/// SEC-3: Reject ws:// (non-TLS) endpoint URLs.
#[tokio::test]
async fn test_reject_ws_endpoint() {
    let result = azlin_azure::native_tunnel::open_tunnel(
        "ws://bastion.example.com",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        "token",
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(5),
    )
    .await;
    assert!(result.is_err(), "must reject ws:// endpoint");
}

/// SEC-3: Accept bare hostname (assumes https://).
#[tokio::test]
async fn test_bare_hostname_treated_as_https() {
    // This will fail to connect (no real bastion), but should NOT fail with
    // a scheme-rejection error. It should fail with a connection error instead.
    let result = azlin_azure::native_tunnel::open_tunnel(
        "bastion.example.com",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        "token",
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(1),
    )
    .await;
    // Should fail with connection error, not scheme error
    assert!(result.is_err());
    let err = format!("{}", result.unwrap_err());
    assert!(
        !err.to_lowercase().contains("scheme") && !err.to_lowercase().contains("tls"),
        "bare hostname should be treated as https, not rejected for bad scheme; got: {}",
        err
    );
}

/// SEC-4: The local TCP listener must bind to 127.0.0.1, never 0.0.0.0.
/// We verify this by checking that the returned port is only reachable on loopback.
/// (Implementation detail: open_tunnel must use 127.0.0.1 for TcpListener::bind.)
#[tokio::test]
async fn test_local_listener_binds_loopback_only() {
    // We can't easily test this without a real tunnel, but we can test the
    // helper function that creates the listener.
    let listener =
        azlin_azure::native_tunnel::bind_local_listener().expect("must bind local listener");
    let addr = listener.local_addr().expect("must have local addr");
    assert!(
        addr.ip().is_loopback(),
        "local listener must bind to loopback, got: {}",
        addr.ip()
    );
    assert_ne!(addr.port(), 0, "must have assigned a real port");
}

// ═══════════════════════════════════════════════════════════════════════
// 5. Error handling
// ═══════════════════════════════════════════════════════════════════════

/// NativeTunnelError must have a TokenExchange variant.
#[test]
fn test_error_has_token_exchange_variant() {
    let err =
        azlin_azure::native_tunnel::NativeTunnelError::TokenExchange("mock failure".to_string());
    let msg = format!("{}", err);
    assert!(
        msg.contains("mock failure") || msg.contains("token"),
        "TokenExchange error should contain context"
    );
}

/// NativeTunnelError must have a WebSocket variant.
#[test]
fn test_error_has_websocket_variant() {
    let err =
        azlin_azure::native_tunnel::NativeTunnelError::WebSocket("connection reset".to_string());
    let msg = format!("{}", err);
    assert!(!msg.is_empty());
}

/// NativeTunnelError must have a Timeout variant.
#[test]
fn test_error_has_timeout_variant() {
    let err =
        azlin_azure::native_tunnel::NativeTunnelError::Timeout(std::time::Duration::from_secs(30));
    let msg = format!("{}", err);
    assert!(msg.contains("30") || msg.to_lowercase().contains("timeout"));
}

/// NativeTunnelError must have an InvalidEndpoint variant for SEC-3.
#[test]
fn test_error_has_invalid_endpoint_variant() {
    let err =
        azlin_azure::native_tunnel::NativeTunnelError::InvalidEndpoint("http://bad".to_string());
    let msg = format!("{}", err);
    assert!(!msg.is_empty());
}

// ═══════════════════════════════════════════════════════════════════════
// 6. Bidirectional forwarding (integration with mock server)
// ═══════════════════════════════════════════════════════════════════════

/// When a TCP client connects to the local port, the tunnel must perform
/// token exchange and WSS connect. Since we can't mock the bastion here,
/// we test the lower-level forward_tcp_ws helper with a real WSS echo server.
///
/// This test starts a local TCP echo server → WSS echo server pipeline and
/// verifies data flows both directions.
#[tokio::test]
async fn test_forward_bidirectional_with_echo() {
    // This test requires the implementation to expose a testable forwarding
    // primitive. It will fail until forward_tcp_to_ws is implemented.
    //
    // The test plan:
    // 1. Start a local TCP listener (mock "upstream" for WSS)
    // 2. Start a local WebSocket echo server
    // 3. Call the forwarding function connecting TCP↔WSS
    // 4. Send data from TCP side, verify it echoes back via WSS→TCP
    //
    // For now, we just verify the function exists with correct types.
    // Full integration test will be done with a mock server.
    let _fn_exists = azlin_azure::native_tunnel::forward_tcp_to_ws;
}

/// Verify that the token cleanup function constructs the correct DELETE request.
/// (We test the URL builder; actual HTTP call is tested via integration.)
#[test]
fn test_token_cleanup_url_includes_node_id_header_name() {
    // The cleanup must send X-Node-Id header. We test that the header constant
    // is correct by checking the module exports it.
    assert_eq!(azlin_azure::native_tunnel::NODE_ID_HEADER, "X-Node-Id");
}

// ═══════════════════════════════════════════════════════════════════════
// 7. Port 0 / resource_port validation
// ═══════════════════════════════════════════════════════════════════════

/// resource_port=0 should be rejected (not a valid SSH port).
#[tokio::test]
async fn test_reject_resource_port_zero() {
    let result = azlin_azure::native_tunnel::open_tunnel(
        "bastion.example.com",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        0, // invalid port
        "token",
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(1),
    )
    .await;
    assert!(result.is_err(), "resource_port=0 must be rejected");
}

/// Empty bastion_endpoint should be rejected.
#[tokio::test]
async fn test_reject_empty_endpoint() {
    let result = azlin_azure::native_tunnel::open_tunnel(
        "",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        "token",
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(1),
    )
    .await;
    assert!(result.is_err(), "empty endpoint must be rejected");
}

/// Empty token should be rejected.
#[tokio::test]
async fn test_reject_empty_token() {
    let result = azlin_azure::native_tunnel::open_tunnel(
        "bastion.example.com",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        "", // empty token
        azlin_azure::native_tunnel::WssUrlMode::NodeScoped,
        std::time::Duration::from_secs(1),
    )
    .await;
    assert!(result.is_err(), "empty token must be rejected");
}

// ═══════════════════════════════════════════════════════════════════════
// 8. WssUrlMode routing
// ═══════════════════════════════════════════════════════════════════════

/// NodeScoped mode must produce a /webtunnelv2/ URL with X-Node-Id query param.
#[test]
fn test_node_scoped_url_uses_webtunnelv2_path() {
    let url = azlin_azure::native_tunnel::build_wss_url_standard(
        "bastion.example.com",
        "ws-tok",
        "node-1",
    );
    assert!(
        url.contains("/webtunnelv2/"),
        "NodeScoped must use /webtunnelv2/ path"
    );
    assert!(
        url.contains("X-Node-Id="),
        "NodeScoped must include X-Node-Id query param"
    );
}

/// EndpointScoped mode must produce a /omni/webtunnel/ URL without X-Node-Id.
#[test]
fn test_endpoint_scoped_url_uses_omni_path() {
    let url = azlin_azure::native_tunnel::build_wss_url_developer("datapod.example.com", "ws-tok");
    assert!(
        url.contains("/omni/webtunnel/"),
        "EndpointScoped must use /omni/webtunnel/ path"
    );
    assert!(
        !url.contains("X-Node-Id"),
        "EndpointScoped must not include X-Node-Id"
    );
}

/// WssUrlMode enum must have exactly NodeScoped and EndpointScoped variants.
#[test]
fn test_wss_url_mode_variants_exist() {
    let _ns = azlin_azure::native_tunnel::WssUrlMode::NodeScoped;
    let _es = azlin_azure::native_tunnel::WssUrlMode::EndpointScoped;
    assert_ne!(_ns, _es);
}

// ═══════════════════════════════════════════════════════════════════════
// 9. WSS URL redaction (issue #1056)
//
// The `wss://` tunnel URL embeds the short-lived `websocketToken` as a path
// segment (Standard/Premium) or as the final path segment (Developer). Before
// this fix, a failed WSS connect/reconnect/close rendered the `tungstenite`
// error (which embeds the full URL) straight into a `tracing` sink, leaking the
// bearer secret into log files and OTel exporters.
//
// `redact_wss_url(&str) -> String` returns a log-safe rendering that masks the
// token while preserving scheme, host, and the non-secret `X-Node-Id`. It is
// fail-closed: input that does not match a known tunnel URL shape is masked to
// `wss://<redacted>`. The live connection is unaffected — `connect_async` still
// receives the real, unredacted URL.
//
// These tests mirror `test_cleanup_error_without_url_does_not_leak_auth_token`
// in `src/native_tunnel.rs` (the cleanup-path token-leak regression test) but
// cover the WSS-connect leak site.
// ═══════════════════════════════════════════════════════════════════════

/// Primary contract (issue #1056): the redacted form of a Standard/Premium SKU
/// WSS URL must never contain the `websocketToken`, raw or URL-encoded, while
/// keeping scheme, host, node id, and a `***` mask marker.
#[test]
fn test_redact_wss_url_never_leaks_websocket_token() {
    const TOKEN: &str = "SUPER-SECRET-WS-TOKEN-9f8e7d6c";
    let url = azlin_azure::native_tunnel::build_wss_url_standard("host.example", TOKEN, "node-42");

    // Precondition: the raw URL carries the token (this is exactly what the
    // fix guards against being logged).
    let encoded = urlencoding::encode(TOKEN).into_owned();
    assert!(
        url.contains(TOKEN) || url.contains(&encoded),
        "precondition: raw wss_url is expected to embed the websocket token"
    );

    let redacted = azlin_azure::native_tunnel::redact_wss_url(&url);

    // The redacted form must never contain the token (raw or encoded).
    assert!(
        !redacted.contains(TOKEN),
        "websocket token leaked (raw) into redacted url: {redacted}"
    );
    assert!(
        !redacted.contains(encoded.as_str()),
        "websocket token leaked (url-encoded) into redacted url: {redacted}"
    );

    // Non-secret structure is preserved for diagnostic value.
    assert!(
        redacted.starts_with("wss://host.example/webtunnelv2/"),
        "redacted url must preserve scheme/host/path shape: {redacted}"
    );
    assert!(
        redacted.contains("X-Node-Id=node-42"),
        "redacted url must retain the non-secret node id: {redacted}"
    );
    assert!(
        redacted.contains("***"),
        "redacted url must include the mask marker: {redacted}"
    );
}

/// Developer/QuickConnect (EndpointScoped) SKU: `wss://host/omni/webtunnel/<TOKEN>`
/// must have its final-segment token masked; there is no node id to preserve.
#[test]
fn test_redact_wss_url_developer_sku_masks_token() {
    const TOKEN: &str = "DEV-WS-TOKEN-abcdef123456";
    let url = azlin_azure::native_tunnel::build_wss_url_developer("datapod.example", TOKEN);

    let redacted = azlin_azure::native_tunnel::redact_wss_url(&url);

    assert!(
        !redacted.contains(TOKEN),
        "developer-sku websocket token leaked into redacted url: {redacted}"
    );
    assert!(
        redacted.starts_with("wss://datapod.example/omni/webtunnel/"),
        "redacted developer url must preserve scheme/host/path shape: {redacted}"
    );
    assert!(
        redacted.contains("***"),
        "redacted developer url must include the mask marker: {redacted}"
    );
}

/// URL-encoding aware: a token with special characters (which
/// `build_wss_url_standard` percent-encodes per SEC-2) must not slip through in
/// either its raw or its percent-encoded form.
#[test]
fn test_redact_wss_url_masks_encoded_special_char_token() {
    const TOKEN: &str = "tok/with+weird=chars&and space";
    let url = azlin_azure::native_tunnel::build_wss_url_standard("host.example", TOKEN, "node-7");
    let encoded = urlencoding::encode(TOKEN).into_owned();

    // Precondition: the encoded token is what actually lands in the URL.
    assert!(
        url.contains(&encoded),
        "precondition: encoded token should be present in the raw url"
    );

    let redacted = azlin_azure::native_tunnel::redact_wss_url(&url);

    assert!(
        !redacted.contains(TOKEN),
        "raw special-char token leaked into redacted url: {redacted}"
    );
    assert!(
        !redacted.contains(encoded.as_str()),
        "encoded special-char token leaked into redacted url: {redacted}"
    );
    assert!(
        redacted.contains("X-Node-Id=node-7"),
        "redacted url must retain the node id: {redacted}"
    );
}

/// Fail-closed: input that does not parse as a known tunnel URL shape must be
/// masked aggressively to `wss://<redacted>` rather than echoed back.
#[test]
fn test_redact_wss_url_fail_closed_on_malformed_input() {
    for garbage in [
        "not-a-url",
        "https://host/api/tokens/some-secret",
        "wss://host/unexpected/path/SECRET-LEAK",
        "",
    ] {
        let redacted = azlin_azure::native_tunnel::redact_wss_url(garbage);
        assert_eq!(
            redacted, "wss://<redacted>",
            "malformed input must fail closed to a fixed masked sentinel, got: {redacted}"
        );
    }
}

/// The redaction must be a logging-only control: it must not mutate or shorten
/// the real URL used for the live connection. We assert the real builder output
/// is unchanged by confirming the token is still present in the source URL after
/// redaction (redaction takes `&str` and returns a new String).
#[test]
fn test_redact_wss_url_does_not_mutate_source_url() {
    const TOKEN: &str = "LIVE-CONNECTION-TOKEN-0011";
    let url = azlin_azure::native_tunnel::build_wss_url_standard("host.example", TOKEN, "node-9");
    let before = url.clone();
    let _ = azlin_azure::native_tunnel::redact_wss_url(&url);
    assert_eq!(
        url, before,
        "redact_wss_url must not mutate the caller's real, token-bearing url"
    );
    assert!(
        url.contains(TOKEN),
        "the real url handed to connect_async must still carry the token"
    );
}

/// Redaction is idempotent: re-scrubbing an already-redacted URL is stable and
/// still leaks nothing, so a double-log path can never expose the token.
#[test]
fn test_redact_wss_url_is_idempotent_and_secret_free() {
    const TOKEN: &str = "IDEMPOTENT-WS-TOKEN-55aa";
    let url = azlin_azure::native_tunnel::build_wss_url_standard("host.example", TOKEN, "node-3");

    let once = azlin_azure::native_tunnel::redact_wss_url(&url);
    let twice = azlin_azure::native_tunnel::redact_wss_url(&once);

    assert_eq!(
        once, twice,
        "redaction must be idempotent: {once} != {twice}"
    );
    assert!(
        !twice.contains(TOKEN),
        "re-redacting an already-redacted URL must stay secret-free: {twice}"
    );
}

/// The exact WSS-connect `warn!` scrub performed in `handle_client`:
///   let redacted_url = redact_wss_url(&wss_url);
///   let safe_err = e.to_string().replace(&wss_url, &redacted_url);
/// A `tungstenite` error `Display` may echo the full connect URL verbatim; the
/// scrub must strip both the raw URL and the token from the emitted log line
/// while keeping the diagnostic error text.
#[test]
fn test_wss_connect_error_scrub_strips_token_and_raw_url() {
    const TOKEN: &str = "CONNECT-ERR-WS-TOKEN-77dd";
    let wss_url =
        azlin_azure::native_tunnel::build_wss_url_standard("host.example", TOKEN, "node-5");
    let raw_error = format!("WebSocket connection to '{wss_url}' failed: handshake error");
    assert!(
        raw_error.contains(TOKEN),
        "precondition: the raw error render leaks the token"
    );

    let redacted_url = azlin_azure::native_tunnel::redact_wss_url(&wss_url);
    let safe_err = raw_error.replace(&wss_url, &redacted_url);

    assert!(
        !safe_err.contains(TOKEN),
        "scrubbed connect-failure log line must NOT contain the token: {safe_err}"
    );
    assert!(
        !safe_err.contains(&wss_url),
        "scrubbed connect-failure log line must NOT contain the raw URL: {safe_err}"
    );
    assert!(
        safe_err.contains("handshake error"),
        "diagnostic error text must survive the scrub: {safe_err}"
    );
}

// ═══════════════════════════════════════════════════════════════════════
// 10. Adaptive token cache / refresh (issue #1059)
//
// ROOT CAUSE: `open_tunnel_with_timeouts` captured the ARM access token ONCE at
// tunnel creation and cloned that static token into every per-connection
// `handle_client`. Azure AD access tokens expire (~60-90 min), so a long-lived
// in-process tunnel kept its loopback listener up but every NEW connection
// through it failed token exchange with an expired `aztoken`, surfacing as
// `kex_exchange_identification: read: Connection reset by peer` on `azlin connect`.
//
// FIX: the tunnel takes a `TokenProvider` (an async, cheap-to-clone closure
// supplied by the `azlin` crate) and caches the token with its expiry in a
// `TokenCache`. Each connection calls `get_valid_token()` first, which refreshes
// the token adaptively — when `now + margin >= expires_at`, where `margin` is
// derived from the token's own lifetime (NOT a hardcoded TTL / reconnect cap).
// Refresh is single-flight (under a mutex) so concurrent connections trigger at
// most one provider call, and the token value is NEVER logged.
//
// TDD: these tests define the contract for `TokenWithExpiry`, `TokenProvider`,
// and `TokenCache` before those types exist. They will fail to compile until the
// implementation lands, then pass once it does.
// ═══════════════════════════════════════════════════════════════════════

use futures_util::future::BoxFuture;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use azlin_azure::native_tunnel::{NativeTunnelError, TokenCache, TokenProvider, TokenWithExpiry};

/// Build a `TokenProvider` that records how many times it is invoked and always
/// returns `value` with the given `lifetime` (None → unknown expiry).
fn counting_provider(
    calls: Arc<AtomicUsize>,
    value: &'static str,
    lifetime: Option<Duration>,
) -> TokenProvider {
    Arc::new(move || {
        let calls = calls.clone();
        Box::pin(async move {
            calls.fetch_add(1, Ordering::SeqCst);
            let now = Instant::now();
            Ok(TokenWithExpiry {
                value: value.to_string(),
                issued_at: now,
                expires_at: lifetime.map(|d| now + d),
            })
        })
            as BoxFuture<
                'static,
                Result<TokenWithExpiry, azlin_azure::native_tunnel::NativeTunnelError>,
            >
    })
}

/// Like `counting_provider` but sleeps before returning, widening the race
/// window so a single-flight regression (N concurrent refreshes) is observable.
fn slow_counting_provider(
    calls: Arc<AtomicUsize>,
    value: &'static str,
    lifetime: Option<Duration>,
    delay: Duration,
) -> TokenProvider {
    Arc::new(move || {
        let calls = calls.clone();
        Box::pin(async move {
            tokio::time::sleep(delay).await;
            calls.fetch_add(1, Ordering::SeqCst);
            let now = Instant::now();
            Ok(TokenWithExpiry {
                value: value.to_string(),
                issued_at: now,
                expires_at: lifetime.map(|d| now + d),
            })
        })
            as BoxFuture<
                'static,
                Result<TokenWithExpiry, azlin_azure::native_tunnel::NativeTunnelError>,
            >
    })
}

/// A `TokenProvider` that always fails, recording how many times it is invoked.
/// Models a transient `az` hiccup so tests can exercise the fail-safe reuse path.
fn failing_provider(calls: Arc<AtomicUsize>) -> TokenProvider {
    Arc::new(move || {
        let calls = calls.clone();
        Box::pin(async move {
            calls.fetch_add(1, Ordering::SeqCst);
            Err(
                azlin_azure::native_tunnel::NativeTunnelError::TokenExchange(
                    "simulated az failure".to_string(),
                ),
            )
        })
            as BoxFuture<
                'static,
                Result<TokenWithExpiry, azlin_azure::native_tunnel::NativeTunnelError>,
            >
    })
}

/// A `TokenProvider` that hangs far longer than any test's refresh timeout,
/// recording invocation so the timeout path (a wedged `az`) can be exercised
/// without the provider ever returning.
fn hanging_provider(calls: Arc<AtomicUsize>) -> TokenProvider {
    Arc::new(move || {
        let calls = calls.clone();
        Box::pin(async move {
            calls.fetch_add(1, Ordering::SeqCst);
            tokio::time::sleep(Duration::from_secs(3600)).await;
            // Never reached within a test's refresh timeout; typed so the async
            // block resolves to the provider's Result output.
            Err(
                azlin_azure::native_tunnel::NativeTunnelError::TokenExchange(
                    "hanging_provider must never return within a test".to_string(),
                ),
            )
        })
            as BoxFuture<
                'static,
                Result<TokenWithExpiry, azlin_azure::native_tunnel::NativeTunnelError>,
            >
    })
}

/// Seed a cache with a token that is about to expire (well inside any sane
/// refresh margin): issued nearly a full lifetime ago, expiring in a few seconds.
fn about_to_expire(value: &str) -> TokenWithExpiry {
    let now = Instant::now();
    TokenWithExpiry {
        value: value.to_string(),
        issued_at: now - Duration::from_secs(3595),
        expires_at: Some(now + Duration::from_secs(5)),
    }
}

/// Seed a cache with a freshly-minted, comfortably-valid token (just issued,
/// expiring in a full hour).
fn comfortably_valid(value: &str) -> TokenWithExpiry {
    let now = Instant::now();
    TokenWithExpiry {
        value: value.to_string(),
        issued_at: now,
        expires_at: Some(now + Duration::from_secs(3600)),
    }
}

/// Seed a cache with a token that is already past its hard expiry, so a failed
/// or timed-out refresh has no reusable token and must surface the error.
fn already_expired(value: &str) -> TokenWithExpiry {
    let now = Instant::now();
    TokenWithExpiry {
        value: value.to_string(),
        issued_at: now - Duration::from_secs(3600),
        expires_at: Some(now - Duration::from_secs(1)),
    }
}

/// PRIMARY CONTRACT (a): a cache seeded with an about-to-expire token must
/// perform EXACTLY ONE provider refresh before the next `get_valid_token()`
/// returns, and must return the freshly-refreshed value — proving a long-lived
/// tunnel's next connection uses a valid token instead of the stale one.
#[tokio::test]
async fn test_cache_refreshes_before_next_exchange_when_about_to_expire() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = counting_provider(
        calls.clone(),
        "FRESH-TOKEN-AFTER-REFRESH",
        Some(Duration::from_secs(3600)),
    );

    let cache = TokenCache::with_token(provider, about_to_expire("STALE-ABOUT-TO-EXPIRE"));

    let token = cache
        .get_valid_token()
        .await
        .expect("get_valid_token should succeed");

    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "an about-to-expire token must trigger exactly one adaptive refresh"
    );
    assert_eq!(
        token, "FRESH-TOKEN-AFTER-REFRESH",
        "get_valid_token must return the refreshed value, not the stale one"
    );
}

/// A comfortably-valid token must NOT trigger a provider call: the adaptive
/// margin is derived from lifetime and must leave a freshly-issued token alone,
/// so steady-state connections never shell out to `az`.
#[tokio::test]
async fn test_cache_does_not_refresh_when_token_is_fresh() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = counting_provider(
        calls.clone(),
        "SHOULD-NEVER-BE-RETURNED",
        Some(Duration::from_secs(3600)),
    );

    let cache = TokenCache::with_token(provider, comfortably_valid("COMFORTABLY-VALID"));

    let token = cache.get_valid_token().await.expect("get_valid_token");

    assert_eq!(
        calls.load(Ordering::SeqCst),
        0,
        "a comfortably-valid token must not invoke the provider"
    );
    assert_eq!(
        token, "COMFORTABLY-VALID",
        "the still-valid cached token must be returned unchanged"
    );
}

/// Unknown expiry (`expires_at = None`, e.g. `az` emitted an unparseable
/// `expiresOn`) must be treated as short-lived and refreshed eagerly on the next
/// use — fail-safe, never a panic, never an indefinitely-cached unknown token.
#[tokio::test]
async fn test_cache_refreshes_eagerly_when_expiry_unknown() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = counting_provider(
        calls.clone(),
        "REFRESHED-WITH-KNOWN-EXPIRY",
        Some(Duration::from_secs(3600)),
    );

    let now = Instant::now();
    let seeded = TokenWithExpiry {
        value: "UNKNOWN-EXPIRY-TOKEN".to_string(),
        issued_at: now,
        expires_at: None,
    };
    let cache = TokenCache::with_token(provider, seeded);

    let token = cache.get_valid_token().await.expect("get_valid_token");

    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "a token with unknown expiry must be refreshed eagerly"
    );
    assert_eq!(token, "REFRESHED-WITH-KNOWN-EXPIRY");
}

/// A cache built with `TokenCache::new` (no seed) must fetch from the provider on
/// the first `get_valid_token()`, then serve the freshly-minted token without a
/// second provider call while it stays valid.
#[tokio::test]
async fn test_cache_new_fetches_once_then_serves_from_cache() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = counting_provider(
        calls.clone(),
        "INITIAL-FETCHED-TOKEN",
        Some(Duration::from_secs(3600)),
    );

    let cache = TokenCache::new(provider);

    let first = cache.get_valid_token().await.expect("first get");
    let second = cache.get_valid_token().await.expect("second get");

    assert_eq!(first, "INITIAL-FETCHED-TOKEN");
    assert_eq!(second, "INITIAL-FETCHED-TOKEN");
    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "the provider must be called once to seed, then the valid token is cached"
    );
}

/// SINGLE-FLIGHT CONTRACT: many connections arriving at once across the expiry
/// boundary must collapse into a SINGLE provider (`az`) invocation. The first
/// waiter refreshes under the mutex; the rest re-check freshness after acquiring
/// the lock and reuse the just-refreshed token — no thundering herd.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn test_concurrent_get_valid_token_is_single_flight() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = slow_counting_provider(
        calls.clone(),
        "SINGLE-FLIGHT-REFRESHED",
        Some(Duration::from_secs(3600)),
        Duration::from_millis(50),
    );

    let cache = Arc::new(TokenCache::with_token(
        provider,
        about_to_expire("STALE-RACED"),
    ));

    let mut handles = Vec::new();
    for _ in 0..16 {
        let cache = cache.clone();
        handles.push(tokio::spawn(async move {
            cache.get_valid_token().await.expect("get_valid_token")
        }));
    }

    for h in handles {
        let value = h.await.expect("task join");
        assert_eq!(
            value, "SINGLE-FLIGHT-REFRESHED",
            "every racing connection must observe the single refreshed token"
        );
    }

    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "concurrent refreshes must collapse to exactly one provider invocation"
    );
}

// ── Fail-safe reuse & liveness (issue #1059 fast-follow) ─────────────────────

/// FAIL-SAFE REUSE (F2): when a refresh fails but the cached token has NOT
/// hard-expired, `get_valid_token` must reuse the still-valid cached value
/// rather than tear the connection down on a transient `az` hiccup. The provider
/// is invoked (the token was inside its refresh margin) but its failure is
/// absorbed.
#[tokio::test]
async fn test_refresh_failure_reuses_still_valid_cached_token() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = failing_provider(calls.clone());

    // about_to_expire is inside the refresh margin (triggers a refresh attempt)
    // but NOT past hard expiry (still reusable on failure).
    let cache = TokenCache::with_token(provider, about_to_expire("STILL-VALID-ON-FAILURE"));

    let token = cache
        .get_valid_token()
        .await
        .expect("a failed refresh must fall back to the still-valid cached token");

    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "the failing provider must have been attempted exactly once"
    );
    assert_eq!(
        token, "STILL-VALID-ON-FAILURE",
        "the not-yet-hard-expired cached token must be reused when refresh fails"
    );
}

/// FAIL-SAFE BOUNDARY (F2): when the cached token is ALSO hard-expired, a refresh
/// failure has no usable fallback and MUST surface the error instead of handing
/// out a dead token.
#[tokio::test]
async fn test_refresh_failure_surfaces_error_when_cached_token_hard_expired() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = failing_provider(calls.clone());

    let cache = TokenCache::with_token(provider, already_expired("DEAD-TOKEN"));

    let result = cache.get_valid_token().await;

    assert!(
        result.is_err(),
        "a refresh failure with no reusable (hard-expired) token must surface an error, got: {result:?}"
    );
    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "the failing provider must have been attempted exactly once"
    );
}

/// LIVENESS (F1): a hung provider (a wedged `az`) must not hold the single-flight
/// lock forever. With no reusable token, the bounded refresh must elapse and
/// surface a `Timeout` error in ~the refresh timeout — NOT hang for the
/// provider's full (3600 s) sleep.
#[tokio::test]
async fn test_hung_provider_times_out_and_surfaces_error() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = hanging_provider(calls.clone());

    let cache = TokenCache::with_token(provider, already_expired("DEAD-TOKEN"))
        .with_refresh_timeout(Duration::from_millis(100));

    let started = Instant::now();
    let result = cache.get_valid_token().await;
    let elapsed = started.elapsed();

    assert!(
        matches!(result, Err(NativeTunnelError::Timeout(_))),
        "a hung refresh with no reusable token must surface a Timeout, got: {result:?}"
    );
    assert!(
        elapsed < Duration::from_secs(5),
        "the hung provider must be abandoned at the refresh timeout, not awaited to completion (elapsed {elapsed:?})"
    );
    assert_eq!(
        calls.load(Ordering::SeqCst),
        1,
        "the provider was invoked once"
    );
}

/// LIVENESS + FAIL-SAFE (F1): a hung provider must be abandoned at the timeout,
/// but if the cached token is still valid the connection proceeds on it — one
/// wedged `az` degrades to reuse instead of a stall.
#[tokio::test]
async fn test_hung_provider_times_out_then_reuses_valid_token() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = hanging_provider(calls.clone());

    let cache = TokenCache::with_token(provider, about_to_expire("STILL-VALID-DESPITE-HANG"))
        .with_refresh_timeout(Duration::from_millis(100));

    let started = Instant::now();
    let token = cache
        .get_valid_token()
        .await
        .expect("a hung refresh must fall back to the still-valid cached token");
    let elapsed = started.elapsed();

    assert_eq!(
        token, "STILL-VALID-DESPITE-HANG",
        "the still-valid cached token must be reused when the refresh hangs"
    );
    assert!(
        elapsed < Duration::from_secs(5),
        "reuse must happen at the refresh timeout, not the provider's full hang (elapsed {elapsed:?})"
    );
}

/// LIVENESS (F1): critically, a hung refresh must RELEASE the single-flight lock
/// so OTHER connections are not wedged. After a hung attempt on a cache with a
/// still-valid token, a subsequent `get_valid_token` must return promptly.
#[tokio::test]
async fn test_hung_refresh_releases_lock_for_other_waiters() {
    let calls = Arc::new(AtomicUsize::new(0));
    let provider = hanging_provider(calls.clone());

    let cache = Arc::new(
        TokenCache::with_token(provider, about_to_expire("STILL-VALID-CONCURRENT"))
            .with_refresh_timeout(Duration::from_millis(100)),
    );

    // First waiter triggers the hung refresh (absorbed via reuse at the timeout).
    let first = cache
        .get_valid_token()
        .await
        .expect("first waiter reuses token");
    assert_eq!(first, "STILL-VALID-CONCURRENT");

    // A second call must not be blocked by the first's abandoned refresh: the
    // lock was released, so this returns promptly (reusing the still-valid token).
    let started = Instant::now();
    let second = cache
        .get_valid_token()
        .await
        .expect("second waiter must not be wedged by the earlier hung refresh");
    let elapsed = started.elapsed();

    assert_eq!(second, "STILL-VALID-CONCURRENT");
    assert!(
        elapsed < Duration::from_secs(5),
        "the single-flight lock must be released after a hung refresh so waiters proceed (elapsed {elapsed:?})"
    );
}

// ── Secret-safety: the token value must never reach a log sink ───────────────
/// A `tracing` writer that appends every emitted byte to a shared buffer so a
/// test can assert what did (and did not) get logged.
#[derive(Clone)]
struct CapturingWriter(Arc<Mutex<Vec<u8>>>);

impl std::io::Write for CapturingWriter {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(buf);
        Ok(buf.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// PRIMARY CONTRACT (b): the secret token value must NEVER appear in log output.
/// We capture all `tracing` output (down to TRACE) emitted while the cache
/// refreshes and serves a token, and assert the secret substring is absent —
/// even if the refresh path emits diagnostics, it must skip the token value.
#[tokio::test]
async fn test_token_value_is_never_logged_during_refresh() {
    const SECRET: &str = "eyJ0b2tlbiI6IlNVUEVSLVNFQ1JFVC1BUk0tVE9LRU4tOTk5In0";

    let buf = Arc::new(Mutex::new(Vec::<u8>::new()));
    let writer_buf = buf.clone();

    let subscriber = tracing_subscriber::fmt()
        .with_max_level(tracing::Level::TRACE)
        .with_writer(move || CapturingWriter(writer_buf.clone()))
        .with_ansi(false)
        .finish();

    let calls = Arc::new(AtomicUsize::new(0));
    let provider = counting_provider(calls.clone(), SECRET, Some(Duration::from_secs(3600)));
    let cache = TokenCache::with_token(provider, about_to_expire("STALE-SECRET-PRECURSOR"));

    {
        let _guard = tracing::subscriber::set_default(subscriber);
        let token = cache.get_valid_token().await.expect("get_valid_token");
        // Sanity: the refresh really happened and returned the secret value ...
        assert_eq!(token, SECRET);
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    let logged = String::from_utf8(buf.lock().unwrap().clone()).expect("utf8 log output");
    assert!(
        !logged.contains(SECRET),
        "the ARM token secret must never be written to a log sink; captured log:\n{logged}"
    );
}

/// Defense in depth: even the `aztoken` form field — which legitimately carries
/// the token on the wire — must not be produced by rendering a loggable type.
/// `build_token_exchange_form` places the token in `aztoken` (wire, not log);
/// this guards that the token stays out of any `Debug`/log rendering of the
/// refresh types by confirming the only place the token appears is the form
/// value, not a formatted string of the cache/provider types.
#[tokio::test]
async fn test_token_never_leaks_via_type_formatting() {
    const SECRET: &str = "ARM-TOKEN-NO-DEBUG-LEAK-4242";

    // The token is expected ONLY in the form's aztoken field (the wire path).
    let form = azlin_azure::native_tunnel::build_token_exchange_form(
        "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        SECRET,
    );
    let aztoken = form
        .iter()
        .find(|(k, _)| *k == "aztoken")
        .map(|(_, v)| v.as_str());
    assert_eq!(
        aztoken,
        Some(SECRET),
        "the token must be carried as the aztoken form field (wire path)"
    );

    // But it must NOT be discoverable by formatting the refresh machinery: a
    // token minted through the provider and served by the cache is returned as a
    // bare String only; the cache/provider types expose no Debug/Display that
    // could render the secret into logs.
    let buf = Arc::new(Mutex::new(Vec::<u8>::new()));
    let writer_buf = buf.clone();
    let subscriber = tracing_subscriber::fmt()
        .with_max_level(tracing::Level::TRACE)
        .with_writer(move || CapturingWriter(writer_buf.clone()))
        .with_ansi(false)
        .finish();

    let calls = Arc::new(AtomicUsize::new(0));
    let provider = counting_provider(calls.clone(), SECRET, Some(Duration::from_secs(3600)));
    let cache = TokenCache::new(provider);

    {
        let _guard = tracing::subscriber::set_default(subscriber);
        let _ = cache.get_valid_token().await.expect("get_valid_token");
    }

    let logged = String::from_utf8(buf.lock().unwrap().clone()).expect("utf8 log output");
    assert!(
        !logged.contains(SECRET),
        "token leaked through refresh-path logging: {logged}"
    );
}
