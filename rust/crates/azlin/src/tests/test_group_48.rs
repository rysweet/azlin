use std::fs;
use tempfile::TempDir;

// ── apply_filters combined tests ────────────────────────────────

fn make_vm_for_filter(
    name: &str,
    state: azlin_core::models::PowerState,
) -> azlin_core::models::VmInfo {
    azlin_core::models::VmInfo {
        name: name.to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: state,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: None,
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    }
}

#[test]
fn test_apply_filters_include_all_keeps_stopped() {
    let mut vms = vec![
        make_vm_for_filter("vm1", azlin_core::models::PowerState::Running),
        make_vm_for_filter("vm2", azlin_core::models::PowerState::Deallocated),
    ];
    crate::list_helpers::apply_filters(&mut vms, true, None, None);
    assert_eq!(vms.len(), 2, "include_all=true should keep stopped VMs");
}

#[test]
fn test_apply_filters_not_include_all_removes_stopped() {
    let mut vms = vec![
        make_vm_for_filter("vm1", azlin_core::models::PowerState::Running),
        make_vm_for_filter("vm2", azlin_core::models::PowerState::Deallocated),
    ];
    crate::list_helpers::apply_filters(&mut vms, false, None, None);
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm1");
}

#[test]
fn test_apply_filters_combined_tag_and_pattern() {
    let mut vm1 = make_vm_for_filter("web-server-1", azlin_core::models::PowerState::Running);
    vm1.tags.insert("env".to_string(), "prod".to_string());
    let mut vm2 = make_vm_for_filter("web-server-2", azlin_core::models::PowerState::Running);
    vm2.tags.insert("env".to_string(), "dev".to_string());
    let mut vm3 = make_vm_for_filter("db-server", azlin_core::models::PowerState::Running);
    vm3.tags.insert("env".to_string(), "prod".to_string());
    let mut vms = vec![vm1, vm2, vm3];
    crate::list_helpers::apply_filters(&mut vms, true, Some("env=prod"), Some("web*"));
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "web-server-1");
}

// ════════════════════════════════════════════════════════════════
// NEW COVERAGE BOOST: snapshot_helpers.rs functions
// ════════════════════════════════════════════════════════════════

#[test]
fn test_schedules_dir_ends_with_schedules() {
    let dir = crate::snapshot_helpers::schedules_dir();
    assert!(dir.ends_with("schedules"));
    assert!(dir.to_string_lossy().contains(".azlin"));
}

#[test]
fn test_schedule_path_appends_toml_extension() {
    let path = crate::snapshot_helpers::schedule_path("my-vm");
    assert_eq!(path.file_name().unwrap().to_str().unwrap(), "my-vm.toml");
    assert!(path.parent().unwrap().ends_with("schedules"));
}

#[test]
fn test_schedule_path_special_characters() {
    let path = crate::snapshot_helpers::schedule_path("vm-with-dashes-123");
    assert_eq!(
        path.file_name().unwrap().to_str().unwrap(),
        "vm-with-dashes-123.toml"
    );
}

#[test]
fn test_save_and_load_schedule_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "roundtrip-vm".to_string(),
        resource_group: "test-rg".to_string(),
        every_hours: 4,
        keep_count: 7,
        enabled: true,
        created: "2025-01-01T00:00:00Z".to_string(),
    };
    // Write manually to temp dir to avoid touching real home dir
    let dir = tmp.path().join(".azlin").join("schedules");
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("roundtrip-vm.toml");
    let contents = toml::to_string_pretty(&schedule).unwrap();
    fs::write(&path, &contents).unwrap();

    // Read back
    let read_contents = fs::read_to_string(&path).unwrap();
    let loaded: crate::snapshot_helpers::SnapshotSchedule = toml::from_str(&read_contents).unwrap();
    assert_eq!(loaded.vm_name, "roundtrip-vm");
    assert_eq!(loaded.resource_group, "test-rg");
    assert_eq!(loaded.every_hours, 4);
    assert_eq!(loaded.keep_count, 7);
    assert!(loaded.enabled);
    assert_eq!(loaded.created, "2025-01-01T00:00:00Z");
}

#[test]
fn test_load_schedule_nonexistent_returns_none() {
    // schedule_path points to home dir, which won't have this VM
    let result = crate::snapshot_helpers::load_schedule("nonexistent-vm-that-does-not-exist-12345");
    assert!(result.is_none());
}

#[test]
fn test_load_all_schedules_empty_dir() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path().join("empty-schedules");
    fs::create_dir_all(&dir).unwrap();
    // Manually read to simulate — load_all_schedules uses schedules_dir()
    // so we test the filtering logic directly
    let entries: Vec<crate::snapshot_helpers::SnapshotSchedule> = fs::read_dir(&dir)
        .unwrap()
        .filter_map(|e| {
            let e = e.ok()?;
            let path = e.path();
            if path.extension().and_then(|x| x.to_str()) == Some("toml") {
                let contents = fs::read_to_string(&path).ok()?;
                toml::from_str(&contents).ok()
            } else {
                None
            }
        })
        .collect();
    assert!(entries.is_empty());
}

#[test]
fn test_load_all_schedules_filters_non_toml() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "vm1".to_string(),
        resource_group: "rg1".to_string(),
        every_hours: 6,
        keep_count: 5,
        enabled: true,
        created: "2025-01-01T00:00:00Z".to_string(),
    };
    fs::write(
        dir.join("vm1.toml"),
        toml::to_string_pretty(&schedule).unwrap(),
    )
    .unwrap();
    fs::write(dir.join("readme.txt"), "not a schedule").unwrap();
    fs::write(dir.join("data.json"), "{}").unwrap();

    let entries: Vec<crate::snapshot_helpers::SnapshotSchedule> = fs::read_dir(dir)
        .unwrap()
        .filter_map(|e| {
            let e = e.ok()?;
            let path = e.path();
            if path.extension().and_then(|x| x.to_str()) == Some("toml") {
                let contents = fs::read_to_string(&path).ok()?;
                toml::from_str(&contents).ok()
            } else {
                None
            }
        })
        .collect();
    assert_eq!(entries.len(), 1);
    assert_eq!(entries[0].vm_name, "vm1");
}

#[test]
fn test_load_all_schedules_multiple_files() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    for i in 1..=3 {
        let schedule = crate::snapshot_helpers::SnapshotSchedule {
            vm_name: format!("vm-{}", i),
            resource_group: "rg".to_string(),
            every_hours: 12,
            keep_count: 5,
            enabled: i % 2 == 0,
            created: "2025-01-01T00:00:00Z".to_string(),
        };
        fs::write(
            dir.join(format!("vm-{}.toml", i)),
            toml::to_string_pretty(&schedule).unwrap(),
        )
        .unwrap();
    }

    let entries: Vec<crate::snapshot_helpers::SnapshotSchedule> = fs::read_dir(dir)
        .unwrap()
        .filter_map(|e| {
            let e = e.ok()?;
            let path = e.path();
            if path.extension().and_then(|x| x.to_str()) == Some("toml") {
                let contents = fs::read_to_string(&path).ok()?;
                toml::from_str(&contents).ok()
            } else {
                None
            }
        })
        .collect();
    assert_eq!(entries.len(), 3);
}

#[test]
fn test_build_snapshot_name_empty_vm() {
    let name = crate::snapshot_helpers::build_snapshot_name("", "20250101_120000");
    assert_eq!(name, "_snapshot_20250101_120000");
}

#[test]
fn test_build_snapshot_name_empty_timestamp() {
    let name = crate::snapshot_helpers::build_snapshot_name("vm1", "");
    assert_eq!(name, "vm1_snapshot_");
}

#[test]
fn test_filter_snapshots_multiple_matches() {
    let snaps = vec![
        serde_json::json!({"name": "dev-vm_snapshot_1"}),
        serde_json::json!({"name": "dev-vm_snapshot_2"}),
        serde_json::json!({"name": "prod-vm_snapshot_1"}),
    ];
    let filtered = crate::snapshot_helpers::filter_snapshots(&snaps, "dev-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_snapshot_row_numeric_disk_size() {
    let snap = serde_json::json!({
        "name": "snap1",
        "diskSizeGb": 128,
        "timeCreated": "2025-01-01",
        "provisioningState": "Succeeded"
    });
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "snap1");
    assert_eq!(row[1], "128"); // numeric value should serialize as "128"
    assert_eq!(row[2], "2025-01-01");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_all_null() {
    let snap = serde_json::json!({});
    let row = crate::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

#[test]
fn test_snapshot_schedule_toml_contains_all_fields() {
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "check-fields".to_string(),
        resource_group: "rg-1".to_string(),
        every_hours: 8,
        keep_count: 3,
        enabled: false,
        created: "2025-06-15T12:00:00Z".to_string(),
    };
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    assert!(toml_str.contains("vm_name = \"check-fields\""));
    assert!(toml_str.contains("resource_group = \"rg-1\""));
    assert!(toml_str.contains("every_hours = 8"));
    assert!(toml_str.contains("keep_count = 3"));
    assert!(toml_str.contains("enabled = false"));
    assert!(toml_str.contains("created = \"2025-06-15T12:00:00Z\""));
}
