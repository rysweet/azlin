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
                    crate::cmd_infra_ops::handle_runner_enable(
                        repo,
                        pool,
                        count,
                        labels,
                        resource_group,
                        vm_size,
                        &runner_dir,
                    )
                    .await?;
                }
                azlin_cli::GithubRunnerAction::Disable { pool, keep_vms } => {
                    crate::cmd_infra_ops::handle_runner_disable(&pool, keep_vms, &runner_dir)?;
                }
                azlin_cli::GithubRunnerAction::Status { pool } => {
                    crate::cmd_infra_ops::handle_runner_status(&pool, &runner_dir)?;
                }
                azlin_cli::GithubRunnerAction::Scale { pool, count } => {
                    crate::cmd_infra_ops::handle_runner_scale(&pool, count, &runner_dir)?;
                }
            }
        }

        azlin_cli::Commands::Compose { action } => match action {
            azlin_cli::ComposeAction::Up {
                file,
                resource_group,
            } => {
                crate::cmd_infra_ops2::handle_compose_action(
                    "up -d",
                    file.as_deref(),
                    resource_group,
                )
                .await?;
            }
            azlin_cli::ComposeAction::Down {
                file,
                resource_group,
            } => {
                crate::cmd_infra_ops2::handle_compose_action(
                    "down",
                    file.as_deref(),
                    resource_group,
                )
                .await?;
            }
            azlin_cli::ComposeAction::Ps {
                file,
                resource_group,
            } => {
                crate::cmd_infra_ops2::handle_compose_action("ps", file.as_deref(), resource_group)
                    .await?;
            }
        },

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
                    crate::cmd_infra_ops2::handle_template_create(
                        &azlin_dir,
                        &name,
                        description.as_deref(),
                        vm_size.as_deref(),
                        region.as_deref(),
                        cloud_init.as_deref(),
                    )?;
                }
                azlin_cli::TemplateAction::List => {
                    crate::cmd_infra_ops2::handle_template_list(&azlin_dir, output)?;
                }
                azlin_cli::TemplateAction::Show { name } => {
                    crate::cmd_infra_ops2::handle_template_show(&azlin_dir, &name)?;
                }
                azlin_cli::TemplateAction::Apply { name } => {
                    crate::cmd_infra_ops2::handle_template_apply(&azlin_dir, &name)?;
                }
                azlin_cli::TemplateAction::Delete { name, force } => {
                    crate::cmd_infra_ops2::handle_template_delete(&azlin_dir, &name, force)?;
                }
                azlin_cli::TemplateAction::Export { name, output_file } => {
                    crate::cmd_infra_ops2::handle_template_export(&azlin_dir, &name, &output_file)?;
                }
                azlin_cli::TemplateAction::Import { input_file } => {
                    crate::cmd_infra_ops2::handle_template_import(&azlin_dir, &input_file)?;
                }
            }
        }

        _ => unreachable!(),
    }
    Ok(())
}
