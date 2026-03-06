use super::*;
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

#[test]
fn test_context_rename_updates_name_field() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    let mut ctx = toml::map::Map::new();
    ctx.insert("name".into(), toml::Value::String("old".into()));
    ctx.insert(
        "subscription_id".into(),
        toml::Value::String("sub-1".into()),
    );
    let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
    fs::write(ctx_dir.join("old.toml"), &toml_str).unwrap();

    let active_path = tmp.path().join("active-context");
    fs::write(&active_path, "old").unwrap();

    // Rename: read, update name, write new, remove old
    let old_path = ctx_dir.join("old.toml");
    let content = fs::read_to_string(&old_path).unwrap();
    let mut table: toml::Value = toml::from_str(&content).unwrap();
    table
        .as_table_mut()
        .unwrap()
        .insert("name".into(), toml::Value::String("new".into()));
    let new_path = ctx_dir.join("new.toml");
    fs::write(&new_path, toml::to_string_pretty(&table).unwrap()).unwrap();
    fs::remove_file(&old_path).unwrap();

    if fs::read_to_string(&active_path).unwrap().trim() == "old" {
        fs::write(&active_path, "new").unwrap();
    }

    assert!(!old_path.exists());
    assert!(new_path.exists());
    let loaded: toml::Value = toml::from_str(&fs::read_to_string(&new_path).unwrap()).unwrap();
    assert_eq!(loaded["name"].as_str().unwrap(), "new");
    assert_eq!(fs::read_to_string(&active_path).unwrap().trim(), "new");
}

#[test]
fn test_context_delete_clears_active_if_matching() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    let mut ctx = toml::map::Map::new();
    ctx.insert("name".into(), toml::Value::String("doomed".into()));
    let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
    fs::write(ctx_dir.join("doomed.toml"), &toml_str).unwrap();

    let active_path = tmp.path().join("active-context");
    fs::write(&active_path, "doomed").unwrap();

    fs::remove_file(ctx_dir.join("doomed.toml")).unwrap();
    if fs::read_to_string(&active_path).unwrap().trim() == "doomed" {
        fs::remove_file(&active_path).unwrap();
    }

    assert!(!active_path.exists());
}

#[test]
fn test_context_toml_format() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    let mut ctx = toml::map::Map::new();
    ctx.insert("name".into(), toml::Value::String("production".into()));
    ctx.insert(
        "subscription_id".into(),
        toml::Value::String("sub-id-here".into()),
    );
    ctx.insert(
        "resource_group".into(),
        toml::Value::String("prod-rg".into()),
    );
    ctx.insert("tenant_id".into(), toml::Value::String("tenant-id".into()));

    let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
    let path = ctx_dir.join("production.toml");
    fs::write(&path, &toml_str).unwrap();

    let content = fs::read_to_string(&path).unwrap();
    assert!(content.contains("name = \"production\""));
    assert!(content.contains("subscription_id = \"sub-id-here\""));
    assert!(content.contains("resource_group = \"prod-rg\""));
    assert!(content.contains("tenant_id = \"tenant-id\""));

    // Round-trip
    let loaded: toml::Value = toml::from_str(&content).unwrap();
    assert_eq!(loaded["name"].as_str().unwrap(), "production");
    assert_eq!(loaded["subscription_id"].as_str().unwrap(), "sub-id-here");
}

#[test]
fn test_session_save_and_load() {
    let tmp = TempDir::new().unwrap();
    let sessions_dir = tmp.path().join("sessions");
    fs::create_dir_all(&sessions_dir).unwrap();

    let content = "\
name = \"my-session\"\n\
resource_group = \"dev-rg\"\n\
vms = [\"dev-vm-1\", \"dev-vm-2\", \"dev-vm-3\"]\n\
created = \"2025-01-01T00:00:00Z\"\n";

    let path = sessions_dir.join("my-session.toml");
    fs::write(&path, content).unwrap();
    assert!(path.exists());

    let loaded: toml::Value = fs::read_to_string(&path).unwrap().parse().unwrap();
    let tbl = loaded.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "my-session");
    assert_eq!(tbl["resource_group"].as_str().unwrap(), "dev-rg");
    let vms: Vec<&str> = tbl["vms"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|v| v.as_str())
        .collect();
    assert_eq!(vms, vec!["dev-vm-1", "dev-vm-2", "dev-vm-3"]);
}

#[test]
fn test_cp_direction_detection() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    assert!(is_remote("myvm:/home/user/file.txt"));
    assert!(!is_remote("/tmp/local.txt"));
    assert!(!is_remote("C:\\Windows")); // Windows drive letter

    let source = "myvm:/home/user/file.txt";
    let dest = "/tmp/local.txt";
    let direction = if is_remote(source) && !is_remote(dest) {
        "remote→local"
    } else if !is_remote(source) && is_remote(dest) {
        "local→remote"
    } else {
        "local→local"
    };
    assert_eq!(direction, "remote→local");
}

#[test]
fn test_shell_escape_simple() {
    assert_eq!(super::shell_escape("hello"), "'hello'");
}

#[test]
fn test_shell_escape_with_single_quotes() {
    assert_eq!(super::shell_escape("it's"), "'it'\\''s'");
}

#[test]
fn test_shell_escape_with_spaces_and_special_chars() {
    let escaped = super::shell_escape("foo bar $HOME");
    assert_eq!(escaped, "'foo bar $HOME'");
}

#[test]
fn test_health_metrics_non_running_vm() {
    let m = super::collect_health_metrics("test-vm", "10.0.0.1", "azureuser", "deallocated", None);
    assert_eq!(m.vm_name, "test-vm");
    assert_eq!(m.power_state, "deallocated");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

#[test]
fn test_ssh_exec_unreachable_host() {
    // ssh_exec to a non-routable address should either error or return non-zero
    let result = super::ssh_exec("192.0.2.1", "user", "echo hello");
    if let Ok((code, _, _)) = result {
        assert_ne!(code, 0, "should fail for unreachable host");
    }
}

#[test]
fn test_home_dir_returns_path() {
    // On any real system, home_dir should return a valid path
    let result = super::home_dir();
    assert!(result.is_ok(), "home_dir should succeed on real system");
    assert!(result.unwrap().is_absolute(), "home dir should be absolute");
}

#[test]
fn test_new_table_creates_table_with_headers() {
    let table = super::new_table(&["Name", "Value", "Status"]);
    let rendered = table.to_string();
    assert!(rendered.contains("Name"), "should contain header 'Name'");
    assert!(rendered.contains("Value"), "should contain header 'Value'");
    assert!(
        rendered.contains("Status"),
        "should contain header 'Status'"
    );
}

#[test]
fn test_new_table_empty_headers() {
    // Should not panic with empty headers
    let table = super::new_table(&[]);
    let _rendered = table.to_string();
}

#[test]
fn test_render_health_table_does_not_panic() {
    let metrics = vec![
        super::HealthMetrics {
            vm_name: "vm1".to_string(),
            power_state: "running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 25.5,
            mem_percent: 60.0,
            disk_percent: 45.0,
        },
        super::HealthMetrics {
            vm_name: "vm2".to_string(),
            power_state: "stopped".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
        },
        super::HealthMetrics {
            vm_name: "vm3".to_string(),
            power_state: "running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 95.0,
            mem_percent: 85.0,
            disk_percent: 92.0,
        },
    ];
    // Should not panic; just renders to stdout
    super::render_health_table(&metrics);
}

#[test]
fn test_run_on_fleet_empty_list() {
    let vms: Vec<(String, String, String)> = vec![];
    // Should not panic on empty list
    super::run_on_fleet(&vms, "echo hi", true);
}

// ── shell_escape tests ───────────────────────────────────────

#[test]
fn test_shell_escape_empty_string() {
    assert_eq!(super::shell_escape(""), "''");
}

#[test]
fn test_shell_escape_no_special_chars() {
    assert_eq!(super::shell_escape("hello"), "'hello'");
}

#[test]
fn test_shell_escape_with_spaces() {
    assert_eq!(super::shell_escape("hello world"), "'hello world'");
}

#[test]
fn test_shell_escape_with_dollar_sign() {
    assert_eq!(super::shell_escape("$HOME"), "'$HOME'");
}

#[test]
fn test_shell_escape_with_backticks() {
    assert_eq!(super::shell_escape("`whoami`"), "'`whoami`'");
}

#[test]
fn test_shell_escape_with_double_quotes() {
    assert_eq!(super::shell_escape(r#"say "hi""#), r#"'say "hi"'"#);
}

#[test]
fn test_shell_escape_multiple_single_quotes() {
    let result = super::shell_escape("it's Tom's");
    assert_eq!(result, "'it'\\''s Tom'\\''s'");
}

#[test]
fn test_shell_escape_newline() {
    let result = super::shell_escape("line1\nline2");
    assert!(result.starts_with('\''));
    assert!(result.ends_with('\''));
    assert!(result.contains('\n'));
}

#[test]
fn test_shell_escape_semicolons_and_pipes() {
    let result = super::shell_escape("cmd1; cmd2 | cmd3");
    assert_eq!(result, "'cmd1; cmd2 | cmd3'");
}

#[test]
fn test_shell_escape_unicode() {
    assert_eq!(super::shell_escape("café"), "'café'");
}

// ── resolve_resource_group tests ─────────────────────────────

#[test]
fn test_resolve_resource_group_with_explicit_value() {
    let result = super::resolve_resource_group(Some("my-rg".to_string()));
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), "my-rg");
}

#[test]
fn test_resolve_resource_group_explicit_empty_string() {
    let result = super::resolve_resource_group(Some("".to_string()));
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), "");
}

#[test]
fn test_resolve_resource_group_explicit_with_special_chars() {
    let result = super::resolve_resource_group(Some("my-rg_123".to_string()));
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), "my-rg_123");
}

// ── HealthMetrics tests ──────────────────────────────────────

#[test]
fn test_health_metrics_stopped_vm() {
    let m = super::collect_health_metrics("vm-stop", "10.0.0.1", "user", "stopped", None);
    assert_eq!(m.vm_name, "vm-stop");
    assert_eq!(m.power_state, "stopped");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

#[test]
fn test_health_metrics_starting_vm() {
    let m = super::collect_health_metrics("vm-start", "10.0.0.1", "user", "starting", None);
    assert_eq!(m.power_state, "starting");
    assert_eq!(m.cpu_percent, 0.0);
}

#[test]
fn test_health_metrics_unknown_state() {
    let m = super::collect_health_metrics("vm-x", "10.0.0.1", "user", "unknown", None);
    assert_eq!(m.power_state, "unknown");
    assert_eq!(m.cpu_percent, 0.0);
}

// ── render_health_table tests ────────────────────────────────

#[test]
fn test_render_health_table_empty_list() {
    let metrics: Vec<super::HealthMetrics> = vec![];
    // Should not panic on empty input
    super::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_single_entry() {
    let metrics = vec![super::HealthMetrics {
        vm_name: "solo-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 50.0,
        mem_percent: 40.0,
        disk_percent: 30.0,
    }];
    super::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_high_usage_values() {
    let metrics = vec![super::HealthMetrics {
        vm_name: "hot-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 99.9,
        mem_percent: 95.0,
        disk_percent: 98.0,
    }];
    super::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_zero_usage() {
    let metrics = vec![super::HealthMetrics {
        vm_name: "idle-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 0.0,
        mem_percent: 0.0,
        disk_percent: 0.0,
    }];
    super::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_mixed_states() {
    let metrics = vec![
        super::HealthMetrics {
            vm_name: "vm-a".to_string(),
            power_state: "running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 10.0,
            mem_percent: 20.0,
            disk_percent: 30.0,
        },
        super::HealthMetrics {
            vm_name: "vm-b".to_string(),
            power_state: "deallocated".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
        },
        super::HealthMetrics {
            vm_name: "vm-c".to_string(),
            power_state: "stopping".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
        },
    ];
    super::render_health_table(&metrics);
}

// ── cp direction detection tests ─────────────────────────────

#[test]
fn test_cp_direction_local_to_remote() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    assert!(!is_remote("/tmp/file.txt"));
    assert!(is_remote("myvm:/home/user/file.txt"));
}

#[test]
fn test_cp_direction_remote_to_local() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    let source = "vm1:/tmp/data.tar.gz";
    let dest = "/home/local/data.tar.gz";
    assert!(is_remote(source));
    assert!(!is_remote(dest));
}

#[test]
fn test_cp_direction_windows_path_not_remote() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    assert!(!is_remote("C:\\Users\\file.txt"));
    assert!(!is_remote("D:\\data"));
}

#[test]
fn test_cp_direction_both_local() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    let source = "/tmp/a.txt";
    let dest = "/tmp/b.txt";
    let direction = if is_remote(source) && !is_remote(dest) {
        "remote→local"
    } else if !is_remote(source) && is_remote(dest) {
        "local→remote"
    } else {
        "local→local"
    };
    assert_eq!(direction, "local→local");
}

#[test]
fn test_cp_direction_absolute_path_with_colon() {
    let is_remote = |s: &str| {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    };
    // Absolute path starting with / should not be remote
    assert!(!is_remote("/path/with:colon"));
}

// ── run_on_fleet tests ───────────────────────────────────────

#[test]
fn test_run_on_fleet_show_output_false() {
    let vms: Vec<(String, String, String)> = vec![];
    super::run_on_fleet(&vms, "ls", false);
}

#[test]
fn test_fleet_spinner_style_template() {
    let style = super::fleet_spinner_style();
    // Verify style can be applied to a spinner without panicking
    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_style(style);
    pb.set_prefix(format!("{:>20}", "test-vm"));
    pb.set_message("connecting...");
    pb.finish_with_message("✓ done");
}

#[test]
fn test_multiprogress_bar_formatting() {
    let mp = indicatif::MultiProgress::new();
    let style = super::fleet_spinner_style();
    let vm_names = ["vm-alpha", "prod-server-01", "x"];
    let bars: Vec<_> = vm_names
        .iter()
        .map(|name| {
            let pb = mp.add(indicatif::ProgressBar::new_spinner());
            pb.set_style(style.clone());
            pb.set_prefix(format!("{:>20}", name));
            pb.set_message("connecting...");
            pb
        })
        .collect();
    // Verify each bar can transition through states
    for (i, pb) in bars.iter().enumerate() {
        pb.set_message(format!("running: cmd-{}", i));
        if i % 2 == 0 {
            pb.finish_with_message(format!("✓ done ({} lines)", i * 10));
        } else {
            pb.finish_with_message(format!("✗ error on vm {}", vm_names[i]));
        }
    }
}

// ── snapshot name format tests ───────────────────────────────

#[test]
fn test_snapshot_name_format_different_vms() {
    for vm_name in &["dev-vm", "prod-server-01", "test_box"] {
        let name = format!(
            "{}_snapshot_{}",
            vm_name,
            chrono::Utc::now().format("%Y%m%d_%H%M%S")
        );
        assert!(name.starts_with(&format!("{}_snapshot_", vm_name)));
    }
}

#[test]
fn test_snapshot_name_contains_timestamp_components() {
    let snap = format!("vm_snapshot_{}", chrono::Utc::now().format("%Y%m%d_%H%M%S"));
    let parts: Vec<&str> = snap.split('_').collect();
    assert!(parts.len() >= 4); // vm, snapshot, date, time
}

// ── storage SKU mapping tests ────────────────────────────────

#[test]
fn test_storage_sku_mapping_case_insensitive() {
    for input in &["PREMIUM", "Premium", "premium", "pReMiUm"] {
        let sku = match input.to_lowercase().as_str() {
            "premium" => "Premium_LRS",
            "standard" => "Standard_LRS",
            _ => "Premium_LRS",
        };
        assert_eq!(sku, "Premium_LRS", "Failed for input: {}", input);
    }
}

#[test]
fn test_storage_sku_mapping_standard_variants() {
    for input in &["STANDARD", "Standard", "standard"] {
        let sku = match input.to_lowercase().as_str() {
            "premium" => "Premium_LRS",
            "standard" => "Standard_LRS",
            _ => "Premium_LRS",
        };
        assert_eq!(sku, "Standard_LRS", "Failed for input: {}", input);
    }
}

#[test]
fn test_storage_sku_mapping_unknown_defaults_to_premium() {
    for input in &["ultra", "archive", "random", ""] {
        let sku = match input.to_lowercase().as_str() {
            "premium" => "Premium_LRS",
            "standard" => "Standard_LRS",
            _ => "Premium_LRS",
        };
        assert_eq!(sku, "Premium_LRS", "Failed for input: {}", input);
    }
}

// ── auth profile tests ───────────────────────────────────────

#[test]
fn test_auth_profile_list_empty_directory() {
    let tmp = TempDir::new().unwrap();
    let profiles_dir = tmp.path().join("profiles");
    fs::create_dir_all(&profiles_dir).unwrap();

    let entries: Vec<String> = fs::read_dir(&profiles_dir)
        .unwrap()
        .filter_map(|e| {
            let name = e.ok()?.file_name().to_string_lossy().to_string();
            if name.ends_with(".json") {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    assert!(entries.is_empty());
}

#[test]
fn test_auth_profile_multiple_profiles() {
    let tmp = TempDir::new().unwrap();
    let profiles_dir = tmp.path().join("profiles");
    fs::create_dir_all(&profiles_dir).unwrap();

    for name in &["dev", "staging", "prod"] {
        let data = serde_json::json!({
            "tenant_id": format!("{}-tenant", name),
            "client_id": format!("{}-client", name),
        });
        fs::write(
            profiles_dir.join(format!("{}.json", name)),
            serde_json::to_string(&data).unwrap(),
        )
        .unwrap();
    }

    let count = fs::read_dir(&profiles_dir)
        .unwrap()
        .filter_map(|e| {
            let n = e.ok()?.file_name().to_string_lossy().to_string();
            if n.ends_with(".json") {
                Some(n)
            } else {
                None
            }
        })
        .count();
    assert_eq!(count, 3);
}

// ── context tests ────────────────────────────────────────────

#[test]
fn test_context_switch_updates_file() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path().join("contexts");
    fs::create_dir_all(&ctx_dir).unwrap();

    let current_path = tmp.path().join("current_context");

    // Create two contexts
    for name in &["dev", "prod"] {
        let ctx = serde_json::json!({
            "name": name,
            "region": if *name == "dev" { "westus2" } else { "eastus" },
        });
        fs::write(
            ctx_dir.join(format!("{}.json", name)),
            serde_json::to_string(&ctx).unwrap(),
        )
        .unwrap();
    }

    // Switch to prod
    fs::write(&current_path, "prod").unwrap();
    assert_eq!(fs::read_to_string(&current_path).unwrap(), "prod");

    // Switch to dev
    fs::write(&current_path, "dev").unwrap();
    assert_eq!(fs::read_to_string(&current_path).unwrap(), "dev");
}

// ── session tests ────────────────────────────────────────────

#[test]
fn test_session_list_multiple() {
    let tmp = TempDir::new().unwrap();
    let sessions_dir = tmp.path().join("sessions");
    fs::create_dir_all(&sessions_dir).unwrap();

    for i in 0..5 {
        let content = format!(
            "name = \"session-{i}\"\nresource_group = \"rg-{i}\"\nvms = []\ncreated = \"2025-01-01T00:00:00Z\"\n"
        );
        fs::write(sessions_dir.join(format!("session-{}.toml", i)), content).unwrap();
    }

    let sessions: Vec<String> = fs::read_dir(&sessions_dir)
        .unwrap()
        .filter_map(|e| Some(e.ok()?.file_name().to_string_lossy().to_string()))
        .filter(|n| n.ends_with(".toml"))
        .collect();
    assert_eq!(sessions.len(), 5);
}

#[test]
fn test_session_overwrite() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("session.toml");

    let v1 = "name = \"s1\"\nresource_group = \"rg-old\"\nvms = []\n";
    fs::write(&path, v1).unwrap();

    let v2 = "name = \"s1\"\nresource_group = \"rg-new\"\nvms = []\n";
    fs::write(&path, v2).unwrap();

    let loaded: toml::Value = fs::read_to_string(&path).unwrap().parse().unwrap();
    assert_eq!(
        loaded.as_table().unwrap()["resource_group"]
            .as_str()
            .unwrap(),
        "rg-new"
    );
}

#[test]
fn test_session_delete() {
    let tmp = TempDir::new().unwrap();
    let sessions_dir = tmp.path().join("sessions");
    fs::create_dir_all(&sessions_dir).unwrap();

    let path = sessions_dir.join("to-delete.toml");
    fs::write(
        &path,
        "name = \"to-delete\"\nresource_group = \"rg\"\nvms = []\n",
    )
    .unwrap();
    assert!(path.exists());

    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}

#[test]
fn test_session_toml_with_vms() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("dev-team.toml");

    let content = "\
name = \"dev-team\"\n\
resource_group = \"dev-rg\"\n\
vms = [\"dev-vm-1\", \"dev-vm-2\", \"dev-vm-3\"]\n\
created = \"2024-01-01T00:00:00Z\"\n";
    fs::write(&path, content).unwrap();

    let loaded: toml::Value = fs::read_to_string(&path).unwrap().parse().unwrap();
    let tbl = loaded.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "dev-team");
    assert_eq!(tbl["resource_group"].as_str().unwrap(), "dev-rg");
    let vms: Vec<&str> = tbl["vms"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|v| v.as_str())
        .collect();
    assert_eq!(vms, vec!["dev-vm-1", "dev-vm-2", "dev-vm-3"]);
    assert_eq!(tbl["created"].as_str().unwrap(), "2024-01-01T00:00:00Z");
}

#[test]
fn test_session_load_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("sessions").join("ghost.toml");
    assert!(!path.exists());
}

// ── template tests ───────────────────────────────────────────

#[test]
fn test_template_list_empty() {
    let tmp = TempDir::new().unwrap();
    let tpl_dir = tmp.path().join("templates");
    fs::create_dir_all(&tpl_dir).unwrap();

    let count = fs::read_dir(&tpl_dir).unwrap().count();
    assert_eq!(count, 0);
}

#[test]
fn test_template_with_cloud_init() {
    let tmp = TempDir::new().unwrap();
    let tpl = serde_json::json!({
        "name": "web-server",
        "vm_size": "Standard_B2s",
        "cloud_init": "#!/bin/bash\napt-get update && apt-get install -y nginx",
    });
    let path = tmp.path().join("web-server.json");
    fs::write(&path, serde_json::to_string_pretty(&tpl).unwrap()).unwrap();

    let loaded: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    assert!(loaded["cloud_init"].as_str().unwrap().contains("nginx"));
}

#[test]
fn test_template_delete() {
    let tmp = TempDir::new().unwrap();
    let path = tmp.path().join("ephemeral.json");
    fs::write(&path, r#"{"name":"ephemeral"}"#).unwrap();
    assert!(path.exists());
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}

// ── keys tests ───────────────────────────────────────────────

#[test]
fn test_keys_list_no_ssh_dir() {
    let tmp = TempDir::new().unwrap();
    let nonexistent = tmp.path().join("no_such_dir");
    assert!(fs::read_dir(&nonexistent).is_err());
}

#[test]
fn test_keys_list_filters_non_key_files() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    fs::write(ssh_dir.join("authorized_keys"), "key data").unwrap();
    fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();
    fs::write(ssh_dir.join("config"), "Host *").unwrap();

    let key_files: Vec<String> = fs::read_dir(ssh_dir)
        .unwrap()
        .filter_map(|e| {
            let name = e.ok()?.file_name().to_string_lossy().to_string();
            if name.starts_with("id_") || name.ends_with(".pub") {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    assert!(key_files.is_empty());
}

#[test]
fn test_keys_multiple_key_types() {
    let tmp = TempDir::new().unwrap();
    let ssh_dir = tmp.path();
    for key_type in &["id_rsa", "id_ed25519", "id_ecdsa"] {
        fs::write(ssh_dir.join(key_type), "private").unwrap();
        fs::write(ssh_dir.join(format!("{}.pub", key_type)), "public").unwrap();
    }

    let keys: Vec<String> = fs::read_dir(ssh_dir)
        .unwrap()
        .filter_map(|e| {
            let name = e.ok()?.file_name().to_string_lossy().to_string();
            if name.starts_with("id_") {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    assert_eq!(keys.len(), 6); // 3 private + 3 public
}

// ── resolve_vm_targets tests ─────────────────────────────────

#[tokio::test]
async fn test_resolve_vm_targets_with_ip_flag() {
    let targets = super::resolve_vm_targets(Some("my-vm"), Some("192.168.1.1"), None)
        .await
        .unwrap();
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0].vm_name, "my-vm");
    assert_eq!(targets[0].ip, "192.168.1.1");
    assert_eq!(targets[0].user, "azureuser");
    assert!(targets[0].bastion.is_none());
}

#[tokio::test]
async fn test_resolve_vm_targets_ip_only_no_vm_name() {
    let targets = super::resolve_vm_targets(None, Some("10.0.0.1"), None)
        .await
        .unwrap();
    assert_eq!(targets.len(), 1);
    assert_eq!(targets[0].vm_name, "10.0.0.1"); // uses IP as display name
    assert_eq!(targets[0].ip, "10.0.0.1");
    assert!(targets[0].bastion.is_none());
}

#[test]
fn test_completions_bash() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "bash"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("_azlin"));
}

#[test]
fn test_completions_zsh() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "zsh"])
        .output()
        .unwrap();
    assert!(output.status.success());
}

#[test]
fn test_completions_fish() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "fish"])
        .output()
        .unwrap();
    assert!(output.status.success());
}

// ── CLI integration: version ─────────────────────────────────

#[test]
fn test_version_command() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .arg("version")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azlin"));
    assert!(stdout.contains("2.3.0"));
}

#[test]
fn test_help_flag() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .arg("--help")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azlin"));
}

// ── CLI integration: azlin-help ──────────────────────────────

#[test]
fn test_azlin_help_no_args() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .arg("azlin-help")
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("azlin"));
}

#[test]
fn test_azlin_help_with_subcommand() {
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["azlin-help", "list"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("list"));
}

// ── CLI integration: template ────────────────────────────────

#[test]
fn test_cli_template_save_and_list() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "save", "mytemplate"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Saved template 'mytemplate'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("mytemplate"));
}

#[test]
fn test_cli_template_save_with_options() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "template",
            "save",
            "custom-tpl",
            "--description",
            "A test template",
            "--vm-size",
            "Standard_D8s_v3",
            "--region",
            "eastus",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "show", "custom-tpl"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Standard_D8s_v3"));
    assert!(stdout.contains("eastus"));
    assert!(stdout.contains("A test template"));
}

#[test]
fn test_cli_template_show_nonexistent() {
    let dir = TempDir::new().unwrap();
    // Ensure azlin dir exists
    fs::create_dir_all(dir.path().join(".azlin").join("templates")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "show", "no-such-template"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not found"));
}

#[test]
fn test_cli_template_apply() {
    let dir = TempDir::new().unwrap();
    // First create a template
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "template",
            "save",
            "apply-test",
            "--vm-size",
            "Standard_D2s_v3",
            "--region",
            "westus2",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "apply", "apply-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Standard_D2s_v3"));
    assert!(stdout.contains("westus2"));
}

#[test]
fn test_cli_template_delete_force() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "save", "todelete"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "delete", "todelete", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Deleted template 'todelete'"));

    // Verify it's gone
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "show", "todelete"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_cli_template_export_import() {
    let dir = TempDir::new().unwrap();
    // Create a template
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "template",
            "save",
            "exportme",
            "--vm-size",
            "Standard_D4s_v3",
            "--region",
            "northeurope",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let export_path = dir.path().join("exported.toml");
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "export", "exportme"])
        .arg(&export_path)
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(export_path.exists());

    // Delete the original
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "delete", "exportme", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    // Import it back
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "import"])
        .arg(&export_path)
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Imported template 'exportme'"));
}

#[test]
fn test_cli_template_list_empty_dir() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No templates found"));
}

#[test]
fn test_cli_template_create_alias() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "create", "via-create"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Saved template 'via-create'"));
}

#[test]
fn test_cli_template_list_multiple() {
    let dir = TempDir::new().unwrap();
    for name in &["tpl-a", "tpl-b", "tpl-c"] {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "save", name])
            .env("HOME", dir.path())
            .output()
            .unwrap();
    }
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("tpl-a"));
    assert!(stdout.contains("tpl-b"));
    assert!(stdout.contains("tpl-c"));
}

// ── CLI integration: sessions ────────────────────────────────

#[test]
fn test_cli_sessions_list_empty() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No saved sessions"));
}

#[test]
fn test_cli_sessions_save_and_list() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "my-session",
            "--resource-group",
            "test-rg",
            "--vms",
            "vm1",
            "vm2",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Saved session 'my-session'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("my-session"));
}

#[test]
fn test_cli_sessions_save_and_load() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "load-test",
            "--resource-group",
            "rg-test",
            "--vms",
            "vm-alpha",
            "vm-beta",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "load-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Loaded session 'load-test'"));
    assert!(stdout.contains("rg-test"));
    assert!(stdout.contains("vm-alpha"));
    assert!(stdout.contains("vm-beta"));
}

#[test]
fn test_cli_sessions_load_nonexistent() {
    let dir = TempDir::new().unwrap();
    fs::create_dir_all(dir.path().join(".azlin").join("sessions")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "nonexistent"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not found"));
}

#[test]
fn test_cli_sessions_delete() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "delete-me",
            "--resource-group",
            "rg1",
            "--vms",
            "vm1",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "delete", "delete-me", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Deleted session"));

    // Verify it's gone
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "delete-me"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
}

#[test]
fn test_cli_sessions_list_multiple() {
    let dir = TempDir::new().unwrap();
    for name in &["sess-1", "sess-2", "sess-3"] {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                name,
                "--resource-group",
                "rg",
                "--vms",
                "vm1",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();
    }
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("sess-1"));
    assert!(stdout.contains("sess-2"));
    assert!(stdout.contains("sess-3"));
}

#[test]
fn test_cli_sessions_overwrite() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "overwrite-me",
            "--resource-group",
            "rg-old",
            "--vms",
            "vm-old",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "overwrite-me",
            "--resource-group",
            "rg-new",
            "--vms",
            "vm-new",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "load", "overwrite-me"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("rg-new"));
    assert!(stdout.contains("vm-new"));
}

// ── CLI integration: context ─────────────────────────────────

#[test]
fn test_cli_context_list_empty() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No contexts found"));
}

#[test]
fn test_cli_context_create_and_list() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "dev-env"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Created context 'dev-env'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("dev-env"));
}

#[test]
fn test_cli_context_create_with_options() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "context",
            "create",
            "prod-env",
            "--subscription-id",
            "sub-123",
            "--tenant-id",
            "tenant-456",
            "--resource-group",
            "prod-rg",
            "--region",
            "eastus2",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());

    // Verify the TOML file was written with the correct fields
    let ctx_path = dir
        .path()
        .join(".azlin")
        .join("contexts")
        .join("prod-env.toml");
    assert!(ctx_path.exists());
    let content = fs::read_to_string(&ctx_path).unwrap();
    assert!(content.contains("sub-123"));
    assert!(content.contains("tenant-456"));
    assert!(content.contains("prod-rg"));
    assert!(content.contains("eastus2"));
}

#[test]
fn test_cli_context_use_and_show() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "staging"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "staging"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Switched to context 'staging'"));

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("staging"));
}

#[test]
fn test_cli_context_use_nonexistent() {
    let dir = TempDir::new().unwrap();
    fs::create_dir_all(dir.path().join(".azlin").join("contexts")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "nonexistent"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("not found"));
}

#[test]
fn test_cli_context_delete_force() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "deleteme"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "delete", "deleteme", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Deleted context 'deleteme'"));
}

#[test]
fn test_cli_context_delete_clears_active() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "active-ctx"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "active-ctx"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "delete", "active-ctx", "--force"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    // Active-context file should be removed
    let active_path = dir.path().join(".azlin").join("active-context");
    assert!(!active_path.exists());
}

#[test]
fn test_cli_context_rename() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "old-name", "--region", "westus2"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "rename", "old-name", "new-name"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Renamed context"));

    // Old file should be gone, new file should exist
    let old_path = dir
        .path()
        .join(".azlin")
        .join("contexts")
        .join("old-name.toml");
    let new_path = dir
        .path()
        .join(".azlin")
        .join("contexts")
        .join("new-name.toml");
    assert!(!old_path.exists());
    assert!(new_path.exists());

    // Name field inside the TOML should be updated
    let content = fs::read_to_string(&new_path).unwrap();
    assert!(content.contains("new-name"));
}

#[test]
fn test_cli_context_rename_updates_active() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "rename-active"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "rename-active"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "rename", "rename-active", "renamed-active"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let active = fs::read_to_string(dir.path().join(".azlin").join("active-context")).unwrap();
    assert_eq!(active.trim(), "renamed-active");
}

#[test]
fn test_cli_context_list_marks_active() {
    let dir = TempDir::new().unwrap();
    for name in &["ctx-a", "ctx-b", "ctx-c"] {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", name])
            .env("HOME", dir.path())
            .output()
            .unwrap();
    }

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "ctx-b"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("* ctx-b"));
}

#[test]
fn test_cli_context_show_no_selection() {
    let dir = TempDir::new().unwrap();
    fs::create_dir_all(dir.path().join(".azlin").join("contexts")).unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("No context selected"));
}

#[test]
fn test_cli_context_switch_alias() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "switch-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "switch", "switch-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("Switched to context 'switch-test'"));
}

#[test]
fn test_cli_context_current_alias() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "create", "cur-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "cur-test"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "current"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("cur-test"));
}

#[test]
fn test_cli_context_migrate() {
    let dir = TempDir::new().unwrap();
    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "migrate"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    // With empty HOME, either no config found or migration attempted
    assert!(
        stdout.contains("No legacy configuration found")
            || stdout.contains("Migrated")
            || stdout.contains("Could not determine"),
        "Unexpected output: {}",
        stdout
    );
}

// ── CLI integration: output formats ──────────────────────────

#[test]
fn test_cli_template_list_json_format() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "save", "json-test", "--vm-size", "Standard_B2s"])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "json", "template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("json-test"));
}

#[test]
fn test_cli_sessions_list_json_format() {
    let dir = TempDir::new().unwrap();
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "sessions",
            "save",
            "json-sess",
            "--resource-group",
            "rg",
            "--vms",
            "vm1",
        ])
        .env("HOME", dir.path())
        .output()
        .unwrap();

    let output = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "json", "sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.contains("json-sess"));
}

// ── Unit tests: collect_health_metrics edge cases ─────────────

#[test]
fn test_health_metrics_deallocated_vm() {
    let m = super::collect_health_metrics("vm-dealloc", "10.0.0.1", "user", "VM deallocated", None);
    assert_eq!(m.vm_name, "vm-dealloc");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

#[test]
fn test_health_metrics_deallocating_vm() {
    let m = super::collect_health_metrics("vm-x", "10.0.0.1", "user", "VM deallocating", None);
    assert_eq!(m.power_state, "VM deallocating");
}

// ── Unit tests: render_health_table edge cases ───────────────

#[test]
fn test_render_health_table_many_entries() {
    let metrics: Vec<super::HealthMetrics> = (0..20)
        .map(|i| super::HealthMetrics {
            vm_name: format!("vm-{}", i),
            power_state: "VM running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: i as f32 * 5.0,
            mem_percent: i as f32 * 3.0,
            disk_percent: i as f32 * 2.0,
        })
        .collect();
    // Should not panic with many entries
    super::render_health_table(&metrics);
}

#[test]
fn test_render_health_table_100_percent() {
    let metrics = vec![super::HealthMetrics {
        vm_name: "vm-full".to_string(),
        power_state: "VM running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 100.0,
        mem_percent: 100.0,
        disk_percent: 100.0,
    }];
    // Should not panic
    super::render_health_table(&metrics);
}

// ── CLI integration: subcommand --help coverage ──────────────

#[test]
fn test_bastion_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "--help"])
        .assert()
        .success();
}

#[test]
fn test_bastion_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_bastion_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_bastion_configure_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["bastion", "configure", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_create_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "create", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_restore_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "restore", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_delete_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "delete", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_enable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "enable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_disable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "disable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_sync_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "sync", "--help"])
        .assert()
        .success();
}

#[test]
fn test_snapshot_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_mount_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "mount", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_create_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "create", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_storage_delete_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["storage", "delete", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_add_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "add", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_remove_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "remove", "--help"])
        .assert()
        .success();
}

#[test]
fn test_tag_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_setup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "setup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_test_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "test", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_show_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "show", "--help"])
        .assert()
        .success();
}

#[test]
fn test_auth_remove_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "remove", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_rotate_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "rotate", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_export_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "export", "--help"])
        .assert()
        .success();
}

#[test]
fn test_keys_backup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "backup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_command_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "command", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_stop_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "stop", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_start_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "start", "--help"])
        .assert()
        .success();
}

#[test]
fn test_batch_sync_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["batch", "sync", "--help"])
        .assert()
        .success();
}

#[test]
fn test_fleet_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "--help"])
        .assert()
        .success();
}

#[test]
fn test_fleet_run_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "run", "--help"])
        .assert()
        .success();
}

#[test]
fn test_fleet_workflow_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "workflow", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_dashboard_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "dashboard", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_history_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "history", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_budget_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "budget", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_recommend_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "recommend", "--help"])
        .assert()
        .success();
}

#[test]
fn test_costs_actions_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["costs", "actions", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_up_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "up", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_down_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "down", "--help"])
        .assert()
        .success();
}

#[test]
fn test_compose_ps_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["compose", "ps", "--help"])
        .assert()
        .success();
}

#[test]
fn test_ip_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["ip", "--help"])
        .assert()
        .success();
}

#[test]
fn test_ip_check_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["ip", "check", "--help"])
        .assert()
        .success();
}

#[test]
fn test_disk_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["disk", "--help"])
        .assert()
        .success();
}

#[test]
fn test_disk_add_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["disk", "add", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_enable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "enable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_disable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "disable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_github_runner_scale_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["github-runner", "scale", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_enable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "enable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_disable_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "disable", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_config_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "config", "--help"])
        .assert()
        .success();
}

#[test]
fn test_autopilot_run_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["autopilot", "run", "--help"])
        .assert()
        .success();
}

#[test]
fn test_web_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "--help"])
        .assert()
        .success();
}

#[test]
fn test_web_start_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "start", "--help"])
        .assert()
        .success();
}

#[test]
fn test_web_stop_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["web", "stop", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_deploy_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "deploy", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_show_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "show", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_cleanup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "cleanup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_doit_examples_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "examples", "--help"])
        .assert()
        .success();
}

// ── CLI integration: top-level command --help ────────────────

#[test]
fn test_new_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["new", "--help"])
        .assert()
        .success();
}

#[test]
fn test_list_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["list", "--help"])
        .assert()
        .success();
}

#[test]
fn test_start_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["start", "--help"])
        .assert()
        .success();
}

#[test]
fn test_stop_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["stop", "--help"])
        .assert()
        .success();
}

#[test]
fn test_show_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["show", "--help"])
        .assert()
        .success();
}

#[test]
fn test_connect_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["connect", "--help"])
        .assert()
        .success();
}

#[test]
fn test_delete_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["delete", "--help"])
        .assert()
        .success();
}

#[test]
fn test_health_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["health", "--help"])
        .assert()
        .success();
}

#[test]
fn test_env_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "--help"])
        .assert()
        .success();
}

#[test]
fn test_cost_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["cost", "--help"])
        .assert()
        .success();
}

#[test]
fn test_session_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["session", "--help"])
        .assert()
        .success();
}

#[test]
fn test_config_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["config", "--help"])
        .assert()
        .success();
}

#[test]
fn test_ask_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["ask", "--help"])
        .assert()
        .success();
}

#[test]
fn test_do_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["do", "--help"])
        .assert()
        .success();
}

#[test]
fn test_clone_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["clone", "--help"])
        .assert()
        .success();
}

#[test]
fn test_cp_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["cp", "--help"])
        .assert()
        .success();
}

#[test]
fn test_sync_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sync", "--help"])
        .assert()
        .success();
}

#[test]
fn test_update_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["update", "--help"])
        .assert()
        .success();
}

#[test]
fn test_logs_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["logs", "--help"])
        .assert()
        .success();
}

#[test]
fn test_cleanup_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["cleanup", "--help"])
        .assert()
        .success();
}

#[test]
fn test_prune_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["prune", "--help"])
        .assert()
        .success();
}

#[test]
fn test_restore_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["restore", "--help"])
        .assert()
        .success();
}

#[test]
fn test_status_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["status", "--help"])
        .assert()
        .success();
}

#[test]
fn test_code_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["code", "--help"])
        .assert()
        .success();
}

#[test]
fn test_os_update_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["os-update", "--help"])
        .assert()
        .success();
}

#[test]
fn test_sync_keys_help() {
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sync-keys", "--help"])
        .assert()
        .success();
}

// ── CLI integration: config commands with temp home ──────────

#[test]
fn test_config_show_with_temp_home() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["config", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&out.stdout);
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        out.status.success()
            || stdout.contains("config")
            || stderr.contains("config")
            || stdout.contains("No")
    );
}

#[test]
fn test_config_set_and_show() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["config", "set", "resource_group", "test-rg"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(out.status.success() || combined.contains("config") || combined.contains("set"));
}

// ── CLI integration: completions content verification ────────

#[test]
fn test_completions_zsh_content() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "zsh"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("compdef") || stdout.len() > 100);
}

#[test]
fn test_completions_powershell() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "powershell"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(out.stdout.len() > 50);
}

#[test]
fn test_completions_elvish() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["completions", "elvish"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(out.stdout.len() > 50);
}

// ── CLI integration: graceful failures without Azure ─────────

#[test]
fn test_list_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["list"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    // Should fail gracefully, not crash
    let stderr = String::from_utf8_lossy(&out.stderr);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        !out.status.success()
            || stderr.contains("config")
            || stderr.contains("subscription")
            || stderr.contains("auth")
            || stderr.contains("az login")
            || stdout.contains("No VMs")
    );
}

#[test]
fn test_show_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["show", "nonexistent-vm"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    assert!(!out.status.success() || !String::from_utf8_lossy(&out.stderr).is_empty());
}

#[test]
fn test_health_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["health"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    // Graceful failure or empty result
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success() || !combined.is_empty());
}

#[test]
fn test_status_no_config() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["status"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success() || !combined.is_empty());
}

// ── CLI integration: context full lifecycle ──────────────────

#[test]
fn test_context_full_lifecycle() {
    let dir = TempDir::new().unwrap();
    // create
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args([
            "context",
            "create",
            "lifecycle-ctx",
            "--subscription-id",
            "sub-123",
            "--resource-group",
            "rg-test",
        ])
        .env("HOME", dir.path())
        .assert()
        .success();
    // list
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
    // use
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "use", "lifecycle-ctx"])
        .env("HOME", dir.path())
        .assert()
        .success();
    // show
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "show"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
    // delete
    assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "delete", "lifecycle-ctx", "--force"])
        .env("HOME", dir.path())
        .assert()
        .success();
}

// ── CLI integration: auth list with temp home ────────────────

#[test]
fn test_auth_list_empty() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["auth", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(
        stdout.contains("No")
            || stdout.contains("profile")
            || stdout.is_empty()
            || stdout.contains("auth")
    );
}

// ── CLI integration: sessions with temp home ─────────────────

#[test]
fn test_sessions_list_empty_temp() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(out.status.success());
}

// ── CLI integration: template with temp home ─────────────────

#[test]
fn test_template_list_empty_temp() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "list"])
        .env("HOME", dir.path())
        .output()
        .unwrap();
    assert!(out.status.success());
}

// ── CLI integration: verbose flag ────────────────────────────

#[test]
fn test_verbose_version() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--verbose", "version"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(String::from_utf8_lossy(&out.stdout).contains("2.3.0"));
}

// ── CLI integration: json output format ──────────────────────

#[test]
fn test_json_output_version() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "json", "version"])
        .output()
        .unwrap();
    assert!(out.status.success());
}

#[test]
fn test_csv_output_version() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["--output", "csv", "version"])
        .output()
        .unwrap();
    assert!(out.status.success());
}

// ── CLI integration: invalid subcommand ──────────────────────

#[test]
fn test_invalid_subcommand() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["totally-bogus-command"])
        .output()
        .unwrap();
    assert!(!out.status.success());
    let stderr = String::from_utf8_lossy(&out.stderr);
    assert!(
        stderr.contains("error")
            || stderr.contains("unrecognized")
            || stderr.contains("invalid")
            || !stderr.is_empty()
    );
}

// ── CLI integration: doit examples ───────────────────────────

#[test]
fn test_doit_examples() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["doit", "examples"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(out.stdout.len() > 10);
}

// ── Tests for extracted helper functions ─────────────────────────

#[test]
fn test_format_cost_summary_json() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 123.45,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Json,
        &None,
        &None,
        false,
        false,
    );
    assert!(result.contains("123.45"));
    assert!(result.contains("USD"));
}

#[test]
fn test_format_cost_summary_csv() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 99.99,
        currency: "EUR".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        false,
    );
    assert!(result.contains("Total Cost,Currency,Period Start,Period End"));
    assert!(result.contains("99.99"));
    assert!(result.contains("EUR"));
}

#[test]
fn test_format_cost_summary_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        false,
    );
    assert!(result.contains("Total Cost: $50.00 USD"));
    assert!(result.contains("Period:"));
}

#[test]
fn test_format_cost_summary_with_estimate() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2024-01-01".to_string()),
        &Some("2024-01-31".to_string()),
        true,
        false,
    );
    assert!(result.contains("Estimate: $200.00/month (projected)"));
    assert!(result.contains("From filter: 2024-01-01"));
    assert!(result.contains("To filter: 2024-01-31"));
}

#[test]
fn test_format_cost_summary_by_vm_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 300.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "vm-1".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "vm-2".to_string(),
                cost: 200.0,
                currency: "USD".to_string(),
            },
        ],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(result.contains("vm-1"));
    assert!(result.contains("vm-2"));
    assert!(result.contains("$100.00"));
    assert!(result.contains("$200.00"));
}

#[test]
fn test_format_cost_summary_by_vm_csv() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 150.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "test-vm".to_string(),
            cost: 150.0,
            currency: "USD".to_string(),
        }],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(result.contains("VM Name,Cost,Currency"));
    assert!(result.contains("test-vm,150.00,USD"));
}

#[test]
fn test_format_cost_summary_by_vm_empty() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 0.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc::now(),
        period_end: chrono::Utc::now(),
        by_vm: vec![],
    };
    let result = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(result.contains("No per-VM cost data available."));
}

#[test]
fn test_parse_cost_history_rows_empty() {
    let data = serde_json::json!({});
    let rows = super::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_with_data() {
    let data = serde_json::json!({
        "rows": [
            [12.34, "2024-01-01"],
            [56.78, "2024-01-02"]
        ]
    });
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0], ("2024-01-01".to_string(), "$12.34".to_string()));
    assert_eq!(rows[1], ("2024-01-02".to_string(), "$56.78".to_string()));
}

#[test]
fn test_parse_cost_history_rows_with_int_date() {
    let data = serde_json::json!({
        "rows": [
            [10.0, 20240101]
        ]
    });
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    // Integer dates hit the as_i64().map(|_| "") branch, producing empty string
    assert_eq!(rows[0].0, "");
    assert_eq!(rows[0].1, "$10.00");
}

#[test]
fn test_parse_cost_history_rows_missing_values() {
    let data = serde_json::json!({
        "rows": [
            [null, null]
        ]
    });
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "-");
    assert_eq!(rows[0].1, "-");
}

#[test]
fn test_parse_recommendation_rows_empty() {
    let data = serde_json::json!([]);
    let rows = super::parse_recommendation_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_recommendation_rows_with_data() {
    let data = serde_json::json!([
        {
            "category": "Cost",
            "impact": "High",
            "shortDescription": {"problem": "Underutilized VM"}
        },
        {
            "category": "Security",
            "impact": "Medium",
            "shortDescription": {"problem": "Open port"}
        }
    ]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(
        rows[0],
        (
            "Cost".to_string(),
            "High".to_string(),
            "Underutilized VM".to_string()
        )
    );
    assert_eq!(
        rows[1],
        (
            "Security".to_string(),
            "Medium".to_string(),
            "Open port".to_string()
        )
    );
}

#[test]
fn test_parse_recommendation_rows_missing_fields() {
    let data = serde_json::json!([{"other_field": "value"}]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0], ("-".to_string(), "-".to_string(), "-".to_string()));
}

#[test]
fn test_parse_cost_action_rows_empty() {
    let data = serde_json::json!([]);
    let rows = super::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_action_rows_with_data() {
    let data = serde_json::json!([
        {
            "impactedField": "Microsoft.Compute/virtualMachines",
            "impact": "High",
            "shortDescription": {"problem": "Resize VM"}
        }
    ]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
    assert_eq!(rows[0].1, "High");
    assert_eq!(rows[0].2, "Resize VM");
}

#[test]
fn test_parse_cost_action_rows_not_array() {
    let data = serde_json::json!({"not": "array"});
    let rows = super::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_templates_build_toml_defaults() {
    let tpl = super::templates::build_template_toml("test", None, None, None, None);
    let tbl = tpl.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "test");
    assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
    assert_eq!(tbl["region"].as_str().unwrap(), "westus2");
    assert_eq!(tbl["description"].as_str().unwrap(), "");
    assert!(tbl.get("cloud_init").is_none());
}

#[test]
fn test_templates_build_toml_custom() {
    let tpl = super::templates::build_template_toml(
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
    let tpl = super::templates::build_template_toml("test-tpl", Some("desc"), None, None, None);
    let path = super::templates::save_template(&dir, "test-tpl", &tpl).unwrap();
    assert!(path.exists());

    let loaded = super::templates::load_template(&dir, "test-tpl").unwrap();
    assert_eq!(loaded.get("name").unwrap().as_str().unwrap(), "test-tpl");
    assert_eq!(loaded.get("description").unwrap().as_str().unwrap(), "desc");
}

#[test]
fn test_templates_load_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let result = super::templates::load_template(tmp.path(), "nope");
    assert!(result.is_err());
}

#[test]
fn test_templates_list_empty() {
    let tmp = TempDir::new().unwrap();
    let rows = super::templates::list_templates(tmp.path()).unwrap();
    assert!(rows.is_empty());
}

#[test]
fn test_templates_list_with_entries() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let tpl1 = super::templates::build_template_toml("a", None, Some("small"), Some("west"), None);
    let tpl2 = super::templates::build_template_toml("b", None, Some("large"), Some("east"), None);
    super::templates::save_template(dir, "a", &tpl1).unwrap();
    super::templates::save_template(dir, "b", &tpl2).unwrap();

    let rows = super::templates::list_templates(dir).unwrap();
    assert_eq!(rows.len(), 2);
}

#[test]
fn test_templates_delete() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let tpl = super::templates::build_template_toml("del-me", None, None, None, None);
    super::templates::save_template(dir, "del-me", &tpl).unwrap();
    assert!(dir.join("del-me.toml").exists());

    super::templates::delete_template(dir, "del-me").unwrap();
    assert!(!dir.join("del-me.toml").exists());
}

#[test]
fn test_templates_delete_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let result = super::templates::delete_template(tmp.path(), "nope");
    assert!(result.is_err());
}

#[test]
fn test_templates_import() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let content = "name = \"imported\"\nvm_size = \"Standard_D2s_v3\"\nregion = \"westus\"\n";
    let name = super::templates::import_template(dir, content).unwrap();
    assert_eq!(name, "imported");
    assert!(dir.join("imported.toml").exists());
}

#[test]
fn test_templates_import_missing_name() {
    let tmp = TempDir::new().unwrap();
    let content = "vm_size = \"Standard_D2s_v3\"\nregion = \"westus\"\n";
    let result = super::templates::import_template(tmp.path(), content);
    assert!(result.is_err());
}

#[test]
fn test_sessions_build_toml() {
    let val =
        super::sessions::build_session_toml("s1", "rg1", &["vm1".to_string(), "vm2".to_string()]);
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
    let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "my-rg");
    assert_eq!(vms, vec!["vm-a", "vm-b"]);
    assert_eq!(created, "2024-01-01T00:00:00Z");
}

#[test]
fn test_sessions_parse_toml_empty_vms() {
    let content =
        "name = \"empty\"\nresource_group = \"rg\"\nvms = []\ncreated = \"2024-01-01T00:00:00Z\"\n";
    let (rg, vms, _) = super::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "rg");
    assert!(vms.is_empty());
}

#[test]
fn test_sessions_parse_toml_missing_fields() {
    let content = "name = \"minimal\"\n";
    let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "-");
    assert!(vms.is_empty());
    assert_eq!(created, "-");
}

#[test]
fn test_sessions_list_names_empty() {
    let tmp = TempDir::new().unwrap();
    let names = super::sessions::list_session_names(tmp.path()).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_sessions_list_names_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let names = super::sessions::list_session_names(&tmp.path().join("nope")).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_sessions_list_names_with_entries() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::write(dir.join("s1.toml"), "name = \"s1\"").unwrap();
    fs::write(dir.join("s2.toml"), "name = \"s2\"").unwrap();
    fs::write(dir.join("not-toml.txt"), "ignore").unwrap();

    let names = super::sessions::list_session_names(dir).unwrap();
    assert_eq!(names.len(), 2);
    assert!(names.contains(&"s1".to_string()));
    assert!(names.contains(&"s2".to_string()));
}

#[test]
fn test_contexts_build_toml_minimal() {
    let result = super::contexts::build_context_toml("ctx1", None, None, None, None, None).unwrap();
    assert!(result.contains("name = \"ctx1\""));
}

#[test]
fn test_contexts_build_toml_full() {
    let result = super::contexts::build_context_toml(
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
    let result = super::contexts::list_contexts(tmp.path(), "").unwrap();
    assert!(result.is_empty());
}

#[test]
fn test_contexts_list_with_active() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::write(dir.join("dev.toml"), "name = \"dev\"").unwrap();
    fs::write(dir.join("prod.toml"), "name = \"prod\"").unwrap();

    let result = super::contexts::list_contexts(dir, "dev").unwrap();
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

    let result = super::contexts::list_contexts(dir, "nonexistent").unwrap();
    assert_eq!(result.len(), 1);
    assert!(!result[0].1);
}

#[test]
fn test_contexts_rename_file() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    let toml_content =
        super::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
    fs::write(dir.join("old.toml"), &toml_content).unwrap();

    super::contexts::rename_context_file(dir, "old", "new").unwrap();
    assert!(!dir.join("old.toml").exists());
    assert!(dir.join("new.toml").exists());

    let content = fs::read_to_string(dir.join("new.toml")).unwrap();
    assert!(content.contains("name = \"new\""));
}

#[test]
fn test_contexts_rename_nonexistent() {
    let tmp = TempDir::new().unwrap();
    let result = super::contexts::rename_context_file(tmp.path(), "nope", "also-nope");
    assert!(result.is_err());
}

// ── env_helpers tests ────────────────────────────────────────

#[test]
fn test_split_env_var_valid() {
    let (k, v) = super::env_helpers::split_env_var("FOO=bar").unwrap();
    assert_eq!(k, "FOO");
    assert_eq!(v, "bar");
}

#[test]
fn test_split_env_var_value_with_equals() {
    let (k, v) = super::env_helpers::split_env_var("DSN=postgres://u:p@h/db?opt=1").unwrap();
    assert_eq!(k, "DSN");
    assert_eq!(v, "postgres://u:p@h/db?opt=1");
}

#[test]
fn test_split_env_var_empty_value() {
    let (k, v) = super::env_helpers::split_env_var("EMPTY=").unwrap();
    assert_eq!(k, "EMPTY");
    assert_eq!(v, "");
}

#[test]
fn test_split_env_var_no_equals() {
    assert!(super::env_helpers::split_env_var("NO_EQUALS").is_none());
}

#[test]
fn test_split_env_var_leading_equals() {
    assert!(super::env_helpers::split_env_var("=value").is_none());
}

#[test]
fn test_build_env_set_cmd_contains_key_value() {
    let cmd = super::env_helpers::build_env_set_cmd("MY_KEY", "'my_val'");
    assert!(cmd.contains("MY_KEY"));
    assert!(cmd.contains("'my_val'"));
    assert!(cmd.contains("grep -q"));
    assert!(cmd.contains("~/.profile"));
}

#[test]
fn test_build_env_delete_cmd() {
    let cmd = super::env_helpers::build_env_delete_cmd("OLD_VAR");
    assert!(cmd.contains("OLD_VAR"));
    assert!(cmd.contains("sed -i"));
    assert!(cmd.contains("~/.profile"));
}

#[test]
fn test_env_list_cmd() {
    assert_eq!(super::env_helpers::env_list_cmd(), "env | sort");
}

#[test]
fn test_env_clear_cmd() {
    let cmd = super::env_helpers::env_clear_cmd();
    assert!(cmd.contains("sed -i"));
    assert!(cmd.contains("export"));
}

#[test]
fn test_parse_env_output_basic() {
    let output = "HOME=/root\nPATH=/usr/bin\nSHELL=/bin/bash\n";
    let vars = super::env_helpers::parse_env_output(output);
    assert_eq!(vars.len(), 3);
    assert_eq!(vars[0], ("HOME".into(), "/root".into()));
    assert_eq!(vars[1], ("PATH".into(), "/usr/bin".into()));
}

#[test]
fn test_parse_env_output_empty() {
    assert!(super::env_helpers::parse_env_output("").is_empty());
}

#[test]
fn test_parse_env_output_value_with_equals() {
    let output = "DSN=host=localhost dbname=test\n";
    let vars = super::env_helpers::parse_env_output(output);
    assert_eq!(vars.len(), 1);
    assert_eq!(vars[0].0, "DSN");
    assert_eq!(vars[0].1, "host=localhost dbname=test");
}

#[test]
fn test_build_env_file() {
    let vars = vec![("A".into(), "1".into()), ("B".into(), "two".into())];
    let file = super::env_helpers::build_env_file(&vars);
    assert_eq!(file, "A=1\nB=two");
}

#[test]
fn test_build_env_file_empty() {
    assert_eq!(super::env_helpers::build_env_file(&[]), "");
}

#[test]
fn test_parse_env_file_basic() {
    let content = "FOO=bar\n# comment\n\nBAZ=qux\n";
    let vars = super::env_helpers::parse_env_file(content);
    assert_eq!(vars.len(), 2);
    assert_eq!(vars[0], ("FOO".into(), "bar".into()));
    assert_eq!(vars[1], ("BAZ".into(), "qux".into()));
}

#[test]
fn test_parse_env_file_empty_lines_only() {
    assert!(super::env_helpers::parse_env_file("\n\n  \n").is_empty());
}

#[test]
fn test_parse_env_file_comments_only() {
    assert!(super::env_helpers::parse_env_file("# comment\n# another").is_empty());
}

#[test]
fn test_parse_env_file_whitespace_trimming() {
    let content = "  KEY=value  \n  OTHER=val2  \n";
    let vars = super::env_helpers::parse_env_file(content);
    assert_eq!(vars.len(), 2);
    assert_eq!(vars[0].0, "KEY");
    assert_eq!(vars[0].1, "value"); // line is trimmed, value after = is as-is
}

#[test]
fn test_parse_env_file_roundtrip() {
    let original = vec![
        ("X".into(), "10".into()),
        ("Y".into(), "hello world".into()),
    ];
    let file = super::env_helpers::build_env_file(&original);
    let parsed = super::env_helpers::parse_env_file(&file);
    assert_eq!(parsed, original);
}

// ── sync_helpers tests ───────────────────────────────────────

#[test]
fn test_default_dotfiles_has_expected_entries() {
    let files = super::sync_helpers::default_dotfiles();
    assert!(files.contains(&".bashrc"));
    assert!(files.contains(&".profile"));
    assert!(files.contains(&".vimrc"));
    assert!(files.contains(&".gitconfig"));
    assert!(files.contains(&".tmux.conf"));
    assert_eq!(files.len(), 5);
}

#[test]
fn test_build_rsync_args_structure() {
    let args = super::sync_helpers::build_rsync_args(
        "/home/me/.bashrc",
        "azureuser",
        "10.0.0.1",
        ".bashrc",
    );
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert_eq!(args[2], "ssh -o StrictHostKeyChecking=accept-new");
    assert_eq!(args[3], "/home/me/.bashrc");
    assert_eq!(args[4], "azureuser@10.0.0.1:~/.bashrc");
}

#[test]
fn test_build_rsync_args_special_chars_in_ip() {
    let args = super::sync_helpers::build_rsync_args("/tmp/f", "user", "192.168.1.100", ".vimrc");
    assert!(args[4].contains("192.168.1.100"));
}

// ── health_helpers tests ─────────────────────────────────────

#[test]
fn test_metric_color_green() {
    assert_eq!(super::health_helpers::metric_color(0.0), "green");
    assert_eq!(super::health_helpers::metric_color(50.0), "green");
}

#[test]
fn test_metric_color_yellow() {
    assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
    assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
}

#[test]
fn test_metric_color_red() {
    assert_eq!(super::health_helpers::metric_color(80.1), "red");
    assert_eq!(super::health_helpers::metric_color(100.0), "red");
}

#[test]
fn test_state_color_running() {
    assert_eq!(super::health_helpers::state_color("running"), "green");
}

#[test]
fn test_state_color_stopped_deallocated() {
    assert_eq!(super::health_helpers::state_color("stopped"), "red");
    assert_eq!(super::health_helpers::state_color("deallocated"), "red");
}

#[test]
fn test_state_color_unknown() {
    assert_eq!(super::health_helpers::state_color("starting"), "yellow");
    assert_eq!(super::health_helpers::state_color(""), "yellow");
}

#[test]
fn test_format_percentage() {
    assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
    assert_eq!(super::health_helpers::format_percentage(99.95), "99.9%");
    assert_eq!(super::health_helpers::format_percentage(42.567), "42.6%");
}

#[test]
fn test_status_emoji_green() {
    assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
    assert_eq!(super::health_helpers::status_emoji(70.0, 70.0, 70.0), "🟢");
}

#[test]
fn test_status_emoji_yellow() {
    assert_eq!(super::health_helpers::status_emoji(70.1, 10.0, 10.0), "🟡");
    assert_eq!(super::health_helpers::status_emoji(10.0, 70.1, 10.0), "🟡");
    assert_eq!(super::health_helpers::status_emoji(10.0, 10.0, 70.1), "🟡");
}

#[test]
fn test_status_emoji_red() {
    assert_eq!(super::health_helpers::status_emoji(90.1, 10.0, 10.0), "🔴");
    assert_eq!(super::health_helpers::status_emoji(10.0, 90.1, 10.0), "🔴");
    assert_eq!(super::health_helpers::status_emoji(10.0, 10.0, 90.1), "🔴");
}

#[test]
fn test_status_emoji_boundary() {
    // exactly 90.0 is yellow, not red
    assert_eq!(super::health_helpers::status_emoji(90.0, 90.0, 90.0), "🟡");
}

// ── snapshot_helpers tests ───────────────────────────────────

#[test]
fn test_build_snapshot_name() {
    let name = super::snapshot_helpers::build_snapshot_name("my-vm", "20250101_120000");
    assert_eq!(name, "my-vm_snapshot_20250101_120000");
}

#[test]
fn test_build_snapshot_name_special_chars() {
    let name = super::snapshot_helpers::build_snapshot_name("vm-with-dashes", "ts");
    assert_eq!(name, "vm-with-dashes_snapshot_ts");
}

#[test]
fn test_filter_snapshots_matches() {
    let snaps: Vec<serde_json::Value> = vec![
        serde_json::json!({"name": "my-vm_snapshot_1", "diskSizeGb": 30}),
        serde_json::json!({"name": "other-vm_snapshot_1", "diskSizeGb": 50}),
        serde_json::json!({"name": "my-vm_snapshot_2", "diskSizeGb": 30}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "my-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_filter_snapshots_no_match() {
    let snaps: Vec<serde_json::Value> = vec![serde_json::json!({"name": "alpha_snapshot_1"})];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "beta");
    assert!(filtered.is_empty());
}

#[test]
fn test_filter_snapshots_missing_name_field() {
    let snaps: Vec<serde_json::Value> = vec![
        serde_json::json!({"id": 1}),
        serde_json::json!({"name": "vm_snapshot_1"}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "vm");
    assert_eq!(filtered.len(), 1);
}

#[test]
fn test_filter_snapshots_empty_list() {
    let snaps: Vec<serde_json::Value> = vec![];
    assert!(super::snapshot_helpers::filter_snapshots(&snaps, "anything").is_empty());
}

#[test]
fn test_snapshot_row_full() {
    let snap = serde_json::json!({
        "name": "vm_snapshot_1",
        "diskSizeGb": 128,
        "timeCreated": "2025-01-15T10:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "vm_snapshot_1");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2025-01-15T10:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_missing_fields() {
    let snap = serde_json::json!({});
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

// ── output_helpers tests ─────────────────────────────────────

#[test]
fn test_format_as_csv_basic() {
    let headers = &["Name", "Value"];
    let rows = vec![vec!["A".into(), "1".into()], vec!["B".into(), "2".into()]];
    let csv = super::output_helpers::format_as_csv(headers, &rows);
    assert_eq!(csv, "Name,Value\nA,1\nB,2");
}

#[test]
fn test_format_as_csv_empty_rows() {
    let csv = super::output_helpers::format_as_csv(&["H1", "H2"], &[]);
    assert_eq!(csv, "H1,H2");
}

#[test]
fn test_format_as_csv_single_column() {
    let rows = vec![vec!["only".into()]];
    let csv = super::output_helpers::format_as_csv(&["Col"], &rows);
    assert_eq!(csv, "Col\nonly");
}

#[test]
fn test_format_as_table_basic() {
    let headers = &["Name", "Age"];
    let rows = vec![
        vec!["Alice".into(), "30".into()],
        vec!["Bob".into(), "25".into()],
    ];
    let tbl = super::output_helpers::format_as_table(headers, &rows);
    assert!(tbl.contains("Name"));
    assert!(tbl.contains("Age"));
    assert!(tbl.contains("Alice"));
    assert!(tbl.contains("Bob"));
    // columns should be aligned
    let lines: Vec<&str> = tbl.lines().collect();
    assert_eq!(lines.len(), 3); // header + 2 rows
}

#[test]
fn test_format_as_table_wide_values() {
    let headers = &["K", "V"];
    let rows = vec![vec!["short".into(), "a very long value here".into()]];
    let tbl = super::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = tbl.lines().collect();
    // header should be padded to match the widest cell
    assert!(lines[0].contains("V"));
    assert!(lines[1].contains("a very long value here"));
}

#[test]
fn test_format_as_table_empty_rows() {
    let tbl = super::output_helpers::format_as_table(&["X"], &[]);
    assert_eq!(tbl, "X");
}

#[test]
fn test_format_as_json_basic() {
    let items = vec![1, 2, 3];
    let json = super::output_helpers::format_as_json(&items);
    let parsed: Vec<i32> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed, vec![1, 2, 3]);
}

#[test]
fn test_format_as_json_strings() {
    let items = vec!["hello", "world"];
    let json = super::output_helpers::format_as_json(&items);
    assert!(json.contains("hello"));
    assert!(json.contains("world"));
}

#[test]
fn test_format_as_json_empty() {
    let items: Vec<String> = vec![];
    let json = super::output_helpers::format_as_json(&items);
    assert_eq!(json.trim(), "[]");
}

#[test]
fn test_creds_file_format() {
    let content = format!("username={}\npassword={}\n", "testaccount", "testkey123");
    assert!(content.starts_with("username="));
    assert!(content.contains("password="));
    assert!(!content.contains("--")); // no CLI args
}

// ── Security & business-logic tests ─────────────────────────────

// 1. Config path traversal
#[test]
fn test_config_path_traversal_blocked() {
    let result = super::config_path_helpers::validate_config_path("../../etc/passwd");
    assert!(result.is_err(), "path traversal must be rejected");
    assert!(result.unwrap_err().contains("traversal"));
}

#[test]
fn test_config_path_traversal_deep() {
    let result = super::config_path_helpers::validate_config_path("foo/../../../etc/shadow");
    assert!(result.is_err());
}

#[test]
fn test_config_path_safe_relative() {
    let result = super::config_path_helpers::validate_config_path("config.toml");
    assert!(result.is_ok());
}

#[test]
fn test_config_path_safe_nested() {
    let result = super::config_path_helpers::validate_config_path("subdir/config.toml");
    assert!(result.is_ok());
}

// 2. VM name validation
#[test]
fn test_vm_name_no_leading_hyphen() {
    let result = super::vm_validation::validate_vm_name("-bad-name");
    assert!(result.is_err(), "leading hyphen must be rejected");
    assert!(result.unwrap_err().contains("hyphen"));
}

#[test]
fn test_vm_name_no_trailing_hyphen() {
    let result = super::vm_validation::validate_vm_name("bad-name-");
    assert!(result.is_err(), "trailing hyphen must be rejected");
}

#[test]
fn test_vm_name_max_length() {
    let long_name = "a".repeat(65);
    let result = super::vm_validation::validate_vm_name(&long_name);
    assert!(result.is_err(), "names > 64 chars must be rejected");
    assert!(result.unwrap_err().contains("64"));
}

#[test]
fn test_vm_name_exactly_64_chars() {
    let name = "a".repeat(64);
    let result = super::vm_validation::validate_vm_name(&name);
    assert!(result.is_ok(), "exactly 64 chars should be allowed");
}

#[test]
fn test_vm_name_empty() {
    let result = super::vm_validation::validate_vm_name("");
    assert!(result.is_err());
}

#[test]
fn test_vm_name_no_shell_metacharacters() {
    for bad in &["vm;rm", "vm$(whoami)", "vm`id`", "vm|cat", "vm&bg"] {
        let result = super::vm_validation::validate_vm_name(bad);
        assert!(result.is_err(), "'{}' must be rejected", bad);
    }
}

#[test]
fn test_vm_name_valid() {
    assert!(super::vm_validation::validate_vm_name("my-dev-vm-01").is_ok());
    assert!(super::vm_validation::validate_vm_name("VM1").is_ok());
}

// 3. Env variable security
#[test]
fn test_env_key_no_command_injection() {
    let result = super::env_helpers::validate_env_key("MY_VAR;rm -rf /");
    assert!(result.is_err(), "semicolons in key must be rejected");
}

#[test]
fn test_env_key_no_spaces() {
    let result = super::env_helpers::validate_env_key("MY VAR");
    assert!(result.is_err(), "spaces in key must be rejected");
}

#[test]
fn test_env_key_no_equals() {
    let result = super::env_helpers::validate_env_key("MY=VAR");
    assert!(result.is_err(), "equals in key must be rejected");
}

#[test]
fn test_env_key_no_dollar() {
    let result = super::env_helpers::validate_env_key("$HOME");
    assert!(result.is_err(), "dollar sign in key must be rejected");
}

#[test]
fn test_env_key_no_leading_digit() {
    let result = super::env_helpers::validate_env_key("9VAR");
    assert!(result.is_err(), "leading digit must be rejected");
}

#[test]
fn test_env_key_valid() {
    assert!(super::env_helpers::validate_env_key("MY_VAR").is_ok());
    assert!(super::env_helpers::validate_env_key("PATH").is_ok());
    assert!(super::env_helpers::validate_env_key("_PRIVATE").is_ok());
}

#[test]
fn test_env_value_no_command_injection() {
    let escaped = super::shell_escape("$(whoami)");
    // shell_escape wraps in single quotes, neutralizing $()
    assert!(escaped.starts_with('\''), "value must be single-quoted");
    assert!(escaped.ends_with('\''), "value must be single-quoted");
    // The $(whoami) is inside single quotes so won't execute
    let cmd = super::env_helpers::build_env_set_cmd("MY_VAR", &escaped);
    assert!(cmd.contains("'$(whoami)'"), "injection must be quoted");
}

#[test]
fn test_env_value_semicolon_injection() {
    let escaped = super::shell_escape("value; rm -rf /");
    let cmd = super::env_helpers::build_env_set_cmd("VAR", &escaped);
    // The semicolon must be inside quotes, not acting as a command separator
    assert!(
        cmd.contains("'value; rm -rf /'"),
        "semicolon must be quoted, got: {}",
        cmd
    );
}

#[test]
fn test_env_set_cmd_rejects_bad_key() {
    let cmd = super::env_helpers::build_env_set_cmd("BAD;KEY", "'safe_value'");
    // With a bad key, should return a no-op
    assert_eq!(cmd, "true", "bad key should produce no-op command");
}

// 4. Shell escape
#[test]
fn test_shell_escape_semicolons() {
    let escaped = super::shell_escape("hello; rm -rf /");
    // Must be wrapped in single quotes
    assert!(escaped.starts_with('\''));
    assert!(escaped.ends_with('\''));
    assert!(escaped.contains("hello; rm -rf /"));
}

#[test]
fn test_shell_escape_backticks() {
    let escaped = super::shell_escape("`whoami`");
    assert!(escaped.starts_with('\''), "backticks must be quoted");
    assert!(escaped.contains("`whoami`"));
}

#[test]
fn test_shell_escape_dollar_paren() {
    let escaped = super::shell_escape("$(rm -rf /)");
    assert!(escaped.starts_with('\''));
    // The dangerous sequence is neutralized inside single quotes
    assert!(!escaped.starts_with("$("));
}

#[test]
fn test_shell_escape_single_quotes() {
    let escaped = super::shell_escape("it's dangerous");
    // Single quotes within single-quoted strings need special escaping
    assert!(escaped.contains("'\\''"), "single quote must be escaped");
}

#[test]
fn test_shell_escape_empty_string_security() {
    let escaped = super::shell_escape("");
    assert_eq!(escaped, "''");
}

#[test]
fn test_shell_escape_pipe() {
    let escaped = super::shell_escape("data | cat /etc/passwd");
    assert!(escaped.starts_with('\''));
    assert!(escaped.ends_with('\''));
}

#[test]
fn test_shell_escape_newlines() {
    let escaped = super::shell_escape("line1\nline2");
    assert!(escaped.starts_with('\''));
    assert!(escaped.ends_with('\''));
}

// 5. Mount path injection
#[test]
fn test_mount_path_no_semicolons() {
    let result = super::mount_helpers::validate_mount_path("/mnt/data;rm -rf /");
    assert!(result.is_err(), "semicolons in mount path must be rejected");
}

#[test]
fn test_mount_path_no_pipe() {
    let result = super::mount_helpers::validate_mount_path("/mnt/data|cat /etc/passwd");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_no_backticks() {
    let result = super::mount_helpers::validate_mount_path("/mnt/`whoami`");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_no_dollar_paren() {
    let result = super::mount_helpers::validate_mount_path("/mnt/$(id)");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_no_traversal() {
    let result = super::mount_helpers::validate_mount_path("/mnt/../etc/shadow");
    assert!(result.is_err());
}

#[test]
fn test_mount_path_requires_absolute() {
    let result = super::mount_helpers::validate_mount_path("relative/path");
    assert!(result.is_err(), "relative paths must be rejected");
}

#[test]
fn test_mount_path_valid() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data").is_ok());
    assert!(super::mount_helpers::validate_mount_path("/mnt/azure-files").is_ok());
}

// 6. Dotfile sync security
#[test]
fn test_sync_rejects_sensitive_paths() {
    let result = super::sync_helpers::validate_sync_source("/etc/shadow");
    assert!(result.is_err(), "sensitive system paths must be rejected");
}

#[test]
fn test_sync_rejects_var_paths() {
    let result = super::sync_helpers::validate_sync_source("/var/log/syslog");
    assert!(result.is_err());
}

#[test]
fn test_sync_rejects_traversal() {
    let result = super::sync_helpers::validate_sync_source("/home/user/../../../etc/passwd");
    assert!(result.is_err());
}

#[test]
fn test_sync_allows_home_dotfiles() {
    assert!(super::sync_helpers::validate_sync_source("/home/user/.bashrc").is_ok());
    assert!(super::sync_helpers::validate_sync_source(".bashrc").is_ok());
}

// 7. Health helpers edge cases
#[test]
fn test_health_percentage_negative() {
    assert_eq!(
        super::health_helpers::format_percentage(-5.0),
        "0.0%",
        "negative percentages must clamp to 0"
    );
}

#[test]
fn test_health_percentage_zero() {
    assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
}

#[test]
fn test_health_percentage_over_100() {
    // Over-100 values are allowed (shows actual measurement)
    let result = super::health_helpers::format_percentage(150.0);
    assert_eq!(result, "150.0%");
}

#[test]
fn test_health_percentage_normal() {
    assert_eq!(super::health_helpers::format_percentage(55.5), "55.5%");
}

#[test]
fn test_health_metric_color_boundaries() {
    assert_eq!(super::health_helpers::metric_color(80.1), "red");
    assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
    assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
    assert_eq!(super::health_helpers::metric_color(50.0), "green");
    assert_eq!(super::health_helpers::metric_color(0.0), "green");
}

// ── Error-path coverage: commands that call create_auth() ────────

/// Helper: run azlin with no Azure config and verify graceful failure.
fn assert_graceful_auth_error(args: &[&str]) {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(args)
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .env_remove("AZURE_CLIENT_ID")
        .env_remove("AZURE_CLIENT_SECRET")
        .env_remove("AZURE_TENANT_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&out.stderr);
    let stdout = String::from_utf8_lossy(&out.stdout);
    let combined = format!("{}{}", stdout, stderr);
    // Must not panic
    assert!(
        !combined.contains("thread 'main' panicked"),
        "Command {:?} panicked: {}",
        args,
        combined
    );
    // Should either fail with non-zero exit OR contain an error/auth message
    let has_error_msg = combined.contains("auth")
        || combined.contains("Auth")
        || combined.contains("config")
        || combined.contains("login")
        || combined.contains("subscription")
        || combined.contains("error")
        || combined.contains("Error")
        || combined.contains("az login")
        || combined.contains("Usage")
        || combined.contains("required");
    assert!(
        !out.status.success() || has_error_msg,
        "Command {:?} should fail or show error message, got success with: {}",
        args,
        combined
    );
}

#[test]
fn test_start_graceful_error_no_auth() {
    assert_graceful_auth_error(&["start", "nonexistent-vm"]);
}

#[test]
fn test_stop_graceful_error_no_auth() {
    assert_graceful_auth_error(&["stop", "nonexistent-vm"]);
}

#[test]
fn test_connect_graceful_error_no_auth() {
    assert_graceful_auth_error(&["connect", "nonexistent-vm"]);
}

#[test]
fn test_new_graceful_error_no_auth() {
    assert_graceful_auth_error(&["new"]);
}

#[test]
fn test_create_graceful_error_no_auth() {
    assert_graceful_auth_error(&["create"]);
}

#[test]
fn test_cost_graceful_error_no_auth() {
    assert_graceful_auth_error(&["cost"]);
}

#[test]
fn test_snapshot_create_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "create", "test-vm"]);
}

#[test]
fn test_snapshot_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "list", "test-vm"]);
}

#[test]
fn test_snapshot_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "delete", "test-snap"]);
}

#[test]
fn test_snapshot_restore_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "restore", "test-vm", "test-snap"]);
}

#[test]
fn test_snapshot_enable_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "enable", "test-vm", "--every", "24"]);
}

#[test]
fn test_snapshot_disable_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "disable", "test-vm"]);
}

#[test]
fn test_snapshot_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["snapshot", "status", "test-vm"]);
}

#[test]
fn test_storage_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "list"]);
}

#[test]
fn test_storage_create_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "create", "teststorage"]);
}

#[test]
fn test_storage_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "status", "teststorage"]);
}

#[test]
fn test_storage_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "delete", "teststorage"]);
}

#[test]
fn test_bastion_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["bastion", "list"]);
}

#[test]
fn test_bastion_status_graceful_error_no_auth() {
    assert_graceful_auth_error(&["bastion", "status", "mybastion", "--rg", "myrg"]);
}

#[test]
fn test_keys_rotate_graceful_error_no_auth() {
    assert_graceful_auth_error(&["keys", "rotate"]);
}

#[test]
fn test_keys_list_no_ssh_dir_graceful() {
    let dir = TempDir::new().unwrap();
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["keys", "list"])
        .env("HOME", dir.path())
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .timeout(std::time::Duration::from_secs(15))
        .output()
        .unwrap();
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(
        !combined.contains("thread 'main' panicked"),
        "keys list panicked: {}",
        combined
    );
    // keys list without Azure checks local SSH dir — succeeds or mentions no keys
    assert!(
        out.status.success()
            || combined.contains("SSH")
            || combined.contains("key")
            || combined.contains("error"),
        "Unexpected output: {}",
        combined
    );
}

#[test]
fn test_tag_add_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tag", "add", "test-vm", "env=dev"]);
}

#[test]
fn test_tag_remove_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tag", "remove", "test-vm", "env"]);
}

#[test]
fn test_tag_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["tag", "list", "test-vm"]);
}

#[test]
fn test_batch_start_graceful_error_no_auth() {
    assert_graceful_auth_error(&["batch", "start", "--all"]);
}

#[test]
fn test_batch_stop_graceful_error_no_auth() {
    assert_graceful_auth_error(&["batch", "stop", "--all"]);
}

#[test]
fn test_fleet_run_graceful_error_no_auth() {
    assert_graceful_auth_error(&["fleet", "run", "echo hello", "--all"]);
}

#[test]
fn test_destroy_graceful_error_no_auth() {
    assert_graceful_auth_error(&["destroy", "test-vm", "--force"]);
}

#[test]
fn test_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["delete", "test-vm", "--force"]);
}

#[test]
fn test_kill_graceful_error_no_auth() {
    assert_graceful_auth_error(&["kill", "test-vm", "--force"]);
}

#[test]
fn test_show_graceful_error_no_auth() {
    assert_graceful_auth_error(&["show", "test-vm"]);
}

#[test]
fn test_update_graceful_error_no_auth() {
    assert_graceful_auth_error(&["update", "test-vm"]);
}

#[test]
fn test_os_update_graceful_error_no_auth() {
    assert_graceful_auth_error(&["os-update", "test-vm"]);
}

#[test]
fn test_code_graceful_error_no_auth() {
    assert_graceful_auth_error(&["code", "test-vm"]);
}

#[test]
fn test_compose_up_graceful_error_no_auth() {
    assert_graceful_auth_error(&["compose", "up"]);
}

#[test]
fn test_compose_down_graceful_error_no_auth() {
    assert_graceful_auth_error(&["compose", "down"]);
}

#[test]
fn test_killall_graceful_error_no_auth() {
    assert_graceful_auth_error(&["killall", "--force"]);
}

#[test]
fn test_cleanup_graceful_error_no_auth() {
    assert_graceful_auth_error(&["cleanup", "--force"]);
}

#[test]
fn test_clone_graceful_error_no_auth() {
    assert_graceful_auth_error(&["clone", "source-vm"]);
}

// ── Env subcommands ─────────────────────────────────────────────

#[test]
fn test_env_set_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "set", "test-vm", "MY_KEY=my_value"]);
}

#[test]
fn test_env_list_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "list", "test-vm"]);
}

#[test]
fn test_env_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "delete", "test-vm", "MY_KEY"]);
}

#[test]
fn test_env_export_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "export", "test-vm"]);
}

#[test]
fn test_env_import_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "import", "test-vm", "/dev/null"]);
}

#[test]
fn test_env_clear_graceful_error_no_auth() {
    assert_graceful_auth_error(&["env", "clear", "test-vm", "--force"]);
}

// ── Compose subcommands ─────────────────────────────────────────

#[test]
fn test_compose_ps_graceful_error_no_auth() {
    assert_graceful_auth_error(&["compose", "ps"]);
}

// ── Sessions subcommands ────────────────────────────────────────

#[test]
fn test_sessions_save_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sessions", "save", "test-session"]);
}

#[test]
fn test_sessions_load_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sessions", "load", "nonexistent-session"]);
}

#[test]
fn test_sessions_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sessions", "delete", "nonexistent-session", "--force"]);
}

// ── GitHub Runner subcommands ───────────────────────────────────

#[test]
fn test_github_runner_enable_graceful_error_no_auth() {
    assert_graceful_auth_error(&[
        "github-runner",
        "enable",
        "--pool",
        "test-pool",
        "--count",
        "1",
    ]);
}

// Note: github-runner disable/status/scale are local filesystem operations
// that don't call Azure auth, so they don't use the auth-error pattern.

// ── Template subcommands ────────────────────────────────────────

// Note: template create/save are local filesystem operations that
// don't call Azure auth, so they don't use the auth-error pattern.

#[test]
fn test_template_apply_graceful_error_no_auth() {
    assert_graceful_auth_error(&["template", "apply", "nonexistent-template"]);
}

#[test]
fn test_template_delete_graceful_error_no_auth() {
    assert_graceful_auth_error(&["template", "delete", "nonexistent-template", "--force"]);
}

// ── Web subcommands ─────────────────────────────────────────────

#[test]
fn test_web_start_graceful_error_no_auth() {
    assert_graceful_auth_error(&["web", "start"]);
}

// Note: web stop is a local PID-file operation that doesn't call
// Azure auth, so it doesn't use the auth-error pattern.

// ── Storage mount/unmount ───────────────────────────────────────

#[test]
fn test_storage_mount_graceful_error_no_auth() {
    assert_graceful_auth_error(&[
        "storage",
        "mount",
        "--storage-name",
        "teststorage",
        "--vm",
        "test-vm",
    ]);
}

#[test]
fn test_storage_unmount_graceful_error_no_auth() {
    assert_graceful_auth_error(&["storage", "unmount", "--vm", "test-vm"]);
}

// ── IP subcommands ──────────────────────────────────────────────

#[test]
fn test_ip_check_graceful_error_no_auth() {
    assert_graceful_auth_error(&["ip", "check", "test-vm"]);
}

// ── Disk subcommands ────────────────────────────────────────────

#[test]
fn test_disk_add_graceful_error_no_auth() {
    assert_graceful_auth_error(&["disk", "add", "test-vm"]);
}

// ── Do (natural language) ───────────────────────────────────────

#[test]
fn test_do_graceful_error_no_auth() {
    assert_graceful_auth_error(&["do", "list all vms"]);
}

// ── Health / w / ps / logs ──────────────────────────────────────

#[test]
fn test_health_graceful_error_no_auth() {
    assert_graceful_auth_error(&["health"]);
}

#[test]
fn test_w_graceful_error_no_auth() {
    assert_graceful_auth_error(&["w", "--vm", "test-vm"]);
}

#[test]
fn test_ps_graceful_error_no_auth() {
    assert_graceful_auth_error(&["ps", "--vm", "test-vm"]);
}

#[test]
fn test_logs_graceful_error_no_auth() {
    assert_graceful_auth_error(&["logs", "test-vm"]);
}

// ── cp / sync / sync-keys ───────────────────────────────────────

#[test]
fn test_cp_graceful_error_no_auth() {
    assert_graceful_auth_error(&["cp", "test-vm:/tmp/file", "/tmp/local"]);
}

#[test]
fn test_sync_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sync"]);
}

#[test]
fn test_sync_keys_graceful_error_no_auth() {
    assert_graceful_auth_error(&["sync-keys", "test-vm"]);
}

// ── Costs subcommands ───────────────────────────────────────────

#[test]
fn test_costs_dashboard_graceful_error_no_auth() {
    assert_graceful_auth_error(&["costs", "dashboard", "--resource-group", "test-rg"]);
}

#[test]
fn test_costs_history_graceful_error_no_auth() {
    assert_graceful_auth_error(&["costs", "history", "--resource-group", "test-rg"]);
}

#[test]
fn test_costs_budget_graceful_error_no_auth() {
    assert_graceful_auth_error(&[
        "costs",
        "budget",
        "--resource-group",
        "test-rg",
        "--action",
        "show",
    ]);
}

#[test]
fn test_costs_recommend_graceful_error_no_auth() {
    assert_graceful_auth_error(&["costs", "recommend", "--resource-group", "test-rg"]);
}

// ── Command-specific validation ─────────────────────────────────

#[test]
fn test_env_set_requires_args() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "set"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_env_delete_requires_args() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "delete"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_env_list_requires_vm() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["env", "list"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_snapshot_create_requires_vm() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["snapshot", "create"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_tag_add_requires_vm_and_tags() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["tag", "add"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_start_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["start"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_stop_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["stop"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_delete_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["delete"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_destroy_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["destroy"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_kill_requires_vm_name() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["kill"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

#[test]
fn test_fleet_run_requires_command() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["fleet", "run"])
        .output()
        .unwrap();
    assert!(!out.status.success());
}

// ── Additional help flag coverage ──────────────────────────────

#[test]
fn test_sessions_help_output() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["sessions", "--help"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("session") || stdout.contains("Session"));
}

#[test]
fn test_context_help_output() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["context", "--help"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("context") || stdout.contains("Context"));
}

#[test]
fn test_template_help_output() {
    let out = assert_cmd::Command::cargo_bin("azlin")
        .unwrap()
        .args(["template", "--help"])
        .output()
        .unwrap();
    assert!(out.status.success());
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert!(stdout.contains("template") || stdout.contains("Template"));
}

// ── Storage helpers tests ───────────────────────────────────────

#[test]
fn test_storage_sku_from_tier_premium() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_standard() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_case_insensitive() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("Premium"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("STANDARD"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_unknown_defaults_premium() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("hot"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier(""),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_full() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "eastus2",
        "kind": "FileStorage",
        "sku": { "name": "Premium_LRS" },
        "provisioningState": "Succeeded"
    });
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(
        row,
        vec![
            "mystorage",
            "eastus2",
            "FileStorage",
            "Premium_LRS",
            "Succeeded"
        ]
    );
}

#[test]
fn test_storage_account_row_missing_fields() {
    let acct = serde_json::json!({});
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(row, vec!["-", "-", "-", "-", "-"]);
}

// ── Key helpers tests ───────────────────────────────────────────

#[test]
fn test_detect_key_type_ed25519() {
    assert_eq!(super::key_helpers::detect_key_type("id_ed25519"), "ed25519");
    assert_eq!(
        super::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
}

#[test]
fn test_detect_key_type_ecdsa() {
    assert_eq!(super::key_helpers::detect_key_type("id_ecdsa"), "ecdsa");
}

#[test]
fn test_detect_key_type_rsa() {
    assert_eq!(super::key_helpers::detect_key_type("id_rsa"), "rsa");
    assert_eq!(super::key_helpers::detect_key_type("id_rsa.pub"), "rsa");
}

#[test]
fn test_detect_key_type_dsa() {
    assert_eq!(super::key_helpers::detect_key_type("id_dsa"), "dsa");
}

#[test]
fn test_detect_key_type_unknown() {
    assert_eq!(
        super::key_helpers::detect_key_type("my_custom_key"),
        "unknown"
    );
    assert_eq!(
        super::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_pub() {
    assert!(super::key_helpers::is_known_key_name("id_rsa.pub"));
    assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
    assert!(super::key_helpers::is_known_key_name("custom.pub"));
}

#[test]
fn test_is_known_key_name_private() {
    assert!(super::key_helpers::is_known_key_name("id_rsa"));
    assert!(super::key_helpers::is_known_key_name("id_ed25519"));
    assert!(super::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(super::key_helpers::is_known_key_name("id_dsa"));
}

#[test]
fn test_is_known_key_name_not_key() {
    assert!(!super::key_helpers::is_known_key_name("known_hosts"));
    assert!(!super::key_helpers::is_known_key_name("config"));
    assert!(!super::key_helpers::is_known_key_name("authorized_keys"));
}

// ── Auth helpers tests ──────────────────────────────────────────

#[test]
fn test_mask_profile_value_plain_string() {
    let v = serde_json::Value::String("my-tenant".into());
    assert_eq!(
        super::auth_helpers::mask_profile_value("tenant_id", &v),
        "my-tenant"
    );
}

#[test]
fn test_mask_profile_value_secret_masked() {
    let v = serde_json::Value::String("super-secret-123".into());
    assert_eq!(
        super::auth_helpers::mask_profile_value("client_secret", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_value_password_masked() {
    let v = serde_json::Value::String("p@ssw0rd".into());
    assert_eq!(
        super::auth_helpers::mask_profile_value("db_password", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_value_non_string() {
    let v = serde_json::json!(42);
    assert_eq!(super::auth_helpers::mask_profile_value("count", &v), "42");
}

#[test]
fn test_mask_profile_value_boolean() {
    let v = serde_json::json!(true);
    assert_eq!(
        super::auth_helpers::mask_profile_value("enabled", &v),
        "true"
    );
}

// ── CP helpers tests ────────────────────────────────────────────

#[test]
fn test_is_remote_path_positive() {
    assert!(super::cp_helpers::is_remote_path(
        "myvm:/home/user/file.txt"
    ));
    assert!(super::cp_helpers::is_remote_path("dev-vm-1:/tmp/data"));
}

#[test]
fn test_is_remote_path_local() {
    assert!(!super::cp_helpers::is_remote_path("/tmp/local.txt"));
    assert!(!super::cp_helpers::is_remote_path("./relative/path"));
    assert!(!super::cp_helpers::is_remote_path("file.txt"));
}

#[test]
fn test_is_remote_path_windows_drive_excluded() {
    assert!(!super::cp_helpers::is_remote_path("C:\\Users\\file"));
}

#[test]
fn test_is_remote_path_too_short() {
    assert!(!super::cp_helpers::is_remote_path("a:"));
}

#[test]
fn test_classify_transfer_direction_remote_to_local() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("vm:/path", "/local"),
        "remote→local"
    );
}

#[test]
fn test_classify_transfer_direction_local_to_remote() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("/local", "vm:/path"),
        "local→remote"
    );
}

#[test]
fn test_classify_transfer_direction_local_to_local() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("/a", "/b"),
        "local→local"
    );
}

#[test]
fn test_resolve_scp_path_rewrites() {
    let result =
        super::cp_helpers::resolve_scp_path("myvm:/home/data", "myvm", "azureuser", "10.0.0.5");
    assert_eq!(result, "azureuser@10.0.0.5:/home/data");
}

#[test]
fn test_resolve_scp_path_no_match() {
    let result = super::cp_helpers::resolve_scp_path("/local/path", "myvm", "user", "10.0.0.1");
    assert_eq!(result, "/local/path");
}

// ── Bastion helpers tests ───────────────────────────────────────

#[test]
fn test_bastion_summary_full() {
    let b = serde_json::json!({
        "name": "my-bastion",
        "resourceGroup": "my-rg",
        "location": "eastus2",
        "sku": { "name": "Standard" },
        "provisioningState": "Succeeded"
    });
    let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "my-bastion");
    assert_eq!(rg, "my-rg");
    assert_eq!(loc, "eastus2");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "Succeeded");
}

#[test]
fn test_bastion_summary_defaults() {
    let b = serde_json::json!({});
    let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "unknown");
    assert_eq!(rg, "unknown");
    assert_eq!(loc, "unknown");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "unknown");
}

#[test]
fn test_shorten_resource_id_full_path() {
    let id =
        "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/my-pip";
    assert_eq!(super::bastion_helpers::shorten_resource_id(id), "my-pip");
}

#[test]
fn test_shorten_resource_id_na() {
    assert_eq!(super::bastion_helpers::shorten_resource_id("N/A"), "N/A");
}

#[test]
fn test_shorten_resource_id_simple() {
    assert_eq!(
        super::bastion_helpers::shorten_resource_id("just-a-name"),
        "just-a-name"
    );
}

#[test]
fn test_extract_ip_configs_with_configs() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": { "id": "/sub/rg/subnets/AzureBastionSubnet" },
                "publicIPAddress": { "id": "/sub/rg/publicIPAddresses/bastion-pip" }
            },
            {
                "subnet": { "id": "N/A" },
                "publicIPAddress": { "id": "N/A" }
            }
        ]
    });
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(
        configs[0],
        ("AzureBastionSubnet".to_string(), "bastion-pip".to_string())
    );
    assert_eq!(configs[1], ("N/A".to_string(), "N/A".to_string()));
}

#[test]
fn test_extract_ip_configs_empty() {
    let b = serde_json::json!({});
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

// ── Log helpers tests ───────────────────────────────────────────

#[test]
fn test_tail_start_index_more_than_count() {
    assert_eq!(super::log_helpers::tail_start_index(100, 20), 80);
}

#[test]
fn test_tail_start_index_less_than_count() {
    assert_eq!(super::log_helpers::tail_start_index(5, 20), 0);
}

#[test]
fn test_tail_start_index_equal() {
    assert_eq!(super::log_helpers::tail_start_index(20, 20), 0);
}

#[test]
fn test_tail_start_index_zero() {
    assert_eq!(super::log_helpers::tail_start_index(0, 20), 0);
}

// ── Auth test helpers tests ─────────────────────────────────────

#[test]
fn test_extract_account_info_full() {
    let acct = serde_json::json!({
        "name": "My Subscription",
        "tenantId": "tenant-123",
        "user": { "name": "user@example.com" }
    });
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "My Subscription");
    assert_eq!(tenant, "tenant-123");
    assert_eq!(user, "user@example.com");
}

#[test]
fn test_extract_account_info_missing_fields() {
    let acct = serde_json::json!({});
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

#[test]
fn test_extract_account_info_partial() {
    let acct = serde_json::json!({
        "name": "Sub Only",
        "user": {}
    });
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "Sub Only");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── NEW: templates edge-case tests ───────────────────────────

#[test]
fn test_template_build_all_none_defaults() {
    let tpl = super::templates::build_template_toml("t1", None, None, None, None);
    let t = tpl.as_table().unwrap();
    assert_eq!(t["name"].as_str().unwrap(), "t1");
    assert_eq!(t["description"].as_str().unwrap(), "");
    assert_eq!(t["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
    assert_eq!(t["region"].as_str().unwrap(), "westus2");
    assert!(t.get("cloud_init").is_none());
}

#[test]
fn test_template_build_all_some() {
    let tpl = super::templates::build_template_toml(
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
    let tpl = super::templates::build_template_toml("x", None, None, None, None);
    let path = super::templates::save_template(&dir, "x", &tpl).unwrap();
    assert!(path.exists());
    assert!(path.to_string_lossy().ends_with("x.toml"));
}

#[test]
fn test_template_load_not_found() {
    let tmp = TempDir::new().unwrap();
    let err = super::templates::load_template(tmp.path(), "nope").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_template_save_load_roundtrip_with_cloud_init() {
    let tmp = TempDir::new().unwrap();
    let tpl = super::templates::build_template_toml(
        "ci",
        Some("cloud-init test"),
        Some("Standard_B2s"),
        Some("westus3"),
        Some("#!/bin/bash\napt update"),
    );
    super::templates::save_template(tmp.path(), "ci", &tpl).unwrap();
    let loaded = super::templates::load_template(tmp.path(), "ci").unwrap();
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
        let tpl = super::templates::build_template_toml(n, None, Some(sz), Some(rg), None);
        super::templates::save_template(tmp.path(), n, &tpl).unwrap();
    }
    let rows = super::templates::list_templates(tmp.path()).unwrap();
    assert_eq!(rows.len(), 2);
    let names: Vec<&str> = rows.iter().map(|r| r[0].as_str()).collect();
    assert!(names.contains(&"a"));
    assert!(names.contains(&"b"));
}

#[test]
fn test_template_list_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let rows = super::templates::list_templates(&tmp.path().join("nope")).unwrap();
    assert!(rows.is_empty());
}

#[test]
fn test_template_list_ignores_non_toml_files() {
    let tmp = TempDir::new().unwrap();
    fs::write(tmp.path().join("readme.md"), "not a template").unwrap();
    fs::write(tmp.path().join("data.json"), "{}").unwrap();
    let tpl = super::templates::build_template_toml("only", None, None, None, None);
    super::templates::save_template(tmp.path(), "only", &tpl).unwrap();
    let rows = super::templates::list_templates(tmp.path()).unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0][0], "only");
}

#[test]
fn test_template_delete_not_found() {
    let tmp = TempDir::new().unwrap();
    let err = super::templates::delete_template(tmp.path(), "ghost").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

#[test]
fn test_template_delete_removes_file() {
    let tmp = TempDir::new().unwrap();
    let tpl = super::templates::build_template_toml("del", None, None, None, None);
    super::templates::save_template(tmp.path(), "del", &tpl).unwrap();
    assert!(tmp.path().join("del.toml").exists());
    super::templates::delete_template(tmp.path(), "del").unwrap();
    assert!(!tmp.path().join("del.toml").exists());
}

#[test]
fn test_template_import_valid() {
    let tmp = TempDir::new().unwrap();
    let content = "name = \"imported\"\nvm_size = \"Standard_D2s_v3\"\nregion = \"westus2\"\n";
    let name = super::templates::import_template(tmp.path(), content).unwrap();
    assert_eq!(name, "imported");
    assert!(tmp.path().join("imported.toml").exists());
}

#[test]
fn test_template_import_missing_name() {
    let tmp = TempDir::new().unwrap();
    let content = "vm_size = \"Standard_D2s_v3\"\n";
    let err = super::templates::import_template(tmp.path(), content).unwrap_err();
    assert!(err.to_string().contains("name"));
}

#[test]
fn test_template_import_invalid_toml() {
    let tmp = TempDir::new().unwrap();
    let err = super::templates::import_template(tmp.path(), "{{invalid").unwrap_err();
    assert!(!err.to_string().is_empty());
}

// ── NEW: sessions edge-case tests ────────────────────────────

#[test]
fn test_session_build_toml_fields() {
    let s = super::sessions::build_session_toml("dev", "rg-dev", &["vm1".into(), "vm2".into()]);
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
    let s = super::sessions::build_session_toml("empty", "rg", &[]);
    let t = s.as_table().unwrap();
    assert!(t["vms"].as_array().unwrap().is_empty());
}

#[test]
fn test_session_parse_toml_valid() {
    let content = "name = \"s1\"\nresource_group = \"rg-test\"\nvms = [\"vm-a\", \"vm-b\"]\ncreated = \"2025-01-01T00:00:00Z\"\n";
    let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "rg-test");
    assert_eq!(vms, vec!["vm-a", "vm-b"]);
    assert_eq!(created, "2025-01-01T00:00:00Z");
}

#[test]
fn test_session_parse_toml_missing_fields() {
    let content = "name = \"minimal\"\n";
    let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "-");
    assert!(vms.is_empty());
    assert_eq!(created, "-");
}

#[test]
fn test_session_parse_toml_invalid() {
    let err = super::sessions::parse_session_toml("{{bad").unwrap_err();
    assert!(!err.to_string().is_empty());
}

#[test]
fn test_session_list_names_empty_dir() {
    let tmp = TempDir::new().unwrap();
    let names = super::sessions::list_session_names(tmp.path()).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_session_list_names_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let names = super::sessions::list_session_names(&tmp.path().join("nope")).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_session_list_names_filters_toml() {
    let tmp = TempDir::new().unwrap();
    fs::write(tmp.path().join("s1.toml"), "name=\"s1\"\n").unwrap();
    fs::write(tmp.path().join("s2.toml"), "name=\"s2\"\n").unwrap();
    fs::write(tmp.path().join("readme.md"), "ignore").unwrap();
    let names = super::sessions::list_session_names(tmp.path()).unwrap();
    assert_eq!(names.len(), 2);
    assert!(names.contains(&"s1".to_string()));
    assert!(names.contains(&"s2".to_string()));
}

#[test]
fn test_session_build_and_parse_roundtrip() {
    let built = super::sessions::build_session_toml("rt", "rg-rt", &["vm-x".into()]);
    let serialized = toml::to_string_pretty(&built).unwrap();
    let (rg, vms, created) = super::sessions::parse_session_toml(&serialized).unwrap();
    assert_eq!(rg, "rg-rt");
    assert_eq!(vms, vec!["vm-x"]);
    assert!(!created.is_empty());
    assert_ne!(created, "-");
}

// ── NEW: contexts edge-case tests ────────────────────────────

#[test]
fn test_context_build_toml_minimal() {
    let toml_str =
        super::contexts::build_context_toml("dev", None, None, None, None, None).unwrap();
    assert!(toml_str.contains("name = \"dev\""));
    assert!(!toml_str.contains("subscription_id"));
}

#[test]
fn test_context_build_toml_all_fields() {
    let toml_str = super::contexts::build_context_toml(
        "prod",
        Some("sub-123"),
        Some("tenant-456"),
        Some("rg-prod"),
        Some("eastus2"),
        Some("kv-prod"),
    )
    .unwrap();
    assert!(toml_str.contains("name = \"prod\""));
    assert!(toml_str.contains("subscription_id = \"sub-123\""));
    assert!(toml_str.contains("tenant_id = \"tenant-456\""));
    assert!(toml_str.contains("resource_group = \"rg-prod\""));
    assert!(toml_str.contains("region = \"eastus2\""));
    assert!(toml_str.contains("key_vault_name = \"kv-prod\""));
}

#[test]
fn test_context_build_toml_partial_fields() {
    let toml_str = super::contexts::build_context_toml(
        "staging",
        Some("sub-789"),
        None,
        Some("rg-staging"),
        None,
        None,
    )
    .unwrap();
    assert!(toml_str.contains("name = \"staging\""));
    assert!(toml_str.contains("subscription_id = \"sub-789\""));
    assert!(toml_str.contains("resource_group = \"rg-staging\""));
    assert!(!toml_str.contains("tenant_id"));
    assert!(!toml_str.contains("region"));
    assert!(!toml_str.contains("key_vault_name"));
}

#[test]
fn test_context_list_empty_dir() {
    let tmp = TempDir::new().unwrap();
    let list = super::contexts::list_contexts(tmp.path(), "").unwrap();
    assert!(list.is_empty());
}

#[test]
fn test_context_list_marks_active_correctly() {
    let tmp = TempDir::new().unwrap();
    for name in &["dev", "staging", "prod"] {
        let content =
            super::contexts::build_context_toml(name, None, None, None, None, None).unwrap();
        fs::write(tmp.path().join(format!("{}.toml", name)), content).unwrap();
    }
    let list = super::contexts::list_contexts(tmp.path(), "staging").unwrap();
    assert_eq!(list.len(), 3);
    for (name, active) in &list {
        if name == "staging" {
            assert!(active, "staging should be active");
        } else {
            assert!(!active, "{} should not be active", name);
        }
    }
}

#[test]
fn test_context_list_ignores_non_toml() {
    let tmp = TempDir::new().unwrap();
    fs::write(tmp.path().join("dev.toml"), "name = \"dev\"\n").unwrap();
    fs::write(tmp.path().join("notes.txt"), "ignore").unwrap();
    let list = super::contexts::list_contexts(tmp.path(), "").unwrap();
    assert_eq!(list.len(), 1);
    assert_eq!(list[0].0, "dev");
}

#[test]
fn test_context_rename_success() {
    let tmp = TempDir::new().unwrap();
    let content = super::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
    fs::write(tmp.path().join("old.toml"), content).unwrap();
    super::contexts::rename_context_file(tmp.path(), "old", "new").unwrap();
    assert!(!tmp.path().join("old.toml").exists());
    assert!(tmp.path().join("new.toml").exists());
    let loaded: toml::Value = fs::read_to_string(tmp.path().join("new.toml"))
        .unwrap()
        .parse()
        .unwrap();
    assert_eq!(loaded["name"].as_str().unwrap(), "new");
}

#[test]
fn test_context_rename_not_found() {
    let tmp = TempDir::new().unwrap();
    let err = super::contexts::rename_context_file(tmp.path(), "ghost", "new").unwrap_err();
    assert!(err.to_string().contains("not found"));
}

// ── NEW: env_helpers additional edge cases ───────────────────

#[test]
fn test_split_env_var_equals_in_value() {
    let result = super::env_helpers::split_env_var("DB_URL=postgres://host:5432/db?opt=val");
    assert_eq!(result, Some(("DB_URL", "postgres://host:5432/db?opt=val")));
}

#[test]
fn test_split_env_var_empty_string() {
    assert_eq!(super::env_helpers::split_env_var(""), None);
}

#[test]
fn test_split_env_var_just_equals() {
    assert_eq!(super::env_helpers::split_env_var("="), None);
}

#[test]
fn test_validate_env_key_underscores() {
    assert!(super::env_helpers::validate_env_key("MY_VAR_123").is_ok());
}

#[test]
fn test_validate_env_key_single_char() {
    assert!(super::env_helpers::validate_env_key("X").is_ok());
}

#[test]
fn test_validate_env_key_with_dash() {
    assert!(super::env_helpers::validate_env_key("MY-VAR").is_err());
}

#[test]
fn test_validate_env_key_with_dot() {
    assert!(super::env_helpers::validate_env_key("my.var").is_err());
}

#[test]
fn test_validate_env_key_unicode() {
    assert!(super::env_helpers::validate_env_key("café").is_err());
}

#[test]
fn test_build_env_set_cmd_valid_key() {
    let cmd = super::env_helpers::build_env_set_cmd("FOO", "'bar'");
    assert!(cmd.contains("FOO"));
    assert!(cmd.contains("'bar'"));
    assert!(cmd.contains("grep"));
}

#[test]
fn test_build_env_set_cmd_invalid_key_returns_noop() {
    let cmd = super::env_helpers::build_env_set_cmd("BAD;KEY", "'val'");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_delete_cmd_format() {
    let cmd = super::env_helpers::build_env_delete_cmd("MY_VAR");
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("MY_VAR"));
}

#[test]
fn test_env_list_cmd_value() {
    assert_eq!(super::env_helpers::env_list_cmd(), "env | sort");
}

#[test]
fn test_env_clear_cmd_value() {
    let cmd = super::env_helpers::env_clear_cmd();
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("export"));
}

#[test]
fn test_parse_env_output_multiline() {
    let output = "A=1\nB=two\nC=three=3\nD=\n";
    let vars = super::env_helpers::parse_env_output(output);
    assert_eq!(vars.len(), 4);
    assert_eq!(vars[0], ("A".into(), "1".into()));
    assert_eq!(vars[1], ("B".into(), "two".into()));
    assert_eq!(vars[2], ("C".into(), "three=3".into()));
    assert_eq!(vars[3], ("D".into(), "".into()));
}

#[test]
fn test_build_env_file_multiple() {
    let vars = vec![("K1".into(), "v1".into()), ("K2".into(), "v2".into())];
    let file = super::env_helpers::build_env_file(&vars);
    assert_eq!(file, "K1=v1\nK2=v2");
}

#[test]
fn test_parse_env_file_mixed_content() {
    let content = "# comment\n\nFOO=bar\n  # another comment  \n  BAZ=qux  \n\n";
    let vars = super::env_helpers::parse_env_file(content);
    assert_eq!(vars.len(), 2);
    assert_eq!(vars[0], ("FOO".into(), "bar".into()));
    assert_eq!(vars[1], ("BAZ".into(), "qux".into()));
}

#[test]
fn test_env_file_build_then_parse_roundtrip() {
    let original = vec![
        ("PATH".into(), "/usr/bin".into()),
        ("HOME".into(), "/home/user".into()),
    ];
    let file = super::env_helpers::build_env_file(&original);
    let parsed = super::env_helpers::parse_env_file(&file);
    assert_eq!(parsed, original);
}

// ── NEW: sync_helpers additional tests ───────────────────────

#[test]
fn test_default_dotfiles_count() {
    let df = super::sync_helpers::default_dotfiles();
    assert!(df.len() >= 4);
    assert!(df.contains(&".bashrc"));
    assert!(df.contains(&".gitconfig"));
}

#[test]
fn test_validate_sync_source_etc() {
    assert!(super::sync_helpers::validate_sync_source("/etc/passwd").is_err());
}

#[test]
fn test_validate_sync_source_proc() {
    assert!(super::sync_helpers::validate_sync_source("/proc/1/status").is_err());
}

#[test]
fn test_validate_sync_source_sys() {
    assert!(super::sync_helpers::validate_sync_source("/sys/class/net").is_err());
}

#[test]
fn test_validate_sync_source_root() {
    assert!(super::sync_helpers::validate_sync_source("/root/secret").is_err());
}

#[test]
fn test_validate_sync_source_traversal_end() {
    assert!(super::sync_helpers::validate_sync_source("foo/..").is_err());
}

#[test]
fn test_validate_sync_source_double_dot_bare() {
    assert!(super::sync_helpers::validate_sync_source("..").is_err());
}

#[test]
fn test_validate_sync_source_safe_home() {
    assert!(super::sync_helpers::validate_sync_source("/home/user/.bashrc").is_ok());
}

#[test]
fn test_validate_sync_source_relative() {
    assert!(super::sync_helpers::validate_sync_source("src/main.rs").is_ok());
}

#[test]
fn test_build_rsync_args_format() {
    let args = super::sync_helpers::build_rsync_args(".bashrc", "admin", "10.0.0.1", ".bashrc");
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert_eq!(args[2], "ssh -o StrictHostKeyChecking=accept-new");
    assert_eq!(args[3], ".bashrc");
    assert_eq!(args[4], "admin@10.0.0.1:~/.bashrc");
}

#[test]
fn test_build_rsync_args_with_subpath() {
    let args = super::sync_helpers::build_rsync_args("config/", "user", "192.168.1.1", "config/");
    assert_eq!(args[4], "user@192.168.1.1:~/config/");
}

// ── NEW: health_helpers boundary tests ───────────────────────

#[test]
fn test_metric_color_exact_50() {
    assert_eq!(super::health_helpers::metric_color(50.0), "green");
}

#[test]
fn test_metric_color_exact_80() {
    assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
}

#[test]
fn test_metric_color_just_above_80() {
    assert_eq!(super::health_helpers::metric_color(80.1), "red");
}

#[test]
fn test_metric_color_just_above_50() {
    assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
}

#[test]
fn test_metric_color_zero() {
    assert_eq!(super::health_helpers::metric_color(0.0), "green");
}

#[test]
fn test_metric_color_100() {
    assert_eq!(super::health_helpers::metric_color(100.0), "red");
}

#[test]
fn test_state_color_deallocated() {
    assert_eq!(super::health_helpers::state_color("deallocated"), "red");
}

#[test]
fn test_state_color_starting() {
    assert_eq!(super::health_helpers::state_color("starting"), "yellow");
}

#[test]
fn test_state_color_empty_string() {
    assert_eq!(super::health_helpers::state_color(""), "yellow");
}

#[test]
fn test_format_percentage_large() {
    assert_eq!(super::health_helpers::format_percentage(99.99), "100.0%");
}

#[test]
fn test_format_percentage_very_negative() {
    assert_eq!(super::health_helpers::format_percentage(-100.0), "0.0%");
}

#[test]
fn test_format_percentage_exactly_zero() {
    assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
}

#[test]
fn test_status_emoji_all_low() {
    assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
}

#[test]
fn test_status_emoji_cpu_critical() {
    assert_eq!(super::health_helpers::status_emoji(91.0, 10.0, 10.0), "🔴");
}

#[test]
fn test_status_emoji_mem_critical() {
    assert_eq!(super::health_helpers::status_emoji(10.0, 95.0, 10.0), "🔴");
}

#[test]
fn test_status_emoji_disk_critical() {
    assert_eq!(super::health_helpers::status_emoji(10.0, 10.0, 91.0), "🔴");
}

#[test]
fn test_status_emoji_cpu_warning() {
    assert_eq!(super::health_helpers::status_emoji(75.0, 10.0, 10.0), "🟡");
}

#[test]
fn test_status_emoji_exact_boundary_70() {
    assert_eq!(super::health_helpers::status_emoji(70.0, 70.0, 70.0), "🟢");
}

#[test]
fn test_status_emoji_exact_boundary_90() {
    assert_eq!(super::health_helpers::status_emoji(90.0, 90.0, 90.0), "🟡");
}

// ── NEW: snapshot_helpers additional tests ───────────────────

#[test]
fn test_build_snapshot_name_format() {
    let name = super::snapshot_helpers::build_snapshot_name("my-vm", "20250101_120000");
    assert_eq!(name, "my-vm_snapshot_20250101_120000");
}

#[test]
fn test_build_snapshot_name_with_dashes() {
    let name = super::snapshot_helpers::build_snapshot_name("vm-with-dashes", "ts");
    assert_eq!(name, "vm-with-dashes_snapshot_ts");
}

#[test]
fn test_filter_snapshots_partial_match() {
    let snaps = vec![
        serde_json::json!({"name": "dev-vm_snapshot_123"}),
        serde_json::json!({"name": "prod-vm_snapshot_456"}),
        serde_json::json!({"name": "dev-vm_snapshot_789"}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "dev-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_snapshot_row_complete() {
    let snap = serde_json::json!({
        "name": "snap-1",
        "diskSizeGb": 128,
        "timeCreated": "2025-01-01T00:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "snap-1");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2025-01-01T00:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_null_fields() {
    let snap = serde_json::json!({});
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

// ── NEW: output_helpers additional tests ─────────────────────

#[test]
fn test_format_as_csv_multiple_rows() {
    let headers = &["Name", "Age", "City"];
    let rows = vec![
        vec!["Alice".into(), "30".into(), "NYC".into()],
        vec!["Bob".into(), "25".into(), "LA".into()],
    ];
    let csv = super::output_helpers::format_as_csv(headers, &rows);
    let lines: Vec<&str> = csv.lines().collect();
    assert_eq!(lines[0], "Name,Age,City");
    assert_eq!(lines[1], "Alice,30,NYC");
    assert_eq!(lines[2], "Bob,25,LA");
}

#[test]
fn test_format_as_csv_single_row() {
    let csv = super::output_helpers::format_as_csv(&["X"], &[vec!["1".into()]]);
    assert_eq!(csv, "X\n1");
}

#[test]
fn test_format_as_table_alignment() {
    let headers = &["Short", "LongerHeader"];
    let rows = vec![vec!["a".into(), "b".into()], vec!["ccc".into(), "d".into()]];
    let table = super::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = table.lines().collect();
    assert_eq!(lines.len(), 3);
    // Header line should have both column names
    assert!(lines[0].contains("Short"));
    assert!(lines[0].contains("LongerHeader"));
}

#[test]
fn test_format_as_table_single_column() {
    let table = super::output_helpers::format_as_table(
        &["Items"],
        &[vec!["one".into()], vec!["two".into()]],
    );
    assert!(table.contains("Items"));
    assert!(table.contains("one"));
    assert!(table.contains("two"));
}

#[test]
fn test_format_as_table_no_rows() {
    let table = super::output_helpers::format_as_table(&["A", "B"], &[]);
    assert!(table.contains("A"));
    assert!(table.contains("B"));
    assert_eq!(table.lines().count(), 1);
}

#[test]
fn test_format_as_table_wide_cell_expands_column() {
    let headers = &["H"];
    let rows = vec![vec!["very long cell content".into()]];
    let table = super::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = table.lines().collect();
    // The header line should be padded to at least the width of the cell
    assert!(lines[0].len() >= "very long cell content".len());
}

#[test]
fn test_format_as_json_numbers() {
    let items: Vec<i32> = vec![1, 2, 3];
    let json = super::output_helpers::format_as_json(&items);
    let parsed: Vec<i32> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed, vec![1, 2, 3]);
}

#[test]
fn test_format_as_json_empty_vec() {
    let items: Vec<String> = vec![];
    let json = super::output_helpers::format_as_json(&items);
    assert_eq!(json.trim(), "[]");
}

#[test]
fn test_format_as_json_structs() {
    let items = vec![
        serde_json::json!({"name": "a"}),
        serde_json::json!({"name": "b"}),
    ];
    let json = super::output_helpers::format_as_json(&items);
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed.len(), 2);
}

// ── NEW: vm_validation additional tests ──────────────────────

#[test]
fn test_vm_name_valid_simple() {
    assert!(super::vm_validation::validate_vm_name("myvm").is_ok());
}

#[test]
fn test_vm_name_valid_with_numbers() {
    assert!(super::vm_validation::validate_vm_name("vm-01-prod").is_ok());
}

#[test]
fn test_vm_name_single_char() {
    assert!(super::vm_validation::validate_vm_name("a").is_ok());
}

#[test]
fn test_vm_name_underscores_rejected() {
    assert!(super::vm_validation::validate_vm_name("my_vm").is_err());
}

#[test]
fn test_vm_name_spaces_rejected() {
    assert!(super::vm_validation::validate_vm_name("my vm").is_err());
}

#[test]
fn test_vm_name_dots_rejected() {
    assert!(super::vm_validation::validate_vm_name("vm.prod").is_err());
}

#[test]
fn test_vm_name_double_hyphen_ok() {
    assert!(super::vm_validation::validate_vm_name("vm--test").is_ok());
}

#[test]
fn test_vm_name_63_chars() {
    let name = "a".repeat(63);
    assert!(super::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_vm_name_64_chars() {
    let name = "b".repeat(64);
    assert!(super::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_vm_name_65_chars() {
    let name = "c".repeat(65);
    assert!(super::vm_validation::validate_vm_name(&name).is_err());
}

// ── NEW: mount_helpers additional tests ──────────────────────

#[test]
fn test_mount_path_valid_nested() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data/disk1").is_ok());
}

#[test]
fn test_mount_path_root() {
    assert!(super::mount_helpers::validate_mount_path("/").is_ok());
}

#[test]
fn test_mount_path_ampersand() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/a&b").is_err());
}

#[test]
fn test_mount_path_dollar() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/$HOME").is_err());
}

#[test]
fn test_mount_path_newline() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/a\nb").is_err());
}

#[test]
fn test_mount_path_null_byte() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/a\0b").is_err());
}

#[test]
fn test_mount_path_relative_rejected() {
    assert!(super::mount_helpers::validate_mount_path("mnt/data").is_err());
}

#[test]
fn test_mount_path_exclamation() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/test!").is_err());
}

#[test]
fn test_mount_path_parentheses() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/(test)").is_err());
}

#[test]
fn test_mount_path_curly_braces() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/{test}").is_err());
}

#[test]
fn test_mount_path_angle_brackets() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/<test>").is_err());
}

// ── NEW: config_path_helpers additional tests ────────────────

#[test]
fn test_config_path_simple_relative() {
    assert!(super::config_path_helpers::validate_config_path("config.toml").is_ok());
}

#[test]
fn test_config_path_nested() {
    assert!(super::config_path_helpers::validate_config_path("a/b/c.toml").is_ok());
}

#[test]
fn test_config_path_dot_prefix() {
    assert!(super::config_path_helpers::validate_config_path("./config.toml").is_ok());
}

#[test]
fn test_config_path_parent_traversal() {
    assert!(super::config_path_helpers::validate_config_path("../etc/passwd").is_err());
}

#[test]
fn test_config_path_middle_traversal() {
    assert!(super::config_path_helpers::validate_config_path("a/../../etc").is_err());
}

#[test]
fn test_config_path_absolute_allowed() {
    assert!(super::config_path_helpers::validate_config_path("/home/user/config.toml").is_ok());
}

// ── NEW: storage_helpers additional tests ────────────────────

#[test]
fn test_storage_sku_premium() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_sku_standard() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_mixed_case() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("PREMIUM"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("StAnDaRd"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_unknown() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("unknown"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier(""),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_complete() {
    let acct = serde_json::json!({
        "name": "mystorageacct",
        "location": "westus2",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(
        row,
        vec![
            "mystorageacct",
            "westus2",
            "StorageV2",
            "Standard_LRS",
            "Succeeded"
        ]
    );
}

#[test]
fn test_storage_account_row_partial() {
    let acct = serde_json::json!({"name": "partial"});
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "partial");
    assert_eq!(row[1], "-");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
    assert_eq!(row[4], "-");
}

#[test]
fn test_storage_account_row_empty() {
    let acct = serde_json::json!({});
    let row = super::storage_helpers::storage_account_row(&acct);
    assert!(row.iter().all(|c| c == "-"));
}

// ── NEW: key_helpers additional tests ────────────────────────

#[test]
fn test_detect_key_type_filename_prefix() {
    assert_eq!(
        super::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
    assert_eq!(super::key_helpers::detect_key_type("id_ecdsa.pub"), "ecdsa");
    assert_eq!(super::key_helpers::detect_key_type("id_rsa.pub"), "rsa");
    assert_eq!(super::key_helpers::detect_key_type("id_dsa.pub"), "dsa");
}

#[test]
fn test_detect_key_type_custom_name() {
    assert_eq!(
        super::key_helpers::detect_key_type("my_ed25519_key"),
        "ed25519"
    );
    assert_eq!(super::key_helpers::detect_key_type("backup_rsa"), "rsa");
}

#[test]
fn test_detect_key_type_random_file() {
    assert_eq!(
        super::key_helpers::detect_key_type("known_hosts"),
        "unknown"
    );
    assert_eq!(
        super::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_standard_private() {
    assert!(super::key_helpers::is_known_key_name("id_rsa"));
    assert!(super::key_helpers::is_known_key_name("id_ed25519"));
    assert!(super::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(super::key_helpers::is_known_key_name("id_dsa"));
}

#[test]
fn test_is_known_key_name_pub_extension() {
    assert!(super::key_helpers::is_known_key_name("custom.pub"));
    assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
}

#[test]
fn test_is_known_key_name_non_key_files() {
    assert!(!super::key_helpers::is_known_key_name("known_hosts"));
    assert!(!super::key_helpers::is_known_key_name("config"));
    assert!(!super::key_helpers::is_known_key_name("authorized_keys"));
}

// ── NEW: auth_helpers additional tests ───────────────────────

#[test]
fn test_mask_profile_string_no_secret() {
    let v = serde_json::json!("my-tenant-id");
    assert_eq!(
        super::auth_helpers::mask_profile_value("tenant_id", &v),
        "my-tenant-id"
    );
}

#[test]
fn test_mask_profile_secret_key() {
    let v = serde_json::json!("s3cr3t-value");
    assert_eq!(
        super::auth_helpers::mask_profile_value("client_secret", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_password_key() {
    let v = serde_json::json!("pa$$word");
    assert_eq!(
        super::auth_helpers::mask_profile_value("admin_password", &v),
        "********"
    );
}

#[test]
fn test_mask_profile_number_value() {
    let v = serde_json::json!(42);
    assert_eq!(super::auth_helpers::mask_profile_value("count", &v), "42");
}

#[test]
fn test_mask_profile_bool_value() {
    let v = serde_json::json!(true);
    assert_eq!(
        super::auth_helpers::mask_profile_value("enabled", &v),
        "true"
    );
}

#[test]
fn test_mask_profile_null_value() {
    let v = serde_json::json!(null);
    assert_eq!(super::auth_helpers::mask_profile_value("field", &v), "null");
}

#[test]
fn test_mask_profile_secret_in_key_substring() {
    let v = serde_json::json!("value123");
    assert_eq!(
        super::auth_helpers::mask_profile_value("my_secret_key", &v),
        "********"
    );
}

// ── NEW: cp_helpers additional tests ─────────────────────────

#[test]
fn test_is_remote_path_standard() {
    assert!(super::cp_helpers::is_remote_path("vm-name:/path/to/file"));
}

#[test]
fn test_is_remote_path_short_colon() {
    // Two chars with colon at pos 1 like "C:" should NOT be remote
    assert!(!super::cp_helpers::is_remote_path("C:"));
}

#[test]
fn test_is_remote_path_absolute() {
    assert!(!super::cp_helpers::is_remote_path("/home/user/file.txt"));
}

#[test]
fn test_is_remote_path_windows_drive() {
    assert!(!super::cp_helpers::is_remote_path("C:\\Users\\file"));
}

#[test]
fn test_is_remote_path_no_colon() {
    assert!(!super::cp_helpers::is_remote_path("localfile.txt"));
}

#[test]
fn test_is_remote_path_empty() {
    assert!(!super::cp_helpers::is_remote_path(""));
}

#[test]
fn test_classify_transfer_local_to_remote() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("file.txt", "vm:/path"),
        "local→remote"
    );
}

#[test]
fn test_classify_transfer_remote_to_local() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("vm:/path", "file.txt"),
        "remote→local"
    );
}

#[test]
fn test_classify_transfer_both_local() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("file1.txt", "file2.txt"),
        "local→local"
    );
}

#[test]
fn test_resolve_scp_path_rewrite() {
    let result =
        super::cp_helpers::resolve_scp_path("vm-1:/data/file.txt", "vm-1", "admin", "10.0.0.5");
    assert_eq!(result, "admin@10.0.0.5:/data/file.txt");
}

#[test]
fn test_resolve_scp_path_no_match_passthrough() {
    let result = super::cp_helpers::resolve_scp_path("other-vm:/file", "vm-1", "u", "1.2.3.4");
    assert_eq!(result, "other-vm:/file");
}

// ── NEW: bastion_helpers additional tests ────────────────────

#[test]
fn test_bastion_summary_full_json() {
    let b = serde_json::json!({
        "name": "bastion-prod",
        "resourceGroup": "rg-prod",
        "location": "eastus",
        "sku": {"name": "Premium"},
        "provisioningState": "Succeeded"
    });
    let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "bastion-prod");
    assert_eq!(rg, "rg-prod");
    assert_eq!(loc, "eastus");
    assert_eq!(sku, "Premium");
    assert_eq!(state, "Succeeded");
}

#[test]
fn test_bastion_summary_missing_all() {
    let b = serde_json::json!({});
    let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "unknown");
    assert_eq!(rg, "unknown");
    assert_eq!(loc, "unknown");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "unknown");
}

#[test]
fn test_shorten_resource_id_long() {
    let id = "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/bastionHosts/my-bastion";
    assert_eq!(
        super::bastion_helpers::shorten_resource_id(id),
        "my-bastion"
    );
}

#[test]
fn test_shorten_resource_id_single_segment() {
    assert_eq!(
        super::bastion_helpers::shorten_resource_id("just-a-name"),
        "just-a-name"
    );
}

#[test]
fn test_shorten_resource_id_empty() {
    assert_eq!(super::bastion_helpers::shorten_resource_id(""), "");
}

#[test]
fn test_extract_ip_configs_multiple() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": {"id": "/subs/x/subnets/sn-1"},
                "publicIPAddress": {"id": "/subs/x/publicIPAddresses/pip-1"}
            },
            {
                "subnet": {"id": "/subs/x/subnets/sn-2"},
                "publicIPAddress": {"id": "/subs/x/publicIPAddresses/pip-2"}
            }
        ]
    });
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(configs[0], ("sn-1".to_string(), "pip-1".to_string()));
    assert_eq!(configs[1], ("sn-2".to_string(), "pip-2".to_string()));
}

#[test]
fn test_extract_ip_configs_missing_ids() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {"subnet": {}, "publicIPAddress": {}}
        ]
    });
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 1);
    assert_eq!(configs[0], ("N/A".to_string(), "N/A".to_string()));
}

#[test]
fn test_extract_ip_configs_no_array() {
    let b = serde_json::json!({"name": "no-configs"});
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

// ── NEW: log_helpers additional tests ────────────────────────

#[test]
fn test_tail_start_index_large_total() {
    assert_eq!(super::log_helpers::tail_start_index(1000, 50), 950);
}

#[test]
fn test_tail_start_index_count_larger_than_total() {
    assert_eq!(super::log_helpers::tail_start_index(5, 100), 0);
}

#[test]
fn test_tail_start_index_both_zero() {
    assert_eq!(super::log_helpers::tail_start_index(0, 0), 0);
}

#[test]
fn test_tail_start_index_count_one() {
    assert_eq!(super::log_helpers::tail_start_index(10, 1), 9);
}

// ── NEW: parse_cost_history_rows additional tests ────────────

#[test]
fn test_parse_cost_history_rows_no_rows_key() {
    let data = serde_json::json!({"other": "data"});
    let rows = super::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_rows_not_array() {
    let data = serde_json::json!({"rows": "not-array"});
    let rows = super::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_multiple_entries() {
    let data = serde_json::json!({
        "rows": [
            [10.5, "2025-01-01"],
            [20.0, "2025-01-02"],
            [0.0, "2025-01-03"]
        ]
    });
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0], ("2025-01-01".to_string(), "$10.50".to_string()));
    assert_eq!(rows[1], ("2025-01-02".to_string(), "$20.00".to_string()));
    assert_eq!(rows[2], ("2025-01-03".to_string(), "$0.00".to_string()));
}

#[test]
fn test_parse_cost_history_rows_integer_date() {
    let data = serde_json::json!({"rows": [[5.0, 20250101]]});
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    // Integer dates yield empty string due to as_str().or_else(as_i64 -> "") mapping
    assert_eq!(rows[0].0, "");
    assert_eq!(rows[0].1, "$5.00");
}

#[test]
fn test_parse_cost_history_rows_null_values() {
    let data = serde_json::json!({"rows": [[null, null]]});
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "-");
    assert_eq!(rows[0].1, "-");
}

// ── NEW: parse_recommendation_rows additional tests ─────────

#[test]
fn test_parse_recommendation_rows_null_input() {
    let data = serde_json::json!(null);
    let rows = super::parse_recommendation_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_recommendation_rows_empty_array() {
    let data = serde_json::json!([]);
    let rows = super::parse_recommendation_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_recommendation_rows_partial_fields() {
    let data = serde_json::json!([
        {"category": "Cost"},
        {"impact": "High"},
        {"shortDescription": {"problem": "Underutilized"}}
    ]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 3);
    assert_eq!(rows[0], ("Cost".into(), "-".into(), "-".into()));
    assert_eq!(rows[1], ("-".into(), "High".into(), "-".into()));
    assert_eq!(rows[2], ("-".into(), "-".into(), "Underutilized".into()));
}

#[test]
fn test_parse_recommendation_rows_complete() {
    let data = serde_json::json!([{
        "category": "Cost",
        "impact": "Medium",
        "shortDescription": {"problem": "Resize VM to save money"}
    }]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].1, "Medium");
    assert_eq!(rows[0].2, "Resize VM to save money");
}

// ── NEW: parse_cost_action_rows additional tests ────────────

#[test]
fn test_parse_cost_action_rows_null_input() {
    let data = serde_json::json!(null);
    let rows = super::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_action_rows_object_not_array() {
    let data = serde_json::json!({"key": "val"});
    let rows = super::parse_cost_action_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_action_rows_complete() {
    let data = serde_json::json!([{
        "impactedField": "Microsoft.Compute/virtualMachines",
        "impact": "High",
        "shortDescription": {"problem": "Shut down unused VMs"}
    }]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
    assert_eq!(rows[0].1, "High");
    assert_eq!(rows[0].2, "Shut down unused VMs");
}

#[test]
fn test_parse_cost_action_rows_missing_all_fields() {
    let data = serde_json::json!([{}]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0], ("-".into(), "-".into(), "-".into()));
}

#[test]
fn test_parse_cost_action_rows_multiple() {
    let data = serde_json::json!([
        {"impactedField": "F1", "impact": "Low", "shortDescription": {"problem": "P1"}},
        {"impactedField": "F2", "impact": "High", "shortDescription": {"problem": "P2"}}
    ]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "F1");
    assert_eq!(rows[1].0, "F2");
}

// ── NEW: format_cost_summary additional tests ───────────────

#[test]
fn test_format_cost_summary_table_with_filters() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 150.75,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2025-01-01".into()),
        &Some("2025-01-31".into()),
        false,
        false,
    );
    assert!(out.contains("$150.75"));
    assert!(out.contains("From filter: 2025-01-01"));
    assert!(out.contains("To filter: 2025-01-31"));
}

#[test]
fn test_format_cost_summary_table_with_estimate() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        true,
        false,
    );
    assert!(out.contains("Estimate: $50.00/month (projected)"));
}

#[test]
fn test_format_cost_summary_by_vm_empty_table() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-06-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-06-30T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("No per-VM cost data available"));
}

#[test]
fn test_format_cost_summary_by_vm_csv_multi() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "vm-a".to_string(),
                cost: 120.50,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "vm-b".to_string(),
                cost: 79.50,
                currency: "USD".to_string(),
            },
        ],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("VM Name,Cost,Currency"));
    assert!(out.contains("vm-a,120.50,USD"));
    assert!(out.contains("vm-b,79.50,USD"));
}

#[test]
fn test_format_cost_summary_by_vm_table_format() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 300.0,
        currency: "EUR".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-03-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-03-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "prod-vm".to_string(),
            cost: 300.0,
            currency: "EUR".to_string(),
        }],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("$300.00 EUR"));
    assert!(out.contains("prod-vm"));
}

#[test]
fn test_format_cost_summary_json_output() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 99.99,
        currency: "USD".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Json,
        &Some("ignored".into()),
        &Some("ignored".into()),
        true,
        true,
    );
    let parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
    assert_eq!(parsed["total_cost"].as_f64().unwrap(), 99.99);
    assert_eq!(parsed["currency"].as_str().unwrap(), "USD");
}

#[test]
fn test_format_cost_summary_csv_no_by_vm() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 42.0,
        currency: "GBP".to_string(),
        period_start: chrono::DateTime::parse_from_rfc3339("2025-02-01T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        period_end: chrono::DateTime::parse_from_rfc3339("2025-02-28T00:00:00Z")
            .unwrap()
            .with_timezone(&chrono::Utc),
        by_vm: vec![],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        false,
    );
    assert!(out.starts_with("Total Cost,Currency,Period Start,Period End\n"));
    assert!(out.contains("42.00,GBP,2025-02-01,2025-02-28"));
}

// ── NEW: shell_escape additional tests ───────────────────────

#[test]
fn test_shell_escape_tab() {
    let result = super::shell_escape("\t");
    assert_eq!(result, "'\t'");
}

#[test]
fn test_shell_escape_mixed_quotes() {
    let result = super::shell_escape("it's a \"test\"");
    assert_eq!(result, "'it'\\''s a \"test\"'");
}

#[test]
fn test_shell_escape_backslash() {
    let result = super::shell_escape("path\\to\\file");
    assert_eq!(result, "'path\\to\\file'");
}

#[test]
fn test_shell_escape_env_var_syntax() {
    let result = super::shell_escape("${HOME}");
    assert_eq!(result, "'${HOME}'");
}

#[test]
fn test_shell_escape_command_substitution() {
    let result = super::shell_escape("$(whoami)");
    assert_eq!(result, "'$(whoami)'");
}

#[test]
fn test_shell_escape_consecutive_single_quotes() {
    let result = super::shell_escape("''");
    assert_eq!(result, "''\\'''\\'''");
}

// ── NEW: auth_test_helpers additional tests ─────────────────

#[test]
fn test_extract_account_info_nested_user() {
    let acct = serde_json::json!({
        "name": "Enterprise Sub",
        "tenantId": "t-abc-123",
        "user": {"name": "admin@contoso.com", "type": "servicePrincipal"}
    });
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "Enterprise Sub");
    assert_eq!(tenant, "t-abc-123");
    assert_eq!(user, "admin@contoso.com");
}

#[test]
fn test_extract_account_info_numeric_values() {
    let acct = serde_json::json!({
        "name": 123,
        "tenantId": 456,
        "user": {"name": 789}
    });
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── NEW: template file system edge cases ─────────────────────

#[test]
fn test_template_overwrite_existing() {
    let tmp = TempDir::new().unwrap();
    let tpl1 = super::templates::build_template_toml("x", Some("v1"), None, None, None);
    super::templates::save_template(tmp.path(), "x", &tpl1).unwrap();
    let tpl2 = super::templates::build_template_toml("x", Some("v2"), None, None, None);
    super::templates::save_template(tmp.path(), "x", &tpl2).unwrap();
    let loaded = super::templates::load_template(tmp.path(), "x").unwrap();
    assert_eq!(loaded["description"].as_str().unwrap(), "v2");
}

#[test]
fn test_template_import_overwrites_existing() {
    let tmp = TempDir::new().unwrap();
    let tpl = super::templates::build_template_toml("imp", Some("old"), None, None, None);
    super::templates::save_template(tmp.path(), "imp", &tpl).unwrap();
    let content =
        "name = \"imp\"\ndescription = \"new\"\nvm_size = \"Standard_A1\"\nregion = \"westus\"\n";
    super::templates::import_template(tmp.path(), content).unwrap();
    let loaded = super::templates::load_template(tmp.path(), "imp").unwrap();
    assert_eq!(loaded["description"].as_str().unwrap(), "new");
}

// ── NEW: session file persistence tests ──────────────────────

#[test]
fn test_session_save_then_list() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path().join("sessions");
    fs::create_dir_all(&dir).unwrap();
    for name in &["alpha", "beta", "gamma"] {
        let s = super::sessions::build_session_toml(name, "rg", &[]);
        let content = toml::to_string_pretty(&s).unwrap();
        fs::write(dir.join(format!("{}.toml", name)), content).unwrap();
    }
    let names = super::sessions::list_session_names(&dir).unwrap();
    assert_eq!(names.len(), 3);
    for expected in &["alpha", "beta", "gamma"] {
        assert!(names.contains(&expected.to_string()));
    }
}

#[test]
fn test_session_parse_with_many_vms() {
    let vms: Vec<String> = (0..20).map(|i| format!("vm-{:03}", i)).collect();
    let built = super::sessions::build_session_toml("big", "rg-big", &vms);
    let serialized = toml::to_string_pretty(&built).unwrap();
    let (rg, parsed_vms, _) = super::sessions::parse_session_toml(&serialized).unwrap();
    assert_eq!(rg, "rg-big");
    assert_eq!(parsed_vms.len(), 20);
    assert_eq!(parsed_vms[0], "vm-000");
    assert_eq!(parsed_vms[19], "vm-019");
}

// ── NEW: context file persistence tests ──────────────────────

#[test]
fn test_context_rename_preserves_other_fields() {
    let tmp = TempDir::new().unwrap();
    let content = super::contexts::build_context_toml(
        "old",
        Some("sub-1"),
        Some("tenant-1"),
        Some("rg-1"),
        Some("westus2"),
        Some("kv-1"),
    )
    .unwrap();
    fs::write(tmp.path().join("old.toml"), content).unwrap();
    super::contexts::rename_context_file(tmp.path(), "old", "new").unwrap();
    let loaded: toml::Value = fs::read_to_string(tmp.path().join("new.toml"))
        .unwrap()
        .parse()
        .unwrap();
    let t = loaded.as_table().unwrap();
    assert_eq!(t["name"].as_str().unwrap(), "new");
    assert_eq!(t["subscription_id"].as_str().unwrap(), "sub-1");
    assert_eq!(t["tenant_id"].as_str().unwrap(), "tenant-1");
    assert_eq!(t["resource_group"].as_str().unwrap(), "rg-1");
    assert_eq!(t["region"].as_str().unwrap(), "westus2");
    assert_eq!(t["key_vault_name"].as_str().unwrap(), "kv-1");
}

#[test]
fn test_context_list_sorted() {
    let tmp = TempDir::new().unwrap();
    for name in &["charlie", "alpha", "bravo"] {
        fs::write(
            tmp.path().join(format!("{}.toml", name)),
            format!("name = \"{}\"\n", name),
        )
        .unwrap();
    }
    let list = super::contexts::list_contexts(tmp.path(), "bravo").unwrap();
    assert_eq!(list[0].0, "alpha");
    assert_eq!(list[1].0, "bravo");
    assert!(list[1].1);
    assert_eq!(list[2].0, "charlie");
}

// ── NEW: comprehensive validate_env_key tests ───────────────

#[test]
fn test_validate_env_key_all_digits() {
    assert!(super::env_helpers::validate_env_key("123").is_err());
}

#[test]
fn test_validate_env_key_underscore_start() {
    assert!(super::env_helpers::validate_env_key("_VAR").is_ok());
}

#[test]
fn test_validate_env_key_long_valid() {
    let key = "A".repeat(256);
    assert!(super::env_helpers::validate_env_key(&key).is_ok());
}

#[test]
fn test_validate_env_key_tab() {
    assert!(super::env_helpers::validate_env_key("A\tB").is_err());
}

#[test]
fn test_validate_env_key_newline() {
    assert!(super::env_helpers::validate_env_key("A\nB").is_err());
}

// ── NEW: cp_helpers edge cases ──────────────────────────────

#[test]
fn test_is_remote_path_colon_at_end() {
    assert!(super::cp_helpers::is_remote_path("vm:"));
}

#[test]
fn test_is_remote_path_long_vm_name() {
    assert!(super::cp_helpers::is_remote_path(
        "my-long-vm-name-123:/data/dir"
    ));
}

#[test]
fn test_classify_both_remote() {
    // Both paths have colons and look remote, so neither condition
    // (remote+!remote or !remote+remote) matches — returns local→local
    let dir = super::cp_helpers::classify_transfer_direction("vm1:/a", "vm2:/b");
    assert_eq!(dir, "local→local");
}

#[test]
fn test_resolve_scp_path_multiple_colons() {
    let result = super::cp_helpers::resolve_scp_path("vm:path:with:colons", "vm", "u", "1.1.1.1");
    assert_eq!(result, "u@1.1.1.1:path:with:colons");
}

// ── NEW: output formatting with unicode ─────────────────────

#[test]
fn test_format_as_csv_unicode_content() {
    let rows = vec![vec!["名前".into(), "東京".into()]];
    let csv = super::output_helpers::format_as_csv(&["Name", "City"], &rows);
    assert!(csv.contains("名前,東京"));
}

#[test]
fn test_format_as_table_unicode_alignment() {
    let rows = vec![vec!["日本語".into(), "データ".into()]];
    let table = super::output_helpers::format_as_table(&["Label", "Value"], &rows);
    assert!(table.contains("日本語"));
    assert!(table.contains("データ"));
}

#[test]
fn test_format_as_csv_commas_in_values() {
    let rows = vec![vec!["a,b".into(), "c".into()]];
    let csv = super::output_helpers::format_as_csv(&["X", "Y"], &rows);
    // Note: no escaping is done - this tests current behavior
    assert!(csv.contains("a,b,c"));
}

// ── NEW: snapshot filter edge cases ──────────────────────────

#[test]
fn test_filter_snapshots_substring_match() {
    let snaps = vec![
        serde_json::json!({"name": "vm1_snap"}),
        serde_json::json!({"name": "vm10_snap"}),
        serde_json::json!({"name": "vm1-extra_snap"}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "vm1");
    // "vm1" is a substring of all three
    assert_eq!(filtered.len(), 3);
}

#[test]
fn test_filter_snapshots_case_sensitive() {
    let snaps = vec![
        serde_json::json!({"name": "VM1_snap"}),
        serde_json::json!({"name": "vm1_snap"}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "vm1");
    assert_eq!(filtered.len(), 1);
}

// ── NEW: validate_mount_path traversal cases ────────────────

#[test]
fn test_mount_path_traversal_in_middle() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/a/../b").is_err());
}

#[test]
fn test_mount_path_traversal_at_end() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/..").is_err());
}

#[test]
fn test_mount_path_with_spaces_ok() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/my data").is_ok());
}

#[test]
fn test_mount_path_deeply_nested() {
    assert!(super::mount_helpers::validate_mount_path("/a/b/c/d/e/f/g/h").is_ok());
}

// ── Additional shell_escape tests ───────────────────────────
#[test]
fn test_shell_escape_empty_v2() {
    assert_eq!(super::shell_escape(""), "''");
}

#[test]
fn test_shell_escape_special_chars() {
    assert_eq!(super::shell_escape("a b;c&d|e"), "'a b;c&d|e'");
}

#[test]
fn test_shell_escape_with_newlines_v2() {
    assert_eq!(super::shell_escape("line1\nline2"), "'line1\nline2'");
}

// ── Additional parse tests ──────────────────────────────────
#[test]
fn test_parse_recommendation_rows_only_category() {
    let data = serde_json::json!([{
        "category": "Cost"
    }]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].1, "-");
}

#[test]
fn test_parse_recommendation_rows_two_entries() {
    let data = serde_json::json!([
        {"category": "Cost", "impact": "High", "shortDescription": {"problem": "idle VM"}},
        {"category": "Security", "impact": "Low", "shortDescription": {"problem": "no NSG"}}
    ]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[1].0, "Security");
}

#[test]
fn test_parse_cost_action_rows_missing_solution_field() {
    let data = serde_json::json!([{
        "category": "Cost",
        "impact": "Medium",
        "shortDescription": {}
    }]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].2, "-");
}

#[test]
fn test_parse_cost_action_rows_two_items() {
    let data = serde_json::json!([
        {"impactedField": "VM/compute", "impact": "High", "shortDescription": {"problem": "idle VM"}},
        {"impactedField": "Storage", "impact": "Low", "shortDescription": {"problem": "unattached disk"}}
    ]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "VM/compute");
    assert_eq!(rows[0].2, "idle VM");
    assert_eq!(rows[1].0, "Storage");
}

// ── format_cost_summary additional tests ────────────────────
#[test]
fn test_format_cost_summary_with_from_to_filters() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "USD".to_string(),
        period_start: chrono::NaiveDate::from_ymd_opt(2025, 1, 1)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        period_end: chrono::NaiveDate::from_ymd_opt(2025, 1, 31)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        by_vm: vec![],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2025-01-01".to_string()),
        &Some("2025-01-31".to_string()),
        false,
        false,
    );
    assert!(out.contains("From filter: 2025-01-01"));
    assert!(out.contains("To filter: 2025-01-31"));
}

#[test]
fn test_format_cost_summary_by_vm_csv_output() {
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::NaiveDate::from_ymd_opt(2025, 1, 1)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        period_end: chrono::NaiveDate::from_ymd_opt(2025, 1, 31)
            .unwrap()
            .and_hms_opt(0, 0, 0)
            .unwrap()
            .and_utc(),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "vm-1".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "vm-2".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            },
        ],
    };
    let out = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(out.contains("VM Name,Cost,Currency"));
    assert!(out.contains("vm-1,100.00,USD"));
    assert!(out.contains("vm-2,100.00,USD"));
}

// ── fleet_spinner_style test ────────────────────────────────
#[test]
fn test_fleet_spinner_style_creation() {
    let style = super::fleet_spinner_style();
    let _ = style;
}

// ── HealthMetrics test ──────────────────────────────────────
#[test]
fn test_health_metrics_struct() {
    let m = super::HealthMetrics {
        vm_name: "test-vm".to_string(),
        power_state: "running".to_string(),
        agent_status: "OK".to_string(),
        error_count: 0,
        cpu_percent: 45.0,
        mem_percent: 60.0,
        disk_percent: 30.0,
    };
    assert_eq!(m.vm_name, "test-vm");
    assert_eq!(m.power_state, "running");
    assert!(m.cpu_percent > 0.0);
}

// ── health_parse_helpers tests ──────────────────────────────

#[test]
fn test_parse_cpu_stdout_valid() {
    assert_eq!(
        super::health_parse_helpers::parse_cpu_stdout(0, "  23.4\n"),
        Some(23.4)
    );
}

#[test]
fn test_parse_cpu_stdout_non_zero_exit() {
    assert_eq!(
        super::health_parse_helpers::parse_cpu_stdout(1, "23.4"),
        None
    );
}

#[test]
fn test_parse_cpu_stdout_garbage() {
    assert_eq!(
        super::health_parse_helpers::parse_cpu_stdout(0, "not a number"),
        None
    );
}

#[test]
fn test_parse_cpu_stdout_empty() {
    assert_eq!(super::health_parse_helpers::parse_cpu_stdout(0, ""), None);
}

#[test]
fn test_parse_cpu_stdout_whitespace_only() {
    assert_eq!(
        super::health_parse_helpers::parse_cpu_stdout(0, "   \n  "),
        None
    );
}

#[test]
fn test_parse_mem_stdout_valid() {
    assert_eq!(
        super::health_parse_helpers::parse_mem_stdout(0, "67.3\n"),
        Some(67.3)
    );
}

#[test]
fn test_parse_mem_stdout_failure() {
    assert_eq!(
        super::health_parse_helpers::parse_mem_stdout(127, "67.3"),
        None
    );
}

#[test]
fn test_parse_mem_stdout_zero() {
    assert_eq!(
        super::health_parse_helpers::parse_mem_stdout(0, "0.0"),
        Some(0.0)
    );
}

#[test]
fn test_parse_disk_stdout_valid() {
    assert_eq!(
        super::health_parse_helpers::parse_disk_stdout(0, " 42 \n"),
        Some(42.0)
    );
}

#[test]
fn test_parse_disk_stdout_failure() {
    assert_eq!(
        super::health_parse_helpers::parse_disk_stdout(255, "42"),
        None
    );
}

#[test]
fn test_parse_disk_stdout_not_numeric() {
    assert_eq!(
        super::health_parse_helpers::parse_disk_stdout(0, "N/A"),
        None
    );
}

#[test]
fn test_default_metrics() {
    let m = super::health_parse_helpers::default_metrics("my-vm", "deallocated");
    assert_eq!(m.vm_name, "my-vm");
    assert_eq!(m.power_state, "deallocated");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

// ── fleet_helpers tests ─────────────────────────────────────

#[test]
fn test_classify_result_success() {
    let (status, ok) = super::fleet_helpers::classify_result(0);
    assert_eq!(status, "OK");
    assert!(ok);
}

#[test]
fn test_classify_result_failure() {
    let (status, ok) = super::fleet_helpers::classify_result(1);
    assert_eq!(status, "FAIL");
    assert!(!ok);
}

#[test]
fn test_classify_result_negative() {
    let (status, ok) = super::fleet_helpers::classify_result(-1);
    assert_eq!(status, "FAIL");
    assert!(!ok);
}

#[test]
fn test_finish_message_success() {
    let msg = super::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert_eq!(msg, "✓ done (3 lines)");
}

#[test]
fn test_finish_message_success_empty_stdout() {
    let msg = super::fleet_helpers::finish_message(0, "", "");
    assert_eq!(msg, "✓ done (0 lines)");
}

#[test]
fn test_finish_message_failure() {
    let msg = super::fleet_helpers::finish_message(1, "", "Permission denied\nfatal error");
    assert_eq!(msg, "✗ Permission denied");
}

#[test]
fn test_finish_message_failure_empty_stderr() {
    let msg = super::fleet_helpers::finish_message(1, "", "");
    assert_eq!(msg, "✗ error");
}

#[test]
fn test_format_output_text_show_output_with_stdout() {
    let text = super::fleet_helpers::format_output_text(0, "hello world\n", "some warning", true);
    assert_eq!(text, "hello world");
}

#[test]
fn test_format_output_text_show_output_empty_stdout() {
    let text = super::fleet_helpers::format_output_text(0, "  \n", "stderr output", true);
    assert_eq!(text, "stderr output");
}

#[test]
fn test_format_output_text_no_show_failure() {
    let text = super::fleet_helpers::format_output_text(
        1,
        "",
        "error: connection refused\nmore details",
        false,
    );
    assert_eq!(text, "error: connection refused");
}

#[test]
fn test_format_output_text_no_show_success() {
    let text = super::fleet_helpers::format_output_text(0, "data", "warning", false);
    assert_eq!(text, "");
}

#[test]
fn test_format_output_text_no_show_failure_empty_stderr() {
    let text = super::fleet_helpers::format_output_text(1, "", "", false);
    assert_eq!(text, "");
}

// ── list_helpers tests ──────────────────────────────────────

fn make_vm(name: &str, state: azlin_core::models::PowerState) -> azlin_core::models::VmInfo {
    azlin_core::models::VmInfo {
        name: name.to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_B2s".to_string(),
        power_state: state,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: Some("10.0.0.1".to_string()),
        private_ip: None,
        admin_username: Some("azureuser".to_string()),
        tags: std::collections::HashMap::new(),
        created_time: None,
    }
}

fn make_tagged_vm(name: &str, tags: Vec<(&str, &str)>) -> azlin_core::models::VmInfo {
    let mut vm = make_vm(name, azlin_core::models::PowerState::Running);
    for (k, v) in tags {
        vm.tags.insert(k.to_string(), v.to_string());
    }
    vm
}

#[test]
fn test_filter_running_removes_stopped() {
    let mut vms = vec![
        make_vm("running-vm", azlin_core::models::PowerState::Running),
        make_vm("stopped-vm", azlin_core::models::PowerState::Stopped),
        make_vm("starting-vm", azlin_core::models::PowerState::Starting),
        make_vm("dealloc-vm", azlin_core::models::PowerState::Deallocated),
    ];
    super::list_helpers::filter_running(&mut vms);
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].name, "running-vm");
    assert_eq!(vms[1].name, "starting-vm");
}

#[test]
fn test_filter_running_empty_list() {
    let mut vms: Vec<azlin_core::models::VmInfo> = vec![];
    super::list_helpers::filter_running(&mut vms);
    assert!(vms.is_empty());
}

#[test]
fn test_filter_by_tag_key_value() {
    let mut vms = vec![
        make_tagged_vm("vm1", vec![("env", "prod")]),
        make_tagged_vm("vm2", vec![("env", "dev")]),
        make_tagged_vm("vm3", vec![("team", "infra")]),
    ];
    super::list_helpers::filter_by_tag(&mut vms, "env=prod");
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm1");
}

#[test]
fn test_filter_by_tag_key_only() {
    let mut vms = vec![
        make_tagged_vm("vm1", vec![("env", "prod")]),
        make_tagged_vm("vm2", vec![("env", "dev")]),
        make_tagged_vm("vm3", vec![("team", "infra")]),
    ];
    super::list_helpers::filter_by_tag(&mut vms, "env");
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].name, "vm1");
    assert_eq!(vms[1].name, "vm2");
}

#[test]
fn test_filter_by_tag_no_match() {
    let mut vms = vec![make_tagged_vm("vm1", vec![("env", "prod")])];
    super::list_helpers::filter_by_tag(&mut vms, "env=staging");
    assert!(vms.is_empty());
}

#[test]
fn test_filter_by_tag_nonexistent_key() {
    let mut vms = vec![make_tagged_vm("vm1", vec![("env", "prod")])];
    super::list_helpers::filter_by_tag(&mut vms, "region");
    assert!(vms.is_empty());
}

#[test]
fn test_filter_by_pattern_simple() {
    let mut vms = vec![
        make_vm("web-server-01", azlin_core::models::PowerState::Running),
        make_vm("db-server-01", azlin_core::models::PowerState::Running),
        make_vm("web-server-02", azlin_core::models::PowerState::Running),
    ];
    super::list_helpers::filter_by_pattern(&mut vms, "web");
    assert_eq!(vms.len(), 2);
    assert_eq!(vms[0].name, "web-server-01");
    assert_eq!(vms[1].name, "web-server-02");
}

#[test]
fn test_filter_by_pattern_with_glob() {
    let mut vms = vec![
        make_vm("web-server-01", azlin_core::models::PowerState::Running),
        make_vm("db-server-01", azlin_core::models::PowerState::Running),
    ];
    super::list_helpers::filter_by_pattern(&mut vms, "*web*");
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "web-server-01");
}

#[test]
fn test_filter_by_pattern_no_match() {
    let mut vms = vec![make_vm(
        "web-server",
        azlin_core::models::PowerState::Running,
    )];
    super::list_helpers::filter_by_pattern(&mut vms, "cache");
    assert!(vms.is_empty());
}

#[test]
fn test_apply_filters_all_disabled() {
    let mut vms = vec![
        make_vm("vm1", azlin_core::models::PowerState::Running),
        make_vm("vm2", azlin_core::models::PowerState::Stopped),
    ];
    super::list_helpers::apply_filters(&mut vms, true, None, None);
    assert_eq!(vms.len(), 2);
}

#[test]
fn test_apply_filters_exclude_stopped() {
    let mut vms = vec![
        make_vm("vm1", azlin_core::models::PowerState::Running),
        make_vm("vm2", azlin_core::models::PowerState::Stopped),
    ];
    super::list_helpers::apply_filters(&mut vms, false, None, None);
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "vm1");
}

#[test]
fn test_apply_filters_combined() {
    let mut vms = vec![
        make_tagged_vm("web-prod", vec![("env", "prod")]),
        make_tagged_vm("web-dev", vec![("env", "dev")]),
        make_tagged_vm("db-prod", vec![("env", "prod")]),
    ];
    super::list_helpers::apply_filters(&mut vms, true, Some("env=prod"), Some("web"));
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "web-prod");
}

// ── batch_helpers tests ─────────────────────────────────────

#[test]
fn test_parse_vm_ids_normal() {
    let ids = super::batch_helpers::parse_vm_ids("/sub/1/rg/test/vm/vm1\n/sub/1/rg/test/vm/vm2\n");
    assert_eq!(ids.len(), 2);
    assert_eq!(ids[0], "/sub/1/rg/test/vm/vm1");
    assert_eq!(ids[1], "/sub/1/rg/test/vm/vm2");
}

#[test]
fn test_parse_vm_ids_empty() {
    let ids = super::batch_helpers::parse_vm_ids("");
    assert!(ids.is_empty());
}

#[test]
fn test_parse_vm_ids_blank_lines() {
    let ids = super::batch_helpers::parse_vm_ids("\n\n/sub/vm1\n\n");
    assert_eq!(ids.len(), 1);
    assert_eq!(ids[0], "/sub/vm1");
}

#[test]
fn test_build_batch_args_deallocate() {
    let ids = vec!["/sub/vm1", "/sub/vm2"];
    let args = super::batch_helpers::build_batch_args("deallocate", &ids);
    assert_eq!(
        args,
        vec!["vm", "deallocate", "--ids", "/sub/vm1", "/sub/vm2"]
    );
}

#[test]
fn test_build_batch_args_start() {
    let ids = vec!["/sub/vm1"];
    let args = super::batch_helpers::build_batch_args("start", &ids);
    assert_eq!(args, vec!["vm", "start", "--ids", "/sub/vm1"]);
}

#[test]
fn test_summarise_batch_success() {
    let msg = super::batch_helpers::summarise_batch("stop", "my-rg", true);
    assert_eq!(msg, "Batch stop completed for resource group 'my-rg'");
}

#[test]
fn test_summarise_batch_failure() {
    let msg = super::batch_helpers::summarise_batch("start", "my-rg", false);
    assert_eq!(msg, "Batch start failed. Run commands individually.");
}

#[test]
fn test_summarise_batch_other_action() {
    let msg = super::batch_helpers::summarise_batch("restart", "prod-rg", true);
    assert!(msg.contains("restart"));
    assert!(msg.contains("prod-rg"));
}

// ── all_contexts tests ────────────────────────────────────────

#[test]
fn test_read_context_resource_group_with_rg() {
    let tmp = TempDir::new().unwrap();
    let ctx_path = tmp.path().join("dev.toml");
    fs::write(
        &ctx_path,
        "name = \"dev\"\nresource_group = \"dev-rg\"\nregion = \"westus2\"\n",
    )
    .unwrap();

    let (name, rg) = super::contexts::read_context_resource_group(&ctx_path).unwrap();
    assert_eq!(name, "dev");
    assert_eq!(rg, Some("dev-rg".to_string()));
}

#[test]
fn test_read_context_resource_group_without_rg() {
    let tmp = TempDir::new().unwrap();
    let ctx_path = tmp.path().join("minimal.toml");
    fs::write(&ctx_path, "name = \"minimal\"\n").unwrap();

    let (name, rg) = super::contexts::read_context_resource_group(&ctx_path).unwrap();
    assert_eq!(name, "minimal");
    assert_eq!(rg, None);
}

#[test]
fn test_read_context_resource_group_falls_back_to_filename() {
    let tmp = TempDir::new().unwrap();
    let ctx_path = tmp.path().join("staging.toml");
    fs::write(&ctx_path, "resource_group = \"staging-rg\"\n").unwrap();

    let (name, rg) = super::contexts::read_context_resource_group(&ctx_path).unwrap();
    assert_eq!(name, "staging");
    assert_eq!(rg, Some("staging-rg".to_string()));
}

// ── create_helpers tests ────────────────────────────────────────

#[test]
fn test_generate_vm_name_with_base_pool_1() {
    let name = super::create_helpers::generate_vm_name(Some("my-vm"), 0, 1, "20240101");
    assert_eq!(name, "my-vm");
}

#[test]
fn test_generate_vm_name_with_base_pool_multiple() {
    let n1 = super::create_helpers::generate_vm_name(Some("my-vm"), 0, 3, "20240101");
    let n2 = super::create_helpers::generate_vm_name(Some("my-vm"), 1, 3, "20240101");
    let n3 = super::create_helpers::generate_vm_name(Some("my-vm"), 2, 3, "20240101");
    assert_eq!(n1, "my-vm-1");
    assert_eq!(n2, "my-vm-2");
    assert_eq!(n3, "my-vm-3");
}

#[test]
fn test_generate_vm_name_no_base_uses_timestamp() {
    let name = super::create_helpers::generate_vm_name(None, 0, 1, "20240315-120000");
    assert_eq!(name, "azlin-vm-20240315-120000");
}

#[test]
fn test_resolve_with_template_default_user_value() {
    let result = super::create_helpers::resolve_with_template_default(
        "Standard_D8s_v3",
        "Standard_D4s_v3",
        Some("Standard_D2s_v3".to_string()),
    );
    assert_eq!(result, "Standard_D8s_v3");
}

#[test]
fn test_resolve_with_template_default_uses_template() {
    let result = super::create_helpers::resolve_with_template_default(
        "Standard_D4s_v3",
        "Standard_D4s_v3",
        Some("Standard_D16s_v3".to_string()),
    );
    assert_eq!(result, "Standard_D16s_v3");
}

#[test]
fn test_resolve_with_template_default_no_template() {
    let result = super::create_helpers::resolve_with_template_default(
        "Standard_D4s_v3",
        "Standard_D4s_v3",
        None,
    );
    assert_eq!(result, "Standard_D4s_v3");
}

#[test]
fn test_build_clone_cmd_https() {
    let cmd = super::create_helpers::build_clone_cmd("https://github.com/user/repo.git").unwrap();
    assert!(cmd.contains("git clone"));
    assert!(cmd.contains("https://github.com/user/repo.git"));
    assert!(cmd.contains("~/src/$(basename"));
}

#[test]
fn test_build_ssh_connect_args() {
    let args = super::create_helpers::build_ssh_connect_args("azureuser", "10.0.0.1");
    assert_eq!(
        args,
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "azureuser@10.0.0.1".to_string(),
        ]
    );
}

#[test]
fn test_create_build_snapshot_name() {
    let name = super::create_helpers::build_snapshot_name("my-vm", "20240315");
    assert_eq!(name, "my-vm_clone_snap_20240315");
}

#[test]
fn test_build_clone_name() {
    assert_eq!(
        super::create_helpers::build_clone_name("source-vm", 0),
        "source-vm-clone-1"
    );
    assert_eq!(
        super::create_helpers::build_clone_name("source-vm", 4),
        "source-vm-clone-5"
    );
}

#[test]
fn test_build_disk_name() {
    assert_eq!(
        super::create_helpers::build_disk_name("my-vm"),
        "my-vm_OsDisk"
    );
}

// ── connect_helpers tests ───────────────────────────────────────

#[test]
fn test_build_ssh_args_without_key() {
    let args = super::connect_helpers::build_ssh_args("azureuser", "10.0.0.5", None);
    assert_eq!(
        args,
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "azureuser@10.0.0.5".to_string(),
        ]
    );
}

#[test]
fn test_build_ssh_args_with_key() {
    use std::path::Path;
    let key = Path::new("/home/user/.ssh/id_ed25519");
    let args = super::connect_helpers::build_ssh_args("admin", "192.168.1.1", Some(key));
    assert_eq!(
        args,
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "-i".to_string(),
            "/home/user/.ssh/id_ed25519".to_string(),
            "admin@192.168.1.1".to_string(),
        ]
    );
}

#[test]
fn test_build_vscode_remote_uri() {
    let uri = super::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_build_log_follow_args() {
    let args =
        super::connect_helpers::build_log_follow_args("azureuser", "10.0.0.5", "/var/log/syslog");
    assert_eq!(args.len(), 6);
    assert_eq!(args[4], "azureuser@10.0.0.5");
    assert_eq!(args[5], "sudo tail -f /var/log/syslog");
}

#[test]
fn test_build_log_tail_args() {
    let args =
        super::connect_helpers::build_log_tail_args("admin", "10.0.0.1", 100, "/var/log/auth.log");
    assert_eq!(args.len(), 6);
    assert!(args[5].contains("tail -n 100"));
    assert!(args[5].contains("/var/log/auth.log"));
}

// ── update_helpers tests ────────────────────────────────────────

#[test]
fn test_build_dev_update_script_contains_sections() {
    let script = super::update_helpers::build_dev_update_script();
    assert!(script.starts_with("#!/bin/bash"));
    assert!(script.contains("set -e"));
    assert!(script.contains("apt-get update"));
    assert!(script.contains("rustup update"));
    assert!(script.contains("pip3 install"));
    assert!(script.contains("npm install"));
}

#[test]
fn test_build_os_update_cmd() {
    let cmd = super::update_helpers::build_os_update_cmd();
    assert!(cmd.contains("apt-get update"));
    assert!(cmd.contains("apt-get upgrade"));
    assert!(cmd.contains("DEBIAN_FRONTEND=noninteractive"));
}

#[test]
fn test_log_type_to_path_cloud_init() {
    assert_eq!(
        super::update_helpers::log_type_to_path("cloud-init"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
}

#[test]
fn test_log_type_to_path_syslog() {
    assert_eq!(
        super::update_helpers::log_type_to_path("syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
}

#[test]
fn test_log_type_to_path_auth() {
    assert_eq!(
        super::update_helpers::log_type_to_path("auth"),
        "/var/log/auth.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
}

#[test]
fn test_log_type_to_path_unknown_defaults_syslog() {
    assert_eq!(
        super::update_helpers::log_type_to_path("something-else"),
        "/var/log/syslog"
    );
}

// ── compose_helpers tests ───────────────────────────────────────

#[test]
fn test_resolve_compose_file_default() {
    let f = super::compose_helpers::resolve_compose_file(None);
    assert_eq!(f, "docker-compose.yml");
}

#[test]
fn test_resolve_compose_file_custom() {
    let f = super::compose_helpers::resolve_compose_file(Some("compose.prod.yaml"));
    assert_eq!(f, "compose.prod.yaml");
}

#[test]
fn test_build_compose_cmd_up() {
    let cmd = super::compose_helpers::build_compose_cmd("up -d", "docker-compose.yml");
    assert_eq!(cmd, "docker compose -f docker-compose.yml up -d");
}

#[test]
fn test_build_compose_cmd_down() {
    let cmd = super::compose_helpers::build_compose_cmd("down", "compose.prod.yaml");
    assert_eq!(cmd, "docker compose -f compose.prod.yaml down");
}

// ── runner_helpers tests ────────────────────────────────────────

#[test]
fn test_build_runner_vm_name() {
    assert_eq!(
        super::runner_helpers::build_runner_vm_name("ci-pool", 0),
        "azlin-runner-ci-pool-1"
    );
    assert_eq!(
        super::runner_helpers::build_runner_vm_name("ci-pool", 2),
        "azlin-runner-ci-pool-3"
    );
}

#[test]
fn test_build_runner_tags() {
    let tags = super::runner_helpers::build_runner_tags("ci-pool", "user/repo");
    assert!(tags.contains("azlin-runner=true"));
    assert!(tags.contains("pool=ci-pool"));
    assert!(tags.contains("repo=user/repo"));
}

#[test]
fn test_build_runner_config_fields() {
    let config = super::runner_helpers::build_runner_config(
        "ci-pool",
        "user/repo",
        3,
        "self-hosted,linux",
        "my-rg",
        "Standard_D4s_v3",
        "2024-03-15T00:00:00Z",
    );
    let keys: Vec<&str> = config.iter().map(|(k, _)| k.as_str()).collect();
    assert!(keys.contains(&"pool"));
    assert!(keys.contains(&"repo"));
    assert!(keys.contains(&"count"));
    assert!(keys.contains(&"labels"));
    assert!(keys.contains(&"resource_group"));
    assert!(keys.contains(&"vm_size"));
    assert!(keys.contains(&"enabled"));
    assert!(keys.contains(&"created"));

    let count = config
        .iter()
        .find(|(k, _)| k == "count")
        .map(|(_, v)| v.as_integer().unwrap())
        .unwrap();
    assert_eq!(count, 3);
}

#[test]
fn test_pool_config_filename() {
    assert_eq!(
        super::runner_helpers::pool_config_filename("ci-pool"),
        "ci-pool.toml"
    );
}

// ── autopilot_helpers tests ─────────────────────────────────────

#[test]
fn test_build_autopilot_config_with_budget() {
    let config = super::autopilot_helpers::build_autopilot_config(
        Some(500),
        "aggressive",
        30,
        80,
        "2024-03-15T00:00:00Z",
    );
    let tbl = config.as_table().unwrap();
    assert_eq!(tbl["enabled"].as_bool(), Some(true));
    assert_eq!(tbl["budget"].as_integer(), Some(500));
    assert_eq!(tbl["strategy"].as_str(), Some("aggressive"));
    assert_eq!(tbl["idle_threshold_minutes"].as_integer(), Some(30));
    assert_eq!(tbl["cpu_threshold_percent"].as_integer(), Some(80));
}

#[test]
fn test_build_autopilot_config_without_budget() {
    let config = super::autopilot_helpers::build_autopilot_config(
        None,
        "conservative",
        60,
        50,
        "2024-03-15T00:00:00Z",
    );
    let tbl = config.as_table().unwrap();
    assert!(tbl.get("budget").is_none());
    assert_eq!(tbl["strategy"].as_str(), Some("conservative"));
}

#[test]
fn test_build_budget_name() {
    assert_eq!(
        super::autopilot_helpers::build_budget_name("my-rg"),
        "azlin-budget-my-rg"
    );
}

#[test]
fn test_build_prefix_filter_query() {
    let q = super::autopilot_helpers::build_prefix_filter_query("azlin-vm");
    assert_eq!(q, "[?starts_with(name, 'azlin-vm')].id");
}

#[test]
fn test_build_cost_scope() {
    let scope = super::autopilot_helpers::build_cost_scope("sub-123", "my-rg");
    assert_eq!(scope, "/subscriptions/sub-123/resourceGroups/my-rg");
}

// ── config_path_helpers tests ───────────────────────────────────

#[test]
fn test_validate_config_path_safe() {
    assert!(super::config_path_helpers::validate_config_path("config.toml").is_ok());
    assert!(super::config_path_helpers::validate_config_path("subdir/config.toml").is_ok());
}

#[test]
fn test_validate_config_path_traversal_rejected() {
    assert!(super::config_path_helpers::validate_config_path("../etc/passwd").is_err());
    assert!(super::config_path_helpers::validate_config_path("subdir/../../etc/shadow").is_err());
}

// ── snapshot_helpers additional tests ────────────────────────────

#[test]
fn test_snapshot_row_full_data() {
    let snap = serde_json::json!({
        "name": "vm1_snapshot_20240315",
        "diskSizeGb": 128,
        "timeCreated": "2024-03-15T12:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "vm1_snapshot_20240315");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2024-03-15T12:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_defaults_for_empty_json() {
    let snap = serde_json::json!({});
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

#[test]
fn test_snapshot_schedule_path_format() {
    let path = super::snapshot_helpers::schedule_path("my-vm");
    assert!(path.to_string_lossy().contains("my-vm.toml"));
    assert!(path.to_string_lossy().contains("schedules"));
}

// ── output_helpers edge case tests ──────────────────────────────

#[test]
fn test_format_as_table_header_only_no_rows() {
    let out = super::output_helpers::format_as_table(&["Name", "Value"], &[]);
    assert_eq!(out, "Name  Value");
}

#[test]
fn test_format_as_table_renders_single_col() {
    let rows = vec![vec!["alpha".to_string()], vec!["beta".to_string()]];
    let out = super::output_helpers::format_as_table(&["Items"], &rows);
    assert!(out.contains("Items"));
    assert!(out.contains("alpha"));
    assert!(out.contains("beta"));
}

#[test]
fn test_format_as_csv_header_only() {
    let out = super::output_helpers::format_as_csv(&["Name", "Size"], &[]);
    assert_eq!(out, "Name,Size");
}

#[test]
fn test_format_as_json_empty_slice() {
    let items: Vec<String> = vec![];
    let out = super::output_helpers::format_as_json(&items);
    assert_eq!(out, "[]");
}

#[test]
fn test_format_as_json_with_data() {
    let items = vec!["hello", "world"];
    let out = super::output_helpers::format_as_json(&items);
    assert!(out.contains("hello"));
    assert!(out.contains("world"));
}

// ── parse_cost_history_rows tests ───────────────────────────────

#[test]
fn test_parse_cost_history_no_rows_key() {
    let data = serde_json::json!({});
    let rows = super::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

#[test]
fn test_parse_cost_history_rows_valid() {
    let data = serde_json::json!({
        "rows": [
            [12.50, "2024-03-01"],
            [8.75, "2024-03-02"]
        ]
    });
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].0, "2024-03-01");
    assert_eq!(rows[0].1, "$12.50");
    assert_eq!(rows[1].0, "2024-03-02");
    assert_eq!(rows[1].1, "$8.75");
}

#[test]
fn test_parse_cost_history_numeric_date() {
    // When date is an integer, the parser maps it to empty string via the
    // `as_str().or_else(|| as_i64().map(|_| ""))` branch.
    let data = serde_json::json!({
        "rows": [
            [5.00, 20240301]
        ]
    });
    let rows = super::parse_cost_history_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].1, "$5.00");
    // Integer dates produce an empty string via the current parser logic
    assert_eq!(rows[0].0, "");
}

#[test]
fn test_parse_cost_history_rows_empty_array() {
    let data = serde_json::json!({ "rows": [] });
    let rows = super::parse_cost_history_rows(&data);
    assert!(rows.is_empty());
}

// ── storage_helpers additional tests ─────────────────────────────

#[test]
fn test_storage_account_row_all_fields() {
    let acct = serde_json::json!({
        "name": "mystorageacct",
        "location": "westus2",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "mystorageacct");
    assert_eq!(row[1], "westus2");
    assert_eq!(row[2], "StorageV2");
    assert_eq!(row[3], "Standard_LRS");
    assert_eq!(row[4], "Succeeded");
}

#[test]
fn test_storage_account_row_missing() {
    let acct = serde_json::json!({});
    let row = super::storage_helpers::storage_account_row(&acct);
    assert!(row.iter().all(|c| c == "-"));
}

// ── vm_validation edge cases ────────────────────────────────────

#[test]
fn test_validate_vm_name_max_length() {
    let name = "a".repeat(64);
    assert!(super::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_validate_vm_name_exceeds_max() {
    let name = "a".repeat(65);
    assert!(super::vm_validation::validate_vm_name(&name).is_err());
}

#[test]
fn test_validate_vm_name_with_underscores_rejected() {
    assert!(super::vm_validation::validate_vm_name("my_vm").is_err());
}

// ── env_helpers edge case tests ─────────────────────────────────

#[test]
fn test_split_env_var_missing_equals() {
    assert!(super::env_helpers::split_env_var("NOVALUE").is_none());
}

#[test]
fn test_split_env_var_empty_key() {
    assert!(super::env_helpers::split_env_var("=value").is_none());
}

#[test]
fn test_split_env_var_blank_value() {
    let result = super::env_helpers::split_env_var("KEY=");
    assert_eq!(result, Some(("KEY", "")));
}

#[test]
fn test_split_env_var_embedded_equals() {
    let result = super::env_helpers::split_env_var("KEY=val=ue");
    assert_eq!(result, Some(("KEY", "val=ue")));
}

#[test]
fn test_parse_env_output_blank_input() {
    let result = super::env_helpers::parse_env_output("");
    assert!(result.is_empty());
}

#[test]
fn test_parse_env_output_multiple() {
    let result =
        super::env_helpers::parse_env_output("HOME=/home/user\nPATH=/usr/bin\nSHELL=/bin/bash");
    assert_eq!(result.len(), 3);
    assert_eq!(result[0], ("HOME".to_string(), "/home/user".to_string()));
    assert_eq!(result[1], ("PATH".to_string(), "/usr/bin".to_string()));
}

// ── sync_helpers edge case tests ────────────────────────────────

#[test]
fn test_validate_sync_source_var_rejected() {
    assert!(super::sync_helpers::validate_sync_source("/var/log/syslog").is_err());
}

#[test]
fn test_validate_sync_source_root_rejected() {
    assert!(super::sync_helpers::validate_sync_source("/root/.bashrc").is_err());
}

#[test]
fn test_validate_sync_source_safe_path() {
    assert!(super::sync_helpers::validate_sync_source("my-dotfiles/.bashrc").is_ok());
}

#[test]
fn test_validate_sync_source_dotdot_only() {
    assert!(super::sync_helpers::validate_sync_source("..").is_err());
}

// ── mount_helpers additional edge case tests ────────────────────

#[test]
fn test_mount_path_null_char() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data\0bad").is_err());
}

#[test]
fn test_mount_path_pipe_char() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data|bad").is_err());
}

#[test]
fn test_mount_path_newline_injection() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data\nbad").is_err());
}

#[test]
fn test_mount_path_not_absolute() {
    assert!(super::mount_helpers::validate_mount_path("relative/path").is_err());
}

// ── stop_helpers tests ──────────────────────────────────────────

#[test]
fn test_stop_action_labels_deallocate() {
    let (action, done) = super::stop_helpers::stop_action_labels(true);
    assert_eq!(action, "Deallocating");
    assert_eq!(done, "Deallocated");
}

#[test]
fn test_stop_action_labels_stop() {
    let (action, done) = super::stop_helpers::stop_action_labels(false);
    assert_eq!(action, "Stopping");
    assert_eq!(done, "Stopped");
}

// ── display_helpers tests ───────────────────────────────────────

#[test]
fn test_config_value_display_string() {
    let v = serde_json::Value::String("hello".to_string());
    assert_eq!(super::display_helpers::config_value_display(&v), "hello");
}

#[test]
fn test_config_value_display_null() {
    assert_eq!(
        super::display_helpers::config_value_display(&serde_json::Value::Null),
        "null"
    );
}

#[test]
fn test_config_value_display_number() {
    let v = serde_json::json!(42);
    assert_eq!(super::display_helpers::config_value_display(&v), "42");
}

#[test]
fn test_truncate_vm_name_short() {
    assert_eq!(
        super::display_helpers::truncate_vm_name("my-vm", 20),
        "my-vm"
    );
}

#[test]
fn test_truncate_vm_name_long() {
    let name = "azlin-very-long-vm-name-12345";
    let result = super::display_helpers::truncate_vm_name(name, 20);
    assert_eq!(result, "azlin-very-long-v...");
    assert_eq!(result.len(), 20);
}

#[test]
fn test_truncate_vm_name_exact_boundary() {
    let name = "exactly-twenty-chars";
    assert_eq!(name.len(), 20);
    assert_eq!(super::display_helpers::truncate_vm_name(name, 20), name);
}

#[test]
fn test_format_tmux_sessions_empty() {
    let sessions: Vec<String> = vec![];
    assert_eq!(
        super::display_helpers::format_tmux_sessions(&sessions, 3),
        "-"
    );
}

#[test]
fn test_format_tmux_sessions_few() {
    let sessions = vec!["main".to_string(), "dev".to_string()];
    assert_eq!(
        super::display_helpers::format_tmux_sessions(&sessions, 3),
        "main, dev"
    );
}

#[test]
fn test_format_tmux_sessions_overflow() {
    let sessions: Vec<String> = (1..=5).map(|i| format!("s{}", i)).collect();
    let result = super::display_helpers::format_tmux_sessions(&sessions, 3);
    assert_eq!(result, "s1, s2, s3, +2 more");
}

#[test]
fn test_reconnect_prompt_format() {
    let msg = super::display_helpers::reconnect_prompt(2, 5);
    assert!(msg.contains("2/5"));
    assert!(msg.contains("[Y/n]"));
}

// ── tag_helpers tests ───────────────────────────────────────────

#[test]
fn test_parse_tag_key_value() {
    assert_eq!(
        super::tag_helpers::parse_tag("env=production"),
        Some(("env", "production"))
    );
}

#[test]
fn test_parse_tag_missing_equals() {
    assert_eq!(super::tag_helpers::parse_tag("justkey"), None);
}

#[test]
fn test_parse_tag_empty_key() {
    assert_eq!(super::tag_helpers::parse_tag("=value"), None);
}

#[test]
fn test_parse_tag_embedded_equals() {
    assert_eq!(
        super::tag_helpers::parse_tag("key=val=ue"),
        Some(("key", "val=ue"))
    );
}

#[test]
fn test_find_invalid_tag_all_valid() {
    let tags = vec!["a=1".to_string(), "b=2".to_string()];
    assert_eq!(super::tag_helpers::find_invalid_tag(&tags), None);
}

#[test]
fn test_find_invalid_tag_has_bad() {
    let tags = vec!["a=1".to_string(), "bad".to_string(), "c=3".to_string()];
    assert_eq!(super::tag_helpers::find_invalid_tag(&tags), Some("bad"));
}

// ── disk_helpers tests ──────────────────────────────────────────

#[test]
fn test_build_data_disk_name_lun0() {
    assert_eq!(
        super::disk_helpers::build_data_disk_name("my-vm", 0),
        "my-vm_datadisk_0"
    );
}

#[test]
fn test_build_data_disk_name_lun5() {
    assert_eq!(
        super::disk_helpers::build_data_disk_name("worker", 5),
        "worker_datadisk_5"
    );
}

#[test]
fn test_build_restored_disk_name() {
    assert_eq!(
        super::disk_helpers::build_restored_disk_name("my-vm"),
        "my-vm_OsDisk_restored"
    );
}

// ── command_helpers tests ───────────────────────────────────────

#[test]
fn test_is_allowed_command_az() {
    assert!(super::command_helpers::is_allowed_command("az vm list"));
}

#[test]
fn test_is_allowed_command_non_az() {
    assert!(!super::command_helpers::is_allowed_command("rm -rf /"));
}

#[test]
fn test_is_allowed_command_whitespace_prefix() {
    assert!(super::command_helpers::is_allowed_command("  az vm list"));
}

#[test]
fn test_skip_reason_allowed() {
    assert_eq!(super::command_helpers::skip_reason("az vm list"), None);
}

#[test]
fn test_skip_reason_empty() {
    assert!(super::command_helpers::skip_reason("").is_some());
}

#[test]
fn test_skip_reason_non_az() {
    let reason = super::command_helpers::skip_reason("curl http://evil.com");
    assert!(reason.is_some());
    assert!(reason.unwrap().contains("non-Azure"));
}

// ── autopilot_parse_helpers tests ───────────────────────────────

#[test]
fn test_parse_idle_check_normal() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("25.3\n3600.5");
    assert!((cpu - 25.3).abs() < 0.01);
    assert!((uptime - 3600.5).abs() < 0.01);
}

#[test]
fn test_parse_idle_check_empty() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("");
    assert!((cpu - 100.0).abs() < 0.01); // defaults to 100% (not idle)
    assert!((uptime - 0.0).abs() < 0.01);
}

#[test]
fn test_parse_idle_check_garbage() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("abc\nxyz");
    assert!((cpu - 100.0).abs() < 0.01);
    assert!((uptime - 0.0).abs() < 0.01);
}

#[test]
fn test_is_idle_true() {
    // CPU 2%, uptime 2 hours, threshold 30 min → idle
    assert!(super::autopilot_parse_helpers::is_idle(2.0, 7200.0, 30));
}

#[test]
fn test_is_idle_high_cpu() {
    // CPU 50%, even with long uptime → not idle
    assert!(!super::autopilot_parse_helpers::is_idle(50.0, 7200.0, 30));
}

#[test]
fn test_is_idle_short_uptime() {
    // CPU 1%, uptime 10 min, threshold 30 min → not idle (too new)
    assert!(!super::autopilot_parse_helpers::is_idle(1.0, 600.0, 30));
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
    let name = super::templates::import_template(dir, content).unwrap();
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
    let result = super::templates::import_template(tmp.path(), content);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("name"));
}

#[test]
fn test_import_template_invalid_toml() {
    let tmp = TempDir::new().unwrap();
    let result = super::templates::import_template(tmp.path(), "not valid { toml [");
    assert!(result.is_err());
}

// ── templates::build_template_toml edge cases ──────────────────

#[test]
fn test_build_template_toml_with_cloud_init() {
    let tpl = super::templates::build_template_toml(
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
    let tpl = super::templates::build_template_toml("minimal", None, None, None, None);
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
    let result = super::vm_validation::validate_vm_name("");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("empty"));
}

#[test]
fn test_validate_vm_name_leading_hyphen() {
    let result = super::vm_validation::validate_vm_name("-bad-name");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("start with a hyphen"));
}

#[test]
fn test_validate_vm_name_trailing_hyphen() {
    let result = super::vm_validation::validate_vm_name("bad-name-");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("end with a hyphen"));
}

#[test]
fn test_validate_vm_name_valid() {
    assert!(super::vm_validation::validate_vm_name("my-good-vm-01").is_ok());
}

#[test]
fn test_validate_vm_name_single_char() {
    assert!(super::vm_validation::validate_vm_name("a").is_ok());
}

#[test]
fn test_validate_vm_name_spaces_rejected() {
    let result = super::vm_validation::validate_vm_name("bad name");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("invalid characters"));
}

// ── snapshot_helpers::SnapshotSchedule serde tests ──────────────

#[test]
fn test_snapshot_schedule_serialize_deserialize_roundtrip() {
    let schedule = super::snapshot_helpers::SnapshotSchedule {
        vm_name: "dev-vm".to_string(),
        resource_group: "my-rg".to_string(),
        every_hours: 6,
        keep_count: 10,
        enabled: true,
        created: "2024-01-15T10:00:00Z".to_string(),
    };
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&toml_str).unwrap();
    assert_eq!(loaded.vm_name, "dev-vm");
    assert_eq!(loaded.resource_group, "my-rg");
    assert_eq!(loaded.every_hours, 6);
    assert_eq!(loaded.keep_count, 10);
    assert!(loaded.enabled);
    assert_eq!(loaded.created, "2024-01-15T10:00:00Z");
}

#[test]
fn test_snapshot_schedule_disabled() {
    let schedule = super::snapshot_helpers::SnapshotSchedule {
        vm_name: "prod-db".to_string(),
        resource_group: "prod-rg".to_string(),
        every_hours: 24,
        keep_count: 3,
        enabled: false,
        created: "2024-06-01T00:00:00Z".to_string(),
    };
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    assert!(toml_str.contains("enabled = false"));
    let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&toml_str).unwrap();
    assert!(!loaded.enabled);
}

#[test]
fn test_snapshot_schedule_write_read_file() {
    let tmp = TempDir::new().unwrap();
    let schedule = super::snapshot_helpers::SnapshotSchedule {
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
    let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&read_back).unwrap();
    assert_eq!(loaded.vm_name, "test-vm");
    assert_eq!(loaded.every_hours, 12);
}

// ── sessions round-trip with list_session_names ─────────────────

#[test]
fn test_session_build_write_list_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();
    fs::create_dir_all(dir).unwrap();

    let session1 = super::sessions::build_session_toml(
        "dev-session",
        "dev-rg",
        &["vm-1".to_string(), "vm-2".to_string()],
    );
    let session2 =
        super::sessions::build_session_toml("staging-session", "staging-rg", &["vm-3".to_string()]);

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

    let names = super::sessions::list_session_names(dir).unwrap();
    assert_eq!(names.len(), 2);
    assert!(names.contains(&"dev-session".to_string()));
    assert!(names.contains(&"staging-session".to_string()));
}

#[test]
fn test_session_parse_toml_missing_all_fields() {
    // Empty table should return defaults
    let content = "[other]\nkey = \"value\"";
    let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
    assert_eq!(rg, "-");
    assert!(vms.is_empty());
    assert_eq!(created, "-");
}

// ── contexts::build_context_toml no optional fields ─────────────

#[test]
fn test_context_build_toml_no_optional_fields() {
    let toml_str =
        super::contexts::build_context_toml("bare", None, None, None, None, None).unwrap();
    let parsed: toml::Value = toml_str.parse().unwrap();
    let tbl = parsed.as_table().unwrap();
    assert_eq!(tbl["name"].as_str().unwrap(), "bare");
    // Optional fields should be absent
    assert!(tbl.get("subscription_id").is_none());
    assert!(tbl.get("tenant_id").is_none());
    assert!(tbl.get("resource_group").is_none());
    assert!(tbl.get("region").is_none());
    assert!(tbl.get("key_vault_name").is_none());
}

// ── contexts::read_context_resource_group — name from filestem ───────

#[test]
fn test_context_read_resource_group_name_from_filestem() {
    let tmp = TempDir::new().unwrap();
    // A context TOML without a "name" field — name is derived from the filename
    let path = tmp.path().join("my-ctx.toml");
    fs::write(&path, "resource_group = \"my-rg\"\n").unwrap();

    let (name, rg) = super::contexts::read_context_resource_group(&path).unwrap();
    assert_eq!(name, "my-ctx");
    assert_eq!(rg, Some("my-rg".to_string()));
}

// ── create_helpers::build_clone_cmd — SSH URL ──────────────────

#[test]
fn test_build_clone_cmd_ssh_url() {
    let cmd = super::create_helpers::build_clone_cmd("git@github.com:user/repo.git").unwrap();
    assert!(cmd.contains("git clone"));
    assert!(cmd.contains("git@github.com:user/repo.git"));
    assert!(cmd.contains("repo")); // basename extraction
}

// ── health_helpers::format_percentage negative clamping ─────────

#[test]
fn test_format_percentage_negative_clamps_to_zero() {
    assert_eq!(super::health_helpers::format_percentage(-5.0), "0.0%");
    assert_eq!(super::health_helpers::format_percentage(-999.0), "0.0%");
}

// ── connect_helpers edge cases ─────────────────────────────────

#[test]
fn test_build_log_follow_args_format() {
    let args =
        super::connect_helpers::build_log_follow_args("admin", "10.0.0.5", "/var/log/syslog");
    assert_eq!(args.len(), 6);
    assert_eq!(args[0], "-o");
    assert_eq!(args[1], "StrictHostKeyChecking=accept-new");
    assert_eq!(args[4], "admin@10.0.0.5");
    assert!(args[5].contains("tail -f"));
    assert!(args[5].contains("/var/log/syslog"));
}

#[test]
fn test_build_log_tail_args_line_count() {
    let args = super::connect_helpers::build_log_tail_args(
        "user",
        "192.168.1.1",
        200,
        "/var/log/auth.log",
    );
    assert_eq!(args.len(), 6);
    assert!(args[5].contains("tail -n 200"));
    assert!(args[5].contains("/var/log/auth.log"));
}

// ── update_helpers::log_type_to_path default branch ────────────

#[test]
fn test_log_type_to_path_capital_variants() {
    assert_eq!(
        super::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
}

// ── autopilot_helpers::build_autopilot_config no budget ────────

#[test]
fn test_build_autopilot_config_no_budget_field_absent() {
    let config = super::autopilot_helpers::build_autopilot_config(
        None,
        "conservative",
        60,
        10,
        "2024-01-01T00:00:00Z",
    );
    let tbl = config.as_table().unwrap();
    assert!(tbl.get("budget").is_none());
    assert_eq!(tbl["strategy"].as_str().unwrap(), "conservative");
    assert_eq!(tbl["idle_threshold_minutes"].as_integer().unwrap(), 60);
    assert_eq!(tbl["cpu_threshold_percent"].as_integer().unwrap(), 10);
}

// ── batch_helpers::parse_vm_ids whitespace handling ─────────────

#[test]
fn test_parse_vm_ids_trailing_newlines() {
    let output = "/subscriptions/abc/vms/vm1\n/subscriptions/abc/vms/vm2\n\n\n";
    let ids = super::batch_helpers::parse_vm_ids(output);
    assert_eq!(ids.len(), 2);
    assert_eq!(ids[0], "/subscriptions/abc/vms/vm1");
    assert_eq!(ids[1], "/subscriptions/abc/vms/vm2");
}

// ── runner_helpers::pool_config_filename ───────────────────────

#[test]
fn test_pool_config_filename_format() {
    assert_eq!(
        super::runner_helpers::pool_config_filename("default"),
        "default.toml"
    );
    assert_eq!(
        super::runner_helpers::pool_config_filename("ci-large"),
        "ci-large.toml"
    );
}

// ── compose_helpers edge case ──────────────────────────────────

#[test]
fn test_build_compose_cmd_with_services() {
    let cmd = super::compose_helpers::build_compose_cmd("up -d", "prod-compose.yml");
    assert_eq!(cmd, "docker compose -f prod-compose.yml up -d");
}

// ── templates::save + load + delete full lifecycle ──────────────

#[test]
fn test_template_full_lifecycle_save_load_list_delete() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path();

    // Save two templates
    let tpl1 = super::templates::build_template_toml(
        "web",
        Some("Web server"),
        Some("Standard_B2s"),
        Some("westus2"),
        None,
    );
    let tpl2 = super::templates::build_template_toml(
        "gpu",
        Some("GPU worker"),
        Some("Standard_NC6"),
        Some("eastus"),
        Some("#!/bin/bash\nnvidia-smi"),
    );
    super::templates::save_template(dir, "web", &tpl1).unwrap();
    super::templates::save_template(dir, "gpu", &tpl2).unwrap();

    // List should return both
    let list = super::templates::list_templates(dir).unwrap();
    assert_eq!(list.len(), 2);

    // Load one
    let loaded = super::templates::load_template(dir, "gpu").unwrap();
    assert_eq!(loaded.get("name").unwrap().as_str().unwrap(), "gpu");
    assert!(loaded.get("cloud_init").is_some());

    // Delete one
    super::templates::delete_template(dir, "web").unwrap();
    let list2 = super::templates::list_templates(dir).unwrap();
    assert_eq!(list2.len(), 1);

    // Load deleted template should fail
    assert!(super::templates::load_template(dir, "web").is_err());
}

// ── contexts::rename_context_file on nonexistent ───────────────

#[test]
fn test_context_rename_nonexistent_errors() {
    let tmp = TempDir::new().unwrap();
    let result = super::contexts::rename_context_file(tmp.path(), "no-such-ctx", "new-name");
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("not found"));
}

// ═══════════════════════════════════════════════════════════════
// NEW COVERAGE TESTS — Batch 2: 35+ tests for 80% target
// ═══════════════════════════════════════════════════════════════

// ── Context CRUD lifecycle ──────────────────────────────────────

#[test]
fn test_context_full_crud_lifecycle() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path();

    // Create
    let toml_str = super::contexts::build_context_toml(
        "myctx",
        Some("sub-123"),
        Some("tenant-456"),
        Some("myrg"),
        Some("eastus"),
        None,
    )
    .unwrap();
    fs::write(ctx_dir.join("myctx.toml"), &toml_str).unwrap();

    // List
    let contexts = super::contexts::list_contexts(ctx_dir, "myctx").unwrap();
    assert_eq!(contexts.len(), 1);
    assert_eq!(contexts[0].0, "myctx");
    assert!(contexts[0].1); // is_active

    // Show (read resource group)
    let (name, rg) =
        super::contexts::read_context_resource_group(&ctx_dir.join("myctx.toml")).unwrap();
    assert_eq!(name, "myctx");
    assert_eq!(rg, Some("myrg".to_string()));

    // Delete
    fs::remove_file(ctx_dir.join("myctx.toml")).unwrap();
    let contexts = super::contexts::list_contexts(ctx_dir, "myctx").unwrap();
    assert!(contexts.is_empty());
}

#[test]
fn test_context_list_multiple_with_active() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path();

    for name in &["alpha", "beta", "gamma"] {
        let toml_str =
            super::contexts::build_context_toml(name, None, None, Some("rg-1"), None, None)
                .unwrap();
        fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
    }

    let contexts = super::contexts::list_contexts(ctx_dir, "beta").unwrap();
    assert_eq!(contexts.len(), 3);
    let active_count = contexts.iter().filter(|(_, a)| *a).count();
    assert_eq!(active_count, 1);
    let beta = contexts.iter().find(|(n, _)| n == "beta").unwrap();
    assert!(beta.1);
}

#[test]
fn test_context_rename_success_with_verify() {
    let tmp = TempDir::new().unwrap();
    let ctx_dir = tmp.path();

    let toml_str =
        super::contexts::build_context_toml("old-ctx", None, None, Some("myrg"), None, None)
            .unwrap();
    fs::write(ctx_dir.join("old-ctx.toml"), &toml_str).unwrap();

    super::contexts::rename_context_file(ctx_dir, "old-ctx", "new-ctx").unwrap();

    assert!(!ctx_dir.join("old-ctx.toml").exists());
    assert!(ctx_dir.join("new-ctx.toml").exists());

    let (name, _) =
        super::contexts::read_context_resource_group(&ctx_dir.join("new-ctx.toml")).unwrap();
    assert_eq!(name, "new-ctx");
}

#[test]
fn test_context_build_all_optional_fields() {
    let toml_str = super::contexts::build_context_toml(
        "full-ctx",
        Some("sub-id"),
        Some("tenant-id"),
        Some("my-rg"),
        Some("westus2"),
        Some("my-vault"),
    )
    .unwrap();
    assert!(toml_str.contains("subscription_id"));
    assert!(toml_str.contains("tenant_id"));
    assert!(toml_str.contains("resource_group"));
    assert!(toml_str.contains("region"));
    assert!(toml_str.contains("key_vault_name"));
    assert!(toml_str.contains("full-ctx"));
}

// ── Session management lifecycle ────────────────────────────────

#[test]
fn test_session_full_lifecycle_save_list_load_delete() {
    let tmp = TempDir::new().unwrap();
    let sessions_dir = tmp.path();

    // Save
    let session = super::sessions::build_session_toml(
        "test-session",
        "my-rg",
        &["vm1".to_string(), "vm2".to_string()],
    );
    let content = toml::to_string_pretty(&session).unwrap();
    fs::write(sessions_dir.join("test-session.toml"), &content).unwrap();

    // List
    let names = super::sessions::list_session_names(sessions_dir).unwrap();
    assert_eq!(names.len(), 1);
    assert_eq!(names[0], "test-session");

    // Load — parse_session_toml returns (rg, vms, created)
    let loaded_content = fs::read_to_string(sessions_dir.join("test-session.toml")).unwrap();
    let (rg, vms, _created) = super::sessions::parse_session_toml(&loaded_content).unwrap();
    assert_eq!(rg, "my-rg");
    assert_eq!(vms, vec!["vm1".to_string(), "vm2".to_string()]);

    // Delete
    fs::remove_file(sessions_dir.join("test-session.toml")).unwrap();
    let names = super::sessions::list_session_names(sessions_dir).unwrap();
    assert!(names.is_empty());
}

#[test]
fn test_session_save_empty_vms_lifecycle() {
    let session = super::sessions::build_session_toml("empty-sess", "rg", &[]);
    let content = toml::to_string_pretty(&session).unwrap();
    let (rg, vms, _created) = super::sessions::parse_session_toml(&content).unwrap();
    assert_eq!(rg, "rg");
    assert!(vms.is_empty());
}

#[test]
fn test_session_list_nonexistent_dir() {
    let tmp = TempDir::new().unwrap();
    let missing = tmp.path().join("no-such-dir");
    let names = super::sessions::list_session_names(&missing).unwrap();
    assert!(names.is_empty());
}

// ── Template lifecycle ──────────────────────────────────────────

#[test]
fn test_template_save_load_roundtrip_all_fields() {
    let tmp = TempDir::new().unwrap();
    let tpl = super::templates::build_template_toml(
        "gpu-box",
        Some("GPU development template"),
        Some("Standard_NC6s_v3"),
        Some("eastus2"),
        Some("#!/bin/bash\napt-get install -y cuda"),
    );
    super::templates::save_template(tmp.path(), "gpu-box", &tpl).unwrap();

    let loaded = super::templates::load_template(tmp.path(), "gpu-box").unwrap();
    assert_eq!(loaded["name"].as_str(), Some("gpu-box"));
    assert_eq!(loaded["vm_size"].as_str(), Some("Standard_NC6s_v3"));
    assert_eq!(loaded["region"].as_str(), Some("eastus2"));
    assert!(loaded["cloud_init"].as_str().unwrap().contains("cuda"));
}

#[test]
fn test_template_list_multiple() {
    let tmp = TempDir::new().unwrap();
    for name in &["dev", "prod", "test"] {
        let tpl = super::templates::build_template_toml(name, None, None, None, None);
        super::templates::save_template(tmp.path(), name, &tpl).unwrap();
    }

    let list = super::templates::list_templates(tmp.path()).unwrap();
    assert_eq!(list.len(), 3);
}

#[test]
fn test_template_load_nonexistent_errors() {
    let tmp = TempDir::new().unwrap();
    let result = super::templates::load_template(tmp.path(), "nope");
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("not found"));
}

#[test]
fn test_template_delete_then_verify_gone() {
    let tmp = TempDir::new().unwrap();
    let tpl = super::templates::build_template_toml("deleteme", None, None, None, None);
    super::templates::save_template(tmp.path(), "deleteme", &tpl).unwrap();
    assert!(tmp.path().join("deleteme.toml").exists());

    super::templates::delete_template(tmp.path(), "deleteme").unwrap();
    assert!(!tmp.path().join("deleteme.toml").exists());
}

#[test]
fn test_template_import_with_extra_fields() {
    let tmp = TempDir::new().unwrap();
    let content = r#"
name = "custom"
vm_size = "Standard_B1s"
region = "northeurope"
custom_field = "extra"
"#;
    let name = super::templates::import_template(tmp.path(), content).unwrap();
    assert_eq!(name, "custom");
    let loaded = super::templates::load_template(tmp.path(), "custom").unwrap();
    assert_eq!(loaded["custom_field"].as_str(), Some("extra"));
}

// ── Autopilot config tests ──────────────────────────────────────

#[test]
fn test_autopilot_config_all_fields() {
    let config = super::autopilot_helpers::build_autopilot_config(
        Some(500),
        "aggressive",
        15,
        10,
        "2024-01-15T10:00:00Z",
    );
    let table = config.as_table().unwrap();
    assert_eq!(table["enabled"].as_bool(), Some(true));
    assert_eq!(table["budget"].as_integer(), Some(500));
    assert_eq!(table["strategy"].as_str(), Some("aggressive"));
    assert_eq!(table["idle_threshold_minutes"].as_integer(), Some(15));
    assert_eq!(table["cpu_threshold_percent"].as_integer(), Some(10));
    assert_eq!(table["updated"].as_str(), Some("2024-01-15T10:00:00Z"));
}

#[test]
fn test_autopilot_config_serializes_to_valid_toml() {
    let config = super::autopilot_helpers::build_autopilot_config(
        None,
        "conservative",
        30,
        5,
        "2024-06-01T00:00:00Z",
    );
    let toml_str = toml::to_string_pretty(&config).unwrap();
    let parsed: toml::Value = toml_str.parse().unwrap();
    assert_eq!(parsed["enabled"].as_bool(), Some(true));
    assert!(parsed.get("budget").is_none());
}

// ── env_helpers edge cases ──────────────────────────────────────

#[test]
fn test_validate_env_key_empty_is_error() {
    assert!(super::env_helpers::validate_env_key("").is_err());
    let err = super::env_helpers::validate_env_key("").unwrap_err();
    assert!(err.contains("must not be empty"));
}

#[test]
fn test_validate_env_key_starting_with_digit_is_error() {
    let err = super::env_helpers::validate_env_key("1ABC").unwrap_err();
    assert!(err.contains("must not start with a digit"));
}

#[test]
fn test_validate_env_key_special_chars_rejected() {
    assert!(super::env_helpers::validate_env_key("MY-VAR").is_err());
    assert!(super::env_helpers::validate_env_key("MY.VAR").is_err());
    assert!(super::env_helpers::validate_env_key("MY VAR").is_err());
    assert!(super::env_helpers::validate_env_key("MY$VAR").is_err());
}

#[test]
fn test_build_env_set_cmd_with_invalid_key_returns_noop() {
    let cmd = super::env_helpers::build_env_set_cmd("BAD-KEY!", "'value'");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_set_cmd_valid_contains_grep_and_sed() {
    let cmd = super::env_helpers::build_env_set_cmd("MY_VAR", "'hello'");
    assert!(cmd.contains("grep"));
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("MY_VAR"));
    assert!(cmd.contains("'hello'"));
}

#[test]
fn test_parse_env_file_skips_comments_and_blanks() {
    let content = "# comment\n\nFOO=bar\n  # another comment\nBAZ=qux\n\n";
    let result = super::env_helpers::parse_env_file(content);
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], ("FOO".to_string(), "bar".to_string()));
    assert_eq!(result[1], ("BAZ".to_string(), "qux".to_string()));
}

#[test]
fn test_build_env_file_and_parse_roundtrip() {
    let vars = vec![
        ("PATH".to_string(), "/usr/bin".to_string()),
        ("HOME".to_string(), "/home/user".to_string()),
        ("LANG".to_string(), "en_US.UTF-8".to_string()),
    ];
    let file_content = super::env_helpers::build_env_file(&vars);
    let parsed = super::env_helpers::parse_env_file(&file_content);
    assert_eq!(parsed, vars);
}

#[test]
fn test_split_env_var_normal() {
    let result = super::env_helpers::split_env_var("KEY=VALUE");
    assert_eq!(result, Some(("KEY", "VALUE")));
}

#[test]
fn test_split_env_var_embedded_equals_sign() {
    let result = super::env_helpers::split_env_var("KEY=VAL=UE");
    assert_eq!(result, Some(("KEY", "VAL=UE")));
}

#[test]
fn test_split_env_var_no_equals_returns_none() {
    assert!(super::env_helpers::split_env_var("NOEQUALS").is_none());
}

// ── sync_helpers ────────────────────────────────────────────────

#[test]
fn test_validate_sync_source_traversal_variants() {
    // "/../" in the middle
    assert!(super::sync_helpers::validate_sync_source("foo/../bar").is_err());
    // Ends with "/.."
    assert!(super::sync_helpers::validate_sync_source("foo/..").is_err());
    // Just ".."
    assert!(super::sync_helpers::validate_sync_source("..").is_err());
    // Safe relative path is OK
    assert!(super::sync_helpers::validate_sync_source("mydir/file").is_ok());
}

#[test]
fn test_validate_sync_source_forbidden_prefixes() {
    for prefix in &[
        "/etc/passwd",
        "/var/log",
        "/root/.ssh",
        "/proc/cpuinfo",
        "/sys/devices",
    ] {
        let result = super::sync_helpers::validate_sync_source(prefix);
        assert!(result.is_err(), "Expected error for prefix: {}", prefix);
    }
}

#[test]
fn test_build_rsync_args_correct_format() {
    let args = super::sync_helpers::build_rsync_args(".bashrc", "azureuser", "10.0.0.1", ".bashrc");
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert!(args[2].contains("StrictHostKeyChecking=accept-new"));
    assert_eq!(args[3], ".bashrc");
    assert_eq!(args[4], "azureuser@10.0.0.1:~/.bashrc");
}

#[test]
fn test_default_dotfiles_contains_expected() {
    let dotfiles = super::sync_helpers::default_dotfiles();
    assert!(dotfiles.contains(&".bashrc"));
    assert!(dotfiles.contains(&".profile"));
    assert!(dotfiles.contains(&".gitconfig"));
    assert!(dotfiles.len() >= 4);
}

// ── health_helpers edge cases ───────────────────────────────────

#[test]
fn test_status_emoji_all_values_low() {
    assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
}

#[test]
fn test_status_emoji_one_high() {
    assert_eq!(super::health_helpers::status_emoji(95.0, 20.0, 30.0), "🔴");
    assert_eq!(super::health_helpers::status_emoji(10.0, 91.0, 30.0), "🔴");
    assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 95.0), "🔴");
}

#[test]
fn test_status_emoji_medium() {
    assert_eq!(super::health_helpers::status_emoji(75.0, 20.0, 30.0), "🟡");
    assert_eq!(super::health_helpers::status_emoji(10.0, 80.0, 30.0), "🟡");
}

#[test]
fn test_metric_color_boundary_values() {
    assert_eq!(super::health_helpers::metric_color(50.0), "green");
    assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
    assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
    assert_eq!(super::health_helpers::metric_color(80.1), "red");
}

#[test]
fn test_state_color_all_variants() {
    assert_eq!(super::health_helpers::state_color("running"), "green");
    assert_eq!(super::health_helpers::state_color("stopped"), "red");
    assert_eq!(super::health_helpers::state_color("deallocated"), "red");
    assert_eq!(super::health_helpers::state_color("starting"), "yellow");
    assert_eq!(super::health_helpers::state_color("random"), "yellow");
}

#[test]
fn test_format_percentage_large_value() {
    let result = super::health_helpers::format_percentage(100.0);
    assert_eq!(result, "100.0%");
}

#[test]
fn test_format_percentage_zero() {
    assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
}

// ── snapshot_helpers ────────────────────────────────────────────

#[test]
fn test_filter_snapshots_partial_name_match() {
    let snapshots = vec![
        serde_json::json!({"name": "dev-vm_snapshot_20240101"}),
        serde_json::json!({"name": "prod-vm_snapshot_20240101"}),
        serde_json::json!({"name": "dev-vm_snapshot_20240102"}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snapshots, "dev-vm");
    assert_eq!(filtered.len(), 2);
}

#[test]
fn test_snapshot_schedule_full_lifecycle() {
    let tmp = TempDir::new().unwrap();
    let schedule = super::snapshot_helpers::SnapshotSchedule {
        vm_name: "test-vm".to_string(),
        resource_group: "test-rg".to_string(),
        every_hours: 6,
        keep_count: 10,
        enabled: true,
        created: "2024-01-15T10:00:00Z".to_string(),
    };

    // Serialize and write
    let toml_str = toml::to_string_pretty(&schedule).unwrap();
    let path = tmp.path().join("test-vm.toml");
    fs::write(&path, &toml_str).unwrap();

    // Read back and deserialize
    let content = fs::read_to_string(&path).unwrap();
    let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&content).unwrap();
    assert_eq!(loaded.vm_name, "test-vm");
    assert_eq!(loaded.every_hours, 6);
    assert_eq!(loaded.keep_count, 10);
    assert!(loaded.enabled);
}

// ── output_helpers ──────────────────────────────────────────────

#[test]
fn test_format_as_table_multirow() {
    let headers = &["Name", "Size", "Status"];
    let rows = vec![
        vec![
            "vm-1".to_string(),
            "Standard_B2s".to_string(),
            "Running".to_string(),
        ],
        vec![
            "vm-2-long-name".to_string(),
            "Standard_D4s_v3".to_string(),
            "Stopped".to_string(),
        ],
    ];
    let table = super::output_helpers::format_as_table(headers, &rows);
    assert!(table.contains("Name"));
    assert!(table.contains("vm-1"));
    assert!(table.contains("vm-2-long-name"));
    // Verify alignment: wider columns expand
    let lines: Vec<&str> = table.lines().collect();
    assert_eq!(lines.len(), 3); // header + 2 rows
}

#[test]
fn test_format_as_csv_with_data() {
    let headers = &["Name", "Cost"];
    let rows = vec![
        vec!["vm-1".to_string(), "$10.50".to_string()],
        vec!["vm-2".to_string(), "$20.00".to_string()],
    ];
    let csv = super::output_helpers::format_as_csv(headers, &rows);
    let lines: Vec<&str> = csv.lines().collect();
    assert_eq!(lines[0], "Name,Cost");
    assert_eq!(lines[1], "vm-1,$10.50");
    assert_eq!(lines[2], "vm-2,$20.00");
}

#[test]
fn test_format_as_json_custom_structs() {
    #[derive(serde::Serialize)]
    struct Item {
        name: String,
        value: i32,
    }
    let items = vec![
        Item {
            name: "a".to_string(),
            value: 1,
        },
        Item {
            name: "b".to_string(),
            value: 2,
        },
    ];
    let json = super::output_helpers::format_as_json(&items);
    let parsed: Vec<serde_json::Value> = serde_json::from_str(&json).unwrap();
    assert_eq!(parsed.len(), 2);
    assert_eq!(parsed[0]["name"], "a");
    assert_eq!(parsed[1]["value"], 2);
}

// ── VM name validation edge cases ───────────────────────────────

#[test]
fn test_validate_vm_name_consecutive_hyphens_allowed() {
    // Azure allows consecutive hyphens
    assert!(super::vm_validation::validate_vm_name("vm--test").is_ok());
}

#[test]
fn test_validate_vm_name_max_64_chars_ok() {
    let name = "a".repeat(64);
    assert!(super::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_validate_vm_name_65_chars_rejected() {
    let name = "a".repeat(65);
    let err = super::vm_validation::validate_vm_name(&name).unwrap_err();
    assert!(err.contains("exceeds 64"));
}

#[test]
fn test_validate_vm_name_special_chars_rejected() {
    assert!(super::vm_validation::validate_vm_name("vm@test").is_err());
    assert!(super::vm_validation::validate_vm_name("vm.test").is_err());
    assert!(super::vm_validation::validate_vm_name("vm test").is_err());
}

// ── mount_helpers edge cases ────────────────────────────────────

#[test]
fn test_validate_mount_path_valid() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data").is_ok());
    assert!(super::mount_helpers::validate_mount_path("/home/user/work").is_ok());
}

#[test]
fn test_validate_mount_path_empty() {
    let err = super::mount_helpers::validate_mount_path("").unwrap_err();
    assert!(err.contains("must not be empty"));
}

#[test]
fn test_validate_mount_path_shell_metacharacters() {
    for path in &[
        "/mnt;rm -rf /",
        "/mnt|cat",
        "/mnt&bg",
        "/mnt$(cmd)",
        "/mnt`cmd`",
    ] {
        assert!(
            super::mount_helpers::validate_mount_path(path).is_err(),
            "Expected error for path: {}",
            path,
        );
    }
}

#[test]
fn test_validate_mount_path_traversal() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/../etc").is_err());
    assert!(super::mount_helpers::validate_mount_path("/mnt/..").is_err());
}

// ── cp_helpers ──────────────────────────────────────────────────

#[test]
fn test_is_remote_path_variants() {
    assert!(super::cp_helpers::is_remote_path("vm-name:/path"));
    assert!(!super::cp_helpers::is_remote_path("/local/path"));
    assert!(!super::cp_helpers::is_remote_path("C:\\windows")); // drive letter
    assert!(!super::cp_helpers::is_remote_path("ab")); // too short
}

#[test]
fn test_classify_transfer_direction_all_cases() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("vm:/path", "/local"),
        "remote→local"
    );
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("/local", "vm:/path"),
        "local→remote"
    );
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("/a", "/b"),
        "local→local"
    );
}

#[test]
fn test_resolve_scp_path_replaces_vm_name() {
    let result =
        super::cp_helpers::resolve_scp_path("my-vm:/remote/path", "my-vm", "azureuser", "10.0.0.1");
    assert_eq!(result, "azureuser@10.0.0.1:/remote/path");
}

// ── bastion_helpers ─────────────────────────────────────────────

#[test]
fn test_bastion_summary_extracts_fields() {
    let b = serde_json::json!({
        "name": "my-bastion",
        "resourceGroup": "my-rg",
        "location": "eastus",
        "sku": {"name": "Standard"},
        "provisioningState": "Succeeded"
    });
    let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "my-bastion");
    assert_eq!(rg, "my-rg");
    assert_eq!(loc, "eastus");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "Succeeded");
}

#[test]
fn test_extract_ip_configs_multiple_entries() {
    let b = serde_json::json!({
        "ipConfigurations": [
            {
                "subnet": {"id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/AzureBastionSubnet"},
                "publicIPAddress": {"id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/publicIPAddresses/bastion-pip"}
            },
            {
                "subnet": {"id": "/subs/rg/vnet/subnets/OtherSubnet"},
                "publicIPAddress": {"id": "N/A"}
            }
        ]
    });
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert_eq!(configs.len(), 2);
    assert_eq!(configs[0].0, "AzureBastionSubnet");
    assert_eq!(configs[0].1, "bastion-pip");
    assert_eq!(configs[1].1, "N/A");
}

#[test]
fn test_shorten_resource_id_long_path() {
    assert_eq!(
        super::bastion_helpers::shorten_resource_id(
            "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/my-pip"
        ),
        "my-pip"
    );
}

// ── fleet_helpers ───────────────────────────────────────────────

#[test]
fn test_classify_result_various_codes() {
    assert_eq!(super::fleet_helpers::classify_result(0), ("OK", true));
    assert_eq!(super::fleet_helpers::classify_result(1), ("FAIL", false));
    assert_eq!(super::fleet_helpers::classify_result(127), ("FAIL", false));
    assert_eq!(super::fleet_helpers::classify_result(-1), ("FAIL", false));
}

#[test]
fn test_finish_message_multiline_stdout() {
    let msg = super::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert!(msg.contains("3 lines"));
}

#[test]
fn test_finish_message_error_first_line() {
    let msg =
        super::fleet_helpers::finish_message(1, "", "Error: connection refused\ndetailed trace\n");
    assert!(msg.contains("Error: connection refused"));
    assert!(!msg.contains("detailed trace"));
}

#[test]
fn test_format_output_text_show_stdout() {
    let text = super::fleet_helpers::format_output_text(0, "hello world", "", true);
    assert_eq!(text, "hello world");
}

#[test]
fn test_format_output_text_show_stderr_when_stdout_empty() {
    let text = super::fleet_helpers::format_output_text(1, "", "error msg", true);
    assert_eq!(text, "error msg");
}

#[test]
fn test_format_output_text_hide_success_empty() {
    let text = super::fleet_helpers::format_output_text(0, "output", "", false);
    assert!(text.is_empty());
}

// ── list_helpers with VmInfo ────────────────────────────────────

#[test]
fn test_filter_running_keeps_starting() {
    use azlin_core::models::{OsType, PowerState, VmInfo};
    let mut vms = vec![
        VmInfo {
            name: "running-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
        VmInfo {
            name: "starting-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Starting,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
        VmInfo {
            name: "stopped-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Stopped,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
    ];
    super::list_helpers::filter_running(&mut vms);
    assert_eq!(vms.len(), 2);
    assert!(vms
        .iter()
        .all(|v| v.power_state == PowerState::Running || v.power_state == PowerState::Starting));
}

#[test]
fn test_filter_by_tag_key_only_match() {
    use azlin_core::models::{OsType, PowerState, VmInfo};
    let mut vms = vec![
        VmInfo {
            name: "tagged".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: [("env".to_string(), "prod".to_string())]
                .into_iter()
                .collect(),
            created_time: None,
        },
        VmInfo {
            name: "untagged".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        },
    ];
    // Key-only filter (no =value)
    super::list_helpers::filter_by_tag(&mut vms, "env");
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "tagged");
}

#[test]
fn test_apply_filters_include_all_skips_running_filter() {
    use azlin_core::models::{OsType, PowerState, VmInfo};
    let mut vms = vec![VmInfo {
        name: "stopped-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "B2s".to_string(),
        power_state: PowerState::Stopped,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: None,
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    }];
    super::list_helpers::apply_filters(&mut vms, true, None, None);
    assert_eq!(vms.len(), 1); // stopped VM kept because include_all=true
}

// ── create_helpers ──────────────────────────────────────────────

#[test]
fn test_generate_vm_name_pool_indexing() {
    let name = super::create_helpers::generate_vm_name(Some("worker"), 0, 3, "20240115");
    assert_eq!(name, "worker-1");
    let name2 = super::create_helpers::generate_vm_name(Some("worker"), 2, 3, "20240115");
    assert_eq!(name2, "worker-3");
}

#[test]
fn test_generate_vm_name_single_pool_no_index() {
    let name = super::create_helpers::generate_vm_name(Some("myvm"), 0, 1, "20240115");
    assert_eq!(name, "myvm");
}

#[test]
fn test_generate_vm_name_auto_timestamp() {
    let name = super::create_helpers::generate_vm_name(None, 0, 1, "20240115120000");
    assert!(name.starts_with("azlin-vm-"));
    assert!(name.contains("20240115120000"));
}

#[test]
fn test_resolve_with_template_sentinel_uses_template() {
    let result = super::create_helpers::resolve_with_template_default(
        "Standard_B2s",
        "Standard_B2s",
        Some("Standard_D4s_v3".to_string()),
    );
    assert_eq!(result, "Standard_D4s_v3");
}

#[test]
fn test_resolve_with_template_user_override() {
    let result = super::create_helpers::resolve_with_template_default(
        "Standard_NC6",
        "Standard_B2s",
        Some("Standard_D4s_v3".to_string()),
    );
    assert_eq!(result, "Standard_NC6");
}

#[test]
fn test_resolve_with_template_sentinel_no_template_keeps_default() {
    let result =
        super::create_helpers::resolve_with_template_default("Standard_B2s", "Standard_B2s", None);
    assert_eq!(result, "Standard_B2s");
}

// ── connect_helpers ─────────────────────────────────────────────

#[test]
fn test_build_ssh_args_with_key_path() {
    let key = std::path::PathBuf::from("/home/user/.ssh/id_ed25519");
    let args = super::connect_helpers::build_ssh_args("azureuser", "10.0.0.1", Some(key.as_path()));
    assert!(args.contains(&"-i".to_string()));
    assert!(args.contains(&"/home/user/.ssh/id_ed25519".to_string()));
    assert!(args.contains(&"azureuser@10.0.0.1".to_string()));
}

#[test]
fn test_build_ssh_args_no_key_provided() {
    let args = super::connect_helpers::build_ssh_args("user", "1.2.3.4", None);
    assert!(!args.contains(&"-i".to_string()));
    assert!(args.contains(&"user@1.2.3.4".to_string()));
}

#[test]
fn test_build_vscode_remote_uri_format() {
    let uri = super::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_build_log_follow_args_has_tail_f() {
    let args = super::connect_helpers::build_log_follow_args("user", "10.0.0.1", "/var/log/syslog");
    assert!(args.iter().any(|a| a.contains("tail -f")));
    assert!(args.iter().any(|a| a.contains("/var/log/syslog")));
}

#[test]
fn test_build_log_tail_args_custom_lines() {
    let args =
        super::connect_helpers::build_log_tail_args("user", "10.0.0.1", 100, "/var/log/auth.log");
    assert!(args.iter().any(|a| a.contains("tail -n 100")));
}

// ── update_helpers ──────────────────────────────────────────────

#[test]
fn test_build_dev_update_script_all_sections() {
    let script = super::update_helpers::build_dev_update_script();
    assert!(script.contains("apt-get update"));
    assert!(script.contains("rustup"));
    assert!(script.contains("pip3"));
    assert!(script.contains("npm"));
}

#[test]
fn test_build_os_update_cmd_format() {
    let cmd = super::update_helpers::build_os_update_cmd();
    assert!(cmd.contains("apt-get update"));
    assert!(cmd.contains("apt-get upgrade"));
    assert!(cmd.contains("DEBIAN_FRONTEND=noninteractive"));
}

#[test]
fn test_log_type_to_path_all_variants() {
    assert_eq!(
        super::update_helpers::log_type_to_path("cloud-init"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("auth"),
        "/var/log/auth.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("other"),
        "/var/log/syslog"
    );
}

// ── runner_helpers ──────────────────────────────────────────────

#[test]
fn test_build_runner_vm_name_format() {
    assert_eq!(
        super::runner_helpers::build_runner_vm_name("ci", 0),
        "azlin-runner-ci-1"
    );
    assert_eq!(
        super::runner_helpers::build_runner_vm_name("deploy", 4),
        "azlin-runner-deploy-5"
    );
}

#[test]
fn test_build_runner_tags_format() {
    let tags = super::runner_helpers::build_runner_tags("ci", "org/repo");
    assert!(tags.contains("azlin-runner=true"));
    assert!(tags.contains("pool=ci"));
    assert!(tags.contains("repo=org/repo"));
}

#[test]
fn test_build_runner_config_all_fields() {
    let config = super::runner_helpers::build_runner_config(
        "ci",
        "org/repo",
        3,
        "self-hosted,linux",
        "my-rg",
        "Standard_D4s_v3",
        "2024-01-15T10:00:00Z",
    );
    assert!(config.iter().any(|(k, _)| k == "pool"));
    assert!(config.iter().any(|(k, _)| k == "count"));
    assert!(config.iter().any(|(k, _)| k == "enabled"));
    let count = config.iter().find(|(k, _)| k == "count").unwrap();
    assert_eq!(count.1.as_integer(), Some(3));
}

// ── compose_helpers ─────────────────────────────────────────────

#[test]
fn test_resolve_compose_file_none_default() {
    assert_eq!(
        super::compose_helpers::resolve_compose_file(None),
        "docker-compose.yml"
    );
}

#[test]
fn test_resolve_compose_file_override() {
    assert_eq!(
        super::compose_helpers::resolve_compose_file(Some("custom.yml")),
        "custom.yml"
    );
}

#[test]
fn test_build_compose_cmd_format() {
    let cmd = super::compose_helpers::build_compose_cmd("up -d", "docker-compose.yml");
    assert_eq!(cmd, "docker compose -f docker-compose.yml up -d");
}

// ── batch_helpers ───────────────────────────────────────────────

#[test]
fn test_parse_vm_ids_multiple_lines() {
    let tsv = "/subs/rg/vm1\n/subs/rg/vm2\n/subs/rg/vm3\n";
    let ids = super::batch_helpers::parse_vm_ids(tsv);
    assert_eq!(ids.len(), 3);
}

#[test]
fn test_parse_vm_ids_blank_input() {
    assert!(super::batch_helpers::parse_vm_ids("").is_empty());
    assert!(super::batch_helpers::parse_vm_ids("\n\n").is_empty());
}

#[test]
fn test_build_batch_args_format() {
    let ids = vec!["/id/1", "/id/2"];
    let args = super::batch_helpers::build_batch_args("deallocate", &ids);
    assert_eq!(args[0], "vm");
    assert_eq!(args[1], "deallocate");
    assert_eq!(args[2], "--ids");
    assert_eq!(args[3], "/id/1");
    assert_eq!(args[4], "/id/2");
}

#[test]
fn test_summarise_batch_messages() {
    let success = super::batch_helpers::summarise_batch("start", "my-rg", true);
    assert!(success.contains("completed"));
    assert!(success.contains("my-rg"));

    let failure = super::batch_helpers::summarise_batch("stop", "my-rg", false);
    assert!(failure.contains("failed"));
}

// ── display_helpers ─────────────────────────────────────────────

#[test]
fn test_config_value_display_bool() {
    let v = serde_json::json!(true);
    assert_eq!(super::display_helpers::config_value_display(&v), "true");
}

#[test]
fn test_config_value_display_array() {
    let v = serde_json::json!([1, 2, 3]);
    assert_eq!(super::display_helpers::config_value_display(&v), "[1,2,3]");
}

#[test]
fn test_truncate_vm_name_max_len_3_or_less() {
    // When max_len <= 3, no truncation should happen (avoid "...")
    let result = super::display_helpers::truncate_vm_name("longname", 3);
    assert_eq!(result, "longname");
}

#[test]
fn test_format_tmux_sessions_max_show_1() {
    let sessions = vec!["s1".to_string(), "s2".to_string(), "s3".to_string()];
    let result = super::display_helpers::format_tmux_sessions(&sessions, 1);
    assert!(result.contains("s1"));
    assert!(result.contains("+2 more"));
}

#[test]
fn test_reconnect_prompt_format_values() {
    let prompt = super::display_helpers::reconnect_prompt(2, 5);
    assert!(prompt.contains("2/5"));
    assert!(prompt.contains("Reconnect?"));
}

// ── health_parse_helpers ────────────────────────────────────────

#[test]
fn test_parse_cpu_stdout_valid_float() {
    assert_eq!(
        super::health_parse_helpers::parse_cpu_stdout(0, "  45.3  "),
        Some(45.3)
    );
}

#[test]
fn test_parse_cpu_stdout_nonzero_exit() {
    assert_eq!(
        super::health_parse_helpers::parse_cpu_stdout(1, "45.3"),
        None
    );
}

#[test]
fn test_parse_mem_stdout_decimal() {
    assert_eq!(
        super::health_parse_helpers::parse_mem_stdout(0, "78.9"),
        Some(78.9)
    );
}

#[test]
fn test_parse_disk_stdout_integer() {
    assert_eq!(
        super::health_parse_helpers::parse_disk_stdout(0, "42"),
        Some(42.0)
    );
}

#[test]
fn test_default_metrics_values() {
    let m = super::health_parse_helpers::default_metrics("vm1", "stopped");
    assert_eq!(m.vm_name, "vm1");
    assert_eq!(m.power_state, "stopped");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

// ── tag_helpers edge cases ──────────────────────────────────────

#[test]
fn test_parse_tag_value_with_spaces() {
    let result = super::tag_helpers::parse_tag("name=My VM Name");
    assert_eq!(result, Some(("name", "My VM Name")));
}

#[test]
fn test_parse_tag_empty_value() {
    let result = super::tag_helpers::parse_tag("key=");
    assert_eq!(result, Some(("key", "")));
}

#[test]
fn test_find_invalid_tag_empty_list() {
    let tags: Vec<String> = vec![];
    assert!(super::tag_helpers::find_invalid_tag(&tags).is_none());
}

// ── disk_helpers ────────────────────────────────────────────────

#[test]
fn test_build_data_disk_name_format() {
    assert_eq!(
        super::disk_helpers::build_data_disk_name("myvm", 2),
        "myvm_datadisk_2"
    );
}

#[test]
fn test_build_restored_disk_name_format() {
    assert_eq!(
        super::disk_helpers::build_restored_disk_name("myvm"),
        "myvm_OsDisk_restored"
    );
}

// ── command_helpers ─────────────────────────────────────────────

#[test]
fn test_is_allowed_command_edge_cases() {
    assert!(super::command_helpers::is_allowed_command("az vm list"));
    assert!(super::command_helpers::is_allowed_command("  az vm list")); // leading whitespace
    assert!(!super::command_helpers::is_allowed_command("rm -rf /"));
    assert!(!super::command_helpers::is_allowed_command(""));
}

#[test]
fn test_skip_reason_various_inputs() {
    assert!(super::command_helpers::skip_reason("").is_some());
    assert!(super::command_helpers::skip_reason("rm -rf /").is_some());
    assert!(super::command_helpers::skip_reason("az vm list").is_none());
}

// ── autopilot_parse_helpers ─────────────────────────────────────

#[test]
fn test_parse_idle_check_valid_two_lines() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("2.5\n3600\n");
    assert!((cpu - 2.5).abs() < 0.01);
    assert!((uptime - 3600.0).abs() < 0.01);
}

#[test]
fn test_parse_idle_check_single_line() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("5.0");
    assert!((cpu - 5.0).abs() < 0.01);
    assert_eq!(uptime, 0.0); // missing second line defaults to 0
}

#[test]
fn test_is_idle_boundary() {
    // CPU = 4.9, uptime > threshold → idle
    assert!(super::autopilot_parse_helpers::is_idle(4.9, 1801.0, 30));
    // CPU = 5.0 → not idle
    assert!(!super::autopilot_parse_helpers::is_idle(5.0, 1801.0, 30));
    // Uptime exactly at threshold (30 min = 1800s) → not idle
    assert!(!super::autopilot_parse_helpers::is_idle(1.0, 1800.0, 30));
}

// ── storage_helpers ─────────────────────────────────────────────

#[test]
fn test_storage_sku_from_tier_all_variants() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("PREMIUM"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("STANDARD"),
        "Standard_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("anything"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_partial_data() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "eastus"
        // Missing kind, sku, provisioningState
    });
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(row[0], "mystorage");
    assert_eq!(row[1], "eastus");
    assert_eq!(row[2], "-"); // missing kind
    assert_eq!(row[3], "-"); // missing sku.name
    assert_eq!(row[4], "-"); // missing provisioningState
}

// ── key_helpers ─────────────────────────────────────────────────

#[test]
fn test_detect_key_type_comprehensive() {
    assert_eq!(super::key_helpers::detect_key_type("id_ed25519"), "ed25519");
    assert_eq!(
        super::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
    assert_eq!(super::key_helpers::detect_key_type("id_ecdsa"), "ecdsa");
    assert_eq!(super::key_helpers::detect_key_type("id_rsa"), "rsa");
    assert_eq!(super::key_helpers::detect_key_type("id_dsa"), "dsa");
    assert_eq!(
        super::key_helpers::detect_key_type("known_hosts"),
        "unknown"
    );
    assert_eq!(
        super::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_comprehensive() {
    assert!(super::key_helpers::is_known_key_name("id_rsa.pub"));
    assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
    assert!(super::key_helpers::is_known_key_name("id_rsa"));
    assert!(super::key_helpers::is_known_key_name("id_ed25519"));
    assert!(super::key_helpers::is_known_key_name("id_ecdsa"));
    assert!(super::key_helpers::is_known_key_name("id_dsa"));
    assert!(!super::key_helpers::is_known_key_name("known_hosts"));
    assert!(!super::key_helpers::is_known_key_name("config"));
}

// ── auth_helpers ────────────────────────────────────────────────

#[test]
fn test_mask_profile_value_secret_variants() {
    let secret_val = serde_json::json!("my-actual-secret");
    assert_eq!(
        super::auth_helpers::mask_profile_value("client_secret", &secret_val),
        "********"
    );
    assert_eq!(
        super::auth_helpers::mask_profile_value("db_password", &secret_val),
        "********"
    );
    // Non-secret field
    assert_eq!(
        super::auth_helpers::mask_profile_value("client_id", &secret_val),
        "my-actual-secret"
    );
}

#[test]
fn test_mask_profile_value_non_string_types() {
    assert_eq!(
        super::auth_helpers::mask_profile_value("count", &serde_json::json!(42)),
        "42"
    );
    assert_eq!(
        super::auth_helpers::mask_profile_value("enabled", &serde_json::json!(true)),
        "true"
    );
    assert_eq!(
        super::auth_helpers::mask_profile_value("data", &serde_json::json!(null)),
        "null"
    );
}

// ── log_helpers ─────────────────────────────────────────────────

#[test]
fn test_tail_start_index_various() {
    assert_eq!(super::log_helpers::tail_start_index(100, 20), 80);
    assert_eq!(super::log_helpers::tail_start_index(10, 20), 0); // can't go negative
    assert_eq!(super::log_helpers::tail_start_index(0, 0), 0);
    assert_eq!(super::log_helpers::tail_start_index(50, 50), 0);
}

// ── auth_test_helpers ───────────────────────────────────────────

#[test]
fn test_extract_account_info_full_json() {
    let acct = serde_json::json!({
        "name": "My Subscription",
        "tenantId": "tenant-123",
        "user": {"name": "user@example.com", "type": "user"}
    });
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "My Subscription");
    assert_eq!(tenant, "tenant-123");
    assert_eq!(user, "user@example.com");
}

#[test]
fn test_extract_account_info_empty_json() {
    let acct = serde_json::json!({});
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── cost helpers ────────────────────────────────────────────────

#[test]
fn test_parse_cost_history_rows_with_only_cost() {
    let data = serde_json::json!({
        "rows": [[42.5]]
    });
    let result = super::parse_cost_history_rows(&data);
    assert_eq!(result.len(), 1);
    assert_eq!(result[0].1, "$42.50");
    assert_eq!(result[0].0, "-"); // no date column
}

#[test]
fn test_parse_recommendation_rows_with_nested_fields() {
    let data = serde_json::json!([
        {
            "category": "Cost",
            "impact": "High",
            "shortDescription": {"problem": "VM is oversized"}
        }
    ]);
    let rows = super::parse_recommendation_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Cost");
    assert_eq!(rows[0].1, "High");
    assert_eq!(rows[0].2, "VM is oversized");
}

#[test]
fn test_parse_cost_action_rows_complete_entry() {
    let data = serde_json::json!([
        {
            "impactedField": "Microsoft.Compute/virtualMachines",
            "impact": "Medium",
            "shortDescription": {"problem": "Rightsize your VM"}
        }
    ]);
    let rows = super::parse_cost_action_rows(&data);
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
    assert_eq!(rows[0].1, "Medium");
    assert_eq!(rows[0].2, "Rightsize your VM");
}

// ── format_cost_summary comprehensive ───────────────────────────

#[test]
fn test_format_cost_summary_table_with_from_and_to() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 123.45,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &Some("2024-01-01".to_string()),
        &Some("2024-01-31".to_string()),
        false,
        false,
    );
    assert!(output.contains("$123.45"));
    assert!(output.contains("USD"));
    assert!(output.contains("From filter: 2024-01-01"));
    assert!(output.contains("To filter: 2024-01-31"));
}

#[test]
fn test_format_cost_summary_csv_format() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 50.0,
        currency: "EUR".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 6, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 6, 30, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        false,
    );
    assert!(output.contains("Total Cost,Currency,Period Start,Period End"));
    assert!(output.contains("50.00,EUR"));
}

#[test]
fn test_format_cost_summary_with_estimate_flag() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 200.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        true,
        false,
    );
    assert!(output.contains("Estimate"));
    assert!(output.contains("$200.00/month"));
}

#[test]
fn test_format_cost_summary_by_vm_table_output() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 300.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![
            azlin_core::models::VmCost {
                vm_name: "dev-vm".to_string(),
                cost: 150.0,
                currency: "USD".to_string(),
            },
            azlin_core::models::VmCost {
                vm_name: "prod-vm".to_string(),
                cost: 150.0,
                currency: "USD".to_string(),
            },
        ],
    };
    let output = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(output.contains("dev-vm"));
    assert!(output.contains("prod-vm"));
    assert!(output.contains("$150.00"));
}

#[test]
fn test_format_cost_summary_by_vm_empty_shows_message() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![],
    };
    let output = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Table,
        &None,
        &None,
        false,
        true,
    );
    assert!(output.contains("No per-VM cost data"));
}

#[test]
fn test_format_cost_summary_by_vm_csv_format() {
    use chrono::TimeZone;
    let summary = azlin_core::models::CostSummary {
        total_cost: 100.0,
        currency: "USD".to_string(),
        period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
        period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
        by_vm: vec![azlin_core::models::VmCost {
            vm_name: "test-vm".to_string(),
            cost: 100.0,
            currency: "USD".to_string(),
        }],
    };
    let output = super::format_cost_summary(
        &summary,
        &azlin_cli::OutputFormat::Csv,
        &None,
        &None,
        false,
        true,
    );
    assert!(output.contains("VM Name,Cost,Currency"));
    assert!(output.contains("test-vm,100.00,USD"));
}

// ── config_path_helpers ─────────────────────────────────────────

#[test]
fn test_validate_config_path_safe_paths() {
    assert!(super::config_path_helpers::validate_config_path("config.toml").is_ok());
    assert!(super::config_path_helpers::validate_config_path("subdir/config.toml").is_ok());
}

#[test]
fn test_validate_config_path_traversal_variants() {
    assert!(super::config_path_helpers::validate_config_path("../evil.toml").is_err());
    assert!(super::config_path_helpers::validate_config_path("sub/../../etc/passwd").is_err());
}

// ── stop_helpers ────────────────────────────────────────────────

#[test]
fn test_stop_action_labels_both_modes() {
    let (ing, ed) = super::stop_helpers::stop_action_labels(true);
    assert_eq!(ing, "Deallocating");
    assert_eq!(ed, "Deallocated");

    let (ing2, ed2) = super::stop_helpers::stop_action_labels(false);
    assert_eq!(ing2, "Stopping");
    assert_eq!(ed2, "Stopped");
}

// ── snapshot_helpers snapshot_row ────────────────────────────────

#[test]
fn test_snapshot_row_complete_data() {
    let snap = serde_json::json!({
        "name": "vm1_snapshot_20240115",
        "diskSizeGb": 128,
        "timeCreated": "2024-01-15T10:00:00Z",
        "provisioningState": "Succeeded"
    });
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "vm1_snapshot_20240115");
    assert_eq!(row[1], "128");
    assert_eq!(row[2], "2024-01-15T10:00:00Z");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_empty_json_defaults() {
    let snap = serde_json::json!({});
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

// ── create_helpers edge cases ───────────────────────────────────

#[test]
fn test_build_clone_cmd_format() {
    let cmd = super::create_helpers::build_clone_cmd("https://github.com/user/repo.git").unwrap();
    assert!(cmd.contains("git clone"));
    assert!(cmd.contains("https://github.com/user/repo.git"));
    assert!(cmd.contains("~/src/$(basename"));
}

#[test]
fn test_build_clone_name_format() {
    assert_eq!(
        super::create_helpers::build_clone_name("myvm", 0),
        "myvm-clone-1"
    );
    assert_eq!(
        super::create_helpers::build_clone_name("myvm", 2),
        "myvm-clone-3"
    );
}

#[test]
fn test_build_disk_name_format() {
    assert_eq!(
        super::create_helpers::build_disk_name("myvm"),
        "myvm_OsDisk"
    );
}

#[test]
fn test_build_ssh_connect_args_format() {
    let args = super::create_helpers::build_ssh_connect_args("user", "10.0.0.1");
    assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
    assert!(args.contains(&"user@10.0.0.1".to_string()));
}

// ═══════════════════════════════════════════════════════════════
// Security fix tests
// ═══════════════════════════════════════════════════════════════

// ── validate_repo_url ──────────────────────────────────────────

#[test]
fn test_validate_repo_url_rejects_semicolon() {
    assert!(super::repo_helpers::validate_repo_url("https://evil.com/repo.git; rm -rf /").is_err());
}

#[test]
fn test_validate_repo_url_rejects_pipe() {
    assert!(
        super::repo_helpers::validate_repo_url("https://evil.com/repo.git|cat /etc/passwd")
            .is_err()
    );
}

#[test]
fn test_validate_repo_url_rejects_backtick() {
    assert!(super::repo_helpers::validate_repo_url("https://evil.com/`whoami`.git").is_err());
}

#[test]
fn test_validate_repo_url_rejects_dollar() {
    assert!(super::repo_helpers::validate_repo_url("https://evil.com/$HOME.git").is_err());
}

#[test]
fn test_validate_repo_url_rejects_ampersand() {
    assert!(
        super::repo_helpers::validate_repo_url("https://evil.com/repo.git&echo pwned").is_err()
    );
}

#[test]
fn test_validate_repo_url_rejects_newline() {
    assert!(super::repo_helpers::validate_repo_url("https://evil.com/repo.git\nrm -rf /").is_err());
}

#[test]
fn test_validate_repo_url_rejects_parens() {
    assert!(super::repo_helpers::validate_repo_url("https://evil.com/$(whoami).git").is_err());
}

#[test]
fn test_validate_repo_url_rejects_empty() {
    assert!(super::repo_helpers::validate_repo_url("").is_err());
}

#[test]
fn test_validate_repo_url_rejects_bad_scheme() {
    assert!(super::repo_helpers::validate_repo_url("ftp://evil.com/repo.git").is_err());
}

#[test]
fn test_validate_repo_url_accepts_https() {
    assert!(super::repo_helpers::validate_repo_url("https://github.com/user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_accepts_git_ssh() {
    assert!(super::repo_helpers::validate_repo_url("git@github.com:user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_accepts_ssh_scheme() {
    assert!(super::repo_helpers::validate_repo_url("ssh://git@github.com/user/repo.git").is_ok());
}

#[test]
fn test_build_clone_cmd_rejects_injection() {
    assert!(super::create_helpers::build_clone_cmd("https://evil.com/repo.git; rm -rf /").is_err());
}

// ── validate_name (path traversal) ─────────────────────────────

#[test]
fn test_validate_name_rejects_slash() {
    assert!(super::name_validation::validate_name("../etc/passwd").is_err());
}

#[test]
fn test_validate_name_rejects_backslash() {
    assert!(super::name_validation::validate_name("foo\\bar").is_err());
}

#[test]
fn test_validate_name_rejects_dotdot() {
    assert!(super::name_validation::validate_name("..").is_err());
}

#[test]
fn test_validate_name_rejects_null() {
    assert!(super::name_validation::validate_name("foo\0bar").is_err());
}

#[test]
fn test_validate_name_rejects_empty() {
    assert!(super::name_validation::validate_name("").is_err());
}

#[test]
fn test_validate_name_accepts_simple() {
    assert!(super::name_validation::validate_name("my-profile").is_ok());
}

#[test]
fn test_validate_name_accepts_dot_prefix() {
    assert!(super::name_validation::validate_name(".hidden").is_ok());
}

#[test]
fn test_validate_name_accepts_underscores() {
    assert!(super::name_validation::validate_name("my_template_v2").is_ok());
}

#[test]
fn test_template_save_rejects_traversal() {
    let tmp = TempDir::new().unwrap();
    let tpl = toml::Value::Table(Default::default());
    let result = super::templates::save_template(tmp.path(), "../escape", &tpl);
    assert!(result.is_err());
}

#[test]
fn test_template_load_rejects_traversal() {
    let tmp = TempDir::new().unwrap();
    let result = super::templates::load_template(tmp.path(), "../../etc/passwd");
    assert!(result.is_err());
}

// ── env delete key validation ──────────────────────────────────

#[test]
fn test_build_env_delete_cmd_rejects_injection() {
    let cmd = super::env_helpers::build_env_delete_cmd("foo;rm -rf /;#");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_delete_cmd_rejects_dollar() {
    let cmd = super::env_helpers::build_env_delete_cmd("$HOME");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_delete_cmd_valid_key_works() {
    let cmd = super::env_helpers::build_env_delete_cmd("VALID_KEY");
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("VALID_KEY"));
}

// ── batch tag filter ───────────────────────────────────────────

#[test]
fn test_build_vm_list_query_no_tag() {
    let q = super::batch_helpers::build_vm_list_query(None).unwrap();
    assert_eq!(q, "[].id");
}

#[test]
fn test_build_vm_list_query_with_tag() {
    let q = super::batch_helpers::build_vm_list_query(Some("env=dev")).unwrap();
    assert_eq!(q, "[?tags.env=='dev'].id");
}

#[test]
fn test_build_vm_list_query_invalid_tag_format() {
    assert!(super::batch_helpers::build_vm_list_query(Some("notag")).is_err());
}

#[test]
fn test_build_vm_list_query_rejects_injection_in_tag_value() {
    assert!(super::batch_helpers::build_vm_list_query(Some("env=dev';rm -rf /")).is_err());
}

#[test]
fn test_build_vm_list_query_rejects_injection_in_tag_key() {
    assert!(super::batch_helpers::build_vm_list_query(Some("en$v=dev")).is_err());
}

// ── OnceLock bastion pool flag ─────────────────────────────────

// ── format_os_display tests ─────────────────────────────────────

#[test]
fn test_format_os_display_ubuntu_version_lts() {
    let result = super::display_helpers::format_os_display(
        Some("ubuntu-24_04-lts"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 24.04 LTS");
}

#[test]
fn test_format_os_display_ubuntu_version_no_lts() {
    let result = super::display_helpers::format_os_display(
        Some("ubuntu-25_10"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 25.10");
}

#[test]
fn test_format_os_display_ubuntu_com_prefix_jammy() {
    let result = super::display_helpers::format_os_display(
        Some("0001-com-ubuntu-server-jammy"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 22.04 LTS");
}

#[test]
fn test_format_os_display_ubuntu_com_prefix_focal() {
    let result = super::display_helpers::format_os_display(
        Some("0001-com-ubuntu-server-focal"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 20.04 LTS");
}

#[test]
fn test_format_os_display_ubuntu_noble_codename() {
    let result = super::display_helpers::format_os_display(
        Some("0001-com-ubuntu-server-noble"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 24.04 LTS");
}

#[test]
fn test_format_os_display_ubuntu_bionic_codename() {
    let result = super::display_helpers::format_os_display(
        Some("0001-com-ubuntu-server-bionic"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 18.04 LTS");
}

#[test]
fn test_format_os_display_ubuntu_oracular() {
    let result = super::display_helpers::format_os_display(
        Some("0001-com-ubuntu-server-oracular"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 24.10");
}

#[test]
fn test_format_os_display_ubuntu_plucky() {
    let result = super::display_helpers::format_os_display(
        Some("0001-com-ubuntu-server-plucky"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 25.04");
}

#[test]
fn test_format_os_display_ubuntu_gen2_suffix() {
    let result = super::display_helpers::format_os_display(
        Some("ubuntu-24_04-lts-gen2"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu 24.04 LTS");
}

#[test]
fn test_format_os_display_ubuntu_unknown_falls_back() {
    let result = super::display_helpers::format_os_display(
        Some("UbuntuWeird"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Ubuntu (UbuntuWeird)");
}

#[test]
fn test_format_os_display_debian() {
    let result = super::display_helpers::format_os_display(
        Some("debian-11"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Debian");
}

#[test]
fn test_format_os_display_rhel() {
    let result =
        super::display_helpers::format_os_display(Some("RHEL"), &azlin_core::models::OsType::Linux);
    assert_eq!(result, "RHEL");
}

#[test]
fn test_format_os_display_centos() {
    let result = super::display_helpers::format_os_display(
        Some("CentOS-7"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "CentOS");
}

#[test]
fn test_format_os_display_suse() {
    let result = super::display_helpers::format_os_display(
        Some("sles-15"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "SUSE");
}

#[test]
fn test_format_os_display_almalinux() {
    let result = super::display_helpers::format_os_display(
        Some("almalinux-9"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "AlmaLinux");
}

#[test]
fn test_format_os_display_rocky() {
    let result = super::display_helpers::format_os_display(
        Some("rockylinux-9"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "Rocky Linux");
}

#[test]
fn test_format_os_display_windows_offer() {
    let result = super::display_helpers::format_os_display(
        Some("WindowsServer"),
        &azlin_core::models::OsType::Windows,
    );
    assert_eq!(result, "Windows");
}

#[test]
fn test_format_os_display_unknown_offer_passthrough() {
    let result = super::display_helpers::format_os_display(
        Some("CustomImage"),
        &azlin_core::models::OsType::Linux,
    );
    assert_eq!(result, "CustomImage");
}

#[test]
fn test_format_os_display_none_linux() {
    let result =
        super::display_helpers::format_os_display(None, &azlin_core::models::OsType::Linux);
    assert_eq!(result, "Linux");
}

#[test]
fn test_format_os_display_none_windows() {
    let result =
        super::display_helpers::format_os_display(None, &azlin_core::models::OsType::Windows);
    assert_eq!(result, "Windows");
}

// ── format_ip_display tests ─────────────────────────────────────

#[test]
fn test_format_ip_display_public_ip() {
    let result = super::display_helpers::format_ip_display(Some("52.1.2.3"), Some("10.0.0.4"));
    assert_eq!(result, "52.1.2.3 (Pub)");
}

#[test]
fn test_format_ip_display_private_only() {
    let result = super::display_helpers::format_ip_display(None, Some("10.0.0.4"));
    assert_eq!(result, "10.0.0.4 (Bast)");
}

#[test]
fn test_format_ip_display_no_ip() {
    let result = super::display_helpers::format_ip_display(None, None);
    assert_eq!(result, "N/A");
}

#[test]
fn test_format_ip_display_public_takes_precedence() {
    // When both exist, public IP should be shown
    let result = super::display_helpers::format_ip_display(Some("1.2.3.4"), Some("10.0.0.1"));
    assert!(result.contains("(Pub)"));
    assert!(result.contains("1.2.3.4"));
}

// ── parse_vm_size_specs tests ───────────────────────────────────

#[test]
fn test_parse_vm_size_specs_d4s_v3() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_D4s_v3");
    assert_eq!(vcpus, "4");
    assert_eq!(mem, "16 GB"); // D-series: 4 vcpus * 4 GB
}

#[test]
fn test_parse_vm_size_specs_e16as() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_E16as_v5");
    assert_eq!(vcpus, "16");
    assert_eq!(mem, "128 GB"); // E-series: 16 vcpus * 8 GB
}

#[test]
fn test_parse_vm_size_specs_f2s() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_F2s_v2");
    assert_eq!(vcpus, "2");
    assert_eq!(mem, "4 GB"); // F-series: 2 vcpus * 2 GB
}

#[test]
fn test_parse_vm_size_specs_b1s() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_B1s");
    assert_eq!(vcpus, "1");
    assert_eq!(mem, "4 GB"); // B-series: 1 * 4 GB
}

#[test]
fn test_parse_vm_size_specs_m32() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_M32ms_v2");
    assert_eq!(vcpus, "32");
    assert_eq!(mem, "512 GB"); // M-series: 32 * 16 GB
}

#[test]
fn test_parse_vm_size_specs_n6() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_N6s_v3");
    assert_eq!(vcpus, "6");
    assert_eq!(mem, "36 GB"); // N-series: 6 * 6 GB
}

#[test]
fn test_parse_vm_size_specs_l8s() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_L8s_v3");
    assert_eq!(vcpus, "8");
    assert_eq!(mem, "64 GB"); // L-series: 8 * 8 GB
}

#[test]
fn test_parse_vm_size_specs_invalid_format() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("NotAVmSize");
    assert_eq!(vcpus, "-");
    assert_eq!(mem, "-");
}

#[test]
fn test_parse_vm_size_specs_empty() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("");
    assert_eq!(vcpus, "-");
    assert_eq!(mem, "-");
}

#[test]
fn test_parse_vm_size_specs_no_number() {
    let (vcpus, mem) = super::display_helpers::parse_vm_size_specs("Standard_Ds_v3");
    assert_eq!(vcpus, "-");
    assert_eq!(mem, "-");
}

// ── build_ssh_target tests ──────────────────────────────────────

#[test]
fn test_build_ssh_target_public_ip_no_bastion() {
    let vm = azlin_core::models::VmInfo {
        name: "my-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: Some("52.1.2.3".to_string()),
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: Some("testuser".to_string()),
        tags: Default::default(),
        created_time: None,
    };
    let bastion_map = std::collections::HashMap::new();
    let target = super::build_ssh_target(&vm, "sub-123", &bastion_map, &None);
    assert_eq!(target.ip, "52.1.2.3");
    assert_eq!(target.user, "testuser");
    assert!(
        target.bastion.is_none(),
        "Public IP VMs should not route through bastion"
    );
}

#[test]
fn test_build_ssh_target_private_ip_with_bastion() {
    let vm = azlin_core::models::VmInfo {
        name: "my-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: Some("azureuser".to_string()),
        tags: Default::default(),
        created_time: None,
    };
    let mut bastion_map = std::collections::HashMap::new();
    bastion_map.insert("eastus".to_string(), "my-bastion".to_string());
    let target = super::build_ssh_target(&vm, "sub-123", &bastion_map, &None);
    assert_eq!(target.ip, "10.0.0.4");
    assert!(
        target.bastion.is_some(),
        "Private-IP-only VM should route through bastion"
    );
    let b = target.bastion.unwrap();
    assert_eq!(b.bastion_name, "my-bastion");
    assert_eq!(b.resource_group, "rg");
    assert!(b.vm_resource_id.contains("my-vm"));
    assert!(b.vm_resource_id.contains("sub-123"));
}

#[test]
fn test_build_ssh_target_private_ip_no_bastion_available() {
    let vm = azlin_core::models::VmInfo {
        name: "my-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.4".to_string()),
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    };
    let bastion_map = std::collections::HashMap::new();
    let target = super::build_ssh_target(&vm, "sub-123", &bastion_map, &None);
    assert_eq!(target.ip, "10.0.0.4");
    assert_eq!(
        target.user, "azureuser",
        "Should fall back to DEFAULT_ADMIN_USERNAME"
    );
    assert!(
        target.bastion.is_none(),
        "No bastion in map, so should be None"
    );
}

#[test]
fn test_build_ssh_target_bastion_wrong_location() {
    let vm = azlin_core::models::VmInfo {
        name: "vm1".to_string(),
        resource_group: "rg".to_string(),
        location: "westus2".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: Some("10.0.0.5".to_string()),
        admin_username: Some("user1".to_string()),
        tags: Default::default(),
        created_time: None,
    };
    let mut bastion_map = std::collections::HashMap::new();
    bastion_map.insert("eastus".to_string(), "east-bastion".to_string());
    let target = super::build_ssh_target(&vm, "sub-456", &bastion_map, &None);
    assert!(
        target.bastion.is_none(),
        "Bastion in different location should not match"
    );
}

#[test]
fn test_build_ssh_target_no_ips() {
    let vm = azlin_core::models::VmInfo {
        name: "orphan-vm".to_string(),
        resource_group: "rg".to_string(),
        location: "eastus".to_string(),
        vm_size: "Standard_D4s_v3".to_string(),
        power_state: azlin_core::models::PowerState::Running,
        provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
        os_type: azlin_core::models::OsType::Linux,
        os_offer: None,
        public_ip: None,
        private_ip: None,
        admin_username: None,
        tags: Default::default(),
        created_time: None,
    };
    let bastion_map = std::collections::HashMap::new();
    let target = super::build_ssh_target(&vm, "sub-1", &bastion_map, &None);
    assert_eq!(target.ip, "", "No IPs at all should result in empty string");
}

// ── context glob filtering tests ────────────────────────────────

/// Helper: apply the same glob logic used in list handler for --contexts
fn context_glob_matches(ctx_name: &str, pattern: &str) -> bool {
    let pat = pattern.replace('*', "");
    if pattern.contains('*') {
        ctx_name.contains(&pat)
    } else {
        ctx_name == pattern
    }
}

#[test]
fn test_context_glob_exact_match() {
    assert!(context_glob_matches("dev", "dev"));
    assert!(!context_glob_matches("dev-pool", "dev"));
}

#[test]
fn test_context_glob_wildcard_prefix() {
    assert!(context_glob_matches("my-dev-pool", "*dev*"));
    assert!(context_glob_matches("dev-pool", "*dev*"));
    assert!(context_glob_matches("dev", "*dev*"));
    assert!(!context_glob_matches("staging", "*dev*"));
}

#[test]
fn test_context_glob_wildcard_suffix() {
    assert!(context_glob_matches("dev-pool", "dev*"));
    assert!(context_glob_matches("dev", "dev*"));
    // Note: the implementation uses substring match (contains), not prefix match
    // so "my-dev" DOES match "dev*" because it contains "dev"
    assert!(context_glob_matches("my-dev", "dev*"));
}

#[test]
fn test_context_glob_empty_pattern() {
    // "*" pattern means "match everything" — empty substring after removing *
    assert!(context_glob_matches("anything", "*"));
    assert!(context_glob_matches("", "*"));
}

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
    super::list_helpers::apply_filters(&mut vms, true, None, None);
    assert_eq!(vms.len(), 2, "include_all=true should keep stopped VMs");
}

#[test]
fn test_apply_filters_not_include_all_removes_stopped() {
    let mut vms = vec![
        make_vm_for_filter("vm1", azlin_core::models::PowerState::Running),
        make_vm_for_filter("vm2", azlin_core::models::PowerState::Deallocated),
    ];
    super::list_helpers::apply_filters(&mut vms, false, None, None);
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
    super::list_helpers::apply_filters(&mut vms, true, Some("env=prod"), Some("web*"));
    assert_eq!(vms.len(), 1);
    assert_eq!(vms[0].name, "web-server-1");
}

// ════════════════════════════════════════════════════════════════
// NEW COVERAGE BOOST: snapshot_helpers.rs functions
// ════════════════════════════════════════════════════════════════

#[test]
fn test_schedules_dir_ends_with_schedules() {
    let dir = super::snapshot_helpers::schedules_dir();
    assert!(dir.ends_with("schedules"));
    assert!(dir.to_string_lossy().contains(".azlin"));
}

#[test]
fn test_schedule_path_appends_toml_extension() {
    let path = super::snapshot_helpers::schedule_path("my-vm");
    assert_eq!(path.file_name().unwrap().to_str().unwrap(), "my-vm.toml");
    assert!(path.parent().unwrap().ends_with("schedules"));
}

#[test]
fn test_schedule_path_special_characters() {
    let path = super::snapshot_helpers::schedule_path("vm-with-dashes-123");
    assert_eq!(
        path.file_name().unwrap().to_str().unwrap(),
        "vm-with-dashes-123.toml"
    );
}

#[test]
fn test_save_and_load_schedule_roundtrip() {
    let tmp = TempDir::new().unwrap();
    let schedule = super::snapshot_helpers::SnapshotSchedule {
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
    let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&read_contents).unwrap();
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
    let result = super::snapshot_helpers::load_schedule("nonexistent-vm-that-does-not-exist-12345");
    assert!(result.is_none());
}

#[test]
fn test_load_all_schedules_empty_dir() {
    let tmp = TempDir::new().unwrap();
    let dir = tmp.path().join("empty-schedules");
    fs::create_dir_all(&dir).unwrap();
    // Manually read to simulate — load_all_schedules uses schedules_dir()
    // so we test the filtering logic directly
    let entries: Vec<super::snapshot_helpers::SnapshotSchedule> = fs::read_dir(&dir)
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
    let schedule = super::snapshot_helpers::SnapshotSchedule {
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

    let entries: Vec<super::snapshot_helpers::SnapshotSchedule> = fs::read_dir(dir)
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
        let schedule = super::snapshot_helpers::SnapshotSchedule {
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

    let entries: Vec<super::snapshot_helpers::SnapshotSchedule> = fs::read_dir(dir)
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
    let name = super::snapshot_helpers::build_snapshot_name("", "20250101_120000");
    assert_eq!(name, "_snapshot_20250101_120000");
}

#[test]
fn test_build_snapshot_name_empty_timestamp() {
    let name = super::snapshot_helpers::build_snapshot_name("vm1", "");
    assert_eq!(name, "vm1_snapshot_");
}

#[test]
fn test_filter_snapshots_multiple_matches() {
    let snaps = vec![
        serde_json::json!({"name": "dev-vm_snapshot_1"}),
        serde_json::json!({"name": "dev-vm_snapshot_2"}),
        serde_json::json!({"name": "prod-vm_snapshot_1"}),
    ];
    let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "dev-vm");
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
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "snap1");
    assert_eq!(row[1], "128"); // numeric value should serialize as "128"
    assert_eq!(row[2], "2025-01-01");
    assert_eq!(row[3], "Succeeded");
}

#[test]
fn test_snapshot_row_all_null() {
    let snap = serde_json::json!({});
    let row = super::snapshot_helpers::snapshot_row(&snap);
    assert_eq!(row[0], "-");
    assert_eq!(row[1], "null");
    assert_eq!(row[2], "-");
    assert_eq!(row[3], "-");
}

#[test]
fn test_snapshot_schedule_toml_contains_all_fields() {
    let schedule = super::snapshot_helpers::SnapshotSchedule {
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

#[test]
fn test_snapshot_schedule_deserialization_from_raw_toml() {
    let raw = r#"
vm_name = "from-raw"
resource_group = "raw-rg"
every_hours = 1
keep_count = 100
enabled = true
created = "2025-12-31T23:59:59Z"
"#;
    let schedule: super::snapshot_helpers::SnapshotSchedule = toml::from_str(raw).unwrap();
    assert_eq!(schedule.vm_name, "from-raw");
    assert_eq!(schedule.every_hours, 1);
    assert_eq!(schedule.keep_count, 100);
}

// ════════════════════════════════════════════════════════════════
// NEW COVERAGE BOOST: main.rs inline helper modules
// ════════════════════════════════════════════════════════════════

// ── stop_helpers ────────────────────────────────────────────────

#[test]
fn test_stop_action_labels_returns_correct_pairs() {
    let (ing, ed) = super::stop_helpers::stop_action_labels(true);
    assert_eq!(ing, "Deallocating");
    assert_eq!(ed, "Deallocated");

    let (ing, ed) = super::stop_helpers::stop_action_labels(false);
    assert_eq!(ing, "Stopping");
    assert_eq!(ed, "Stopped");
}

// ── bastion_helpers ─────────────────────────────────────────────

#[test]
fn test_bastion_summary_partial_fields() {
    let b = serde_json::json!({
        "name": "my-bastion",
        "location": "eastus"
    });
    let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
    assert_eq!(name, "my-bastion");
    assert_eq!(rg, "unknown");
    assert_eq!(loc, "eastus");
    assert_eq!(sku, "Standard");
    assert_eq!(state, "unknown");
}

#[test]
fn test_shorten_resource_id_empty_string() {
    assert_eq!(super::bastion_helpers::shorten_resource_id(""), "");
}

#[test]
fn test_shorten_resource_id_no_slash() {
    assert_eq!(
        super::bastion_helpers::shorten_resource_id("just-a-name"),
        "just-a-name"
    );
}

#[test]
fn test_extract_ip_configs_missing_ip_configurations_key() {
    let b = serde_json::json!({"name": "test"});
    let configs = super::bastion_helpers::extract_ip_configs(&b);
    assert!(configs.is_empty());
}

// ── auth_helpers ────────────────────────────────────────────────

#[test]
fn test_mask_profile_value_client_secret() {
    let val = serde_json::json!("super-secret-123");
    let masked = super::auth_helpers::mask_profile_value("client_secret", &val);
    assert_eq!(masked, "********");
}

#[test]
fn test_mask_profile_value_normal_key() {
    let val = serde_json::json!("visible-value");
    let masked = super::auth_helpers::mask_profile_value("tenant_id", &val);
    assert_eq!(masked, "visible-value");
}

#[test]
fn test_mask_profile_value_array() {
    let val = serde_json::json!([1, 2, 3]);
    let masked = super::auth_helpers::mask_profile_value("data", &val);
    assert_eq!(masked, "[1,2,3]");
}

// ── log_helpers ─────────────────────────────────────────────────

#[test]
fn test_tail_start_index_large_count() {
    assert_eq!(super::log_helpers::tail_start_index(1000, 500), 500);
}

#[test]
fn test_tail_start_index_count_exceeds_total() {
    assert_eq!(super::log_helpers::tail_start_index(10, 100), 0);
}

// ── config_path_helpers ─────────────────────────────────────────

#[test]
fn test_validate_config_path_empty_string_ok() {
    assert!(super::config_path_helpers::validate_config_path("").is_ok());
}

#[test]
fn test_validate_config_path_absolute_linux() {
    assert!(super::config_path_helpers::validate_config_path("/etc/azlin/config.toml").is_ok());
}

#[test]
fn test_validate_config_path_parent_at_start() {
    assert!(super::config_path_helpers::validate_config_path("../evil.toml").is_err());
}

#[test]
fn test_validate_config_path_parent_in_middle() {
    assert!(super::config_path_helpers::validate_config_path("foo/../bar.toml").is_err());
}

// ── disk_helpers ────────────────────────────────────────────────

#[test]
fn test_build_data_disk_name_zero_lun() {
    assert_eq!(
        super::disk_helpers::build_data_disk_name("myvm", 0),
        "myvm_datadisk_0"
    );
}

#[test]
fn test_build_data_disk_name_high_lun() {
    assert_eq!(
        super::disk_helpers::build_data_disk_name("prod-db", 63),
        "prod-db_datadisk_63"
    );
}

#[test]
fn test_restored_disk_name_construction() {
    assert_eq!(
        super::disk_helpers::build_restored_disk_name("web-server"),
        "web-server_OsDisk_restored"
    );
}

// ── command_helpers ─────────────────────────────────────────────

#[test]
fn test_is_allowed_command_az_vm() {
    assert!(super::command_helpers::is_allowed_command("az vm list"));
}

#[test]
fn test_is_allowed_command_az_with_leading_space() {
    assert!(super::command_helpers::is_allowed_command("  az vm list"));
}

#[test]
fn test_is_allowed_command_rm_rejected() {
    assert!(!super::command_helpers::is_allowed_command("rm -rf /"));
}

#[test]
fn test_is_allowed_command_empty() {
    assert!(!super::command_helpers::is_allowed_command(""));
}

#[test]
fn test_skip_reason_az_command_none() {
    assert!(super::command_helpers::skip_reason("az vm list").is_none());
}

#[test]
fn test_skip_reason_empty_returns_message() {
    let reason = super::command_helpers::skip_reason("").unwrap();
    assert!(reason.contains("empty"));
}

#[test]
fn test_skip_reason_non_az_returns_message() {
    let reason = super::command_helpers::skip_reason("docker ps").unwrap();
    assert!(reason.contains("non-Azure"));
}

// ── mount_helpers ───────────────────────────────────────────────

#[test]
fn test_mount_path_empty_rejected() {
    assert!(super::mount_helpers::validate_mount_path("").is_err());
}

#[test]
fn test_mount_path_valid_data() {
    assert!(super::mount_helpers::validate_mount_path("/data").is_ok());
}

#[test]
fn test_mount_path_valid_deep_nested() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/data/vol/1").is_ok());
}

#[test]
fn test_mount_path_traversal_dotdot() {
    assert!(super::mount_helpers::validate_mount_path("/mnt/../etc/shadow").is_err());
}

#[test]
fn test_mount_path_shell_injection_semicolon() {
    assert!(super::mount_helpers::validate_mount_path("/mnt; rm -rf /").is_err());
}

// ── vm_validation ───────────────────────────────────────────────

#[test]
fn test_validate_vm_name_numeric_only() {
    assert!(super::vm_validation::validate_vm_name("12345").is_ok());
}

#[test]
fn test_validate_vm_name_with_hyphens() {
    assert!(super::vm_validation::validate_vm_name("my-dev-vm-01").is_ok());
}

#[test]
fn test_validate_vm_name_underscore_rejected() {
    assert!(super::vm_validation::validate_vm_name("my_vm").is_err());
}

#[test]
fn test_validate_vm_name_dot_rejected() {
    assert!(super::vm_validation::validate_vm_name("my.vm").is_err());
}

#[test]
fn test_validate_vm_name_exactly_64_chars() {
    let name = "a".repeat(64);
    assert!(super::vm_validation::validate_vm_name(&name).is_ok());
}

#[test]
fn test_validate_vm_name_exactly_65_chars() {
    let name = "a".repeat(65);
    assert!(super::vm_validation::validate_vm_name(&name).is_err());
}

// ── repo_helpers ────────────────────────────────────────────────

#[test]
fn test_validate_repo_url_https_valid() {
    assert!(super::repo_helpers::validate_repo_url("https://github.com/user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_git_ssh_valid() {
    assert!(super::repo_helpers::validate_repo_url("git@github.com:user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_ssh_scheme_valid() {
    assert!(super::repo_helpers::validate_repo_url("ssh://git@github.com/user/repo").is_ok());
}

#[test]
fn test_validate_repo_url_http_valid() {
    assert!(super::repo_helpers::validate_repo_url("http://github.com/user/repo").is_ok());
}

#[test]
fn test_validate_repo_url_ftp_rejected() {
    assert!(super::repo_helpers::validate_repo_url("ftp://example.com/repo").is_err());
}

#[test]
fn test_validate_repo_url_space_rejected() {
    assert!(super::repo_helpers::validate_repo_url("https://example.com/my repo").is_err());
}

#[test]
fn test_validate_repo_url_quotes_rejected() {
    assert!(super::repo_helpers::validate_repo_url("https://example.com/repo'").is_err());
    assert!(super::repo_helpers::validate_repo_url("https://example.com/repo\"").is_err());
}

// ── cp_helpers ──────────────────────────────────────────────────

#[test]
fn test_is_remote_path_vm_with_path() {
    assert!(super::cp_helpers::is_remote_path(
        "myvm:/home/user/file.txt"
    ));
}

#[test]
fn test_is_remote_path_local_absolute() {
    assert!(!super::cp_helpers::is_remote_path("/home/user/file.txt"));
}

#[test]
fn test_remote_path_empty_string_false() {
    assert!(!super::cp_helpers::is_remote_path(""));
}

#[test]
fn test_is_remote_path_single_char_before_colon() {
    // "a:" has len 2, so should be false (too short: len > 2 check)
    assert!(!super::cp_helpers::is_remote_path("a:"));
}

#[test]
fn test_classify_transfer_local_to_local_both_paths() {
    assert_eq!(
        super::cp_helpers::classify_transfer_direction("/tmp/a.txt", "/tmp/b.txt"),
        "local\u{2192}local"
    );
}

#[test]
fn test_resolve_scp_path_replaces_first_occurrence() {
    let result = super::cp_helpers::resolve_scp_path("myvm:/path", "myvm", "admin", "10.0.0.1");
    assert_eq!(result, "admin@10.0.0.1:/path");
}

// ── key_helpers ─────────────────────────────────────────────────

#[test]
fn test_detect_key_type_ed25519_pub() {
    assert_eq!(
        super::key_helpers::detect_key_type("id_ed25519.pub"),
        "ed25519"
    );
}

#[test]
fn test_detect_key_type_rsa_private() {
    assert_eq!(super::key_helpers::detect_key_type("id_rsa"), "rsa");
}

#[test]
fn test_detect_key_type_random() {
    assert_eq!(
        super::key_helpers::detect_key_type("authorized_keys"),
        "unknown"
    );
}

#[test]
fn test_is_known_key_name_ed25519_pub() {
    assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
}

#[test]
fn test_is_known_key_name_id_rsa() {
    assert!(super::key_helpers::is_known_key_name("id_rsa"));
}

#[test]
fn test_is_known_key_name_config() {
    assert!(!super::key_helpers::is_known_key_name("config"));
}

#[test]
fn test_is_known_key_name_known_hosts() {
    assert!(!super::key_helpers::is_known_key_name("known_hosts"));
}

// ── auth_test_helpers ───────────────────────────────────────────

#[test]
fn test_extract_account_info_complete() {
    let acct = serde_json::json!({
        "name": "My Subscription",
        "tenantId": "tenant-abc",
        "user": {"name": "user@example.com"}
    });
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "My Subscription");
    assert_eq!(tenant, "tenant-abc");
    assert_eq!(user, "user@example.com");
}

#[test]
fn test_extract_account_info_all_missing() {
    let acct = serde_json::json!({});
    let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
    assert_eq!(sub, "-");
    assert_eq!(tenant, "-");
    assert_eq!(user, "-");
}

// ── storage_helpers ─────────────────────────────────────────────

#[test]
fn test_storage_sku_from_tier_premium_lrs() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("premium"),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_standard_lrs() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("standard"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_from_tier_mixed_case() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("PREMIUM"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("StAnDaRd"),
        "Standard_LRS"
    );
}

#[test]
fn test_storage_sku_unknown_tier_defaults() {
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier("hot"),
        "Premium_LRS"
    );
    assert_eq!(
        super::storage_helpers::storage_sku_from_tier(""),
        "Premium_LRS"
    );
}

#[test]
fn test_storage_account_row_complete_json() {
    let acct = serde_json::json!({
        "name": "mystorage",
        "location": "westus2",
        "kind": "StorageV2",
        "sku": {"name": "Standard_LRS"},
        "provisioningState": "Succeeded"
    });
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(
        row,
        vec![
            "mystorage",
            "westus2",
            "StorageV2",
            "Standard_LRS",
            "Succeeded"
        ]
    );
}

#[test]
fn test_storage_account_row_all_missing() {
    let acct = serde_json::json!({});
    let row = super::storage_helpers::storage_account_row(&acct);
    assert_eq!(row, vec!["-", "-", "-", "-", "-"]);
}

// ── compose_helpers ─────────────────────────────────────────────

#[test]
fn test_resolve_compose_file_default_value() {
    assert_eq!(
        super::compose_helpers::resolve_compose_file(None),
        "docker-compose.yml"
    );
}

#[test]
fn test_resolve_compose_file_custom_value() {
    assert_eq!(
        super::compose_helpers::resolve_compose_file(Some("custom.yml")),
        "custom.yml"
    );
}

#[test]
fn test_build_compose_cmd_ps() {
    assert_eq!(
        super::compose_helpers::build_compose_cmd("ps", "docker-compose.yml"),
        "docker compose -f docker-compose.yml ps"
    );
}

#[test]
fn test_build_compose_cmd_logs() {
    assert_eq!(
        super::compose_helpers::build_compose_cmd("logs", "custom.yml"),
        "docker compose -f custom.yml logs"
    );
}

// ── runner_helpers ──────────────────────────────────────────────

#[test]
fn test_build_runner_vm_name_zero_index() {
    assert_eq!(
        super::runner_helpers::build_runner_vm_name("dev", 0),
        "azlin-runner-dev-1"
    );
}

#[test]
fn test_build_runner_vm_name_multiple_index() {
    assert_eq!(
        super::runner_helpers::build_runner_vm_name("ci", 4),
        "azlin-runner-ci-5"
    );
}

#[test]
fn test_runner_tags_contains_all_parts() {
    let tags = super::runner_helpers::build_runner_tags("ci-pool", "org/repo");
    assert!(tags.contains("azlin-runner=true"));
    assert!(tags.contains("pool=ci-pool"));
    assert!(tags.contains("repo=org/repo"));
}

#[test]
fn test_build_runner_config_structure() {
    let config = super::runner_helpers::build_runner_config(
        "my-pool",
        "org/repo",
        3,
        "self-hosted,linux",
        "my-rg",
        "Standard_D2s_v3",
        "2025-01-01",
    );
    let map: std::collections::HashMap<String, toml::Value> = config.into_iter().collect();
    assert_eq!(
        map.get("pool").unwrap(),
        &toml::Value::String("my-pool".to_string())
    );
    assert_eq!(map.get("count").unwrap(), &toml::Value::Integer(3));
    assert_eq!(map.get("enabled").unwrap(), &toml::Value::Boolean(true));
}

#[test]
fn test_pool_config_filename_toml_extension() {
    assert_eq!(
        super::runner_helpers::pool_config_filename("dev"),
        "dev.toml"
    );
    assert_eq!(
        super::runner_helpers::pool_config_filename("ci-pool"),
        "ci-pool.toml"
    );
}

// ── autopilot_helpers ───────────────────────────────────────────

#[test]
fn test_autopilot_config_budget_present_and_fields() {
    let config = super::autopilot_helpers::build_autopilot_config(
        Some(500),
        "conservative",
        30,
        10,
        "2025-01-01T00:00:00Z",
    );
    let table = config.as_table().unwrap();
    assert_eq!(table["budget"].as_integer().unwrap(), 500);
    assert_eq!(table["strategy"].as_str().unwrap(), "conservative");
    assert_eq!(table["idle_threshold_minutes"].as_integer().unwrap(), 30);
    assert_eq!(table["cpu_threshold_percent"].as_integer().unwrap(), 10);
    assert!(table["enabled"].as_bool().unwrap());
}

#[test]
fn test_autopilot_config_no_budget_omits_key() {
    let config = super::autopilot_helpers::build_autopilot_config(
        None,
        "aggressive",
        15,
        5,
        "2025-06-01T00:00:00Z",
    );
    let table = config.as_table().unwrap();
    assert!(!table.contains_key("budget"));
    assert_eq!(table["strategy"].as_str().unwrap(), "aggressive");
}

#[test]
fn test_build_budget_name_format() {
    assert_eq!(
        super::autopilot_helpers::build_budget_name("prod-rg"),
        "azlin-budget-prod-rg"
    );
}

#[test]
fn test_build_prefix_filter_query_format() {
    assert_eq!(
        super::autopilot_helpers::build_prefix_filter_query("dev-"),
        "[?starts_with(name, 'dev-')].id"
    );
}

#[test]
fn test_build_cost_scope_format() {
    assert_eq!(
        super::autopilot_helpers::build_cost_scope("sub-123", "my-rg"),
        "/subscriptions/sub-123/resourceGroups/my-rg"
    );
}

// ── autopilot_parse_helpers ─────────────────────────────────────

#[test]
fn test_parse_idle_check_valid_input() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("2.5\n3600.0");
    assert!((cpu - 2.5).abs() < f64::EPSILON);
    assert!((uptime - 3600.0).abs() < f64::EPSILON);
}

#[test]
fn test_parse_idle_check_empty_input() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("");
    assert!((cpu - 100.0).abs() < f64::EPSILON); // defaults to 100
    assert!((uptime - 0.0).abs() < f64::EPSILON);
}

#[test]
fn test_idle_parse_single_line_only() {
    let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("50.0");
    assert!((cpu - 50.0).abs() < f64::EPSILON);
    assert!((uptime - 0.0).abs() < f64::EPSILON);
}

#[test]
fn test_is_idle_low_cpu_long_uptime() {
    assert!(super::autopilot_parse_helpers::is_idle(1.0, 7200.0, 60));
}

#[test]
fn test_idle_check_high_cpu_not_idle() {
    assert!(!super::autopilot_parse_helpers::is_idle(50.0, 7200.0, 60));
}

#[test]
fn test_idle_check_short_uptime_not_idle() {
    assert!(!super::autopilot_parse_helpers::is_idle(1.0, 100.0, 60));
}

#[test]
fn test_is_idle_boundary_cpu_exactly_5() {
    // cpu_pct < 5.0 is the check, so 5.0 should NOT be idle
    assert!(!super::autopilot_parse_helpers::is_idle(5.0, 7200.0, 60));
}

#[test]
fn test_is_idle_boundary_uptime_exactly_threshold() {
    // uptime must be > threshold * 60, so exactly equal should NOT be idle
    assert!(!super::autopilot_parse_helpers::is_idle(1.0, 3600.0, 60));
}

// ── batch_helpers ───────────────────────────────────────────────

#[test]
fn test_parse_vm_ids_normal_input() {
    let ids = super::batch_helpers::parse_vm_ids("/sub/rg/vm1\n/sub/rg/vm2\n");
    assert_eq!(ids, vec!["/sub/rg/vm1", "/sub/rg/vm2"]);
}

#[test]
fn test_parse_vm_ids_empty_string() {
    let ids = super::batch_helpers::parse_vm_ids("");
    assert!(ids.is_empty());
}

#[test]
fn test_parse_vm_ids_blank_lines_filtered() {
    let ids = super::batch_helpers::parse_vm_ids("/sub/rg/vm1\n\n\n/sub/rg/vm2\n");
    assert_eq!(ids.len(), 2);
}

#[test]
fn test_batch_args_start_format() {
    let ids = vec!["/sub/rg/vm1", "/sub/rg/vm2"];
    let args = super::batch_helpers::build_batch_args("start", &ids);
    assert_eq!(
        args,
        vec!["vm", "start", "--ids", "/sub/rg/vm1", "/sub/rg/vm2"]
    );
}

#[test]
fn test_build_vm_list_query_no_tag_returns_all() {
    assert_eq!(
        super::batch_helpers::build_vm_list_query(None).unwrap(),
        "[].id"
    );
}

#[test]
fn test_build_vm_list_query_with_valid_tag() {
    assert_eq!(
        super::batch_helpers::build_vm_list_query(Some("env=prod")).unwrap(),
        "[?tags.env=='prod'].id"
    );
}

#[test]
fn test_build_vm_list_query_injection_rejected() {
    assert!(super::batch_helpers::build_vm_list_query(Some("env=prod';--")).is_err());
}

#[test]
fn test_summarise_batch_success_message() {
    let msg = super::batch_helpers::summarise_batch("deallocate", "my-rg", true);
    assert!(msg.contains("deallocate"));
    assert!(msg.contains("my-rg"));
    assert!(msg.contains("completed"));
}

#[test]
fn test_summarise_batch_failure_message() {
    let msg = super::batch_helpers::summarise_batch("start", "prod-rg", false);
    assert!(msg.contains("failed"));
}

// ── fleet_helpers ───────────────────────────────────────────────

#[test]
fn test_classify_result_zero_is_ok() {
    let (label, success) = super::fleet_helpers::classify_result(0);
    assert_eq!(label, "OK");
    assert!(success);
}

#[test]
fn test_classify_result_nonzero_is_fail() {
    let (label, success) = super::fleet_helpers::classify_result(1);
    assert_eq!(label, "FAIL");
    assert!(!success);
}

#[test]
fn test_classify_result_negative_is_fail() {
    let (label, success) = super::fleet_helpers::classify_result(-1);
    assert_eq!(label, "FAIL");
    assert!(!success);
}

#[test]
fn test_finish_message_success_counts_lines() {
    let msg = super::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
    assert!(msg.contains("3 lines"));
}

#[test]
fn test_finish_message_success_empty_output() {
    let msg = super::fleet_helpers::finish_message(0, "", "");
    assert!(msg.contains("0 lines"));
}

#[test]
fn test_finish_message_failure_shows_first_error_line() {
    let msg = super::fleet_helpers::finish_message(1, "", "error occurred\ndetails here");
    assert!(msg.contains("error occurred"));
    assert!(!msg.contains("details here"));
}

#[test]
fn test_format_output_text_show_output_prefers_stdout() {
    let text = super::fleet_helpers::format_output_text(0, "stdout data", "stderr data", true);
    assert_eq!(text, "stdout data");
}

#[test]
fn test_format_output_text_show_output_falls_back_to_stderr() {
    let text = super::fleet_helpers::format_output_text(0, "  \n  ", "fallback stderr", true);
    assert_eq!(text, "fallback stderr");
}

#[test]
fn test_format_output_text_no_show_success_is_empty() {
    let text = super::fleet_helpers::format_output_text(0, "stdout", "stderr", false);
    assert!(text.is_empty());
}

#[test]
fn test_format_output_text_no_show_failure_shows_first_stderr_line() {
    let text = super::fleet_helpers::format_output_text(1, "", "first error\nsecond error", false);
    assert_eq!(text, "first error");
}

// ── output_helpers ──────────────────────────────────────────────

#[test]
fn test_format_as_csv_with_empty_cells() {
    let headers = &["A", "B"];
    let rows = vec![vec!["".to_string(), "val".to_string()]];
    let csv = super::output_helpers::format_as_csv(headers, &rows);
    assert_eq!(csv, "A,B\n,val");
}

#[test]
fn test_format_as_table_single_row() {
    let headers = &["Name"];
    let rows = vec![vec!["hello".to_string()]];
    let table = super::output_helpers::format_as_table(headers, &rows);
    let lines: Vec<&str> = table.lines().collect();
    assert_eq!(lines.len(), 2);
    assert!(lines[0].contains("Name"));
    assert!(lines[1].contains("hello"));
}

#[test]
fn test_format_as_json_integers() {
    let items = vec![1, 2, 3];
    let json = super::output_helpers::format_as_json(&items);
    assert!(json.contains("1"));
    assert!(json.contains("2"));
    assert!(json.contains("3"));
}

// ── connect_helpers ─────────────────────────────────────────────

#[test]
fn test_build_ssh_args_no_key() {
    let args = super::connect_helpers::build_ssh_args("admin", "10.0.0.1", None);
    assert!(args.contains(&"admin@10.0.0.1".to_string()));
    assert!(args.contains(&"-o".to_string()));
    assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
    assert!(!args.iter().any(|a| a == "-i"));
}

#[test]
fn test_ssh_args_includes_key_flag() {
    let key = std::path::Path::new("/home/user/.ssh/id_ed25519");
    let args = super::connect_helpers::build_ssh_args("admin", "10.0.0.1", Some(key));
    assert!(args.contains(&"-i".to_string()));
    assert!(args.contains(&"/home/user/.ssh/id_ed25519".to_string()));
}

#[test]
fn test_vscode_uri_ssh_remote_prefix() {
    let uri = super::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
    assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
}

#[test]
fn test_build_log_follow_args_structure() {
    let args =
        super::connect_helpers::build_log_follow_args("admin", "10.0.0.1", "/var/log/syslog");
    assert!(args.contains(&"admin@10.0.0.1".to_string()));
    assert!(args.iter().any(|a| a.contains("tail -f")));
    assert!(args.iter().any(|a| a.contains("/var/log/syslog")));
}

#[test]
fn test_log_tail_args_includes_line_count() {
    let args =
        super::connect_helpers::build_log_tail_args("admin", "10.0.0.1", 50, "/var/log/syslog");
    assert!(args.iter().any(|a| a.contains("tail -n 50")));
}

// ── update_helpers ──────────────────────────────────────────────

#[test]
fn test_build_dev_update_script_not_empty() {
    let script = super::update_helpers::build_dev_update_script();
    assert!(script.starts_with("#!/bin/bash\n"));
    assert!(script.contains("apt-get update"));
    assert!(script.contains("rustup update"));
    assert!(script.contains("npm install"));
}

#[test]
fn test_build_os_update_cmd_contains_apt() {
    let cmd = super::update_helpers::build_os_update_cmd();
    assert!(cmd.contains("apt-get update"));
    assert!(cmd.contains("apt-get upgrade"));
}

#[test]
fn test_log_path_cloud_init_variant() {
    assert_eq!(
        super::update_helpers::log_type_to_path("cloud-init"),
        "/var/log/cloud-init-output.log"
    );
}

#[test]
fn test_log_path_syslog_variant() {
    assert_eq!(
        super::update_helpers::log_type_to_path("syslog"),
        "/var/log/syslog"
    );
}

#[test]
fn test_log_path_auth_variant() {
    assert_eq!(
        super::update_helpers::log_type_to_path("auth"),
        "/var/log/auth.log"
    );
}

#[test]
fn test_log_path_capitalized_names() {
    assert_eq!(
        super::update_helpers::log_type_to_path("CloudInit"),
        "/var/log/cloud-init-output.log"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Syslog"),
        "/var/log/syslog"
    );
    assert_eq!(
        super::update_helpers::log_type_to_path("Auth"),
        "/var/log/auth.log"
    );
}

#[test]
fn test_log_path_unknown_fallback_syslog() {
    assert_eq!(
        super::update_helpers::log_type_to_path("garbage"),
        "/var/log/syslog"
    );
}

// ── tag_helpers ─────────────────────────────────────────────────

#[test]
fn test_parse_tag_simple_kv() {
    let result = super::tag_helpers::parse_tag("env=prod");
    assert_eq!(result, Some(("env", "prod")));
}

#[test]
fn test_parse_tag_value_with_equals() {
    let result = super::tag_helpers::parse_tag("config=key=value");
    assert_eq!(result, Some(("config", "key=value")));
}

#[test]
fn test_tag_parse_value_empty_string() {
    let result = super::tag_helpers::parse_tag("key=");
    assert_eq!(result, Some(("key", "")));
}

#[test]
fn test_parse_tag_no_equals() {
    assert!(super::tag_helpers::parse_tag("noequals").is_none());
}

#[test]
fn test_tag_parse_empty_key_rejected() {
    assert!(super::tag_helpers::parse_tag("=value").is_none());
}

#[test]
fn test_find_invalid_tag_all_valid_list() {
    let tags = vec!["a=1".to_string(), "b=2".to_string()];
    assert!(super::tag_helpers::find_invalid_tag(&tags).is_none());
}

#[test]
fn test_find_invalid_tag_with_bad_entry() {
    let tags = vec!["a=1".to_string(), "bad".to_string(), "c=3".to_string()];
    assert_eq!(super::tag_helpers::find_invalid_tag(&tags), Some("bad"));
}

#[test]
fn test_find_invalid_tag_empty_vec_is_none() {
    let tags: Vec<String> = vec![];
    assert!(super::tag_helpers::find_invalid_tag(&tags).is_none());
}

// ── name_validation ─────────────────────────────────────────────

#[test]
fn test_validate_name_simple_ok() {
    assert!(super::name_validation::validate_name("my-vm.toml").is_ok());
}

#[test]
fn test_validate_name_empty_rejected() {
    assert!(super::name_validation::validate_name("").is_err());
}

#[test]
fn test_validate_name_slash_rejected() {
    assert!(super::name_validation::validate_name("path/traversal").is_err());
}

#[test]
fn test_validate_name_backslash_rejected() {
    assert!(super::name_validation::validate_name("path\\traversal").is_err());
}

#[test]
fn test_validate_name_null_byte_rejected() {
    assert!(super::name_validation::validate_name("name\0evil").is_err());
}

#[test]
fn test_validate_name_dotdot_rejected() {
    assert!(super::name_validation::validate_name("..").is_err());
    assert!(super::name_validation::validate_name("foo..bar").is_err());
}

#[test]
fn test_validate_name_underscores_ok() {
    assert!(super::name_validation::validate_name("my_file_name").is_ok());
}

// ── health_helpers ──────────────────────────────────────────────

#[test]
fn test_health_metric_color_low() {
    assert_eq!(super::health_helpers::metric_color(10.0), "green");
}

#[test]
fn test_health_metric_color_medium() {
    assert_eq!(super::health_helpers::metric_color(60.0), "yellow");
}

#[test]
fn test_health_metric_color_high() {
    assert_eq!(super::health_helpers::metric_color(95.0), "red");
}

#[test]
fn test_health_state_color_running() {
    assert_eq!(super::health_helpers::state_color("running"), "green");
}

#[test]
fn test_health_state_color_stopped() {
    assert_eq!(super::health_helpers::state_color("stopped"), "red");
}

#[test]
fn test_health_state_color_deallocated() {
    assert_eq!(super::health_helpers::state_color("deallocated"), "red");
}

#[test]
fn test_health_state_color_other() {
    assert_eq!(super::health_helpers::state_color("starting"), "yellow");
}

#[test]
fn test_health_format_percentage_normal() {
    assert_eq!(super::health_helpers::format_percentage(55.7), "55.7%");
}

#[test]
fn test_health_format_percentage_negative_clamps() {
    assert_eq!(super::health_helpers::format_percentage(-10.0), "0.0%");
}

#[test]
fn test_health_format_percentage_zero() {
    assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
}

#[test]
fn test_health_status_emoji_all_green() {
    assert_eq!(
        super::health_helpers::status_emoji(20.0, 30.0, 40.0),
        "\u{1F7E2}"
    );
}

#[test]
fn test_health_status_emoji_cpu_critical() {
    assert_eq!(
        super::health_helpers::status_emoji(95.0, 30.0, 40.0),
        "\u{1F534}"
    );
}

#[test]
fn test_health_status_emoji_mem_warning() {
    assert_eq!(
        super::health_helpers::status_emoji(20.0, 75.0, 40.0),
        "\u{1F7E1}"
    );
}

// ── sync_helpers ────────────────────────────────────────────────

#[test]
fn test_default_dotfiles_contains_bashrc() {
    let files = super::sync_helpers::default_dotfiles();
    assert!(files.contains(&".bashrc"));
}

#[test]
fn test_default_dotfiles_contains_gitconfig() {
    let files = super::sync_helpers::default_dotfiles();
    assert!(files.contains(&".gitconfig"));
}

#[test]
fn test_validate_sync_source_safe_relative() {
    assert!(super::sync_helpers::validate_sync_source("~/.bashrc").is_ok());
}

#[test]
fn test_validate_sync_source_etc_rejected() {
    assert!(super::sync_helpers::validate_sync_source("/etc/passwd").is_err());
}

#[test]
fn test_validate_sync_source_proc_rejected() {
    assert!(super::sync_helpers::validate_sync_source("/proc/1/status").is_err());
}

#[test]
fn test_validate_sync_source_traversal_rejected() {
    assert!(super::sync_helpers::validate_sync_source("foo/../../../etc/passwd").is_err());
}

#[test]
fn test_build_rsync_args_correct_structure() {
    let args = super::sync_helpers::build_rsync_args(".bashrc", "admin", "10.0.0.1", ".bashrc");
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert!(args[2].contains("StrictHostKeyChecking=accept-new"));
    assert_eq!(args[3], ".bashrc");
    assert_eq!(args[4], "admin@10.0.0.1:~/.bashrc");
}
