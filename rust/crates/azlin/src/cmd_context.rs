#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Context { action } => {
            let azlin_home = home_dir()?.join(".azlin");
            let ctx_dir = azlin_home.join("contexts");
            let active_ctx_path = azlin_home.join("active-context");
            std::fs::create_dir_all(&ctx_dir)?;

            match action {
                azlin_cli::ContextAction::List { .. } => {
                    let active = std::fs::read_to_string(&active_ctx_path)
                        .map(|s| s.trim().to_string())
                        .unwrap_or_default();
                    let ctx_list = crate::contexts::list_contexts(&ctx_dir, &active)?;
                    if ctx_list.is_empty() {
                        println!("{}", crate::handlers::format_no_contexts());
                    } else {
                        let rows: Vec<Vec<String>> = ctx_list
                            .iter()
                            .map(|(name, is_active)| {
                                vec![
                                    name.clone(),
                                    if *is_active { "true" } else { "false" }.to_string(),
                                ]
                            })
                            .collect();
                        match output {
                            azlin_cli::OutputFormat::Table => {
                                print!("{}", crate::handlers::format_context_list_table(&ctx_list));
                            }
                            _ => {
                                azlin_cli::table::render_rows(&["Name", "Active"], &rows, output);
                            }
                        }
                    }
                }
                azlin_cli::ContextAction::Show { .. } => {
                    match std::fs::read_to_string(&active_ctx_path) {
                        Ok(name) => {
                            let name = name.trim().to_string();
                            let path = ctx_dir.join(format!("{}.toml", name));
                            let content = std::fs::read_to_string(&path).ok();
                            println!(
                                "{}",
                                crate::handlers::format_context_show(&name, content.as_deref())
                            );
                        }
                        Err(_) => println!("No context selected."),
                    }
                }
                azlin_cli::ContextAction::Use { name, .. } => {
                    if let Err(e) = crate::name_validation::validate_name(&name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    let ctx_path = ctx_dir.join(format!("{}.toml", name));
                    if !ctx_path.exists() {
                        anyhow::bail!("Context '{}' not found.", name);
                    }
                    std::fs::write(&active_ctx_path, &name)?;
                    println!("{}", crate::handlers::format_context_switched(&name));
                }
                azlin_cli::ContextAction::Create {
                    name,
                    subscription_id,
                    tenant_id,
                    resource_group,
                    region,
                    key_vault_name,
                    ..
                } => {
                    if let Err(e) = crate::name_validation::validate_name(&name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    let toml_str = crate::contexts::build_context_toml(
                        &name,
                        subscription_id.as_deref(),
                        tenant_id.as_deref(),
                        resource_group.as_deref(),
                        region.as_deref(),
                        key_vault_name.as_deref(),
                    )?;
                    let path = ctx_dir.join(format!("{}.toml", name));
                    std::fs::write(&path, &toml_str)?;
                    println!("{}", crate::handlers::format_context_created(&name));
                }
                azlin_cli::ContextAction::Delete { name, force, .. } => {
                    if let Err(e) = crate::name_validation::validate_name(&name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    let path = ctx_dir.join(format!("{}.toml", name));
                    if !path.exists() {
                        anyhow::bail!("Context '{}' not found.", name);
                    }
                    if !safe_confirm(&format!("Delete context '{}'?", name), force)? {
                        println!("Cancelled.");
                        return Ok(());
                    }
                    std::fs::remove_file(&path)?;
                    // Clear active context if it was the deleted one
                    if let Ok(active) = std::fs::read_to_string(&active_ctx_path) {
                        if active.trim() == name {
                            let _ = std::fs::remove_file(&active_ctx_path);
                        }
                    }
                    println!("{}", crate::handlers::format_context_deleted(&name));
                }
                azlin_cli::ContextAction::Rename {
                    old_name, new_name, ..
                } => {
                    if let Err(e) = crate::name_validation::validate_name(&old_name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    if let Err(e) = crate::name_validation::validate_name(&new_name) {
                        anyhow::bail!("Invalid context name: {}", e);
                    }
                    crate::contexts::rename_context_file(&ctx_dir, &old_name, &new_name)?;
                    // Update active context if it was the renamed one
                    if let Ok(active) = std::fs::read_to_string(&active_ctx_path) {
                        if active.trim() == old_name {
                            std::fs::write(&active_ctx_path, &new_name)?;
                        }
                    }
                    println!(
                        "{}",
                        crate::handlers::format_context_renamed(&old_name, &new_name)
                    );
                }
                azlin_cli::ContextAction::Migrate { force, .. } => {
                    // Check for legacy config.toml with subscription/tenant at top level
                    let cfg = azlin_core::AzlinConfig::load()
                        .context("Failed to load azlin config for migration")?;
                    let sub = cfg.default_resource_group.as_ref().and_then(|_| {
                        let out = std::process::Command::new("az")
                            .args(["account", "show", "--query", "id", "-o", "tsv"])
                            .output()
                            .ok()?;
                        if out.status.success() {
                            Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
                        } else {
                            None
                        }
                    });
                    let tenant = std::process::Command::new("az")
                        .args(["account", "show", "--query", "tenantId", "-o", "tsv"])
                        .output()
                        .ok()
                        .and_then(|o| {
                            if o.status.success() {
                                Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
                            } else {
                                None
                            }
                        });

                    if let (Some(sub_id), Some(tenant_id)) = (sub, tenant) {
                        let ctx_name = "default";
                        let ctx_path = ctx_dir.join(format!("{}.toml", ctx_name));
                        if ctx_path.exists() && !force {
                            println!("Context 'default' already exists. Use --force to overwrite.");
                        } else {
                            let mut ctx = toml::map::Map::new();
                            ctx.insert(
                                "name".to_string(),
                                toml::Value::String(ctx_name.to_string()),
                            );
                            ctx.insert("subscription_id".to_string(), toml::Value::String(sub_id));
                            ctx.insert("tenant_id".to_string(), toml::Value::String(tenant_id));
                            if let Some(rg) = &cfg.default_resource_group {
                                ctx.insert(
                                    "resource_group".to_string(),
                                    toml::Value::String(rg.clone()),
                                );
                            }
                            if !cfg.default_region.is_empty() {
                                ctx.insert(
                                    "region".to_string(),
                                    toml::Value::String(cfg.default_region.clone()),
                                );
                            }
                            let val = toml::Value::Table(ctx);
                            std::fs::write(&ctx_path, toml::to_string_pretty(&val)?)?;
                            std::fs::write(&active_ctx_path, ctx_name)?;
                            println!("Migrated legacy config to context '{}'", ctx_name);
                        }
                    } else {
                        println!("Could not determine subscription/tenant from az account. Run 'az login' first.");
                    }
                }
            }
        }

        // ── Disk ─────────────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
