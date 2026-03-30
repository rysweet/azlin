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

async fn handle_dr_test(
    vm_name: &str,
    test_region: &str,
    backup: Option<&str>,
    rg: &str,
) -> Result<()> {
    let backup_name = match backup {
        Some(b) => b.to_string(),
        None => {
            // Find most recent backup for this VM
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

    let pb = penguin_spinner(&format!(
        "Running DR test for '{}' in {}...",
        vm_name, test_region
    ));

    // Create a test replica in the target region
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
        pb.finish_and_clear();
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

    pb.finish_and_clear();

    if create_output.status.success() {
        println!("DR test for '{}' PASSED:", vm_name);
        println!("  Backup:      {}", backup_name);
        println!("  Test region: {}", test_region);
        println!("  Test name:   {}", test_name);

        // Clean up test snapshot
        let _ = std::process::Command::new("az")
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

        // Record result
        record_dr_result(vm_name, test_region, &backup_name, true)?;
    } else {
        let stderr = String::from_utf8_lossy(&create_output.stderr);
        record_dr_result(vm_name, test_region, &backup_name, false)?;
        anyhow::bail!(
            "DR test FAILED for '{}': {}",
            vm_name,
            azlin_core::sanitizer::sanitize(stderr.trim())
        );
    }
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

    let vm_names: Vec<String> = serde_json::from_slice(&output.stdout).unwrap_or_default();
    let unique_vms: std::collections::BTreeSet<String> = vm_names.into_iter().collect();

    if unique_vms.is_empty() {
        println!("No VMs with backups found in resource group.");
        return Ok(());
    }

    println!(
        "Running DR tests for {} VMs in {} (target: {})...",
        unique_vms.len(),
        rg,
        region
    );

    let mut passed = 0u32;
    let mut failed = 0u32;
    for vm in &unique_vms {
        match handle_dr_test(vm, region, None, rg).await {
            Ok(()) => passed += 1,
            Err(e) => {
                eprintln!("  FAIL: {} — {}", vm, e);
                failed += 1;
            }
        }
    }
    println!(
        "DR test-all complete: {} passed, {} failed out of {} VMs",
        passed,
        failed,
        unique_vms.len()
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

fn load_dr_history(vm_filter: Option<&str>, days: u32) -> Vec<DrTestResult> {
    let dir = dr_history_dir();
    let entries = match std::fs::read_dir(&dir) {
        Ok(e) => e,
        Err(_) => return Vec::new(),
    };

    let cutoff = chrono::Utc::now() - chrono::Duration::days(i64::from(days));
    let mut results = Vec::new();

    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().map_or(true, |e| e != "json") {
            continue;
        }
        if let Ok(contents) = std::fs::read_to_string(&path) {
            if let Ok(result) = serde_json::from_str::<DrTestResult>(&contents) {
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
        }
    }

    results.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
    results
}

// ---------------------------------------------------------------------------
// dr test-history — show test history for a VM
// ---------------------------------------------------------------------------

fn handle_dr_test_history(vm_name: &str, days: u32) -> Result<()> {
    let results = load_dr_history(Some(vm_name), days);

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
    let results = load_dr_history(vm_filter, days);

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
