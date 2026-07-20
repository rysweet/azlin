# Bastion Tunnel Data-Plane DNS Name Resolution

**Issue:** #1046
**Status:** Implemented
**Affects:** `azlin connect`, `azlin ssh`, `azlin gui`, `azlin sync` for all
Standard/Premium SKU Azure Bastion hosts.

## Overview

The native Rust bastion tunnel connects to the Azure Bastion **data plane** using
the bastion resource's real ARM `properties.dnsName` (for example
`bst-7299861d-50e0-4142-8b50-2f8bc6f5b549.bastion.azure.com`).

Earlier native-tunnel builds constructed the endpoint by string-formatting the
bastion *resource name* (`{bastion_name}.bastion.azure.com`). That host does not
exist in DNS, so the token-exchange request failed at the transport layer with an
opaque `error sending request for url (...)`, surfaced as `token exchange failed:
request failed: ...` and then `failed to open native bastion tunnel`. This broke
`azlin connect` for every Standard/Premium bastion.

Azlin now resolves the correct data-plane FQDN from Azure Resource Manager before
opening the tunnel, caches it in the tunnel registry for reuse, and surfaces the
full transport error cause chain when a request does fail.

There are **no user-facing command or configuration changes** — connections that
previously failed now succeed transparently.

## Behavior

### DNS name resolution

When `get_or_create_tunnel()` needs to open a new tunnel, it resolves the bastion
data-plane FQDN from ARM:

```bash
az network bastion show \
  --name <bastion_name> \
  --resource-group <resource_group> \
  --query dnsName -o tsv
```

- The lookup runs on a blocking worker thread (the same pattern used for Azure AD
  token acquisition), so it never stalls the async runtime.
- The returned `dnsName` is used verbatim as the `bastion_endpoint` passed to
  `azlin_azure::native_tunnel::open_tunnel`.
- The command is invoked with an argument array (no shell), so the bastion name
  and resource group are never interpolated into a shell string.

### Validation (fail closed)

The resolved value is validated before use. Azlin **never** falls back to the
broken `{bastion_name}.bastion.azure.com` form.

The resolved host must:

- be non-empty after trimming,
- contain no whitespace or control characters and no `/`, `\`, or `@`,
- end with the `.bastion.azure.com` suffix.

If the `az` lookup fails, returns empty, or the value fails validation, azlin
returns a clear, actionable error naming the bastion, the resource group, and the
underlying `az` stderr. For example:

```
failed to resolve Azure Bastion data-plane DNS name for bastion
'azlin-bastion-southcentralus' in resource group 'rysweet-linux-vm-pool':
az network bastion show returned an empty dnsName. Verify the bastion exists
and that you have read access (az network bastion show -n <name> -g <rg>).
```

### Caching in the tunnel registry

The resolved `dnsName` is stored on the tunnel registry entry so repeat connects
and reused tunnels do **not** re-query ARM each time.

- A new `dns_name` field is added to each registry entry.
- When an existing tunnel is reused, the cached `dns_name` is used directly.
- Registry files written by older versions (missing `dns_name`) load with an
  empty value via `#[serde(default)]`; the next new tunnel for that VM re-resolves
  and repopulates it. This is a one-time, safe re-resolution.

### Transport error transparency

When a token-exchange or cleanup request fails at the transport layer, azlin now
surfaces the **full `std::error::Error::source()` cause chain** via an internal
`error_chain` helper (in `azlin_azure::native_tunnel`), so the real cause (DNS
resolution failure, TLS error, connection timeout) is visible instead of the
opaque top-level `error sending request for url`.

- `exchange_token` includes the cause chain in the `TokenExchange` error text.
- `cleanup_token` no longer silently discards failures; it logs the cause chain at
  `warn` level with the `node_id` for correlation.
- Tokens, URLs, and header values are **never** logged. Only the error cause chain
  and non-sensitive identifiers are surfaced.

> Note: azlin does **not** parse or classify tool/error output strings to make
> decisions. String-classification of `az`/transport output is a brittle-parsing
> antipattern; the error chain is surfaced for **diagnostics only**.

## API

### `TunnelRegistryEntry` (`azlin::bastion_tunnel`)

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TunnelRegistryEntry {
    pub vm_resource_id: String,
    pub bastion_name: String,
    pub resource_group: String,
    pub local_port: u16,
    pub pid: u32,
    pub created_at: u64,

    /// Tunnel type: "native" (in-process WSS) or "legacy" (az CLI subprocess).
    #[serde(default = "default_tunnel_type")]
    pub tunnel_type: String,

    /// Resolved Azure Bastion data-plane FQDN (ARM `properties.dnsName`),
    /// e.g. "bst-<guid>.bastion.azure.com". Cached to avoid re-querying ARM on
    /// tunnel reuse. Defaults to empty for registry files written before this
    /// field existed; an empty value triggers a one-time re-resolution.
    #[serde(default)]
    pub dns_name: String,
}
```

### DNS name helpers (`azlin::bastion_tunnel`)

```rust
/// Parse and validate the `dnsName` value returned by
/// `az network bastion show ... --query dnsName -o tsv`.
///
/// Trims the output, takes the first line, and rejects empty values, values
/// containing whitespace/control characters or `/`, `\`, `@`, and values that
/// do not end with `.bastion.azure.com`. Pure and offline-testable.
fn parse_dns_name(az_stdout: &str) -> anyhow::Result<String>;

/// Resolve the Azure Bastion data-plane FQDN from ARM by running
/// `az network bastion show --name <n> --resource-group <rg>
///  --query dnsName -o tsv` on a blocking thread, then validating the result
/// with `parse_dns_name`. Returns an actionable error on failure; never falls
/// back to a constructed host.
async fn resolve_bastion_dns_name(
    bastion_name: &str,
    resource_group: &str,
) -> anyhow::Result<String>;
```

`get_or_create_tunnel()` keeps its existing three-argument signature — no callers
change:

```rust
pub async fn get_or_create_tunnel(
    bastion_name: &str,
    resource_group: &str,
    vm_resource_id: &str,
) -> anyhow::Result<u16>;
```

## Examples

### End-user (unchanged commands, now working)

```bash
# Standard/Premium SKU bastion — previously failed with
# "failed to open native bastion tunnel", now connects successfully.
azlin connect my-vm
```

### Inspecting the cached DNS name

```bash
cat ~/.azlin/tunnels/registry.json
```

```json
{
  "tunnels": {
    "/subscriptions/.../virtualMachines/my-vm": {
      "vm_resource_id": "/subscriptions/.../virtualMachines/my-vm",
      "bastion_name": "azlin-bastion-southcentralus",
      "resource_group": "rysweet-linux-vm-pool",
      "local_port": 52341,
      "pid": 12345,
      "created_at": 1750000000,
      "tunnel_type": "native",
      "dns_name": "bst-7299861d-50e0-4142-8b50-2f8bc6f5b549.bastion.azure.com"
    }
  }
}
```

### Verifying the data-plane FQDN manually

```bash
# The value azlin resolves and uses (resolves in DNS):
az network bastion show \
  -n azlin-bastion-southcentralus \
  -g rysweet-linux-vm-pool \
  --query dnsName -o tsv
# -> bst-7299861d-50e0-4142-8b50-2f8bc6f5b549.bastion.azure.com

# The old constructed host (does NOT resolve — this was the bug):
#   azlin-bastion-southcentralus.bastion.azure.com
```

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `failed to resolve Azure Bastion data-plane DNS name ...` | `az network bastion show` failed or returned empty | Confirm the bastion name/resource group and that you have read access; run the `az` command manually. |
| Cause chain shows a DNS/`dns error`/`Name or service not known` | The resolved FQDN could not be looked up | Verify network/DNS connectivity to `*.bastion.azure.com`. |
| Cause chain shows a TLS or timeout error | Transport failure after DNS resolved | Check firewall/proxy; increase `bastion_tunnel_timeout` in `~/.azlin/config.toml`. |
| First connect after upgrade is slightly slower | One-time ARM re-resolution because the cached `dns_name` was empty | Expected; subsequent connects reuse the cached value. |

## Testing

Regression coverage proves the endpoint used is the ARM `dnsName`, not the
constructed `{bastion_name}.bastion.azure.com` form:

- `parse_dns_name` unit tests: valid ARM output; empty/whitespace-only output;
  hostile multi-line input; input containing `@`, `/`, `\`, or control
  characters; values missing the `.bastion.azure.com` suffix.
- A guard test asserting the `{bastion_name}.bastion.azure.com` string form is
  never produced as the tunnel endpoint.
- `error_chain` unit tests asserting the full nested `source()` chain is walked
  and that no token/auth material appears in the rendered string.

## Related

- [Native Bastion Tunnel](native-bastion-tunnel.md) — the underlying native WSS
  tunnel this fix corrects.
