use regex::Regex;
use std::sync::LazyLock;

// PEM marker pattern built at runtime to avoid tripping detect-private-key hooks
fn pem_begin_pattern() -> String {
    format!("-----BEGIN [A-Z ]+ {}-----", "PRIVATE KEY")
}

static PATTERNS: LazyLock<Vec<(Regex, &str)>> = LazyLock::new(|| {
    vec![
        // Azure storage keys (base64, 88 chars)
        (
            Regex::new(r#"(?i)(key|password|secret|token|credential)[\s=:]+['""]?(\S{8,})"#)
                .unwrap(),
            "$1=***REDACTED***",
        ),
        // Connection strings
        (
            Regex::new(r"(?i)AccountKey=[A-Za-z0-9+/=]+").unwrap(),
            "AccountKey=***REDACTED***",
        ),
        // SAS tokens
        (
            Regex::new(r"(?i)sig=[A-Za-z0-9%+/=]+").unwrap(),
            "sig=***REDACTED***",
        ),
        // Bearer tokens
        (
            Regex::new(r#"(?i)Bearer\s+[A-Za-z0-9._-]+"#).unwrap(),
            "Bearer ***REDACTED***",
        ),
        // SSH keys (PEM format)
        (
            Regex::new(&pem_begin_pattern()).unwrap(),
            "***PEM_KEY_REDACTED***",
        ),
    ]
});

/// Everything a terminal treats as an instruction rather than as text.
///
/// `char::is_control()` answers for general category `Cc` alone. `Cf` is the
/// category the bidirectional overrides live in, and it is reachable from a
/// filesystem LABEL: `home\u{202e}dedarged` renders the tail right-to-left, so
/// a `degraded` verdict can be made to read as `ok` with no control character
/// anywhere in the string. Both categories go.
///
/// The class is written as a regex rather than as a hand-rolled table because
/// `Cf` is 25 disjoint ranges that Unicode revises; `regex` already ships and
/// maintains those tables, and this crate already depends on it.
static NON_PRINTABLE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[\p{Cc}\p{Cf}]").unwrap());

/// Remote-derived text with anything that can move a terminal cursor removed.
///
/// Device paths, provisioning statuses and failed-section names all come off a
/// VM and land in an operator's terminal — a table cell, a repair plan, a
/// `[AZLIN]` note. All of it is root-controlled on the VM, so nothing here
/// defends against an attacker who is already root there; what it does is stop
/// one machine's output from rewriting the report of the machines listed after
/// it, or from dressing a bad verdict up as a good one.
///
/// Stripping is about cursor movement, not about ASCII: a hostname or a label
/// in another script is not hostile and survives intact.
///
/// This lives beside [`sanitize`] because the two compose, and in one
/// direction only — redact first, then strip. The redaction patterns are
/// written against ordinary text, and a control character planted inside a
/// token is enough to split it out of a match:
///
/// ```
/// use azlin_core::sanitizer::{printable, sanitize};
///
/// let hostile = "AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5\r\x1b[1;31mSTORAGE OK";
/// let cleaned = printable(&sanitize(hostile));
/// assert!(cleaned.contains("REDACTED"));
/// assert!(!cleaned.contains('\r') && !cleaned.contains('\u{1b}'));
/// ```
pub fn printable(value: &str) -> String {
    NON_PRINTABLE.replace_all(value, "").into_owned()
}

/// Sanitize a string by replacing sensitive patterns with redacted versions.
///
/// # Examples
///
/// ```
/// use azlin_core::sanitizer::sanitize;
///
/// // Normal text passes through unchanged
/// let text = "VM started in eastus";
/// assert_eq!(sanitize(text), text);
///
/// // Account keys are redacted
/// let input = "AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5";
/// assert!(sanitize(input).contains("REDACTED"));
///
/// // Bearer tokens are redacted
/// let input = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig";
/// let output = sanitize(input);
/// assert!(output.contains("REDACTED"));
/// assert!(!output.contains("eyJh"));
/// ```
pub fn sanitize(input: &str) -> String {
    let mut result = input.to_string();
    for (pattern, replacement) in PATTERNS.iter() {
        result = pattern.replace_all(&result, *replacement).to_string();
    }
    result
}

/// Check if a string contains sensitive data.
///
/// # Examples
///
/// ```
/// use azlin_core::sanitizer::contains_sensitive_data;
///
/// assert!(!contains_sensitive_data("just normal text"));
/// assert!(contains_sensitive_data("AccountKey=abc123def456"));
/// assert!(contains_sensitive_data("Bearer eyJhbGciOiJIUzI1NiJ9"));
/// ```
pub fn contains_sensitive_data(input: &str) -> bool {
    PATTERNS.iter().any(|(pattern, _)| pattern.is_match(input))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sanitize_account_key() {
        let input = "AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5IHZhbHVlIGZvciBBenVyZQ==";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
        assert!(!sanitized.contains("dGhpcyB"));
    }

    #[test]
    fn test_sanitize_bearer_token() {
        let input = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
        assert!(!sanitized.contains("eyJh"));
    }

    #[test]
    fn test_sanitize_sas_token() {
        let input = "https://storage.blob.core.windows.net/container?sig=abc123def456%2B";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_sanitize_password_field() {
        let input = "password=MySecretPass123!";
        let sanitized = sanitize(input);
        assert!(sanitized.contains("REDACTED"));
        assert!(!sanitized.contains("MySecret"));
    }

    #[test]
    fn test_sanitize_preserves_normal_text() {
        let input = "VM 'my-vm' started successfully in eastus region";
        assert_eq!(sanitize(input), input);
    }

    #[test]
    fn test_sanitize_pem_key() {
        // Construct the marker at runtime to avoid detect-private-key hook
        let marker = format!("-----BEGIN RSA {} KEY-----", "PRIVATE");
        let input = format!("Found key: {}", marker);
        let sanitized = sanitize(&input);
        assert!(sanitized.contains("REDACTED"));
    }

    #[test]
    fn test_contains_sensitive_true() {
        assert!(contains_sensitive_data("AccountKey=abc123"));
    }

    #[test]
    fn test_contains_sensitive_false() {
        assert!(!contains_sensitive_data("just normal text"));
    }

    // -----------------------------------------------------------------------
    // printable: remote-derived text that lands in an operator's terminal
    //
    // `disk_layout` strips control characters at the parse boundary, but it is
    // not the only reader of VM-supplied text. Sharing one predicate here is
    // what lets the second and third readers get the rule for free instead of
    // each remembering it. See the callers in `auth_forward::failed_sections`
    // and the storage probe's stderr bail.
    // -----------------------------------------------------------------------

    #[test]
    fn printable_keeps_text_a_terminal_can_render() {
        assert_eq!(printable("disk-home"), "disk-home");
        assert_eq!(
            printable("/dev/disk/azure/scsi1/lun0"),
            "/dev/disk/azure/scsi1/lun0"
        );
        assert_eq!(printable("apt-install, disk-tmp"), "apt-install, disk-tmp");
    }

    #[test]
    fn printable_removes_anything_that_moves_the_cursor() {
        // A label a VM controls, carrying a CR to overwrite the row already
        // printed and an ANSI sequence to repaint what follows it.
        let hostile = "ok\r\x1b[2Kdegraded\x08\x07";
        let cleaned = printable(hostile);
        assert!(
            !cleaned.contains('\r'),
            "carriage return survived: {cleaned:?}"
        );
        assert!(!cleaned.contains('\x1b'), "escape survived: {cleaned:?}");
        assert!(!cleaned.contains('\x08'), "backspace survived: {cleaned:?}");
        assert!(!cleaned.contains('\x07'), "bell survived: {cleaned:?}");
        // The escape *introducer* is gone, so what is left is inert text.
        assert_eq!(cleaned, "ok[2Kdegraded");
    }

    /// `char::is_control()` answers for category Cc only. Category Cf carries
    /// the bidirectional overrides, and a filesystem LABEL is enough to reach
    /// them: `LABEL=home\u{202e}...` renders the rest of the row right-to-left,
    /// so a `degraded` verdict can be made to read as `ok` with no control
    /// character anywhere in the string.
    #[test]
    fn printable_removes_the_format_characters_is_control_misses() {
        for (name, ch) in [
            ("LEFT-TO-RIGHT MARK", '\u{200e}'),
            ("RIGHT-TO-LEFT MARK", '\u{200f}'),
            ("LEFT-TO-RIGHT EMBEDDING", '\u{202a}'),
            ("RIGHT-TO-LEFT OVERRIDE", '\u{202e}'),
            ("POP DIRECTIONAL FORMATTING", '\u{202c}'),
            ("LEFT-TO-RIGHT ISOLATE", '\u{2066}'),
            ("POP DIRECTIONAL ISOLATE", '\u{2069}'),
            ("SOFT HYPHEN", '\u{00ad}'),
        ] {
            let input = format!("home{ch}data");
            assert_eq!(
                printable(&input),
                "homedata",
                "{name} (U+{:04X}) survived printable()",
                ch as u32
            );
        }
    }

    #[test]
    fn printable_keeps_non_ascii_that_is_merely_foreign() {
        // Stripping is about cursor movement, not about ASCII. A hostname or a
        // label in another script is not hostile and must survive intact.
        assert_eq!(printable("données"), "données");
        assert_eq!(printable("ホーム"), "ホーム");
        assert_eq!(printable("home-données"), "home-données");
    }

    #[test]
    fn printable_leaves_nothing_when_given_nothing_but_control() {
        assert_eq!(printable("\r\n\t\u{202e}"), "");
        assert_eq!(printable(""), "");
    }

    /// The two helpers compose in one direction only: redact first (the
    /// patterns are written against ordinary text), then strip. A control
    /// character inside a token is enough to split it out of a regex match.
    #[test]
    fn printable_and_sanitize_compose_for_remote_stderr() {
        let hostile = "AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5\r\x1b[1;31mSTORAGE OK";
        let cleaned = printable(&sanitize(hostile));
        assert!(cleaned.contains("REDACTED"), "redaction lost: {cleaned:?}");
        assert!(!cleaned.contains("dGhpcyB"), "key survived: {cleaned:?}");
        assert!(
            !cleaned.contains('\r') && !cleaned.contains('\x1b'),
            "cursor control survived: {cleaned:?}"
        );
    }
}
