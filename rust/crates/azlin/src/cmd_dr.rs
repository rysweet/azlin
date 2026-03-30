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
        azlin_cli::Commands::Dr { action } => match action {
            azlin_cli::DrAction::Test {
                vm_name,
                test_region,
                backup,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                handle_dr_test(&vm_name, &test_region, backup.as_deref(), &rg).await?;
            }
            azlin_cli::DrAction::TestAll {
                test_region,
                resource_group,
            } => {
                let rg = resolve_resource_group(resource_group)?;
                handle_dr_test_all(test_region.as_deref(), &rg).await?;
            }
            azlin_cli::DrAction::TestHistory { vm_name, days } => {
                handle_dr_test_history(&vm_name, days)?;
            }
            azlin_cli::DrAction::SuccessRate { vm, days } => {
                handle_dr_success_rate(vm.as_deref(), days)?;
            }
        },
        _ => unreachable!(),
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// dr test — run a DR test for a single VM
// ---------------------------------------------------------------------------

/// Outcome of a successful DR test, used for reporting.
struct DrTestOutcome {
    backup_name: String,
    test_name: String,
}

/// Core blocking DR test — shared by single test and parallel test-all.
fn dr_test_core(
    vm_name: &str,
    test_region: &str,
    backup: Option<&str>,
    rg: &str,
) -> Result<DrTestOutcome> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let backup_name = match backup {
        Some(b) => b.to_string(),
        None => {
            let output = std::process::Command::new("az")
                .args([
                    "snapshot",
                    "list",
                    "--resource-group",
                    rg,
                    "--query",
                    &format!(
                        "[?tags.vm=='{}' && tags.type=='backup'] | sort_by(@, &timeCreated) | [-1].name",
                        vm_name
                    ),
                    "--output",
                    "tsv",
                ])
                .output()?;

            if !output.status.success() || output.stdout.is_empty() {
                anyhow::bail!(
                    "No backups found for VM '{}'. Create a backup first with 'azlin backup trigger {}'.",
                    vm_name,
                    vm_name
                );
            }
            String::from_utf8_lossy(&output.stdout).trim().to_string()
        }
    };

    let test_name = format!(
        "{}-dr-test-{}",
        vm_name,
        chrono::Utc::now().format("%Y%m%d_%H%M%S")
    );

    let source_output = std::process::Command::new("az")
        .args([
            "snapshot",
            "show",
            "--resource-group",
            rg,
            "--name",
            &backup_name,
            "--query",
            "id",
            "--output",
            "tsv",
        ])
        .output()?;

    if !source_output.status.success() {
        anyhow::bail!("Backup '{}' not found.", backup_name);
    }

    let source_id = String::from_utf8_lossy(&source_output.stdout)
        .trim()
        .to_string();

    let create_output = std::process::Command::new("az")
        .args([
            "snapshot",
            "create",
            "--resource-group",
            rg,
            "--name",
            &test_name,
            "--source",
            &source_id,
            "--location",
            test_region,
            "--tags",
            &format!("vm={}", vm_name),
            "type=dr-test",
            &format!("source={}", backup_name),
            "--output",
            "json",
        ])
        .output()?;

    if create_output.status.success() {
        // Clean up test snapshot — surface failure rather than silently orphaning resources
        let cleanup = std::process::Command::new("az")
            .args([
                "snapshot",
                "delete",
                "--resource-group",
                rg,
                "--name",
                &test_name,
                "--yes",
            ])
            .output();
        match cleanup {
            Ok(o) if !o.status.success() => {
                eprintln!(
                    "Warning: DR test passed but cleanup of '{}' failed (orphaned resource)",
                    test_name
                );
            }
            Err(e) => {
                eprintln!(
                    "Warning: DR test passed but cleanup of '{}' failed: {}",
                    test_name, e
                );
            }
            _ => {}
        }

        record_dr_result(vm_name, test_region, &backup_name, true)?;
        Ok(DrTestOutcome {
            backup_name,
            test_name,
        })
    } else {
        let stderr = String::from_utf8_lossy(&create_output.stderr);
        record_dr_result(vm_name, test_region, &backup_name, false)?;
        anyhow::bail!(
            "DR test FAILED for '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
}

async fn handle_dr_test(
    vm_name: &str,
    test_region: &str,
    backup: Option<&str>,
    rg: &str,
) -> Result<()> {
    let pb = penguin_spinner(&format!(
        "Running DR test for '{}' in {}...",
        vm_name, test_region
    ));
    let result = dr_test_core(vm_name, test_region, backup, rg);
    pb.finish_and_clear();
    let outcome = result?;
    println!("DR test for '{}' PASSED:", vm_name);
    println!("  Backup:      {}", outcome.backup_name);
    println!("  Test region: {}", test_region);
    println!("  Test name:   {}", outcome.test_name);
    Ok(())
}

// ---------------------------------------------------------------------------
// dr test-all — run DR tests for all VMs in a resource group
// ---------------------------------------------------------------------------

async fn handle_dr_test_all(test_region: Option<&str>, rg: &str) -> Result<()> {
    let region = test_region.unwrap_or("eastus2");

    let output = std::process::Command::new("az")
        .args([
            "snapshot",
            "list",
            "--resource-group",
            rg,
            "--query",
            "[?tags.type=='backup'].tags.vm",
            "--output",
            "json",
        ])
        .output()?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!(
            "Failed to list VMs with backups: {}",
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }

    let vm_names: Vec<String> = serde_json::from_slice(&output.stdout)
        .map_err(|e| anyhow::anyhow!("Failed to parse VM list JSON: {}", e))?;
    let unique_vms: std::collections::BTreeSet<String> = vm_names.into_iter().collect();

    if unique_vms.is_empty() {
        println!("No VMs with backups found in resource group.");
        return Ok(());
    }

    let total = unique_vms.len();
    println!(
        "Running DR tests for {} VMs in {} (target: {})...",
        total, rg, region
    );

    // Run DR tests in parallel via the blocking thread pool
    let mut set = tokio::task::JoinSet::new();
    for vm in unique_vms {
        let region = region.to_string();
        let rg = rg.to_string();
        set.spawn_blocking(move || -> (String, Result<DrTestOutcome>) {
            let result = dr_test_core(&vm, &region, None, &rg);
            (vm, result)
        });
    }

    let mut passed = 0u32;
    let mut failed = 0u32;
    while let Some(result) = set.join_next().await {
        match result {
            Ok((vm, Ok(_outcome))) => {
                println!("  PASS: {}", vm);
                passed += 1;
            }
            Ok((vm, Err(e))) => {
                eprintln!("  FAIL: {} — {}", vm, e);
                failed += 1;
            }
            Err(join_err) => {
                eprintln!("  FAIL: task error — {}", join_err);
                failed += 1;
            }
        }
    }
    println!(
        "DR test-all complete: {} passed, {} failed out of {} VMs",
        passed, failed, total
    );
    Ok(())
}

// ---------------------------------------------------------------------------
// DR result persistence (~/.azlin/dr-history/)
// ---------------------------------------------------------------------------

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize)]
struct DrTestResult {
    vm_name: String,
    test_region: String,
    backup_name: String,
    success: bool,
    timestamp: String,
}

fn dr_history_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".azlin")
        .join("dr-history")
}

fn record_dr_result(
    vm_name: &str,
    test_region: &str,
    backup_name: &str,
    success: bool,
) -> Result<()> {
    let dir = dr_history_dir();
    std::fs::create_dir_all(&dir)?;

    let ts = chrono::Utc::now();
    let result = DrTestResult {
        vm_name: vm_name.to_string(),
        test_region: test_region.to_string(),
        backup_name: backup_name.to_string(),
        success,
        timestamp: ts.to_rfc3339(),
    };

    let filename = format!(
        "{}-{}.json",
        vm_name,
        ts.format("%Y%m%d_%H%M%S")
    );
    let path = dir.join(filename);
    let json = serde_json::to_string_pretty(&result)?;
    std::fs::write(path, json)?;
    Ok(())
}

fn load_dr_history(vm_filter: Option<&str>, days: u32) -> Result<Vec<DrTestResult>> {
    let dir = dr_history_dir();
    let entries = match std::fs::read_dir(&dir) {
        Ok(e) => e,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => anyhow::bail!("Failed to read DR history directory: {}", e),
    };

    let cutoff = chrono::Utc::now() - chrono::Duration::days(i64::from(days));
    let mut results = Vec::new();

    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().map_or(true, |e| e != "json") {
            continue;
        }
        // Skip files whose name doesn't start with the VM prefix (avoids
        // unnecessary file reads and JSON parsing for large history dirs)
        if let Some(vm) = vm_filter {
            if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                if !stem.starts_with(vm) {
                    continue;
                }
            }
        }
        let contents = std::fs::read_to_string(&path)
            .map_err(|e| anyhow::anyhow!("Failed to read DR history file {}: {}", path.display(), e))?;
        let result: DrTestResult = serde_json::from_str(&contents)
            .map_err(|e| anyhow::anyhow!("Corrupt DR history file {}: {}", path.display(), e))?;
        if let Some(vm) = vm_filter {
            if result.vm_name != vm {
                continue;
            }
        }
        if let Ok(ts) = chrono::DateTime::parse_from_rfc3339(&result.timestamp) {
            if ts >= cutoff {
                results.push(result);
            }
        }
    }

    results.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
    Ok(results)
}

// ---------------------------------------------------------------------------
// dr test-history — show test history for a VM
// ---------------------------------------------------------------------------

fn handle_dr_test_history(vm_name: &str, days: u32) -> Result<()> {
    if let Err(e) = crate::name_validation::validate_name(vm_name) {
        anyhow::bail!("Invalid VM name: {}", e);
    }
    let results = load_dr_history(Some(vm_name), days)?;

    if results.is_empty() {
        println!(
            "No DR test history found for '{}' in the last {} days.",
            vm_name, days
        );
        return Ok(());
    }

    println!(
        "DR test history for '{}' (last {} days):",
        vm_name, days
    );
    let mut table = new_table(
        &["Timestamp", "Region", "Backup", "Result"],
        &[26, 15, 40, 8],
    );
    for r in &results {
        table.add_row(vec![
            r.timestamp.clone(),
            r.test_region.clone(),
            r.backup_name.clone(),
            if r.success {
                "PASS".to_string()
            } else {
                "FAIL".to_string()
            },
        ]);
    }
    println!("{table}");
    Ok(())
}

// ---------------------------------------------------------------------------
// dr success-rate — show success rate across VMs
// ---------------------------------------------------------------------------

fn handle_dr_success_rate(vm_filter: Option<&str>, days: u32) -> Result<()> {
    if let Some(vm) = vm_filter {
        if let Err(e) = crate::name_validation::validate_name(vm) {
            anyhow::bail!("Invalid VM name: {}", e);
        }
    }
    let results = load_dr_history(vm_filter, days)?;

    if results.is_empty() {
        println!("No DR test results found in the last {} days.", days);
        return Ok(());
    }

    let total = results.len();
    let passed = results.iter().filter(|r| r.success).count();

    println!("DR Test Success Rate (last {} days):", days);
    if let Some(vm) = vm_filter {
        println!("  VM filter: {}", vm);
    }
    println!("  Total tests: {}", total);
    println!("  Passed:      {}", passed);
    println!("  Failed:      {}", total - passed);
    println!(
        "  Success rate: {:.1}%",
        (passed as f64 / total as f64) * 100.0
    );
    Ok(())
}
