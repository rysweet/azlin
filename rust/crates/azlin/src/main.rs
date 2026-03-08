use anyhow::{Context, Result};
use clap::Parser;

// Re-exported for sub-modules that still use comfy_table via `use super::*`.
#[allow(unused_imports)]
use comfy_table::{presets::UTF8_FULL_CONDENSED, Attribute, Cell, Color, Table};
#[allow(unused_imports)]
use dialoguer::Confirm;

/// Create a styled table with box-drawing borders and truncation.
/// Automatically adapts width to the current terminal size.
fn new_table(headers: &[&str], widths: &[usize]) -> table_render::SimpleTable {
    table_render::SimpleTable::new(headers, widths)
}
use crossterm::{
    event::{self, Event, KeyCode},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    ExecutableCommand,
};
use indicatif::{MultiProgress, ProgressBar, ProgressStyle};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout},
    style::{Color as RatColor, Style as RatStyle},
    widgets::{Block, Borders, Cell as RatCell, Row, Table as RatTable},
    Terminal,
};
use tracing_subscriber::EnvFilter;

/// Estimated monthly cost for an orphaned Azure Standard public IP address.
mod dispatch;
mod dispatch_helpers;
const ORPHANED_PUBLIC_IP_MONTHLY_COST: f64 = 3.65;

/// Default admin username for Azure VMs.
const DEFAULT_ADMIN_USERNAME: &str = "azureuser";

/// Health metrics collected from a VM via SSH.
struct HealthMetrics {
    vm_name: String,
    power_state: String,
    agent_status: String,
    error_count: u32,
    cpu_percent: f32,
    mem_percent: f32,
    disk_percent: f32,
}

/// Run an SSH command on a remote host and return (exit_code, stdout, stderr).
fn ssh_exec(ip: &str, user: &str, cmd: &str) -> Result<(i32, String, String)> {
    let args = ssh_arg_helpers::build_ssh_args(ip, user, cmd);
    let output = std::process::Command::new("ssh").args(&args).output()?;
    Ok((
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    ))
}

/// Run a command on a VM through Azure Bastion and return (exit_code, stdout, stderr).
fn bastion_ssh_exec(
    bastion_name: &str,
    resource_group: &str,
    vm_resource_id: &str,
    user: &str,
    ssh_key: Option<&std::path::Path>,
    cmd: &str,
) -> Result<(i32, String, String)> {
    let key_str = ssh_key.map(|k| k.to_string_lossy().to_string());
    let args = ssh_arg_helpers::build_bastion_ssh_args(
        bastion_name,
        resource_group,
        vm_resource_id,
        user,
        key_str.as_deref(),
        cmd,
    );
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    azlin_azure::run_with_timeout("az", &arg_refs, 60)
}

/// Named bastion routing info, replacing the opaque 4-tuple.
struct BastionRoute {
    bastion_name: String,
    resource_group: String,
    vm_resource_id: String,
    ssh_key_path: Option<std::path::PathBuf>,
}

/// A running `az network bastion tunnel` subprocess bound to a local port.
struct BastionTunnel {
    local_port: u16,
    child: std::process::Child,
}

/// Pool of bastion tunnels keyed by VM name.  Re-uses an existing tunnel when
/// the same VM is queried twice, and tears down all tunnels on drop.
struct BastionTunnelPool {
    tunnels: std::collections::HashMap<String, BastionTunnel>,
    next_port: u16,
}

impl BastionTunnelPool {
    fn new() -> Self {
        Self {
            tunnels: std::collections::HashMap::new(),
            next_port: 50100,
        }
    }

    fn get_or_create(
        &mut self,
        vm_name: &str,
        bastion_name: &str,
        rg: &str,
        vm_rid: &str,
    ) -> Result<u16> {
        if let Some(tunnel) = self.tunnels.get(vm_name) {
            return Ok(tunnel.local_port);
        }
        let port = self.next_port;
        self.next_port += 1;
        let child = std::process::Command::new("az")
            .args([
                "network",
                "bastion",
                "tunnel",
                "--name",
                bastion_name,
                "--resource-group",
                rg,
                "--target-resource-id",
                vm_rid,
                "--resource-port",
                "22",
                "--port",
                &port.to_string(),
            ])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()?;
        // Wait briefly for tunnel to establish
        std::thread::sleep(std::time::Duration::from_secs(2));
        self.tunnels.insert(
            vm_name.to_string(),
            BastionTunnel {
                local_port: port,
                child,
            },
        );
        Ok(port)
    }
}

impl Drop for BastionTunnelPool {
    fn drop(&mut self) {
        for (_, mut tunnel) in self.tunnels.drain() {
            let _ = tunnel.child.kill();
            let _ = tunnel.child.wait();
        }
    }
}

/// Encapsulates SSH connection info for a VM, supporting both direct and bastion routes.
struct VmSshTarget {
    vm_name: String,
    ip: String,
    user: String,
    bastion: Option<BastionRoute>,
}

impl VmSshTarget {
    fn exec(&self, cmd: &str) -> Result<(i32, String, String)> {
        let result = self.exec_inner(cmd)?;

        // Auto-sync SSH key on "Permission denied" — retry once after key push
        if result.0 == 255 && result.2.contains("Permission denied") {
            if let Some(key_path) = resolve_ssh_key() {
                let pub_key_path = key_path.with_extension("pub");
                if pub_key_path.exists() {
                    let pub_key = std::fs::read_to_string(&pub_key_path).unwrap_or_default();
                    if !pub_key.is_empty() {
                        // For bastion targets we have RG + VM name; for direct SSH we have vm_name
                        let (rg, vm_name) = if let Some(ref b) = self.bastion {
                            let name = b.vm_resource_id.rsplit('/').next().unwrap_or(&self.vm_name);
                            (b.resource_group.clone(), name.to_string())
                        } else {
                            // Direct SSH — vm_name is set by the caller
                            // We don't have the RG here, so skip auto-sync for direct targets
                            // (they typically work because the key was deployed at create time)
                            return Ok(result);
                        };

                        eprintln!(
                            "SSH auth failed for {}, syncing key via az vm user update...",
                            vm_name
                        );
                        let status = std::process::Command::new("az")
                            .args([
                                "vm",
                                "user",
                                "update",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                                "--username",
                                &self.user,
                                "--ssh-key-value",
                                pub_key.trim(),
                            ])
                            .stdout(std::process::Stdio::null())
                            .stderr(std::process::Stdio::null())
                            .status();

                        if status.is_ok_and(|s| s.success()) {
                            eprintln!("Key synced, retrying SSH...");
                            return self.exec_inner(cmd);
                        } else {
                            eprintln!(
                                "Warning: az vm user update failed, returning original error"
                            );
                        }
                    }
                }
            }
        }

        Ok(result)
    }

    fn exec_inner(&self, cmd: &str) -> Result<(i32, String, String)> {
        if let Some(ref b) = self.bastion {
            bastion_ssh_exec(
                &b.bastion_name,
                &b.resource_group,
                &b.vm_resource_id,
                &self.user,
                b.ssh_key_path.as_deref(),
                cmd,
            )
        } else {
            ssh_exec(&self.ip, &self.user, cmd)
        }
    }

    fn exec_checked(&self, cmd: &str) -> Result<String> {
        let (code, stdout, stderr) = self.exec(cmd)?;
        if code != 0 {
            anyhow::bail!("SSH command failed (exit {}): {}", code, stderr);
        }
        Ok(stdout)
    }
}

/// Build a `VmSshTarget` from a `VmInfo`, routing through bastion when the VM has no public IP.
///
/// `ssh_key` is resolved once by the caller and passed in to avoid redundant filesystem lookups.
fn build_ssh_target(
    vm: &azlin_core::models::VmInfo,
    subscription_id: &str,
    bastion_map: &std::collections::HashMap<String, String>,
    ssh_key: &Option<std::path::PathBuf>,
) -> VmSshTarget {
    let ip = ssh_arg_helpers::pick_ssh_ip(vm.public_ip.as_deref(), vm.private_ip.as_deref());
    let user = vm
        .admin_username
        .clone()
        .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

    let bastion = if ssh_arg_helpers::needs_bastion(vm.public_ip.as_deref()) {
        bastion_map.get(&vm.location).map(|bastion_name| {
            let vm_rid = ssh_arg_helpers::build_vm_resource_id(
                subscription_id,
                &vm.resource_group,
                &vm.name,
            );
            BastionRoute {
                bastion_name: bastion_name.clone(),
                resource_group: vm.resource_group.clone(),
                vm_resource_id: vm_rid,
                ssh_key_path: ssh_key.clone(),
            }
        })
    } else {
        None
    };

    VmSshTarget {
        vm_name: vm.name.clone(),
        ip,
        user,
        bastion,
    }
}

/// Resolve an SSH key for bastion tunnelling: prefer ~/.ssh/azlin_key, fall back to ~/.ssh/id_rsa.
fn resolve_ssh_key() -> Option<std::path::PathBuf> {
    let h = dirs::home_dir()?;
    let azlin_key = h.join(".ssh").join("azlin_key");
    if azlin_key.exists() {
        return Some(azlin_key);
    }
    let id_rsa = h.join(".ssh").join("id_rsa");
    if id_rsa.exists() {
        return Some(id_rsa);
    }
    None
}

/// Collect health metrics from a single VM via SSH (direct or through Bastion).
fn collect_health_metrics(
    vm_name: &str,
    ip: &str,
    user: &str,
    power_state: &str,
    bastion_info: Option<(&str, &str, &str, Option<&std::path::Path>)>,
) -> HealthMetrics {
    if power_state != "Running" {
        return health_parse_helpers::default_metrics(vm_name, power_state);
    }

    // Helper closure: route through Bastion when bastion_info is provided,
    // otherwise use direct SSH.
    let exec = |cmd: &str| -> Result<(i32, String, String)> {
        if let Some((bastion_name, rg, vm_rid, ssh_key)) = bastion_info {
            bastion_ssh_exec(bastion_name, rg, vm_rid, user, ssh_key, cmd)
        } else {
            ssh_exec(ip, user, cmd)
        }
    };

    // CPU usage from top (extract idle% before "id" regardless of field position)
    let cpu = exec("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_cpu_stdout(code, &out))
        .unwrap_or(0.0);

    // Memory usage from free
    let mem = exec("free | awk '/Mem:/{printf \"%.1f\", $3/$2 * 100}'")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_mem_stdout(code, &out))
        .unwrap_or(0.0);

    // Disk usage from df
    let disk = exec("df / --output=pcent | tail -1 | tr -d ' %'")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_disk_stdout(code, &out))
        .unwrap_or(0.0);

    // Agent status from walinuxagent service
    let agent = exec("systemctl is-active walinuxagent 2>/dev/null || echo \"N/A\"")
        .ok()
        .map(|(_, out, _)| ssh_arg_helpers::classify_agent_status(&out).to_string())
        .unwrap_or_else(|| "N/A".to_string());

    // Error count from journalctl (last hour)
    let errors = exec("journalctl -p err --since '1 hour ago' --no-pager -q 2>/dev/null | wc -l")
        .ok()
        .and_then(|(_, out, _)| out.trim().parse::<u32>().ok())
        .unwrap_or(0);

    HealthMetrics {
        vm_name: vm_name.to_string(),
        power_state: power_state.to_string(),
        agent_status: agent,
        error_count: errors,
        cpu_percent: cpu,
        mem_percent: mem,
        disk_percent: disk,
    }
}

/// Apply ANSI color based on threshold level.
fn threshold_ansi(level: error_helpers::ThresholdLevel, s: &str) -> String {
    match level {
        error_helpers::ThresholdLevel::Normal => format!("\x1b[32m{}\x1b[0m", s),
        error_helpers::ThresholdLevel::Warning => format!("\x1b[33m{}\x1b[0m", s),
        error_helpers::ThresholdLevel::Critical => format!("\x1b[31m{}\x1b[0m", s),
    }
}

/// Render a health metrics table.
fn render_health_table(metrics: &[HealthMetrics]) {
    let mut table = new_table(
        &[
            "VM Name", "State", "Agent", "Errors", "CPU %", "Memory %", "Disk %",
        ],
        &[20, 10, 10, 6, 6, 8, 6],
    );

    for m in metrics {
        // Pass plain text to table for correct width calculation.
        // Colors are applied per-line after rendering.
        table.add_row(vec![
            m.vm_name.clone(),
            m.power_state.clone(),
            m.agent_status.clone(),
            m.error_count.to_string(),
            format!("{:.1}", m.cpu_percent),
            format!("{:.1}", m.mem_percent),
            format!("{:.1}", m.disk_percent),
        ]);
    }

    // Render table as plain text, then colorize each data row
    let rendered = format!("{table}");
    for (line_idx, line) in rendered.lines().enumerate() {
        if line_idx < 3 || metrics.is_empty() {
            // Header rows (top border, header, separator) — print as-is
            println!("{line}");
        } else {
            let data_idx = line_idx - 3;
            if data_idx < metrics.len() {
                // Color individual cell values in the rendered line
                let m = &metrics[data_idx];
                let mut colored = line.to_string();
                // Replace plain values with colored versions (rightmost first to preserve positions)
                let replacements = [
                    (
                        &format!("{:.1}", m.disk_percent),
                        error_helpers::classify_metric_70_90(m.disk_percent),
                    ),
                    (
                        &format!("{:.1}", m.mem_percent),
                        error_helpers::classify_metric_70_90(m.mem_percent),
                    ),
                    (
                        &format!("{:.1}", m.cpu_percent),
                        error_helpers::classify_metric_70_90(m.cpu_percent),
                    ),
                    (
                        &m.error_count.to_string(),
                        error_helpers::classify_error_count(m.error_count),
                    ),
                    (
                        &m.agent_status,
                        error_helpers::classify_agent_level(&m.agent_status),
                    ),
                    (
                        &m.power_state,
                        error_helpers::classify_power_state(&m.power_state),
                    ),
                ];
                for (val, level) in &replacements {
                    if !val.is_empty() {
                        let ansi = threshold_ansi(*level, val);
                        // Replace last occurrence to avoid matching substrings in VM name
                        if let Some(pos) = colored.rfind(val.as_str()) {
                            colored = format!(
                                "{}{}{}",
                                &colored[..pos],
                                ansi,
                                &colored[pos + val.len()..]
                            );
                        }
                    }
                }
                println!("{colored}");
            } else {
                println!("{line}");
            }
        }
    }
    println!();
    println!(
        "Signals: Latency=Agent | Traffic=State | Errors=Agent fails | Saturation=CPU/Mem/Disk"
    );
    println!("Thresholds: <70% 70-90% >90%");
}

/// Run an interactive TUI dashboard showing health metrics.
fn run_health_tui(metrics: &[HealthMetrics]) -> Result<()> {
    enable_raw_mode()?;
    std::io::stdout().execute(EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(std::io::stdout());
    let mut terminal = Terminal::new(backend)?;

    let result = (|| -> Result<()> {
        loop {
            terminal.draw(|f| {
                let chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([
                        Constraint::Length(3),
                        Constraint::Min(10),
                        Constraint::Length(3),
                    ])
                    .split(f.area());

                // Header
                let header = Block::default()
                    .title(" azlin health dashboard ")
                    .borders(Borders::ALL)
                    .border_style(RatStyle::default().fg(RatColor::Cyan));
                f.render_widget(header, chunks[0]);

                // Table
                let header_row = Row::new(vec![
                    RatCell::from("VM Name").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("State").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Agent").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Errors").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("CPU %").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Memory %").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Disk %").style(RatStyle::default().fg(RatColor::Yellow)),
                ]);

                let rows: Vec<Row> = metrics
                    .iter()
                    .map(|m| {
                        let state_color = match m.power_state.as_str() {
                            "running" => RatColor::Green,
                            "stopped" | "deallocated" => RatColor::Red,
                            _ => RatColor::Yellow,
                        };
                        let cpu_color = if m.cpu_percent > 80.0 {
                            RatColor::Red
                        } else if m.cpu_percent > 50.0 {
                            RatColor::Yellow
                        } else {
                            RatColor::Green
                        };
                        let mem_color = if m.mem_percent > 80.0 {
                            RatColor::Red
                        } else if m.mem_percent > 50.0 {
                            RatColor::Yellow
                        } else {
                            RatColor::Green
                        };
                        let disk_color = if m.disk_percent > 80.0 {
                            RatColor::Red
                        } else if m.disk_percent > 50.0 {
                            RatColor::Yellow
                        } else {
                            RatColor::Green
                        };
                        let agent_color = match m.agent_status.as_str() {
                            "OK" => RatColor::Green,
                            "Down" => RatColor::Red,
                            _ => RatColor::Yellow,
                        };
                        let error_color = if m.error_count > 10 {
                            RatColor::Red
                        } else if m.error_count > 0 {
                            RatColor::Yellow
                        } else {
                            RatColor::Green
                        };
                        Row::new(vec![
                            RatCell::from(m.vm_name.as_str()),
                            RatCell::from(m.power_state.as_str())
                                .style(RatStyle::default().fg(state_color)),
                            RatCell::from(m.agent_status.as_str())
                                .style(RatStyle::default().fg(agent_color)),
                            RatCell::from(format!("{}", m.error_count))
                                .style(RatStyle::default().fg(error_color)),
                            RatCell::from(format!("{:.1}", m.cpu_percent))
                                .style(RatStyle::default().fg(cpu_color)),
                            RatCell::from(format!("{:.1}", m.mem_percent))
                                .style(RatStyle::default().fg(mem_color)),
                            RatCell::from(format!("{:.1}", m.disk_percent))
                                .style(RatStyle::default().fg(disk_color)),
                        ])
                    })
                    .collect();

                let table = RatTable::new(
                    rows,
                    [
                        Constraint::Percentage(22),
                        Constraint::Percentage(13),
                        Constraint::Percentage(10),
                        Constraint::Percentage(10),
                        Constraint::Percentage(15),
                        Constraint::Percentage(15),
                        Constraint::Percentage(15),
                    ],
                )
                .header(header_row)
                .block(
                    Block::default()
                        .title(" Health — Four Golden Signals ")
                        .borders(Borders::ALL),
                );
                f.render_widget(table, chunks[1]);

                // Footer
                let footer = Block::default()
                    .title(" q: quit | r: refresh ")
                    .borders(Borders::ALL)
                    .border_style(RatStyle::default().fg(RatColor::DarkGray));
                f.render_widget(footer, chunks[2]);
            })?;

            if event::poll(std::time::Duration::from_secs(10))? {
                if let Event::Key(key) = event::read()? {
                    match key.code {
                        KeyCode::Char('q') => break,
                        KeyCode::Char('r') => continue,
                        _ => {}
                    }
                }
            }
        }
        Ok(())
    })();

    disable_raw_mode()?;
    std::io::stdout().execute(LeaveAlternateScreen)?;
    result
}

/// Get running VMs with their IPs from Azure for SSH-based commands.
/// Returns Vec of (vm_name, ip, admin_user).
async fn get_running_vms_with_ips(
    vm_manager: &azlin_azure::VmManager,
    rg: &str,
) -> Result<Vec<(String, String, String)>> {
    let vms = vm_manager.list_vms(rg)?;
    let mut results = Vec::new();
    for vm in &vms {
        if vm.power_state == azlin_core::models::PowerState::Running {
            if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                let user = vm
                    .admin_username
                    .clone()
                    .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                results.push((vm.name.clone(), ip.clone(), user));
            }
        }
    }
    Ok(results)
}

/// Create a consistent spinner style used across all operations.
fn fleet_spinner_style() -> ProgressStyle {
    ProgressStyle::default_spinner()
        .template("{prefix:.bold} {spinner} {msg}")
        .expect("valid spinner template")
}

/// Execute a command on all running VMs with MultiProgress bars, then print a
/// summary table. Each VM gets its own spinner showing live status.
fn run_on_fleet(vms: &[(String, String, String)], command: &str, show_output: bool) {
    let mp = MultiProgress::new();
    let style = fleet_spinner_style();

    let bars: Vec<_> = vms
        .iter()
        .map(|(name, _ip, _user)| {
            let pb = mp.add(ProgressBar::new_spinner());
            pb.set_style(style.clone());
            pb.set_prefix(format!("{:>20}", name));
            pb.set_message("connecting...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            pb
        })
        .collect();

    let mut table = new_table(&["VM", "Status", "Output"], &[20, 8, 60]);

    for (i, (name, ip, user)) in vms.iter().enumerate() {
        bars[i].set_message(format!("running: {}", command));
        let (code, stdout, stderr) = match ssh_exec(ip, user, command) {
            Ok(r) => r,
            Err(e) => (-1, String::new(), e.to_string()),
        };

        bars[i].finish_with_message(fleet_helpers::finish_message(code, &stdout, &stderr));

        let (status, ok) = fleet_helpers::classify_result(code);
        let status_str = if ok {
            format!("\x1b[32m{}\x1b[0m", status)
        } else {
            format!("\x1b[31m{}\x1b[0m", status)
        };
        let output_text = fleet_helpers::format_output_text(code, &stdout, &stderr, show_output);
        table.add_row(vec![name.to_string(), status_str, output_text]);
    }
    println!("{table}");
}

fn main() {
    color_eyre::install().ok();

    let result = tokio::runtime::Runtime::new()
        .expect("Failed to create tokio runtime")
        .block_on(async_main());

    if let Err(e) = result {
        let msg = format!("{e:?}");
        // Use {e:#} to show the full error chain (not just the outermost context)
        eprintln!("Error: {e:#}");

        let suggestions = error_helpers::error_suggestions(&msg);
        for (i, s) in suggestions.iter().enumerate() {
            if i == 0 {
                eprintln!("\n\u{1f4a1} Suggestion: {s}");
            } else {
                eprintln!("   {s}");
            }
        }

        std::process::exit(1);
    }
}

async fn async_main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let cli = azlin_cli::Cli::parse();
    dispatch::dispatch_command(cli).await
}

// Re-export common utilities from dispatch_helpers for cmd_* modules via `use super::*`.
pub(crate) use dispatch_helpers::{
    create_auth, home_dir, resolve_resource_group, resolve_vm_ssh_target, resolve_vm_targets,
    safe_confirm, shell_escape,
};

mod handlers;

/// Wrapper for backward compatibility with tests that pass OutputFormat enum.
#[cfg(test)]
fn format_cost_summary(
    summary: &azlin_core::models::CostSummary,
    output: &azlin_cli::OutputFormat,
    from: &Option<String>,
    to: &Option<String>,
    estimate: bool,
    by_vm: bool,
) -> String {
    let fmt_str = match output {
        azlin_cli::OutputFormat::Json => "json",
        azlin_cli::OutputFormat::Csv => "csv",
        azlin_cli::OutputFormat::Table => "table",
    };
    handlers::format_cost_summary(summary, fmt_str, from, to, estimate, by_vm)
}

/// Wrapper for backward compatibility with tests.
#[cfg(test)]
fn parse_cost_history_rows(data: &serde_json::Value) -> Vec<(String, String)> {
    handlers::parse_cost_history_rows(data)
}

/// Wrapper for backward compatibility with tests.
#[cfg(test)]
fn parse_recommendation_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    handlers::parse_recommendation_rows(data)
}

/// Wrapper for backward compatibility with tests.
#[cfg(test)]
fn parse_cost_action_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    handlers::parse_cost_action_rows(data)
}

/// Validate names used to construct filesystem paths (profiles, templates).
mod name_validation;

/// Template TOML helpers for reading, writing, and listing templates.
mod templates;

/// Session TOML helpers for reading, writing, and listing sessions.
mod sessions;

/// Context TOML helpers for reading, writing, and listing contexts.
mod contexts;

/// Helpers for `azlin env` subcommands — pure functions that build SSH commands
/// and parse environment variable output. No network I/O.
#[allow(dead_code)]
mod env_helpers;

/// Helpers for the `azlin sync` dotfile-sync subcommand.
#[allow(dead_code)]
mod sync_helpers;

/// Helpers for health-metric display — pure functions over numeric data.
mod health_helpers;

/// Helpers for the `azlin snapshot` subcommands.
#[allow(dead_code)]
mod snapshot_helpers;

/// Generic output-format helpers (JSON / CSV / plain table).
#[allow(dead_code)]
mod output_helpers;

/// VM name validation — enforces Azure naming constraints.
#[allow(dead_code)]
mod vm_validation;

/// Mount path validation — prevents command injection in mount operations.
#[allow(dead_code)]
mod mount_helpers;

/// Config path validation — prevents traversal attacks on config file loading.
#[allow(dead_code)]
mod config_path_helpers;

/// Helpers for storage account operations — SKU resolution and row extraction.
#[allow(dead_code)]
mod storage_helpers;

/// Helpers for SSH key file classification and type detection.
#[allow(dead_code)]
mod key_helpers;

/// Helpers for auth profile display — masking secrets.
#[allow(dead_code)]
mod auth_helpers;

/// Helpers for `azlin cp` — remote path detection and SCP path rewriting.
#[allow(dead_code)]
mod cp_helpers;

/// Helpers for Bastion host JSON extraction.
#[allow(dead_code)]
mod bastion_helpers;

/// Helpers for log tail computation.
#[allow(dead_code)]
mod log_helpers;

/// Helpers for auth test result extraction.
#[allow(dead_code)]
mod auth_test_helpers;

/// Pure helpers for parsing SSH stdout into health metric values.
/// These extract the logic that was previously inline in `collect_health_metrics`,
/// making it testable without SSH.
mod health_parse_helpers;

/// Pure helpers for the `run_on_fleet` result classification and formatting.
mod fleet_helpers;

/// Pure helpers for filtering VMs in the list handler.
mod list_helpers;

/// Pure helpers for validating repository URLs against shell injection.
#[allow(dead_code)]
mod repo_helpers;

/// Pure helpers for VM creation: name generation, template resolution, clone naming.
#[allow(dead_code)]
mod create_helpers;

/// Pure helpers for the connect handler: SSH arg building, VS Code URI construction.
mod connect_helpers;

/// Pure helpers for update/os-update commands: script generation.
mod update_helpers;

/// Pure helpers for compose commands: command building, file resolution.
mod compose_helpers;

/// Pure helpers for GitHub runner fleet management.
#[allow(dead_code)]
mod runner_helpers;

/// Pure helpers for autopilot config building.
#[allow(dead_code)]
mod autopilot_helpers;

/// Pure helpers for VM lifecycle action labelling.
mod stop_helpers;

/// Pure helpers for display-formatting inline values.
mod display_helpers;

/// Pure helpers for tag parsing and validation.
mod tag_helpers;

/// Pure helpers for disk naming conventions.
#[allow(dead_code)]
mod disk_helpers;

/// Pure helpers for AI-generated command validation.
#[allow(dead_code)]
mod command_helpers;

/// Pure helpers for autopilot idle-detection parsing.
#[allow(dead_code)]
mod autopilot_parse_helpers;

/// Pure helpers for batch handler result parsing and aggregation.
mod batch_helpers;

/// Pure helpers for SSH argument building and target classification.
mod ssh_arg_helpers;

/// Pure helpers for error suggestion generation and metric threshold classification.
mod error_helpers;

// Command dispatch modules
mod cmd_ai;
mod cmd_ai_ops;
mod cmd_ai_ops2;
mod cmd_auth;
mod cmd_autopilot;
mod cmd_batch;
mod cmd_cleanup;
mod cmd_cleanup_costs;
mod cmd_cleanup_costs2;
mod cmd_cleanup_ops;
mod cmd_connect;
mod cmd_context;
mod cmd_env;
mod cmd_infra;
mod cmd_infra_ops;
mod cmd_infra_ops2;
mod cmd_keys;
mod cmd_lifecycle;
mod cmd_list;
mod cmd_list_data;
mod cmd_list_render;
mod cmd_monitoring;
mod cmd_network;
mod cmd_network_ops;
mod cmd_network_ops2;
mod cmd_self_update;
mod cmd_session;
mod cmd_snapshot;
mod cmd_snapshot_ops;
mod cmd_snapshot_ops2;
mod cmd_storage;
mod cmd_storage_ops;
mod cmd_storage_ops2;
mod cmd_sync;
mod cmd_sync_ops;
mod cmd_tag;
mod cmd_vm;
mod cmd_vm_ops;
mod cmd_vm_ops2;
mod lifecycle_helpers;
mod table_render;

#[cfg(test)]
#[allow(deprecated)]
mod tests;
