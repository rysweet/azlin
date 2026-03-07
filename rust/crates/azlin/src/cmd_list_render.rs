//! Rendering logic for the list command (table, JSON, CSV output).
#![allow(dead_code)]

use anyhow::Result;
use azlin_core::models::VmInfo;
use comfy_table::{
    modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Color, Table,
};
use std::collections::HashMap;

/// Configuration for list rendering.
pub(crate) struct ListRenderConfig<'a> {
    pub output: &'a azlin_cli::OutputFormat,
    pub show_tmux_col: bool,
    pub wide: bool,
    pub compact: bool,
    pub with_latency: bool,
    pub with_health: bool,
    pub show_procs: bool,
    pub show_all_vms: bool,
}

/// Collected data for list rendering.
pub(crate) struct ListRenderData<'a> {
    pub vms: &'a [VmInfo],
    pub tmux_sessions: &'a HashMap<String, Vec<String>>,
    pub latencies: &'a HashMap<String, u64>,
    pub health_data: &'a HashMap<String, String>,
    pub proc_data: &'a HashMap<String, String>,
}

/// Build column headers based on configuration.
fn build_headers(cfg: &ListRenderConfig) -> Vec<&'static str> {
    let mut headers = vec!["Session"];
    if cfg.show_tmux_col {
        headers.push("Tmux");
    }
    if cfg.wide {
        headers.push("VM Name");
    }
    headers.extend_from_slice(&["OS", "Status", "IP", "Region"]);
    if cfg.wide {
        headers.push("SKU");
    }
    headers.extend_from_slice(&["CPU", "Mem"]);
    if cfg.with_latency {
        headers.push("Latency");
    }
    if cfg.with_health {
        headers.push("Health");
    }
    if cfg.show_procs {
        headers.push("Top Procs");
    }
    headers
}

/// Render the list output in the configured format.
pub(crate) fn render_list(cfg: &ListRenderConfig, data: &ListRenderData) -> Result<()> {
    let headers = build_headers(cfg);

    match cfg.output {
        azlin_cli::OutputFormat::Json => render_json(cfg, data),
        azlin_cli::OutputFormat::Csv => {
            render_csv(cfg, data, &headers);
            Ok(())
        }
        azlin_cli::OutputFormat::Table => {
            render_table(cfg, data, &headers);
            Ok(())
        }
    }
}

fn render_json(cfg: &ListRenderConfig, data: &ListRenderData) -> Result<()> {
    let json_vms: Vec<serde_json::Value> = data
        .vms
        .iter()
        .map(|vm| {
            let ip_display = crate::display_helpers::format_ip_display(
                vm.public_ip.as_deref(),
                vm.private_ip.as_deref(),
            );
            let os_display =
                crate::display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type);
            let (cpu, mem) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
            let mut obj = serde_json::json!({
                "name": vm.name,
                "resource_group": vm.resource_group,
                "power_state": vm.power_state.to_string(),
                "ip": ip_display,
                "public_ip": vm.public_ip,
                "private_ip": vm.private_ip,
                "location": vm.location,
                "vm_size": vm.vm_size,
                "os": os_display,
                "os_offer": vm.os_offer,
                "cpu": cpu,
                "mem": mem,
                "session": vm.tags.get("azlin-session").unwrap_or(&"-".to_string()),
                "tmux_sessions": data.tmux_sessions.get(&vm.name).cloned().unwrap_or_default(),
            });
            if cfg.with_latency {
                obj["latency_ms"] = serde_json::json!(data.latencies.get(&vm.name));
            }
            if cfg.with_health {
                obj["health"] = serde_json::json!(data.health_data.get(&vm.name));
            }
            obj
        })
        .collect();
    println!("{}", serde_json::to_string_pretty(&json_vms)?);
    Ok(())
}

fn render_csv(cfg: &ListRenderConfig, data: &ListRenderData, headers: &[&str]) {
    println!("{}", headers.join(","));
    for vm in data.vms {
        let session = vm
            .tags
            .get("azlin-session")
            .map(|s| s.as_str())
            .unwrap_or("-");
        let tmux = data
            .tmux_sessions
            .get(&vm.name)
            .map(|s| s.join(";"))
            .unwrap_or_default();
        let ip_display = crate::display_helpers::format_ip_display(
            vm.public_ip.as_deref(),
            vm.private_ip.as_deref(),
        );
        let os_display =
            crate::display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type);
        let (cpu, mem) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
        let mut row = session.to_string();
        if cfg.show_tmux_col {
            row.push_str(&format!(",{}", tmux));
        }
        if cfg.wide {
            row.push_str(&format!(",{}", vm.name));
        }
        row.push_str(&format!(
            ",{},{},{},{}",
            os_display, vm.power_state, ip_display, vm.location
        ));
        if cfg.wide {
            row.push_str(&format!(",{}", vm.vm_size));
        }
        row.push_str(&format!(",{},{}", cpu, mem));
        if cfg.with_latency {
            row.push_str(&format!(
                ",{}",
                data.latencies
                    .get(&vm.name)
                    .map(|l| format!("{}ms", l))
                    .unwrap_or_default()
            ));
        }
        println!("{}", row);
    }
}

fn render_table(cfg: &ListRenderConfig, data: &ListRenderData, headers: &[&str]) {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS);
    let header_cells: Vec<Cell> = headers
        .iter()
        .map(|h| Cell::new(h).add_attribute(Attribute::Bold))
        .collect();
    table.set_header(header_cells);

    let term_width = crossterm::terminal::size()
        .map(|(w, _)| w as u16)
        .unwrap_or(120);
    if cfg.compact {
        table.set_width(80.min(term_width));
    } else {
        table.set_width(term_width);
    }

    for vm in data.vms {
        let session = vm
            .tags
            .get("azlin-session")
            .map(|s| s.as_str())
            .unwrap_or("-");
        let tmux = data
            .tmux_sessions
            .get(&vm.name)
            .map(|s| crate::display_helpers::format_tmux_sessions(s, 3))
            .unwrap_or_else(|| "-".to_string());
        let ip_display = crate::display_helpers::format_ip_display(
            vm.public_ip.as_deref(),
            vm.private_ip.as_deref(),
        );
        let os_display =
            crate::display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type);
        let (cpu, mem) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
        let state_color = match vm.power_state {
            azlin_core::models::PowerState::Running => Color::Green,
            azlin_core::models::PowerState::Stopped
            | azlin_core::models::PowerState::Deallocated => Color::Red,
            _ => Color::Yellow,
        };
        let vm_name_display = if cfg.wide {
            vm.name.clone()
        } else {
            crate::display_helpers::truncate_vm_name(&vm.name, 20)
        };
        let mut row = vec![Cell::new(session)];
        if cfg.show_tmux_col {
            row.push(Cell::new(&tmux));
        }
        if cfg.wide {
            row.push(Cell::new(&vm_name_display));
        }
        row.extend_from_slice(&[
            Cell::new(&os_display),
            Cell::new(vm.power_state.to_string()).fg(state_color),
            Cell::new(&ip_display),
            Cell::new(&vm.location),
        ]);
        if cfg.wide {
            row.push(Cell::new(&vm.vm_size));
        }
        row.extend_from_slice(&[Cell::new(&cpu), Cell::new(&mem)]);
        if cfg.with_latency {
            let lat = data
                .latencies
                .get(&vm.name)
                .map(|l| format!("{}ms", l))
                .unwrap_or_else(|| "-".to_string());
            row.push(Cell::new(lat));
        }
        if cfg.with_health {
            let h = data
                .health_data
                .get(&vm.name)
                .cloned()
                .unwrap_or_else(|| "-".to_string());
            row.push(Cell::new(h));
        }
        if cfg.show_procs {
            let p = data
                .proc_data
                .get(&vm.name)
                .cloned()
                .unwrap_or_else(|| "-".to_string());
            row.push(Cell::new(p));
        }
        table.add_row(row);
    }
    println!("{table}");

    // Summary footer
    let total = data.vms.len();
    let total_tmux: usize = data.tmux_sessions.values().map(|v| v.len()).sum();
    println!();
    if total_tmux > 0 {
        println!("Total: {} VMs | {} tmux sessions", total, total_tmux);
    } else {
        println!("Total: {} VMs", total);
    }
    if !cfg.show_all_vms {
        println!();
        println!("Hints:");
        println!("  azlin list -a        Show all VMs across all resource groups");
        println!("  azlin list -w        Wide mode (show VM Name, SKU columns)");
        println!("  azlin list -r        Restore all tmux sessions in new terminal window");
        println!("  azlin list -q        Show quota usage (slower)");
        println!("  azlin list -v        Verbose mode (show tunnel/SSH details)");
    }
}
