# Native Bastion Tunnel — Adaptive Token Refresh

Status: Implemented (issue #1059)

## Summary

The azlin native Azure Bastion tunnel refreshes its Azure AD (ARM) access token
adaptively, so long-lived cached tunnels keep working indefinitely — well past
the ~60–90 minute lifetime of a single `az account get-access-token` token.

Before this change, a tunnel captured the ARM bearer token **once** at creation
and reused that same static token for every subsequent connection. Once the
token expired, the tunnel's loopback listener stayed up but every new SSH
connection failed token exchange, surfacing as:

```
kex_exchange_identification: read: Connection reset by peer
```

on `azlin connect`. The tunnel now sources its token from a **token provider**
and caches it with its expiry, refreshing only when the token is near or past
expiry. Each inbound connection obtains a valid token before performing its
bastion token exchange, so a tunnel that has been alive for 22 hours works
exactly like a freshly minted one.

## User-facing behavior

There is **no new configuration and no new command flag**. The fix is
transparent:

- A tunnel created hours ago continues to accept new `azlin connect` and
  `azlin` command sessions without error.
- Long-running sessions (e.g. `azlin connect <vm> --tmux-session`) that own a
  background tunnel no longer break after the initial token expires.
- `azlin connect` no longer intermittently fails with
  `kex_exchange_identification: read: Connection reset by peer` on tunnels that
  have outlived their original token.

### Example

```bash
# Start a long-lived tmux session; this owns a background native tunnel.
azlin connect ia2 --resource-group rysweet-linux-vm-pool --tmux-session work

# ... many hours later, well past the original token's expiry ...

# A brand-new connection reuses the SAME cached tunnel and still succeeds,
# because the tunnel transparently refreshed its ARM token.
azlin connect ia2 --resource-group rysweet-linux-vm-pool --no-tmux -y -- \
  "echo OK; hostname"
```

Expected result: the command connects and prints `OK` followed by the hostname,
even when the tunnel process has been running longer than the token lifetime.

## Design

### Token provider (decoupling)

`azlin-azure` never shells out to the Azure CLI. Instead, the caller (the
`azlin` crate) supplies a **token provider**: a cheap-to-clone async closure that
knows how to mint a fresh ARM token and report its expiry.

```rust
/// A token value paired with its issued/expiry instants.
///
/// Deliberately has no `Debug`, `Serialize`, or `Display` impls so the secret
/// value can never be accidentally logged or serialized.
pub struct TokenWithExpiry {
    /// The ARM bearer token value.
    pub value: String,
    /// When the token was issued (monotonic). Used together with `expires_at`
    /// to derive the token's lifetime for the adaptive refresh margin. Defaults
    /// to the instant the provider returned the token.
    pub issued_at: Instant,
    /// When the token stops being valid, if known. `None` means "unknown
    /// lifetime" and triggers eager refresh on next use.
    pub expires_at: Option<Instant>,
}
```

Both instants are monotonic `Instant`s so the cache can compare against
`Instant::now()` without clock-skew hazards. Because Azure CLI reports expiry as
a **wall-clock** `expiresOn`, the provider converts it to a monotonic instant at
mint time (see [Provider implementation](#provider-implementation-azlinbastion_tunnel)):

```rust
// wall-clock expiresOn -> monotonic Instant
let remaining = (expires_on - Local::now()).to_std().ok();      // Duration until expiry
let expires_at = remaining.map(|d| Instant::now() + d);         // None if already past / unparseable
```

```rust
/// Async, cheap-to-clone, thread-safe source of ARM tokens.
///
/// Supplied by the `azlin` crate so `azlin-azure` stays CLI-agnostic.
pub type TokenProvider =
    Arc<dyn Fn() -> BoxFuture<'static, Result<TokenWithExpiry, NativeTunnelError>>
        + Send
        + Sync>;
```

The provider is invoked:

1. Once when the tunnel is created (to verify connectivity), and
2. Again, lazily, whenever the cached token is near or past expiry.

### Adaptive refresh (no arbitrary caps)

The tunnel caches the token together with its expiry and refreshes only when it
is close to expiring. The refresh margin is **derived from the token's own
lifetime**, not a hardcoded TTL or a fixed reconnect cap:

```
margin = max(lifetime * REFRESH_FRACTION, MIN_MARGIN)
refresh when: now + margin >= expires_at
```

- `lifetime = expires_at - issued_at`. A token that lives 90 minutes gets a
  proportionally larger safety margin than one that lives 10 minutes.
- `MIN_MARGIN` is a small pre-expiry safety floor used only when a proportional
  margin would be too small to cover a refresh round-trip. It is a safety
  margin, not a forced reconnect interval.
- If `expires_at` is `None` (lifetime unknown / unparseable), the token is
  treated as short-lived and refreshed eagerly on the next connection.

This keeps the behavior adaptive: the tunnel lives as long as the identity can
mint tokens, and never expires because of an artificial fixed limit.

### Single-flight refresh

The cache is an `Arc<tokio::sync::Mutex<CachedToken>>` shared into the accept
loop and every per-connection task. Refresh happens under the mutex, so when
many connections arrive at once only **one** `az account get-access-token`
invocation runs; the rest await the lock and receive the freshly refreshed
token. This prevents a thundering herd of CLI calls (and identity rate-limiting)
after expiry.

If a refresh fails (transient CLI hiccup) but the currently cached token is not
yet hard-expired, the cached token is reused. If the token is hard-expired and
refresh fails, only that one connection fails — the tunnel stays up and later
connections retry. The tunnel never falls back to an unauthenticated path
(fail-closed).

### Per-connection self-healing

Each inbound TCP connection calls `get_valid_token()` on the cache as its first
step, before performing the bastion `/api/tokens` exchange. So the tunnel
self-heals: the first connection after expiry triggers a refresh, and it plus
all following connections use the fresh token.

## API reference (`azlin-azure::native_tunnel`)

### `open_tunnel_with_timeouts`

```rust
pub async fn open_tunnel_with_timeouts(
    bastion_endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token_provider: TokenProvider,
    url_mode: WssUrlMode,
    timeout: Duration,
    connect_timeout: Duration,
) -> Result<(u16, JoinHandle<()>), NativeTunnelError>
```

The primary entry point. Takes a `TokenProvider` instead of a static token
string. It seeds a token cache from the provider, uses the cache for the initial
connectivity verification, and clones the cache into each per-connection task so
every connection obtains a valid (refreshed if needed) token.

- `token_provider` — async source of ARM bearer tokens with expiry. Called on
  setup and again lazily when the cached token nears expiry.

Other arguments (`bastion_endpoint`, `target_resource_id`, `resource_port`,
`url_mode`, `timeout`, `connect_timeout`) are unchanged.

### `open_tunnel` (stable wrapper)

```rust
pub async fn open_tunnel(
    bastion_endpoint: &str,
    target_resource_id: &str,
    resource_port: u16,
    token: &str,
    url_mode: WssUrlMode,
    timeout: Duration,
) -> Result<(u16, JoinHandle<()>), NativeTunnelError>
```

The stable `open_tunnel` signature is **unchanged**. It accepts a `&str` token
and internally wraps it into a trivial provider that always returns that literal
value with `expires_at = None`. This preserves all existing callers and tests
that pass a static token (which do not expire during a test run) while the
adaptive path is used by production code through `open_tunnel_with_timeouts`.

Passing an empty `token` still returns
`NativeTunnelError::InvalidEndpoint("token must not be empty")`.

### Security properties (preserved)

- **SEC-3 / TLS-only**: non-TLS endpoints are rejected (`normalize_endpoint`).
- **SEC-4 / loopback bind**: the listener binds only to `127.0.0.1`; refresh
  never changes the bind scope.
- **Token as form field**: the ARM token is carried as the `aztoken` POST form
  field on `/api/tokens`, never as an `Authorization` header or URL parameter.
- **Never logged**: `TokenWithExpiry` has no `Debug`/`Serialize`/`Display`;
  `#[instrument(skip(client, token))]` is retained; `wss_url` is redacted in
  logs. The token value never appears in any log output.
- **In-memory only**: tokens live in `Arc<Mutex<CachedToken>>` — never written
  to disk, temp files, environment, or session artifacts.
- **Fail-closed**: a hard-expired token with a failing provider fails the
  connection; there is no unauthenticated fallback.

## Provider implementation (`azlin::bastion_tunnel`)

The `azlin` crate builds the provider closure once and passes it to
`open_tunnel_with_timeouts`. The closure queries token **and** expiry in a single
Azure CLI call and parses the expiry robustly:

```bash
az account get-access-token \
  --query "{t:accessToken,e:expiresOn}" -o json
```

- The `accessToken` becomes `TokenWithExpiry.value`.
- `expiresOn` is parsed as a local-time naive datetime
  (`"%Y-%m-%d %H:%M:%S%.f"` via `chrono::Local`), with an ISO-8601/RFC3339
  fallback. The parsed wall-clock expiry is converted to a **monotonic**
  `Instant` at mint time — `Instant::now() + (expiresOn - Local::now())` — so the
  cache never compares against a skew-prone wall clock. `issued_at` is set to the
  `Instant::now()` captured at the same point, giving the cache a real lifetime.
- If parsing fails, or the expiry is already in the past, `expires_at` is `None`,
  which safely forces eager refresh on the next connection (never a panic).
- The CLI is invoked on `spawn_blocking` with an explicit argument vector (no
  shell interpolation), using the same identity and scope on every refresh.

Because the provider is a reusable closure (not a one-shot fetch), the tunnel can
call it as many times as needed over its lifetime.

## Tunnel reuse validation

`get_or_create_tunnel` continues to validate cross-process tunnel reuse by
checking that the owning process is still running. It no longer needs to
validate token freshness at reuse time, because a reused tunnel now refreshes
its own token on demand. A long-lived tunnel owned by another live process is
safe to reuse.

## Testing

The cache/refresh logic is unit-tested in isolation (no network), covering:

- **refresh_before_next_exchange** — a cache seeded with an about-to-expire
  token performs exactly one provider refresh before the next
  `get_valid_token()` returns, and returns the refreshed value.
- **no_refresh_when_fresh** — a cache with a comfortably-valid token does not
  invoke the provider.
- **single_flight** — concurrent `get_valid_token()` calls that race across
  expiry invoke the provider only once.
- **token_never_logged** — `tracing` output captured around refresh and
  token-exchange form construction never contains the secret token substring.

Existing tests continue to pass, including the `open_tunnel` static-token call
sites and error-surface tests.

## Verification

```bash
cd rust
cargo clippy --all --locked -- -D warnings
cargo test -p azlin
cargo test -p azlin-azure
```

Live verification against VM `ia2`:

```bash
azlin connect ia2 --resource-group rysweet-linux-vm-pool --no-tmux -y -- \
  "echo OK; hostname"
```

The command succeeds, and a tunnel kept alive past the original token lifetime
continues to accept new connections.
