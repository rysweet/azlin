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
            println!("azlin {} (rust)", env!("CARGO_PKG_VERSION"));
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
            let auth = match azlin_azure::AzureAuth::new() {
                Ok(a) => a,
                Err(e) => {
                    eprintln!("Azure authentication failed: {e}");
                    eprintln!("Run 'az login' to authenticate with Azure CLI.");
                    std::process::exit(1);
                }
            };

            let vm_manager = azlin_azure::VmManager::new(&auth);

            let vms = match &resource_group {
                Some(rg) => vm_manager.list_vms(rg).await?,
                None => {
                    // Try loading resource group from config
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
        _ => {
            eprintln!("Command not yet implemented in Rust version. Use Python version.");
            std::process::exit(1);
        }
    }

    Ok(())
}
