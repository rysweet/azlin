use anyhow::Result;
use clap::CommandFactory;
use console::Style;

use super::*;

/// Dispatch a parsed CLI command. Separated from async_main for testability —
/// tests can construct a Cli struct and call this directly (in-process coverage).
#[cfg_attr(test, allow(dead_code))]
pub(crate) async fn dispatch_command(cli: azlin_cli::Cli) -> Result<()> {
    if cli.verbose {
        tracing::info!("Verbose mode enabled");
    }

    match cli.command {
        azlin_cli::Commands::Version => {
            println!("azlin {} (rust)", env!("CARGO_PKG_VERSION"));
        }
        azlin_cli::Commands::Config { action } => {
            handle_config(action)?;
        }
        cmd @ azlin_cli::Commands::List { .. } => {
            crate::cmd_list::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Start { .. }
        | cmd @ azlin_cli::Commands::Stop { .. }
        | cmd @ azlin_cli::Commands::Delete { .. }
        | cmd @ azlin_cli::Commands::Kill { .. }
        | cmd @ azlin_cli::Commands::Destroy { .. }
        | cmd @ azlin_cli::Commands::Killall { .. }
        | cmd @ azlin_cli::Commands::OsUpdate { .. } => {
            crate::cmd_lifecycle::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Connect { .. } | cmd @ azlin_cli::Commands::Show { .. } => {
            crate::cmd_connect::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Tag { .. } => {
            crate::cmd_tag::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::W { .. }
        | cmd @ azlin_cli::Commands::Ps { .. }
        | cmd @ azlin_cli::Commands::Top { .. }
        | cmd @ azlin_cli::Commands::Health { .. } => {
            crate::cmd_monitoring::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Env { .. } => {
            crate::cmd_env::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        azlin_cli::Commands::Cost {
            resource_group,
            by_vm,
            from,
            to,
            estimate,
            ..
        } => {
            handle_cost(resource_group, &cli.output, from, to, estimate, by_vm)?;
        }
        cmd @ azlin_cli::Commands::Snapshot { .. } => {
            crate::cmd_snapshot::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Storage { .. } => {
            crate::cmd_storage::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Keys { .. } => {
            crate::cmd_keys::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Auth { .. } => {
            crate::cmd_auth::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Ask { .. }
        | cmd @ azlin_cli::Commands::Do { .. }
        | cmd @ azlin_cli::Commands::Doit { .. } => {
            crate::cmd_ai::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::New { .. }
        | cmd @ azlin_cli::Commands::Vm { .. }
        | cmd @ azlin_cli::Commands::Clone { .. } => {
            crate::cmd_vm::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Session { .. }
        | cmd @ azlin_cli::Commands::Sessions { .. }
        | cmd @ azlin_cli::Commands::Status { .. }
        | cmd @ azlin_cli::Commands::Code { .. } => {
            crate::cmd_session::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Batch { .. } | cmd @ azlin_cli::Commands::Fleet { .. } => {
            crate::cmd_batch::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::GithubRunner { .. }
        | cmd @ azlin_cli::Commands::Compose { .. }
        | cmd @ azlin_cli::Commands::Template { .. } => {
            crate::cmd_infra::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Autopilot { .. } => {
            crate::cmd_autopilot::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Context { .. } => {
            crate::cmd_context::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Disk { .. }
        | cmd @ azlin_cli::Commands::Ip { .. }
        | cmd @ azlin_cli::Commands::Web { .. }
        | cmd @ azlin_cli::Commands::Bastion { .. } => {
            crate::cmd_network::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Tunnel { .. } => {
            crate::cmd_tunnel::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Gui { .. } => {
            crate::cmd_gui::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Cleanup { .. }
        | cmd @ azlin_cli::Commands::Costs { .. }
        | cmd @ azlin_cli::Commands::Restore { .. } => {
            crate::cmd_cleanup::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        cmd @ azlin_cli::Commands::Sync { .. }
        | cmd @ azlin_cli::Commands::SyncKeys { .. }
        | cmd @ azlin_cli::Commands::Cp { .. }
        | cmd @ azlin_cli::Commands::Logs { .. } => {
            crate::cmd_sync::dispatch(cmd, cli.verbose, &cli.output).await?;
        }
        azlin_cli::Commands::Update => {
            crate::cmd_self_update::handle_self_update()?;
        }
        azlin_cli::Commands::Completions { shell, install } => {
            if install {
                crate::cmd_completions::install_completions(shell)?;
            } else {
                let mut cmd = azlin_cli::Cli::command();
                clap_complete::generate(shell, &mut cmd, "azlin", &mut std::io::stdout());
            }
        }
        azlin_cli::Commands::History { action, count } => {
            crate::cmd_history::handle_history(action, count)?;
        }
        azlin_cli::Commands::AzlinHelp { command_name } => {
            println!("{}", handlers::build_extended_help(command_name.as_deref()));
        }
    }

    Ok(())
}

fn handle_config(action: azlin_cli::ConfigAction) -> Result<()> {
    match action {
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
            azlin_core::AzlinConfig::set_field(&key, &value)?;
            println!("Set {key} = {value}");
        }
        azlin_cli::ConfigAction::Diff { all, format, file } => {
            crate::cmd_config_diff::handle_config_diff(all, &format, file.as_deref())?;
        }
        azlin_cli::ConfigAction::Init { force } => {
            crate::cmd_config_init::handle_config_init(force)?;
        }
    }
    Ok(())
}

fn handle_cost(
    resource_group: Option<String>,
    output: &azlin_cli::OutputFormat,
    from: Option<String>,
    to: Option<String>,
    estimate: bool,
    by_vm: bool,
) -> Result<()> {
    let auth = create_auth()?;
    let rg = resolve_resource_group(resource_group)?;
    let cost_timeout = azlin_core::AzlinConfig::load()
        .map(|c| c.az_cli_timeout)
        .unwrap_or(120);

    let pb = penguin_spinner("Fetching cost data...");
    match azlin_azure::get_cost_summary(&auth, &rg, cost_timeout) {
        Ok(summary) => {
            pb.finish_and_clear();
            let fmt_str = match output {
                azlin_cli::OutputFormat::Json => "json",
                azlin_cli::OutputFormat::Csv => "csv",
                azlin_cli::OutputFormat::Table => "table",
            };
            println!(
                "{}",
                handlers::format_cost_summary(&summary, fmt_str, &from, &to, estimate, by_vm)
            );
        }
        Err(e) => {
            pb.finish_and_clear();
            eprintln!("Cost data unavailable: {e}");
            eprintln!("  Run 'az consumption usage list' for cost data via Azure CLI.");
        }
    }
    Ok(())
}

// Utility functions live in dispatch_helpers module; accessed via `use super::*`.
