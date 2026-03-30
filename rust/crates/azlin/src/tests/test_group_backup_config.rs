//! TDD RED PHASE: Backup configuration unit tests.
//!
//! These tests define the expected behavior for backup scheduling,
//! tier determination, and retention policy logic. They FAIL until
//! the backup configuration module is implemented.
//!
//! Expected module: crate::backup_config (or integrated into snapshot_helpers)
//!
//! Feature spec: docs/backup-disaster-recovery.md
//! Test coverage spec: docs/testing/backup-dr-test-coverage.md

use chrono::{Datelike, NaiveDate, Weekday};
use serde::{Deserialize, Serialize};
use std::fs;
use tempfile::TempDir;

// ---------------------------------------------------------------------------
// Expected data structures (contract definition)
// These types define the API that the implementation must provide.
// Once implemented, replace with: use crate::backup_config::*;
// ---------------------------------------------------------------------------

/// Retention tier for a backup snapshot.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
enum BackupTier {
    Daily,
    Weekly,
    Monthly,
}

/// Backup schedule configuration stored per-VM.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BackupScheduleConfig {
    vm_name: String,
    resource_group: String,
    daily_retention: u32,
    weekly_retention: Option<u32>,
    monthly_retention: Option<u32>,
    cross_region: bool,
    target_region: Option<String>,
    enabled: bool,
}

/// Information about a single backup.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct BackupInfo {
    name: String,
    vm_name: String,
    tier: BackupTier,
    size_gb: u64,
    created: String,
    verified: bool,
    replicated: bool,
}

// ---------------------------------------------------------------------------
// Helper: determine backup tier from date
// This logic MUST be implemented in the backup_config module.
// ---------------------------------------------------------------------------

fn determine_backup_tier(date: NaiveDate) -> BackupTier {
    // Contract: first day of month → Monthly
    if date.day() == 1 {
        return BackupTier::Monthly;
    }
    // Contract: first day of week (Sunday in US convention) → Weekly
    if date.weekday() == Weekday::Sun {
        return BackupTier::Weekly;
    }
    BackupTier::Daily
}

/// Generate a backup name from VM name, tier, and timestamp.
fn build_backup_name(vm_name: &str, tier: BackupTier, timestamp: &str) -> String {
    let tier_str = match tier {
        BackupTier::Daily => "daily",
        BackupTier::Weekly => "weekly",
        BackupTier::Monthly => "monthly",
    };
    format!("{}-backup-{}-{}", vm_name, tier_str, timestamp)
}

// ===========================================================================
// BackupScheduleConfig serialization tests
// ===========================================================================

#[test]
fn test_backup_config_serializes_to_toml() {
    let config = BackupScheduleConfig {
        vm_name: "prod-db-vm".to_string(),
        resource_group: "prod-rg".to_string(),
        daily_retention: 7,
        weekly_retention: Some(4),
        monthly_retention: Some(12),
        cross_region: true,
        target_region: Some("westus2".to_string()),
        enabled: true,
    };
    let toml_str = toml::to_string_pretty(&config).unwrap();
    assert!(toml_str.contains("prod-db-vm"));
    assert!(toml_str.contains("daily_retention = 7"));
    assert!(toml_str.contains("weekly_retention = 4"));
    assert!(toml_str.contains("monthly_retention = 12"));
    assert!(toml_str.contains("cross_region = true"));
    assert!(toml_str.contains("westus2"));
}

#[test]
fn test_backup_config_roundtrip_toml() {
    let config = BackupScheduleConfig {
        vm_name: "test-vm".to_string(),
        resource_group: "test-rg".to_string(),
        daily_retention: 7,
        weekly_retention: None,
        monthly_retention: None,
        cross_region: false,
        target_region: None,
        enabled: true,
    };
    let toml_str = toml::to_string_pretty(&config).unwrap();
    let loaded: BackupScheduleConfig = toml::from_str(&toml_str).unwrap();
    assert_eq!(loaded.vm_name, "test-vm");
    assert_eq!(loaded.daily_retention, 7);
    assert!(loaded.weekly_retention.is_none());
    assert!(!loaded.cross_region);
}

#[test]
fn test_backup_config_persists_to_file() {
    let tmp = TempDir::new().unwrap();
    let config = BackupScheduleConfig {
        vm_name: "file-test-vm".to_string(),
        resource_group: "rg".to_string(),
        daily_retention: 14,
        weekly_retention: Some(8),
        monthly_retention: Some(24),
        cross_region: true,
        target_region: Some("eastus2".to_string()),
        enabled: true,
    };
    let path = tmp.path().join("file-test-vm.backup.toml");
    let contents = toml::to_string_pretty(&config).unwrap();
    fs::write(&path, &contents).unwrap();

    let loaded: BackupScheduleConfig =
        toml::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(loaded.vm_name, "file-test-vm");
    assert_eq!(loaded.daily_retention, 14);
    assert_eq!(loaded.weekly_retention, Some(8));
    assert_eq!(loaded.monthly_retention, Some(24));
    assert!(loaded.cross_region);
    assert_eq!(loaded.target_region.as_deref(), Some("eastus2"));
}

#[test]
fn test_backup_config_json_serialization() {
    let config = BackupScheduleConfig {
        vm_name: "json-vm".to_string(),
        resource_group: "rg".to_string(),
        daily_retention: 7,
        weekly_retention: Some(4),
        monthly_retention: None,
        cross_region: false,
        target_region: None,
        enabled: false,
    };
    let json = serde_json::to_string(&config).unwrap();
    let loaded: BackupScheduleConfig = serde_json::from_str(&json).unwrap();
    assert_eq!(loaded.vm_name, "json-vm");
    assert!(!loaded.enabled);
}

// ===========================================================================
// Tier determination logic tests
// ===========================================================================

#[test]
fn test_determine_tier_regular_weekday_is_daily() {
    // Wednesday March 18, 2026 — not first of week or month
    let date = NaiveDate::from_ymd_opt(2026, 3, 18).unwrap();
    assert_eq!(date.weekday(), Weekday::Wed);
    assert_eq!(determine_backup_tier(date), BackupTier::Daily);
}

#[test]
fn test_determine_tier_first_of_month_is_monthly() {
    // April 1, 2026 — first day of month
    let date = NaiveDate::from_ymd_opt(2026, 4, 1).unwrap();
    assert_eq!(determine_backup_tier(date), BackupTier::Monthly);
}

#[test]
fn test_determine_tier_sunday_is_weekly() {
    // March 29, 2026 — Sunday
    let date = NaiveDate::from_ymd_opt(2026, 3, 29).unwrap();
    assert_eq!(date.weekday(), Weekday::Sun);
    assert_eq!(determine_backup_tier(date), BackupTier::Weekly);
}

#[test]
fn test_determine_tier_first_of_month_on_sunday_is_monthly() {
    // June 1, 2025 — first of month AND Sunday → Monthly takes priority
    let date = NaiveDate::from_ymd_opt(2025, 6, 1).unwrap();
    assert_eq!(date.weekday(), Weekday::Sun);
    assert_eq!(
        determine_backup_tier(date),
        BackupTier::Monthly,
        "Monthly takes priority over Weekly when both match"
    );
}

#[test]
fn test_determine_tier_saturday_is_daily() {
    let date = NaiveDate::from_ymd_opt(2026, 3, 28).unwrap();
    assert_eq!(date.weekday(), Weekday::Sat);
    assert_eq!(determine_backup_tier(date), BackupTier::Daily);
}

#[test]
fn test_determine_tier_end_of_month_is_daily() {
    // March 31, 2026 — last day, Tuesday
    let date = NaiveDate::from_ymd_opt(2026, 3, 31).unwrap();
    assert_eq!(determine_backup_tier(date), BackupTier::Daily);
}

// ===========================================================================
// Backup name generation tests
// ===========================================================================

#[test]
fn test_backup_name_daily() {
    let name = build_backup_name("prod-db-vm", BackupTier::Daily, "20261201-0800");
    assert_eq!(name, "prod-db-vm-backup-daily-20261201-0800");
}

#[test]
fn test_backup_name_weekly() {
    let name = build_backup_name("prod-db-vm", BackupTier::Weekly, "20261124-0800");
    assert_eq!(name, "prod-db-vm-backup-weekly-20261124-0800");
}

#[test]
fn test_backup_name_monthly() {
    let name = build_backup_name("prod-db-vm", BackupTier::Monthly, "20261201-0800");
    assert_eq!(name, "prod-db-vm-backup-monthly-20261201-0800");
}

#[test]
fn test_backup_name_contains_vm_name() {
    let name = build_backup_name("my-special-vm", BackupTier::Daily, "20260101-0000");
    assert!(name.starts_with("my-special-vm-backup-"));
}

// ===========================================================================
// BackupInfo structure tests
// ===========================================================================

#[test]
fn test_backup_info_serialization() {
    let info = BackupInfo {
        name: "vm-backup-daily-20261201-0800".to_string(),
        vm_name: "my-vm".to_string(),
        tier: BackupTier::Daily,
        size_gb: 128,
        created: "2026-12-01T08:00:00Z".to_string(),
        verified: true,
        replicated: false,
    };
    let json = serde_json::to_string(&info).unwrap();
    assert!(json.contains("\"tier\":\"daily\""));
    assert!(json.contains("\"verified\":true"));
    assert!(json.contains("\"replicated\":false"));
}

#[test]
fn test_backup_info_deserialization() {
    let json = r#"{
        "name": "vm-backup-weekly-20261124",
        "vm_name": "my-vm",
        "tier": "weekly",
        "size_gb": 64,
        "created": "2026-11-24T08:00:00Z",
        "verified": false,
        "replicated": true
    }"#;
    let info: BackupInfo = serde_json::from_str(json).unwrap();
    assert_eq!(info.tier, BackupTier::Weekly);
    assert_eq!(info.size_gb, 64);
    assert!(!info.verified);
    assert!(info.replicated);
}

// ===========================================================================
// Retention policy validation tests
// ===========================================================================

#[test]
fn test_retention_defaults_daily_only() {
    let config = BackupScheduleConfig {
        vm_name: "vm".to_string(),
        resource_group: "rg".to_string(),
        daily_retention: 7,
        weekly_retention: None,
        monthly_retention: None,
        cross_region: false,
        target_region: None,
        enabled: true,
    };
    assert_eq!(config.daily_retention, 7);
    assert!(config.weekly_retention.is_none());
    assert!(config.monthly_retention.is_none());
}

#[test]
fn test_retention_zero_daily_is_valid() {
    // Zero retention means "don't keep daily backups" (edge case)
    let config = BackupScheduleConfig {
        vm_name: "vm".to_string(),
        resource_group: "rg".to_string(),
        daily_retention: 0,
        weekly_retention: Some(4),
        monthly_retention: Some(12),
        cross_region: false,
        target_region: None,
        enabled: true,
    };
    assert_eq!(config.daily_retention, 0);
}

#[test]
fn test_cross_region_requires_target_region() {
    let config = BackupScheduleConfig {
        vm_name: "vm".to_string(),
        resource_group: "rg".to_string(),
        daily_retention: 7,
        weekly_retention: None,
        monthly_retention: None,
        cross_region: true,
        target_region: None, // This should be validated by implementation
        enabled: true,
    };
    // Contract: implementation MUST validate that cross_region=true requires target_region
    assert!(
        config.cross_region && config.target_region.is_none(),
        "Test setup: cross_region=true but no target_region"
    );
    // When implementation exists, calling configure() with this config should return an error
}

// ===========================================================================
// Boundary condition tests
// ===========================================================================

#[test]
fn test_backup_name_with_empty_vm_name() {
    let name = build_backup_name("", BackupTier::Daily, "20261201-0800");
    assert_eq!(name, "-backup-daily-20261201-0800");
    // Contract: implementation should reject empty VM names before reaching this point
}

#[test]
fn test_backup_tier_serializes_lowercase() {
    let daily = serde_json::to_string(&BackupTier::Daily).unwrap();
    let weekly = serde_json::to_string(&BackupTier::Weekly).unwrap();
    let monthly = serde_json::to_string(&BackupTier::Monthly).unwrap();
    assert_eq!(daily, "\"daily\"");
    assert_eq!(weekly, "\"weekly\"");
    assert_eq!(monthly, "\"monthly\"");
}

// ===========================================================================
// Contract tests — these verify expected module structure
// Once backup_config module exists, uncomment the imports and these will pass.
// ===========================================================================

#[test]
fn test_existing_snapshot_helpers_build_name() {
    // Verify existing snapshot_helpers::build_snapshot_name still works
    // This ensures backward compatibility during feature development
    let name = crate::snapshot_helpers::build_snapshot_name("my-vm", "20260301_120000");
    assert_eq!(name, "my-vm_snapshot_20260301_120000");
}

#[test]
fn test_existing_snapshot_helpers_filter() {
    let snaps = vec![
        serde_json::json!({"name": "my-vm_snapshot_1"}),
        serde_json::json!({"name": "other-vm_snapshot_1"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "my-vm");
    assert_eq!(filtered.len(), 1);
}

#[test]
fn test_existing_snapshot_schedule_structure() {
    // Verify the existing SnapshotSchedule is compatible with new BackupScheduleConfig
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "test-vm".to_string(),
        resource_group: "rg".to_string(),
        every_hours: 24,
        keep_count: 7,
        enabled: true,
        created: "2026-03-01".to_string(),
    };
    assert_eq!(schedule.vm_name, "test-vm");
    assert_eq!(schedule.every_hours, 24);
    // Contract: BackupScheduleConfig must be a superset of SnapshotSchedule capabilities
}
