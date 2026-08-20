//! `azlin keys list` — the VM side of the SSH key inventory.
//!
//! The subcommand's own help says "List VMs and their SSH public keys" and it
//! takes `--resource-group`, `--all-vms` and `--vm-prefix` to choose which
//! VMs. It listed the files in the caller's `~/.ssh` instead, ignoring all
//! three (#1089). Nothing about the output depended on Azure at all, so the
//! command answered a question nobody asked and the one it advertised — *which
//! of my VMs carry which key* — could not be asked at all.
//!
//! The VM selection here matches `keys rotate` exactly, deliberately: the two
//! subcommands take the same three flags, and a listing that disagreed with
//! the rotation about which VMs are in scope would be worse than no listing.
//!
//! Keys are shown as OpenSSH SHA256 fingerprints, the same string
//! `ssh-keygen -lf ~/.ssh/id_ed25519.pub` prints, so a fingerprint from this
//! table can be compared against a local key by eye.

use anyhow::{Context, Result};

/// One public key as Azure records it on a VM.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VmPublicKey {
    /// Where the key lands on the VM, e.g. `/home/azureuser/.ssh/authorized_keys`.
    pub path: String,
    /// The `ssh-ed25519 AAAA... comment` line itself.
    pub key_data: String,
}

/// One VM and every public key Azure has recorded for it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VmKeys {
    pub name: String,
    pub keys: Vec<VmPublicKey>,
}

/// Which name prefix restricts the listing, following `keys rotate`: an empty
/// string means every VM in the resource group.
pub fn prefix_filter<'a>(all_vms: bool, vm_prefix: &'a str) -> &'a str {
    if all_vms {
        ""
    } else {
        vm_prefix
    }
}

/// `az vm list` restricted to the fields the table needs.
///
/// The projection is done server-side so that a resource group with a hundred
/// VMs does not ship a hundred full VM documents to print four columns.
pub fn build_vm_keys_args(resource_group: &str, prefix: &str) -> Vec<String> {
    let selector = if prefix.is_empty() {
        "[]".to_string()
    } else {
        format!("[?starts_with(name, '{}')]", prefix)
    };
    let query = format!(
        "{}.{{name:name, keys:osProfile.linuxConfiguration.ssh.publicKeys}}",
        selector
    );
    vec![
        "vm".to_string(),
        "list".to_string(),
        "--resource-group".to_string(),
        resource_group.to_string(),
        "--query".to_string(),
        query,
        "--output".to_string(),
        "json".to_string(),
    ]
}

/// Read the projected `az vm list` output.
///
/// A VM with no `linuxConfiguration` — a Windows VM, or one created with
/// password auth — comes back with `keys: null`, which is a VM with no keys
/// rather than a parse failure. It is listed, saying so.
pub fn parse_vm_keys(stdout: &[u8]) -> Result<Vec<VmKeys>> {
    let value: serde_json::Value =
        serde_json::from_slice(stdout).context("Could not read the VM list returned by Azure")?;
    let array = value
        .as_array()
        .context("Azure returned something other than a list of VMs")?;

    let mut out = Vec::with_capacity(array.len());
    for entry in array {
        let name = entry
            .get("name")
            .and_then(|n| n.as_str())
            .unwrap_or("")
            .to_string();
        if name.is_empty() {
            continue;
        }
        let keys = entry
            .get("keys")
            .and_then(|k| k.as_array())
            .map(|items| {
                items
                    .iter()
                    .map(|item| VmPublicKey {
                        path: item
                            .get("path")
                            .and_then(|p| p.as_str())
                            .unwrap_or("-")
                            .to_string(),
                        key_data: item
                            .get("keyData")
                            .and_then(|d| d.as_str())
                            .unwrap_or("")
                            .to_string(),
                    })
                    .collect()
            })
            .unwrap_or_default();
        out.push(VmKeys { name, keys });
    }
    Ok(out)
}

/// The OpenSSH fingerprint of one `ssh-... AAAA... comment` line.
///
/// Returns `SHA256:…` exactly as `ssh-keygen -l` prints it. Anything that is
/// not a public key line — an empty field, a truncated blob — returns `None`
/// rather than a fingerprint of nothing, because a wrong fingerprint in this
/// table is worse than a blank cell: it would be compared and trusted.
pub fn fingerprint(key_data: &str) -> Option<String> {
    let blob = key_data.split_whitespace().nth(1)?;
    let decoded = base64_decode(blob)?;
    if decoded.is_empty() {
        return None;
    }
    use sha2::{Digest, Sha256};
    let digest = Sha256::digest(&decoded);
    Some(format!("SHA256:{}", base64_encode_unpadded(&digest)))
}

/// The comment at the end of a public key line, if it has one.
pub fn key_comment(key_data: &str) -> Option<String> {
    let rest = key_data.split_whitespace().skip(2).collect::<Vec<_>>();
    if rest.is_empty() {
        None
    } else {
        Some(rest.join(" "))
    }
}

/// The key algorithm, e.g. `ssh-ed25519`.
pub fn key_algorithm(key_data: &str) -> Option<String> {
    key_data
        .split_whitespace()
        .next()
        .filter(|a| a.starts_with("ssh-") || a.starts_with("ecdsa-"))
        .map(|a| a.to_string())
}

const B64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

fn base64_encode_unpadded(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | b[2] as u32;
        let chars = [
            B64[(n >> 18) as usize & 63],
            B64[(n >> 12) as usize & 63],
            B64[(n >> 6) as usize & 63],
            B64[n as usize & 63],
        ];
        // One input byte carries two output characters, two carry three.
        let keep = chunk.len() + 1;
        for c in chars.iter().take(keep) {
            out.push(*c as char);
        }
    }
    out
}

fn base64_decode(input: &str) -> Option<Vec<u8>> {
    let mut acc: u32 = 0;
    let mut bits = 0u32;
    let mut out = Vec::with_capacity(input.len() * 3 / 4);
    for c in input.bytes() {
        if c == b'=' {
            break;
        }
        let v = match c {
            b'A'..=b'Z' => c - b'A',
            b'a'..=b'z' => c - b'a' + 26,
            b'0'..=b'9' => c - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            b'\r' | b'\n' => continue,
            _ => return None,
        } as u32;
        acc = (acc << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((acc >> bits) as u8);
        }
    }
    Some(out)
}

/// The table rows: one line per key, so a VM with two keys occupies two lines
/// and a VM with none still occupies one and says so.
pub fn build_rows(vms: &[VmKeys]) -> Vec<Vec<String>> {
    let mut rows = Vec::new();
    for vm in vms {
        if vm.keys.is_empty() {
            rows.push(vec![
                vm.name.clone(),
                "-".to_string(),
                "no keys recorded".to_string(),
                "-".to_string(),
            ]);
            continue;
        }
        for key in &vm.keys {
            rows.push(vec![
                vm.name.clone(),
                key_algorithm(&key.key_data).unwrap_or_else(|| "-".to_string()),
                fingerprint(&key.key_data).unwrap_or_else(|| "unreadable".to_string()),
                key_comment(&key.key_data).unwrap_or_else(|| "-".to_string()),
            ]);
        }
    }
    rows
}

/// What to say when the selection matched nothing, naming the filter that did
/// the excluding so the fix is obvious.
pub fn empty_message(resource_group: &str, all_vms: bool, vm_prefix: &str) -> String {
    if all_vms || vm_prefix.is_empty() {
        format!("No VMs found in resource group '{}'.", resource_group)
    } else {
        format!(
            "No VMs starting with '{}' found in resource group '{}'. Use --all-vms to list every VM, or --vm-prefix to change the filter.",
            vm_prefix, resource_group
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── prefix_filter ────────────────────────────────────────────

    #[test]
    fn all_vms_clears_the_prefix_exactly_as_rotate_does() {
        assert_eq!(prefix_filter(true, "azlin"), "");
        assert_eq!(prefix_filter(false, "azlin"), "azlin");
        assert_eq!(prefix_filter(false, "web"), "web");
    }

    // ── build_vm_keys_args ───────────────────────────────────────

    #[test]
    fn the_prefix_reaches_the_query() {
        let args = build_vm_keys_args("rg", "web");
        let query = args.iter().find(|a| a.contains("starts_with")).unwrap();
        assert!(query.contains("starts_with(name, 'web')"), "{}", query);
        assert!(query.contains("osProfile.linuxConfiguration.ssh.publicKeys"));
    }

    #[test]
    fn an_empty_prefix_selects_every_vm_without_a_filter() {
        let args = build_vm_keys_args("rg", "");
        let query = args.iter().find(|a| a.contains("publicKeys")).unwrap();
        assert!(!query.contains("starts_with"), "{}", query);
        assert!(query.starts_with("[]."), "{}", query);
    }

    #[test]
    fn the_resource_group_reaches_the_argv() {
        let args = build_vm_keys_args("my-rg", "azlin");
        let i = args.iter().position(|a| a == "--resource-group").unwrap();
        assert_eq!(args[i + 1], "my-rg");
    }

    // ── parse_vm_keys ────────────────────────────────────────────

    #[test]
    fn keys_are_read_per_vm() {
        let json = br#"[
            {"name":"azlin-a","keys":[{"path":"/home/azureuser/.ssh/authorized_keys","keyData":"ssh-ed25519 AAAA me@host"}]},
            {"name":"azlin-b","keys":null}
        ]"#;
        let vms = parse_vm_keys(json).unwrap();
        assert_eq!(vms.len(), 2);
        assert_eq!(vms[0].keys.len(), 1);
        assert_eq!(vms[0].keys[0].path, "/home/azureuser/.ssh/authorized_keys");
        assert!(vms[1].keys.is_empty(), "a null keys field is no keys");
    }

    #[test]
    fn a_vm_with_no_name_is_skipped_rather_than_printed_blank() {
        let vms = parse_vm_keys(br#"[{"keys":null},{"name":"ok","keys":null}]"#).unwrap();
        assert_eq!(vms.len(), 1);
        assert_eq!(vms[0].name, "ok");
    }

    #[test]
    fn garbage_is_an_error_not_an_empty_list() {
        assert!(parse_vm_keys(b"not json").is_err());
        assert!(parse_vm_keys(br#"{"name":"x"}"#).is_err());
    }

    // ── fingerprint ──────────────────────────────────────────────

    #[test]
    fn the_fingerprint_matches_ssh_keygen() {
        // Cross-checked against `ssh-keygen -lf` on this exact key line.
        let key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILUy08oEACPMZQLM0aYTxQExFNSh9xspYJuOdIJokIDR azlin-test";
        assert_eq!(
            fingerprint(key).unwrap(),
            "SHA256:TB1POjaEffD1TfV6GeqnsBUgA7/FTWD9mSt/J0nW/fI"
        );
    }

    #[test]
    fn an_unreadable_key_has_no_fingerprint_rather_than_a_wrong_one() {
        assert_eq!(fingerprint(""), None);
        assert_eq!(fingerprint("ssh-ed25519"), None);
        assert_eq!(fingerprint("ssh-ed25519 !!!not-base64!!!"), None);
    }

    #[test]
    fn base64_round_trips_through_both_halves() {
        for input in [
            &b""[..],
            &b"f"[..],
            &b"fo"[..],
            &b"foo"[..],
            &b"foob"[..],
            &b"fooba"[..],
            &b"foobar"[..],
        ] {
            let encoded = base64_encode_unpadded(input);
            assert_eq!(
                base64_decode(&encoded).unwrap(),
                input,
                "round trip failed for {:?}",
                input
            );
        }
        // RFC 4648 vectors, minus the padding OpenSSH fingerprints omit.
        assert_eq!(base64_encode_unpadded(b"f"), "Zg");
        assert_eq!(base64_encode_unpadded(b"foobar"), "Zm9vYmFy");
    }

    // ── comment and algorithm ────────────────────────────────────

    #[test]
    fn the_comment_is_whatever_follows_the_blob() {
        assert_eq!(
            key_comment("ssh-ed25519 AAAA user@host").as_deref(),
            Some("user@host")
        );
        assert_eq!(
            key_comment("ssh-rsa AAAA two word comment").as_deref(),
            Some("two word comment")
        );
        assert_eq!(key_comment("ssh-ed25519 AAAA"), None);
    }

    #[test]
    fn the_algorithm_is_read_only_when_it_looks_like_one() {
        assert_eq!(
            key_algorithm("ssh-ed25519 AAAA x").as_deref(),
            Some("ssh-ed25519")
        );
        assert_eq!(
            key_algorithm("ecdsa-sha2-nistp256 AAAA").as_deref(),
            Some("ecdsa-sha2-nistp256")
        );
        assert_eq!(key_algorithm("garbage AAAA"), None);
    }

    // ── build_rows ───────────────────────────────────────────────

    #[test]
    fn a_vm_with_two_keys_takes_two_rows_and_one_with_none_still_takes_one() {
        let vms = vec![
            VmKeys {
                name: "a".into(),
                keys: vec![
                    VmPublicKey {
                        path: "p".into(),
                        key_data: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILUy08oEACPMZQLM0aYTxQExFNSh9xspYJuOdIJokIDR one".into(),
                    },
                    VmPublicKey {
                        path: "p".into(),
                        key_data: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILUy08oEACPMZQLM0aYTxQExFNSh9xspYJuOdIJokIDR two".into(),
                    },
                ],
            },
            VmKeys {
                name: "b".into(),
                keys: vec![],
            },
        ];
        let rows = build_rows(&vms);
        assert_eq!(rows.len(), 3);
        assert_eq!(rows[0][0], "a");
        assert_eq!(rows[1][3], "two");
        assert_eq!(rows[2][0], "b");
        assert!(rows[2][2].contains("no keys"), "{:?}", rows[2]);
    }

    // ── empty_message ────────────────────────────────────────────

    #[test]
    fn an_empty_listing_names_the_filter_that_excluded_everything() {
        let msg = empty_message("rg", false, "web");
        assert!(msg.contains("'web'"), "{}", msg);
        assert!(msg.contains("--all-vms"), "{}", msg);

        let msg = empty_message("rg", true, "web");
        assert!(
            !msg.contains("--all-vms"),
            "already listing every VM: {}",
            msg
        );
    }
}
