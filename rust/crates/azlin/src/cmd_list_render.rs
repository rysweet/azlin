//! Rendering logic for the list command (table, JSON, CSV output).
#![allow(dead_code)]

use anyhow::Result;
use azlin_core::models::VmInfo;
use comfy_table::{
    presets::UTF8_FULL_CONDENSED, Attribute, Cell, CellAlignment, Color, ColumnConstraint, Table,
    Width,
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

/// Set a maximum width constraint on a table column.
fn set_col_max(table: &mut Table, idx: usize, max: u16) {
    if let Some(col) = table.column_mut(idx) {
        col.set_constraint(ColumnConstraint::UpperBoundary(Width::Fixed(max)));
    }
}

/// Truncate a string to max_len visible characters, appending "..." if needed.
fn truncate_str(s: &str, max_len: usize) -> String {
    if s.len() <= max_len {
        s.to_string()
    } else if max_len <= 3 {
        s.chars().take(max_len).collect()
    } else {
        let truncated: String = s.chars().take(max_len - 3).collect();
        format!("{}...", truncated)
    }
}

/// Format tmux sessions as plain text, truncated to max_width.
/// Input format: `session_name:attached_flag` (e.g. "main:1", "build:0")
/// Returns plain text only — no ANSI codes (comfy_table can't measure them).
fn format_tmux_plain(sessions: &[String], max_show: usize, max_width: usize) -> String {
    if sessions.is_empty() {
        return "-".to_string();
    }

    // Strip the `:0`/`:1` suffix to get plain session names
    let names: Vec<&str> = sessions
        .iter()
        .take(max_show)
        .map(|s| {
            s.rsplit_once(':')
                .map(|(name, _)| name)
                .unwrap_or(s.as_str())
        })
        .collect();
    let overflow_count = sessions.len().saturating_sub(max_show);

    let mut result = String::new();
    let mut plain_len = 0usize;
    for (i, name) in names.iter().enumerate() {
        let sep = if i > 0 { ", " } else { "" };
        let needed = sep.len() + name.len();
        if plain_len + needed > max_width && !result.is_empty() {
            result.push_str("...");
            return result;
        }
        plain_len += needed;
        result.push_str(sep);
        result.push_str(name);
    }
    if overflow_count > 0 {
        result.push_str(&format!(", +{}", overflow_count));
    }
    // Final truncation safety net
    truncate_str(&result, max_width)
}

fn render_table(cfg: &ListRenderConfig, data: &ListRenderData, headers: &[&str]) {
    let mut table = Table::new();
    table.load_preset(UTF8_FULL_CONDENSED);
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

    // Set column constraints matching Python's explicit widths.
    // Column indices depend on which optional columns are present.
    let mut col_idx = 0usize;
    // Session
    set_col_max(&mut table, col_idx, if cfg.compact { 12 } else { 14 });
    col_idx += 1;
    // Tmux (optional)
    if cfg.show_tmux_col {
        set_col_max(&mut table, col_idx, if cfg.compact { 20 } else { 25 });
        col_idx += 1;
    }
    // VM Name (optional, wide only)
    if cfg.wide {
        col_idx += 1; // no constraint — let it expand
    }
    // OS
    set_col_max(&mut table, col_idx, if cfg.compact { 12 } else { 18 });
    col_idx += 1;
    // Status
    set_col_max(&mut table, col_idx, 8);
    col_idx += 1;
    // IP
    set_col_max(&mut table, col_idx, 18);
    col_idx += 1;
    // Region
    set_col_max(&mut table, col_idx, if cfg.compact { 6 } else { 16 });
    col_idx += 1;
    // SKU (optional, wide only)
    if cfg.wide {
        set_col_max(&mut table, col_idx, 15);
        col_idx += 1;
    }
    // CPU
    set_col_max(&mut table, col_idx, 4);
    col_idx += 1;
    // Mem
    set_col_max(&mut table, col_idx, 7);

    for vm in data.vms {
        let session = vm
            .tags
            .get("azlin-session")
            .map(|s| s.as_str())
            .unwrap_or("-");
        let tmux = data
            .tmux_sessions
            .get(&vm.name)
            .map(|s| {
                let max_w = if cfg.compact { 18 } else { 22 };
                format_tmux_plain(s, 3, max_w)
            })
            .unwrap_or_else(|| "-".to_string());
        let ip_raw = crate::display_helpers::format_ip_display(
            vm.public_ip.as_deref(),
            vm.private_ip.as_deref(),
        );
        let ip_display = truncate_str(&ip_raw, 18);
        let os_max = if cfg.compact { 12 } else { 18 };
        let os_display = truncate_str(
            &crate::display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type),
            os_max,
        );
        let rgn_max = if cfg.compact { 6 } else { 16 };
        let region_display = truncate_str(&vm.location, rgn_max);
        let (cpu, mem) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
        let state_color = match vm.power_state {
            azlin_core::models::PowerState::Running => Color::Green,
            azlin_core::models::PowerState::Stopped
            | azlin_core::models::PowerState::Deallocated => Color::Red,
            _ => Color::Yellow,
        };
        let session_display = truncate_str(session, if cfg.compact { 12 } else { 14 });
        let vm_name_display = if cfg.wide {
            vm.name.clone()
        } else {
            crate::display_helpers::truncate_vm_name(&vm.name, 20)
        };
        let mut row = vec![Cell::new(&session_display).fg(Color::Cyan)];
        if cfg.show_tmux_col {
            row.push(Cell::new(&tmux));
        }
        if cfg.wide {
            row.push(Cell::new(&vm_name_display));
        }
        row.extend_from_slice(&[
            Cell::new(&os_display),
            Cell::new(vm.power_state.to_string()).fg(state_color),
            Cell::new(&ip_display).fg(Color::DarkYellow),
            Cell::new(&region_display).fg(Color::Grey),
        ]);
        if cfg.wide {
            row.push(Cell::new(truncate_str(&vm.vm_size, 15)));
        }
        row.extend_from_slice(&[
            Cell::new(&cpu)
                .fg(Color::Grey)
                .set_alignment(CellAlignment::Right),
            Cell::new(&mem)
                .fg(Color::Grey)
                .set_alignment(CellAlignment::Right),
        ]);
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
            row.push(Cell::new(p).fg(Color::Green));
        }
        table.add_row(row);
    }
    println!("{table}");

    // Summary footer (bold, matching Python)
    let total = data.vms.len();
    let running = data
        .vms
        .iter()
        .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
        .count();
    let total_tmux: usize = data.tmux_sessions.values().map(|v| v.len()).sum();
    println!();
    let bold = console::Style::new().bold();
    let cyan = console::Style::new().cyan();
    let dim = console::Style::new().dim();
    let summary = if total_tmux > 0 {
        format!(
            "Total: {} VMs | {} running | {} tmux sessions",
            total, running, total_tmux
        )
    } else {
        format!("Total: {} VMs | {} running", total, running)
    };
    println!("{}", bold.apply_to(&summary));
    if !cfg.show_all_vms {
        println!();
        println!("{}", dim.apply_to("Hints:"));
        for (flag, desc) in [
            ("azlin list -a", "Show all VMs across all resource groups"),
            ("azlin list -w", "Wide mode (show VM Name, SKU columns)"),
            (
                "azlin list -r",
                "Restore all tmux sessions in new terminal window",
            ),
            ("azlin list -q", "Show quota usage (slower)"),
            ("azlin list -v", "Verbose mode (show tunnel/SSH details)"),
        ] {
            println!("  {}  {}", cyan.apply_to(flag), dim.apply_to(desc));
        }
    }
}
