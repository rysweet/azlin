use std::fs;
use tempfile::TempDir;

// ── NEW: templates edge-case tests ───────────────────────────

#[test]
fn test_template_build_all_none_defaults() {
    let tpl = crate::templates::build_template_toml("t1", None, None, None, None);
    let t = tpl.as_table().unwrap();
    assert_eq!(t["name"].as_str().unwrap(), "t1");
    assert_eq!(t["description"].as_str().unwrap(), "");
    assert_eq!(t["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
    assert_eq!(t["region"].as_str().unwrap(), "westus2");
    assert!(t.get("cloud_init").is_none());
}

#[test]
fn test_template_build_all_some() {
    let tpl = crate::templates::build_template_toml(
        "big",
        Some("GPU template"),
        Some("Standard_NC6"),
        Some("eastus"),
        Some("#!/bin/bash\necho hi"),
    );
    let t = tpl.as_table().unwrap();
    assert_eq!(t["name"].as_str().unwrap(), "big");
    assert_eq!(t["description"].as_str().unwrap(), "GPU template");
    assert_eq!(t["vm_size"].as_str().unwrap(), "Standard_NC6");
    assert_eq!(t["region"].as_str().unwrap(), "eastus");
    assert_eq!(t["cloud_init"].as_str().unwrap(), "#!/bin/bash\necho hi");
}

#[test]
fn test_template_save_creates_directory() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path().join("nested").join("templates");
    let tpl = crate::templates::build_template_toml("x", None, None, None, None);
    let path = crate::templates::save_template(&dir, "x", &tpl).unwrap();
    assert!(path.exists());
    assert!(path.to_string_lossy().ends_with("x.toml"));
}

#[test]
fn test_template_load_not_found() {
    let tmp = TempDir::new().unwrap();
    let err = crate::templates::load_template(tmp.path(), "nope").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_template_save_load_roundtrip_with_cloud_init() {
    let tmp = TempDir::new().unwrap();
    let tpl = crate::templates::build_template_toml(
        "ci",
        Some("cloud-init test"),
        Some("Standard_B2s"),
        Some("westus3"),
        Some("#!/bin/bash\napt update"),
    );
    crate::templates::save_template(tmp.path(), "ci", &tpl).unwrap();
    let loaded = crate::templates::load_template(tmp.path(), "ci").unwrap();
    assert_eq!(loaded["name"].as_str().unwrap(), "ci");
    assert_eq!(
        loaded["cloud_init"].as_str().unwrap(),
        "#!/bin/bash\napt update"
    );
}

#[test]
fn test_template_list_multiple_sorted_fields() {
    let tmp = TempDir::new().unwrap();
    for (n, sz, rg) in &[
        ("a", "Standard_A1", "westus"),
        ("b", "Standard_B2", "eastus"),
    ] {
        let tpl = crate::templates::build_template_toml(n, None, Some(sz), Some(rg), None);
        crate::templates::save_template(tmp.path(), n, &tpl).unwrap();
    }
    let rows = crate::templates::list_templates(tmp.path()).unwrap();
    assert_eq!(rows.len(), 2);
    let names: Vec<&str> = rows.iter().map(|r| r[0].as_str()).collect();
    assert!(names.contains(&"a"));
    assert!(names.contains(&"b"));
}

#[test]
fn test_template_list_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let rows = crate::templates::list_templates(&tmp.path().join("nope")).unwrap();
    assert!(rows.is_empty());
}

#[test]
fn test_template_list_ignores_non_toml_files() {
    let tmp = TempDir::new().unwrap();
    fs::write(tmp.path().join("readme.md"), "not a template").unwrap();
    fs::write(tmp.path().join("data.json"), "{}").unwrap();
    let tpl = crate::templates::build_template_toml("only", None, None, None, None);
    crate::templates::save_template(tmp.path(), "only", &tpl).unwrap();
    let rows = crate::templates::list_templates(tmp.path()).unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0][0], "only");
}

#[test]
fn test_template_delete_not_found() {
    let tmp = TempDir::new().unwrap();
    let err = crate::templates::delete_template(tmp.path(), "ghost").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_template_delete_removes_file() {
    let tmp = TempDir::new().unwrap();
    let tpl = crate::templates::build_template_toml("del", None, None, None, None);
    crate::templates::save_template(tmp.path(), "del", &tpl).unwrap();
    assert!(tmp.path().join("del.toml").exists());
    crate::templates::delete_template(tmp.path(), "del").unwrap();
    assert!(!tmp.path().join("del.toml").exists());
}

#[test]
fn test_template_import_valid() {
    let tmp = TempDir::new().unwrap();
    let content = "name = \"imported\"\nvm_size = \"Standard_D2s_v3\"\nregion = \"westus2\"\n";
    let name = crate::templates::import_template(tmp.path(), content).unwrap();
    assert_eq!(name, "imported");
    assert!(tmp.path().join("imported.toml").exists());
}

#[test]
fn test_template_import_missing_name() {
    let tmp = TempDir::new().unwrap();
    let content = "vm_size = \"Standard_D2s_v3\"\n";
    let err = crate::templates::import_template(tmp.path(), content).unwrap_err();
    assert!(err.to_string().contains("name"));
}

#[test]
fn test_template_import_invalid_toml() {
    let tmp = TempDir::new().unwrap();
    let err = crate::templates::import_template(tmp.path(), "{{invalid").unwrap_err();
    assert!(!err.to_string().is_empty());
}

// ── NEW: sessions edge-case tests ────────────────────────────

#[test]
fn test_session_build_toml_fields() {
    let s = crate::sessions::build_session_toml("dev", "rg-dev", &["vm1".into(), "vm2".into()]);
    let t = s.as_table().unwrap();
    assert_eq!(t["name"].as_str().unwrap(), "dev");
    assert_eq!(t["resource_group"].as_str().unwrap(), "rg-dev");
    let vms = t["vms"].as_array().unwrap();
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].as_str().unwrap(), "vm1");
    assert!(t["created"].as_str().unwrap().contains('T'));
}

#[test]
fn test_session_build_toml_empty_vms() {
    let s = crate::sessions::build_session_toml("empty", "rg", &[]);
    let t = s.as_table().unwrap();
    assert!(t["vms"].as_array().unwrap().is_empty());
}

#[test]
fn test_session_parse_toml_valid() {
    let content = "name = \"s1\"\nresource_group = \"rg-test\"\nvms = [\"vm-a\", \"vm-b\"]\ncreated = \"2025-01-01T00:00:00Z\"\n";
    let (rg, vms, created) = crate::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "rg-test");
    assert_eq!(vms, vec!["vm-a", "vm-b"]);
    assert_eq!(created, "2025-01-01T00:00:00Z");
}

#[test]
fn test_session_parse_toml_missing_fields() {
    let content = "name = \"minimal\"\n";
    let (rg, vms, created) = crate::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "-");
    assert!(vms.is_empty());
    assert_eq!(created, "-");
}

#[test]
fn test_session_parse_toml_invalid() {
    let err = crate::sessions::parse_session_toml("{{bad").unwrap_err();
    assert!(!err.to_string().is_empty());
}

#[test]
fn test_session_list_names_empty_dir() {
    let tmp = TempDir::new().unwrap();
    let names = crate::sessions::list_session_names(tmp.path()).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_session_list_names_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let names = crate::sessions::list_session_names(&tmp.path().join("nope")).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_session_list_names_filters_toml() {
    let tmp = TempDir::new().unwrap();
    fs::write(tmp.path().join("s1.toml"), "name=\"s1\"\n").unwrap();
    fs::write(tmp.path().join("s2.toml"), "name=\"s2\"\n").unwrap();
    fs::write(tmp.path().join("readme.md"), "ignore").unwrap();
    let names = crate::sessions::list_session_names(tmp.path()).unwrap();
    assert_eq!(names.len(), 2);
    assert!(names.contains(&"s1".to_string()));
    assert!(names.contains(&"s2".to_string()));
}

#[test]
fn test_session_build_and_parse_roundtrip() {
    let built = crate::sessions::build_session_toml("rt", "rg-rt", &["vm-x".into()]);
    let serialized = toml::to_string_pretty(&built).unwrap();
    let (rg, vms, created) = crate::sessions::parse_session_toml(&serialized).unwrap();
    assert_eq!(rg, "rg-rt");
    assert_eq!(vms, vec!["vm-x"]);
    assert!(!created.is_empty());
    assert_ne!(created, "-");
}
