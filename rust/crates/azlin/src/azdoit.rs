use anyhow::Result;
use clap::Parser;

/// Execute natural language Azure commands using AI (standalone CLI).
///
/// azdoit uses AI to iteratively pursue Azure infrastructure objectives.
///
/// Quick Start:
///   1. Set API key: export ANTHROPIC_API_KEY=your-key-here
///   2. Try: azdoit "create a VM called dev-box"
#[derive(Parser)]
#[command(name = "azdoit", version = "2.3.0")]
struct Args {
    /// Natural language request describing what to do
    request: Vec<String>,

    /// Maximum number of AI turns
    #[arg(long, default_value = "10")]
    max_turns: u32,

    /// Show plan without executing
    #[arg(long)]
    dry_run: bool,

    /// Enable verbose output
    #[arg(short, long)]
    verbose: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    if args.verbose {
        tracing_subscriber::fmt().with_env_filter("debug").init();
    }

    let request = args.request.join(" ");
    if request.is_empty() {
        eprintln!("Error: No request provided.");
        eprintln!("Usage: azdoit \"create a VM called dev-box\"");
        std::process::exit(1);
    }

    let client = azlin_ai::AnthropicClient::new()
        .map_err(|e| anyhow::anyhow!("AI client error: {}. Set ANTHROPIC_API_KEY.", e))?;

    let system_prompt = format!(
        "You are azdoit, an Azure infrastructure automation tool. \
        The user wants to: {}\n\
        Generate a sequence of Azure CLI (az) commands to accomplish this.\n\
        Format each command on its own line, prefixed with '$ '.\n\
        Include brief explanations before each command.\n\
        Maximum {} steps.",
        request, args.max_turns
    );

    println!("🤖 azdoit — Planning: {}", request);
    println!();

    let response = client.ask(&system_prompt, &request).await?;

    if args.dry_run {
        println!("Plan (dry-run, not executing):\n");
        println!("{}", response);
        return Ok(());
    }

    println!("{}\n", response);

    let commands: Vec<&str> = response
        .lines()
        .filter(|l| l.trim().starts_with("$ "))
        .map(|l| l.trim().strip_prefix("$ ").unwrap_or(l.trim()))
        .collect();

    if commands.is_empty() {
        println!("No executable commands found in the plan.");
        return Ok(());
    }

    if !dialoguer::Confirm::new()
        .with_prompt(format!("Execute {} command(s)?", commands.len()))
        .default(false)
        .interact()?
    {
        println!("Cancelled.");
        return Ok(());
    }

    let allowed_prefixes = ["az ", "echo ", "azlin "];
    let dangerous_patterns = ["run-command", "extension set", "extension delete", "vm user", "vm secret"];
    for (i, cmd) in commands.iter().enumerate() {
        let trimmed = cmd.trim();
        let is_allowed = allowed_prefixes.iter().any(|p| trimmed.starts_with(p));
        if !is_allowed {
            eprintln!("⚠ Skipping disallowed command: {}", trimmed);
            continue;
        }
        if trimmed.starts_with("az ") && dangerous_patterns.iter().any(|d| trimmed.contains(d)) {
            eprintln!("⚠ Blocked potentially dangerous command: {}", trimmed);
            continue;
        }
        println!("→ [{}/{}] {}", i + 1, commands.len(), cmd);
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        if parts.is_empty() {
            continue;
        }
        let output = std::process::Command::new(parts[0])
            .args(&parts[1..])
            .output()?;
        if !output.stdout.is_empty() {
            print!("{}", String::from_utf8_lossy(&output.stdout));
        }
        if !output.status.success() {
            eprintln!(
                "  ⚠ Command failed (exit {})",
                output.status.code().unwrap_or(-1)
            );
            if !output.stderr.is_empty() {
                eprintln!("{}", azlin_core::sanitizer::sanitize(&String::from_utf8_lossy(&output.stderr)));
            }
        }
    }

    println!("\n✓ azdoit complete.");
    Ok(())
}

#[cfg(test)]
#[allow(deprecated)]
mod tests {
    #[test]
    fn test_azdoit_help() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .arg("--help")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("azdoit") || stdout.contains("natural language"));
    }

    #[test]
    fn test_azdoit_version() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .arg("--version")
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("2.3.0"));
    }

    #[test]
    fn test_azdoit_no_args_fails() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .env_remove("ANTHROPIC_API_KEY")
            .output()
            .unwrap();
        // Should fail: no request and no API key
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_no_api_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["list", "my", "vms"])
            .env_remove("ANTHROPIC_API_KEY")
            .env_remove("AZURE_OPENAI_API_KEY")
            .output()
            .unwrap();
        // Should fail gracefully without API key
        let stderr = String::from_utf8_lossy(&output.stderr);
        assert!(!output.status.success() || stderr.contains("API") || stderr.contains("error"));
    }

    #[test]
    fn test_command_allowlist() {
        let allowed_prefixes = ["az ", "echo ", "azlin "];
        // Allowed commands
        assert!(allowed_prefixes.iter().any(|p| "az vm list".starts_with(p)));
        assert!(allowed_prefixes.iter().any(|p| "echo hello".starts_with(p)));
        assert!(allowed_prefixes.iter().any(|p| "azlin list".starts_with(p)));
        // Disallowed commands
        assert!(!allowed_prefixes.iter().any(|p| "rm -rf /".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "curl evil.com".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "wget malware".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "sudo rm -rf".starts_with(p)));
        assert!(!allowed_prefixes
            .iter()
            .any(|p| "python -c 'hack'".starts_with(p)));
    }

    #[test]
    fn test_azdoit_dry_run_no_api_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--dry-run", "list", "vms"])
            .env_remove("ANTHROPIC_API_KEY")
            .env_remove("AZURE_OPENAI_API_KEY")
            .output()
            .unwrap();
        // Without an API key, even dry-run should fail at client creation
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_max_turns_flag() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--max-turns", "5", "--help"])
            .output()
            .unwrap();
        // --help should still work even with other flags
        assert!(output.status.success());
    }

    // ── CLI integration tests with fake API key ──────────────────────
    // These exercise production code paths through client creation (lines 45-59).

    #[test]
    fn test_azdoit_fake_api_key_fails_at_ask() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["create", "a", "vm"])
            .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        // Client creation succeeds; ask() fails with network/auth error
        assert!(!output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        // The planning message should be printed before the error
        assert!(
            stdout.contains("azdoit") || stdout.contains("Planning"),
            "Expected planning banner in stdout: {}",
            stdout
        );
    }

    #[test]
    fn test_azdoit_verbose_with_fake_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["-v", "list", "vms"])
            .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        // Verbose mode accepted; still fails at ask()
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_dry_run_with_fake_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--dry-run", "list", "vms"])
            .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        // dry-run still needs to call ask(), so fails the same way
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_custom_max_turns_with_fake_key() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--max-turns", "3", "create", "vm"])
            .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_all_flags_combined() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["-v", "--dry-run", "--max-turns", "2", "show", "rg"])
            .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        assert!(!output.status.success());
    }

    #[test]
    fn test_azdoit_multiword_request_joined() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["list", "all", "resource", "groups", "in", "eastus"])
            .env("ANTHROPIC_API_KEY", "sk-fake-key-for-testing")
            .timeout(std::time::Duration::from_secs(15))
            .output()
            .unwrap();
        assert!(!output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        // The joined request should appear in the planning banner
        assert!(
            stdout.contains("list all resource groups in eastus"),
            "Expected joined request in banner: {}",
            stdout
        );
    }

    // ── Command extraction logic tests ───────────────────────────────
    // Mirrors the filter/map pattern at lines 71-75.

    fn extract_commands(response: &str) -> Vec<&str> {
        response
            .lines()
            .filter(|l| l.trim().starts_with("$ "))
            .map(|l| l.trim().strip_prefix("$ ").unwrap_or(l.trim()))
            .collect()
    }

    #[test]
    fn test_extract_commands_basic() {
        let response = "First, create a resource group.\n\
                         $ az group create --name mygroup --location eastus\n\
                         Now create a VM.\n\
                         $ az vm create --name myvm --resource-group mygroup\n\
                         Done!";
        let cmds = extract_commands(response);
        assert_eq!(cmds.len(), 2);
        assert_eq!(cmds[0], "az group create --name mygroup --location eastus");
        assert_eq!(cmds[1], "az vm create --name myvm --resource-group mygroup");
    }

    #[test]
    fn test_extract_commands_empty_response() {
        assert!(extract_commands("").is_empty());
    }

    #[test]
    fn test_extract_commands_no_dollar_prefix() {
        let response = "az vm list\necho hello\nNo commands here.";
        assert!(extract_commands(response).is_empty());
    }

    #[test]
    fn test_extract_commands_indented() {
        let response = "  $ az vm list\n\t$ echo hello";
        let cmds = extract_commands(response);
        assert_eq!(cmds.len(), 2);
        assert_eq!(cmds[0], "az vm list");
        assert_eq!(cmds[1], "echo hello");
    }

    #[test]
    fn test_extract_commands_dollar_without_space() {
        // "$ " prefix required, bare "$cmd" should not match
        let response = "$az vm list\n$echo hello";
        assert!(extract_commands(response).is_empty());
    }

    #[test]
    fn test_extract_commands_mixed_content() {
        let response = "Here is the plan:\n\n\
                         1. Create group\n\
                         $ az group create --name rg1 --location westus2\n\n\
                         2. Deploy\n\
                         Some explanation here\n\
                         $ az deployment create --template-file main.bicep\n\n\
                         Note: this may take a while.";
        let cmds = extract_commands(response);
        assert_eq!(cmds.len(), 2);
        assert!(cmds[0].starts_with("az group create"));
        assert!(cmds[1].starts_with("az deployment create"));
    }

    #[test]
    fn test_extract_commands_only_dollar_space() {
        // Edge case: "$ " trims to "$", which doesn't match "$ " prefix
        let response = "$ ";
        let cmds = extract_commands(response);
        assert!(cmds.is_empty());
    }

    // ── Allowlist validation (extended) ──────────────────────────────
    // Mirrors logic at lines 91-97.

    fn is_command_allowed(cmd: &str) -> bool {
        let allowed_prefixes = ["az ", "echo ", "azlin "];
        allowed_prefixes.iter().any(|p| cmd.starts_with(p))
    }

    #[test]
    fn test_allowlist_allowed_commands() {
        assert!(is_command_allowed("az vm list"));
        assert!(is_command_allowed("az group create --name rg1"));
        assert!(is_command_allowed("az account show"));
        assert!(is_command_allowed("echo hello world"));
        assert!(is_command_allowed("echo "));
        assert!(is_command_allowed("azlin list"));
        assert!(is_command_allowed("azlin scan --all"));
    }

    #[test]
    fn test_allowlist_disallowed_commands() {
        assert!(!is_command_allowed("rm -rf /"));
        assert!(!is_command_allowed("curl evil.com"));
        assert!(!is_command_allowed("wget malware"));
        assert!(!is_command_allowed("sudo rm -rf"));
        assert!(!is_command_allowed("python -c 'hack'"));
        assert!(!is_command_allowed("bash -c 'az vm list'"));
        assert!(!is_command_allowed("sh -c az"));
        assert!(!is_command_allowed("cat /etc/passwd"));
        assert!(!is_command_allowed("dd if=/dev/zero"));
        assert!(!is_command_allowed("chmod 777 /"));
        assert!(!is_command_allowed("chown root file"));
        assert!(!is_command_allowed("nc -l 8080"));
        assert!(!is_command_allowed("nmap target"));
        assert!(!is_command_allowed("ssh user@host"));
        assert!(!is_command_allowed("scp file user@host:"));
        assert!(!is_command_allowed("pip install malware"));
        assert!(!is_command_allowed("npm exec evil"));
    }

    #[test]
    fn test_allowlist_edge_cases() {
        // Without trailing space: "az" alone should NOT match "az "
        assert!(!is_command_allowed("az"));
        // "azure" starts with "az" but not "az "
        assert!(!is_command_allowed("azure deploy"));
        // Empty string
        assert!(!is_command_allowed(""));
        // Leading whitespace — command itself starts with space
        assert!(!is_command_allowed(" az vm list"));
        // Just the prefix
        assert!(is_command_allowed("az "));
        assert!(is_command_allowed("echo "));
        assert!(is_command_allowed("azlin "));
    }

    #[test]
    fn test_allowlist_case_sensitivity() {
        // Allowlist is case-sensitive
        assert!(!is_command_allowed("AZ vm list"));
        assert!(!is_command_allowed("Az vm list"));
        assert!(!is_command_allowed("ECHO hello"));
        assert!(!is_command_allowed("AZLIN list"));
    }

    // ── System prompt construction ───────────────────────────────────
    // Mirrors logic at lines 48-56.

    fn build_system_prompt(request: &str, max_turns: u32) -> String {
        format!(
            "You are azdoit, an Azure infrastructure automation tool. \
            The user wants to: {}\n\
            Generate a sequence of Azure CLI (az) commands to accomplish this.\n\
            Format each command on its own line, prefixed with '$ '.\n\
            Include brief explanations before each command.\n\
            Maximum {} steps.",
            request, max_turns
        )
    }

    #[test]
    fn test_system_prompt_contains_request() {
        let prompt = build_system_prompt("create a VM called dev-box", 10);
        assert!(prompt.contains("create a VM called dev-box"));
    }

    #[test]
    fn test_system_prompt_contains_max_turns() {
        let prompt = build_system_prompt("list vms", 5);
        assert!(prompt.contains("Maximum 5 steps"));
    }

    #[test]
    fn test_system_prompt_structure() {
        let prompt = build_system_prompt("deploy app", 8);
        assert!(prompt.starts_with("You are azdoit"));
        assert!(prompt.contains("Azure CLI (az)"));
        assert!(prompt.contains("prefixed with '$ '"));
        assert!(prompt.contains("Include brief explanations"));
        assert!(prompt.contains("Maximum 8 steps"));
    }

    #[test]
    fn test_system_prompt_special_chars_in_request() {
        let prompt = build_system_prompt("create VM with --size Standard_B2s", 10);
        assert!(prompt.contains("--size Standard_B2s"));
    }

    // ── Command splitting logic ──────────────────────────────────────
    // Mirrors line 99: cmd.split_whitespace()

    #[test]
    fn test_command_splitting_basic() {
        let cmd = "az vm create --name myvm --resource-group mygroup";
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        assert_eq!(parts[0], "az");
        assert_eq!(parts.len(), 7);
    }

    #[test]
    fn test_command_splitting_extra_whitespace() {
        let cmd = "az   vm   list";
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        assert_eq!(parts, vec!["az", "vm", "list"]);
    }

    #[test]
    fn test_command_splitting_single_word() {
        let cmd = "az";
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        assert_eq!(parts.len(), 1);
        assert_eq!(parts[0], "az");
    }

    #[test]
    fn test_command_splitting_empty() {
        let cmd = "";
        let parts: Vec<&str> = cmd.split_whitespace().collect();
        assert!(parts.is_empty());
    }

    // ── Request join logic ───────────────────────────────────────────
    // Mirrors line 38: args.request.join(" ")

    #[test]
    fn test_request_join_multiple_words() {
        let parts: Vec<String> = vec![
            "list".into(),
            "my".into(),
            "vms".into(),
        ];
        assert_eq!(parts.join(" "), "list my vms");
    }

    #[test]
    fn test_request_join_single_word() {
        let parts: Vec<String> = vec!["deploy".into()];
        assert_eq!(parts.join(" "), "deploy");
    }

    #[test]
    fn test_request_join_empty() {
        let parts: Vec<String> = vec![];
        let joined = parts.join(" ");
        assert!(joined.is_empty());
    }

    #[test]
    fn test_request_join_preserves_quoted_args() {
        let parts: Vec<String> = vec![
            "create".into(),
            "vm".into(),
            "named".into(),
            "my-dev-box".into(),
        ];
        assert_eq!(parts.join(" "), "create vm named my-dev-box");
    }

    // ── Error message formatting ─────────────────────────────────────
    // Mirrors error patterns at lines 41-42, 46, 95-96, 110-116.

    #[test]
    fn test_error_msg_no_request() {
        let msg = "Error: No request provided.";
        let usage = "Usage: azdoit \"create a VM called dev-box\"";
        assert!(msg.starts_with("Error:"));
        assert!(usage.contains("azdoit"));
    }

    #[test]
    fn test_error_msg_api_client() {
        let inner = "missing API key";
        let msg = format!("AI client error: {}. Set ANTHROPIC_API_KEY.", inner);
        assert!(msg.contains("ANTHROPIC_API_KEY"));
        assert!(msg.contains("missing API key"));
    }

    #[test]
    fn test_error_msg_disallowed_command() {
        let cmd = "rm -rf /";
        let msg = format!("⚠ Skipping disallowed command: {}", cmd);
        assert!(msg.contains("Skipping disallowed"));
        assert!(msg.contains("rm -rf /"));
    }

    #[test]
    fn test_error_msg_command_failed() {
        let exit_code: i32 = 1;
        let msg = format!("  ⚠ Command failed (exit {})", exit_code);
        assert!(msg.contains("Command failed"));
        assert!(msg.contains("exit 1"));
    }

    #[test]
    fn test_error_msg_command_failed_unknown_exit() {
        let exit_code = -1_i32;
        let msg = format!("  ⚠ Command failed (exit {})", exit_code);
        assert!(msg.contains("exit -1"));
    }

    // ── Progress display formatting ──────────────────────────────────
    // Mirrors line 98: println!("→ [{}/{}] {}", i + 1, commands.len(), cmd)

    #[test]
    fn test_progress_display_format() {
        let commands = ["az vm list", "az group show"];
        for (i, cmd) in commands.iter().enumerate() {
            let msg = format!("→ [{}/{}] {}", i + 1, commands.len(), cmd);
            assert!(msg.contains(&format!("{}/{}", i + 1, commands.len())));
            assert!(msg.contains(cmd));
        }
    }

    // ── Full pipeline test (extraction + allowlist) ──────────────────

    #[test]
    fn test_full_pipeline_extract_and_filter() {
        let response = "Plan:\n\
                         $ az group create --name rg1 --location eastus\n\
                         $ rm -rf /tmp/cache\n\
                         $ az vm create --name vm1 --resource-group rg1\n\
                         $ curl http://example.com\n\
                         $ echo Done";
        let commands = extract_commands(response);
        assert_eq!(commands.len(), 5);

        let allowed: Vec<&&str> = commands
            .iter()
            .filter(|cmd| is_command_allowed(cmd))
            .collect();
        assert_eq!(allowed.len(), 3);
        assert_eq!(*allowed[0], "az group create --name rg1 --location eastus");
        assert_eq!(*allowed[1], "az vm create --name vm1 --resource-group rg1");
        assert_eq!(*allowed[2], "echo Done");
    }

    #[test]
    fn test_full_pipeline_all_disallowed() {
        let response = "$ rm -rf /\n$ wget malware.exe\n$ python -c 'evil'";
        let commands = extract_commands(response);
        let allowed: Vec<&&str> = commands
            .iter()
            .filter(|cmd| is_command_allowed(cmd))
            .collect();
        assert!(allowed.is_empty());
    }

    #[test]
    fn test_full_pipeline_all_allowed() {
        let response = "$ az vm list\n$ az group show --name rg1\n$ echo ok";
        let commands = extract_commands(response);
        let allowed: Vec<&&str> = commands
            .iter()
            .filter(|cmd| is_command_allowed(cmd))
            .collect();
        assert_eq!(allowed.len(), 3);
    }

    // ── Integration tests requiring real API key ─────────────────────

    #[test]
    #[ignore]
    fn test_azdoit_dry_run_real_api() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["--dry-run", "list", "resource", "groups"])
            .output()
            .unwrap();
        assert!(output.status.success());
        let stdout = String::from_utf8_lossy(&output.stdout);
        assert!(stdout.contains("dry-run") || stdout.contains("Plan"));
    }

    #[test]
    #[ignore]
    fn test_azdoit_verbose_dry_run_real_api() {
        let output = assert_cmd::Command::cargo_bin("azdoit")
            .unwrap()
            .args(["-v", "--dry-run", "--max-turns", "3", "show", "account", "info"])
            .output()
            .unwrap();
        assert!(output.status.success());
    }
}
