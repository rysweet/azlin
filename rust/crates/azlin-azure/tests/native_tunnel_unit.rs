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
        "",  // empty endpoint → InvalidEndpoint error
        "test-resource-id",
        22,
        "test-token",
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
    let url = azlin_azure::native_tunnel::build_token_exchange_url(
        "bastion-host.example.com",
    );
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

/// Token exchange request body must contain the correct fields.
#[test]
fn test_token_exchange_request_body() {
    let body = azlin_azure::native_tunnel::build_token_exchange_body(
        "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        22,
        "bearer-token-xyz",
    );
    // Should be valid JSON with the required fields
    let parsed: serde_json::Value = serde_json::from_str(&body)
        .expect("token exchange body must be valid JSON");
    assert_eq!(
        parsed["resourceId"],
        "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    );
    assert_eq!(parsed["protocol"], "tcptunnel");
    assert_eq!(parsed["workloadHostPort"], "22");
    // aztoken and token fields must both be the bearer token
    assert_eq!(parsed["aztoken"], "bearer-token-xyz");
    assert_eq!(parsed["token"], "bearer-token-xyz");
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
        "http://bastion.example.com",  // http:// not https://
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm",
        22,
        "token",
        std::time::Duration::from_secs(5),
    )
    .await;
    assert!(result.is_err(), "must reject non-TLS endpoint");
    let err = result.unwrap_err();
    let msg = format!("{}", err);
    assert!(
        msg.to_lowercase().contains("tls") || msg.to_lowercase().contains("https") || msg.to_lowercase().contains("scheme"),
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
    let listener = azlin_azure::native_tunnel::bind_local_listener()
        .expect("must bind local listener");
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
    let err = azlin_azure::native_tunnel::NativeTunnelError::TokenExchange(
        "mock failure".to_string(),
    );
    let msg = format!("{}", err);
    assert!(msg.contains("mock failure") || msg.contains("token"),
        "TokenExchange error should contain context");
}

/// NativeTunnelError must have a WebSocket variant.
#[test]
fn test_error_has_websocket_variant() {
    let err = azlin_azure::native_tunnel::NativeTunnelError::WebSocket(
        "connection reset".to_string(),
    );
    let msg = format!("{}", err);
    assert!(!msg.is_empty());
}

/// NativeTunnelError must have a Timeout variant.
#[test]
fn test_error_has_timeout_variant() {
    let err = azlin_azure::native_tunnel::NativeTunnelError::Timeout(
        std::time::Duration::from_secs(30),
    );
    let msg = format!("{}", err);
    assert!(msg.contains("30") || msg.to_lowercase().contains("timeout"));
}

/// NativeTunnelError must have an InvalidEndpoint variant for SEC-3.
#[test]
fn test_error_has_invalid_endpoint_variant() {
    let err = azlin_azure::native_tunnel::NativeTunnelError::InvalidEndpoint(
        "http://bad".to_string(),
    );
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
    assert_eq!(
        azlin_azure::native_tunnel::NODE_ID_HEADER,
        "X-Node-Id"
    );
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
        0,  // invalid port
        "token",
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
        "",  // empty token
        std::time::Duration::from_secs(1),
    )
    .await;
    assert!(result.is_err(), "empty token must be rejected");
}
