//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Orphan cost estimation ──────────────────────────────────────────────

/// Estimate monthly cost of orphaned public IPs.
pub fn estimate_orphan_costs(orphan_count: usize, cost_per_ip: f64) -> String {
    let total = orphan_count as f64 * cost_per_ip;
    format!(
        "{} orphaned public IP(s) estimated at ${:.2}/month",
        orphan_count, total
    )
}

// ── Cleanup / orphan detection helpers ───────────────────────────────

/// Parse NIC JSON array and classify orphaned NICs (no VM attached).
pub fn classify_orphaned_nics(nics: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nics.iter()
        .filter(|nic| {
            let attached = nic
                .get("virtualMachine")
                .map(|v| !v.is_null())
                .unwrap_or(false);
            !attached
        })
        .filter_map(|nic| {
            let name = nic.get("name")?.as_str()?.to_string();
            let rg = nic
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            Some(OrphanedResourceInfo {
                name,
                resource_type: "NIC".to_string(),
                resource_group: rg,
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Parse public IP JSON array and classify orphaned IPs (no ipConfiguration).
pub fn classify_orphaned_ips(
    ips: &[serde_json::Value],
    cost_per_ip: f64,
) -> Vec<OrphanedResourceInfo> {
    ips.iter()
        .filter(|ip| {
            let attached = ip
                .get("ipConfiguration")
                .map(|v| !v.is_null())
                .unwrap_or(false);
            !attached
        })
        .filter_map(|ip| {
            let name = ip.get("name")?.as_str()?.to_string();
            let rg = ip
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            Some(OrphanedResourceInfo {
                name,
                resource_type: "Public IP".to_string(),
                resource_group: rg,
                estimated_monthly_cost: cost_per_ip,
            })
        })
        .collect()
}

/// Parse NSG JSON array and classify orphaned NSGs (no NICs or subnets attached).
pub fn classify_orphaned_nsgs(nsgs: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nsgs.iter()
        .filter(|nsg| {
            let has_nics = nsg
                .get("networkInterfaces")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            let has_subnets = nsg
                .get("subnets")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            !has_nics && !has_subnets
        })
        .filter_map(|nsg| {
            let name = nsg.get("name")?.as_str()?.to_string();
            let rg = nsg
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            Some(OrphanedResourceInfo {
                name,
                resource_type: "NSG".to_string(),
                resource_group: rg,
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Lightweight orphaned resource info for handler-level logic.
/// Uses String resource_type to avoid coupling to azlin_azure types.
#[derive(Debug, Clone, PartialEq)]
pub struct OrphanedResourceInfo {
    pub name: String,
    pub resource_type: String,
    pub resource_group: String,
    pub estimated_monthly_cost: f64,
}

/// Build a cleanup plan: list of resources to delete, with dry_run annotation.
pub fn build_cleanup_plan(resources: &[OrphanedResourceInfo], dry_run: bool) -> Vec<CleanupAction> {
    resources
        .iter()
        .map(|r| CleanupAction {
            resource_name: r.name.clone(),
            resource_type: r.resource_type.clone(),
            resource_group: r.resource_group.clone(),
            action: if dry_run {
                "would delete".to_string()
            } else {
                "delete".to_string()
            },
        })
        .collect()
}

/// A planned cleanup action.
#[derive(Debug, Clone, PartialEq)]
pub struct CleanupAction {
    pub resource_name: String,
    pub resource_type: String,
    pub resource_group: String,
    pub action: String,
}

/// Format an orphan report from a list of orphaned resources.
pub fn format_orphan_report(resources: &[OrphanedResourceInfo]) -> String {
    if resources.is_empty() {
        return "No orphaned resources found.".to_string();
    }
    let mut out = format!("Found {} orphaned resource(s):\n", resources.len());
    let total_cost: f64 = resources.iter().map(|r| r.estimated_monthly_cost).sum();
    for r in resources {
        out.push_str(&format!(
            "  {} '{}' ({}) - ${:.2}/mo\n",
            r.resource_type, r.name, r.resource_group, r.estimated_monthly_cost
        ));
    }
    out.push_str(&format!("Estimated savings: ${:.2}/month", total_cost));
    out
}

// ── Cleanup/orphan classification handlers ──────────────────────────────

/// Classify NICs as orphaned if they have no virtual machine attached.
/// Pure function over parsed JSON — no CLI calls.
pub fn find_orphaned_nics(nics: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nics.iter()
        .filter(|nic| {
            !nic.get("virtualMachine")
                .map(|v| !v.is_null())
                .unwrap_or(false)
        })
        .filter_map(|nic| {
            let name = nic.get("name")?.as_str()?;
            let rg = nic
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown");
            Some(OrphanedResourceInfo {
                name: name.to_string(),
                resource_type: "NetworkInterface".to_string(),
                resource_group: rg.to_string(),
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Classify public IPs as orphaned if they have no ipConfiguration.
pub fn find_orphaned_public_ips(
    ips: &[serde_json::Value],
    cost_per_ip: f64,
) -> Vec<OrphanedResourceInfo> {
    ips.iter()
        .filter(|ip| {
            !ip.get("ipConfiguration")
                .map(|v| !v.is_null())
                .unwrap_or(false)
        })
        .filter_map(|ip| {
            let name = ip.get("name")?.as_str()?;
            let rg = ip
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown");
            Some(OrphanedResourceInfo {
                name: name.to_string(),
                resource_type: "PublicIp".to_string(),
                resource_group: rg.to_string(),
                estimated_monthly_cost: cost_per_ip,
            })
        })
        .collect()
}

/// Classify NSGs as orphaned if they have no attached NICs or subnets.
pub fn find_orphaned_nsgs(nsgs: &[serde_json::Value]) -> Vec<OrphanedResourceInfo> {
    nsgs.iter()
        .filter(|nsg| {
            let has_nics = nsg
                .get("networkInterfaces")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            let has_subnets = nsg
                .get("subnets")
                .and_then(|v| v.as_array())
                .map(|a| !a.is_empty())
                .unwrap_or(false);
            !has_nics && !has_subnets
        })
        .filter_map(|nsg| {
            let name = nsg.get("name")?.as_str()?;
            let rg = nsg
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown");
            Some(OrphanedResourceInfo {
                name: name.to_string(),
                resource_type: "NetworkSecurityGroup".to_string(),
                resource_group: rg.to_string(),
                estimated_monthly_cost: 0.0,
            })
        })
        .collect()
}

/// Format a cleanup summary line.
pub fn format_cleanup_complete(deleted: usize, total: usize) -> String {
    format!(
        "Cleanup complete. Deleted {}/{} orphaned resources.",
        deleted, total
    )
}

/// Format the scan header for cleanup.
pub fn format_cleanup_scan_header(resource_group: &str, age_days: u32, dry_run: bool) -> String {
    format!(
        "{}Scanning for orphaned resources in '{}' (older than {} days)...",
        if dry_run { "Dry run — " } else { "" },
        resource_group,
        age_days
    )
}
