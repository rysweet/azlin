#[allow(unused_imports)]
use super::*;
use anyhow::{Context, Result};
use console::Style;

pub(crate) async fn dispatch(
    command: azlin_cli::Commands,
    verbose: bool,
    output: &azlin_cli::OutputFormat,
) -> Result<()> {
    #[allow(unused_variables)]
    let _ = (verbose, output);
    match command {
        azlin_cli::Commands::Auth { action } => {
            let azlin_dir = home_dir()?.join(".azlin");

            match action {
                azlin_cli::AuthAction::List => {
                    let profiles_dir = azlin_dir.join("profiles");
                    if !profiles_dir.exists() {
                        println!("No authentication profiles found.");
                        return Ok(());
                    }

                    let entries = std::fs::read_dir(&profiles_dir)?;
                    let mut rows: Vec<Vec<String>> = Vec::new();

                    for entry in entries {
                        let entry = entry?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        if name.ends_with(".json") {
                            let content = std::fs::read_to_string(entry.path())?;
                            let profile: serde_json::Value = serde_json::from_str(&content)
                                .context(format!("Failed to parse auth profile '{}'", name))?;
                            let profile_name = name.trim_end_matches(".json");
                            rows.push(vec![
                                profile_name.to_string(),
                                profile["tenant_id"].as_str().unwrap_or("-").to_string(),
                                profile["client_id"].as_str().unwrap_or("-").to_string(),
                            ]);
                        }
                    }

                    if rows.is_empty() {
                        println!("No authentication profiles found.");
                    } else {
                        azlin_cli::table::render_rows(
                            &["Profile", "Tenant ID", "Client ID"],
                            &rows,
                            output,
                        );
                    }
                }
                azlin_cli::AuthAction::Show { profile } => {
                    if let Err(e) = crate::name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        anyhow::bail!("Profile '{}' not found.", profile);
                    }

                    let content = std::fs::read_to_string(&profile_path)?;
                    let data: serde_json::Value = serde_json::from_str(&content)
                        .context(format!("Failed to parse auth profile '{}'", profile))?;
                    let key_style = Style::new().cyan().bold();

                    println!("{}: {}", key_style.apply_to("Profile"), profile);
                    if let Some(obj) = data.as_object() {
                        for (k, v) in obj {
                            let display = crate::auth_helpers::mask_profile_value(k, v);
                            println!("{}: {}", key_style.apply_to(k), display);
                        }
                    }
                }
                azlin_cli::AuthAction::Test { profile, .. } => {
                    let pb = indicatif::ProgressBar::new_spinner();
                    pb.set_message(format!(
                        "Testing authentication for profile '{}'...",
                        profile
                    ));
                    pb.enable_steady_tick(std::time::Duration::from_millis(100));

                    let output = std::process::Command::new("az")
                        .args(["account", "show", "--output", "json"])
                        .output()?;

                    pb.finish_and_clear();
                    if output.status.success() {
                        let acct: serde_json::Value = serde_json::from_slice(&output.stdout)
                            .context("Failed to parse 'az account show' JSON")?;
                        let key_style = Style::new().cyan().bold();
                        let (subscription, tenant, user) =
                            crate::auth_test_helpers::extract_account_info(&acct);
                        println!(
                            "{}",
                            Style::new()
                                .green()
                                .bold()
                                .apply_to("Authentication successful!")
                        );
                        println!("{}: {}", key_style.apply_to("Subscription"), subscription);
                        println!("{}: {}", key_style.apply_to("Tenant"), tenant);
                        println!("{}: {}", key_style.apply_to("User"), user);
                    } else {
                        anyhow::bail!(
                            "Authentication test failed. Run 'az login' to authenticate."
                        );
                    }
                }
                azlin_cli::AuthAction::Setup {
                    profile,
                    tenant_id,
                    client_id,
                    subscription_id,
                    ..
                } => {
                    use dialoguer::Input;

                    let tenant = match tenant_id {
                        Some(t) => t,
                        None => Input::new()
                            .with_prompt("Azure Tenant ID")
                            .interact_text()?,
                    };
                    let client = match client_id {
                        Some(c) => c,
                        None => Input::new()
                            .with_prompt("Azure Client ID")
                            .interact_text()?,
                    };
                    let subscription = match subscription_id {
                        Some(s) => s,
                        None => Input::new()
                            .with_prompt("Azure Subscription ID")
                            .interact_text()?,
                    };

                    let profiles_dir = azlin_dir.join("profiles");
                    std::fs::create_dir_all(&profiles_dir)?;

                    if let Err(e) = crate::name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }

                    let profile_data = serde_json::json!({
                        "tenant_id": tenant,
                        "client_id": client,
                        "subscription_id": subscription,
                    });

                    let profile_path = profiles_dir.join(format!("{}.json", profile));
                    std::fs::write(&profile_path, serde_json::to_string_pretty(&profile_data)?)?;
                    println!("Saved profile '{}' to {}", profile, profile_path.display());
                }
                azlin_cli::AuthAction::Remove { profile, yes } => {
                    if let Err(e) = crate::name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        anyhow::bail!("Profile '{}' not found.", profile);
                    }

                    if !safe_confirm(&format!("Remove profile '{}'?", profile), yes)? {
                        println!("Cancelled.");
                        return Ok(());
                    }

                    std::fs::remove_file(&profile_path)?;
                    println!("Removed profile '{}'", profile);
                }
            }
        }
        // ── NLP Commands ──────────────────────────────────────────────
        _ => unreachable!(),
    }
    Ok(())
}
