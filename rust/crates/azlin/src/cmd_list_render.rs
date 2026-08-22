//! Rendering logic for the list command (table, JSON, CSV output).
#![allow(dead_code)]

use crate::list_disclosure;
use crate::list_helpers::FilterCounts;
use anyhow::Result;
use azlin_core::models::VmInfo;
use std::collections::HashMap;

/// Write the filter disclosure (#1142) to stderr, or nothing if nothing was
/// filtered.
///
/// `-o json` and `-o csv` own their stdout: prose there would corrupt a payload
/// piped into `jq` or Python's `csv`, and CSV has no metadata channel at all (a
/// `#` comment is a bogus record; an extra column vanishes precisely when the
/// result set is empty). stderr reaches the operator at a terminal and never
/// reaches the parser -- the channel `azlin list` already uses for such notes.
fn disclose_on_stderr(filters: &FilterCounts) {
    for line in list_disclosure::stderr_lines(filters) {
        eprintln!("{line}");
    }
}

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
    pub health_data: &'a HashMap<String, crate::HealthMetrics>,
    pub storage_data: &'a HashMap<String, azlin_azure::disk_layout::StorageStatus>,
    pub proc_data: &'a HashMap<String, String>,
    /// What `apply_filters` removed on the way here. Carried by value (it is
    /// three `usize`s) so every renderer can disclose it -- the whole point of
    /// #1142 is that no output surface gets to stay silent about it.
    pub filters: FilterCounts,
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

/// Apply ANSI color based on threshold level.
fn threshold_ansi(level: crate::error_helpers::ThresholdLevel, s: &str) -> String {
    match level {
        crate::error_helpers::ThresholdLevel::Normal => format!("\x1b[32m{}\x1b[0m", s),
        crate::error_helpers::ThresholdLevel::Warning => format!("\x1b[33m{}\x1b[0m", s),
        crate::error_helpers::ThresholdLevel::Critical => format!("\x1b[31m{}\x1b[0m", s),
    }
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

// ── Azure-supplied text, sanitized for display ───────────────────────

/// The Azure-supplied strings of one VM, sanitized once for display.
///
/// A VM name, an `azlin-session` tag value, a region, a SKU and an OS offer are
/// all echoed back from Azure exactly as whoever created them typed them, and
/// anyone with write access to the subscription chooses them. A name carrying
/// `ESC [ 2 K` and a carriage return erases the row that reports it and prints
/// whatever follows in its place, so the operator reads a fleet that does not
/// exist. This is the same treatment, and the same reasoning, that the "Azure
/// Bastion Hosts" table applies to a bastion's name, location and SKU.
///
/// Alignment is the second reason. [`trunc`] pads a cell to an exact count of
/// *visible* columns, but a control character is one `char` that occupies no
/// column, so an unsanitized name silently breaks every border to its right.
/// Sanitizing before the width is measured is what keeps the two in step.
///
/// Built once per VM and shared by the table and CSV writers, so neither can
/// forget a field the other remembers.
///
/// This deliberately holds *display* copies only. `vm.name` is also the key of
/// `tmux_sessions`, `latencies`, `health_data` and `proc_data`, and those
/// lookups must keep using the raw name — sanitizing a key would silently miss
/// the entry it names.
///
/// JSON output does not come through here, and deliberately is not sanitized:
/// its consumer is a machine, and a machine consumer must keep the exact bytes
/// Azure returned. Note the limit of what `serde_json` does for a human who
/// `cat`s that JSON to a terminal anyway -- its escape table covers `0x00`
/// through `0x1F`, `"` and `\` and nothing else, so `U+007F`, the C1 range and
/// `U+2028` are emitted raw. Rendering JSON safely is the terminal's problem,
/// not this module's; escaping it here would corrupt the contract.
struct VmDisplayText {
    session: String,
    name: String,
    os: String,
    ip: String,
    location: String,
    vm_size: String,
}

impl VmDisplayText {
    fn for_vm(vm: &VmInfo) -> Self {
        use crate::cmd_list_data::sanitize_remote_text;
        Self {
            session: vm
                .tags
                .get("azlin-session")
                .map(|s| sanitize_remote_text(s))
                .unwrap_or_else(|| "-".to_string()),
            name: sanitize_remote_text(&vm.name),
            // `format_os_display` echoes the offer back for Ubuntu, so the
            // rendered string is Azure text even though the fallback is an enum.
            os: sanitize_remote_text(&crate::display_helpers::format_os_display(
                vm.os_offer.as_deref(),
                &vm.os_type,
            )),
            ip: sanitize_remote_text(&crate::display_helpers::format_ip_display(
                vm.public_ip.as_deref(),
                vm.private_ip.as_deref(),
            )),
            location: sanitize_remote_text(&vm.location),
            vm_size: sanitize_remote_text(&vm.vm_size),
        }
    }
}

// ── Table renderer ───────────────────────────────────────────────────

fn render_table(cfg: &ListRenderConfig, data: &ListRenderData) {
    let term_width = crossterm::terminal::size()
        .map(|(w, _)| w as usize)
        .unwrap_or(120);

    // Sanitized once per VM, up front, because the width pass and the row pass
    // both need it and each used to build its own copy -- six sanitized
    // `String`s allocated per VM, measured, thrown away, and allocated again a
    // hundred lines below. Sizing a column against text other than the text
    // that will be printed is also how a border ends up in the wrong place, so
    // sharing one value is the safer arrangement as well as the cheaper one.
    let display: Vec<VmDisplayText> = data.vms.iter().map(VmDisplayText::for_vm).collect();

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
        let tmux_w = compute_tmux_content_width(data.tmux_sessions, usize::MAX, usize::MAX)
            .max(if cfg.compact { 18 } else { 22 });
        cols.push(ColDef {
            header: "Tmux",
            width: tmux_w,
            right_align: false,
        });
    }
    if cfg.wide {
        // Size VM Name to fit the widest entry so names are never truncated
        // (this is the main reason users pass -w).
        // Measured on the sanitized name, which is what actually gets printed.
        // Measuring the raw one would size the column for characters that
        // occupy no columns, padding every row past the border.
        let vm_name_w = display
            .iter()
            .map(|d| d.name.chars().count())
            .max()
            .unwrap_or(7)
            .max(7); // minimum = header width
        cols.push(ColDef {
            header: "VM Name",
            width: vm_name_w,
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
        // Widths by header, so a column added to HEALTH_COLUMNS cannot be
        // rendered without one.
        for header in crate::health_render::HEALTH_COLUMNS {
            let (width, right_align) = match *header {
                "Agent" => (5, false),
                "Storage" => (8, false),
                _ => (5, true),
            };
            cols.push(ColDef {
                header,
                width,
                right_align,
            });
        }
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
        // Priority 2: shrink other columns (OS, IP, SKU, etc.)
        // but NOT Session, Tmux, or VM Name — those must stay fully visible.
        let protected = ["Session", "Tmux", "VM Name"];
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
        // VM Name stays protected — it is the primary reason users pass -w.
        if excess > 0 {
            let remaining_total: usize = cols
                .iter()
                .filter(|c| c.header != "VM Name")
                .map(|c| c.width.saturating_sub(3))
                .sum();
            if remaining_total > 0 {
                let ratio = excess.min(remaining_total) as f64 / remaining_total as f64;
                for col in &mut cols {
                    if col.header == "VM Name" {
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
    for (vm, disp) in data.vms.iter().zip(&display) {
        let mut cells: Vec<String> = Vec::new();
        let mut col_i = 0;

        // Session
        cells.push(cyan(&trunc(&disp.session, cols[col_i].width)));
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
            cells.push(trunc(&disp.name, cols[col_i].width));
            col_i += 1;
        }

        // OS
        cells.push(trunc(&disp.os, cols[col_i].width));
        col_i += 1;

        // Status (colored)
        let status_padded = trunc(&vm.power_state.to_string(), cols[col_i].width);
        cells.push(
            color_status(&vm.power_state).replace(&vm.power_state.to_string(), &status_padded),
        );
        col_i += 1;

        // IP
        cells.push(dim_yellow(&trunc(&disp.ip, cols[col_i].width)));
        col_i += 1;

        // Region
        cells.push(dim(&trunc(&disp.location, cols[col_i].width)));
        col_i += 1;

        // SKU
        if cfg.wide {
            cells.push(dim(&trunc(&disp.vm_size, cols[col_i].width)));
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

        // Health columns, always HEALTH_COLUMNS long: a row that is silently
        // short shifts every column after it.
        if cfg.with_health {
            let metrics = data.health_data.get(&vm.name);
            let storage = data.storage_data.get(&vm.name).copied();
            let texts = crate::health_render::health_cells(metrics, storage);
            for (header, text) in crate::health_render::HEALTH_COLUMNS.iter().zip(&texts) {
                let width = cols[col_i].width;
                // Colour is decided per column, and an unmeasured value is
                // never painted green: green is the claim that the machine is
                // fine, which is exactly what could not be checked.
                let cell = match *header {
                    "Agent" => {
                        let padded = trunc(text, width);
                        match crate::health_render::agent_level(
                            metrics.map(|m| m.agent_status.as_str()),
                        ) {
                            Some(level) => threshold_ansi(level, &padded),
                            None => padded,
                        }
                    }
                    // Coloured from the enum, not from the text it rendered to:
                    // matching on `"ok"`/`"degraded"` couples the colour to a
                    // spelling the compiler cannot see, so renaming the display
                    // text would silently stop painting a degraded VM red.
                    "Storage" => {
                        let padded = trunc(text, width);
                        match storage {
                            Some(azlin_azure::disk_layout::StorageStatus::Ok) => green(&padded),
                            Some(azlin_azure::disk_layout::StorageStatus::Degraded) => red(&padded),
                            _ => padded,
                        }
                    }
                    _ => {
                        let value = metrics.and_then(|m| match *header {
                            "CPU%" => m.cpu_percent,
                            "Mem%" => m.mem_percent,
                            _ => m.disk_percent,
                        });
                        let padded = trunc_right(text, width);
                        match crate::health_render::metric_level(value) {
                            Some(level) => threshold_ansi(level, &padded),
                            None => padded,
                        }
                    }
                };
                cells.push(cell);
                col_i += 1;
            }
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
    let mut summary = if total_tmux > 0 {
        format!(
            "Total: {} VMs | {} running | {} tmux sessions",
            total, running, total_tmux
        )
    } else {
        format!("Total: {} VMs | {} running", total, running)
    };
    // The disclosure (#1142) extends the summary line rather than starting a new
    // one: the footer is the line an operator actually reads, and it is the line
    // that used to say `Total: 2 VMs | 2 running` while four VMs quietly billed
    // for 11.7 TB of disk. The suffix is empty when nothing was filtered, so an
    // unfiltered listing is byte-for-byte unchanged. Both lines are coloured as
    // a whole, never mid-string, so the text stays greppable in captured output.
    summary.push_str(&list_disclosure::summary_suffix(&data.filters));
    println!("{}", bold(&summary));
    if let Some(remedy) = list_disclosure::remedy_line(&data.filters) {
        println!("{}", dim(remedy));
    }
    if !cfg.show_all_vms {
        println!();
        println!("{}", dim("Hints:"));
        // `--all` leads, because it is the flag the disclosure above points at.
        // `-a` used to read "Show all VMs across all resource groups", which is
        // near enough to "show all VMs" to be read as the stopped-VM reveal --
        // a plausible contributor to the original incident. It now says what it
        // is and what it is not.
        let hints = [
            ("azlin list --all", "Include stopped/deallocated VMs"),
            (
                "azlin list -a",
                "Scan all resource groups (not the same as --all)",
            ),
            ("azlin list -w", "Wide mode (show VM Name, SKU columns)"),
            (
                "azlin list -r",
                "Restore all tmux sessions in new terminal window",
            ),
            ("azlin list -q", "Show quota usage (slower)"),
            ("azlin list -v", "Verbose mode (show tunnel/SSH details)"),
        ];
        // Pad against the *plain* flag: `format!("{:<16}", cyan(flag))` would
        // count the ANSI escape bytes and pad every row short. Before `--all`
        // joined the block every flag was 13 characters and the column aligned
        // by accident.
        let width = hints.iter().map(|(f, _)| f.len()).max().unwrap_or(0);
        for (flag, desc) in hints {
            println!(
                "  {}{}  {}",
                cyan(flag),
                " ".repeat(width.saturating_sub(flag.len())),
                dim(desc)
            );
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
                if let Some(m) = data.health_data.get(&vm.name) {
                    obj["health_agent"] = serde_json::json!(m.agent_status);
                    // `Option` serialises to `null`, which is the JSON way
                    // of saying "no reading" — `0` would be a measurement.
                    obj["health_cpu_percent"] = serde_json::json!(m.cpu_percent);
                    obj["health_mem_percent"] = serde_json::json!(m.mem_percent);
                    obj["health_disk_percent"] = serde_json::json!(m.disk_percent);
                } else {
                    obj["health_agent"] = serde_json::json!(null);
                    obj["health_cpu_percent"] = serde_json::json!(null);
                    obj["health_mem_percent"] = serde_json::json!(null);
                    obj["health_disk_percent"] = serde_json::json!(null);
                }
                // `null` for anything that is not a verdict — unprobed,
                // unparseable, or a VM with no data disks. The table renders
                // all three as `--`; emitting `"unknown"` here would give the
                // JSON and CSV consumers a different vocabulary from the one
                // the tests pin, for the same VM.
                obj["storage"] = serde_json::json!(crate::health_render::storage_verdict(
                    data.storage_data.get(&vm.name).copied(),
                ));
            }
            obj
        })
        .collect();
    // BREAKING (#1142): this was a bare top-level array. A bare array has
    // nowhere to put result-level metadata, and the filter counts have to reach
    // machine consumers -- a monitor that reads `azlin list` and sees two VMs
    // is exactly the reader the silent filter misled. `.[]` becomes `.vms[]`.
    //
    // `filters` is always present with all three keys, zeros included. The
    // "say nothing when nothing was hidden" rule governs human output; a key
    // that appears only sometimes would force every consumer to tell `null`
    // from `0`, which is a defect generator.
    //
    // Built as one `Value` and serialised once -- no fragment splicing.
    let payload = serde_json::json!({
        "vms": json_vms,
        "filters": {
            "hidden_not_running": data.filters.hidden_not_running,
            "dropped_by_tag": data.filters.dropped_by_tag,
            "dropped_by_pattern": data.filters.dropped_by_pattern,
        },
    });
    println!("{}", serde_json::to_string_pretty(&payload)?);
    disclose_on_stderr(&data.filters);
    Ok(())
}

// ── CSV renderer ─────────────────────────────────────────────────────

/// Quote a CSV field that could contain a delimiter, per RFC 4180.
///
/// Two of the fields in this row are free-form text the renderer does not
/// control: the session name comes from an Azure tag and the `Tmux` value comes
/// off the listed VM itself. `sanitize_remote_text` strips control characters,
/// but a comma is not a control character — an unquoted session name of `a,b`
/// therefore ends the field early and shifts every later column by one, which a
/// consumer reads as valid data for the wrong VM. That is the same
/// confidently-wrong-row failure the rest of this work removes, arriving through
/// the CSV writer instead of the routing.
fn csv_field(value: &str) -> String {
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

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
        headers.extend_from_slice(crate::health_render::HEALTH_COLUMNS);
    }
    println!("{}", headers.join(","));

    for vm in data.vms {
        // Sanitized for the same reason as the table, plus one specific to this
        // format: `sanitize_remote_text` strips newlines (and `U+2028`/`U+2029`
        // with them), and a newline in a name would otherwise end the record
        // early and let a listed VM inject rows of its own into the CSV a
        // script goes on to parse.
        //
        // Record injection and field injection are both closed: every
        // free-form field is sanitised and then quoted per RFC 4180 by
        // `csv_field`, so a comma in an Azure name can no longer shift the
        // columns after it. Quoting rather than stripping is deliberate --
        // stripping would silently rename a VM in output a script parses.
        // The residual is formula evaluation, not delimiter shifting: a value
        // opening with `=`, `+`, `-` or `@` is still evaluated by a
        // spreadsheet, which quoting does not address.
        let disp = VmDisplayText::for_vm(vm);
        let tmux = data
            .tmux_sessions
            .get(&vm.name)
            .map(|s| s.join(";"))
            .unwrap_or_default();
        let (cpu, mem) = crate::display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
        let mut row = csv_field(&disp.session);
        if cfg.show_tmux_col {
            row.push_str(&format!(",{}", csv_field(&tmux)));
        }
        if cfg.wide {
            row.push_str(&format!(",{}", csv_field(&disp.name)));
        }
        // Every free-form field, not only the three that motivated `csv_field`.
        // The OS offer, the region and the SKU are Azure-supplied strings echoed
        // back as whoever created them typed them, and the argument that closed
        // the session name applies to them unchanged: sanitising strips control
        // characters, and a comma is not one. `power_state` is an enum and the
        // vCPU/memory figures are computed here, so they carry no delimiter to
        // quote.
        row.push_str(&format!(
            ",{},{},{},{}",
            csv_field(&disp.os),
            vm.power_state,
            csv_field(&disp.ip),
            csv_field(&disp.location)
        ));
        if cfg.wide {
            row.push_str(&format!(",{}", csv_field(&disp.vm_size)));
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
            if let Some(m) = data.health_data.get(&vm.name) {
                row.push_str(&format!(
                    ",{},{},{},{}",
                    // Read off the listed host over SSH, so this is the same
                    // untrusted source as a session name -- the strongest case
                    // for quoting on the row, and the one that was missed.
                    csv_field(&crate::cmd_list_data::sanitize_remote_text(&m.agent_status)),
                    crate::health_render::metric_csv(m.cpu_percent),
                    crate::health_render::metric_csv(m.mem_percent),
                    crate::health_render::metric_csv(m.disk_percent)
                ));
            } else {
                // One empty field per metric column, counted from the shared
                // column list so it cannot fall behind it.
                for _ in 0..crate::health_render::HEALTH_COLUMNS.len() - 1 {
                    row.push(',');
                }
            }
            // Empty rather than `unknown`: an empty CSV field is the
            // conventional "no value", and this column must not claim one.
            row.push_str(&format!(
                ",{}",
                crate::health_render::storage_verdict(data.storage_data.get(&vm.name).copied())
                    .unwrap_or("")
            ));
        }
        println!("{}", row);
    }

    disclose_on_stderr(&data.filters);
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── csv_field ─────────────────────────────────────────────────────

    #[test]
    fn csv_field_leaves_ordinary_values_alone() {
        assert_eq!(csv_field("main"), "main");
        assert_eq!(csv_field("build-agent_1"), "build-agent_1");
        assert_eq!(csv_field(""), "");
    }

    #[test]
    fn csv_field_quotes_a_value_containing_the_delimiter() {
        // A tmux session literally named `a,b` used to end the field early and
        // shift every later column by one.
        assert_eq!(csv_field("a,b"), "\"a,b\"");
    }

    #[test]
    fn csv_field_doubles_embedded_quotes() {
        assert_eq!(csv_field("say \"hi\""), "\"say \"\"hi\"\"\"");
    }

    #[test]
    fn csv_field_quotes_embedded_newlines() {
        // sanitize_remote_text strips these before they reach the renderer;
        // the writer does not rely on that being true forever.
        assert_eq!(csv_field("a\nb"), "\"a\nb\"");
        assert_eq!(csv_field("a\rb"), "\"a\rb\"");
    }

    /// Every free-form field on the row, not just the three that motivated the
    /// helper. A comma in any one of them shifts every later column by one, and
    /// a consumer reads that as valid data for the wrong VM.
    ///
    /// `agent_status` matters most: it is read off the listed host over SSH, so
    /// it is the same untrusted source as a session name.
    #[test]
    fn csv_field_covers_every_free_form_field_on_the_row() {
        for value in [
            "Ubuntu 24.04 LTS, minimal", // os offer
            "East US, Zone 1",           // location as Azure may echo it
            "Standard_D4s_v3, promo",    // sku
            "ready, degraded",           // agent status, read off the host
            "10.0.0.4, 10.0.0.5",        // ip display
        ] {
            let quoted = csv_field(value);
            assert!(
                quoted.starts_with('"') && quoted.ends_with('"'),
                "a comma-bearing field was left unquoted: {quoted:?}"
            );
            // One field, so exactly one unquoted delimiter boundary: the comma
            // is now inside the quotes rather than ending the field.
            assert_eq!(
                quoted,
                format!("\"{value}\""),
                "quoting changed the value itself"
            );
        }
    }

    /// Sanitising is not escaping -- the distinction the CSV fix rests on.
    /// `sanitize_remote_text` removes control characters and leaves a comma
    /// untouched, so a value that survives it can still break the row.
    #[test]
    fn sanitizing_does_not_remove_the_delimiter_that_quoting_handles() {
        let hostile = "build,agent";
        assert_eq!(
            crate::cmd_list_data::sanitize_remote_text(hostile),
            hostile,
            "sanitising is expected to leave a comma alone; if it starts \
             stripping them, the CSV writer's reason for quoting changes"
        );
        assert_eq!(csv_field(hostile), "\"build,agent\"");
    }

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
            assert!(
                result.contains(&format!("sess-{}", i)),
                "missing sess-{}",
                i
            );
        }
        assert!(
            !result.contains('+'),
            "should not contain overflow indicator"
        );
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
            ColDef {
                header: "Session",
                width: 11,
                right_align: false,
            },
            ColDef {
                header: "Tmux",
                width: 50,
                right_align: false,
            },
            ColDef {
                header: "OS",
                width: 14,
                right_align: false,
            },
            ColDef {
                header: "Status",
                width: 7,
                right_align: false,
            },
            ColDef {
                header: "IP",
                width: 17,
                right_align: false,
            },
            ColDef {
                header: "Region",
                width: 14,
                right_align: false,
            },
            ColDef {
                header: "CPU",
                width: 3,
                right_align: true,
            },
            ColDef {
                header: "Mem",
                width: 6,
                right_align: true,
            },
        ];
        let term_width: usize = 100;
        let border_overhead = cols.len() * 3 + 1;
        let content_budget = term_width.saturating_sub(border_overhead);
        let total_content: usize = cols.iter().map(|c| c.width).sum();

        assert!(
            total_content > content_budget,
            "test setup: must exceed budget"
        );

        let mut excess = total_content - content_budget;

        // Priority 1: shrink Region, Status, CPU, Mem
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

        // Priority 2: shrink non-protected columns
        let protected = ["Session", "Tmux", "VM Name"];
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

        // After priorities 1 and 2, Tmux should still be 50
        let tmux_col = cols.iter().find(|c| c.header == "Tmux").unwrap();
        assert_eq!(
            tmux_col.width, 50,
            "Tmux column should not be shrunk when other columns can absorb the excess"
        );
    }

    // ── Azure-supplied text is sanitized for display ──────────────────

    /// `ESC [ 2 K` erases the line and `CR` returns to its start, so a name
    /// carrying both makes the row that reports it render as whatever follows.
    const ERASE_LINE_THEN_RETURN: &str = "\x1b[2K\rALL-CLEAR";

    fn vm_with_hostile_names() -> VmInfo {
        let mut tags = std::collections::HashMap::new();
        tags.insert(
            "azlin-session".to_string(),
            format!("prod{}\ninjected", ERASE_LINE_THEN_RETURN),
        );
        VmInfo {
            name: format!("oit-vm{}", ERASE_LINE_THEN_RETURN),
            resource_group: "rg-oit".to_string(),
            location: format!("eastus{}", ERASE_LINE_THEN_RETURN),
            vm_size: format!("Standard_D4s_v3{}", ERASE_LINE_THEN_RETURN),
            power_state: azlin_core::models::PowerState::Running,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: azlin_core::models::OsType::Linux,
            os_offer: Some(format!("ubuntu-24_04{}", ERASE_LINE_THEN_RETURN)),
            public_ip: None,
            private_ip: Some("10.0.0.4".to_string()),
            admin_username: Some("azureuser".to_string()),
            tags,
            created_time: None,
        }
    }

    /// Every Azure-supplied cell, not just the ones a reviewer happened to
    /// think of. If a field is added to `VmDisplayText` without sanitizing it,
    /// this is the test that should fail.
    #[test]
    fn display_text_strips_control_characters_from_every_field() {
        let vm = vm_with_hostile_names();
        let d = VmDisplayText::for_vm(&vm);

        for (field, value) in [
            ("session", &d.session),
            ("name", &d.name),
            ("os", &d.os),
            ("ip", &d.ip),
            ("location", &d.location),
            ("vm_size", &d.vm_size),
        ] {
            assert!(
                !value.chars().any(|c| c.is_control()),
                "{} still carries a control character: {:?}",
                field,
                value
            );
        }
    }

    /// Sanitizing must not blank the cell: an operator still has to be able to
    /// read which VM the row is about. Stripping the escape and keeping the
    /// printable remainder is the whole point.
    #[test]
    fn display_text_keeps_the_printable_remainder() {
        let vm = vm_with_hostile_names();
        let d = VmDisplayText::for_vm(&vm);
        assert!(d.name.starts_with("oit-vm"), "name was {:?}", d.name);
        assert!(d.name.contains("ALL-CLEAR"), "name was {:?}", d.name);
        assert!(d.location.starts_with("eastus"), "loc was {:?}", d.location);
        assert!(d.session.starts_with("prod"), "session {:?}", d.session);
    }

    /// A newline in a name would end a CSV record early and let a listed VM
    /// inject rows of its own into output a script goes on to parse.
    #[test]
    fn display_text_strips_newlines_that_would_forge_a_csv_record() {
        let vm = vm_with_hostile_names();
        let d = VmDisplayText::for_vm(&vm);
        assert!(!d.session.contains('\n'), "session {:?}", d.session);
        assert!(d.session.contains("injected"), "session {:?}", d.session);
    }

    /// A VM with no session tag reads as `-`, not as an empty cell.
    #[test]
    fn display_text_missing_session_tag_renders_dash() {
        let mut vm = vm_with_hostile_names();
        vm.tags.clear();
        assert_eq!(VmDisplayText::for_vm(&vm).session, "-");
    }

    /// The sanitized name is what gets printed, so it is what the column must
    /// be measured against. Measuring the raw name reserves columns for
    /// characters that occupy none, pushing every border right.
    #[test]
    fn display_name_is_shorter_than_the_raw_name_it_came_from() {
        let vm = vm_with_hostile_names();
        let d = VmDisplayText::for_vm(&vm);
        assert!(
            d.name.chars().count() < vm.name.chars().count(),
            "sanitized {:?} should be shorter than raw {:?}",
            d.name,
            vm.name
        );
    }

    /// Ordinary names must survive untouched — sanitizing is not allowed to
    /// mangle the 99.9% case, including non-ASCII names Azure accepts.
    #[test]
    fn display_text_leaves_ordinary_names_alone() {
        let mut vm = vm_with_hostile_names();
        vm.name = "oit-vm-a".to_string();
        vm.location = "eastus".to_string();
        vm.vm_size = "Standard_D4s_v3".to_string();
        vm.tags.insert("azlin-session".into(), "café-prod".into());
        let d = VmDisplayText::for_vm(&vm);
        assert_eq!(d.name, "oit-vm-a");
        assert_eq!(d.location, "eastus");
        assert_eq!(d.vm_size, "Standard_D4s_v3");
        assert_eq!(d.session, "café-prod");
    }
}
