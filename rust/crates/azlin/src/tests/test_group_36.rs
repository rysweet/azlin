use std::fs;
use tempfile::TempDir;

// ── command_helpers tests ───────────────────────────────────────

#[test]
fn test_is_allowed_command_az() {
    assert!(crate::command_helpers::is_allowed_command("az vm list"));
}

#[test]
fn test_is_allowed_command_non_az() {
    assert!(!crate::command_helpers::is_allowed_command("rm -rf /"));
}

#[test]
fn test_is_allowed_command_whitespace_prefix() {
    assert!(crate::command_helpers::is_allowed_command("  az vm list"));
}

#[test]
fn test_skip_reason_allowed() {
    assert_eq!(crate::command_helpers::skip_reason("az vm list"), None);
}

#[test]
fn test_skip_reason_empty() {
    assert!(crate::command_helpers::skip_reason("").is_some());
}

#[test]
fn test_skip_reason_non_az() {
    let reason = crate::command_helpers::skip_reason("curl http://evil.com");
    assert!(reason.is_some());
    assert!(reason.unwrap().contains("non-Azure"));
}

// ── autopilot_parse_helpers tests ───────────────────────────────

#[test]
fn test_parse_idle_check_normal() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("25.3\n3600.5");
    assert!((cpu - 25.3).abs() < 0.01);
    assert!((uptime - 3600.5).abs() < 0.01);
}

#[test]
fn test_parse_idle_check_empty() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("");
    assert!((cpu - 100.0).abs() < 0.01); // defaults to 100% (not idle)
    assert!((uptime - 0.0).abs() < 0.01);
}

#[test]
fn test_parse_idle_check_garbage() {
    let (cpu, uptime) = crate::autopilot_parse_helpers::parse_idle_check("abc\nxyz");
    assert!((cpu - 100.0).abs() < 0.01);
    assert!((uptime - 0.0).abs() < 0.01);
}

#[test]
fn test_is_idle_true() {
    // CPU 2%, uptime 2 hours, threshold 30 min → idle
    assert!(crate::autopilot_parse_helpers::is_idle(2.0, 7200.0, 30));
}

#[test]
fn test_is_idle_high_cpu() {
    // CPU 50%, even with long uptime → not idle
    assert!(!crate::autopilot_parse_helpers::is_idle(50.0, 7200.0, 30));
}

#[test]
fn test_is_idle_short_uptime() {
    // CPU 1%, uptime 10 min, threshold 30 min → not idle (too new)
    assert!(!crate::autopilot_parse_helpers::is_idle(1.0, 600.0, 30));
}

// ── templates::import_template tests ────────────────────────────

#[test]
fn test_import_template_success() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let content = r#"
name = "web-server"
vm_size = "Standard_B2s"
region = "eastus"
"#;
    let name = crate::templates::import_template(dir, content).unwrap();
    assert_eq!(name, "web-server");
    // Verify the file was created
    assert!(dir.join("web-server.toml").exists());
}

#[test]
fn test_import_template_missing_name() {
    let tmp = TempDir::new().unwrap();
    let content = r#"
vm_size = "Standard_B2s"
region = "eastus"
"#;
    let result = crate::templates::import_template(tmp.path(), content);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("name"));
}

#[test]
fn test_import_template_invalid_toml() {
    let tmp = TempDir::new().unwrap();
    let result = crate::templates::import_template(tmp.path(), "not valid { toml [");
    assert!(result.is_err());
}

// ── templates::build_template_toml edge cases ──────────────────

#[test]
fn test_build_template_toml_with_cloud_init() {
    let tpl = crate::templates::build_template_toml(
        "my-tpl",
        Some("A dev VM"),
        Some("Standard_E4s_v3"),
        Some("northeurope"),
        Some("#!/bin/bash\napt-get update"),
    );
    let tbl = tpl.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "my-tpl");
    assert_eq!(tbl["description"].as_str().unwrap(), "A dev VM");
    assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_E4s_v3");
    assert_eq!(tbl["region"].as_str().unwrap(), "northeurope");
    assert!(tbl["cloud_init"].as_str().unwrap().contains("apt-get"));
}

#[test]
fn test_build_template_toml_all_defaults() {
    let tpl = crate::templates::build_template_toml("minimal", None, None, None, None);
    let tbl = tpl.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "minimal");
    assert_eq!(tbl["description"].as_str().unwrap(), "");
    assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
    assert_eq!(tbl["region"].as_str().unwrap(), "westus2");
    assert!(tbl.get("cloud_init").is_none());
}

// ── vm_validation tests ────────────────────────────────────────

#[test]
fn test_validate_vm_name_empty() {
    let result = crate::vm_validation::validate_vm_name("");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("empty"));
}

#[test]
fn test_validate_vm_name_leading_hyphen() {
    let result = crate::vm_validation::validate_vm_name("-bad-name");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("start with a hyphen"));
}

#[test]
fn test_validate_vm_name_trailing_hyphen() {
    let result = crate::vm_validation::validate_vm_name("bad-name-");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("end with a hyphen"));
}

#[test]
fn test_validate_vm_name_valid() {
    assert!(crate::vm_validation::validate_vm_name("my-good-vm-01").is_ok());
}

#[test]
fn test_validate_vm_name_single_char() {
    assert!(crate::vm_validation::validate_vm_name("a").is_ok());
}

#[test]
fn test_validate_vm_name_spaces_rejected() {
    let result = crate::vm_validation::validate_vm_name("bad name");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("invalid characters"));
}

// ── snapshot_helpers::SnapshotSchedule serde tests ──────────────

#[test]
fn test_snapshot_schedule_serialize_deserialize_roundtrip() {
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "dev-vm".to_string(),
        resource_group: "my-rg".to_string(),
        every_hours: 6,
        keep_count: 10,
        enabled: true,
        created: "2024-01-15T10:00:00Z".to_string(),
    };
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    let loaded: crate::snapshot_helpers::SnapshotSchedule = toml::from_str(&toml_str).unwrap();
    assert_eq!(loaded.vm_name, "dev-vm");
    assert_eq!(loaded.resource_group, "my-rg");
    assert_eq!(loaded.every_hours, 6);
    assert_eq!(loaded.keep_count, 10);
    assert!(loaded.enabled);
    assert_eq!(loaded.created, "2024-01-15T10:00:00Z");
}

#[test]
fn test_snapshot_schedule_disabled() {
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "prod-db".to_string(),
        resource_group: "prod-rg".to_string(),
        every_hours: 24,
        keep_count: 3,
        enabled: false,
        created: "2024-06-01T00:00:00Z".to_string(),
    };
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    assert!(toml_str.contains("enabled = false"));
    let loaded: crate::snapshot_helpers::SnapshotSchedule = toml::from_str(&toml_str).unwrap();
    assert!(!loaded.enabled);
}

#[test]
fn test_snapshot_schedule_write_read_file() {
    let tmp = TempDir::new().unwrap();
    let schedule = crate::snapshot_helpers::SnapshotSchedule {
        vm_name: "test-vm".to_string(),
        resource_group: "test-rg".to_string(),
        every_hours: 12,
        keep_count: 5,
        enabled: true,
        created: "2024-03-01T08:00:00Z".to_string(),
    };
    let path = tmp.path().join("test-vm.toml");
    let contents = toml::to_string_pretty(&schedule).unwrap();
    fs::write(&path, &contents).unwrap();

    let read_back = fs::read_to_string(&path).unwrap();
    let loaded: crate::snapshot_helpers::SnapshotSchedule = toml::from_str(&read_back).unwrap();
    assert_eq!(loaded.vm_name, "test-vm");
    assert_eq!(loaded.every_hours, 12);
}

// ── sessions round-trip with list_session_names ─────────────────

#[test]
fn test_session_build_write_list_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::create_dir_all(dir).unwrap();

    let session1 = crate::sessions::build_session_toml(
        "dev-session",
        "dev-rg",
        &["vm-1".to_string(), "vm-2".to_string()],
    );
    let session2 =
        crate::sessions::build_session_toml("staging-session", "staging-rg", &["vm-3".to_string()]);

    fs::write(
        dir.join("dev-session.toml"),
        toml::to_string_pretty(&session1).unwrap(),
    )
    .unwrap();
    fs::write(
        dir.join("staging-session.toml"),
        toml::to_string_pretty(&session2).unwrap(),
    )
    .unwrap();
    // Add a non-toml file that should be ignored
    fs::write(dir.join("notes.txt"), "some notes").unwrap();

    let names = crate::sessions::list_session_names(dir).unwrap();
    assert_eq!(names.len(), 2);
    assert!(names.contains(&"dev-session".to_string()));
    assert!(names.contains(&"staging-session".to_string()));
}

#[test]
fn test_session_parse_toml_missing_all_fields() {
    // Empty table should return defaults
    let content = "[other]\nkey = \"value\"";
    let (rg, vms, created) = crate::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "-");
    assert!(vms.is_empty());
    assert_eq!(created, "-");
}
