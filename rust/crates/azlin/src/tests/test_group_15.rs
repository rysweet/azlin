use crate::*;
use std::fs;
use tempfile::TempDir;

#[test]
fn test_parse_cost_action_rows_not_array() {
    let data = serde_json::json!({"not": "array"});
    let rows = crate::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_templates_build_toml_defaults() {
    let tpl = crate::templates::build_template_toml("test", None, None, None, None);
    let tbl = tpl.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "test");
    assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
    assert_eq!(tbl["region"].as_str().unwrap(), "westus2");
    assert_eq!(tbl["description"].as_str().unwrap(), "");
    assert!(tbl.get("cloud_init").is_none());
}

#[test]
fn test_templates_build_toml_custom() {
    let tpl = crate::templates::build_template_toml(
        "myvm",
        Some("A dev VM"),
        Some("Standard_D8s_v3"),
        Some("eastus"),
        Some("/path/to/init.sh"),
    );
    let tbl = tpl.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "myvm");
    assert_eq!(tbl["description"].as_str().unwrap(), "A dev VM");
    assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D8s_v3");
    assert_eq!(tbl["region"].as_str().unwrap(), "eastus");
    assert_eq!(tbl["cloud_init"].as_str().unwrap(), "/path/to/init.sh");
}

#[test]
fn test_templates_save_and_load() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path().join("templates");
    let tpl = crate::templates::build_template_toml("test-tpl", Some("desc"), None, None, None);
    let path = crate::templates::save_template(&dir, "test-tpl", &tpl).unwrap();
    assert!(path.exists());

    let loaded = crate::templates::load_template(&dir, "test-tpl").unwrap();
    assert_eq!(loaded.get("name").unwrap().as_str().unwrap(), "test-tpl");
    assert_eq!(loaded.get("description").unwrap().as_str().unwrap(), "desc");
}

#[test]
fn test_templates_load_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let result = crate::templates::load_template(tmp.path(), "nope");
    assert!(result.is_err());
}

#[test]
fn test_templates_list_empty() {
    let tmp = TempDir::new().unwrap();
    let rows = crate::templates::list_templates(tmp.path()).unwrap();
    assert!(rows.is_empty());
}

#[test]
fn test_templates_list_with_entries() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let tpl1 = crate::templates::build_template_toml("a", None, Some("small"), Some("west"), None);
    let tpl2 = crate::templates::build_template_toml("b", None, Some("large"), Some("east"), None);
    crate::templates::save_template(dir, "a", &tpl1).unwrap();
    crate::templates::save_template(dir, "b", &tpl2).unwrap();

    let rows = crate::templates::list_templates(dir).unwrap();
    assert_eq!(rows.len(), 2);
}

#[test]
fn test_templates_delete() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let tpl = crate::templates::build_template_toml("del-me", None, None, None, None);
    crate::templates::save_template(dir, "del-me", &tpl).unwrap();
    assert!(dir.join("del-me.toml").exists());

    crate::templates::delete_template(dir, "del-me").unwrap();
    assert!(!dir.join("del-me.toml").exists());
}

#[test]
fn test_templates_delete_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let result = crate::templates::delete_template(tmp.path(), "nope");
    assert!(result.is_err());
}

#[test]
fn test_templates_import() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let content = "name = \"imported\"\nvm_size = \"Standard_D2s_v3\"\nregion = \"westus\"\n";
    let name = crate::templates::import_template(dir, content).unwrap();
    assert_eq!(name, "imported");
    assert!(dir.join("imported.toml").exists());
}

#[test]
fn test_templates_import_missing_name() {
    let tmp = TempDir::new().unwrap();
    let content = "vm_size = \"Standard_D2s_v3\"\nregion = \"westus\"\n";
    let result = crate::templates::import_template(tmp.path(), content);
    assert!(result.is_err());
}

#[test]
fn test_sessions_build_toml() {
    let val =
        crate::sessions::build_session_toml("s1", "rg1", &["vm1".to_string(), "vm2".to_string()]);
    let tbl = val.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "s1");
    assert_eq!(tbl["resource_group"].as_str().unwrap(), "rg1");
    let vms = tbl["vms"].as_array().unwrap();
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].as_str().unwrap(), "vm1");
    assert!(tbl.contains_key("created"));
}

#[test]
fn test_sessions_parse_toml() {
    let content = "name = \"test-sess\"\nresource_group = \"my-rg\"\nvms = [\"vm-a\", \"vm-b\"]\ncreated = \"2024-01-01T00:00:00Z\"\n";
    let (rg, vms, created) = crate::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "my-rg");
    assert_eq!(vms, vec!["vm-a", "vm-b"]);
    assert_eq!(created, "2024-01-01T00:00:00Z");
}

#[test]
fn test_sessions_parse_toml_empty_vms() {
    let content =
        "name = \"empty\"\nresource_group = \"rg\"\nvms = []\ncreated = \"2024-01-01T00:00:00Z\"\n";
    let (rg, vms, _) = crate::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "rg");
    assert!(vms.is_empty());
}

#[test]
fn test_sessions_parse_toml_missing_fields() {
    let content = "name = \"minimal\"\n";
    let (rg, vms, created) = crate::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "-");
    assert!(vms.is_empty());
    assert_eq!(created, "-");
}

#[test]
fn test_sessions_list_names_empty() {
    let tmp = TempDir::new().unwrap();
    let names = crate::sessions::list_session_names(tmp.path()).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_sessions_list_names_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let names = crate::sessions::list_session_names(&tmp.path().join("nope")).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_sessions_list_names_with_entries() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::write(dir.join("s1.toml"), "name = \"s1\"").unwrap();
    fs::write(dir.join("s2.toml"), "name = \"s2\"").unwrap();
    fs::write(dir.join("not-toml.txt"), "ignore").unwrap();

    let names = crate::sessions::list_session_names(dir).unwrap();
    assert_eq!(names.len(), 2);
    assert!(names.contains(&"s1".to_string()));
    assert!(names.contains(&"s2".to_string()));
}

#[test]
fn test_contexts_build_toml_minimal() {
    let result = crate::contexts::build_context_toml("ctx1", None, None, None, None, None).unwrap();
    assert!(result.contains("name = \"ctx1\""));
}

#[test]
fn test_contexts_build_toml_full() {
    let result = crate::contexts::build_context_toml(
        "prod",
        Some("sub-123"),
        Some("tenant-456"),
        Some("rg-prod"),
        Some("westus2"),
        Some("my-vault"),
    )
    .unwrap();
    assert!(result.contains("name = \"prod\""));
    assert!(result.contains("subscription_id = \"sub-123\""));
    assert!(result.contains("tenant_id = \"tenant-456\""));
    assert!(result.contains("resource_group = \"rg-prod\""));
    assert!(result.contains("region = \"westus2\""));
    assert!(result.contains("key_vault_name = \"my-vault\""));
}

#[test]
fn test_contexts_list_empty() {
    let tmp = TempDir::new().unwrap();
    let result = crate::contexts::list_contexts(tmp.path(), "").unwrap();
    assert!(result.is_empty());
}

#[test]
fn test_contexts_list_with_active() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::write(dir.join("dev.toml"), "name = \"dev\"").unwrap();
    fs::write(dir.join("prod.toml"), "name = \"prod\"").unwrap();

    let result = crate::contexts::list_contexts(dir, "dev").unwrap();
    assert_eq!(result.len(), 2);
    let dev = result.iter().find(|(n, _)| n == "dev").unwrap();
    assert!(dev.1);
    let prod = result.iter().find(|(n, _)| n == "prod").unwrap();
    assert!(!prod.1);
}

#[test]
fn test_contexts_list_no_active() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::write(dir.join("ctx.toml"), "name = \"ctx\"").unwrap();

    let result = crate::contexts::list_contexts(dir, "nonexistent").unwrap();
    assert_eq!(result.len(), 1);
    assert!(!result[0].1);
}

#[test]
fn test_contexts_rename_file() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let toml_content =
        crate::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
    fs::write(dir.join("old.toml"), &toml_content).unwrap();

    crate::contexts::rename_context_file(dir, "old", "new").unwrap();
    assert!(!dir.join("old.toml").exists());
    assert!(dir.join("new.toml").exists());

    let content = fs::read_to_string(dir.join("new.toml")).unwrap();
    assert!(content.contains("name = \"new\""));
}

#[test]
fn test_contexts_rename_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let result = crate::contexts::rename_context_file(tmp.path(), "nope", "also-nope");
    assert!(result.is_err());
}
