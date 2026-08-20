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
                azlin_cli::AuthAction::Test {
                    profile,
                    subscription_id,
                } => {
                    // `--profile` reached only the spinner text: this ran
                    // `az account show` and reported "Authentication
                    // successful!" about whatever the CLI happened to be
                    // logged into, for a profile it never opened. And
                    // `--subscription-id` ("Test specific subscription
                    // access") was discarded outright (#1089).
                    let stored = crate::auth_profile::load(&azlin_dir, &profile)?;

                    // What to check against: the flag if given, else the
                    // profile's own subscription. A test with nothing to check
                    // against is not a test.
                    let want = match subscription_id.as_deref() {
                        Some(id) => id,
                        None => crate::auth_profile::require_subscription(&stored)?,
                    };

                    let pb = penguin_spinner(&format!(
                        "Checking access to subscription {} for profile '{}'...",
                        want, profile
                    ));
                    let result = azlin_azure::AzureAuth::for_subscription(want);
                    pb.finish_and_clear();

                    let auth = result.map_err(|e| {
                        anyhow::anyhow!(
                            "Profile '{}' cannot reach subscription {}: {}\n\
                             Run 'az login' for the tenant that owns it.",
                            profile,
                            want,
                            e
                        )
                    })?;

                    let key_style = Style::new().cyan().bold();
                    println!(
                        "{}",
                        Style::new().green().bold().apply_to("Access confirmed.")
                    );
                    println!(
                        "{}: {}",
                        key_style.apply_to("Subscription"),
                        auth.subscription_id()
                    );
                    if let Some(tenant) = auth.tenant_id() {
                        println!("{}: {}", key_style.apply_to("Tenant"), tenant);
                        // A profile pinning a different tenant is a real
                        // failure, not a note: the subscription id matched but
                        // the identity behind it is not the one recorded.
                        if let Some(want_tenant) = stored.tenant_id.as_deref() {
                            if want_tenant != tenant {
                                anyhow::bail!(
                                    "Profile '{}' records tenant {} but the Azure CLI is \
                                     signed in to {}.",
                                    profile,
                                    want_tenant,
                                    tenant
                                );
                            }
                        }
                    }
                    // Do not overstate what was checked. No login was
                    // performed as the profile's principal; a profile stores
                    // no secret.
                    println!(
                        "  Checked with the current `az` session, not by signing in as \
                         client {}. A profile stores no secret.",
                        stored.client_id.as_deref().unwrap_or("-")
                    );
                }
                azlin_cli::AuthAction::Setup {
                    profile,
                    tenant_id,
                    client_id,
                    subscription_id,
                    use_certificate,
                    certificate_path,
                } => {
                    use dialoguer::Input;

                    // Both certificate flags were accepted and discarded
                    // (#1089): `--use-certificate` produced a profile
                    // indistinguishable from a password-based one, and a
                    // `--certificate-path` pointing at nothing was recorded as
                    // success. Validated before anything is prompted for, so a
                    // typo'd path is not found out after three questions.
                    crate::auth_profile::validate_certificate_flags(
                        use_certificate,
                        certificate_path.as_deref(),
                    )?;

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

                    let stored = crate::auth_profile::AuthProfile {
                        name: profile.clone(),
                        tenant_id: Some(tenant),
                        client_id: Some(client),
                        subscription_id: Some(subscription),
                        use_certificate,
                        certificate_path: certificate_path.clone(),
                    };
                    let profile_data = crate::auth_profile::to_json(&stored);

                    let profile_path = profiles_dir.join(format!("{}.json", profile));
                    std::fs::write(&profile_path, serde_json::to_string_pretty(&profile_data)?)?;
                    println!("Saved profile '{}' to {}", profile, profile_path.display());
                    if use_certificate {
                        if let Some(path) = &certificate_path {
                            println!("  Certificate: {}", path.display());
                        }
                    }
                    // Say what the profile can and cannot do. It stores no
                    // secret, so azlin cannot log in as this principal; what a
                    // profile pins is the subscription and tenant a command
                    // runs against.
                    println!(
                        "  `--auth-profile {}` will run commands against subscription {}. \
                         azlin does not log in as this principal — sign in to its tenant \
                         with `az login` first.",
                        profile,
                        stored.subscription_id.as_deref().unwrap_or("-")
                    );
                }
                azlin_cli::AuthAction::Remove { profile, yes } => {
                    if let Err(e) = crate::name_validation::validate_name(&profile) {
                        anyhow::bail!("Invalid profile name: {}", e);
                    }
                    let profile_path = azlin_dir.join("profiles").join(format!("{}.json", profile));
                    if !profile_path.exists() {
                        anyhow::bail!("Profile '{}' not found.", profile);
                    }

                    if !safe_confirm_with_flag(
                        &format!("Remove profile '{}'?", profile),
                        yes,
                        "--yes",
                    )? {
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
