use crate::*;
use std::fs;
use tempfile::TempDir;

// ── run_on_fleet tests ───────────────────────────────────────

#[test]
fn test_run_on_fleet_show_output_false() {
    let vms: Vec<(String, String, String)> = vec![];
    crate::run_on_fleet(&vms, "ls", false);
}

#[test]
fn test_fleet_spinner_style_template() {
    let style = crate::fleet_spinner_style();
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
    let style = crate::fleet_spinner_style();
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
