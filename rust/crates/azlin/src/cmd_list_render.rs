//! Rendering logic for the list command (table, JSON, CSV output).
#![allow(dead_code)]

use crate::cmd_list_data::HealthMetricsData;
use anyhow::Result;
use azlin_core::models::VmInfo;
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
    pub health_data: &'a HashMap<String, HealthMetricsData>,
    pub proc_data: &'a HashMap<String, String>,
}

/// Render the list output in the configured format.
pub(crate) fn render_list(cfg: &ListRenderConfig, data: &ListRenderData) -> Result<()> {
    match cfg.output {
        azlin_cli::OutputFormat::Json => render_json(cfg, data),
        azlin_cli::OutputFormat::Csv => {
            render_csv(cfg, data);
            Ok(())
        }
        azlin_cli::OutputFormat::Table => {
            render_table(cfg, data);
            Ok(())
        }
    }
}

// ── Column definition ────────────────────────────────────────────────

struct ColDef {
    header: &'static str,
    width: usize,
    right_align: bool,
}

use crate::table_render::{trunc, trunc_right};

/// Draw a horizontal border line.
fn border_line(widths: &[usize], left: char, mid: char, right: char, fill: char) -> String {
    let mut line = String::new();
    line.push(left);
    for (i, w) in widths.iter().enumerate() {
        for _ in 0..*w + 2 {
            line.push(fill);
        }
        if i + 1 < widths.len() {
            line.push(mid);
        }
    }
    line.push(right);
    line
}

/// Render a single row with box-drawing borders.
fn render_row(cells: &[String], widths: &[usize]) -> String {
    let mut line = String::from("│");
    for (i, (cell, _w)) in cells.iter().zip(widths.iter()).enumerate() {
        line.push(' ');
        // Cell is already exactly *w chars (padded/truncated by trunc/trunc_right)
        line.push_str(cell);
        line.push(' ');
        if i + 1 < widths.len() {
            line.push('│');
        }
    }
    line.push('│');
    line
}

// ── Plain tmux formatting ────────────────────────────────────────────

/// Format tmux sessions as a plain comma-separated string.
/// Strips `:N` suffixes (e.g. "main:1" -> "main", "build:0" -> "build").
/// Shows up to `max_show` sessions; overflow is summarised as "+N".
fn format_tmux_plain(sessions: &[String], max_show: usize) -> String {
    if sessions.is_empty() {
        return "-".to_string();
    }
    let names: Vec<&str> = sessions
        .iter()
        .take(max_show)
        .map(|s| s.rsplit_once(':').map(|(n, _)| n).unwrap_or(s.as_str()))
        .collect();
    let overflow = sessions.len().saturating_sub(max_show);
    let mut result = names.join(", ");
    if overflow > 0 {
        result.push_str(&format!(", +{}", overflow));
    }
    result
}

/// Compute the width needed for the tmux column by scanning all tmux data.
/// Returns the length of the widest formatted entry, capped at `max_width`.
fn compute_tmux_content_width(
    tmux_sessions: &HashMap<String, Vec<String>>,
    max_show: usize,
    max_width: usize,
) -> usize {
    let mut widest: usize = 4; // minimum: "Tmux" header
    for sessions in tmux_sessions.values() {
        let formatted = format_tmux_plain(sessions, max_show);
        widest = widest.max(formatted.len());
    }
    widest.min(max_width)
}

// ── ANSI color helpers ───────────────────────────────────────────────

fn cyan(s: &str) -> String {
    format!("\x1b[36m{}\x1b[0m", s)
}
fn green(s: &str) -> String {
    format!("\x1b[32m{}\x1b[0m", s)
}
fn red(s: &str) -> String {
    format!("\x1b[31m{}\x1b[0m", s)
}
fn yellow(s: &str) -> String {
    format!("\x1b[33m{}\x1b[0m", s)
}
fn dim(s: &str) -> String {
    format!("\x1b[2m{}\x1b[0m", s)
}
fn dim_yellow(s: &str) -> String {
    format!("\x1b[2;33m{}\x1b[0m", s)
}
fn bold(s: &str) -> String {
    format!("\x1b[1m{}\x1b[0m", s)
}

/// Color a status string based on VM power state.
fn color_status(state: &azlin_core::models::PowerState) -> String {
    let s = state.to_string();
    match state {
        azlin_core::models::PowerState::Running => green(&s),
        azlin_core::models::PowerState::Stopped | azlin_core::models::PowerState::Deallocated => {
            red(&s)
        }
        _ => yellow(&s),
    }
}

/// Wrap a pre-padded cell string with ANSI color. The padding is done BEFORE
/// coloring so ANSI codes don't affect width calculation.
fn color_cell(padded: &str, color_fn: fn(&str) -> String) -> String {
    color_fn(padded)
}

// ── Table renderer ───────────────────────────────────────────────────

fn render_table(cfg: &ListRenderConfig, data: &ListRenderData) {
    let term_width = crossterm::terminal::size()
        .map(|(w, _)| w as usize)
        .unwrap_or(120);

    // Build column definitions based on config and terminal width.
    // Start with minimum columns, then allocate remaining space.
    let mut cols: Vec<ColDef> = Vec::new();

    let session_w = if cfg.compact { 10 } else { 11 };
    cols.push(ColDef {
        header: "Session",
        width: session_w,
        right_align: false,
    });

    if cfg.show_tmux_col {
        // Size the tmux column to fit the widest entry — no hard cap so
        // session names are never truncated.  The shrink pass below will
        // compress other columns first if the table exceeds terminal width.
        let tmux_w = compute_tmux_content_width(data.tmux_sessions, usize::MAX, usize::MAX).max(if cfg.compact {
            18
        } else {
            22
        });
        cols.push(ColDef {
            header: "Tmux",
            width: tmux_w,
            right_align: false,
        });
    }
    if cfg.wide {
        cols.push(ColDef {
            header: "VM Name",
            width: 20,
            right_align: false,
        });
    }

    let os_w = if cfg.compact { 10 } else { 14 };
    cols.push(ColDef {
        header: "OS",
        width: os_w,
        right_align: false,
    });

    cols.push(ColDef {
        header: "Status",
        width: 7,
        right_align: false,
    });

    let ip_w = if cfg.compact { 12 } else { 17 };
    cols.push(ColDef {
        header: "IP",
        width: ip_w,
        right_align: false,
    });

    let rgn_w = if cfg.compact { 5 } else { 14 };
    cols.push(ColDef {
        header: "Region",
        width: rgn_w,
        right_align: false,
    });

    if cfg.wide {
        cols.push(ColDef {
            header: "SKU",
            width: 15,
            right_align: false,
        });
    }

    cols.push(ColDef {
        header: "CPU",
        width: 3,
        right_align: true,
    });
    cols.push(ColDef {
        header: "Mem",
        width: 6,
        right_align: true,
    });

    if cfg.with_latency {
        cols.push(ColDef {
            header: "Latency",
            width: 7,
            right_align: true,
        });
    }
    if cfg.with_health {
        cols.push(ColDef {
            header: "Agent",
            width: 8,
            right_align: false,
        });
        cols.push(ColDef {
            header: "CPU%",
            width: 5,
            right_align: true,
        });
        cols.push(ColDef {
            header: "Mem%",
            width: 5,
            right_align: true,
        });
        cols.push(ColDef {
            header: "Disk%",
            width: 5,
            right_align: true,
        });
    }
    if cfg.show_procs {
        cols.push(ColDef {
            header: "Procs",
            width: 25,
            right_align: false,
        });
    }

    // If total width exceeds terminal, shrink less-important columns first
    // (Status, Region, CPU, Mem down to 3 chars each) before touching
    // Session or Tmux, so session names stay fully visible.
    let border_overhead = cols.len() * 3 + 1; // "│ " + " " per col + final "│"
    let content_budget = term_width.saturating_sub(border_overhead);
    let total_content: usize = cols.iter().map(|c| c.width).sum();
    if total_content > content_budget {
        let mut excess = total_content - content_budget;
        // Priority 1: shrink these columns first (order: Region, Status, CPU, Mem)
        let shrinkable_first = ["Region", "Status", "CPU", "Mem"];
        for header in &shrinkable_first {
            if excess == 0 {
                break;
            }
            if let Some(col) = cols.iter_mut().find(|c| c.header == *header) {
                let can_give = col.width.saturating_sub(3);
                let give = can_give.min(excess);
                col.width -= give;
                excess -= give;
            }
        }
        // Priority 2: shrink other columns (OS, IP, VM Name, SKU, etc.)
        // but NOT Session or Tmux — those must stay fully visible.
        let protected = ["Session", "Tmux"];
        if excess > 0 {
            let shrinkable: usize = cols
                .iter()
                .filter(|c| !protected.contains(&c.header))
                .map(|c| c.width.saturating_sub(3))
                .sum();
            if shrinkable > 0 {
                let ratio = excess.min(shrinkable) as f64 / shrinkable as f64;
                for col in &mut cols {
                    if protected.contains(&col.header) {
                        continue;
                    }
                    let can_give = col.width.saturating_sub(3);
                    let give = (can_give as f64 * ratio).ceil() as usize;
                    let give = give.min(can_give).min(excess);
                    col.width -= give;
                    excess -= give;
                    if excess == 0 {
                        break;
                    }
                }
            }
        }
        // Priority 3 (last resort): shrink Session and Tmux proportionally
        if excess > 0 {
            let remaining_total: usize = cols.iter().map(|c| c.width.saturating_sub(3)).sum();
            if remaining_total > 0 {
                let ratio = excess.min(remaining_total) as f64 / remaining_total as f64;
                for col in &mut cols {
                    let can_give = col.width.saturating_sub(3);
                    let give = (can_give as f64 * ratio).ceil() as usize;
                    let give = give.min(can_give).min(excess);
                    col.width -= give;
                    excess -= give;
                    if excess == 0 {
                        break;
                    }
                }
            }
        }
    }

    let widths: Vec<usize> = cols.iter().map(|c| c.width).collect();

    // Header
    println!("{}", border_line(&widths, '┌', '┬', '┐', '─'));
    let header_cells: Vec<String> = cols
        .iter()
        .map(|c| bold(&trunc(c.header, c.width)))
        .collect();
    println!("{}", render_row(&header_cells, &widths));
    println!("{}", border_line(&widths, '├', '┼', '┤', '─'));

    // Data rows
    for vm in data.vms {
        let session = vm
            .tags
            .get("azlin-session")
            .map(|s| s.as_str())
            .unwrap_or("-");

        let mut cells: Vec<String> = Vec::new();
        let mut col_i = 0;

        // Session
        cells.push(cyan(&trunc(session, cols[col_i].width)));
        col_i += 1;

        // Tmux — show all session names; pad or truncate to exact column width
        // so borders stay aligned.  The column is sized to the widest entry
        // and protected from shrinking, so truncation should be rare (only
        // when terminal is extremely narrow).
        if cfg.show_tmux_col {
            let tmux_text = data
                .tmux_sessions
                .get(&vm.name)
                .map(|s| format_tmux_plain(s, usize::MAX))
                .unwrap_or_else(|| "-".to_string());
            let w = cols[col_i].width;
            let padded = if tmux_text.len() <= w {
                format!("{:<width$}", tmux_text, width = w)
            } else {
                // Last resort: terminal too narrow, must truncate for alignment
                trunc(&tmux_text, w)
            };
            cells.push(padded);
            col_i += 1;
        }

        // VM Name
        if cfg.wide {
            cells.push(trunc(&vm.name, cols[col_i].width));
            col_i += 1;
        }

        // OS
        let os_str = crate::display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type);
        cells.push(trunc(&os_str, cols[col_i].width));
        col_i += 1;

        // Status (colored)
        let status_padded = trunc(&vm.power_state.to_string(), cols[col_i].width);
        cells.push(
            color_status(&vm.power_state).replace(&vm.power_state.to_string(), &status_padded),
        );
        col_i += 1;

        // IP
        let ip_str = crate::display_helpers::format_ip_display(
            vm.public_ip.as_deref(),
            vm.private_ip.as_deref(),
        );
        cells.push(dim_yellow(&trunc(&ip_str, cols[col_i].width)));
        col_i += 1;

        // Region
        cells.push(dim(&trunc(&vm.location, cols[col_i].width)));
        col_i += 1;

        // SKU
        if cfg.wide {
            cells.push(dim(&trunc(&vm.vm_size, cols[col_i].width)));
            col_i += 1;
        }

        // CPU
        let (cpu, mem_str) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
        cells.push(dim(&trunc_right(&cpu, cols[col_i].width)));
        col_i += 1;

        // Mem
        cells.push(dim(&trunc_right(&mem_str, cols[col_i].width)));
        col_i += 1;

        // Latency
        if cfg.with_latency {
            let lat = data
                .latencies
                .get(&vm.name)
                .map(|l| format!("{}ms", l))
                .unwrap_or_else(|| "-".to_string());
            cells.push(trunc_right(&lat, cols[col_i].width));
            col_i += 1;
        }

        // Health - 4 columns: Agent, CPU%, Mem%, Disk%
        if cfg.with_health {
            let health = data.health_data.get(&vm.name);

            // Agent status
            let agent = health.map(|h| h.agent_status.as_str()).unwrap_or("-");
            let agent_colored = match agent {
                "Active" => green(agent),
                "Inactive" | "N/A" => dim(agent),
                "Failed" => red(agent),
                _ => dim(agent),
            };
            let agent_padded = trunc(&agent_colored, cols[col_i].width);
            cells.push(agent_padded);
            col_i += 1;

            // CPU%
            let cpu = health.map(|h| format!("{:.1}", h.cpu_percent)).unwrap_or_else(|| "-".to_string());
            cells.push(dim(&trunc_right(&cpu, cols[col_i].width)));
            col_i += 1;

            // Mem%
            let mem = health.map(|h| format!("{:.1}", h.mem_percent)).unwrap_or_else(|| "-".to_string());
            cells.push(dim(&trunc_right(&mem, cols[col_i].width)));
            col_i += 1;

            // Disk%
            let disk = health.map(|h| format!("{:.1}", h.disk_percent)).unwrap_or_else(|| "-".to_string());
            cells.push(dim(&trunc_right(&disk, cols[col_i].width)));
            col_i += 1;
        }

        // Procs
        if cfg.show_procs {
            let p = data
                .proc_data
                .get(&vm.name)
                .cloned()
                .unwrap_or_else(|| "-".to_string());
            cells.push(green(&trunc(&p, cols[col_i].width)));
        }

        println!("{}", render_row(&cells, &widths));
    }

    // Bottom border
    println!("{}", border_line(&widths, '└', '┴', '┘', '─'));

    // Summary footer
    let total = data.vms.len();
    let running = data
        .vms
        .iter()
        .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
        .count();
    let total_tmux: usize = data.tmux_sessions.values().map(|v| v.len()).sum();
    println!();
    let summary = if total_tmux > 0 {
        format!(
            "Total: {} VMs | {} running | {} tmux sessions",
            total, running, total_tmux
        )
    } else {
        format!("Total: {} VMs | {} running", total, running)
    };
    println!("{}", bold(&summary));
    if !cfg.show_all_vms {
        println!();
        println!("{}", dim("Hints:"));
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
            println!("  {}  {}", cyan(flag), dim(desc));
        }
    }
}

// ── JSON renderer ────────────────────────────────────────────────────

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
                if let Some(health) = data.health_data.get(&vm.name) {
                    obj["health"] = serde_json::json!({
                        "agent_status": health.agent_status,
                        "cpu_percent": health.cpu_percent,
                        "mem_percent": health.mem_percent,
                        "disk_percent": health.disk_percent,
                        "error_count": health.error_count,
                    });
                } else {
                    obj["health"] = serde_json::Value::Null;
                }
            }
            obj
        })
        .collect();
    println!("{}", serde_json::to_string_pretty(&json_vms)?);
    Ok(())
}

// ── CSV renderer ─────────────────────────────────────────────────────

fn render_csv(cfg: &ListRenderConfig, data: &ListRenderData) {
    // Build headers
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
        headers.extend_from_slice(&["Agent", "CPU%", "Mem%", "Disk%"]);
    }
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
        if cfg.with_health {
            if let Some(health) = data.health_data.get(&vm.name) {
                row.push_str(&format!(
                    ",{},{:.1},{:.1},{:.1}",
                    health.agent_status,
                    health.cpu_percent,
                    health.mem_percent,
                    health.disk_percent
                ));
            } else {
                row.push_str(",-,-,-,-");
            }
        }
        println!("{}", row);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cmd_list_data::HealthMetricsData;

    // ── format_tmux_plain ─────────────────────────────────────────────

    #[test]
    fn tmux_plain_empty_returns_dash() {
        assert_eq!(format_tmux_plain(&[], 10), "-");
    }

    #[test]
    fn tmux_plain_strips_colon_suffix() {
        let sessions = vec!["main:1".to_string(), "build:0".to_string()];
        assert_eq!(format_tmux_plain(&sessions, 10), "main, build");
    }

    #[test]
    fn tmux_plain_no_suffix() {
        let sessions = vec!["dev".to_string()];
        assert_eq!(format_tmux_plain(&sessions, 10), "dev");
    }

    #[test]
    fn tmux_plain_unlimited_shows_all() {
        let sessions: Vec<String> = (1..=10).map(|i| format!("sess-{}", i)).collect();
        let result = format_tmux_plain(&sessions, usize::MAX);
        // All 10 sessions should appear, no "+N" overflow
        for i in 1..=10 {
            assert!(result.contains(&format!("sess-{}", i)), "missing sess-{}", i);
        }
        assert!(!result.contains('+'), "should not contain overflow indicator");
    }

    // ── compute_tmux_content_width ────────────────────────────────────

    #[test]
    fn tmux_width_empty_map_returns_header_width() {
        let map = HashMap::new();
        assert_eq!(compute_tmux_content_width(&map, usize::MAX, usize::MAX), 4);
    }

    #[test]
    fn tmux_width_matches_widest_entry() {
        let mut map = HashMap::new();
        map.insert("vm1".into(), vec!["short:0".to_string()]);
        map.insert(
            "vm2".into(),
            vec![
                "long-session-name-alpha:1".to_string(),
                "long-session-name-beta:0".to_string(),
            ],
        );
        let width = compute_tmux_content_width(&map, usize::MAX, usize::MAX);
        // vm2 formatted: "long-session-name-alpha, long-session-name-beta"
        let expected = "long-session-name-alpha, long-session-name-beta".len();
        assert_eq!(width, expected);
    }

    #[test]
    fn tmux_width_no_cap_allows_long_entries() {
        let mut map = HashMap::new();
        // Create a session list that exceeds 60 chars when formatted
        let sessions: Vec<String> = (1..=8)
            .map(|i| format!("my-long-session-name-{}:0", i))
            .collect();
        map.insert("vm1".into(), sessions);
        let width = compute_tmux_content_width(&map, usize::MAX, usize::MAX);
        // Should be well over 60 chars
        assert!(width > 60, "width {} should exceed 60 with no cap", width);
    }

    #[test]
    fn tmux_width_respects_cap_when_given() {
        let mut map = HashMap::new();
        let sessions: Vec<String> = (1..=8)
            .map(|i| format!("my-long-session-name-{}:0", i))
            .collect();
        map.insert("vm1".into(), sessions);
        let width = compute_tmux_content_width(&map, usize::MAX, 60);
        assert_eq!(width, 60);
    }

    // ── Column shrink priority ────────────────────────────────────────

    /// Verify that the shrink logic protects Tmux column from being reduced
    /// before less-important columns are fully compressed.
    #[test]
    fn shrink_protects_tmux_column() {
        // Simulate the shrink logic from render_table by building ColDefs
        // manually and applying the same algorithm.
        let mut cols = vec![
            ColDef { header: "Session", width: 11, right_align: false },
            ColDef { header: "Tmux",    width: 50, right_align: false },
            ColDef { header: "OS",      width: 14, right_align: false },
            ColDef { header: "Status",  width: 7,  right_align: false },
            ColDef { header: "IP",      width: 17, right_align: false },
            ColDef { header: "Region",  width: 14, right_align: false },
            ColDef { header: "CPU",     width: 3,  right_align: true },
            ColDef { header: "Mem",     width: 6,  right_align: true },
        ];
        let term_width: usize = 100;
        let border_overhead = cols.len() * 3 + 1;
        let content_budget = term_width.saturating_sub(border_overhead);
        let total_content: usize = cols.iter().map(|c| c.width).sum();

        assert!(total_content > content_budget, "test setup: must exceed budget");

        let mut excess = total_content - content_budget;

        // Priority 1: shrink Region, Status, CPU, Mem
        let shrinkable_first = ["Region", "Status", "CPU", "Mem"];
        for header in &shrinkable_first {
            if excess == 0 { break; }
            if let Some(col) = cols.iter_mut().find(|c| c.header == *header) {
                let can_give = col.width.saturating_sub(3);
                let give = can_give.min(excess);
                col.width -= give;
                excess -= give;
            }
        }

        // Priority 2: shrink non-protected columns
        let protected = ["Session", "Tmux"];
        if excess > 0 {
            let shrinkable: usize = cols.iter()
                .filter(|c| !protected.contains(&c.header))
                .map(|c| c.width.saturating_sub(3))
                .sum();
            if shrinkable > 0 {
                let ratio = excess.min(shrinkable) as f64 / shrinkable as f64;
                for col in &mut cols {
                    if protected.contains(&col.header) { continue; }
                    let can_give = col.width.saturating_sub(3);
                    let give = (can_give as f64 * ratio).ceil() as usize;
                    let give = give.min(can_give).min(excess);
                    col.width -= give;
                    excess -= give;
                    if excess == 0 { break; }
                }
            }
        }

        // After priorities 1 and 2, Tmux should still be 50
        let tmux_col = cols.iter().find(|c| c.header == "Tmux").unwrap();
        assert_eq!(
            tmux_col.width, 50,
            "Tmux column should not be shrunk when other columns can absorb the excess"
        );
    }
}
