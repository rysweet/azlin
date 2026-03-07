#[allow(unused_imports)]
use super::*;
use anyhow::Result;
use dialoguer::Confirm;

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
                    let rg = resolve_resource_group(resource_group)?;
                    if let Err(e) = crate::name_validation::validate_name(&pool) {
                        anyhow::bail!("Invalid pool name: {}", e);
                    }
                    let repo_name = repo.unwrap_or_else(|| "<not set>".to_string());
                    let label_str = labels.unwrap_or_else(|| "self-hosted".to_string());
                    let size = vm_size.unwrap_or_else(|| "Standard_B2s".to_string());

                    // Save config
                    let mut config = toml::map::Map::new();
                    config.insert("pool".to_string(), toml::Value::String(pool.clone()));
                    config.insert("repo".to_string(), toml::Value::String(repo_name.clone()));
                    config.insert("count".to_string(), toml::Value::Integer(count as i64));
                    config.insert("labels".to_string(), toml::Value::String(label_str.clone()));
                    config.insert(
                        "resource_group".to_string(),
                        toml::Value::String(rg.clone()),
                    );
                    config.insert("vm_size".to_string(), toml::Value::String(size.clone()));
                    config.insert("enabled".to_string(), toml::Value::Boolean(true));
                    config.insert(
                        "created".to_string(),
                        toml::Value::String(
                            chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string(),
                        ),
                    );
                    let val = toml::Value::Table(config);
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    std::fs::write(&pool_path, toml::to_string_pretty(&val)?)?;

                    // Provision runner VMs
                    println!("Enabling GitHub runner fleet:");
                    println!("  Repository:     {}", repo_name);
                    println!("  Pool:           {}", pool);
                    println!("  Count:          {}", count);
                    println!("  Labels:         {}", label_str);
                    println!("  VM Size:        {}", size);
                    println!("  Resource Group: {}", rg);

                    for i in 0..count {
                        let vm_name = format!("azlin-runner-{}-{}", pool, i + 1);
                        let pb = indicatif::ProgressBar::new_spinner();
                        pb.set_message(format!("Provisioning {}...", vm_name));
                        pb.enable_steady_tick(std::time::Duration::from_millis(100));
                        let out = std::process::Command::new("az")
                            .args([
                                "vm",
                                "create",
                                "--resource-group",
                                &rg,
                                "--name",
                                &vm_name,
                                "--image",
                                "Ubuntu2204",
                                "--size",
                                &size,
                                "--admin-username",
                                DEFAULT_ADMIN_USERNAME,
                                "--generate-ssh-keys",
                                "--tags",
                                &format!("azlin-runner=true pool={} repo={}", pool, repo_name),
                                "--output",
                                "json",
                            ])
                            .output()?;
                        pb.finish_and_clear();
                        if out.status.success() {
                            println!("  Provisioned VM '{}'", vm_name);
                        } else {
                            let stderr = String::from_utf8_lossy(&out.stderr);
                            eprintln!(
                                "  Failed to provision '{}': {}",
                                vm_name,
                                azlin_core::sanitizer::sanitize(stderr.trim())
                            );
                        }
                    }
                    println!(
                        "Runner fleet configuration saved to {}",
                        pool_path.display()
                    );
                    println!(
                        "Note: To complete setup, install the GitHub Actions runner on each VM."
                    );
                }
                azlin_cli::GithubRunnerAction::Disable { pool, keep_vms } => {
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    if pool_path.exists() {
                        if !keep_vms {
                            // Find and delete runner VMs
                            let rg_output = std::process::Command::new("az")
                                .args([
                                    "vm",
                                    "list",
                                    "--query",
                                    &format!("[?tags.pool=='{}'].id", pool),
                                    "--output",
                                    "tsv",
                                ])
                                .output()?;
                            if rg_output.status.success() {
                                let ids = String::from_utf8_lossy(&rg_output.stdout);
                                let id_list: Vec<&str> =
                                    ids.lines().filter(|l| !l.is_empty()).collect();
                                if !id_list.is_empty() {
                                    println!("Deleting {} runner VM(s)...", id_list.len());
                                    let mut args = vec!["vm", "delete", "--yes", "--ids"];
                                    args.extend(id_list.iter().copied());
                                    let del_output =
                                        std::process::Command::new("az").args(&args).output()?;
                                    if !del_output.status.success() {
                                        eprintln!(
                                            "Warning: VM deletion may have failed (exit {})",
                                            del_output.status.code().unwrap_or(-1)
                                        );
                                    }
                                }
                            }
                        } else {
                            println!("VMs will be kept running.");
                        }
                        std::fs::remove_file(&pool_path)?;
                        println!("Runner pool '{}' disabled.", pool);
                    } else {
                        println!("Runner pool '{}' not found.", pool);
                    }
                }
                azlin_cli::GithubRunnerAction::Status { pool } => {
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    if pool_path.exists() {
                        let content = std::fs::read_to_string(&pool_path)?;
                        let val: toml::Value = toml::from_str(&content)?;
                        println!("Runner pool '{}':", pool);
                        if let Some(t) = val.as_table() {
                            for (k, v) in t {
                                println!("  {}: {}", k, v);
                            }
                        }
                        // List actual runner VMs
                        let output = std::process::Command::new("az")
                            .args([
                                "vm",
                                "list",
                                "--query",
                                &format!(
                                    "[?tags.pool=='{}'].{{name:name, state:powerState}}",
                                    pool
                                ),
                                "--output",
                                "table",
                            ])
                            .output()?;
                        if output.status.success() {
                            let text = String::from_utf8_lossy(&output.stdout);
                            if !text.trim().is_empty() {
                                println!("\nRunner VMs:");
                                print!("{}", text);
                            }
                        }
                    } else {
                        println!("Runner pool '{}': not configured", pool);
                        println!(
                            "Enable with: azlin github-runner enable --repo <owner/repo> --pool {}",
                            pool
                        );
                    }
                }
                azlin_cli::GithubRunnerAction::Scale { pool, count } => {
                    let pool_path = runner_dir.join(format!("{}.toml", pool));
                    if pool_path.exists() {
                        let content = std::fs::read_to_string(&pool_path)?;
                        let mut val: toml::Value = toml::from_str(&content)?;
                        let old_count = val
                            .as_table()
                            .and_then(|t| t.get("count"))
                            .and_then(|v| v.as_integer())
                            .unwrap_or(0) as u32;
                        if let Some(t) = val.as_table_mut() {
                            t.insert("count".to_string(), toml::Value::Integer(count as i64));
                        }
                        std::fs::write(&pool_path, toml::to_string_pretty(&val)?)?;
                        println!(
                            "Scaled runner pool '{}': {} → {} runners",
                            pool, old_count, count
                        );
                        if count > old_count {
                            println!(
                                "Note: Provision additional VMs with 'azlin github-runner enable'"
                            );
                        }
                    } else {
                        println!("Runner pool '{}' not configured.", pool);
                    }
                }
            }
        }

        // ── Template ─────────────────────────────────────────────────
        azlin_cli::Commands::Compose { action } => match action {
            azlin_cli::ComposeAction::Up {
                file,
                resource_group,
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let f = file
                    .as_deref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "docker-compose.yml".to_string());

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
                let cmd = crate::compose_helpers::build_compose_cmd("up -d", &escaped_f);
                println!("Running 'docker compose up' on {} VM(s)...", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
            azlin_cli::ComposeAction::Down {
                file,
                resource_group,
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let f = file
                    .as_deref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "docker-compose.yml".to_string());

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
                let cmd = crate::compose_helpers::build_compose_cmd("down", &escaped_f);
                println!("Running 'docker compose down' on {} VM(s)...", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
            azlin_cli::ComposeAction::Ps {
                file,
                resource_group,
            } => {
                let auth = create_auth()?;
                let vm_manager = azlin_azure::VmManager::new(&auth);
                let rg = resolve_resource_group(resource_group)?;
                let f = file
                    .as_deref()
                    .map(|p| p.display().to_string())
                    .unwrap_or_else(|| "docker-compose.yml".to_string());

                let vms = get_running_vms_with_ips(&vm_manager, &rg).await?;
                if vms.is_empty() {
                    println!("No running VMs found in resource group '{}'", rg);
                    return Ok(());
                }

                let escaped_f = shlex::try_quote(&f).unwrap_or_else(|_| f.clone().into());
                let cmd = crate::compose_helpers::build_compose_cmd("ps", &escaped_f);
                println!("Docker compose status on {} VM(s):", vms.len());
                run_on_fleet(&vms, &cmd, true);
            }
        },

        // ── GitHub Runner ────────────────────────────────────────────
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
                    let tpl = crate::templates::build_template_toml(
                        &name,
                        description.as_deref(),
                        vm_size.as_deref(),
                        region.as_deref(),
                        cloud_init
                            .as_ref()
                            .map(|p| p.display().to_string())
                            .as_deref(),
                    );
                    let path = crate::templates::save_template(&azlin_dir, &name, &tpl)?;
                    println!("Saved template '{}' at {}", name, path.display());
                }
                azlin_cli::TemplateAction::List => {
                    let rows = crate::templates::list_templates(&azlin_dir)?;
                    if rows.is_empty() {
                        println!("No templates found.");
                    } else {
                        azlin_cli::table::render_rows(
                            &["Name", "VM Size", "Region"],
                            &rows,
                            output,
                        );
                    }
                }
                azlin_cli::TemplateAction::Show { name } => {
                    match crate::templates::load_template(&azlin_dir, &name) {
                        Ok(tpl) => println!("{}", toml::to_string_pretty(&tpl).unwrap_or_default()),
                        Err(_) => {
                            anyhow::bail!("Template '{}' not found.", name);
                        }
                    }
                }
                azlin_cli::TemplateAction::Apply { name } => {
                    match crate::templates::load_template(&azlin_dir, &name) {
                        Ok(tpl) => {
                            let vm_size = tpl
                                .get("vm_size")
                                .and_then(|v| v.as_str())
                                .unwrap_or("Standard_D4s_v3");
                            let region = tpl
                                .get("region")
                                .and_then(|v| v.as_str())
                                .unwrap_or("westus2");
                            println!(
                                "To create a VM with template '{}', run:\n  azlin new my-vm --size {} --region {}",
                                name, vm_size, region
                            );
                        }
                        Err(_) => {
                            anyhow::bail!("Template '{}' not found.", name);
                        }
                    }
                }
                azlin_cli::TemplateAction::Delete { name, force } => {
                    if crate::templates::load_template(&azlin_dir, &name).is_err() {
                        anyhow::bail!("Template '{}' not found.", name);
                    }
                    if !force {
                        let ok = Confirm::new()
                            .with_prompt(format!("Delete template '{}'?", name))
                            .default(false)
                            .interact()?;
                        if !ok {
                            println!("Cancelled.");
                            return Ok(());
                        }
                    }
                    crate::templates::delete_template(&azlin_dir, &name)?;
                    println!("Deleted template '{}'", name);
                }
                azlin_cli::TemplateAction::Export { name, output_file } => {
                    let path = azlin_dir.join(format!("{}.toml", name));
                    if !path.exists() {
                        anyhow::bail!("Template '{}' not found.", name);
                    }
                    std::fs::copy(&path, &output_file)?;
                    println!("Exported template '{}' to {}", name, output_file.display());
                }
                azlin_cli::TemplateAction::Import { input_file } => {
                    let content = std::fs::read_to_string(&input_file)?;
                    let name = crate::templates::import_template(&azlin_dir, &content)?;
                    println!("Imported template '{}' from {}", name, input_file.display());
                }
            }
        }

        // ── Autopilot ────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
