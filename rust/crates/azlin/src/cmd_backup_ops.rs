#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// Backup config persistence (~/.azlin/backup/{vm_name}.toml)
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize)]
pub(crate) struct BackupConfig {
    pub vm_name: String,
    pub daily_retention: Option<u32>,
    pub weekly_retention: Option<u32>,
    pub monthly_retention: Option<u32>,
    pub cross_region: bool,
    pub target_region: Option<String>,
    pub resource_group: Option<String>,
    pub created: String,
}

fn backup_config_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".azlin")
        .join("backup")
}

fn backup_config_path(vm_name: &str) -> PathBuf {
    backup_config_dir().join(format!("{}.toml", vm_name))
}

fn load_backup_config(vm_name: &str) -> Option<BackupConfig> {
    let path = backup_config_path(vm_name);
    let contents = std::fs::read_to_string(path).ok()?;
    toml::from_str(&contents).ok()
}

fn save_backup_config(config: &BackupConfig) -> Result<()> {
    let dir = backup_config_dir();
    std::fs::create_dir_all(&dir)?;
    let path = backup_config_path(&config.vm_name);
    let contents = toml::to_string_pretty(config)?;
    std::fs::write(path, contents)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// backup configure — local config, no Azure credentials needed
// ---------------------------------------------------------------------------

pub(crate) fn handle_backup_configure(
    vm_name: &str,
    daily_retention: Option<u32>,
    weekly_retention: Option<u32>,
    monthly_retention: Option<u32>,
    cross_region: bool,
    target_region: Option<&str>,
    resource_group: Option<&str>,
) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }

    let config = BackupConfig {
        vm_name: vm_name.to_string(),
        daily_retention,
        weekly_retention,
        monthly_retention,
        cross_region,
        target_region: target_region.map(|s| s.to_string()),
        resource_group: resource_group.map(|s| s.to_string()),
        created: chrono::Utc::now().to_rfc3339(),
    };
    save_backup_config(&config)?;

    println!("Configured backup policy for VM '{}':", vm_name);
    if let Some(d) = daily_retention {
        println!("  Daily retention:   {} days", d);
    }
    if let Some(w) = weekly_retention {
        println!("  Weekly retention:  {} weeks", w);
    }
    if let Some(m) = monthly_retention {
        println!("  Monthly retention: {} months", m);
    }
    if cross_region {
        if let Some(region) = target_region {
            println!("  Cross-region:      enabled (target: {})", region);
        } else {
            println!("  Cross-region:      enabled");
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup config-show — reads local config
// ---------------------------------------------------------------------------

pub(crate) fn handle_backup_config_show(vm_name: &str) -> Result<()> {
    match load_backup_config(vm_name) {
        Some(config) => {
            println!("Backup configuration for VM '{}':", vm_name);
            println!(
                "  Daily retention:   {}",
                config
                    .daily_retention
                    .map_or("not set".to_string(), |d| format!("{} days", d))
            );
            println!(
                "  Weekly retention:  {}",
                config
                    .weekly_retention
                    .map_or("not set".to_string(), |w| format!("{} weeks", w))
            );
            println!(
                "  Monthly retention: {}",
                config
                    .monthly_retention
                    .map_or("not set".to_string(), |m| format!("{} months", m))
            );
            if config.cross_region {
                println!(
                    "  Cross-region:      enabled (target: {})",
                    config.target_region.as_deref().unwrap_or("not set")
                );
            } else {
                println!("  Cross-region:      disabled");
            }
        }
        None => {
            println!("No backup configuration found for VM '{}'.", vm_name);
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup disable — removes local config
// ---------------------------------------------------------------------------

pub(crate) fn handle_backup_disable(vm_name: &str) -> Result<()> {
    let path = backup_config_path(vm_name);
    if path.exists() {
        std::fs::remove_file(&path)?;
        println!("Disabled backups for VM '{}'.", vm_name);
    } else {
        println!("No backup configuration found for VM '{}'.", vm_name);
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup trigger — triggers on-demand backup via az CLI
// ---------------------------------------------------------------------------

pub(crate) async fn handle_backup_trigger(
    vm_name: &str,
    tier: Option<azlin_cli::BackupTier>,
    rg: &str,
) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let tier_label = match tier {
        Some(azlin_cli::BackupTier::Daily) => "daily",
        Some(azlin_cli::BackupTier::Weekly) => "weekly",
        Some(azlin_cli::BackupTier::Monthly) => "monthly",
        None => "daily",
    };

    let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S").to_string();
    let backup_name = format!("{}-backup-{}-{}", vm_name, tier_label, ts);

    let (disk_id, location) = crate::dispatch_helpers::lookup_vm_disk_info(rg, vm_name)?;

    let pb = penguin_spinner(&format!("Creating {} backup for '{}'...", tier_label, vm_name));

    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "create",
            "--resource-group",
            rg,
            "--source",
            &disk_id,
            "--name",
            &backup_name,
            "--location",
            &location,
            "--tags",
            &format!("tier={}", tier_label),
            &format!("vm={}", vm_name),
            "type=backup",
            "--output",
            "json",
        ])
        .output()?;

    pb.finish_and_clear();
    if output.status.success() {
        println!(
            "Triggered {} backup '{}' for VM '{}'",
            tier_label, backup_name, vm_name
        );
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to trigger backup: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup list — lists backups for a VM
// ---------------------------------------------------------------------------

pub(crate) async fn handle_backup_list(
    vm_name: &str,
    tier: Option<azlin_cli::BackupTier>,
    rg: &str,
) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    // Push tier filter into JMESPath query to reduce data transfer from Azure
    let query = match &tier {
        Some(t) => {
            let tier_str = match t {
                azlin_cli::BackupTier::Daily => "daily",
                azlin_cli::BackupTier::Weekly => "weekly",
                azlin_cli::BackupTier::Monthly => "monthly",
            };
            format!(
                "[?tags.vm=='{}' && tags.type=='backup' && tags.tier=='{}']",
                vm_name, tier_str
            )
        }
        None => format!("[?tags.vm=='{}' && tags.type=='backup']", vm_name),
    };

    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            &query,
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let snapshots: Vec<serde_json::Value> =
            serde_json::from_slice(&output.stdout).unwrap_or_default();

        if snapshots.is_empty() {
            println!("No backups found for VM '{}'.", vm_name);
        } else {
            let mut table = new_table(
                &["Name", "Tier", "Disk Size (GB)", "Created", "State"],
                &[40, 8, 14, 22, 10],
            );
            for snap in &snapshots {
                let name = snap["name"].as_str().unwrap_or("-");
                let snap_tier = snap
                    .get("tags")
                    .and_then(|t| t.get("tier"))
                    .and_then(|t| t.as_str())
                    .unwrap_or("-");
                let size = snap["diskSizeGb"]
                    .as_u64()
                    .map_or("-".to_string(), |s| s.to_string());
                let created = snap["timeCreated"].as_str().unwrap_or("-");
                let state = snap["provisioningState"].as_str().unwrap_or("-");
                table.add_row(vec![
                    name.to_string(),
                    snap_tier.to_string(),
                    size,
                    created.to_string(),
                    state.to_string(),
                ]);
            }
            println!("{table}");
        }
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list backups: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup restore — restores from a named backup
// ---------------------------------------------------------------------------

pub(crate) async fn handle_backup_restore(
    vm_name: &str,
    backup_name: &str,
    force: bool,
    rg: &str,
) -> Result<()> {
    if !safe_confirm(
        &format!(
            "Restore VM '{}' from backup '{}'? This will replace the current disk.",
            vm_name, backup_name
        ),
        force,
    )? {
        println!("Cancelled.");
        return Ok(());
    }

    crate::cmd_snapshot_ops::handle_snapshot_restore(vm_name, backup_name, true, rg).await
}

// ---------------------------------------------------------------------------
// backup verify — verifies backup integrity
// ---------------------------------------------------------------------------

/// Core blocking verify — shared by single verify and parallel verify-all.
fn verify_backup_core(backup_name: &str, rg: &str) -> Result<(String, u64)> {
    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "show",
            "--resource-group",
            rg,
            "--name",
            backup_name,
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let snap: serde_json::Value = serde_json::from_slice(&output.stdout)?;
        let state = snap["provisioningState"]
            .as_str()
            .unwrap_or("Unknown")
            .to_string();
        let size = snap["diskSizeGb"].as_u64().unwrap_or(0);
        Ok((state, size))
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to verify backup '{}': {}",
            backup_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
}

pub(crate) async fn handle_backup_verify(backup_name: &str, rg: &str) -> Result<()> {
    let pb = penguin_spinner(&format!("Verifying backup '{}'...", backup_name));
    let result = verify_backup_core(backup_name, rg);
    pb.finish_and_clear();
    let (state, size) = result?;
    println!("Backup '{}': state={}, size={}GB — Verified OK", backup_name, state, size);
    Ok(())
}

// ---------------------------------------------------------------------------
// backup replicate — replicates a single backup to another region
// ---------------------------------------------------------------------------

/// Core blocking replicate — shared by single replicate and parallel replicate-all.
fn replicate_backup_core(backup_name: &str, target_region: &str, rg: &str) -> Result<String> {
    let replica_name = format!("{}-replica-{}", backup_name, target_region);

    // Query both the snapshot ID and its vm tag so we can propagate it to the replica
    let show_output = std::process::Command::new("az")
        .args([
            "snapshot",
            "show",
            "--resource-group",
            rg,
            "--name",
            backup_name,
            "--query",
            "{id: id, vm: tags.vm}",
            "--output",
            "json",
        ])
        .output()?;

    if !show_output.status.success() {
        anyhow::bail!("Backup '{}' not found.", backup_name);
    }

    let info: serde_json::Value = serde_json::from_slice(&show_output.stdout)?;
    let source_id = info["id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Backup '{}' has no resource ID.", backup_name))?;
    let vm_tag = info["vm"].as_str().unwrap_or("");

    let mut tag_args = vec![
        format!("source={}", backup_name),
        "type=replica".to_string(),
    ];
    if !vm_tag.is_empty() {
        tag_args.push(format!("vm={}", vm_tag));
    }

    let mut args = vec![
        "snapshot",
        "create",
        "--resource-group",
        rg,
        "--name",
        &replica_name,
        "--source",
        source_id,
        "--location",
        target_region,
        "--tags",
    ];
    for tag in &tag_args {
        args.push(tag);
    }
    args.push("--output");
    args.push("json");

    let output = std::process::Command::new("az").args(&args).output()?;

    if output.status.success() {
        Ok(replica_name)
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to replicate backup: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
}

pub(crate) async fn handle_backup_replicate(
    backup_name: &str,
    target_region: &str,
    rg: &str,
) -> Result<()> {
    let pb = penguin_spinner(&format!(
        "Replicating '{}' to {}...",
        backup_name, target_region
    ));
    let result = replicate_backup_core(backup_name, target_region, rg);
    pb.finish_and_clear();
    let replica_name = result?;
    println!(
        "Replicated '{}' to {} as '{}'",
        backup_name, target_region, replica_name
    );
    Ok(())
}

// ---------------------------------------------------------------------------
// backup replicate-all — replicates all backups for a VM
// ---------------------------------------------------------------------------

pub(crate) async fn handle_backup_replicate_all(
    vm_name: &str,
    target_region: &str,
    rg: &str,
) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            &format!("[?tags.vm=='{}' && tags.type=='backup'].name", vm_name),
            "--output",
            "json",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list backups: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let names: Vec<String> = serde_json::from_slice(&output.stdout).unwrap_or_default();
    if names.is_empty() {
        println!("No backups found for VM '{}'.", vm_name);
        return Ok(());
    }

    let total = names.len();
    println!(
        "Replicating {} backups for '{}' to {}...",
        total, vm_name, target_region
    );

    // Run replications in parallel via the blocking thread pool
    let mut set = tokio::task::JoinSet::new();
    for name in names {
        let region = target_region.to_string();
        let rg = rg.to_string();
        set.spawn_blocking(move || {
            replicate_backup_core(&name, &region, &rg).map(|replica| (name, replica))
        });
    }

    let mut ok_count = 0u32;
    let mut fail_count = 0u32;
    while let Some(result) = set.join_next().await {
        match result {
            Ok(Ok((name, replica))) => {
                println!("  OK: '{}' → '{}'", name, replica);
                ok_count += 1;
            }
            Ok(Err(e)) => {
                eprintln!("  FAIL: {}", e);
                fail_count += 1;
            }
            Err(join_err) => {
                eprintln!("  FAIL: task error — {}", join_err);
                fail_count += 1;
            }
        }
    }

    if fail_count > 0 {
        anyhow::bail!(
            "{} of {} backups failed to replicate",
            fail_count,
            total
        );
    }
    println!("All {} backups replicated successfully.", ok_count);
    Ok(())
}

// ---------------------------------------------------------------------------
// backup replication-status — shows replication status
// ---------------------------------------------------------------------------

pub(crate) async fn handle_replication_status(vm_name: &str, rg: &str) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            &format!(
                "[?tags.vm=='{}' && tags.type=='replica']",
                vm_name
            ),
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let replicas: Vec<serde_json::Value> =
            serde_json::from_slice(&output.stdout).unwrap_or_default();
        if replicas.is_empty() {
            println!("No replicated backups found for VM '{}'.", vm_name);
        } else {
            let mut table = new_table(
                &["Replica", "Location", "Source", "State"],
                &[40, 15, 40, 12],
            );
            for r in &replicas {
                let name = r["name"].as_str().unwrap_or("-");
                let loc = r["location"].as_str().unwrap_or("-");
                let source = r
                    .get("tags")
                    .and_then(|t| t.get("source"))
                    .and_then(|s| s.as_str())
                    .unwrap_or("-");
                let state = r["provisioningState"].as_str().unwrap_or("-");
                table.add_row(vec![
                    name.to_string(),
                    loc.to_string(),
                    source.to_string(),
                    state.to_string(),
                ]);
            }
            println!("{table}");
        }
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to get replication status: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup replication-jobs — lists replication jobs
// ---------------------------------------------------------------------------

pub(crate) async fn handle_replication_jobs(
    status_filter: Option<&str>,
    vm_filter: Option<&str>,
    rg: &str,
) -> Result<()> {
    if let Some(vm) = vm_filter {
        if let Err(e) = crate::name_validation::validate_name(vm) {
            anyhow::bail!("Invalid VM name: {}", e);
        }
    }
    let mut query = "[?tags.type=='replica']".to_string();
    if let Some(vm) = vm_filter {
        query = format!("[?tags.vm=='{}' && tags.type=='replica']", vm);
    }

    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            &query,
            "--output",
            "json",
        ])
        .output()?;

    if output.status.success() {
        let jobs: Vec<serde_json::Value> =
            serde_json::from_slice(&output.stdout).unwrap_or_default();

        let filtered: Vec<&serde_json::Value> = if let Some(st) = status_filter {
            jobs.iter()
                .filter(|j| {
                    j["provisioningState"]
                        .as_str()
                        .map_or(false, |s| s.eq_ignore_ascii_case(st))
                })
                .collect()
        } else {
            jobs.iter().collect()
        };

        if filtered.is_empty() {
            println!("No replication jobs found.");
        } else {
            let mut table = new_table(
                &["Name", "Source", "Location", "State"],
                &[40, 40, 15, 12],
            );
            for j in &filtered {
                let name = j["name"].as_str().unwrap_or("-");
                let source = j
                    .get("tags")
                    .and_then(|t| t.get("source"))
                    .and_then(|s| s.as_str())
                    .unwrap_or("-");
                let loc = j["location"].as_str().unwrap_or("-");
                let state = j["provisioningState"].as_str().unwrap_or("-");
                table.add_row(vec![
                    name.to_string(),
                    source.to_string(),
                    loc.to_string(),
                    state.to_string(),
                ]);
            }
            println!("{table}");
        }
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list replication jobs: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// backup verify-all — verifies all backups for a VM
// ---------------------------------------------------------------------------

pub(crate) async fn handle_backup_verify_all(vm_name: &str, rg: &str) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            &format!("[?tags.vm=='{}' && tags.type=='backup'].name", vm_name),
            "--output",
            "json",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list backups: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let names: Vec<String> = serde_json::from_slice(&output.stdout).unwrap_or_default();
    if names.is_empty() {
        println!("No backups found for VM '{}'.", vm_name);
        return Ok(());
    }

    let total = names.len();
    println!("Verifying {} backups for '{}'...", total, vm_name);

    // Run verifications in parallel via the blocking thread pool
    let mut set = tokio::task::JoinSet::new();
    for name in names {
        let rg = rg.to_string();
        set.spawn_blocking(move || {
            verify_backup_core(&name, &rg).map(|(state, size)| (name, state, size))
        });
    }

    let mut passed = 0u32;
    let mut failed = 0u32;
    while let Some(result) = set.join_next().await {
        match result {
            Ok(Ok((name, state, size))) => {
                println!("  OK: '{}' state={}, size={}GB", name, state, size);
                passed += 1;
            }
            Ok(Err(e)) => {
                eprintln!("  FAIL: {}", e);
                failed += 1;
            }
            Err(join_err) => {
                eprintln!("  FAIL: task error — {}", join_err);
                failed += 1;
            }
        }
    }
    println!(
        "Verification complete: {} passed, {} failed out of {} total",
        passed, failed, total
    );
    Ok(())
}

// ---------------------------------------------------------------------------
// backup verification-report — aggregate verification report
// ---------------------------------------------------------------------------

pub(crate) async fn handle_verification_report(
    days: u32,
    vm_filter: Option<&str>,
    rg: &str,
) -> Result<()> {
    if let Some(vm) = vm_filter {
        if let Err(e) = crate::name_validation::validate_name(vm) {
            anyhow::bail!("Invalid VM name: {}", e);
        }
    }
    let cutoff = chrono::Utc::now() - chrono::Duration::days(i64::from(days));

    let mut query = "[?tags.type=='backup']".to_string();
    if let Some(vm) = vm_filter {
        query = format!("[?tags.vm=='{}' && tags.type=='backup']", vm);
    }

    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            &query,
            "--output",
            "json",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list backups: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let snaps: Vec<serde_json::Value> =
        serde_json::from_slice(&output.stdout).unwrap_or_default();

    let recent: Vec<&serde_json::Value> = snaps
        .iter()
        .filter(|s| {
            s["timeCreated"]
                .as_str()
                .and_then(|t| chrono::DateTime::parse_from_rfc3339(t).ok())
                .map_or(false, |dt| dt >= cutoff)
        })
        .collect();

    let total = recent.len();
    let succeeded = recent
        .iter()
        .filter(|s| s["provisioningState"].as_str() == Some("Succeeded"))
        .count();

    println!("Backup Verification Report (last {} days):", days);
    if let Some(vm) = vm_filter {
        println!("  VM filter: {}", vm);
    }
    println!("  Total backups:  {}", total);
    println!("  Succeeded:      {}", succeeded);
    println!("  Failed:         {}", total - succeeded);
    if total > 0 {
        println!(
            "  Success rate:   {:.1}%",
            (succeeded as f64 / total as f64) * 100.0
        );
    }
    Ok(())
}
