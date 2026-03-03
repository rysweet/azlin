//! Template system integration tests.
//!
//! Ported from Python E2E: test_template_system_e2e.py,
//! Python unit tests: test_template_manager.py, templates/test_validation.py.

mod integration;

use integration::{run_azlin, run_azlin_with_env};

// ---------------------------------------------------------------------------
// Template subcommand help
// ---------------------------------------------------------------------------

#[test]
fn test_template_help() {
    let (stdout, _, code) = run_azlin(&["template", "--help"]);
    assert_eq!(code, 0);
    assert!(stdout.contains("create") || stdout.contains("Create"));
    assert!(stdout.contains("save") || stdout.contains("Save"));
    assert!(stdout.contains("show") || stdout.contains("Show"));
    assert!(stdout.contains("apply") || stdout.contains("Apply"));
}

#[test]
fn test_template_create_help() {
    let (_, _, code) = run_azlin(&["template", "create", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_list_help() {
    let (_, _, code) = run_azlin(&["template", "list", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Template without auth — graceful error
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_without_auth_no_panic() {
    let (stdout, stderr, _) = run_azlin(&["template", "list"]);
    let combined = format!("{}{}", stdout, stderr);
    assert!(
        !combined.contains("panicked"),
        "template list should not panic without auth"
    );
}

// ---------------------------------------------------------------------------
// Template list empty & show nonexistent
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_empty() {
    let (stdout, _, code) = run_azlin(&["template", "list"]);
    assert!(stdout.contains("No templates") || code == 0);
}

#[test]
fn test_template_show_nonexistent() {
    let (_, stderr, code) = run_azlin(&["template", "show", "nonexistent-template-xyz"]);
    // Should fail gracefully (non-zero exit or error message)
    assert!(code != 0 || stderr.contains("not found"));
}

// ---------------------------------------------------------------------------
// Template save / show / apply help
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_help() {
    let (_, _, code) = run_azlin(&["template", "save", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_show_help() {
    let (_, _, code) = run_azlin(&["template", "show", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_apply_help() {
    let (_, _, code) = run_azlin(&["template", "apply", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_delete_help() {
    let (_, _, code) = run_azlin(&["template", "delete", "--help"]);
    assert_eq!(code, 0);
}

// ---------------------------------------------------------------------------
// Template save + list roundtrip (isolated via HOME)
// Ported from Python: TestTemplateCreation + TestTemplateListing
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_and_list_roundtrip() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    // Save a template
    let (stdout, stderr, code) = run_azlin_with_env(
        &[
            "template",
            "save",
            "my-dev-vm",
            "--description",
            "Dev VM template",
            "--vm-size",
            "Standard_D2s_v3",
            "--region",
            "eastus",
        ],
        &env,
    );
    let combined = format!("{}{}", stdout, stderr);
    assert_eq!(code, 0, "template save should succeed, got: {}", combined);
    assert!(
        stdout.contains("Saved") || stdout.contains("my-dev-vm"),
        "should confirm save, got: {}",
        stdout,
    );

    // List templates — should include the saved one
    let (stdout, _, code) = run_azlin_with_env(&["template", "list"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("my-dev-vm"),
        "template list should include saved template, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Template save + show roundtrip
// Ported from Python: TestTemplateRetrieval.test_get_existing_template
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_and_show_roundtrip() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (_, _, code) = run_azlin_with_env(
        &[
            "template",
            "save",
            "show-test",
            "--vm-size",
            "Standard_B2s",
            "--region",
            "westus2",
        ],
        &env,
    );
    assert_eq!(code, 0);

    let (stdout, _, code) = run_azlin_with_env(&["template", "show", "show-test"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("Standard_B2s") || stdout.contains("westus2"),
        "template show should display saved values, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Template save + delete + list confirms removal
// Ported from Python: TestTemplateDeletion.test_delete_existing_template
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_delete_list() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    // Save
    let (_, _, code) = run_azlin_with_env(
        &["template", "save", "to-delete", "--region", "eastus"],
        &env,
    );
    assert_eq!(code, 0);

    // Delete with --force to skip prompt
    let (stdout, _, code) = run_azlin_with_env(
        &["template", "delete", "to-delete", "--force"],
        &env,
    );
    assert_eq!(code, 0, "delete should succeed");
    assert!(
        stdout.contains("Deleted") || stdout.contains("to-delete"),
        "should confirm deletion, got: {}",
        stdout,
    );

    // List should be empty now
    let (stdout, _, _) = run_azlin_with_env(&["template", "list"], &env);
    assert!(
        !stdout.contains("to-delete"),
        "deleted template should not appear in list, got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Template delete nonexistent — should fail gracefully
// Ported from Python: TestTemplateDeletion.test_delete_nonexistent_template_fails
// ---------------------------------------------------------------------------

#[test]
fn test_template_delete_nonexistent() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) = run_azlin_with_env(
        &["template", "delete", "no-such-template", "--force"],
        &env,
    );
    let combined = format!("{}{}", stdout, stderr);
    assert_ne!(code, 0, "deleting nonexistent template should fail");
    assert!(
        combined.contains("not found") || combined.contains("No"),
        "should indicate not found, got: {}",
        combined,
    );
}

// ---------------------------------------------------------------------------
// Template show nonexistent with isolated HOME
// Ported from Python: TestTemplateRetrieval.test_get_nonexistent_template_fails
// ---------------------------------------------------------------------------

#[test]
fn test_template_show_nonexistent_isolated() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) =
        run_azlin_with_env(&["template", "show", "ghost-template"], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert_ne!(code, 0, "showing nonexistent template should fail");
    assert!(
        combined.contains("not found"),
        "should say not found, got: {}",
        combined,
    );
}

// ---------------------------------------------------------------------------
// Template apply nonexistent — graceful error
// Ported from Python: TestErrorHandlingE2E.test_missing_dependency_error_handling
// ---------------------------------------------------------------------------

#[test]
fn test_template_apply_nonexistent() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, stderr, code) =
        run_azlin_with_env(&["template", "apply", "missing-tmpl"], &env);
    let combined = format!("{}{}", stdout, stderr);
    assert_ne!(code, 0, "applying nonexistent template should fail");
    assert!(
        combined.contains("not found"),
        "should indicate not found, got: {}",
        combined,
    );
}

// ---------------------------------------------------------------------------
// Template list empty in isolated dir
// Ported from Python: TestTemplateListing.test_list_templates_empty_directory
// ---------------------------------------------------------------------------

#[test]
fn test_template_list_empty_isolated() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    let (stdout, _, code) = run_azlin_with_env(&["template", "list"], &env);
    assert_eq!(code, 0);
    assert!(
        stdout.contains("No templates"),
        "empty dir should show 'No templates', got: {}",
        stdout,
    );
}

// ---------------------------------------------------------------------------
// Template save multiple + list shows all
// Ported from Python: TestTemplateListing.test_list_templates_multiple_templates
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_multiple_list() {
    let tmp = tempfile::TempDir::new().unwrap();
    let env = [("HOME", tmp.path().to_str().unwrap())];

    for name in &["alpha-tmpl", "beta-tmpl", "gamma-tmpl"] {
        let (_, _, code) = run_azlin_with_env(
            &["template", "save", name, "--region", "eastus"],
            &env,
        );
        assert_eq!(code, 0, "save {} should succeed", name);
    }

    let (stdout, _, code) = run_azlin_with_env(&["template", "list"], &env);
    assert_eq!(code, 0);
    for name in &["alpha-tmpl", "beta-tmpl", "gamma-tmpl"] {
        assert!(
            stdout.contains(name),
            "template list should include {}, got: {}",
            name,
            stdout,
        );
    }
}

// ---------------------------------------------------------------------------
// Template save missing name — should fail
// Ported from Python: TestTemplateValidation.test_validate_template_fields
// ---------------------------------------------------------------------------

#[test]
fn test_template_save_missing_name() {
    let (_, _, code) = run_azlin(&["template", "save"]);
    assert_ne!(code, 0, "template save without name should fail");
}

// ---------------------------------------------------------------------------
// Template export + import help
// Ported from Python: TestTemplateExportImport
// ---------------------------------------------------------------------------

#[test]
fn test_template_export_help() {
    let (_, _, code) = run_azlin(&["template", "export", "--help"]);
    assert_eq!(code, 0);
}

#[test]
fn test_template_import_help() {
    let (_, _, code) = run_azlin(&["template", "import", "--help"]);
    assert_eq!(code, 0);
}
