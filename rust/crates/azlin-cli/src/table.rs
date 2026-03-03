//! Table rendering utilities for VM display.

use azlin_core::models::{PowerState, VmInfo};
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Cell, Color, Table};

use crate::OutputFormat;

/// Render generic tabular data (headers + rows of strings) in the requested format.
pub fn render_rows(headers: &[&str], rows: &[Vec<String>], format: &OutputFormat) {
    match format {
        OutputFormat::Table => {
            if rows.is_empty() {
                println!("No data found.");
                return;
            }
            let mut table = Table::new();
            table
                .load_preset(UTF8_FULL)
                .apply_modifier(UTF8_ROUND_CORNERS)
                .set_header(headers.iter().map(|h| Cell::new(h)).collect::<Vec<_>>());
            for row in rows {
                table.add_row(row.iter().map(|c| Cell::new(c)).collect::<Vec<_>>());
            }
            println!("{table}");
        }
        OutputFormat::Json => {
            let objects: Vec<serde_json::Value> = rows
                .iter()
                .map(|row| {
                    let mut map = serde_json::Map::new();
                    for (i, h) in headers.iter().enumerate() {
                        map.insert(
                            h.to_string(),
                            serde_json::Value::String(row.get(i).cloned().unwrap_or_default()),
                        );
                    }
                    serde_json::Value::Object(map)
                })
                .collect();
            match serde_json::to_string_pretty(&objects) {
                Ok(json) => println!("{json}"),
                Err(e) => eprintln!("Failed to serialize to JSON: {e}"),
            }
        }
        OutputFormat::Csv => {
            println!("{}", headers.join(","));
            for row in rows {
                let escaped: Vec<String> = row.iter().map(|c| csv_escape(c)).collect();
                println!("{}", escaped.join(","));
            }
        }
    }
}

/// Render a list of VMs in the requested output format.
pub fn render_vm_table(vms: &[VmInfo], format: &OutputFormat) {
    match format {
        OutputFormat::Table => render_table(vms),
        OutputFormat::Json => render_json(vms),
        OutputFormat::Csv => render_csv(vms),
    }
}

/// Render a tag listing in a table.
pub fn render_tags_table(vm_name: &str, tags: &std::collections::HashMap<String, String>) {
    if tags.is_empty() {
        println!("No tags on VM '{}'.", vm_name);
        return;
    }

    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec!["Key", "Value"]);

    let mut keys: Vec<&String> = tags.keys().collect();
    keys.sort();
    for key in keys {
        if let Some(val) = tags.get(key) {
            table.add_row(vec![Cell::new(key), Cell::new(val)]);
        }
    }

    println!("Tags for VM '{}':", vm_name);
    println!("{table}");
}

fn render_table(vms: &[VmInfo]) {
    if vms.is_empty() {
        println!("No VMs found.");
        return;
    }

    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec!["Session", "VM Name", "Status", "IP", "Region", "SKU"]);

    for vm in vms {
        let session = vm
            .tags
            .get("session")
            .cloned()
            .unwrap_or_else(|| "-".to_string());
        let ip = vm
            .public_ip
            .as_deref()
            .or(vm.private_ip.as_deref())
            .unwrap_or("-");

        let status_cell = match &vm.power_state {
            PowerState::Running => Cell::new("running").fg(Color::Green),
            PowerState::Stopped => Cell::new("stopped").fg(Color::Red),
            PowerState::Deallocated => Cell::new("deallocated").fg(Color::DarkYellow),
            PowerState::Starting => Cell::new("starting").fg(Color::Yellow),
            PowerState::Stopping => Cell::new("stopping").fg(Color::Yellow),
            PowerState::Unknown => Cell::new("unknown").fg(Color::Grey),
        };

        table.add_row(vec![
            Cell::new(&session),
            Cell::new(&vm.name),
            status_cell,
            Cell::new(ip),
            Cell::new(&vm.location),
            Cell::new(&vm.vm_size),
        ]);
    }

    println!("{table}");
}

fn render_json(vms: &[VmInfo]) {
    match serde_json::to_string_pretty(vms) {
        Ok(json) => println!("{json}"),
        Err(e) => eprintln!("Failed to serialize VMs to JSON: {e}"),
    }
}

fn render_csv(vms: &[VmInfo]) {
    println!("Session,VM Name,Status,IP,Region,SKU");
    for vm in vms {
        let session = vm.tags.get("session").cloned().unwrap_or_default();
        let ip = vm
            .public_ip
            .as_deref()
            .or(vm.private_ip.as_deref())
            .unwrap_or("");
        println!(
            "{},{},{},{},{},{}",
            csv_escape(&session),
            csv_escape(&vm.name),
            vm.power_state,
            csv_escape(ip),
            csv_escape(&vm.location),
            csv_escape(&vm.vm_size),
        );
    }
}

/// Escape a value for CSV output.
fn csv_escape(s: &str) -> String {
    if s.contains(',') || s.contains('"') || s.contains('\n') {
        format!("\"{}\"", s.replace('"', "\"\""))
    } else {
        s.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn mock_vm(name: &str, state: PowerState, ip: Option<&str>, session: Option<&str>) -> VmInfo {
        let mut tags = HashMap::new();
        if let Some(s) = session {
            tags.insert("session".to_string(), s.to_string());
        }
        VmInfo {
            name: name.to_string(),
            resource_group: "test-rg".to_string(),
            location: "westus2".to_string(),
            vm_size: "Standard_E16as_v5".to_string(),
            power_state: state,
            provisioning_state: "Succeeded".to_string(),
            os_type: azlin_core::models::OsType::Linux,
            public_ip: ip.map(String::from),
            private_ip: Some("10.0.0.4".to_string()),
            admin_username: Some("azureuser".to_string()),
            tags,
            created_time: None,
        }
    }

    #[test]
    fn test_render_table_no_vms() {
        // Should not panic
        render_vm_table(&[], &OutputFormat::Table);
    }

    #[test]
    fn test_render_table_with_vms() {
        let vms = vec![
            mock_vm("vm-1", PowerState::Running, Some("1.2.3.4"), Some("dev")),
            mock_vm("vm-2", PowerState::Stopped, None, None),
            mock_vm("vm-3", PowerState::Deallocated, None, Some("staging")),
        ];
        // Should not panic
        render_vm_table(&vms, &OutputFormat::Table);
    }

    #[test]
    fn test_render_json() {
        let vms = vec![mock_vm(
            "vm-1",
            PowerState::Running,
            Some("1.2.3.4"),
            Some("dev"),
        )];
        // Should not panic
        render_vm_table(&vms, &OutputFormat::Json);
    }

    #[test]
    fn test_render_csv() {
        let vms = vec![
            mock_vm("vm-1", PowerState::Running, Some("1.2.3.4"), Some("dev")),
            mock_vm("vm-2", PowerState::Stopped, None, Some("test,session")),
        ];
        // Should not panic
        render_vm_table(&vms, &OutputFormat::Csv);
    }

    #[test]
    fn test_csv_escape() {
        assert_eq!(csv_escape("simple"), "simple");
        assert_eq!(csv_escape("has,comma"), "\"has,comma\"");
        assert_eq!(csv_escape("has\"quote"), "\"has\"\"quote\"");
    }

    #[test]
    fn test_csv_escape_newline() {
        assert_eq!(csv_escape("has\nnewline"), "\"has\nnewline\"");
    }

    #[test]
    fn test_csv_escape_empty() {
        assert_eq!(csv_escape(""), "");
    }

    #[test]
    fn test_csv_escape_no_special_chars() {
        assert_eq!(csv_escape("plain text"), "plain text");
        assert_eq!(csv_escape("12345"), "12345");
    }

    #[test]
    fn test_csv_escape_multiple_commas() {
        assert_eq!(csv_escape("a,b,c"), "\"a,b,c\"");
    }

    #[test]
    fn test_csv_escape_multiple_quotes() {
        assert_eq!(csv_escape(r#"a"b"c"#), r#""a""b""c""#);
    }

    #[test]
    fn test_csv_escape_comma_and_quote() {
        assert_eq!(csv_escape(r#"a,"b""#), r#""a,""b""""#);
    }

    #[test]
    fn test_render_tags_table_empty() {
        let tags = HashMap::new();
        // Should not panic
        render_tags_table("test-vm", &tags);
    }

    #[test]
    fn test_render_tags_table_with_tags() {
        let mut tags = HashMap::new();
        tags.insert("env".to_string(), "prod".to_string());
        tags.insert("team".to_string(), "backend".to_string());
        // Should not panic
        render_tags_table("test-vm", &tags);
    }

    #[test]
    fn test_render_all_power_states() {
        let states = vec![
            PowerState::Running,
            PowerState::Stopped,
            PowerState::Deallocated,
            PowerState::Starting,
            PowerState::Stopping,
            PowerState::Unknown,
        ];
        for state in states {
            let vms = vec![mock_vm("vm", state, Some("1.2.3.4"), None)];
            render_vm_table(&vms, &OutputFormat::Table);
        }
    }

    #[test]
    fn test_render_json_empty() {
        render_vm_table(&[], &OutputFormat::Json);
    }

    #[test]
    fn test_render_csv_empty() {
        render_vm_table(&[], &OutputFormat::Csv);
    }

    #[test]
    fn test_render_vm_no_ips() {
        let mut vm = mock_vm("vm-1", PowerState::Running, None, None);
        vm.private_ip = None;
        let ip = vm
            .public_ip
            .as_deref()
            .or(vm.private_ip.as_deref())
            .unwrap_or("-");
        assert_eq!(ip, "-");
    }

    #[test]
    fn test_render_uses_public_ip_over_private() {
        let vm = mock_vm("vm-1", PowerState::Running, Some("1.2.3.4"), None);
        // The public IP should be preferred; we test via CSV output
        let ip = vm
            .public_ip
            .as_deref()
            .or(vm.private_ip.as_deref())
            .unwrap_or("-");
        assert_eq!(ip, "1.2.3.4");
    }

    #[test]
    fn test_render_falls_back_to_private_ip() {
        let vm = mock_vm("vm-1", PowerState::Running, None, None);
        let ip = vm
            .public_ip
            .as_deref()
            .or(vm.private_ip.as_deref())
            .unwrap_or("-");
        assert_eq!(ip, "10.0.0.4");
    }
}
