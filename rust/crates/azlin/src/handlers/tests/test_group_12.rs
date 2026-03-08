// ── Tests for batch_helpers pure functions ────────────────────────
//
// These cover logic extracted from cmd_batch.rs: confirmation prompts,
// filter display, workflow step extraction, and message formatting.

// ── resolve_filter_display ────────────────────────────────────────

#[test]
fn test_resolve_filter_display_none_returns_all() {
    assert_eq!(crate::batch_helpers::resolve_filter_display(None), "all");
}

#[test]
fn test_resolve_filter_display_some_returns_tag() {
    assert_eq!(
        crate::batch_helpers::resolve_filter_display(Some("env=prod")),
        "env=prod"
    );
}

#[test]
fn test_resolve_filter_display_empty_string() {
    assert_eq!(crate::batch_helpers::resolve_filter_display(Some("")), "");
}

// ── build_confirmation_prompt ─────────────────────────────────────

#[test]
fn test_build_confirmation_prompt_stop() {
    let prompt = crate::batch_helpers::build_confirmation_prompt("Stop", "all", "my-rg");
    assert_eq!(prompt, "Stop VMs matching 'all' in my-rg?");
}

#[test]
fn test_build_confirmation_prompt_start_with_tag() {
    let prompt = crate::batch_helpers::build_confirmation_prompt("Start", "env=dev", "prod-rg");
    assert_eq!(prompt, "Start VMs matching 'env=dev' in prod-rg?");
}

#[test]
fn test_build_confirmation_prompt_contains_action() {
    let prompt = crate::batch_helpers::build_confirmation_prompt("Delete", "all", "rg");
    assert!(prompt.starts_with("Delete"));
}

// ── extract_workflow_step ─────────────────────────────────────────

#[test]
fn test_extract_workflow_step_with_name_and_command() {
    let yaml: serde_yaml::Value =
        serde_yaml::from_str("name: install-deps\ncommand: apt-get update").unwrap();
    let step = crate::batch_helpers::extract_workflow_step(&yaml, 0);
    assert_eq!(step.name, "install-deps");
    assert_eq!(step.command.as_deref(), Some("apt-get update"));
}

#[test]
fn test_extract_workflow_step_with_run_instead_of_command() {
    let yaml: serde_yaml::Value = serde_yaml::from_str("name: deploy\nrun: ./deploy.sh").unwrap();
    let step = crate::batch_helpers::extract_workflow_step(&yaml, 0);
    assert_eq!(step.name, "deploy");
    assert_eq!(step.command.as_deref(), Some("./deploy.sh"));
}

#[test]
fn test_extract_workflow_step_command_preferred_over_run() {
    let yaml: serde_yaml::Value =
        serde_yaml::from_str("name: test\ncommand: make test\nrun: make run").unwrap();
    let step = crate::batch_helpers::extract_workflow_step(&yaml, 0);
    // `command` takes priority over `run`
    assert_eq!(step.command.as_deref(), Some("make test"));
}

#[test]
fn test_extract_workflow_step_no_name_uses_default() {
    let yaml: serde_yaml::Value = serde_yaml::from_str("command: echo hello").unwrap();
    let step = crate::batch_helpers::extract_workflow_step(&yaml, 2);
    assert_eq!(step.name, "step-3");
    assert_eq!(step.command.as_deref(), Some("echo hello"));
}

#[test]
fn test_extract_workflow_step_no_command() {
    let yaml: serde_yaml::Value = serde_yaml::from_str("name: wait-step").unwrap();
    let step = crate::batch_helpers::extract_workflow_step(&yaml, 0);
    assert_eq!(step.name, "wait-step");
    assert!(step.command.is_none());
}

#[test]
fn test_extract_workflow_step_empty_mapping() {
    let yaml: serde_yaml::Value = serde_yaml::from_str("{}").unwrap();
    let step = crate::batch_helpers::extract_workflow_step(&yaml, 5);
    assert_eq!(step.name, "step-6");
    assert!(step.command.is_none());
}

// ── format_step_header ────────────────────────────────────────────

#[test]
fn test_format_step_header() {
    let header = crate::batch_helpers::format_step_header(1, "install-deps");
    assert_eq!(header, "\n── Step 1: install-deps ──");
}

#[test]
fn test_format_step_header_large_number() {
    let header = crate::batch_helpers::format_step_header(42, "cleanup");
    assert!(header.contains("Step 42"));
    assert!(header.contains("cleanup"));
}

// ── format_no_vms_message / format_no_running_vms_message ─────────

#[test]
fn test_format_no_vms_message() {
    let msg = crate::batch_helpers::format_no_vms_message("dev-rg");
    assert_eq!(msg, "No VMs found in resource group 'dev-rg'");
}

#[test]
fn test_format_no_running_vms_message() {
    let msg = crate::batch_helpers::format_no_running_vms_message("staging-rg");
    assert_eq!(msg, "No running VMs found in resource group 'staging-rg'");
}

// ── format_fleet_run_message / format_fleet_across_message ────────

#[test]
fn test_format_fleet_run_message() {
    let msg = crate::batch_helpers::format_fleet_run_message("uptime", 5);
    assert_eq!(msg, "Running 'uptime' on 5 VM(s)...");
}

#[test]
fn test_format_fleet_run_message_single_vm() {
    let msg = crate::batch_helpers::format_fleet_run_message("hostname", 1);
    assert_eq!(msg, "Running 'hostname' on 1 VM(s)...");
}

#[test]
fn test_format_fleet_across_message() {
    let msg = crate::batch_helpers::format_fleet_across_message("apt update", 3);
    assert_eq!(msg, "Running 'apt update' across 3 VM(s)...");
}

// ── WorkflowStep equality ─────────────────────────────────────────

#[test]
fn test_workflow_step_equality() {
    let a = crate::batch_helpers::WorkflowStep {
        name: "test".to_string(),
        command: Some("echo 1".to_string()),
    };
    let b = crate::batch_helpers::WorkflowStep {
        name: "test".to_string(),
        command: Some("echo 1".to_string()),
    };
    assert_eq!(a, b);
}

#[test]
fn test_workflow_step_inequality() {
    let a = crate::batch_helpers::WorkflowStep {
        name: "a".to_string(),
        command: None,
    };
    let b = crate::batch_helpers::WorkflowStep {
        name: "b".to_string(),
        command: None,
    };
    assert_ne!(a, b);
}
