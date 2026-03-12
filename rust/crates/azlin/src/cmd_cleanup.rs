#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = output;
    match command {
        azlin_cli::Commands::Cleanup {
            resource_group,
            dry_run,
            force,
            age_days,
            ..
        } => {
            crate::cmd_cleanup_ops::handle_cleanup(resource_group, dry_run, force, age_days)?;
        }

        azlin_cli::Commands::Costs { action } => {
            crate::cmd_cleanup_costs::dispatch_costs(action)?;
        }

        azlin_cli::Commands::Restore {
            resource_group,
            skip_health_check,
            force,
            terminal,
            exclude,
            ..
        } => {
            crate::cmd_cleanup_ops::handle_restore(
                resource_group,
                verbose,
                skip_health_check,
                force,
                terminal,
                exclude,
            )?;
        }

        _ => unreachable!(),
    }
    Ok(())
}
