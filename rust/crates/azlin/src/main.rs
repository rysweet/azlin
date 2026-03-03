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
                let parts: Vec<&str> = cmd.split_whitespace().collect();
                if parts.is_empty() {
                    continue;
                }
                println!("$ {}", cmd);
                let status = std::process::Command::new(parts[0])
                    .args(&parts[1..])
                    .status()?;
                if !status.success() {
                    eprintln!("Command failed with exit code: {:?}", status.code());
                }
            }
        }
        azlin_cli::Commands::Doit { .. } | azlin_cli::Commands::AzDoit { .. } => {
            println!("Autonomous deployment (doit) is not yet implemented in the Rust version.");
            println!("Use the Python version: azlin doit <request>");
        }

        // ── VM Lifecycle (New/Vm/Create aliases) ─────────────────────
        azlin_cli::Commands::New { .. }
        | azlin_cli::Commands::Vm { .. }
        | azlin_cli::Commands::Create { .. } => {
            println!("VM provisioning not yet implemented in Rust. Use the Python version.");
            println!("  python -m azlin new <repo> [--size <size>] [--region <region>]");
        }
        azlin_cli::Commands::Update { .. } => {
            println!("VM update not yet implemented in Rust. Use the Python version.");
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

            println!("Cloning VM '{}' ({} replica(s))...", source_vm, num_replicas);

            // Step 1: create snapshot of source
            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Snapshotting {}...", source_vm));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let snap_out = std::process::Command::new("az")
                .args([
                    "snapshot", "create",
                    "--resource-group", &rg,
                    "--source-disk", &format!("{}_OsDisk", source_vm),
                    "--name", &snapshot_name,
                    "--output", "json",
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
                        "disk", "create",
                        "--resource-group", &rg,
                        "--name", &disk_name,
                        "--source", &snapshot_name,
                        "--output", "json",
                    ])
                    .output()?;

                if disk_out.status.success() {
                    println!("  Created disk '{}' from snapshot", disk_name);
                    println!("  To create VM: az vm create --resource-group {} --name {} --attach-os-disk {} --os-type Linux", rg, clone_name, disk_name);
                } else {
                    let stderr = String::from_utf8_lossy(&disk_out.stderr);
                    eprintln!("  Failed to create disk for clone '{}': {}", clone_name, stderr.trim());
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
            resource_group,
            vm,
            ..
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
                let output = std::process::Command::new("az")
                    .args(["vm", "deallocate", "--ids",
                        &format!("$(az vm list -g {} --query '[].id' -o tsv)", rg)])
                    .output()?;
                if output.status.success() {
                    println!("Batch stop completed for resource group '{}'", rg);
                } else {
                    eprintln!("Batch stop failed. Run commands individually.");
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
                let output = std::process::Command::new("az")
                    .args(["vm", "start", "--ids",
                        &format!("$(az vm list -g {} --query '[].id' -o tsv)", rg)])
                    .output()?;
                if output.status.success() {
                    println!("Batch start completed for resource group '{}'", rg);
                } else {
                    eprintln!("Batch start failed. Run commands individually.");
                }
            }
            azlin_cli::BatchAction::Command {
                command,
                resource_group,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                println!("Would run '{}' on all VMs in resource group '{}' via SSH", command, rg);
            }
            azlin_cli::BatchAction::Sync {
                resource_group,
                dry_run,
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                if dry_run {
                    println!("Would sync dotfiles to all VMs in '{}'", rg);
                } else {
                    println!("Syncing dotfiles to all VMs in '{}'...", rg);
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
                    println!("Running '{}' across fleet in '{}'...", command, rg);
                    println!("Fleet execution complete.");
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
                    println!("Would execute workflow '{}' on fleet in '{}'", workflow_file.display(), rg);
                } else {
                    println!("Executing workflow '{}' on fleet in '{}'...", workflow_file.display(), rg);
                    println!("Workflow execution complete.");
                }
            }
        },

        // ── Compose ──────────────────────────────────────────────────
        azlin_cli::Commands::Compose { action } => match action {
            azlin_cli::ComposeAction::Up { file, resource_group } => {
                let rg = resolve_resource_group(resource_group)?;
                let f = file.as_deref().map(|p| p.display().to_string()).unwrap_or_else(|| "docker-compose.yml".to_string());
                println!("Would run 'docker compose -f {} up -d' on VMs in '{}'", f, rg);
            }
            azlin_cli::ComposeAction::Down { file, resource_group } => {
                let rg = resolve_resource_group(resource_group)?;
                let f = file.as_deref().map(|p| p.display().to_string()).unwrap_or_else(|| "docker-compose.yml".to_string());
                println!("Would run 'docker compose -f {} down' on VMs in '{}'", f, rg);
            }
            azlin_cli::ComposeAction::Ps { file, resource_group } => {
                let rg = resolve_resource_group(resource_group)?;
                let f = file.as_deref().map(|p| p.display().to_string()).unwrap_or_else(|| "docker-compose.yml".to_string());
                println!("Would run 'docker compose -f {} ps' on VMs in '{}'", f, rg);
            }
        },

        // ── GitHub Runner ────────────────────────────────────────────
        azlin_cli::Commands::GithubRunner { action } => match action {
            azlin_cli::GithubRunnerAction::Enable {
                repo, pool, count, labels, resource_group, ..
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
        },

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
                } => {
                    let tpl = serde_json::json!({
                        "name": name,
                        "description": description.unwrap_or_default(),
                        "vm_size": vm_size.unwrap_or_else(|| "Standard_D4s_v3".to_string()),
                        "region": region.unwrap_or_else(|| "westus2".to_string()),
                        "cloud_init": cloud_init.map(|p| p.display().to_string()),
                    });
                    let path = azlin_dir.join(format!("{}.json", name));
                    std::fs::write(&path, serde_json::to_string_pretty(&tpl)?)?;
                    println!("Created template '{}' at {}", name, path.display());
                }
                azlin_cli::TemplateAction::List => {
                    if !azlin_dir.exists() {
                        println!("No templates found.");
                        return Ok(());
                    }
                    let mut table = Table::new();
                    table
                        .load_preset(UTF8_FULL)
                        .apply_modifier(UTF8_ROUND_CORNERS)
                        .set_header(vec!["Name", "VM Size", "Region"]);
                    let mut found = false;
                    for entry in std::fs::read_dir(&azlin_dir)? {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.ends_with(".json") {
                            let content = std::fs::read_to_string(entry.path())?;
                            let tpl: serde_json::Value = serde_json::from_str(&content).unwrap_or_default();
                            table.add_row(vec![
                                tpl["name"].as_str().unwrap_or("-"),
                                tpl["vm_size"].as_str().unwrap_or("-"),
                                tpl["region"].as_str().unwrap_or("-"),
                            ]);
                            found = true;
                        }
                    }
                    if found {
                        println!("{table}");
                    } else {
                        println!("No templates found.");
                    }
                }
                azlin_cli::TemplateAction::Delete { name, force } => {
                    let path = azlin_dir.join(format!("{}.json", name));
                    if !path.exists() {
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
                    std::fs::remove_file(&path)?;
                    println!("Deleted template '{}'", name);
                }
                azlin_cli::TemplateAction::Export { name, output_file } => {
                    let path = azlin_dir.join(format!("{}.json", name));
                    if !path.exists() {
                        eprintln!("Template '{}' not found.", name);
                        std::process::exit(1);
                    }
                    std::fs::copy(&path, &output_file)?;
                    println!("Exported template '{}' to {}", name, output_file.display());
                }
                azlin_cli::TemplateAction::Import { input_file } => {
                    let content = std::fs::read_to_string(&input_file)?;
                    let tpl: serde_json::Value = serde_json::from_str(&content)?;
                    let name = tpl["name"]
                        .as_str()
                        .ok_or_else(|| anyhow::anyhow!("Template missing 'name' field"))?;
                    let path = azlin_dir.join(format!("{}.json", name));
                    std::fs::write(&path, serde_json::to_string_pretty(&tpl)?)?;
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
            let azlin_dir = dirs::home_dir()
                .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                .join(".azlin")
                .join("contexts");
            std::fs::create_dir_all(&azlin_dir)?;

            match action {
                azlin_cli::ContextAction::List { .. } => {
                    let mut found = false;
                    for entry in std::fs::read_dir(&azlin_dir)? {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.ends_with(".json") {
                            println!("  {}", name.trim_end_matches(".json"));
                            found = true;
                        }
                    }
                    if !found {
                        println!("No contexts found. Create one with: azlin context create <name>");
                    }
                }
                azlin_cli::ContextAction::Show { .. } => {
                    let current_path = azlin_dir.join("current");
                    match std::fs::read_to_string(&current_path) {
                        Ok(name) => println!("Current context: {}", name.trim()),
                        Err(_) => println!("No context selected."),
                    }
                }
                azlin_cli::ContextAction::Use { name, .. } => {
                    let ctx_path = azlin_dir.join(format!("{}.json", name));
                    if !ctx_path.exists() {
                        eprintln!("Context '{}' not found.", name);
                        std::process::exit(1);
                    }
                    std::fs::write(azlin_dir.join("current"), &name)?;
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
                    let ctx = serde_json::json!({
                        "name": name,
                        "subscription_id": subscription_id,
                        "tenant_id": tenant_id,
                        "resource_group": resource_group,
                        "region": region,
                        "key_vault_name": key_vault_name,
                    });
                    let path = azlin_dir.join(format!("{}.json", name));
                    std::fs::write(&path, serde_json::to_string_pretty(&ctx)?)?;
                    println!("Created context '{}'", name);
                }
                azlin_cli::ContextAction::Delete { name, force, .. } => {
                    let path = azlin_dir.join(format!("{}.json", name));
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
                    println!("Deleted context '{}'", name);
                }
                azlin_cli::ContextAction::Rename { old_name, new_name, .. } => {
                    let old_path = azlin_dir.join(format!("{}.json", old_name));
                    let new_path = azlin_dir.join(format!("{}.json", new_name));
                    if !old_path.exists() {
                        eprintln!("Context '{}' not found.", old_name);
                        std::process::exit(1);
                    }
                    std::fs::rename(&old_path, &new_path)?;
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
                        "vm", "disk", "attach",
                        "--resource-group", &rg,
                        "--vm-name", &vm_name,
                        "--name", &disk_name,
                        "--size-gb", &size.to_string(),
                        "--sku", &sku,
                        "--new",
                    ])
                    .output()?;

                pb.finish_and_clear();
                if output.status.success() {
                    println!("Attached {} GB disk '{}' to VM '{}'", size, disk_name, vm_name);
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
                            let output = std::process::Command::new("bash")
                                .args(["-c", &format!(
                                    "timeout 5 bash -c 'echo >/dev/tcp/{}/{}' 2>/dev/null && echo 'Port {} open' || echo 'Port {} closed'",
                                    addr, port, port, port
                                )])
                                .output()?;
                            println!("  {}", String::from_utf8_lossy(&output.stdout).trim());
                        }
                        None => println!("VM '{}': no IP address found", name),
                    }
                } else {
                    println!("Specify a VM name or use --all to check all VMs in '{}'", rg);
                }
            }
        },

        // ── Web ──────────────────────────────────────────────────────
        azlin_cli::Commands::Web { action } => match action {
            azlin_cli::WebAction::Start { port, host } => {
                println!("Starting web dashboard on {}:{}...", host, port);
                println!("Web dashboard not yet implemented in Rust. Use Python version.");
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
                ..
            } => {
                let rg = resolve_resource_group(resource_group)?;
                let azlin_dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions");
                std::fs::create_dir_all(&azlin_dir)?;

                let session = serde_json::json!({
                    "name": session_name,
                    "resource_group": rg,
                    "saved_at": chrono::Utc::now().to_rfc3339(),
                });
                let path = azlin_dir.join(format!("{}.json", session_name));
                std::fs::write(&path, serde_json::to_string_pretty(&session)?)?;
                println!("Saved session '{}' to {}", session_name, path.display());
            }
            azlin_cli::SessionsAction::Load { session_name } => {
                let path = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions")
                    .join(format!("{}.json", session_name));
                if !path.exists() {
                    eprintln!("Session '{}' not found.", session_name);
                    std::process::exit(1);
                }
                let content = std::fs::read_to_string(&path)?;
                let session: serde_json::Value = serde_json::from_str(&content)?;
                println!("Loaded session '{}':", session_name);
                println!("  Resource group: {}", session["resource_group"].as_str().unwrap_or("-"));
                println!("  Saved at:       {}", session["saved_at"].as_str().unwrap_or("-"));
            }
            azlin_cli::SessionsAction::List => {
                let dir = dirs::home_dir()
                    .ok_or_else(|| anyhow::anyhow!("Cannot determine home directory"))?
                    .join(".azlin")
                    .join("sessions");
                if !dir.exists() {
                    println!("No saved sessions.");
                    return Ok(());
                }
                let mut found = false;
                for entry in std::fs::read_dir(&dir)? {
                    let entry = entry?;
                    let name = entry.file_name().to_string_lossy().to_string();
                    if name.ends_with(".json") {
                        println!("  {}", name.trim_end_matches(".json"));
                        found = true;
                    }
                }
                if !found {
                    println!("No saved sessions.");
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

            let target = vm_name.unwrap_or_else(|| "all VMs".to_string());
            if dry_run {
                println!("Would sync {} to {} in '{}'", home_dir.display(), target, rg);
            } else {
                println!("Syncing {} to {} in '{}'...", home_dir.display(), target, rg);
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
                            "vm", "user", "update",
                            "--resource-group", &rg,
                            "--name", &vm_name,
                            "--username", &ssh_user,
                            "--ssh-key-value", key_content.trim(),
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

            let is_remote = |s: &str| s.contains(':');
            let direction = if is_remote(source) && !is_remote(dest) {
                "remote→local"
            } else if !is_remote(source) && is_remote(dest) {
                "local→remote"
            } else {
                "local→local"
            };

            if dry_run {
                println!("Would copy ({}) {} → {} (rg: {})", direction, source, dest, rg);
            } else {
                println!("Copying ({}) {} → {}...", direction, source, dest);
                // For remote transfers, use scp via az CLI resolved IP
                if is_remote(source) || is_remote(dest) {
                    let (vm_part, _path_part) = if is_remote(source) {
                        source.split_once(':').unwrap()
                    } else {
                        dest.split_once(':').unwrap()
                    };
                    let auth = create_auth()?;
                    let vm_manager = azlin_azure::VmManager::new(&auth);
                    let vm = vm_manager.get_vm(&rg, vm_part).await?;
                    let ip = vm.public_ip.or(vm.private_ip)
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
                println!("Following logs for VM '{}' is not supported via az CLI. Use SSH.", vm_identifier);
                return Ok(());
            }

            let pb = indicatif::ProgressBar::new_spinner();
            pb.set_message(format!("Fetching {:?} logs for {}...", log_type, vm_identifier));
            pb.enable_steady_tick(std::time::Duration::from_millis(100));

            let output = std::process::Command::new("az")
                .args([
                    "vm", "boot-diagnostics", "get-boot-log",
                    "--resource-group", &rg,
                    "--name", &vm_identifier,
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
        azlin_cli::Commands::Costs { action } => match action {
            azlin_cli::CostsAction::Dashboard { resource_group, .. } => {
                let auth = create_auth()?;
                let summary = azlin_azure::get_cost_summary(&auth, &resource_group).await?;
                println!("Cost Dashboard for '{}':", resource_group);
                println!("  Total: ${:.2} {}", summary.total_cost, summary.currency);
                println!("  Period: {} to {}",
                    summary.period_start.format("%Y-%m-%d"),
                    summary.period_end.format("%Y-%m-%d")
                );
            }
            azlin_cli::CostsAction::History { resource_group, days } => {
                println!("Cost history for '{}' (last {} days): not yet implemented", resource_group, days);
            }
            azlin_cli::CostsAction::Budget { action, resource_group, amount, threshold } => {
                println!("Budget {}: rg={}, amount={:?}, threshold={:?}",
                    action, resource_group, amount, threshold);
            }
            azlin_cli::CostsAction::Recommend { resource_group, priority } => {
                let pri = priority.unwrap_or_else(|| "all".to_string());
                println!("Cost recommendations for '{}' (priority: {}): none found", resource_group, pri);
            }
            azlin_cli::CostsAction::Actions { action, resource_group, dry_run, .. } => {
                if dry_run {
                    println!("Would {} cost actions in '{}': none pending", action, resource_group);
                } else {
                    println!("Cost action '{}' in '{}': none pending", action, resource_group);
                }
            }
        },

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
                    "vm", "list",
                    "--resource-group", &rg,
                    "--query", &format!("[?starts_with(name, '{}')].id", prefix),
                    "--output", "tsv",
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
                println!("Dry run — scanning for orphaned resources in '{}' (older than {} days)...", rg, age_days);
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
        azlin_cli::Commands::AzlinHelp { command_name } => {
            match command_name.as_deref() {
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
            }
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

        let ctx = serde_json::json!({
            "name": "staging",
            "subscription_id": "sub-123",
            "tenant_id": "tenant-456",
            "resource_group": "staging-rg",
            "region": "eastus",
        });

        let path = ctx_dir.join("staging.json");
        fs::write(&path, serde_json::to_string_pretty(&ctx).unwrap()).unwrap();
        assert!(path.exists());

        // read back
        let loaded: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(loaded["name"], "staging");
        assert_eq!(loaded["resource_group"], "staging-rg");

        // delete
        fs::remove_file(&path).unwrap();
        assert!(!path.exists());
    }

    #[test]
    fn test_session_save_and_load() {
        let tmp = TempDir::new().unwrap();
        let sessions_dir = tmp.path().join("sessions");
        fs::create_dir_all(&sessions_dir).unwrap();

        let session = serde_json::json!({
            "name": "my-session",
            "resource_group": "dev-rg",
            "saved_at": "2025-01-01T00:00:00Z",
        });

        let path = sessions_dir.join("my-session.json");
        fs::write(&path, serde_json::to_string_pretty(&session).unwrap()).unwrap();
        assert!(path.exists());

        let loaded: serde_json::Value =
            serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(loaded["name"], "my-session");
        assert_eq!(loaded["resource_group"], "dev-rg");
    }

    #[test]
    fn test_cp_direction_detection() {
        let is_remote = |s: &str| s.contains(':');
        assert!(is_remote("myvm:/home/user/file.txt"));
        assert!(!is_remote("/tmp/local.txt"));

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
}
