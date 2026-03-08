#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Ask {
            query,
            resource_group,
            dry_run,
            ..
        } => {
            crate::cmd_ai_ops::handle_ask(query, resource_group, dry_run).await?;
        }
        azlin_cli::Commands::Do {
            request,
            dry_run,
            yes,
            verbose,
            ..
        } => {
            crate::cmd_ai_ops::handle_do(&request, dry_run, yes, verbose).await?;
        }
        azlin_cli::Commands::Doit { action } => match action {
            azlin_cli::DoitAction::Deploy {
                request, dry_run, ..
            } => {
                crate::cmd_ai_ops::handle_doit_deploy(&request, dry_run).await?;
            }
            azlin_cli::DoitAction::Status { session } => {
                crate::cmd_ai_ops2::handle_doit_status(session)?;
            }
            azlin_cli::DoitAction::List { username } => {
                crate::cmd_ai_ops2::handle_doit_list(username)?;
            }
            azlin_cli::DoitAction::Show { resource_id } => {
                crate::cmd_ai_ops2::handle_doit_show(&resource_id)?;
            }
            azlin_cli::DoitAction::Cleanup {
                force,
                dry_run,
                username,
            } => {
                crate::cmd_ai_ops2::handle_doit_cleanup(force, dry_run, username)?;
            }
            azlin_cli::DoitAction::Examples => {
                crate::cmd_ai_ops2::handle_doit_examples();
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}
