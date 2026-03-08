// Command extraction, allowlist, system prompt, and safety tests for azdoit.

fn extract_commands(response: &str) -> Vec<&str> {
    response
        .lines()
        .filter(|l| l.trim().starts_with("$ "))
        .map(|l| l.trim().strip_prefix("$ ").unwrap_or(l.trim()))
        .collect()
}

fn is_command_allowed(cmd: &str) -> bool {
    let allowed_prefixes = ["az ", "echo ", "azlin "];
    allowed_prefixes.iter().any(|p| cmd.starts_with(p))
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
}

#[test]
fn test_extract_commands_dollar_without_space() {
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
}

#[test]
fn test_extract_commands_only_dollar_space() {
    let response = "$ ";
    let cmds = extract_commands(response);
    assert!(cmds.is_empty());
}

#[test]
fn test_allowlist_allowed_commands() {
    assert!(is_command_allowed("az vm list"));
    assert!(is_command_allowed("az group create --name rg1"));
    assert!(is_command_allowed("echo hello world"));
    assert!(is_command_allowed("azlin list"));
}

#[test]
fn test_allowlist_disallowed_commands() {
    assert!(!is_command_allowed("rm -rf /"));
    assert!(!is_command_allowed("curl evil.com"));
    assert!(!is_command_allowed("wget malware"));
    assert!(!is_command_allowed("sudo rm -rf"));
    assert!(!is_command_allowed("python -c 'hack'"));
    assert!(!is_command_allowed("bash -c 'az vm list'"));
    assert!(!is_command_allowed("cat /etc/passwd"));
    assert!(!is_command_allowed("ssh user@host"));
    assert!(!is_command_allowed("pip install malware"));
}

#[test]
fn test_allowlist_edge_cases() {
    assert!(!is_command_allowed("az"));
    assert!(!is_command_allowed("azure deploy"));
    assert!(!is_command_allowed(""));
    assert!(!is_command_allowed(" az vm list"));
    assert!(is_command_allowed("az "));
    assert!(is_command_allowed("echo "));
}

#[test]
fn test_allowlist_case_sensitivity() {
    assert!(!is_command_allowed("AZ vm list"));
    assert!(!is_command_allowed("ECHO hello"));
}

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
}

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
fn test_request_join_multiple_words() {
    let parts: Vec<String> = vec!["list".into(), "my".into(), "vms".into()];
    assert_eq!(parts.join(" "), "list my vms");
}

#[test]
fn test_request_join_empty() {
    let parts: Vec<String> = vec![];
    assert!(parts.join(" ").is_empty());
}

#[test]
fn test_full_pipeline_extract_and_filter() {
    let response = "Plan:\n\
                     $ az group create --name rg1 --location eastus\n\
                     $ rm -rf /tmp/cache\n\
                     $ az vm create --name vm1 --resource-group rg1\n\
                     $ curl http://example.com\n\
                     $ echo Done";
    let commands = extract_commands(response);
    let allowed: Vec<&&str> = commands
        .iter()
        .filter(|cmd| is_command_allowed(cmd))
        .collect();
    assert_eq!(allowed.len(), 3);
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

// classify_command safety tests

#[test]
fn test_classify_allowed_az_command() {
    assert_eq!(
        super::classify_command("az vm list --output table"),
        super::CommandSafety::Allowed
    );
}

#[test]
fn test_classify_allowed_echo() {
    assert_eq!(
        super::classify_command("echo hello world"),
        super::CommandSafety::Allowed
    );
}

#[test]
fn test_classify_disallowed_arbitrary_command() {
    assert_eq!(
        super::classify_command("rm -rf /"),
        super::CommandSafety::Disallowed
    );
}

#[test]
fn test_classify_dangerous_run_command() {
    assert_eq!(
        super::classify_command("az vm run-command invoke --command-id RunShellScript"),
        super::CommandSafety::Dangerous
    );
}

#[test]
fn test_classify_dangerous_az_rest() {
    assert_eq!(
        super::classify_command("az rest --method PUT --uri /subscriptions/..."),
        super::CommandSafety::Dangerous
    );
}

#[test]
fn test_classify_dangerous_role_assignment() {
    assert_eq!(
        super::classify_command("az role assignment create --assignee attacker"),
        super::CommandSafety::Dangerous
    );
}

#[test]
fn test_classify_dangerous_keyvault_secret() {
    assert_eq!(
        super::classify_command("az keyvault secret set --name mykey --value stolen"),
        super::CommandSafety::Dangerous
    );
}

#[test]
fn test_classify_whitespace_trimmed() {
    assert_eq!(
        super::classify_command("  az vm list  "),
        super::CommandSafety::Allowed
    );
}

#[test]
fn test_classify_empty_string() {
    assert_eq!(
        super::classify_command(""),
        super::CommandSafety::Disallowed
    );
}

// Integration tests requiring real API key
#[test]
#[ignore]
fn test_azdoit_dry_run_real_api() {
    let output = assert_cmd::Command::cargo_bin("azdoit")
        .unwrap()
        .args(["--dry-run", "list", "resource", "groups"])
        .output()
        .unwrap();
    assert!(output.status.success());
}
