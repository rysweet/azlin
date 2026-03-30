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
        azlin_cli::Commands::Backup { action } => match action {
            azlin_cli::BackupAction::Configure {
                vm_name,
                daily_retention,
                weekly_retention,
                monthly_retention,
                cross_region,
                target_region,
                resource_group,
            } => {
                crate::cmd_backup_ops::handle_backup_configure(
                    &vm_name,
                    daily_retention,
                    weekly_retention,
                    monthly_retention,
                    cross_region,
                    target_region.as_deref(),
                    resource_group.as_deref(),
                )?;
            }
            azlin_cli::BackupAction::Trigger {
                vm_name,
                tier,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_trigger(&vm_name, tier, &rg).await?;
            }
            azlin_cli::BackupAction::List {
                vm_name,
                tier,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_list(&vm_name, tier, &rg).await?;
            }
            azlin_cli::BackupAction::Restore {
                vm_name,
                backup,
                force,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_restore(&vm_name, &backup, force, &rg)
                    .await?;
            }
            azlin_cli::BackupAction::Verify {
                backup_name,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_verify(&backup_name, &rg).await?;
            }
            azlin_cli::BackupAction::Replicate {
                backup_name,
                target_region,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_replicate(&backup_name, &target_region, &rg)
                    .await?;
            }
            azlin_cli::BackupAction::ConfigShow { vm_name } => {
                crate::cmd_backup_ops::handle_backup_config_show(&vm_name)?;
            }
            azlin_cli::BackupAction::Disable { vm_name } => {
                crate::cmd_backup_ops::handle_backup_disable(&vm_name)?;
            }
            azlin_cli::BackupAction::ReplicateAll {
                vm_name,
                target_region,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_replicate_all(&vm_name, &target_region, &rg)
                    .await?;
            }
            azlin_cli::BackupAction::ReplicationStatus {
                vm_name,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_replication_status(&vm_name, &rg).await?;
            }
            azlin_cli::BackupAction::ReplicationJobs {
                status,
                vm,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_replication_jobs(
                    status.as_deref(),
                    vm.as_deref(),
                    &rg,
                )
                .await?;
            }
            azlin_cli::BackupAction::VerifyAll {
                vm_name,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_backup_verify_all(&vm_name, &rg).await?;
            }
            azlin_cli::BackupAction::VerificationReport {
                days,
                vm,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                crate::cmd_backup_ops::handle_verification_report(days, vm.as_deref(), &rg)
                    .await?;
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}
