# Region Fit — Automatic Region Selection

Automatically find an Azure region with available quota and SKU capacity for your requested VM size, eliminating manual trial-and-error across regions.

## What is Region Fit?

Region fit is an azlin feature that scans candidate Azure regions in parallel to find one where your requested VM size is both available and has sufficient quota. When you pass `--region-fit` to `azlin new`, azlin:

1. Determines the required core count from your `--size` tier or `--vm-size` SKU
2. Queries each candidate region in parallel (with 10-second per-region timeouts):
   - Checks quota via `az vm list-usage --location {region}`
   - Checks SKU availability via `az vm list-skus --location {region} --size {sku}`
3. Selects the first responding region (in candidate order) that has both enough quota AND the SKU is not restricted
4. Prints which region was selected and the available capacity
5. Proceeds with VM creation in that region

If no region has capacity, azlin prints a table of all regions with their quota status and SKU availability, so you can take action (request a quota increase or choose a different SKU).

Region fit also activates automatically as error recovery: when `azlin new` fails with `QuotaExceeded` or `SkuNotAvailable`, the error message suggests re-running with `--region-fit`.

## Why Would I Use It?

### Problem 1: Quota Exhausted in Your Default Region

You've used all your cores in `westus2`:

```bash
azlin new --size l --region westus2
```

Error:
```
Error: QuotaExceeded - Operation could not be completed as it results in
exceeding approved Total Regional Cores quota (limit: 100, current: 96,
requested: 16).

Tip: Re-run with --region-fit to automatically find a region with available quota:
  azlin new --size l --region-fit
```

With `--region-fit`, azlin finds `centralus` has 64 unused cores and creates the VM there.

### Problem 2: SKU Not Available in Region

The v5 SKU you want isn't deployed in your preferred region:

```bash
azlin new --vm-size Standard_D32s_v5 --region northcentralus
```

Error:
```
Error: SkuNotAvailable - The requested VM size Standard_D32s_v5 is not
available in location northcentralus.
```

With `--region-fit`, azlin scans US regions and finds `eastus2` supports the SKU.

### Problem 3: You Don't Know Which Region to Use

You just want a VM and don't care which region it lands in:

```bash
azlin new --size m --region-fit
```

Output:
```
🔍 Scanning 8 regions for Standard_D8s_v5 (8 cores)...
  ✓ westus2: 48/100 cores used, SKU available
  ✗ westus: SKU not available
  ✗ centralus: 98/100 cores used (insufficient)
  ✓ eastus: 12/100 cores used, SKU available
  ... (skipping remaining — match found)

✅ Selected region: westus2 (52 cores available)
Creating VM in westus2...
```

## Usage

```bash
# Find any region with capacity for a medium VM
azlin new --size m --region-fit

# Combine with --vm-family for E-series memory-optimized
azlin new --size l --vm-family e --region-fit

# Use with explicit SKU
azlin new --vm-size Standard_E32as_v5 --region-fit

# In CI/CD — fully automated
azlin new --size xl --region-fit --yes --no-auto-connect
```

### With a Preferred Region

If you also pass `--region`, that region is checked first. Region fit only scans others if the preferred region lacks capacity:

```bash
# Prefer westus2, but fall back to any US region
azlin new --size l --region westus2 --region-fit
```

## Candidate Regions

By default, azlin scans these US regions (in order):

1. `westus2`
2. `eastus`
3. `eastus2`
4. `centralus`
5. `westus`
6. `westus3`
7. `northcentralus`
8. `southcentralus`

If `--region` is specified and is not in this list, it is prepended as the first candidate.

### Customizing Candidate Regions (Planned)

> **Note:** Custom candidate regions are planned for a future release. The initial implementation uses the hardcoded US region list above.

When available, you will be able to override the candidate list in `~/.azlin/config.toml`:

```toml
[region_fit]
candidate_regions = ["westeurope", "northeurope", "uksouth", "francecentral"]
```

## How It Works

Region fit runs quota and SKU checks in parallel using `az` CLI commands:

**Quota check** (per region):
```bash
az vm list-usage --location westus2 --output json
```
Parses the JSON output to find the "Total Regional vCPUs" entry and compares `currentValue + requestedCores <= limit`.

**SKU availability check** (per region):
```bash
az vm list-skus --location westus2 --size Standard_D8s_v5 --output json
```
Parses the JSON output to verify the SKU exists and has no restriction entries (e.g., `NotAvailableForSubscription`).

Both checks run with a 10-second timeout per region. Regions that time out are skipped and reported as "timeout" in the summary table.

## No-Region-Found Output

When no region has capacity, azlin prints a diagnostic table:

```
🔍 Scanning 8 regions for Standard_D16s_v5 (16 cores)...

Region              Cores Used   Limit   Available   SKU Status
─────────────────   ──────────   ─────   ─────────   ──────────
westus2             96/100       100     4           Available
eastus              88/100       100     12          Available (insufficient)
eastus2             100/100      100     0           Available
centralus           72/100       100     28          Not Available
westus              64/100       100     36          Not Available
westus3             timeout      —       —           —
northcentralus      48/100       50      2           Available (insufficient)
southcentralus      44/100       50      6           Available (insufficient)

❌ No region found with 16 available cores and SKU support.

Suggestions:
  • Request a quota increase: https://aka.ms/ProdportalCRP/#blade/Microsoft_Azure_Capacity/UsageAndQuota.ReactView
  • Try a smaller VM size: azlin new --size s
  • Use a different SKU: azlin new --vm-size Standard_D16s_v3
```

## Integration with Error Recovery

Even without `--region-fit`, azlin's error handler detects quota and SKU failures and suggests the flag:

```
Error: QuotaExceeded in region westus2.

Tip: Re-run with --region-fit to automatically find a region with available quota:
  azlin new --size l --region-fit
```

This works for both `QuotaExceeded` and `SkuNotAvailable` error codes from the Azure API.

## Caveats

- **TOCTOU race**: Quota may be consumed between the region-fit check and VM creation. If this happens, azlin reports the creation error normally (it does not retry automatically).
- **Rate limits**: Scanning 8 regions makes 16 `az` CLI calls (2 per region). Subscriptions with very restrictive rate limits may see throttling.
- **Time cost**: A full scan typically completes in 5-15 seconds (parallel, 10s timeout per region). This is added to the normal provisioning time.

## Related

- [VM Size Tiers and Families](../../docs-site/commands/vm/new.md#size-tiers-explained) — Understanding `--size` and `--vm-family`
- [Quota Performance Review](../QUOTA_PERFORMANCE_REVIEW.md) — Azure quota management
- [Quick Reference](../QUICK_REFERENCE.md) — All CLI flags at a glance
