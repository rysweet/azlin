/// Split a `key=value` tag string. Returns `None` if the format is invalid
/// (missing `=`, empty key, or fewer than 2 parts).
pub fn parse_tag(input: &str) -> Option<(&str, &str)> {
    let parts: Vec<&str> = input.splitn(2, '=').collect();
    if parts.len() == 2 && !parts[0].is_empty() {
        Some((parts[0], parts[1]))
    } else {
        None
    }
}

/// Validate a list of tag strings, returning the first invalid one (if any).
#[allow(dead_code)]
pub fn find_invalid_tag(tags: &[String]) -> Option<&str> {
    tags.iter()
        .find(|t| parse_tag(t).is_none())
        .map(|t| t.as_str())
}
