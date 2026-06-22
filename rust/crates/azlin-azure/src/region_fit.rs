//! Region-fit: find Azure regions with available quota and SKU capacity.
//!
//! Provides pure JSON parsers for `az vm list-usage` and `az vm list-skus`
//! output, plus data types for quota/availability checking.

use anyhow::{Context, Result};
use std::fmt::Write as _;

// ── Default candidate regions ─────────────────────────────────────────

/// Default US regions to check for availability, in priority order.
pub fn default_candidate_regions() -> Vec<&'static str> {
    vec![
        "westus2",
        "eastus",
        "eastus2",
        "centralus",
        "westus",
        "westus3",
        "northcentralus",
        "southcentralus",
    ]
}

/// Return candidate regions with the preferred region first (deduplicated).
pub fn candidate_regions_with_preferred(preferred: &str) -> Vec<String> {
    let defaults = default_candidate_regions();
    let mut result: Vec<String> = Vec::with_capacity(defaults.len() + 1);
    result.push(preferred.to_string());

    for r in defaults {
        if r != preferred {
            result.push(r.to_string());
        }
    }
    result
}

// ── Quota types ───────────────────────────────────────────────────────

/// Per-family quota entry.
#[derive(Debug, Clone)]
pub struct FamilyQuota {
    pub name: String,
    pub used: u32,
    pub limit: u32,
}

/// Parsed regional quota information from `az vm list-usage`.
#[derive(Debug, Clone)]
pub struct RegionQuota {
    pub region: String,
    pub total_regional_used: u32,
    pub total_regional_limit: u32,
    pub family_quotas: Vec<FamilyQuota>,
}

impl RegionQuota {
    /// Available cores (limit - used), floored at 0.
    pub fn available_cores(&self) -> u32 {
        self.total_regional_limit.saturating_sub(self.total_regional_used)
    }

    /// Whether the region has capacity for `required_cores`.
    pub fn has_capacity_for(&self, required_cores: u32) -> bool {
        self.available_cores() >= required_cores
    }

    /// Look up family-specific quota by name (e.g. "standardDv5Family").
    pub fn family_quota(&self, family_name: &str) -> Option<&FamilyQuota> {
        self.family_quotas.iter().find(|fq| fq.name == family_name)
    }
}

// ── Region check result ───────────────────────────────────────────────

/// Result of checking a single region's availability for a given SKU.
#[derive(Debug, Clone)]
pub struct RegionCheckResult {
    pub region: String,
    pub sku_available: bool,
    pub quota_available: u32,
    pub quota_limit: u32,
    pub has_capacity: bool,
    pub error: Option<String>,
}

impl RegionCheckResult {
    /// Whether this region is usable (SKU available, has capacity, no error).
    pub fn is_usable(&self) -> bool {
        self.sku_available && self.has_capacity && self.error.is_none()
    }
}

// ── JSON parsers ──────────────────────────────────────────────────────

/// Parse the JSON output of `az vm list-usage --location <region> -o json`.
///
/// Extracts total regional vCPU quota and per-family quotas.
pub fn parse_quota_json(json: &str) -> Result<RegionQuota> {
    let entries: Vec<serde_json::Value> =
        serde_json::from_str(json).context("Failed to parse quota JSON")?;

    if entries.is_empty() {
        anyhow::bail!("Empty quota list — region may not support compute");
    }

    let mut total_used: u32 = 0;
    let mut total_limit: u32 = 0;
    let mut found_total = false;
    let mut family_quotas = Vec::new();

    for entry in &entries {
        let name_value = entry
            .get("name")
            .and_then(|n| n.get("value"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let current = entry
            .get("currentValue")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32;
        let limit = entry
            .get("limit")
            .and_then(|v| v.as_u64())
            .unwrap_or(0) as u32;

        if name_value == "cores" {
            total_used = current;
            total_limit = limit;
            found_total = true;
        } else if !name_value.is_empty() {
            family_quotas.push(FamilyQuota {
                name: name_value.to_string(),
                used: current,
                limit,
            });
        }
    }

    if !found_total {
        anyhow::bail!("No 'Total Regional vCPUs' entry found in quota response");
    }

    Ok(RegionQuota {
        region: String::new(),
        total_regional_used: total_used,
        total_regional_limit: total_limit,
        family_quotas,
    })
}

/// Parse the JSON output of `az vm list-skus --location <region> --size <sku> -o json`.
///
/// Returns `true` if the SKU is listed with no blocking restrictions.
pub fn parse_sku_availability_json(json: &str, target_sku: &str) -> bool {
    let entries: Vec<serde_json::Value> = match serde_json::from_str(json) {
        Ok(v) => v,
        Err(_) => return false,
    };

    for entry in &entries {
        let name = entry.get("name").and_then(|n| n.as_str()).unwrap_or("");
        if name != target_sku {
            continue;
        }

        // Check restrictions array
        let restrictions = entry
            .get("restrictions")
            .and_then(|r| r.as_array())
            .map(|arr| arr.as_slice())
            .unwrap_or(&[]);

        // If any restriction has reasonCode "NotAvailableForSubscription", it's blocked
        let blocked = restrictions.iter().any(|r| {
            r.get("reasonCode")
                .and_then(|rc| rc.as_str())
                .map(|rc| rc == "NotAvailableForSubscription")
                .unwrap_or(false)
        });

        return !blocked;
    }

    // SKU not found in the list
    false
}

// ── Table formatting ──────────────────────────────────────────────────

/// Format region check results as a readable table.
pub fn format_region_table(results: &[RegionCheckResult]) -> String {
    let mut out = String::new();
    let _ = writeln!(
        out,
        "{:<20} {:<10} {:<15} {:<10}",
        "Region", "SKU", "Quota", "Usable"
    );
    let _ = writeln!(out, "{}", "-".repeat(58));

    for r in results {
        let sku_status = if r.error.is_some() {
            "error"
        } else if r.sku_available {
            "available"
        } else {
            "restricted"
        };

        let quota_info = if r.error.is_some() {
            "N/A".to_string()
        } else {
            format!("{}/{}", r.quota_available, r.quota_limit)
        };

        let usable = if r.is_usable() { "✓" } else { "✗" };

        let _ = writeln!(
            out,
            "{:<20} {:<10} {:<15} {:<10}",
            r.region, sku_status, quota_info, usable
        );
    }

    out
}
