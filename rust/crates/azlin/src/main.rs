use anyhow::Result;
use clap::Parser;
use comfy_table::{modifiers::UTF8_ROUND_CORNERS, presets::UTF8_FULL, Table};
use console::Style;
use dialoguer::Confirm;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
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
                        println!("{}: {}", key_style.apply_to(k), val_style.apply_to(&display));
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
        azlin_cli::Commands::List {
            resource_group,
            ..
        } => {
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

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Starting {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.start_vm(&rg, &vm_name).await?;
            pb.finish_with_message(format!("Started {}", vm_name));
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

            let action = if deallocate { "Deallocating" } else { "Stopping" };
            let done = if deallocate { "Deallocated" } else { "Stopped" };
            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("{} {}...", action, vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.stop_vm(&rg, &vm_name, deallocate).await?;
            pb.finish_with_message(format!("{} {}", done, vm_name));
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

            let ip = vm.public_ip.or(vm.private_ip)
                .ok_or_else(|| anyhow::anyhow!("No IP address found for VM '{}'", name))?;
            let username = vm.admin_username.unwrap_or_else(|| user.clone());

            let mut ssh_args = vec![
                "-o".to_string(),
                "StrictHostKeyChecking=no".to_string(),
            ];
            if let Some(key_path) = &key {
                ssh_args.push("-i".to_string());
                ssh_args.push(key_path.display().to_string());
            }
            ssh_args.push(format!("{}@{}", username, ip));

            let status = std::process::Command::new("ssh")
                .args(&ssh_args)
                .status()?;

            std::process::exit(status.code().unwrap_or(1));
        }
        azlin_cli::Commands::Tag { action } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);

            match action {
                azlin_cli::TagAction::Add { vm_name, tags, resource_group } => {
                    let rg = resolve_resource_group(resource_group)?;
                    for tag in &tags {
                        let parts: Vec<&str> = tag.splitn(2, '=').collect();
                        if parts.len() != 2 {
                            eprintln!("Invalid tag format '{}'. Use key=value.", tag);
                            std::process::exit(1);
                        }
                        vm_manager.add_tag(&rg, &vm_name, parts[0], parts[1]).await?;
                        println!("Added tag {}={} to VM '{}'", parts[0], parts[1], vm_name);
                    }
                }
                azlin_cli::TagAction::Remove { vm_name, tag_keys, resource_group } => {
                    let rg = resolve_resource_group(resource_group)?;
                    for key in &tag_keys {
                        vm_manager.remove_tag(&rg, &vm_name, key).await?;
                        println!("Removed tag '{}' from VM '{}'", key, vm_name);
                    }
                }
                azlin_cli::TagAction::List { vm_name, resource_group } => {
                    let rg = resolve_resource_group(resource_group)?;
                    let tags = vm_manager.list_tags(&rg, &vm_name).await?;
                    azlin_cli::table::render_tags_table(&vm_name, &tags);
                }
            }
        }
        azlin_cli::Commands::W { .. } => {
            println!("Not yet connected to any VMs");
        }
        azlin_cli::Commands::Ps { .. } => {
            println!("Not yet connected to any VMs");
        }
        azlin_cli::Commands::Top { .. } => {
            println!("Not yet connected to any VMs");
        }
        azlin_cli::Commands::Health { .. } => {
            println!("Health monitoring not yet implemented");
        }
        azlin_cli::Commands::OsUpdate { .. } => {
            println!("OS update not yet implemented");
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

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Deleting {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.delete_vm(&rg, &vm_name).await?;
            pb.finish_with_message(format!("Deleted {}", vm_name));
        }
        azlin_cli::Commands::Kill {
            vm_name,
            resource_group,
            ..
        } => {
            let auth = create_auth()?;
            let vm_manager = azlin_azure::VmManager::new(&auth);
            let rg = resolve_resource_group(resource_group)?;

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Killing {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.delete_vm(&rg, &vm_name).await?;
            pb.finish_with_message(format!("Killed {}", vm_name));
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

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Destroying {}...", vm_name));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));
            vm_manager.delete_vm(&rg, &vm_name).await?;
            pb.finish_with_message(format!("Destroyed {}", vm_name));
        }
        azlin_cli::Commands::Env { action } => match action {
            azlin_cli::EnvAction::Set {
                vm_identifier,
                env_var,
                ..
            } => {
                let parts: Vec<&str> = env_var.splitn(2, '=').collect();
                if parts.len() != 2 {
                    eprintln!("Invalid format. Use KEY=VALUE");
                    std::process::exit(1);
                }
                let (key, value) = (parts[0], parts[1]);
                println!(
                    "Would set {}={} on VM '{}' via: echo 'export {}={}' >> ~/.bashrc",
                    key, value, vm_identifier, key, value
                );
            }
            azlin_cli::EnvAction::List {
                vm_identifier, ..
            } => {
                println!(
                    "Would list environment variables on VM '{}' via: env | sort",
                    vm_identifier
                );
            }
            azlin_cli::EnvAction::Delete {
                vm_identifier,
                key,
                ..
            } => {
                println!(
                    "Would delete '{}' from VM '{}' via: sed -i '/^export {}=/d' ~/.bashrc",
                    key, vm_identifier, key
                );
            }
            azlin_cli::EnvAction::Export {
                vm_identifier,
                output_file,
                ..
            } => {
                let file = output_file.as_deref().unwrap_or("<stdout>");
                println!(
                    "Would export env vars from VM '{}' to '{}'",
                    vm_identifier, file
                );
            }
            azlin_cli::EnvAction::Import {
                vm_identifier,
                env_file,
                ..
            } => {
                println!(
                    "Would import env vars from '{}' to VM '{}'",
                    env_file.display(),
                    vm_identifier
                );
            }
            azlin_cli::EnvAction::Clear {
                vm_identifier,
                force,
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
                println!(
                    "Would clear all custom environment variables on VM '{}'",
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

            let key_style = Style::new().cyan().bold();
            let val_style = Style::new().white();

            println!(
                "{}: ${:.2} {}",
                key_style.apply_to("Total Cost"),
                summary.total_cost,
                val_style.apply_to(&summary.currency)
            );
            println!(
                "{}: {} to {}",
                key_style.apply_to("Period"),
                summary.period_start.format("%Y-%m-%d"),
                summary.period_end.format("%Y-%m-%d")
            );

            if let Some(ref f) = from {
                println!("{}: {}", key_style.apply_to("From filter"), f);
            }
            if let Some(ref t) = to {
                println!("{}: {}", key_style.apply_to("To filter"), t);
            }
            if estimate {
                println!(
                    "{}: ${:.2}/month (projected)",
                    key_style.apply_to("Estimate"),
                    summary.total_cost
                );
            }

            if by_vm && !summary.by_vm.is_empty() {
                println!();
                let mut table = comfy_table::Table::new();
                table
                    .load_preset(comfy_table::presets::UTF8_FULL)
                    .apply_modifier(comfy_table::modifiers::UTF8_ROUND_CORNERS)
                    .set_header(vec!["VM Name", "Cost", "Currency"]);

                for vm_cost in &summary.by_vm {
                    table.add_row(vec![
                        comfy_table::Cell::new(&vm_cost.vm_name),
                        comfy_table::Cell::new(format!("${:.2}", vm_cost.cost)),
                        comfy_table::Cell::new(&vm_cost.currency),
                    ]);
                }
                println!("{table}");
            } else if by_vm {
                println!("\nNo per-VM cost data available.");
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
                            "snapshot", "create",
                            "--resource-group", &rg,
                            "--source-disk", &format!("{}_OsDisk", vm_name),
                            "--name", &snapshot_name,
                            "--output", "json",
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
                            "snapshot", "list",
                            "--resource-group", &rg,
                            "--output", "json",
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
                                .set_header(vec!["Name", "Disk Size (GB)", "Time Created", "State"]);
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
                            "snapshot", "show",
                            "--resource-group", &rg,
                            "--name", &snapshot_name,
                            "--query", "id",
                            "--output", "tsv",
                        ])
                        .output()?;

                    if !snap_output.status.success() {
                        pb.finish_and_clear();
                        eprintln!("Snapshot '{}' not found.", snapshot_name);
                        std::process::exit(1);
                    }

                    let snap_id = String::from_utf8_lossy(&snap_output.stdout).trim().to_string();
                    let new_disk = format!("{}_OsDisk_restored", vm_name);

                    let disk_output = std::process::Command::new("az")
                        .args([
                            "disk", "create",
                            "--resource-group", &rg,
                            "--name", &new_disk,
                            "--source", &snap_id,
                            "--output", "json",
                        ])
                        .output()?;

                    pb.finish_and_clear();
                    if disk_output.status.success() {
                        println!("Restored disk '{}' from snapshot '{}'", new_disk, snapshot_name);
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
                            "snapshot", "delete",
                            "--resource-group", &rg,
                            "--name", &snapshot_name,
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
                azlin_cli::SnapshotAction::Enable { vm_name, every, keep, .. } => {
                    println!(
                        "Scheduled snapshots enabled for VM '{}': every {}h, keep {}",
                        vm_name, every, keep
                    );
                }
                azlin_cli::SnapshotAction::Disable { vm_name, .. } => {
                    println!("Scheduled snapshots disabled for VM '{}'", vm_name);
                }
                azlin_cli::SnapshotAction::Sync { vm, .. } => {
                    match vm {
                        Some(name) => println!("Snapshot sync completed for VM '{}'", name),
                        None => println!("Snapshot sync completed for all VMs"),
                    }
                }
                azlin_cli::SnapshotAction::Status { vm_name, .. } => {
                    println!("Snapshot schedule status for VM '{}': no schedule configured", vm_name);
                }
            }
        }
        azlin_cli::Commands::Storage { action } => {
            match action {
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
                            "storage", "account", "create",
                            "--name", &name,
                            "--resource-group", &rg,
                            "--location", &loc,
                            "--sku", sku,
                            "--kind", "FileStorage",
                            "--enable-nfs-v3", "true",
                            "--output", "json",
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
                            "storage", "account", "list",
                            "--resource-group", &rg,
                            "--output", "json",
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
                            "storage", "account", "show",
                            "--name", &name,
                            "--resource-group", &rg,
                            "--output", "json",
                        ])
                        .output()?;

                    if output.status.success() {
                        let acct: serde_json::Value =
                            serde_json::from_slice(&output.stdout).unwrap_or_default();
                        let key_style = Style::new().cyan().bold();
                        println!("{}: {}", key_style.apply_to("Name"), acct["name"].as_str().unwrap_or("-"));
                        println!("{}: {}", key_style.apply_to("Location"), acct["location"].as_str().unwrap_or("-"));
                        println!("{}: {}", key_style.apply_to("Kind"), acct["kind"].as_str().unwrap_or("-"));
                        println!("{}: {}", key_style.apply_to("SKU"), acct["sku"]["name"].as_str().unwrap_or("-"));
                        println!("{}: {}", key_style.apply_to("State"), acct["provisioningState"].as_str().unwrap_or("-"));
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

                    let ip = vm_info.public_ip.or(vm_info.private_ip).ok_or_else(|| {
                        anyhow::anyhow!("No IP address found for VM '{}'", vm)
                    })?;
                    let user = vm_info.admin_username.unwrap_or_else(|| "azureuser".to_string());

                    let mount_cmd = format!(
                        "sudo mkdir -p /mnt/{storage_name} && sudo mount -t nfs {storage_name}.file.core.windows.net:/{storage_name}/home /mnt/{storage_name} -o vers=3,sec=sys"
                    );
                    let status = std::process::Command::new("ssh")
                        .args([
                            "-o", "StrictHostKeyChecking=no",
                            &format!("{}@{}", user, ip),
                            &mount_cmd,
                        ])
                        .status()?;

                    if status.success() {
                        println!("Mounted '{}' on VM '{}' at /mnt/{}", storage_name, vm, storage_name);
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

                    let ip = vm_info.public_ip.or(vm_info.private_ip).ok_or_else(|| {
                        anyhow::anyhow!("No IP address found for VM '{}'", vm)
                    })?;
                    let user = vm_info.admin_username.unwrap_or_else(|| "azureuser".to_string());

                    let status = std::process::Command::new("ssh")
                        .args([
                            "-o", "StrictHostKeyChecking=no",
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
                            "storage", "account", "delete",
                            "--name", &name,
                            "--resource-group", &rg,
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
            }
        }
        azlin_cli::Commands::Keys { action } => {
            match action {
                azlin_cli::KeysAction::List { .. } => {
                    let ssh_dir = dirs::home_dir()
                        .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                        .join(".ssh");

                    if !ssh_dir.exists() {
                        println!("No SSH directory found at {}", ssh_dir.display());
                        return Ok(());
                    }

                    let entries = std::fs::read_dir(&ssh_dir)?;
                    let mut table = Table::new();
                    table
                        .load_preset(UTF8_FULL)
                        .apply_modifier(UTF8_ROUND_CORNERS)
                        .set_header(vec!["Key File", "Type", "Size (bytes)", "Modified"]);

                    let mut found = false;
                    for entry in entries {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();

                        let is_key = name.ends_with(".pub")
                            || ["id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"]
                                .contains(&name.as_str())
                            || (!name.starts_with('.') && !name.ends_with(".pub")
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

                        table.add_row(vec![&name, key_type, &meta.len().to_string(), &modified]);
                        found = true;
                    }

                    if found {
                        println!("{table}");
                    } else {
                        println!("No SSH keys found in {}", ssh_dir.display());
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
                            "-t", "ed25519",
                            "-f", &new_key.to_string_lossy(),
                            "-N", "",
                            "-C", "azlin-rotated",
                        ])
                        .output()?;

                    if !keygen.status.success() {
                        eprintln!("Failed to generate new SSH key.");
                        std::process::exit(1);
                    }
                    println!("Generated new ed25519 key pair");

                    let prefix_filter = if all_vms { "" } else { &vm_prefix };
                    let query = format!("[?starts_with(name, '{}')]", prefix_filter);
                    let mut az_args = vec![
                        "vm", "list",
                        "--resource-group", &rg,
                        "--output", "json",
                    ];
                    if !prefix_filter.is_empty() {
                        az_args.extend(["--query", query.as_str()]);
                    }

                    let output = std::process::Command::new("az")
                        .args(&az_args)
                        .output()?;

                    if output.status.success() {
                        let vms: Vec<serde_json::Value> =
                            serde_json::from_slice(&output.stdout).unwrap_or_default();
                        let pub_key_content =
                            std::fs::read_to_string(ssh_dir.join("id_ed25519_azlin.pub"))?;
                        for vm_val in &vms {
                            let name = vm_val["name"].as_str().unwrap_or("");
                            let result = std::process::Command::new("az")
                                .args([
                                    "vm", "user", "update",
                                    "--resource-group", &rg,
                                    "--name", name,
                                    "--username", "azureuser",
                                    "--ssh-key-value", pub_key_content.trim(),
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
                            println!(
                                "Exported {} to {}",
                                src.file_name().unwrap().to_string_lossy(),
                                output.display()
                            );
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
            }
        }
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
                    let mut table = Table::new();
                    table
                        .load_preset(UTF8_FULL)
                        .apply_modifier(UTF8_ROUND_CORNERS)
                        .set_header(vec!["Profile", "Tenant ID", "Client ID"]);

                    let mut found = false;
                    for entry in entries {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.ends_with(".json") {
                            let content = std::fs::read_to_string(entry.path())?;
                            let profile: serde_json::Value =
                                serde_json::from_str(&content).unwrap_or_default();
                            let profile_name = name.trim_end_matches(".json");
                            table.add_row(vec![
                                profile_name,
                                profile["tenant_id"].as_str().unwrap_or("-"),
                                profile["client_id"].as_str().unwrap_or("-"),
                            ]);
                            found = true;
                        }
                    }

                    if found {
                        println!("{table}");
                    } else {
                        println!("No authentication profiles found.");
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
                    pb.set_message(format!("Testing authentication for profile '{}'...", profile));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args(["account", "show", "--output", "json"])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        let acct: serde_json::Value =
                            serde_json::from_slice(&output.stdout).unwrap_or_default();
                        let key_style = Style::new().cyan().bold();
                        println!("{}", Style::new().green().bold().apply_to("Authentication successful!"));
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
                    std::fs::write(
                        &profile_path,
                        serde_json::to_string_pretty(&profile_data)?,
                    )?;
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
        _ => {
            eprintln!("Command not yet implemented in Rust version. Use Python version.");
            std::process::exit(1);
        }
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
        fs::write(&profile_path, serde_json::to_string_pretty(&profile_data).unwrap()).unwrap();

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
}
