use serde::{Deserialize, Serialize};

/// An orphaned Azure resource
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrphanedResource {
    pub name: String,
    pub resource_type: ResourceType,
    pub resource_group: String,
    pub estimated_monthly_cost: f64,
    /// When Azure says the resource was created, when it says at all.
    ///
    /// `None` is not "new": most of these types report no creation time in
    /// their list output at all, and a caller filtering by age has to keep
    /// "created recently" apart from "we do not know when". Treating unknown
    /// as new would hide resources that are billing; treating it as old would
    /// delete resources that are not.
    pub created_time: Option<chrono::DateTime<chrono::Utc>>,
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
pub fn find_orphaned_disks(disk_json: &str) -> anyhow::Result<Vec<OrphanedResource>> {
    let disks: Vec<serde_json::Value> = serde_json::from_str(disk_json)
        .map_err(|e| anyhow::anyhow!("Failed to parse disk list JSON: {e}"))?;
    Ok(disks
        .iter()
        .filter(|d| {
            // A disk is orphaned only if BOTH conditions are true:
            // 1. diskState is "Unattached" (not in use by any VM)
            // 2. managedBy is null/missing (no VM owns it)
            // Using AND prevents false positives during provisioning transitions
            // where diskState might be "Attached" but managedBy is temporarily null.
            let is_unattached = d.get("diskState").and_then(|s| s.as_str()) == Some("Unattached");
            let no_manager = d.get("managedBy").map(|m| m.is_null()).unwrap_or(true);
            is_unattached && no_manager
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
            // `az disk list` is the one orphan source that reports a creation
            // time, which is what makes `azlin cleanup --age-days` mean
            // anything at all.
            let created_time = d
                .get("timeCreated")
                .and_then(|t| t.as_str())
                .and_then(|t| chrono::DateTime::parse_from_rfc3339(t).ok())
                .map(|t| t.with_timezone(&chrono::Utc));
            Some(OrphanedResource {
                name,
                resource_type: ResourceType::Disk,
                resource_group: rg,
                estimated_monthly_cost: cost,
                created_time,
            })
        })
        .collect())
}

/// Split orphans into those older than `age_days` and those held back.
///
/// `azlin cleanup` printed "Scanning for orphaned resources in 'rg' (older
/// than 1 days)..." and then listed and deleted every orphan regardless of
/// age. The flag reached the header and nothing else — which is worse than the
/// flags that were dropped outright, because the output said it had been
/// applied (#1089).
///
/// A resource with **no** creation time is kept, not filtered out. Only
/// `az disk list` reports one; NICs, public IPs and NSGs do not, and dropping
/// them because their age is unknown would silently stop cleaning up the
/// majority of what this command exists to clean up. The caller says which is
/// which, so "we did not filter these" is never mistaken for "these are old".
///
/// `age_days == 0` keeps everything, which is what "older than zero days"
/// means.
pub fn partition_by_age(
    resources: Vec<OrphanedResource>,
    age_days: u32,
    now: chrono::DateTime<chrono::Utc>,
) -> (Vec<OrphanedResource>, Vec<OrphanedResource>) {
    if age_days == 0 {
        return (resources, Vec::new());
    }
    let cutoff = now - chrono::Duration::days(age_days as i64);
    resources.into_iter().partition(|r| match r.created_time {
        Some(created) => created <= cutoff,
        None => true,
    })
}

/// How many of these resources Azure gave no creation time for.
///
/// Reported so "unfiltered" is visible rather than assumed.
pub fn undated_count(resources: &[OrphanedResource]) -> usize {
    resources
        .iter()
        .filter(|r| r.created_time.is_none())
        .count()
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
    // ── `--age-days` (#1089) ─────────────────────────────────────────

    fn orphan(name: &str, created: Option<&str>) -> OrphanedResource {
        OrphanedResource {
            name: name.to_string(),
            resource_type: ResourceType::Disk,
            resource_group: "rg".to_string(),
            estimated_monthly_cost: 1.0,
            created_time: created.map(|t| {
                chrono::DateTime::parse_from_rfc3339(t)
                    .unwrap()
                    .with_timezone(&chrono::Utc)
            }),
        }
    }

    fn now() -> chrono::DateTime<chrono::Utc> {
        chrono::DateTime::parse_from_rfc3339("2026-08-20T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc)
    }

    #[test]
    fn a_resource_newer_than_the_threshold_is_held_back() {
        let (old, held) = partition_by_age(
            vec![
                orphan("ancient", Some("2026-01-01T00:00:00Z")),
                orphan("yesterday", Some("2026-08-19T12:00:00Z")),
            ],
            7,
            now(),
        );
        assert_eq!(old.len(), 1);
        assert_eq!(old[0].name, "ancient");
        assert_eq!(held.len(), 1);
        assert_eq!(held[0].name, "yesterday");
    }

    /// Only `az disk list` reports a creation time. Dropping NICs, public IPs
    /// and NSGs for having an unknown age would silently stop cleaning up most
    /// of what this command exists for.
    #[test]
    fn a_resource_with_no_creation_time_is_kept_not_dropped() {
        let (old, held) = partition_by_age(vec![orphan("nic-1", None)], 7, now());
        assert_eq!(old.len(), 1);
        assert!(held.is_empty());
        assert_eq!(undated_count(&old), 1);
    }

    /// "Older than zero days" is everything, which is also what the flag's
    /// default of 1 must not silently become.
    #[test]
    fn zero_days_keeps_everything() {
        let (old, held) =
            partition_by_age(vec![orphan("new", Some("2026-08-19T23:59:00Z"))], 0, now());
        assert_eq!(old.len(), 1);
        assert!(held.is_empty());
    }

    /// Exactly at the cutoff counts as old enough: a disk created seven days
    /// ago is seven days old.
    #[test]
    fn the_cutoff_is_inclusive() {
        let (old, _) = partition_by_age(
            vec![orphan("exact", Some("2026-08-13T00:00:00Z"))],
            7,
            now(),
        );
        assert_eq!(old.len(), 1);
    }

    /// The creation time has to survive parsing, or every disk becomes
    /// undated and `--age-days` quietly does nothing again.
    #[test]
    fn disk_creation_time_is_read_from_azure() {
        let json = r#"[{"name":"d1","diskState":"Unattached","managedBy":null,
                        "resourceGroup":"rg","diskSizeGb":128,
                        "timeCreated":"2026-01-02T03:04:05.678901+00:00"}]"#;
        let found = find_orphaned_disks(json).unwrap();
        assert_eq!(found.len(), 1);
        assert!(
            found[0].created_time.is_some(),
            "a disk with a timeCreated must not come back undated"
        );
    }

    /// And a disk whose timestamp Azure omits or mangles is undated rather
    /// than dated to now — which would make it look new and spare it forever.
    #[test]
    fn an_unparsable_creation_time_is_undated() {
        let json = r#"[{"name":"d1","diskState":"Unattached","managedBy":null,
                        "resourceGroup":"rg","timeCreated":"not a date"}]"#;
        let found = find_orphaned_disks(json).unwrap();
        assert_eq!(found[0].created_time, None);
    }

    use super::*;

    #[test]
    fn test_find_orphaned_disks() {
        let json = r#"[
            {"name": "disk1", "diskState": "Unattached", "resourceGroup": "rg1", "diskSizeGb": 128},
            {"name": "disk2", "diskState": "Attached", "managedBy": "/subscriptions/.../vms/vm1", "resourceGroup": "rg1", "diskSizeGb": 64}
        ]"#;
        let orphans = find_orphaned_disks(json).unwrap();
        assert_eq!(orphans.len(), 1);
        assert_eq!(orphans[0].name, "disk1");
        assert!((orphans[0].estimated_monthly_cost - 5.12).abs() < 0.01);
    }

    #[test]
    fn test_attached_disk_with_null_managed_by_not_orphaned() {
        // Regression test: a disk in "Attached" state with null managedBy
        // (which can happen during provisioning transitions) should NOT
        // be flagged as orphaned. The AND logic fix prevents this.
        let json = r#"[
            {"name": "transitioning-disk", "diskState": "Attached", "managedBy": null, "resourceGroup": "rg1", "diskSizeGb": 64}
        ]"#;
        let orphans = find_orphaned_disks(json).unwrap();
        assert!(
            orphans.is_empty(),
            "Attached disk with null managedBy should NOT be flagged as orphaned"
        );
    }

    #[test]
    fn test_unattached_disk_with_valid_manager_not_orphaned() {
        // A disk that is "Unattached" but still has a managedBy reference
        // (e.g., being detached but not yet cleaned up) should not be orphaned.
        let json = r#"[
            {"name": "detaching-disk", "diskState": "Unattached", "managedBy": "/subscriptions/.../vms/vm1", "resourceGroup": "rg1", "diskSizeGb": 64}
        ]"#;
        let orphans = find_orphaned_disks(json).unwrap();
        assert!(
            orphans.is_empty(),
            "Unattached disk with valid managedBy should NOT be flagged as orphaned"
        );
    }

    #[test]
    fn test_find_orphaned_disks_empty() {
        assert!(find_orphaned_disks("[]").unwrap().is_empty());
    }

    #[test]
    fn test_find_orphaned_disks_invalid_json() {
        assert!(find_orphaned_disks("not json").is_err());
    }

    #[test]
    fn test_total_savings() {
        let resources = vec![
            OrphanedResource {
                name: "d1".into(),
                resource_type: ResourceType::Disk,
                resource_group: "rg".into(),
                estimated_monthly_cost: 5.0,
                created_time: None,
            },
            OrphanedResource {
                name: "d2".into(),
                resource_type: ResourceType::Disk,
                resource_group: "rg".into(),
                estimated_monthly_cost: 3.0,
                created_time: None,
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
            created_time: None,
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
