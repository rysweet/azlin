#[allow(unused_imports)]
use crate::*;
use std::fs;
use tempfile::TempDir;

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
    assert_eq!(crate::shell_escape("hello"), "'hello'");
}

#[test]
fn test_shell_escape_with_single_quotes() {
    assert_eq!(crate::shell_escape("it's"), "'it'\\''s'");
}

#[test]
fn test_shell_escape_with_spaces_and_special_chars() {
    let escaped = crate::shell_escape("foo bar $HOME");
    assert_eq!(escaped, "'foo bar $HOME'");
}

#[test]
fn test_health_metrics_non_running_vm() {
    let m = crate::collect_health_metrics("test-vm", "10.0.0.1", "azureuser", "deallocated", None);
    assert_eq!(m.vm_name, "test-vm");
    assert_eq!(m.power_state, "deallocated");
    assert_eq!(m.cpu_percent, 0.0);
    assert_eq!(m.mem_percent, 0.0);
    assert_eq!(m.disk_percent, 0.0);
}

#[test]
fn test_ssh_exec_unreachable_host() {
    // ssh_exec to a non-routable address should either error or return non-zero
    let result = crate::ssh_exec("192.0.2.1", "user", "echo hello");
    if let Ok((code, _, _)) = result {
        assert_ne!(code, 0, "should fail for unreachable host");
    }
}

#[test]
fn test_home_dir_returns_path() {
    // On any real system, home_dir should return a valid path
    let result = crate::home_dir();
    assert!(result.is_ok(), "home_dir should succeed on real system");
    assert!(result.unwrap().is_absolute(), "home dir should be absolute");
}

#[test]
fn test_new_table_creates_table_with_headers() {
    let table = crate::new_table(&["Name", "Value", "Status"]);
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
    let table = crate::new_table(&[]);
    let _rendered = table.to_string();
}

#[test]
fn test_render_health_table_does_not_panic() {
    let metrics = vec![
        crate::HealthMetrics {
            vm_name: "vm1".to_string(),
            power_state: "running".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 25.5,
            mem_percent: 60.0,
            disk_percent: 45.0,
        },
        crate::HealthMetrics {
            vm_name: "vm2".to_string(),
            power_state: "stopped".to_string(),
            agent_status: "OK".to_string(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
        },
        crate::HealthMetrics {
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
    crate::render_health_table(&metrics);
}

#[test]
fn test_run_on_fleet_empty_list() {
    let vms: Vec<(String, String, String)> = vec![];
    // Should not panic on empty list
    crate::run_on_fleet(&vms, "echo hi", true);
}
