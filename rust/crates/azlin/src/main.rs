use anyhow::{Context, Result};
use clap::Parser;
use std::io::IsTerminal;

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
///
/// Single source of truth shared by `cleanup` and the teardown planner, so the
/// two paths can never quote different savings for the same resource.
use azlin_azure::teardown::ORPHANED_PUBLIC_IP_MONTHLY_COST;

mod auth_forward;
mod dispatch;
mod dispatch_helpers;
mod release_select;
mod update_check;

/// Default admin username for Azure VMs.
const DEFAULT_ADMIN_USERNAME: &str = "azureuser";

/// Health metrics collected from a VM via SSH.
#[derive(Debug)]
/// One VM's health reading.
///
/// The percentages are `Option` because a reading can fail, and a failed
/// reading is not zero. Substituting `0.0` made an unreachable VM render as a
/// healthy idle one — green cells, no warning, exit 0 — which is the whole
/// bug this type now prevents at the type level.
#[derive(Clone)]
struct HealthMetrics {
    vm_name: String,
    power_state: String,
    agent_status: String,
    error_count: Option<u32>,
    cpu_percent: Option<f32>,
    mem_percent: Option<f32>,
    disk_percent: Option<f32>,
}

/// Run an SSH command on a remote host and return (exit_code, stdout, stderr).
fn ssh_exec(
    ip: &str,
    user: &str,
    cmd: &str,
    key_override: Option<&std::path::Path>,
    allow_preferred_key_fallback: bool,
) -> Result<(i32, String, String)> {
    let config = crate::dispatch_helpers::load_user_config();
    let mut args = ssh_arg_helpers::build_ssh_args(ip, user, cmd, config.ssh_connect_timeout);
    if let Some(k) = resolve_target_ssh_key_path(key_override, None, allow_preferred_key_fallback) {
        ssh_arg_helpers::inject_identity_key(&mut args, &k);
    }
    let output = std::process::Command::new("ssh").args(&args).output()?;
    Ok((
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    ))
}

/// Try native SSH via russh connection pool. Uses `block_in_place` to bridge
/// async russh into the synchronous `exec_inner` call path without deadlocking.
fn try_native_ssh(ip: &str, user: &str, cmd: &str) -> Result<(i32, String, String)> {
    let handle = tokio::runtime::Handle::try_current()
        .map_err(|_| anyhow::anyhow!("no tokio runtime for native SSH"))?;
    tokio::task::block_in_place(|| handle.block_on(native_ssh::native_exec(ip, user, cmd)))
}

/// Local wall-clock cap on a single bastion exec, in seconds.
///
/// The bastion path shells out to `az network bastion ssh`, which needs a
/// bound or a hung session wedges the caller forever. Commands that declare
/// their own budget (`fleet run --timeout`) pass a larger cap instead, or the
/// flag would promise more time than the transport allows and the command
/// would die at 60s reporting a transport failure.
const BASTION_EXEC_TIMEOUT_SECS: u64 = 60;

/// Run a command on a VM through Azure Bastion and return (exit_code, stdout, stderr).
fn bastion_ssh_exec(
    bastion_name: &str,
    resource_group: &str,
    vm_resource_id: &str,
    user: &str,
    ssh_key: Option<&std::path::Path>,
    cmd: &str,
    local_timeout_secs: u64,
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
    azlin_azure::run_with_timeout("az", &arg_refs, local_timeout_secs)
}

/// Named bastion routing info, replacing the opaque 4-tuple.
#[derive(Clone)]
struct BastionRoute {
    bastion_name: String,
    resource_group: String,
    vm_resource_id: String,
    ssh_key_path: Option<std::path::PathBuf>,
}

/// Ask the OS for a free local TCP port by binding to `127.0.0.1:0`.
///
/// The listener is dropped immediately after reading the assigned port number.
/// There is a brief TOCTOU window between the drop and when the caller's
/// process binds the port, but on loopback this is negligible in practice.
fn pick_unused_local_port() -> Result<u16> {
    let listener = std::net::TcpListener::bind(("127.0.0.1", 0))
        .context("Failed to allocate a local port for bastion tunnel")?;
    let port = listener
        .local_addr()
        .context("Failed to inspect allocated bastion tunnel port")?
        .port();
    Ok(port)
}

/// Poll until a TCP listener appears on `127.0.0.1:<port>` or `timeout` elapses.
///
/// Also watches `pid` with `kill -0`: if the process exits before the port
/// becomes ready the function bails immediately rather than waiting for the
/// full timeout.  Returns `Ok(())` once a connection succeeds, or `Err` on
/// timeout or early process death.
#[cfg(test)]
fn wait_for_local_port_listener(port: u16, pid: u32, timeout: std::time::Duration) -> Result<()> {
    let deadline = std::time::Instant::now() + timeout;
    while std::time::Instant::now() < deadline {
        if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(());
        }
        let process_gone = std::process::Command::new("kill")
            .args(["-0", &pid.to_string()])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| !s.success())
            .unwrap_or(true);
        if process_gone {
            anyhow::bail!(
                "Bastion tunnel process {} exited before listening on 127.0.0.1:{}",
                pid,
                port
            );
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }

    anyhow::bail!(
        "Timed out waiting for bastion tunnel process {} to listen on 127.0.0.1:{}",
        pid,
        port
    );
}

/// Encapsulates SSH connection info for a VM, supporting both direct and bastion routes.
///
/// `Clone` so `fleet run --retry-failed` can build a second target list from
/// the subset that failed without re-resolving them against Azure.
#[derive(Clone)]
struct VmSshTarget {
    vm_name: String,
    ip: String,
    user: String,
    ssh_key_path: Option<std::path::PathBuf>,
    allow_preferred_key_fallback: bool,
    bastion: Option<BastionRoute>,
}

impl VmSshTarget {
    fn exec(&self, cmd: &str) -> Result<(i32, String, String)> {
        self.exec_with_local_timeout(cmd, BASTION_EXEC_TIMEOUT_SECS)
    }

    /// [`Self::exec`] with an explicit cap on how long the bastion transport
    /// may take, so a command with its own `--timeout` is not cut short at the
    /// default 60 seconds and reported as a transport error.
    fn exec_with_local_timeout(
        &self,
        cmd: &str,
        local_timeout_secs: u64,
    ) -> Result<(i32, String, String)> {
        let result = self.exec_inner(cmd, local_timeout_secs)?;

        // Auto-sync SSH key on "Permission denied" — retry once after key push
        if result.0 == 255 && result.2.contains("Permission denied") {
            if let Some(key_path) = resolve_target_ssh_key_path(
                None,
                self.ssh_key_path.as_deref(),
                self.allow_preferred_key_fallback,
            ) {
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
                            return self.exec_inner(cmd, local_timeout_secs);
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

    fn exec_inner(&self, cmd: &str, local_timeout_secs: u64) -> Result<(i32, String, String)> {
        if let Some(ref b) = self.bastion {
            bastion_ssh_exec(
                &b.bastion_name,
                &b.resource_group,
                &b.vm_resource_id,
                &self.user,
                b.ssh_key_path.as_deref(),
                cmd,
                local_timeout_secs,
            )
        } else {
            if self.ssh_key_path.is_none() && self.allow_preferred_key_fallback {
                // Try native russh first for direct SSH (lower latency, connection reuse).
                // Fall back to subprocess SSH on any failure.
                match try_native_ssh(&self.ip, &self.user, cmd) {
                    Ok(result) => return Ok(result),
                    Err(e) => {
                        tracing::debug!(
                            "native SSH to {} failed ({}), falling back to subprocess",
                            self.ip,
                            e
                        );
                    }
                }
            }
            ssh_exec(
                &self.ip,
                &self.user,
                cmd,
                self.ssh_key_path.as_deref(),
                self.allow_preferred_key_fallback,
            )
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
        ssh_key_path: ssh_key.clone(),
        allow_preferred_key_fallback: true,
        bastion,
    }
}

/// Resolve an SSH key for direct and bastion SSH: prefer azlin_key, then
/// id_ed25519_azlin, id_ed25519, then id_rsa.
fn resolve_ssh_key() -> Option<std::path::PathBuf> {
    let ssh_dir = dirs::home_dir()?.join(".ssh");
    crate::key_helpers::find_preferred_private_key(&ssh_dir)
}

pub(crate) fn resolve_target_ssh_key_path(
    key_override: Option<&std::path::Path>,
    target_ssh_key: Option<&std::path::Path>,
    allow_preferred_key_fallback: bool,
) -> Option<std::path::PathBuf> {
    key_override
        .map(std::path::Path::to_path_buf)
        .or_else(|| target_ssh_key.map(std::path::Path::to_path_buf))
        .or_else(|| {
            if allow_preferred_key_fallback {
                resolve_ssh_key()
            } else {
                None
            }
        })
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
            bastion_ssh_exec(
                bastion_name,
                rg,
                vm_rid,
                user,
                ssh_key,
                cmd,
                BASTION_EXEC_TIMEOUT_SECS,
            )
        } else {
            ssh_exec(ip, user, cmd, None, true)
        }
    };

    // CPU usage from top (extract idle% before "id" regardless of field position)
    // Each metric stays `None` when the command failed or the output did not
    // parse. `unwrap_or(0.0)` here is what made an unreachable VM look idle.
    let cpu = exec("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_cpu_stdout(code, &out));

    // Memory usage from free
    let mem = exec("free | awk '/Mem:/{printf \"%.1f\", $3/$2 * 100}'")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_mem_stdout(code, &out));

    // Disk usage from df
    let disk = exec("df / --output=pcent | tail -1 | tr -d ' %'")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_disk_stdout(code, &out));

    // Agent status from walinuxagent service
    let agent = exec("systemctl is-active walinuxagent 2>/dev/null || echo \"N/A\"")
        .ok()
        .map(|(_, out, _)| ssh_arg_helpers::classify_agent_status(&out).to_string())
        .unwrap_or_else(|| "N/A".to_string());

    // Error count from journalctl (last hour)
    let errors = exec("journalctl -p err --since '1 hour ago' --no-pager -q 2>/dev/null | wc -l")
        .ok()
        .and_then(|(_, out, _)| out.trim().parse::<u32>().ok());

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

/// Apply ANSI colour for a level that may be absent.
///
/// No level means no reading, and an unread metric must not be painted green:
/// green is the claim that the machine is fine, which is exactly what could
/// not be checked.
fn optional_threshold_ansi(level: Option<error_helpers::ThresholdLevel>, s: &str) -> String {
    match level {
        Some(l) => threshold_ansi(l, s),
        None => s.to_string(),
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

/// Render a health metrics table with per-cell coloring.
/// Colors are applied AFTER truncation to avoid ANSI width corruption.
fn render_health_table(metrics: &[HealthMetrics]) {
    use crate::table_render::{trunc, trunc_right};

    let headers = [
        "VM Name", "State", "Agent", "Errors", "CPU %", "Memory %", "Disk %",
    ];
    let widths = [20usize, 10, 10, 6, 6, 8, 6];

    // Build border lines
    let top = table_render::border_line(&widths, '┌', '┬', '┐', '─');
    let sep = table_render::border_line(&widths, '├', '┼', '┤', '─');
    let bot = table_render::border_line(&widths, '└', '┴', '┘', '─');

    // Header row — bold
    let hdr_cells: Vec<String> = headers
        .iter()
        .zip(widths.iter())
        .map(|(h, w)| format!("\x1b[1m{}\x1b[0m", trunc(h, *w)))
        .collect();

    println!("{top}");
    println!("{}", table_render::render_row(&hdr_cells, &widths));
    println!("{sep}");

    // Data rows — color applied per-cell after truncation
    for m in metrics {
        let cells = vec![
            trunc(&m.vm_name, widths[0]),
            threshold_ansi(
                error_helpers::classify_power_state(&m.power_state),
                &trunc(&m.power_state, widths[1]),
            ),
            threshold_ansi(
                error_helpers::classify_agent_level(&m.agent_status),
                &trunc(&m.agent_status, widths[2]),
            ),
            optional_threshold_ansi(
                health_render::error_count_level(m.error_count),
                &trunc_right(&health_render::error_count_cell(m.error_count), widths[3]),
            ),
            optional_threshold_ansi(
                health_render::metric_level(m.cpu_percent),
                &trunc_right(&health_render::metric_cell(m.cpu_percent), widths[4]),
            ),
            optional_threshold_ansi(
                health_render::metric_level(m.mem_percent),
                &trunc_right(&health_render::metric_cell(m.mem_percent), widths[5]),
            ),
            optional_threshold_ansi(
                health_render::metric_level(m.disk_percent),
                &trunc_right(&health_render::metric_cell(m.disk_percent), widths[6]),
            ),
        ];
        println!("{}", table_render::render_row(&cells, &widths));
    }
    println!("{bot}");
    println!();
    // Name the VMs that produced no reading. A `--` in a table is easy to skim
    // past; a summary line is not, and the point of this change is that a
    // failed measurement is visible rather than green.
    let unmeasured: Vec<String> = metrics
        .iter()
        .filter(|m| {
            health_render::has_missing_metric(m.cpu_percent, m.mem_percent, m.disk_percent)
                && m.power_state.eq_ignore_ascii_case("running")
        })
        .map(|m| m.vm_name.clone())
        .collect();
    if let Some(footer) = health_render::unavailable_footer(&unmeasured) {
        eprintln!("{footer}");
        println!();
    }
    println!(
        "Signals: Latency=Agent | Traffic=State | Errors=Agent fails | Saturation=CPU/Mem/Disk"
    );
    println!("Thresholds: <70% 70-90% >90%");
}

/// Run a simple static TUI showing health metrics (legacy fallback).
#[allow(dead_code)]
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
                        // A metric with no reading is grey, never green:
                        // green claims the VM is fine, which is exactly what
                        // could not be checked.
                        let metric_color = |v: Option<f32>| match v {
                            None => RatColor::DarkGray,
                            Some(p) if p > 80.0 => RatColor::Red,
                            Some(p) if p > 50.0 => RatColor::Yellow,
                            Some(_) => RatColor::Green,
                        };
                        let agent_color = match m.agent_status.as_str() {
                            "OK" => RatColor::Green,
                            "Down" => RatColor::Red,
                            _ => RatColor::Yellow,
                        };
                        let error_color = match m.error_count {
                            None => RatColor::DarkGray,
                            Some(c) if c > 10 => RatColor::Red,
                            Some(c) if c > 0 => RatColor::Yellow,
                            Some(_) => RatColor::Green,
                        };
                        Row::new(vec![
                            RatCell::from(m.vm_name.as_str()),
                            RatCell::from(m.power_state.as_str())
                                .style(RatStyle::default().fg(state_color)),
                            RatCell::from(m.agent_status.as_str())
                                .style(RatStyle::default().fg(agent_color)),
                            RatCell::from(health_render::error_count_cell(m.error_count))
                                .style(RatStyle::default().fg(error_color)),
                            RatCell::from(health_render::metric_cell(m.cpu_percent))
                                .style(RatStyle::default().fg(metric_color(m.cpu_percent))),
                            RatCell::from(health_render::metric_cell(m.mem_percent))
                                .style(RatStyle::default().fg(metric_color(m.mem_percent))),
                            RatCell::from(health_render::metric_cell(m.disk_percent))
                                .style(RatStyle::default().fg(metric_color(m.disk_percent))),
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
async fn get_running_vm_targets(resource_group: Option<String>) -> Result<Vec<VmSshTarget>> {
    resolve_vm_targets(None, None, resource_group).await
}

/// Penguin tick frames — the penguin waddles back and forth across dots.
const PENGUIN_TICKS: &[&str] = &[
    "🐧·····",
    "·🐧····",
    "··🐧···",
    "···🐧··",
    "····🐧·",
    "·····🐧",
    "····🐧·",
    "···🐧··",
    "··🐧···",
    "·🐧····",
];

/// Create a penguin-themed spinner for slow operations.
pub(crate) fn penguin_spinner(msg: &str) -> indicatif::ProgressBar {
    let pb = indicatif::ProgressBar::new_spinner();
    pb.set_style(
        indicatif::ProgressStyle::default_spinner()
            .tick_strings(PENGUIN_TICKS)
            .template("{spinner} {msg}")
            .expect("valid spinner template"),
    );
    pb.set_message(msg.to_string());
    pb.enable_steady_tick(std::time::Duration::from_millis(120));
    pb
}

/// Create a consistent spinner style used across fleet operations.
fn fleet_spinner_style() -> ProgressStyle {
    ProgressStyle::default_spinner()
        .tick_strings(PENGUIN_TICKS)
        .template("{prefix:.bold} {spinner} {msg}")
        .expect("valid spinner template")
}

/// One spinner per target, sharing a `MultiProgress` so they render as a block.
fn fleet_progress_bars(targets: &[VmSshTarget]) -> Vec<ProgressBar> {
    let mp = MultiProgress::new();
    let style = fleet_spinner_style();
    targets
        .iter()
        .map(|t| {
            let pb = mp.add(ProgressBar::new_spinner());
            pb.set_style(style.clone());
            pb.set_prefix(format!("{:>20}", t.vm_name));
            pb.set_message("connecting...");
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            pb
        })
        .collect()
}

/// Run `command` on every target, at most `workers` at a time, and return the
/// `(exit_code, stdout, stderr)` triples **in target order**.
///
/// Ordering is deliberate: `--parallel` changes how long a fleet run takes,
/// never what it reports, so the summary table and the `--show-diff` grouping
/// are reproducible whatever order the hosts happen to answer in.
///
/// `workers <= 1` keeps the original in-line loop rather than spawning a single
/// thread. That is not only an optimisation: the native-SSH fast path in
/// `VmSshTarget::exec_inner` needs the ambient tokio runtime, which a plain
/// `std::thread` does not carry, and would silently fall back to subprocess ssh
/// for everyone who never asked for parallelism.
///
/// `display_command` is what the progress spinners show. It differs from
/// `command` whenever the caller has wrapped the user's command — otherwise
/// `--timeout` would splash `timeout 300 bash -c '...'` across the UI.
fn exec_fleet(
    targets: &[VmSshTarget],
    command: &str,
    workers: usize,
    bars: &[ProgressBar],
    local_timeout_secs: u64,
    display_command: &str,
) -> Vec<(i32, String, String)> {
    let run_one = |i: usize| -> (i32, String, String) {
        // The spinner shows what the user typed, not the `timeout N bash -c
        // '...'` wrapper `--timeout` adds around it.
        bars[i].set_message(format!("running: {}", display_command));
        let result = match targets[i].exec_with_local_timeout(command, local_timeout_secs) {
            Ok(r) => r,
            Err(e) => (-1, String::new(), e.to_string()),
        };
        bars[i].finish_with_message(fleet_helpers::finish_message(
            result.0, &result.1, &result.2,
        ));
        result
    };

    if workers <= 1 || targets.len() <= 1 {
        return (0..targets.len()).map(run_one).collect();
    }

    let slots: Vec<std::sync::Mutex<Option<(i32, String, String)>>> = (0..targets.len())
        .map(|_| std::sync::Mutex::new(None))
        .collect();
    let next = std::sync::atomic::AtomicUsize::new(0);
    let run_one = &run_one;
    let slots_ref = &slots;
    let next_ref = &next;
    std::thread::scope(|scope| {
        for _ in 0..workers.min(targets.len()) {
            scope.spawn(move || loop {
                let i = next_ref.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                if i >= slots_ref.len() {
                    break;
                }
                let result = run_one(i);
                *slots_ref[i].lock().expect("fleet result slot poisoned") = Some(result);
            });
        }
    });
    slots
        .into_iter()
        .map(|slot| {
            slot.into_inner()
                .expect("fleet result slot poisoned")
                .expect("every fleet slot is filled before the scope ends")
        })
        .collect()
}

/// Print the fleet summary table for a set of results.
fn print_fleet_table(
    targets: &[VmSshTarget],
    results: &[(i32, String, String)],
    show_output: bool,
) {
    let mut table = new_table(&["VM", "Status", "Output"], &[20, 8, 60]);
    for (target, (code, stdout, stderr)) in targets.iter().zip(results) {
        let (status, ok) = fleet_helpers::classify_result(*code);
        let status_str = if ok {
            format!("\x1b[32m{}\x1b[0m", status)
        } else {
            format!("\x1b[31m{}\x1b[0m", status)
        };
        let output_text = fleet_helpers::format_output_text(*code, stdout, stderr, show_output);
        table.add_row(vec![target.vm_name.clone(), status_str, output_text]);
    }
    println!("{table}");
}

/// Run `cmd` on one VM under a user-supplied `--timeout`.
///
/// Three commands declare a `--timeout` and enforced none of it: `os-update`,
/// `vm update-tools` and `top` all handed the command to SSH and waited
/// (#1089). This puts `timeout(1)` around it *on the VM*, so a runaway `apt`
/// dies there rather than being orphaned when the session is torn down, and
/// gives the transport a matching budget so the remote limit is the one that
/// fires.
///
/// What one timed-bounded remote command did.
enum TimedExec {
    /// The command ran to completion — successfully or not.
    Finished {
        code: i32,
        stdout: String,
        stderr: String,
    },
    /// `--timeout` fired. Carries the sentence naming the flag.
    TimedOut(String),
}

fn exec_under_timeout(target: &VmSshTarget, cmd: &str, timeout: u32) -> Result<TimedExec> {
    let wrapped = fleet_select::wrap_with_timeout(cmd, timeout);
    // The flag bounds the *remote command*. It must never shrink the transport
    // below what the transport itself needs: `azlin top --timeout 5` over a
    // bastion would otherwise get a 35-second budget for a hop that routinely
    // takes longer to establish than that, and every VM would "time out"
    // before its command had started.
    let transport = fleet_select::local_timeout_secs(timeout).max(BASTION_EXEC_TIMEOUT_SECS);
    let (code, stdout, stderr) = target.exec_with_local_timeout(&wrapped, transport)?;
    Ok(match fleet_select::timeout_note(code, timeout) {
        Some(note) => TimedExec::TimedOut(note),
        None => TimedExec::Finished {
            code,
            stdout,
            stderr,
        },
    })
}

/// Execute a command on all running VMs with MultiProgress bars, then print a
/// summary table. Each VM gets its own spinner showing live status.
/// Uses VmSshTarget for proper bastion routing on private VMs.
fn run_on_fleet(targets: &[VmSshTarget], command: &str, show_output: bool) {
    run_on_fleet_with_workers(targets, command, show_output, 1);
}

/// [`run_on_fleet`] with an explicit `--parallel` worker count.
fn run_on_fleet_with_workers(
    targets: &[VmSshTarget],
    command: &str,
    show_output: bool,
    workers: usize,
) -> Vec<(i32, String, String)> {
    run_on_fleet_with_workers_and_timeout(
        targets,
        command,
        show_output,
        workers,
        BASTION_EXEC_TIMEOUT_SECS,
        command,
    )
}

/// [`run_on_fleet_with_workers`] with an explicit transport budget and a
/// display form for the command.
///
/// `azlin batch command --timeout` wraps the user's command the same way
/// `fleet run` does, so the transport needs the same larger budget and the
/// spinners need the unwrapped text.
fn run_on_fleet_with_workers_and_timeout(
    targets: &[VmSshTarget],
    command: &str,
    show_output: bool,
    workers: usize,
    local_timeout_secs: u64,
    display_command: &str,
) -> Vec<(i32, String, String)> {
    let bars = fleet_progress_bars(targets);
    let results = exec_fleet(
        targets,
        command,
        workers,
        &bars,
        local_timeout_secs,
        display_command,
    );
    print_fleet_table(targets, &results, show_output);
    results
}

/// Say so when `--timeout` is what killed a command, naming each VM.
///
/// Without this the table shows a bare `exit 124` with nothing tying it to the
/// flag the user passed.
fn report_batch_timeouts(targets: &[VmSshTarget], results: &[(i32, String, String)], timeout: u32) {
    for (target, (code, _, _)) in targets.iter().zip(results) {
        if let Some(note) = fleet_select::timeout_note(*code, timeout) {
            eprintln!("  {}: {}", target.vm_name, note);
        }
    }
}

fn main() {
    // Suppress Python deprecation warnings from Azure CLI extensions (e.g.
    // pkg_resources in azext_bastion).
    if std::env::var("PYTHONWARNINGS").is_err() {
        // SAFETY: No threads have been spawned yet — this is the first
        // statement in main().  `set_var` is unsafe because it mutates global
        // process state which is UB when other threads read the environment
        // concurrently.  This must remain before any thread-spawning code
        // (including the tokio runtime created below).
        unsafe { std::env::set_var("PYTHONWARNINGS", "ignore::UserWarning:pkg_resources") };
    }

    let start = std::time::Instant::now();
    if let Err(e) = color_eyre::install() {
        eprintln!("Warning: failed to install color_eyre error handler: {e}");
    }

    let result = tokio::runtime::Runtime::new()
        .expect("Failed to create tokio runtime")
        .block_on(async_main(start));

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

async fn async_main(start: std::time::Instant) -> Result<()> {
    let cli = azlin_cli::Cli::parse();

    // --config: the single point where the flag becomes real.
    //
    // Installing the path here, before anything dispatches, is what makes
    // `--config` true for all ~60 subcommands at once. Handlers keep calling
    // `AzlinConfig::load()` and get the file the user named; there is no
    // per-handler plumbing to forget. Before this, `--config` was declared on
    // 60 variants and honoured by one, so `azlin killall --config
    // ./staging.toml --force` read `~/.azlin/config.toml` and could delete
    // every azlin VM in the wrong resource group while reporting success
    // (#1089).
    if let Some(path) = cli.config.as_deref() {
        if let Err(e) = azlin_core::AzlinConfig::use_config_file(path) {
            eprintln!("azlin-error: {e}");
            eprintln!();
            eprintln!(
                "azlin will not fall back to ~/.azlin/config.toml for a --config file it \n\
                 cannot read: that file names a different resource group and subscription, \n\
                 so falling back would run this command somewhere you did not ask for. \n\
                 Check the path, or drop --config to use the default config."
            );
            std::process::exit(2);
        }
    }

    // --startup-time: print diagnostic timing and exit immediately
    if cli.startup_time {
        let parse_elapsed = start.elapsed();
        println!("Startup diagnostics:");
        println!(
            "  CLI parse:  {:.2}ms",
            parse_elapsed.as_secs_f64() * 1000.0
        );
        let config_start = std::time::Instant::now();
        let _config = azlin_core::AzlinConfig::load();
        let config_elapsed = config_start.elapsed();
        println!(
            "  Config load: {:.2}ms",
            config_elapsed.as_secs_f64() * 1000.0
        );
        let total = start.elapsed();
        println!("  Total:       {:.2}ms", total.as_secs_f64() * 1000.0);
        if total.as_millis() < 15 {
            println!(
                "
Startup time is within the <15ms target."
            );
        } else {
            println!(
                "
Startup time ({:.1}ms) exceeds the <15ms target.",
                total.as_secs_f64() * 1000.0
            );
        }
        return Ok(());
    }

    // Initialize tracing lazily -- only when verbose or RUST_LOG is set
    if cli.verbose || std::env::var("RUST_LOG").is_ok() {
        tracing_subscriber::fmt()
            .with_env_filter(EnvFilter::from_default_env())
            .init();
    }

    // Interactive update check: prompt user if a newer version is available.
    // Skip the prompt for the `update` command itself (avoids double-update)
    // and for non-interactive sessions (piped stdin).
    let is_update_cmd = matches!(cli.command, azlin_cli::Commands::Update);
    if !is_update_cmd && std::io::stdin().is_terminal() {
        if let Some(latest) = update_check::check_for_updates_interactive() {
            let safe_version: String = latest
                .chars()
                .filter(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-'))
                .collect();
            eprintln!(
                "\x1b[33mA newer version of azlin is available: v{} → v{}\x1b[0m",
                env!("CARGO_PKG_VERSION"),
                safe_version,
            );
            let should_update = Confirm::new()
                .with_prompt("Update now?")
                .default(true)
                .interact()
                .unwrap_or(false);
            if should_update {
                if let Err(e) = cmd_self_update::handle_self_update() {
                    eprintln!("\x1b[31mUpdate failed: {e:#}\x1b[0m");
                    eprintln!("Continuing with current version...");
                }
            }
        }
    } else if !is_update_cmd {
        // Non-interactive: fall back to passive background check
        update_check::check_for_updates();
    }

    dispatch::dispatch_command(cli).await
}

// Re-export common utilities from dispatch_helpers for cmd_* modules via `use super::*`.
pub(crate) use dispatch_helpers::{
    create_auth, create_auth_with_profile, home_dir, resolve_fleet_targets, resolve_resource_group,
    resolve_vm_ssh_target, resolve_vm_targets, safe_confirm, safe_confirm_with_flag, shell_escape,
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

/// Read side of `azlin context use` — resolves the selected context and the
/// subscription / resource group every command must run against.
mod active_context;

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

/// VM-side SSH key inventory for `azlin keys list`.
#[allow(dead_code)]
mod keys_list;

/// Output layout for `azlin ps` across several VMs.
#[allow(dead_code)]
mod ps_output;

/// Helpers for auth profile display — masking secrets.
#[allow(dead_code)]
mod auth_helpers;

/// Helpers for `azlin cp` — remote path detection and SCP path rewriting.
#[allow(dead_code)]
mod cp_helpers;

/// Helpers for Bastion host JSON extraction.
#[allow(dead_code)]
mod bastion_helpers;

/// NAT gateway provisioning for private VMs (outbound internet) — issue #1092.
/// Azure Bastion is inbound-only and provides no egress.
mod nat_helpers;

/// Scoped bastion tunnel for SSH/SCP through Azure Bastion.
#[allow(dead_code)]
mod bastion_tunnel;

/// Native SSH execution via russh (connection pool).
#[allow(dead_code)]
mod native_ssh;

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

/// Interactive TUI dashboard with sparklines, VM actions, and live refresh.
pub(crate) mod tui_dashboard;

/// Pure helpers for the `run_on_fleet` result classification and formatting.
mod fleet_helpers;

/// Argument construction for `azlin clone`.
mod clone_helpers;

/// Reading and writing `~/.azlin/profiles/`, and what a profile can pin.
mod auth_profile;

/// The `azlin new` egress requirements (R4 and R5 of issue #1092).
mod egress_gate;

/// Pure helpers for the `fleet run` selection, gating and reporting flags.
mod fleet_select;

/// Rendering rules for health metrics that may have no reading at all.
mod health_render;

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

/// Snap-aware wrappers for GUI/X11 command launches.
mod gui_launch_helpers;

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

/// Pure planning helpers for `azlin restore` (dry-run preview, tab expansion).
mod restore_helpers;

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
#[allow(dead_code)]
mod batch_helpers;

/// Multi-progress bar support for batch VM operations.
#[allow(dead_code)]
mod batch_progress;

/// Cost dashboard TUI with budget tracking charts.
mod cost_dashboard;

/// Fleet run output with per-VM tab panels.
mod fleet_tabs;

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
#[allow(dead_code)]
mod cmd_completions;
mod cmd_config_diff;
mod cmd_config_init;
mod cmd_connect;
mod cmd_context;
mod cmd_env;
mod cmd_gui;
mod cmd_gui_install;
#[allow(dead_code)]
mod cmd_history;
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
mod cmd_tunnel;
mod cmd_vm;
mod cmd_vm_ops;
mod cmd_vm_ops2;
mod lifecycle_helpers;
#[allow(dead_code)]
mod ssh_status;
mod table_render;

#[cfg(test)]
#[allow(deprecated)]
mod tests;
