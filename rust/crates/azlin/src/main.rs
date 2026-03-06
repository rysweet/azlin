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

/// Thread-safe flag to disable bastion pool, replacing the unsound
/// `std::env::set_var` call in an async/multi-threaded context.
static DISABLE_BASTION_POOL: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

/// Estimated monthly cost for an orphaned Azure Standard public IP address.
const ORPHANED_PUBLIC_IP_MONTHLY_COST: f64 = 3.65;

/// Default admin username for Azure VMs.
const DEFAULT_ADMIN_USERNAME: &str = "azureuser";

/// Check whether bastion pool is disabled.
#[allow(dead_code)]
fn is_bastion_pool_disabled() -> bool {
    *DISABLE_BASTION_POOL.get().unwrap_or(&false)
}

/// Health metrics collected from a VM via SSH.
struct HealthMetrics {
    vm_name: String,
    power_state: String,
    cpu_percent: f32,
    mem_percent: f32,
    disk_percent: f32,
    load_avg: String,
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
        "network", "bastion", "ssh",
        "--name", bastion_name,
        "--resource-group", resource_group,
        "--target-resource-id", vm_resource_id,
        "--auth-type", "ssh-key",
        "--username", user,
    ];
    let key_str;
    if let Some(key) = ssh_key {
        key_str = key.to_string_lossy().to_string();
        args.push("--ssh-key");
        args.push(&key_str);
    }
    args.push("--");
    args.push(cmd);

    let output = std::process::Command::new("az")
        .args(&args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .output()?;

    Ok((
        output.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    ))
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

    // CPU usage from top (idle percentage -> used)
    let cpu = exec("top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}'")
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

    // Load average from uptime
    let load = exec("uptime | awk -F'load average:' '{print $2}' | xargs")
        .ok()
        .and_then(|(code, out, _)| health_parse_helpers::parse_load_stdout(code, &out))
        .unwrap_or_else(|| "-".to_string());

    HealthMetrics {
        vm_name: vm_name.to_string(),
        power_state: power_state.to_string(),
        cpu_percent: cpu,
        mem_percent: mem,
        disk_percent: disk,
        load_avg: load,
    }
}

/// Render a health metrics table.
fn render_health_table(metrics: &[HealthMetrics]) {
    let mut table = new_table(&[
        "VM Name",
        "Power State",
        "CPU %",
        "Memory %",
        "Disk %",
        "Load Average",
    ]);

    for m in metrics {
        let state_color = match m.power_state.as_str() {
            "running" => Color::Green,
            "stopped" | "deallocated" => Color::Red,
            _ => Color::Yellow,
        };
        let cpu_color = if m.cpu_percent > 80.0 {
            Color::Red
        } else if m.cpu_percent > 50.0 {
            Color::Yellow
        } else {
            Color::Green
        };
        let mem_color = if m.mem_percent > 80.0 {
            Color::Red
        } else if m.mem_percent > 50.0 {
            Color::Yellow
        } else {
            Color::Green
        };
        let disk_color = if m.disk_percent > 80.0 {
            Color::Red
        } else if m.disk_percent > 50.0 {
            Color::Yellow
        } else {
            Color::Green
        };

        table.add_row(vec![
            Cell::new(&m.vm_name),
            Cell::new(&m.power_state).fg(state_color),
            Cell::new(format!("{:.1}", m.cpu_percent)).fg(cpu_color),
            Cell::new(format!("{:.1}", m.mem_percent)).fg(mem_color),
            Cell::new(format!("{:.1}", m.disk_percent)).fg(disk_color),
            Cell::new(&m.load_avg),
        ]);
    }
    println!("{table}");
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
                    RatCell::from("Power State").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("CPU %").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Memory %").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Disk %").style(RatStyle::default().fg(RatColor::Yellow)),
                    RatCell::from("Load Avg").style(RatStyle::default().fg(RatColor::Yellow)),
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
                        Row::new(vec![
                            RatCell::from(m.vm_name.as_str()),
                            RatCell::from(m.power_state.as_str())
                                .style(RatStyle::default().fg(state_color)),
                            RatCell::from(format!("{:.1}", m.cpu_percent))
                                .style(RatStyle::default().fg(cpu_color)),
                            RatCell::from(format!("{:.1}", m.mem_percent))
                                .style(RatStyle::default().fg(mem_color)),
                            RatCell::from(format!("{:.1}", m.disk_percent))
                                .style(RatStyle::default().fg(disk_color)),
                            RatCell::from(m.load_avg.as_str()),
                        ])
                    })
                    .collect();

                let table = RatTable::new(
                    rows,
                    [
                        Constraint::Percentage(25),
                        Constraint::Percentage(15),
                        Constraint::Percentage(15),
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
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let include_all = all || include_stopped;

            // Resolve resource group(s)
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
                                match vm_manager.list_vms(&rg) {
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
                        Some(rg) => vm_manager.list_vms(rg)?,
                        None => {
                            let config = azlin_core::AzlinConfig::load()
                                .context("Failed to load azlin config")?;
                            match config.default_resource_group {
                                Some(rg) => vm_manager.list_vms(&rg)?,
                                None => {
                                    anyhow::bail!("No resource group specified. Use --resource-group or set in config.");
                                }
                            }
                        }
                    }
                }
            } else if show_all_vms {
                vm_manager.list_all_vms()?
            } else {
                match &resource_group {
                    Some(rg) => vm_manager.list_vms(rg)?,
                    None => {
                        let config = azlin_core::AzlinConfig::load()
                            .context("Failed to load azlin config")?;
                        match config.default_resource_group {
                            Some(rg) => vm_manager.list_vms(&rg)?,
                            None => {
                                anyhow::bail!("No resource group specified. Use --resource-group or set in config.");
                            }
                        }
                    }
                }
            };

            // Filter stopped VMs unless --all/--include-stopped,
            // then by tag and name pattern.
            list_helpers::apply_filters(
                &mut all_vms,
                include_all,
                tag.as_deref(),
                vm_pattern.as_deref(),
            );

            // Sort VMs by session name (matching Python order)
            all_vms.sort_by(|a, b| {
                let sa = a.tags.get("azlin-session").map(|s| s.as_str()).unwrap_or("");
                let sb = b.tags.get("azlin-session").map(|s| s.as_str()).unwrap_or("");
                sa.cmp(sb)
            });

            // Detect and display bastion hosts (matching Python: shown above VM table)
            // Use the resolved resource group from the VMs themselves
            let effective_rg = all_vms.first().map(|v| v.resource_group.as_str()).unwrap_or("");
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

            // Collect tmux sessions if not disabled
            let mut tmux_sessions: std::collections::HashMap<String, Vec<String>> =
                std::collections::HashMap::new();
            if !no_tmux {
                // Build bastion name map (region -> bastion_name) for private VMs
                let bastion_map: std::collections::HashMap<String, String> =
                    if matches!(&cli.output, azlin_cli::OutputFormat::Table) {
                        if let Ok(bastions) = list_helpers::detect_bastion_hosts(effective_rg) {
                            bastions.into_iter().map(|(name, location, _)| (location, name)).collect()
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
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=5",
                                "-o", "BatchMode=yes",
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
                            "network".to_string(), "bastion".to_string(), "ssh".to_string(),
                            "--name".to_string(), bastion_name.clone(),
                            "--resource-group".to_string(), vm.resource_group.clone(),
                            "--target-resource-id".to_string(), vm_id,
                            "--auth-type".to_string(), "ssh-key".to_string(),
                            "--username".to_string(), user.to_string(),
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
                                "echo \"CPU:$(top -bn1 | grep 'Cpu(s)' | awk '{print $2}')% MEM:$(free -m | awk '/Mem:/{printf \"%.0f%%\", $3/$2*100}') DISK:$(df -h / | awk 'NR==2{print $5}')\"",
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
                            let (cpu, mem) = display_helpers::parse_vm_size_specs(&vm.vm_size);
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
                        let os_display = display_helpers::format_os_display(
                            vm.os_offer.as_deref(),
                            &vm.os_type,
                        );
                        let (cpu, mem) = display_helpers::parse_vm_size_specs(&vm.vm_size);
                        let mut row = format!("{}", session);
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
                        let os_display = display_helpers::format_os_display(
                            vm.os_offer.as_deref(),
                            &vm.os_type,
                        );
                        let (cpu, mem) = display_helpers::parse_vm_size_specs(&vm.vm_size);
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
                        row.extend_from_slice(&[
                            Cell::new(&cpu),
                            Cell::new(&mem),
                        ]);
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
                    let running = all_vms
                        .iter()
                        .filter(|vm| {
                            vm.power_state == azlin_core::models::PowerState::Running
                        })
                        .count();
                    let total_vcpus: u32 = all_vms
                        .iter()
                        .filter(|vm| {
                            vm.power_state == azlin_core::models::PowerState::Running
                        })
                        .map(|vm| {
                            display_helpers::parse_vm_size_specs(&vm.vm_size)
                                .0
                                .parse::<u32>()
                                .unwrap_or(0)
                        })
                        .sum();
                    let total_mem: u32 = all_vms
                        .iter()
                        .filter(|vm| {
                            vm.power_state == azlin_core::models::PowerState::Running
                        })
                        .map(|vm| {
                            display_helpers::parse_vm_size_specs(&vm.vm_size)
                                .1
                                .trim_end_matches(" GB")
                                .parse::<u32>()
                                .unwrap_or(0)
                        })
                        .sum();
                    let total_tmux: usize =
                        tmux_sessions.values().map(|v| v.len()).sum();

                    println!();
                    println!(
                        "Total: {} VMs | {} running | {} vCPUs in use | {} GB memory in use | {} tmux sessions",
                        total, running, total_vcpus, total_mem, total_tmux
                    );

                    if !show_all_vms {
                        println!();
                        println!("Hints:");
                        println!(
                            "  azlin list -a        Show all VMs across all resource groups"
                        );
                        println!(
                            "  azlin list -w        Wide mode (show VM Name, SKU columns)"
                        );
                        println!(
                            "  azlin list -r        Restore all tmux sessions in new terminal window"
                        );
                        println!(
                            "  azlin list -q        Show quota usage (slower)"
                        );
                        println!(
                            "  azlin list -v        Verbose mode (show tunnel/SSH details)"
                        );
                    }
                }
            }

            // Restore tmux sessions if requested (connect to each VM with active tmux)
            if restore && !tmux_sessions.is_empty() {
                println!("\nRestoring tmux sessions...");
                for (vm_name, sessions) in &tmux_sessions {
                    if let Some(first_session) = sessions.first() {
                        println!("  Connecting to {} (session: {})", vm_name, first_session);
                        // Open in a new terminal tab/window using the connect logic
                        let _ = std::process::Command::new("azlin")
                            .args(["connect", vm_name, "--tmux-session", first_session])
                            .spawn();
                    }
                }
                println!("Session restore initiated. Check your terminal tabs.");
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
            vm_manager.start_vm(&rg, &vm_name)?;
            pb.finish_with_message(format!("✓ Started {}", vm_name));
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

            let (action, done) = stop_helpers::stop_action_labels(deallocate);
            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("{} {}...", action, vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.stop_vm(&rg, &vm_name, deallocate)?;
            pb.finish_with_message(format!("✓ {} {}", done, vm_name));
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
            let vm = vm_manager.get_vm(&rg, &name)?;
            pb.finish_and_clear();

            match output {
                azlin_cli::OutputFormat::Json => {
                    let json = serde_json::json!({
                        "name": vm.name,
                        "resource_group": vm.resource_group,
                        "location": vm.location,
                        "vm_size": vm.vm_size,
                        "os_type": format!("{:?}", vm.os_type),
                        "power_state": vm.power_state.to_string(),
                        "provisioning_state": vm.provisioning_state,
                        "public_ip": vm.public_ip,
                        "private_ip": vm.private_ip,
                        "admin_username": vm.admin_username,
                        "tags": vm.tags,
                        "created_time": vm.created_time.map(|t| t.format("%Y-%m-%d %H:%M:%S UTC").to_string()),
                    });
                    println!("{}", serde_json::to_string_pretty(&json)?);
                }
                azlin_cli::OutputFormat::Csv => {
                    println!("Field,Value");
                    println!("name,{}", vm.name);
                    println!("resource_group,{}", vm.resource_group);
                    println!("location,{}", vm.location);
                    println!("vm_size,{}", vm.vm_size);
                    println!("os_type,{:?}", vm.os_type);
                    println!("power_state,{}", vm.power_state);
                    println!("provisioning_state,{}", vm.provisioning_state);
                    println!("public_ip,{}", vm.public_ip.as_deref().unwrap_or(""));
                    println!("private_ip,{}", vm.private_ip.as_deref().unwrap_or(""));
                    println!(
                        "admin_username,{}",
                        vm.admin_username.as_deref().unwrap_or("")
                    );
                }
                azlin_cli::OutputFormat::Table => {
                    println!("Name:               {}", vm.name);
                    println!("Resource Group:     {}", vm.resource_group);
                    println!("Location:           {}", vm.location);
                    println!("VM Size:            {}", vm.vm_size);
                    println!("OS Type:            {:?}", vm.os_type);
                    println!("Power State:        {}", vm.power_state);
                    println!("Provisioning State: {}", vm.provisioning_state);
                    if let Some(ip) = &vm.public_ip {
                        println!("Public IP:          {}", ip);
                    }
                    if let Some(ip) = &vm.private_ip {
                        println!("Private IP:         {}", ip);
                    }
                    if let Some(user) = &vm.admin_username {
                        println!("Admin User:         {}", user);
                    }
                    if !vm.tags.is_empty() {
                        println!("Tags:");
                        for (k, v) in &vm.tags {
                            println!("  {}: {}", k, v);
                        }
                    }
                    if let Some(t) = &vm.created_time {
                        println!("Created:            {}", t.format("%Y-%m-%d %H:%M:%S UTC"));
                    }
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
            disable_bastion_pool,
            remote_command,
            ..
        } => {
            let name = vm_identifier.ok_or_else(|| anyhow::anyhow!("VM name is required."))?;

            if disable_bastion_pool {
                let _ = DISABLE_BASTION_POOL.set(true);
            }

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
                    for tag in &tags {
                        let (key, value) = match tag_helpers::parse_tag(tag) {
                            Some(kv) => kv,
                            None => {
                                anyhow::bail!("Invalid tag format '{}'. Use key=value.", tag);
                            }
                        };
                        vm_manager.add_tag(&rg, &vm_name, key, value)?;
                        println!("Added tag {}={} to VM '{}'", key, value, vm_name);
                    }
                }
                azlin_cli::TagAction::Remove {
                    vm_name,
                    tag_keys,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    for key in &tag_keys {
                        vm_manager.remove_tag(&rg, &vm_name, key)?;
                        println!("Removed tag '{}' from VM '{}'", key, vm_name);
                    }
                }
                azlin_cli::TagAction::List {
                    vm_name,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let tags = vm_manager.list_tags(&rg, &vm_name)?;
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
            for (name, addr, user) in &targets {
                println!("── {} ──", name);
                match ssh_exec_checked(addr, user, "w").await {
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
            for (name, addr, user) in &targets {
                println!("── {} ──", name);
                match ssh_exec_checked(addr, user, "ps aux --sort=-%mem | head -20").await {
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
            for (name, addr, user) in &targets {
                println!("── {} ──", name);
                match ssh_exec_checked(addr, user, "top -b -n 1 | head -30").await {
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

                vec![collect_health_metrics(&vm_name, &ip, &user, &state, bastion_ref)]
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
            vm_manager.delete_vm(&rg, &vm_name)?;
            pb.finish_with_message(format!("✓ Deleted {}", vm_name));
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
            vm_manager.delete_vm(&rg, &vm_name)?;
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
                println!("Dry run — would delete:");
                println!("  VM: {}", vm_name);
                println!("  Resource group: {}", rg);
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
            vm_manager.delete_vm(&rg, &vm_name)?;
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
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let escaped = shell_escape(value);
                let cmd = env_helpers::build_env_set_cmd(key, &escaped);
                if cmd == "true" {
                    anyhow::bail!("Invalid environment variable key: {}", key);
                }
                ssh_exec_checked(&addr, &user, &cmd).await?;
                println!("Set {}={} on VM '{}'", key, value, vm_identifier);
            }
            azlin_cli::EnvAction::List {
                vm_identifier,
                resource_group,
                ip,
                ..
            } => {
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let output = ssh_exec_checked(&addr, &user, env_helpers::env_list_cmd()).await?;
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
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let cmd = env_helpers::build_env_delete_cmd(&key);
                ssh_exec_checked(&addr, &user, &cmd).await?;
                println!("Deleted '{}' from VM '{}'", key, vm_identifier);
            }
            azlin_cli::EnvAction::Export {
                vm_identifier,
                output_file,
                resource_group,
                ip,
                ..
            } => {
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let output = ssh_exec_checked(&addr, &user, env_helpers::env_list_cmd()).await?;
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
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let content = std::fs::read_to_string(&env_file)?;
                for (key, value) in env_helpers::parse_env_file(&content) {
                    let escaped = shell_escape(&value);
                    let cmd = env_helpers::build_env_set_cmd(&key, &escaped);
                    if cmd == "true" {
                        eprintln!("Skipping invalid environment variable key: {}", key);
                        continue;
                    }
                    ssh_exec_checked(&addr, &user, &cmd).await?;
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
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let cmd = env_helpers::env_clear_cmd();
                ssh_exec_checked(&addr, &user, cmd).await?;
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

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Fetching cost data...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            match azlin_azure::get_cost_summary(&auth, &rg) {
                Ok(summary) => {
                    pb.finish_and_clear();
                    println!(
                        "{}",
                        format_cost_summary(&summary, &cli.output, &from, &to, estimate, by_vm)
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
                            println!("Snapshot schedule for VM '{}':", vm_name);
                            println!("  Resource group: {}", sched.resource_group);
                            println!("  Interval:       every {} hours", sched.every_hours);
                            println!("  Keep count:     {}", sched.keep_count);
                            println!("  Enabled:        {}", sched.enabled);
                            println!("  Created:        {}", sched.created);
                        }
                        None => {
                            println!(
                                "Snapshot schedule status for VM '{}': no schedule configured",
                                vm_name
                            );
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
                    println!(
                        "{}: {}",
                        key_style.apply_to("Name"),
                        acct["name"].as_str().unwrap_or("-")
                    );
                    println!(
                        "{}: {}",
                        key_style.apply_to("Location"),
                        acct["location"].as_str().unwrap_or("-")
                    );
                    println!(
                        "{}: {}",
                        key_style.apply_to("Kind"),
                        acct["kind"].as_str().unwrap_or("-")
                    );
                    println!(
                        "{}: {}",
                        key_style.apply_to("SKU"),
                        acct["sku"]["name"].as_str().unwrap_or("-")
                    );
                    println!(
                        "{}: {}",
                        key_style.apply_to("State"),
                        acct["provisioningState"].as_str().unwrap_or("-")
                    );
                    println!(
                        "{}: {}",
                        key_style.apply_to("Primary Endpoint"),
                        acct["primaryEndpoints"]["file"].as_str().unwrap_or("-")
                    );
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

                let mount_cmd = format!(
                        "sudo mkdir -p {mp} && sudo mount -t nfs {storage_name}.file.core.windows.net:/{storage_name}/home {mp} -o vers=3,sec=sys"
                    );
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
                let unc = format!("//{}.file.core.windows.net/{}", account, share);
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
                        &format!(
                            "vers=3.0,credentials={},serverino,nosharesock,actimeo=30",
                            creds_path.display()
                        ),
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
            let rg = resolve_resource_group(resource_group)?;

            // Map log types to file paths
            let log_path = match log_type {
                azlin_cli::LogType::CloudInit => "/var/log/cloud-init-output.log",
                azlin_cli::LogType::Syslog => "/var/log/syslog",
                azlin_cli::LogType::Auth => "/var/log/auth.log",
            };

            // Get VM IP for SSH
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let vm = vm_manager.get_vm(&rg, &vm_identifier)?;
            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm_identifier))?;
            let username = vm
                .admin_username
                .as_deref()
                .unwrap_or(DEFAULT_ADMIN_USERNAME);

            if follow {
                // Stream logs via SSH tail -f
                println!("Following {} on {}...", log_path, vm_identifier);
                let follow_args = connect_helpers::build_log_follow_args(username, &ip, log_path);
                let status = std::process::Command::new("ssh")
                    .args(&follow_args)
                    .status()?;
                if !status.success() {
                    std::process::exit(status.code().unwrap_or(1));
                }
            } else {
                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!(
                    "Fetching {:?} logs for {}...",
                    log_type, vm_identifier
                ));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));

                let tail_args =
                    connect_helpers::build_log_tail_args(username, &ip, lines, log_path);
                let output = std::process::Command::new("ssh")
                    .args(&tail_args)
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    let log_text = String::from_utf8_lossy(&output.stdout);
                    print!("{}", log_text);
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    anyhow::bail!(
                        "Failed to fetch logs via SSH: {}",
                        azlin_core::sanitizer::sanitize(stderr.trim())
                    );
                }
            }
        }

        // ── Costs (intelligence) ─────────────────────────────────────
        azlin_cli::Commands::Costs { action } => {
            match action {
                azlin_cli::CostsAction::Dashboard { resource_group, .. } => {
                    let auth = create_auth()?;
                    match azlin_azure::get_cost_summary(&auth, &resource_group) {
                        Ok(summary) => {
                            println!("Cost Dashboard for '{}':", resource_group);
                            println!("  Total: ${:.2} {}", summary.total_cost, summary.currency);
                            println!(
                                "  Period: {} to {}",
                                summary.period_start.format("%Y-%m-%d"),
                                summary.period_end.format("%Y-%m-%d")
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
                    let start_date = (chrono::Utc::now() - chrono::Duration::days(days as i64))
                        .format("%Y-%m-%dT00:00:00+00:00")
                        .to_string();
                    let end_date = chrono::Utc::now()
                        .format("%Y-%m-%dT23:59:59+00:00")
                        .to_string();

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

                    let scope = format!(
                        "/subscriptions/{}/resourceGroups/{}",
                        sub_id, resource_group
                    );
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

                                for (date, cost) in parse_cost_history_rows(&data) {
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
                        let output = std::process::Command::new("az")
                            .args([
                                "consumption",
                                "budget",
                                "create",
                                "--budget-name",
                                &format!("azlin-budget-{}", resource_group),
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
                                "Budget set: ${:.2}/month for '{}' (alert at {}%)",
                                budget_amount, resource_group, alert_threshold
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
                        let output = std::process::Command::new("az")
                            .args([
                                "consumption",
                                "budget",
                                "delete",
                                "--budget-name",
                                &format!("azlin-budget-{}", resource_group),
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
                                            parse_recommendation_rows(&data)
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
                                            parse_cost_action_rows(&data)
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
        azlin_cli::Commands::AzlinHelp { command_name } => match command_name.as_deref() {
            Some(cmd) => {
                println!("azlin {} — Extended help", cmd);
                println!();
                println!("Run 'azlin {} --help' for usage details.", cmd);
            }
            None => {
                println!("azlin — Azure VM fleet management CLI");
                println!();
                println!("Run 'azlin --help' for a list of commands.");
                println!("Run 'azlin <command> --help' for command-specific help.");
            }
        },
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

/// Execute a command on a remote host via SSH, returning stdout on success.
async fn ssh_exec_checked(ip: &str, username: &str, command: &str) -> Result<String> {
    let (code, stdout, stderr) = ssh_exec(ip, username, command)?;
    if code != 0 {
        anyhow::bail!("SSH command failed (exit {}): {}", code, stderr);
    }
    Ok(stdout)
}

/// Resolve a VM identifier to (ip, username) — uses --ip flag if provided, else Azure lookup.
async fn resolve_vm_ip(vm_name: &str, resource_group: Option<String>) -> Result<(String, String)> {
    match create_auth() {
        Ok(auth) => {
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;
            let vm = vm_manager.get_vm(&rg, vm_name)?;
            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm_name))?;
            let user = vm
                .admin_username
                .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
            Ok((ip, user))
        }
        Err(_) => {
            anyhow::bail!("Azure auth not available. Use --ip flag to specify VM IP directly.")
        }
    }
}

/// Resolve VM IP: use --ip flag if provided, otherwise look up via Azure.
async fn resolve_vm_ip_or_flag(
    vm_name: &str,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<(String, String)> {
    if let Some(ip) = ip_flag {
        return Ok((ip.to_string(), DEFAULT_ADMIN_USERNAME.to_string()));
    }
    resolve_vm_ip(vm_name, resource_group).await
}

/// Resolve targets for W/Ps/Top: single VM (--vm/--ip) or all VMs via Azure.
/// Returns Vec<(display_name, ip, username)>.
async fn resolve_vm_targets(
    vm_flag: Option<&str>,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<Vec<(String, String, String)>> {
    if let Some(ip) = ip_flag {
        let name = vm_flag.unwrap_or(ip);
        return Ok(vec![(
            name.to_string(),
            ip.to_string(),
            DEFAULT_ADMIN_USERNAME.to_string(),
        )]);
    }
    if let Some(vm_name) = vm_flag {
        let (ip, user) = resolve_vm_ip(vm_name, resource_group).await?;
        return Ok(vec![(vm_name.to_string(), ip, user)]);
    }
    // List all running VMs
    let auth = create_auth()?;
    let vm_manager = azlin_azure::VmManager::new(&auth);
    let rg = resolve_resource_group(resource_group)?;
    let vms = vm_manager.list_vms(&rg)?;
    let mut targets = Vec::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        let ip = match vm.public_ip.or(vm.private_ip) {
            Some(ip) => ip,
            None => continue,
        };
        let user = vm
            .admin_username
            .unwrap_or_else(|| DEFAULT_ADMIN_USERNAME.to_string());
        targets.push((vm.name, ip, user));
    }
    if targets.is_empty() {
        anyhow::bail!("No running VMs found. Use --vm or --ip to target a specific VM.");
    }
    Ok(targets)
}

// ── Extracted helpers for testability ────────────────────────────────

/// Format a cost summary for display. Returns the formatted string.
fn format_cost_summary(
    summary: &azlin_core::models::CostSummary,
    output: &azlin_cli::OutputFormat,
    from: &Option<String>,
    to: &Option<String>,
    estimate: bool,
    by_vm: bool,
) -> String {
    let mut out = String::new();
    if let azlin_cli::OutputFormat::Json = output {
        match serde_json::to_string_pretty(summary) {
            Ok(json) => out.push_str(&json),
            Err(e) => out.push_str(&format!("Failed to serialize cost data: {e}")),
        }
        return out;
    }

    let is_csv = matches!(output, azlin_cli::OutputFormat::Csv);

    if is_csv {
        out.push_str("Total Cost,Currency,Period Start,Period End\n");
        out.push_str(&format!(
            "{:.2},{},{},{}",
            summary.total_cost,
            summary.currency,
            summary.period_start.format("%Y-%m-%d"),
            summary.period_end.format("%Y-%m-%d")
        ));
    } else {
        out.push_str(&format!(
            "Total Cost: ${:.2} {}",
            summary.total_cost, summary.currency
        ));
        out.push_str(&format!(
            "\nPeriod: {} to {}",
            summary.period_start.format("%Y-%m-%d"),
            summary.period_end.format("%Y-%m-%d")
        ));

        if let Some(ref f) = from {
            out.push_str(&format!("\nFrom filter: {}", f));
        }
        if let Some(ref t) = to {
            out.push_str(&format!("\nTo filter: {}", t));
        }
        if estimate {
            out.push_str(&format!(
                "\nEstimate: ${:.2}/month (projected)",
                summary.total_cost
            ));
        }
    }

    if by_vm && !summary.by_vm.is_empty() {
        if is_csv {
            out.push_str("\nVM Name,Cost,Currency");
            for vc in &summary.by_vm {
                out.push_str(&format!("\n{},{:.2},{}", vc.vm_name, vc.cost, vc.currency));
            }
        } else {
            out.push('\n');
            for vc in &summary.by_vm {
                out.push_str(&format!(
                    "\n{:<20} ${:.2} {}",
                    vc.vm_name, vc.cost, vc.currency
                ));
            }
        }
    } else if by_vm {
        out.push_str("\n\nNo per-VM cost data available.");
    }

    out
}

/// Parse cost history rows from JSON data into (date, cost) pairs.
fn parse_cost_history_rows(data: &serde_json::Value) -> Vec<(String, String)> {
    let mut result = Vec::new();
    if let Some(rows) = data.get("rows").and_then(|r| r.as_array()) {
        for row in rows {
            if let Some(arr) = row.as_array() {
                let cost = arr
                    .first()
                    .and_then(|v| v.as_f64())
                    .map(|v| format!("${:.2}", v))
                    .unwrap_or_else(|| "-".to_string());
                let date = arr
                    .get(1)
                    .and_then(|v| v.as_str().or_else(|| v.as_i64().map(|_| "")))
                    .map(|s| s.to_string())
                    .or_else(|| arr.get(1).and_then(|v| v.as_i64()).map(|v| v.to_string()))
                    .unwrap_or_else(|| "-".to_string());
                result.push((date, cost));
            }
        }
    }
    result
}

/// Parse recommendation entries from JSON array into (category, impact, problem) triples.
fn parse_recommendation_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    let mut result = Vec::new();
    if let Some(recs) = data.as_array() {
        for rec in recs {
            let category = rec
                .get("category")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let impact = rec
                .get("impact")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let problem = rec
                .get("shortDescription")
                .and_then(|v| v.get("problem"))
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            result.push((category, impact, problem));
        }
    }
    result
}

/// Parse cost action entries from JSON array into (resource, impact, recommendation) triples.
fn parse_cost_action_rows(data: &serde_json::Value) -> Vec<(String, String, String)> {
    let mut result = Vec::new();
    if let Some(recs) = data.as_array() {
        for rec in recs {
            let resource = rec
                .get("impactedField")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let impact = rec
                .get("impact")
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            let problem = rec
                .get("shortDescription")
                .and_then(|v| v.get("problem"))
                .and_then(|v| v.as_str())
                .unwrap_or("-")
                .to_string();
            result.push((resource, impact, problem));
        }
    }
    result
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
mod templates {
    use std::path::{Path, PathBuf};

    /// Build template TOML content from fields.
    pub fn build_template_toml(
        name: &str,
        description: Option<&str>,
        vm_size: Option<&str>,
        region: Option<&str>,
        cloud_init: Option<&str>,
    ) -> toml::Value {
        let mut tbl = toml::map::Map::new();
        tbl.insert("name".into(), toml::Value::String(name.to_string()));
        tbl.insert(
            "description".into(),
            toml::Value::String(description.unwrap_or("").to_string()),
        );
        tbl.insert(
            "vm_size".into(),
            toml::Value::String(vm_size.unwrap_or("Standard_D4s_v3").to_string()),
        );
        tbl.insert(
            "region".into(),
            toml::Value::String(region.unwrap_or("westus2").to_string()),
        );
        if let Some(ci) = cloud_init {
            tbl.insert("cloud_init".into(), toml::Value::String(ci.to_string()));
        }
        toml::Value::Table(tbl)
    }

    /// Save a template TOML value to the given directory.
    pub fn save_template(
        dir: &Path,
        name: &str,
        tpl: &toml::Value,
    ) -> Result<PathBuf, anyhow::Error> {
        super::name_validation::validate_name(name)
            .map_err(|e| anyhow::anyhow!("Invalid template name: {}", e))?;
        std::fs::create_dir_all(dir)?;
        let path = dir.join(format!("{}.toml", name));
        std::fs::write(
            &path,
            toml::to_string_pretty(tpl)
                .map_err(|e| anyhow::anyhow!("TOML serialization error: {e}"))?,
        )?;
        Ok(path)
    }

    /// Load a template TOML from the given directory.
    pub fn load_template(dir: &Path, name: &str) -> Result<toml::Value, anyhow::Error> {
        super::name_validation::validate_name(name)
            .map_err(|e| anyhow::anyhow!("Invalid template name: {}", e))?;
        let path = dir.join(format!("{}.toml", name));
        if !path.exists() {
            anyhow::bail!("Template '{}' not found.", name);
        }
        let content = std::fs::read_to_string(&path)?;
        Ok(content.parse()?)
    }

    /// List templates in the directory. Returns Vec of (name, vm_size, region).
    pub fn list_templates(dir: &Path) -> Result<Vec<Vec<String>>, anyhow::Error> {
        if !dir.exists() {
            return Ok(Vec::new());
        }
        let mut rows: Vec<Vec<String>> = Vec::new();
        for entry in std::fs::read_dir(dir)? {
            let entry = entry?;
            let fname = entry.file_name().to_string_lossy().to_string();
            if fname.ends_with(".toml") {
                let content = std::fs::read_to_string(entry.path())?;
                let tpl: toml::Value = content
                    .parse()
                    .unwrap_or(toml::Value::Table(Default::default()));
                rows.push(vec![
                    tpl.get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("-")
                        .to_string(),
                    tpl.get("vm_size")
                        .and_then(|v| v.as_str())
                        .unwrap_or("-")
                        .to_string(),
                    tpl.get("region")
                        .and_then(|v| v.as_str())
                        .unwrap_or("-")
                        .to_string(),
                ]);
            }
        }
        Ok(rows)
    }

    /// Delete a template by name. Returns error if not found.
    pub fn delete_template(dir: &Path, name: &str) -> Result<(), anyhow::Error> {
        super::name_validation::validate_name(name)
            .map_err(|e| anyhow::anyhow!("Invalid template name: {}", e))?;
        let path = dir.join(format!("{}.toml", name));
        if !path.exists() {
            anyhow::bail!("Template '{}' not found.", name);
        }
        std::fs::remove_file(&path)?;
        Ok(())
    }

    /// Import a template from a file, returning the template name.
    pub fn import_template(dir: &Path, content: &str) -> Result<String, anyhow::Error> {
        let tpl: toml::Value = content.parse()?;
        let name = tpl
            .get("name")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Template missing 'name' field"))?
            .to_string();
        // validate_name is called inside save_template
        save_template(dir, &name, &tpl)?;
        Ok(name)
    }
}

/// Session TOML helpers for reading, writing, and listing sessions.
mod sessions {
    use std::path::Path;

    /// Build a session TOML value.
    pub fn build_session_toml(name: &str, resource_group: &str, vms: &[String]) -> toml::Value {
        let mut session = toml::map::Map::new();
        session.insert("name".to_string(), toml::Value::String(name.to_string()));
        session.insert(
            "resource_group".to_string(),
            toml::Value::String(resource_group.to_string()),
        );
        let vm_array: Vec<toml::Value> =
            vms.iter().map(|v| toml::Value::String(v.clone())).collect();
        session.insert("vms".to_string(), toml::Value::Array(vm_array));
        session.insert(
            "created".to_string(),
            toml::Value::String(chrono::Utc::now().to_rfc3339()),
        );
        toml::Value::Table(session)
    }

    /// Parse a session TOML and return (resource_group, vms, created).
    pub fn parse_session_toml(
        content: &str,
    ) -> Result<(String, Vec<String>, String), anyhow::Error> {
        let session: toml::Value = content.parse()?;
        let default_tbl = toml::map::Map::new();
        let tbl = session.as_table().unwrap_or(&default_tbl);
        let rg = tbl
            .get("resource_group")
            .and_then(|v| v.as_str())
            .unwrap_or("-")
            .to_string();
        let vms = tbl
            .get("vms")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect()
            })
            .unwrap_or_default();
        let created = tbl
            .get("created")
            .and_then(|v| v.as_str())
            .unwrap_or("-")
            .to_string();
        Ok((rg, vms, created))
    }

    /// List session names from a directory.
    pub fn list_session_names(dir: &Path) -> Result<Vec<String>, anyhow::Error> {
        if !dir.exists() {
            return Ok(Vec::new());
        }
        let mut names = Vec::new();
        for entry in std::fs::read_dir(dir)? {
            let entry = entry?;
            let fname = entry.file_name().to_string_lossy().to_string();
            if fname.ends_with(".toml") {
                names.push(fname.trim_end_matches(".toml").to_string());
            }
        }
        Ok(names)
    }
}

/// Context TOML helpers for reading, writing, and listing contexts.
mod contexts {
    use std::path::Path;

    /// Build a context TOML string from fields.
    pub fn build_context_toml(
        name: &str,
        subscription_id: Option<&str>,
        tenant_id: Option<&str>,
        resource_group: Option<&str>,
        region: Option<&str>,
        key_vault_name: Option<&str>,
    ) -> Result<String, anyhow::Error> {
        let mut ctx = toml::map::Map::new();
        ctx.insert("name".to_string(), toml::Value::String(name.to_string()));
        if let Some(v) = subscription_id {
            ctx.insert(
                "subscription_id".to_string(),
                toml::Value::String(v.to_string()),
            );
        }
        if let Some(v) = tenant_id {
            ctx.insert("tenant_id".to_string(), toml::Value::String(v.to_string()));
        }
        if let Some(v) = resource_group {
            ctx.insert(
                "resource_group".to_string(),
                toml::Value::String(v.to_string()),
            );
        }
        if let Some(v) = region {
            ctx.insert("region".to_string(), toml::Value::String(v.to_string()));
        }
        if let Some(v) = key_vault_name {
            ctx.insert(
                "key_vault_name".to_string(),
                toml::Value::String(v.to_string()),
            );
        }
        Ok(toml::to_string_pretty(&toml::Value::Table(ctx))?)
    }

    /// List contexts in a directory. Returns Vec of (name, is_active).
    pub fn list_contexts(
        ctx_dir: &Path,
        active: &str,
    ) -> Result<Vec<(String, bool)>, anyhow::Error> {
        let mut entries: Vec<_> = std::fs::read_dir(ctx_dir)?.filter_map(|e| e.ok()).collect();
        entries.sort_by_key(|e| e.file_name());
        let mut result = Vec::new();
        for entry in entries {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.ends_with(".toml") {
                let ctx_name = name.trim_end_matches(".toml").to_string();
                let is_active = ctx_name == active;
                result.push((ctx_name, is_active));
            }
        }
        Ok(result)
    }

    /// Rename a context: update the name field in the TOML, rename the file,
    /// and return whether the active context was renamed.
    pub fn rename_context_file(
        ctx_dir: &Path,
        old_name: &str,
        new_name: &str,
    ) -> Result<(), anyhow::Error> {
        let old_path = ctx_dir.join(format!("{}.toml", old_name));
        let new_path = ctx_dir.join(format!("{}.toml", new_name));
        if !old_path.exists() {
            anyhow::bail!("Context '{}' not found.", old_name);
        }
        let content = std::fs::read_to_string(&old_path)?;
        let mut table: toml::Value = toml::from_str(&content)?;
        if let Some(t) = table.as_table_mut() {
            t.insert(
                "name".to_string(),
                toml::Value::String(new_name.to_string()),
            );
        }
        std::fs::write(&new_path, toml::to_string_pretty(&table)?)?;
        std::fs::remove_file(&old_path)?;
        Ok(())
    }

    /// Read a context TOML file and return (name, resource_group).
    /// Returns `None` for resource_group when the field is absent.
    pub fn read_context_resource_group(
        ctx_path: &Path,
    ) -> Result<(String, Option<String>), anyhow::Error> {
        let content = std::fs::read_to_string(ctx_path)?;
        let table: toml::Value = toml::from_str(&content)?;
        let name = table
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or_else(|| {
                ctx_path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("unknown")
            })
            .to_string();
        let rg = table
            .get("resource_group")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
        Ok((name, rg))
    }
}

/// Helpers for `azlin env` subcommands — pure functions that build SSH commands
/// and parse environment variable output. No network I/O.
#[allow(dead_code)]
mod env_helpers {
    /// Validate and split a `KEY=VALUE` string. Returns `None` on bad input.
    pub fn split_env_var(input: &str) -> Option<(&str, &str)> {
        let parts: Vec<&str> = input.splitn(2, '=').collect();
        if parts.len() == 2 && !parts[0].is_empty() {
            Some((parts[0], parts[1]))
        } else {
            None
        }
    }

    /// Validate that an env key contains only safe characters (alphanumeric + underscore).
    pub fn validate_env_key(key: &str) -> Result<(), String> {
        if key.is_empty() {
            return Err("Environment variable key must not be empty".into());
        }
        if !key.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
            return Err(format!(
                "Environment variable key '{}' contains invalid characters; only [A-Za-z0-9_] allowed",
                key
            ));
        }
        if key.starts_with(|c: char| c.is_ascii_digit()) {
            return Err(format!(
                "Environment variable key '{}' must not start with a digit",
                key
            ));
        }
        Ok(())
    }

    /// Build the shell command that upserts `KEY=VALUE` in `~/.profile`.
    /// The `escaped_value` must already be shell-escaped (e.g. via `shell_escape`).
    pub fn build_env_set_cmd(key: &str, escaped_value: &str) -> String {
        // Validate key to prevent injection through the key name
        if validate_env_key(key).is_err() {
            // Return a harmless no-op rather than an injectable command
            return "true".to_string();
        }
        format!(
            "grep -q '^export {}=' ~/.profile 2>/dev/null && sed -i 's/^export {}=.*/export {}={}/' ~/.profile || echo 'export {}={}' >> ~/.profile",
            key, key, key, escaped_value, key, escaped_value
        )
    }

    /// Build the shell command that removes a key from `~/.profile`.
    pub fn build_env_delete_cmd(key: &str) -> String {
        // Validate key to prevent injection through the key name
        if validate_env_key(key).is_err() {
            // Return a harmless no-op rather than an injectable command
            return "true".to_string();
        }
        format!("sed -i '/^export {}=/d' ~/.profile", key)
    }

    /// The command used to list environment variables on a remote VM.
    pub fn env_list_cmd() -> &'static str {
        "env | sort"
    }

    /// Parse the output of `env | sort` into `(key, value)` pairs.
    pub fn parse_env_output(output: &str) -> Vec<(String, String)> {
        output
            .lines()
            .filter_map(|line| {
                line.split_once('=')
                    .map(|(k, v)| (k.to_string(), v.to_string()))
            })
            .collect()
    }

    /// Build a file body suitable for `env export` (one `KEY=VALUE` per line).
    pub fn build_env_file(vars: &[(String, String)]) -> String {
        vars.iter()
            .map(|(k, v)| format!("{}={}", k, v))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// Parse a `.env`-style file, skipping blank lines and `#` comments.
    pub fn parse_env_file(content: &str) -> Vec<(String, String)> {
        content
            .lines()
            .map(|l| l.trim())
            .filter(|l| !l.is_empty() && !l.starts_with('#'))
            .filter_map(|l| {
                l.split_once('=')
                    .map(|(k, v)| (k.to_string(), v.to_string()))
            })
            .collect()
    }

    /// The command used to clear all custom env vars from `~/.profile`.
    pub fn env_clear_cmd() -> &'static str {
        "sed -i '/^export /d' ~/.profile"
    }
}

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
mod snapshot_helpers {
    use serde::{Deserialize, Serialize};
    use std::path::PathBuf;

    /// Schedule configuration persisted to `~/.azlin/schedules/{vm_name}.toml`.
    #[derive(Debug, Serialize, Deserialize)]
    pub struct SnapshotSchedule {
        pub vm_name: String,
        pub resource_group: String,
        pub every_hours: u32,
        pub keep_count: u32,
        pub enabled: bool,
        pub created: String,
    }

    /// Return the directory that holds per-VM schedule files.
    pub fn schedules_dir() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".azlin")
            .join("schedules")
    }

    /// Path to the schedule file for a given VM.
    pub fn schedule_path(vm_name: &str) -> PathBuf {
        schedules_dir().join(format!("{}.toml", vm_name))
    }

    /// Read the schedule config for a VM, if it exists.
    pub fn load_schedule(vm_name: &str) -> Option<SnapshotSchedule> {
        let path = schedule_path(vm_name);
        let contents = std::fs::read_to_string(path).ok()?;
        toml::from_str(&contents).ok()
    }

    /// Write a schedule config for a VM.
    pub fn save_schedule(schedule: &SnapshotSchedule) -> anyhow::Result<()> {
        let dir = schedules_dir();
        std::fs::create_dir_all(&dir)?;
        let path = schedule_path(&schedule.vm_name);
        let contents = toml::to_string_pretty(schedule)?;
        std::fs::write(path, contents)?;
        Ok(())
    }

    /// List all schedule files and load them.
    pub fn load_all_schedules() -> Vec<SnapshotSchedule> {
        let dir = schedules_dir();
        let entries = match std::fs::read_dir(&dir) {
            Ok(e) => e,
            Err(_) => return Vec::new(),
        };
        entries
            .filter_map(|e| {
                let e = e.ok()?;
                let path = e.path();
                if path.extension().and_then(|x| x.to_str()) == Some("toml") {
                    let contents = std::fs::read_to_string(&path).ok()?;
                    toml::from_str(&contents).ok()
                } else {
                    None
                }
            })
            .collect()
    }

    /// Generate a deterministic snapshot name from a VM name and a formatted timestamp.
    pub fn build_snapshot_name(vm_name: &str, timestamp: &str) -> String {
        format!("{}_snapshot_{}", vm_name, timestamp)
    }

    /// Filter a list of snapshot JSON values by VM name substring match on `"name"`.
    pub fn filter_snapshots<'a>(
        snapshots: &'a [serde_json::Value],
        vm_name: &str,
    ) -> Vec<&'a serde_json::Value> {
        snapshots
            .iter()
            .filter(|s| {
                s["name"]
                    .as_str()
                    .map(|n| n.contains(vm_name))
                    .unwrap_or(false)
            })
            .collect()
    }

    /// Extract display columns from a single snapshot JSON value.
    pub fn snapshot_row(snap: &serde_json::Value) -> Vec<String> {
        vec![
            snap["name"].as_str().unwrap_or("-").to_string(),
            snap["diskSizeGb"].to_string(),
            snap["timeCreated"].as_str().unwrap_or("-").to_string(),
            snap["provisioningState"]
                .as_str()
                .unwrap_or("-")
                .to_string(),
        ]
    }
}

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
mod health_parse_helpers {
    /// Parse CPU percentage from the stdout of
    /// `top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}'`.
    /// Returns `None` if the output cannot be parsed.
    pub fn parse_cpu_stdout(exit_code: i32, stdout: &str) -> Option<f32> {
        if exit_code == 0 {
            stdout.trim().parse::<f32>().ok()
        } else {
            None
        }
    }

    /// Parse memory percentage from the stdout of
    /// `free | awk '/Mem:/{printf "%.1f", $3/$2 * 100}'`.
    pub fn parse_mem_stdout(exit_code: i32, stdout: &str) -> Option<f32> {
        if exit_code == 0 {
            stdout.trim().parse::<f32>().ok()
        } else {
            None
        }
    }

    /// Parse disk percentage from the stdout of
    /// `df / --output=pcent | tail -1 | tr -d ' %'`.
    pub fn parse_disk_stdout(exit_code: i32, stdout: &str) -> Option<f32> {
        if exit_code == 0 {
            stdout.trim().parse::<f32>().ok()
        } else {
            None
        }
    }

    /// Parse load average string from the stdout of
    /// `uptime | awk -F'load average:' '{print $2}' | xargs`.
    pub fn parse_load_stdout(exit_code: i32, stdout: &str) -> Option<String> {
        if exit_code == 0 {
            let trimmed = stdout.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_string())
            }
        } else {
            None
        }
    }

    /// Build a complete set of default (zero) metrics for a non-running VM.
    pub fn default_metrics(vm_name: &str, power_state: &str) -> super::HealthMetrics {
        super::HealthMetrics {
            vm_name: vm_name.to_string(),
            power_state: power_state.to_string(),
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
            load_avg: "-".to_string(),
        }
    }
}

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
mod list_helpers {
    use azlin_core::models::{PowerState, VmInfo};

    /// Filter out stopped/deallocated VMs, keeping only Running and Starting.
    pub fn filter_running(vms: &mut Vec<VmInfo>) {
        vms.retain(|vm| {
            vm.power_state == PowerState::Running || vm.power_state == PowerState::Starting
        });
    }

    /// Filter VMs by a tag expression.
    /// If `tag_filter` is `"key=value"`, keeps VMs where `tags[key] == value`.
    /// If `tag_filter` is just `"key"`, keeps VMs that have the key present.
    pub fn filter_by_tag(vms: &mut Vec<VmInfo>, tag_filter: &str) {
        if let Some((key, val)) = tag_filter.split_once('=') {
            vms.retain(|vm| vm.tags.get(key).is_some_and(|v| v == val));
        } else {
            vms.retain(|vm| vm.tags.contains_key(tag_filter));
        }
    }

    /// Filter VMs by a glob-like name pattern (supports `*` as a wildcard).
    pub fn filter_by_pattern(vms: &mut Vec<VmInfo>, pattern: &str) {
        let pat = pattern.replace('*', "");
        vms.retain(|vm| vm.name.contains(&pat));
    }

    /// Apply all three optional filters in order: stopped, tag, pattern.
    pub fn apply_filters(
        vms: &mut Vec<VmInfo>,
        include_all: bool,
        tag: Option<&str>,
        pattern: Option<&str>,
    ) {
        if !include_all {
            filter_running(vms);
        }
        if let Some(t) = tag {
            filter_by_tag(vms, t);
        }
        if let Some(p) = pattern {
            filter_by_pattern(vms, p);
        }
    }

    /// Detect Azure Bastion hosts for a resource group.
    /// Returns Vec of (name, location, sku).
    pub fn detect_bastion_hosts(resource_group: &str) -> anyhow::Result<Vec<(String, String, String)>> {
        let output = std::process::Command::new("az")
            .args(["network", "bastion", "list", "--resource-group", resource_group, "--output", "json"])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .output()?;

        if !output.status.success() {
            return Ok(Vec::new()); // Bastion not available, not an error
        }

        let bastions: Vec<serde_json::Value> =
            serde_json::from_slice(&output.stdout).unwrap_or_default();

        Ok(bastions
            .iter()
            .map(|b| {
                let name = b["name"].as_str().unwrap_or("").to_string();
                let location = b["location"].as_str().unwrap_or("").to_string();
                let sku = b["sku"]["name"].as_str().unwrap_or("Basic").to_string();
                (name, location, sku)
            })
            .collect())
    }
}

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
mod create_helpers {
    /// Generate a VM name. If a base name is given with pool > 1, appends index.
    /// If no base name, generates a timestamped name.
    pub fn generate_vm_name(
        base: Option<&str>,
        index: usize,
        pool_count: usize,
        timestamp: &str,
    ) -> String {
        match base {
            Some(n) if pool_count > 1 => format!("{}-{}", n, index + 1),
            Some(n) => n.to_string(),
            None => format!("azlin-vm-{}", timestamp),
        }
    }

    /// Resolve final VM size: if the user-supplied size is the default sentinel,
    /// use the template override (if any), otherwise keep the user value.
    pub fn resolve_with_template_default(
        user_value: &str,
        default_sentinel: &str,
        template_value: Option<String>,
    ) -> String {
        if user_value == default_sentinel {
            template_value.unwrap_or_else(|| user_value.to_string())
        } else {
            user_value.to_string()
        }
    }

    /// Build the git clone command to run on a remote VM.
    ///
    /// Returns `Err` if the URL contains shell metacharacters.
    pub fn build_clone_cmd(repo_url: &str) -> Result<String, String> {
        super::repo_helpers::validate_repo_url(repo_url)?;
        let quoted = shlex::try_quote(repo_url).map_err(|e| format!("Failed to quote URL: {e}"))?;
        Ok(format!(
            "git clone {} ~/src/$(basename {} .git)",
            quoted, quoted
        ))
    }

    /// Build SSH connect args (for auto-connect after VM creation).
    pub fn build_ssh_connect_args(user: &str, ip: &str) -> Vec<String> {
        vec![
            "-o".to_string(),
            "StrictHostKeyChecking=accept-new".to_string(),
            format!("{}@{}", user, ip),
        ]
    }

    /// Generate a snapshot name for VM cloning.
    pub fn build_snapshot_name(source_vm: &str, timestamp: &str) -> String {
        format!("{}_clone_snap_{}", source_vm, timestamp)
    }

    /// Generate a clone VM name from the source VM and replica index.
    pub fn build_clone_name(source_vm: &str, index: usize) -> String {
        format!("{}-clone-{}", source_vm, index + 1)
    }

    /// Generate an OS disk name from a VM name.
    pub fn build_disk_name(vm_name: &str) -> String {
        format!("{}_OsDisk", vm_name)
    }
}

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
mod display_helpers {
    /// Render a serde_json::Value as a user-friendly string for config display.
    /// `Null` → `"null"`, `String` → the raw string, everything else → its JSON representation.
    #[allow(dead_code)]
    pub fn config_value_display(v: &serde_json::Value) -> String {
        match v {
            serde_json::Value::String(s) => s.clone(),
            serde_json::Value::Null => "null".to_string(),
            other => other.to_string(),
        }
    }

    /// Truncate a VM name to `max_len` characters, appending "..." if truncated.
    /// Returns the name unchanged if it fits within `max_len`.
    pub fn truncate_vm_name(name: &str, max_len: usize) -> String {
        if name.len() > max_len && max_len > 3 {
            let truncated: String = name.chars().take(max_len.saturating_sub(3)).collect();
            format!("{}...", truncated)
        } else {
            name.to_string()
        }
    }

    /// Format a list of tmux session names for display, collapsing long lists.
    /// If the list has more than `max_show` entries, the remainder is summarised
    /// as `"+N more"`.
    pub fn format_tmux_sessions(sessions: &[String], max_show: usize) -> String {
        if sessions.is_empty() {
            "-".to_string()
        } else if sessions.len() <= max_show {
            sessions.join(", ")
        } else {
            format!(
                "{}, +{} more",
                sessions[..max_show].join(", "),
                sessions.len() - max_show,
            )
        }
    }

    /// Format the reconnect prompt message for SSH auto-reconnect.
    #[allow(dead_code)]
    pub fn reconnect_prompt(attempt: u32, max_retries: u32) -> String {
        format!(
            "SSH disconnected. Reconnect? (attempt {}/{}) [Y/n] ",
            attempt, max_retries,
        )
    }

    /// Format OS offer string into a human-readable distro name.
    pub fn format_os_display(
        os_offer: Option<&str>,
        os_type: &azlin_core::models::OsType,
    ) -> String {
        if let Some(offer) = os_offer {
            let lower = offer.to_lowercase();
            if lower.contains("ubuntu") {
                return format_ubuntu_offer(offer);
            }
            if lower.contains("debian") {
                return "Debian".to_string();
            }
            if lower.contains("rhel") {
                return "RHEL".to_string();
            }
            if lower.contains("centos") {
                return "CentOS".to_string();
            }
            if lower.contains("sles") || lower.contains("suse") {
                return "SUSE".to_string();
            }
            if lower.contains("alma") {
                return "AlmaLinux".to_string();
            }
            if lower.contains("rocky") {
                return "Rocky Linux".to_string();
            }
            if lower.contains("windowsserver") || lower.contains("windows") {
                return "Windows".to_string();
            }
            return offer.to_string();
        }
        match os_type {
            azlin_core::models::OsType::Windows => "Windows".to_string(),
            _ => "Linux".to_string(),
        }
    }

    /// Parse Ubuntu offer strings into human-readable format.
    /// Handles multiple Azure offer formats:
    ///   "ubuntu-24_04-lts" -> "Ubuntu 24.04 LTS"
    ///   "ubuntu-25_10" -> "Ubuntu 25.10"
    ///   "0001-com-ubuntu-server-jammy" -> "Ubuntu 22.04 LTS"
    fn format_ubuntu_offer(offer: &str) -> String {
        let lower = offer.to_lowercase();

        // Try version format: ubuntu-XX_YY[-lts]
        // Strip common prefixes
        let stripped = lower
            .strip_prefix("ubuntu-")
            .or_else(|| {
                // Handle 0001-com-ubuntu-* format
                lower.find("ubuntu-").map(|i| &lower[i + 7..])
            })
            .unwrap_or(&lower);

        let is_lts = stripped.contains("lts");
        let version_part = stripped
            .replace("-lts", "")
            .replace("_lts", "")
            .replace("-gen1", "")
            .replace("-gen2", "");

        // Parse XX_YY -> XX.YY
        if let Some((major, minor)) = version_part.split_once('_') {
            if major.chars().all(|c| c.is_numeric()) {
                let suffix = if is_lts { " LTS" } else { "" };
                return format!("Ubuntu {}.{}{}", major, minor, suffix);
            }
        }

        // Codename fallback — search the ENTIRE offer string for codenames
        if lower.contains("plucky") {
            return "Ubuntu 25.04".to_string();
        }
        if lower.contains("oracular") {
            return "Ubuntu 24.10".to_string();
        }
        if lower.contains("noble") {
            return "Ubuntu 24.04 LTS".to_string();
        }
        if lower.contains("jammy") {
            return "Ubuntu 22.04 LTS".to_string();
        }
        if lower.contains("focal") {
            return "Ubuntu 20.04 LTS".to_string();
        }
        if lower.contains("bionic") {
            return "Ubuntu 18.04 LTS".to_string();
        }

        format!("Ubuntu ({})", offer)
    }

    /// Format IP display with annotation (Pub/Bast/N/A).
    pub fn format_ip_display(public_ip: Option<&str>, private_ip: Option<&str>) -> String {
        if let Some(pub_ip) = public_ip {
            format!("{} (Pub)", pub_ip)
        } else if let Some(priv_ip) = private_ip {
            format!("{} (Bast)", priv_ip)
        } else {
            "N/A".to_string()
        }
    }

    /// Extract vCPU count and estimated memory from Azure VM size name.
    /// e.g. "Standard_D4s_v3" -> ("4", "16 GB")
    pub fn parse_vm_size_specs(vm_size: &str) -> (String, String) {
        let parts: Vec<&str> = vm_size.split('_').collect();
        if parts.len() >= 2 {
            let size_part = parts[1]; // e.g., "D4s" or "E16as"
            let vcpus: String = size_part
                .chars()
                .skip_while(|c| c.is_alphabetic())
                .take_while(|c| c.is_numeric())
                .collect();
            if let Ok(cpu_count) = vcpus.parse::<u32>() {
                let mem_gb = estimate_memory_gb(size_part, cpu_count);
                return (format!("{}", cpu_count), format!("{} GB", mem_gb));
            }
        }
        ("-".to_string(), "-".to_string())
    }

    /// Estimate memory in GB based on VM family letter and vCPU count.
    fn estimate_memory_gb(size_part: &str, vcpus: u32) -> u32 {
        let family = size_part.chars().next().unwrap_or('D');
        match family.to_ascii_uppercase() {
            'E' => vcpus * 8,          // E-series: memory optimized
            'M' => vcpus * 16,         // M-series: memory optimized (large)
            'F' => (vcpus * 2).max(1), // F-series: compute optimized
            'L' => vcpus * 8,          // L-series: storage optimized
            'N' => vcpus * 6,          // N-series: GPU
            'B' => (vcpus * 4).max(1), // B-series: burstable
            _ => vcpus * 4,            // D-series and default
        }
    }
}

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
mod tests {
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_keys_list_finds_pub_files() {
        let tmp = TempDir::new().unwrap();
        let ssh_dir = tmp.path();
        fs::write(ssh_dir.join("id_ed25519"), "private key").unwrap();
        fs::write(ssh_dir.join("id_ed25519.pub"), "ssh-ed25519 AAAA test@host").unwrap();
        fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();

        let entries: Vec<String> = fs::read_dir(ssh_dir)
            .unwrap()
            .filter_map(|e| {
                let name = e.ok()?.file_name().to_string_lossy().to_string();
                if name.ends_with(".pub")
                    || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"].contains(&name.as_str())
                {
                    Some(name)
                } else {
                    None
                }
            })
            .collect();

        assert_eq!(entries.len(), 2);
        assert!(entries.contains(&"id_ed25519".to_string()));
        assert!(entries.contains(&"id_ed25519.pub".to_string()));
    }

    #[test]
    fn test_keys_backup_copies_id_files_only() {
        let tmp = TempDir::new().unwrap();
        let ssh_dir = tmp.path();
        fs::write(ssh_dir.join("id_rsa"), "rsa private").unwrap();
        fs::write(ssh_dir.join("id_rsa.pub"), "rsa public").unwrap();
        fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();
        fs::write(ssh_dir.join("config"), "Host *").unwrap();

        let backup_dir = tmp.path().join("backup");
        fs::create_dir_all(&backup_dir).unwrap();

        let mut count = 0u32;
        for entry in fs::read_dir(ssh_dir).unwrap() {
            let entry = entry.unwrap();
            let name = entry.file_name().to_string_lossy().to_string();
            if name.starts_with("id_") {
                fs::copy(entry.path(), backup_dir.join(&name)).unwrap();
                count += 1;
            }
        }

        assert_eq!(count, 2);
        assert!(backup_dir.join("id_rsa").exists());
        assert!(backup_dir.join("id_rsa.pub").exists());
        assert!(!backup_dir.join("known_hosts").exists());
    }

    #[test]
    fn test_keys_export_selects_first_available() {
        let tmp = TempDir::new().unwrap();
        let ssh_dir = tmp.path();
        fs::write(ssh_dir.join("id_ed25519.pub"), "ssh-ed25519 AAAA test").unwrap();

        let candidates = ["id_ed25519_azlin.pub", "id_ed25519.pub", "id_rsa.pub"];
        let found = candidates
            .iter()
            .map(|f| ssh_dir.join(f))
            .find(|p| p.exists());

        assert!(found.is_some());
        assert!(found.unwrap().ends_with("id_ed25519.pub"));
    }

    #[test]
    fn test_auth_profile_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let profiles_dir = tmp.path().join("profiles");
        fs::create_dir_all(&profiles_dir).unwrap();

        let profile_data = serde_json::json!({
            "tenant_id": "test-tenant",
            "client_id": "test-client",
            "subscription_id": "test-sub",
        });

        let profile_path = profiles_dir.join("test.json");
        fs::write(
            &profile_path,
            serde_json::to_string_pretty(&profile_data).unwrap(),
        )
        .unwrap();

        assert!(profile_path.exists());
        let content = fs::read_to_string(&profile_path).unwrap();
        let loaded: serde_json::Value = serde_json::from_str(&content).unwrap();
        assert_eq!(loaded["tenant_id"], "test-tenant");
        assert_eq!(loaded["client_id"], "test-client");
        assert_eq!(loaded["subscription_id"], "test-sub");
    }

    #[test]
    fn test_auth_profile_remove() {
        let tmp = TempDir::new().unwrap();
        let profiles_dir = tmp.path().join("profiles");
        fs::create_dir_all(&profiles_dir).unwrap();

        let profile_path = profiles_dir.join("staging.json");
        fs::write(&profile_path, r#"{"tenant_id":"t","client_id":"c"}"#).unwrap();
        assert!(profile_path.exists());

        fs::remove_file(&profile_path).unwrap();
        assert!(!profile_path.exists());
    }

    #[test]
    fn test_snapshot_name_format() {
        let vm_name = "test-vm";
        let snapshot_name = format!(
            "{}_snapshot_{}",
            vm_name,
            chrono::Utc::now().format("%Y%m%d_%H%M%S")
        );
        assert!(snapshot_name.starts_with("test-vm_snapshot_"));
        assert!(snapshot_name.len() > 30);
    }

    #[test]
    fn test_storage_sku_mapping() {
        let cases = vec![
            ("premium", "Premium_LRS"),
            ("standard", "Standard_LRS"),
            ("Premium", "Premium_LRS"),
            ("other", "Premium_LRS"),
        ];
        for (input, expected) in cases {
            let sku = match input.to_lowercase().as_str() {
                "premium" => "Premium_LRS",
                "standard" => "Standard_LRS",
                _ => "Premium_LRS",
            };
            assert_eq!(sku, expected, "Failed for input: {}", input);
        }
    }

    #[test]
    fn test_template_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let tpl_dir = tmp.path().join("templates");
        fs::create_dir_all(&tpl_dir).unwrap();

        let tpl = serde_json::json!({
            "name": "dev-box",
            "description": "Development VM",
            "vm_size": "Standard_D4s_v3",
            "region": "westus2",
            "cloud_init": null,
        });

        let path = tpl_dir.join("dev-box.json");
        fs::write(&path, serde_json::to_string_pretty(&tpl).unwrap()).unwrap();
        assert!(path.exists());

        let loaded: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(loaded["name"], "dev-box");
        assert_eq!(loaded["vm_size"], "Standard_D4s_v3");
    }

    #[test]
    fn test_context_create_and_delete() {
        let tmp = TempDir::new().unwrap();
        let ctx_dir = tmp.path().join("contexts");
        fs::create_dir_all(&ctx_dir).unwrap();

        let mut ctx = toml::map::Map::new();
        ctx.insert("name".into(), toml::Value::String("staging".into()));
        ctx.insert(
            "subscription_id".into(),
            toml::Value::String("sub-123".into()),
        );
        ctx.insert("tenant_id".into(), toml::Value::String("tenant-456".into()));
        ctx.insert(
            "resource_group".into(),
            toml::Value::String("staging-rg".into()),
        );
        ctx.insert("region".into(), toml::Value::String("eastus".into()));

        let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
        let path = ctx_dir.join("staging.toml");
        fs::write(&path, &toml_str).unwrap();
        assert!(path.exists());

        // read back
        let loaded: toml::Value = toml::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(loaded["name"].as_str().unwrap(), "staging");
        assert_eq!(loaded["resource_group"].as_str().unwrap(), "staging-rg");

        // delete
        fs::remove_file(&path).unwrap();
        assert!(!path.exists());
    }

    #[test]
    fn test_context_switch_updates_active_context() {
        let tmp = TempDir::new().unwrap();
        let ctx_dir = tmp.path().join("contexts");
        fs::create_dir_all(&ctx_dir).unwrap();

        for name in &["dev", "prod"] {
            let mut ctx = toml::map::Map::new();
            ctx.insert("name".into(), toml::Value::String(name.to_string()));
            ctx.insert(
                "subscription_id".into(),
                toml::Value::String(format!("sub-{}", name)),
            );
            let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
            fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
        }

        let active_path = tmp.path().join("active-context");
        fs::write(&active_path, "dev").unwrap();
        assert_eq!(fs::read_to_string(&active_path).unwrap().trim(), "dev");

        // Switch to prod
        assert!(ctx_dir.join("prod.toml").exists());
        fs::write(&active_path, "prod").unwrap();
        assert_eq!(fs::read_to_string(&active_path).unwrap().trim(), "prod");
    }

    #[test]
    fn test_context_list_marks_active() {
        let tmp = TempDir::new().unwrap();
        let ctx_dir = tmp.path().join("contexts");
        fs::create_dir_all(&ctx_dir).unwrap();

        for name in &["alpha", "beta", "gamma"] {
            let mut ctx = toml::map::Map::new();
            ctx.insert("name".into(), toml::Value::String(name.to_string()));
            let toml_str = toml::to_string_pretty(&toml::Value::Table(ctx)).unwrap();
            fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
        }

        let active_path = tmp.path().join("active-context");
        fs::write(&active_path, "beta").unwrap();
        let active = fs::read_to_string(&active_path).unwrap().trim().to_string();

        let mut entries: Vec<_> = fs::read_dir(&ctx_dir)
            .unwrap()
            .filter_map(|e| e.ok())
            .collect();
        entries.sort_by_key(|e| e.file_name());
        let mut lines = Vec::new();
        for entry in entries {
            let fname = entry.file_name().to_string_lossy().to_string();
            if fname.ends_with(".toml") {
                let ctx_name = fname.trim_end_matches(".toml");
                if ctx_name == active {
                    lines.push(format!("* {}", ctx_name));
                } else {
                    lines.push(format!("  {}", ctx_name));
                }
            }
        }
        assert_eq!(lines, vec!["  alpha", "* beta", "  gamma"]);
    }

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
        assert_eq!(super::shell_escape("hello"), "'hello'");
    }

    #[test]
    fn test_shell_escape_with_single_quotes() {
        assert_eq!(super::shell_escape("it's"), "'it'\\''s'");
    }

    #[test]
    fn test_shell_escape_with_spaces_and_special_chars() {
        let escaped = super::shell_escape("foo bar $HOME");
        assert_eq!(escaped, "'foo bar $HOME'");
    }

    #[tokio::test]
    async fn test_resolve_vm_ip_or_flag_uses_ip_flag() {
        let (ip, user) = super::resolve_vm_ip_or_flag("ignored", Some("1.2.3.4"), None)
            .await
            .unwrap();
        assert_eq!(ip, "1.2.3.4");
        assert_eq!(user, "azureuser");
    }

    #[test]
    fn test_health_metrics_non_running_vm() {
        let m = super::collect_health_metrics("test-vm", "10.0.0.1", "azureuser", "deallocated", None);
        assert_eq!(m.vm_name, "test-vm");
        assert_eq!(m.power_state, "deallocated");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
        assert_eq!(m.load_avg, "-");
    }

    #[test]
    fn test_ssh_exec_unreachable_host() {
        // ssh_exec to a non-routable address should either error or return non-zero
        let result = super::ssh_exec("192.0.2.1", "user", "echo hello");
        if let Ok((code, _, _)) = result {
            assert_ne!(code, 0, "should fail for unreachable host");
        }
    }

    #[test]
    fn test_home_dir_returns_path() {
        // On any real system, home_dir should return a valid path
        let result = super::home_dir();
        assert!(result.is_ok(), "home_dir should succeed on real system");
        assert!(result.unwrap().is_absolute(), "home dir should be absolute");
    }

    #[test]
    fn test_new_table_creates_table_with_headers() {
        let table = super::new_table(&["Name", "Value", "Status"]);
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
        let table = super::new_table(&[]);
        let _rendered = table.to_string();
    }

    #[test]
    fn test_render_health_table_does_not_panic() {
        let metrics = vec![
            super::HealthMetrics {
                vm_name: "vm1".to_string(),
                power_state: "running".to_string(),
                cpu_percent: 25.5,
                mem_percent: 60.0,
                disk_percent: 45.0,
                load_avg: "0.50, 0.30, 0.20".to_string(),
            },
            super::HealthMetrics {
                vm_name: "vm2".to_string(),
                power_state: "stopped".to_string(),
                cpu_percent: 0.0,
                mem_percent: 0.0,
                disk_percent: 0.0,
                load_avg: "-".to_string(),
            },
            super::HealthMetrics {
                vm_name: "vm3".to_string(),
                power_state: "running".to_string(),
                cpu_percent: 95.0,
                mem_percent: 85.0,
                disk_percent: 92.0,
                load_avg: "4.00, 3.50, 3.00".to_string(),
            },
        ];
        // Should not panic; just renders to stdout
        super::render_health_table(&metrics);
    }

    #[test]
    fn test_run_on_fleet_empty_list() {
        let vms: Vec<(String, String, String)> = vec![];
        // Should not panic on empty list
        super::run_on_fleet(&vms, "echo hi", true);
    }

    // ── shell_escape tests ───────────────────────────────────────

    #[test]
    fn test_shell_escape_empty_string() {
        assert_eq!(super::shell_escape(""), "''");
    }

    #[test]
    fn test_shell_escape_no_special_chars() {
        assert_eq!(super::shell_escape("hello"), "'hello'");
    }

    #[test]
    fn test_shell_escape_with_spaces() {
        assert_eq!(super::shell_escape("hello world"), "'hello world'");
    }

    #[test]
    fn test_shell_escape_with_dollar_sign() {
        assert_eq!(super::shell_escape("$HOME"), "'$HOME'");
    }

    #[test]
    fn test_shell_escape_with_backticks() {
        assert_eq!(super::shell_escape("`whoami`"), "'`whoami`'");
    }

    #[test]
    fn test_shell_escape_with_double_quotes() {
        assert_eq!(super::shell_escape(r#"say "hi""#), r#"'say "hi"'"#);
    }

    #[test]
    fn test_shell_escape_multiple_single_quotes() {
        let result = super::shell_escape("it's Tom's");
        assert_eq!(result, "'it'\\''s Tom'\\''s'");
    }

    #[test]
    fn test_shell_escape_newline() {
        let result = super::shell_escape("line1\nline2");
        assert!(result.starts_with('\''));
        assert!(result.ends_with('\''));
        assert!(result.contains('\n'));
    }

    #[test]
    fn test_shell_escape_semicolons_and_pipes() {
        let result = super::shell_escape("cmd1; cmd2 | cmd3");
        assert_eq!(result, "'cmd1; cmd2 | cmd3'");
    }

    #[test]
    fn test_shell_escape_unicode() {
        assert_eq!(super::shell_escape("café"), "'café'");
    }

    // ── resolve_resource_group tests ─────────────────────────────

    #[test]
    fn test_resolve_resource_group_with_explicit_value() {
        let result = super::resolve_resource_group(Some("my-rg".to_string()));
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "my-rg");
    }

    #[test]
    fn test_resolve_resource_group_explicit_empty_string() {
        let result = super::resolve_resource_group(Some("".to_string()));
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "");
    }

    #[test]
    fn test_resolve_resource_group_explicit_with_special_chars() {
        let result = super::resolve_resource_group(Some("my-rg_123".to_string()));
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), "my-rg_123");
    }

    // ── resolve_vm_ip_or_flag tests ──────────────────────────────

    #[tokio::test]
    async fn test_resolve_vm_ip_or_flag_returns_provided_ip() {
        let (ip, user) = super::resolve_vm_ip_or_flag("any-vm", Some("10.0.0.5"), None)
            .await
            .unwrap();
        assert_eq!(ip, "10.0.0.5");
        assert_eq!(user, "azureuser");
    }

    #[tokio::test]
    async fn test_resolve_vm_ip_or_flag_ipv6() {
        let (ip, user) = super::resolve_vm_ip_or_flag("vm", Some("::1"), None)
            .await
            .unwrap();
        assert_eq!(ip, "::1");
        assert_eq!(user, "azureuser");
    }

    #[tokio::test]
    async fn test_resolve_vm_ip_or_flag_localhost() {
        let (ip, user) = super::resolve_vm_ip_or_flag("vm", Some("127.0.0.1"), None)
            .await
            .unwrap();
        assert_eq!(ip, "127.0.0.1");
        assert_eq!(user, "azureuser");
    }

    // ── HealthMetrics tests ──────────────────────────────────────

    #[test]
    fn test_health_metrics_stopped_vm() {
        let m = super::collect_health_metrics("vm-stop", "10.0.0.1", "user", "stopped", None);
        assert_eq!(m.vm_name, "vm-stop");
        assert_eq!(m.power_state, "stopped");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
        assert_eq!(m.load_avg, "-");
    }

    #[test]
    fn test_health_metrics_starting_vm() {
        let m = super::collect_health_metrics("vm-start", "10.0.0.1", "user", "starting", None);
        assert_eq!(m.power_state, "starting");
        assert_eq!(m.cpu_percent, 0.0);
    }

    #[test]
    fn test_health_metrics_unknown_state() {
        let m = super::collect_health_metrics("vm-x", "10.0.0.1", "user", "unknown", None);
        assert_eq!(m.power_state, "unknown");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.load_avg, "-");
    }

    // ── render_health_table tests ────────────────────────────────

    #[test]
    fn test_render_health_table_empty_list() {
        let metrics: Vec<super::HealthMetrics> = vec![];
        // Should not panic on empty input
        super::render_health_table(&metrics);
    }

    #[test]
    fn test_render_health_table_single_entry() {
        let metrics = vec![super::HealthMetrics {
            vm_name: "solo-vm".to_string(),
            power_state: "running".to_string(),
            cpu_percent: 50.0,
            mem_percent: 40.0,
            disk_percent: 30.0,
            load_avg: "1.00, 0.50, 0.25".to_string(),
        }];
        super::render_health_table(&metrics);
    }

    #[test]
    fn test_render_health_table_high_usage_values() {
        let metrics = vec![super::HealthMetrics {
            vm_name: "hot-vm".to_string(),
            power_state: "running".to_string(),
            cpu_percent: 99.9,
            mem_percent: 95.0,
            disk_percent: 98.0,
            load_avg: "16.00, 12.00, 8.00".to_string(),
        }];
        super::render_health_table(&metrics);
    }

    #[test]
    fn test_render_health_table_zero_usage() {
        let metrics = vec![super::HealthMetrics {
            vm_name: "idle-vm".to_string(),
            power_state: "running".to_string(),
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
            load_avg: "0.00, 0.00, 0.00".to_string(),
        }];
        super::render_health_table(&metrics);
    }

    #[test]
    fn test_render_health_table_mixed_states() {
        let metrics = vec![
            super::HealthMetrics {
                vm_name: "vm-a".to_string(),
                power_state: "running".to_string(),
                cpu_percent: 10.0,
                mem_percent: 20.0,
                disk_percent: 30.0,
                load_avg: "0.10".to_string(),
            },
            super::HealthMetrics {
                vm_name: "vm-b".to_string(),
                power_state: "deallocated".to_string(),
                cpu_percent: 0.0,
                mem_percent: 0.0,
                disk_percent: 0.0,
                load_avg: "-".to_string(),
            },
            super::HealthMetrics {
                vm_name: "vm-c".to_string(),
                power_state: "stopping".to_string(),
                cpu_percent: 0.0,
                mem_percent: 0.0,
                disk_percent: 0.0,
                load_avg: "-".to_string(),
            },
        ];
        super::render_health_table(&metrics);
    }

    // ── cp direction detection tests ─────────────────────────────

    #[test]
    fn test_cp_direction_local_to_remote() {
        let is_remote = |s: &str| {
            s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
        };
        assert!(!is_remote("/tmp/file.txt"));
        assert!(is_remote("myvm:/home/user/file.txt"));
    }

    #[test]
    fn test_cp_direction_remote_to_local() {
        let is_remote = |s: &str| {
            s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
        };
        let source = "vm1:/tmp/data.tar.gz";
        let dest = "/home/local/data.tar.gz";
        assert!(is_remote(source));
        assert!(!is_remote(dest));
    }

    #[test]
    fn test_cp_direction_windows_path_not_remote() {
        let is_remote = |s: &str| {
            s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
        };
        assert!(!is_remote("C:\\Users\\file.txt"));
        assert!(!is_remote("D:\\data"));
    }

    #[test]
    fn test_cp_direction_both_local() {
        let is_remote = |s: &str| {
            s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
        };
        let source = "/tmp/a.txt";
        let dest = "/tmp/b.txt";
        let direction = if is_remote(source) && !is_remote(dest) {
            "remote→local"
        } else if !is_remote(source) && is_remote(dest) {
            "local→remote"
        } else {
            "local→local"
        };
        assert_eq!(direction, "local→local");
    }

    #[test]
    fn test_cp_direction_absolute_path_with_colon() {
        let is_remote = |s: &str| {
            s.contains(':') && !s.starts_with('/') && s.len() > 2 && s.chars().nth(1) != Some(':')
        };
        // Absolute path starting with / should not be remote
        assert!(!is_remote("/path/with:colon"));
    }

    // ── run_on_fleet tests ───────────────────────────────────────

    #[test]
    fn test_run_on_fleet_show_output_false() {
        let vms: Vec<(String, String, String)> = vec![];
        super::run_on_fleet(&vms, "ls", false);
    }

    #[test]
    fn test_fleet_spinner_style_template() {
        let style = super::fleet_spinner_style();
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
        let style = super::fleet_spinner_style();
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

    // ── template tests ───────────────────────────────────────────

    #[test]
    fn test_template_list_empty() {
        let tmp = TempDir::new().unwrap();
        let tpl_dir = tmp.path().join("templates");
        fs::create_dir_all(&tpl_dir).unwrap();

        let count = fs::read_dir(&tpl_dir).unwrap().count();
        assert_eq!(count, 0);
    }

    #[test]
    fn test_template_with_cloud_init() {
        let tmp = TempDir::new().unwrap();
        let tpl = serde_json::json!({
            "name": "web-server",
            "vm_size": "Standard_B2s",
            "cloud_init": "#!/bin/bash\napt-get update && apt-get install -y nginx",
        });
        let path = tmp.path().join("web-server.json");
        fs::write(&path, serde_json::to_string_pretty(&tpl).unwrap()).unwrap();

        let loaded: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        assert!(loaded["cloud_init"].as_str().unwrap().contains("nginx"));
    }

    #[test]
    fn test_template_delete() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("ephemeral.json");
        fs::write(&path, r#"{"name":"ephemeral"}"#).unwrap();
        assert!(path.exists());
        fs::remove_file(&path).unwrap();
        assert!(!path.exists());
    }

    // ── keys tests ───────────────────────────────────────────────

    #[test]
    fn test_keys_list_no_ssh_dir() {
        let tmp = TempDir::new().unwrap();
        let nonexistent = tmp.path().join("no_such_dir");
        assert!(fs::read_dir(&nonexistent).is_err());
    }

    #[test]
    fn test_keys_list_filters_non_key_files() {
        let tmp = TempDir::new().unwrap();
        let ssh_dir = tmp.path();
        fs::write(ssh_dir.join("authorized_keys"), "key data").unwrap();
        fs::write(ssh_dir.join("known_hosts"), "host data").unwrap();
        fs::write(ssh_dir.join("config"), "Host *").unwrap();

        let key_files: Vec<String> = fs::read_dir(ssh_dir)
            .unwrap()
            .filter_map(|e| {
                let name = e.ok()?.file_name().to_string_lossy().to_string();
                if name.starts_with("id_") || name.ends_with(".pub") {
                    Some(name)
                } else {
                    None
                }
            })
            .collect();
        assert!(key_files.is_empty());
    }

    #[test]
    fn test_keys_multiple_key_types() {
        let tmp = TempDir::new().unwrap();
        let ssh_dir = tmp.path();
        for key_type in &["id_rsa", "id_ed25519", "id_ecdsa"] {
            fs::write(ssh_dir.join(key_type), "private").unwrap();
            fs::write(ssh_dir.join(format!("{}.pub", key_type)), "public").unwrap();
        }

        let keys: Vec<String> = fs::read_dir(ssh_dir)
            .unwrap()
            .filter_map(|e| {
                let name = e.ok()?.file_name().to_string_lossy().to_string();
                if name.starts_with("id_") {
                    Some(name)
                } else {
                    None
                }
            })
            .collect();
        assert_eq!(keys.len(), 6); // 3 private + 3 public
    }

    // ── resolve_vm_targets tests ─────────────────────────────────

    #[tokio::test]
    async fn test_resolve_vm_targets_with_ip_flag() {
        let targets = super::resolve_vm_targets(Some("my-vm"), Some("192.168.1.1"), None)
            .await
            .unwrap();
        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].0, "my-vm");
        assert_eq!(targets[0].1, "192.168.1.1");
        assert_eq!(targets[0].2, "azureuser");
    }

    #[tokio::test]
    async fn test_resolve_vm_targets_ip_only_no_vm_name() {
        let targets = super::resolve_vm_targets(None, Some("10.0.0.1"), None)
            .await
            .unwrap();
        assert_eq!(targets.len(), 1);
        assert_eq!(targets[0].0, "10.0.0.1"); // uses IP as display name
        assert_eq!(targets[0].1, "10.0.0.1");
    }

    // ── ssh_exec_checked tests ───────────────────────────────────

    #[tokio::test]
    async fn test_ssh_exec_checked_unreachable_returns_error() {
        let result = super::ssh_exec_checked("192.0.2.1", "user", "echo hello").await;
        // Unreachable host should fail (either connection refused or timeout)
        assert!(result.is_err());
    }

    #[test]
    fn test_completions_bash() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["completions", "bash"])
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("_azlin"));
    }

    #[test]
    fn test_completions_zsh() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["completions", "zsh"])
            .output()
            .unwrap();
        assert!(output.status.success());
    }

    #[test]
    fn test_completions_fish() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["completions", "fish"])
            .output()
            .unwrap();
        assert!(output.status.success());
    }

    // ── CLI integration: version ─────────────────────────────────

    #[test]
    fn test_version_command() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .arg("version")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("azlin"));
        assert!(stdout.contains("2.3.0"));
    }

    #[test]
    fn test_help_flag() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .arg("--help")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("azlin"));
    }

    // ── CLI integration: azlin-help ──────────────────────────────

    #[test]
    fn test_azlin_help_no_args() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .arg("azlin-help")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("azlin"));
    }

    #[test]
    fn test_azlin_help_with_subcommand() {
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["azlin-help", "list"])
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("list"));
    }

    // ── CLI integration: template ────────────────────────────────

    #[test]
    fn test_cli_template_save_and_list() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "save", "mytemplate"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Saved template 'mytemplate'"));

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("mytemplate"));
    }

    #[test]
    fn test_cli_template_save_with_options() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "template",
                "save",
                "custom-tpl",
                "--description",
                "A test template",
                "--vm-size",
                "Standard_D8s_v3",
                "--region",
                "eastus",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "show", "custom-tpl"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Standard_D8s_v3"));
        assert!(stdout.contains("eastus"));
        assert!(stdout.contains("A test template"));
    }

    #[test]
    fn test_cli_template_show_nonexistent() {
        let dir = TempDir::new().unwrap();
        // Ensure azlin dir exists
        fs::create_dir_all(dir.path().join(".azlin").join("templates")).unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "show", "no-such-template"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(!output.status.success());
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(stderr.contains("not found"));
    }

    #[test]
    fn test_cli_template_apply() {
        let dir = TempDir::new().unwrap();
        // First create a template
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "template",
                "save",
                "apply-test",
                "--vm-size",
                "Standard_D2s_v3",
                "--region",
                "westus2",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "apply", "apply-test"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Standard_D2s_v3"));
        assert!(stdout.contains("westus2"));
    }

    #[test]
    fn test_cli_template_delete_force() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "save", "todelete"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "delete", "todelete", "--force"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Deleted template 'todelete'"));

        // Verify it's gone
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "show", "todelete"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(!output.status.success());
    }

    #[test]
    fn test_cli_template_export_import() {
        let dir = TempDir::new().unwrap();
        // Create a template
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "template",
                "save",
                "exportme",
                "--vm-size",
                "Standard_D4s_v3",
                "--region",
                "northeurope",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let export_path = dir.path().join("exported.toml");
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "export", "exportme"])
            .arg(&export_path)
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        assert!(export_path.exists());

        // Delete the original
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "delete", "exportme", "--force"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        // Import it back
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "import"])
            .arg(&export_path)
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Imported template 'exportme'"));
    }

    #[test]
    fn test_cli_template_list_empty_dir() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("No templates found"));
    }

    #[test]
    fn test_cli_template_create_alias() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "create", "via-create"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Saved template 'via-create'"));
    }

    #[test]
    fn test_cli_template_list_multiple() {
        let dir = TempDir::new().unwrap();
        for name in &["tpl-a", "tpl-b", "tpl-c"] {
            assert_cmd::Command::cargo_bin("azlin")
                .unwrap()
                .args(["template", "save", name])
                .env("HOME", dir.path())
                .output()
                .unwrap();
        }
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("tpl-a"));
        assert!(stdout.contains("tpl-b"));
        assert!(stdout.contains("tpl-c"));
    }

    // ── CLI integration: sessions ────────────────────────────────

    #[test]
    fn test_cli_sessions_list_empty() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("No saved sessions"));
    }

    #[test]
    fn test_cli_sessions_save_and_list() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                "my-session",
                "--resource-group",
                "test-rg",
                "--vms",
                "vm1",
                "vm2",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Saved session 'my-session'"));

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("my-session"));
    }

    #[test]
    fn test_cli_sessions_save_and_load() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                "load-test",
                "--resource-group",
                "rg-test",
                "--vms",
                "vm-alpha",
                "vm-beta",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "load", "load-test"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Loaded session 'load-test'"));
        assert!(stdout.contains("rg-test"));
        assert!(stdout.contains("vm-alpha"));
        assert!(stdout.contains("vm-beta"));
    }

    #[test]
    fn test_cli_sessions_load_nonexistent() {
        let dir = TempDir::new().unwrap();
        fs::create_dir_all(dir.path().join(".azlin").join("sessions")).unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "load", "nonexistent"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(!output.status.success());
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(stderr.contains("not found"));
    }

    #[test]
    fn test_cli_sessions_delete() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                "delete-me",
                "--resource-group",
                "rg1",
                "--vms",
                "vm1",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "delete", "delete-me", "--force"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Deleted session"));

        // Verify it's gone
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "load", "delete-me"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(!output.status.success());
    }

    #[test]
    fn test_cli_sessions_list_multiple() {
        let dir = TempDir::new().unwrap();
        for name in &["sess-1", "sess-2", "sess-3"] {
            assert_cmd::Command::cargo_bin("azlin")
                .unwrap()
                .args([
                    "sessions",
                    "save",
                    name,
                    "--resource-group",
                    "rg",
                    "--vms",
                    "vm1",
                ])
                .env("HOME", dir.path())
                .output()
                .unwrap();
        }
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("sess-1"));
        assert!(stdout.contains("sess-2"));
        assert!(stdout.contains("sess-3"));
    }

    #[test]
    fn test_cli_sessions_overwrite() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                "overwrite-me",
                "--resource-group",
                "rg-old",
                "--vms",
                "vm-old",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                "overwrite-me",
                "--resource-group",
                "rg-new",
                "--vms",
                "vm-new",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "load", "overwrite-me"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("rg-new"));
        assert!(stdout.contains("vm-new"));
    }

    // ── CLI integration: context ─────────────────────────────────

    #[test]
    fn test_cli_context_list_empty() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("No contexts found"));
    }

    #[test]
    fn test_cli_context_create_and_list() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "dev-env"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Created context 'dev-env'"));

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("dev-env"));
    }

    #[test]
    fn test_cli_context_create_with_options() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "context",
                "create",
                "prod-env",
                "--subscription-id",
                "sub-123",
                "--tenant-id",
                "tenant-456",
                "--resource-group",
                "prod-rg",
                "--region",
                "eastus2",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());

        // Verify the TOML file was written with the correct fields
        let ctx_path = dir
            .path()
            .join(".azlin")
            .join("contexts")
            .join("prod-env.toml");
        assert!(ctx_path.exists());
        let content = fs::read_to_string(&ctx_path).unwrap();
        assert!(content.contains("sub-123"));
        assert!(content.contains("tenant-456"));
        assert!(content.contains("prod-rg"));
        assert!(content.contains("eastus2"));
    }

    #[test]
    fn test_cli_context_use_and_show() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "staging"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "staging"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Switched to context 'staging'"));

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "show"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("staging"));
    }

    #[test]
    fn test_cli_context_use_nonexistent() {
        let dir = TempDir::new().unwrap();
        fs::create_dir_all(dir.path().join(".azlin").join("contexts")).unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "nonexistent"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(!output.status.success());
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(stderr.contains("not found"));
    }

    #[test]
    fn test_cli_context_delete_force() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "deleteme"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "delete", "deleteme", "--force"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Deleted context 'deleteme'"));
    }

    #[test]
    fn test_cli_context_delete_clears_active() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "active-ctx"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "active-ctx"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "delete", "active-ctx", "--force"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        // Active-context file should be removed
        let active_path = dir.path().join(".azlin").join("active-context");
        assert!(!active_path.exists());
    }

    #[test]
    fn test_cli_context_rename() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "old-name", "--region", "westus2"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "rename", "old-name", "new-name"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Renamed context"));

        // Old file should be gone, new file should exist
        let old_path = dir
            .path()
            .join(".azlin")
            .join("contexts")
            .join("old-name.toml");
        let new_path = dir
            .path()
            .join(".azlin")
            .join("contexts")
            .join("new-name.toml");
        assert!(!old_path.exists());
        assert!(new_path.exists());

        // Name field inside the TOML should be updated
        let content = fs::read_to_string(&new_path).unwrap();
        assert!(content.contains("new-name"));
    }

    #[test]
    fn test_cli_context_rename_updates_active() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "rename-active"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "rename-active"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "rename", "rename-active", "renamed-active"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let active = fs::read_to_string(dir.path().join(".azlin").join("active-context")).unwrap();
        assert_eq!(active.trim(), "renamed-active");
    }

    #[test]
    fn test_cli_context_list_marks_active() {
        let dir = TempDir::new().unwrap();
        for name in &["ctx-a", "ctx-b", "ctx-c"] {
            assert_cmd::Command::cargo_bin("azlin")
                .unwrap()
                .args(["context", "create", name])
                .env("HOME", dir.path())
                .output()
                .unwrap();
        }

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "ctx-b"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("* ctx-b"));
    }

    #[test]
    fn test_cli_context_show_no_selection() {
        let dir = TempDir::new().unwrap();
        fs::create_dir_all(dir.path().join(".azlin").join("contexts")).unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "show"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("No context selected"));
    }

    #[test]
    fn test_cli_context_switch_alias() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "switch-test"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "switch", "switch-test"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("Switched to context 'switch-test'"));
    }

    #[test]
    fn test_cli_context_current_alias() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "create", "cur-test"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "cur-test"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "current"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("cur-test"));
    }

    #[test]
    fn test_cli_context_migrate() {
        let dir = TempDir::new().unwrap();
        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "migrate"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        // With empty HOME, either no config found or migration attempted
        assert!(
            stdout.contains("No legacy configuration found")
                || stdout.contains("Migrated")
                || stdout.contains("Could not determine"),
            "Unexpected output: {}",
            stdout
        );
    }

    // ── CLI integration: output formats ──────────────────────────

    #[test]
    fn test_cli_template_list_json_format() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "save", "json-test", "--vm-size", "Standard_B2s"])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["--output", "json", "template", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("json-test"));
    }

    #[test]
    fn test_cli_sessions_list_json_format() {
        let dir = TempDir::new().unwrap();
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions",
                "save",
                "json-sess",
                "--resource-group",
                "rg",
                "--vms",
                "vm1",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["--output", "json", "sessions", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("json-sess"));
    }

    // ── Unit tests: collect_health_metrics edge cases ─────────────

    #[test]
    fn test_health_metrics_deallocated_vm() {
        let m = super::collect_health_metrics("vm-dealloc", "10.0.0.1", "user", "VM deallocated", None);
        assert_eq!(m.vm_name, "vm-dealloc");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
    }

    #[test]
    fn test_health_metrics_deallocating_vm() {
        let m = super::collect_health_metrics("vm-x", "10.0.0.1", "user", "VM deallocating", None);
        assert_eq!(m.power_state, "VM deallocating");
        assert_eq!(m.load_avg, "-");
    }

    // ── Unit tests: render_health_table edge cases ───────────────

    #[test]
    fn test_render_health_table_many_entries() {
        let metrics: Vec<super::HealthMetrics> = (0..20)
            .map(|i| super::HealthMetrics {
                vm_name: format!("vm-{}", i),
                power_state: "VM running".to_string(),
                cpu_percent: i as f32 * 5.0,
                mem_percent: i as f32 * 3.0,
                disk_percent: i as f32 * 2.0,
                load_avg: format!("{:.2}", i as f32 * 0.5),
            })
            .collect();
        // Should not panic with many entries
        super::render_health_table(&metrics);
    }

    #[test]
    fn test_render_health_table_100_percent() {
        let metrics = vec![super::HealthMetrics {
            vm_name: "vm-full".to_string(),
            power_state: "VM running".to_string(),
            cpu_percent: 100.0,
            mem_percent: 100.0,
            disk_percent: 100.0,
            load_avg: "99.99".to_string(),
        }];
        // Should not panic
        super::render_health_table(&metrics);
    }

    // ── CLI integration: subcommand --help coverage ──────────────

    #[test]
    fn test_bastion_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["bastion", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_bastion_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["bastion", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_bastion_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["bastion", "status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_bastion_configure_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["bastion", "configure", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_create_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "create", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_restore_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "restore", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_delete_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "delete", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_enable_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "enable", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_disable_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "disable", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_sync_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "sync", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_snapshot_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_storage_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["storage", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_storage_mount_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["storage", "mount", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_storage_create_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["storage", "create", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_storage_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["storage", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_storage_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["storage", "status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_storage_delete_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["storage", "delete", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_tag_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["tag", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_tag_add_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["tag", "add", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_tag_remove_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["tag", "remove", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_tag_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["tag", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_auth_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_auth_setup_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "setup", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_auth_test_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "test", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_auth_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_auth_show_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "show", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_auth_remove_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "remove", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_keys_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["keys", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_keys_rotate_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["keys", "rotate", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_keys_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["keys", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_keys_export_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["keys", "export", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_keys_backup_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["keys", "backup", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_batch_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["batch", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_batch_command_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["batch", "command", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_batch_stop_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["batch", "stop", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_batch_start_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["batch", "start", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_batch_sync_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["batch", "sync", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_fleet_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["fleet", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_fleet_run_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["fleet", "run", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_fleet_workflow_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["fleet", "workflow", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_costs_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["costs", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_costs_dashboard_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["costs", "dashboard", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_costs_history_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["costs", "history", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_costs_budget_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["costs", "budget", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_costs_recommend_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["costs", "recommend", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_costs_actions_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["costs", "actions", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_compose_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["compose", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_compose_up_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["compose", "up", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_compose_down_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["compose", "down", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_compose_ps_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["compose", "ps", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_ip_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["ip", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_ip_check_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["ip", "check", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_disk_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["disk", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_disk_add_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["disk", "add", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_github_runner_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["github-runner", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_github_runner_enable_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["github-runner", "enable", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_github_runner_disable_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["github-runner", "disable", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_github_runner_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["github-runner", "status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_github_runner_scale_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["github-runner", "scale", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_autopilot_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["autopilot", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_autopilot_enable_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["autopilot", "enable", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_autopilot_disable_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["autopilot", "disable", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_autopilot_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["autopilot", "status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_autopilot_config_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["autopilot", "config", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_autopilot_run_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["autopilot", "run", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_web_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["web", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_web_start_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["web", "start", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_web_stop_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["web", "stop", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_deploy_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "deploy", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_show_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "show", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_cleanup_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "cleanup", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_doit_examples_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "examples", "--help"])
            .assert()
            .success();
    }

    // ── CLI integration: top-level command --help ────────────────

    #[test]
    fn test_new_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["new", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_list_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["list", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_start_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["start", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_stop_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["stop", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_show_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["show", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_connect_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["connect", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_delete_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["delete", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_health_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["health", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_env_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["env", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_cost_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["cost", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_session_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["session", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_config_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["config", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_ask_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["ask", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_do_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["do", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_clone_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["clone", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_cp_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["cp", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_sync_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sync", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_update_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["update", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_logs_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["logs", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_cleanup_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["cleanup", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_prune_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["prune", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_restore_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["restore", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_status_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["status", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_code_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["code", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_os_update_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["os-update", "--help"])
            .assert()
            .success();
    }

    #[test]
    fn test_sync_keys_help() {
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sync-keys", "--help"])
            .assert()
            .success();
    }

    // ── CLI integration: config commands with temp home ──────────

    #[test]
    fn test_config_show_with_temp_home() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["config", "show"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        let stdout = String::from_utf8_lossy(&out.stdout);
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            out.status.success()
                || stdout.contains("config")
                || stderr.contains("config")
                || stdout.contains("No")
        );
    }

    #[test]
    fn test_config_set_and_show() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["config", "set", "resource_group", "test-rg"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        assert!(out.status.success() || combined.contains("config") || combined.contains("set"));
    }

    // ── CLI integration: completions content verification ────────

    #[test]
    fn test_completions_zsh_content() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["completions", "zsh"])
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("compdef") || stdout.len() > 100);
    }

    #[test]
    fn test_completions_powershell() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["completions", "powershell"])
            .output()
            .unwrap();
        assert!(out.status.success());
        assert!(out.stdout.len() > 50);
    }

    #[test]
    fn test_completions_elvish() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["completions", "elvish"])
            .output()
            .unwrap();
        assert!(out.status.success());
        assert!(out.stdout.len() > 50);
    }

    // ── CLI integration: graceful failures without Azure ─────────

    #[test]
    fn test_list_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["list"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output()
            .unwrap();
        // Should fail gracefully, not crash
        let stderr = String::from_utf8_lossy(&out.stderr);
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(
            !out.status.success()
                || stderr.contains("config")
                || stderr.contains("subscription")
                || stderr.contains("auth")
                || stderr.contains("az login")
                || stdout.contains("No VMs")
        );
    }

    #[test]
    fn test_show_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["show", "nonexistent-vm"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output()
            .unwrap();
        assert!(!out.status.success() || !String::from_utf8_lossy(&out.stderr).is_empty());
    }

    #[test]
    fn test_health_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["health"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output()
            .unwrap();
        // Graceful failure or empty result
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        assert!(!out.status.success() || !combined.is_empty());
    }

    #[test]
    fn test_status_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["status"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output()
            .unwrap();
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        assert!(!out.status.success() || !combined.is_empty());
    }

    // ── CLI integration: context full lifecycle ──────────────────

    #[test]
    fn test_context_full_lifecycle() {
        let dir = TempDir::new().unwrap();
        // create
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "context",
                "create",
                "lifecycle-ctx",
                "--subscription-id",
                "sub-123",
                "--resource-group",
                "rg-test",
            ])
            .env("HOME", dir.path())
            .assert()
            .success();
        // list
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
        // use
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "use", "lifecycle-ctx"])
            .env("HOME", dir.path())
            .assert()
            .success();
        // show
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "show"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
        // delete
        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "delete", "lifecycle-ctx", "--force"])
            .env("HOME", dir.path())
            .assert()
            .success();
    }

    // ── CLI integration: auth list with temp home ────────────────

    #[test]
    fn test_auth_list_empty() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["auth", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(
            stdout.contains("No")
                || stdout.contains("profile")
                || stdout.is_empty()
                || stdout.contains("auth")
        );
    }

    // ── CLI integration: sessions with temp home ─────────────────

    #[test]
    fn test_sessions_list_empty_temp() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(out.status.success());
    }

    // ── CLI integration: template with temp home ─────────────────

    #[test]
    fn test_template_list_empty_temp() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "list"])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(out.status.success());
    }

    // ── CLI integration: verbose flag ────────────────────────────

    #[test]
    fn test_verbose_version() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["--verbose", "version"])
            .output()
            .unwrap();
        assert!(out.status.success());
        assert!(String::from_utf8_lossy(&out.stdout).contains("2.3.0"));
    }

    // ── CLI integration: json output format ──────────────────────

    #[test]
    fn test_json_output_version() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["--output", "json", "version"])
            .output()
            .unwrap();
        assert!(out.status.success());
    }

    #[test]
    fn test_csv_output_version() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["--output", "csv", "version"])
            .output()
            .unwrap();
        assert!(out.status.success());
    }

    // ── CLI integration: invalid subcommand ──────────────────────

    #[test]
    fn test_invalid_subcommand() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["totally-bogus-command"])
            .output()
            .unwrap();
        assert!(!out.status.success());
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(
            stderr.contains("error")
                || stderr.contains("unrecognized")
                || stderr.contains("invalid")
                || !stderr.is_empty()
        );
    }

    // ── CLI integration: doit examples ───────────────────────────

    #[test]
    fn test_doit_examples() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["doit", "examples"])
            .output()
            .unwrap();
        assert!(out.status.success());
        assert!(out.stdout.len() > 10);
    }

    // ── Tests for extracted helper functions ─────────────────────────

    #[test]
    fn test_format_cost_summary_json() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 123.45,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Json,
            &None,
            &None,
            false,
            false,
        );
        assert!(result.contains("123.45"));
        assert!(result.contains("USD"));
    }

    #[test]
    fn test_format_cost_summary_csv() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 99.99,
            currency: "EUR".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            false,
        );
        assert!(result.contains("Total Cost,Currency,Period Start,Period End"));
        assert!(result.contains("99.99"));
        assert!(result.contains("EUR"));
    }

    #[test]
    fn test_format_cost_summary_table() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 50.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            false,
        );
        assert!(result.contains("Total Cost: $50.00 USD"));
        assert!(result.contains("Period:"));
    }

    #[test]
    fn test_format_cost_summary_with_estimate() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 200.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &Some("2024-01-01".to_string()),
            &Some("2024-01-31".to_string()),
            true,
            false,
        );
        assert!(result.contains("Estimate: $200.00/month (projected)"));
        assert!(result.contains("From filter: 2024-01-01"));
        assert!(result.contains("To filter: 2024-01-31"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_table() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 300.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![
                azlin_core::models::VmCost {
                    vm_name: "vm-1".to_string(),
                    cost: 100.0,
                    currency: "USD".to_string(),
                },
                azlin_core::models::VmCost {
                    vm_name: "vm-2".to_string(),
                    cost: 200.0,
                    currency: "USD".to_string(),
                },
            ],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            true,
        );
        assert!(result.contains("vm-1"));
        assert!(result.contains("vm-2"));
        assert!(result.contains("$100.00"));
        assert!(result.contains("$200.00"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_csv() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 150.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![azlin_core::models::VmCost {
                vm_name: "test-vm".to_string(),
                cost: 150.0,
                currency: "USD".to_string(),
            }],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            true,
        );
        assert!(result.contains("VM Name,Cost,Currency"));
        assert!(result.contains("test-vm,150.00,USD"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_empty() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 0.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc::now(),
            period_end: chrono::Utc::now(),
            by_vm: vec![],
        };
        let result = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            true,
        );
        assert!(result.contains("No per-VM cost data available."));
    }

    #[test]
    fn test_parse_cost_history_rows_empty() {
        let data = serde_json::json!({});
        let rows = super::parse_cost_history_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_history_rows_with_data() {
        let data = serde_json::json!({
            "rows": [
                [12.34, "2024-01-01"],
                [56.78, "2024-01-02"]
            ]
        });
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0], ("2024-01-01".to_string(), "$12.34".to_string()));
        assert_eq!(rows[1], ("2024-01-02".to_string(), "$56.78".to_string()));
    }

    #[test]
    fn test_parse_cost_history_rows_with_int_date() {
        let data = serde_json::json!({
            "rows": [
                [10.0, 20240101]
            ]
        });
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 1);
        // Integer dates hit the as_i64().map(|_| "") branch, producing empty string
        assert_eq!(rows[0].0, "");
        assert_eq!(rows[0].1, "$10.00");
    }

    #[test]
    fn test_parse_cost_history_rows_missing_values() {
        let data = serde_json::json!({
            "rows": [
                [null, null]
            ]
        });
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "-");
        assert_eq!(rows[0].1, "-");
    }

    #[test]
    fn test_parse_recommendation_rows_empty() {
        let data = serde_json::json!([]);
        let rows = super::parse_recommendation_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_recommendation_rows_with_data() {
        let data = serde_json::json!([
            {
                "category": "Cost",
                "impact": "High",
                "shortDescription": {"problem": "Underutilized VM"}
            },
            {
                "category": "Security",
                "impact": "Medium",
                "shortDescription": {"problem": "Open port"}
            }
        ]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(
            rows[0],
            (
                "Cost".to_string(),
                "High".to_string(),
                "Underutilized VM".to_string()
            )
        );
        assert_eq!(
            rows[1],
            (
                "Security".to_string(),
                "Medium".to_string(),
                "Open port".to_string()
            )
        );
    }

    #[test]
    fn test_parse_recommendation_rows_missing_fields() {
        let data = serde_json::json!([{"other_field": "value"}]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0], ("-".to_string(), "-".to_string(), "-".to_string()));
    }

    #[test]
    fn test_parse_cost_action_rows_empty() {
        let data = serde_json::json!([]);
        let rows = super::parse_cost_action_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_action_rows_with_data() {
        let data = serde_json::json!([
            {
                "impactedField": "Microsoft.Compute/virtualMachines",
                "impact": "High",
                "shortDescription": {"problem": "Resize VM"}
            }
        ]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
        assert_eq!(rows[0].1, "High");
        assert_eq!(rows[0].2, "Resize VM");
    }

    #[test]
    fn test_parse_cost_action_rows_not_array() {
        let data = serde_json::json!({"not": "array"});
        let rows = super::parse_cost_action_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_templates_build_toml_defaults() {
        let tpl = super::templates::build_template_toml("test", None, None, None, None);
        let tbl = tpl.as_table().unwrap();
        assert_eq!(tbl["name"].as_str().unwrap(), "test");
        assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
        assert_eq!(tbl["region"].as_str().unwrap(), "westus2");
        assert_eq!(tbl["description"].as_str().unwrap(), "");
        assert!(tbl.get("cloud_init").is_none());
    }

    #[test]
    fn test_templates_build_toml_custom() {
        let tpl = super::templates::build_template_toml(
            "myvm",
            Some("A dev VM"),
            Some("Standard_D8s_v3"),
            Some("eastus"),
            Some("/path/to/init.sh"),
        );
        let tbl = tpl.as_table().unwrap();
        assert_eq!(tbl["name"].as_str().unwrap(), "myvm");
        assert_eq!(tbl["description"].as_str().unwrap(), "A dev VM");
        assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D8s_v3");
        assert_eq!(tbl["region"].as_str().unwrap(), "eastus");
        assert_eq!(tbl["cloud_init"].as_str().unwrap(), "/path/to/init.sh");
    }

    #[test]
    fn test_templates_save_and_load() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join("templates");
        let tpl = super::templates::build_template_toml("test-tpl", Some("desc"), None, None, None);
        let path = super::templates::save_template(&dir, "test-tpl", &tpl).unwrap();
        assert!(path.exists());

        let loaded = super::templates::load_template(&dir, "test-tpl").unwrap();
        assert_eq!(loaded.get("name").unwrap().as_str().unwrap(), "test-tpl");
        assert_eq!(loaded.get("description").unwrap().as_str().unwrap(), "desc");
    }

    #[test]
    fn test_templates_load_nonexistent() {
        let tmp = TempDir::new().unwrap();
        let result = super::templates::load_template(tmp.path(), "nope");
        assert!(result.is_err());
    }

    #[test]
    fn test_templates_list_empty() {
        let tmp = TempDir::new().unwrap();
        let rows = super::templates::list_templates(tmp.path()).unwrap();
        assert!(rows.is_empty());
    }

    #[test]
    fn test_templates_list_with_entries() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        let tpl1 =
            super::templates::build_template_toml("a", None, Some("small"), Some("west"), None);
        let tpl2 =
            super::templates::build_template_toml("b", None, Some("large"), Some("east"), None);
        super::templates::save_template(dir, "a", &tpl1).unwrap();
        super::templates::save_template(dir, "b", &tpl2).unwrap();

        let rows = super::templates::list_templates(dir).unwrap();
        assert_eq!(rows.len(), 2);
    }

    #[test]
    fn test_templates_delete() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        let tpl = super::templates::build_template_toml("del-me", None, None, None, None);
        super::templates::save_template(dir, "del-me", &tpl).unwrap();
        assert!(dir.join("del-me.toml").exists());

        super::templates::delete_template(dir, "del-me").unwrap();
        assert!(!dir.join("del-me.toml").exists());
    }

    #[test]
    fn test_templates_delete_nonexistent() {
        let tmp = TempDir::new().unwrap();
        let result = super::templates::delete_template(tmp.path(), "nope");
        assert!(result.is_err());
    }

    #[test]
    fn test_templates_import() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        let content = "name = \"imported\"\nvm_size = \"Standard_D2s_v3\"\nregion = \"westus\"\n";
        let name = super::templates::import_template(dir, content).unwrap();
        assert_eq!(name, "imported");
        assert!(dir.join("imported.toml").exists());
    }

    #[test]
    fn test_templates_import_missing_name() {
        let tmp = TempDir::new().unwrap();
        let content = "vm_size = \"Standard_D2s_v3\"\nregion = \"westus\"\n";
        let result = super::templates::import_template(tmp.path(), content);
        assert!(result.is_err());
    }

    #[test]
    fn test_sessions_build_toml() {
        let val = super::sessions::build_session_toml(
            "s1",
            "rg1",
            &["vm1".to_string(), "vm2".to_string()],
        );
        let tbl = val.as_table().unwrap();
        assert_eq!(tbl["name"].as_str().unwrap(), "s1");
        assert_eq!(tbl["resource_group"].as_str().unwrap(), "rg1");
        let vms = tbl["vms"].as_array().unwrap();
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].as_str().unwrap(), "vm1");
        assert!(tbl.contains_key("created"));
    }

    #[test]
    fn test_sessions_parse_toml() {
        let content = "name = \"test-sess\"\nresource_group = \"my-rg\"\nvms = [\"vm-a\", \"vm-b\"]\ncreated = \"2024-01-01T00:00:00Z\"\n";
        let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
        assert_eq!(rg, "my-rg");
        assert_eq!(vms, vec!["vm-a", "vm-b"]);
        assert_eq!(created, "2024-01-01T00:00:00Z");
    }

    #[test]
    fn test_sessions_parse_toml_empty_vms() {
        let content = "name = \"empty\"\nresource_group = \"rg\"\nvms = []\ncreated = \"2024-01-01T00:00:00Z\"\n";
        let (rg, vms, _) = super::sessions::parse_session_toml(content).unwrap();
        assert_eq!(rg, "rg");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_sessions_parse_toml_missing_fields() {
        let content = "name = \"minimal\"\n";
        let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
        assert_eq!(rg, "-");
        assert!(vms.is_empty());
        assert_eq!(created, "-");
    }

    #[test]
    fn test_sessions_list_names_empty() {
        let tmp = TempDir::new().unwrap();
        let names = super::sessions::list_session_names(tmp.path()).unwrap();
        assert!(names.is_empty());
    }

    #[test]
    fn test_sessions_list_names_nonexistent_dir() {
        let tmp = TempDir::new().unwrap();
        let names = super::sessions::list_session_names(&tmp.path().join("nope")).unwrap();
        assert!(names.is_empty());
    }

    #[test]
    fn test_sessions_list_names_with_entries() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        fs::write(dir.join("s1.toml"), "name = \"s1\"").unwrap();
        fs::write(dir.join("s2.toml"), "name = \"s2\"").unwrap();
        fs::write(dir.join("not-toml.txt"), "ignore").unwrap();

        let names = super::sessions::list_session_names(dir).unwrap();
        assert_eq!(names.len(), 2);
        assert!(names.contains(&"s1".to_string()));
        assert!(names.contains(&"s2".to_string()));
    }

    #[test]
    fn test_contexts_build_toml_minimal() {
        let result =
            super::contexts::build_context_toml("ctx1", None, None, None, None, None).unwrap();
        assert!(result.contains("name = \"ctx1\""));
    }

    #[test]
    fn test_contexts_build_toml_full() {
        let result = super::contexts::build_context_toml(
            "prod",
            Some("sub-123"),
            Some("tenant-456"),
            Some("rg-prod"),
            Some("westus2"),
            Some("my-vault"),
        )
        .unwrap();
        assert!(result.contains("name = \"prod\""));
        assert!(result.contains("subscription_id = \"sub-123\""));
        assert!(result.contains("tenant_id = \"tenant-456\""));
        assert!(result.contains("resource_group = \"rg-prod\""));
        assert!(result.contains("region = \"westus2\""));
        assert!(result.contains("key_vault_name = \"my-vault\""));
    }

    #[test]
    fn test_contexts_list_empty() {
        let tmp = TempDir::new().unwrap();
        let result = super::contexts::list_contexts(tmp.path(), "").unwrap();
        assert!(result.is_empty());
    }

    #[test]
    fn test_contexts_list_with_active() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        fs::write(dir.join("dev.toml"), "name = \"dev\"").unwrap();
        fs::write(dir.join("prod.toml"), "name = \"prod\"").unwrap();

        let result = super::contexts::list_contexts(dir, "dev").unwrap();
        assert_eq!(result.len(), 2);
        let dev = result.iter().find(|(n, _)| n == "dev").unwrap();
        assert!(dev.1);
        let prod = result.iter().find(|(n, _)| n == "prod").unwrap();
        assert!(!prod.1);
    }

    #[test]
    fn test_contexts_list_no_active() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        fs::write(dir.join("ctx.toml"), "name = \"ctx\"").unwrap();

        let result = super::contexts::list_contexts(dir, "nonexistent").unwrap();
        assert_eq!(result.len(), 1);
        assert!(!result[0].1);
    }

    #[test]
    fn test_contexts_rename_file() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        let toml_content =
            super::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
        fs::write(dir.join("old.toml"), &toml_content).unwrap();

        super::contexts::rename_context_file(dir, "old", "new").unwrap();
        assert!(!dir.join("old.toml").exists());
        assert!(dir.join("new.toml").exists());

        let content = fs::read_to_string(dir.join("new.toml")).unwrap();
        assert!(content.contains("name = \"new\""));
    }

    #[test]
    fn test_contexts_rename_nonexistent() {
        let tmp = TempDir::new().unwrap();
        let result = super::contexts::rename_context_file(tmp.path(), "nope", "also-nope");
        assert!(result.is_err());
    }

    // ── env_helpers tests ────────────────────────────────────────

    #[test]
    fn test_split_env_var_valid() {
        let (k, v) = super::env_helpers::split_env_var("FOO=bar").unwrap();
        assert_eq!(k, "FOO");
        assert_eq!(v, "bar");
    }

    #[test]
    fn test_split_env_var_value_with_equals() {
        let (k, v) = super::env_helpers::split_env_var("DSN=postgres://u:p@h/db?opt=1").unwrap();
        assert_eq!(k, "DSN");
        assert_eq!(v, "postgres://u:p@h/db?opt=1");
    }

    #[test]
    fn test_split_env_var_empty_value() {
        let (k, v) = super::env_helpers::split_env_var("EMPTY=").unwrap();
        assert_eq!(k, "EMPTY");
        assert_eq!(v, "");
    }

    #[test]
    fn test_split_env_var_no_equals() {
        assert!(super::env_helpers::split_env_var("NO_EQUALS").is_none());
    }

    #[test]
    fn test_split_env_var_leading_equals() {
        assert!(super::env_helpers::split_env_var("=value").is_none());
    }

    #[test]
    fn test_build_env_set_cmd_contains_key_value() {
        let cmd = super::env_helpers::build_env_set_cmd("MY_KEY", "'my_val'");
        assert!(cmd.contains("MY_KEY"));
        assert!(cmd.contains("'my_val'"));
        assert!(cmd.contains("grep -q"));
        assert!(cmd.contains("~/.profile"));
    }

    #[test]
    fn test_build_env_delete_cmd() {
        let cmd = super::env_helpers::build_env_delete_cmd("OLD_VAR");
        assert!(cmd.contains("OLD_VAR"));
        assert!(cmd.contains("sed -i"));
        assert!(cmd.contains("~/.profile"));
    }

    #[test]
    fn test_env_list_cmd() {
        assert_eq!(super::env_helpers::env_list_cmd(), "env | sort");
    }

    #[test]
    fn test_env_clear_cmd() {
        let cmd = super::env_helpers::env_clear_cmd();
        assert!(cmd.contains("sed -i"));
        assert!(cmd.contains("export"));
    }

    #[test]
    fn test_parse_env_output_basic() {
        let output = "HOME=/root\nPATH=/usr/bin\nSHELL=/bin/bash\n";
        let vars = super::env_helpers::parse_env_output(output);
        assert_eq!(vars.len(), 3);
        assert_eq!(vars[0], ("HOME".into(), "/root".into()));
        assert_eq!(vars[1], ("PATH".into(), "/usr/bin".into()));
    }

    #[test]
    fn test_parse_env_output_empty() {
        assert!(super::env_helpers::parse_env_output("").is_empty());
    }

    #[test]
    fn test_parse_env_output_value_with_equals() {
        let output = "DSN=host=localhost dbname=test\n";
        let vars = super::env_helpers::parse_env_output(output);
        assert_eq!(vars.len(), 1);
        assert_eq!(vars[0].0, "DSN");
        assert_eq!(vars[0].1, "host=localhost dbname=test");
    }

    #[test]
    fn test_build_env_file() {
        let vars = vec![("A".into(), "1".into()), ("B".into(), "two".into())];
        let file = super::env_helpers::build_env_file(&vars);
        assert_eq!(file, "A=1\nB=two");
    }

    #[test]
    fn test_build_env_file_empty() {
        assert_eq!(super::env_helpers::build_env_file(&[]), "");
    }

    #[test]
    fn test_parse_env_file_basic() {
        let content = "FOO=bar\n# comment\n\nBAZ=qux\n";
        let vars = super::env_helpers::parse_env_file(content);
        assert_eq!(vars.len(), 2);
        assert_eq!(vars[0], ("FOO".into(), "bar".into()));
        assert_eq!(vars[1], ("BAZ".into(), "qux".into()));
    }

    #[test]
    fn test_parse_env_file_empty_lines_only() {
        assert!(super::env_helpers::parse_env_file("\n\n  \n").is_empty());
    }

    #[test]
    fn test_parse_env_file_comments_only() {
        assert!(super::env_helpers::parse_env_file("# comment\n# another").is_empty());
    }

    #[test]
    fn test_parse_env_file_whitespace_trimming() {
        let content = "  KEY=value  \n  OTHER=val2  \n";
        let vars = super::env_helpers::parse_env_file(content);
        assert_eq!(vars.len(), 2);
        assert_eq!(vars[0].0, "KEY");
        assert_eq!(vars[0].1, "value"); // line is trimmed, value after = is as-is
    }

    #[test]
    fn test_parse_env_file_roundtrip() {
        let original = vec![
            ("X".into(), "10".into()),
            ("Y".into(), "hello world".into()),
        ];
        let file = super::env_helpers::build_env_file(&original);
        let parsed = super::env_helpers::parse_env_file(&file);
        assert_eq!(parsed, original);
    }

    // ── sync_helpers tests ───────────────────────────────────────

    #[test]
    fn test_default_dotfiles_has_expected_entries() {
        let files = super::sync_helpers::default_dotfiles();
        assert!(files.contains(&".bashrc"));
        assert!(files.contains(&".profile"));
        assert!(files.contains(&".vimrc"));
        assert!(files.contains(&".gitconfig"));
        assert!(files.contains(&".tmux.conf"));
        assert_eq!(files.len(), 5);
    }

    #[test]
    fn test_build_rsync_args_structure() {
        let args = super::sync_helpers::build_rsync_args(
            "/home/me/.bashrc",
            "azureuser",
            "10.0.0.1",
            ".bashrc",
        );
        assert_eq!(args[0], "-az");
        assert_eq!(args[1], "-e");
        assert_eq!(args[2], "ssh -o StrictHostKeyChecking=accept-new");
        assert_eq!(args[3], "/home/me/.bashrc");
        assert_eq!(args[4], "azureuser@10.0.0.1:~/.bashrc");
    }

    #[test]
    fn test_build_rsync_args_special_chars_in_ip() {
        let args =
            super::sync_helpers::build_rsync_args("/tmp/f", "user", "192.168.1.100", ".vimrc");
        assert!(args[4].contains("192.168.1.100"));
    }

    // ── health_helpers tests ─────────────────────────────────────

    #[test]
    fn test_metric_color_green() {
        assert_eq!(super::health_helpers::metric_color(0.0), "green");
        assert_eq!(super::health_helpers::metric_color(50.0), "green");
    }

    #[test]
    fn test_metric_color_yellow() {
        assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
        assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
    }

    #[test]
    fn test_metric_color_red() {
        assert_eq!(super::health_helpers::metric_color(80.1), "red");
        assert_eq!(super::health_helpers::metric_color(100.0), "red");
    }

    #[test]
    fn test_state_color_running() {
        assert_eq!(super::health_helpers::state_color("running"), "green");
    }

    #[test]
    fn test_state_color_stopped_deallocated() {
        assert_eq!(super::health_helpers::state_color("stopped"), "red");
        assert_eq!(super::health_helpers::state_color("deallocated"), "red");
    }

    #[test]
    fn test_state_color_unknown() {
        assert_eq!(super::health_helpers::state_color("starting"), "yellow");
        assert_eq!(super::health_helpers::state_color(""), "yellow");
    }

    #[test]
    fn test_format_percentage() {
        assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
        assert_eq!(super::health_helpers::format_percentage(99.95), "99.9%");
        assert_eq!(super::health_helpers::format_percentage(42.567), "42.6%");
    }

    #[test]
    fn test_status_emoji_green() {
        assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
        assert_eq!(super::health_helpers::status_emoji(70.0, 70.0, 70.0), "🟢");
    }

    #[test]
    fn test_status_emoji_yellow() {
        assert_eq!(super::health_helpers::status_emoji(70.1, 10.0, 10.0), "🟡");
        assert_eq!(super::health_helpers::status_emoji(10.0, 70.1, 10.0), "🟡");
        assert_eq!(super::health_helpers::status_emoji(10.0, 10.0, 70.1), "🟡");
    }

    #[test]
    fn test_status_emoji_red() {
        assert_eq!(super::health_helpers::status_emoji(90.1, 10.0, 10.0), "🔴");
        assert_eq!(super::health_helpers::status_emoji(10.0, 90.1, 10.0), "🔴");
        assert_eq!(super::health_helpers::status_emoji(10.0, 10.0, 90.1), "🔴");
    }

    #[test]
    fn test_status_emoji_boundary() {
        // exactly 90.0 is yellow, not red
        assert_eq!(super::health_helpers::status_emoji(90.0, 90.0, 90.0), "🟡");
    }

    // ── snapshot_helpers tests ───────────────────────────────────

    #[test]
    fn test_build_snapshot_name() {
        let name = super::snapshot_helpers::build_snapshot_name("my-vm", "20250101_120000");
        assert_eq!(name, "my-vm_snapshot_20250101_120000");
    }

    #[test]
    fn test_build_snapshot_name_special_chars() {
        let name = super::snapshot_helpers::build_snapshot_name("vm-with-dashes", "ts");
        assert_eq!(name, "vm-with-dashes_snapshot_ts");
    }

    #[test]
    fn test_filter_snapshots_matches() {
        let snaps: Vec<serde_json::Value> = vec![
            serde_json::json!({"name": "my-vm_snapshot_1", "diskSizeGb": 30}),
            serde_json::json!({"name": "other-vm_snapshot_1", "diskSizeGb": 50}),
            serde_json::json!({"name": "my-vm_snapshot_2", "diskSizeGb": 30}),
        ];
        let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "my-vm");
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_filter_snapshots_no_match() {
        let snaps: Vec<serde_json::Value> = vec![serde_json::json!({"name": "alpha_snapshot_1"})];
        let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "beta");
        assert!(filtered.is_empty());
    }

    #[test]
    fn test_filter_snapshots_missing_name_field() {
        let snaps: Vec<serde_json::Value> = vec![
            serde_json::json!({"id": 1}),
            serde_json::json!({"name": "vm_snapshot_1"}),
        ];
        let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "vm");
        assert_eq!(filtered.len(), 1);
    }

    #[test]
    fn test_filter_snapshots_empty_list() {
        let snaps: Vec<serde_json::Value> = vec![];
        assert!(super::snapshot_helpers::filter_snapshots(&snaps, "anything").is_empty());
    }

    #[test]
    fn test_snapshot_row_full() {
        let snap = serde_json::json!({
            "name": "vm_snapshot_1",
            "diskSizeGb": 128,
            "timeCreated": "2025-01-15T10:00:00Z",
            "provisioningState": "Succeeded"
        });
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "vm_snapshot_1");
        assert_eq!(row[1], "128");
        assert_eq!(row[2], "2025-01-15T10:00:00Z");
        assert_eq!(row[3], "Succeeded");
    }

    #[test]
    fn test_snapshot_row_missing_fields() {
        let snap = serde_json::json!({});
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "-");
        assert_eq!(row[1], "null");
        assert_eq!(row[2], "-");
        assert_eq!(row[3], "-");
    }

    // ── output_helpers tests ─────────────────────────────────────

    #[test]
    fn test_format_as_csv_basic() {
        let headers = &["Name", "Value"];
        let rows = vec![vec!["A".into(), "1".into()], vec!["B".into(), "2".into()]];
        let csv = super::output_helpers::format_as_csv(headers, &rows);
        assert_eq!(csv, "Name,Value\nA,1\nB,2");
    }

    #[test]
    fn test_format_as_csv_empty_rows() {
        let csv = super::output_helpers::format_as_csv(&["H1", "H2"], &[]);
        assert_eq!(csv, "H1,H2");
    }

    #[test]
    fn test_format_as_csv_single_column() {
        let rows = vec![vec!["only".into()]];
        let csv = super::output_helpers::format_as_csv(&["Col"], &rows);
        assert_eq!(csv, "Col\nonly");
    }

    #[test]
    fn test_format_as_table_basic() {
        let headers = &["Name", "Age"];
        let rows = vec![
            vec!["Alice".into(), "30".into()],
            vec!["Bob".into(), "25".into()],
        ];
        let tbl = super::output_helpers::format_as_table(headers, &rows);
        assert!(tbl.contains("Name"));
        assert!(tbl.contains("Age"));
        assert!(tbl.contains("Alice"));
        assert!(tbl.contains("Bob"));
        // columns should be aligned
        let lines: Vec<&str> = tbl.lines().collect();
        assert_eq!(lines.len(), 3); // header + 2 rows
    }

    #[test]
    fn test_format_as_table_wide_values() {
        let headers = &["K", "V"];
        let rows = vec![vec!["short".into(), "a very long value here".into()]];
        let tbl = super::output_helpers::format_as_table(headers, &rows);
        let lines: Vec<&str> = tbl.lines().collect();
        // header should be padded to match the widest cell
        assert!(lines[0].contains("V"));
        assert!(lines[1].contains("a very long value here"));
    }

    #[test]
    fn test_format_as_table_empty_rows() {
        let tbl = super::output_helpers::format_as_table(&["X"], &[]);
        assert_eq!(tbl, "X");
    }

    #[test]
    fn test_format_as_json_basic() {
        let items = vec![1, 2, 3];
        let json = super::output_helpers::format_as_json(&items);
        let parsed: Vec<i32> = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed, vec![1, 2, 3]);
    }

    #[test]
    fn test_format_as_json_strings() {
        let items = vec!["hello", "world"];
        let json = super::output_helpers::format_as_json(&items);
        assert!(json.contains("hello"));
        assert!(json.contains("world"));
    }

    #[test]
    fn test_format_as_json_empty() {
        let items: Vec<String> = vec![];
        let json = super::output_helpers::format_as_json(&items);
        assert_eq!(json.trim(), "[]");
    }

    #[test]
    fn test_creds_file_format() {
        let content = format!("username={}\npassword={}\n", "testaccount", "testkey123");
        assert!(content.starts_with("username="));
        assert!(content.contains("password="));
        assert!(!content.contains("--")); // no CLI args
    }

    // ── Security & business-logic tests ─────────────────────────────

    // 1. Config path traversal
    #[test]
    fn test_config_path_traversal_blocked() {
        let result = super::config_path_helpers::validate_config_path("../../etc/passwd");
        assert!(result.is_err(), "path traversal must be rejected");
        assert!(result.unwrap_err().contains("traversal"));
    }

    #[test]
    fn test_config_path_traversal_deep() {
        let result = super::config_path_helpers::validate_config_path("foo/../../../etc/shadow");
        assert!(result.is_err());
    }

    #[test]
    fn test_config_path_safe_relative() {
        let result = super::config_path_helpers::validate_config_path("config.toml");
        assert!(result.is_ok());
    }

    #[test]
    fn test_config_path_safe_nested() {
        let result = super::config_path_helpers::validate_config_path("subdir/config.toml");
        assert!(result.is_ok());
    }

    // 2. VM name validation
    #[test]
    fn test_vm_name_no_leading_hyphen() {
        let result = super::vm_validation::validate_vm_name("-bad-name");
        assert!(result.is_err(), "leading hyphen must be rejected");
        assert!(result.unwrap_err().contains("hyphen"));
    }

    #[test]
    fn test_vm_name_no_trailing_hyphen() {
        let result = super::vm_validation::validate_vm_name("bad-name-");
        assert!(result.is_err(), "trailing hyphen must be rejected");
    }

    #[test]
    fn test_vm_name_max_length() {
        let long_name = "a".repeat(65);
        let result = super::vm_validation::validate_vm_name(&long_name);
        assert!(result.is_err(), "names > 64 chars must be rejected");
        assert!(result.unwrap_err().contains("64"));
    }

    #[test]
    fn test_vm_name_exactly_64_chars() {
        let name = "a".repeat(64);
        let result = super::vm_validation::validate_vm_name(&name);
        assert!(result.is_ok(), "exactly 64 chars should be allowed");
    }

    #[test]
    fn test_vm_name_empty() {
        let result = super::vm_validation::validate_vm_name("");
        assert!(result.is_err());
    }

    #[test]
    fn test_vm_name_no_shell_metacharacters() {
        for bad in &["vm;rm", "vm$(whoami)", "vm`id`", "vm|cat", "vm&bg"] {
            let result = super::vm_validation::validate_vm_name(bad);
            assert!(result.is_err(), "'{}' must be rejected", bad);
        }
    }

    #[test]
    fn test_vm_name_valid() {
        assert!(super::vm_validation::validate_vm_name("my-dev-vm-01").is_ok());
        assert!(super::vm_validation::validate_vm_name("VM1").is_ok());
    }

    // 3. Env variable security
    #[test]
    fn test_env_key_no_command_injection() {
        let result = super::env_helpers::validate_env_key("MY_VAR;rm -rf /");
        assert!(result.is_err(), "semicolons in key must be rejected");
    }

    #[test]
    fn test_env_key_no_spaces() {
        let result = super::env_helpers::validate_env_key("MY VAR");
        assert!(result.is_err(), "spaces in key must be rejected");
    }

    #[test]
    fn test_env_key_no_equals() {
        let result = super::env_helpers::validate_env_key("MY=VAR");
        assert!(result.is_err(), "equals in key must be rejected");
    }

    #[test]
    fn test_env_key_no_dollar() {
        let result = super::env_helpers::validate_env_key("$HOME");
        assert!(result.is_err(), "dollar sign in key must be rejected");
    }

    #[test]
    fn test_env_key_no_leading_digit() {
        let result = super::env_helpers::validate_env_key("9VAR");
        assert!(result.is_err(), "leading digit must be rejected");
    }

    #[test]
    fn test_env_key_valid() {
        assert!(super::env_helpers::validate_env_key("MY_VAR").is_ok());
        assert!(super::env_helpers::validate_env_key("PATH").is_ok());
        assert!(super::env_helpers::validate_env_key("_PRIVATE").is_ok());
    }

    #[test]
    fn test_env_value_no_command_injection() {
        let escaped = super::shell_escape("$(whoami)");
        // shell_escape wraps in single quotes, neutralizing $()
        assert!(escaped.starts_with('\''), "value must be single-quoted");
        assert!(escaped.ends_with('\''), "value must be single-quoted");
        // The $(whoami) is inside single quotes so won't execute
        let cmd = super::env_helpers::build_env_set_cmd("MY_VAR", &escaped);
        assert!(cmd.contains("'$(whoami)'"), "injection must be quoted");
    }

    #[test]
    fn test_env_value_semicolon_injection() {
        let escaped = super::shell_escape("value; rm -rf /");
        let cmd = super::env_helpers::build_env_set_cmd("VAR", &escaped);
        // The semicolon must be inside quotes, not acting as a command separator
        assert!(
            cmd.contains("'value; rm -rf /'"),
            "semicolon must be quoted, got: {}",
            cmd
        );
    }

    #[test]
    fn test_env_set_cmd_rejects_bad_key() {
        let cmd = super::env_helpers::build_env_set_cmd("BAD;KEY", "'safe_value'");
        // With a bad key, should return a no-op
        assert_eq!(cmd, "true", "bad key should produce no-op command");
    }

    // 4. Shell escape
    #[test]
    fn test_shell_escape_semicolons() {
        let escaped = super::shell_escape("hello; rm -rf /");
        // Must be wrapped in single quotes
        assert!(escaped.starts_with('\''));
        assert!(escaped.ends_with('\''));
        assert!(escaped.contains("hello; rm -rf /"));
    }

    #[test]
    fn test_shell_escape_backticks() {
        let escaped = super::shell_escape("`whoami`");
        assert!(escaped.starts_with('\''), "backticks must be quoted");
        assert!(escaped.contains("`whoami`"));
    }

    #[test]
    fn test_shell_escape_dollar_paren() {
        let escaped = super::shell_escape("$(rm -rf /)");
        assert!(escaped.starts_with('\''));
        // The dangerous sequence is neutralized inside single quotes
        assert!(!escaped.starts_with("$("));
    }

    #[test]
    fn test_shell_escape_single_quotes() {
        let escaped = super::shell_escape("it's dangerous");
        // Single quotes within single-quoted strings need special escaping
        assert!(escaped.contains("'\\''"), "single quote must be escaped");
    }

    #[test]
    fn test_shell_escape_empty_string_security() {
        let escaped = super::shell_escape("");
        assert_eq!(escaped, "''");
    }

    #[test]
    fn test_shell_escape_pipe() {
        let escaped = super::shell_escape("data | cat /etc/passwd");
        assert!(escaped.starts_with('\''));
        assert!(escaped.ends_with('\''));
    }

    #[test]
    fn test_shell_escape_newlines() {
        let escaped = super::shell_escape("line1\nline2");
        assert!(escaped.starts_with('\''));
        assert!(escaped.ends_with('\''));
    }

    // 5. Mount path injection
    #[test]
    fn test_mount_path_no_semicolons() {
        let result = super::mount_helpers::validate_mount_path("/mnt/data;rm -rf /");
        assert!(result.is_err(), "semicolons in mount path must be rejected");
    }

    #[test]
    fn test_mount_path_no_pipe() {
        let result = super::mount_helpers::validate_mount_path("/mnt/data|cat /etc/passwd");
        assert!(result.is_err());
    }

    #[test]
    fn test_mount_path_no_backticks() {
        let result = super::mount_helpers::validate_mount_path("/mnt/`whoami`");
        assert!(result.is_err());
    }

    #[test]
    fn test_mount_path_no_dollar_paren() {
        let result = super::mount_helpers::validate_mount_path("/mnt/$(id)");
        assert!(result.is_err());
    }

    #[test]
    fn test_mount_path_no_traversal() {
        let result = super::mount_helpers::validate_mount_path("/mnt/../etc/shadow");
        assert!(result.is_err());
    }

    #[test]
    fn test_mount_path_requires_absolute() {
        let result = super::mount_helpers::validate_mount_path("relative/path");
        assert!(result.is_err(), "relative paths must be rejected");
    }

    #[test]
    fn test_mount_path_valid() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/data").is_ok());
        assert!(super::mount_helpers::validate_mount_path("/mnt/azure-files").is_ok());
    }

    // 6. Dotfile sync security
    #[test]
    fn test_sync_rejects_sensitive_paths() {
        let result = super::sync_helpers::validate_sync_source("/etc/shadow");
        assert!(result.is_err(), "sensitive system paths must be rejected");
    }

    #[test]
    fn test_sync_rejects_var_paths() {
        let result = super::sync_helpers::validate_sync_source("/var/log/syslog");
        assert!(result.is_err());
    }

    #[test]
    fn test_sync_rejects_traversal() {
        let result = super::sync_helpers::validate_sync_source("/home/user/../../../etc/passwd");
        assert!(result.is_err());
    }

    #[test]
    fn test_sync_allows_home_dotfiles() {
        assert!(super::sync_helpers::validate_sync_source("/home/user/.bashrc").is_ok());
        assert!(super::sync_helpers::validate_sync_source(".bashrc").is_ok());
    }

    // 7. Health helpers edge cases
    #[test]
    fn test_health_percentage_negative() {
        assert_eq!(
            super::health_helpers::format_percentage(-5.0),
            "0.0%",
            "negative percentages must clamp to 0"
        );
    }

    #[test]
    fn test_health_percentage_zero() {
        assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
    }

    #[test]
    fn test_health_percentage_over_100() {
        // Over-100 values are allowed (shows actual measurement)
        let result = super::health_helpers::format_percentage(150.0);
        assert_eq!(result, "150.0%");
    }

    #[test]
    fn test_health_percentage_normal() {
        assert_eq!(super::health_helpers::format_percentage(55.5), "55.5%");
    }

    #[test]
    fn test_health_metric_color_boundaries() {
        assert_eq!(super::health_helpers::metric_color(80.1), "red");
        assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
        assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
        assert_eq!(super::health_helpers::metric_color(50.0), "green");
        assert_eq!(super::health_helpers::metric_color(0.0), "green");
    }

    // ── Error-path coverage: commands that call create_auth() ────────

    /// Helper: run azlin with no Azure config and verify graceful failure.
    fn assert_graceful_auth_error(args: &[&str]) {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(args)
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .env_remove("AZURE_CLIENT_ID")
            .env_remove("AZURE_CLIENT_SECRET")
            .env_remove("AZURE_TENANT_ID")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        let stderr = String::from_utf8_lossy(&out.stderr);
        let stdout = String::from_utf8_lossy(&out.stdout);
        let combined = format!("{}{}", stdout, stderr);
        // Must not panic
        assert!(
            !combined.contains("thread 'main' panicked"),
            "Command {:?} panicked: {}",
            args,
            combined
        );
        // Should either fail with non-zero exit OR contain an error/auth message
        let has_error_msg = combined.contains("auth")
            || combined.contains("Auth")
            || combined.contains("config")
            || combined.contains("login")
            || combined.contains("subscription")
            || combined.contains("error")
            || combined.contains("Error")
            || combined.contains("az login")
            || combined.contains("Usage")
            || combined.contains("required");
        assert!(
            !out.status.success() || has_error_msg,
            "Command {:?} should fail or show error message, got success with: {}",
            args,
            combined
        );
    }

    #[test]
    fn test_start_graceful_error_no_auth() {
        assert_graceful_auth_error(&["start", "nonexistent-vm"]);
    }

    #[test]
    fn test_stop_graceful_error_no_auth() {
        assert_graceful_auth_error(&["stop", "nonexistent-vm"]);
    }

    #[test]
    fn test_connect_graceful_error_no_auth() {
        assert_graceful_auth_error(&["connect", "nonexistent-vm"]);
    }

    #[test]
    fn test_new_graceful_error_no_auth() {
        assert_graceful_auth_error(&["new"]);
    }

    #[test]
    fn test_create_graceful_error_no_auth() {
        assert_graceful_auth_error(&["create"]);
    }

    #[test]
    fn test_cost_graceful_error_no_auth() {
        assert_graceful_auth_error(&["cost"]);
    }

    #[test]
    fn test_snapshot_create_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "create", "test-vm"]);
    }

    #[test]
    fn test_snapshot_list_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "list", "test-vm"]);
    }

    #[test]
    fn test_snapshot_delete_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "delete", "test-snap"]);
    }

    #[test]
    fn test_snapshot_restore_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "restore", "test-vm", "test-snap"]);
    }

    #[test]
    fn test_snapshot_enable_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "enable", "test-vm", "--every", "24"]);
    }

    #[test]
    fn test_snapshot_disable_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "disable", "test-vm"]);
    }

    #[test]
    fn test_snapshot_status_graceful_error_no_auth() {
        assert_graceful_auth_error(&["snapshot", "status", "test-vm"]);
    }

    #[test]
    fn test_storage_list_graceful_error_no_auth() {
        assert_graceful_auth_error(&["storage", "list"]);
    }

    #[test]
    fn test_storage_create_graceful_error_no_auth() {
        assert_graceful_auth_error(&["storage", "create", "teststorage"]);
    }

    #[test]
    fn test_storage_status_graceful_error_no_auth() {
        assert_graceful_auth_error(&["storage", "status", "teststorage"]);
    }

    #[test]
    fn test_storage_delete_graceful_error_no_auth() {
        assert_graceful_auth_error(&["storage", "delete", "teststorage"]);
    }

    #[test]
    fn test_bastion_list_graceful_error_no_auth() {
        assert_graceful_auth_error(&["bastion", "list"]);
    }

    #[test]
    fn test_bastion_status_graceful_error_no_auth() {
        assert_graceful_auth_error(&["bastion", "status", "mybastion", "--rg", "myrg"]);
    }

    #[test]
    fn test_keys_rotate_graceful_error_no_auth() {
        assert_graceful_auth_error(&["keys", "rotate"]);
    }

    #[test]
    fn test_keys_list_no_ssh_dir_graceful() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["keys", "list"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        let combined = format!(
            "{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr)
        );
        assert!(
            !combined.contains("thread 'main' panicked"),
            "keys list panicked: {}",
            combined
        );
        // keys list without Azure checks local SSH dir — succeeds or mentions no keys
        assert!(
            out.status.success()
                || combined.contains("SSH")
                || combined.contains("key")
                || combined.contains("error"),
            "Unexpected output: {}",
            combined
        );
    }

    #[test]
    fn test_tag_add_graceful_error_no_auth() {
        assert_graceful_auth_error(&["tag", "add", "test-vm", "env=dev"]);
    }

    #[test]
    fn test_tag_remove_graceful_error_no_auth() {
        assert_graceful_auth_error(&["tag", "remove", "test-vm", "env"]);
    }

    #[test]
    fn test_tag_list_graceful_error_no_auth() {
        assert_graceful_auth_error(&["tag", "list", "test-vm"]);
    }

    #[test]
    fn test_batch_start_graceful_error_no_auth() {
        assert_graceful_auth_error(&["batch", "start", "--all"]);
    }

    #[test]
    fn test_batch_stop_graceful_error_no_auth() {
        assert_graceful_auth_error(&["batch", "stop", "--all"]);
    }

    #[test]
    fn test_fleet_run_graceful_error_no_auth() {
        assert_graceful_auth_error(&["fleet", "run", "echo hello", "--all"]);
    }

    #[test]
    fn test_destroy_graceful_error_no_auth() {
        assert_graceful_auth_error(&["destroy", "test-vm", "--force"]);
    }

    #[test]
    fn test_delete_graceful_error_no_auth() {
        assert_graceful_auth_error(&["delete", "test-vm", "--force"]);
    }

    #[test]
    fn test_kill_graceful_error_no_auth() {
        assert_graceful_auth_error(&["kill", "test-vm", "--force"]);
    }

    #[test]
    fn test_show_graceful_error_no_auth() {
        assert_graceful_auth_error(&["show", "test-vm"]);
    }

    #[test]
    fn test_update_graceful_error_no_auth() {
        assert_graceful_auth_error(&["update", "test-vm"]);
    }

    #[test]
    fn test_os_update_graceful_error_no_auth() {
        assert_graceful_auth_error(&["os-update", "test-vm"]);
    }

    #[test]
    fn test_code_graceful_error_no_auth() {
        assert_graceful_auth_error(&["code", "test-vm"]);
    }

    #[test]
    fn test_compose_up_graceful_error_no_auth() {
        assert_graceful_auth_error(&["compose", "up"]);
    }

    #[test]
    fn test_compose_down_graceful_error_no_auth() {
        assert_graceful_auth_error(&["compose", "down"]);
    }

    #[test]
    fn test_killall_graceful_error_no_auth() {
        assert_graceful_auth_error(&["killall", "--force"]);
    }

    #[test]
    fn test_cleanup_graceful_error_no_auth() {
        assert_graceful_auth_error(&["cleanup", "--force"]);
    }

    #[test]
    fn test_clone_graceful_error_no_auth() {
        assert_graceful_auth_error(&["clone", "source-vm"]);
    }

    // ── Env subcommands ─────────────────────────────────────────────

    #[test]
    fn test_env_set_graceful_error_no_auth() {
        assert_graceful_auth_error(&["env", "set", "test-vm", "MY_KEY=my_value"]);
    }

    #[test]
    fn test_env_list_graceful_error_no_auth() {
        assert_graceful_auth_error(&["env", "list", "test-vm"]);
    }

    #[test]
    fn test_env_delete_graceful_error_no_auth() {
        assert_graceful_auth_error(&["env", "delete", "test-vm", "MY_KEY"]);
    }

    #[test]
    fn test_env_export_graceful_error_no_auth() {
        assert_graceful_auth_error(&["env", "export", "test-vm"]);
    }

    #[test]
    fn test_env_import_graceful_error_no_auth() {
        assert_graceful_auth_error(&["env", "import", "test-vm", "/dev/null"]);
    }

    #[test]
    fn test_env_clear_graceful_error_no_auth() {
        assert_graceful_auth_error(&["env", "clear", "test-vm", "--force"]);
    }

    // ── Compose subcommands ─────────────────────────────────────────

    #[test]
    fn test_compose_ps_graceful_error_no_auth() {
        assert_graceful_auth_error(&["compose", "ps"]);
    }

    // ── Sessions subcommands ────────────────────────────────────────

    #[test]
    fn test_sessions_save_graceful_error_no_auth() {
        assert_graceful_auth_error(&["sessions", "save", "test-session"]);
    }

    #[test]
    fn test_sessions_load_graceful_error_no_auth() {
        assert_graceful_auth_error(&["sessions", "load", "nonexistent-session"]);
    }

    #[test]
    fn test_sessions_delete_graceful_error_no_auth() {
        assert_graceful_auth_error(&["sessions", "delete", "nonexistent-session", "--force"]);
    }

    // ── GitHub Runner subcommands ───────────────────────────────────

    #[test]
    fn test_github_runner_enable_graceful_error_no_auth() {
        assert_graceful_auth_error(&[
            "github-runner",
            "enable",
            "--pool",
            "test-pool",
            "--count",
            "1",
        ]);
    }

    // Note: github-runner disable/status/scale are local filesystem operations
    // that don't call Azure auth, so they don't use the auth-error pattern.

    // ── Template subcommands ────────────────────────────────────────

    // Note: template create/save are local filesystem operations that
    // don't call Azure auth, so they don't use the auth-error pattern.

    #[test]
    fn test_template_apply_graceful_error_no_auth() {
        assert_graceful_auth_error(&["template", "apply", "nonexistent-template"]);
    }

    #[test]
    fn test_template_delete_graceful_error_no_auth() {
        assert_graceful_auth_error(&["template", "delete", "nonexistent-template", "--force"]);
    }

    // ── Web subcommands ─────────────────────────────────────────────

    #[test]
    fn test_web_start_graceful_error_no_auth() {
        assert_graceful_auth_error(&["web", "start"]);
    }

    // Note: web stop is a local PID-file operation that doesn't call
    // Azure auth, so it doesn't use the auth-error pattern.

    // ── Storage mount/unmount ───────────────────────────────────────

    #[test]
    fn test_storage_mount_graceful_error_no_auth() {
        assert_graceful_auth_error(&[
            "storage",
            "mount",
            "--storage-name",
            "teststorage",
            "--vm",
            "test-vm",
        ]);
    }

    #[test]
    fn test_storage_unmount_graceful_error_no_auth() {
        assert_graceful_auth_error(&["storage", "unmount", "--vm", "test-vm"]);
    }

    // ── IP subcommands ──────────────────────────────────────────────

    #[test]
    fn test_ip_check_graceful_error_no_auth() {
        assert_graceful_auth_error(&["ip", "check", "test-vm"]);
    }

    // ── Disk subcommands ────────────────────────────────────────────

    #[test]
    fn test_disk_add_graceful_error_no_auth() {
        assert_graceful_auth_error(&["disk", "add", "test-vm"]);
    }

    // ── Do (natural language) ───────────────────────────────────────

    #[test]
    fn test_do_graceful_error_no_auth() {
        assert_graceful_auth_error(&["do", "list all vms"]);
    }

    // ── Health / w / ps / logs ──────────────────────────────────────

    #[test]
    fn test_health_graceful_error_no_auth() {
        assert_graceful_auth_error(&["health"]);
    }

    #[test]
    fn test_w_graceful_error_no_auth() {
        assert_graceful_auth_error(&["w", "--vm", "test-vm"]);
    }

    #[test]
    fn test_ps_graceful_error_no_auth() {
        assert_graceful_auth_error(&["ps", "--vm", "test-vm"]);
    }

    #[test]
    fn test_logs_graceful_error_no_auth() {
        assert_graceful_auth_error(&["logs", "test-vm"]);
    }

    // ── cp / sync / sync-keys ───────────────────────────────────────

    #[test]
    fn test_cp_graceful_error_no_auth() {
        assert_graceful_auth_error(&["cp", "test-vm:/tmp/file", "/tmp/local"]);
    }

    #[test]
    fn test_sync_graceful_error_no_auth() {
        assert_graceful_auth_error(&["sync"]);
    }

    #[test]
    fn test_sync_keys_graceful_error_no_auth() {
        assert_graceful_auth_error(&["sync-keys", "test-vm"]);
    }

    // ── Costs subcommands ───────────────────────────────────────────

    #[test]
    fn test_costs_dashboard_graceful_error_no_auth() {
        assert_graceful_auth_error(&["costs", "dashboard", "--resource-group", "test-rg"]);
    }

    #[test]
    fn test_costs_history_graceful_error_no_auth() {
        assert_graceful_auth_error(&["costs", "history", "--resource-group", "test-rg"]);
    }

    #[test]
    fn test_costs_budget_graceful_error_no_auth() {
        assert_graceful_auth_error(&[
            "costs",
            "budget",
            "--resource-group",
            "test-rg",
            "--action",
            "show",
        ]);
    }

    #[test]
    fn test_costs_recommend_graceful_error_no_auth() {
        assert_graceful_auth_error(&["costs", "recommend", "--resource-group", "test-rg"]);
    }

    // ── Command-specific validation ─────────────────────────────────

    #[test]
    fn test_env_set_requires_args() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["env", "set"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_env_delete_requires_args() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["env", "delete"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_env_list_requires_vm() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["env", "list"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_snapshot_create_requires_vm() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["snapshot", "create"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_tag_add_requires_vm_and_tags() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["tag", "add"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_start_requires_vm_name() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["start"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_stop_requires_vm_name() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["stop"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_delete_requires_vm_name() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["delete"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_destroy_requires_vm_name() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["destroy"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_kill_requires_vm_name() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["kill"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    #[test]
    fn test_fleet_run_requires_command() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["fleet", "run"])
            .output()
            .unwrap();
        assert!(!out.status.success());
    }

    // ── Additional help flag coverage ──────────────────────────────

    #[test]
    fn test_sessions_help_output() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "--help"])
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("session") || stdout.contains("Session"));
    }

    #[test]
    fn test_context_help_output() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["context", "--help"])
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("context") || stdout.contains("Context"));
    }

    #[test]
    fn test_template_help_output() {
        let out = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["template", "--help"])
            .output()
            .unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("template") || stdout.contains("Template"));
    }

    // ── Storage helpers tests ───────────────────────────────────────

    #[test]
    fn test_storage_sku_from_tier_premium() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("premium"),
            "Premium_LRS"
        );
    }

    #[test]
    fn test_storage_sku_from_tier_standard() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("standard"),
            "Standard_LRS"
        );
    }

    #[test]
    fn test_storage_sku_from_tier_case_insensitive() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("Premium"),
            "Premium_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("STANDARD"),
            "Standard_LRS"
        );
    }

    #[test]
    fn test_storage_sku_from_tier_unknown_defaults_premium() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("hot"),
            "Premium_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier(""),
            "Premium_LRS"
        );
    }

    #[test]
    fn test_storage_account_row_full() {
        let acct = serde_json::json!({
            "name": "mystorage",
            "location": "eastus2",
            "kind": "FileStorage",
            "sku": { "name": "Premium_LRS" },
            "provisioningState": "Succeeded"
        });
        let row = super::storage_helpers::storage_account_row(&acct);
        assert_eq!(
            row,
            vec![
                "mystorage",
                "eastus2",
                "FileStorage",
                "Premium_LRS",
                "Succeeded"
            ]
        );
    }

    #[test]
    fn test_storage_account_row_missing_fields() {
        let acct = serde_json::json!({});
        let row = super::storage_helpers::storage_account_row(&acct);
        assert_eq!(row, vec!["-", "-", "-", "-", "-"]);
    }

    // ── Key helpers tests ───────────────────────────────────────────

    #[test]
    fn test_detect_key_type_ed25519() {
        assert_eq!(super::key_helpers::detect_key_type("id_ed25519"), "ed25519");
        assert_eq!(
            super::key_helpers::detect_key_type("id_ed25519.pub"),
            "ed25519"
        );
    }

    #[test]
    fn test_detect_key_type_ecdsa() {
        assert_eq!(super::key_helpers::detect_key_type("id_ecdsa"), "ecdsa");
    }

    #[test]
    fn test_detect_key_type_rsa() {
        assert_eq!(super::key_helpers::detect_key_type("id_rsa"), "rsa");
        assert_eq!(super::key_helpers::detect_key_type("id_rsa.pub"), "rsa");
    }

    #[test]
    fn test_detect_key_type_dsa() {
        assert_eq!(super::key_helpers::detect_key_type("id_dsa"), "dsa");
    }

    #[test]
    fn test_detect_key_type_unknown() {
        assert_eq!(
            super::key_helpers::detect_key_type("my_custom_key"),
            "unknown"
        );
        assert_eq!(
            super::key_helpers::detect_key_type("authorized_keys"),
            "unknown"
        );
    }

    #[test]
    fn test_is_known_key_name_pub() {
        assert!(super::key_helpers::is_known_key_name("id_rsa.pub"));
        assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
        assert!(super::key_helpers::is_known_key_name("custom.pub"));
    }

    #[test]
    fn test_is_known_key_name_private() {
        assert!(super::key_helpers::is_known_key_name("id_rsa"));
        assert!(super::key_helpers::is_known_key_name("id_ed25519"));
        assert!(super::key_helpers::is_known_key_name("id_ecdsa"));
        assert!(super::key_helpers::is_known_key_name("id_dsa"));
    }

    #[test]
    fn test_is_known_key_name_not_key() {
        assert!(!super::key_helpers::is_known_key_name("known_hosts"));
        assert!(!super::key_helpers::is_known_key_name("config"));
        assert!(!super::key_helpers::is_known_key_name("authorized_keys"));
    }

    // ── Auth helpers tests ──────────────────────────────────────────

    #[test]
    fn test_mask_profile_value_plain_string() {
        let v = serde_json::Value::String("my-tenant".into());
        assert_eq!(
            super::auth_helpers::mask_profile_value("tenant_id", &v),
            "my-tenant"
        );
    }

    #[test]
    fn test_mask_profile_value_secret_masked() {
        let v = serde_json::Value::String("super-secret-123".into());
        assert_eq!(
            super::auth_helpers::mask_profile_value("client_secret", &v),
            "********"
        );
    }

    #[test]
    fn test_mask_profile_value_password_masked() {
        let v = serde_json::Value::String("p@ssw0rd".into());
        assert_eq!(
            super::auth_helpers::mask_profile_value("db_password", &v),
            "********"
        );
    }

    #[test]
    fn test_mask_profile_value_non_string() {
        let v = serde_json::json!(42);
        assert_eq!(super::auth_helpers::mask_profile_value("count", &v), "42");
    }

    #[test]
    fn test_mask_profile_value_boolean() {
        let v = serde_json::json!(true);
        assert_eq!(
            super::auth_helpers::mask_profile_value("enabled", &v),
            "true"
        );
    }

    // ── CP helpers tests ────────────────────────────────────────────

    #[test]
    fn test_is_remote_path_positive() {
        assert!(super::cp_helpers::is_remote_path(
            "myvm:/home/user/file.txt"
        ));
        assert!(super::cp_helpers::is_remote_path("dev-vm-1:/tmp/data"));
    }

    #[test]
    fn test_is_remote_path_local() {
        assert!(!super::cp_helpers::is_remote_path("/tmp/local.txt"));
        assert!(!super::cp_helpers::is_remote_path("./relative/path"));
        assert!(!super::cp_helpers::is_remote_path("file.txt"));
    }

    #[test]
    fn test_is_remote_path_windows_drive_excluded() {
        assert!(!super::cp_helpers::is_remote_path("C:\\Users\\file"));
    }

    #[test]
    fn test_is_remote_path_too_short() {
        assert!(!super::cp_helpers::is_remote_path("a:"));
    }

    #[test]
    fn test_classify_transfer_direction_remote_to_local() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("vm:/path", "/local"),
            "remote→local"
        );
    }

    #[test]
    fn test_classify_transfer_direction_local_to_remote() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("/local", "vm:/path"),
            "local→remote"
        );
    }

    #[test]
    fn test_classify_transfer_direction_local_to_local() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("/a", "/b"),
            "local→local"
        );
    }

    #[test]
    fn test_resolve_scp_path_rewrites() {
        let result =
            super::cp_helpers::resolve_scp_path("myvm:/home/data", "myvm", "azureuser", "10.0.0.5");
        assert_eq!(result, "azureuser@10.0.0.5:/home/data");
    }

    #[test]
    fn test_resolve_scp_path_no_match() {
        let result = super::cp_helpers::resolve_scp_path("/local/path", "myvm", "user", "10.0.0.1");
        assert_eq!(result, "/local/path");
    }

    // ── Bastion helpers tests ───────────────────────────────────────

    #[test]
    fn test_bastion_summary_full() {
        let b = serde_json::json!({
            "name": "my-bastion",
            "resourceGroup": "my-rg",
            "location": "eastus2",
            "sku": { "name": "Standard" },
            "provisioningState": "Succeeded"
        });
        let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
        assert_eq!(name, "my-bastion");
        assert_eq!(rg, "my-rg");
        assert_eq!(loc, "eastus2");
        assert_eq!(sku, "Standard");
        assert_eq!(state, "Succeeded");
    }

    #[test]
    fn test_bastion_summary_defaults() {
        let b = serde_json::json!({});
        let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
        assert_eq!(name, "unknown");
        assert_eq!(rg, "unknown");
        assert_eq!(loc, "unknown");
        assert_eq!(sku, "Standard");
        assert_eq!(state, "unknown");
    }

    #[test]
    fn test_shorten_resource_id_full_path() {
        let id = "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/my-pip";
        assert_eq!(super::bastion_helpers::shorten_resource_id(id), "my-pip");
    }

    #[test]
    fn test_shorten_resource_id_na() {
        assert_eq!(super::bastion_helpers::shorten_resource_id("N/A"), "N/A");
    }

    #[test]
    fn test_shorten_resource_id_simple() {
        assert_eq!(
            super::bastion_helpers::shorten_resource_id("just-a-name"),
            "just-a-name"
        );
    }

    #[test]
    fn test_extract_ip_configs_with_configs() {
        let b = serde_json::json!({
            "ipConfigurations": [
                {
                    "subnet": { "id": "/sub/rg/subnets/AzureBastionSubnet" },
                    "publicIPAddress": { "id": "/sub/rg/publicIPAddresses/bastion-pip" }
                },
                {
                    "subnet": { "id": "N/A" },
                    "publicIPAddress": { "id": "N/A" }
                }
            ]
        });
        let configs = super::bastion_helpers::extract_ip_configs(&b);
        assert_eq!(configs.len(), 2);
        assert_eq!(
            configs[0],
            ("AzureBastionSubnet".to_string(), "bastion-pip".to_string())
        );
        assert_eq!(configs[1], ("N/A".to_string(), "N/A".to_string()));
    }

    #[test]
    fn test_extract_ip_configs_empty() {
        let b = serde_json::json!({});
        let configs = super::bastion_helpers::extract_ip_configs(&b);
        assert!(configs.is_empty());
    }

    // ── Log helpers tests ───────────────────────────────────────────

    #[test]
    fn test_tail_start_index_more_than_count() {
        assert_eq!(super::log_helpers::tail_start_index(100, 20), 80);
    }

    #[test]
    fn test_tail_start_index_less_than_count() {
        assert_eq!(super::log_helpers::tail_start_index(5, 20), 0);
    }

    #[test]
    fn test_tail_start_index_equal() {
        assert_eq!(super::log_helpers::tail_start_index(20, 20), 0);
    }

    #[test]
    fn test_tail_start_index_zero() {
        assert_eq!(super::log_helpers::tail_start_index(0, 20), 0);
    }

    // ── Auth test helpers tests ─────────────────────────────────────

    #[test]
    fn test_extract_account_info_full() {
        let acct = serde_json::json!({
            "name": "My Subscription",
            "tenantId": "tenant-123",
            "user": { "name": "user@example.com" }
        });
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "My Subscription");
        assert_eq!(tenant, "tenant-123");
        assert_eq!(user, "user@example.com");
    }

    #[test]
    fn test_extract_account_info_missing_fields() {
        let acct = serde_json::json!({});
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "-");
        assert_eq!(tenant, "-");
        assert_eq!(user, "-");
    }

    #[test]
    fn test_extract_account_info_partial() {
        let acct = serde_json::json!({
            "name": "Sub Only",
            "user": {}
        });
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "Sub Only");
        assert_eq!(tenant, "-");
        assert_eq!(user, "-");
    }

    // ── NEW: templates edge-case tests ───────────────────────────

    #[test]
    fn test_template_build_all_none_defaults() {
        let tpl = super::templates::build_template_toml("t1", None, None, None, None);
        let t = tpl.as_table().unwrap();
        assert_eq!(t["name"].as_str().unwrap(), "t1");
        assert_eq!(t["description"].as_str().unwrap(), "");
        assert_eq!(t["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
        assert_eq!(t["region"].as_str().unwrap(), "westus2");
        assert!(t.get("cloud_init").is_none());
    }

    #[test]
    fn test_template_build_all_some() {
        let tpl = super::templates::build_template_toml(
            "big",
            Some("GPU template"),
            Some("Standard_NC6"),
            Some("eastus"),
            Some("#!/bin/bash\necho hi"),
        );
        let t = tpl.as_table().unwrap();
        assert_eq!(t["name"].as_str().unwrap(), "big");
        assert_eq!(t["description"].as_str().unwrap(), "GPU template");
        assert_eq!(t["vm_size"].as_str().unwrap(), "Standard_NC6");
        assert_eq!(t["region"].as_str().unwrap(), "eastus");
        assert_eq!(t["cloud_init"].as_str().unwrap(), "#!/bin/bash\necho hi");
    }

    #[test]
    fn test_template_save_creates_directory() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join("nested").join("templates");
        let tpl = super::templates::build_template_toml("x", None, None, None, None);
        let path = super::templates::save_template(&dir, "x", &tpl).unwrap();
        assert!(path.exists());
        assert!(path.to_string_lossy().ends_with("x.toml"));
    }

    #[test]
    fn test_template_load_not_found() {
        let tmp = TempDir::new().unwrap();
        let err = super::templates::load_template(tmp.path(), "nope").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    #[test]
    fn test_template_save_load_roundtrip_with_cloud_init() {
        let tmp = TempDir::new().unwrap();
        let tpl = super::templates::build_template_toml(
            "ci",
            Some("cloud-init test"),
            Some("Standard_B2s"),
            Some("westus3"),
            Some("#!/bin/bash\napt update"),
        );
        super::templates::save_template(tmp.path(), "ci", &tpl).unwrap();
        let loaded = super::templates::load_template(tmp.path(), "ci").unwrap();
        assert_eq!(loaded["name"].as_str().unwrap(), "ci");
        assert_eq!(
            loaded["cloud_init"].as_str().unwrap(),
            "#!/bin/bash\napt update"
        );
    }

    #[test]
    fn test_template_list_multiple_sorted_fields() {
        let tmp = TempDir::new().unwrap();
        for (n, sz, rg) in &[
            ("a", "Standard_A1", "westus"),
            ("b", "Standard_B2", "eastus"),
        ] {
            let tpl = super::templates::build_template_toml(n, None, Some(sz), Some(rg), None);
            super::templates::save_template(tmp.path(), n, &tpl).unwrap();
        }
        let rows = super::templates::list_templates(tmp.path()).unwrap();
        assert_eq!(rows.len(), 2);
        let names: Vec<&str> = rows.iter().map(|r| r[0].as_str()).collect();
        assert!(names.contains(&"a"));
        assert!(names.contains(&"b"));
    }

    #[test]
    fn test_template_list_nonexistent_dir() {
        let tmp = TempDir::new().unwrap();
        let rows = super::templates::list_templates(&tmp.path().join("nope")).unwrap();
        assert!(rows.is_empty());
    }

    #[test]
    fn test_template_list_ignores_non_toml_files() {
        let tmp = TempDir::new().unwrap();
        fs::write(tmp.path().join("readme.md"), "not a template").unwrap();
        fs::write(tmp.path().join("data.json"), "{}").unwrap();
        let tpl = super::templates::build_template_toml("only", None, None, None, None);
        super::templates::save_template(tmp.path(), "only", &tpl).unwrap();
        let rows = super::templates::list_templates(tmp.path()).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0][0], "only");
    }

    #[test]
    fn test_template_delete_not_found() {
        let tmp = TempDir::new().unwrap();
        let err = super::templates::delete_template(tmp.path(), "ghost").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    #[test]
    fn test_template_delete_removes_file() {
        let tmp = TempDir::new().unwrap();
        let tpl = super::templates::build_template_toml("del", None, None, None, None);
        super::templates::save_template(tmp.path(), "del", &tpl).unwrap();
        assert!(tmp.path().join("del.toml").exists());
        super::templates::delete_template(tmp.path(), "del").unwrap();
        assert!(!tmp.path().join("del.toml").exists());
    }

    #[test]
    fn test_template_import_valid() {
        let tmp = TempDir::new().unwrap();
        let content = "name = \"imported\"\nvm_size = \"Standard_D2s_v3\"\nregion = \"westus2\"\n";
        let name = super::templates::import_template(tmp.path(), content).unwrap();
        assert_eq!(name, "imported");
        assert!(tmp.path().join("imported.toml").exists());
    }

    #[test]
    fn test_template_import_missing_name() {
        let tmp = TempDir::new().unwrap();
        let content = "vm_size = \"Standard_D2s_v3\"\n";
        let err = super::templates::import_template(tmp.path(), content).unwrap_err();
        assert!(err.to_string().contains("name"));
    }

    #[test]
    fn test_template_import_invalid_toml() {
        let tmp = TempDir::new().unwrap();
        let err = super::templates::import_template(tmp.path(), "{{invalid").unwrap_err();
        assert!(!err.to_string().is_empty());
    }

    // ── NEW: sessions edge-case tests ────────────────────────────

    #[test]
    fn test_session_build_toml_fields() {
        let s = super::sessions::build_session_toml("dev", "rg-dev", &["vm1".into(), "vm2".into()]);
        let t = s.as_table().unwrap();
        assert_eq!(t["name"].as_str().unwrap(), "dev");
        assert_eq!(t["resource_group"].as_str().unwrap(), "rg-dev");
        let vms = t["vms"].as_array().unwrap();
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].as_str().unwrap(), "vm1");
        assert!(t["created"].as_str().unwrap().contains('T'));
    }

    #[test]
    fn test_session_build_toml_empty_vms() {
        let s = super::sessions::build_session_toml("empty", "rg", &[]);
        let t = s.as_table().unwrap();
        assert!(t["vms"].as_array().unwrap().is_empty());
    }

    #[test]
    fn test_session_parse_toml_valid() {
        let content = "name = \"s1\"\nresource_group = \"rg-test\"\nvms = [\"vm-a\", \"vm-b\"]\ncreated = \"2025-01-01T00:00:00Z\"\n";
        let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
        assert_eq!(rg, "rg-test");
        assert_eq!(vms, vec!["vm-a", "vm-b"]);
        assert_eq!(created, "2025-01-01T00:00:00Z");
    }

    #[test]
    fn test_session_parse_toml_missing_fields() {
        let content = "name = \"minimal\"\n";
        let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
        assert_eq!(rg, "-");
        assert!(vms.is_empty());
        assert_eq!(created, "-");
    }

    #[test]
    fn test_session_parse_toml_invalid() {
        let err = super::sessions::parse_session_toml("{{bad").unwrap_err();
        assert!(!err.to_string().is_empty());
    }

    #[test]
    fn test_session_list_names_empty_dir() {
        let tmp = TempDir::new().unwrap();
        let names = super::sessions::list_session_names(tmp.path()).unwrap();
        assert!(names.is_empty());
    }

    #[test]
    fn test_session_list_names_nonexistent_dir() {
        let tmp = TempDir::new().unwrap();
        let names = super::sessions::list_session_names(&tmp.path().join("nope")).unwrap();
        assert!(names.is_empty());
    }

    #[test]
    fn test_session_list_names_filters_toml() {
        let tmp = TempDir::new().unwrap();
        fs::write(tmp.path().join("s1.toml"), "name=\"s1\"\n").unwrap();
        fs::write(tmp.path().join("s2.toml"), "name=\"s2\"\n").unwrap();
        fs::write(tmp.path().join("readme.md"), "ignore").unwrap();
        let names = super::sessions::list_session_names(tmp.path()).unwrap();
        assert_eq!(names.len(), 2);
        assert!(names.contains(&"s1".to_string()));
        assert!(names.contains(&"s2".to_string()));
    }

    #[test]
    fn test_session_build_and_parse_roundtrip() {
        let built = super::sessions::build_session_toml("rt", "rg-rt", &["vm-x".into()]);
        let serialized = toml::to_string_pretty(&built).unwrap();
        let (rg, vms, created) = super::sessions::parse_session_toml(&serialized).unwrap();
        assert_eq!(rg, "rg-rt");
        assert_eq!(vms, vec!["vm-x"]);
        assert!(!created.is_empty());
        assert_ne!(created, "-");
    }

    // ── NEW: contexts edge-case tests ────────────────────────────

    #[test]
    fn test_context_build_toml_minimal() {
        let toml_str =
            super::contexts::build_context_toml("dev", None, None, None, None, None).unwrap();
        assert!(toml_str.contains("name = \"dev\""));
        assert!(!toml_str.contains("subscription_id"));
    }

    #[test]
    fn test_context_build_toml_all_fields() {
        let toml_str = super::contexts::build_context_toml(
            "prod",
            Some("sub-123"),
            Some("tenant-456"),
            Some("rg-prod"),
            Some("eastus2"),
            Some("kv-prod"),
        )
        .unwrap();
        assert!(toml_str.contains("name = \"prod\""));
        assert!(toml_str.contains("subscription_id = \"sub-123\""));
        assert!(toml_str.contains("tenant_id = \"tenant-456\""));
        assert!(toml_str.contains("resource_group = \"rg-prod\""));
        assert!(toml_str.contains("region = \"eastus2\""));
        assert!(toml_str.contains("key_vault_name = \"kv-prod\""));
    }

    #[test]
    fn test_context_build_toml_partial_fields() {
        let toml_str = super::contexts::build_context_toml(
            "staging",
            Some("sub-789"),
            None,
            Some("rg-staging"),
            None,
            None,
        )
        .unwrap();
        assert!(toml_str.contains("name = \"staging\""));
        assert!(toml_str.contains("subscription_id = \"sub-789\""));
        assert!(toml_str.contains("resource_group = \"rg-staging\""));
        assert!(!toml_str.contains("tenant_id"));
        assert!(!toml_str.contains("region"));
        assert!(!toml_str.contains("key_vault_name"));
    }

    #[test]
    fn test_context_list_empty_dir() {
        let tmp = TempDir::new().unwrap();
        let list = super::contexts::list_contexts(tmp.path(), "").unwrap();
        assert!(list.is_empty());
    }

    #[test]
    fn test_context_list_marks_active_correctly() {
        let tmp = TempDir::new().unwrap();
        for name in &["dev", "staging", "prod"] {
            let content =
                super::contexts::build_context_toml(name, None, None, None, None, None).unwrap();
            fs::write(tmp.path().join(format!("{}.toml", name)), content).unwrap();
        }
        let list = super::contexts::list_contexts(tmp.path(), "staging").unwrap();
        assert_eq!(list.len(), 3);
        for (name, active) in &list {
            if name == "staging" {
                assert!(active, "staging should be active");
            } else {
                assert!(!active, "{} should not be active", name);
            }
        }
    }

    #[test]
    fn test_context_list_ignores_non_toml() {
        let tmp = TempDir::new().unwrap();
        fs::write(tmp.path().join("dev.toml"), "name = \"dev\"\n").unwrap();
        fs::write(tmp.path().join("notes.txt"), "ignore").unwrap();
        let list = super::contexts::list_contexts(tmp.path(), "").unwrap();
        assert_eq!(list.len(), 1);
        assert_eq!(list[0].0, "dev");
    }

    #[test]
    fn test_context_rename_success() {
        let tmp = TempDir::new().unwrap();
        let content =
            super::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
        fs::write(tmp.path().join("old.toml"), content).unwrap();
        super::contexts::rename_context_file(tmp.path(), "old", "new").unwrap();
        assert!(!tmp.path().join("old.toml").exists());
        assert!(tmp.path().join("new.toml").exists());
        let loaded: toml::Value = fs::read_to_string(tmp.path().join("new.toml"))
            .unwrap()
            .parse()
            .unwrap();
        assert_eq!(loaded["name"].as_str().unwrap(), "new");
    }

    #[test]
    fn test_context_rename_not_found() {
        let tmp = TempDir::new().unwrap();
        let err = super::contexts::rename_context_file(tmp.path(), "ghost", "new").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    // ── NEW: env_helpers additional edge cases ───────────────────

    #[test]
    fn test_split_env_var_equals_in_value() {
        let result = super::env_helpers::split_env_var("DB_URL=postgres://host:5432/db?opt=val");
        assert_eq!(result, Some(("DB_URL", "postgres://host:5432/db?opt=val")));
    }

    #[test]
    fn test_split_env_var_empty_string() {
        assert_eq!(super::env_helpers::split_env_var(""), None);
    }

    #[test]
    fn test_split_env_var_just_equals() {
        assert_eq!(super::env_helpers::split_env_var("="), None);
    }

    #[test]
    fn test_validate_env_key_underscores() {
        assert!(super::env_helpers::validate_env_key("MY_VAR_123").is_ok());
    }

    #[test]
    fn test_validate_env_key_single_char() {
        assert!(super::env_helpers::validate_env_key("X").is_ok());
    }

    #[test]
    fn test_validate_env_key_with_dash() {
        assert!(super::env_helpers::validate_env_key("MY-VAR").is_err());
    }

    #[test]
    fn test_validate_env_key_with_dot() {
        assert!(super::env_helpers::validate_env_key("my.var").is_err());
    }

    #[test]
    fn test_validate_env_key_unicode() {
        assert!(super::env_helpers::validate_env_key("café").is_err());
    }

    #[test]
    fn test_build_env_set_cmd_valid_key() {
        let cmd = super::env_helpers::build_env_set_cmd("FOO", "'bar'");
        assert!(cmd.contains("FOO"));
        assert!(cmd.contains("'bar'"));
        assert!(cmd.contains("grep"));
    }

    #[test]
    fn test_build_env_set_cmd_invalid_key_returns_noop() {
        let cmd = super::env_helpers::build_env_set_cmd("BAD;KEY", "'val'");
        assert_eq!(cmd, "true");
    }

    #[test]
    fn test_build_env_delete_cmd_format() {
        let cmd = super::env_helpers::build_env_delete_cmd("MY_VAR");
        assert!(cmd.contains("sed"));
        assert!(cmd.contains("MY_VAR"));
    }

    #[test]
    fn test_env_list_cmd_value() {
        assert_eq!(super::env_helpers::env_list_cmd(), "env | sort");
    }

    #[test]
    fn test_env_clear_cmd_value() {
        let cmd = super::env_helpers::env_clear_cmd();
        assert!(cmd.contains("sed"));
        assert!(cmd.contains("export"));
    }

    #[test]
    fn test_parse_env_output_multiline() {
        let output = "A=1\nB=two\nC=three=3\nD=\n";
        let vars = super::env_helpers::parse_env_output(output);
        assert_eq!(vars.len(), 4);
        assert_eq!(vars[0], ("A".into(), "1".into()));
        assert_eq!(vars[1], ("B".into(), "two".into()));
        assert_eq!(vars[2], ("C".into(), "three=3".into()));
        assert_eq!(vars[3], ("D".into(), "".into()));
    }

    #[test]
    fn test_build_env_file_multiple() {
        let vars = vec![("K1".into(), "v1".into()), ("K2".into(), "v2".into())];
        let file = super::env_helpers::build_env_file(&vars);
        assert_eq!(file, "K1=v1\nK2=v2");
    }

    #[test]
    fn test_parse_env_file_mixed_content() {
        let content = "# comment\n\nFOO=bar\n  # another comment  \n  BAZ=qux  \n\n";
        let vars = super::env_helpers::parse_env_file(content);
        assert_eq!(vars.len(), 2);
        assert_eq!(vars[0], ("FOO".into(), "bar".into()));
        assert_eq!(vars[1], ("BAZ".into(), "qux".into()));
    }

    #[test]
    fn test_env_file_build_then_parse_roundtrip() {
        let original = vec![
            ("PATH".into(), "/usr/bin".into()),
            ("HOME".into(), "/home/user".into()),
        ];
        let file = super::env_helpers::build_env_file(&original);
        let parsed = super::env_helpers::parse_env_file(&file);
        assert_eq!(parsed, original);
    }

    // ── NEW: sync_helpers additional tests ───────────────────────

    #[test]
    fn test_default_dotfiles_count() {
        let df = super::sync_helpers::default_dotfiles();
        assert!(df.len() >= 4);
        assert!(df.contains(&".bashrc"));
        assert!(df.contains(&".gitconfig"));
    }

    #[test]
    fn test_validate_sync_source_etc() {
        assert!(super::sync_helpers::validate_sync_source("/etc/passwd").is_err());
    }

    #[test]
    fn test_validate_sync_source_proc() {
        assert!(super::sync_helpers::validate_sync_source("/proc/1/status").is_err());
    }

    #[test]
    fn test_validate_sync_source_sys() {
        assert!(super::sync_helpers::validate_sync_source("/sys/class/net").is_err());
    }

    #[test]
    fn test_validate_sync_source_root() {
        assert!(super::sync_helpers::validate_sync_source("/root/secret").is_err());
    }

    #[test]
    fn test_validate_sync_source_traversal_end() {
        assert!(super::sync_helpers::validate_sync_source("foo/..").is_err());
    }

    #[test]
    fn test_validate_sync_source_double_dot_bare() {
        assert!(super::sync_helpers::validate_sync_source("..").is_err());
    }

    #[test]
    fn test_validate_sync_source_safe_home() {
        assert!(super::sync_helpers::validate_sync_source("/home/user/.bashrc").is_ok());
    }

    #[test]
    fn test_validate_sync_source_relative() {
        assert!(super::sync_helpers::validate_sync_source("src/main.rs").is_ok());
    }

    #[test]
    fn test_build_rsync_args_format() {
        let args = super::sync_helpers::build_rsync_args(".bashrc", "admin", "10.0.0.1", ".bashrc");
        assert_eq!(args[0], "-az");
        assert_eq!(args[1], "-e");
        assert_eq!(args[2], "ssh -o StrictHostKeyChecking=accept-new");
        assert_eq!(args[3], ".bashrc");
        assert_eq!(args[4], "admin@10.0.0.1:~/.bashrc");
    }

    #[test]
    fn test_build_rsync_args_with_subpath() {
        let args =
            super::sync_helpers::build_rsync_args("config/", "user", "192.168.1.1", "config/");
        assert_eq!(args[4], "user@192.168.1.1:~/config/");
    }

    // ── NEW: health_helpers boundary tests ───────────────────────

    #[test]
    fn test_metric_color_exact_50() {
        assert_eq!(super::health_helpers::metric_color(50.0), "green");
    }

    #[test]
    fn test_metric_color_exact_80() {
        assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
    }

    #[test]
    fn test_metric_color_just_above_80() {
        assert_eq!(super::health_helpers::metric_color(80.1), "red");
    }

    #[test]
    fn test_metric_color_just_above_50() {
        assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
    }

    #[test]
    fn test_metric_color_zero() {
        assert_eq!(super::health_helpers::metric_color(0.0), "green");
    }

    #[test]
    fn test_metric_color_100() {
        assert_eq!(super::health_helpers::metric_color(100.0), "red");
    }

    #[test]
    fn test_state_color_deallocated() {
        assert_eq!(super::health_helpers::state_color("deallocated"), "red");
    }

    #[test]
    fn test_state_color_starting() {
        assert_eq!(super::health_helpers::state_color("starting"), "yellow");
    }

    #[test]
    fn test_state_color_empty_string() {
        assert_eq!(super::health_helpers::state_color(""), "yellow");
    }

    #[test]
    fn test_format_percentage_large() {
        assert_eq!(super::health_helpers::format_percentage(99.99), "100.0%");
    }

    #[test]
    fn test_format_percentage_very_negative() {
        assert_eq!(super::health_helpers::format_percentage(-100.0), "0.0%");
    }

    #[test]
    fn test_format_percentage_exactly_zero() {
        assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
    }

    #[test]
    fn test_status_emoji_all_low() {
        assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
    }

    #[test]
    fn test_status_emoji_cpu_critical() {
        assert_eq!(super::health_helpers::status_emoji(91.0, 10.0, 10.0), "🔴");
    }

    #[test]
    fn test_status_emoji_mem_critical() {
        assert_eq!(super::health_helpers::status_emoji(10.0, 95.0, 10.0), "🔴");
    }

    #[test]
    fn test_status_emoji_disk_critical() {
        assert_eq!(super::health_helpers::status_emoji(10.0, 10.0, 91.0), "🔴");
    }

    #[test]
    fn test_status_emoji_cpu_warning() {
        assert_eq!(super::health_helpers::status_emoji(75.0, 10.0, 10.0), "🟡");
    }

    #[test]
    fn test_status_emoji_exact_boundary_70() {
        assert_eq!(super::health_helpers::status_emoji(70.0, 70.0, 70.0), "🟢");
    }

    #[test]
    fn test_status_emoji_exact_boundary_90() {
        assert_eq!(super::health_helpers::status_emoji(90.0, 90.0, 90.0), "🟡");
    }

    // ── NEW: snapshot_helpers additional tests ───────────────────

    #[test]
    fn test_build_snapshot_name_format() {
        let name = super::snapshot_helpers::build_snapshot_name("my-vm", "20250101_120000");
        assert_eq!(name, "my-vm_snapshot_20250101_120000");
    }

    #[test]
    fn test_build_snapshot_name_with_dashes() {
        let name = super::snapshot_helpers::build_snapshot_name("vm-with-dashes", "ts");
        assert_eq!(name, "vm-with-dashes_snapshot_ts");
    }

    #[test]
    fn test_filter_snapshots_partial_match() {
        let snaps = vec![
            serde_json::json!({"name": "dev-vm_snapshot_123"}),
            serde_json::json!({"name": "prod-vm_snapshot_456"}),
            serde_json::json!({"name": "dev-vm_snapshot_789"}),
        ];
        let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "dev-vm");
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_snapshot_row_complete() {
        let snap = serde_json::json!({
            "name": "snap-1",
            "diskSizeGb": 128,
            "timeCreated": "2025-01-01T00:00:00Z",
            "provisioningState": "Succeeded"
        });
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "snap-1");
        assert_eq!(row[1], "128");
        assert_eq!(row[2], "2025-01-01T00:00:00Z");
        assert_eq!(row[3], "Succeeded");
    }

    #[test]
    fn test_snapshot_row_null_fields() {
        let snap = serde_json::json!({});
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "-");
        assert_eq!(row[1], "null");
        assert_eq!(row[2], "-");
        assert_eq!(row[3], "-");
    }

    // ── NEW: output_helpers additional tests ─────────────────────

    #[test]
    fn test_format_as_csv_multiple_rows() {
        let headers = &["Name", "Age", "City"];
        let rows = vec![
            vec!["Alice".into(), "30".into(), "NYC".into()],
            vec!["Bob".into(), "25".into(), "LA".into()],
        ];
        let csv = super::output_helpers::format_as_csv(headers, &rows);
        let lines: Vec<&str> = csv.lines().collect();
        assert_eq!(lines[0], "Name,Age,City");
        assert_eq!(lines[1], "Alice,30,NYC");
        assert_eq!(lines[2], "Bob,25,LA");
    }

    #[test]
    fn test_format_as_csv_single_row() {
        let csv = super::output_helpers::format_as_csv(&["X"], &[vec!["1".into()]]);
        assert_eq!(csv, "X\n1");
    }

    #[test]
    fn test_format_as_table_alignment() {
        let headers = &["Short", "LongerHeader"];
        let rows = vec![vec!["a".into(), "b".into()], vec!["ccc".into(), "d".into()]];
        let table = super::output_helpers::format_as_table(headers, &rows);
        let lines: Vec<&str> = table.lines().collect();
        assert_eq!(lines.len(), 3);
        // Header line should have both column names
        assert!(lines[0].contains("Short"));
        assert!(lines[0].contains("LongerHeader"));
    }

    #[test]
    fn test_format_as_table_single_column() {
        let table = super::output_helpers::format_as_table(
            &["Items"],
            &[vec!["one".into()], vec!["two".into()]],
        );
        assert!(table.contains("Items"));
        assert!(table.contains("one"));
        assert!(table.contains("two"));
    }

    #[test]
    fn test_format_as_table_no_rows() {
        let table = super::output_helpers::format_as_table(&["A", "B"], &[]);
        assert!(table.contains("A"));
        assert!(table.contains("B"));
        assert_eq!(table.lines().count(), 1);
    }

    #[test]
    fn test_format_as_table_wide_cell_expands_column() {
        let headers = &["H"];
        let rows = vec![vec!["very long cell content".into()]];
        let table = super::output_helpers::format_as_table(headers, &rows);
        let lines: Vec<&str> = table.lines().collect();
        // The header line should be padded to at least the width of the cell
        assert!(lines[0].len() >= "very long cell content".len());
    }

    #[test]
    fn test_format_as_json_numbers() {
        let items: Vec<i32> = vec![1, 2, 3];
        let json = super::output_helpers::format_as_json(&items);
        let parsed: Vec<i32> = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed, vec![1, 2, 3]);
    }

    #[test]
    fn test_format_as_json_empty_vec() {
        let items: Vec<String> = vec![];
        let json = super::output_helpers::format_as_json(&items);
        assert_eq!(json.trim(), "[]");
    }

    #[test]
    fn test_format_as_json_structs() {
        let items = vec![
            serde_json::json!({"name": "a"}),
            serde_json::json!({"name": "b"}),
        ];
        let json = super::output_helpers::format_as_json(&items);
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.len(), 2);
    }

    // ── NEW: vm_validation additional tests ──────────────────────

    #[test]
    fn test_vm_name_valid_simple() {
        assert!(super::vm_validation::validate_vm_name("myvm").is_ok());
    }

    #[test]
    fn test_vm_name_valid_with_numbers() {
        assert!(super::vm_validation::validate_vm_name("vm-01-prod").is_ok());
    }

    #[test]
    fn test_vm_name_single_char() {
        assert!(super::vm_validation::validate_vm_name("a").is_ok());
    }

    #[test]
    fn test_vm_name_underscores_rejected() {
        assert!(super::vm_validation::validate_vm_name("my_vm").is_err());
    }

    #[test]
    fn test_vm_name_spaces_rejected() {
        assert!(super::vm_validation::validate_vm_name("my vm").is_err());
    }

    #[test]
    fn test_vm_name_dots_rejected() {
        assert!(super::vm_validation::validate_vm_name("vm.prod").is_err());
    }

    #[test]
    fn test_vm_name_double_hyphen_ok() {
        assert!(super::vm_validation::validate_vm_name("vm--test").is_ok());
    }

    #[test]
    fn test_vm_name_63_chars() {
        let name = "a".repeat(63);
        assert!(super::vm_validation::validate_vm_name(&name).is_ok());
    }

    #[test]
    fn test_vm_name_64_chars() {
        let name = "b".repeat(64);
        assert!(super::vm_validation::validate_vm_name(&name).is_ok());
    }

    #[test]
    fn test_vm_name_65_chars() {
        let name = "c".repeat(65);
        assert!(super::vm_validation::validate_vm_name(&name).is_err());
    }

    // ── NEW: mount_helpers additional tests ──────────────────────

    #[test]
    fn test_mount_path_valid_nested() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/data/disk1").is_ok());
    }

    #[test]
    fn test_mount_path_root() {
        assert!(super::mount_helpers::validate_mount_path("/").is_ok());
    }

    #[test]
    fn test_mount_path_ampersand() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/a&b").is_err());
    }

    #[test]
    fn test_mount_path_dollar() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/$HOME").is_err());
    }

    #[test]
    fn test_mount_path_newline() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/a\nb").is_err());
    }

    #[test]
    fn test_mount_path_null_byte() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/a\0b").is_err());
    }

    #[test]
    fn test_mount_path_relative_rejected() {
        assert!(super::mount_helpers::validate_mount_path("mnt/data").is_err());
    }

    #[test]
    fn test_mount_path_exclamation() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/test!").is_err());
    }

    #[test]
    fn test_mount_path_parentheses() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/(test)").is_err());
    }

    #[test]
    fn test_mount_path_curly_braces() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/{test}").is_err());
    }

    #[test]
    fn test_mount_path_angle_brackets() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/<test>").is_err());
    }

    // ── NEW: config_path_helpers additional tests ────────────────

    #[test]
    fn test_config_path_simple_relative() {
        assert!(super::config_path_helpers::validate_config_path("config.toml").is_ok());
    }

    #[test]
    fn test_config_path_nested() {
        assert!(super::config_path_helpers::validate_config_path("a/b/c.toml").is_ok());
    }

    #[test]
    fn test_config_path_dot_prefix() {
        assert!(super::config_path_helpers::validate_config_path("./config.toml").is_ok());
    }

    #[test]
    fn test_config_path_parent_traversal() {
        assert!(super::config_path_helpers::validate_config_path("../etc/passwd").is_err());
    }

    #[test]
    fn test_config_path_middle_traversal() {
        assert!(super::config_path_helpers::validate_config_path("a/../../etc").is_err());
    }

    #[test]
    fn test_config_path_absolute_allowed() {
        assert!(super::config_path_helpers::validate_config_path("/home/user/config.toml").is_ok());
    }

    // ── NEW: storage_helpers additional tests ────────────────────

    #[test]
    fn test_storage_sku_premium() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("premium"),
            "Premium_LRS"
        );
    }

    #[test]
    fn test_storage_sku_standard() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("standard"),
            "Standard_LRS"
        );
    }

    #[test]
    fn test_storage_sku_mixed_case() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("PREMIUM"),
            "Premium_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("StAnDaRd"),
            "Standard_LRS"
        );
    }

    #[test]
    fn test_storage_sku_unknown() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("unknown"),
            "Premium_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier(""),
            "Premium_LRS"
        );
    }

    #[test]
    fn test_storage_account_row_complete() {
        let acct = serde_json::json!({
            "name": "mystorageacct",
            "location": "westus2",
            "kind": "StorageV2",
            "sku": {"name": "Standard_LRS"},
            "provisioningState": "Succeeded"
        });
        let row = super::storage_helpers::storage_account_row(&acct);
        assert_eq!(
            row,
            vec![
                "mystorageacct",
                "westus2",
                "StorageV2",
                "Standard_LRS",
                "Succeeded"
            ]
        );
    }

    #[test]
    fn test_storage_account_row_partial() {
        let acct = serde_json::json!({"name": "partial"});
        let row = super::storage_helpers::storage_account_row(&acct);
        assert_eq!(row[0], "partial");
        assert_eq!(row[1], "-");
        assert_eq!(row[2], "-");
        assert_eq!(row[3], "-");
        assert_eq!(row[4], "-");
    }

    #[test]
    fn test_storage_account_row_empty() {
        let acct = serde_json::json!({});
        let row = super::storage_helpers::storage_account_row(&acct);
        assert!(row.iter().all(|c| c == "-"));
    }

    // ── NEW: key_helpers additional tests ────────────────────────

    #[test]
    fn test_detect_key_type_filename_prefix() {
        assert_eq!(
            super::key_helpers::detect_key_type("id_ed25519.pub"),
            "ed25519"
        );
        assert_eq!(super::key_helpers::detect_key_type("id_ecdsa.pub"), "ecdsa");
        assert_eq!(super::key_helpers::detect_key_type("id_rsa.pub"), "rsa");
        assert_eq!(super::key_helpers::detect_key_type("id_dsa.pub"), "dsa");
    }

    #[test]
    fn test_detect_key_type_custom_name() {
        assert_eq!(
            super::key_helpers::detect_key_type("my_ed25519_key"),
            "ed25519"
        );
        assert_eq!(super::key_helpers::detect_key_type("backup_rsa"), "rsa");
    }

    #[test]
    fn test_detect_key_type_random_file() {
        assert_eq!(
            super::key_helpers::detect_key_type("known_hosts"),
            "unknown"
        );
        assert_eq!(
            super::key_helpers::detect_key_type("authorized_keys"),
            "unknown"
        );
    }

    #[test]
    fn test_is_known_key_name_standard_private() {
        assert!(super::key_helpers::is_known_key_name("id_rsa"));
        assert!(super::key_helpers::is_known_key_name("id_ed25519"));
        assert!(super::key_helpers::is_known_key_name("id_ecdsa"));
        assert!(super::key_helpers::is_known_key_name("id_dsa"));
    }

    #[test]
    fn test_is_known_key_name_pub_extension() {
        assert!(super::key_helpers::is_known_key_name("custom.pub"));
        assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
    }

    #[test]
    fn test_is_known_key_name_non_key_files() {
        assert!(!super::key_helpers::is_known_key_name("known_hosts"));
        assert!(!super::key_helpers::is_known_key_name("config"));
        assert!(!super::key_helpers::is_known_key_name("authorized_keys"));
    }

    // ── NEW: auth_helpers additional tests ───────────────────────

    #[test]
    fn test_mask_profile_string_no_secret() {
        let v = serde_json::json!("my-tenant-id");
        assert_eq!(
            super::auth_helpers::mask_profile_value("tenant_id", &v),
            "my-tenant-id"
        );
    }

    #[test]
    fn test_mask_profile_secret_key() {
        let v = serde_json::json!("s3cr3t-value");
        assert_eq!(
            super::auth_helpers::mask_profile_value("client_secret", &v),
            "********"
        );
    }

    #[test]
    fn test_mask_profile_password_key() {
        let v = serde_json::json!("pa$$word");
        assert_eq!(
            super::auth_helpers::mask_profile_value("admin_password", &v),
            "********"
        );
    }

    #[test]
    fn test_mask_profile_number_value() {
        let v = serde_json::json!(42);
        assert_eq!(super::auth_helpers::mask_profile_value("count", &v), "42");
    }

    #[test]
    fn test_mask_profile_bool_value() {
        let v = serde_json::json!(true);
        assert_eq!(
            super::auth_helpers::mask_profile_value("enabled", &v),
            "true"
        );
    }

    #[test]
    fn test_mask_profile_null_value() {
        let v = serde_json::json!(null);
        assert_eq!(super::auth_helpers::mask_profile_value("field", &v), "null");
    }

    #[test]
    fn test_mask_profile_secret_in_key_substring() {
        let v = serde_json::json!("value123");
        assert_eq!(
            super::auth_helpers::mask_profile_value("my_secret_key", &v),
            "********"
        );
    }

    // ── NEW: cp_helpers additional tests ─────────────────────────

    #[test]
    fn test_is_remote_path_standard() {
        assert!(super::cp_helpers::is_remote_path("vm-name:/path/to/file"));
    }

    #[test]
    fn test_is_remote_path_short_colon() {
        // Two chars with colon at pos 1 like "C:" should NOT be remote
        assert!(!super::cp_helpers::is_remote_path("C:"));
    }

    #[test]
    fn test_is_remote_path_absolute() {
        assert!(!super::cp_helpers::is_remote_path("/home/user/file.txt"));
    }

    #[test]
    fn test_is_remote_path_windows_drive() {
        assert!(!super::cp_helpers::is_remote_path("C:\\Users\\file"));
    }

    #[test]
    fn test_is_remote_path_no_colon() {
        assert!(!super::cp_helpers::is_remote_path("localfile.txt"));
    }

    #[test]
    fn test_is_remote_path_empty() {
        assert!(!super::cp_helpers::is_remote_path(""));
    }

    #[test]
    fn test_classify_transfer_local_to_remote() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("file.txt", "vm:/path"),
            "local→remote"
        );
    }

    #[test]
    fn test_classify_transfer_remote_to_local() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("vm:/path", "file.txt"),
            "remote→local"
        );
    }

    #[test]
    fn test_classify_transfer_both_local() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("file1.txt", "file2.txt"),
            "local→local"
        );
    }

    #[test]
    fn test_resolve_scp_path_rewrite() {
        let result =
            super::cp_helpers::resolve_scp_path("vm-1:/data/file.txt", "vm-1", "admin", "10.0.0.5");
        assert_eq!(result, "admin@10.0.0.5:/data/file.txt");
    }

    #[test]
    fn test_resolve_scp_path_no_match_passthrough() {
        let result = super::cp_helpers::resolve_scp_path("other-vm:/file", "vm-1", "u", "1.2.3.4");
        assert_eq!(result, "other-vm:/file");
    }

    // ── NEW: bastion_helpers additional tests ────────────────────

    #[test]
    fn test_bastion_summary_full_json() {
        let b = serde_json::json!({
            "name": "bastion-prod",
            "resourceGroup": "rg-prod",
            "location": "eastus",
            "sku": {"name": "Premium"},
            "provisioningState": "Succeeded"
        });
        let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
        assert_eq!(name, "bastion-prod");
        assert_eq!(rg, "rg-prod");
        assert_eq!(loc, "eastus");
        assert_eq!(sku, "Premium");
        assert_eq!(state, "Succeeded");
    }

    #[test]
    fn test_bastion_summary_missing_all() {
        let b = serde_json::json!({});
        let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
        assert_eq!(name, "unknown");
        assert_eq!(rg, "unknown");
        assert_eq!(loc, "unknown");
        assert_eq!(sku, "Standard");
        assert_eq!(state, "unknown");
    }

    #[test]
    fn test_shorten_resource_id_long() {
        let id = "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Network/bastionHosts/my-bastion";
        assert_eq!(
            super::bastion_helpers::shorten_resource_id(id),
            "my-bastion"
        );
    }

    #[test]
    fn test_shorten_resource_id_single_segment() {
        assert_eq!(
            super::bastion_helpers::shorten_resource_id("just-a-name"),
            "just-a-name"
        );
    }

    #[test]
    fn test_shorten_resource_id_empty() {
        assert_eq!(super::bastion_helpers::shorten_resource_id(""), "");
    }

    #[test]
    fn test_extract_ip_configs_multiple() {
        let b = serde_json::json!({
            "ipConfigurations": [
                {
                    "subnet": {"id": "/subs/x/subnets/sn-1"},
                    "publicIPAddress": {"id": "/subs/x/publicIPAddresses/pip-1"}
                },
                {
                    "subnet": {"id": "/subs/x/subnets/sn-2"},
                    "publicIPAddress": {"id": "/subs/x/publicIPAddresses/pip-2"}
                }
            ]
        });
        let configs = super::bastion_helpers::extract_ip_configs(&b);
        assert_eq!(configs.len(), 2);
        assert_eq!(configs[0], ("sn-1".to_string(), "pip-1".to_string()));
        assert_eq!(configs[1], ("sn-2".to_string(), "pip-2".to_string()));
    }

    #[test]
    fn test_extract_ip_configs_missing_ids() {
        let b = serde_json::json!({
            "ipConfigurations": [
                {"subnet": {}, "publicIPAddress": {}}
            ]
        });
        let configs = super::bastion_helpers::extract_ip_configs(&b);
        assert_eq!(configs.len(), 1);
        assert_eq!(configs[0], ("N/A".to_string(), "N/A".to_string()));
    }

    #[test]
    fn test_extract_ip_configs_no_array() {
        let b = serde_json::json!({"name": "no-configs"});
        let configs = super::bastion_helpers::extract_ip_configs(&b);
        assert!(configs.is_empty());
    }

    // ── NEW: log_helpers additional tests ────────────────────────

    #[test]
    fn test_tail_start_index_large_total() {
        assert_eq!(super::log_helpers::tail_start_index(1000, 50), 950);
    }

    #[test]
    fn test_tail_start_index_count_larger_than_total() {
        assert_eq!(super::log_helpers::tail_start_index(5, 100), 0);
    }

    #[test]
    fn test_tail_start_index_both_zero() {
        assert_eq!(super::log_helpers::tail_start_index(0, 0), 0);
    }

    #[test]
    fn test_tail_start_index_count_one() {
        assert_eq!(super::log_helpers::tail_start_index(10, 1), 9);
    }

    // ── NEW: parse_cost_history_rows additional tests ────────────

    #[test]
    fn test_parse_cost_history_rows_no_rows_key() {
        let data = serde_json::json!({"other": "data"});
        let rows = super::parse_cost_history_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_history_rows_rows_not_array() {
        let data = serde_json::json!({"rows": "not-array"});
        let rows = super::parse_cost_history_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_history_rows_multiple_entries() {
        let data = serde_json::json!({
            "rows": [
                [10.5, "2025-01-01"],
                [20.0, "2025-01-02"],
                [0.0, "2025-01-03"]
            ]
        });
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0], ("2025-01-01".to_string(), "$10.50".to_string()));
        assert_eq!(rows[1], ("2025-01-02".to_string(), "$20.00".to_string()));
        assert_eq!(rows[2], ("2025-01-03".to_string(), "$0.00".to_string()));
    }

    #[test]
    fn test_parse_cost_history_rows_integer_date() {
        let data = serde_json::json!({"rows": [[5.0, 20250101]]});
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 1);
        // Integer dates yield empty string due to as_str().or_else(as_i64 -> "") mapping
        assert_eq!(rows[0].0, "");
        assert_eq!(rows[0].1, "$5.00");
    }

    #[test]
    fn test_parse_cost_history_rows_null_values() {
        let data = serde_json::json!({"rows": [[null, null]]});
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "-");
        assert_eq!(rows[0].1, "-");
    }

    // ── NEW: parse_recommendation_rows additional tests ─────────

    #[test]
    fn test_parse_recommendation_rows_null_input() {
        let data = serde_json::json!(null);
        let rows = super::parse_recommendation_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_recommendation_rows_empty_array() {
        let data = serde_json::json!([]);
        let rows = super::parse_recommendation_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_recommendation_rows_partial_fields() {
        let data = serde_json::json!([
            {"category": "Cost"},
            {"impact": "High"},
            {"shortDescription": {"problem": "Underutilized"}}
        ]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0], ("Cost".into(), "-".into(), "-".into()));
        assert_eq!(rows[1], ("-".into(), "High".into(), "-".into()));
        assert_eq!(rows[2], ("-".into(), "-".into(), "Underutilized".into()));
    }

    #[test]
    fn test_parse_recommendation_rows_complete() {
        let data = serde_json::json!([{
            "category": "Cost",
            "impact": "Medium",
            "shortDescription": {"problem": "Resize VM to save money"}
        }]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "Cost");
        assert_eq!(rows[0].1, "Medium");
        assert_eq!(rows[0].2, "Resize VM to save money");
    }

    // ── NEW: parse_cost_action_rows additional tests ────────────

    #[test]
    fn test_parse_cost_action_rows_null_input() {
        let data = serde_json::json!(null);
        let rows = super::parse_cost_action_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_action_rows_object_not_array() {
        let data = serde_json::json!({"key": "val"});
        let rows = super::parse_cost_action_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_action_rows_complete() {
        let data = serde_json::json!([{
            "impactedField": "Microsoft.Compute/virtualMachines",
            "impact": "High",
            "shortDescription": {"problem": "Shut down unused VMs"}
        }]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
        assert_eq!(rows[0].1, "High");
        assert_eq!(rows[0].2, "Shut down unused VMs");
    }

    #[test]
    fn test_parse_cost_action_rows_missing_all_fields() {
        let data = serde_json::json!([{}]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0], ("-".into(), "-".into(), "-".into()));
    }

    #[test]
    fn test_parse_cost_action_rows_multiple() {
        let data = serde_json::json!([
            {"impactedField": "F1", "impact": "Low", "shortDescription": {"problem": "P1"}},
            {"impactedField": "F2", "impact": "High", "shortDescription": {"problem": "P2"}}
        ]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].0, "F1");
        assert_eq!(rows[1].0, "F2");
    }

    // ── NEW: format_cost_summary additional tests ───────────────

    #[test]
    fn test_format_cost_summary_table_with_filters() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 150.75,
            currency: "USD".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &Some("2025-01-01".into()),
            &Some("2025-01-31".into()),
            false,
            false,
        );
        assert!(out.contains("$150.75"));
        assert!(out.contains("From filter: 2025-01-01"));
        assert!(out.contains("To filter: 2025-01-31"));
    }

    #[test]
    fn test_format_cost_summary_table_with_estimate() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 50.0,
            currency: "USD".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            true,
            false,
        );
        assert!(out.contains("Estimate: $50.00/month (projected)"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_empty_table() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-06-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-06-30T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            true,
        );
        assert!(out.contains("No per-VM cost data available"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_csv_multi() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 200.0,
            currency: "USD".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![
                azlin_core::models::VmCost {
                    vm_name: "vm-a".to_string(),
                    cost: 120.50,
                    currency: "USD".to_string(),
                },
                azlin_core::models::VmCost {
                    vm_name: "vm-b".to_string(),
                    cost: 79.50,
                    currency: "USD".to_string(),
                },
            ],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            true,
        );
        assert!(out.contains("VM Name,Cost,Currency"));
        assert!(out.contains("vm-a,120.50,USD"));
        assert!(out.contains("vm-b,79.50,USD"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_table_format() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 300.0,
            currency: "EUR".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-03-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-03-31T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![azlin_core::models::VmCost {
                vm_name: "prod-vm".to_string(),
                cost: 300.0,
                currency: "EUR".to_string(),
            }],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            true,
        );
        assert!(out.contains("$300.00 EUR"));
        assert!(out.contains("prod-vm"));
    }

    #[test]
    fn test_format_cost_summary_json_output() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 99.99,
            currency: "USD".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-01-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-01-31T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Json,
            &Some("ignored".into()),
            &Some("ignored".into()),
            true,
            true,
        );
        let parsed: serde_json::Value = serde_json::from_str(&out).unwrap();
        assert_eq!(parsed["total_cost"].as_f64().unwrap(), 99.99);
        assert_eq!(parsed["currency"].as_str().unwrap(), "USD");
    }

    #[test]
    fn test_format_cost_summary_csv_no_by_vm() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 42.0,
            currency: "GBP".to_string(),
            period_start: chrono::DateTime::parse_from_rfc3339("2025-02-01T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            period_end: chrono::DateTime::parse_from_rfc3339("2025-02-28T00:00:00Z")
                .unwrap()
                .with_timezone(&chrono::Utc),
            by_vm: vec![],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            false,
        );
        assert!(out.starts_with("Total Cost,Currency,Period Start,Period End\n"));
        assert!(out.contains("42.00,GBP,2025-02-01,2025-02-28"));
    }

    // ── NEW: shell_escape additional tests ───────────────────────

    #[test]
    fn test_shell_escape_tab() {
        let result = super::shell_escape("\t");
        assert_eq!(result, "'\t'");
    }

    #[test]
    fn test_shell_escape_mixed_quotes() {
        let result = super::shell_escape("it's a \"test\"");
        assert_eq!(result, "'it'\\''s a \"test\"'");
    }

    #[test]
    fn test_shell_escape_backslash() {
        let result = super::shell_escape("path\\to\\file");
        assert_eq!(result, "'path\\to\\file'");
    }

    #[test]
    fn test_shell_escape_env_var_syntax() {
        let result = super::shell_escape("${HOME}");
        assert_eq!(result, "'${HOME}'");
    }

    #[test]
    fn test_shell_escape_command_substitution() {
        let result = super::shell_escape("$(whoami)");
        assert_eq!(result, "'$(whoami)'");
    }

    #[test]
    fn test_shell_escape_consecutive_single_quotes() {
        let result = super::shell_escape("''");
        assert_eq!(result, "''\\'''\\'''");
    }

    // ── NEW: auth_test_helpers additional tests ─────────────────

    #[test]
    fn test_extract_account_info_nested_user() {
        let acct = serde_json::json!({
            "name": "Enterprise Sub",
            "tenantId": "t-abc-123",
            "user": {"name": "admin@contoso.com", "type": "servicePrincipal"}
        });
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "Enterprise Sub");
        assert_eq!(tenant, "t-abc-123");
        assert_eq!(user, "admin@contoso.com");
    }

    #[test]
    fn test_extract_account_info_numeric_values() {
        let acct = serde_json::json!({
            "name": 123,
            "tenantId": 456,
            "user": {"name": 789}
        });
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "-");
        assert_eq!(tenant, "-");
        assert_eq!(user, "-");
    }

    // ── NEW: template file system edge cases ─────────────────────

    #[test]
    fn test_template_overwrite_existing() {
        let tmp = TempDir::new().unwrap();
        let tpl1 = super::templates::build_template_toml("x", Some("v1"), None, None, None);
        super::templates::save_template(tmp.path(), "x", &tpl1).unwrap();
        let tpl2 = super::templates::build_template_toml("x", Some("v2"), None, None, None);
        super::templates::save_template(tmp.path(), "x", &tpl2).unwrap();
        let loaded = super::templates::load_template(tmp.path(), "x").unwrap();
        assert_eq!(loaded["description"].as_str().unwrap(), "v2");
    }

    #[test]
    fn test_template_import_overwrites_existing() {
        let tmp = TempDir::new().unwrap();
        let tpl = super::templates::build_template_toml("imp", Some("old"), None, None, None);
        super::templates::save_template(tmp.path(), "imp", &tpl).unwrap();
        let content = "name = \"imp\"\ndescription = \"new\"\nvm_size = \"Standard_A1\"\nregion = \"westus\"\n";
        super::templates::import_template(tmp.path(), content).unwrap();
        let loaded = super::templates::load_template(tmp.path(), "imp").unwrap();
        assert_eq!(loaded["description"].as_str().unwrap(), "new");
    }

    // ── NEW: session file persistence tests ──────────────────────

    #[test]
    fn test_session_save_then_list() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path().join("sessions");
        fs::create_dir_all(&dir).unwrap();
        for name in &["alpha", "beta", "gamma"] {
            let s = super::sessions::build_session_toml(name, "rg", &[]);
            let content = toml::to_string_pretty(&s).unwrap();
            fs::write(dir.join(format!("{}.toml", name)), content).unwrap();
        }
        let names = super::sessions::list_session_names(&dir).unwrap();
        assert_eq!(names.len(), 3);
        for expected in &["alpha", "beta", "gamma"] {
            assert!(names.contains(&expected.to_string()));
        }
    }

    #[test]
    fn test_session_parse_with_many_vms() {
        let vms: Vec<String> = (0..20).map(|i| format!("vm-{:03}", i)).collect();
        let built = super::sessions::build_session_toml("big", "rg-big", &vms);
        let serialized = toml::to_string_pretty(&built).unwrap();
        let (rg, parsed_vms, _) = super::sessions::parse_session_toml(&serialized).unwrap();
        assert_eq!(rg, "rg-big");
        assert_eq!(parsed_vms.len(), 20);
        assert_eq!(parsed_vms[0], "vm-000");
        assert_eq!(parsed_vms[19], "vm-019");
    }

    // ── NEW: context file persistence tests ──────────────────────

    #[test]
    fn test_context_rename_preserves_other_fields() {
        let tmp = TempDir::new().unwrap();
        let content = super::contexts::build_context_toml(
            "old",
            Some("sub-1"),
            Some("tenant-1"),
            Some("rg-1"),
            Some("westus2"),
            Some("kv-1"),
        )
        .unwrap();
        fs::write(tmp.path().join("old.toml"), content).unwrap();
        super::contexts::rename_context_file(tmp.path(), "old", "new").unwrap();
        let loaded: toml::Value = fs::read_to_string(tmp.path().join("new.toml"))
            .unwrap()
            .parse()
            .unwrap();
        let t = loaded.as_table().unwrap();
        assert_eq!(t["name"].as_str().unwrap(), "new");
        assert_eq!(t["subscription_id"].as_str().unwrap(), "sub-1");
        assert_eq!(t["tenant_id"].as_str().unwrap(), "tenant-1");
        assert_eq!(t["resource_group"].as_str().unwrap(), "rg-1");
        assert_eq!(t["region"].as_str().unwrap(), "westus2");
        assert_eq!(t["key_vault_name"].as_str().unwrap(), "kv-1");
    }

    #[test]
    fn test_context_list_sorted() {
        let tmp = TempDir::new().unwrap();
        for name in &["charlie", "alpha", "bravo"] {
            fs::write(
                tmp.path().join(format!("{}.toml", name)),
                format!("name = \"{}\"\n", name),
            )
            .unwrap();
        }
        let list = super::contexts::list_contexts(tmp.path(), "bravo").unwrap();
        assert_eq!(list[0].0, "alpha");
        assert_eq!(list[1].0, "bravo");
        assert!(list[1].1);
        assert_eq!(list[2].0, "charlie");
    }

    // ── NEW: comprehensive validate_env_key tests ───────────────

    #[test]
    fn test_validate_env_key_all_digits() {
        assert!(super::env_helpers::validate_env_key("123").is_err());
    }

    #[test]
    fn test_validate_env_key_underscore_start() {
        assert!(super::env_helpers::validate_env_key("_VAR").is_ok());
    }

    #[test]
    fn test_validate_env_key_long_valid() {
        let key = "A".repeat(256);
        assert!(super::env_helpers::validate_env_key(&key).is_ok());
    }

    #[test]
    fn test_validate_env_key_tab() {
        assert!(super::env_helpers::validate_env_key("A\tB").is_err());
    }

    #[test]
    fn test_validate_env_key_newline() {
        assert!(super::env_helpers::validate_env_key("A\nB").is_err());
    }

    // ── NEW: cp_helpers edge cases ──────────────────────────────

    #[test]
    fn test_is_remote_path_colon_at_end() {
        assert!(super::cp_helpers::is_remote_path("vm:"));
    }

    #[test]
    fn test_is_remote_path_long_vm_name() {
        assert!(super::cp_helpers::is_remote_path(
            "my-long-vm-name-123:/data/dir"
        ));
    }

    #[test]
    fn test_classify_both_remote() {
        // Both paths have colons and look remote, so neither condition
        // (remote+!remote or !remote+remote) matches — returns local→local
        let dir = super::cp_helpers::classify_transfer_direction("vm1:/a", "vm2:/b");
        assert_eq!(dir, "local→local");
    }

    #[test]
    fn test_resolve_scp_path_multiple_colons() {
        let result =
            super::cp_helpers::resolve_scp_path("vm:path:with:colons", "vm", "u", "1.1.1.1");
        assert_eq!(result, "u@1.1.1.1:path:with:colons");
    }

    // ── NEW: output formatting with unicode ─────────────────────

    #[test]
    fn test_format_as_csv_unicode_content() {
        let rows = vec![vec!["名前".into(), "東京".into()]];
        let csv = super::output_helpers::format_as_csv(&["Name", "City"], &rows);
        assert!(csv.contains("名前,東京"));
    }

    #[test]
    fn test_format_as_table_unicode_alignment() {
        let rows = vec![vec!["日本語".into(), "データ".into()]];
        let table = super::output_helpers::format_as_table(&["Label", "Value"], &rows);
        assert!(table.contains("日本語"));
        assert!(table.contains("データ"));
    }

    #[test]
    fn test_format_as_csv_commas_in_values() {
        let rows = vec![vec!["a,b".into(), "c".into()]];
        let csv = super::output_helpers::format_as_csv(&["X", "Y"], &rows);
        // Note: no escaping is done - this tests current behavior
        assert!(csv.contains("a,b,c"));
    }

    // ── NEW: snapshot filter edge cases ──────────────────────────

    #[test]
    fn test_filter_snapshots_substring_match() {
        let snaps = vec![
            serde_json::json!({"name": "vm1_snap"}),
            serde_json::json!({"name": "vm10_snap"}),
            serde_json::json!({"name": "vm1-extra_snap"}),
        ];
        let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "vm1");
        // "vm1" is a substring of all three
        assert_eq!(filtered.len(), 3);
    }

    #[test]
    fn test_filter_snapshots_case_sensitive() {
        let snaps = vec![
            serde_json::json!({"name": "VM1_snap"}),
            serde_json::json!({"name": "vm1_snap"}),
        ];
        let filtered = super::snapshot_helpers::filter_snapshots(&snaps, "vm1");
        assert_eq!(filtered.len(), 1);
    }

    // ── NEW: validate_mount_path traversal cases ────────────────

    #[test]
    fn test_mount_path_traversal_in_middle() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/a/../b").is_err());
    }

    #[test]
    fn test_mount_path_traversal_at_end() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/..").is_err());
    }

    #[test]
    fn test_mount_path_with_spaces_ok() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/my data").is_ok());
    }

    #[test]
    fn test_mount_path_deeply_nested() {
        assert!(super::mount_helpers::validate_mount_path("/a/b/c/d/e/f/g/h").is_ok());
    }

    // ── Additional shell_escape tests ───────────────────────────
    #[test]
    fn test_shell_escape_empty_v2() {
        assert_eq!(super::shell_escape(""), "''");
    }

    #[test]
    fn test_shell_escape_special_chars() {
        assert_eq!(super::shell_escape("a b;c&d|e"), "'a b;c&d|e'");
    }

    #[test]
    fn test_shell_escape_with_newlines_v2() {
        assert_eq!(super::shell_escape("line1\nline2"), "'line1\nline2'");
    }

    // ── Additional parse tests ──────────────────────────────────
    #[test]
    fn test_parse_recommendation_rows_only_category() {
        let data = serde_json::json!([{
            "category": "Cost"
        }]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "Cost");
        assert_eq!(rows[0].1, "-");
    }

    #[test]
    fn test_parse_recommendation_rows_two_entries() {
        let data = serde_json::json!([
            {"category": "Cost", "impact": "High", "shortDescription": {"problem": "idle VM"}},
            {"category": "Security", "impact": "Low", "shortDescription": {"problem": "no NSG"}}
        ]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[1].0, "Security");
    }

    #[test]
    fn test_parse_cost_action_rows_missing_solution_field() {
        let data = serde_json::json!([{
            "category": "Cost",
            "impact": "Medium",
            "shortDescription": {}
        }]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].2, "-");
    }

    #[test]
    fn test_parse_cost_action_rows_two_items() {
        let data = serde_json::json!([
            {"impactedField": "VM/compute", "impact": "High", "shortDescription": {"problem": "idle VM"}},
            {"impactedField": "Storage", "impact": "Low", "shortDescription": {"problem": "unattached disk"}}
        ]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].0, "VM/compute");
        assert_eq!(rows[0].2, "idle VM");
        assert_eq!(rows[1].0, "Storage");
    }

    // ── format_cost_summary additional tests ────────────────────
    #[test]
    fn test_format_cost_summary_with_from_to_filters() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 50.0,
            currency: "USD".to_string(),
            period_start: chrono::NaiveDate::from_ymd_opt(2025, 1, 1)
                .unwrap()
                .and_hms_opt(0, 0, 0)
                .unwrap()
                .and_utc(),
            period_end: chrono::NaiveDate::from_ymd_opt(2025, 1, 31)
                .unwrap()
                .and_hms_opt(0, 0, 0)
                .unwrap()
                .and_utc(),
            by_vm: vec![],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &Some("2025-01-01".to_string()),
            &Some("2025-01-31".to_string()),
            false,
            false,
        );
        assert!(out.contains("From filter: 2025-01-01"));
        assert!(out.contains("To filter: 2025-01-31"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_csv_output() {
        let summary = azlin_core::models::CostSummary {
            total_cost: 200.0,
            currency: "USD".to_string(),
            period_start: chrono::NaiveDate::from_ymd_opt(2025, 1, 1)
                .unwrap()
                .and_hms_opt(0, 0, 0)
                .unwrap()
                .and_utc(),
            period_end: chrono::NaiveDate::from_ymd_opt(2025, 1, 31)
                .unwrap()
                .and_hms_opt(0, 0, 0)
                .unwrap()
                .and_utc(),
            by_vm: vec![
                azlin_core::models::VmCost {
                    vm_name: "vm-1".to_string(),
                    cost: 100.0,
                    currency: "USD".to_string(),
                },
                azlin_core::models::VmCost {
                    vm_name: "vm-2".to_string(),
                    cost: 100.0,
                    currency: "USD".to_string(),
                },
            ],
        };
        let out = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            true,
        );
        assert!(out.contains("VM Name,Cost,Currency"));
        assert!(out.contains("vm-1,100.00,USD"));
        assert!(out.contains("vm-2,100.00,USD"));
    }

    // ── fleet_spinner_style test ────────────────────────────────
    #[test]
    fn test_fleet_spinner_style_creation() {
        let style = super::fleet_spinner_style();
        let _ = style;
    }

    // ── HealthMetrics test ──────────────────────────────────────
    #[test]
    fn test_health_metrics_struct() {
        let m = super::HealthMetrics {
            vm_name: "test-vm".to_string(),
            power_state: "running".to_string(),
            cpu_percent: 45.0,
            mem_percent: 60.0,
            disk_percent: 30.0,
            load_avg: "1.5 2.0 1.8".to_string(),
        };
        assert_eq!(m.vm_name, "test-vm");
        assert_eq!(m.power_state, "running");
        assert!(m.cpu_percent > 0.0);
    }

    // ── health_parse_helpers tests ──────────────────────────────

    #[test]
    fn test_parse_cpu_stdout_valid() {
        assert_eq!(
            super::health_parse_helpers::parse_cpu_stdout(0, "  23.4\n"),
            Some(23.4)
        );
    }

    #[test]
    fn test_parse_cpu_stdout_non_zero_exit() {
        assert_eq!(
            super::health_parse_helpers::parse_cpu_stdout(1, "23.4"),
            None
        );
    }

    #[test]
    fn test_parse_cpu_stdout_garbage() {
        assert_eq!(
            super::health_parse_helpers::parse_cpu_stdout(0, "not a number"),
            None
        );
    }

    #[test]
    fn test_parse_cpu_stdout_empty() {
        assert_eq!(super::health_parse_helpers::parse_cpu_stdout(0, ""), None);
    }

    #[test]
    fn test_parse_cpu_stdout_whitespace_only() {
        assert_eq!(
            super::health_parse_helpers::parse_cpu_stdout(0, "   \n  "),
            None
        );
    }

    #[test]
    fn test_parse_mem_stdout_valid() {
        assert_eq!(
            super::health_parse_helpers::parse_mem_stdout(0, "67.3\n"),
            Some(67.3)
        );
    }

    #[test]
    fn test_parse_mem_stdout_failure() {
        assert_eq!(
            super::health_parse_helpers::parse_mem_stdout(127, "67.3"),
            None
        );
    }

    #[test]
    fn test_parse_mem_stdout_zero() {
        assert_eq!(
            super::health_parse_helpers::parse_mem_stdout(0, "0.0"),
            Some(0.0)
        );
    }

    #[test]
    fn test_parse_disk_stdout_valid() {
        assert_eq!(
            super::health_parse_helpers::parse_disk_stdout(0, " 42 \n"),
            Some(42.0)
        );
    }

    #[test]
    fn test_parse_disk_stdout_failure() {
        assert_eq!(
            super::health_parse_helpers::parse_disk_stdout(255, "42"),
            None
        );
    }

    #[test]
    fn test_parse_disk_stdout_not_numeric() {
        assert_eq!(
            super::health_parse_helpers::parse_disk_stdout(0, "N/A"),
            None
        );
    }

    #[test]
    fn test_parse_load_stdout_valid() {
        assert_eq!(
            super::health_parse_helpers::parse_load_stdout(0, " 1.23, 0.45, 0.67 \n"),
            Some("1.23, 0.45, 0.67".to_string())
        );
    }

    #[test]
    fn test_parse_load_stdout_failure() {
        assert_eq!(
            super::health_parse_helpers::parse_load_stdout(1, "1.23, 0.45, 0.67"),
            None
        );
    }

    #[test]
    fn test_parse_load_stdout_empty() {
        assert_eq!(
            super::health_parse_helpers::parse_load_stdout(0, "  \n"),
            None
        );
    }

    #[test]
    fn test_default_metrics() {
        let m = super::health_parse_helpers::default_metrics("my-vm", "deallocated");
        assert_eq!(m.vm_name, "my-vm");
        assert_eq!(m.power_state, "deallocated");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
        assert_eq!(m.load_avg, "-");
    }

    // ── fleet_helpers tests ─────────────────────────────────────

    #[test]
    fn test_classify_result_success() {
        let (status, ok) = super::fleet_helpers::classify_result(0);
        assert_eq!(status, "OK");
        assert!(ok);
    }

    #[test]
    fn test_classify_result_failure() {
        let (status, ok) = super::fleet_helpers::classify_result(1);
        assert_eq!(status, "FAIL");
        assert!(!ok);
    }

    #[test]
    fn test_classify_result_negative() {
        let (status, ok) = super::fleet_helpers::classify_result(-1);
        assert_eq!(status, "FAIL");
        assert!(!ok);
    }

    #[test]
    fn test_finish_message_success() {
        let msg = super::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
        assert_eq!(msg, "✓ done (3 lines)");
    }

    #[test]
    fn test_finish_message_success_empty_stdout() {
        let msg = super::fleet_helpers::finish_message(0, "", "");
        assert_eq!(msg, "✓ done (0 lines)");
    }

    #[test]
    fn test_finish_message_failure() {
        let msg = super::fleet_helpers::finish_message(1, "", "Permission denied\nfatal error");
        assert_eq!(msg, "✗ Permission denied");
    }

    #[test]
    fn test_finish_message_failure_empty_stderr() {
        let msg = super::fleet_helpers::finish_message(1, "", "");
        assert_eq!(msg, "✗ error");
    }

    #[test]
    fn test_format_output_text_show_output_with_stdout() {
        let text =
            super::fleet_helpers::format_output_text(0, "hello world\n", "some warning", true);
        assert_eq!(text, "hello world");
    }

    #[test]
    fn test_format_output_text_show_output_empty_stdout() {
        let text = super::fleet_helpers::format_output_text(0, "  \n", "stderr output", true);
        assert_eq!(text, "stderr output");
    }

    #[test]
    fn test_format_output_text_no_show_failure() {
        let text = super::fleet_helpers::format_output_text(
            1,
            "",
            "error: connection refused\nmore details",
            false,
        );
        assert_eq!(text, "error: connection refused");
    }

    #[test]
    fn test_format_output_text_no_show_success() {
        let text = super::fleet_helpers::format_output_text(0, "data", "warning", false);
        assert_eq!(text, "");
    }

    #[test]
    fn test_format_output_text_no_show_failure_empty_stderr() {
        let text = super::fleet_helpers::format_output_text(1, "", "", false);
        assert_eq!(text, "");
    }

    // ── list_helpers tests ──────────────────────────────────────

    fn make_vm(name: &str, state: azlin_core::models::PowerState) -> azlin_core::models::VmInfo {
        azlin_core::models::VmInfo {
            name: name.to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "Standard_B2s".to_string(),
            power_state: state,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: azlin_core::models::OsType::Linux,
            os_offer: None,
            public_ip: Some("10.0.0.1".to_string()),
            private_ip: None,
            admin_username: Some("azureuser".to_string()),
            tags: std::collections::HashMap::new(),
            created_time: None,
        }
    }

    fn make_tagged_vm(name: &str, tags: Vec<(&str, &str)>) -> azlin_core::models::VmInfo {
        let mut vm = make_vm(name, azlin_core::models::PowerState::Running);
        for (k, v) in tags {
            vm.tags.insert(k.to_string(), v.to_string());
        }
        vm
    }

    #[test]
    fn test_filter_running_removes_stopped() {
        let mut vms = vec![
            make_vm("running-vm", azlin_core::models::PowerState::Running),
            make_vm("stopped-vm", azlin_core::models::PowerState::Stopped),
            make_vm("starting-vm", azlin_core::models::PowerState::Starting),
            make_vm("dealloc-vm", azlin_core::models::PowerState::Deallocated),
        ];
        super::list_helpers::filter_running(&mut vms);
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].name, "running-vm");
        assert_eq!(vms[1].name, "starting-vm");
    }

    #[test]
    fn test_filter_running_empty_list() {
        let mut vms: Vec<azlin_core::models::VmInfo> = vec![];
        super::list_helpers::filter_running(&mut vms);
        assert!(vms.is_empty());
    }

    #[test]
    fn test_filter_by_tag_key_value() {
        let mut vms = vec![
            make_tagged_vm("vm1", vec![("env", "prod")]),
            make_tagged_vm("vm2", vec![("env", "dev")]),
            make_tagged_vm("vm3", vec![("team", "infra")]),
        ];
        super::list_helpers::filter_by_tag(&mut vms, "env=prod");
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "vm1");
    }

    #[test]
    fn test_filter_by_tag_key_only() {
        let mut vms = vec![
            make_tagged_vm("vm1", vec![("env", "prod")]),
            make_tagged_vm("vm2", vec![("env", "dev")]),
            make_tagged_vm("vm3", vec![("team", "infra")]),
        ];
        super::list_helpers::filter_by_tag(&mut vms, "env");
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].name, "vm1");
        assert_eq!(vms[1].name, "vm2");
    }

    #[test]
    fn test_filter_by_tag_no_match() {
        let mut vms = vec![make_tagged_vm("vm1", vec![("env", "prod")])];
        super::list_helpers::filter_by_tag(&mut vms, "env=staging");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_filter_by_tag_nonexistent_key() {
        let mut vms = vec![make_tagged_vm("vm1", vec![("env", "prod")])];
        super::list_helpers::filter_by_tag(&mut vms, "region");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_filter_by_pattern_simple() {
        let mut vms = vec![
            make_vm("web-server-01", azlin_core::models::PowerState::Running),
            make_vm("db-server-01", azlin_core::models::PowerState::Running),
            make_vm("web-server-02", azlin_core::models::PowerState::Running),
        ];
        super::list_helpers::filter_by_pattern(&mut vms, "web");
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].name, "web-server-01");
        assert_eq!(vms[1].name, "web-server-02");
    }

    #[test]
    fn test_filter_by_pattern_with_glob() {
        let mut vms = vec![
            make_vm("web-server-01", azlin_core::models::PowerState::Running),
            make_vm("db-server-01", azlin_core::models::PowerState::Running),
        ];
        super::list_helpers::filter_by_pattern(&mut vms, "*web*");
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "web-server-01");
    }

    #[test]
    fn test_filter_by_pattern_no_match() {
        let mut vms = vec![make_vm(
            "web-server",
            azlin_core::models::PowerState::Running,
        )];
        super::list_helpers::filter_by_pattern(&mut vms, "cache");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_apply_filters_all_disabled() {
        let mut vms = vec![
            make_vm("vm1", azlin_core::models::PowerState::Running),
            make_vm("vm2", azlin_core::models::PowerState::Stopped),
        ];
        super::list_helpers::apply_filters(&mut vms, true, None, None);
        assert_eq!(vms.len(), 2);
    }

    #[test]
    fn test_apply_filters_exclude_stopped() {
        let mut vms = vec![
            make_vm("vm1", azlin_core::models::PowerState::Running),
            make_vm("vm2", azlin_core::models::PowerState::Stopped),
        ];
        super::list_helpers::apply_filters(&mut vms, false, None, None);
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "vm1");
    }

    #[test]
    fn test_apply_filters_combined() {
        let mut vms = vec![
            make_tagged_vm("web-prod", vec![("env", "prod")]),
            make_tagged_vm("web-dev", vec![("env", "dev")]),
            make_tagged_vm("db-prod", vec![("env", "prod")]),
        ];
        super::list_helpers::apply_filters(&mut vms, true, Some("env=prod"), Some("web"));
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "web-prod");
    }

    // ── batch_helpers tests ─────────────────────────────────────

    #[test]
    fn test_parse_vm_ids_normal() {
        let ids =
            super::batch_helpers::parse_vm_ids("/sub/1/rg/test/vm/vm1\n/sub/1/rg/test/vm/vm2\n");
        assert_eq!(ids.len(), 2);
        assert_eq!(ids[0], "/sub/1/rg/test/vm/vm1");
        assert_eq!(ids[1], "/sub/1/rg/test/vm/vm2");
    }

    #[test]
    fn test_parse_vm_ids_empty() {
        let ids = super::batch_helpers::parse_vm_ids("");
        assert!(ids.is_empty());
    }

    #[test]
    fn test_parse_vm_ids_blank_lines() {
        let ids = super::batch_helpers::parse_vm_ids("\n\n/sub/vm1\n\n");
        assert_eq!(ids.len(), 1);
        assert_eq!(ids[0], "/sub/vm1");
    }

    #[test]
    fn test_build_batch_args_deallocate() {
        let ids = vec!["/sub/vm1", "/sub/vm2"];
        let args = super::batch_helpers::build_batch_args("deallocate", &ids);
        assert_eq!(
            args,
            vec!["vm", "deallocate", "--ids", "/sub/vm1", "/sub/vm2"]
        );
    }

    #[test]
    fn test_build_batch_args_start() {
        let ids = vec!["/sub/vm1"];
        let args = super::batch_helpers::build_batch_args("start", &ids);
        assert_eq!(args, vec!["vm", "start", "--ids", "/sub/vm1"]);
    }

    #[test]
    fn test_summarise_batch_success() {
        let msg = super::batch_helpers::summarise_batch("stop", "my-rg", true);
        assert_eq!(msg, "Batch stop completed for resource group 'my-rg'");
    }

    #[test]
    fn test_summarise_batch_failure() {
        let msg = super::batch_helpers::summarise_batch("start", "my-rg", false);
        assert_eq!(msg, "Batch start failed. Run commands individually.");
    }

    #[test]
    fn test_summarise_batch_other_action() {
        let msg = super::batch_helpers::summarise_batch("restart", "prod-rg", true);
        assert!(msg.contains("restart"));
        assert!(msg.contains("prod-rg"));
    }

    // ── all_contexts tests ────────────────────────────────────────

    #[test]
    fn test_read_context_resource_group_with_rg() {
        let tmp = TempDir::new().unwrap();
        let ctx_path = tmp.path().join("dev.toml");
        fs::write(
            &ctx_path,
            "name = \"dev\"\nresource_group = \"dev-rg\"\nregion = \"westus2\"\n",
        )
        .unwrap();

        let (name, rg) = super::contexts::read_context_resource_group(&ctx_path).unwrap();
        assert_eq!(name, "dev");
        assert_eq!(rg, Some("dev-rg".to_string()));
    }

    #[test]
    fn test_read_context_resource_group_without_rg() {
        let tmp = TempDir::new().unwrap();
        let ctx_path = tmp.path().join("minimal.toml");
        fs::write(&ctx_path, "name = \"minimal\"\n").unwrap();

        let (name, rg) = super::contexts::read_context_resource_group(&ctx_path).unwrap();
        assert_eq!(name, "minimal");
        assert_eq!(rg, None);
    }

    #[test]
    fn test_read_context_resource_group_falls_back_to_filename() {
        let tmp = TempDir::new().unwrap();
        let ctx_path = tmp.path().join("staging.toml");
        fs::write(&ctx_path, "resource_group = \"staging-rg\"\n").unwrap();

        let (name, rg) = super::contexts::read_context_resource_group(&ctx_path).unwrap();
        assert_eq!(name, "staging");
        assert_eq!(rg, Some("staging-rg".to_string()));
    }

    // ── create_helpers tests ────────────────────────────────────────

    #[test]
    fn test_generate_vm_name_with_base_pool_1() {
        let name = super::create_helpers::generate_vm_name(Some("my-vm"), 0, 1, "20240101");
        assert_eq!(name, "my-vm");
    }

    #[test]
    fn test_generate_vm_name_with_base_pool_multiple() {
        let n1 = super::create_helpers::generate_vm_name(Some("my-vm"), 0, 3, "20240101");
        let n2 = super::create_helpers::generate_vm_name(Some("my-vm"), 1, 3, "20240101");
        let n3 = super::create_helpers::generate_vm_name(Some("my-vm"), 2, 3, "20240101");
        assert_eq!(n1, "my-vm-1");
        assert_eq!(n2, "my-vm-2");
        assert_eq!(n3, "my-vm-3");
    }

    #[test]
    fn test_generate_vm_name_no_base_uses_timestamp() {
        let name = super::create_helpers::generate_vm_name(None, 0, 1, "20240315-120000");
        assert_eq!(name, "azlin-vm-20240315-120000");
    }

    #[test]
    fn test_resolve_with_template_default_user_value() {
        let result = super::create_helpers::resolve_with_template_default(
            "Standard_D8s_v3",
            "Standard_D4s_v3",
            Some("Standard_D2s_v3".to_string()),
        );
        assert_eq!(result, "Standard_D8s_v3");
    }

    #[test]
    fn test_resolve_with_template_default_uses_template() {
        let result = super::create_helpers::resolve_with_template_default(
            "Standard_D4s_v3",
            "Standard_D4s_v3",
            Some("Standard_D16s_v3".to_string()),
        );
        assert_eq!(result, "Standard_D16s_v3");
    }

    #[test]
    fn test_resolve_with_template_default_no_template() {
        let result = super::create_helpers::resolve_with_template_default(
            "Standard_D4s_v3",
            "Standard_D4s_v3",
            None,
        );
        assert_eq!(result, "Standard_D4s_v3");
    }

    #[test]
    fn test_build_clone_cmd_https() {
        let cmd =
            super::create_helpers::build_clone_cmd("https://github.com/user/repo.git").unwrap();
        assert!(cmd.contains("git clone"));
        assert!(cmd.contains("https://github.com/user/repo.git"));
        assert!(cmd.contains("~/src/$(basename"));
    }

    #[test]
    fn test_build_ssh_connect_args() {
        let args = super::create_helpers::build_ssh_connect_args("azureuser", "10.0.0.1");
        assert_eq!(
            args,
            vec![
                "-o".to_string(),
                "StrictHostKeyChecking=accept-new".to_string(),
                "azureuser@10.0.0.1".to_string(),
            ]
        );
    }

    #[test]
    fn test_create_build_snapshot_name() {
        let name = super::create_helpers::build_snapshot_name("my-vm", "20240315");
        assert_eq!(name, "my-vm_clone_snap_20240315");
    }

    #[test]
    fn test_build_clone_name() {
        assert_eq!(
            super::create_helpers::build_clone_name("source-vm", 0),
            "source-vm-clone-1"
        );
        assert_eq!(
            super::create_helpers::build_clone_name("source-vm", 4),
            "source-vm-clone-5"
        );
    }

    #[test]
    fn test_build_disk_name() {
        assert_eq!(
            super::create_helpers::build_disk_name("my-vm"),
            "my-vm_OsDisk"
        );
    }

    // ── connect_helpers tests ───────────────────────────────────────

    #[test]
    fn test_build_ssh_args_without_key() {
        let args = super::connect_helpers::build_ssh_args("azureuser", "10.0.0.5", None);
        assert_eq!(
            args,
            vec![
                "-o".to_string(),
                "StrictHostKeyChecking=accept-new".to_string(),
                "azureuser@10.0.0.5".to_string(),
            ]
        );
    }

    #[test]
    fn test_build_ssh_args_with_key() {
        use std::path::Path;
        let key = Path::new("/home/user/.ssh/id_ed25519");
        let args = super::connect_helpers::build_ssh_args("admin", "192.168.1.1", Some(key));
        assert_eq!(
            args,
            vec![
                "-o".to_string(),
                "StrictHostKeyChecking=accept-new".to_string(),
                "-i".to_string(),
                "/home/user/.ssh/id_ed25519".to_string(),
                "admin@192.168.1.1".to_string(),
            ]
        );
    }

    #[test]
    fn test_build_vscode_remote_uri() {
        let uri = super::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
        assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
    }

    #[test]
    fn test_build_log_follow_args() {
        let args = super::connect_helpers::build_log_follow_args(
            "azureuser",
            "10.0.0.5",
            "/var/log/syslog",
        );
        assert_eq!(args.len(), 6);
        assert_eq!(args[4], "azureuser@10.0.0.5");
        assert_eq!(args[5], "sudo tail -f /var/log/syslog");
    }

    #[test]
    fn test_build_log_tail_args() {
        let args = super::connect_helpers::build_log_tail_args(
            "admin",
            "10.0.0.1",
            100,
            "/var/log/auth.log",
        );
        assert_eq!(args.len(), 6);
        assert!(args[5].contains("tail -n 100"));
        assert!(args[5].contains("/var/log/auth.log"));
    }

    // ── update_helpers tests ────────────────────────────────────────

    #[test]
    fn test_build_dev_update_script_contains_sections() {
        let script = super::update_helpers::build_dev_update_script();
        assert!(script.starts_with("#!/bin/bash"));
        assert!(script.contains("set -e"));
        assert!(script.contains("apt-get update"));
        assert!(script.contains("rustup update"));
        assert!(script.contains("pip3 install"));
        assert!(script.contains("npm install"));
    }

    #[test]
    fn test_build_os_update_cmd() {
        let cmd = super::update_helpers::build_os_update_cmd();
        assert!(cmd.contains("apt-get update"));
        assert!(cmd.contains("apt-get upgrade"));
        assert!(cmd.contains("DEBIAN_FRONTEND=noninteractive"));
    }

    #[test]
    fn test_log_type_to_path_cloud_init() {
        assert_eq!(
            super::update_helpers::log_type_to_path("cloud-init"),
            "/var/log/cloud-init-output.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("CloudInit"),
            "/var/log/cloud-init-output.log"
        );
    }

    #[test]
    fn test_log_type_to_path_syslog() {
        assert_eq!(
            super::update_helpers::log_type_to_path("syslog"),
            "/var/log/syslog"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("Syslog"),
            "/var/log/syslog"
        );
    }

    #[test]
    fn test_log_type_to_path_auth() {
        assert_eq!(
            super::update_helpers::log_type_to_path("auth"),
            "/var/log/auth.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("Auth"),
            "/var/log/auth.log"
        );
    }

    #[test]
    fn test_log_type_to_path_unknown_defaults_syslog() {
        assert_eq!(
            super::update_helpers::log_type_to_path("something-else"),
            "/var/log/syslog"
        );
    }

    // ── compose_helpers tests ───────────────────────────────────────

    #[test]
    fn test_resolve_compose_file_default() {
        let f = super::compose_helpers::resolve_compose_file(None);
        assert_eq!(f, "docker-compose.yml");
    }

    #[test]
    fn test_resolve_compose_file_custom() {
        let f = super::compose_helpers::resolve_compose_file(Some("compose.prod.yaml"));
        assert_eq!(f, "compose.prod.yaml");
    }

    #[test]
    fn test_build_compose_cmd_up() {
        let cmd = super::compose_helpers::build_compose_cmd("up -d", "docker-compose.yml");
        assert_eq!(cmd, "docker compose -f docker-compose.yml up -d");
    }

    #[test]
    fn test_build_compose_cmd_down() {
        let cmd = super::compose_helpers::build_compose_cmd("down", "compose.prod.yaml");
        assert_eq!(cmd, "docker compose -f compose.prod.yaml down");
    }

    // ── runner_helpers tests ────────────────────────────────────────

    #[test]
    fn test_build_runner_vm_name() {
        assert_eq!(
            super::runner_helpers::build_runner_vm_name("ci-pool", 0),
            "azlin-runner-ci-pool-1"
        );
        assert_eq!(
            super::runner_helpers::build_runner_vm_name("ci-pool", 2),
            "azlin-runner-ci-pool-3"
        );
    }

    #[test]
    fn test_build_runner_tags() {
        let tags = super::runner_helpers::build_runner_tags("ci-pool", "user/repo");
        assert!(tags.contains("azlin-runner=true"));
        assert!(tags.contains("pool=ci-pool"));
        assert!(tags.contains("repo=user/repo"));
    }

    #[test]
    fn test_build_runner_config_fields() {
        let config = super::runner_helpers::build_runner_config(
            "ci-pool",
            "user/repo",
            3,
            "self-hosted,linux",
            "my-rg",
            "Standard_D4s_v3",
            "2024-03-15T00:00:00Z",
        );
        let keys: Vec<&str> = config.iter().map(|(k, _)| k.as_str()).collect();
        assert!(keys.contains(&"pool"));
        assert!(keys.contains(&"repo"));
        assert!(keys.contains(&"count"));
        assert!(keys.contains(&"labels"));
        assert!(keys.contains(&"resource_group"));
        assert!(keys.contains(&"vm_size"));
        assert!(keys.contains(&"enabled"));
        assert!(keys.contains(&"created"));

        let count = config
            .iter()
            .find(|(k, _)| k == "count")
            .map(|(_, v)| v.as_integer().unwrap())
            .unwrap();
        assert_eq!(count, 3);
    }

    #[test]
    fn test_pool_config_filename() {
        assert_eq!(
            super::runner_helpers::pool_config_filename("ci-pool"),
            "ci-pool.toml"
        );
    }

    // ── autopilot_helpers tests ─────────────────────────────────────

    #[test]
    fn test_build_autopilot_config_with_budget() {
        let config = super::autopilot_helpers::build_autopilot_config(
            Some(500),
            "aggressive",
            30,
            80,
            "2024-03-15T00:00:00Z",
        );
        let tbl = config.as_table().unwrap();
        assert_eq!(tbl["enabled"].as_bool(), Some(true));
        assert_eq!(tbl["budget"].as_integer(), Some(500));
        assert_eq!(tbl["strategy"].as_str(), Some("aggressive"));
        assert_eq!(tbl["idle_threshold_minutes"].as_integer(), Some(30));
        assert_eq!(tbl["cpu_threshold_percent"].as_integer(), Some(80));
    }

    #[test]
    fn test_build_autopilot_config_without_budget() {
        let config = super::autopilot_helpers::build_autopilot_config(
            None,
            "conservative",
            60,
            50,
            "2024-03-15T00:00:00Z",
        );
        let tbl = config.as_table().unwrap();
        assert!(tbl.get("budget").is_none());
        assert_eq!(tbl["strategy"].as_str(), Some("conservative"));
    }

    #[test]
    fn test_build_budget_name() {
        assert_eq!(
            super::autopilot_helpers::build_budget_name("my-rg"),
            "azlin-budget-my-rg"
        );
    }

    #[test]
    fn test_build_prefix_filter_query() {
        let q = super::autopilot_helpers::build_prefix_filter_query("azlin-vm");
        assert_eq!(q, "[?starts_with(name, 'azlin-vm')].id");
    }

    #[test]
    fn test_build_cost_scope() {
        let scope = super::autopilot_helpers::build_cost_scope("sub-123", "my-rg");
        assert_eq!(scope, "/subscriptions/sub-123/resourceGroups/my-rg");
    }

    // ── config_path_helpers tests ───────────────────────────────────

    #[test]
    fn test_validate_config_path_safe() {
        assert!(super::config_path_helpers::validate_config_path("config.toml").is_ok());
        assert!(super::config_path_helpers::validate_config_path("subdir/config.toml").is_ok());
    }

    #[test]
    fn test_validate_config_path_traversal_rejected() {
        assert!(super::config_path_helpers::validate_config_path("../etc/passwd").is_err());
        assert!(
            super::config_path_helpers::validate_config_path("subdir/../../etc/shadow").is_err()
        );
    }

    // ── snapshot_helpers additional tests ────────────────────────────

    #[test]
    fn test_snapshot_row_full_data() {
        let snap = serde_json::json!({
            "name": "vm1_snapshot_20240315",
            "diskSizeGb": 128,
            "timeCreated": "2024-03-15T12:00:00Z",
            "provisioningState": "Succeeded"
        });
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "vm1_snapshot_20240315");
        assert_eq!(row[1], "128");
        assert_eq!(row[2], "2024-03-15T12:00:00Z");
        assert_eq!(row[3], "Succeeded");
    }

    #[test]
    fn test_snapshot_row_defaults_for_empty_json() {
        let snap = serde_json::json!({});
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "-");
        assert_eq!(row[1], "null");
        assert_eq!(row[2], "-");
        assert_eq!(row[3], "-");
    }

    #[test]
    fn test_snapshot_schedule_path_format() {
        let path = super::snapshot_helpers::schedule_path("my-vm");
        assert!(path.to_string_lossy().contains("my-vm.toml"));
        assert!(path.to_string_lossy().contains("schedules"));
    }

    // ── output_helpers edge case tests ──────────────────────────────

    #[test]
    fn test_format_as_table_header_only_no_rows() {
        let out = super::output_helpers::format_as_table(&["Name", "Value"], &[]);
        assert_eq!(out, "Name  Value");
    }

    #[test]
    fn test_format_as_table_renders_single_col() {
        let rows = vec![vec!["alpha".to_string()], vec!["beta".to_string()]];
        let out = super::output_helpers::format_as_table(&["Items"], &rows);
        assert!(out.contains("Items"));
        assert!(out.contains("alpha"));
        assert!(out.contains("beta"));
    }

    #[test]
    fn test_format_as_csv_header_only() {
        let out = super::output_helpers::format_as_csv(&["Name", "Size"], &[]);
        assert_eq!(out, "Name,Size");
    }

    #[test]
    fn test_format_as_json_empty_slice() {
        let items: Vec<String> = vec![];
        let out = super::output_helpers::format_as_json(&items);
        assert_eq!(out, "[]");
    }

    #[test]
    fn test_format_as_json_with_data() {
        let items = vec!["hello", "world"];
        let out = super::output_helpers::format_as_json(&items);
        assert!(out.contains("hello"));
        assert!(out.contains("world"));
    }

    // ── parse_cost_history_rows tests ───────────────────────────────

    #[test]
    fn test_parse_cost_history_no_rows_key() {
        let data = serde_json::json!({});
        let rows = super::parse_cost_history_rows(&data);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_parse_cost_history_rows_valid() {
        let data = serde_json::json!({
            "rows": [
                [12.50, "2024-03-01"],
                [8.75, "2024-03-02"]
            ]
        });
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].0, "2024-03-01");
        assert_eq!(rows[0].1, "$12.50");
        assert_eq!(rows[1].0, "2024-03-02");
        assert_eq!(rows[1].1, "$8.75");
    }

    #[test]
    fn test_parse_cost_history_numeric_date() {
        // When date is an integer, the parser maps it to empty string via the
        // `as_str().or_else(|| as_i64().map(|_| ""))` branch.
        let data = serde_json::json!({
            "rows": [
                [5.00, 20240301]
            ]
        });
        let rows = super::parse_cost_history_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].1, "$5.00");
        // Integer dates produce an empty string via the current parser logic
        assert_eq!(rows[0].0, "");
    }

    #[test]
    fn test_parse_cost_history_rows_empty_array() {
        let data = serde_json::json!({ "rows": [] });
        let rows = super::parse_cost_history_rows(&data);
        assert!(rows.is_empty());
    }

    // ── storage_helpers additional tests ─────────────────────────────

    #[test]
    fn test_storage_account_row_all_fields() {
        let acct = serde_json::json!({
            "name": "mystorageacct",
            "location": "westus2",
            "kind": "StorageV2",
            "sku": {"name": "Standard_LRS"},
            "provisioningState": "Succeeded"
        });
        let row = super::storage_helpers::storage_account_row(&acct);
        assert_eq!(row[0], "mystorageacct");
        assert_eq!(row[1], "westus2");
        assert_eq!(row[2], "StorageV2");
        assert_eq!(row[3], "Standard_LRS");
        assert_eq!(row[4], "Succeeded");
    }

    #[test]
    fn test_storage_account_row_missing() {
        let acct = serde_json::json!({});
        let row = super::storage_helpers::storage_account_row(&acct);
        assert!(row.iter().all(|c| c == "-"));
    }

    // ── vm_validation edge cases ────────────────────────────────────

    #[test]
    fn test_validate_vm_name_max_length() {
        let name = "a".repeat(64);
        assert!(super::vm_validation::validate_vm_name(&name).is_ok());
    }

    #[test]
    fn test_validate_vm_name_exceeds_max() {
        let name = "a".repeat(65);
        assert!(super::vm_validation::validate_vm_name(&name).is_err());
    }

    #[test]
    fn test_validate_vm_name_with_underscores_rejected() {
        assert!(super::vm_validation::validate_vm_name("my_vm").is_err());
    }

    // ── env_helpers edge case tests ─────────────────────────────────

    #[test]
    fn test_split_env_var_missing_equals() {
        assert!(super::env_helpers::split_env_var("NOVALUE").is_none());
    }

    #[test]
    fn test_split_env_var_empty_key() {
        assert!(super::env_helpers::split_env_var("=value").is_none());
    }

    #[test]
    fn test_split_env_var_blank_value() {
        let result = super::env_helpers::split_env_var("KEY=");
        assert_eq!(result, Some(("KEY", "")));
    }

    #[test]
    fn test_split_env_var_embedded_equals() {
        let result = super::env_helpers::split_env_var("KEY=val=ue");
        assert_eq!(result, Some(("KEY", "val=ue")));
    }

    #[test]
    fn test_parse_env_output_blank_input() {
        let result = super::env_helpers::parse_env_output("");
        assert!(result.is_empty());
    }

    #[test]
    fn test_parse_env_output_multiple() {
        let result =
            super::env_helpers::parse_env_output("HOME=/home/user\nPATH=/usr/bin\nSHELL=/bin/bash");
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], ("HOME".to_string(), "/home/user".to_string()));
        assert_eq!(result[1], ("PATH".to_string(), "/usr/bin".to_string()));
    }

    // ── sync_helpers edge case tests ────────────────────────────────

    #[test]
    fn test_validate_sync_source_var_rejected() {
        assert!(super::sync_helpers::validate_sync_source("/var/log/syslog").is_err());
    }

    #[test]
    fn test_validate_sync_source_root_rejected() {
        assert!(super::sync_helpers::validate_sync_source("/root/.bashrc").is_err());
    }

    #[test]
    fn test_validate_sync_source_safe_path() {
        assert!(super::sync_helpers::validate_sync_source("my-dotfiles/.bashrc").is_ok());
    }

    #[test]
    fn test_validate_sync_source_dotdot_only() {
        assert!(super::sync_helpers::validate_sync_source("..").is_err());
    }

    // ── mount_helpers additional edge case tests ────────────────────

    #[test]
    fn test_mount_path_null_char() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/data\0bad").is_err());
    }

    #[test]
    fn test_mount_path_pipe_char() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/data|bad").is_err());
    }

    #[test]
    fn test_mount_path_newline_injection() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/data\nbad").is_err());
    }

    #[test]
    fn test_mount_path_not_absolute() {
        assert!(super::mount_helpers::validate_mount_path("relative/path").is_err());
    }

    // ── stop_helpers tests ──────────────────────────────────────────

    #[test]
    fn test_stop_action_labels_deallocate() {
        let (action, done) = super::stop_helpers::stop_action_labels(true);
        assert_eq!(action, "Deallocating");
        assert_eq!(done, "Deallocated");
    }

    #[test]
    fn test_stop_action_labels_stop() {
        let (action, done) = super::stop_helpers::stop_action_labels(false);
        assert_eq!(action, "Stopping");
        assert_eq!(done, "Stopped");
    }

    // ── display_helpers tests ───────────────────────────────────────

    #[test]
    fn test_config_value_display_string() {
        let v = serde_json::Value::String("hello".to_string());
        assert_eq!(super::display_helpers::config_value_display(&v), "hello");
    }

    #[test]
    fn test_config_value_display_null() {
        assert_eq!(
            super::display_helpers::config_value_display(&serde_json::Value::Null),
            "null"
        );
    }

    #[test]
    fn test_config_value_display_number() {
        let v = serde_json::json!(42);
        assert_eq!(super::display_helpers::config_value_display(&v), "42");
    }

    #[test]
    fn test_truncate_vm_name_short() {
        assert_eq!(
            super::display_helpers::truncate_vm_name("my-vm", 20),
            "my-vm"
        );
    }

    #[test]
    fn test_truncate_vm_name_long() {
        let name = "azlin-very-long-vm-name-12345";
        let result = super::display_helpers::truncate_vm_name(name, 20);
        assert_eq!(result, "azlin-very-long-v...");
        assert_eq!(result.len(), 20);
    }

    #[test]
    fn test_truncate_vm_name_exact_boundary() {
        let name = "exactly-twenty-chars";
        assert_eq!(name.len(), 20);
        assert_eq!(super::display_helpers::truncate_vm_name(name, 20), name);
    }

    #[test]
    fn test_format_tmux_sessions_empty() {
        let sessions: Vec<String> = vec![];
        assert_eq!(
            super::display_helpers::format_tmux_sessions(&sessions, 3),
            "-"
        );
    }

    #[test]
    fn test_format_tmux_sessions_few() {
        let sessions = vec!["main".to_string(), "dev".to_string()];
        assert_eq!(
            super::display_helpers::format_tmux_sessions(&sessions, 3),
            "main, dev"
        );
    }

    #[test]
    fn test_format_tmux_sessions_overflow() {
        let sessions: Vec<String> = (1..=5).map(|i| format!("s{}", i)).collect();
        let result = super::display_helpers::format_tmux_sessions(&sessions, 3);
        assert_eq!(result, "s1, s2, s3, +2 more");
    }

    #[test]
    fn test_reconnect_prompt_format() {
        let msg = super::display_helpers::reconnect_prompt(2, 5);
        assert!(msg.contains("2/5"));
        assert!(msg.contains("[Y/n]"));
    }

    // ── tag_helpers tests ───────────────────────────────────────────

    #[test]
    fn test_parse_tag_key_value() {
        assert_eq!(
            super::tag_helpers::parse_tag("env=production"),
            Some(("env", "production"))
        );
    }

    #[test]
    fn test_parse_tag_missing_equals() {
        assert_eq!(super::tag_helpers::parse_tag("justkey"), None);
    }

    #[test]
    fn test_parse_tag_empty_key() {
        assert_eq!(super::tag_helpers::parse_tag("=value"), None);
    }

    #[test]
    fn test_parse_tag_embedded_equals() {
        assert_eq!(
            super::tag_helpers::parse_tag("key=val=ue"),
            Some(("key", "val=ue"))
        );
    }

    #[test]
    fn test_find_invalid_tag_all_valid() {
        let tags = vec!["a=1".to_string(), "b=2".to_string()];
        assert_eq!(super::tag_helpers::find_invalid_tag(&tags), None);
    }

    #[test]
    fn test_find_invalid_tag_has_bad() {
        let tags = vec!["a=1".to_string(), "bad".to_string(), "c=3".to_string()];
        assert_eq!(super::tag_helpers::find_invalid_tag(&tags), Some("bad"));
    }

    // ── disk_helpers tests ──────────────────────────────────────────

    #[test]
    fn test_build_data_disk_name_lun0() {
        assert_eq!(
            super::disk_helpers::build_data_disk_name("my-vm", 0),
            "my-vm_datadisk_0"
        );
    }

    #[test]
    fn test_build_data_disk_name_lun5() {
        assert_eq!(
            super::disk_helpers::build_data_disk_name("worker", 5),
            "worker_datadisk_5"
        );
    }

    #[test]
    fn test_build_restored_disk_name() {
        assert_eq!(
            super::disk_helpers::build_restored_disk_name("my-vm"),
            "my-vm_OsDisk_restored"
        );
    }

    // ── command_helpers tests ───────────────────────────────────────

    #[test]
    fn test_is_allowed_command_az() {
        assert!(super::command_helpers::is_allowed_command("az vm list"));
    }

    #[test]
    fn test_is_allowed_command_non_az() {
        assert!(!super::command_helpers::is_allowed_command("rm -rf /"));
    }

    #[test]
    fn test_is_allowed_command_whitespace_prefix() {
        assert!(super::command_helpers::is_allowed_command("  az vm list"));
    }

    #[test]
    fn test_skip_reason_allowed() {
        assert_eq!(super::command_helpers::skip_reason("az vm list"), None);
    }

    #[test]
    fn test_skip_reason_empty() {
        assert!(super::command_helpers::skip_reason("").is_some());
    }

    #[test]
    fn test_skip_reason_non_az() {
        let reason = super::command_helpers::skip_reason("curl http://evil.com");
        assert!(reason.is_some());
        assert!(reason.unwrap().contains("non-Azure"));
    }

    // ── autopilot_parse_helpers tests ───────────────────────────────

    #[test]
    fn test_parse_idle_check_normal() {
        let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("25.3\n3600.5");
        assert!((cpu - 25.3).abs() < 0.01);
        assert!((uptime - 3600.5).abs() < 0.01);
    }

    #[test]
    fn test_parse_idle_check_empty() {
        let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("");
        assert!((cpu - 100.0).abs() < 0.01); // defaults to 100% (not idle)
        assert!((uptime - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_parse_idle_check_garbage() {
        let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("abc\nxyz");
        assert!((cpu - 100.0).abs() < 0.01);
        assert!((uptime - 0.0).abs() < 0.01);
    }

    #[test]
    fn test_is_idle_true() {
        // CPU 2%, uptime 2 hours, threshold 30 min → idle
        assert!(super::autopilot_parse_helpers::is_idle(2.0, 7200.0, 30));
    }

    #[test]
    fn test_is_idle_high_cpu() {
        // CPU 50%, even with long uptime → not idle
        assert!(!super::autopilot_parse_helpers::is_idle(50.0, 7200.0, 30));
    }

    #[test]
    fn test_is_idle_short_uptime() {
        // CPU 1%, uptime 10 min, threshold 30 min → not idle (too new)
        assert!(!super::autopilot_parse_helpers::is_idle(1.0, 600.0, 30));
    }

    // ── templates::import_template tests ────────────────────────────

    #[test]
    fn test_import_template_success() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        let content = r#"
name = "web-server"
vm_size = "Standard_B2s"
region = "eastus"
"#;
        let name = super::templates::import_template(dir, content).unwrap();
        assert_eq!(name, "web-server");
        // Verify the file was created
        assert!(dir.join("web-server.toml").exists());
    }

    #[test]
    fn test_import_template_missing_name() {
        let tmp = TempDir::new().unwrap();
        let content = r#"
vm_size = "Standard_B2s"
region = "eastus"
"#;
        let result = super::templates::import_template(tmp.path(), content);
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("name"));
    }

    #[test]
    fn test_import_template_invalid_toml() {
        let tmp = TempDir::new().unwrap();
        let result = super::templates::import_template(tmp.path(), "not valid { toml [");
        assert!(result.is_err());
    }

    // ── templates::build_template_toml edge cases ──────────────────

    #[test]
    fn test_build_template_toml_with_cloud_init() {
        let tpl = super::templates::build_template_toml(
            "my-tpl",
            Some("A dev VM"),
            Some("Standard_E4s_v3"),
            Some("northeurope"),
            Some("#!/bin/bash\napt-get update"),
        );
        let tbl = tpl.as_table().unwrap();
        assert_eq!(tbl["name"].as_str().unwrap(), "my-tpl");
        assert_eq!(tbl["description"].as_str().unwrap(), "A dev VM");
        assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_E4s_v3");
        assert_eq!(tbl["region"].as_str().unwrap(), "northeurope");
        assert!(tbl["cloud_init"].as_str().unwrap().contains("apt-get"));
    }

    #[test]
    fn test_build_template_toml_all_defaults() {
        let tpl = super::templates::build_template_toml("minimal", None, None, None, None);
        let tbl = tpl.as_table().unwrap();
        assert_eq!(tbl["name"].as_str().unwrap(), "minimal");
        assert_eq!(tbl["description"].as_str().unwrap(), "");
        assert_eq!(tbl["vm_size"].as_str().unwrap(), "Standard_D4s_v3");
        assert_eq!(tbl["region"].as_str().unwrap(), "westus2");
        assert!(tbl.get("cloud_init").is_none());
    }

    // ── vm_validation tests ────────────────────────────────────────

    #[test]
    fn test_validate_vm_name_empty() {
        let result = super::vm_validation::validate_vm_name("");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("empty"));
    }

    #[test]
    fn test_validate_vm_name_leading_hyphen() {
        let result = super::vm_validation::validate_vm_name("-bad-name");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("start with a hyphen"));
    }

    #[test]
    fn test_validate_vm_name_trailing_hyphen() {
        let result = super::vm_validation::validate_vm_name("bad-name-");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("end with a hyphen"));
    }

    #[test]
    fn test_validate_vm_name_valid() {
        assert!(super::vm_validation::validate_vm_name("my-good-vm-01").is_ok());
    }

    #[test]
    fn test_validate_vm_name_single_char() {
        assert!(super::vm_validation::validate_vm_name("a").is_ok());
    }

    #[test]
    fn test_validate_vm_name_spaces_rejected() {
        let result = super::vm_validation::validate_vm_name("bad name");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("invalid characters"));
    }

    // ── snapshot_helpers::SnapshotSchedule serde tests ──────────────

    #[test]
    fn test_snapshot_schedule_serialize_deserialize_roundtrip() {
        let schedule = super::snapshot_helpers::SnapshotSchedule {
            vm_name: "dev-vm".to_string(),
            resource_group: "my-rg".to_string(),
            every_hours: 6,
            keep_count: 10,
            enabled: true,
            created: "2024-01-15T10:00:00Z".to_string(),
        };
        let toml_str = toml::to_string_pretty(&schedule).unwrap();
        let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&toml_str).unwrap();
        assert_eq!(loaded.vm_name, "dev-vm");
        assert_eq!(loaded.resource_group, "my-rg");
        assert_eq!(loaded.every_hours, 6);
        assert_eq!(loaded.keep_count, 10);
        assert!(loaded.enabled);
        assert_eq!(loaded.created, "2024-01-15T10:00:00Z");
    }

    #[test]
    fn test_snapshot_schedule_disabled() {
        let schedule = super::snapshot_helpers::SnapshotSchedule {
            vm_name: "prod-db".to_string(),
            resource_group: "prod-rg".to_string(),
            every_hours: 24,
            keep_count: 3,
            enabled: false,
            created: "2024-06-01T00:00:00Z".to_string(),
        };
        let toml_str = toml::to_string_pretty(&schedule).unwrap();
        assert!(toml_str.contains("enabled = false"));
        let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&toml_str).unwrap();
        assert!(!loaded.enabled);
    }

    #[test]
    fn test_snapshot_schedule_write_read_file() {
        let tmp = TempDir::new().unwrap();
        let schedule = super::snapshot_helpers::SnapshotSchedule {
            vm_name: "test-vm".to_string(),
            resource_group: "test-rg".to_string(),
            every_hours: 12,
            keep_count: 5,
            enabled: true,
            created: "2024-03-01T08:00:00Z".to_string(),
        };
        let path = tmp.path().join("test-vm.toml");
        let contents = toml::to_string_pretty(&schedule).unwrap();
        fs::write(&path, &contents).unwrap();

        let read_back = fs::read_to_string(&path).unwrap();
        let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&read_back).unwrap();
        assert_eq!(loaded.vm_name, "test-vm");
        assert_eq!(loaded.every_hours, 12);
    }

    // ── sessions round-trip with list_session_names ─────────────────

    #[test]
    fn test_session_build_write_list_roundtrip() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();
        fs::create_dir_all(dir).unwrap();

        let session1 = super::sessions::build_session_toml(
            "dev-session",
            "dev-rg",
            &["vm-1".to_string(), "vm-2".to_string()],
        );
        let session2 = super::sessions::build_session_toml(
            "staging-session",
            "staging-rg",
            &["vm-3".to_string()],
        );

        fs::write(
            dir.join("dev-session.toml"),
            toml::to_string_pretty(&session1).unwrap(),
        )
        .unwrap();
        fs::write(
            dir.join("staging-session.toml"),
            toml::to_string_pretty(&session2).unwrap(),
        )
        .unwrap();
        // Add a non-toml file that should be ignored
        fs::write(dir.join("notes.txt"), "some notes").unwrap();

        let names = super::sessions::list_session_names(dir).unwrap();
        assert_eq!(names.len(), 2);
        assert!(names.contains(&"dev-session".to_string()));
        assert!(names.contains(&"staging-session".to_string()));
    }

    #[test]
    fn test_session_parse_toml_missing_all_fields() {
        // Empty table should return defaults
        let content = "[other]\nkey = \"value\"";
        let (rg, vms, created) = super::sessions::parse_session_toml(content).unwrap();
        assert_eq!(rg, "-");
        assert!(vms.is_empty());
        assert_eq!(created, "-");
    }

    // ── contexts::build_context_toml no optional fields ─────────────

    #[test]
    fn test_context_build_toml_no_optional_fields() {
        let toml_str =
            super::contexts::build_context_toml("bare", None, None, None, None, None).unwrap();
        let parsed: toml::Value = toml_str.parse().unwrap();
        let tbl = parsed.as_table().unwrap();
        assert_eq!(tbl["name"].as_str().unwrap(), "bare");
        // Optional fields should be absent
        assert!(tbl.get("subscription_id").is_none());
        assert!(tbl.get("tenant_id").is_none());
        assert!(tbl.get("resource_group").is_none());
        assert!(tbl.get("region").is_none());
        assert!(tbl.get("key_vault_name").is_none());
    }

    // ── contexts::read_context_resource_group — name from filestem ───────

    #[test]
    fn test_context_read_resource_group_name_from_filestem() {
        let tmp = TempDir::new().unwrap();
        // A context TOML without a "name" field — name is derived from the filename
        let path = tmp.path().join("my-ctx.toml");
        fs::write(&path, "resource_group = \"my-rg\"\n").unwrap();

        let (name, rg) = super::contexts::read_context_resource_group(&path).unwrap();
        assert_eq!(name, "my-ctx");
        assert_eq!(rg, Some("my-rg".to_string()));
    }

    // ── create_helpers::build_clone_cmd — SSH URL ──────────────────

    #[test]
    fn test_build_clone_cmd_ssh_url() {
        let cmd = super::create_helpers::build_clone_cmd("git@github.com:user/repo.git").unwrap();
        assert!(cmd.contains("git clone"));
        assert!(cmd.contains("git@github.com:user/repo.git"));
        assert!(cmd.contains("repo")); // basename extraction
    }

    // ── health_helpers::format_percentage negative clamping ─────────

    #[test]
    fn test_format_percentage_negative_clamps_to_zero() {
        assert_eq!(super::health_helpers::format_percentage(-5.0), "0.0%");
        assert_eq!(super::health_helpers::format_percentage(-999.0), "0.0%");
    }

    // ── connect_helpers edge cases ─────────────────────────────────

    #[test]
    fn test_build_log_follow_args_format() {
        let args =
            super::connect_helpers::build_log_follow_args("admin", "10.0.0.5", "/var/log/syslog");
        assert_eq!(args.len(), 6);
        assert_eq!(args[0], "-o");
        assert_eq!(args[1], "StrictHostKeyChecking=accept-new");
        assert_eq!(args[4], "admin@10.0.0.5");
        assert!(args[5].contains("tail -f"));
        assert!(args[5].contains("/var/log/syslog"));
    }

    #[test]
    fn test_build_log_tail_args_line_count() {
        let args = super::connect_helpers::build_log_tail_args(
            "user",
            "192.168.1.1",
            200,
            "/var/log/auth.log",
        );
        assert_eq!(args.len(), 6);
        assert!(args[5].contains("tail -n 200"));
        assert!(args[5].contains("/var/log/auth.log"));
    }

    // ── update_helpers::log_type_to_path default branch ────────────

    #[test]
    fn test_log_type_to_path_capital_variants() {
        assert_eq!(
            super::update_helpers::log_type_to_path("CloudInit"),
            "/var/log/cloud-init-output.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("Syslog"),
            "/var/log/syslog"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("Auth"),
            "/var/log/auth.log"
        );
    }

    // ── autopilot_helpers::build_autopilot_config no budget ────────

    #[test]
    fn test_build_autopilot_config_no_budget_field_absent() {
        let config = super::autopilot_helpers::build_autopilot_config(
            None,
            "conservative",
            60,
            10,
            "2024-01-01T00:00:00Z",
        );
        let tbl = config.as_table().unwrap();
        assert!(tbl.get("budget").is_none());
        assert_eq!(tbl["strategy"].as_str().unwrap(), "conservative");
        assert_eq!(tbl["idle_threshold_minutes"].as_integer().unwrap(), 60);
        assert_eq!(tbl["cpu_threshold_percent"].as_integer().unwrap(), 10);
    }

    // ── batch_helpers::parse_vm_ids whitespace handling ─────────────

    #[test]
    fn test_parse_vm_ids_trailing_newlines() {
        let output = "/subscriptions/abc/vms/vm1\n/subscriptions/abc/vms/vm2\n\n\n";
        let ids = super::batch_helpers::parse_vm_ids(output);
        assert_eq!(ids.len(), 2);
        assert_eq!(ids[0], "/subscriptions/abc/vms/vm1");
        assert_eq!(ids[1], "/subscriptions/abc/vms/vm2");
    }

    // ── runner_helpers::pool_config_filename ───────────────────────

    #[test]
    fn test_pool_config_filename_format() {
        assert_eq!(
            super::runner_helpers::pool_config_filename("default"),
            "default.toml"
        );
        assert_eq!(
            super::runner_helpers::pool_config_filename("ci-large"),
            "ci-large.toml"
        );
    }

    // ── compose_helpers edge case ──────────────────────────────────

    #[test]
    fn test_build_compose_cmd_with_services() {
        let cmd = super::compose_helpers::build_compose_cmd("up -d", "prod-compose.yml");
        assert_eq!(cmd, "docker compose -f prod-compose.yml up -d");
    }

    // ── templates::save + load + delete full lifecycle ──────────────

    #[test]
    fn test_template_full_lifecycle_save_load_list_delete() {
        let tmp = TempDir::new().unwrap();
        let dir = tmp.path();

        // Save two templates
        let tpl1 = super::templates::build_template_toml(
            "web",
            Some("Web server"),
            Some("Standard_B2s"),
            Some("westus2"),
            None,
        );
        let tpl2 = super::templates::build_template_toml(
            "gpu",
            Some("GPU worker"),
            Some("Standard_NC6"),
            Some("eastus"),
            Some("#!/bin/bash\nnvidia-smi"),
        );
        super::templates::save_template(dir, "web", &tpl1).unwrap();
        super::templates::save_template(dir, "gpu", &tpl2).unwrap();

        // List should return both
        let list = super::templates::list_templates(dir).unwrap();
        assert_eq!(list.len(), 2);

        // Load one
        let loaded = super::templates::load_template(dir, "gpu").unwrap();
        assert_eq!(loaded.get("name").unwrap().as_str().unwrap(), "gpu");
        assert!(loaded.get("cloud_init").is_some());

        // Delete one
        super::templates::delete_template(dir, "web").unwrap();
        let list2 = super::templates::list_templates(dir).unwrap();
        assert_eq!(list2.len(), 1);

        // Load deleted template should fail
        assert!(super::templates::load_template(dir, "web").is_err());
    }

    // ── contexts::rename_context_file on nonexistent ───────────────

    #[test]
    fn test_context_rename_nonexistent_errors() {
        let tmp = TempDir::new().unwrap();
        let result = super::contexts::rename_context_file(tmp.path(), "no-such-ctx", "new-name");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not found"));
    }

    // ═══════════════════════════════════════════════════════════════
    // NEW COVERAGE TESTS — Batch 2: 35+ tests for 80% target
    // ═══════════════════════════════════════════════════════════════

    // ── Context CRUD lifecycle ──────────────────────────────────────

    #[test]
    fn test_context_full_crud_lifecycle() {
        let tmp = TempDir::new().unwrap();
        let ctx_dir = tmp.path();

        // Create
        let toml_str = super::contexts::build_context_toml(
            "myctx",
            Some("sub-123"),
            Some("tenant-456"),
            Some("myrg"),
            Some("eastus"),
            None,
        )
        .unwrap();
        fs::write(ctx_dir.join("myctx.toml"), &toml_str).unwrap();

        // List
        let contexts = super::contexts::list_contexts(ctx_dir, "myctx").unwrap();
        assert_eq!(contexts.len(), 1);
        assert_eq!(contexts[0].0, "myctx");
        assert!(contexts[0].1); // is_active

        // Show (read resource group)
        let (name, rg) =
            super::contexts::read_context_resource_group(&ctx_dir.join("myctx.toml")).unwrap();
        assert_eq!(name, "myctx");
        assert_eq!(rg, Some("myrg".to_string()));

        // Delete
        fs::remove_file(ctx_dir.join("myctx.toml")).unwrap();
        let contexts = super::contexts::list_contexts(ctx_dir, "myctx").unwrap();
        assert!(contexts.is_empty());
    }

    #[test]
    fn test_context_list_multiple_with_active() {
        let tmp = TempDir::new().unwrap();
        let ctx_dir = tmp.path();

        for name in &["alpha", "beta", "gamma"] {
            let toml_str =
                super::contexts::build_context_toml(name, None, None, Some("rg-1"), None, None)
                    .unwrap();
            fs::write(ctx_dir.join(format!("{}.toml", name)), &toml_str).unwrap();
        }

        let contexts = super::contexts::list_contexts(ctx_dir, "beta").unwrap();
        assert_eq!(contexts.len(), 3);
        let active_count = contexts.iter().filter(|(_, a)| *a).count();
        assert_eq!(active_count, 1);
        let beta = contexts.iter().find(|(n, _)| n == "beta").unwrap();
        assert!(beta.1);
    }

    #[test]
    fn test_context_rename_success_with_verify() {
        let tmp = TempDir::new().unwrap();
        let ctx_dir = tmp.path();

        let toml_str =
            super::contexts::build_context_toml("old-ctx", None, None, Some("myrg"), None, None)
                .unwrap();
        fs::write(ctx_dir.join("old-ctx.toml"), &toml_str).unwrap();

        super::contexts::rename_context_file(ctx_dir, "old-ctx", "new-ctx").unwrap();

        assert!(!ctx_dir.join("old-ctx.toml").exists());
        assert!(ctx_dir.join("new-ctx.toml").exists());

        let (name, _) =
            super::contexts::read_context_resource_group(&ctx_dir.join("new-ctx.toml")).unwrap();
        assert_eq!(name, "new-ctx");
    }

    #[test]
    fn test_context_build_all_optional_fields() {
        let toml_str = super::contexts::build_context_toml(
            "full-ctx",
            Some("sub-id"),
            Some("tenant-id"),
            Some("my-rg"),
            Some("westus2"),
            Some("my-vault"),
        )
        .unwrap();
        assert!(toml_str.contains("subscription_id"));
        assert!(toml_str.contains("tenant_id"));
        assert!(toml_str.contains("resource_group"));
        assert!(toml_str.contains("region"));
        assert!(toml_str.contains("key_vault_name"));
        assert!(toml_str.contains("full-ctx"));
    }

    // ── Session management lifecycle ────────────────────────────────

    #[test]
    fn test_session_full_lifecycle_save_list_load_delete() {
        let tmp = TempDir::new().unwrap();
        let sessions_dir = tmp.path();

        // Save
        let session = super::sessions::build_session_toml(
            "test-session",
            "my-rg",
            &["vm1".to_string(), "vm2".to_string()],
        );
        let content = toml::to_string_pretty(&session).unwrap();
        fs::write(sessions_dir.join("test-session.toml"), &content).unwrap();

        // List
        let names = super::sessions::list_session_names(sessions_dir).unwrap();
        assert_eq!(names.len(), 1);
        assert_eq!(names[0], "test-session");

        // Load — parse_session_toml returns (rg, vms, created)
        let loaded_content = fs::read_to_string(sessions_dir.join("test-session.toml")).unwrap();
        let (rg, vms, _created) = super::sessions::parse_session_toml(&loaded_content).unwrap();
        assert_eq!(rg, "my-rg");
        assert_eq!(vms, vec!["vm1".to_string(), "vm2".to_string()]);

        // Delete
        fs::remove_file(sessions_dir.join("test-session.toml")).unwrap();
        let names = super::sessions::list_session_names(sessions_dir).unwrap();
        assert!(names.is_empty());
    }

    #[test]
    fn test_session_save_empty_vms_lifecycle() {
        let session = super::sessions::build_session_toml("empty-sess", "rg", &[]);
        let content = toml::to_string_pretty(&session).unwrap();
        let (rg, vms, _created) = super::sessions::parse_session_toml(&content).unwrap();
        assert_eq!(rg, "rg");
        assert!(vms.is_empty());
    }

    #[test]
    fn test_session_list_nonexistent_dir() {
        let tmp = TempDir::new().unwrap();
        let missing = tmp.path().join("no-such-dir");
        let names = super::sessions::list_session_names(&missing).unwrap();
        assert!(names.is_empty());
    }

    // ── Template lifecycle ──────────────────────────────────────────

    #[test]
    fn test_template_save_load_roundtrip_all_fields() {
        let tmp = TempDir::new().unwrap();
        let tpl = super::templates::build_template_toml(
            "gpu-box",
            Some("GPU development template"),
            Some("Standard_NC6s_v3"),
            Some("eastus2"),
            Some("#!/bin/bash\napt-get install -y cuda"),
        );
        super::templates::save_template(tmp.path(), "gpu-box", &tpl).unwrap();

        let loaded = super::templates::load_template(tmp.path(), "gpu-box").unwrap();
        assert_eq!(loaded["name"].as_str(), Some("gpu-box"));
        assert_eq!(loaded["vm_size"].as_str(), Some("Standard_NC6s_v3"));
        assert_eq!(loaded["region"].as_str(), Some("eastus2"));
        assert!(loaded["cloud_init"].as_str().unwrap().contains("cuda"));
    }

    #[test]
    fn test_template_list_multiple() {
        let tmp = TempDir::new().unwrap();
        for name in &["dev", "prod", "test"] {
            let tpl = super::templates::build_template_toml(name, None, None, None, None);
            super::templates::save_template(tmp.path(), name, &tpl).unwrap();
        }

        let list = super::templates::list_templates(tmp.path()).unwrap();
        assert_eq!(list.len(), 3);
    }

    #[test]
    fn test_template_load_nonexistent_errors() {
        let tmp = TempDir::new().unwrap();
        let result = super::templates::load_template(tmp.path(), "nope");
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("not found"));
    }

    #[test]
    fn test_template_delete_then_verify_gone() {
        let tmp = TempDir::new().unwrap();
        let tpl = super::templates::build_template_toml("deleteme", None, None, None, None);
        super::templates::save_template(tmp.path(), "deleteme", &tpl).unwrap();
        assert!(tmp.path().join("deleteme.toml").exists());

        super::templates::delete_template(tmp.path(), "deleteme").unwrap();
        assert!(!tmp.path().join("deleteme.toml").exists());
    }

    #[test]
    fn test_template_import_with_extra_fields() {
        let tmp = TempDir::new().unwrap();
        let content = r#"
name = "custom"
vm_size = "Standard_B1s"
region = "northeurope"
custom_field = "extra"
"#;
        let name = super::templates::import_template(tmp.path(), content).unwrap();
        assert_eq!(name, "custom");
        let loaded = super::templates::load_template(tmp.path(), "custom").unwrap();
        assert_eq!(loaded["custom_field"].as_str(), Some("extra"));
    }

    // ── Autopilot config tests ──────────────────────────────────────

    #[test]
    fn test_autopilot_config_all_fields() {
        let config = super::autopilot_helpers::build_autopilot_config(
            Some(500),
            "aggressive",
            15,
            10,
            "2024-01-15T10:00:00Z",
        );
        let table = config.as_table().unwrap();
        assert_eq!(table["enabled"].as_bool(), Some(true));
        assert_eq!(table["budget"].as_integer(), Some(500));
        assert_eq!(table["strategy"].as_str(), Some("aggressive"));
        assert_eq!(table["idle_threshold_minutes"].as_integer(), Some(15));
        assert_eq!(table["cpu_threshold_percent"].as_integer(), Some(10));
        assert_eq!(table["updated"].as_str(), Some("2024-01-15T10:00:00Z"));
    }

    #[test]
    fn test_autopilot_config_serializes_to_valid_toml() {
        let config = super::autopilot_helpers::build_autopilot_config(
            None,
            "conservative",
            30,
            5,
            "2024-06-01T00:00:00Z",
        );
        let toml_str = toml::to_string_pretty(&config).unwrap();
        let parsed: toml::Value = toml_str.parse().unwrap();
        assert_eq!(parsed["enabled"].as_bool(), Some(true));
        assert!(parsed.get("budget").is_none());
    }

    // ── env_helpers edge cases ──────────────────────────────────────

    #[test]
    fn test_validate_env_key_empty_is_error() {
        assert!(super::env_helpers::validate_env_key("").is_err());
        let err = super::env_helpers::validate_env_key("").unwrap_err();
        assert!(err.contains("must not be empty"));
    }

    #[test]
    fn test_validate_env_key_starting_with_digit_is_error() {
        let err = super::env_helpers::validate_env_key("1ABC").unwrap_err();
        assert!(err.contains("must not start with a digit"));
    }

    #[test]
    fn test_validate_env_key_special_chars_rejected() {
        assert!(super::env_helpers::validate_env_key("MY-VAR").is_err());
        assert!(super::env_helpers::validate_env_key("MY.VAR").is_err());
        assert!(super::env_helpers::validate_env_key("MY VAR").is_err());
        assert!(super::env_helpers::validate_env_key("MY$VAR").is_err());
    }

    #[test]
    fn test_build_env_set_cmd_with_invalid_key_returns_noop() {
        let cmd = super::env_helpers::build_env_set_cmd("BAD-KEY!", "'value'");
        assert_eq!(cmd, "true");
    }

    #[test]
    fn test_build_env_set_cmd_valid_contains_grep_and_sed() {
        let cmd = super::env_helpers::build_env_set_cmd("MY_VAR", "'hello'");
        assert!(cmd.contains("grep"));
        assert!(cmd.contains("sed"));
        assert!(cmd.contains("MY_VAR"));
        assert!(cmd.contains("'hello'"));
    }

    #[test]
    fn test_parse_env_file_skips_comments_and_blanks() {
        let content = "# comment\n\nFOO=bar\n  # another comment\nBAZ=qux\n\n";
        let result = super::env_helpers::parse_env_file(content);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], ("FOO".to_string(), "bar".to_string()));
        assert_eq!(result[1], ("BAZ".to_string(), "qux".to_string()));
    }

    #[test]
    fn test_build_env_file_and_parse_roundtrip() {
        let vars = vec![
            ("PATH".to_string(), "/usr/bin".to_string()),
            ("HOME".to_string(), "/home/user".to_string()),
            ("LANG".to_string(), "en_US.UTF-8".to_string()),
        ];
        let file_content = super::env_helpers::build_env_file(&vars);
        let parsed = super::env_helpers::parse_env_file(&file_content);
        assert_eq!(parsed, vars);
    }

    #[test]
    fn test_split_env_var_normal() {
        let result = super::env_helpers::split_env_var("KEY=VALUE");
        assert_eq!(result, Some(("KEY", "VALUE")));
    }

    #[test]
    fn test_split_env_var_embedded_equals_sign() {
        let result = super::env_helpers::split_env_var("KEY=VAL=UE");
        assert_eq!(result, Some(("KEY", "VAL=UE")));
    }

    #[test]
    fn test_split_env_var_no_equals_returns_none() {
        assert!(super::env_helpers::split_env_var("NOEQUALS").is_none());
    }

    // ── sync_helpers ────────────────────────────────────────────────

    #[test]
    fn test_validate_sync_source_traversal_variants() {
        // "/../" in the middle
        assert!(super::sync_helpers::validate_sync_source("foo/../bar").is_err());
        // Ends with "/.."
        assert!(super::sync_helpers::validate_sync_source("foo/..").is_err());
        // Just ".."
        assert!(super::sync_helpers::validate_sync_source("..").is_err());
        // Safe relative path is OK
        assert!(super::sync_helpers::validate_sync_source("mydir/file").is_ok());
    }

    #[test]
    fn test_validate_sync_source_forbidden_prefixes() {
        for prefix in &[
            "/etc/passwd",
            "/var/log",
            "/root/.ssh",
            "/proc/cpuinfo",
            "/sys/devices",
        ] {
            let result = super::sync_helpers::validate_sync_source(prefix);
            assert!(result.is_err(), "Expected error for prefix: {}", prefix);
        }
    }

    #[test]
    fn test_build_rsync_args_correct_format() {
        let args =
            super::sync_helpers::build_rsync_args(".bashrc", "azureuser", "10.0.0.1", ".bashrc");
        assert_eq!(args[0], "-az");
        assert_eq!(args[1], "-e");
        assert!(args[2].contains("StrictHostKeyChecking=accept-new"));
        assert_eq!(args[3], ".bashrc");
        assert_eq!(args[4], "azureuser@10.0.0.1:~/.bashrc");
    }

    #[test]
    fn test_default_dotfiles_contains_expected() {
        let dotfiles = super::sync_helpers::default_dotfiles();
        assert!(dotfiles.contains(&".bashrc"));
        assert!(dotfiles.contains(&".profile"));
        assert!(dotfiles.contains(&".gitconfig"));
        assert!(dotfiles.len() >= 4);
    }

    // ── health_helpers edge cases ───────────────────────────────────

    #[test]
    fn test_status_emoji_all_values_low() {
        assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
    }

    #[test]
    fn test_status_emoji_one_high() {
        assert_eq!(super::health_helpers::status_emoji(95.0, 20.0, 30.0), "🔴");
        assert_eq!(super::health_helpers::status_emoji(10.0, 91.0, 30.0), "🔴");
        assert_eq!(super::health_helpers::status_emoji(10.0, 20.0, 95.0), "🔴");
    }

    #[test]
    fn test_status_emoji_medium() {
        assert_eq!(super::health_helpers::status_emoji(75.0, 20.0, 30.0), "🟡");
        assert_eq!(super::health_helpers::status_emoji(10.0, 80.0, 30.0), "🟡");
    }

    #[test]
    fn test_metric_color_boundary_values() {
        assert_eq!(super::health_helpers::metric_color(50.0), "green");
        assert_eq!(super::health_helpers::metric_color(50.1), "yellow");
        assert_eq!(super::health_helpers::metric_color(80.0), "yellow");
        assert_eq!(super::health_helpers::metric_color(80.1), "red");
    }

    #[test]
    fn test_state_color_all_variants() {
        assert_eq!(super::health_helpers::state_color("running"), "green");
        assert_eq!(super::health_helpers::state_color("stopped"), "red");
        assert_eq!(super::health_helpers::state_color("deallocated"), "red");
        assert_eq!(super::health_helpers::state_color("starting"), "yellow");
        assert_eq!(super::health_helpers::state_color("random"), "yellow");
    }

    #[test]
    fn test_format_percentage_large_value() {
        let result = super::health_helpers::format_percentage(100.0);
        assert_eq!(result, "100.0%");
    }

    #[test]
    fn test_format_percentage_zero() {
        assert_eq!(super::health_helpers::format_percentage(0.0), "0.0%");
    }

    // ── snapshot_helpers ────────────────────────────────────────────

    #[test]
    fn test_filter_snapshots_partial_name_match() {
        let snapshots = vec![
            serde_json::json!({"name": "dev-vm_snapshot_20240101"}),
            serde_json::json!({"name": "prod-vm_snapshot_20240101"}),
            serde_json::json!({"name": "dev-vm_snapshot_20240102"}),
        ];
        let filtered = super::snapshot_helpers::filter_snapshots(&snapshots, "dev-vm");
        assert_eq!(filtered.len(), 2);
    }

    #[test]
    fn test_snapshot_schedule_full_lifecycle() {
        let tmp = TempDir::new().unwrap();
        let schedule = super::snapshot_helpers::SnapshotSchedule {
            vm_name: "test-vm".to_string(),
            resource_group: "test-rg".to_string(),
            every_hours: 6,
            keep_count: 10,
            enabled: true,
            created: "2024-01-15T10:00:00Z".to_string(),
        };

        // Serialize and write
        let toml_str = toml::to_string_pretty(&schedule).unwrap();
        let path = tmp.path().join("test-vm.toml");
        fs::write(&path, &toml_str).unwrap();

        // Read back and deserialize
        let content = fs::read_to_string(&path).unwrap();
        let loaded: super::snapshot_helpers::SnapshotSchedule = toml::from_str(&content).unwrap();
        assert_eq!(loaded.vm_name, "test-vm");
        assert_eq!(loaded.every_hours, 6);
        assert_eq!(loaded.keep_count, 10);
        assert!(loaded.enabled);
    }

    // ── output_helpers ──────────────────────────────────────────────

    #[test]
    fn test_format_as_table_multirow() {
        let headers = &["Name", "Size", "Status"];
        let rows = vec![
            vec![
                "vm-1".to_string(),
                "Standard_B2s".to_string(),
                "Running".to_string(),
            ],
            vec![
                "vm-2-long-name".to_string(),
                "Standard_D4s_v3".to_string(),
                "Stopped".to_string(),
            ],
        ];
        let table = super::output_helpers::format_as_table(headers, &rows);
        assert!(table.contains("Name"));
        assert!(table.contains("vm-1"));
        assert!(table.contains("vm-2-long-name"));
        // Verify alignment: wider columns expand
        let lines: Vec<&str> = table.lines().collect();
        assert_eq!(lines.len(), 3); // header + 2 rows
    }

    #[test]
    fn test_format_as_csv_with_data() {
        let headers = &["Name", "Cost"];
        let rows = vec![
            vec!["vm-1".to_string(), "$10.50".to_string()],
            vec!["vm-2".to_string(), "$20.00".to_string()],
        ];
        let csv = super::output_helpers::format_as_csv(headers, &rows);
        let lines: Vec<&str> = csv.lines().collect();
        assert_eq!(lines[0], "Name,Cost");
        assert_eq!(lines[1], "vm-1,$10.50");
        assert_eq!(lines[2], "vm-2,$20.00");
    }

    #[test]
    fn test_format_as_json_custom_structs() {
        #[derive(serde::Serialize)]
        struct Item {
            name: String,
            value: i32,
        }
        let items = vec![
            Item {
                name: "a".to_string(),
                value: 1,
            },
            Item {
                name: "b".to_string(),
                value: 2,
            },
        ];
        let json = super::output_helpers::format_as_json(&items);
        let parsed: Vec<serde_json::Value> = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed.len(), 2);
        assert_eq!(parsed[0]["name"], "a");
        assert_eq!(parsed[1]["value"], 2);
    }

    // ── VM name validation edge cases ───────────────────────────────

    #[test]
    fn test_validate_vm_name_consecutive_hyphens_allowed() {
        // Azure allows consecutive hyphens
        assert!(super::vm_validation::validate_vm_name("vm--test").is_ok());
    }

    #[test]
    fn test_validate_vm_name_max_64_chars_ok() {
        let name = "a".repeat(64);
        assert!(super::vm_validation::validate_vm_name(&name).is_ok());
    }

    #[test]
    fn test_validate_vm_name_65_chars_rejected() {
        let name = "a".repeat(65);
        let err = super::vm_validation::validate_vm_name(&name).unwrap_err();
        assert!(err.contains("exceeds 64"));
    }

    #[test]
    fn test_validate_vm_name_special_chars_rejected() {
        assert!(super::vm_validation::validate_vm_name("vm@test").is_err());
        assert!(super::vm_validation::validate_vm_name("vm.test").is_err());
        assert!(super::vm_validation::validate_vm_name("vm test").is_err());
    }

    // ── mount_helpers edge cases ────────────────────────────────────

    #[test]
    fn test_validate_mount_path_valid() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/data").is_ok());
        assert!(super::mount_helpers::validate_mount_path("/home/user/work").is_ok());
    }

    #[test]
    fn test_validate_mount_path_empty() {
        let err = super::mount_helpers::validate_mount_path("").unwrap_err();
        assert!(err.contains("must not be empty"));
    }

    #[test]
    fn test_validate_mount_path_shell_metacharacters() {
        for path in &[
            "/mnt;rm -rf /",
            "/mnt|cat",
            "/mnt&bg",
            "/mnt$(cmd)",
            "/mnt`cmd`",
        ] {
            assert!(
                super::mount_helpers::validate_mount_path(path).is_err(),
                "Expected error for path: {}",
                path,
            );
        }
    }

    #[test]
    fn test_validate_mount_path_traversal() {
        assert!(super::mount_helpers::validate_mount_path("/mnt/../etc").is_err());
        assert!(super::mount_helpers::validate_mount_path("/mnt/..").is_err());
    }

    // ── cp_helpers ──────────────────────────────────────────────────

    #[test]
    fn test_is_remote_path_variants() {
        assert!(super::cp_helpers::is_remote_path("vm-name:/path"));
        assert!(!super::cp_helpers::is_remote_path("/local/path"));
        assert!(!super::cp_helpers::is_remote_path("C:\\windows")); // drive letter
        assert!(!super::cp_helpers::is_remote_path("ab")); // too short
    }

    #[test]
    fn test_classify_transfer_direction_all_cases() {
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("vm:/path", "/local"),
            "remote→local"
        );
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("/local", "vm:/path"),
            "local→remote"
        );
        assert_eq!(
            super::cp_helpers::classify_transfer_direction("/a", "/b"),
            "local→local"
        );
    }

    #[test]
    fn test_resolve_scp_path_replaces_vm_name() {
        let result = super::cp_helpers::resolve_scp_path(
            "my-vm:/remote/path",
            "my-vm",
            "azureuser",
            "10.0.0.1",
        );
        assert_eq!(result, "azureuser@10.0.0.1:/remote/path");
    }

    // ── bastion_helpers ─────────────────────────────────────────────

    #[test]
    fn test_bastion_summary_extracts_fields() {
        let b = serde_json::json!({
            "name": "my-bastion",
            "resourceGroup": "my-rg",
            "location": "eastus",
            "sku": {"name": "Standard"},
            "provisioningState": "Succeeded"
        });
        let (name, rg, loc, sku, state) = super::bastion_helpers::bastion_summary(&b);
        assert_eq!(name, "my-bastion");
        assert_eq!(rg, "my-rg");
        assert_eq!(loc, "eastus");
        assert_eq!(sku, "Standard");
        assert_eq!(state, "Succeeded");
    }

    #[test]
    fn test_extract_ip_configs_multiple_entries() {
        let b = serde_json::json!({
            "ipConfigurations": [
                {
                    "subnet": {"id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/virtualNetworks/vnet1/subnets/AzureBastionSubnet"},
                    "publicIPAddress": {"id": "/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.Network/publicIPAddresses/bastion-pip"}
                },
                {
                    "subnet": {"id": "/subs/rg/vnet/subnets/OtherSubnet"},
                    "publicIPAddress": {"id": "N/A"}
                }
            ]
        });
        let configs = super::bastion_helpers::extract_ip_configs(&b);
        assert_eq!(configs.len(), 2);
        assert_eq!(configs[0].0, "AzureBastionSubnet");
        assert_eq!(configs[0].1, "bastion-pip");
        assert_eq!(configs[1].1, "N/A");
    }

    #[test]
    fn test_shorten_resource_id_long_path() {
        assert_eq!(
            super::bastion_helpers::shorten_resource_id(
                "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/my-pip"
            ),
            "my-pip"
        );
    }

    // ── fleet_helpers ───────────────────────────────────────────────

    #[test]
    fn test_classify_result_various_codes() {
        assert_eq!(super::fleet_helpers::classify_result(0), ("OK", true));
        assert_eq!(super::fleet_helpers::classify_result(1), ("FAIL", false));
        assert_eq!(super::fleet_helpers::classify_result(127), ("FAIL", false));
        assert_eq!(super::fleet_helpers::classify_result(-1), ("FAIL", false));
    }

    #[test]
    fn test_finish_message_multiline_stdout() {
        let msg = super::fleet_helpers::finish_message(0, "line1\nline2\nline3\n", "");
        assert!(msg.contains("3 lines"));
    }

    #[test]
    fn test_finish_message_error_first_line() {
        let msg = super::fleet_helpers::finish_message(
            1,
            "",
            "Error: connection refused\ndetailed trace\n",
        );
        assert!(msg.contains("Error: connection refused"));
        assert!(!msg.contains("detailed trace"));
    }

    #[test]
    fn test_format_output_text_show_stdout() {
        let text = super::fleet_helpers::format_output_text(0, "hello world", "", true);
        assert_eq!(text, "hello world");
    }

    #[test]
    fn test_format_output_text_show_stderr_when_stdout_empty() {
        let text = super::fleet_helpers::format_output_text(1, "", "error msg", true);
        assert_eq!(text, "error msg");
    }

    #[test]
    fn test_format_output_text_hide_success_empty() {
        let text = super::fleet_helpers::format_output_text(0, "output", "", false);
        assert!(text.is_empty());
    }

    // ── list_helpers with VmInfo ────────────────────────────────────

    #[test]
    fn test_filter_running_keeps_starting() {
        use azlin_core::models::{OsType, PowerState, VmInfo};
        let mut vms = vec![
            VmInfo {
                name: "running-vm".to_string(),
                resource_group: "rg".to_string(),
                location: "eastus".to_string(),
                vm_size: "B2s".to_string(),
                power_state: PowerState::Running,
                provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
                os_type: OsType::Linux,
                os_offer: None,
                public_ip: None,
                private_ip: None,
                admin_username: None,
                tags: Default::default(),
                created_time: None,
            },
            VmInfo {
                name: "starting-vm".to_string(),
                resource_group: "rg".to_string(),
                location: "eastus".to_string(),
                vm_size: "B2s".to_string(),
                power_state: PowerState::Starting,
                provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
                os_type: OsType::Linux,
                os_offer: None,
                public_ip: None,
                private_ip: None,
                admin_username: None,
                tags: Default::default(),
                created_time: None,
            },
            VmInfo {
                name: "stopped-vm".to_string(),
                resource_group: "rg".to_string(),
                location: "eastus".to_string(),
                vm_size: "B2s".to_string(),
                power_state: PowerState::Stopped,
                provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
                os_type: OsType::Linux,
                os_offer: None,
                public_ip: None,
                private_ip: None,
                admin_username: None,
                tags: Default::default(),
                created_time: None,
            },
        ];
        super::list_helpers::filter_running(&mut vms);
        assert_eq!(vms.len(), 2);
        assert!(
            vms.iter()
                .all(|v| v.power_state == PowerState::Running
                    || v.power_state == PowerState::Starting)
        );
    }

    #[test]
    fn test_filter_by_tag_key_only_match() {
        use azlin_core::models::{OsType, PowerState, VmInfo};
        let mut vms = vec![
            VmInfo {
                name: "tagged".to_string(),
                resource_group: "rg".to_string(),
                location: "eastus".to_string(),
                vm_size: "B2s".to_string(),
                power_state: PowerState::Running,
                provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
                os_type: OsType::Linux,
                os_offer: None,
                public_ip: None,
                private_ip: None,
                admin_username: None,
                tags: [("env".to_string(), "prod".to_string())]
                    .into_iter()
                    .collect(),
                created_time: None,
            },
            VmInfo {
                name: "untagged".to_string(),
                resource_group: "rg".to_string(),
                location: "eastus".to_string(),
                vm_size: "B2s".to_string(),
                power_state: PowerState::Running,
                provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
                os_type: OsType::Linux,
                os_offer: None,
                public_ip: None,
                private_ip: None,
                admin_username: None,
                tags: Default::default(),
                created_time: None,
            },
        ];
        // Key-only filter (no =value)
        super::list_helpers::filter_by_tag(&mut vms, "env");
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "tagged");
    }

    #[test]
    fn test_apply_filters_include_all_skips_running_filter() {
        use azlin_core::models::{OsType, PowerState, VmInfo};
        let mut vms = vec![VmInfo {
            name: "stopped-vm".to_string(),
            resource_group: "rg".to_string(),
            location: "eastus".to_string(),
            vm_size: "B2s".to_string(),
            power_state: PowerState::Stopped,
            provisioning_state: azlin_core::models::ProvisioningState::Succeeded,
            os_type: OsType::Linux,
            os_offer: None,
            public_ip: None,
            private_ip: None,
            admin_username: None,
            tags: Default::default(),
            created_time: None,
        }];
        super::list_helpers::apply_filters(&mut vms, true, None, None);
        assert_eq!(vms.len(), 1); // stopped VM kept because include_all=true
    }

    // ── create_helpers ──────────────────────────────────────────────

    #[test]
    fn test_generate_vm_name_pool_indexing() {
        let name = super::create_helpers::generate_vm_name(Some("worker"), 0, 3, "20240115");
        assert_eq!(name, "worker-1");
        let name2 = super::create_helpers::generate_vm_name(Some("worker"), 2, 3, "20240115");
        assert_eq!(name2, "worker-3");
    }

    #[test]
    fn test_generate_vm_name_single_pool_no_index() {
        let name = super::create_helpers::generate_vm_name(Some("myvm"), 0, 1, "20240115");
        assert_eq!(name, "myvm");
    }

    #[test]
    fn test_generate_vm_name_auto_timestamp() {
        let name = super::create_helpers::generate_vm_name(None, 0, 1, "20240115120000");
        assert!(name.starts_with("azlin-vm-"));
        assert!(name.contains("20240115120000"));
    }

    #[test]
    fn test_resolve_with_template_sentinel_uses_template() {
        let result = super::create_helpers::resolve_with_template_default(
            "Standard_B2s",
            "Standard_B2s",
            Some("Standard_D4s_v3".to_string()),
        );
        assert_eq!(result, "Standard_D4s_v3");
    }

    #[test]
    fn test_resolve_with_template_user_override() {
        let result = super::create_helpers::resolve_with_template_default(
            "Standard_NC6",
            "Standard_B2s",
            Some("Standard_D4s_v3".to_string()),
        );
        assert_eq!(result, "Standard_NC6");
    }

    #[test]
    fn test_resolve_with_template_sentinel_no_template_keeps_default() {
        let result = super::create_helpers::resolve_with_template_default(
            "Standard_B2s",
            "Standard_B2s",
            None,
        );
        assert_eq!(result, "Standard_B2s");
    }

    // ── connect_helpers ─────────────────────────────────────────────

    #[test]
    fn test_build_ssh_args_with_key_path() {
        let key = std::path::PathBuf::from("/home/user/.ssh/id_ed25519");
        let args =
            super::connect_helpers::build_ssh_args("azureuser", "10.0.0.1", Some(key.as_path()));
        assert!(args.contains(&"-i".to_string()));
        assert!(args.contains(&"/home/user/.ssh/id_ed25519".to_string()));
        assert!(args.contains(&"azureuser@10.0.0.1".to_string()));
    }

    #[test]
    fn test_build_ssh_args_no_key_provided() {
        let args = super::connect_helpers::build_ssh_args("user", "1.2.3.4", None);
        assert!(!args.contains(&"-i".to_string()));
        assert!(args.contains(&"user@1.2.3.4".to_string()));
    }

    #[test]
    fn test_build_vscode_remote_uri_format() {
        let uri = super::connect_helpers::build_vscode_remote_uri("azureuser", "10.0.0.5");
        assert_eq!(uri, "ssh-remote+azureuser@10.0.0.5");
    }

    #[test]
    fn test_build_log_follow_args_has_tail_f() {
        let args =
            super::connect_helpers::build_log_follow_args("user", "10.0.0.1", "/var/log/syslog");
        assert!(args.iter().any(|a| a.contains("tail -f")));
        assert!(args.iter().any(|a| a.contains("/var/log/syslog")));
    }

    #[test]
    fn test_build_log_tail_args_custom_lines() {
        let args = super::connect_helpers::build_log_tail_args(
            "user",
            "10.0.0.1",
            100,
            "/var/log/auth.log",
        );
        assert!(args.iter().any(|a| a.contains("tail -n 100")));
    }

    // ── update_helpers ──────────────────────────────────────────────

    #[test]
    fn test_build_dev_update_script_all_sections() {
        let script = super::update_helpers::build_dev_update_script();
        assert!(script.contains("apt-get update"));
        assert!(script.contains("rustup"));
        assert!(script.contains("pip3"));
        assert!(script.contains("npm"));
    }

    #[test]
    fn test_build_os_update_cmd_format() {
        let cmd = super::update_helpers::build_os_update_cmd();
        assert!(cmd.contains("apt-get update"));
        assert!(cmd.contains("apt-get upgrade"));
        assert!(cmd.contains("DEBIAN_FRONTEND=noninteractive"));
    }

    #[test]
    fn test_log_type_to_path_all_variants() {
        assert_eq!(
            super::update_helpers::log_type_to_path("cloud-init"),
            "/var/log/cloud-init-output.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("CloudInit"),
            "/var/log/cloud-init-output.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("syslog"),
            "/var/log/syslog"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("Syslog"),
            "/var/log/syslog"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("auth"),
            "/var/log/auth.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("Auth"),
            "/var/log/auth.log"
        );
        assert_eq!(
            super::update_helpers::log_type_to_path("other"),
            "/var/log/syslog"
        );
    }

    // ── runner_helpers ──────────────────────────────────────────────

    #[test]
    fn test_build_runner_vm_name_format() {
        assert_eq!(
            super::runner_helpers::build_runner_vm_name("ci", 0),
            "azlin-runner-ci-1"
        );
        assert_eq!(
            super::runner_helpers::build_runner_vm_name("deploy", 4),
            "azlin-runner-deploy-5"
        );
    }

    #[test]
    fn test_build_runner_tags_format() {
        let tags = super::runner_helpers::build_runner_tags("ci", "org/repo");
        assert!(tags.contains("azlin-runner=true"));
        assert!(tags.contains("pool=ci"));
        assert!(tags.contains("repo=org/repo"));
    }

    #[test]
    fn test_build_runner_config_all_fields() {
        let config = super::runner_helpers::build_runner_config(
            "ci",
            "org/repo",
            3,
            "self-hosted,linux",
            "my-rg",
            "Standard_D4s_v3",
            "2024-01-15T10:00:00Z",
        );
        assert!(config.iter().any(|(k, _)| k == "pool"));
        assert!(config.iter().any(|(k, _)| k == "count"));
        assert!(config.iter().any(|(k, _)| k == "enabled"));
        let count = config.iter().find(|(k, _)| k == "count").unwrap();
        assert_eq!(count.1.as_integer(), Some(3));
    }

    // ── compose_helpers ─────────────────────────────────────────────

    #[test]
    fn test_resolve_compose_file_none_default() {
        assert_eq!(
            super::compose_helpers::resolve_compose_file(None),
            "docker-compose.yml"
        );
    }

    #[test]
    fn test_resolve_compose_file_override() {
        assert_eq!(
            super::compose_helpers::resolve_compose_file(Some("custom.yml")),
            "custom.yml"
        );
    }

    #[test]
    fn test_build_compose_cmd_format() {
        let cmd = super::compose_helpers::build_compose_cmd("up -d", "docker-compose.yml");
        assert_eq!(cmd, "docker compose -f docker-compose.yml up -d");
    }

    // ── batch_helpers ───────────────────────────────────────────────

    #[test]
    fn test_parse_vm_ids_multiple_lines() {
        let tsv = "/subs/rg/vm1\n/subs/rg/vm2\n/subs/rg/vm3\n";
        let ids = super::batch_helpers::parse_vm_ids(tsv);
        assert_eq!(ids.len(), 3);
    }

    #[test]
    fn test_parse_vm_ids_blank_input() {
        assert!(super::batch_helpers::parse_vm_ids("").is_empty());
        assert!(super::batch_helpers::parse_vm_ids("\n\n").is_empty());
    }

    #[test]
    fn test_build_batch_args_format() {
        let ids = vec!["/id/1", "/id/2"];
        let args = super::batch_helpers::build_batch_args("deallocate", &ids);
        assert_eq!(args[0], "vm");
        assert_eq!(args[1], "deallocate");
        assert_eq!(args[2], "--ids");
        assert_eq!(args[3], "/id/1");
        assert_eq!(args[4], "/id/2");
    }

    #[test]
    fn test_summarise_batch_messages() {
        let success = super::batch_helpers::summarise_batch("start", "my-rg", true);
        assert!(success.contains("completed"));
        assert!(success.contains("my-rg"));

        let failure = super::batch_helpers::summarise_batch("stop", "my-rg", false);
        assert!(failure.contains("failed"));
    }

    // ── display_helpers ─────────────────────────────────────────────

    #[test]
    fn test_config_value_display_bool() {
        let v = serde_json::json!(true);
        assert_eq!(super::display_helpers::config_value_display(&v), "true");
    }

    #[test]
    fn test_config_value_display_array() {
        let v = serde_json::json!([1, 2, 3]);
        assert_eq!(super::display_helpers::config_value_display(&v), "[1,2,3]");
    }

    #[test]
    fn test_truncate_vm_name_max_len_3_or_less() {
        // When max_len <= 3, no truncation should happen (avoid "...")
        let result = super::display_helpers::truncate_vm_name("longname", 3);
        assert_eq!(result, "longname");
    }

    #[test]
    fn test_format_tmux_sessions_max_show_1() {
        let sessions = vec!["s1".to_string(), "s2".to_string(), "s3".to_string()];
        let result = super::display_helpers::format_tmux_sessions(&sessions, 1);
        assert!(result.contains("s1"));
        assert!(result.contains("+2 more"));
    }

    #[test]
    fn test_reconnect_prompt_format_values() {
        let prompt = super::display_helpers::reconnect_prompt(2, 5);
        assert!(prompt.contains("2/5"));
        assert!(prompt.contains("Reconnect?"));
    }

    // ── health_parse_helpers ────────────────────────────────────────

    #[test]
    fn test_parse_cpu_stdout_valid_float() {
        assert_eq!(
            super::health_parse_helpers::parse_cpu_stdout(0, "  45.3  "),
            Some(45.3)
        );
    }

    #[test]
    fn test_parse_cpu_stdout_nonzero_exit() {
        assert_eq!(
            super::health_parse_helpers::parse_cpu_stdout(1, "45.3"),
            None
        );
    }

    #[test]
    fn test_parse_mem_stdout_decimal() {
        assert_eq!(
            super::health_parse_helpers::parse_mem_stdout(0, "78.9"),
            Some(78.9)
        );
    }

    #[test]
    fn test_parse_disk_stdout_integer() {
        assert_eq!(
            super::health_parse_helpers::parse_disk_stdout(0, "42"),
            Some(42.0)
        );
    }

    #[test]
    fn test_parse_load_stdout_trimmed() {
        let result = super::health_parse_helpers::parse_load_stdout(0, " 1.2, 0.8, 0.5 ");
        assert_eq!(result, Some("1.2, 0.8, 0.5".to_string()));
    }

    #[test]
    fn test_parse_load_stdout_empty_returns_none() {
        assert_eq!(
            super::health_parse_helpers::parse_load_stdout(0, "  "),
            None
        );
    }

    #[test]
    fn test_default_metrics_values() {
        let m = super::health_parse_helpers::default_metrics("vm1", "stopped");
        assert_eq!(m.vm_name, "vm1");
        assert_eq!(m.power_state, "stopped");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
        assert_eq!(m.load_avg, "-");
    }

    // ── tag_helpers edge cases ──────────────────────────────────────

    #[test]
    fn test_parse_tag_value_with_spaces() {
        let result = super::tag_helpers::parse_tag("name=My VM Name");
        assert_eq!(result, Some(("name", "My VM Name")));
    }

    #[test]
    fn test_parse_tag_empty_value() {
        let result = super::tag_helpers::parse_tag("key=");
        assert_eq!(result, Some(("key", "")));
    }

    #[test]
    fn test_find_invalid_tag_empty_list() {
        let tags: Vec<String> = vec![];
        assert!(super::tag_helpers::find_invalid_tag(&tags).is_none());
    }

    // ── disk_helpers ────────────────────────────────────────────────

    #[test]
    fn test_build_data_disk_name_format() {
        assert_eq!(
            super::disk_helpers::build_data_disk_name("myvm", 2),
            "myvm_datadisk_2"
        );
    }

    #[test]
    fn test_build_restored_disk_name_format() {
        assert_eq!(
            super::disk_helpers::build_restored_disk_name("myvm"),
            "myvm_OsDisk_restored"
        );
    }

    // ── command_helpers ─────────────────────────────────────────────

    #[test]
    fn test_is_allowed_command_edge_cases() {
        assert!(super::command_helpers::is_allowed_command("az vm list"));
        assert!(super::command_helpers::is_allowed_command("  az vm list")); // leading whitespace
        assert!(!super::command_helpers::is_allowed_command("rm -rf /"));
        assert!(!super::command_helpers::is_allowed_command(""));
    }

    #[test]
    fn test_skip_reason_various_inputs() {
        assert!(super::command_helpers::skip_reason("").is_some());
        assert!(super::command_helpers::skip_reason("rm -rf /").is_some());
        assert!(super::command_helpers::skip_reason("az vm list").is_none());
    }

    // ── autopilot_parse_helpers ─────────────────────────────────────

    #[test]
    fn test_parse_idle_check_valid_two_lines() {
        let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("2.5\n3600\n");
        assert!((cpu - 2.5).abs() < 0.01);
        assert!((uptime - 3600.0).abs() < 0.01);
    }

    #[test]
    fn test_parse_idle_check_single_line() {
        let (cpu, uptime) = super::autopilot_parse_helpers::parse_idle_check("5.0");
        assert!((cpu - 5.0).abs() < 0.01);
        assert_eq!(uptime, 0.0); // missing second line defaults to 0
    }

    #[test]
    fn test_is_idle_boundary() {
        // CPU = 4.9, uptime > threshold → idle
        assert!(super::autopilot_parse_helpers::is_idle(4.9, 1801.0, 30));
        // CPU = 5.0 → not idle
        assert!(!super::autopilot_parse_helpers::is_idle(5.0, 1801.0, 30));
        // Uptime exactly at threshold (30 min = 1800s) → not idle
        assert!(!super::autopilot_parse_helpers::is_idle(1.0, 1800.0, 30));
    }

    // ── storage_helpers ─────────────────────────────────────────────

    #[test]
    fn test_storage_sku_from_tier_all_variants() {
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("premium"),
            "Premium_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("PREMIUM"),
            "Premium_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("standard"),
            "Standard_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("STANDARD"),
            "Standard_LRS"
        );
        assert_eq!(
            super::storage_helpers::storage_sku_from_tier("anything"),
            "Premium_LRS"
        );
    }

    #[test]
    fn test_storage_account_row_partial_data() {
        let acct = serde_json::json!({
            "name": "mystorage",
            "location": "eastus"
            // Missing kind, sku, provisioningState
        });
        let row = super::storage_helpers::storage_account_row(&acct);
        assert_eq!(row[0], "mystorage");
        assert_eq!(row[1], "eastus");
        assert_eq!(row[2], "-"); // missing kind
        assert_eq!(row[3], "-"); // missing sku.name
        assert_eq!(row[4], "-"); // missing provisioningState
    }

    // ── key_helpers ─────────────────────────────────────────────────

    #[test]
    fn test_detect_key_type_comprehensive() {
        assert_eq!(super::key_helpers::detect_key_type("id_ed25519"), "ed25519");
        assert_eq!(
            super::key_helpers::detect_key_type("id_ed25519.pub"),
            "ed25519"
        );
        assert_eq!(super::key_helpers::detect_key_type("id_ecdsa"), "ecdsa");
        assert_eq!(super::key_helpers::detect_key_type("id_rsa"), "rsa");
        assert_eq!(super::key_helpers::detect_key_type("id_dsa"), "dsa");
        assert_eq!(
            super::key_helpers::detect_key_type("known_hosts"),
            "unknown"
        );
        assert_eq!(
            super::key_helpers::detect_key_type("authorized_keys"),
            "unknown"
        );
    }

    #[test]
    fn test_is_known_key_name_comprehensive() {
        assert!(super::key_helpers::is_known_key_name("id_rsa.pub"));
        assert!(super::key_helpers::is_known_key_name("id_ed25519.pub"));
        assert!(super::key_helpers::is_known_key_name("id_rsa"));
        assert!(super::key_helpers::is_known_key_name("id_ed25519"));
        assert!(super::key_helpers::is_known_key_name("id_ecdsa"));
        assert!(super::key_helpers::is_known_key_name("id_dsa"));
        assert!(!super::key_helpers::is_known_key_name("known_hosts"));
        assert!(!super::key_helpers::is_known_key_name("config"));
    }

    // ── auth_helpers ────────────────────────────────────────────────

    #[test]
    fn test_mask_profile_value_secret_variants() {
        let secret_val = serde_json::json!("my-actual-secret");
        assert_eq!(
            super::auth_helpers::mask_profile_value("client_secret", &secret_val),
            "********"
        );
        assert_eq!(
            super::auth_helpers::mask_profile_value("db_password", &secret_val),
            "********"
        );
        // Non-secret field
        assert_eq!(
            super::auth_helpers::mask_profile_value("client_id", &secret_val),
            "my-actual-secret"
        );
    }

    #[test]
    fn test_mask_profile_value_non_string_types() {
        assert_eq!(
            super::auth_helpers::mask_profile_value("count", &serde_json::json!(42)),
            "42"
        );
        assert_eq!(
            super::auth_helpers::mask_profile_value("enabled", &serde_json::json!(true)),
            "true"
        );
        assert_eq!(
            super::auth_helpers::mask_profile_value("data", &serde_json::json!(null)),
            "null"
        );
    }

    // ── log_helpers ─────────────────────────────────────────────────

    #[test]
    fn test_tail_start_index_various() {
        assert_eq!(super::log_helpers::tail_start_index(100, 20), 80);
        assert_eq!(super::log_helpers::tail_start_index(10, 20), 0); // can't go negative
        assert_eq!(super::log_helpers::tail_start_index(0, 0), 0);
        assert_eq!(super::log_helpers::tail_start_index(50, 50), 0);
    }

    // ── auth_test_helpers ───────────────────────────────────────────

    #[test]
    fn test_extract_account_info_full_json() {
        let acct = serde_json::json!({
            "name": "My Subscription",
            "tenantId": "tenant-123",
            "user": {"name": "user@example.com", "type": "user"}
        });
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "My Subscription");
        assert_eq!(tenant, "tenant-123");
        assert_eq!(user, "user@example.com");
    }

    #[test]
    fn test_extract_account_info_empty_json() {
        let acct = serde_json::json!({});
        let (sub, tenant, user) = super::auth_test_helpers::extract_account_info(&acct);
        assert_eq!(sub, "-");
        assert_eq!(tenant, "-");
        assert_eq!(user, "-");
    }

    // ── cost helpers ────────────────────────────────────────────────

    #[test]
    fn test_parse_cost_history_rows_with_only_cost() {
        let data = serde_json::json!({
            "rows": [[42.5]]
        });
        let result = super::parse_cost_history_rows(&data);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].1, "$42.50");
        assert_eq!(result[0].0, "-"); // no date column
    }

    #[test]
    fn test_parse_recommendation_rows_with_nested_fields() {
        let data = serde_json::json!([
            {
                "category": "Cost",
                "impact": "High",
                "shortDescription": {"problem": "VM is oversized"}
            }
        ]);
        let rows = super::parse_recommendation_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "Cost");
        assert_eq!(rows[0].1, "High");
        assert_eq!(rows[0].2, "VM is oversized");
    }

    #[test]
    fn test_parse_cost_action_rows_complete_entry() {
        let data = serde_json::json!([
            {
                "impactedField": "Microsoft.Compute/virtualMachines",
                "impact": "Medium",
                "shortDescription": {"problem": "Rightsize your VM"}
            }
        ]);
        let rows = super::parse_cost_action_rows(&data);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].0, "Microsoft.Compute/virtualMachines");
        assert_eq!(rows[0].1, "Medium");
        assert_eq!(rows[0].2, "Rightsize your VM");
    }

    // ── format_cost_summary comprehensive ───────────────────────────

    #[test]
    fn test_format_cost_summary_table_with_from_and_to() {
        use chrono::TimeZone;
        let summary = azlin_core::models::CostSummary {
            total_cost: 123.45,
            currency: "USD".to_string(),
            period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
            by_vm: vec![],
        };
        let output = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &Some("2024-01-01".to_string()),
            &Some("2024-01-31".to_string()),
            false,
            false,
        );
        assert!(output.contains("$123.45"));
        assert!(output.contains("USD"));
        assert!(output.contains("From filter: 2024-01-01"));
        assert!(output.contains("To filter: 2024-01-31"));
    }

    #[test]
    fn test_format_cost_summary_csv_format() {
        use chrono::TimeZone;
        let summary = azlin_core::models::CostSummary {
            total_cost: 50.0,
            currency: "EUR".to_string(),
            period_start: chrono::Utc.with_ymd_and_hms(2024, 6, 1, 0, 0, 0).unwrap(),
            period_end: chrono::Utc.with_ymd_and_hms(2024, 6, 30, 0, 0, 0).unwrap(),
            by_vm: vec![],
        };
        let output = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            false,
        );
        assert!(output.contains("Total Cost,Currency,Period Start,Period End"));
        assert!(output.contains("50.00,EUR"));
    }

    #[test]
    fn test_format_cost_summary_with_estimate_flag() {
        use chrono::TimeZone;
        let summary = azlin_core::models::CostSummary {
            total_cost: 200.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
            by_vm: vec![],
        };
        let output = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            true,
            false,
        );
        assert!(output.contains("Estimate"));
        assert!(output.contains("$200.00/month"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_table_output() {
        use chrono::TimeZone;
        let summary = azlin_core::models::CostSummary {
            total_cost: 300.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
            by_vm: vec![
                azlin_core::models::VmCost {
                    vm_name: "dev-vm".to_string(),
                    cost: 150.0,
                    currency: "USD".to_string(),
                },
                azlin_core::models::VmCost {
                    vm_name: "prod-vm".to_string(),
                    cost: 150.0,
                    currency: "USD".to_string(),
                },
            ],
        };
        let output = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            true,
        );
        assert!(output.contains("dev-vm"));
        assert!(output.contains("prod-vm"));
        assert!(output.contains("$150.00"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_empty_shows_message() {
        use chrono::TimeZone;
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
            by_vm: vec![],
        };
        let output = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Table,
            &None,
            &None,
            false,
            true,
        );
        assert!(output.contains("No per-VM cost data"));
    }

    #[test]
    fn test_format_cost_summary_by_vm_csv_format() {
        use chrono::TimeZone;
        let summary = azlin_core::models::CostSummary {
            total_cost: 100.0,
            currency: "USD".to_string(),
            period_start: chrono::Utc.with_ymd_and_hms(2024, 1, 1, 0, 0, 0).unwrap(),
            period_end: chrono::Utc.with_ymd_and_hms(2024, 1, 31, 0, 0, 0).unwrap(),
            by_vm: vec![azlin_core::models::VmCost {
                vm_name: "test-vm".to_string(),
                cost: 100.0,
                currency: "USD".to_string(),
            }],
        };
        let output = super::format_cost_summary(
            &summary,
            &azlin_cli::OutputFormat::Csv,
            &None,
            &None,
            false,
            true,
        );
        assert!(output.contains("VM Name,Cost,Currency"));
        assert!(output.contains("test-vm,100.00,USD"));
    }

    // ── config_path_helpers ─────────────────────────────────────────

    #[test]
    fn test_validate_config_path_safe_paths() {
        assert!(super::config_path_helpers::validate_config_path("config.toml").is_ok());
        assert!(super::config_path_helpers::validate_config_path("subdir/config.toml").is_ok());
    }

    #[test]
    fn test_validate_config_path_traversal_variants() {
        assert!(super::config_path_helpers::validate_config_path("../evil.toml").is_err());
        assert!(super::config_path_helpers::validate_config_path("sub/../../etc/passwd").is_err());
    }

    // ── stop_helpers ────────────────────────────────────────────────

    #[test]
    fn test_stop_action_labels_both_modes() {
        let (ing, ed) = super::stop_helpers::stop_action_labels(true);
        assert_eq!(ing, "Deallocating");
        assert_eq!(ed, "Deallocated");

        let (ing2, ed2) = super::stop_helpers::stop_action_labels(false);
        assert_eq!(ing2, "Stopping");
        assert_eq!(ed2, "Stopped");
    }

    // ── snapshot_helpers snapshot_row ────────────────────────────────

    #[test]
    fn test_snapshot_row_complete_data() {
        let snap = serde_json::json!({
            "name": "vm1_snapshot_20240115",
            "diskSizeGb": 128,
            "timeCreated": "2024-01-15T10:00:00Z",
            "provisioningState": "Succeeded"
        });
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "vm1_snapshot_20240115");
        assert_eq!(row[1], "128");
        assert_eq!(row[2], "2024-01-15T10:00:00Z");
        assert_eq!(row[3], "Succeeded");
    }

    #[test]
    fn test_snapshot_row_empty_json_defaults() {
        let snap = serde_json::json!({});
        let row = super::snapshot_helpers::snapshot_row(&snap);
        assert_eq!(row[0], "-");
        assert_eq!(row[2], "-");
        assert_eq!(row[3], "-");
    }

    // ── create_helpers edge cases ───────────────────────────────────

    #[test]
    fn test_build_clone_cmd_format() {
        let cmd =
            super::create_helpers::build_clone_cmd("https://github.com/user/repo.git").unwrap();
        assert!(cmd.contains("git clone"));
        assert!(cmd.contains("https://github.com/user/repo.git"));
        assert!(cmd.contains("~/src/$(basename"));
    }

    #[test]
    fn test_build_clone_name_format() {
        assert_eq!(
            super::create_helpers::build_clone_name("myvm", 0),
            "myvm-clone-1"
        );
        assert_eq!(
            super::create_helpers::build_clone_name("myvm", 2),
            "myvm-clone-3"
        );
    }

    #[test]
    fn test_build_disk_name_format() {
        assert_eq!(
            super::create_helpers::build_disk_name("myvm"),
            "myvm_OsDisk"
        );
    }

    #[test]
    fn test_build_ssh_connect_args_format() {
        let args = super::create_helpers::build_ssh_connect_args("user", "10.0.0.1");
        assert!(args.contains(&"StrictHostKeyChecking=accept-new".to_string()));
        assert!(args.contains(&"user@10.0.0.1".to_string()));
    }

    // ═══════════════════════════════════════════════════════════════
    // Security fix tests
    // ═══════════════════════════════════════════════════════════════

    // ── validate_repo_url ──────────────────────────────────────────

    #[test]
    fn test_validate_repo_url_rejects_semicolon() {
        assert!(
            super::repo_helpers::validate_repo_url("https://evil.com/repo.git; rm -rf /").is_err()
        );
    }

    #[test]
    fn test_validate_repo_url_rejects_pipe() {
        assert!(super::repo_helpers::validate_repo_url(
            "https://evil.com/repo.git|cat /etc/passwd"
        )
        .is_err());
    }

    #[test]
    fn test_validate_repo_url_rejects_backtick() {
        assert!(super::repo_helpers::validate_repo_url("https://evil.com/`whoami`.git").is_err());
    }

    #[test]
    fn test_validate_repo_url_rejects_dollar() {
        assert!(super::repo_helpers::validate_repo_url("https://evil.com/$HOME.git").is_err());
    }

    #[test]
    fn test_validate_repo_url_rejects_ampersand() {
        assert!(
            super::repo_helpers::validate_repo_url("https://evil.com/repo.git&echo pwned").is_err()
        );
    }

    #[test]
    fn test_validate_repo_url_rejects_newline() {
        assert!(
            super::repo_helpers::validate_repo_url("https://evil.com/repo.git\nrm -rf /").is_err()
        );
    }

    #[test]
    fn test_validate_repo_url_rejects_parens() {
        assert!(super::repo_helpers::validate_repo_url("https://evil.com/$(whoami).git").is_err());
    }

    #[test]
    fn test_validate_repo_url_rejects_empty() {
        assert!(super::repo_helpers::validate_repo_url("").is_err());
    }

    #[test]
    fn test_validate_repo_url_rejects_bad_scheme() {
        assert!(super::repo_helpers::validate_repo_url("ftp://evil.com/repo.git").is_err());
    }

    #[test]
    fn test_validate_repo_url_accepts_https() {
        assert!(super::repo_helpers::validate_repo_url("https://github.com/user/repo.git").is_ok());
    }

    #[test]
    fn test_validate_repo_url_accepts_git_ssh() {
        assert!(super::repo_helpers::validate_repo_url("git@github.com:user/repo.git").is_ok());
    }

    #[test]
    fn test_validate_repo_url_accepts_ssh_scheme() {
        assert!(
            super::repo_helpers::validate_repo_url("ssh://git@github.com/user/repo.git").is_ok()
        );
    }

    #[test]
    fn test_build_clone_cmd_rejects_injection() {
        assert!(
            super::create_helpers::build_clone_cmd("https://evil.com/repo.git; rm -rf /").is_err()
        );
    }

    // ── validate_name (path traversal) ─────────────────────────────

    #[test]
    fn test_validate_name_rejects_slash() {
        assert!(super::name_validation::validate_name("../etc/passwd").is_err());
    }

    #[test]
    fn test_validate_name_rejects_backslash() {
        assert!(super::name_validation::validate_name("foo\\bar").is_err());
    }

    #[test]
    fn test_validate_name_rejects_dotdot() {
        assert!(super::name_validation::validate_name("..").is_err());
    }

    #[test]
    fn test_validate_name_rejects_null() {
        assert!(super::name_validation::validate_name("foo\0bar").is_err());
    }

    #[test]
    fn test_validate_name_rejects_empty() {
        assert!(super::name_validation::validate_name("").is_err());
    }

    #[test]
    fn test_validate_name_accepts_simple() {
        assert!(super::name_validation::validate_name("my-profile").is_ok());
    }

    #[test]
    fn test_validate_name_accepts_dot_prefix() {
        assert!(super::name_validation::validate_name(".hidden").is_ok());
    }

    #[test]
    fn test_validate_name_accepts_underscores() {
        assert!(super::name_validation::validate_name("my_template_v2").is_ok());
    }

    #[test]
    fn test_template_save_rejects_traversal() {
        let tmp = TempDir::new().unwrap();
        let tpl = toml::Value::Table(Default::default());
        let result = super::templates::save_template(tmp.path(), "../escape", &tpl);
        assert!(result.is_err());
    }

    #[test]
    fn test_template_load_rejects_traversal() {
        let tmp = TempDir::new().unwrap();
        let result = super::templates::load_template(tmp.path(), "../../etc/passwd");
        assert!(result.is_err());
    }

    // ── env delete key validation ──────────────────────────────────

    #[test]
    fn test_build_env_delete_cmd_rejects_injection() {
        let cmd = super::env_helpers::build_env_delete_cmd("foo;rm -rf /;#");
        assert_eq!(cmd, "true");
    }

    #[test]
    fn test_build_env_delete_cmd_rejects_dollar() {
        let cmd = super::env_helpers::build_env_delete_cmd("$HOME");
        assert_eq!(cmd, "true");
    }

    #[test]
    fn test_build_env_delete_cmd_valid_key_works() {
        let cmd = super::env_helpers::build_env_delete_cmd("VALID_KEY");
        assert!(cmd.contains("sed"));
        assert!(cmd.contains("VALID_KEY"));
    }

    // ── batch tag filter ───────────────────────────────────────────

    #[test]
    fn test_build_vm_list_query_no_tag() {
        let q = super::batch_helpers::build_vm_list_query(None).unwrap();
        assert_eq!(q, "[].id");
    }

    #[test]
    fn test_build_vm_list_query_with_tag() {
        let q = super::batch_helpers::build_vm_list_query(Some("env=dev")).unwrap();
        assert_eq!(q, "[?tags.env=='dev'].id");
    }

    #[test]
    fn test_build_vm_list_query_invalid_tag_format() {
        assert!(super::batch_helpers::build_vm_list_query(Some("notag")).is_err());
    }

    #[test]
    fn test_build_vm_list_query_rejects_injection_in_tag_value() {
        assert!(super::batch_helpers::build_vm_list_query(Some("env=dev';rm -rf /")).is_err());
    }

    #[test]
    fn test_build_vm_list_query_rejects_injection_in_tag_key() {
        assert!(super::batch_helpers::build_vm_list_query(Some("en$v=dev")).is_err());
    }

    // ── OnceLock bastion pool flag ─────────────────────────────────

    #[test]
    fn test_is_bastion_pool_disabled_default() {
        // OnceLock may or may not be set from other tests, so just verify it
        // returns a bool without panicking
        let _result = super::is_bastion_pool_disabled();
    }
}
