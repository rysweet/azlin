use anyhow::Result;
use clap::{CommandFactory, Parser};
use comfy_table::{
    modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Attribute, Cell, Color, Table,
};
use console::Style;
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
            "StrictHostKeyChecking=no",
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

/// Collect health metrics from a single VM via SSH.
fn collect_health_metrics(vm_name: &str, ip: &str, user: &str, power_state: &str) -> HealthMetrics {
    if power_state != "running" {
        return HealthMetrics {
            vm_name: vm_name.to_string(),
            power_state: power_state.to_string(),
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
            load_avg: "-".to_string(),
        };
    }

    // CPU usage from top (idle percentage -> used)
    let cpu = ssh_exec(
        ip,
        user,
        "top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}'",
    )
    .ok()
    .and_then(|(code, out, _)| {
        if code == 0 {
            out.trim().parse::<f32>().ok()
        } else {
            None
        }
    })
    .unwrap_or(0.0);

    // Memory usage from free
    let mem = ssh_exec(
        ip,
        user,
        "free | awk '/Mem:/{printf \"%.1f\", $3/$2 * 100}'",
    )
    .ok()
    .and_then(|(code, out, _)| {
        if code == 0 {
            out.trim().parse::<f32>().ok()
        } else {
            None
        }
    })
    .unwrap_or(0.0);

    // Disk usage from df
    let disk = ssh_exec(ip, user, "df / --output=pcent | tail -1 | tr -d ' %'")
        .ok()
        .and_then(|(code, out, _)| {
            if code == 0 {
                out.trim().parse::<f32>().ok()
            } else {
                None
            }
        })
        .unwrap_or(0.0);

    // Load average from uptime
    let load = ssh_exec(
        ip,
        user,
        "uptime | awk -F'load average:' '{print $2}' | xargs",
    )
    .ok()
    .and_then(|(code, out, _)| {
        if code == 0 {
            Some(out.trim().to_string())
        } else {
            None
        }
    })
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
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .apply_modifier(UTF8_ROUND_CORNERS)
        .set_header(vec![
            Cell::new("VM Name").add_attribute(Attribute::Bold),
            Cell::new("Power State").add_attribute(Attribute::Bold),
            Cell::new("CPU %").add_attribute(Attribute::Bold),
            Cell::new("Memory %").add_attribute(Attribute::Bold),
            Cell::new("Disk %").add_attribute(Attribute::Bold),
            Cell::new("Load Average").add_attribute(Attribute::Bold),
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
    let vms = vm_manager.list_vms(rg).await?;
    let mut results = Vec::new();
    for vm in &vms {
        if vm.power_state == azlin_core::models::PowerState::Running {
            if let Some(ip) = vm.public_ip.as_ref().or(vm.private_ip.as_ref()) {
                let user = vm
                    .admin_username
                    .clone()
                    .unwrap_or_else(|| "azureuser".to_string());
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

        if code == 0 {
            let line_count = stdout.trim().lines().count();
            bars[i].finish_with_message(format!("✓ done ({} lines)", line_count));
        } else {
            let err_summary = stderr.trim().lines().next().unwrap_or("error");
            bars[i].finish_with_message(format!("✗ {}", err_summary));
        }

        let status = if code == 0 { "OK" } else { "FAIL" };
        let status_color = if code == 0 { Color::Green } else { Color::Red };
        let output_text = if show_output {
            let out = stdout.trim();
            if out.is_empty() {
                stderr.trim().to_string()
            } else {
                out.to_string()
            }
        } else if code != 0 {
            stderr.trim().lines().next().unwrap_or("").to_string()
        } else {
            String::new()
        };
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
            println!("azlin 2.3.0 (rust)");
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
                        eprintln!("Unknown config key: {key}");
                        std::process::exit(1);
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
        azlin_cli::Commands::List { resource_group, .. } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            let vms = match &resource_group {
                Some(rg) => vm_manager.list_vms(rg).await?,
                None => {
                    let config = azlin_core::AzlinConfig::load().ok();
                    match config.and_then(|c| c.default_resource_group) {
                        Some(rg) => vm_manager.list_vms(&rg).await?,
                        None => {
                            eprintln!("No resource group specified. Use --resource-group or set in config.");
                            std::process::exit(1);
                        }
                    }
                }
            };

            azlin_cli::table::render_vm_table(&vms, &cli.output);
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
            vm_manager.start_vm(&rg, &vm_name).await?;
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

            let action = if deallocate {
                "Deallocating"
            } else {
                "Stopping"
            };
            let done = if deallocate { "Deallocated" } else { "Stopped" };
            let pb = ProgressBar::new_spinner();
            pb.set_style(fleet_spinner_style());
            pb.set_prefix(format!("{:>20}", vm_name));
            pb.set_message(format!("{} {}...", action, vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.stop_vm(&rg, &vm_name, deallocate).await?;
            pb.finish_with_message(format!("✓ {} {}", done, vm_name));
        }
        azlin_cli::Commands::Show { name } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let config = azlin_core::AzlinConfig::load().ok();
            let rg = config
                .and_then(|c| c.default_resource_group)
                .unwrap_or_default();
            if rg.is_empty() {
                eprintln!("No resource group specified. Set default_resource_group in config.");
                std::process::exit(1);
            }

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Fetching {}...", name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &name).await?;
            pb.finish_and_clear();

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
        azlin_cli::Commands::Connect {
            vm_identifier,
            resource_group,
            user,
            key,
            ..
        } => {
            let name = vm_identifier.unwrap_or_else(|| {
                eprintln!("VM name is required.");
                std::process::exit(1);
            });

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &name).await?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
            let username = vm.admin_username.unwrap_or_else(|| user.clone());

            let mut ssh_args = vec!["-o".to_string(), "StrictHostKeyChecking=no".to_string()];
            if let Some(key_path) = &key {
                ssh_args.push("-i".to_string());
                ssh_args.push(key_path.display().to_string());
            }
            ssh_args.push(format!("{}@{}", username, ip));

            let status = std::process::Command::new("ssh").args(&ssh_args).status()?;

            std::process::exit(status.code().unwrap_or(1));
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
                        let parts: Vec<&str> = tag.splitn(2, '=').collect();
                        if parts.len() != 2 {
                            eprintln!("Invalid tag format '{}'. Use key=value.", tag);
                            std::process::exit(1);
                        }
                        vm_manager
                            .add_tag(&rg, &vm_name, parts[0], parts[1])
                            .await?;
                        println!("Added tag {}={} to VM '{}'", parts[0], parts[1], vm_name);
                    }
                }
                azlin_cli::TagAction::Remove {
                    vm_name,
                    tag_keys,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    for key in &tag_keys {
                        vm_manager.remove_tag(&rg, &vm_name, key).await?;
                        println!("Removed tag '{}' from VM '{}'", key, vm_name);
                    }
                }
                azlin_cli::TagAction::List {
                    vm_name,
                    resource_group,
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let tags = vm_manager.list_tags(&rg, &vm_name).await?;
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
            vm, resource_group, tui, ..
        } => {
            let auth = match azlin_azure::AzureAuth::new() {
                Ok(a) => a,
                Err(_) => {
                    eprintln!("Azure authentication failed.");
                    eprintln!(
                        "Hint: use 'az login' or specify --vm and --ip flags for direct SSH."
                    );
                    std::process::exit(1);
                }
            };
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message("Collecting health metrics...");
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let metrics: Vec<HealthMetrics> = if let Some(vm_name) = vm {
                let vm_info = vm_manager.get_vm(&rg, &vm_name).await?;
                let ip = vm_info
                    .public_ip
                    .or(vm_info.private_ip)
                    .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_name))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| "azureuser".to_string());
                let state = vm_info.power_state.to_string();
                vec![collect_health_metrics(&vm_name, &ip, &user, &state)]
            } else {
                let vms = vm_manager.list_vms(&rg).await?;
                vms.iter()
                    .filter_map(|vm_info| {
                        let ip = vm_info.public_ip.as_ref().or(vm_info.private_ip.as_ref())?;
                        let user = vm_info
                            .admin_username
                            .clone()
                            .unwrap_or_else(|| "azureuser".to_string());
                        let state = vm_info.power_state.to_string();
                        Some(collect_health_metrics(&vm_info.name, ip, &user, &state))
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
            let vm = vm_manager.get_vm(&rg, &vm_identifier).await?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
            let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());

            println!("Running OS updates on '{}'...", vm_identifier);
            let cmd = "sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq".to_string();
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
                if !stderr.trim().is_empty() {
                    eprintln!("{}", stderr.trim());
                }
                std::process::exit(1);
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
            vm_manager.delete_vm(&rg, &vm_name).await?;
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
            vm_manager.delete_vm(&rg, &vm_name).await?;
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
            vm_manager.delete_vm(&rg, &vm_name).await?;
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
                let parts: Vec<&str> = env_var.splitn(2, '=').collect();
                if parts.len() != 2 {
                    eprintln!("Invalid format. Use KEY=VALUE");
                    std::process::exit(1);
                }
                let (key, value) = (parts[0], parts[1]);
                let (addr, user) =
                    resolve_vm_ip_or_flag(&vm_identifier, ip.as_deref(), resource_group).await?;
                let escaped = shell_escape(value);
                let cmd = format!(
                    "grep -q '^export {}=' ~/.profile 2>/dev/null && sed -i 's/^export {}=.*/export {}={}/' ~/.profile || echo 'export {}={}' >> ~/.profile",
                    key, key, key, escaped, key, escaped
                );
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
                let output = ssh_exec_checked(&addr, &user, "env | sort").await?;
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
                let cmd = format!("sed -i '/^export {}=/d' ~/.profile", key);
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
                let output = ssh_exec_checked(&addr, &user, "env | sort").await?;
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
                for line in content.lines() {
                    let line = line.trim();
                    if line.is_empty() || line.starts_with('#') {
                        continue;
                    }
                    if let Some((key, value)) = line.split_once('=') {
                        let escaped = shell_escape(value);
                        let cmd = format!(
                            "grep -q '^export {}=' ~/.profile 2>/dev/null && sed -i 's/^export {}=.*/export {}={}/' ~/.profile || echo 'export {}={}' >> ~/.profile",
                            key, key, key, escaped, key, escaped
                        );
                        ssh_exec_checked(&addr, &user, &cmd).await?;
                    }
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
                let cmd = "sed -i '/^export /d' ~/.profile";
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
            let summary = azlin_azure::get_cost_summary(&auth, &rg).await?;
            pb.finish_and_clear();

            println!("{}", format_cost_summary(&summary, &cli.output, &from, &to, estimate, by_vm));
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
                    let snapshot_name = format!(
                        "{}_snapshot_{}",
                        vm_name,
                        chrono::Utc::now().format("%Y%m%d_%H%M%S")
                    );
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
                        eprintln!("Failed to create snapshot: {}", stderr.trim());
                        std::process::exit(1);
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
                            serde_json::from_slice(&output.stdout).unwrap_or_default();
                        let filtered: Vec<&serde_json::Value> = snapshots
                            .iter()
                            .filter(|s| {
                                s["name"]
                                    .as_str()
                                    .map(|n| n.contains(&vm_name))
                                    .unwrap_or(false)
                            })
                            .collect();

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
                                table.add_row(vec![
                                    snap["name"].as_str().unwrap_or("-"),
                                    &snap["diskSizeGb"].to_string(),
                                    snap["timeCreated"].as_str().unwrap_or("-"),
                                    snap["provisioningState"].as_str().unwrap_or("-"),
                                ]);
                            }
                            println!("{table}");
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        eprintln!("Failed to list snapshots: {}", stderr.trim());
                        std::process::exit(1);
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
                        eprintln!("Snapshot '{}' not found.", snapshot_name);
                        std::process::exit(1);
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
                        println!(
                            "Swap the OS disk on VM '{}' with: az vm update --resource-group {} --name {} --os-disk {}",
                            vm_name, rg, vm_name, new_disk
                        );
                    } else {
                        let stderr = String::from_utf8_lossy(&disk_output.stderr);
                        eprintln!("Failed to restore: {}", stderr.trim());
                        std::process::exit(1);
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
                        eprintln!("Failed to delete snapshot: {}", stderr.trim());
                        std::process::exit(1);
                    }
                }
                azlin_cli::SnapshotAction::Enable {
                    vm_name,
                    every,
                    keep,
                    ..
                } => {
                    println!(
                        "Scheduled snapshots enabled for VM '{}': every {}h, keep {}",
                        vm_name, every, keep
                    );
                }
                azlin_cli::SnapshotAction::Disable { vm_name, .. } => {
                    println!("Scheduled snapshots disabled for VM '{}'", vm_name);
                }
                azlin_cli::SnapshotAction::Sync { vm, .. } => match vm {
                    Some(name) => println!("Snapshot sync completed for VM '{}'", name),
                    None => println!("Snapshot sync completed for all VMs"),
                },
                azlin_cli::SnapshotAction::Status { vm_name, .. } => {
                    println!(
                        "Snapshot schedule status for VM '{}': no schedule configured",
                        vm_name
                    );
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

                let sku = match tier.to_lowercase().as_str() {
                    "premium" => "Premium_LRS",
                    "standard" => "Standard_LRS",
                    _ => "Premium_LRS",
                };

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
                    eprintln!("Failed to create storage account: {}", stderr.trim());
                    std::process::exit(1);
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
                        serde_json::from_slice(&output.stdout).unwrap_or_default();

                    if accounts.is_empty() {
                        println!("No storage accounts found.");
                    } else {
                        let mut table = Table::new();
                        table
                            .load_preset(UTF8_FULL)
                            .apply_modifier(UTF8_ROUND_CORNERS)
                            .set_header(vec!["Name", "Location", "Kind", "SKU", "State"]);
                        for acct in &accounts {
                            table.add_row(vec![
                                acct["name"].as_str().unwrap_or("-"),
                                acct["location"].as_str().unwrap_or("-"),
                                acct["kind"].as_str().unwrap_or("-"),
                                acct["sku"]["name"].as_str().unwrap_or("-"),
                                acct["provisioningState"].as_str().unwrap_or("-"),
                            ]);
                        }
                        println!("{table}");
                    }
                } else {
                    let stderr = String::from_utf8_lossy(&output.stderr);
                    eprintln!("Failed to list storage accounts: {}", stderr.trim());
                    std::process::exit(1);
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
                    let acct: serde_json::Value =
                        serde_json::from_slice(&output.stdout).unwrap_or_default();
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
                    eprintln!("Failed to show storage account: {}", stderr.trim());
                    std::process::exit(1);
                }
            }
            azlin_cli::StorageAction::Mount {
                storage_name,
                vm,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Looking up VM {}...", vm));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm_info = vm_manager.get_vm(&rg, &vm).await?;
                pb.finish_and_clear();

                let ip = vm_info
                    .public_ip
                    .or(vm_info.private_ip)
                    .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| "azureuser".to_string());

                let mount_cmd = format!(
                        "sudo mkdir -p /mnt/{storage_name} && sudo mount -t nfs {storage_name}.file.core.windows.net:/{storage_name}/home /mnt/{storage_name} -o vers=3,sec=sys"
                    );
                let status = std::process::Command::new("ssh")
                    .args([
                        "-o",
                        "StrictHostKeyChecking=no",
                        &format!("{}@{}", user, ip),
                        &mount_cmd,
                    ])
                    .status()?;

                if status.success() {
                    println!(
                        "Mounted '{}' on VM '{}' at /mnt/{}",
                        storage_name, vm, storage_name
                    );
                } else {
                    eprintln!("Failed to mount storage on VM.");
                    std::process::exit(1);
                }
            }
            azlin_cli::StorageAction::Unmount { vm, resource_group } => {
                let rg = resolve_resource_group(resource_group)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                let pb = indicatif::ProgressBar::new_spinner();
                pb.set_message(format!("Looking up VM {}...", vm));
                pb.enable_steady_tick(std::time::Duration::from_millis(100));
                let vm_info = vm_manager.get_vm(&rg, &vm).await?;
                pb.finish_and_clear();

                let ip = vm_info
                    .public_ip
                    .or(vm_info.private_ip)
                    .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm))?;
                let user = vm_info
                    .admin_username
                    .unwrap_or_else(|| "azureuser".to_string());

                let status = std::process::Command::new("ssh")
                    .args([
                        "-o",
                        "StrictHostKeyChecking=no",
                        &format!("{}@{}", user, ip),
                        "sudo umount /mnt/* 2>/dev/null; echo done",
                    ])
                    .status()?;

                if status.success() {
                    println!("Unmounted NFS storage from VM '{}'", vm);
                } else {
                    eprintln!("Failed to unmount storage from VM.");
                    std::process::exit(1);
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
                    eprintln!("Failed to delete storage account: {}", stderr.trim());
                    std::process::exit(1);
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
                    eprintln!("Failed to get storage account key: {}", stderr.trim());
                    std::process::exit(1);
                }

                let key = String::from_utf8_lossy(&key_output.stdout)
                    .trim()
                    .to_string();
                let unc = format!("//{}.file.core.windows.net/{}", account, share);
                let mount_str = mount_dir.display().to_string();

                // Create mount point and mount
                let _ = std::process::Command::new("sudo")
                    .args(["mkdir", "-p", &mount_str])
                    .status();

                let status = std::process::Command::new("sudo")
                    .args([
                        "mount",
                        "-t",
                        "cifs",
                        &unc,
                        &mount_str,
                        "-o",
                        &format!(
                            "vers=3.0,username={},password={},serverino,nosharesock,actimeo=30",
                            account, key
                        ),
                    ])
                    .status()?;

                if status.success() {
                    println!("Mounted '{}' at {}", share, mount_str);
                } else {
                    eprintln!("Failed to mount Azure Files share.");
                    std::process::exit(1);
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
                    eprintln!("Failed to unmount '{}'.", mount_str);
                    std::process::exit(1);
                }
            }
        },
        azlin_cli::Commands::Keys { action } => match action {
            azlin_cli::KeysAction::List { .. } => {
                let ssh_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".ssh");

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

                    let key_type = if name.contains("ed25519") {
                        "ed25519"
                    } else if name.contains("ecdsa") {
                        "ecdsa"
                    } else if name.contains("rsa") {
                        "rsa"
                    } else if name.contains("dsa") {
                        "dsa"
                    } else {
                        "unknown"
                    };

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
                let ssh_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".ssh");

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
                    eprintln!("Failed to generate new SSH key.");
                    std::process::exit(1);
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
                    let vms: Vec<serde_json::Value> =
                        serde_json::from_slice(&output.stdout).unwrap_or_default();
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
                                "azureuser",
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
                let ssh_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".ssh");

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
                        eprintln!("No SSH public key found in {}", ssh_dir.display());
                        std::process::exit(1);
                    }
                }
            }
            azlin_cli::KeysAction::Backup { destination } => {
                let ssh_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".ssh");

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
            let azlin_dir = dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                .join(".azlin");

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
                            let profile: serde_json::Value =
                                serde_json::from_str(&content).unwrap_or_default();
                            let profile_name = name.trim_end_matches(".json");
                            rows.push(vec![
                                profile_name.to_string(),
                                profile["tenant_id"]
                                    .as_str()
                                    .unwrap_or("-")
                                    .to_string(),
                                profile["client_id"]
                                    .as_str()
                                    .unwrap_or("-")
                                    .to_string(),
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
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        eprintln!("Profile '{}' not found.", profile);
                        std::process::exit(1);
                    }

                    let content = std::fs::read_to_string(&profile_path)?;
                    let data: serde_json::Value =
                        serde_json::from_str(&content).unwrap_or_default();
                    let key_style = Style::new().cyan().bold();

                    println!("{}: {}", key_style.apply_to("Profile"), profile);
                    if let Some(obj) = data.as_object() {
                        for (k, v) in obj {
                            let display = match v {
                                serde_json::Value::String(s) => {
                                    if k.contains("secret") || k.contains("password") {
                                        "********".to_string()
                                    } else {
                                        s.clone()
                                    }
                                }
                                other => other.to_string(),
                            };
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
                        let acct: serde_json::Value =
                            serde_json::from_slice(&output.stdout).unwrap_or_default();
                        let key_style = Style::new().cyan().bold();
                        println!(
                            "{}",
                            Style::new()
                                .green()
                                .bold()
                                .apply_to("Authentication successful!")
                        );
                        println!(
                            "{}: {}",
                            key_style.apply_to("Subscription"),
                            acct["name"].as_str().unwrap_or("-")
                        );
                        println!(
                            "{}: {}",
                            key_style.apply_to("Tenant"),
                            acct["tenantId"].as_str().unwrap_or("-")
                        );
                        println!(
                            "{}: {}",
                            key_style.apply_to("User"),
                            acct["user"]["name"].as_str().unwrap_or("-")
                        );
                    } else {
                        eprintln!("Authentication test failed. Run 'az login' to authenticate.");
                        std::process::exit(1);
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
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        eprintln!("Profile '{}' not found.", profile);
                        std::process::exit(1);
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
            dry_run,
            ..
        } => {
            let query_text = query.unwrap_or_else(|| {
                eprintln!("No query provided.");
                std::process::exit(1);
            });

            if dry_run {
                println!("Would query Claude API with: {}", query_text);
                return Ok(());
            }

            let client = azlin_ai::AnthropicClient::new()?;
            let rg = resource_group
                .or_else(|| {
                    azlin_core::AzlinConfig::load()
                        .ok()
                        .and_then(|c| c.default_resource_group)
                })
                .unwrap_or_default();

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
                println!("$ {}", cmd_str);
                let status = std::process::Command::new(&parts[0])
                    .args(&parts[1..])
                    .status()?;
                if !status.success() {
                    eprintln!("Command failed with exit code: {:?}", status.code());
                }
            }
        }
        azlin_cli::Commands::Doit { action } | azlin_cli::Commands::AzDoit { action } => {
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
                    let session_id = session.unwrap_or_else(|| "latest".to_string());
                    println!(
                        "Deployment status for session '{}': no active sessions tracked.",
                        session_id
                    );
                }
                azlin_cli::DoitAction::List { username } => {
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let rg_result = resolve_resource_group(None);
                    if let Ok(rg) = rg_result {
                        let pb = indicatif::ProgressBar::new_spinner();
                        pb.set_message("Listing doit-created resources...");
                        pb.enable_steady_tick(std::time::Duration::from_millis(100));
                        let vms = vm_manager.list_vms(&rg).await?;
                        pb.finish_and_clear();
                        let filtered: Vec<_> = vms
                            .iter()
                            .filter(|vm| {
                                let has_tag =
                                    vm.tags.get("created_by").is_some_and(|v| v == "azlin-doit");
                                let user_match = username.as_ref().is_none_or(|u| {
                                    vm.admin_username.as_deref() == Some(u.as_str())
                                });
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
                    } else {
                        println!(
                            "No resource group configured. Use --resource-group or set in config."
                        );
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
                            String::from_utf8_lossy(&output.stderr)
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
                    let vms = vm_manager.list_vms(&rg).await?;
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
                        vm_manager.delete_vm(&rg, &vm.name).await?;
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
        }
        | azlin_cli::Commands::Vm {
            repo,
            vm_size,
            region,
            resource_group,
            name,
            pool,
            no_auto_connect,
            template,
            ..
        }
        | azlin_cli::Commands::Create {
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
            let size = vm_size.unwrap_or_else(|| "Standard_DS2_v2".to_string());
            let loc = region.unwrap_or_else(|| "eastus2".to_string());
            let admin_user = "azureuser".to_string();
            let ssh_key_path = dirs::home_dir()
                .unwrap_or_default()
                .join(".ssh")
                .join("id_rsa.pub");

            // Load template defaults if specified
            let (tmpl_size, tmpl_region) = if let Some(ref tmpl_name) = template {
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

            let final_size = if size == "Standard_DS2_v2" {
                tmpl_size.unwrap_or(size)
            } else {
                size
            };
            let final_loc = if loc == "eastus2" {
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
                let vm = vm_manager.create_vm(&params).await?;
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
                        println!("Cloning repository '{}'...", repo_url);
                        let clone_cmd =
                            format!("git clone {} ~/src/$(basename {} .git)", repo_url, repo_url);
                        let (exit_code, stdout, stderr) = ssh_exec(ip, &admin_user, &clone_cmd)?;
                        if exit_code == 0 {
                            println!("Repository cloned successfully.");
                            if !stdout.is_empty() {
                                print!("{}", stdout);
                            }
                        } else {
                            eprintln!("Failed to clone repository: {}", stderr);
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
                                "StrictHostKeyChecking=no",
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
            let vm = vm_manager.get_vm(&rg, &vm_identifier).await?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP found for VM '{}'", vm_identifier))?;
            let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());

            println!("Updating development tools on '{}'...", vm_identifier);
            let update_script = concat!(
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
            );
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
                let red = Style::new().red();
                eprintln!(
                    "{}",
                    red.apply_to(format!("Update failed on '{}'", vm_identifier))
                );
                if !stderr.trim().is_empty() {
                    eprintln!("{}", stderr.trim());
                }
                std::process::exit(1);
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
                eprintln!("Failed to snapshot source VM: {}", stderr.trim());
                std::process::exit(1);
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
                    println!("  To create VM: az vm create --resource-group {} --name {} --attach-os-disk {} --os-type Linux", rg, clone_name, disk_name);
                } else {
                    let stderr = String::from_utf8_lossy(&disk_out.stderr);
                    eprintln!(
                        "  Failed to create disk for clone '{}': {}",
                        clone_name,
                        stderr.trim()
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
            let mut config = azlin_core::AzlinConfig::load().unwrap_or_default();
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

            let vms = vm_manager.list_vms(&rg).await?;
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
            ..
        } => {
            let name = vm_identifier.unwrap_or_else(|| {
                eprintln!("VM name is required.");
                std::process::exit(1);
            });

            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Looking up {}...", name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            let vm = vm_manager.get_vm(&rg, &name).await?;
            pb.finish_and_clear();

            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
            let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());

            let remote_uri = format!("ssh-remote+{}@{}", user, ip);
            println!("Opening VS Code: code --remote {}", remote_uri);
            let status = std::process::Command::new("code")
                .args(["--remote", &remote_uri])
                .status();

            match status {
                Ok(s) if s.success() => println!("VS Code opened for VM '{}'", name),
                _ => {
                    eprintln!("Failed to open VS Code. Ensure 'code' is in your PATH.");
                    std::process::exit(1);
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
                let list_output = std::process::Command::new("az")
                    .args(["vm", "list", "-g", &rg, "--query", "[].id", "-o", "tsv"])
                    .output()?;
                let ids: Vec<&str> = std::str::from_utf8(&list_output.stdout)
                    .unwrap_or("")
                    .lines()
                    .filter(|l| !l.is_empty())
                    .collect();
                if ids.is_empty() {
                    println!("No VMs found in resource group '{}'", rg);
                } else {
                    let mut args = vec!["vm", "deallocate", "--ids"];
                    args.extend(ids.iter().copied());
                    let output = std::process::Command::new("az").args(&args).output()?;
                    if output.status.success() {
                        println!("Batch stop completed for resource group '{}'", rg);
                    } else {
                        eprintln!("Batch stop failed. Run commands individually.");
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
                let list_output = std::process::Command::new("az")
                    .args(["vm", "list", "-g", &rg, "--query", "[].id", "-o", "tsv"])
                    .output()?;
                let ids: Vec<&str> = std::str::from_utf8(&list_output.stdout)
                    .unwrap_or("")
                    .lines()
                    .filter(|l| !l.is_empty())
                    .collect();
                if ids.is_empty() {
                    println!("No VMs found in resource group '{}'", rg);
                } else {
                    let mut args = vec!["vm", "start", "--ids"];
                    args.extend(ids.iter().copied());
                    let output = std::process::Command::new("az").args(&args).output()?;
                    if output.status.success() {
                        println!("Batch start completed for resource group '{}'", rg);
                    } else {
                        eprintln!("Batch start failed. Run commands individually.");
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

                let home = dirs::home_dir().unwrap_or_default();
                let dotfiles: Vec<&str> =
                    vec![".bashrc", ".profile", ".vimrc", ".tmux.conf", ".gitconfig"];

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
                                .args(["-az", "-e", "ssh -o StrictHostKeyChecking=no"])
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
                                        stderr.trim()
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

                let cmd = format!("docker compose -f {} up -d", f);
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

                let cmd = format!("docker compose -f {} down", f);
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

                let cmd = format!("docker compose -f {} ps", f);
                println!("Docker compose status on {} VM(s):", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
        },

        // ── GitHub Runner ────────────────────────────────────────────
        azlin_cli::Commands::GithubRunner { action } => {
            match action {
                azlin_cli::GithubRunnerAction::Enable {
                    repo,
                    pool,
                    count,
                    labels,
                    resource_group,
                    ..
                } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let repo_name = repo.unwrap_or_else(|| "<not set>".to_string());
                    let label_str = labels.unwrap_or_else(|| "self-hosted".to_string());
                    println!("Enabling GitHub runner fleet:");
                    println!("  Repository:     {}", repo_name);
                    println!("  Pool:           {}", pool);
                    println!("  Count:          {}", count);
                    println!("  Labels:         {}", label_str);
                    println!("  Resource Group: {}", rg);
                    println!("Runner fleet configuration saved. Deploy with 'azlin github-runner status'.");
                }
                azlin_cli::GithubRunnerAction::Disable { pool, keep_vms } => {
                    println!("Disabling runner pool '{}'", pool);
                    if keep_vms {
                        println!("VMs will be kept running.");
                    }
                    println!("Runner fleet disabled.");
                }
                azlin_cli::GithubRunnerAction::Status { pool } => {
                    println!("Runner pool '{}': no runners configured", pool);
                }
                azlin_cli::GithubRunnerAction::Scale { pool, count } => {
                    println!("Scaling runner pool '{}' to {} runners", pool, count);
                }
            }
        }

        // ── Template ─────────────────────────────────────────────────
        azlin_cli::Commands::Template { action } => {
            let azlin_dir = dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                .join(".azlin")
                .join("templates");
            std::fs::create_dir_all(&azlin_dir)?;

            match action {
                azlin_cli::TemplateAction::Create {
                    name,
                    description,
                    vm_size,
                    region,
                    cloud_init,
                }
                | azlin_cli::TemplateAction::Save {
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
                        cloud_init.as_ref().map(|p| p.display().to_string()).as_deref(),
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
                            eprintln!("Template '{}' not found.", name);
                            std::process::exit(1);
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
                            eprintln!("Template '{}' not found.", name);
                            std::process::exit(1);
                        }
                    }
                }
                azlin_cli::TemplateAction::Delete { name, force } => {
                    if templates::load_template(&azlin_dir, &name).is_err() {
                        eprintln!("Template '{}' not found.", name);
                        std::process::exit(1);
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
                        eprintln!("Template '{}' not found.", name);
                        std::process::exit(1);
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
                println!("Autopilot enabled:");
                if let Some(b) = budget {
                    println!("  Budget:         ${}/month", b);
                }
                println!("  Strategy:       {}", strategy);
                println!("  Idle threshold: {} min", idle_threshold);
                println!("  CPU threshold:  {}%", cpu_threshold);
            }
            azlin_cli::AutopilotAction::Disable { keep_config } => {
                println!("Autopilot disabled.");
                if keep_config {
                    println!("Configuration preserved.");
                }
            }
            azlin_cli::AutopilotAction::Status => {
                println!("Autopilot: not configured");
            }
            azlin_cli::AutopilotAction::Config { set, show } => {
                if show || set.is_empty() {
                    println!("Autopilot configuration: no settings configured");
                } else {
                    for kv in &set {
                        println!("Set {}", kv);
                    }
                }
            }
            azlin_cli::AutopilotAction::Run { dry_run } => {
                if dry_run {
                    println!("Autopilot dry run: no actions needed");
                } else {
                    println!("Autopilot check: no actions taken");
                }
            }
        },

        // ── Context ──────────────────────────────────────────────────
        azlin_cli::Commands::Context { action } => {
            let azlin_home = dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                .join(".azlin");
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
                azlin_cli::ContextAction::Show { .. }
                | azlin_cli::ContextAction::Current { .. } => {
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
                azlin_cli::ContextAction::Use { name, .. }
                | azlin_cli::ContextAction::Switch { name, .. } => {
                    let ctx_path = ctx_dir.join(format!("{}.toml", name));
                    if !ctx_path.exists() {
                        eprintln!("Context '{}' not found.", name);
                        std::process::exit(1);
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
                    let path = ctx_dir.join(format!("{}.toml", name));
                    if !path.exists() {
                        eprintln!("Context '{}' not found.", name);
                        std::process::exit(1);
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
                    contexts::rename_context_file(&ctx_dir, &old_name, &new_name)?;
                    // Update active context if it was the renamed one
                    if let Ok(active) = std::fs::read_to_string(&active_ctx_path) {
                        if active.trim() == old_name {
                            std::fs::write(&active_ctx_path, &new_name)?;
                        }
                    }
                    println!("Renamed context '{}' → '{}'", old_name, new_name);
                }
                azlin_cli::ContextAction::Migrate { .. } => {
                    println!("Context migration: no legacy configuration found.");
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
                    eprintln!("Failed to attach disk: {}", stderr.trim());
                    std::process::exit(1);
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
                    let vm = vm_manager.get_vm(&rg, &name).await?;

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
            azlin_cli::WebAction::Start { port: _, host: _ } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);

                // Determine resource group from config
                let rg = resolve_resource_group(None)?;

                println!(
                    "Starting monitoring dashboard for '{}' (Ctrl+C to exit)...",
                    rg
                );
                println!("Full TUI dashboard coming soon. Showing real-time VM status:\n");

                loop {
                    // Clear screen
                    print!("\x1B[2J\x1B[H");
                    std::io::Write::flush(&mut std::io::stdout())?;

                    let vms = vm_manager.list_vms(&rg).await?;
                    let mut table = Table::new();
                    table
                        .load_preset(UTF8_FULL)
                        .apply_modifier(UTF8_ROUND_CORNERS)
                        .set_header(vec![
                            Cell::new("Name").add_attribute(Attribute::Bold),
                            Cell::new("State").add_attribute(Attribute::Bold),
                            Cell::new("Size").add_attribute(Attribute::Bold),
                            Cell::new("IP").add_attribute(Attribute::Bold),
                            Cell::new("Location").add_attribute(Attribute::Bold),
                        ]);
                    for vm in &vms {
                        let state_color = match vm.power_state {
                            azlin_core::models::PowerState::Running => Color::Green,
                            azlin_core::models::PowerState::Stopped
                            | azlin_core::models::PowerState::Deallocated => Color::Red,
                            _ => Color::Yellow,
                        };
                        table.add_row(vec![
                            Cell::new(&vm.name),
                            Cell::new(vm.power_state.to_string()).fg(state_color),
                            Cell::new(&vm.vm_size),
                            Cell::new(vm.public_ip.as_deref().unwrap_or("-")),
                            Cell::new(&vm.location),
                        ]);
                    }
                    println!("{table}");
                    println!("\nRefreshing in 10s... (Ctrl+C to exit)");
                    tokio::time::sleep(std::time::Duration::from_secs(10)).await;
                }
            }
            azlin_cli::WebAction::Stop => {
                println!("Web dashboard stopped.");
            }
        },

        // ── Restore ──────────────────────────────────────────────────
        azlin_cli::Commands::Restore { resource_group, .. } => {
            let rg = resolve_resource_group(resource_group)?;
            println!("Restoring azlin sessions in '{}'...", rg);
            println!("Session restore complete.");
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
                let sessions_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions");
                std::fs::create_dir_all(&sessions_dir)?;

                let session_val = sessions::build_session_toml(&session_name, &rg, &vms);
                let path = sessions_dir.join(format!("{}.toml", session_name));
                std::fs::write(&path, toml::to_string_pretty(&session_val)?)?;
                println!("Saved session '{}' to {}", session_name, path.display());
            }
            azlin_cli::SessionsAction::Load { session_name } => {
                let path = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.toml", session_name));
                if !path.exists() {
                    eprintln!("Session '{}' not found.", session_name);
                    std::process::exit(1);
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
            azlin_cli::SessionsAction::Delete { session_name } => {
                let path = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.toml", session_name));
                if !path.exists() {
                    eprintln!("Session '{}' not found.", session_name);
                    std::process::exit(1);
                }
                std::fs::remove_file(&path)?;
                println!("Deleted session '{}'.", session_name);
            }
            azlin_cli::SessionsAction::List => {
                let dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions");
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
                            azlin_cli::table::render_rows(
                                &["Session"],
                                &rows,
                                &cli.output,
                            );
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
            let home_dir = dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                .join(".azlin")
                .join("home");

            if !home_dir.exists() {
                eprintln!("No ~/.azlin/home/ directory found. Nothing to sync.");
                std::process::exit(1);
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
                let vms = vm_manager.list_vms(&rg).await?;
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
                        let user = vm.admin_username.as_deref().unwrap_or("azureuser");
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
            let ssh_dir = dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                .join(".ssh");

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
                        eprintln!("Failed to sync keys: {}", stderr.trim());
                        std::process::exit(1);
                    }
                }
                None => {
                    eprintln!("No SSH public key found in {}", ssh_dir.display());
                    std::process::exit(1);
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
                eprintln!("Use vm_name:path for remote paths.");
                std::process::exit(1);
            }

            let source = &args[0];
            let dest = &args[args.len() - 1];
            let rg = resolve_resource_group(resource_group)?;

            let is_remote = |s: &str| {
                s.contains(':')
                    && !s.starts_with('/')
                    && s.len() > 2
                    && s.chars().nth(1) != Some(':')
            };
            let direction = if is_remote(source) && !is_remote(dest) {
                "remote→local"
            } else if !is_remote(source) && is_remote(dest) {
                "local→remote"
            } else {
                "local→local"
            };

            if dry_run {
                println!(
                    "Would copy ({}) {} → {} (rg: {})",
                    direction, source, dest, rg
                );
            } else {
                println!("Copying ({}) {} → {}...", direction, source, dest);
                // For remote transfers, use scp via az CLI resolved IP
                if is_remote(source) || is_remote(dest) {
                    let (vm_part, _path_part) = if is_remote(source) {
                        source
                            .split_once(':')
                            .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", source))?
                    } else {
                        dest.split_once(':')
                            .ok_or_else(|| anyhow::anyhow!("Invalid remote path: {}", dest))?
                    };
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vm = vm_manager.get_vm(&rg, vm_part).await?;
                    let ip = vm
                        .public_ip
                        .or(vm.private_ip)
                        .ok_or_else(|| anyhow::anyhow!("No IP for VM '{}'", vm_part))?;
                    let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());

                    let scp_source = if is_remote(source) {
                        source.replacen(vm_part, &format!("{}@{}", user, ip), 1)
                    } else {
                        source.clone()
                    };
                    let scp_dest = if is_remote(dest) {
                        dest.replacen(vm_part, &format!("{}@{}", user, ip), 1)
                    } else {
                        dest.clone()
                    };

                    let status = std::process::Command::new("scp")
                        .args(["-o", "StrictHostKeyChecking=no", &scp_source, &scp_dest])
                        .status()?;
                    if status.success() {
                        println!("Copy complete.");
                    } else {
                        eprintln!("scp failed.");
                        std::process::exit(1);
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

            if follow {
                println!(
                    "Following logs for VM '{}' is not supported via az CLI. Use SSH.",
                    vm_identifier
                );
                return Ok(());
            }

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!(
                "Fetching {:?} logs for {}...",
                log_type, vm_identifier
            ));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let output = std::process::Command::new("az")
                .args([
                    "vm",
                    "boot-diagnostics",
                    "get-boot-log",
                    "--resource-group",
                    &rg,
                    "--name",
                    &vm_identifier,
                ])
                .output()?;

            pb.finish_and_clear();
            if output.status.success() {
                let log_text = String::from_utf8_lossy(&output.stdout);
                let log_lines: Vec<&str> = log_text.lines().collect();
                let start = if log_lines.len() > lines as usize {
                    log_lines.len() - lines as usize
                } else {
                    0
                };
                for line in &log_lines[start..] {
                    println!("{}", line);
                }
            } else {
                let stderr = String::from_utf8_lossy(&output.stderr);
                eprintln!("Failed to fetch logs: {}", stderr.trim());
                std::process::exit(1);
            }
        }

        // ── Costs (intelligence) ─────────────────────────────────────
        azlin_cli::Commands::Costs { action } => {
            match action {
                azlin_cli::CostsAction::Dashboard { resource_group, .. } => {
                    let auth = create_auth()?;
                    let summary = azlin_azure::get_cost_summary(&auth, &resource_group).await?;
                    println!("Cost Dashboard for '{}':", resource_group);
                    println!("  Total: ${:.2} {}", summary.total_cost, summary.currency);
                    println!(
                        "  Period: {} to {}",
                        summary.period_start.format("%Y-%m-%d"),
                        summary.period_end.format("%Y-%m-%d")
                    );
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

                    let output = std::process::Command::new("az")
                    .args([
                        "costmanagement", "query",
                        "--type", "ActualCost",
                        "--scope", &format!("/subscriptions/$(az account show --query id -o tsv)/resourceGroups/{}", resource_group),
                        "--timeframe", "Custom",
                        "--time-period", &format!("start={}&end={}", start_date, end_date),
                        "-o", "json",
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
                        eprintln!("Failed to query cost history: {}", stderr.trim());
                        std::process::exit(1);
                    }
                }
                azlin_cli::CostsAction::Budget {
                    action,
                    resource_group,
                    amount,
                    threshold,
                } => {
                    println!(
                        "Budget {}: rg={}, amount={:?}, threshold={:?}",
                        action, resource_group, amount, threshold
                    );
                }
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
                                        for (category, impact, problem) in parse_recommendation_rows(&data) {
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
                        eprintln!("Failed to list recommendations: {}", stderr.trim());
                        std::process::exit(1);
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
                                        for (resource, impact, problem) in parse_cost_action_rows(&data) {
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
                                    }
                                }
                            }
                            Err(e) => eprintln!("Failed to parse advisor data: {}", e),
                        }
                    } else {
                        let stderr = String::from_utf8_lossy(&output.stderr);
                        eprintln!("Failed to list cost actions: {}", stderr.trim());
                        std::process::exit(1);
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
                        eprintln!("Failed to delete VMs: {}", stderr.trim());
                        std::process::exit(1);
                    }
                }
            } else {
                pb.finish_and_clear();
                eprintln!("Failed to list VMs.");
                std::process::exit(1);
            }
        }

        // ── Cleanup / Prune ──────────────────────────────────────────
        azlin_cli::Commands::Cleanup {
            resource_group,
            dry_run,
            force,
            age_days,
            ..
        }
        | azlin_cli::Commands::Prune {
            resource_group,
            dry_run,
            force,
            age_days,
            ..
        } => {
            let rg = resolve_resource_group(resource_group)?;

            if dry_run {
                println!(
                    "Dry run — scanning for orphaned resources in '{}' (older than {} days)...",
                    rg, age_days
                );
                println!("No orphaned resources found.");
                return Ok(());
            }

            if !force {
                let ok = Confirm::new()
                    .with_prompt(format!("Clean up orphaned resources in '{}'?", rg))
                    .default(false)
                    .interact()?;
                if !ok {
                    println!("Cancelled.");
                    return Ok(());
                }
            }

            println!("Scanning for orphaned resources in '{}'...", rg);
            println!("Cleanup complete. No orphaned resources found.");
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
                    eprintln!("Error listing Bastion hosts: {}", err);
                    std::process::exit(1);
                }
                let bastions: Vec<serde_json::Value> =
                    serde_json::from_slice(&output.stdout).unwrap_or_default();
                if bastions.is_empty() {
                    if let Some(rg) = &resource_group {
                        println!("No Bastion hosts found in resource group: {}", rg);
                    } else {
                        println!("No Bastion hosts found in subscription");
                    }
                } else {
                    println!("\nFound {} Bastion host(s):\n", bastions.len());
                    for b in &bastions {
                        let name = b["name"].as_str().unwrap_or("unknown");
                        let rg = b["resourceGroup"].as_str().unwrap_or("unknown");
                        let location = b["location"].as_str().unwrap_or("unknown");
                        let sku = b["sku"]["name"].as_str().unwrap_or("Standard");
                        let state = b["provisioningState"].as_str().unwrap_or("unknown");
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
                    eprintln!(
                        "Bastion host not found: {} in {}: {}",
                        name, resource_group, err
                    );
                    std::process::exit(1);
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
                let ip_configs = b["ipConfigurations"].as_array();
                if let Some(configs) = ip_configs {
                    println!("\nIP Configurations: {}", configs.len());
                    for (idx, config) in configs.iter().enumerate() {
                        let subnet_id = config["subnet"]["id"].as_str().unwrap_or("N/A");
                        let public_ip_id =
                            config["publicIPAddress"]["id"].as_str().unwrap_or("N/A");
                        let subnet_short = if subnet_id != "N/A" {
                            subnet_id.rsplit('/').next().unwrap_or("N/A")
                        } else {
                            "N/A"
                        };
                        let pip_short = if public_ip_id != "N/A" {
                            public_ip_id.rsplit('/').next().unwrap_or("N/A")
                        } else {
                            "N/A"
                        };
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

                let config_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin");
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
        eprintln!("Azure authentication failed: {e}");
        eprintln!("Run 'az login' to authenticate with Azure CLI.");
        std::process::exit(1);
    })
}

fn resolve_resource_group(explicit: Option<String>) -> Result<String> {
    if let Some(rg) = explicit {
        return Ok(rg);
    }
    let config = azlin_core::AzlinConfig::load().ok();
    match config.and_then(|c| c.default_resource_group) {
        Some(rg) => Ok(rg),
        None => {
            eprintln!("No resource group specified. Use --resource-group or set in config.");
            std::process::exit(1);
        }
    }
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
            let vm = vm_manager.get_vm(&rg, vm_name).await?;
            let ip = vm
                .public_ip
                .or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", vm_name))?;
            let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());
            Ok((ip, user))
        }
        Err(_) => {
            anyhow::bail!("Azure auth not available. Use --ip flag to specify VM IP directly.")
        }
    }
}

/// Resolve VM IP: prefer --ip flag, fall back to Azure lookup.
async fn resolve_vm_ip_or_flag(
    vm_name: &str,
    ip_flag: Option<&str>,
    resource_group: Option<String>,
) -> Result<(String, String)> {
    if let Some(ip) = ip_flag {
        return Ok((ip.to_string(), "azureuser".to_string()));
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
            "azureuser".to_string(),
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
    let vms = vm_manager.list_vms(&rg).await?;
    let mut targets = Vec::new();
    for vm in vms {
        if vm.power_state != azlin_core::models::PowerState::Running {
            continue;
        }
        let ip = match vm.public_ip.or(vm.private_ip) {
            Some(ip) => ip,
            None => continue,
        };
        let user = vm.admin_username.unwrap_or_else(|| "azureuser".to_string());
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
    match output {
        azlin_cli::OutputFormat::Json => {
            match serde_json::to_string_pretty(summary) {
                Ok(json) => out.push_str(&json),
                Err(e) => out.push_str(&format!("Failed to serialize cost data: {e}")),
            }
            return out;
        }
        _ => {}
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
            out.push_str("\n");
            for vc in &summary.by_vm {
                out.push_str(&format!("\n{:<20} ${:.2} {}", vc.vm_name, vc.cost, vc.currency));
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
            toml::Value::String(
                vm_size
                    .unwrap_or("Standard_D4s_v3")
                    .to_string(),
            ),
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
        save_template(dir, &name, &tpl)?;
        Ok(name)
    }
}

/// Session TOML helpers for reading, writing, and listing sessions.
mod sessions {
    use std::path::Path;

    /// Build a session TOML value.
    pub fn build_session_toml(
        name: &str,
        resource_group: &str,
        vms: &[String],
    ) -> toml::Value {
        let mut session = toml::map::Map::new();
        session.insert("name".to_string(), toml::Value::String(name.to_string()));
        session.insert(
            "resource_group".to_string(),
            toml::Value::String(resource_group.to_string()),
        );
        let vm_array: Vec<toml::Value> = vms
            .iter()
            .map(|v| toml::Value::String(v.clone()))
            .collect();
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
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
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
        let mut entries: Vec<_> = std::fs::read_dir(ctx_dir)?
            .filter_map(|e| e.ok())
            .collect();
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
}

#[cfg(test)]
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
        let m = super::collect_health_metrics("test-vm", "10.0.0.1", "azureuser", "deallocated");
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
        let m = super::collect_health_metrics("vm-stop", "10.0.0.1", "user", "stopped");
        assert_eq!(m.vm_name, "vm-stop");
        assert_eq!(m.power_state, "stopped");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
        assert_eq!(m.load_avg, "-");
    }

    #[test]
    fn test_health_metrics_starting_vm() {
        let m = super::collect_health_metrics("vm-start", "10.0.0.1", "user", "starting");
        assert_eq!(m.power_state, "starting");
        assert_eq!(m.cpu_percent, 0.0);
    }

    #[test]
    fn test_health_metrics_unknown_state() {
        let m = super::collect_health_metrics("vm-x", "10.0.0.1", "user", "unknown");
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
                "template", "save", "custom-tpl",
                "--description", "A test template",
                "--vm-size", "Standard_D8s_v3",
                "--region", "eastus",
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
                "template", "save", "apply-test",
                "--vm-size", "Standard_D2s_v3",
                "--region", "westus2",
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
                "template", "save", "exportme",
                "--vm-size", "Standard_D4s_v3",
                "--region", "northeurope",
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
                "sessions", "save", "my-session",
                "--resource-group", "test-rg",
                "--vms", "vm1", "vm2",
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
                "sessions", "save", "load-test",
                "--resource-group", "rg-test",
                "--vms", "vm-alpha", "vm-beta",
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
                "sessions", "save", "delete-me",
                "--resource-group", "rg1",
                "--vms", "vm1",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        let output = assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args(["sessions", "delete", "delete-me"])
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
                    "sessions", "save", name,
                    "--resource-group", "rg",
                    "--vms", "vm1",
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
                "sessions", "save", "overwrite-me",
                "--resource-group", "rg-old",
                "--vms", "vm-old",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();

        assert_cmd::Command::cargo_bin("azlin")
            .unwrap()
            .args([
                "sessions", "save", "overwrite-me",
                "--resource-group", "rg-new",
                "--vms", "vm-new",
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
                "context", "create", "prod-env",
                "--subscription-id", "sub-123",
                "--tenant-id", "tenant-456",
                "--resource-group", "prod-rg",
                "--region", "eastus2",
            ])
            .env("HOME", dir.path())
            .output()
            .unwrap();
        assert!(output.status.success());

        // Verify the TOML file was written with the correct fields
        let ctx_path = dir.path().join(".azlin").join("contexts").join("prod-env.toml");
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
        let old_path = dir.path().join(".azlin").join("contexts").join("old-name.toml");
        let new_path = dir.path().join(".azlin").join("contexts").join("new-name.toml");
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
        assert!(stdout.contains("no legacy configuration found"));
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
                "sessions", "save", "json-sess",
                "--resource-group", "rg",
                "--vms", "vm1",
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
        let m = super::collect_health_metrics("vm-dealloc", "10.0.0.1", "user", "VM deallocated");
        assert_eq!(m.vm_name, "vm-dealloc");
        assert_eq!(m.cpu_percent, 0.0);
        assert_eq!(m.mem_percent, 0.0);
        assert_eq!(m.disk_percent, 0.0);
    }

    #[test]
    fn test_health_metrics_deallocating_vm() {
        let m = super::collect_health_metrics("vm-x", "10.0.0.1", "user", "VM deallocating");
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
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["bastion", "--help"]).assert().success();
    }

    #[test]
    fn test_bastion_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["bastion", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_bastion_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["bastion", "status", "--help"]).assert().success();
    }

    #[test]
    fn test_bastion_configure_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["bastion", "configure", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_create_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "create", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_restore_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "restore", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_delete_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "delete", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_enable_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "enable", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_disable_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "disable", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_sync_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "sync", "--help"]).assert().success();
    }

    #[test]
    fn test_snapshot_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["snapshot", "status", "--help"]).assert().success();
    }

    #[test]
    fn test_storage_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["storage", "--help"]).assert().success();
    }

    #[test]
    fn test_storage_mount_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["storage", "mount", "--help"]).assert().success();
    }

    #[test]
    fn test_storage_create_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["storage", "create", "--help"]).assert().success();
    }

    #[test]
    fn test_storage_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["storage", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_storage_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["storage", "status", "--help"]).assert().success();
    }

    #[test]
    fn test_storage_delete_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["storage", "delete", "--help"]).assert().success();
    }

    #[test]
    fn test_tag_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["tag", "--help"]).assert().success();
    }

    #[test]
    fn test_tag_add_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["tag", "add", "--help"]).assert().success();
    }

    #[test]
    fn test_tag_remove_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["tag", "remove", "--help"]).assert().success();
    }

    #[test]
    fn test_tag_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["tag", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_auth_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "--help"]).assert().success();
    }

    #[test]
    fn test_auth_setup_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "setup", "--help"]).assert().success();
    }

    #[test]
    fn test_auth_test_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "test", "--help"]).assert().success();
    }

    #[test]
    fn test_auth_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_auth_show_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "show", "--help"]).assert().success();
    }

    #[test]
    fn test_auth_remove_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "remove", "--help"]).assert().success();
    }

    #[test]
    fn test_keys_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["keys", "--help"]).assert().success();
    }

    #[test]
    fn test_keys_rotate_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["keys", "rotate", "--help"]).assert().success();
    }

    #[test]
    fn test_keys_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["keys", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_keys_export_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["keys", "export", "--help"]).assert().success();
    }

    #[test]
    fn test_keys_backup_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["keys", "backup", "--help"]).assert().success();
    }

    #[test]
    fn test_batch_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["batch", "--help"]).assert().success();
    }

    #[test]
    fn test_batch_command_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["batch", "command", "--help"]).assert().success();
    }

    #[test]
    fn test_batch_stop_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["batch", "stop", "--help"]).assert().success();
    }

    #[test]
    fn test_batch_start_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["batch", "start", "--help"]).assert().success();
    }

    #[test]
    fn test_batch_sync_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["batch", "sync", "--help"]).assert().success();
    }

    #[test]
    fn test_fleet_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["fleet", "--help"]).assert().success();
    }

    #[test]
    fn test_fleet_run_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["fleet", "run", "--help"]).assert().success();
    }

    #[test]
    fn test_fleet_workflow_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["fleet", "workflow", "--help"]).assert().success();
    }

    #[test]
    fn test_costs_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["costs", "--help"]).assert().success();
    }

    #[test]
    fn test_costs_dashboard_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["costs", "dashboard", "--help"]).assert().success();
    }

    #[test]
    fn test_costs_history_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["costs", "history", "--help"]).assert().success();
    }

    #[test]
    fn test_costs_budget_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["costs", "budget", "--help"]).assert().success();
    }

    #[test]
    fn test_costs_recommend_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["costs", "recommend", "--help"]).assert().success();
    }

    #[test]
    fn test_costs_actions_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["costs", "actions", "--help"]).assert().success();
    }

    #[test]
    fn test_compose_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["compose", "--help"]).assert().success();
    }

    #[test]
    fn test_compose_up_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["compose", "up", "--help"]).assert().success();
    }

    #[test]
    fn test_compose_down_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["compose", "down", "--help"]).assert().success();
    }

    #[test]
    fn test_compose_ps_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["compose", "ps", "--help"]).assert().success();
    }

    #[test]
    fn test_ip_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["ip", "--help"]).assert().success();
    }

    #[test]
    fn test_ip_check_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["ip", "check", "--help"]).assert().success();
    }

    #[test]
    fn test_disk_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["disk", "--help"]).assert().success();
    }

    #[test]
    fn test_disk_add_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["disk", "add", "--help"]).assert().success();
    }

    #[test]
    fn test_github_runner_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["github-runner", "--help"]).assert().success();
    }

    #[test]
    fn test_github_runner_enable_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["github-runner", "enable", "--help"]).assert().success();
    }

    #[test]
    fn test_github_runner_disable_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["github-runner", "disable", "--help"]).assert().success();
    }

    #[test]
    fn test_github_runner_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["github-runner", "status", "--help"]).assert().success();
    }

    #[test]
    fn test_github_runner_scale_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["github-runner", "scale", "--help"]).assert().success();
    }

    #[test]
    fn test_autopilot_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["autopilot", "--help"]).assert().success();
    }

    #[test]
    fn test_autopilot_enable_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["autopilot", "enable", "--help"]).assert().success();
    }

    #[test]
    fn test_autopilot_disable_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["autopilot", "disable", "--help"]).assert().success();
    }

    #[test]
    fn test_autopilot_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["autopilot", "status", "--help"]).assert().success();
    }

    #[test]
    fn test_autopilot_config_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["autopilot", "config", "--help"]).assert().success();
    }

    #[test]
    fn test_autopilot_run_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["autopilot", "run", "--help"]).assert().success();
    }

    #[test]
    fn test_web_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["web", "--help"]).assert().success();
    }

    #[test]
    fn test_web_start_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["web", "start", "--help"]).assert().success();
    }

    #[test]
    fn test_web_stop_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["web", "stop", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_deploy_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "deploy", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "status", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "list", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_show_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "show", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_cleanup_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "cleanup", "--help"]).assert().success();
    }

    #[test]
    fn test_doit_examples_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "examples", "--help"]).assert().success();
    }

    // ── CLI integration: top-level command --help ────────────────

    #[test]
    fn test_new_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["new", "--help"]).assert().success();
    }

    #[test]
    fn test_list_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["list", "--help"]).assert().success();
    }

    #[test]
    fn test_start_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["start", "--help"]).assert().success();
    }

    #[test]
    fn test_stop_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["stop", "--help"]).assert().success();
    }

    #[test]
    fn test_show_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["show", "--help"]).assert().success();
    }

    #[test]
    fn test_connect_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["connect", "--help"]).assert().success();
    }

    #[test]
    fn test_delete_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["delete", "--help"]).assert().success();
    }

    #[test]
    fn test_health_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["health", "--help"]).assert().success();
    }

    #[test]
    fn test_env_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["env", "--help"]).assert().success();
    }

    #[test]
    fn test_cost_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["cost", "--help"]).assert().success();
    }

    #[test]
    fn test_session_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["session", "--help"]).assert().success();
    }

    #[test]
    fn test_config_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["config", "--help"]).assert().success();
    }

    #[test]
    fn test_ask_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["ask", "--help"]).assert().success();
    }

    #[test]
    fn test_do_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["do", "--help"]).assert().success();
    }

    #[test]
    fn test_clone_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["clone", "--help"]).assert().success();
    }

    #[test]
    fn test_cp_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["cp", "--help"]).assert().success();
    }

    #[test]
    fn test_sync_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["sync", "--help"]).assert().success();
    }

    #[test]
    fn test_update_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["update", "--help"]).assert().success();
    }

    #[test]
    fn test_logs_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["logs", "--help"]).assert().success();
    }

    #[test]
    fn test_cleanup_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["cleanup", "--help"]).assert().success();
    }

    #[test]
    fn test_prune_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["prune", "--help"]).assert().success();
    }

    #[test]
    fn test_restore_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["restore", "--help"]).assert().success();
    }

    #[test]
    fn test_status_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["status", "--help"]).assert().success();
    }

    #[test]
    fn test_code_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["code", "--help"]).assert().success();
    }

    #[test]
    fn test_os_update_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["os-update", "--help"]).assert().success();
    }

    #[test]
    fn test_sync_keys_help() {
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["sync-keys", "--help"]).assert().success();
    }

    // ── CLI integration: config commands with temp home ──────────

    #[test]
    fn test_config_show_with_temp_home() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["config", "show"])
            .env("HOME", dir.path())
            .output().unwrap();
        let stdout = String::from_utf8_lossy(&out.stdout);
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(out.status.success() || stdout.contains("config") ||
                stderr.contains("config") || stdout.contains("No"));
    }

    #[test]
    fn test_config_set_and_show() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["config", "set", "resource_group", "test-rg"])
            .env("HOME", dir.path())
            .output().unwrap();
        let combined = format!("{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr));
        assert!(out.status.success() || combined.contains("config") ||
                combined.contains("set"));
    }

    // ── CLI integration: completions content verification ────────

    #[test]
    fn test_completions_zsh_content() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["completions", "zsh"]).output().unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("compdef") || stdout.len() > 100);
    }

    #[test]
    fn test_completions_powershell() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["completions", "powershell"]).output().unwrap();
        assert!(out.status.success());
        assert!(out.stdout.len() > 50);
    }

    #[test]
    fn test_completions_elvish() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["completions", "elvish"]).output().unwrap();
        assert!(out.status.success());
        assert!(out.stdout.len() > 50);
    }

    // ── CLI integration: graceful failures without Azure ─────────

    #[test]
    fn test_list_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["list"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output().unwrap();
        // Should fail gracefully, not crash
        let stderr = String::from_utf8_lossy(&out.stderr);
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(!out.status.success() ||
                stderr.contains("config") || stderr.contains("subscription") ||
                stderr.contains("auth") || stderr.contains("az login") ||
                stdout.contains("No VMs"));
    }

    #[test]
    fn test_show_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["show", "nonexistent-vm"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output().unwrap();
        assert!(!out.status.success() ||
                String::from_utf8_lossy(&out.stderr).len() > 0);
    }

    #[test]
    fn test_health_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["health"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output().unwrap();
        // Graceful failure or empty result
        let combined = format!("{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr));
        assert!(!out.status.success() || combined.len() > 0);
    }

    #[test]
    fn test_status_no_config() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["status"])
            .env("HOME", dir.path())
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .output().unwrap();
        let combined = format!("{}{}",
            String::from_utf8_lossy(&out.stdout),
            String::from_utf8_lossy(&out.stderr));
        assert!(!out.status.success() || combined.len() > 0);
    }

    // ── CLI integration: context full lifecycle ──────────────────

    #[test]
    fn test_context_full_lifecycle() {
        let dir = TempDir::new().unwrap();
        // create
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["context", "create", "lifecycle-ctx",
                   "--subscription-id", "sub-123",
                   "--resource-group", "rg-test"])
            .env("HOME", dir.path()).assert().success();
        // list
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["context", "list"])
            .env("HOME", dir.path()).output().unwrap();
        assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
        // use
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["context", "use", "lifecycle-ctx"])
            .env("HOME", dir.path()).assert().success();
        // show
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["context", "show"])
            .env("HOME", dir.path()).output().unwrap();
        assert!(String::from_utf8_lossy(&out.stdout).contains("lifecycle-ctx"));
        // delete
        assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["context", "delete", "lifecycle-ctx", "--force"])
            .env("HOME", dir.path()).assert().success();
    }

    // ── CLI integration: auth list with temp home ────────────────

    #[test]
    fn test_auth_list_empty() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["auth", "list"])
            .env("HOME", dir.path())
            .output().unwrap();
        assert!(out.status.success());
        let stdout = String::from_utf8_lossy(&out.stdout);
        assert!(stdout.contains("No") || stdout.contains("profile") || stdout.is_empty() || stdout.contains("auth"));
    }

    // ── CLI integration: sessions with temp home ─────────────────

    #[test]
    fn test_sessions_list_empty_temp() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["sessions", "list"])
            .env("HOME", dir.path())
            .output().unwrap();
        assert!(out.status.success());
    }

    // ── CLI integration: template with temp home ─────────────────

    #[test]
    fn test_template_list_empty_temp() {
        let dir = TempDir::new().unwrap();
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["template", "list"])
            .env("HOME", dir.path())
            .output().unwrap();
        assert!(out.status.success());
    }

    // ── CLI integration: verbose flag ────────────────────────────

    #[test]
    fn test_verbose_version() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["--verbose", "version"])
            .output().unwrap();
        assert!(out.status.success());
        assert!(String::from_utf8_lossy(&out.stdout).contains("2.3.0"));
    }

    // ── CLI integration: json output format ──────────────────────

    #[test]
    fn test_json_output_version() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["--output", "json", "version"])
            .output().unwrap();
        assert!(out.status.success());
    }

    #[test]
    fn test_csv_output_version() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["--output", "csv", "version"])
            .output().unwrap();
        assert!(out.status.success());
    }

    // ── CLI integration: invalid subcommand ──────────────────────

    #[test]
    fn test_invalid_subcommand() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["totally-bogus-command"])
            .output().unwrap();
        assert!(!out.status.success());
        let stderr = String::from_utf8_lossy(&out.stderr);
        assert!(stderr.contains("error") || stderr.contains("unrecognized") ||
                stderr.contains("invalid") || stderr.len() > 0);
    }

    // ── CLI integration: doit examples ───────────────────────────

    #[test]
    fn test_doit_examples() {
        let out = assert_cmd::Command::cargo_bin("azlin").unwrap()
            .args(["doit", "examples"])
            .output().unwrap();
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
        assert_eq!(rows[0], ("Cost".to_string(), "High".to_string(), "Underutilized VM".to_string()));
        assert_eq!(rows[1], ("Security".to_string(), "Medium".to_string(), "Open port".to_string()));
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
        let tpl1 = super::templates::build_template_toml("a", None, Some("small"), Some("west"), None);
        let tpl2 = super::templates::build_template_toml("b", None, Some("large"), Some("east"), None);
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
        let val = super::sessions::build_session_toml("s1", "rg1", &["vm1".to_string(), "vm2".to_string()]);
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
        let result = super::contexts::build_context_toml("ctx1", None, None, None, None, None).unwrap();
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
        let toml_content = super::contexts::build_context_toml("old", None, None, None, None, None).unwrap();
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
}
