use serde::{Deserialize, Serialize};

/// An orphaned Azure resource
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrphanedResource {
    pub name: String,
    pub resource_type: ResourceType,
    pub resource_group: String,
    pub estimated_monthly_cost: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum ResourceType {
    Disk,
    NetworkInterface,
    PublicIp,
    NetworkSecurityGroup,
}

impl std::fmt::Display for ResourceType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Disk => write!(f, "Disk"),
            Self::NetworkInterface => write!(f, "NIC"),
            Self::PublicIp => write!(f, "Public IP"),
            Self::NetworkSecurityGroup => write!(f, "NSG"),
        }
    }
}

/// Parse Azure disk list output to find unattached disks
pub fn find_orphaned_disks(disk_json: &str) -> Vec<OrphanedResource> {
    let disks: Vec<serde_json::Value> = serde_json::from_str(disk_json).unwrap_or_default();
    disks
        .iter()
        .filter(|d| {
            d.get("diskState").and_then(|s| s.as_str()) == Some("Unattached")
                || d.get("managedBy").map(|m| m.is_null()).unwrap_or(true)
        })
        .filter_map(|d| {
            let name = d.get("name")?.as_str()?.to_string();
            let rg = d
                .get("resourceGroup")
                .and_then(|r| r.as_str())
                .unwrap_or("unknown")
                .to_string();
            let size_gb = d.get("diskSizeGb").and_then(|s| s.as_f64()).unwrap_or(0.0);
            // Estimate: ~$0.04/GB/month for standard SSD
            let cost = size_gb * 0.04;
            Some(OrphanedResource {
                name,
                resource_type: ResourceType::Disk,
                resource_group: rg,
                estimated_monthly_cost: cost,
            })
        })
        .collect()
}

/// Calculate total estimated savings from cleaning up orphaned resources
pub fn total_estimated_savings(resources: &[OrphanedResource]) -> f64 {
    resources.iter().map(|r| r.estimated_monthly_cost).sum()
}

/// Format orphaned resources as a summary string
pub fn format_orphan_summary(resources: &[OrphanedResource]) -> String {
    if resources.is_empty() {
        return "✅ No orphaned resources found.".to_string();
    }

    let mut msg = format!("⚠️ Found {} orphaned resource(s):\n\n", resources.len());
    for r in resources {
        msg.push_str(&format!(
            "  {} {} ({}) - ${:.2}/mo\n",
            r.resource_type, r.name, r.resource_group, r.estimated_monthly_cost
        ));
    }
    msg.push_str(&format!(
        "\n💰 Estimated savings: ${:.2}/month\n",
        total_estimated_savings(resources)
    ));
    msg
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_find_orphaned_disks() {
        let json = r#"[
            {"name": "disk1", "diskState": "Unattached", "resourceGroup": "rg1", "diskSizeGb": 128},
            {"name": "disk2", "diskState": "Attached", "managedBy": "/subscriptions/.../vms/vm1", "resourceGroup": "rg1", "diskSizeGb": 64}
        ]"#;
        let orphans = find_orphaned_disks(json);
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "disk1");
        assert!((orphans[0].estimated_monthly_cost - 5.12).abs() < 0.01);
    }

    #[test]
    fn test_find_orphaned_disks_empty() {
        assert!(find_orphaned_disks("[]").is_empty());
    }

    #[test]
    fn test_find_orphaned_disks_invalid_json() {
        assert!(find_orphaned_disks("not json").is_empty());
    }

    #[test]
    fn test_total_savings() {
        let resources = vec![
            OrphanedResource {
                name: "d1".into(),
                resource_type: ResourceType::Disk,
                resource_group: "rg".into(),
                estimated_monthly_cost: 5.0,
            },
            OrphanedResource {
                name: "d2".into(),
                resource_type: ResourceType::Disk,
                resource_group: "rg".into(),
                estimated_monthly_cost: 3.0,
            },
        ];
        assert!((total_estimated_savings(&resources) - 8.0).abs() < 0.01);
    }

    #[test]
    fn test_format_empty_summary() {
        assert!(format_orphan_summary(&[]).contains("No orphaned"));
    }

    #[test]
    fn test_format_summary_with_resources() {
        let resources = vec![OrphanedResource {
            name: "d1".into(),
            resource_type: ResourceType::Disk,
            resource_group: "rg1".into(),
            estimated_monthly_cost: 5.12,
        }];
        let summary = format_orphan_summary(&resources);
        assert!(summary.contains("1 orphaned"));
        assert!(summary.contains("$5.12"));
    }

    #[test]
    fn test_resource_type_display() {
        assert_eq!(format!("{}", ResourceType::Disk), "Disk");
        assert_eq!(format!("{}", ResourceType::NetworkInterface), "NIC");
        assert_eq!(format!("{}", ResourceType::PublicIp), "Public IP");
    }
}
