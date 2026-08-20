#[allow(unused_imports)]
use super::*;
use anyhow::Result;

pub(crate) async fn handle_ask(
    query: Option<String>,
    resource_group: Option<String>,
    dry_run: bool,
    timeout: u32,
    auth_profile: Option<String>,
) -> Result<()> {
    let query_text = query.ok_or_else(|| anyhow::anyhow!("No query provided."))?;

    if dry_run {
        println!("Would query Claude API with: {}", query_text);
        return Ok(());
    }

    // `--auth-profile` was accepted and discarded (#1089). `ask` describes the
    // environment to the model rather than acting on it, so what the flag
    // changes is which subscription gets described — and an answer about
    // somebody else's infrastructure is the failure it prevents.
    //
    // Resolved before the API client is built, so a profile that does not
    // exist is reported as such instead of being shadowed by an unrelated
    // missing `ANTHROPIC_API_KEY`. Resolving costs an `az` round-trip, so it
    // happens only when the flag was actually passed: `azlin ask` without one
    // makes no Azure call, exactly as before.
    let subscription = match auth_profile.as_deref() {
        Some(name) => Some(
            crate::dispatch_helpers::create_auth_with_profile(Some(name))?
                .subscription_id()
                .to_string(),
        ),
        None => None,
    };

    let client = azlin_ai::AnthropicClient::new()?;
    // Full precedence: --resource-group, then the active context, then the
    // config default. Reading the config default directly here skipped the
    // context entirely (#1090).
    let rg = crate::dispatch_helpers::resolve_resource_group(resource_group)?;

    let context = match &subscription {
        Some(sub) => format!("Resource group: {}\nSubscription: {}", rg, sub),
        None => format!("Resource group: {}", rg),
    };
    let pb = penguin_spinner("Querying Claude...");
    // `--timeout` was accepted and discarded, so an API call that never came
    // back left the spinner turning until the user gave up (#1089). The bound
    // is on the whole request rather than on connect, because a stalled
    // response body is the shape that actually happens.
    //
    // `--timeout 0` means "no limit", the same reading `timeout(1)` gives it
    // and the same one every other azlin timeout flag has. Handing 0 to
    // `tokio::time::timeout` would instead fire immediately, so 0 would mean
    // "no limit" on four commands and "fail instantly" on this one.
    let request = client.ask(&query_text, &context);
    let answer = if timeout == 0 {
        Ok(request.await)
    } else {
        tokio::time::timeout(std::time::Duration::from_secs(timeout as u64), request).await
    };
    pb.finish_and_clear();
    match answer {
        Ok(result) => println!("{}", result?),
        Err(_) => anyhow::bail!(
            "The Claude API did not answer within {}s (--timeout). Raise --timeout, \
             use --timeout 0 for no limit, or re-run with --dry-run to see the query \
             without sending it.",
            timeout
        ),
    }
    Ok(())
}

/// The resource group an `az` command names, if it names one.
///
/// Reads `-g`/`--resource-group` out of an already-split argv. `None` means
/// the command carries no group of its own and will inherit whatever `az`
/// defaults to.
pub(crate) fn command_resource_group(argv: &[String]) -> Option<&str> {
    for (i, arg) in argv.iter().enumerate() {
        if arg == "-g" || arg == "--resource-group" {
            return argv.get(i + 1).map(String::as_str);
        }
        if let Some(value) = arg.strip_prefix("--resource-group=") {
            return Some(value);
        }
    }
    None
}

/// Which generated commands would run against a different resource group.
///
/// `azlin do --resource-group X` used to discard the flag entirely, so the
/// model was never told which group to use and the commands it produced ran
/// against whatever `az` happened to default to. Telling the model is half the
/// fix; this is the other half, because a model's answer is not a guarantee.
///
/// Returns `(index, group)` pairs so the caller can name the offending line.
pub(crate) fn conflicting_resource_groups<'a>(
    commands: &'a [Vec<String>],
    expected: &str,
) -> Vec<(usize, &'a str)> {
    commands
        .iter()
        .enumerate()
        .filter_map(|(i, argv)| match command_resource_group(argv) {
            Some(g) if !g.eq_ignore_ascii_case(expected) => Some((i, g)),
            _ => None,
        })
        .collect()
}

/// Ask the model to work inside one resource group.
///
/// Appended rather than templated over the request so the user's own words
/// stay intact and first.
pub(crate) fn scope_request_to_resource_group(request: &str, resource_group: &str) -> String {
    format!(
        "{request}\n\nUse the Azure resource group '{resource_group}' for every command. \
         Pass it explicitly as --resource-group rather than relying on any default."
    )
}

pub(crate) async fn handle_do(
    request: &str,
    dry_run: bool,
    yes: bool,
    verbose: bool,
    resource_group: Option<String>,
) -> Result<()> {
    let client = azlin_ai::AnthropicClient::new()?;
    let rg = resolve_resource_group(resource_group)?;

    let pb = penguin_spinner("Generating commands...");
    let commands = client
        .execute(&scope_request_to_resource_group(request, &rg))
        .await?;
    pb.finish_and_clear();

    if commands.is_empty() {
        println!("No commands generated.");
        return Ok(());
    }

    println!("Generated commands (resource group '{}'):", rg);
    for (i, cmd) in commands.iter().enumerate() {
        println!("  {}. {}", i + 1, cmd);
    }

    // A model told which group to use is not a model that used it. Every
    // command that names a *different* group is refused before any of them
    // runs — partially executing a batch that turned out to target the wrong
    // subscription slice is worse than executing none of it.
    let parsed: Vec<Vec<String>> = commands
        .iter()
        .map(|c| shlex::split(c.trim()).unwrap_or_default())
        .collect();

    // The check above only sees commands that name a group. One that names
    // none inherits whatever `az` currently defaults to, which is the failure
    // `--resource-group` exists to prevent and the one most likely to occur:
    // a model told the group will often omit it on read-only commands.
    // Injecting `-g` is not the answer — not every `az` command accepts one,
    // and guessing which do is worse than not guessing — but the user approves
    // this plan before it runs, so the plan is where the residual risk belongs.
    let ungrouped = parsed
        .iter()
        .filter(|argv| !argv.is_empty() && command_resource_group(argv).is_none())
        .count();
    if ungrouped > 0 {
        println!(
            "  ({} command(s) name no resource group and will use whatever `az` \
             currently defaults to.)",
            ungrouped
        );
    }

    let conflicts = conflicting_resource_groups(&parsed, &rg);
    if !conflicts.is_empty() {
        let detail = conflicts
            .iter()
            .map(|(i, g)| format!("  {}. targets '{}'", i + 1, g))
            .collect::<Vec<_>>()
            .join("\n");
        anyhow::bail!(
            "Refusing to run: {} generated command(s) target a resource group other than \
             '{}':\n{}\nRe-run with --resource-group set to the group you meant, or rephrase \
             the request.",
            conflicts.len(),
            rg,
            detail
        );
    }

    if dry_run {
        return Ok(());
    }

    if !safe_confirm_with_flag("Execute these commands?", yes, "--yes")? {
        println!("Cancelled.");
        return Ok(());
    }

    for cmd in &commands {
        let cmd_str = cmd.trim();
        if cmd_str.is_empty() {
            continue;
        }
        if !cmd_str.starts_with("az ") {
            eprintln!("Skipping non-Azure command: {}", cmd_str);
            continue;
        }
        let parts = match shlex::split(cmd_str) {
            Some(p) if !p.is_empty() => p,
            _ => {
                eprintln!("Failed to parse command: {}", cmd_str);
                continue;
            }
        };
        if verbose {
            eprintln!("[verbose] Executing: {}", cmd_str);
        }
        println!("$ {}", cmd_str);
        let output = std::process::Command::new(&parts[0])
            .args(&parts[1..])
            .output()?;
        let stdout = String::from_utf8_lossy(&output.stdout);
        let stderr = String::from_utf8_lossy(&output.stderr);
        if !stdout.is_empty() {
            print!("{}", stdout);
        }
        if verbose && !stderr.is_empty() {
            eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
        }
        if !output.status.success() {
            eprintln!("Command failed with exit code: {:?}", output.status.code());
            if !verbose && !stderr.is_empty() {
                eprint!("{}", azlin_core::sanitizer::sanitize(&stderr));
            }
        }
    }
    Ok(())
}

pub(crate) async fn handle_doit_deploy(
    request: &str,
    dry_run: bool,
    yes: bool,
    output_dir: Option<std::path::PathBuf>,
    max_iterations: u32,
    quiet: bool,
) -> Result<()> {
    // Three flags accepted and discarded (#1089). `--max-iterations` is the
    // one that mattered: nothing bounded how many commands a model could hand
    // back to be executed against a live subscription, while `--help` said 50.
    let verbosity = crate::doit_deploy::Verbosity::new(quiet);
    if let Some(ref dir) = output_dir {
        // Before the API call, so a directory that cannot be created is a
        // failure the user can fix rather than one that arrives after paying
        // for a plan.
        crate::doit_deploy::prepare_output_dir(dir)?;
    }

    let client = azlin_ai::AnthropicClient::new()?;

    let system_context = "You are azlin, an Azure VM fleet management tool. \
        Generate a list of azlin CLI commands to accomplish the user's request.\n\
        Format: one command per line, each an 'az' CLI command.\n\
        Available operations: az vm list, az vm start, az vm stop, az vm create, \
        az vm delete, az group create, az network nsg create, etc.";

    let pb = penguin_spinner("Generating deployment plan...");
    let commands = client.ask(request, system_context).await?;
    pb.finish_and_clear();

    if let Some(ref dir) = output_dir {
        let path = crate::doit_deploy::plan_path(dir);
        std::fs::write(&path, &commands)
            .with_context(|| format!("Could not write the plan to {}", path.display()))?;
        if verbosity.shows_progress() {
            println!("Plan written to {}", path.display());
        }
    }

    if verbosity.shows_progress() {
        println!("Plan:\n{}\n", commands);
    }

    if dry_run {
        return Ok(());
    }

    // Counted before the prompt: being asked to confirm a plan that will then
    // be refused wastes the one decision the user gets to make.
    let planned = crate::doit_deploy::plan_commands(&commands);
    if let Some(refusal) = crate::doit_deploy::over_iteration_limit(planned.len(), max_iterations) {
        anyhow::bail!("{}", refusal);
    }

    // Not gated on --quiet: a prompt nobody sees is a prompt nobody can answer.
    if !safe_confirm_with_flag("Execute this plan?", yes, "--yes")? {
        println!("Cancelled.");
        return Ok(());
    }

    // Written after every command, not once at the end: a run that stops
    // halfway is exactly the run whose transcript matters, and a command that
    // cannot be spawned returns before any end-of-loop write.
    let transcript_file = output_dir
        .as_ref()
        .map(|dir| crate::doit_deploy::transcript_path(dir));
    let mut transcript = String::new();
    for trimmed in planned {
        let parts = match shlex::split(trimmed) {
            Some(p) if !p.is_empty() => p,
            _ => {
                eprintln!("Failed to parse command: {}", trimmed);
                transcript.push_str(&format!("unparsed {}\n", trimmed));
                continue;
            }
        };
        if verbosity.shows_progress() {
            println!("-> {}", trimmed);
        }
        let status = std::process::Command::new(&parts[0])
            .args(&parts[1..])
            .status();
        transcript.push_str(&match &status {
            Ok(s) => crate::doit_deploy::transcript_line(trimmed, s.code()),
            Err(e) => crate::doit_deploy::transcript_unspawnable_line(trimmed, &e.to_string()),
        });
        if let Some(ref path) = transcript_file {
            std::fs::write(path, &transcript)
                .with_context(|| format!("Could not write the transcript to {}", path.display()))?;
        }
        // Propagated only after the transcript has recorded it.
        let status = status?;
        if !status.success() {
            // Never gated on --quiet.
            eprintln!("Command failed with exit code: {:?}", status.code());
        }
    }

    if let Some(ref path) = transcript_file {
        if verbosity.shows_progress() {
            println!("Transcript written to {}", path.display());
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn argv(s: &str) -> Vec<String> {
        shlex::split(s).unwrap()
    }

    // ── `azlin do --resource-group` (#1089) ──────────────────────────

    #[test]
    fn the_short_and_long_forms_are_both_read() {
        assert_eq!(
            command_resource_group(&argv("az vm list -g rg-a")),
            Some("rg-a")
        );
        assert_eq!(
            command_resource_group(&argv("az vm list --resource-group rg-b")),
            Some("rg-b")
        );
        assert_eq!(
            command_resource_group(&argv("az vm list --resource-group=rg-c")),
            Some("rg-c")
        );
    }

    #[test]
    fn a_command_with_no_group_names_none() {
        assert_eq!(command_resource_group(&argv("az account show")), None);
        // A dangling flag names nothing rather than picking up the next
        // unrelated token.
        assert_eq!(command_resource_group(&argv("az vm list -g")), None);
    }

    /// The flag existed to scope the run and was discarded, so the model was
    /// never told which group to use. Telling it is half the fix; refusing a
    /// command that ignored the instruction is the other half.
    #[test]
    fn a_command_targeting_another_group_is_reported() {
        let commands = vec![
            argv("az vm list -g rg-mine"),
            argv("az vm delete -g rg-someone-else --name prod-db"),
            argv("az account show"),
        ];
        let conflicts = conflicting_resource_groups(&commands, "rg-mine");
        assert_eq!(conflicts, vec![(1, "rg-someone-else")]);
    }

    /// A command with no group of its own inherits `az`'s default, which the
    /// instruction in the request is there to prevent. It is not a conflict:
    /// refusing it would reject `az account show` and friends.
    #[test]
    fn a_command_with_no_group_is_not_a_conflict() {
        let commands = vec![argv("az account show"), argv("az group list")];
        assert!(conflicting_resource_groups(&commands, "rg-mine").is_empty());
    }

    /// Azure resource group names are case-insensitive, so a case difference
    /// is not a different group and must not block the run.
    #[test]
    fn case_does_not_make_a_different_group() {
        let commands = vec![argv("az vm list -g RG-Mine")];
        assert!(conflicting_resource_groups(&commands, "rg-mine").is_empty());
    }

    /// The conflict check is blind to commands with no group of their own, so
    /// they are counted for the plan the user approves. `az account show` is
    /// legitimately group-less; the point is that the count is visible, not
    /// that it is zero.
    #[test]
    fn group_less_commands_are_countable_for_the_plan() {
        let commands = vec![
            argv("az account show"),
            argv("az vm list -g rg-mine"),
            argv("az group list"),
        ];
        let ungrouped = commands
            .iter()
            .filter(|a| command_resource_group(a).is_none())
            .count();
        assert_eq!(ungrouped, 2);
    }

    #[test]
    fn the_request_keeps_the_users_words_first() {
        let scoped = scope_request_to_resource_group("delete the test VMs", "rg-mine");
        assert!(scoped.starts_with("delete the test VMs"), "{scoped}");
        assert!(scoped.contains("rg-mine"), "{scoped}");
        assert!(scoped.contains("--resource-group"), "{scoped}");
    }
}
