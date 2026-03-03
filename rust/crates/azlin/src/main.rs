use anyhow::Result;
use clap::Parser;
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
