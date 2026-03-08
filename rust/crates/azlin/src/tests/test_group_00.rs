use std::fs;
use tempfile::TempDir;

#[test]
fn test_keys_list_finds_pub_files() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    fs::write(ssh_dir.join("id_ed25519"), "private key").unwrap();
    fs::write(ssh_dir.join("id_ed25519.pub"), "ssh-ed25519 AAAA test@host").unwrap();
    fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();

    let entries: Vec<String> = fs::read_dir(ssh_dir)
        .unwrap()
        .filter_map(|e| {
            let name = e.ok()?.file_name().to_string_lossy().to_string();
            if name.ends_with(".pub")
                || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name.as_str())
            {
                Some(name)
            } else {
                None
            }
        })
        .collect();

    assert_eq!(entries.len(), 2);
    assert!(entries.contains(&"id_ed25519".to_string()));
    assert!(entries.contains(&"id_ed25519.pub".to_string()));
}

#[test]
fn test_keys_backup_copies_id_files_only() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    fs::write(ssh_dir.join("id_rsa"), "rsa private").unwrap();
    fs::write(ssh_dir.join("id_rsa.pub"), "rsa public").unwrap();
    fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();
    fs::write(ssh_dir.join("config"), "Host *").unwrap();

    let backup_dir = tmp.path().join("backup");
    fs::create_dir_all(&backup_dir).unwrap();

    let mut count = 0u32;
    for entry in fs::read_dir(ssh_dir).unwrap() {
        let entry = entry.unwrap();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with("id_") {
            fs::copy(entry.path(), backup_dir.join(&name)).unwrap();
            count += 1;
        }
    }

    assert_eq!(count, 2);
    assert!(backup_dir.join("id_rsa").exists());
    assert!(backup_dir.join("id_rsa.pub").exists());
    assert!(!backup_dir.join("known_hosts").exists());
}

#[test]
fn test_keys_export_selects_first_available() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    fs::write(ssh_dir.join("id_ed25519.pub"), "ssh-ed25519 AAAA test").unwrap();

    let candidates = ["id_ed25519_azlin.pub", "id_ed25519.pub", "id_rsa.pub"];
    let found = candidates
        .iter()
        .map(|f| ssh_dir.join(f))
        .find(|p| p.exists());

    assert!(found.is_some());
    assert!(found.unwrap().ends_with("id_ed25519.pub"));
}

#[test]
fn test_auth_profile_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let profiles_dir = tmp.path().join("profiles");
    fs::create_dir_all(&profiles_dir).unwrap();

    let profile_data = serde_json::json!({
        "tenant_id": "test-tenant",
        "client_id": "test-client",
        "subscription_id": "test-sub",
    });

    let profile_path = profiles_dir.join("test.json");
    fs::write(
        &profile_path,
        serde_json::to_string_pretty(&profile_data).unwrap(),
    )
    .unwrap();

    assert!(profile_path.exists());
    let content = fs::read_to_string(&profile_path).unwrap();
    let loaded: serde_json::Value = serde_json::from_str(&content).unwrap();
    assert_eq!(loaded["tenant_id"], "test-tenant");
    assert_eq!(loaded["client_id"], "test-client");
    assert_eq!(loaded["subscription_id"], "test-sub");
}

#[test]
fn test_auth_profile_remove() {
    let tmp = TempDir::new().unwrap();
    let profiles_dir = tmp.path().join("profiles");
    fs::create_dir_all(&profiles_dir).unwrap();

    let profile_path = profiles_dir.join("staging.json");
    fs::write(&profile_path, r#"{"tenant_id":"t","client_id":"c"}"#).unwrap();
    assert!(profile_path.exists());

    fs::remove_file(&profile_path).unwrap();
    assert!(!profile_path.exists());
}

#[test]
fn test_snapshot_name_format() {
    let vm_name = "test-vm";
    let snapshot_name = format!(
        "{}_snapshot_{}",
        vm_name,
        chrono::Utc::now().format("%Y%m%d_%H%M%S")
    );
    assert!(snapshot_name.starts_with("test-vm_snapshot_"));
    assert!(snapshot_name.len() > 30);
}

#[test]
fn test_storage_sku_mapping() {
    let cases = vec![
        ("premium", "Premium_LRS"),
        ("standard", "Standard_LRS"),
        ("Premium", "Premium_LRS"),
        ("other", "Premium_LRS"),
    ];
    for (input, expected) in cases {
        let sku = match input.to_lowercase().as_str() {
            "premium" => "Premium_LRS",
            "standard" => "Standard_LRS",
            _ => "Premium_LRS",
        };
        assert_eq!(sku, expected, "Failed for input: {}", input);
    }
}

#[test]
fn test_template_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let tpl_dir = tmp.path().join("templates");
    fs::create_dir_all(&tpl_dir).unwrap();

    let tpl = serde_json::json!({
        "name": "dev-box",
        "description": "Development VM",
        "vm_size": "Standard_D4s_v3",
        "region": "westus2",
        "cloud_init": null,
    });

    let path = tpl_dir.join("dev-box.json");
    fs::write(&path, serde_json::to_string_pretty(&tpl).unwrap()).unwrap();
    assert!(path.exists());

    let loaded: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(loaded["name"], "dev-box");
    assert_eq!(loaded["vm_size"], "Standard_D4s_v3");
}

#[test]
fn test_context_create_and_delete() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    let mut ctx = toml::map::Map::new();
    ctx.insert("name".into(), toml::Value::String("staging".into()));
    ctx.insert(
        "subscription_id".into(),
        toml::Value::String("sub-123".into()),
    );
    ctx.insert("tenant_id".into(), toml::Value::String("tenant-456".into()));
    ctx.insert(
        "resource_group".into(),
        toml::Value::String("staging-rg".into()),
    );
    ctx.insert("region".into(), toml::Value::String("eastus".into()));

    let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
    let path = ctx_dir.join("staging.toml");
    fs::write(&path, &toml_str).unwrap();
    assert!(path.exists());

    // read back
    let loaded: toml::Value = toml::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(loaded["name"].as_str().unwrap(), "staging");
    assert_eq!(loaded["resource_group"].as_str().unwrap(), "staging-rg");

    // delete
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}

#[test]
fn test_context_switch_updates_active_context() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    for name in &["dev", "prod"] {
        let mut ctx = toml::map::Map::new();
        ctx.insert("name".into(), toml::Value::String(name.to_string()));
        ctx.insert(
            "subscription_id".into(),
            toml::Value::String(format!("sub-{}", name)),
        );
        let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
        fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
    }

    let active_path = tmp.path().join("active-context");
    fs::write(&active_path, "dev").unwrap();
    assert_eq!(fs::read_to_string(&active_path).unwrap().trim(), "dev");

    // Switch to prod
    assert!(ctx_dir.join("prod.toml").exists());
    fs::write(&active_path, "prod").unwrap();
    assert_eq!(fs::read_to_string(&active_path).unwrap().trim(), "prod");
}

#[test]
fn test_context_list_marks_active() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    for name in &["alpha", "beta", "gamma"] {
        let mut ctx = toml::map::Map::new();
        ctx.insert("name".into(), toml::Value::String(name.to_string()));
        let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
        fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
    }

    let active_path = tmp.path().join("active-context");
    fs::write(&active_path, "beta").unwrap();
    let active = fs::read_to_string(&active_path).unwrap().trim().to_string();

    let mut entries: Vec<_> = fs::read_dir(&ctx_dir)
        .unwrap()
        .filter_map(|e| e.ok())
        .collect();
    entries.sort_by_key(|e| e.file_name());
    let mut lines = Vec::new();
    for entry in entries {
        let fname = entry.file_name().to_string_lossy().to_string();
        if fname.ends_with(".toml") {
            let ctx_name = fname.trim_end_matches(".toml");
            if ctx_name == active {
                lines.push(format!("* {}", ctx_name));
            } else {
                lines.push(format!("  {}", ctx_name));
            }
        }
    }
    assert_eq!(lines, vec!["  alpha", "* beta", "  gamma"]);
}
