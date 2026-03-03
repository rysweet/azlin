use anyhow::Result;
use clap::Parser;
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
                println!("{}", toml::to_string_pretty(&config)?);
            }
            azlin_cli::ConfigAction::Get { key } => {
                let config = azlin_core::AzlinConfig::load()?;
                let json = serde_json::to_value(&config)?;
                match json.get(&key) {
                    Some(val) => println!("{val}"),
                    None => eprintln!("Unknown config key: {key}"),
                }
            }
            azlin_cli::ConfigAction::Set { key, value } => {
                let mut config = azlin_core::AzlinConfig::load()?;
                let mut json = serde_json::to_value(&config)?;
                if let Some(obj) = json.as_object_mut() {
                    obj.insert(key.clone(), serde_json::Value::String(value));
                    config = serde_json::from_value(json)?;
                    config.save()?;
                    println!("Set {key}");
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
