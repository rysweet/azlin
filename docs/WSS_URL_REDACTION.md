# WSS URL Redaction (`redact_wss_url`)

**Status:** Shipped · **Issue:** [rysweet/azlin#1056](https://github.com/rysweet/azlin/issues/1056)
· **Crate:** `azlin-azure` · **Module:** `native_tunnel`

## Overview

Native bastion tunnels connect over a WebSocket Secure (`wss://`) URL whose path
segment embeds a short-lived **`websocketToken`** — a bearer secret that grants
access to the tunnel. Before this change, when a WSS connect/reconnect/close
event failed, the `tungstenite` error was rendered with its full URL and written
to a log sink via `tracing`, leaking the token into log files and OpenTelemetry
exporters.

`redact_wss_url` masks the token-bearing portion of a `wss://` URL so it is safe
to log, while the real, token-bearing URL is still used for the live connection.
The redaction is **fail-closed**: any input that does not parse as an expected
tunnel URL is masked aggressively rather than passed through.

## Guarantees

- The `websocketToken` (Standard/Premium **path segment**, Developer/QuickConnect
  **path segment**, or any `?...token...` query / `userinfo`) never appears in a
  logged string.
- Host, scheme, node id (`X-Node-Id`), and structural shape of the URL are
  preserved so logs stay diagnostically useful.
- URL-encoding aware: matches the encoding applied by `build_wss_url_standard` /
  `build_wss_url_developer` (SEC-2), so an encoded token cannot slip through.
- Behavior of the live tunnel is **unchanged** — `connect_async` still receives
  the unredacted, token-bearing URL.
- Additive and non-breaking: no public type or existing function signature
  changes.

## API

```rust
/// Return a log-safe rendering of a `wss://` bastion tunnel URL with the
/// embedded `websocketToken` replaced by `***`.
///
/// Preserves scheme, host, and the `X-Node-Id` query parameter. Fail-closed:
/// input that does not match a known tunnel URL shape is masked to
/// `wss://<redacted>`.
pub fn redact_wss_url(url: &str) -> String;
```

### Masking rules

| Input shape (SKU)              | Example (abbreviated)                                  | Redacted output                                        |
| ------------------------------ | ------------------------------------------------------ | ------------------------------------------------------ |
| Standard / Premium (`NodeScoped`)  | `wss://host/webtunnelv2/<TOKEN>?X-Node-Id=<id>`        | `wss://host/webtunnelv2/***?X-Node-Id=<id>`            |
| Developer / QuickConnect (`EndpointScoped`) | `wss://host/omni/webtunnel/<TOKEN>`                    | `wss://host/omni/webtunnel/***`                        |
| Unrecognized / malformed       | `garbage`                                              | `wss://<redacted>`                                     |

Only the token segment is masked; the node id is retained because it is not a
secret and aids correlation.

## Usage

Route any URL- or connection-error-bearing log field through `redact_wss_url`.
Do **not** log raw `wss_url` or the raw `tungstenite` error `Display` (which
renders the URL). Note: `reqwest`'s `without_url()` is **not** applicable here —
the WSS leak site renders a `tungstenite` error, which has no such method.

```rust
use crate::native_tunnel::redact_wss_url;

// Step 2: build the real, token-bearing URL used for the live connection.
let wss_url = build_wss_url_standard(&endpoint, &token_resp.websocket_token, &token_resp.node_id);

// Step 3: connect with the REAL url (unchanged).
match tokio_tungstenite::connect_async(&wss_url).await {
    Ok((ws_stream, _)) => { /* forward */ }
    Err(e) => {
        // The tungstenite error Display embeds the URL; redact before logging.
        warn!(url = %redact_wss_url(&wss_url), "bastion WSS connect failed: {e}");
        // ...best-effort cleanup...
    }
}
```

### Audited log sites (`native_tunnel.rs`)

Line numbers below reflect `native_tunnel.rs` at the time of writing and may
drift; the events are the stable reference.

| Line   | Event                       | Action                                           |
| ------ | --------------------------- | ------------------------------------------------ |
| 527–529 | WSS connect failed (primary leak) | Redact URL field *and* scrub the rendered error via `e.to_string().replace(&wss_url, &redacted_url)` |
| 427–429 | cleanup error chain         | Already stripped via `without_url()` (reqwest)   |
| 504    | token exchange failed       | No URL rendered; verified token-free             |
| 542    | WSS connected (`debug!`)    | No URL rendered                                   |
| 556    | tunnel closed (`debug!`)    | No URL rendered                                   |

## Configuration

No configuration. Redaction is unconditional at every WSS URL/error log site and
cannot be turned off. There is no verbosity level at which the raw token is
emitted.

## Security notes

- The token remains present in memory and on the wire (required for the
  connection) — redaction is a **logging** control only.
- `redact_wss_url` performs no allocation of the raw token into any returned
  value; the returned `String` contains only masked content plus non-secret
  structure.
- Structured `tracing` + OpenTelemetry only. No `print!` / `println!` /
  `eprintln!` in the tunnel path.

## Testing

Unit test in `rust/crates/azlin-azure/tests/native_tunnel_unit.rs` (mirrors
`test_cleanup_error_without_url_does_not_leak_auth_token`):

```rust
#[test]
fn test_redact_wss_url_never_leaks_websocket_token() {
    const TOKEN: &str = "SUPER-SECRET-WS-TOKEN-9f8e7d6c";
    let url = azlin_azure::native_tunnel::build_wss_url_standard(
        "host.example", TOKEN, "node-42",
    );

    // Precondition: the raw URL carries the token.
    assert!(url.contains(TOKEN) || url.contains(&urlencoding::encode(TOKEN).into_owned()));

    let redacted = azlin_azure::native_tunnel::redact_wss_url(&url);

    // The redacted form must never contain the token (raw or encoded).
    assert!(!redacted.contains(TOKEN));
    assert!(!redacted.contains(urlencoding::encode(TOKEN).as_ref()));
    // Non-secret structure is preserved.
    assert!(redacted.starts_with("wss://host.example/webtunnelv2/"));
    assert!(redacted.contains("X-Node-Id=node-42"));
    assert!(redacted.contains("***"));
}
```

### Coverage matrix

| Path                              | Asserts                                                                         |
| --------------------------------- | ------------------------------------------------------------------------------- |
| Standard / Premium (`NodeScoped`) | Token masked to `***`; host + `X-Node-Id` preserved.                            |
| Developer / QuickConnect (`EndpointScoped`) | Token masked; `/omni/webtunnel/***` structure preserved.              |
| URL-encoded token                 | Encoded token (special chars) never appears in redacted output.                 |
| Fail-closed (malformed input)     | Unrecognized shape masked to `wss://<redacted>`; no fragment of input echoed.   |
| WSS-connect `warn!` scrub         | The rendered `tungstenite` error passed to `warn!` (after `to_string().replace(&wss_url, &redact_wss_url(&wss_url))`) never contains `websocket_token` or raw `wss_url`. |

The WSS-connect `warn!` scrub test constructs a `wss_url` from a known token,
simulates the error-render/replace applied at the leak site
(`native_tunnel.rs:527-529`), and asserts the logged string contains neither the
raw token nor the raw URL — locking the security control regardless of upstream
`tungstenite` `Display` behavior.
