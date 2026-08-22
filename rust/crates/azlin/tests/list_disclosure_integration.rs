//! End-to-end coverage for the filter disclosure in `azlin list` (#1142).
//!
//! The defect these tests exist for was never in `apply_filters`. Filtering to
//! running VMs by default is the right behaviour. The defect was that the
//! filtering was *silent*: the repo owner had six VMs in
//! `rysweet-linux-vm-pool`, `azlin list` showed two, and the four it removed --
//! `deva2`, `deva3`, `ia2` (Deallocated) and `test-lifecycle-vm` (Stopped) --
//! held ~11.7 TB of attached Premium SSD that billed at full rate for weeks.
//! The summary line read `Total: 2 VMs | 2 running` and gave no hint that a
//! longer list existed or which flag revealed it.
//!
//! A unit test on a counter cannot catch that. The counter was never the thing
//! that failed the operator -- the *screen* was. So these tests drive the real
//! binary, with a stub `az` on `PATH` standing in for Azure, and assert on what
//! a user would actually see in each output format.

#![cfg(unix)]

use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

// ── Fixtures ─────────────────────────────────────────────────────────

/// One `az vm list --show-details` entry.
fn vm_json(name: &str, power_state: &str, env_tag: &str) -> String {
    format!(
        r#"{{
          "name": "{name}",
          "resourceGroup": "rysweet-linux-vm-pool",
          "location": "eastus",
          "powerState": "{power_state}",
          "provisioningState": "Succeeded",
          "hardwareProfile": {{ "vmSize": "Standard_D4s_v3" }},
          "storageProfile": {{
            "osDisk": {{ "osType": "Linux" }},
            "imageReference": {{ "offer": "ubuntu-24_04-lts" }}
          }},
          "osProfile": {{ "adminUsername": "azureuser" }},
          "publicIps": "",
          "privateIps": "10.0.0.1",
          "tags": {{ "env": "{env_tag}" }}
        }}"#
    )
}

/// The pool as it actually stood on 2026-08-21: two running, four not.
fn six_vm_pool() -> String {
    let vms = [
        vm_json("azt1", "VM running", "dev"),
        vm_json("dev", "VM running", "dev"),
        vm_json("deva2", "VM deallocated", "dev"),
        vm_json("deva3", "VM deallocated", "dev"),
        vm_json("ia2", "VM deallocated", "prod"),
        vm_json("test-lifecycle-vm", "VM stopped", "dev"),
    ];
    format!("[{}]", vms.join(","))
}

/// A pool where every VM is running, so no filter has anything to remove.
fn all_running_pool() -> String {
    let vms = [
        vm_json("azt1", "VM running", "dev"),
        vm_json("dev", "VM running", "dev"),
    ];
    format!("[{}]", vms.join(","))
}

// ── Harness ──────────────────────────────────────────────────────────

/// A sandbox holding a stub `az`, a VM fixture, and empty HOME/config dirs.
///
/// azlin reaches Azure by shelling out to `az`, resolved from `PATH`. Putting
/// a stub first on `PATH` is therefore enough to run the whole `list` pipeline
/// -- auth, fetch, filter, render -- against known data with no subscription,
/// no credentials, and no network. `HOME` and `AZLIN_CONFIG_DIR` point at empty
/// temp dirs so a developer's real `~/.azlin` cannot leak in (#1079).
struct Sandbox {
    dir: tempfile::TempDir,
}

impl Sandbox {
    fn new(vm_fixture: &str) -> Self {
        let dir = tempfile::TempDir::new().expect("sandbox temp dir");
        let root = dir.path();
        std::fs::create_dir_all(root.join("bin")).expect("bin dir");
        std::fs::create_dir_all(root.join("home")).expect("home dir");
        std::fs::create_dir_all(root.join("config")).expect("config dir");

        let fixture = root.join("vms.json");
        std::fs::write(&fixture, vm_fixture).expect("write vm fixture");

        // Answers only the calls `azlin list` makes: `account show` for auth,
        // `vm list` for the pool. Everything else -- bastion enumeration, size
        // lookups -- gets an empty array, which is a valid "none of those".
        let stub = format!(
            "#!/bin/sh\n\
             case \"$*\" in\n\
             *'account show'*) echo '{{\"id\":\"00000000-0000-0000-0000-000000000001\",\
             \"tenantId\":\"00000000-0000-0000-0000-000000000002\",\"name\":\"stub\",\
             \"user\":{{\"name\":\"stub@example.com\"}}}}' ;;\n\
             *'vm list'*) cat '{}' ;;\n\
             *) echo '[]' ;;\n\
             esac\n\
             exit 0\n",
            fixture.display()
        );
        let az = root.join("bin").join("az");
        let mut f = std::fs::File::create(&az).expect("create az stub");
        f.write_all(stub.as_bytes()).expect("write az stub");
        drop(f);
        std::fs::set_permissions(&az, std::fs::Permissions::from_mode(0o755))
            .expect("chmod az stub");

        Self { dir }
    }

    fn path(&self) -> &Path {
        self.dir.path()
    }

    fn bin_dir(&self) -> PathBuf {
        self.path().join("bin")
    }

    /// Run `azlin <args>` inside the sandbox; returns (stdout, stderr, code).
    fn run(&self, args: &[&str]) -> (String, String, i32) {
        let inherited = std::env::var("PATH").unwrap_or_default();
        let path = format!("{}:{}", self.bin_dir().display(), inherited);
        let out = Command::new(env!("CARGO_BIN_EXE_azlin"))
            .args(args)
            .env("PATH", path)
            .env("HOME", self.path().join("home"))
            .env("AZLIN_CONFIG_DIR", self.path().join("config"))
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .env_remove("AZURE_TENANT_ID")
            .output()
            .expect("run azlin");
        (
            strip_ansi(&String::from_utf8_lossy(&out.stdout)),
            strip_ansi(&String::from_utf8_lossy(&out.stderr)),
            out.status.code().unwrap_or(-1),
        )
    }
}

/// Drop ANSI SGR sequences so assertions match the words, not the colours.
///
/// azlin styles its summary and hints unconditionally -- it does not honour
/// `NO_COLOR` -- so a literal `contains("4 hidden")` against raw output would
/// pass or fail on where the bold escape happens to fall.
fn strip_ansi(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c != '\u{1b}' {
            out.push(c);
            continue;
        }
        if chars.peek() == Some(&'[') {
            chars.next();
            for c in chars.by_ref() {
                if c.is_ascii_alphabetic() {
                    break;
                }
            }
        }
    }
    out
}

/// The `list` invocation these tests share: an explicit resource group (no
/// config is present to supply one) and no tmux collection (which would try to
/// SSH to the fixture VMs).
const BASE: [&str; 3] = ["--resource-group", "rysweet-linux-vm-pool", "--no-tmux"];

fn list_args<'a>(extra: &[&'a str]) -> Vec<&'a str> {
    let mut args = vec!["list"];
    args.extend_from_slice(&BASE);
    args.extend_from_slice(extra);
    args
}

/// The same invocation with a global `--output <format>` in front of `list`.
fn formatted_list_args(format: &'static str) -> Vec<&'static str> {
    let mut args = vec!["--output", format, "list"];
    args.extend_from_slice(&BASE);
    args
}

// ── Table output ─────────────────────────────────────────────────────

/// The #1142 regression test. Four VMs vanish from the default view; the
/// default view must say so, and must name the flag that brings them back.
#[test]
fn default_table_discloses_hidden_non_running_vms() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&list_args(&[]));
    assert_eq!(code, 0, "list should succeed: {stdout}");

    // The default is unchanged: still running-only.
    assert!(
        stdout.contains("Total: 2 VMs"),
        "unexpected summary: {stdout}"
    );
    assert!(
        !stdout.contains("deva2"),
        "the default view must not start listing stopped VMs: {stdout}"
    );

    // ...but it is no longer silent about the four it dropped.
    assert!(
        stdout.contains("4 hidden"),
        "the default view must disclose the four hidden VMs: {stdout}"
    );
    assert!(
        stdout.contains("stopped/deallocated"),
        "the disclosure must say *why* they are hidden: {stdout}"
    );
    // Assert the *remedy sentence*, not just the flag name. `azlin list --all`
    // on its own is a useless assertion: the hints block prints that exact
    // string on every run, so this test passed with the remedy `println!`
    // deleted from `render_table` entirely -- i.e. with the cost message the
    // whole incident was about missing from the screen. The literal below
    // appears nowhere but the disclosure.
    assert!(
        stdout.contains("Hidden VMs still bill for attached storage."),
        "the disclosure must state the cost consequence, which is the reason \
         #1142 mattered -- 11.7 TB of Premium SSD billed against machines the \
         listing did not mention: {stdout}"
    );
    assert!(
        stdout.contains("Run 'azlin list --all' to include them."),
        "the disclosure must name the flag that reveals them -- note `-a` is \
         --show-all-vms (scan all resource groups), a different flag: {stdout}"
    );
}

/// Requirement 1's other half: do not print a scary warning when nothing was
/// hidden. A disclosure that fires on every run is noise, and noise is ignored.
#[test]
fn default_table_stays_quiet_when_nothing_is_hidden() {
    let sandbox = Sandbox::new(&all_running_pool());
    let (stdout, stderr, code) = sandbox.run(&list_args(&[]));
    assert_eq!(code, 0, "list should succeed: {stdout}");
    assert!(
        stdout.contains("Total: 2 VMs"),
        "unexpected summary: {stdout}"
    );
    assert!(
        !stdout.contains("hidden"),
        "nothing was filtered, so nothing should be disclosed: {stdout}"
    );
    assert!(
        !stderr.contains("hidden"),
        "nothing was filtered, so stderr should be quiet too: {stderr}"
    );
}

#[test]
fn all_flag_shows_every_vm_and_discloses_nothing() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&list_args(&["--all"]));
    assert_eq!(code, 0, "list --all should succeed: {stdout}");
    assert!(
        stdout.contains("Total: 6 VMs"),
        "unexpected summary: {stdout}"
    );
    assert!(
        !stdout.contains("hidden"),
        "--all hides nothing, so it must disclose nothing: {stdout}"
    );
}

#[test]
fn include_stopped_flag_shows_every_vm_and_discloses_nothing() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&list_args(&["--include-stopped"]));
    assert_eq!(code, 0, "list --include-stopped should succeed: {stdout}");
    assert!(
        stdout.contains("Total: 6 VMs"),
        "unexpected summary: {stdout}"
    );
    assert!(
        !stdout.contains("hidden"),
        "--include-stopped hides nothing, so it must disclose nothing: {stdout}"
    );
}

/// Requirement 2: `--vm-pattern` was silent too. An empty table tells the
/// operator nothing; "2 excluded by --vm-pattern" tells them their pattern is
/// wrong, which is almost always the truth.
#[test]
fn table_discloses_rows_excluded_by_vm_pattern() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&list_args(&["--vm-pattern", "staging*"]));
    assert_eq!(code, 0, "list --vm-pattern should succeed: {stdout}");
    assert!(
        stdout.contains("Total: 0 VMs"),
        "unexpected summary: {stdout}"
    );
    assert!(
        stdout.contains("6 excluded") && stdout.contains("--vm-pattern"),
        "an empty result must name the pattern that emptied it, and the count \
         is all six -- the pattern runs before the running-only default, so it \
         sees the whole fetched set: {stdout}"
    );
    // The pattern removed everything before the running filter ran, so nothing
    // was hidden *from this listing*. Claiming otherwise would be a lie about
    // the operator's query, and would drag in a remedy that does not apply.
    assert!(
        !stdout.contains("hidden"),
        "nothing was hidden from a listing the pattern had already emptied: {stdout}"
    );
    assert!(
        !stdout.contains("bill for attached storage"),
        "`--all` would not bring back rows the pattern excluded, so advising it \
         here would send the operator to a different question's answer: {stdout}"
    );
}

/// The hidden count must describe *the operator's query*, not the resource
/// group. This is the case that made group-wide counting indefensible: the
/// remedy says "run `azlin list --all`", and the number next to it has to be
/// what that command would actually add back to *this* listing.
#[test]
fn hidden_count_is_scoped_to_the_pattern_the_operator_typed() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&list_args(&["--vm-pattern", "dev*"]));
    assert_eq!(code, 0, "list --vm-pattern should succeed: {stdout}");

    // Pool: azt1, dev (Running); deva2, deva3, ia2 (Deallocated);
    // test-lifecycle-vm (Stopped). `dev*` matches dev, deva2, deva3.
    assert!(
        stdout.contains("Total: 1 VMs"),
        "only the running `dev` matches the pattern: {stdout}"
    );
    assert!(
        stdout.contains("3 excluded") && stdout.contains("--vm-pattern"),
        "azt1, ia2 and test-lifecycle-vm do not match `dev*`: {stdout}"
    );
    assert!(
        stdout.contains("2 hidden"),
        "deva2 and deva3 -- the two hidden machines `--all` would add to THIS \
         listing. The pool holds four non-running VMs, but ia2 and \
         test-lifecycle-vm do not match the pattern and are not what the \
         remedy is offering: {stdout}"
    );
    assert!(
        !stdout.contains("4 hidden"),
        "reporting the resource group's four would misattribute two machines \
         the operator did not ask about: {stdout}"
    );
    assert!(
        stdout.contains("Hidden VMs still bill for attached storage."),
        "two of the operator's own dev machines are billing; say so: {stdout}"
    );
}

/// Requirement 2, tag half. `ia2` is the only `env=prod` VM and it is
/// deallocated, so with the default filters `--tag env=prod` drops nothing by
/// tag and everything by power state -- exactly the confusing case worth
/// spelling out. `--all` isolates the tag filter's own count.
#[test]
fn table_discloses_rows_excluded_by_tag() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&list_args(&["--all", "--tag", "env=prod"]));
    assert_eq!(code, 0, "list --tag should succeed: {stdout}");
    assert!(
        stdout.contains("Total: 1 VMs"),
        "unexpected summary: {stdout}"
    );
    assert!(
        stdout.contains("5 excluded") && stdout.contains("--tag"),
        "the tag filter must report its own drops: {stdout}"
    );
}

// ── JSON output ──────────────────────────────────────────────────────

/// Requirement 3: the counts must reach machine consumers, not just the table.
///
/// The payload becomes an envelope -- `{"vms": [...], "filters": {...}}` --
/// because a bare top-level array has nowhere to put result-level metadata.
/// A trailing synthetic element would pollute `.[]`; per-VM duplication has the
/// wrong cardinality and disappears entirely when the result is empty, which is
/// precisely the case that most needs explaining.
#[test]
fn json_carries_filter_counts_in_an_envelope() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, _stderr, code) = sandbox.run(&formatted_list_args("json"));
    assert_eq!(code, 0, "json list should succeed: {stdout}");

    let payload: serde_json::Value = serde_json::from_str(&stdout)
        .unwrap_or_else(|e| panic!("stdout must be JSON ({e}): {stdout}"));
    let vms = payload["vms"]
        .as_array()
        .unwrap_or_else(|| panic!("payload must have a `vms` array: {stdout}"));
    assert_eq!(
        vms.len(),
        2,
        "the default view still returns running VMs only"
    );

    let filters = &payload["filters"];
    assert_eq!(
        filters["hidden_not_running"], 4,
        "the hidden count must reach JSON consumers: {stdout}"
    );
    assert_eq!(filters["dropped_by_tag"], 0, "{stdout}");
    assert_eq!(filters["dropped_by_pattern"], 0, "{stdout}");
}

/// The envelope's schema is stable: `filters` is always present with all three
/// keys, zeros included. Requirement 1's "stay quiet" rule governs human
/// output; a conditionally-present key would force every consumer to
/// disambiguate `null` from `0`, which is a defect generator.
#[test]
fn json_envelope_always_carries_filters_even_when_zero() {
    let sandbox = Sandbox::new(&all_running_pool());
    let (stdout, _stderr, code) = sandbox.run(&formatted_list_args("json"));
    assert_eq!(code, 0, "json list should succeed: {stdout}");

    let payload: serde_json::Value = serde_json::from_str(&stdout)
        .unwrap_or_else(|e| panic!("stdout must be JSON ({e}): {stdout}"));
    assert_eq!(payload["vms"].as_array().map(Vec::len), Some(2), "{stdout}");
    assert_eq!(payload["filters"]["hidden_not_running"], 0, "{stdout}");
    assert_eq!(payload["filters"]["dropped_by_tag"], 0, "{stdout}");
    assert_eq!(payload["filters"]["dropped_by_pattern"], 0, "{stdout}");
}

/// Requirement 3's prohibition: no human hint text in the machine formats.
/// The disclosure a terminal user needs goes to stderr, where it cannot
/// corrupt a payload being piped into `jq`.
#[test]
fn json_keeps_prose_off_stdout_and_discloses_on_stderr() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, stderr, code) = sandbox.run(&formatted_list_args("json"));
    assert_eq!(code, 0, "json list should succeed: {stdout}");

    serde_json::from_str::<serde_json::Value>(&stdout)
        .unwrap_or_else(|e| panic!("stdout must parse as JSON ({e}): {stdout}"));
    assert!(
        !stdout.contains("azlin list --all") && !stdout.contains("Hints:"),
        "human hint text must not appear in the JSON payload: {stdout}"
    );
    assert!(
        stderr.contains("4 hidden"),
        "a human running `-o json` at a terminal still needs the disclosure: {stderr}"
    );
}

// ── CSV output ───────────────────────────────────────────────────────

/// CSV has nowhere to carry metadata without corrupting itself: a `#` comment
/// line is a bogus row to most parsers, and extra columns have the wrong
/// cardinality. So stdout stays exactly header-plus-rows and the disclosure
/// goes to stderr -- visible to the operator, invisible to the parser.
#[test]
fn csv_stdout_stays_uncorrupted_and_discloses_on_stderr() {
    let sandbox = Sandbox::new(&six_vm_pool());
    let (stdout, stderr, code) = sandbox.run(&formatted_list_args("csv"));
    assert_eq!(code, 0, "csv list should succeed: {stdout}");

    let lines: Vec<&str> = stdout.lines().filter(|l| !l.trim().is_empty()).collect();
    assert_eq!(
        lines.len(),
        3,
        "CSV stdout must be one header plus two data rows, nothing else: {stdout}"
    );
    assert!(
        lines[0].starts_with("Session,"),
        "unexpected header: {stdout}"
    );
    assert!(
        !stdout.contains('#') && !stdout.contains("hidden"),
        "no commentary may be written into the CSV stream: {stdout}"
    );
    assert!(
        stderr.contains("4 hidden"),
        "CSV consumers and operators still need the hidden count: {stderr}"
    );
}

#[test]
fn csv_stays_quiet_when_nothing_is_hidden() {
    let sandbox = Sandbox::new(&all_running_pool());
    let (stdout, stderr, code) = sandbox.run(&formatted_list_args("csv"));
    assert_eq!(code, 0, "csv list should succeed: {stdout}");
    assert!(
        !stderr.contains("hidden"),
        "nothing was filtered, so stderr must stay quiet: {stderr}"
    );
}

// ── Envelope safety (SR-1) ───────────────────────────────────────────

/// A VM whose `azlin-session` tag is a JSON-breaking string.
///
/// Azure resource tags are writable by anyone holding Contributor on the
/// resource group, who is not necessarily the person running `azlin list`.
/// So every tag value is untrusted input that reaches a JSON document another
/// program parses.
fn vm_with_hostile_session_tag(session: &str) -> String {
    format!(
        r#"[{{
          "name": "azt1",
          "resourceGroup": "rysweet-linux-vm-pool",
          "location": "eastus",
          "powerState": "VM running",
          "provisioningState": "Succeeded",
          "hardwareProfile": {{ "vmSize": "Standard_D4s_v3" }},
          "storageProfile": {{
            "osDisk": {{ "osType": "Linux" }},
            "imageReference": {{ "offer": "ubuntu-24_04-lts" }}
          }},
          "osProfile": {{ "adminUsername": "azureuser" }},
          "publicIps": "",
          "privateIps": "10.0.0.1",
          "tags": {{ "azlin-session": {} }}
        }}]"#,
        serde_json::Value::String(session.to_string())
    )
}

/// The envelope must be built as one `serde_json::Value` and serialised once --
/// never by `format!`-ing a pre-serialised array into a string template.
///
/// The `filters` object added by #1142 holds only integers, so it cannot be
/// forged. The surface that *can* is the one that was always there: `session`
/// carries a tenant-controlled tag value straight into the payload. This test
/// pins that a value chosen to close the string and open a sibling key stays a
/// single opaque string -- so a future refactor that reaches for string
/// concatenation to bolt metadata onto the envelope fails here rather than in
/// somebody's automation.
#[test]
fn hostile_tag_value_cannot_forge_json_structure() {
    // Closes `"session": "`, opens a fake `injected` key, and leaves the
    // document balanced if -- and only if -- the value was not escaped.
    const HOSTILE: &str = r#"a","injected":"x"#;

    let sandbox = Sandbox::new(&vm_with_hostile_session_tag(HOSTILE));
    let (stdout, _stderr, code) = sandbox.run(&formatted_list_args("json"));
    assert_eq!(code, 0, "json list should succeed: {stdout}");

    let payload: serde_json::Value = serde_json::from_str(&stdout)
        .unwrap_or_else(|e| panic!("stdout must still be valid JSON ({e}): {stdout}"));

    let vms = payload["vms"]
        .as_array()
        .unwrap_or_else(|| panic!("payload must have a `vms` array: {stdout}"));
    assert_eq!(vms.len(), 1, "{stdout}");

    let vm = vms[0].as_object().expect("VM entry must be an object");
    assert_eq!(
        vm["session"], HOSTILE,
        "the tag value must survive as one literal string: {stdout}"
    );
    assert!(
        !vm.contains_key("injected"),
        "a tag value must not be able to add a key: {stdout}"
    );

    // And it must not have escaped into the result-level metadata either.
    let filters = payload["filters"]
        .as_object()
        .unwrap_or_else(|| panic!("payload must have a `filters` object: {stdout}"));
    assert_eq!(
        filters.len(),
        3,
        "`filters` carries exactly three integer counts: {stdout}"
    );
    for (key, value) in filters {
        assert!(
            value.is_u64(),
            "`filters.{key}` must be an integer, never a caller-controlled string: {stdout}"
        );
    }
    assert_eq!(
        payload.as_object().map(serde_json::Map::len),
        Some(2),
        "the envelope has exactly `vms` and `filters`: {stdout}"
    );
}
