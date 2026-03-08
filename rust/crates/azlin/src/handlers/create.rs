//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

use azlin_core::models::VmInfo;

// ── Create VM result formatting ─────────────────────────────────────

/// Build property rows for a newly created VM (for table display).
pub fn build_create_vm_rows(
    vm: &VmInfo,
    resource_group: &str,
    vm_size: &str,
    region: &str,
) -> Vec<(String, String)> {
    let mut rows = vec![
        ("Name".to_string(), vm.name.clone()),
        ("Resource Group".to_string(), resource_group.to_string()),
        ("Size".to_string(), vm_size.to_string()),
        ("Region".to_string(), region.to_string()),
        ("State".to_string(), vm.power_state.to_string()),
    ];
    if let Some(ref ip) = vm.public_ip {
        rows.push(("Public IP".to_string(), ip.clone()));
    }
    if let Some(ref ip) = vm.private_ip {
        rows.push(("Private IP".to_string(), ip.clone()));
    }
    rows
}

// ── Doit VM filtering ───────────────────────────────────────────────

/// Filter VMs tagged as doit-created, optionally by username.
pub fn filter_doit_vms<'a>(vms: &'a [VmInfo], username: Option<&str>) -> Vec<&'a VmInfo> {
    vms.iter()
        .filter(|vm| {
            let has_tag = vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
            let user_match = username.is_none_or(|u| vm.admin_username.as_deref() == Some(u));
            has_tag && user_match
        })
        .collect()
}
