//! Shared GitHub-release selection logic for the update notice and the
//! self-update downloader.
//!
//! Both callers must agree on which release is "latest", and both must ignore
//! prereleases and drafts. GitHub's `/releases` endpoint returns items ordered
//! by creation time, which is NOT the same as semantic-version order and does
//! not exclude prereleases — so naively taking the first `-rust` tag can select
//! a yanked prerelease (e.g. a release republished as a prerelease keeps its
//! assets and can sort ahead of a newer stable one). Always filter, then pick
//! the highest semver.

use serde_json::Value;

/// Parse a release tag such as `v2.6.86-rust.d82739c` (or a bare `2.6.86`) into
/// its numeric `(major, minor, patch)` components. Returns `None` if the base
/// version isn't three dot-separated integers.
pub fn parse_base_version(tag: &str) -> Option<(u64, u64, u64)> {
    let s = tag.strip_prefix('v').unwrap_or(tag);
    // Drop the `-rust.<sha>` (or any other `-` suffix) before parsing.
    let base = s.split('-').next().unwrap_or(s);
    let mut parts = base.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    // Reject trailing junk like "2.6.86.1" so the format stays strict.
    if parts.next().is_some() {
        return None;
    }
    Some((major, minor, patch))
}

/// Return true if the release is a usable stable `-rust` release: it carries a
/// `-rust` tag with a parseable version and is neither a prerelease nor a draft.
fn is_stable_rust_release(release: &Value) -> bool {
    let tag = release["tag_name"].as_str().unwrap_or("");
    tag.contains("-rust")
        && parse_base_version(tag).is_some()
        && !release["prerelease"].as_bool().unwrap_or(false)
        && !release["draft"].as_bool().unwrap_or(false)
}

/// Return true if the release has an asset whose name contains `suffix` and ends
/// with `.tar.gz` (the platform binary tarball).
fn has_matching_asset(release: &Value, suffix: &str) -> bool {
    release["assets"]
        .as_array()
        .map(|assets| {
            assets.iter().any(|a| {
                let name = a["name"].as_str().unwrap_or("");
                name.contains(suffix) && name.ends_with(".tar.gz")
            })
        })
        .unwrap_or(false)
}

/// Select the highest-semver stable `-rust` release from a GitHub `/releases`
/// JSON array. When `require_asset` is `Some(suffix)`, only releases that
/// publish a matching `<suffix>*.tar.gz` asset are considered (used by the
/// downloader so it never selects an assetless yanked release). Returns the
/// chosen release object, or `None` if nothing qualifies.
pub fn best_stable_release<'a>(
    releases: &'a [Value],
    require_asset: Option<&str>,
) -> Option<&'a Value> {
    releases
        .iter()
        .filter(|r| is_stable_rust_release(r))
        .filter(|r| match require_asset {
            Some(suffix) => has_matching_asset(r, suffix),
            None => true,
        })
        .max_by_key(|r| {
            // Safe: is_stable_rust_release already guaranteed a parseable tag.
            parse_base_version(r["tag_name"].as_str().unwrap_or("")).unwrap_or((0, 0, 0))
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_rust_tag() {
        assert_eq!(parse_base_version("v2.6.86-rust.d82739c"), Some((2, 6, 86)));
        assert_eq!(parse_base_version("2.6.86-rust.abc"), Some((2, 6, 86)));
        assert_eq!(parse_base_version("v2.6.86"), Some((2, 6, 86)));
        assert_eq!(parse_base_version("v10.20.30-rust.x"), Some((10, 20, 30)));
    }

    #[test]
    fn rejects_malformed_tags() {
        assert_eq!(parse_base_version("v2.6"), None);
        assert_eq!(parse_base_version("2.6.86.1"), None);
        assert_eq!(parse_base_version("latest"), None);
        assert_eq!(parse_base_version("v2.x.0-rust.y"), None);
    }

    fn rel(tag: &str, prerelease: bool, draft: bool, assets: &[&str]) -> Value {
        json!({
            "tag_name": tag,
            "prerelease": prerelease,
            "draft": draft,
            "assets": assets.iter().map(|n| json!({"name": n})).collect::<Vec<_>>(),
        })
    }

    #[test]
    fn skips_prerelease_even_if_newest_and_has_assets() {
        // A prerelease with a higher patch must NOT be chosen over a stable one.
        let releases = vec![
            rel("v2.6.84-rust.aaa", true, false, &["azlin-linux-aarch64.tar.gz"]),
            rel("v2.6.83-rust.bbb", true, false, &[]),
            rel("v2.6.82-rust.ccc", false, false, &["azlin-linux-aarch64.tar.gz"]),
        ];
        let best = best_stable_release(&releases, None).unwrap();
        assert_eq!(best["tag_name"], "v2.6.82-rust.ccc");
    }

    #[test]
    fn picks_highest_semver_regardless_of_list_order() {
        // Out-of-order list; must still pick 2.6.86, not the first element.
        let releases = vec![
            rel("v2.6.80-rust.a", false, false, &["azlin-linux-aarch64.tar.gz"]),
            rel("v2.6.86-rust.b", false, false, &["azlin-linux-aarch64.tar.gz"]),
            rel("v2.6.85-rust.c", false, false, &["azlin-linux-aarch64.tar.gz"]),
        ];
        let best = best_stable_release(&releases, None).unwrap();
        assert_eq!(best["tag_name"], "v2.6.86-rust.b");
    }

    #[test]
    fn require_asset_skips_assetless_and_wrong_platform() {
        let releases = vec![
            rel("v2.6.86-rust.a", false, false, &[]), // assetless (yanked-style)
            rel("v2.6.85-rust.b", false, false, &["azlin-macos-x86_64.tar.gz"]),
            rel("v2.6.84-rust.c", false, false, &["azlin-linux-aarch64.tar.gz"]),
        ];
        let best = best_stable_release(&releases, Some("linux-aarch64")).unwrap();
        assert_eq!(best["tag_name"], "v2.6.84-rust.c");
    }

    #[test]
    fn ignores_non_rust_and_drafts() {
        let releases = vec![
            rel("v9.9.9", false, false, &["azlin-linux-aarch64.tar.gz"]), // no -rust
            rel("v2.6.90-rust.d", false, true, &["azlin-linux-aarch64.tar.gz"]), // draft
            rel("v2.6.86-rust.e", false, false, &["azlin-linux-aarch64.tar.gz"]),
        ];
        let best = best_stable_release(&releases, None).unwrap();
        assert_eq!(best["tag_name"], "v2.6.86-rust.e");
    }

    #[test]
    fn returns_none_when_nothing_qualifies() {
        let releases = vec![
            rel("v2.6.84-rust.a", true, false, &["azlin-linux-aarch64.tar.gz"]),
            rel("v9.9.9", false, false, &["azlin-linux-aarch64.tar.gz"]),
        ];
        assert!(best_stable_release(&releases, None).is_none());
    }
}
