use anyhow::{Context, Result};
use clap::{CommandFactory, Parser};
use comfy_table::{
    modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Color, Table,
};
use console::Style;

/// Create a styled table with the standard UTF8 rounded preset and bold headers.
fn new_table(headers: &[&str]) -> Table {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(
            headers
                .iter()
                .map(|h| Cell::new(*h).add_attribute(Attribute::Bold))
                .collect::<Vec<_>>(),
        );
    table
}
use crossterm::{
    event::{self, Event, KeyCode},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    ExecutableCommand,
};
use dialoguer::Confirm;
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
    let output = std::process::Command::new("ssh")
        .args([
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "BatchMode=yes",
            &format!("{}@{}", user, ip),
            cmd,
        ])
        .output()?;
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
    let mut args = vec![
        "network",
        "bastion",
        "ssh",
        "--name",
        bastion_name,
        "--resource-group",
        resource_group,
        "--target-resource-id",
        vm_resource_id,
        "--auth-type",
        "ssh-key",
        "--username",
        user,
    ];
    let key_str;
    if let Some(key) = ssh_key {
        key_str = key.to_string_lossy().to_string();
        args.push("--ssh-key");
        args.push(&key_str);
    }
    args.push("--");
    args.push(cmd);

    azlin_azure::run_with_timeout("az", &args, 60)
}

/// Named bastion routing info, replacing the opaque 4-tuple.
struct BastionRoute {
    bastion_name: String,
    resource_group: String,
    vm_resource_id: String,
    ssh_key_path: Option<std::path::PathBuf>,
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
    let ip = vm
        .public_ip
        .as_deref()
        .or(vm.private_ip.as_deref())
        .unwrap_or("")
        .to_string();
    let user = vm
        .admin_username
        .clone()
        .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

    let bastion = if vm.public_ip.is_none() {
        // Private IP only — need bastion
        bastion_map.get(&vm.location).map(|bastion_name| {
            let vm_rid = format!(
                "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                subscription_id, vm.resource_group, vm.name
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
        .map(|(_, out, _)| {
            let trimmed = out.trim();
            if trimmed == "active" {
                "OK".to_string()
            } else if trimmed == "inactive" {
                "Down".to_string()
            } else {
                "N/A".to_string()
            }
        })
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

/// Render a health metrics table.
fn render_health_table(metrics: &[HealthMetrics]) {
    let mut table = new_table(&[
        "VM Name", "State", "Agent", "Errors", "CPU %", "Memory %", "Disk %",
    ]);

    for m in metrics {
        let state_color = match m.power_state.as_str() {
            "running" => Color::Green,
            "stopped" | "deallocated" => Color::Red,
            _ => Color::Yellow,
        };
        let agent_color = match m.agent_status.as_str() {
            "OK" => Color::Green,
            "Down" => Color::Red,
            _ => Color::Yellow,
        };
        let error_color = if m.error_count > 10 {
            Color::Red
        } else if m.error_count > 0 {
            Color::Yellow
        } else {
            Color::Green
        };
        let cpu_color = if m.cpu_percent > 90.0 {
            Color::Red
        } else if m.cpu_percent > 70.0 {
            Color::Yellow
        } else {
            Color::Green
        };
        let mem_color = if m.mem_percent > 90.0 {
            Color::Red
        } else if m.mem_percent > 70.0 {
            Color::Yellow
        } else {
            Color::Green
        };
        let disk_color = if m.disk_percent > 90.0 {
            Color::Red
        } else if m.disk_percent > 70.0 {
            Color::Yellow
        } else {
            Color::Green
        };

        table.add_row(vec![
            Cell::new(&m.vm_name),
            Cell::new(&m.power_state).fg(state_color),
            Cell::new(&m.agent_status).fg(agent_color),
            Cell::new(m.error_count.to_string()).fg(error_color),
            Cell::new(format!("{:.1}", m.cpu_percent)).fg(cpu_color),
            Cell::new(format!("{:.1}", m.mem_percent)).fg(mem_color),
            Cell::new(format!("{:.1}", m.disk_percent)).fg(disk_color),
        ]);
    }
    println!("{table}");
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

    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec![
            Cell::new("VM").add_attribute(Attribute::Bold),
            Cell::new("Status").add_attribute(Attribute::Bold),
            Cell::new("Output").add_attribute(Attribute::Bold),
        ]);

    for (i, (name, ip, user)) in vms.iter().enumerate() {
        bars[i].set_message(format!("running: {}", command));
        let (code, stdout, stderr) = match ssh_exec(ip, user, command) {
            Ok(r) => r,
            Err(e) => (-1, String::new(), e.to_string()),
        };

        bars[i].finish_with_message(fleet_helpers::finish_message(code, &stdout, &stderr));

        let (status, ok) = fleet_helpers::classify_result(code);
        let status_color = if ok { Color::Green } else { Color::Red };
        let output_text = fleet_helpers::format_output_text(code, &stdout, &stderr, show_output);
        table.add_row(vec![
            Cell::new(name),
            Cell::new(status).fg(status_color),
            Cell::new(&output_text),
        ]);
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
        eprintln!("Error: {e}");

        if msg.contains("az login") || msg.contains("authentication") || msg.contains("Azure") {
            eprintln!("\n💡 Suggestion: Run 'az login' to authenticate with Azure");
        }
        if msg.contains("ANTHROPIC_API_KEY") {
            eprintln!("\n💡 Suggestion: Set ANTHROPIC_API_KEY environment variable");
            eprintln!("   Get a key at: https://console.anthropic.com/");
        }
        if msg.contains("not found") && msg.contains("VM") {
            eprintln!("\n💡 Suggestion: Run 'azlin list' to see available VMs");
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
    dispatch_command(cli).await
}

/// Dispatch a parsed CLI command. Separated from async_main for testability —
/// tests can construct a Cli struct and call this directly (in-process coverage).
#[cfg_attr(test, allow(dead_code))]
async fn dispatch_command(cli: azlin_cli::Cli) -> Result<()> {
    if cli.verbose {
        tracing::info!("Verbose mode enabled");
    }

    match cli.command {
        azlin_cli::Commands::Version => {
            println!("azlin {} (rust)", env!("CARGO_PKG_VERSION"));
        }
        azlin_cli::Commands::Config { action } => match action {
            azlin_cli::ConfigAction::Show => {
                let config = azlin_core::AzlinConfig::load()?;
                let json = serde_json::to_value(&config)?;
                let key_style = Style::new().cyan().bold();
                let val_style = Style::new().white();
                if let Some(obj) = json.as_object() {
                    for (k, v) in obj {
                        let display = match v {
                            serde_json::Value::String(s) => s.clone(),
                            serde_json::Value::Null => "null".to_string(),
                            other => other.to_string(),
                        };
                        println!(
                            "{}: {}",
                            key_style.apply_to(k),
                            val_style.apply_to(&display)
                        );
                    }
                }
            }
            azlin_cli::ConfigAction::Get { key } => {
                let config = azlin_core::AzlinConfig::load()?;
                let json = serde_json::to_value(&config)?;
                match json.get(&key) {
                    Some(serde_json::Value::String(s)) => println!("{s}"),
                    Some(val) => println!("{val}"),
                    None => eprintln!("Unknown config key: {key}"),
                }
            }
            azlin_cli::ConfigAction::Set { key, value } => {
                let mut config = azlin_core::AzlinConfig::load()?;
                let mut json = serde_json::to_value(&config)?;
                if let Some(obj) = json.as_object() {
                    if !obj.contains_key(&key) {
                        anyhow::bail!("Unknown config key: {key}");
                    }
                }
                let validated = azlin_core::AzlinConfig::validate_field(&key, &value)?;
                if let Some(obj) = json.as_object_mut() {
                    obj.insert(key.clone(), validated);
                    config = serde_json::from_value(json)?;
                    config.save()?;
                    println!("Set {key} = {value}");
                }
            }
        },
        azlin_cli::Commands::List {
            resource_group,
            all,
            tag,
            no_tmux,
            with_latency,
            show_procs,
            with_health,
            wide,
            compact,
            quota,
            show_all_vms,
            vm_pattern,
            include_stopped,
            all_contexts,
            restore,
            contexts,
            no_cache,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let include_all = all || include_stopped;

            // Select cached or uncached list methods based on --no-cache flag
            let list_vms = |mgr: &azlin_azure::VmManager,
                            rg: &str|
             -> Result<Vec<azlin_core::models::VmInfo>> {
                if no_cache {
                    mgr.list_vms_no_cache(rg)
                } else {
                    mgr.list_vms(rg)
                }
            };
            let list_all =
                |mgr: &azlin_azure::VmManager| -> Result<Vec<azlin_core::models::VmInfo>> {
                    if no_cache {
                        mgr.list_all_vms_no_cache()
                    } else {
                        mgr.list_all_vms()
                    }
                };

            // Resolve resource group(s)
            if cli.verbose {
                eprintln!(
                    "[VERBOSE] Fetching VMs from resource group: {}",
                    resource_group.as_deref().unwrap_or("(default)")
                );
            }
            let mut all_vms = if all_contexts {
                // Read all context files from ~/.azlin/contexts/ and aggregate VMs
                let ctx_dir = home_dir()?.join(".azlin").join("contexts");
                if ctx_dir.is_dir() {
                    let mut aggregated = Vec::new();
                    let mut entries: Vec<_> = std::fs::read_dir(&ctx_dir)?
                        .filter_map(|e| e.ok())
                        .filter(|e| e.path().extension().is_some_and(|ext| ext == "toml"))
                        .collect();
                    entries.sort_by_key(|e| e.file_name());
                    for entry in entries {
                        match contexts::read_context_resource_group(&entry.path()) {
                            Ok((ctx_name, Some(rg))) => {
                                // If --contexts pattern provided, filter context names
                                if let Some(ref pattern) = contexts {
                                    let pat = pattern.replace('*', "");
                                    // Simple glob: if pattern contains *, do substring match
                                    // Otherwise exact match
                                    if pattern.contains('*') {
                                        if !ctx_name.contains(&pat) {
                                            continue;
                                        }
                                    } else if ctx_name != *pattern {
                                        continue;
                                    }
                                }
                                match list_vms(&vm_manager, &rg) {
                                    Ok(vms) => {
                                        println!("── context: {} (rg: {}) ──", ctx_name, rg);
                                        aggregated.extend(vms);
                                    }
                                    Err(e) => {
                                        eprintln!("Warning: failed to list VMs for context '{}' (rg: {}): {}", ctx_name, rg, e);
                                    }
                                }
                            }
                            Ok((ctx_name, None)) => {
                                eprintln!(
                                    "Warning: context '{}' has no resource_group, skipping.",
                                    ctx_name
                                );
                            }
                            Err(e) => {
                                eprintln!(
                                    "Warning: failed to read context file {:?}: {}",
                                    entry.path(),
                                    e
                                );
                            }
                        }
                    }
                    aggregated
                } else {
                    eprintln!(
                        "Warning: no contexts directory found at {:?}. Using default VM list.",
                        ctx_dir
                    );
                    match &resource_group {
                        Some(rg) => list_vms(&vm_manager, rg)?,
                        None => {
                            let config = azlin_core::AzlinConfig::load()
                                .context("Failed to load azlin config")?;
                            match config.default_resource_group {
                                Some(rg) => list_vms(&vm_manager, &rg)?,
                                None => {
                                    anyhow::bail!("No resource group specified. Use --resource-group or set in config.");
                                }
                            }
                        }
                    }
                }
            } else if show_all_vms {
                list_all(&vm_manager)?
            } else {
                match &resource_group {
                    Some(rg) => list_vms(&vm_manager, rg)?,
                    None => {
                        let config = azlin_core::AzlinConfig::load()
                            .context("Failed to load azlin config")?;
                        match config.default_resource_group {
                            Some(rg) => list_vms(&vm_manager, &rg)?,
                            None => {
                                anyhow::bail!("No resource group specified. Use --resource-group or set in config.");
                            }
                        }
                    }
                }
            };

            if cli.verbose {
                eprintln!("[VERBOSE] Fetched {} VMs", all_vms.len());
            }

            // Filter stopped VMs unless --all/--include-stopped,
            // then by tag and name pattern.
            list_helpers::apply_filters(
                &mut all_vms,
                include_all,
                tag.as_deref(),
                vm_pattern.as_deref(),
            );

            // Preserve Azure's natural ordering (matches Python behavior)

            if cli.verbose {
                eprintln!("[VERBOSE] Detecting bastion hosts...");
            }
            // Detect and display bastion hosts (matching Python: shown above VM table)
            // Use the resolved resource group from the VMs themselves
            let effective_rg = all_vms
                .first()
                .map(|v| v.resource_group.as_str())
                .unwrap_or("");
            if matches!(&cli.output, azlin_cli::OutputFormat::Table) && !effective_rg.is_empty() {
                if let Ok(bastions) = list_helpers::detect_bastion_hosts(effective_rg) {
                    if !bastions.is_empty() {
                        let mut bastion_table = Table::new();
                        bastion_table
                            .load_preset(UTF8_FULL)
                            .apply_modifier(UTF8_ROUND_CORNERS);
                        bastion_table.set_header(vec![
                            Cell::new("Name").add_attribute(Attribute::Bold),
                            Cell::new("Location").add_attribute(Attribute::Bold),
                            Cell::new("SKU").add_attribute(Attribute::Bold),
                        ]);
                        for (name, location, sku) in &bastions {
                            bastion_table.add_row(vec![
                                Cell::new(name),
                                Cell::new(location),
                                Cell::new(sku),
                            ]);
                        }
                        println!("Azure Bastion Hosts");
                        println!("{bastion_table}");
                        println!();
                    }
                }
            }

            if cli.verbose {
                eprintln!("[VERBOSE] Collecting tmux sessions via bastion SSH...");
            }
            // Collect tmux sessions if not disabled
            let mut tmux_sessions: std::collections::HashMap<String, Vec<String>> =
                std::collections::HashMap::new();
            if !no_tmux {
                // Build bastion name map (region -> bastion_name) for private VMs
                let bastion_map: std::collections::HashMap<String, String> =
                    if matches!(&cli.output, azlin_cli::OutputFormat::Table) {
                        if let Ok(bastions) = list_helpers::detect_bastion_hosts(effective_rg) {
                            bastions
                                .into_iter()
                                .map(|(name, location, _)| (location, name))
                                .collect()
                        } else {
                            std::collections::HashMap::new()
                        }
                    } else {
                        std::collections::HashMap::new()
                    };

                // Resolve SSH key path
                let ssh_key = home_dir()
                    .ok()
                    .map(|h| h.join(".ssh").join("azlin_key"))
                    .filter(|p| p.exists())
                    .or_else(|| {
                        home_dir()
                            .ok()
                            .map(|h| h.join(".ssh").join("id_rsa"))
                            .filter(|p| p.exists())
                    });

                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let user = vm
                        .admin_username
                        .as_deref()
                        .unwrap_or(DEFAULT_ADMIN_USERNAME);
                    let tmux_cmd = "tmux list-sessions -F '#{session_name}' 2>/dev/null || true";

                    let output = if let Some(ip) = &vm.public_ip {
                        // Direct SSH for VMs with public IPs
                        std::process::Command::new("ssh")
                            .args([
                                "-o",
                                "StrictHostKeyChecking=accept-new",
                                "-o",
                                "ConnectTimeout=5",
                                "-o",
                                "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                tmux_cmd,
                            ])
                            .output()
                    } else if let Some(bastion_name) = bastion_map.get(&vm.location) {
                        // Use az network bastion ssh for private-only VMs
                        let vm_id = format!(
                            "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                            vm_manager.subscription_id(), vm.resource_group, vm.name
                        );
                        let mut args = vec![
                            "network".to_string(),
                            "bastion".to_string(),
                            "ssh".to_string(),
                            "--name".to_string(),
                            bastion_name.clone(),
                            "--resource-group".to_string(),
                            vm.resource_group.clone(),
                            "--target-resource-id".to_string(),
                            vm_id,
                            "--auth-type".to_string(),
                            "ssh-key".to_string(),
                            "--username".to_string(),
                            user.to_string(),
                        ];
                        if let Some(ref key) = ssh_key {
                            args.push("--ssh-key".to_string());
                            args.push(key.to_string_lossy().to_string());
                        }
                        args.push("--".to_string());
                        args.push(tmux_cmd.to_string());

                        let str_args: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
                        std::process::Command::new("az")
                            .args(&str_args)
                            .stdout(std::process::Stdio::piped())
                            .stderr(std::process::Stdio::piped())
                            .output()
                    } else {
                        continue; // No bastion available for this region
                    };

                    if let Ok(out) = output {
                        if out.status.success() {
                            let sessions: Vec<String> = String::from_utf8_lossy(&out.stdout)
                                .lines()
                                .filter(|l| !l.is_empty() && !l.starts_with('{'))
                                .map(|l| l.to_string())
                                .collect();
                            if cli.verbose {
                                eprintln!("[VERBOSE] {} -> {} sessions", vm.name, sessions.len());
                            }
                            if !sessions.is_empty() {
                                tmux_sessions.insert(vm.name.clone(), sessions);
                            }
                        }
                    }
                }
            }

            // Collect latency if requested
            let mut latencies: std::collections::HashMap<String, u64> =
                std::collections::HashMap::new();
            if with_latency {
                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let addr = match format!("{}:22", ip).parse() {
                            Ok(addr) => addr,
                            Err(_) => continue,
                        };
                        let start = std::time::Instant::now();
                        let _ = std::net::TcpStream::connect_timeout(
                            &addr,
                            std::time::Duration::from_secs(5),
                        );
                        latencies.insert(vm.name.clone(), start.elapsed().as_millis() as u64);
                    }
                }
            }

            // Collect health metrics if requested
            let mut health_data: std::collections::HashMap<String, String> =
                std::collections::HashMap::new();
            if with_health {
                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        let output = std::process::Command::new("ssh")
                            .args([
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=10",
                                "-o", "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                "echo \"CPU:$(top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{printf \"%.1f\", 100 - $1}')% MEM:$(free -m | awk '/Mem:/{printf \"%.0f%%\", $3/$2*100}') DISK:$(df -h / | awk 'NR==2{print $5}')\"",
                            ])
                            .output();
                        if let Ok(out) = output {
                            if out.status.success() {
                                let metrics =
                                    String::from_utf8_lossy(&out.stdout).trim().to_string();
                                health_data.insert(vm.name.clone(), metrics);
                            }
                        }
                    }
                }
            }

            // Collect top processes if requested
            let mut proc_data: std::collections::HashMap<String, String> =
                std::collections::HashMap::new();
            if show_procs {
                for vm in &all_vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        let output = std::process::Command::new("ssh")
                            .args([
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=10",
                                "-o", "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                "ps aux --sort=-%mem | head -6 | tail -5 | awk '{print $11}' | tr '\\n' ', '",
                            ])
                            .output();
                        if let Ok(out) = output {
                            if out.status.success() {
                                let procs = String::from_utf8_lossy(&out.stdout).trim().to_string();
                                proc_data.insert(vm.name.clone(), procs);
                            }
                        }
                    }
                }
            }

            // Build and render table
            let show_tmux_col = !no_tmux;
            let mut headers = vec!["Session"];
            if show_tmux_col {
                headers.push("Tmux");
            }
            if wide {
                headers.push("VM Name");
            }
            headers.extend_from_slice(&["OS", "Status", "IP", "Region"]);
            if wide {
                headers.push("SKU");
            }
            headers.extend_from_slice(&["CPU", "Mem"]);
            if with_latency {
                headers.push("Latency");
            }
            if with_health {
                headers.push("Health");
            }
            if show_procs {
                headers.push("Top Procs");
            }

            match &cli.output {
                azlin_cli::OutputFormat::Json => {
                    let json_vms: Vec<serde_json::Value> = all_vms
                        .iter()
                        .map(|vm| {
                            let ip_display = display_helpers::format_ip_display(
                                vm.public_ip.as_deref(),
                                vm.private_ip.as_deref(),
                            );
                            let os_display = display_helpers::format_os_display(
                                vm.os_offer.as_deref(),
                                &vm.os_type,
                            );
                            let (cpu, mem) = display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
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
                                "tmux_sessions": tmux_sessions.get(&vm.name).cloned().unwrap_or_default(),
                            });
                            if with_latency {
                                obj["latency_ms"] = serde_json::json!(latencies.get(&vm.name));
                            }
                            if with_health {
                                obj["health"] = serde_json::json!(health_data.get(&vm.name));
                            }
                            obj
                        })
                        .collect();
                    println!("{}", serde_json::to_string_pretty(&json_vms)?);
                }
                azlin_cli::OutputFormat::Csv => {
                    println!("{}", headers.join(","));
                    for vm in &all_vms {
                        let session = vm
                            .tags
                            .get("azlin-session")
                            .map(|s| s.as_str())
                            .unwrap_or("-");
                        let tmux = tmux_sessions
                            .get(&vm.name)
                            .map(|s| s.join(";"))
                            .unwrap_or_default();
                        let ip_display = display_helpers::format_ip_display(
                            vm.public_ip.as_deref(),
                            vm.private_ip.as_deref(),
                        );
                        let os_display =
                            display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type);
                        let (cpu, mem) =
                            display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
                        let mut row = session.to_string();
                        if show_tmux_col {
                            row.push_str(&format!(",{}", tmux));
                        }
                        if wide {
                            row.push_str(&format!(",{}", vm.name));
                        }
                        row.push_str(&format!(
                            ",{},{},{},{}",
                            os_display, vm.power_state, ip_display, vm.location
                        ));
                        if wide {
                            row.push_str(&format!(",{}", vm.vm_size));
                        }
                        row.push_str(&format!(",{},{}", cpu, mem));
                        if with_latency {
                            row.push_str(&format!(
                                ",{}",
                                latencies
                                    .get(&vm.name)
                                    .map(|l| format!("{}ms", l))
                                    .unwrap_or_default()
                            ));
                        }
                        println!("{}", row);
                    }
                }
                azlin_cli::OutputFormat::Table => {
                    let mut table = Table::new();
                    table
                        .load_preset(UTF8_FULL)
                        .apply_modifier(UTF8_ROUND_CORNERS);
                    let header_cells: Vec<Cell> = headers
                        .iter()
                        .map(|h| Cell::new(h).add_attribute(Attribute::Bold))
                        .collect();
                    table.set_header(header_cells);

                    if compact {
                        table.set_width(80);
                    }

                    for vm in &all_vms {
                        let session = vm
                            .tags
                            .get("azlin-session")
                            .map(|s| s.as_str())
                            .unwrap_or("-");
                        let tmux = tmux_sessions
                            .get(&vm.name)
                            .map(|s| display_helpers::format_tmux_sessions(s, 3))
                            .unwrap_or_else(|| "-".to_string());
                        let ip_display = display_helpers::format_ip_display(
                            vm.public_ip.as_deref(),
                            vm.private_ip.as_deref(),
                        );
                        let os_display =
                            display_helpers::format_os_display(vm.os_offer.as_deref(), &vm.os_type);
                        let (cpu, mem) =
                            display_helpers::query_vm_size_specs(&vm.vm_size, &vm.location);
                        let state_color = match vm.power_state {
                            azlin_core::models::PowerState::Running => Color::Green,
                            azlin_core::models::PowerState::Stopped
                            | azlin_core::models::PowerState::Deallocated => Color::Red,
                            _ => Color::Yellow,
                        };

                        let vm_name_display = if wide {
                            vm.name.clone()
                        } else {
                            display_helpers::truncate_vm_name(&vm.name, 20)
                        };

                        let mut row = vec![Cell::new(session)];
                        if show_tmux_col {
                            row.push(Cell::new(&tmux));
                        }
                        if wide {
                            row.push(Cell::new(&vm_name_display));
                        }
                        row.extend_from_slice(&[
                            Cell::new(&os_display),
                            Cell::new(vm.power_state.to_string()).fg(state_color),
                            Cell::new(&ip_display),
                            Cell::new(&vm.location),
                        ]);
                        if wide {
                            row.push(Cell::new(&vm.vm_size));
                        }
                        row.extend_from_slice(&[Cell::new(&cpu), Cell::new(&mem)]);
                        if with_latency {
                            let lat = latencies
                                .get(&vm.name)
                                .map(|l| format!("{}ms", l))
                                .unwrap_or_else(|| "-".to_string());
                            row.push(Cell::new(lat));
                        }
                        if with_health {
                            let h = health_data
                                .get(&vm.name)
                                .cloned()
                                .unwrap_or_else(|| "-".to_string());
                            row.push(Cell::new(h));
                        }
                        if show_procs {
                            let p = proc_data
                                .get(&vm.name)
                                .cloned()
                                .unwrap_or_else(|| "-".to_string());
                            row.push(Cell::new(p));
                        }
                        table.add_row(row);
                    }
                    println!("{table}");

                    // Summary footer
                    let total = all_vms.len();
                    let total_tmux: usize = tmux_sessions.values().map(|v| v.len()).sum();

                    println!();
                    if total_tmux > 0 {
                        println!("Total: {} VMs | {} tmux sessions", total, total_tmux);
                    } else {
                        println!("Total: {} VMs", total);
                    }

                    if !show_all_vms {
                        println!();
                        println!("Hints:");
                        println!("  azlin list -a        Show all VMs across all resource groups");
                        println!("  azlin list -w        Wide mode (show VM Name, SKU columns)");
                        println!(
                            "  azlin list -r        Restore all tmux sessions in new terminal window"
                        );
                        println!("  azlin list -q        Show quota usage (slower)");
                        println!("  azlin list -v        Verbose mode (show tunnel/SSH details)");
                    }
                }
            }

            // Restore tmux sessions if requested (connect to each VM with active tmux)
            if restore && !tmux_sessions.is_empty() {
                println!("\nRestoring tmux sessions...");
                let use_wt = std::env::var("WT_SESSION").is_ok();
                for (vm_name, sessions) in &tmux_sessions {
                    if let Some(first_session) = sessions.first() {
                        if use_wt {
                            println!("  Opening tab: {} (session: {})", vm_name, first_session);
                            let _ = std::process::Command::new("wt.exe")
                                .args([
                                    "-w",
                                    "0",
                                    "new-tab",
                                    "azlin",
                                    "connect",
                                    vm_name,
                                    "--tmux-session",
                                    first_session,
                                ])
                                .spawn();
                        } else {
                            println!("  Connecting to {} (session: {})", vm_name, first_session);
                            let _ = std::process::Command::new("azlin")
                                .args(["connect", vm_name, "--tmux-session", first_session])
                                .spawn();
                        }
                    }
                }
                println!("Session restore initiated.");
            }

            // Show quota summary if requested
            if quota {
                let _rg = match resource_group {
                    Some(rg) => rg,
                    None => {
                        let config = azlin_core::AzlinConfig::load()
                            .context("Failed to load azlin config")?;
                        config.default_resource_group.ok_or_else(|| {
                            anyhow::anyhow!("No resource group specified. Use --resource-group or set in config.")
                        })?
                    }
                };
                println!("\nvCPU Quota:");
                // Use the configured default region instead of hardcoding "westus"
                let config_for_quota = azlin_core::AzlinConfig::load().unwrap_or_default();
                let quota_location = config_for_quota.default_region.clone();
                let output = std::process::Command::new("az")
                    .args([
                        "vm",
                        "list-usage",
                        "--location",
                        &quota_location,
                        "--query",
                        "[?contains(name.value, 'vCPUs')].{Name:name.localizedValue, Current:currentValue, Limit:limit}",
                        "--output",
                        "table",
                    ])
                    .output()?;
                if output.status.success() {
                    print!("{}", String::from_utf8_lossy(&output.stdout));
                }
            }
        }
        azlin_cli::Commands::Start {
            vm_name,
            resource_group,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("Starting {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let msg = handlers::handle_start(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(format!("✓ {}", msg));
        }
        azlin_cli::Commands::Stop {
            vm_name,
            resource_group,
            deallocate,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let (action, _done) = stop_helpers::stop_action_labels(deallocate);
            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("{} {}...", action, vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let msg = handlers::handle_stop(&vm_manager, &rg, &vm_name, deallocate)?;
            pb.finish_with_message(format!("✓ {}", msg));
        }
        azlin_cli::Commands::Show {
            name,
            resource_group,
            config: _,
            output,
            verbose: _,
            auth_profile: _,
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Fetching {}...", name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = handlers::handle_show(&vm_manager, &rg, &name)?;
            pb.finish_and_clear();

            match output {
                azlin_cli::OutputFormat::Json => {
                    println!("{}", handlers::format_show_json(&vm)?);
                }
                azlin_cli::OutputFormat::Csv => {
                    print!("{}", handlers::format_show_csv(&vm));
                }
                azlin_cli::OutputFormat::Table => {
                    print!("{}", handlers::format_show_table(&vm));
                }
            }
        }
        azlin_cli::Commands::Connect {
            vm_identifier,
            resource_group,
            user,
            key,
            no_tmux,
            tmux_session,
            no_reconnect,
            max_retries,
            yes,
            remote_command,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            // If no VM specified, show interactive picker of running VMs
            let name = if let Some(id) = vm_identifier {
                id
            } else {
                let vms = vm_manager.list_vms(&rg)?;
                let running: Vec<_> = vms
                    .iter()
                    .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
                    .collect();
                if running.is_empty() {
                    anyhow::bail!("No running VMs found in resource group '{}'", rg);
                }
                println!("Select a VM to connect to:");
                for (i, vm) in running.iter().enumerate() {
                    let ip = vm
                        .public_ip
                        .as_deref()
                        .or(vm.private_ip.as_deref())
                        .unwrap_or("-");
                    println!("  [{}] {} ({})", i + 1, vm.name, ip);
                }
                print!("> ");
                use std::io::Write;
                std::io::stdout().flush()?;
                let mut input = String::new();
                std::io::stdin().read_line(&mut input)?;
                let idx: usize = input
                    .trim()
                    .parse::<usize>()
                    .context("Invalid selection")?
                    .checked_sub(1)
                    .context("Selection out of range")?;
                if idx >= running.len() {
                    anyhow::bail!("Selection out of range");
                }
                running[idx].name.clone()
            };

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &name)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
            let username = vm.admin_username.unwrap_or_else(|| user.clone());

            let mut ssh_args = connect_helpers::build_ssh_args(&username, &ip, key.as_deref());

            if !no_tmux {
                let sess = tmux_session.as_deref().unwrap_or("azlin");
                if !sess
                    .chars()
                    .all(|c| c.is_alphanumeric() || c == '_' || c == '-')
                {
                    anyhow::bail!(
                        "Invalid tmux session name: must be alphanumeric, underscore, or hyphen"
                    );
                }
                // Wrap SSH in tmux attach-or-create
                if remote_command.is_empty() {
                    ssh_args.push("-t".to_string());
                    ssh_args.push(format!("tmux new-session -A -s {}", sess));
                } else {
                    ssh_args.extend(remote_command.iter().cloned());
                }
            } else if !remote_command.is_empty() {
                ssh_args.extend(remote_command.iter().cloned());
            }

            let mut attempt = 0u32;
            let max = if no_reconnect { 1 } else { max_retries + 1 };
            loop {
                let status = std::process::Command::new("ssh").args(&ssh_args).status()?;
                attempt += 1;
                if status.success() || attempt >= max {
                    std::process::exit(status.code().unwrap_or(1));
                }
                if !yes {
                    eprint!(
                        "SSH disconnected. Reconnect? (attempt {}/{}) [Y/n] ",
                        attempt,
                        max - 1
                    );
                    let mut input = String::new();
                    std::io::stdin().read_line(&mut input)?;
                    if input.trim().eq_ignore_ascii_case("n") {
                        std::process::exit(status.code().unwrap_or(1));
                    }
                } else {
                    eprintln!(
                        "SSH disconnected. Reconnecting (attempt {}/{})...",
                        attempt,
                        max - 1
                    );
                }
                std::thread::sleep(std::time::Duration::from_secs(2));
            }
        }
        azlin_cli::Commands::Tag { action } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            match action {
                azlin_cli::TagAction::Add {
                    vm_name,
                    tags,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let parsed: Vec<(String, String)> = tags
                        .iter()
                        .map(|tag| match tag_helpers::parse_tag(tag) {
                            Some((k, v)) => Ok((k.to_string(), v.to_string())),
                            None => anyhow::bail!("Invalid tag format '{}'. Use key=value.", tag),
                        })
                        .collect::<Result<Vec<_>>>()?;
                    let msgs = handlers::handle_tag_add(&vm_manager, &rg, &vm_name, &parsed)?;
                    for msg in msgs {
                        println!("{}", msg);
                    }
                }
                azlin_cli::TagAction::Remove {
                    vm_name,
                    tag_keys,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let msgs = handlers::handle_tag_remove(&vm_manager, &rg, &vm_name, &tag_keys)?;
                    for msg in msgs {
                        println!("{}", msg);
                    }
                }
                azlin_cli::TagAction::List {
                    vm_name,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let tags = handlers::handle_tag_list(&vm_manager, &rg, &vm_name)?;
                    azlin_cli::table::render_tags_table(&vm_name, &tags);
                }
            }
        }
        azlin_cli::Commands::W {
            resource_group,
            vm,
            ip,
            ..
        } => {
            let targets = resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
            for target in &targets {
                println!("── {} ──", target.vm_name);
                match target.exec_checked("w") {
                    Ok(output) => print!("{}", output),
                    Err(e) => eprintln!("  Error: {}", e),
                }
            }
        }
        azlin_cli::Commands::Ps {
            resource_group,
            vm,
            ip,
            ..
        } => {
            let targets = resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
            for target in &targets {
                println!("── {} ──", target.vm_name);
                match target.exec_checked("ps aux --sort=-%mem | head -20") {
                    Ok(output) => print!("{}", output),
                    Err(e) => eprintln!("  Error: {}", e),
                }
            }
        }
        azlin_cli::Commands::Top {
            resource_group,
            vm,
            ip,
            ..
        } => {
            let targets = resolve_vm_targets(vm.as_deref(), ip.as_deref(), resource_group).await?;
            for target in &targets {
                println!("── {} ──", target.vm_name);
                match target.exec_checked("top -b -n 1 | head -30") {
                    Ok(output) => print!("{}", output),
                    Err(e) => eprintln!("  Error: {}", e),
                }
            }
        }
        azlin_cli::Commands::Health {
            vm,
            resource_group,
            tui,
            ..
        } => {
            let auth = match azlin_azure::AzureAuth::new() {
                Ok(a) => a,
                Err(_) => {
                    anyhow::bail!(
                        "Azure authentication failed.\n\
                         Hint: use 'az login' or specify --vm and --ip flags for direct SSH."
                    );
                }
            };
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Collecting health metrics...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            // Detect bastion hosts for private-IP-only VMs
            let bastion_map: std::collections::HashMap<String, String> =
                list_helpers::detect_bastion_hosts(&rg)
                    .unwrap_or_default()
                    .into_iter()
                    .map(|(name, location, _)| (location, name))
                    .collect();

            // Resolve SSH key path for bastion tunnelling
            let ssh_key_path = home_dir()
                .ok()
                .map(|h| h.join(".ssh").join("azlin_key"))
                .filter(|p| p.exists())
                .or_else(|| {
                    home_dir()
                        .ok()
                        .map(|h| h.join(".ssh").join("id_rsa"))
                        .filter(|p| p.exists())
                });

            let sub_id = vm_manager.subscription_id().to_string();

            let metrics: Vec<HealthMetrics> = if let Some(vm_name) = vm {
                let vm_info = vm_manager.get_vm(&rg, &vm_name)?;
                let ip = vm_info
                    .public_ip
                    .clone()
                    .or(vm_info.private_ip.clone())
                    .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_name))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                let state = vm_info.power_state.to_string();

                // Use bastion when there is no public IP
                let bastion_info_owned: Option<(
                    String,
                    String,
                    String,
                    Option<std::path::PathBuf>,
                )> = if vm_info.public_ip.is_none() {
                    bastion_map.get(&vm_info.location).map(|bn| {
                            let vm_rid = format!(
                                "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                                sub_id, vm_info.resource_group, vm_info.name
                            );
                            (bn.clone(), vm_info.resource_group.clone(), vm_rid, ssh_key_path.clone())
                        })
                } else {
                    None
                };
                let bastion_ref = bastion_info_owned.as_ref().map(|(bn, rg_b, rid, key)| {
                    (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref())
                });

                vec![collect_health_metrics(
                    &vm_name,
                    &ip,
                    &user,
                    &state,
                    bastion_ref,
                )]
            } else {
                let vms = vm_manager.list_vms(&rg)?;
                vms.iter()
                    .filter_map(|vm_info| {
                        let ip = vm_info.public_ip.as_ref().or(vm_info.private_ip.as_ref())?;
                        let user = vm_info
                            .admin_username
                            .clone()
                            .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
                        let state = vm_info.power_state.to_string();

                        // Use bastion when there is no public IP
                        let bastion_info_owned: Option<(String, String, String, Option<std::path::PathBuf>)> =
                            if vm_info.public_ip.is_none() {
                                bastion_map.get(&vm_info.location).map(|bn| {
                                    let vm_rid = format!(
                                        "/subscriptions/{}/resourceGroups/{}/providers/Microsoft.Compute/virtualMachines/{}",
                                        sub_id, vm_info.resource_group, vm_info.name
                                    );
                                    (bn.clone(), vm_info.resource_group.clone(), vm_rid, ssh_key_path.clone())
                                })
                            } else {
                                None
                            };
                        let bastion_ref = bastion_info_owned.as_ref().map(|(bn, rg_b, rid, key)| {
                            (bn.as_str(), rg_b.as_str(), rid.as_str(), key.as_deref())
                        });

                        Some(collect_health_metrics(&vm_info.name, ip, &user, &state, bastion_ref))
                    })
                    .collect()
            };
            pb.finish_and_clear();

            if metrics.is_empty() {
                println!("No VMs found in resource group '{}'", rg);
            } else if tui {
                run_health_tui(&metrics)?;
            } else {
                println!("Health Dashboard — Four Golden Signals ({})", rg);
                render_health_table(&metrics);
            }
        }
        azlin_cli::Commands::OsUpdate {
            vm_identifier,
            resource_group,
            timeout: _,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", vm_identifier));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &vm_identifier)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

            println!("Running OS updates on '{}'...", vm_identifier);
            let cmd = update_helpers::build_os_update_cmd().to_string();
            let (code, stdout, stderr) = ssh_exec(&ip, &user, &cmd)?;
            if code == 0 {
                let green = Style::new().green();
                println!(
                    "{}",
                    green.apply_to(format!("OS update completed on '{}'", vm_identifier))
                );
                if !stdout.trim().is_empty() {
                    println!("{}", stdout.trim());
                }
            } else {
                let red = Style::new().red();
                eprintln!(
                    "{}",
                    red.apply_to(format!("OS update failed on '{}'", vm_identifier))
                );
                let detail = if stderr.trim().is_empty() {
                    String::new()
                } else {
                    format!(": {}", azlin_core::sanitizer::sanitize(stderr.trim()))
                };
                anyhow::bail!("OS update failed on '{}'{}", vm_identifier, detail);
            }
        }
        azlin_cli::Commands::Delete {
            vm_name,
            resource_group,
            force,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            if !force {
                let confirmed = Confirm::new()
                    .with_prompt(format!("Delete VM '{}'? This cannot be undone.", vm_name))
                    .default(false)
                    .interact()?;
                if !confirmed {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("Deleting {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let msg = handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(format!("✓ {}", msg));
        }
        azlin_cli::Commands::Kill {
            vm_name,
            resource_group,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("Killing {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let _msg = handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(format!("✓ Killed {}", vm_name));
        }
        azlin_cli::Commands::Destroy {
            vm_name,
            resource_group,
            force,
            dry_run,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;

            if dry_run {
                println!("{}", handlers::format_destroy_dry_run(&vm_name, &rg));
                return Ok(());
            }

            if !force {
                let confirmed = Confirm::new()
                    .with_prompt(format!("Destroy VM '{}'? This cannot be undone.", vm_name))
                    .default(false)
                    .interact()?;
                if !confirmed {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("Destroying {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            handlers::handle_delete(&vm_manager, &rg, &vm_name)?;
            pb.finish_with_message(format!("✓ Destroyed {}", vm_name));
        }
        azlin_cli::Commands::Env { action } => match action {
            azlin_cli::EnvAction::Set {
                vm_identifier,
                env_var,
                resource_group,
                ip,
                ..
            } => {
                let (key, value) = match env_helpers::split_env_var(&env_var) {
                    Some(kv) => kv,
                    None => {
                        anyhow::bail!("Invalid format. Use KEY=VALUE");
                    }
                };
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let escaped = shell_escape(value);
                let cmd = env_helpers::build_env_set_cmd(key, &escaped);
                if cmd == "true" {
                    anyhow::bail!("Invalid environment variable key: {}", key);
                }
                target.exec_checked(&cmd)?;
                println!("Set {}={} on VM '{}'", key, value, vm_identifier);
            }
            azlin_cli::EnvAction::List {
                vm_identifier,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let output = target.exec_checked(env_helpers::env_list_cmd())?;
                let mut table = Table::new();
                table
                    .load_preset(UTF8_FULL)
                    .apply_modifier(UTF8_ROUND_CORNERS)
                    .set_header(vec!["Variable", "Value"]);
                for line in output.lines() {
                    if let Some((k, v)) = line.split_once('=') {
                        table.add_row(vec![k, v]);
                    }
                }
                println!("{table}");
            }
            azlin_cli::EnvAction::Delete {
                vm_identifier,
                key,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let cmd = env_helpers::build_env_delete_cmd(&key);
                target.exec_checked(&cmd)?;
                println!("Deleted '{}' from VM '{}'", key, vm_identifier);
            }
            azlin_cli::EnvAction::Export {
                vm_identifier,
                output_file,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let output = target.exec_checked(env_helpers::env_list_cmd())?;
                match output_file {
                    Some(path) => {
                        std::fs::write(&path, &output)?;
                        println!(
                            "Exported env vars from VM '{}' to '{}'",
                            vm_identifier, path
                        );
                    }
                    None => print!("{}", output),
                }
            }
            azlin_cli::EnvAction::Import {
                vm_identifier,
                env_file,
                resource_group,
                ip,
                ..
            } => {
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let content = std::fs::read_to_string(&env_file)?;
                for (key, value) in env_helpers::parse_env_file(&content) {
                    let escaped = shell_escape(&value);
                    let cmd = env_helpers::build_env_set_cmd(&key, &escaped);
                    if cmd == "true" {
                        eprintln!("Skipping invalid environment variable key: {}", key);
                        continue;
                    }
                    target.exec_checked(&cmd)?;
                }
                println!(
                    "Imported env vars from '{}' to VM '{}'",
                    env_file.display(),
                    vm_identifier
                );
            }
            azlin_cli::EnvAction::Clear {
                vm_identifier,
                force,
                resource_group,
                ip,
                ..
            } => {
                if !force {
                    let confirmed = Confirm::new()
                        .with_prompt(format!(
                            "Clear all custom env vars on VM '{}'? This cannot be undone.",
                            vm_identifier
                        ))
                        .default(false)
                        .interact()?;
                    if !confirmed {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }
                let target =
                    resolve_vm_ssh_target(&vm_identifier, ip.as_deref(), resource_group).await?;
                let cmd = env_helpers::env_clear_cmd();
                target.exec_checked(cmd)?;
                println!(
                    "Cleared all custom environment variables on VM '{}'",
                    vm_identifier
                );
            }
        },
        azlin_cli::Commands::Cost {
            resource_group,
            by_vm,
            from,
            to,
            estimate,
            ..
        } => {
            let auth = create_auth()?;
            let rg = resolve_resource_group(resource_group)?;
            let cost_timeout = azlin_core::AzlinConfig::load()
                .map(|c| c.az_cli_timeout)
                .unwrap_or(120);

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Fetching cost data...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            match azlin_azure::get_cost_summary(&auth, &rg, cost_timeout) {
                Ok(summary) => {
                    pb.finish_and_clear();
                    let fmt_str = match &cli.output {
                        azlin_cli::OutputFormat::Json => "json",
                        azlin_cli::OutputFormat::Csv => "csv",
                        azlin_cli::OutputFormat::Table => "table",
                    };
                    println!(
                        "{}",
                        handlers::format_cost_summary(
                            &summary, fmt_str, &from, &to, estimate, by_vm
                        )
                    );
                }
                Err(e) => {
                    pb.finish_and_clear();
                    eprintln!("⚠ Cost data unavailable: {e}");
                    eprintln!("  Run 'az consumption usage list' for cost data via Azure CLI.");
                }
            }
        }
        azlin_cli::Commands::Snapshot { action } => {
            let rg = match &action {
                azlin_cli::SnapshotAction::Create { resource_group, .. }
                | azlin_cli::SnapshotAction::List { resource_group, .. }
                | azlin_cli::SnapshotAction::Restore { resource_group, .. }
                | azlin_cli::SnapshotAction::Delete { resource_group, .. }
                | azlin_cli::SnapshotAction::Enable { resource_group, .. }
                | azlin_cli::SnapshotAction::Disable { resource_group, .. }
                | azlin_cli::SnapshotAction::Sync { resource_group, .. }
                | azlin_cli::SnapshotAction::Status { resource_group, .. } => {
                    resolve_resource_group(resource_group.clone())?
                }
            };

            match action {
                azlin_cli::SnapshotAction::Create { vm_name, .. } => {
                    let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
                    let snapshot_name = snapshot_helpers::build_snapshot_name(&vm_name, &ts);
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Creating snapshot {}...", snapshot_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "create",
                            "--resource-group",
                            &rg,
                            "--source-disk",
                            &format!("{}_OsDisk", vm_name),
                            "--name",
                            &snapshot_name,
                            "--output",
                            "json",
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        println!("Created snapshot '{}'", snapshot_name);
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to create snapshot: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::List { vm_name, .. } => {
                    let output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "list",
                            "--resource-group",
                            &rg,
                            "--output",
                            "json",
                        ])
                        .output()?;

                    if output.status.success() {
                        let snapshots: Vec<serde_json::Value> =
                            serde_json::from_slice(&output.stdout)
                                .context("Failed to parse snapshot list JSON")?;
                        let filtered = snapshot_helpers::filter_snapshots(&snapshots, &vm_name);

                        if filtered.is_empty() {
                            println!("No snapshots found for VM '{}'.", vm_name);
                        } else {
                            let mut table = Table::new();
                            table
                                .load_preset(UTF8_FULL)
                                .apply_modifier(UTF8_ROUND_CORNERS)
                                .set_header(vec![
                                    "Name",
                                    "Disk Size (GB)",
                                    "Time Created",
                                    "State",
                                ]);
                            for snap in &filtered {
                                let row = snapshot_helpers::snapshot_row(snap);
                                table.add_row(row);
                            }
                            println!("{table}");
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to list snapshots: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Restore {
                    vm_name,
                    snapshot_name,
                    force,
                    ..
                } => {
                    if !force {
                        let confirmed = Confirm::new()
                            .with_prompt(format!(
                                "Restore VM '{}' from snapshot '{}'? This will replace the current disk.",
                                vm_name, snapshot_name
                            ))
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Restoring {} from {}...", vm_name, snapshot_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let snap_output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "show",
                            "--resource-group",
                            &rg,
                            "--name",
                            &snapshot_name,
                            "--query",
                            "id",
                            "--output",
                            "tsv",
                        ])
                        .output()?;

                    if !snap_output.status.success() {
                        pb.finish_and_clear();
                        anyhow::bail!("Snapshot '{}' not found.", snapshot_name);
                    }

                    let snap_id = String::from_utf8_lossy(&snap_output.stdout)
                        .trim()
                        .to_string();
                    let new_disk = format!("{}_OsDisk_restored", vm_name);

                    let disk_output = std::process::Command::new("az")
                        .args([
                            "disk",
                            "create",
                            "--resource-group",
                            &rg,
                            "--name",
                            &new_disk,
                            "--source",
                            &snap_id,
                            "--output",
                            "json",
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if disk_output.status.success() {
                        println!(
                            "Restored disk '{}' from snapshot '{}'",
                            new_disk, snapshot_name
                        );
                        // Step 3: Deallocate the VM so we can swap the OS disk
                        let pb2 = indicatif::ProgressBar::new_spinner();
                        pb2.set_message(format!("Deallocating VM '{}'...", vm_name));
                        pb2.enable_steady_tick(std::time::Duration::from_millis(100));
                        let dealloc = std::process::Command::new("az")
                            .args([
                                "vm",
                                "deallocate",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                            ])
                            .output()?;
                        pb2.finish_and_clear();
                        if !dealloc.status.success() {
                            let stderr = String::from_utf8_lossy(&dealloc.stderr);
                            anyhow::bail!(
                                "Failed to deallocate VM: {}\n\
                                 Manual swap: az vm update --resource-group {} --name {} --os-disk {}",
                                azlin_core::sanitizer::sanitize(stderr.trim()),
                                rg, vm_name, new_disk
                            );
                        }

                        // Step 4: Swap the OS disk
                        let pb3 = indicatif::ProgressBar::new_spinner();
                        pb3.set_message("Swapping OS disk...");
                        pb3.enable_steady_tick(std::time::Duration::from_millis(100));
                        let swap = std::process::Command::new("az")
                            .args([
                                "vm",
                                "update",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                                "--os-disk",
                                &new_disk,
                                "--output",
                                "json",
                            ])
                            .output()?;
                        pb3.finish_and_clear();
                        if !swap.status.success() {
                            let stderr = String::from_utf8_lossy(&swap.stderr);
                            anyhow::bail!(
                                "Failed to swap OS disk: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }

                        // Step 5: Start the VM back up
                        let pb4 = indicatif::ProgressBar::new_spinner();
                        pb4.set_message(format!("Starting VM '{}'...", vm_name));
                        pb4.enable_steady_tick(std::time::Duration::from_millis(100));
                        let start = std::process::Command::new("az")
                            .args(["vm", "start", "--resource-group", &rg, "--name", &vm_name])
                            .output()?;
                        pb4.finish_and_clear();
                        if start.status.success() {
                            println!(
                                "Restored VM '{}' from snapshot '{}' and restarted.",
                                vm_name, snapshot_name
                            );
                        } else {
                            let stderr = String::from_utf8_lossy(&start.stderr);
                            eprintln!(
                                "VM restored but failed to restart: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&disk_output.stderr);
                        anyhow::bail!(
                            "Failed to restore: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Delete {
                    snapshot_name,
                    force,
                    ..
                } => {
                    if !force {
                        let confirmed = Confirm::new()
                            .with_prompt(format!(
                                "Delete snapshot '{}'? This cannot be undone.",
                                snapshot_name
                            ))
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Deleting snapshot {}...", snapshot_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args([
                            "snapshot",
                            "delete",
                            "--resource-group",
                            &rg,
                            "--name",
                            &snapshot_name,
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        println!("Deleted snapshot '{}'", snapshot_name);
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to delete snapshot: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::SnapshotAction::Enable {
                    vm_name,
                    every,
                    keep,
                    ..
                } => {
                    if let Err(e) = name_validation::validate_name(&vm_name) {
                        anyhow::bail!("Invalid VM name: {}", e);
                    }
                    let schedule = snapshot_helpers::SnapshotSchedule {
                        vm_name: vm_name.clone(),
                        resource_group: rg.clone(),
                        every_hours: every,
                        keep_count: keep,
                        enabled: true,
                        created: chrono::Utc::now().to_rfc3339(),
                    };
                    snapshot_helpers::save_schedule(&schedule)?;
                    println!(
                        "Scheduled snapshots enabled for VM '{}': every {}h, keep {}",
                        vm_name, every, keep
                    );
                }
                azlin_cli::SnapshotAction::Disable { vm_name, .. } => {
                    if let Err(e) = name_validation::validate_name(&vm_name) {
                        anyhow::bail!("Invalid VM name: {}", e);
                    }
                    let path = snapshot_helpers::schedule_path(&vm_name);
                    if let Some(mut sched) = snapshot_helpers::load_schedule(&vm_name) {
                        sched.enabled = false;
                        snapshot_helpers::save_schedule(&sched)?;
                        println!("Scheduled snapshots disabled for VM '{}'", vm_name);
                    } else if path.exists() {
                        std::fs::remove_file(&path)?;
                        println!("Scheduled snapshots disabled for VM '{}'", vm_name);
                    } else {
                        println!("No schedule configured for VM '{}'", vm_name);
                    }
                }
                azlin_cli::SnapshotAction::Sync { vm, .. } => {
                    let schedules = match &vm {
                        Some(name) => snapshot_helpers::load_schedule(name)
                            .into_iter()
                            .collect::<Vec<_>>(),
                        None => snapshot_helpers::load_all_schedules(),
                    };
                    let enabled: Vec<_> = schedules.iter().filter(|s| s.enabled).collect();
                    if enabled.is_empty() {
                        println!("No enabled snapshot schedules found.");
                    } else {
                        for sched in &enabled {
                            // List existing snapshots for this VM to find the most recent
                            let list_output = std::process::Command::new("az")
                                .args([
                                    "snapshot",
                                    "list",
                                    "--resource-group",
                                    &sched.resource_group,
                                    "--output",
                                    "json",
                                ])
                                .output()?;

                            let mut needs_snapshot = true;
                            if list_output.status.success() {
                                let all_snaps: Vec<serde_json::Value> =
                                    serde_json::from_slice(&list_output.stdout).unwrap_or_default();
                                let filtered =
                                    snapshot_helpers::filter_snapshots(&all_snaps, &sched.vm_name);
                                // Find the most recent snapshot by timeCreated
                                let newest = filtered
                                    .iter()
                                    .filter_map(|s| {
                                        s["timeCreated"].as_str().and_then(|t| {
                                            chrono::DateTime::parse_from_rfc3339(t).ok()
                                        })
                                    })
                                    .max();
                                if let Some(latest) = newest {
                                    let age = chrono::Utc::now()
                                        .signed_duration_since(latest.with_timezone(&chrono::Utc));
                                    if age.num_hours() < sched.every_hours as i64 {
                                        needs_snapshot = false;
                                        println!(
                                            "VM '{}': latest snapshot is {}h old (interval {}h), skipping",
                                            sched.vm_name,
                                            age.num_hours(),
                                            sched.every_hours
                                        );
                                    }
                                }
                            }

                            if needs_snapshot {
                                let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
                                let snap_name =
                                    snapshot_helpers::build_snapshot_name(&sched.vm_name, &ts);

                                let pb = indicatif::ProgressBar::new_spinner();
                                pb.set_message(format!("Creating snapshot {}...", snap_name));
                                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                                let disk_id_output = std::process::Command::new("az")
                                    .args([
                                        "vm",
                                        "show",
                                        "--resource-group",
                                        &sched.resource_group,
                                        "--name",
                                        &sched.vm_name,
                                        "--query",
                                        "storageProfile.osDisk.managedDisk.id",
                                        "--output",
                                        "tsv",
                                    ])
                                    .output()?;

                                if !disk_id_output.status.success() {
                                    pb.finish_and_clear();
                                    eprintln!(
                                        "Failed to get disk ID for VM '{}': {}",
                                        sched.vm_name,
                                        String::from_utf8_lossy(&disk_id_output.stderr).trim()
                                    );
                                    continue;
                                }

                                let disk_id = String::from_utf8_lossy(&disk_id_output.stdout)
                                    .trim()
                                    .to_string();

                                let create_output = std::process::Command::new("az")
                                    .args([
                                        "snapshot",
                                        "create",
                                        "--resource-group",
                                        &sched.resource_group,
                                        "--name",
                                        &snap_name,
                                        "--source",
                                        &disk_id,
                                        "--output",
                                        "json",
                                    ])
                                    .output()?;

                                pb.finish_and_clear();
                                if create_output.status.success() {
                                    println!(
                                        "Created snapshot '{}' for VM '{}'",
                                        snap_name, sched.vm_name
                                    );
                                } else {
                                    eprintln!(
                                        "Failed to create snapshot for VM '{}': {}",
                                        sched.vm_name,
                                        String::from_utf8_lossy(&create_output.stderr).trim()
                                    );
                                }
                            }
                        }
                        match &vm {
                            Some(name) => println!("Snapshot sync completed for VM '{}'", name),
                            None => println!("Snapshot sync completed for all VMs"),
                        }
                    }
                }
                azlin_cli::SnapshotAction::Status { vm_name, .. } => {
                    match snapshot_helpers::load_schedule(&vm_name) {
                        Some(sched) => {
                            let info = handlers::SnapshotScheduleInfo {
                                vm_name: sched.vm_name.clone(),
                                resource_group: sched.resource_group.clone(),
                                every_hours: sched.every_hours,
                                keep_count: sched.keep_count,
                                enabled: sched.enabled,
                                created: sched.created.clone(),
                            };
                            println!("{}", handlers::format_snapshot_status(&info));
                        }
                        None => {
                            println!("{}", handlers::format_snapshot_no_schedule(&vm_name));
                        }
                    }
                }
            }
        }
        azlin_cli::Commands::Storage { action } => match action {
            azlin_cli::StorageAction::Create {
                name,
                size,
                tier,
                resource_group,
                region,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let loc = region.unwrap_or_else(|| "westus2".to_string());

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Creating storage account {}...", name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let sku = storage_helpers::storage_sku_from_tier(&tier);

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "create",
                        "--name",
                        &name,
                        "--resource-group",
                        &rg,
                        "--location",
                        &loc,
                        "--sku",
                        sku,
                        "--kind",
                        "FileStorage",
                        "--enable-nfs-v3",
                        "true",
                        "--output",
                        "json",
                    ])
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    println!("Created storage account '{}' ({} GB, {})", name, size, tier);
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to create storage account: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            azlin_cli::StorageAction::List { resource_group } => {
                let rg = resolve_resource_group(resource_group)?;

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "list",
                        "--resource-group",
                        &rg,
                        "--output",
                        "json",
                    ])
                    .output()?;

                if output.status.success() {
                    let accounts: Vec<serde_json::Value> =
                        serde_json::from_slice(&output.stdout)
                            .context("Failed to parse storage account list JSON")?;

                    if accounts.is_empty() {
                        println!("No storage accounts found.");
                    } else {
                        let mut table = Table::new();
                        table
                            .load_preset(UTF8_FULL)
                            .apply_modifier(UTF8_ROUND_CORNERS)
                            .set_header(vec!["Name", "Location", "Kind", "SKU", "State"]);
                        for acct in &accounts {
                            table.add_row(storage_helpers::storage_account_row(acct));
                        }
                        println!("{table}");
                    }
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to list storage accounts: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            azlin_cli::StorageAction::Status {
                name,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "show",
                        "--name",
                        &name,
                        "--resource-group",
                        &rg,
                        "--output",
                        "json",
                    ])
                    .output()?;

                if output.status.success() {
                    let acct: serde_json::Value = serde_json::from_slice(&output.stdout)
                        .context("Failed to parse storage account JSON")?;
                    let key_style = Style::new().cyan().bold();
                    for (key, value) in handlers::format_storage_status(&acct) {
                        println!("{}: {}", key_style.apply_to(&key), value);
                    }
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to show storage account: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            azlin_cli::StorageAction::Mount {
                storage_name,
                vm,
                mount_point,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Looking up VM {}...", vm));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm_info = vm_manager.get_vm(&rg, &vm)?;
                pb.finish_and_clear();

                let ip = vm_info
                    .public_ip
                    .or(vm_info.private_ip)
                    .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

                // Validate storage_name: Azure storage accounts allow only [a-zA-Z0-9-]
                if !storage_name
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '-')
                {
                    anyhow::bail!("Invalid storage name: contains disallowed characters");
                }

                let mp = mount_point.unwrap_or_else(|| format!("/mnt/{}", storage_name));

                // Validate mount path to prevent command injection
                mount_helpers::validate_mount_path(&mp)
                    .map_err(|e| anyhow::anyhow!("Invalid mount path: {}", e))?;

                let mount_cmd = handlers::build_nfs_mount_command(&storage_name, &mp);
                let status = std::process::Command::new("ssh")
                    .args([
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        &format!("{}@{}", user, ip),
                        &mount_cmd,
                    ])
                    .status()?;

                if status.success() {
                    println!("Mounted '{}' on VM '{}' at {}", storage_name, vm, mp);
                } else {
                    anyhow::bail!("Failed to mount storage on VM.");
                }
            }
            azlin_cli::StorageAction::Unmount { vm, resource_group } => {
                let rg = resolve_resource_group(resource_group)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Looking up VM {}...", vm));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm_info = vm_manager.get_vm(&rg, &vm)?;
                pb.finish_and_clear();

                let ip = vm_info
                    .public_ip
                    .or(vm_info.private_ip)
                    .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

                let status = std::process::Command::new("ssh")
                    .args([
                        "-o",
                        "StrictHostKeyChecking=accept-new",
                        &format!("{}@{}", user, ip),
                        "sudo umount /mnt/* 2>/dev/null; echo done",
                    ])
                    .status()?;

                if status.success() {
                    println!("Unmounted NFS storage from VM '{}'", vm);
                } else {
                    anyhow::bail!("Failed to unmount storage from VM.");
                }
            }
            azlin_cli::StorageAction::Delete {
                name,
                resource_group,
                force,
            } => {
                let rg = resolve_resource_group(resource_group)?;

                if !force {
                    let confirmed = Confirm::new()
                        .with_prompt(format!(
                            "Delete storage account '{}'? This cannot be undone.",
                            name
                        ))
                        .default(false)
                        .interact()?;
                    if !confirmed {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Deleting storage account {}...", name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "delete",
                        "--name",
                        &name,
                        "--resource-group",
                        &rg,
                        "--yes",
                    ])
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    println!("Deleted storage account '{}'", name);
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to delete storage account: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
            azlin_cli::StorageAction::MountFile {
                account,
                share,
                mount_point,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let mount_dir = mount_point
                    .unwrap_or_else(|| std::path::PathBuf::from(format!("/mnt/{}", account)));

                // Get storage account key
                let key_output = std::process::Command::new("az")
                    .args([
                        "storage",
                        "account",
                        "keys",
                        "list",
                        "--account-name",
                        &account,
                        "--resource-group",
                        &rg,
                        "--query",
                        "[0].value",
                        "-o",
                        "tsv",
                    ])
                    .output()?;

                if !key_output.status.success() {
                    let stderr = String::from_utf8_lossy(&key_output.stderr);
                    anyhow::bail!(
                        "Failed to get storage account key: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }

                let key = String::from_utf8_lossy(&key_output.stdout)
                    .trim()
                    .to_string();
                let unc = handlers::build_azure_files_unc(&account, &share);
                let mount_str = mount_dir.display().to_string();

                // Create mount point (best-effort; mount will fail if this fails)
                let mkdir_status = std::process::Command::new("sudo")
                    .args(["mkdir", "-p", &mount_str])
                    .status()?;
                if !mkdir_status.success() {
                    eprintln!("Warning: failed to create mount point {}", mount_str);
                }

                // Write credentials to a temp file instead of passing on CLI
                // to avoid exposing the storage key in process listings.
                use std::os::unix::fs::PermissionsExt;
                let creds_dir = home_dir()?.join(".azlin");
                std::fs::create_dir_all(&creds_dir)?;
                let creds_path = creds_dir.join(format!(".mount_creds_{}", account));
                std::fs::write(
                    &creds_path,
                    format!("username={}\npassword={}\n", account, key),
                )?;
                std::fs::set_permissions(&creds_path, std::fs::Permissions::from_mode(0o600))?;

                let status = std::process::Command::new("sudo")
                    .args([
                        "mount",
                        "-t",
                        "cifs",
                        &unc,
                        &mount_str,
                        "-o",
                        &handlers::build_cifs_mount_options(&creds_path.display().to_string()),
                    ])
                    .status()?;

                // Clean up credentials file after mount — warn if cleanup fails
                // since the file contains a storage account key in plaintext
                if let Err(e) = std::fs::remove_file(&creds_path) {
                    eprintln!(
                        "⚠ Warning: could not remove credentials file {}: {e}",
                        creds_path.display()
                    );
                    eprintln!("  Please remove it manually (contains storage account key).");
                }

                if status.success() {
                    println!("Mounted '{}' at {}", share, mount_str);
                } else {
                    anyhow::bail!("Failed to mount Azure Files share.");
                }
            }
            azlin_cli::StorageAction::UnmountFile { mount_point } => {
                let mount_str = mount_point
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "/mnt".to_string());

                let status = std::process::Command::new("sudo")
                    .args(["umount", &mount_str])
                    .status()?;

                if status.success() {
                    println!("Unmounted '{}'", mount_str);
                } else {
                    anyhow::bail!("Failed to unmount '{}'.", mount_str);
                }
            }
        },
        azlin_cli::Commands::Keys { action } => match action {
            azlin_cli::KeysAction::List { .. } => {
                let ssh_dir = home_dir()?.join(".ssh");

                if !ssh_dir.exists() {
                    println!("No SSH directory found at {}", ssh_dir.display());
                    return Ok(());
                }

                let entries = std::fs::read_dir(&ssh_dir)?;
                let mut rows: Vec<Vec<String>> = Vec::new();

                for entry in entries {
                    let entry = entry?;
                    let name = entry.file_name().to_string_lossy().to_string();

                    let is_key = name.ends_with(".pub")
                        || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name.as_str())
                        || (!name.starts_with('.')
                            && !name.ends_with(".pub")
                            && std::path::Path::new(&ssh_dir)
                                .join(format!("{}.pub", name))
                                .exists());

                    if !is_key {
                        continue;
                    }

                    let meta = entry.metadata()?;
                    let modified = meta
                        .modified()
                        .map(|t| {
                            let dt: chrono::DateTime<chrono::Utc> = t.into();
                            dt.format("%Y-%m-%d %H:%M").to_string()
                        })
                        .unwrap_or_else(|_| "-".to_string());

                    let key_type = key_helpers::detect_key_type(&name);

                    rows.push(vec![
                        name,
                        key_type.to_string(),
                        meta.len().to_string(),
                        modified,
                    ]);
                }

                if rows.is_empty() {
                    println!("No SSH keys found in {}", ssh_dir.display());
                } else {
                    azlin_cli::table::render_rows(
                        &["Key File", "Type", "Size (bytes)", "Modified"],
                        &rows,
                        &cli.output,
                    );
                }
            }
            azlin_cli::KeysAction::Rotate {
                resource_group,
                all_vms,
                no_backup,
                vm_prefix,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let ssh_dir = home_dir()?.join(".ssh");

                if !no_backup {
                    let backup_dir = ssh_dir.join(format!(
                        "backup_{}",
                        chrono::Utc::now().format("%Y%m%d_%H%M%S")
                    ));
                    std::fs::create_dir_all(&backup_dir)?;
                    for entry in std::fs::read_dir(&ssh_dir)? {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.starts_with("id_") {
                            std::fs::copy(entry.path(), backup_dir.join(&name))?;
                        }
                    }
                    println!("Backed up existing keys to {}", backup_dir.display());
                }

                let new_key = ssh_dir.join("id_ed25519_azlin");
                if new_key.exists() {
                    std::fs::remove_file(&new_key)?;
                    let pub_key = ssh_dir.join("id_ed25519_azlin.pub");
                    if pub_key.exists() {
                        std::fs::remove_file(&pub_key)?;
                    }
                }

                let keygen = std::process::Command::new("ssh-keygen")
                    .args([
                        "-t",
                        "ed25519",
                        "-f",
                        &new_key.to_string_lossy(),
                        "-N",
                        "",
                        "-C",
                        "azlin-rotated",
                    ])
                    .output()?;

                if !keygen.status.success() {
                    anyhow::bail!("Failed to generate new SSH key.");
                }
                println!("Generated new ed25519 key pair");

                let prefix_filter = if all_vms { "" } else { &vm_prefix };
                let query = format!("[?starts_with(name, '{}')]", prefix_filter);
                let mut az_args = vec!["vm", "list", "--resource-group", &rg, "--output", "json"];
                if !prefix_filter.is_empty() {
                    az_args.extend(["--query", query.as_str()]);
                }

                let output = std::process::Command::new("az").args(&az_args).output()?;

                if output.status.success() {
                    let vms: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)
                        .context("Failed to parse VM list JSON")?;
                    let pub_key_content =
                        std::fs::read_to_string(ssh_dir.join("id_ed25519_azlin.pub"))?;
                    for vm_val in &vms {
                        let name = vm_val["name"].as_str().unwrap_or("");
                        let result = std::process::Command::new("az")
                            .args([
                                "vm",
                                "user",
                                "update",
                                "--resource-group",
                                &rg,
                                "--name",
                                name,
                                "--username",
                                DEFAULT_ADMIN_USERNAME,
                                "--ssh-key-value",
                                pub_key_content.trim(),
                            ])
                            .output();
                        match result {
                            Ok(o) if o.status.success() => {
                                println!("  Deployed key to VM '{}'", name);
                            }
                            _ => {
                                eprintln!("  Failed to deploy key to VM '{}'", name);
                            }
                        }
                    }
                }

                println!("Key rotation complete.");
            }
            azlin_cli::KeysAction::Export { output } => {
                let ssh_dir = home_dir()?.join(".ssh");

                let pub_key = ["id_ed25519_azlin.pub", "id_ed25519.pub", "id_rsa.pub"]
                    .iter()
                    .map(|f| ssh_dir.join(f))
                    .find(|p| p.exists());

                match pub_key {
                    Some(src) => {
                        std::fs::copy(&src, &output)?;
                        let fname = src
                            .file_name()
                            .map(|f| f.to_string_lossy().into_owned())
                            .unwrap_or_else(|| src.display().to_string());
                        println!("Exported {} to {}", fname, output.display());
                    }
                    None => {
                        anyhow::bail!("No SSH public key found in {}", ssh_dir.display());
                    }
                }
            }
            azlin_cli::KeysAction::Backup { destination } => {
                let ssh_dir = home_dir()?.join(".ssh");

                let backup_dir = destination.unwrap_or_else(|| {
                    ssh_dir.join(format!(
                        "backup_{}",
                        chrono::Utc::now().format("%Y%m%d_%H%M%S")
                    ))
                });

                std::fs::create_dir_all(&backup_dir)?;
                let mut count = 0u32;
                for entry in std::fs::read_dir(&ssh_dir)? {
                    let entry = entry?;
                    let name = entry.file_name().to_string_lossy().to_string();
                    if name.starts_with("id_") {
                        std::fs::copy(entry.path(), backup_dir.join(&name))?;
                        count += 1;
                    }
                }
                println!("Backed up {} key files to {}", count, backup_dir.display());
            }
        },
        azlin_cli::Commands::Auth { action } => {
            let azlin_dir = home_dir()?.join(".azlin");

            match action {
                azlin_cli::AuthAction::List => {
                    let profiles_dir = azlin_dir.join("profiles");
                    if !profiles_dir.exists() {
                        println!("No authentication profiles found.");
                        return Ok(());
                    }

                    let entries = std::fs::read_dir(&profiles_dir)?;
                    let mut rows: Vec<Vec<String>> = Vec::new();

                    for entry in entries {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.ends_with(".json") {
                            let content = std::fs::read_to_string(entry.path())?;
                            let profile: serde_json::Value = serde_json::from_str(&content)
                                .context(format!("Failed to parse auth profile '{}'", name))?;
                            let profile_name = name.trim_end_matches(".json");
                            rows.push(vec![
                                profile_name.to_string(),
                                profile["tenant_id"].as_str().unwrap_or("-").to_string(),
                                profile["client_id"].as_str().unwrap_or("-").to_string(),
                            ]);
                        }
                    }

                    if rows.is_empty() {
                        println!("No authentication profiles found.");
                    } else {
                        azlin_cli::table::render_rows(
                            &["Profile", "Tenant ID", "Client ID"],
                            &rows,
                            &cli.output,
                        );
                    }
                }
                azlin_cli::AuthAction::Show { profile } => {
                    if let Err(e) = name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        anyhow::bail!("Profile '{}' not found.", profile);
                    }

                    let content = std::fs::read_to_string(&profile_path)?;
                    let data: serde_json::Value = serde_json::from_str(&content)
                        .context(format!("Failed to parse auth profile '{}'", profile))?;
                    let key_style = Style::new().cyan().bold();

                    println!("{}: {}", key_style.apply_to("Profile"), profile);
                    if let Some(obj) = data.as_object() {
                        for (k, v) in obj {
                            let display = auth_helpers::mask_profile_value(k, v);
                            println!("{}: {}", key_style.apply_to(k), display);
                        }
                    }
                }
                azlin_cli::AuthAction::Test { profile, .. } => {
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!(
                        "Testing authentication for profile '{}'...",
                        profile
                    ));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args(["account", "show", "--output", "json"])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        let acct: serde_json::Value = serde_json::from_slice(&output.stdout)
                            .context("Failed to parse 'az account show' JSON")?;
                        let key_style = Style::new().cyan().bold();
                        let (subscription, tenant, user) =
                            auth_test_helpers::extract_account_info(&acct);
                        println!(
                            "{}",
                            Style::new()
                                .green()
                                .bold()
                                .apply_to("Authentication successful!")
                        );
                        println!("{}: {}", key_style.apply_to("Subscription"), subscription);
                        println!("{}: {}", key_style.apply_to("Tenant"), tenant);
                        println!("{}: {}", key_style.apply_to("User"), user);
                    } else {
                        anyhow::bail!(
                            "Authentication test failed. Run 'az login' to authenticate."
                        );
                    }
                }
                azlin_cli::AuthAction::Setup {
                    profile,
                    tenant_id,
                    client_id,
                    subscription_id,
                    ..
                } => {
                    use dialoguer::Input;

                    let tenant = match tenant_id {
                        Some(t) => t,
                        None => Input::new()
                            .with_prompt("Azure Tenant ID")
                            .interact_text()?,
                    };
                    let client = match client_id {
                        Some(c) => c,
                        None => Input::new()
                            .with_prompt("Azure Client ID")
                            .interact_text()?,
                    };
                    let subscription = match subscription_id {
                        Some(s) => s,
                        None => Input::new()
                            .with_prompt("Azure Subscription ID")
                            .interact_text()?,
                    };

                    let profiles_dir = azlin_dir.join("profiles");
                    std::fs::create_dir_all(&profiles_dir)?;

                    if let Err(e) = name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }

                    let profile_data = serde_json::json!({
                        "tenant_id": tenant,
                        "client_id": client,
                        "subscription_id": subscription,
                    });

                    let profile_path = profiles_dir.join(format!("{}.json", profile));
                    std::fs::write(&profile_path, serde_json::to_string_pretty(&profile_data)?)?;
                    println!("Saved profile '{}' to {}", profile, profile_path.display());
                }
                azlin_cli::AuthAction::Remove { profile, yes } => {
                    if let Err(e) = name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        anyhow::bail!("Profile '{}' not found.", profile);
                    }

                    if !yes {
                        let confirmed = Confirm::new()
                            .with_prompt(format!("Remove profile '{}'?", profile))
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    std::fs::remove_file(&profile_path)?;
                    println!("Removed profile '{}'", profile);
                }
            }
        }
        // ── NLP Commands ──────────────────────────────────────────────
        azlin_cli::Commands::Ask {
            query,
            resource_group,
            config: _,
            dry_run,
            auth_profile: _,
            ..
        } => {
            let query_text = query.ok_or_else(|| anyhow::anyhow!("No query provided."))?;

            if dry_run {
                println!("Would query Claude API with: {}", query_text);
                return Ok(());
            }

            let client = azlin_ai::AnthropicClient::new()?;
            let rg = match resource_group {
                Some(rg) => rg,
                None => {
                    let config =
                        azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
                    config.default_resource_group.ok_or_else(|| {
                        anyhow::anyhow!(
                            "No resource group specified. Use --resource-group or set in config."
                        )
                    })?
                }
            };

            let context = format!("Resource group: {}", rg);
            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Querying Claude...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let answer = client.ask(&query_text, &context).await?;
            pb.finish_and_clear();
            println!("{}", answer);
        }
        azlin_cli::Commands::Do {
            request,
            dry_run,
            yes,
            verbose,
            ..
        } => {
            let client = azlin_ai::AnthropicClient::new()?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Generating commands...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let commands = client.execute(&request).await?;
            pb.finish_and_clear();

            if commands.is_empty() {
                println!("No commands generated.");
                return Ok(());
            }

            println!("Generated commands:");
            for (i, cmd) in commands.iter().enumerate() {
                println!("  {}. {}", i + 1, cmd);
            }

            if dry_run {
                return Ok(());
            }

            if !yes {
                let confirmed = Confirm::new()
                    .with_prompt("Execute these commands?")
                    .default(false)
                    .interact()?;
                if !confirmed {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            for cmd in &commands {
                let cmd_str = cmd.trim();
                if cmd_str.is_empty() {
                    continue;
                }
                // Validate command starts with allowed prefix
                if !cmd_str.starts_with("az ") {
                    eprintln!("Skipping non-Azure command: {}", cmd_str);
                    continue;
                }
                // Use shlex for proper argument parsing
                let parts = match shlex::split(cmd_str) {
                    Some(p) if !p.is_empty() => p,
                    _ => {
                        eprintln!("Failed to parse command: {}", cmd_str);
                        continue;
                    }
                };
                if verbose {
                    eprintln!("[verbose] Executing: {}", cmd_str);
                }
                println!("$ {}", cmd_str);
                let output = std::process::Command::new(&parts[0])
                    .args(&parts[1..])
                    .output()?;
                let stdout = String::from_utf8_lossy(&output.stdout);
                let stderr = String::from_utf8_lossy(&output.stderr);
                if !stdout.is_empty() {
                    print!("{}", stdout);
                }
                if verbose && !stderr.is_empty() {
                    eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
                }
                if !output.status.success() {
                    eprintln!("Command failed with exit code: {:?}", output.status.code());
                    if !verbose && !stderr.is_empty() {
                        eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
                    }
                }
            }
        }
        azlin_cli::Commands::Doit { action } => {
            match action {
                azlin_cli::DoitAction::Deploy {
                    request, dry_run, ..
                } => {
                    let client = azlin_ai::AnthropicClient::new()?;

                    let system_context = "You are azlin, an Azure VM fleet management tool. \
                        Generate a list of azlin CLI commands to accomplish the user's request.\n\
                        Format: one command per line, each an 'az' CLI command.\n\
                        Available operations: az vm list, az vm start, az vm stop, az vm create, \
                        az vm delete, az group create, az network nsg create, etc.";

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message("Generating deployment plan...");
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));
                    let commands = client.ask(&request, system_context).await?;
                    pb.finish_and_clear();

                    println!("Plan:\n{}\n", commands);

                    if dry_run {
                        return Ok(());
                    }

                    let confirmed = Confirm::new()
                        .with_prompt("Execute this plan?")
                        .default(false)
                        .interact()?;
                    if !confirmed {
                        println!("Cancelled.");
                        return Ok(());
                    }

                    for line in commands.lines() {
                        let trimmed = line.trim();
                        if trimmed.is_empty() || !trimmed.starts_with("az ") {
                            continue;
                        }
                        let parts = match shlex::split(trimmed) {
                            Some(p) if !p.is_empty() => p,
                            _ => {
                                eprintln!("Failed to parse command: {}", trimmed);
                                continue;
                            }
                        };
                        println!("→ {}", trimmed);
                        let status = std::process::Command::new(&parts[0])
                            .args(&parts[1..])
                            .status()?;
                        if !status.success() {
                            eprintln!("Command failed with exit code: {:?}", status.code());
                        }
                    }
                }
                azlin_cli::DoitAction::Status { session } => {
                    // Check for doit-tagged VMs in the default RG to show deployment status
                    let rg = resolve_resource_group(None)?;
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vms = vm_manager.list_vms(&rg)?;
                    let doit_vms: Vec<_> = vms
                        .iter()
                        .filter(|vm| vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit"))
                        .collect();
                    if doit_vms.is_empty() {
                        let session_id = session.unwrap_or_else(|| "latest".to_string());
                        println!(
                            "No active doit deployments for session '{}' in '{}'.",
                            session_id, rg
                        );
                    } else {
                        println!("Doit deployments in '{}':", rg);
                        for vm in &doit_vms {
                            println!("  {} — {} — {}", vm.name, vm.power_state, vm.vm_size);
                        }
                    }
                }
                azlin_cli::DoitAction::List { username } => {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let rg = resolve_resource_group(None)?;
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message("Listing doit-created resources...");
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));
                    let vms = vm_manager.list_vms(&rg)?;
                    pb.finish_and_clear();
                    let filtered: Vec<_> = vms
                        .iter()
                        .filter(|vm| {
                            let has_tag =
                                vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
                            let user_match = username
                                .as_ref()
                                .is_none_or(|u| vm.admin_username.as_deref() == Some(u.as_str()));
                            has_tag && user_match
                        })
                        .collect();
                    if filtered.is_empty() {
                        println!("No doit-created resources found.");
                    } else {
                        for vm in &filtered {
                            println!("  {} ({})", vm.name, vm.power_state);
                        }
                    }
                }
                azlin_cli::DoitAction::Show { resource_id } => {
                    let output = std::process::Command::new("az")
                        .args(["resource", "show", "--ids", &resource_id, "-o", "json"])
                        .output()?;
                    if output.status.success() {
                        print!("{}", String::from_utf8_lossy(&output.stdout));
                    } else {
                        eprintln!(
                            "Failed to show resource: {}",
                            azlin_core::sanitizer::sanitize(&String::from_utf8_lossy(
                                &output.stderr
                            ))
                        );
                    }
                }
                azlin_cli::DoitAction::Cleanup {
                    force,
                    dry_run,
                    username,
                } => {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let rg = resolve_resource_group(None)?;

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message("Finding doit-created resources...");
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));
                    let vms = vm_manager.list_vms(&rg)?;
                    pb.finish_and_clear();

                    let to_delete: Vec<_> = vms
                        .iter()
                        .filter(|vm| {
                            let has_tag =
                                vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
                            let user_match = username
                                .as_ref()
                                .is_none_or(|u| vm.admin_username.as_deref() == Some(u.as_str()));
                            has_tag && user_match
                        })
                        .collect();

                    if to_delete.is_empty() {
                        println!("No doit-created resources to clean up.");
                        return Ok(());
                    }

                    println!("Resources to delete:");
                    for vm in &to_delete {
                        println!("  {} ({})", vm.name, vm.power_state);
                    }

                    if dry_run {
                        return Ok(());
                    }

                    if !force {
                        let confirmed = Confirm::new()
                            .with_prompt("Delete these resources?")
                            .default(false)
                            .interact()?;
                        if !confirmed {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }

                    for vm in &to_delete {
                        println!("Deleting '{}'...", vm.name);
                        vm_manager.delete_vm(&rg, &vm.name)?;
                    }
                    println!("Cleanup complete.");
                }
                azlin_cli::DoitAction::Examples => {
                    println!("Example doit requests:");
                    println!("  azlin doit deploy \"Create a 2-VM cluster with Ubuntu 24.04\"");
                    println!("  azlin doit deploy \"Set up a dev VM with 4 cores and 16GB RAM\"");
                    println!("  azlin doit deploy \"Scale my fleet to 5 VMs in eastus2\"");
                    println!("  azlin doit deploy --dry-run \"Delete all stopped VMs\"");
                }
            }
        }

        // ── VM Lifecycle (New/Vm/Create aliases) ─────────────────────
        azlin_cli::Commands::New {
            repo,
            vm_size,
            region,
            resource_group,
            name,
            pool,
            no_auto_connect,
            template,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let vm_count = pool.unwrap_or(1);
            // Use config defaults instead of hardcoded values
            let config_defaults = azlin_core::AzlinConfig::load().unwrap_or_default();
            let user_specified_size = vm_size.is_some();
            let user_specified_region = region.is_some();
            let size = vm_size.unwrap_or_else(|| config_defaults.default_vm_size.clone());
            let loc = region.unwrap_or_else(|| config_defaults.default_region.clone());
            let admin_user = DEFAULT_ADMIN_USERNAME.to_string();
            let ssh_key_path = dirs::home_dir()
                .unwrap_or_default()
                .join(".ssh")
                .join("id_rsa.pub");

            // Load template defaults if specified
            let (tmpl_size, tmpl_region) = if let Some(ref tmpl_name) = template {
                if let Err(e) = name_validation::validate_name(tmpl_name) {
                    anyhow::bail!("Invalid template name: {}", e);
                }
                let templates_dir = dirs::home_dir()
                    .unwrap_or_default()
                    .join(".config")
                    .join("azlin")
                    .join("templates");
                let tmpl_path = templates_dir.join(format!("{}.toml", tmpl_name));
                if tmpl_path.exists() {
                    let content = std::fs::read_to_string(&tmpl_path)?;
                    let tmpl: toml::Value = content.parse()?;
                    let ts = tmpl
                        .get("vm_size")
                        .and_then(|v| v.as_str())
                        .map(String::from);
                    let tr = tmpl
                        .get("region")
                        .and_then(|v| v.as_str())
                        .map(String::from);
                    (ts, tr)
                } else {
                    eprintln!(
                        "Template '{}' not found at {}",
                        tmpl_name,
                        tmpl_path.display()
                    );
                    (None, None)
                }
            } else {
                (None, None)
            };

            // If the user didn't specify --vm-size or --region explicitly (i.e.,
            // they're still the config defaults), allow the template to override.
            let final_size = if !user_specified_size {
                tmpl_size.unwrap_or(size)
            } else {
                size
            };
            let final_loc = if !user_specified_region {
                tmpl_region.unwrap_or(loc)
            } else {
                loc
            };

            for i in 0..vm_count {
                let vm_name = if let Some(ref n) = name {
                    if vm_count > 1 {
                        format!("{}-{}", n, i + 1)
                    } else {
                        n.clone()
                    }
                } else {
                    format!("azlin-vm-{}", chrono::Utc::now().format("%Y%m%d-%H%M%S"))
                };

                azlin_core::models::validate_vm_name(&vm_name).map_err(|e| anyhow::anyhow!(e))?;

                let params = azlin_core::models::CreateVmParams {
                    name: vm_name.clone(),
                    resource_group: rg.clone(),
                    region: final_loc.clone(),
                    vm_size: final_size.clone(),
                    admin_username: admin_user.clone(),
                    ssh_key_path: ssh_key_path.clone(),
                    image: azlin_core::models::VmImage::default(),
                    tags: std::collections::HashMap::new(),
                };

                if let Err(e) = params.validate() {
                    anyhow::bail!("Invalid VM parameters: {}", e);
                }

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Creating VM '{}'...", vm_name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm = vm_manager.create_vm(&params)?;
                pb.finish_and_clear();

                println!("VM '{}' created successfully!", vm.name);

                let mut table = Table::new();
                table
                    .load_preset(UTF8_FULL)
                    .apply_modifier(UTF8_ROUND_CORNERS);
                table.set_header(vec!["Property", "Value"]);
                table.add_row(vec!["Name", &vm.name]);
                table.add_row(vec!["Resource Group", &rg]);
                table.add_row(vec!["Size", &final_size]);
                table.add_row(vec!["Region", &final_loc]);
                table.add_row(vec!["State", &vm.power_state.to_string()]);
                if let Some(ref ip) = vm.public_ip {
                    table.add_row(vec!["Public IP", ip]);
                }
                if let Some(ref ip) = vm.private_ip {
                    table.add_row(vec!["Private IP", ip]);
                }
                println!("{table}");

                // Clone repo if specified
                if let Some(ref repo_url) = repo {
                    if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                        let clone_cmd = match create_helpers::build_clone_cmd(repo_url) {
                            Ok(cmd) => cmd,
                            Err(e) => {
                                eprintln!("Invalid repository URL: {}", e);
                                return Ok(());
                            }
                        };
                        println!("Cloning repository '{}'...", repo_url);
                        let (exit_code, stdout, stderr) = ssh_exec(ip, &admin_user, &clone_cmd)?;
                        if exit_code == 0 {
                            println!("Repository cloned successfully.");
                            if !stdout.is_empty() {
                                print!("{}", stdout);
                            }
                        } else {
                            eprintln!(
                                "Failed to clone repository: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                }

                // Auto-connect if not disabled and single VM
                if !no_auto_connect && vm_count == 1 {
                    if let Some(ref ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                        println!("Connecting to '{}'...", vm_name);
                        let status = std::process::Command::new("ssh")
                            .args([
                                "-o",
                                "StrictHostKeyChecking=accept-new",
                                &format!("{}@{}", admin_user, ip),
                            ])
                            .status()?;
                        if !status.success() {
                            eprintln!("SSH connection ended with exit code: {:?}", status.code());
                        }
                    }
                }
            }
        }
        azlin_cli::Commands::Update {
            vm_identifier,
            resource_group,
            timeout: _,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", vm_identifier));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &vm_identifier)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

            println!("Updating development tools on '{}'...", vm_identifier);
            let update_script = update_helpers::build_dev_update_script();
            let (code, stdout, stderr) = ssh_exec(&ip, &user, update_script)?;
            if code == 0 {
                let green = Style::new().green();
                println!(
                    "{}",
                    green.apply_to(format!("Update completed on '{}'", vm_identifier))
                );
                if !stdout.trim().is_empty() {
                    println!("{}", stdout.trim());
                }
            } else {
                let detail = if stderr.trim().is_empty() {
                    String::new()
                } else {
                    format!(": {}", azlin_core::sanitizer::sanitize(stderr.trim()))
                };
                anyhow::bail!("Update failed on '{}'{}", vm_identifier, detail);
            }
        }

        // ── Clone ────────────────────────────────────────────────────
        azlin_cli::Commands::Clone {
            source_vm,
            num_replicas,
            resource_group,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            let snapshot_name = format!(
                "{}_clone_snap_{}",
                source_vm,
                chrono::Utc::now().format("%Y%m%d_%H%M%S")
            );

            println!(
                "Cloning VM '{}' ({} replica(s))...",
                source_vm, num_replicas
            );

            // Step 1: create snapshot of source
            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Snapshotting {}...", source_vm));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let snap_out = std::process::Command::new("az")
                .args([
                    "snapshot",
                    "create",
                    "--resource-group",
                    &rg,
                    "--source-disk",
                    &format!("{}_OsDisk", source_vm),
                    "--name",
                    &snapshot_name,
                    "--output",
                    "json",
                ])
                .output()?;
            pb.finish_and_clear();

            if !snap_out.status.success() {
                let stderr = String::from_utf8_lossy(&snap_out.stderr);
                anyhow::bail!(
                    "Failed to snapshot source VM: {}",
                    azlin_core::sanitizer::sanitize(stderr.trim())
                );
            }
            println!("Created snapshot '{}'", snapshot_name);

            // Step 2: create VMs from snapshot
            for i in 0..num_replicas {
                let clone_name = format!("{}-clone-{}", source_vm, i + 1);
                println!("Creating clone '{}'...", clone_name);
                let disk_name = format!("{}_OsDisk", clone_name);

                let disk_out = std::process::Command::new("az")
                    .args([
                        "disk",
                        "create",
                        "--resource-group",
                        &rg,
                        "--name",
                        &disk_name,
                        "--source",
                        &snapshot_name,
                        "--output",
                        "json",
                    ])
                    .output()?;

                if disk_out.status.success() {
                    println!("  Created disk '{}' from snapshot", disk_name);
                    // Step 3: create VM from the disk
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Creating VM '{}'...", clone_name));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let vm_out = std::process::Command::new("az")
                        .args([
                            "vm",
                            "create",
                            "--resource-group",
                            &rg,
                            "--name",
                            &clone_name,
                            "--attach-os-disk",
                            &disk_name,
                            "--os-type",
                            "Linux",
                            "--nsg",
                            "",
                            "--output",
                            "json",
                        ])
                        .output()?;
                    pb.finish_and_clear();

                    if vm_out.status.success() {
                        println!("  Created VM '{}'", clone_name);
                    } else {
                        let stderr = String::from_utf8_lossy(&vm_out.stderr);
                        eprintln!(
                            "  Failed to create VM '{}': {}",
                            clone_name,
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                } else {
                    let stderr = String::from_utf8_lossy(&disk_out.stderr);
                    eprintln!(
                        "  Failed to create disk for clone '{}': {}",
                        clone_name,
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
        }

        // ── Session ──────────────────────────────────────────────────
        azlin_cli::Commands::Session {
            vm_name,
            session_name,
            clear,
            ..
        } => {
            let mut config =
                azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
            let mut json = serde_json::to_value(&config)?;

            let sessions_key = "sessions";
            if clear {
                if let Some(obj) = json.as_object_mut() {
                    if let Some(sessions) = obj.get_mut(sessions_key) {
                        if let Some(s) = sessions.as_object_mut() {
                            s.remove(&vm_name);
                        }
                    }
                }
                config = serde_json::from_value(json)?;
                config.save()?;
                println!("Cleared session name for VM '{}'", vm_name);
            } else if let Some(name) = session_name {
                if let Some(obj) = json.as_object_mut() {
                    let sessions = obj
                        .entry(sessions_key)
                        .or_insert_with(|| serde_json::json!({}));
                    if let Some(s) = sessions.as_object_mut() {
                        s.insert(vm_name.clone(), serde_json::json!(name));
                    }
                }
                config = serde_json::from_value(json)?;
                config.save()?;
                println!("Set session for VM '{}' = '{}'", vm_name, name);
            } else {
                let session = json
                    .get(sessions_key)
                    .and_then(|s| s.get(&vm_name))
                    .and_then(|v| v.as_str());
                match session {
                    Some(s) => println!("Session for VM '{}': {}", vm_name, s),
                    None => println!("No session name set for VM '{}'", vm_name),
                }
            }
        }

        // ── Status ───────────────────────────────────────────────────
        azlin_cli::Commands::Status {
            resource_group, vm, ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Fetching VM status...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let vms = vm_manager.list_vms(&rg)?;
            pb.finish_and_clear();

            let filtered: Vec<_> = match &vm {
                Some(name) => vms.into_iter().filter(|v| &v.name == name).collect(),
                None => vms,
            };

            if filtered.is_empty() {
                println!("No VMs found.");
                return Ok(());
            }

            let key_style = Style::new().cyan().bold();
            for v in &filtered {
                println!("{}:", key_style.apply_to(&v.name));
                println!("  Power State:        {}", v.power_state);
                println!("  Provisioning State: {}", v.provisioning_state);
                println!("  VM Size:            {}", v.vm_size);
                println!("  Location:           {}", v.location);
                if let Some(ip) = &v.public_ip {
                    println!("  Public IP:          {}", ip);
                }
                if let Some(ip) = &v.private_ip {
                    println!("  Private IP:         {}", ip);
                }
                println!();
            }
        }

        // ── Code (VS Code Remote-SSH) ────────────────────────────────
        azlin_cli::Commands::Code {
            vm_identifier,
            resource_group,
            auth_profile: _,
            ..
        } => {
            let name = vm_identifier.ok_or_else(|| anyhow::anyhow!("VM name is required."))?;

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &name)?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

            let remote_uri = format!("ssh-remote+{}@{}", user, ip);
            println!("Opening VS Code: code --remote {}", remote_uri);
            let status = std::process::Command::new("code")
                .args(["--remote", &remote_uri])
                .status();

            match status {
                Ok(s) if s.success() => println!("VS Code opened for VM '{}'", name),
                _ => {
                    anyhow::bail!("Failed to open VS Code. Ensure 'code' is in your PATH.");
                }
            }
        }

        // ── Batch ────────────────────────────────────────────────────
        azlin_cli::Commands::Batch { action } => match action {
            azlin_cli::BatchAction::Stop {
                resource_group,
                tag,
                confirm,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let filter_msg = tag.as_deref().unwrap_or("all");
                if !confirm {
                    let ok = Confirm::new()
                        .with_prompt(format!("Stop VMs matching '{}' in {}?", filter_msg, rg))
                        .default(false)
                        .interact()?;
                    if !ok {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }
                let query = batch_helpers::build_vm_list_query(tag.as_deref())
                    .map_err(|e| anyhow::anyhow!("{}", e))?;
                let list_output = std::process::Command::new("az")
                    .args(["vm", "list", "-g", &rg, "--query", &query, "-o", "tsv"])
                    .output()?;
                let tsv = std::str::from_utf8(&list_output.stdout).unwrap_or("");
                let ids = batch_helpers::parse_vm_ids(tsv);
                if ids.is_empty() {
                    println!("No VMs found in resource group '{}'", rg);
                } else {
                    let args = batch_helpers::build_batch_args("deallocate", &ids);
                    let output = std::process::Command::new("az").args(&args).output()?;
                    let msg = batch_helpers::summarise_batch("stop", &rg, output.status.success());
                    if output.status.success() {
                        println!("{}", msg);
                    } else {
                        eprintln!("{}", msg);
                    }
                }
            }
            azlin_cli::BatchAction::Start {
                resource_group,
                tag,
                confirm,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let filter_msg = tag.as_deref().unwrap_or("all");
                if !confirm {
                    let ok = Confirm::new()
                        .with_prompt(format!("Start VMs matching '{}' in {}?", filter_msg, rg))
                        .default(false)
                        .interact()?;
                    if !ok {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }
                let query = batch_helpers::build_vm_list_query(tag.as_deref())
                    .map_err(|e| anyhow::anyhow!("{}", e))?;
                let list_output = std::process::Command::new("az")
                    .args(["vm", "list", "-g", &rg, "--query", &query, "-o", "tsv"])
                    .output()?;
                let tsv = std::str::from_utf8(&list_output.stdout).unwrap_or("");
                let ids = batch_helpers::parse_vm_ids(tsv);
                if ids.is_empty() {
                    println!("No VMs found in resource group '{}'", rg);
                } else {
                    let args = batch_helpers::build_batch_args("start", &ids);
                    let output = std::process::Command::new("az").args(&args).output()?;
                    let msg = batch_helpers::summarise_batch("start", &rg, output.status.success());
                    if output.status.success() {
                        println!("{}", msg);
                    } else {
                        eprintln!("{}", msg);
                    }
                }
            }
            azlin_cli::BatchAction::Command {
                command,
                resource_group,
                show_output,
                ..
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Running '{}' on all VMs in '{}'...", command, rg));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                pb.finish_and_clear();

                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                } else {
                    println!("Running '{}' on {} VM(s)...", command, vms.len());
                    run_on_fleet(&vms, &command, show_output);
                }
            }
            azlin_cli::BatchAction::Sync {
                resource_group,
                dry_run,
                ..
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let home = home_dir()?;
                let dotfiles = sync_helpers::default_dotfiles();

                for (name, ip, user) in &vms {
                    for dotfile in &dotfiles {
                        let local = home.join(dotfile);
                        if !local.exists() {
                            continue;
                        }
                        if dry_run {
                            println!("[dry-run] Would sync {} to {}:{}", dotfile, name, dotfile);
                        } else {
                            let output = std::process::Command::new("rsync")
                                .args(["-az", "-e", "ssh -o StrictHostKeyChecking=accept-new"])
                                .arg(local.as_os_str())
                                .arg(format!("{}@{}:~/{}", user, ip, dotfile))
                                .output();
                            match output {
                                Ok(o) if o.status.success() => {
                                    println!("Synced {} to {}", dotfile, name);
                                }
                                Ok(o) => {
                                    let stderr = String::from_utf8_lossy(&o.stderr);
                                    eprintln!(
                                        "Failed to sync {} to {}: {}",
                                        dotfile,
                                        name,
                                        azlin_core::sanitizer::sanitize(stderr.trim())
                                    );
                                }
                                Err(e) => {
                                    eprintln!("Failed to sync {} to {}: {}", dotfile, name, e);
                                }
                            }
                        }
                    }
                }
                if !dry_run {
                    println!("Sync complete.");
                }
            }
        },

        // ── Fleet ────────────────────────────────────────────────────
        azlin_cli::Commands::Fleet { action } => match action {
            azlin_cli::FleetAction::Run {
                command,
                resource_group,
                dry_run,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if dry_run {
                    println!("Would run '{}' across fleet in '{}'", command, rg);
                } else {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);

                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!("Gathering fleet VMs in '{}'...", rg));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                    pb.finish_and_clear();

                    if vms.is_empty() {
                        println!("No running VMs found in resource group '{}'", rg);
                    } else {
                        println!("Running '{}' across {} VM(s)...", command, vms.len());
                        run_on_fleet(&vms, &command, true);
                        println!("Fleet execution complete.");
                    }
                }
            }
            azlin_cli::FleetAction::Workflow {
                workflow_file,
                resource_group,
                dry_run,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if dry_run {
                    println!(
                        "Would execute workflow '{}' on fleet in '{}'",
                        workflow_file.display(),
                        rg
                    );
                } else {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);

                    let content = std::fs::read_to_string(&workflow_file).map_err(|e| {
                        anyhow::anyhow!(
                            "Failed to read workflow file '{}': {}",
                            workflow_file.display(),
                            e
                        )
                    })?;
                    let workflow: serde_yaml::Value = serde_yaml::from_str(&content)
                        .map_err(|e| anyhow::anyhow!("Failed to parse workflow YAML: {}", e))?;

                    let steps = workflow
                        .get("steps")
                        .and_then(|s| s.as_sequence())
                        .ok_or_else(|| {
                            anyhow::anyhow!("Workflow YAML must contain a 'steps' array")
                        })?;

                    let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                    if vms.is_empty() {
                        println!("No running VMs found in resource group '{}'", rg);
                        return Ok(());
                    }

                    println!(
                        "Executing workflow '{}' on {} VM(s)...",
                        workflow_file.display(),
                        vms.len()
                    );
                    for (i, step) in steps.iter().enumerate() {
                        let default_name = format!("step-{}", i + 1);
                        let step_name = step
                            .get("name")
                            .and_then(|n| n.as_str())
                            .unwrap_or(&default_name);
                        let cmd = step
                            .get("command")
                            .or_else(|| step.get("run"))
                            .and_then(|c| c.as_str());

                        if let Some(cmd) = cmd {
                            println!("\n── Step {}: {} ──", i + 1, step_name);
                            run_on_fleet(&vms, cmd, true);
                        } else {
                            eprintln!(
                                "Step {} ('{}') has no 'command' or 'run' field, skipping",
                                i + 1,
                                step_name
                            );
                        }
                    }
                    println!("\nWorkflow execution complete.");
                }
            }
        },

        // ── Compose ──────────────────────────────────────────────────
        azlin_cli::Commands::Compose { action } => match action {
            azlin_cli::ComposeAction::Up {
                file,
                resource_group,
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let f = file
                    .as_deref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "docker-compose.yml".to_string());

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
                let cmd = compose_helpers::build_compose_cmd("up -d", &escaped_f);
                println!("Running 'docker compose up' on {} VM(s)...", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
            azlin_cli::ComposeAction::Down {
                file,
                resource_group,
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let f = file
                    .as_deref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "docker-compose.yml".to_string());

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
                let cmd = compose_helpers::build_compose_cmd("down", &escaped_f);
                println!("Running 'docker compose down' on {} VM(s)...", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
            azlin_cli::ComposeAction::Ps {
                file,
                resource_group,
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let f = file
                    .as_deref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "docker-compose.yml".to_string());

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
                let cmd = compose_helpers::build_compose_cmd("ps", &escaped_f);
                println!("Docker compose status on {} VM(s):", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
        },

        // ── GitHub Runner ────────────────────────────────────────────
        azlin_cli::Commands::GithubRunner { action } => {
            let runner_dir = home_dir()?.join(".azlin").join("runners");
            std::fs::create_dir_all(&runner_dir)?;

            match action {
                azlin_cli::GithubRunnerAction::Enable {
                    repo,
                    pool,
                    count,
                    labels,
                    resource_group,
                    vm_size,
                    ..
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    if let Err(e) = name_validation::validate_name(&pool) {
                        anyhow::bail!("Invalid pool name: {}", e);
                    }
                    let repo_name = repo.unwrap_or_else(|| "<not set>".to_string());
                    let label_str = labels.unwrap_or_else(|| "self-hosted".to_string());
                    let size = vm_size.unwrap_or_else(|| "Standard_B2s".to_string());

                    // Save config
                    let mut config = toml::map::Map::new();
                    config.insert("pool".to_string(), toml::Value::String(pool.clone()));
                    config.insert("repo".to_string(), toml::Value::String(repo_name.clone()));
                    config.insert("count".to_string(), toml::Value::Integer(count as i64));
                    config.insert("labels".to_string(), toml::Value::String(label_str.clone()));
                    config.insert(
                        "resource_group".to_string(),
                        toml::Value::String(rg.clone()),
                    );
                    config.insert("vm_size".to_string(), toml::Value::String(size.clone()));
                    config.insert("enabled".to_string(), toml::Value::Boolean(true));
                    config.insert(
                        "created".to_string(),
                        toml::Value::String(
                            chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
                        ),
                    );
                    let val = toml::Value::Table(config);
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    std::fs::write(&pool_path, toml::to_string_pretty(&val)?)?;

                    // Provision runner VMs
                    println!("Enabling GitHub runner fleet:");
                    println!("  Repository:     {}", repo_name);
                    println!("  Pool:           {}", pool);
                    println!("  Count:          {}", count);
                    println!("  Labels:         {}", label_str);
                    println!("  VM Size:        {}", size);
                    println!("  Resource Group: {}", rg);

                    for i in 0..count {
                        let vm_name = format!("azlin-runner-{}-{}", pool, i + 1);
                        let pb = indicatif::ProgressBar::new_spinner();
                        pb.set_message(format!("Provisioning {}...", vm_name));
                        pb.enable_steady_tick(std::time::Duration::from_millis(100));
                        let out = std::process::Command::new("az")
                            .args([
                                "vm",
                                "create",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                                "--image",
                                "Ubuntu2204",
                                "--size",
                                &size,
                                "--admin-username",
                                DEFAULT_ADMIN_USERNAME,
                                "--generate-ssh-keys",
                                "--tags",
                                &format!("azlin-runner=true pool={} repo={}", pool, repo_name),
                                "--output",
                                "json",
                            ])
                            .output()?;
                        pb.finish_and_clear();
                        if out.status.success() {
                            println!("  Provisioned VM '{}'", vm_name);
                        } else {
                            let stderr = String::from_utf8_lossy(&out.stderr);
                            eprintln!(
                                "  Failed to provision '{}': {}",
                                vm_name,
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                    println!(
                        "Runner fleet configuration saved to {}",
                        pool_path.display()
                    );
                    println!(
                        "Note: To complete setup, install the GitHub Actions runner on each VM."
                    );
                }
                azlin_cli::GithubRunnerAction::Disable { pool, keep_vms } => {
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    if pool_path.exists() {
                        if !keep_vms {
                            // Find and delete runner VMs
                            let rg_output = std::process::Command::new("az")
                                .args([
                                    "vm",
                                    "list",
                                    "--query",
                                    &format!("[?tags.pool=='{}'].id", pool),
                                    "--output",
                                    "tsv",
                                ])
                                .output()?;
                            if rg_output.status.success() {
                                let ids = String::from_utf8_lossy(&rg_output.stdout);
                                let id_list: Vec<&str> =
                                    ids.lines().filter(|l| !l.is_empty()).collect();
                                if !id_list.is_empty() {
                                    println!("Deleting {} runner VM(s)...", id_list.len());
                                    let mut args = vec!["vm", "delete", "--yes", "--ids"];
                                    args.extend(id_list.iter().copied());
                                    let del_output =
                                        std::process::Command::new("az").args(&args).output()?;
                                    if !del_output.status.success() {
                                        eprintln!(
                                            "Warning: VM deletion may have failed (exit {})",
                                            del_output.status.code().unwrap_or(-1)
                                        );
                                    }
                                }
                            }
                        } else {
                            println!("VMs will be kept running.");
                        }
                        std::fs::remove_file(&pool_path)?;
                        println!("Runner pool '{}' disabled.", pool);
                    } else {
                        println!("Runner pool '{}' not found.", pool);
                    }
                }
                azlin_cli::GithubRunnerAction::Status { pool } => {
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    if pool_path.exists() {
                        let content = std::fs::read_to_string(&pool_path)?;
                        let val: toml::Value = toml::from_str(&content)?;
                        println!("Runner pool '{}':", pool);
                        if let Some(t) = val.as_table() {
                            for (k, v) in t {
                                println!("  {}: {}", k, v);
                            }
                        }
                        // List actual runner VMs
                        let output = std::process::Command::new("az")
                            .args([
                                "vm",
                                "list",
                                "--query",
                                &format!(
                                    "[?tags.pool=='{}'].{{name:name, state:powerState}}",
                                    pool
                                ),
                                "--output",
                                "table",
                            ])
                            .output()?;
                        if output.status.success() {
                            let text = String::from_utf8_lossy(&output.stdout);
                            if !text.trim().is_empty() {
                                println!("\nRunner VMs:");
                                print!("{}", text);
                            }
                        }
                    } else {
                        println!("Runner pool '{}': not configured", pool);
                        println!(
                            "Enable with: azlin github-runner enable --repo <owner/repo> --pool {}",
                            pool
                        );
                    }
                }
                azlin_cli::GithubRunnerAction::Scale { pool, count } => {
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    if pool_path.exists() {
                        let content = std::fs::read_to_string(&pool_path)?;
                        let mut val: toml::Value = toml::from_str(&content)?;
                        let old_count = val
                            .as_table()
                            .and_then(|t| t.get("count"))
                            .and_then(|v| v.as_integer())
                            .unwrap_or(0) as u32;
                        if let Some(t) = val.as_table_mut() {
                            t.insert("count".to_string(), toml::Value::Integer(count as i64));
                        }
                        std::fs::write(&pool_path, toml::to_string_pretty(&val)?)?;
                        println!(
                            "Scaled runner pool '{}': {} → {} runners",
                            pool, old_count, count
                        );
                        if count > old_count {
                            println!(
                                "Note: Provision additional VMs with 'azlin github-runner enable'"
                            );
                        }
                    } else {
                        println!("Runner pool '{}' not configured.", pool);
                    }
                }
            }
        }

        // ── Template ─────────────────────────────────────────────────
        azlin_cli::Commands::Template { action } => {
            let azlin_dir = home_dir()?.join(".azlin").join("templates");
            std::fs::create_dir_all(&azlin_dir)?;

            match action {
                azlin_cli::TemplateAction::Create {
                    name,
                    description,
                    vm_size,
                    region,
                    cloud_init,
                } => {
                    let tpl = templates::build_template_toml(
                        &name,
                        description.as_deref(),
                        vm_size.as_deref(),
                        region.as_deref(),
                        cloud_init
                            .as_ref()
                            .map(|p| p.display().to_string())
                            .as_deref(),
                    );
                    let path = templates::save_template(&azlin_dir, &name, &tpl)?;
                    println!("Saved template '{}' at {}", name, path.display());
                }
                azlin_cli::TemplateAction::List => {
                    let rows = templates::list_templates(&azlin_dir)?;
                    if rows.is_empty() {
                        println!("No templates found.");
                    } else {
                        azlin_cli::table::render_rows(
                            &["Name", "VM Size", "Region"],
                            &rows,
                            &cli.output,
                        );
                    }
                }
                azlin_cli::TemplateAction::Show { name } => {
                    match templates::load_template(&azlin_dir, &name) {
                        Ok(tpl) => println!("{}", toml::to_string_pretty(&tpl).unwrap_or_default()),
                        Err(_) => {
                            anyhow::bail!("Template '{}' not found.", name);
                        }
                    }
                }
                azlin_cli::TemplateAction::Apply { name } => {
                    match templates::load_template(&azlin_dir, &name) {
                        Ok(tpl) => {
                            let vm_size = tpl
                                .get("vm_size")
                                .and_then(|v| v.as_str())
                                .unwrap_or("Standard_D4s_v3");
                            let region = tpl
                                .get("region")
                                .and_then(|v| v.as_str())
                                .unwrap_or("westus2");
                            println!(
                                "To create a VM with template '{}', run:\n  azlin new my-vm --size {} --region {}",
                                name, vm_size, region
                            );
                        }
                        Err(_) => {
                            anyhow::bail!("Template '{}' not found.", name);
                        }
                    }
                }
                azlin_cli::TemplateAction::Delete { name, force } => {
                    if templates::load_template(&azlin_dir, &name).is_err() {
                        anyhow::bail!("Template '{}' not found.", name);
                    }
                    if !force {
                        let ok = Confirm::new()
                            .with_prompt(format!("Delete template '{}'?", name))
                            .default(false)
                            .interact()?;
                        if !ok {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }
                    templates::delete_template(&azlin_dir, &name)?;
                    println!("Deleted template '{}'", name);
                }
                azlin_cli::TemplateAction::Export { name, output_file } => {
                    let path = azlin_dir.join(format!("{}.toml", name));
                    if !path.exists() {
                        anyhow::bail!("Template '{}' not found.", name);
                    }
                    std::fs::copy(&path, &output_file)?;
                    println!("Exported template '{}' to {}", name, output_file.display());
                }
                azlin_cli::TemplateAction::Import { input_file } => {
                    let content = std::fs::read_to_string(&input_file)?;
                    let name = templates::import_template(&azlin_dir, &content)?;
                    println!("Imported template '{}' from {}", name, input_file.display());
                }
            }
        }

        // ── Autopilot ────────────────────────────────────────────────
        azlin_cli::Commands::Autopilot { action } => match action {
            azlin_cli::AutopilotAction::Enable {
                budget,
                strategy,
                idle_threshold,
                cpu_threshold,
            } => {
                let azlin_home = home_dir()?.join(".azlin");
                std::fs::create_dir_all(&azlin_home)?;
                let ap_path = azlin_home.join("autopilot.toml");
                let mut config = toml::map::Map::new();
                config.insert("enabled".to_string(), toml::Value::Boolean(true));
                if let Some(b) = budget {
                    config.insert("budget".to_string(), toml::Value::Integer(b as i64));
                }
                config.insert(
                    "strategy".to_string(),
                    toml::Value::String(strategy.clone()),
                );
                config.insert(
                    "idle_threshold_minutes".to_string(),
                    toml::Value::Integer(idle_threshold as i64),
                );
                config.insert(
                    "cpu_threshold_percent".to_string(),
                    toml::Value::Integer(cpu_threshold as i64),
                );
                config.insert(
                    "updated".to_string(),
                    toml::Value::String(
                        chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
                    ),
                );
                let val = toml::Value::Table(config);
                std::fs::write(&ap_path, toml::to_string_pretty(&val)?)?;
                println!("Autopilot enabled:");
                if let Some(b) = budget {
                    println!("  Budget:         ${}/month", b);
                }
                println!("  Strategy:       {}", strategy);
                println!("  Idle threshold: {} min", idle_threshold);
                println!("  CPU threshold:  {}%", cpu_threshold);
                println!("Saved to {}", ap_path.display());
            }
            azlin_cli::AutopilotAction::Disable { keep_config } => {
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                if ap_path.exists() {
                    if keep_config {
                        let content = std::fs::read_to_string(&ap_path)?;
                        let mut val: toml::Value = toml::from_str(&content)?;
                        if let Some(t) = val.as_table_mut() {
                            t.insert("enabled".to_string(), toml::Value::Boolean(false));
                        }
                        std::fs::write(&ap_path, toml::to_string_pretty(&val)?)?;
                        println!("Autopilot disabled. Configuration preserved.");
                    } else {
                        std::fs::remove_file(&ap_path)?;
                        println!("Autopilot disabled and configuration removed.");
                    }
                } else {
                    println!("Autopilot was not configured.");
                }
            }
            azlin_cli::AutopilotAction::Status => {
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                if ap_path.exists() {
                    let content = std::fs::read_to_string(&ap_path)?;
                    let val: toml::Value = toml::from_str(&content)?;
                    if let Some(t) = val.as_table() {
                        let enabled = t.get("enabled").and_then(|v| v.as_bool()).unwrap_or(false);
                        println!(
                            "Autopilot: {}",
                            if enabled { "ENABLED" } else { "DISABLED" }
                        );
                        for (k, v) in t {
                            if k != "enabled" {
                                println!("  {}: {}", k, v);
                            }
                        }
                    }
                } else {
                    println!("Autopilot: not configured");
                    println!("Enable with: azlin autopilot enable");
                }
            }
            azlin_cli::AutopilotAction::Config { set, show } => {
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                if show || set.is_empty() {
                    if ap_path.exists() {
                        let content = std::fs::read_to_string(&ap_path)?;
                        print!("{}", content);
                    } else {
                        println!("No autopilot configuration found.");
                    }
                } else {
                    let content = if ap_path.exists() {
                        std::fs::read_to_string(&ap_path)?
                    } else {
                        String::new()
                    };
                    let mut val: toml::Value = if content.is_empty() {
                        toml::Value::Table(toml::map::Map::new())
                    } else {
                        toml::from_str(&content)?
                    };
                    if let Some(t) = val.as_table_mut() {
                        for kv in &set {
                            if let Some((k, v)) = kv.split_once('=') {
                                t.insert(k.to_string(), toml::Value::String(v.to_string()));
                                println!("Set {} = {}", k, v);
                            }
                        }
                    }
                    std::fs::write(&ap_path, toml::to_string_pretty(&val)?)?;
                }
            }
            azlin_cli::AutopilotAction::Run { dry_run } => {
                // Check VM utilization and recommend actions
                let rg = resolve_resource_group(None)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let vms = vm_manager.list_vms(&rg)?;
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                let (idle_threshold, cost_limit) = if ap_path.exists() {
                    let content = std::fs::read_to_string(&ap_path)?;
                    let val: toml::Value = toml::from_str(&content)?;
                    let thresh = val
                        .as_table()
                        .and_then(|t| t.get("idle_threshold_minutes"))
                        .and_then(|v| v.as_integer())
                        .unwrap_or(30) as u32;
                    let limit = val
                        .as_table()
                        .and_then(|t| t.get("cost_limit_usd"))
                        .and_then(|v| v.as_float())
                        .unwrap_or(0.0);
                    (thresh, limit)
                } else {
                    (30, 0.0)
                };
                println!(
                    "Autopilot check (idle threshold: {} min, cost limit: ${:.2}):",
                    idle_threshold, cost_limit
                );

                let mut actions: Vec<(String, String)> = Vec::new();
                for vm in &vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        // Check CPU and uptime via SSH
                        let output = std::process::Command::new("ssh")
                            .args([
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=10",
                                "-o", "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                "awk '{u=$2+$4; t=$2+$4+$5; if (t>0) printf \"%.1f\", u*100/t; else print \"0\"}' /proc/stat | head -1 && cat /proc/uptime | awk '{print $1}'",
                            ])
                            .output();
                        if let Ok(out) = output {
                            if out.status.success() {
                                let text = String::from_utf8_lossy(&out.stdout);
                                let lines: Vec<&str> = text.trim().lines().collect();
                                let cpu_pct: f64 =
                                    lines.first().and_then(|s| s.parse().ok()).unwrap_or(100.0);
                                let uptime_secs: f64 =
                                    lines.get(1).and_then(|s| s.parse().ok()).unwrap_or(0.0);
                                let idle_mins = idle_threshold as f64;
                                if cpu_pct < 5.0 && uptime_secs > idle_mins * 60.0 {
                                    println!("  ⚠ {} — CPU {} for {:.0}min — IDLE (recommend deallocate)",
                                             vm.name, health_helpers::format_percentage(cpu_pct as f32), uptime_secs / 60.0);
                                    actions.push((vm.name.clone(), "deallocate".to_string()));
                                } else {
                                    println!(
                                        "  ✓ {} — CPU {} — active",
                                        vm.name,
                                        health_helpers::format_percentage(cpu_pct as f32)
                                    );
                                }
                            } else {
                                println!("  ? {} — could not check (SSH failed)", vm.name);
                            }
                        } else {
                            println!("  ? {} — could not check (SSH unavailable)", vm.name);
                        }
                    }
                }

                if actions.is_empty() {
                    println!("No cost-saving actions needed at this time.");
                } else if dry_run {
                    println!("\nDry run — {} action(s) would be taken:", actions.len());
                    for (name, action) in &actions {
                        println!("  {} → {}", name, action);
                    }
                } else {
                    println!("\nApplying {} action(s):", actions.len());
                    for (name, action) in &actions {
                        if action == "deallocate" {
                            print!("  Deallocating {}...", name);
                            let result = vm_manager.stop_vm(&rg, name, true);
                            match result {
                                Ok(_) => println!(" ✓ done"),
                                Err(e) => println!(" ✗ failed: {}", e),
                            }
                        }
                    }
                }
            }
        },

        // ── Context ──────────────────────────────────────────────────
        azlin_cli::Commands::Context { action } => {
            let azlin_home = home_dir()?.join(".azlin");
            let ctx_dir = azlin_home.join("contexts");
            let active_ctx_path = azlin_home.join("active-context");
            std::fs::create_dir_all(&ctx_dir)?;

            match action {
                azlin_cli::ContextAction::List { .. } => {
                    let active = std::fs::read_to_string(&active_ctx_path)
                        .map(|s| s.trim().to_string())
                        .unwrap_or_default();
                    let ctx_list = contexts::list_contexts(&ctx_dir, &active)?;
                    if ctx_list.is_empty() {
                        println!("No contexts found. Create one with: azlin context create <name>");
                    } else {
                        let rows: Vec<Vec<String>> = ctx_list
                            .iter()
                            .map(|(name, is_active)| {
                                vec![
                                    name.clone(),
                                    if *is_active { "true" } else { "false" }.to_string(),
                                ]
                            })
                            .collect();
                        match &cli.output {
                            azlin_cli::OutputFormat::Table => {
                                for (name, is_active) in &ctx_list {
                                    if *is_active {
                                        println!("* {}", name);
                                    } else {
                                        println!("  {}", name);
                                    }
                                }
                            }
                            _ => {
                                azlin_cli::table::render_rows(
                                    &["Name", "Active"],
                                    &rows,
                                    &cli.output,
                                );
                            }
                        }
                    }
                }
                azlin_cli::ContextAction::Show { .. } => {
                    match std::fs::read_to_string(&active_ctx_path) {
                        Ok(name) => {
                            let name = name.trim();
                            println!("Current context: {}", name);
                            let path = ctx_dir.join(format!("{}.toml", name));
                            if let Ok(content) = std::fs::read_to_string(&path) {
                                println!("{}", content.trim());
                            }
                        }
                        Err(_) => println!("No context selected."),
                    }
                }
                azlin_cli::ContextAction::Use { name, .. } => {
                    if let Err(e) = name_validation::validate_name(&name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    let ctx_path = ctx_dir.join(format!("{}.toml", name));
                    if !ctx_path.exists() {
                        anyhow::bail!("Context '{}' not found.", name);
                    }
                    std::fs::write(&active_ctx_path, &name)?;
                    println!("Switched to context '{}'", name);
                }
                azlin_cli::ContextAction::Create {
                    name,
                    subscription_id,
                    tenant_id,
                    resource_group,
                    region,
                    key_vault_name,
                    ..
                } => {
                    if let Err(e) = name_validation::validate_name(&name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    let toml_str = contexts::build_context_toml(
                        &name,
                        subscription_id.as_deref(),
                        tenant_id.as_deref(),
                        resource_group.as_deref(),
                        region.as_deref(),
                        key_vault_name.as_deref(),
                    )?;
                    let path = ctx_dir.join(format!("{}.toml", name));
                    std::fs::write(&path, &toml_str)?;
                    println!("Created context '{}'", name);
                }
                azlin_cli::ContextAction::Delete { name, force, .. } => {
                    if let Err(e) = name_validation::validate_name(&name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    let path = ctx_dir.join(format!("{}.toml", name));
                    if !path.exists() {
                        anyhow::bail!("Context '{}' not found.", name);
                    }
                    if !force {
                        let ok = Confirm::new()
                            .with_prompt(format!("Delete context '{}'?", name))
                            .default(false)
                            .interact()?;
                        if !ok {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }
                    std::fs::remove_file(&path)?;
                    // Clear active context if it was the deleted one
                    if let Ok(active) = std::fs::read_to_string(&active_ctx_path) {
                        if active.trim() == name {
                            let _ = std::fs::remove_file(&active_ctx_path);
                        }
                    }
                    println!("Deleted context '{}'", name);
                }
                azlin_cli::ContextAction::Rename {
                    old_name, new_name, ..
                } => {
                    if let Err(e) = name_validation::validate_name(&old_name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    if let Err(e) = name_validation::validate_name(&new_name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    contexts::rename_context_file(&ctx_dir, &old_name, &new_name)?;
                    // Update active context if it was the renamed one
                    if let Ok(active) = std::fs::read_to_string(&active_ctx_path) {
                        if active.trim() == old_name {
                            std::fs::write(&active_ctx_path, &new_name)?;
                        }
                    }
                    println!("Renamed context '{}' → '{}'", old_name, new_name);
                }
                azlin_cli::ContextAction::Migrate { force, .. } => {
                    // Check for legacy config.toml with subscription/tenant at top level
                    let cfg = azlin_core::AzlinConfig::load()
                        .context("Failed to load azlin config for migration")?;
                    let sub = cfg.default_resource_group.as_ref().and_then(|_| {
                        let out = std::process::Command::new("az")
                            .args(["account", "show", "--query", "id", "-o", "tsv"])
                            .output()
                            .ok()?;
                        if out.status.success() {
                            Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
                        } else {
                            None
                        }
                    });
                    let tenant = std::process::Command::new("az")
                        .args(["account", "show", "--query", "tenantId", "-o", "tsv"])
                        .output()
                        .ok()
                        .and_then(|o| {
                            if o.status.success() {
                                Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
                            } else {
                                None
                            }
                        });

                    if let (Some(sub_id), Some(tenant_id)) = (sub, tenant) {
                        let ctx_name = "default";
                        let ctx_path = ctx_dir.join(format!("{}.toml", ctx_name));
                        if ctx_path.exists() && !force {
                            println!("Context 'default' already exists. Use --force to overwrite.");
                        } else {
                            let mut ctx = toml::map::Map::new();
                            ctx.insert(
                                "name".to_string(),
                                toml::Value::String(ctx_name.to_string()),
                            );
                            ctx.insert("subscription_id".to_string(), toml::Value::String(sub_id));
                            ctx.insert("tenant_id".to_string(), toml::Value::String(tenant_id));
                            if let Some(rg) = &cfg.default_resource_group {
                                ctx.insert(
                                    "resource_group".to_string(),
                                    toml::Value::String(rg.clone()),
                                );
                            }
                            if !cfg.default_region.is_empty() {
                                ctx.insert(
                                    "region".to_string(),
                                    toml::Value::String(cfg.default_region.clone()),
                                );
                            }
                            let val = toml::Value::Table(ctx);
                            std::fs::write(&ctx_path, toml::to_string_pretty(&val)?)?;
                            std::fs::write(&active_ctx_path, ctx_name)?;
                            println!("Migrated legacy config to context '{}'", ctx_name);
                        }
                    } else {
                        println!("Could not determine subscription/tenant from az account. Run 'az login' first.");
                    }
                }
            }
        }

        // ── Disk ─────────────────────────────────────────────────────
        azlin_cli::Commands::Disk { action } => match action {
            azlin_cli::DiskAction::Add {
                vm_name,
                size,
                sku,
                resource_group,
                lun,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let disk_name = format!("{}_datadisk_{}", vm_name, lun.unwrap_or(0));

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Adding {} GB disk to {}...", size, vm_name));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let output = std::process::Command::new("az")
                    .args([
                        "vm",
                        "disk",
                        "attach",
                        "--resource-group",
                        &rg,
                        "--vm-name",
                        &vm_name,
                        "--name",
                        &disk_name,
                        "--size-gb",
                        &size.to_string(),
                        "--sku",
                        &sku,
                        "--new",
                    ])
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    println!(
                        "Attached {} GB disk '{}' to VM '{}'",
                        size, disk_name, vm_name
                    );
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to attach disk: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
        },

        // ── IP ───────────────────────────────────────────────────────
        azlin_cli::Commands::Ip { action } => match action {
            azlin_cli::IpAction::Check {
                vm_identifier,
                resource_group,
                port,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if let Some(name) = vm_identifier {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vm = vm_manager.get_vm(&rg, &name)?;

                    let ip = vm.public_ip.or(vm.private_ip);
                    match ip {
                        Some(addr) => {
                            println!("VM '{}': {}", name, addr);
                            let addr_port = format!("{}:{}", addr, port);
                            match addr_port.parse::<std::net::SocketAddr>() {
                                Ok(sock_addr) => {
                                    match std::net::TcpStream::connect_timeout(
                                        &sock_addr,
                                        std::time::Duration::from_secs(5),
                                    ) {
                                        Ok(_) => println!("  Port {} on {} is OPEN", port, addr),
                                        Err(_) => println!("  Port {} on {} is CLOSED", port, addr),
                                    }
                                }
                                Err(e) => eprintln!("  Invalid address '{}': {}", addr_port, e),
                            }
                        }
                        None => println!("VM '{}': no IP address found", name),
                    }
                } else {
                    println!(
                        "Specify a VM name or use --all to check all VMs in '{}'",
                        rg
                    );
                }
            }
        },

        // ── Web ──────────────────────────────────────────────────────
        azlin_cli::Commands::Web { action } => match action {
            azlin_cli::WebAction::Start { port, host } => {
                // Start the PWA dev server (same as Python: npm run dev in pwa/)
                let pwa_dir = std::env::current_dir()?.join("pwa");
                if !pwa_dir.exists() {
                    anyhow::bail!(
                        "PWA directory not found at {:?}. Make sure you're in the azlin project root.",
                        pwa_dir
                    );
                }

                // Generate env config from azlin context
                let config =
                    azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
                let env_file = pwa_dir.join(".env.local");
                {
                    let cfg = &config;
                    let mut env_content = String::new();
                    if let Some(ref rg) = cfg.default_resource_group {
                        env_content.push_str(&format!("VITE_RESOURCE_GROUP={}\n", rg));
                    }
                    // Get subscription from az CLI
                    let sub_output = std::process::Command::new("az")
                        .args(["account", "show", "--query", "id", "-o", "tsv"])
                        .output();
                    if let Ok(out) = sub_output {
                        let sub = String::from_utf8_lossy(&out.stdout).trim().to_string();
                        if !sub.is_empty() {
                            env_content.push_str(&format!("VITE_SUBSCRIPTION_ID={}\n", sub));
                        }
                    }
                    if !env_content.is_empty() {
                        std::fs::write(&env_file, &env_content)?;
                    }
                }

                let port_str = port.to_string();
                println!("🏴‍☠️ Starting Azlin Mobile PWA on http://{}:{}", host, port);
                println!("Press Ctrl+C to stop the server");

                // Write PID file for web stop
                let pid_path = home_dir()?.join(".azlin").join("web.pid");
                if let Some(parent) = pid_path.parent() {
                    std::fs::create_dir_all(parent)?;
                }

                let mut child = std::process::Command::new("npm")
                    .args(["run", "dev", "--", "--port", &port_str, "--host", &host])
                    .current_dir(&pwa_dir)
                    .spawn()?;

                std::fs::write(&pid_path, child.id().to_string())?;
                let status = child.wait()?;
                // Clean up PID file
                let _ = std::fs::remove_file(&pid_path);
                if !status.success() {
                    std::process::exit(status.code().unwrap_or(1));
                }
            }
            azlin_cli::WebAction::Stop => {
                // Check for a running web dashboard pid file
                let pid_path = home_dir()?.join(".azlin").join("web.pid");
                if pid_path.exists() {
                    let pid_str = std::fs::read_to_string(&pid_path)?;
                    if let Ok(pid) = pid_str.trim().parse::<u32>() {
                        // Check if process is running
                        let check = std::process::Command::new("kill")
                            .args(["-0", &pid.to_string()])
                            .output()?;
                        if check.status.success() {
                            let _ = std::process::Command::new("kill")
                                .arg(pid.to_string())
                                .output()?;
                            println!("Stopped web dashboard (PID {}).", pid);
                        } else {
                            println!("Web dashboard process {} not found.", pid);
                        }
                    }
                    let _ = std::fs::remove_file(&pid_path);
                } else {
                    println!("No web dashboard running. Start one with: azlin web start");
                }
            }
        },

        // ── Restore ──────────────────────────────────────────────────
        azlin_cli::Commands::Restore { resource_group, .. } => {
            let rg = resolve_resource_group(resource_group)?;
            println!("Restoring azlin sessions in '{}'...", rg);

            // Find running VMs with session tags
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let vms = vm_manager.list_vms(&rg)?;
            let running: Vec<_> = vms
                .iter()
                .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
                .collect();

            if running.is_empty() {
                println!("No running VMs found in '{}'.", rg);
                return Ok(());
            }

            println!("Found {} running VM(s):", running.len());
            for vm in &running {
                let session = vm
                    .tags
                    .get("azlin-session")
                    .map(|s| s.as_str())
                    .unwrap_or("-");
                let ip = vm
                    .public_ip
                    .as_deref()
                    .or(vm.private_ip.as_deref())
                    .unwrap_or("no-ip");
                println!("  {} (session: {}, ip: {})", vm.name, session, ip);
            }
            println!("Session restore complete. Use 'azlin connect <vm-name>' to reconnect.");
        }

        // ── Sessions ─────────────────────────────────────────────────
        azlin_cli::Commands::Sessions { action } => match action {
            azlin_cli::SessionsAction::Save {
                session_name,
                resource_group,
                vms,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let sessions_dir = home_dir()?.join(".azlin").join("sessions");
                std::fs::create_dir_all(&sessions_dir)?;

                let session_val = sessions::build_session_toml(&session_name, &rg, &vms);
                let path = sessions_dir.join(format!("{}.toml", session_name));
                std::fs::write(&path, toml::to_string_pretty(&session_val)?)?;
                println!("Saved session '{}' to {}", session_name, path.display());
            }
            azlin_cli::SessionsAction::Load { session_name } => {
                let path = home_dir()?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.toml", session_name));
                if !path.exists() {
                    anyhow::bail!("Session '{}' not found.", session_name);
                }
                let content = std::fs::read_to_string(&path)?;
                let (rg, vms, created) = sessions::parse_session_toml(&content)?;
                println!("Loaded session '{}':", session_name);
                println!("  Resource group: {}", rg);
                if !vms.is_empty() {
                    println!("  VMs:            {}", vms.join(", "));
                }
                println!("  Created:        {}", created);
            }
            azlin_cli::SessionsAction::Delete {
                session_name,
                force,
            } => {
                let path = home_dir()?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.toml", session_name));
                if !path.exists() {
                    anyhow::bail!("Session '{}' not found.", session_name);
                }
                if !force {
                    let confirmed = Confirm::new()
                        .with_prompt(format!("Delete session '{}'?", session_name))
                        .default(false)
                        .interact()?;
                    if !confirmed {
                        println!("Cancelled.");
                        return Ok(());
                    }
                }
                std::fs::remove_file(&path)?;
                println!("Deleted session '{}'.", session_name);
            }
            azlin_cli::SessionsAction::List => {
                let dir = home_dir()?.join(".azlin").join("sessions");
                let names = sessions::list_session_names(&dir)?;
                if names.is_empty() {
                    println!("No saved sessions.");
                } else {
                    let rows: Vec<Vec<String>> = names.into_iter().map(|n| vec![n]).collect();
                    match &cli.output {
                        azlin_cli::OutputFormat::Table => {
                            for row in &rows {
                                println!("  {}", row[0]);
                            }
                        }
                        _ => {
                            azlin_cli::table::render_rows(&["Session"], &rows, &cli.output);
                        }
                    }
                }
            }
        },

        // ── Sync ─────────────────────────────────────────────────────
        azlin_cli::Commands::Sync {
            vm_name,
            dry_run,
            resource_group,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            let home_dir = home_dir()?.join(".azlin").join("home");

            if !home_dir.exists() {
                anyhow::bail!("No ~/.azlin/home/ directory found. Nothing to sync.");
            }

            let target_vm = vm_name;
            if dry_run {
                let target_name = target_vm.as_deref().unwrap_or("all VMs");
                println!(
                    "Would sync {} to {} in '{}'",
                    home_dir.display(),
                    target_name,
                    rg
                );
            } else {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let vms = vm_manager.list_vms(&rg)?;
                let running_vms: Vec<_> = vms
                    .iter()
                    .filter(|v| v.power_state == azlin_core::models::PowerState::Running)
                    .filter(|v| target_vm.as_ref().is_none_or(|t| &v.name == t))
                    .collect();

                if running_vms.is_empty() {
                    println!("No running VMs found to sync in '{}'", rg);
                    return Ok(());
                }

                // Collect dotfiles from ~/.azlin/home/
                let dotfiles: Vec<String> = std::fs::read_dir(&home_dir)?
                    .filter_map(|e| e.ok())
                    .map(|e| e.path().display().to_string())
                    .collect();

                if dotfiles.is_empty() {
                    println!("No files found in {}", home_dir.display());
                    return Ok(());
                }

                for vm in &running_vms {
                    if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        println!("Syncing dotfiles to {}...", vm.name);
                        let mut args: Vec<&str> = vec!["-avz", "--progress"];
                        let file_refs: Vec<&str> = dotfiles.iter().map(|s| s.as_str()).collect();
                        args.extend_from_slice(&file_refs);
                        let dest = format!("{}@{}:~/", user, ip);
                        args.push(&dest);
                        let status = std::process::Command::new("rsync").args(&args).status()?;
                        if status.success() {
                            println!("  ✓ {} synced", vm.name);
                        } else {
                            eprintln!("  ✗ {} sync failed", vm.name);
                        }
                    } else {
                        eprintln!("  ✗ {} has no IP address", vm.name);
                    }
                }
                println!("Sync complete.");
            }
        }

        // ── SyncKeys ────────────────────────────────────────────────
        azlin_cli::Commands::SyncKeys {
            vm_name,
            resource_group,
            ssh_user,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            let ssh_dir = home_dir()?.join(".ssh");

            let pub_key = ["id_ed25519_azlin.pub", "id_ed25519.pub", "id_rsa.pub"]
                .iter()
                .map(|f| ssh_dir.join(f))
                .find(|p| p.exists());

            match pub_key {
                Some(key_path) => {
                    let key_content = std::fs::read_to_string(&key_path)?;
                    let output = std::process::Command::new("az")
                        .args([
                            "vm",
                            "user",
                            "update",
                            "--resource-group",
                            &rg,
                            "--name",
                            &vm_name,
                            "--username",
                            &ssh_user,
                            "--ssh-key-value",
                            key_content.trim(),
                        ])
                        .output()?;
                    if output.status.success() {
                        println!("Synced SSH key to VM '{}' for user '{}'", vm_name, ssh_user);
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to sync keys: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                None => {
                    anyhow::bail!("No SSH public key found in {}", ssh_dir.display());
                }
            }
        }

        // ── Cp ───────────────────────────────────────────────────────
        azlin_cli::Commands::Cp {
            args,
            dry_run,
            resource_group,
            ..
        } => {
            if args.len() < 2 {
                eprintln!("Usage: azlin cp <source> <destination>");
                anyhow::bail!("Use vm_name:path for remote paths.");
            }

            let source = &args[0];
            let dest = &args[args.len() - 1];
            let rg = resolve_resource_group(resource_group)?;

            let direction = cp_helpers::classify_transfer_direction(source, dest);

            if dry_run {
                println!(
                    "Would copy ({}) {} → {} (rg: {})",
                    direction, source, dest, rg
                );
            } else {
                println!("Copying ({}) {} → {}...", direction, source, dest);
                // For remote transfers, use scp via az CLI resolved IP
                if cp_helpers::is_remote_path(source) || cp_helpers::is_remote_path(dest) {
                    let (vm_part, _path_part) = if cp_helpers::is_remote_path(source) {
                        source
                            .split_once(':')
                            .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", source))?
                    } else {
                        dest.split_once(':')
                            .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", dest))?
                    };
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vm = vm_manager.get_vm(&rg, vm_part)?;
                    let ip = vm
                        .public_ip
                        .or(vm.private_ip)
                        .ok_or_else(|| anyhow::anyhow!("No IP for VM '{}'", vm_part))?;
                    let user = vm
                        .admin_username
                        .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());

                    let scp_source = if cp_helpers::is_remote_path(source) {
                        cp_helpers::resolve_scp_path(source, vm_part, &user, &ip)
                    } else {
                        source.clone()
                    };
                    let scp_dest = if cp_helpers::is_remote_path(dest) {
                        cp_helpers::resolve_scp_path(dest, vm_part, &user, &ip)
                    } else {
                        dest.clone()
                    };

                    let status = std::process::Command::new("scp")
                        .args([
                            "-o",
                            "StrictHostKeyChecking=accept-new",
                            &scp_source,
                            &scp_dest,
                        ])
                        .status()?;
                    if status.success() {
                        println!("Copy complete.");
                    } else {
                        anyhow::bail!("scp failed.");
                    }
                } else {
                    std::fs::copy(source, dest)?;
                    println!("Copy complete.");
                }
            }
        }

        // ── Logs ─────────────────────────────────────────────────────
        azlin_cli::Commands::Logs {
            vm_identifier,
            lines,
            follow,
            log_type,
            resource_group,
            ..
        } => {
            // Map log types to file paths
            let log_path = match log_type {
                azlin_cli::LogType::CloudInit => "/var/log/cloud-init-output.log",
                azlin_cli::LogType::Syslog => "/var/log/syslog",
                azlin_cli::LogType::Auth => "/var/log/auth.log",
            };

            let target = resolve_vm_ssh_target(&vm_identifier, None, resource_group).await?;

            if follow {
                // Stream logs interactively
                println!("Following {} on {}...", log_path, vm_identifier);
                if let Some(ref b) = target.bastion {
                    // Interactive follow through bastion
                    let mut args = vec![
                        "network".to_string(),
                        "bastion".to_string(),
                        "ssh".to_string(),
                        "--name".to_string(),
                        b.bastion_name.clone(),
                        "--resource-group".to_string(),
                        b.resource_group.clone(),
                        "--target-resource-id".to_string(),
                        b.vm_resource_id.clone(),
                        "--auth-type".to_string(),
                        "ssh-key".to_string(),
                        "--username".to_string(),
                        target.user.clone(),
                    ];
                    if let Some(ref key) = b.ssh_key_path {
                        args.push("--ssh-key".to_string());
                        args.push(key.to_string_lossy().to_string());
                    }
                    args.push("--".to_string());
                    args.push(format!("sudo tail -f {}", log_path));
                    let status = std::process::Command::new("az").args(&args).status()?;
                    if !status.success() {
                        std::process::exit(status.code().unwrap_or(1));
                    }
                } else {
                    let follow_args =
                        connect_helpers::build_log_follow_args(&target.user, &target.ip, log_path);
                    let status = std::process::Command::new("ssh")
                        .args(&follow_args)
                        .status()?;
                    if !status.success() {
                        std::process::exit(status.code().unwrap_or(1));
                    }
                }
            } else {
                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!(
                    "Fetching {:?} logs for {}...",
                    log_type, vm_identifier
                ));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let tail_cmd = format!("sudo tail -n {} {}", lines, log_path);
                let result = target.exec(&tail_cmd);

                pb.finish_and_clear();
                match result {
                    Ok((0, stdout, _stderr)) => {
                        print!("{}", stdout);
                    }
                    Ok((_, _, stderr)) => {
                        anyhow::bail!(
                            "Failed to fetch logs via SSH: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                    Err(e) => {
                        anyhow::bail!("Failed to fetch logs via SSH: {}", e);
                    }
                }
            }
        }

        // ── Costs (intelligence) ─────────────────────────────────────
        azlin_cli::Commands::Costs { action } => {
            match action {
                azlin_cli::CostsAction::Dashboard { resource_group, .. } => {
                    let auth = create_auth()?;
                    let cost_timeout = azlin_core::AzlinConfig::load()
                        .map(|c| c.az_cli_timeout)
                        .unwrap_or(120);
                    match azlin_azure::get_cost_summary(&auth, &resource_group, cost_timeout) {
                        Ok(summary) => {
                            println!(
                                "{}",
                                handlers::format_cost_dashboard(
                                    &resource_group,
                                    summary.total_cost,
                                    &summary.currency,
                                    &summary.period_start.format("%Y-%m-%d").to_string(),
                                    &summary.period_end.format("%Y-%m-%d").to_string(),
                                )
                            );
                        }
                        Err(e) => {
                            eprintln!("⚠ Cost data unavailable: {e}");
                            eprintln!(
                                "  Run 'az consumption usage list' for cost data via Azure CLI."
                            );
                        }
                    }
                }
                azlin_cli::CostsAction::History {
                    resource_group,
                    days,
                } => {
                    let (start_date, end_date) = handlers::build_cost_history_dates(days);

                    // Get subscription ID first
                    let sub_output = std::process::Command::new("az")
                        .args(["account", "show", "--query", "id", "-o", "tsv"])
                        .output()?;
                    let sub_id = String::from_utf8_lossy(&sub_output.stdout)
                        .trim()
                        .to_string();
                    if sub_id.is_empty() {
                        anyhow::bail!("Could not determine subscription ID. Run 'az login' first.");
                    }

                    let scope = handlers::build_cost_management_scope(&sub_id, &resource_group);
                    let output = std::process::Command::new("az")
                        .args([
                            "costmanagement",
                            "query",
                            "--type",
                            "ActualCost",
                            "--scope",
                            &scope,
                            "--timeframe",
                            "Custom",
                            "--time-period",
                            &format!("start={}&end={}", start_date, end_date),
                            "-o",
                            "json",
                        ])
                        .output()?;

                    if output.status.success() {
                        let json_str = String::from_utf8_lossy(&output.stdout);
                        match serde_json::from_str::<serde_json::Value>(&json_str) {
                            Ok(data) => {
                                let mut table = Table::new();
                                table
                                    .load_preset(UTF8_FULL)
                                    .apply_modifier(UTF8_ROUND_CORNERS)
                                    .set_header(vec![
                                        Cell::new("Date").add_attribute(Attribute::Bold),
                                        Cell::new("Cost (USD)").add_attribute(Attribute::Bold),
                                    ]);

                                for (date, cost) in handlers::parse_cost_history_rows(&data) {
                                    table.add_row(vec![Cell::new(&date), Cell::new(&cost)]);
                                }
                                println!(
                                    "Cost history for '{}' (last {} days):",
                                    resource_group, days
                                );
                                println!("{table}");
                            }
                            Err(e) => {
                                eprintln!("Failed to parse cost data: {}", e);
                                println!("{}", json_str);
                            }
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to query cost history: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::CostsAction::Budget {
                    action,
                    resource_group,
                    amount,
                    threshold,
                } => match action.as_str() {
                    "create" | "set" => {
                        let budget_amount = amount.unwrap_or(100.0);
                        let alert_threshold = threshold.unwrap_or(80);
                        let budget_name = handlers::build_budget_name(&resource_group);
                        let output = std::process::Command::new("az")
                            .args([
                                "consumption",
                                "budget",
                                "create",
                                "--budget-name",
                                &budget_name,
                                "--amount",
                                &format!("{:.2}", budget_amount),
                                "--time-grain",
                                "Monthly",
                                "--resource-group",
                                &resource_group,
                                "--category",
                                "Cost",
                                "--output",
                                "json",
                            ])
                            .output()?;
                        if output.status.success() {
                            println!(
                                "{}",
                                handlers::format_budget_created(
                                    budget_amount,
                                    &resource_group,
                                    alert_threshold,
                                )
                            );
                        } else {
                            let stderr = String::from_utf8_lossy(&output.stderr);
                            anyhow::bail!(
                                "Failed to create budget: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                    "show" | "list" => {
                        let output = std::process::Command::new("az")
                            .args([
                                "consumption",
                                "budget",
                                "list",
                                "--resource-group",
                                &resource_group,
                                "--output",
                                "table",
                            ])
                            .output()?;
                        if output.status.success() {
                            let text = String::from_utf8_lossy(&output.stdout);
                            if text.trim().is_empty() {
                                println!("No budgets found for '{}'.", resource_group);
                            } else {
                                print!("{}", text);
                            }
                        } else {
                            let stderr = String::from_utf8_lossy(&output.stderr);
                            eprintln!(
                                "Failed to list budgets: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                    "delete" => {
                        let budget_name = handlers::build_budget_name(&resource_group);
                        let output = std::process::Command::new("az")
                            .args([
                                "consumption",
                                "budget",
                                "delete",
                                "--budget-name",
                                &budget_name,
                                "--resource-group",
                                &resource_group,
                            ])
                            .output()?;
                        if output.status.success() {
                            println!("Budget deleted for '{}'.", resource_group);
                        } else {
                            let stderr = String::from_utf8_lossy(&output.stderr);
                            eprintln!(
                                "Failed to delete budget: {}",
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                    _ => {
                        anyhow::bail!(
                            "Unknown budget action '{}'. Use: create, show, delete",
                            action
                        );
                    }
                },
                azlin_cli::CostsAction::Recommend {
                    resource_group,
                    priority,
                } => {
                    let mut cmd_args = vec![
                        "advisor".to_string(),
                        "recommendation".to_string(),
                        "list".to_string(),
                        "--resource-group".to_string(),
                        resource_group.clone(),
                        "-o".to_string(),
                        "json".to_string(),
                    ];
                    if let Some(ref pri) = priority {
                        cmd_args.push("--query".to_string());
                        cmd_args.push(format!("[?impact=='{}']", pri));
                    }
                    let output = std::process::Command::new("az").args(&cmd_args).output()?;

                    if output.status.success() {
                        let json_str = String::from_utf8_lossy(&output.stdout);
                        match serde_json::from_str::<serde_json::Value>(&json_str) {
                            Ok(data) => {
                                if let Some(recs) = data.as_array() {
                                    if recs.is_empty() {
                                        let pri = priority.unwrap_or_else(|| "all".to_string());
                                        println!(
                                            "No cost recommendations found for '{}' (priority: {})",
                                            resource_group, pri
                                        );
                                    } else {
                                        let mut table = Table::new();
                                        table
                                            .load_preset(UTF8_FULL)
                                            .apply_modifier(UTF8_ROUND_CORNERS)
                                            .set_header(vec![
                                                Cell::new("Category")
                                                    .add_attribute(Attribute::Bold),
                                                Cell::new("Impact").add_attribute(Attribute::Bold),
                                                Cell::new("Problem").add_attribute(Attribute::Bold),
                                            ]);
                                        for (category, impact, problem) in
                                            handlers::parse_recommendation_rows(&data)
                                        {
                                            table.add_row(vec![
                                                Cell::new(&category),
                                                Cell::new(&impact),
                                                Cell::new(&problem),
                                            ]);
                                        }
                                        println!("Cost recommendations for '{}':", resource_group);
                                        println!("{table}");
                                    }
                                }
                            }
                            Err(e) => eprintln!("Failed to parse advisor data: {}", e),
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to list recommendations: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
                azlin_cli::CostsAction::Actions {
                    action,
                    resource_group,
                    dry_run,
                    ..
                } => {
                    let output = std::process::Command::new("az")
                        .args([
                            "advisor",
                            "recommendation",
                            "list",
                            "--resource-group",
                            &resource_group,
                            "--query",
                            "[?category=='Cost']",
                            "-o",
                            "json",
                        ])
                        .output()?;

                    if output.status.success() {
                        let json_str = String::from_utf8_lossy(&output.stdout);
                        match serde_json::from_str::<serde_json::Value>(&json_str) {
                            Ok(data) => {
                                if let Some(recs) = data.as_array() {
                                    if recs.is_empty() {
                                        println!("No pending cost actions in '{}'", resource_group);
                                    } else {
                                        let mut table = Table::new();
                                        table
                                            .load_preset(UTF8_FULL)
                                            .apply_modifier(UTF8_ROUND_CORNERS)
                                            .set_header(vec![
                                                Cell::new("Resource")
                                                    .add_attribute(Attribute::Bold),
                                                Cell::new("Impact").add_attribute(Attribute::Bold),
                                                Cell::new("Recommendation")
                                                    .add_attribute(Attribute::Bold),
                                            ]);
                                        for (resource, impact, problem) in
                                            handlers::parse_cost_action_rows(&data)
                                        {
                                            table.add_row(vec![
                                                Cell::new(&resource),
                                                Cell::new(&impact),
                                                Cell::new(&problem),
                                            ]);
                                        }
                                        if dry_run {
                                            println!(
                                                "Would {} the following cost actions in '{}':",
                                                action, resource_group
                                            );
                                        } else {
                                            println!(
                                                "Cost actions ({}) in '{}':",
                                                action, resource_group
                                            );
                                        }
                                        println!("{table}");
                                        // Apply actions if not dry-run
                                        if !dry_run && action == "apply" {
                                            println!("\nApplying cost recommendations...");
                                            for rec in recs {
                                                let resource_id = rec
                                                    .get("resourceMetadata")
                                                    .and_then(|rm| rm.get("resourceId"))
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("");
                                                let impact = rec
                                                    .get("impact")
                                                    .and_then(|v| v.as_str())
                                                    .unwrap_or("");
                                                if !resource_id.is_empty()
                                                    && resource_id.contains("virtualMachines")
                                                {
                                                    println!(
                                                        "  Deallocating idle VM: {} (impact: {})",
                                                        resource_id, impact
                                                    );
                                                    match std::process::Command::new("az")
                                                        .args([
                                                            "vm",
                                                            "deallocate",
                                                            "--ids",
                                                            resource_id,
                                                        ])
                                                        .output()
                                                    {
                                                        Ok(output) if output.status.success() => {
                                                            println!(
                                                                "  ✓ Deallocated successfully"
                                                            );
                                                        }
                                                        Ok(output) => {
                                                            eprintln!(
                                                                "  ✗ Failed to deallocate: {}",
                                                                String::from_utf8_lossy(
                                                                    &output.stderr
                                                                )
                                                                .trim()
                                                            );
                                                        }
                                                        Err(e) => {
                                                            eprintln!(
                                                                "  ✗ Failed to run az: {}",
                                                                e
                                                            );
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            Err(e) => eprintln!("Failed to parse advisor data: {}", e),
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        anyhow::bail!(
                            "Failed to list cost actions: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
            }
        }

        // ── Killall ──────────────────────────────────────────────────
        azlin_cli::Commands::Killall {
            resource_group,
            force,
            prefix,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;
            if !force {
                let ok = Confirm::new()
                    .with_prompt(format!(
                        "Delete ALL VMs with prefix '{}' in '{}'? This cannot be undone.",
                        prefix, rg
                    ))
                    .default(false)
                    .interact()?;
                if !ok {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Deleting VMs with prefix '{}'...", prefix));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let output = std::process::Command::new("az")
                .args([
                    "vm",
                    "list",
                    "--resource-group",
                    &rg,
                    "--query",
                    &format!("[?starts_with(name, '{}')].id", prefix),
                    "--output",
                    "tsv",
                ])
                .output()?;

            if output.status.success() {
                let ids = String::from_utf8_lossy(&output.stdout);
                let id_list: Vec<&str> = ids.lines().filter(|l| !l.is_empty()).collect();
                if id_list.is_empty() {
                    pb.finish_and_clear();
                    println!("No VMs found with prefix '{}'", prefix);
                } else {
                    let del = std::process::Command::new("az")
                        .args(["vm", "delete", "--ids"])
                        .args(&id_list)
                        .args(["--yes"])
                        .output()?;
                    pb.finish_and_clear();
                    if del.status.success() {
                        println!("Deleted {} VMs with prefix '{}'", id_list.len(), prefix);
                    } else {
                        let stderr = String::from_utf8_lossy(&del.stderr);
                        anyhow::bail!(
                            "Failed to delete VMs: {}",
                            azlin_core::sanitizer::sanitize(stderr.trim())
                        );
                    }
                }
            } else {
                pb.finish_and_clear();
                anyhow::bail!("Failed to list VMs.");
            }
        }

        // ── Cleanup / Prune ──────────────────────────────────────────
        azlin_cli::Commands::Cleanup {
            resource_group,
            dry_run,
            force,
            age_days,
            ..
        } => {
            use azlin_azure::orphan_detector::{
                find_orphaned_disks, format_orphan_summary, OrphanedResource, ResourceType,
            };

            let rg = resolve_resource_group(resource_group)?;

            println!(
                "{}Scanning for orphaned resources in '{}' (older than {} days)...",
                if dry_run { "Dry run — " } else { "" },
                rg,
                age_days
            );

            // Helper: run an az CLI query and return stdout as String
            let az_list = |args: &[&str]| -> Result<String> {
                let output = std::process::Command::new("az")
                    .args(args)
                    .args(["-g", &rg, "-o", "json"])
                    .output()?;
                if !output.status.success() {
                    let err = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "az command failed: {}",
                        azlin_core::sanitizer::sanitize(err.trim())
                    );
                }
                Ok(String::from_utf8_lossy(&output.stdout).to_string())
            };

            let mut all_orphans: Vec<OrphanedResource> = Vec::new();

            // 1) Orphaned disks
            let disk_json =
                az_list(&["disk", "list"]).context("Failed to list disks for orphan detection")?;
            all_orphans.extend(find_orphaned_disks(&disk_json)?);

            // 2) Orphaned NICs (no VM attached)
            let nic_json = az_list(&["network", "nic", "list"])
                .context("Failed to list NICs for orphan detection")?;
            let nics: Vec<serde_json::Value> =
                serde_json::from_str(&nic_json).context("Failed to parse NIC list JSON")?;
            for nic in &nics {
                let attached = nic
                    .get("virtualMachine")
                    .map(|v| !v.is_null())
                    .unwrap_or(false);
                if !attached {
                    if let Some(name) = nic.get("name").and_then(|n| n.as_str()) {
                        let nic_rg = nic
                            .get("resourceGroup")
                            .and_then(|r| r.as_str())
                            .unwrap_or("unknown");
                        all_orphans.push(OrphanedResource {
                            name: name.to_string(),
                            resource_type: ResourceType::NetworkInterface,
                            resource_group: nic_rg.to_string(),
                            estimated_monthly_cost: 0.0,
                        });
                    }
                }
            }

            // 3) Orphaned public IPs (no ipConfiguration)
            let pip_json = az_list(&["network", "public-ip", "list"])
                .context("Failed to list public IPs for orphan detection")?;
            let ips: Vec<serde_json::Value> =
                serde_json::from_str(&pip_json).context("Failed to parse public IP list JSON")?;
            for ip in &ips {
                let attached = ip
                    .get("ipConfiguration")
                    .map(|v| !v.is_null())
                    .unwrap_or(false);
                if !attached {
                    if let Some(name) = ip.get("name").and_then(|n| n.as_str()) {
                        let ip_rg = ip
                            .get("resourceGroup")
                            .and_then(|r| r.as_str())
                            .unwrap_or("unknown");
                        all_orphans.push(OrphanedResource {
                            name: name.to_string(),
                            resource_type: ResourceType::PublicIp,
                            resource_group: ip_rg.to_string(),
                            // Azure Standard public IP ~$3.65/month
                            estimated_monthly_cost: ORPHANED_PUBLIC_IP_MONTHLY_COST,
                        });
                    }
                }
            }

            // 4) Orphaned NSGs (no attached NICs or subnets)
            let nsg_json = az_list(&["network", "nsg", "list"])
                .context("Failed to list NSGs for orphan detection")?;
            let nsgs: Vec<serde_json::Value> =
                serde_json::from_str(&nsg_json).context("Failed to parse NSG list JSON")?;
            for nsg in &nsgs {
                let has_nics = nsg
                    .get("networkInterfaces")
                    .and_then(|v| v.as_array())
                    .map(|a| !a.is_empty())
                    .unwrap_or(false);
                let has_subnets = nsg
                    .get("subnets")
                    .and_then(|v| v.as_array())
                    .map(|a| !a.is_empty())
                    .unwrap_or(false);
                if !has_nics && !has_subnets {
                    if let Some(name) = nsg.get("name").and_then(|n| n.as_str()) {
                        let nsg_rg = nsg
                            .get("resourceGroup")
                            .and_then(|r| r.as_str())
                            .unwrap_or("unknown");
                        all_orphans.push(OrphanedResource {
                            name: name.to_string(),
                            resource_type: ResourceType::NetworkSecurityGroup,
                            resource_group: nsg_rg.to_string(),
                            estimated_monthly_cost: 0.0,
                        });
                    }
                }
            }

            if all_orphans.is_empty() {
                println!("{}", format_orphan_summary(&[]));
                return Ok(());
            }

            // Display findings in a table
            let mut table = Table::new();
            table
                .load_preset(UTF8_FULL)
                .apply_modifier(UTF8_ROUND_CORNERS)
                .set_header(vec![
                    Cell::new("Type").add_attribute(Attribute::Bold),
                    Cell::new("Name").add_attribute(Attribute::Bold),
                    Cell::new("Resource Group").add_attribute(Attribute::Bold),
                    Cell::new("Est. Cost/mo").add_attribute(Attribute::Bold),
                ]);
            for r in &all_orphans {
                table.add_row(vec![
                    Cell::new(format!("{}", r.resource_type)),
                    Cell::new(&r.name),
                    Cell::new(&r.resource_group),
                    Cell::new(format!("${:.2}", r.estimated_monthly_cost)),
                ]);
            }
            println!("{table}");
            println!("{}", format_orphan_summary(&all_orphans));

            if dry_run {
                println!("Dry run complete — no resources were deleted.");
                return Ok(());
            }

            if !force {
                let ok = Confirm::new()
                    .with_prompt(format!(
                        "Delete {} orphaned resource(s) in '{}'?",
                        all_orphans.len(),
                        rg
                    ))
                    .default(false)
                    .interact()?;
                if !ok {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            // Delete orphaned resources
            let mut deleted = 0usize;
            for r in &all_orphans {
                let result = match r.resource_type {
                    ResourceType::Disk => std::process::Command::new("az")
                        .args([
                            "disk",
                            "delete",
                            "--name",
                            &r.name,
                            "-g",
                            &r.resource_group,
                            "--yes",
                            "--no-wait",
                        ])
                        .output(),
                    ResourceType::NetworkInterface => std::process::Command::new("az")
                        .args([
                            "network",
                            "nic",
                            "delete",
                            "--name",
                            &r.name,
                            "-g",
                            &r.resource_group,
                            "--no-wait",
                        ])
                        .output(),
                    ResourceType::PublicIp => std::process::Command::new("az")
                        .args([
                            "network",
                            "public-ip",
                            "delete",
                            "--name",
                            &r.name,
                            "-g",
                            &r.resource_group,
                        ])
                        .output(),
                    ResourceType::NetworkSecurityGroup => std::process::Command::new("az")
                        .args([
                            "network",
                            "nsg",
                            "delete",
                            "--name",
                            &r.name,
                            "-g",
                            &r.resource_group,
                        ])
                        .output(),
                };
                match result {
                    Ok(o) if o.status.success() => {
                        deleted += 1;
                        println!("  ✓ Deleted {} '{}'", r.resource_type, r.name);
                    }
                    Ok(o) => {
                        let err = String::from_utf8_lossy(&o.stderr);
                        eprintln!(
                            "  ✗ Failed to delete {} '{}': {}",
                            r.resource_type,
                            r.name,
                            err.trim()
                        );
                    }
                    Err(e) => {
                        eprintln!(
                            "  ✗ Failed to delete {} '{}': {}",
                            r.resource_type, r.name, e
                        );
                    }
                }
            }
            println!(
                "Cleanup complete. Deleted {}/{} orphaned resources.",
                deleted,
                all_orphans.len()
            );
        }

        // ── Help ─────────────────────────────────────────────────────
        // ── Bastion ───────────────────────────────────────────────────
        azlin_cli::Commands::Bastion { action } => match action {
            azlin_cli::BastionAction::List { resource_group } => {
                println!("Listing Bastion hosts...");
                let mut cmd = std::process::Command::new("az");
                cmd.args(["network", "bastion", "list", "-o", "json"]);
                if let Some(rg) = &resource_group {
                    cmd.args(["--resource-group", rg]);
                }
                let output = cmd.output()?;
                if !output.status.success() {
                    let err = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Error listing Bastion hosts: {}",
                        azlin_core::sanitizer::sanitize(&err)
                    );
                }
                let bastions: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)
                    .context("Failed to parse Bastion host list JSON")?;
                if bastions.is_empty() {
                    if let Some(rg) = &resource_group {
                        println!("No Bastion hosts found in resource group: {}", rg);
                    } else {
                        println!("No Bastion hosts found in subscription");
                    }
                } else {
                    println!("\nFound {} Bastion host(s):\n", bastions.len());
                    for b in &bastions {
                        let (name, rg, location, sku, state) = bastion_helpers::bastion_summary(b);
                        println!("  {}", name);
                        println!("    Resource Group: {}", rg);
                        println!("    Location: {}", location);
                        println!("    SKU: {}", sku);
                        println!("    State: {}", state);
                        println!();
                    }
                }
            }
            azlin_cli::BastionAction::Status {
                name,
                resource_group,
            } => {
                println!("Checking Bastion host: {}...", name);
                let output = std::process::Command::new("az")
                    .args([
                        "network",
                        "bastion",
                        "show",
                        "--name",
                        &name,
                        "--resource-group",
                        &resource_group,
                        "-o",
                        "json",
                    ])
                    .output()?;
                if !output.status.success() {
                    let err = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Bastion host not found: {} in {}: {}",
                        name,
                        resource_group,
                        azlin_core::sanitizer::sanitize(&err)
                    );
                }
                let b: serde_json::Value = serde_json::from_slice(&output.stdout)?;
                println!(
                    "\nBastion Host: {}",
                    b["name"].as_str().unwrap_or("unknown")
                );
                println!(
                    "Resource Group: {}",
                    b["resourceGroup"].as_str().unwrap_or("unknown")
                );
                println!("Location: {}", b["location"].as_str().unwrap_or("unknown"));
                println!("SKU: {}", b["sku"]["name"].as_str().unwrap_or("Standard"));
                println!(
                    "Provisioning State: {}",
                    b["provisioningState"].as_str().unwrap_or("Unknown")
                );
                println!("DNS Name: {}", b["dnsName"].as_str().unwrap_or("N/A"));
                let ip_config_list = bastion_helpers::extract_ip_configs(&b);
                if !ip_config_list.is_empty() {
                    println!("\nIP Configurations: {}", ip_config_list.len());
                    for (idx, (subnet_short, pip_short)) in ip_config_list.iter().enumerate() {
                        println!("  [{}] Subnet: {}", idx + 1, subnet_short);
                        println!("      Public IP: {}", pip_short);
                    }
                }
            }
            azlin_cli::BastionAction::Configure {
                vm_name,
                bastion_name,
                resource_group,
                bastion_resource_group,
                disable,
            } => {
                let vm_rg = resolve_resource_group(resource_group)?;
                let bastion_rg = bastion_resource_group.unwrap_or_else(|| vm_rg.clone());

                let config_dir = home_dir()?.join(".azlin");
                std::fs::create_dir_all(&config_dir)?;
                let config_path = config_dir.join("bastion_config.json");

                let mut config: serde_json::Value = if config_path.exists() {
                    let data = std::fs::read_to_string(&config_path)?;
                    serde_json::from_str(&data).unwrap_or(serde_json::json!({"mappings": {}}))
                } else {
                    serde_json::json!({"mappings": {}})
                };

                let mappings = config["mappings"]
                    .as_object_mut()
                    .ok_or_else(|| anyhow::anyhow!("Invalid bastion config format"))?;

                if disable {
                    mappings.remove(&vm_name);
                    std::fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
                    println!("✓ Disabled Bastion mapping for: {}", vm_name);
                } else {
                    mappings.insert(
                        vm_name.clone(),
                        serde_json::json!({
                            "bastion_name": bastion_name,
                            "vm_resource_group": vm_rg,
                            "bastion_resource_group": bastion_rg,
                        }),
                    );
                    std::fs::write(&config_path, serde_json::to_string_pretty(&config)?)?;
                    println!("✓ Configured {} to use Bastion: {}", vm_name, bastion_name);
                    println!("  VM RG: {}", vm_rg);
                    println!("  Bastion RG: {}", bastion_rg);
                    println!("\nConnection will now route through Bastion automatically.");
                }
            }
        },

        azlin_cli::Commands::Completions { shell } => {
            let mut cmd = azlin_cli::Cli::command();
            clap_complete::generate(shell, &mut cmd, "azlin", &mut std::io::stdout());
        }
        azlin_cli::Commands::AzlinHelp { command_name } => {
            println!("{}", handlers::build_extended_help(command_name.as_deref()));
        }
    }

    Ok(())
}

fn create_auth() -> Result<azlin_azure::AzureAuth> {
    azlin_azure::AzureAuth::new().map_err(|e| {
        anyhow::anyhow!(
            "Azure authentication failed: {e}\n\
             Run 'az login' to authenticate with Azure CLI."
        )
    })
}

fn resolve_resource_group(explicit: Option<String>) -> Result<String> {
    if let Some(rg) = explicit {
        return Ok(rg);
    }
    let config = azlin_core::AzlinConfig::load().context("Failed to load azlin config")?;
    config.default_resource_group.ok_or_else(|| {
        anyhow::anyhow!(
            "No resource group specified. Use --resource-group or set via:\n  \
             azlin config set default_resource_group <your-rg>"
        )
    })
}

/// Get the user's home directory, returning a clear error on failure.
fn home_dir() -> Result<std::path::PathBuf> {
    dirs::home_dir().ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))
}

/// Escape a value for safe inclusion in a shell command.
fn shell_escape(s: &str) -> String {
    let mut escaped = String::with_capacity(s.len() + 2);
    escaped.push('\'');
    for c in s.chars() {
        if c == '\'' {
            escaped.push_str("'\\''");
        } else {
            escaped.push(c);
        }
    }
    escaped.push('\'');
    escaped
}

/// Resolve a single VM to a `VmSshTarget`, using --ip flag if provided.
/// Routes through bastion automatically for private-IP-only VMs.
async fn resolve_vm_ssh_target(
    vm_name: &str,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<VmSshTarget> {
    if let Some(ip) = ip_flag {
        return Ok(VmSshTarget {
            vm_name: vm_name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
            bastion: None,
        });
    }
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let vm = vm_manager.get_vm(&rg, vm_name)?;
    let bastion_map: std::collections::HashMap<String, String> =
        list_helpers::detect_bastion_hosts(&rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();
    let ssh_key = resolve_ssh_key();
    let target = build_ssh_target(&vm, vm_manager.subscription_id(), &bastion_map, &ssh_key);
    if target.ip.is_empty() {
        anyhow::bail!("No IP address found for VM '{}'", vm_name);
    }
    Ok(target)
}

/// Resolve targets for W/Ps/Top: single VM (--vm/--ip) or all VMs via Azure.
/// Returns `Vec<VmSshTarget>` with bastion routing for private-IP-only VMs.
async fn resolve_vm_targets(
    vm_flag: Option<&str>,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<Vec<VmSshTarget>> {
    if let Some(ip) = ip_flag {
        let name = vm_flag.unwrap_or(ip);
        return Ok(vec![VmSshTarget {
            vm_name: name.to_string(),
            ip: ip.to_string(),
            user: DEFAULT_ADMIN_USERNAME.to_string(),
            bastion: None,
        }]);
    }
    if let Some(vm_name) = vm_flag {
        let auth = create_auth()?;
        let vm_manager = azlin_azure::VmManager::new(&auth);
        let rg = resolve_resource_group(resource_group)?;
        let vm = vm_manager.get_vm(&rg, vm_name)?;
        let bastion_map: std::collections::HashMap<String, String> =
            list_helpers::detect_bastion_hosts(&rg)
                .unwrap_or_default()
                .into_iter()
                .map(|(name, location, _)| (location, name))
                .collect();
        let ssh_key = resolve_ssh_key();
        let target = build_ssh_target(&vm, vm_manager.subscription_id(), &bastion_map, &ssh_key);
        if target.ip.is_empty() {
            anyhow::bail!("No IP address found for VM '{}'", vm_name);
        }
        return Ok(vec![target]);
    }
    // List all running VMs
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let bastion_map: std::collections::HashMap<String, String> =
        list_helpers::detect_bastion_hosts(&rg)
            .unwrap_or_default()
            .into_iter()
            .map(|(name, location, _)| (location, name))
            .collect();
    let sub_id = vm_manager.subscription_id().to_string();
    let ssh_key = resolve_ssh_key();
    let vms = vm_manager.list_vms(&rg)?;
    let mut targets = Vec::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        if vm.public_ip.is_none() && vm.private_ip.is_none() {
            continue;
        }
        targets.push(build_ssh_target(&vm, &sub_id, &bastion_map, &ssh_key));
    }
    if targets.is_empty() {
        anyhow::bail!("No running VMs found. Use --vm or --ip to target a specific VM.");
    }
    Ok(targets)
}

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
mod name_validation {
    /// Reject names containing path-traversal or null-byte characters.
    ///
    /// A valid name consists only of ASCII alphanumerics, hyphens, underscores,
    /// and dots (but not `..`).  No slashes, backslashes, or null bytes.
    pub fn validate_name(name: &str) -> Result<(), String> {
        if name.is_empty() {
            return Err("Name must not be empty".into());
        }
        if name.contains('/') || name.contains('\\') {
            return Err(format!(
                "Name '{}' contains path separator characters",
                name
            ));
        }
        if name.contains('\0') {
            return Err(format!("Name '{}' contains a null byte", name));
        }
        if name.contains("..") {
            return Err(format!("Name '{}' contains '..' (path traversal)", name));
        }
        Ok(())
    }
}

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
mod sync_helpers {
    /// The default set of dotfiles synchronised to VMs.
    pub fn default_dotfiles() -> Vec<&'static str> {
        vec![".bashrc", ".profile", ".vimrc", ".tmux.conf", ".gitconfig"]
    }

    /// Validate that a sync source path is safe (no absolute paths to sensitive
    /// system files, no traversal outside the user's home).
    pub fn validate_sync_source(source: &str) -> Result<(), String> {
        // Reject paths that reference sensitive system directories directly
        let forbidden_prefixes = ["/etc/", "/var/", "/root/", "/proc/", "/sys/"];
        for prefix in &forbidden_prefixes {
            if source.starts_with(prefix) {
                return Err(format!(
                    "Sync source '{}' references a sensitive system path",
                    source
                ));
            }
        }
        // Reject path-traversal sequences that escape the intended directory
        if source.contains("/../") || source.ends_with("/..") || source == ".." {
            return Err(format!("Sync source '{}' contains path traversal", source));
        }
        Ok(())
    }

    /// Build the argument list for an rsync invocation.
    pub fn build_rsync_args(source: &str, user: &str, ip: &str, dest: &str) -> Vec<String> {
        vec![
            "-az".to_string(),
            "-e".to_string(),
            "ssh -o StrictHostKeyChecking=accept-new".to_string(),
            source.to_string(),
            format!("{}@{}:~/{}", user, ip, dest),
        ]
    }
}

/// Helpers for health-metric display — pure functions over numeric data.
mod health_helpers {
    /// Pick a colour name for a utilisation percentage.
    #[allow(dead_code)]
    pub fn metric_color(pct: f32) -> &'static str {
        if pct > 80.0 {
            "red"
        } else if pct > 50.0 {
            "yellow"
        } else {
            "green"
        }
    }

    /// Pick a colour name for a VM power-state string.
    #[allow(dead_code)]
    pub fn state_color(state: &str) -> &'static str {
        match state {
            "running" => "green",
            "stopped" | "deallocated" => "red",
            _ => "yellow",
        }
    }

    /// Format a metric value as `"xx.x%"`, clamping negatives to 0.
    pub fn format_percentage(value: f32) -> String {
        let clamped = if value < 0.0 { 0.0 } else { value };
        format!("{:.1}%", clamped)
    }

    /// Return a status emoji summarising overall health.
    #[allow(dead_code)]
    pub fn status_emoji(cpu: f32, mem: f32, disk: f32) -> &'static str {
        if cpu > 90.0 || mem > 90.0 || disk > 90.0 {
            "🔴"
        } else if cpu > 70.0 || mem > 70.0 || disk > 70.0 {
            "🟡"
        } else {
            "🟢"
        }
    }
}

/// Helpers for the `azlin snapshot` subcommands.
#[allow(dead_code)]
mod snapshot_helpers;

/// Generic output-format helpers (JSON / CSV / plain table).
#[allow(dead_code)]
mod output_helpers {
    /// Render `rows` as CSV text with a header line.
    pub fn format_as_csv(headers: &[&str], rows: &[Vec<String>]) -> String {
        let mut out = headers.join(",");
        for row in rows {
            out.push('\n');
            out.push_str(&row.join(","));
        }
        out
    }

    /// Render `rows` as a simple aligned-column table.
    pub fn format_as_table(headers: &[&str], rows: &[Vec<String>]) -> String {
        let ncols = headers.len();
        let mut widths: Vec<usize> = headers.iter().map(|h| h.len()).collect();
        for row in rows {
            for (i, cell) in row.iter().enumerate() {
                if i < ncols && cell.len() > widths[i] {
                    widths[i] = cell.len();
                }
            }
        }
        let mut out = String::new();
        for (i, h) in headers.iter().enumerate() {
            if i > 0 {
                out.push_str("  ");
            }
            out.push_str(&format!("{:<width$}", h, width = widths[i]));
        }
        for row in rows {
            out.push('\n');
            for (i, cell) in row.iter().enumerate() {
                if i > 0 {
                    out.push_str("  ");
                }
                let w = if i < ncols { widths[i] } else { cell.len() };
                out.push_str(&format!("{:<width$}", cell, width = w));
            }
        }
        out
    }

    /// Serialize a slice to pretty-printed JSON. Returns an error string on failure.
    pub fn format_as_json<T: serde::Serialize>(items: &[T]) -> String {
        serde_json::to_string_pretty(items).unwrap_or_else(|e| format!("JSON error: {e}"))
    }
}

/// VM name validation — enforces Azure naming constraints.
#[allow(dead_code)]
mod vm_validation {
    /// Azure VM names: 1-64 chars, alphanumeric and hyphens, no leading/trailing hyphen.
    pub fn validate_vm_name(name: &str) -> Result<(), String> {
        if name.is_empty() {
            return Err("VM name must not be empty".into());
        }
        if name.len() > 64 {
            return Err(format!(
                "VM name '{}' exceeds 64 character limit (got {})",
                &name[..32],
                name.len()
            ));
        }
        if name.starts_with('-') {
            return Err(format!("VM name '{}' must not start with a hyphen", name));
        }
        if name.ends_with('-') {
            return Err(format!("VM name '{}' must not end with a hyphen", name));
        }
        if !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
            return Err(format!(
                "VM name '{}' contains invalid characters; only [a-zA-Z0-9-] allowed",
                name
            ));
        }
        Ok(())
    }
}

/// Mount path validation — prevents command injection in mount operations.
#[allow(dead_code)]
mod mount_helpers {
    /// Validate a mount-point path is safe (no shell metacharacters, no traversal).
    pub fn validate_mount_path(path: &str) -> Result<(), String> {
        if path.is_empty() {
            return Err("Mount path must not be empty".into());
        }
        if !path.starts_with('/') {
            return Err(format!("Mount path '{}' must be absolute", path));
        }
        // Reject shell metacharacters
        let bad_chars = [
            ';', '|', '&', '$', '`', '(', ')', '{', '}', '<', '>', '!', '\n', '\0',
        ];
        for c in bad_chars {
            if path.contains(c) {
                return Err(format!(
                    "Mount path '{}' contains dangerous character '{}'",
                    path, c
                ));
            }
        }
        // Reject traversal
        if path.contains("/../") || path.ends_with("/..") || path == ".." {
            return Err(format!("Mount path '{}' contains path traversal", path));
        }
        Ok(())
    }
}

/// Config path validation — prevents traversal attacks on config file loading.
#[allow(dead_code)]
mod config_path_helpers {
    use std::path::Path;

    /// Validate a config file path doesn't escape the expected config directory.
    pub fn validate_config_path(path: &str) -> Result<(), String> {
        let p = Path::new(path);
        // Reject traversal components
        for component in p.components() {
            if let std::path::Component::ParentDir = component {
                return Err(format!(
                    "Config path '{}' contains parent directory traversal",
                    path
                ));
            }
        }
        Ok(())
    }
}

/// Helpers for storage account operations — SKU resolution and row extraction.
#[allow(dead_code)]
mod storage_helpers {
    /// Map a user-facing storage tier string to the Azure SKU name.
    pub fn storage_sku_from_tier(tier: &str) -> &'static str {
        match tier.to_lowercase().as_str() {
            "premium" => "Premium_LRS",
            "standard" => "Standard_LRS",
            _ => "Premium_LRS",
        }
    }

    /// Extract display columns from a storage account JSON value.
    pub fn storage_account_row(acct: &serde_json::Value) -> Vec<String> {
        vec![
            acct["name"].as_str().unwrap_or("-").to_string(),
            acct["location"].as_str().unwrap_or("-").to_string(),
            acct["kind"].as_str().unwrap_or("-").to_string(),
            acct["sku"]["name"].as_str().unwrap_or("-").to_string(),
            acct["provisioningState"]
                .as_str()
                .unwrap_or("-")
                .to_string(),
        ]
    }
}

/// Helpers for SSH key file classification and type detection.
#[allow(dead_code)]
mod key_helpers {
    /// Detect the SSH key type from a filename.
    pub fn detect_key_type(name: &str) -> &'static str {
        if name.contains("ed25519") {
            "ed25519"
        } else if name.contains("ecdsa") {
            "ecdsa"
        } else if name.contains("rsa") {
            "rsa"
        } else if name.contains("dsa") {
            "dsa"
        } else {
            "unknown"
        }
    }

    /// Determine whether a filename looks like an SSH key (without filesystem checks).
    /// Returns true for `.pub` files and known private key names.
    pub fn is_known_key_name(name: &str) -> bool {
        name.ends_with(".pub") || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name)
    }
}

/// Helpers for auth profile display — masking secrets.
#[allow(dead_code)]
mod auth_helpers {
    /// Return a display-safe representation of a profile field value.
    /// Secrets (fields whose key contains "secret" or "password") are masked.
    pub fn mask_profile_value(key: &str, value: &serde_json::Value) -> String {
        match value {
            serde_json::Value::String(s) => {
                if key.contains("secret") || key.contains("password") {
                    "********".to_string()
                } else {
                    s.clone()
                }
            }
            other => other.to_string(),
        }
    }
}

/// Helpers for `azlin cp` — remote path detection and SCP path rewriting.
#[allow(dead_code)]
mod cp_helpers {
    /// Check whether a path string refers to a remote VM (e.g. `vm-name:/path`).
    pub fn is_remote_path(s: &str) -> bool {
        s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
    }

    /// Classify the transfer direction based on source and destination strings.
    pub fn classify_transfer_direction(source: &str, dest: &str) -> &'static str {
        if is_remote_path(source) && !is_remote_path(dest) {
            "remote→local"
        } else if !is_remote_path(source) && is_remote_path(dest) {
            "local→remote"
        } else {
            "local→local"
        }
    }

    /// Rewrite a `vm_name:path` string to `user@ip:path` for SCP.
    pub fn resolve_scp_path(path: &str, vm_part: &str, user: &str, ip: &str) -> String {
        path.replacen(vm_part, &format!("{}@{}", user, ip), 1)
    }
}

/// Helpers for Bastion host JSON extraction.
#[allow(dead_code)]
mod bastion_helpers {
    /// Extract display fields from a Bastion host JSON value.
    pub fn bastion_summary(b: &serde_json::Value) -> (String, String, String, String, String) {
        (
            b["name"].as_str().unwrap_or("unknown").to_string(),
            b["resourceGroup"].as_str().unwrap_or("unknown").to_string(),
            b["location"].as_str().unwrap_or("unknown").to_string(),
            b["sku"]["name"].as_str().unwrap_or("Standard").to_string(),
            b["provisioningState"]
                .as_str()
                .unwrap_or("unknown")
                .to_string(),
        )
    }

    /// Extract the short name from the end of an Azure resource ID.
    pub fn shorten_resource_id(id: &str) -> &str {
        if id == "N/A" {
            return "N/A";
        }
        id.rsplit('/').next().unwrap_or("N/A")
    }

    /// Extract IP configuration details from a Bastion JSON value.
    /// Returns Vec of (subnet_short, public_ip_short).
    pub fn extract_ip_configs(b: &serde_json::Value) -> Vec<(String, String)> {
        let mut result = Vec::new();
        if let Some(configs) = b["ipConfigurations"].as_array() {
            for config in configs {
                let subnet_id = config["subnet"]["id"].as_str().unwrap_or("N/A");
                let public_ip_id = config["publicIPAddress"]["id"].as_str().unwrap_or("N/A");
                result.push((
                    shorten_resource_id(subnet_id).to_string(),
                    shorten_resource_id(public_ip_id).to_string(),
                ));
            }
        }
        result
    }
}

/// Helpers for log tail computation.
#[allow(dead_code)]
mod log_helpers {
    /// Compute the start index for tailing `count` lines from a total of `total` lines.
    pub fn tail_start_index(total: usize, count: usize) -> usize {
        total.saturating_sub(count)
    }
}

/// Helpers for auth test result extraction.
#[allow(dead_code)]
mod auth_test_helpers {
    /// Extract subscription, tenant, and user from an `az account show` JSON response.
    pub fn extract_account_info(acct: &serde_json::Value) -> (String, String, String) {
        (
            acct["name"].as_str().unwrap_or("-").to_string(),
            acct["tenantId"].as_str().unwrap_or("-").to_string(),
            acct["user"]["name"].as_str().unwrap_or("-").to_string(),
        )
    }
}

/// Pure helpers for parsing SSH stdout into health metric values.
/// These extract the logic that was previously inline in `collect_health_metrics`,
/// making it testable without SSH.
mod health_parse_helpers;

/// Pure helpers for the `run_on_fleet` result classification and formatting.
mod fleet_helpers {
    /// Classify SSH result exit code into a status label and whether it succeeded.
    pub fn classify_result(exit_code: i32) -> (&'static str, bool) {
        if exit_code == 0 {
            ("OK", true)
        } else {
            ("FAIL", false)
        }
    }

    /// Build the progress-bar finish message for a completed SSH execution.
    pub fn finish_message(exit_code: i32, stdout: &str, stderr: &str) -> String {
        if exit_code == 0 {
            let line_count = stdout.trim().lines().count();
            format!("✓ done ({} lines)", line_count)
        } else {
            let err_summary = stderr.trim().lines().next().unwrap_or("error");
            format!("✗ {}", err_summary)
        }
    }

    /// Build the output-column text for the fleet summary table.
    pub fn format_output_text(
        exit_code: i32,
        stdout: &str,
        stderr: &str,
        show_output: bool,
    ) -> String {
        if show_output {
            let out = stdout.trim();
            if out.is_empty() {
                stderr.trim().to_string()
            } else {
                out.to_string()
            }
        } else if exit_code != 0 {
            stderr.trim().lines().next().unwrap_or("").to_string()
        } else {
            String::new()
        }
    }
}

/// Pure helpers for filtering VMs in the list handler.
mod list_helpers;

/// Pure helpers for validating repository URLs against shell injection.
#[allow(dead_code)]
mod repo_helpers {
    /// Shell metacharacters that must not appear in a repo URL.
    const SHELL_META: &[char] = &[
        ';', '|', '&', '$', '`', '(', ')', '\n', '\r', '\'', '"', '<', '>', '{', '}', ' ',
    ];

    /// Validate that a repository URL does not contain shell metacharacters.
    ///
    /// Returns `Ok(())` if the URL is safe to interpolate into a shell command,
    /// or `Err(String)` describing the problem.
    pub fn validate_repo_url(url: &str) -> Result<(), String> {
        if url.is_empty() {
            return Err("Repository URL must not be empty".into());
        }
        if let Some(bad) = url.chars().find(|c| SHELL_META.contains(c)) {
            return Err(format!(
                "Repository URL contains disallowed character '{}'",
                bad.escape_default()
            ));
        }
        // Must look like an HTTPS or git@ URL
        if !(url.starts_with("https://")
            || url.starts_with("http://")
            || url.starts_with("git@")
            || url.starts_with("ssh://"))
        {
            return Err(format!(
                "Repository URL must start with https://, http://, git@, or ssh:// (got '{}')",
                url
            ));
        }
        Ok(())
    }
}

/// Pure helpers for VM creation: name generation, template resolution, clone naming.
#[allow(dead_code)]
mod create_helpers;

/// Pure helpers for the connect handler: SSH arg building, VS Code URI construction.
mod connect_helpers {
    use std::path::Path;

    /// Build SSH command arguments for connecting to a VM.
    pub fn build_ssh_args(username: &str, ip: &str, key: Option<&Path>) -> Vec<String> {
        let mut args = vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
        ];
        if let Some(key_path) = key {
            args.push("-i".to_string());
            args.push(key_path.display().to_string());
        }
        args.push(format!("{}@{}", username, ip));
        args
    }

    /// Build a VS Code remote SSH URI for a VM.
    #[allow(dead_code)]
    pub fn build_vscode_remote_uri(user: &str, ip: &str) -> String {
        format!("ssh-remote+{}@{}", user, ip)
    }

    /// Build SSH args for streaming logs via `tail -f`.
    pub fn build_log_follow_args(username: &str, ip: &str, log_path: &str) -> Vec<String> {
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "-o".to_string(),
            "ConnectTimeout=10".to_string(),
            format!("{}@{}", username, ip),
            format!("sudo tail -f {}", log_path),
        ]
    }

    /// Build SSH args for fetching a specific number of log lines.
    #[allow(dead_code)]
    pub fn build_log_tail_args(
        username: &str,
        ip: &str,
        lines: u32,
        log_path: &str,
    ) -> Vec<String> {
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            "-o".to_string(),
            "ConnectTimeout=10".to_string(),
            format!("{}@{}", username, ip),
            format!("sudo tail -n {} {}", lines, log_path),
        ]
    }
}

/// Pure helpers for update/os-update commands: script generation.
mod update_helpers {
    /// Build the full development tools update script.
    pub fn build_dev_update_script() -> &'static str {
        concat!(
            "#!/bin/bash\n",
            "set -e\n",
            "echo 'Updating system packages...'\n",
            "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq\n",
            "sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq\n",
            "echo 'Updating Rust toolchain...'\n",
            "if command -v rustup &>/dev/null; then rustup update 2>/dev/null || true; fi\n",
            "echo 'Updating Python packages...'\n",
            "if command -v pip3 &>/dev/null; then pip3 install --upgrade pip 2>/dev/null || true; fi\n",
            "echo 'Updating Node.js packages...'\n",
            "if command -v npm &>/dev/null; then sudo npm install -g npm 2>/dev/null || true; fi\n",
            "echo 'Development tools updated.'\n",
        )
    }

    /// Build the OS-only update command.
    pub fn build_os_update_cmd() -> &'static str {
        "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq"
    }

    /// Map a log type name to its file path on the remote VM.
    #[allow(dead_code)]
    pub fn log_type_to_path(log_type: &str) -> &'static str {
        match log_type {
            "cloud-init" | "CloudInit" => "/var/log/cloud-init-output.log",
            "syslog" | "Syslog" => "/var/log/syslog",
            "auth" | "Auth" => "/var/log/auth.log",
            _ => "/var/log/syslog",
        }
    }
}

/// Pure helpers for compose commands: command building, file resolution.
mod compose_helpers {
    /// Resolve the compose file path, defaulting to "docker-compose.yml".
    #[allow(dead_code)]
    pub fn resolve_compose_file(file: Option<&str>) -> String {
        file.unwrap_or("docker-compose.yml").to_string()
    }

    /// Build a docker compose command string for a given subcommand and file.
    pub fn build_compose_cmd(subcommand: &str, file: &str) -> String {
        format!("docker compose -f {} {}", file, subcommand)
    }
}

/// Pure helpers for GitHub runner fleet management.
#[allow(dead_code)]
mod runner_helpers {
    /// Generate a runner VM name from pool name and index.
    pub fn build_runner_vm_name(pool: &str, index: usize) -> String {
        format!("azlin-runner-{}-{}", pool, index + 1)
    }

    /// Build the tag string for a runner VM.
    pub fn build_runner_tags(pool: &str, repo: &str) -> String {
        format!("azlin-runner=true pool={} repo={}", pool, repo)
    }

    /// Build a runner pool TOML config as a map of key-value pairs.
    pub fn build_runner_config(
        pool: &str,
        repo: &str,
        count: u32,
        labels: &str,
        rg: &str,
        vm_size: &str,
        timestamp: &str,
    ) -> Vec<(String, toml::Value)> {
        vec![
            ("pool".to_string(), toml::Value::String(pool.to_string())),
            ("repo".to_string(), toml::Value::String(repo.to_string())),
            ("count".to_string(), toml::Value::Integer(count as i64)),
            (
                "labels".to_string(),
                toml::Value::String(labels.to_string()),
            ),
            (
                "resource_group".to_string(),
                toml::Value::String(rg.to_string()),
            ),
            (
                "vm_size".to_string(),
                toml::Value::String(vm_size.to_string()),
            ),
            ("enabled".to_string(), toml::Value::Boolean(true)),
            (
                "created".to_string(),
                toml::Value::String(timestamp.to_string()),
            ),
        ]
    }

    /// Build the pool config file name.
    pub fn pool_config_filename(pool: &str) -> String {
        format!("{}.toml", pool)
    }
}

/// Pure helpers for autopilot config building.
#[allow(dead_code)]
mod autopilot_helpers {
    /// Build the autopilot TOML config as a toml::Value::Table.
    pub fn build_autopilot_config(
        budget: Option<u32>,
        strategy: &str,
        idle_threshold: u32,
        cpu_threshold: u32,
        timestamp: &str,
    ) -> toml::Value {
        let mut config = toml::map::Map::new();
        config.insert("enabled".to_string(), toml::Value::Boolean(true));
        if let Some(b) = budget {
            config.insert("budget".to_string(), toml::Value::Integer(b as i64));
        }
        config.insert(
            "strategy".to_string(),
            toml::Value::String(strategy.to_string()),
        );
        config.insert(
            "idle_threshold_minutes".to_string(),
            toml::Value::Integer(idle_threshold as i64),
        );
        config.insert(
            "cpu_threshold_percent".to_string(),
            toml::Value::Integer(cpu_threshold as i64),
        );
        config.insert(
            "updated".to_string(),
            toml::Value::String(timestamp.to_string()),
        );
        toml::Value::Table(config)
    }

    /// Build the budget name for a resource group.
    pub fn build_budget_name(resource_group: &str) -> String {
        format!("azlin-budget-{}", resource_group)
    }

    /// Build the killall VM filter query for `az vm list`.
    pub fn build_prefix_filter_query(prefix: &str) -> String {
        format!("[?starts_with(name, '{}')].id", prefix)
    }

    /// Build the cost management scope string.
    pub fn build_cost_scope(subscription_id: &str, resource_group: &str) -> String {
        format!(
            "/subscriptions/{}/resourceGroups/{}",
            subscription_id, resource_group
        )
    }
}

/// Pure helpers for VM lifecycle action labelling.
mod stop_helpers {
    /// Return the (in-progress, completed) label pair for a stop/deallocate action.
    /// E.g. `("Deallocating", "Deallocated")` or `("Stopping", "Stopped")`.
    pub fn stop_action_labels(deallocate: bool) -> (&'static str, &'static str) {
        if deallocate {
            ("Deallocating", "Deallocated")
        } else {
            ("Stopping", "Stopped")
        }
    }
}

/// Pure helpers for display-formatting inline values.
mod display_helpers;

/// Pure helpers for tag parsing and validation.
mod tag_helpers {
    /// Split a `key=value` tag string. Returns `None` if the format is invalid
    /// (missing `=`, empty key, or fewer than 2 parts).
    pub fn parse_tag(input: &str) -> Option<(&str, &str)> {
        let parts: Vec<&str> = input.splitn(2, '=').collect();
        if parts.len() == 2 && !parts[0].is_empty() {
            Some((parts[0], parts[1]))
        } else {
            None
        }
    }

    /// Validate a list of tag strings, returning the first invalid one (if any).
    #[allow(dead_code)]
    pub fn find_invalid_tag(tags: &[String]) -> Option<&str> {
        tags.iter()
            .find(|t| parse_tag(t).is_none())
            .map(|t| t.as_str())
    }
}

/// Pure helpers for disk naming conventions.
#[allow(dead_code)]
mod disk_helpers {
    /// Build a data-disk name for a VM: `{vm_name}_datadisk_{lun}`.
    pub fn build_data_disk_name(vm_name: &str, lun: u32) -> String {
        format!("{}_datadisk_{}", vm_name, lun)
    }

    /// Build the restored OS disk name: `{vm_name}_OsDisk_restored`.
    pub fn build_restored_disk_name(vm_name: &str) -> String {
        format!("{}_OsDisk_restored", vm_name)
    }
}

/// Pure helpers for AI-generated command validation.
#[allow(dead_code)]
mod command_helpers {
    /// Check whether a command string is allowed for execution.
    /// Currently only allows commands starting with `"az "`.
    pub fn is_allowed_command(cmd: &str) -> bool {
        cmd.trim().starts_with("az ")
    }

    /// Classify a command and return a user-facing skip reason, or `None` if it's allowed.
    pub fn skip_reason(cmd: &str) -> Option<String> {
        let trimmed = cmd.trim();
        if trimmed.is_empty() {
            Some("empty command".to_string())
        } else if !is_allowed_command(trimmed) {
            Some(format!("Skipping non-Azure command: {}", trimmed))
        } else {
            None
        }
    }
}

/// Pure helpers for autopilot idle-detection parsing.
#[allow(dead_code)]
mod autopilot_parse_helpers {
    /// Parse CPU percentage and uptime from the combined SSH output
    /// of `/proc/stat` + `/proc/uptime` commands.
    /// Returns `(cpu_pct, uptime_secs)`.
    pub fn parse_idle_check(stdout: &str) -> (f64, f64) {
        let lines: Vec<&str> = stdout.trim().lines().collect();
        let cpu_pct = lines
            .first()
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(100.0);
        let uptime_secs = lines
            .get(1)
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(0.0);
        (cpu_pct, uptime_secs)
    }

    /// Decide whether a VM is idle given its CPU percentage, uptime in seconds,
    /// and the configured idle threshold in minutes.
    pub fn is_idle(cpu_pct: f64, uptime_secs: f64, idle_threshold_minutes: u32) -> bool {
        cpu_pct < 5.0 && uptime_secs > (idle_threshold_minutes as f64) * 60.0
    }
}

/// Pure helpers for batch handler result parsing and aggregation.
mod batch_helpers {
    /// Parse VM resource IDs from the TSV output of
    /// `az vm list -g <rg> --query "[].id" -o tsv`.
    pub fn parse_vm_ids(tsv_output: &str) -> Vec<&str> {
        tsv_output.lines().filter(|l| !l.is_empty()).collect()
    }

    /// Build the `az` argument list for a batch VM operation.
    /// `action` is e.g. `"deallocate"` or `"start"`.
    pub fn build_batch_args<'a>(action: &'a str, ids: &[&'a str]) -> Vec<&'a str> {
        let mut args = vec!["vm", action, "--ids"];
        args.extend(ids);
        args
    }

    /// Build the JMESPath query for `az vm list`.
    ///
    /// If `tag` is `Some("key=value")`, returns a filter like
    /// `[?tags.KEY=='VALUE'].id`.  Otherwise returns `[].id`.
    pub fn build_vm_list_query(tag: Option<&str>) -> Result<String, String> {
        match tag {
            Some(t) => {
                let (key, value) = super::tag_helpers::parse_tag(t)
                    .ok_or_else(|| format!("Invalid tag format '{}'. Use key=value.", t))?;
                // Reject characters that could break JMESPath / shell quoting
                for ch in ['\'', '"', '\\', '`', '$', ';', '|', '&', '\n', '\r'] {
                    if key.contains(ch) || value.contains(ch) {
                        return Err(format!(
                            "Tag key or value contains disallowed character '{}'",
                            ch.escape_default()
                        ));
                    }
                }
                Ok(format!("[?tags.{}=='{}'].id", key, value))
            }
            None => Ok("[].id".to_string()),
        }
    }

    /// Summarise the result of a batch operation as a user-facing message.
    pub fn summarise_batch(action: &str, rg: &str, success: bool) -> String {
        if success {
            format!("Batch {} completed for resource group '{}'", action, rg)
        } else {
            format!("Batch {} failed. Run commands individually.", action)
        }
    }
}

#[cfg(test)]
#[allow(deprecated)]
mod tests;
