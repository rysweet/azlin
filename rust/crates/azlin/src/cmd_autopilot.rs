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
        azlin_cli::Commands::Autopilot { action } => match action {
            azlin_cli::AutopilotAction::Enable {
                budget,
                strategy,
                idle_threshold,
                cpu_threshold,
            } => {
                let azlin_home = home_dir()?.join(".azlin");
                std::fs::create_dir_all(&azlin_home)?;
                let ap_path = azlin_home.join("autopilot.toml");
                let ts = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
                let val = crate::handlers::build_autopilot_config(
                    budget,
                    &strategy,
                    idle_threshold,
                    cpu_threshold,
                    &ts,
                );
                std::fs::write(&ap_path, toml::to_string_pretty(&val)?)?;
                println!(
                    "{}",
                    crate::handlers::format_autopilot_enabled(
                        budget,
                        &strategy,
                        idle_threshold,
                        cpu_threshold
                    )
                );
                println!("Saved to {}", ap_path.display());
            }
            azlin_cli::AutopilotAction::Disable { keep_config } => {
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                if ap_path.exists() {
                    if keep_config {
                        let content = std::fs::read_to_string(&ap_path)?;
                        let mut val: toml::Value = toml::from_str(&content)?;
                        if let Some(t) = val.as_table_mut() {
                            t.insert("enabled".to_string(), toml::Value::Boolean(false));
                        }
                        std::fs::write(&ap_path, toml::to_string_pretty(&val)?)?;
                        println!("Autopilot disabled. Configuration preserved.");
                    } else {
                        std::fs::remove_file(&ap_path)?;
                        println!("Autopilot disabled and configuration removed.");
                    }
                } else {
                    println!("Autopilot was not configured.");
                }
            }
            azlin_cli::AutopilotAction::Status => {
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                let config = if ap_path.exists() {
                    let content = std::fs::read_to_string(&ap_path)?;
                    let val: toml::Value = toml::from_str(&content)?;
                    Some(val)
                } else {
                    None
                };
                println!(
                    "{}",
                    crate::handlers::format_autopilot_status(config.as_ref())
                );
            }
            azlin_cli::AutopilotAction::Config { set, show } => {
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                if show || set.is_empty() {
                    if ap_path.exists() {
                        let content = std::fs::read_to_string(&ap_path)?;
                        print!("{}", content);
                    } else {
                        println!("No autopilot configuration found.");
                    }
                } else {
                    let content = if ap_path.exists() {
                        std::fs::read_to_string(&ap_path)?
                    } else {
                        String::new()
                    };
                    let mut val: toml::Value = if content.is_empty() {
                        toml::Value::Table(toml::map::Map::new())
                    } else {
                        toml::from_str(&content)?
                    };
                    if let Some(t) = val.as_table_mut() {
                        for kv in &set {
                            if let Some((k, v)) = kv.split_once('=') {
                                t.insert(k.to_string(), toml::Value::String(v.to_string()));
                                println!("Set {} = {}", k, v);
                            }
                        }
                    }
                    std::fs::write(&ap_path, toml::to_string_pretty(&val)?)?;
                }
            }
            azlin_cli::AutopilotAction::Run { dry_run } => {
                // Check VM utilization and recommend actions
                let rg = resolve_resource_group(None)?;
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let vms = vm_manager.list_vms(&rg)?;
                let ap_path = home_dir()?.join(".azlin").join("autopilot.toml");
                let ap_config = if ap_path.exists() {
                    let content = std::fs::read_to_string(&ap_path)?;
                    let val: toml::Value = toml::from_str(&content)?;
                    Some(val)
                } else {
                    None
                };
                let (idle_threshold, cost_limit) =
                    crate::handlers::parse_autopilot_thresholds(ap_config.as_ref());
                println!(
                    "Autopilot check (idle threshold: {} min, cost limit: ${:.2}):",
                    idle_threshold, cost_limit
                );

                let mut actions: Vec<(String, String)> = Vec::new();
                for vm in &vms {
                    if vm.power_state != azlin_core::models::PowerState::Running {
                        continue;
                    }
                    let ip = vm.public_ip.as_deref().or(vm.private_ip.as_deref());
                    if let Some(ip) = ip {
                        let user = vm
                            .admin_username
                            .as_deref()
                            .unwrap_or(DEFAULT_ADMIN_USERNAME);
                        // Check CPU and uptime via SSH
                        let output = std::process::Command::new("ssh")
                            .args([
                                "-o", "StrictHostKeyChecking=accept-new",
                                "-o", "ConnectTimeout=10",
                                "-o", "BatchMode=yes",
                                &format!("{}@{}", user, ip),
                                "awk '{u=$2+$4; t=$2+$4+$5; if (t>0) printf \"%.1f\", u*100/t; else print \"0\"}' /proc/stat | head -1 && cat /proc/uptime | awk '{print $1}'",
                            ])
                            .output();
                        if let Ok(out) = output {
                            if out.status.success() {
                                let text = String::from_utf8_lossy(&out.stdout);
                                let lines: Vec<&str> = text.trim().lines().collect();
                                let cpu_pct: f64 = match lines.first().and_then(|s| s.parse().ok())
                                {
                                    Some(v) => v,
                                    None => {
                                        eprintln!(
                                            "  Warning: {} — failed to parse CPU stats, skipping",
                                            vm.name
                                        );
                                        continue;
                                    }
                                };
                                let uptime_secs: f64 =
                                    match lines.get(1).and_then(|s| s.parse().ok()) {
                                        Some(v) => v,
                                        None => {
                                            eprintln!(
                                                "  Warning: {} — failed to parse uptime, skipping",
                                                vm.name
                                            );
                                            continue;
                                        }
                                    };
                                if let Some(action_name) = crate::handlers::classify_autopilot_vm(
                                    cpu_pct,
                                    uptime_secs,
                                    idle_threshold,
                                ) {
                                    println!(
                                        "  ⚠ {} — CPU {} for {:.0}min — IDLE (recommend {})",
                                        vm.name,
                                        crate::health_helpers::format_percentage(cpu_pct as f32),
                                        uptime_secs / 60.0,
                                        action_name
                                    );
                                    actions.push((vm.name.clone(), action_name));
                                } else {
                                    println!(
                                        "  ✓ {} — CPU {} — active",
                                        vm.name,
                                        crate::health_helpers::format_percentage(cpu_pct as f32)
                                    );
                                }
                            } else {
                                println!("  ? {} — could not check (SSH failed)", vm.name);
                            }
                        } else {
                            println!("  ? {} — could not check (SSH unavailable)", vm.name);
                        }
                    }
                }

                if actions.is_empty() {
                    println!("No cost-saving actions needed at this time.");
                } else if dry_run {
                    println!("{}", crate::handlers::format_autopilot_dry_run(&actions));
                } else {
                    println!("\nApplying {} action(s):", actions.len());
                    for (name, action) in &actions {
                        if action == "deallocate" {
                            print!("  Deallocating {}...", name);
                            let result = vm_manager.stop_vm(&rg, name, true);
                            match result {
                                Ok(_) => println!(" ✓ done"),
                                Err(e) => println!(" ✗ failed: {}", e),
                            }
                        }
                    }
                }
            }
        },

        // ── Context ──────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
