use crate::*;
use std::fs;
use tempfile::TempDir;

// ── validate_repo_url ──────────────────────────────────────────

#[test]
fn test_validate_repo_url_rejects_semicolon() {
    assert!(crate::repo_helpers::validate_repo_url("https://evil.com/repo.git; rm -rf /").is_err());
}

#[test]
fn test_validate_repo_url_rejects_pipe() {
    assert!(
        crate::repo_helpers::validate_repo_url("https://evil.com/repo.git|cat /etc/passwd")
            .is_err()
    );
}

#[test]
fn test_validate_repo_url_rejects_backtick() {
    assert!(crate::repo_helpers::validate_repo_url("https://evil.com/`whoami`.git").is_err());
}

#[test]
fn test_validate_repo_url_rejects_dollar() {
    assert!(crate::repo_helpers::validate_repo_url("https://evil.com/$HOME.git").is_err());
}

#[test]
fn test_validate_repo_url_rejects_ampersand() {
    assert!(
        crate::repo_helpers::validate_repo_url("https://evil.com/repo.git&echo pwned").is_err()
    );
}

#[test]
fn test_validate_repo_url_rejects_newline() {
    assert!(crate::repo_helpers::validate_repo_url("https://evil.com/repo.git\nrm -rf /").is_err());
}

#[test]
fn test_validate_repo_url_rejects_parens() {
    assert!(crate::repo_helpers::validate_repo_url("https://evil.com/$(whoami).git").is_err());
}

#[test]
fn test_validate_repo_url_rejects_empty() {
    assert!(crate::repo_helpers::validate_repo_url("").is_err());
}

#[test]
fn test_validate_repo_url_rejects_bad_scheme() {
    assert!(crate::repo_helpers::validate_repo_url("ftp://evil.com/repo.git").is_err());
}

#[test]
fn test_validate_repo_url_accepts_https() {
    assert!(crate::repo_helpers::validate_repo_url("https://github.com/user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_accepts_git_ssh() {
    assert!(crate::repo_helpers::validate_repo_url("git@github.com:user/repo.git").is_ok());
}

#[test]
fn test_validate_repo_url_accepts_ssh_scheme() {
    assert!(crate::repo_helpers::validate_repo_url("ssh://git@github.com/user/repo.git").is_ok());
}

#[test]
fn test_build_clone_cmd_rejects_injection() {
    assert!(crate::create_helpers::build_clone_cmd("https://evil.com/repo.git; rm -rf /").is_err());
}

// ── validate_name (path traversal) ─────────────────────────────

#[test]
fn test_validate_name_rejects_slash() {
    assert!(crate::name_validation::validate_name("../etc/passwd").is_err());
}

#[test]
fn test_validate_name_rejects_backslash() {
    assert!(crate::name_validation::validate_name("foo\\bar").is_err());
}

#[test]
fn test_validate_name_rejects_dotdot() {
    assert!(crate::name_validation::validate_name("..").is_err());
}

#[test]
fn test_validate_name_rejects_null() {
    assert!(crate::name_validation::validate_name("foo\0bar").is_err());
}

#[test]
fn test_validate_name_rejects_empty() {
    assert!(crate::name_validation::validate_name("").is_err());
}

#[test]
fn test_validate_name_accepts_simple() {
    assert!(crate::name_validation::validate_name("my-profile").is_ok());
}

#[test]
fn test_validate_name_accepts_dot_prefix() {
    assert!(crate::name_validation::validate_name(".hidden").is_ok());
}

#[test]
fn test_validate_name_accepts_underscores() {
    assert!(crate::name_validation::validate_name("my_template_v2").is_ok());
}

#[test]
fn test_template_save_rejects_traversal() {
    let tmp = TempDir::new().unwrap();
    let tpl = toml::Value::Table(Default::default());
    let result = crate::templates::save_template(tmp.path(), "../escape", &tpl);
    assert!(result.is_err());
}

#[test]
fn test_template_load_rejects_traversal() {
    let tmp = TempDir::new().unwrap();
    let result = crate::templates::load_template(tmp.path(), "../../etc/passwd");
    assert!(result.is_err());
}

// ── env delete key validation ──────────────────────────────────

#[test]
fn test_build_env_delete_cmd_rejects_injection() {
    let cmd = crate::env_helpers::build_env_delete_cmd("foo;rm -rf /;#");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_delete_cmd_rejects_dollar() {
    let cmd = crate::env_helpers::build_env_delete_cmd("$HOME");
    assert_eq!(cmd, "true");
}

#[test]
fn test_build_env_delete_cmd_valid_key_works() {
    let cmd = crate::env_helpers::build_env_delete_cmd("VALID_KEY");
    assert!(cmd.contains("sed"));
    assert!(cmd.contains("VALID_KEY"));
}

// ── batch tag filter ───────────────────────────────────────────

#[test]
fn test_build_vm_list_query_no_tag() {
    let q = crate::batch_helpers::build_vm_list_query(None).unwrap();
    assert_eq!(q, "[].id");
}

#[test]
fn test_build_vm_list_query_with_tag() {
    let q = crate::batch_helpers::build_vm_list_query(Some("env=dev")).unwrap();
    assert_eq!(q, "[?tags.env=='dev'].id");
}

#[test]
fn test_build_vm_list_query_invalid_tag_format() {
    assert!(crate::batch_helpers::build_vm_list_query(Some("notag")).is_err());
}

#[test]
fn test_build_vm_list_query_rejects_injection_in_tag_value() {
    assert!(crate::batch_helpers::build_vm_list_query(Some("env=dev';rm -rf /")).is_err());
}

#[test]
fn test_build_vm_list_query_rejects_injection_in_tag_key() {
    assert!(crate::batch_helpers::build_vm_list_query(Some("en$v=dev")).is_err());
}

// ── OnceLock bastion pool flag ─────────────────────────────────
