/// Shell metacharacters that must not appear in a repo URL.
const SHELL_META: &[char] = &[
    ';', '|', '&', '$', '`', '(', ')', '\n', '\r', '\'', '"', '<', '>', '{', '}', ' ',
];

/// Validate that a repository URL does not contain shell metacharacters.
///
/// Returns `Ok(())` if the URL is safe to interpolate into a shell command,
/// or `Err(String)` describing the problem.
pub fn validate_repo_url(url: &str) -> Result<(), String> {
    if url.is_empty() {
        return Err("Repository URL must not be empty".into());
    }
    if let Some(bad) = url.chars().find(|c| SHELL_META.contains(c)) {
        return Err(format!(
            "Repository URL contains disallowed character '{}'",
            bad.escape_default()
        ));
    }
    // Must look like an HTTPS or git@ URL
    if !(url.starts_with("https://")
        || url.starts_with("http://")
        || url.starts_with("git@")
        || url.starts_with("ssh://"))
    {
        return Err(format!(
            "Repository URL must start with https://, http://, git@, or ssh:// (got '{}')",
            url
        ));
    }
    Ok(())
}
