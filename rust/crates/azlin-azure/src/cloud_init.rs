/// Validate a cloud-init input string against YAML injection.
///
/// Rejects values containing newlines or YAML special sequences that could
/// break the document structure.
fn validate_cloud_init_input(value: &str, field_name: &str) -> std::result::Result<(), String> {
    if value.contains('\n') || value.contains('\r') {
        return Err(format!(
            "{field_name} must not contain newlines (possible YAML injection)"
        ));
    }
    // Block YAML directives and document markers
    if value.starts_with("---") || value.starts_with("...") {
        return Err(format!("{field_name} contains YAML special sequences"));
    }
    Ok(())
}

/// YAML-safe quoting: wrap value in single quotes, escaping internal single
/// quotes by doubling them (YAML 1.1 spec).
fn yaml_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "''"))
}

fn append_runcmd_entry(yaml: &mut String, cmd: &str) {
    if cmd.contains('\n') || cmd.contains('\r') {
        let normalized = cmd.replace("\r\n", "\n").replace('\r', "\n");
        yaml.push_str("  - |\n");
        for line in normalized.lines() {
            yaml.push_str("    ");
            yaml.push_str(line);
            yaml.push('\n');
        }
    } else if validate_cloud_init_input(cmd, "setup_command").is_ok() {
        // YAML-quote each single-line command to prevent injection via special chars.
        yaml.push_str(&format!("  - {}\n", yaml_quote(cmd)));
    }
}

/// The admin username as it is safe to interpolate, or `azureuser`.
///
/// `char::is_alphanumeric` is a **Unicode** predicate: it accepts `Ω`, `𝟙` and
/// every other letter or digit in the standard, none of which `useradd` will
/// take and several of which normalise to something else on the way to the VM.
/// The rule that matters here is the POSIX one, so this asks for ASCII.
///
/// The fallback is deliberate and stays. Cloud-init cannot fail closed: a
/// rejected username means a VM that boots with no account on it and no way in.
/// `azlin disk repair` faces the same question with the opposite right answer —
/// see `disk_layout::checked_username`, which rejects, because repairing
/// `azureuser`'s home when the caller named someone else would bind the wrong
/// directory over the wrong path.
fn sanitize_admin_username(username: &str) -> &str {
    if !username.is_empty()
        && username
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        username
    } else {
        "azureuser"
    }
}

/// Generate cloud-init YAML for VM provisioning.
///
/// All inputs are validated against YAML injection. Usernames must be
/// alphanumeric (plus hyphens/underscores). SSH keys and commands are
/// YAML-quoted to prevent injection.
pub fn generate_cloud_init(
    username: &str,
    ssh_public_key: &str,
    packages: &[&str],
    setup_commands: &[String],
) -> String {
    // One username rule, in `sanitize_admin_username`. This used to be a second
    // copy of it, and the two had already drifted: the copy accepted an empty
    // name and emitted `users:\n  - name:` — valid YAML, no account.
    let username = sanitize_admin_username(username);

    // Validate SSH key (no newlines)
    if validate_cloud_init_input(ssh_public_key, "ssh_public_key").is_err() {
        return String::from(
            "#cloud-config\n# ERROR: invalid ssh_public_key (rejected for safety)\n",
        );
    }

    let mut yaml = String::with_capacity(512);
    yaml.push_str("#cloud-config\n");
    yaml.push_str(&format!("users:\n  - name: {}\n", username));
    yaml.push_str("    groups: sudo, docker\n");
    yaml.push_str("    shell: /bin/bash\n");
    yaml.push_str("    sudo: ALL=(ALL) NOPASSWD:ALL\n");
    yaml.push_str("    ssh_authorized_keys:\n");
    yaml.push_str(&format!("      - {}\n", ssh_public_key));

    if !packages.is_empty() {
        yaml.push_str("\npackage_update: true\npackage_upgrade: true\npackages:\n");
        for pkg in packages {
            // Package names: ASCII alphanumeric, hyphens, dots, plus signs.
            //
            // ASCII for the same reason the username is: `char::is_alphanumeric`
            // is the Unicode predicate and accepts letters and digits from every
            // script in the standard. Debian package names are `[a-z0-9.+-]`, so
            // a name this let through is one `apt` will reject anyway -- after
            // the section it is in has already been recorded `failed`.
            if pkg
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '.' || c == '+')
            {
                yaml.push_str(&format!("  - {}\n", pkg));
            }
        }
    }

    if !setup_commands.is_empty() {
        yaml.push_str("\nruncmd:\n");
        for cmd in setup_commands {
            append_runcmd_entry(&mut yaml, cmd);
        }
    }

    yaml
}

/// Disk configuration for cloud-init provisioning.
#[derive(Debug, Clone, Default)]
pub struct DiskConfig {
    /// If true, a home disk is attached. Its filesystem is mounted at
    /// `/mnt/home-data` and `/mnt/home-data/{user}` is bind-mounted at
    /// `/home/{user}`; nothing is ever mounted on `/home` directly. See
    /// `disk_layout`.
    pub home_disk: bool,
    /// If true, a tmp disk is attached, mounted at `/mnt/tmp-data` with
    /// `/mnt/tmp-data/tmp` bind-mounted at `/tmp`. LUNs are assigned in attach
    /// order, so this is LUN 0 when there is no home disk. See `disk_layout`.
    pub tmp_disk: bool,
}

/// Shell snippet: wait for an Azure LUN device to appear (udevadm + retry loop).
/// Returns a script fragment that sets `$DEV_VAR` to the resolved block device path.
///
/// The device path is derived from the LUN here rather than passed alongside
/// it: two parameters that must agree are two parameters that can disagree.
fn lun_wait_snippet(lun: u32, dev_var: &str, label: &str) -> String {
    let device = crate::disk_layout::lun_device_path(lun);
    format!(
        r#"  # Wait for udev to finish processing device events
  udevadm settle --timeout=30 || true

  # Retry loop: poll for LUN device availability (12 retries x 5s = 60s max)
  {dev_var}=""
  for retry in $(seq 1 12); do
    {dev_var}=$(readlink -f {device} 2>/dev/null) || true
    if [ -n "${dev_var}" ] && [ -b "${dev_var}" ]; then
      break
    fi
    echo "[AZLIN] Waiting for {label} disk LUN {lun} (attempt $retry/12)..."
    sleep 5
  done

  if [ -z "${dev_var}" ] || [ ! -b "${dev_var}" ]; then
    echo "WARNING: {label} disk at LUN {lun} not found after 60s"
    exit 1
  fi"#,
        lun = lun,
        dev_var = dev_var,
        label = label,
        device = device,
    )
}

pub fn render_dev_cloud_init_script(admin_username: &str) -> String {
    render_dev_cloud_init_script_with_disks(admin_username, &DiskConfig::default())
}

/// One failure-isolated section of the generated provisioning script.
struct Section {
    /// Ledger key. Printed back by `azlin disk check`, so it is a contract —
    /// see `docs-site/storage/data-disk-layout.md`.
    name: String,
    /// The commands, emitted verbatim inside the section's subshell.
    body: String,
    /// Whether the section needs the package archive to be reachable. Those
    /// are skipped, not run and failed, when it demonstrably is not.
    needs_network: bool,
}

/// The preamble: the ledger writer, the storage summary, and the terminal
/// state that runs on every path.
///
/// `set -euo pipefail` stays the file default. Critical work still fails fast
/// at its first error; only the section boundaries are permeable, and each one
/// records what happened.
fn provisioning_preamble() -> String {
    let backings = crate::disk_layout::all_backing_paths().join(" ");
    let body = r#"#!/bin/bash
set -euo pipefail

mkdir -p /var/lib/azlin
# Readable by everyone, writable by root. `azlin disk check` reads the ledger
# over SSH as the admin user, and the mode is stated rather than inherited from
# whatever umask cloud-init happens to run under.
chmod 755 /var/lib/azlin

# The ledger describes *this* run, so it starts empty.
#
# Appending to whatever was there before would let a `failed` row from an
# earlier boot pin the VM at `degraded` forever, with no way to clear it short
# of deleting the file by hand.
: > /var/lib/azlin/provisioning.tsv

# Record one section's outcome.
#
# $2 is a numeric exit status, or the literal `skipped` for a section whose
# dependency failed. A `[ "$2" = 0 ]` test alone would render `skipped` as
# `failed`, and "the archive was unreachable" is not the same report as "this
# step is broken".
azlin_record() {
  azlin_status=failed
  case "$2" in
    0) azlin_status=ok ;;
    skipped) azlin_status=skipped ;;
  esac
  printf '%s\t%s\t%s\n' "$1" "$azlin_status" "$2" >> /var/lib/azlin/provisioning.tsv
  echo "[AZLIN] section=$1 status=$azlin_status rc=$2"
}

# The azlin data-disk backing mounts, reported unconditionally so
# /var/log/cloud-init-output.log records the storage the VM actually came up
# with. A VM with no data disks shows both as absent, which is the answer to
# "where did my /home go". `fstab=no` on a mounted backing path means the mount
# is live now and will not survive a reboot.
azlin_storage_summary() {
  for azlin_backing in __AZLIN_BACKINGS__; do
    if mountpoint -q "$azlin_backing" 2>/dev/null; then
      azlin_persisted=no
      if grep -qs " $azlin_backing " /etc/fstab; then azlin_persisted=yes; fi
      echo "[AZLIN] storage: $azlin_backing mounted, fstab=$azlin_persisted"
    else
      echo "[AZLIN] storage: $azlin_backing absent"
    fi
  done
}

# Terminal state, written on every path.
#
# #1131 left the VM with no terminal state at all: the script died mid-way, the
# sentinel was never written, and readiness checks had nothing to read. Both
# files are written here, from an EXIT trap, so even an unhandled failure
# outside a section reaches a terminal state -- a degraded one.
azlin_finalize() {
  azlin_exit=$?
  azlin_storage_summary
  # `ok` has to be *earned*: the ledger must exist, hold no failed row, and the
  # shell must be on its way out cleanly. Defaulting to `ok` and downgrading
  # only on a failed row would report success for a run that died before it
  # wrote anything -- which is the failure this whole change exists to stop.
  azlin_final=degraded
  if [ "$azlin_exit" -eq 0 ] && [ -f /var/lib/azlin/provisioning.tsv ] \
     && ! awk -F'\t' '$2=="failed"{f=1} END{exit !f}' /var/lib/azlin/provisioning.tsv; then
    azlin_final=ok
  fi
  printf '%s\n' "$azlin_final" > /var/lib/azlin/provisioning-status
  : > /var/lib/azlin/provisioning-complete
  echo "[AZLIN] provisioning finished: status=$azlin_final"
}
trap azlin_finalize EXIT

"#;
    body.replace("__AZLIN_BACKINGS__", &backings)
}

/// Wrap one section so its failure cannot end the script, without making the
/// section itself permissive.
///
/// ```sh
/// rc=0
/// set +e
/// (
///   set -e
///   …
/// )
/// rc=$?
/// set -e
/// ```
///
/// Every part of that is load-bearing, and the obvious shorter spelling is
/// wrong in a way that is invisible by inspection:
///
/// `( … ) || rc=$?` reads as "run the group under `set -e`, capture its
/// status". It is not. POSIX suspends `errexit` for *any* command that is an
/// operand of `&&` or `||`, and bash propagates that suspension into the
/// subshell — so the body runs straight past its first failing command and
/// `$rc` ends up as the status of the body's **last** command. Every disk
/// section ends in `echo`, so every section would have been recorded `ok` no
/// matter what failed inside it. Re-declaring `set -e` at the top of the
/// subshell does not help either; the suspension is a property of the context,
/// not of the option. Verified in bash 5.3 and in dash.
///
/// The consequence was not cosmetic: a failed `mount` would have been followed
/// by the copy, the `mv`, the bind over the OS-disk directory, and finally
/// `rm -rf /home/<user>.old` — deleting the original — with the ledger
/// reporting `ok`. `set +e` at the *boundary* with `set -e` restored *inside*
/// the group is the form that both stops the body at its first failure and
/// keeps that failure from ending the script.
///
/// `rc=0` before the group keeps `$rc` defined under `set -u` on the branch
/// where the group is skipped.
fn render_section(section: &Section) -> String {
    let Section {
        name,
        body,
        needs_network,
    } = section;
    let mut out = format!("# ---- section: {name} ----\nrc=0\n");
    if *needs_network {
        out.push_str(&format!(
            "if [ \"$AZLIN_ARCHIVE\" = down ]; then\n  azlin_record {name} skipped\nelse\n"
        ));
    }
    out.push_str("set +e\n(\n  set -e\n");
    out.push_str(body.trim_end());
    out.push_str(&format!(
        "\n)\nrc=$?\nset -e\nazlin_record {name} \"$rc\"\n"
    ));
    if *needs_network {
        out.push_str("fi\n");
    }
    out.push('\n');
    out
}

/// The disk sections, which run before anything that touches the network.
///
/// Every layout fact here comes from `disk_layout` — see the drift rule in that
/// module's header for why none of them is spelled locally.
///
/// The two procedures stay distinct, because they genuinely are: the home block
/// makes a mandatory, verified copy and can roll back, and the tmp block sets a
/// sticky bit and treats its copy as disposable.
fn disk_sections(disk_config: &DiskConfig, user: &str) -> Vec<Section> {
    use crate::disk_layout::{bind_pair, fstab_line, roles, BindKind, FstabSpec};

    roles(disk_config)
        .into_iter()
        .map(|role| {
            let (bind_src, bind_dst) = bind_pair(&role, user);
            let uuid_var = format!("{}_UUID", role.name.to_uppercase());
            let dev_var = format!("{}_DEV", role.name.to_uppercase());
            let ext4 = fstab_line(&FstabSpec::Ext4ByUuid {
                uuid_expr: format!("${uuid_var}"),
                target: role.backing.to_string(),
            });
            let bind = fstab_line(&FstabSpec::Bind {
                source: bind_src.clone(),
                target: bind_dst.clone(),
            });
            let wait = lun_wait_snippet(role.lun, &dev_var, role.name);

            let body = match role.bind_kind {
                BindKind::UserHome => format!(
                    r#"  # Home disk (LUN {lun})
{wait}

  mkfs.ext4 -F -L {label} "${dev_var}"
  mkdir -p {backing}
  mount "${dev_var}" {backing}
  mkdir -p {src}
  # Copy the existing home to the new disk.
  #
  # `rsync` is in default_dev_packages(), not in the Azure Ubuntu base image,
  # and this block now runs *before* apt -- so the tool is chosen at runtime.
  # `cp -a` (= `-dR --preserve=all`) is in coreutils and covers the same
  # xattr/ACL intent. Neither is suppressed: a silently skipped copy would bind
  # an empty directory over the user's home.
  if command -v rsync > /dev/null 2>&1; then
    rsync -aAX {dst}/ {src}/
  else
    cp -a {dst}/. {src}/
  fi
  # Bind mount over {dst} -- with rollback trap to restore original on failure
  mv {dst} {dst}.old
  trap 'if [ -d {dst}.old ] && ! mountpoint -q {dst} 2>/dev/null; then rm -rf {dst}; mv {dst}.old {dst}; echo "[AZLIN] Rolled back {dst} after disk setup failure"; fi' EXIT
  mkdir -p {dst}
  mount --bind {src} {dst}
  # A `mount` that returns 0 without producing a mountpoint would leave the
  # user's home an empty directory on the OS disk with their data in `.old`,
  # and the rest of the block would still record the section `ok`. Fail here
  # instead, and let the trap above put the original back.
  if ! mountpoint -q {dst}; then
    echo "WARNING: the bind mount over {dst} did not take"
    exit 1
  fi
  chown {u}:{u} {src}
  # Persist in fstab (idempotent)
  {uuid_var}=$(blkid -s UUID -o value "${dev_var}")
  grep -q "UUID=${uuid_var}" /etc/fstab || echo "{ext4}" >> /etc/fstab
  grep -q "{src} {dst}" /etc/fstab || echo "{bind}" >> /etc/fstab
  # Only now is the copy on the OS disk expendable. Until fstab is written the
  # mount does not survive a reboot, so a failure anywhere above this line must
  # leave the original where the operator can still find it.
  rm -rf {dst}.old
  echo "[AZLIN] Home disk mounted at {dst} ($(lsblk -no SIZE "${dev_var}" | tr -d ' '))""#,
                    lun = role.lun,
                    wait = wait,
                    label = role.fs_label,
                    dev_var = dev_var,
                    uuid_var = uuid_var,
                    backing = role.backing,
                    src = bind_src,
                    dst = bind_dst,
                    u = user,
                    ext4 = ext4,
                    bind = bind,
                ),
                BindKind::Tmp => format!(
                    r#"  # Tmp disk (LUN {lun})
{wait}

  mkfs.ext4 -F -L {label} "${dev_var}"
  mkdir -p {backing}
  mount "${dev_var}" {backing}
  mkdir -p {src}
  # The sticky bit goes on the *backing* directory. A boot mounts that
  # directory over {dst}, so {dst} shows whatever mode it carries; a `chmod 1777
  # {dst}` afterwards reaches the same inode through the bind and looks correct
  # until the next reboot brings {dst} up unwritable.
  chmod 1777 {src}
  # {dst} contents are disposable, so unlike the home copy this one is
  # best-effort by design.
  {{ if command -v rsync > /dev/null 2>&1; then rsync -aAX {dst}/ {src}/; else cp -a {dst}/. {src}/; fi ; }} || true
  mount --bind {src} {dst}
  # Same reason as the home block: a bind that did not take must fail the
  # section rather than be recorded `ok` with {dst} still on the OS disk.
  if ! mountpoint -q {dst}; then
    echo "WARNING: the bind mount over {dst} did not take"
    exit 1
  fi
  # Persist in fstab (idempotent)
  {uuid_var}=$(blkid -s UUID -o value "${dev_var}")
  grep -q "UUID=${uuid_var}" /etc/fstab || echo "{ext4}" >> /etc/fstab
  grep -q "{src} {dst}" /etc/fstab || echo "{bind}" >> /etc/fstab
  echo "[AZLIN] Tmp disk mounted at {dst} ($(lsblk -no SIZE "${dev_var}" | tr -d ' '))""#,
                    lun = role.lun,
                    wait = wait,
                    label = role.fs_label,
                    dev_var = dev_var,
                    uuid_var = uuid_var,
                    backing = role.backing,
                    src = bind_src,
                    dst = bind_dst,
                    ext4 = ext4,
                    bind = bind,
                ),
            };

            Section {
                name: format!("disk-{}", role.name),
                needs_network: false,
                body,
            }
        })
        .collect()
}

/// Render the dev cloud-init shell script with optional data disk setup.
///
/// Two properties of the ordering here are the fix for issue #1131, and both
/// are asserted by `tests/cloud_init_failure_isolation.rs`:
///
/// 1. **Disk setup is emitted first.** It needs `udevadm`, `mkfs.ext4`, `blkid`
///    and `mount` -- all in the Azure Ubuntu base image -- and no network at
///    all. Package installation needs the archive, which on a bastion-only VM
///    with no outbound route is unreachable. Sequencing the step that cannot
///    fail for network reasons behind the step that can is what left VMs with
///    attached, unformatted disks for weeks.
/// 2. **Every section is failure-isolated and recorded.** Ordering alone only
///    protects whatever happens to be first; a missing `tree` package must not
///    be able to abort filesystem provisioning no matter where it sits.
pub fn render_dev_cloud_init_script_with_disks(
    admin_username: &str,
    disk_config: &DiskConfig,
) -> String {
    let safe_username = sanitize_admin_username(admin_username);
    let packages = default_dev_packages();

    // Pre-allocate ~24KB for the generated script to avoid repeated reallocations
    let mut script = String::with_capacity(24 * 1024);
    script.push_str(&provisioning_preamble());

    if disk_config.home_disk || disk_config.tmp_disk {
        script.push_str("echo '[AZLIN] Formatting and mounting data disks...'\n\n");
    }
    for section in disk_sections(disk_config, safe_username) {
        script.push_str(&render_section(&section));
    }

    script.push_str(&render_section(&Section {
        name: "apt-update".to_string(),
        needs_network: false,
        body: "  apt-get update -qq".to_string(),
    }));
    script.push_str("AZLIN_APT_UPDATE_RC=$rc\n\n");

    script.push_str(&render_section(&Section {
        name: "apt-upgrade".to_string(),
        needs_network: false,
        body: "  apt-get upgrade -y -qq".to_string(),
    }));

    let mut install = String::from("  apt-get install -y -qq \\\n");
    for (idx, package) in packages.iter().enumerate() {
        install.push_str("    ");
        install.push_str(package);
        if idx + 1 != packages.len() {
            install.push_str(" \\\n");
        }
    }
    script.push_str(&render_section(&Section {
        name: "apt-install".to_string(),
        needs_network: false,
        body: install,
    }));

    // The gate for the toolchain sections below.
    //
    // Two signals, not one: `apt-get update` fails whenever any configured
    // source is unreachable, and `apt-get install` fails when a single package
    // name is missing from an otherwise healthy archive. Either alone would
    // misfire. Both failing is the archive being unreachable -- and then every
    // `curl https://...` below would spend its own timeout failing the same
    // way, which is how #1131's VM spent its provisioning window.
    script.push_str("AZLIN_APT_INSTALL_RC=$rc\n\n");
    script.push_str(
        "AZLIN_ARCHIVE=up\n\
         if [ \"$AZLIN_APT_UPDATE_RC\" -ne 0 ] && [ \"$AZLIN_APT_INSTALL_RC\" -ne 0 ]; then\n  \
           AZLIN_ARCHIVE=down\n  \
           echo '[AZLIN] the package archive is unreachable; skipping the \
network-dependent toolchain sections'\n\
         fi\n\n",
    );

    for section in dev_setup_sections(safe_username) {
        script.push_str(&render_section(&section));
    }

    // Provisioning is finished, and the terminal state is written by the EXIT
    // trap. Exiting 0 even from a degraded run is deliberate: a non-zero exit
    // here produces a `Failed to run module scripts_user` line buried in
    // /var/log/cloud-init-output.log, which is exactly the channel that failed
    // to tell anyone about #1131 for weeks. `provisioning-status`, the
    // `Storage` column and `azlin disk check` are the channels that work.
    script.push_str("exit 0\n");

    script
}

/// `cmd`, but a failure prints `message` and still fails.
///
/// The steps below used to end in `|| echo 'WARNING: … failed'`, which was the
/// only way to report a failure while keeping `set -euo pipefail` from ending
/// the whole script. Now that each section is isolated and its exit status is
/// recorded in the ledger, that suffix would actively hide the failure: it
/// turns a non-zero status into zero, and the section would be recorded `ok`.
/// This keeps the message and keeps the status.
fn warn_and_fail(cmd: &str, message: &str) -> String {
    format!("{cmd} || {{ echo 'WARNING: {message}' >&2; false; }}")
}

/// Default setup commands for development VMs, in execution order.
///
/// These install toolchains that aren't available as apt packages, matching
/// the full Python azlin provisioning (gh, az, node, claude, rust, go, .NET).
fn dev_setup_sections(username: &str) -> Vec<Section> {
    let u = username;
    vec![
        // Python 3.14 - install via deadsnakes but do NOT change system python3
        Section {
            name: "setup-python314".to_string(),
            needs_network: true,
            body: "if python3.14 --version 2>/dev/null; then echo 'Python 3.14 available'; else add-apt-repository -y ppa:deadsnakes/ppa && apt update && apt install -y python3.14 python3.14-venv python3.14-dev; fi".to_string(),
        },
        Section {
            name: "setup-github-cli".to_string(),
            needs_network: true,
            body: warn_and_fail(
                "mkdir -p -m 755 /etc/apt/keyrings && wget -nv -O /etc/apt/keyrings/githubcli-archive-keyring.gpg https://cli.github.com/packages/githubcli-archive-keyring.gpg && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && mkdir -p -m 755 /etc/apt/sources.list.d && echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && apt update && apt install -y gh",
                "GitHub CLI install failed",
            ),
        },
        // Azure CLI.
        //
        // Not `curl -sL https://aka.ms/InstallAzureCLIDeb | bash`. That script
        // derives its apt dist from `lsb_release -cs` and 404s on any codename
        // Microsoft has not published. Ubuntu 26.04 ("resolute") is not
        // published -- only up to "noble" is -- so on 26.04 it simply fails.
        //
        // Worse, it failed *silently*: in a `curl ... | bash` pipeline the exit
        // status is bash's, so a failed download still exits 0, and `-s`
        // suppressed curl's error. Provisioning reported success on a VM with
        // no `az` installed and nothing in cloud-init-output.log to say so.
        //
        // Install from the repo directly instead: use the running codename when
        // Microsoft publishes it, fall back to the newest published LTS when
        // they do not, and report failure either way.
        Section {
            name: "setup-azure-cli".to_string(),
            needs_network: true,
            body: warn_and_fail(
                r#"AZ_DIST=$(lsb_release -cs) && if ! curl -fsSL "https://packages.microsoft.com/repos/azure-cli/dists/$AZ_DIST/Release" >/dev/null 2>&1; then echo "NOTE: azure-cli has no apt dist for '$AZ_DIST'; falling back to noble"; AZ_DIST=noble; fi && mkdir -p -m 755 /etc/apt/keyrings && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg && chmod go+r /etc/apt/keyrings/microsoft.gpg && mkdir -p -m 755 /etc/apt/sources.list.d && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/azure-cli/ $AZ_DIST main" > /etc/apt/sources.list.d/azure-cli.list && apt-get update && apt-get install -y azure-cli"#,
                "Azure CLI install failed",
            ),
        },
        // Chromium (Ubuntu ships this as a snap-backed launcher)
        Section {
            name: "setup-chromium".to_string(),
            needs_network: true,
            body: "apt-get install -y chromium-browser".to_string(),
        },
        // Chromium wrappers so SSH/X11 launches use a scoped user session instead of
        // failing with the snap cgroup error.
        Section {
            name: "setup-chromium-wrappers".to_string(),
            needs_network: false,
            body: r#"mkdir -p /usr/local/bin
cat > /usr/local/bin/chromium-browser << 'CHROMIUMWRAP'
#!/bin/sh
set -eu

REAL_COMMAND=/usr/bin/chromium-browser
if [ ! -x "$REAL_COMMAND" ]; then
    REAL_COMMAND=/snap/bin/chromium
fi

if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi

if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -S "$XDG_RUNTIME_DIR/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
fi

if command -v snap >/dev/null 2>&1 && snap list chromium >/dev/null 2>&1; then
    if ! command -v systemd-run >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
        echo "Chromium requires systemd user scope support on this VM, but systemd tooling is unavailable." >&2
        exit 1
    fi
    if ! systemctl --user show-environment >/dev/null 2>&1; then
        echo "Chromium requires an active systemd user environment on this VM. Check linger/user-systemd setup." >&2
        exit 1
    fi
    exec systemd-run --user --scope --quiet -- "$REAL_COMMAND" "$@"
fi

exec "$REAL_COMMAND" "$@"
CHROMIUMWRAP
chmod 755 /usr/local/bin/chromium-browser

cat > /usr/local/bin/chromium << 'CHROMIUMALIAS'
#!/bin/sh
exec /usr/local/bin/chromium-browser "$@"
CHROMIUMALIAS
chmod 755 /usr/local/bin/chromium"#.to_string(),
        },
        // astral-uv (uv package manager).
        //
        // `snap wait system seed.loaded` first: cloud-init's scripts-user stage
        // routinely runs while snapd is still seeding, and an install issued
        // then fails with "too early for operation, device not yet seeded".
        // That used to be absorbed by a trailing `|| true`, which now would
        // record the section `ok` regardless. Waiting removes the race instead
        // of hiding it, and a genuine failure is reported.
        Section {
            name: "setup-astral-uv".to_string(),
            needs_network: true,
            body: "snap wait system seed.loaded && snap install astral-uv --classic".to_string(),
        },
        // Node.js 24 LTS (via NodeSource)
        Section {
            name: "setup-nodejs".to_string(),
            needs_network: true,
            body: warn_and_fail(
                "curl -fsSL https://deb.nodesource.com/setup_24.x | bash - && apt install -y nodejs",
                "Node.js install failed",
            ),
        },
        // npm user-local configuration
        Section {
            name: "setup-npm-prefix".to_string(),
            needs_network: false,
            body: format!("mkdir -p /home/{u}/.npm-packages && echo 'prefix=${{HOME}}/.npm-packages' > /home/{u}/.npmrc && chown {u}:{u} /home/{u}/.npmrc /home/{u}/.npm-packages"),
        },
        // Tmux configuration
        Section {
            name: "setup-tmux-conf".to_string(),
            needs_network: false,
            // `%` needs no escaping in a Rust format string. The doubled
            // `%%` that used to be here reached the VM verbatim, where shell
            // `printf` reads `%%` as a literal percent and discards its
            // arguments -- the log line printed `[%s] %s`, and tmux rendered a
            // literal `%Y-%m-%d %H:%M` in every VM's status bar.
            body: format!("printf '[%s] %s\\n' \"$(hostname)\" \"tmux.conf\" && cat > /home/{u}/.tmux.conf << 'TMUXEOF'\nset -g status-left-length 50\nset -g status-left \"#[fg=cyan][#h]#[fg=green] #S #[fg=yellow]| \"\nset -g status-right \"#[fg=cyan]%Y-%m-%d %H:%M\"\nset -g status-interval 60\nset -g status-bg black\nset -g status-fg white\nTMUXEOF\nchown {u}:{u} /home/{u}/.tmux.conf"),
        },
        // Fix tmux socket dir permissions (Ubuntu 25.10+).
        //
        // `chmod 1777 /tmp` here is on the live mount and is correct for the
        // running boot; the mode that survives a reboot is the one the tmp
        // disk section set on /mnt/tmp-data/tmp.
        Section {
            name: "setup-tmux-socket".to_string(),
            needs_network: false,
            body: format!("chmod 1777 /tmp && TMUX_UID=$(id -u {u}) && mkdir -p /tmp/tmux-$TMUX_UID && chmod 700 /tmp/tmux-$TMUX_UID && chown {u}:{u} /tmp/tmux-$TMUX_UID"),
        },
        // Claude Code AI Assistant.
        //
        // This is a required tool for an azlin development VM. Like every other
        // section its failure is isolated so later sections can record their
        // own outcomes, but the failed ledger row makes the terminal
        // provisioning status `degraded`.
        //
        // Anthropic's installer is a Bash program (it uses arrays), so invoking
        // it through Ubuntu's /bin/sh (dash) fails before installation starts.
        // Download, then execute. NOT `curl ... | bash` inside `su -c`: the
        // generated script sets `pipefail`, but that is a per-shell option and
        // the fresh login shell `su -` starts does not inherit it. Verified:
        // `bash -c 'set -o pipefail; bash -c "false | true; echo $?"'` prints 0.
        // So a failed download would leave bash reading empty stdin, exiting 0,
        // and the failure report below would never fire -- #1069 one level
        // deeper.
        Section {
            name: "setup-claude-code".to_string(),
            needs_network: true,
            body: warn_and_fail(
                &format!("su - {u} -c 'curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh && bash /tmp/claude-install.sh; rc=$?; rm -f /tmp/claude-install.sh; exit $rc'"),
                "Claude Code installation failed",
            ),
        },
        // Rust. rustup's installer is deliberately invoked with `sh`: unlike
        // Anthropic's installer, https://sh.rustup.rs is POSIX-sh compatible
        // (`dash -n` succeeds).
        // Download, then execute -- same `su -c` pipefail reasoning as above.
        Section {
            name: "setup-rust".to_string(),
            needs_network: true,
            body: warn_and_fail(
                &format!("su - {u} -c 'curl --proto =https --tlsv1.2 -fsSf https://sh.rustup.rs -o /tmp/rustup-init.sh && sh /tmp/rustup-init.sh -y; rc=$?; rm -f /tmp/rustup-init.sh; exit $rc'"),
                "Rust install failed",
            ),
        },
        // amplihack-rs (pre-built binary from latest GitHub release)
        Section {
            name: "setup-amplihack".to_string(),
            needs_network: true,
            body: warn_and_fail(
                &format!("su - {u} -c 'ARCH=$(uname -m | sed s/aarch64/aarch64/ | sed s/x86_64/x86_64/) && \
            URL=$(curl -fsSL https://api.github.com/repos/rysweet/amplihack-rs/releases/latest | grep browser_download_url | grep $ARCH-unknown-linux-gnu.tar.gz\\\" | head -1 | cut -d\\\"  -f4) && \
            mkdir -p /tmp/amplihack-install && cd /tmp/amplihack-install && \
            curl -fsSL $URL -o amplihack.tar.gz && tar xzf amplihack.tar.gz && \
            mkdir -p ~/.cargo/bin && cp amplihack amplihack-hooks ~/.cargo/bin/ && \
            chmod +x ~/.cargo/bin/amplihack ~/.cargo/bin/amplihack-hooks && \
            cd ~ && rm -rf /tmp/amplihack-install && \
            ~/.cargo/bin/amplihack install'"),
                "amplihack-rs installation failed",
            ),
        },
        // azlin CLI (pre-built binary from latest GitHub release).
        // Release archives ship platform-suffixed members (azlin-linux-x86_64,
        // azdoit-linux-x86_64, ay-linux-x86_64), so each is renamed on copy.
        Section {
            name: "setup-azlin-cli".to_string(),
            needs_network: true,
            body: warn_and_fail(
                &format!("su - {u} -c 'ARCH=$(uname -m | sed s/aarch64/aarch64/ | sed s/x86_64/x86_64/) && \
            URL=$(curl -fsSL https://api.github.com/repos/rysweet/azlin/releases/latest | grep browser_download_url | grep linux-$ARCH.tar.gz\\\" | head -1 | cut -d\\\"  -f4) && \
            mkdir -p /tmp/azlin-install && cd /tmp/azlin-install && \
            curl -fsSL $URL -o azlin.tar.gz && tar xzf azlin.tar.gz && \
            mkdir -p ~/.cargo/bin && \
            cp azlin-linux-$ARCH ~/.cargo/bin/azlin && \
            cp azdoit-linux-$ARCH ~/.cargo/bin/azdoit && \
            cp ay-linux-$ARCH ~/.cargo/bin/ay && \
            chmod +x ~/.cargo/bin/azlin ~/.cargo/bin/azdoit ~/.cargo/bin/ay && \
            cd ~ && rm -rf /tmp/azlin-install'"),
                "azlin binary installation failed (azlin/azdoit/ay)",
            ),
        },
        // Put the installed CLIs on the default PATH.
        //
        // The installers above drop binaries in ~/.cargo/bin, which is only added
        // to PATH by ~/.cargo/env sourced from .bashrc -- and bash skips .bashrc
        // for non-interactive shells. That made `ssh <vm> 'amplihack ...'`, cron
        // jobs and CI steps fail with "command not found" while an interactive
        // `azlin connect` session worked, which reads as a failed install (#1095).
        // /usr/local/bin is on the default PATH for every shell type, and linking
        // there also removes the dependency on rustup having created ~/.cargo/env.
        //
        // Each link is guarded by `[ -x ... ]`: a missing binary must produce a
        // WARNING, never a dangling symlink that makes `command -v` succeed while
        // running the command fails.
        Section {
            name: "setup-path-links".to_string(),
            needs_network: false,
            body: format!("mkdir -p /usr/local/bin && for b in amplihack amplihack-hooks azlin azdoit ay; do src=/home/{u}/.cargo/bin/$b; if [ -x \"$src\" ]; then ln -sf \"$src\" /usr/local/bin/$b || echo \"WARNING: could not link $b into /usr/local/bin; it will be missing from non-interactive shells\" >&2; else echo \"WARNING: $src is missing or not executable; $b will be missing from non-interactive shells\" >&2; fi; done"),
        },
        // Go
        Section {
            name: "setup-go".to_string(),
            needs_network: true,
            body: warn_and_fail(
                "wget -q https://go.dev/dl/go1.26.4.linux-amd64.tar.gz -O /tmp/go.tar.gz && tar -C /usr/local -xzf /tmp/go.tar.gz && rm /tmp/go.tar.gz",
                "Go install failed",
            ),
        },
        // .NET 10 SDK
        //
        // The `ln` is guarded by `[ -x ... ]` rather than chained off the
        // installer's exit status: the installer can exit 0 without leaving a
        // usable binary, and linking unconditionally left a dangling
        // /usr/local/bin/dotnet -- `command -v dotnet` succeeded, running it
        // did not. The guard's `else` branch fails the section, so a missing
        // SDK is recorded rather than merely mentioned.
        Section {
            name: "setup-dotnet".to_string(),
            needs_network: true,
            body: "curl -sSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && chmod +x /tmp/dotnet-install.sh && { /tmp/dotnet-install.sh --channel 10.0 --install-dir /usr/share/dotnet || echo 'WARNING: .NET 10 SDK install failed' >&2; }; rm -f /tmp/dotnet-install.sh; if [ -x /usr/share/dotnet/dotnet ]; then ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet; else echo 'WARNING: /usr/share/dotnet/dotnet is missing; not linking /usr/local/bin/dotnet' >&2; false; fi".to_string(),
        },
        // Docker post-install
        Section {
            name: "setup-docker-group".to_string(),
            needs_network: false,
            body: format!("usermod -aG docker {u} && systemctl enable docker && systemctl start docker"),
        },
        // Enable systemd user linger so SSH sessions get a systemd user instance
        // (required for snap Chromium cgroup scoping via systemd-run --user)
        Section {
            name: "setup-linger".to_string(),
            needs_network: false,
            body: format!("loginctl enable-linger {u}"),
        },
        // bashrc additions (npm path, go path, cargo env)
        Section {
            name: "setup-bashrc".to_string(),
            needs_network: false,
            body: format!("cat >> /home/{u}/.bashrc << 'BASHEOF'\n\n# npm user-local configuration\nNPM_PACKAGES=\"${{HOME}}/.npm-packages\"\nPATH=\"$NPM_PACKAGES/bin:$PATH\"\nMANPATH=\"$NPM_PACKAGES/share/man:$(manpath 2>/dev/null || echo $MANPATH)\"\n\n# Go\nexport PATH=$PATH:/usr/local/go/bin\n\n# Cargo\nsource $HOME/.cargo/env 2>/dev/null\nBASHEOF"),
        },
        // Non-interactive PATH check. The login-shell check below passes even when
        // the binaries only exist in ~/.cargo/bin, which is exactly how #1095 hid:
        // `azlin connect` worked, `ssh <vm> 'amplihack ...'` did not. `su` without
        // `-` gives a non-login, non-interactive shell -- the same environment ssh
        // commands, cron jobs and CI steps get.
        Section {
            name: "setup-path-check".to_string(),
            needs_network: false,
            body: format!("su {u} -s /bin/bash -c 'for b in amplihack amplihack-hooks azlin azdoit ay; do command -v $b > /dev/null || echo \"WARNING: $b is not on the default non-interactive PATH\" >&2; done'"),
        },
        // Version verification (rustc is in user homedir, must check as user).
        // All three azlin archive members are checked: the install chain is a
        // single `&&` sequence, so a member missing from a future tarball aborts
        // it *after* earlier binaries already landed. Checking only `azlin` would
        // let that pass silently. Note `ay` is a renamed copy of the `azlin`
        // binary (see .github/workflows/rust-release.yml), so `ay --version`
        // prints `azlin <version>`; this check proves `ay` is present and
        // executable, not that it is a distinct program.
        //
        // Its exit status is no longer discarded: this *is* the check that the
        // toolchains landed, and a section recorded `ok` after it failed would
        // be a verification that verifies nothing.
        //
        // Which is also why `az --version` is no longer piped into `head -2`.
        // The section runs under the file's `pipefail`, and `az` prints ~15
        // lines; `head` exiting after two leaves `az` to take SIGPIPE and exit
        // non-zero, failing the section on a VM where everything is installed.
        // The old trailing `|| true` hid that; nothing needs to now, because
        // the check only cares whether the command runs at all.
        Section {
            name: "setup-verify".to_string(),
            needs_network: false,
            body: format!("echo '[AZLIN] Verifying installed toolchains' && which gh && gh --version && which az && az --version > /dev/null && which node && node --version && su - {u} -c 'which claude && claude --version && which rustc && rustc --version && which amplihack && amplihack --version && which azlin && azlin --version && which azdoit && azdoit --version && which ay && ay --version' && which dotnet && dotnet --version"),
        },
    ]
}

/// The setup commands alone, in execution order.
///
/// The generator renders `dev_setup_sections` directly; this projection exists
/// only so the tests below can assert on a single step's command without
/// re-deriving the section wrapper around it.
#[cfg(test)]
fn default_dev_setup_commands(username: &str) -> Vec<String> {
    dev_setup_sections(username)
        .into_iter()
        .map(|s| s.body)
        .collect()
}

/// Default packages for development VMs (installed via apt).
/// Returns a static slice to avoid heap allocation on each call.
pub fn default_dev_packages() -> &'static [&'static str] {
    &[
        "docker.io",
        "git",
        "tmux",
        "curl",
        "wget",
        "build-essential",
        "make",
        "cmake",
        "software-properties-common",
        "ripgrep",
        "fd-find",
        "python3-pip",
        "pipx",
        "jq",
        "unzip",
        "xdg-utils",
        "htop",
        "tree",
        "vim",
    ]
}

#[cfg(test)]
mod tests {

    /// `char::is_alphanumeric` is the **Unicode** predicate.
    ///
    /// It accepts `Ω`, `𝟙`, Devanagari digits and every other letter or digit
    /// in the standard — none of which `useradd` will take, several of which
    /// normalise to something else on the way to the VM, and one class of which
    /// (the confusables) makes `azlin nеw --user admin` with a Cyrillic `е`
    /// indistinguishable by eye from the ASCII one. The rule that governs a
    /// POSIX account name is the ASCII rule, so that is the rule asked for.
    #[test]
    fn a_unicode_username_is_not_mistaken_for_an_alphanumeric_one() {
        for username in [
            "Ωmega",
            "admin\u{0435}",
            "\u{0660}\u{0661}",
            "user name",
            "u;rm -rf /",
            "",
        ] {
            assert_eq!(
                sanitize_admin_username(username),
                "azureuser",
                "{username:?} must fall back"
            );
        }
        for username in ["azureuser", "dev-1", "dev_1", "AzureUser2"] {
            assert_eq!(sanitize_admin_username(username), username);
        }
    }

    /// The fallback stays, and it is the opposite of what `azlin disk repair`
    /// does with the same question.
    ///
    /// Cloud-init cannot fail closed: a rejected username means a VM that boots
    /// with no account on it and no way in. `disk_layout::checked_username`
    /// rejects instead, because repairing `azureuser`'s home when the caller
    /// named someone else binds the wrong directory over the wrong path.
    #[test]
    fn a_bad_username_still_produces_a_usable_vm() {
        let yaml = generate_cloud_init("Ωmega", "ssh-ed25519 AAAA test", &[], &[]);
        assert!(yaml.contains("- name: azureuser"), "{yaml}");
        assert!(!yaml.contains("Ωmega"), "{yaml}");
    }

    /// One username rule, not two. The copy inside `generate_cloud_init`
    /// accepted an empty name and emitted `users:\n  - name:` — valid YAML,
    /// no account, no way in.
    #[test]
    fn an_empty_username_does_not_produce_a_vm_with_no_account() {
        let yaml = generate_cloud_init("", "ssh-ed25519 AAAA test", &[], &[]);
        assert!(yaml.contains("- name: azureuser"), "{yaml}");
        assert!(!yaml.contains("- name: \n"), "{yaml}");
    }

    /// A package name outside `[a-z0-9.+-]` is one `apt` would reject anyway.
    #[test]
    fn package_names_are_ascii_too() {
        let yaml = generate_cloud_init(
            "azureuser",
            "ssh-ed25519 AAAA test",
            &["build-essential", "libc++1", "gΩcc"],
            &[],
        );
        assert!(yaml.contains("- build-essential"), "{yaml}");
        assert!(yaml.contains("- libc++1"), "{yaml}");
        assert!(!yaml.contains("gΩcc"), "{yaml}");
    }

    /// The mode on the directory the ledger lives in is stated, not inherited.
    ///
    /// `azlin disk check` reads `/var/lib/azlin/*` over SSH as the admin user,
    /// so it has to be traversable; relying on whatever umask cloud-init
    /// happens to run under is how that becomes a probe returning `unknown` for
    /// reasons nobody can see.
    #[test]
    fn the_provisioning_state_directory_has_an_explicit_mode() {
        let script = render_dev_cloud_init_script("azureuser");
        let mkdir = script.find("mkdir -p /var/lib/azlin").expect("the mkdir");
        let chmod = script
            .find("chmod 755 /var/lib/azlin")
            .expect("an explicit mode on the state directory");
        assert!(mkdir < chmod, "{script}");
    }
    use super::*;

    #[test]
    fn test_cloud_init_basic() {
        let yaml = generate_cloud_init("azureuser", "ssh-rsa AAAA...", &[], &[]);
        assert!(yaml.starts_with("#cloud-config"));
        assert!(yaml.contains("azureuser"));
        assert!(yaml.contains("ssh-rsa"));
    }

    #[test]
    fn test_cloud_init_with_packages() {
        let yaml = generate_cloud_init("user", "key", &["git", "curl"], &[]);
        assert!(yaml.contains("packages:"));
        assert!(yaml.contains("  - git"));
        assert!(yaml.contains("  - curl"));
    }

    #[test]
    fn test_cloud_init_with_commands() {
        let cmds = vec!["apt update".to_string(), "pip install uv".to_string()];
        let yaml = generate_cloud_init("user", "key", &[], &cmds);
        assert!(yaml.contains("runcmd:"));
        // Commands are now YAML-quoted for injection safety
        assert!(yaml.contains("'apt update'"));
    }

    #[test]
    fn test_cloud_init_rejects_newline_in_username() {
        // Username with newline should fall back to "azureuser"
        let yaml = generate_cloud_init("evil\nuser", "key", &[], &[]);
        assert!(yaml.contains("azureuser"));
        assert!(!yaml.contains("evil"));
    }

    #[test]
    fn test_cloud_init_rejects_newline_in_ssh_key() {
        let yaml = generate_cloud_init("user", "key\ninjection", &[], &[]);
        assert!(yaml.contains("ERROR"));
    }

    #[test]
    fn test_cloud_init_rejects_special_username() {
        // Username with spaces should fall back to "azureuser"
        let yaml = generate_cloud_init("evil user", "key", &[], &[]);
        assert!(yaml.contains("azureuser"));
    }

    #[test]
    fn test_cloud_init_filters_bad_packages() {
        // Package with special chars should be filtered out
        let yaml = generate_cloud_init("user", "key", &["git", "bad;pkg", "curl"], &[]);
        assert!(yaml.contains("  - git"));
        assert!(yaml.contains("  - curl"));
        assert!(!yaml.contains("bad;pkg"));
    }

    #[test]
    fn test_default_dev_packages() {
        let pkgs = default_dev_packages();
        assert!(pkgs.contains(&"git"));
        assert!(pkgs.contains(&"docker.io"));
        assert!(pkgs.contains(&"python3-pip"));
        assert!(pkgs.contains(&"ripgrep"));
        assert!(pkgs.contains(&"make"));
        assert!(pkgs.contains(&"fd-find"));
        assert!(pkgs.contains(&"pipx"));
        assert!(pkgs.contains(&"xdg-utils"));
        assert!(pkgs.contains(&"software-properties-common"));
        assert!(pkgs.len() >= 10);
    }

    #[test]
    fn test_default_dev_setup_commands() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter().any(|c| c.contains("rustup.rs")),
            "Missing Rust install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("dotnet-install.sh")),
            "Missing .NET install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("apt install -y gh")),
            "Missing GitHub CLI install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("azure-cli")),
            "Missing Azure CLI install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("nodesource.com")),
            "Missing Node.js install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("claude.ai/install.sh")),
            "Missing Claude Code install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("go.dev")),
            "Missing Go install command"
        );
        assert!(
            cmds.iter().any(|c| c.contains("usermod -aG docker")),
            "Missing Docker post-install command"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_enables_systemd_linger() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("loginctl enable-linger azureuser")),
            "default_dev_setup_commands must enable systemd user linger for snap Chromium cgroup support"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_linger_uses_custom_username() {
        let cmds = default_dev_setup_commands("devuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("loginctl enable-linger devuser")),
            "linger command must use the provisioned admin username"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_install_chromium_and_wrappers() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter()
                .any(|c| c.contains("apt-get install -y chromium-browser")),
            "default_dev_setup_commands must install chromium-browser"
        );
        assert!(
            cmds.iter()
                .any(|c| c.contains("cat > /usr/local/bin/chromium-browser << 'CHROMIUMWRAP'")),
            "default_dev_setup_commands must install the chromium-browser wrapper"
        );
        assert!(
            cmds.iter()
                .any(|c| c.contains("exec /usr/local/bin/chromium-browser \"$@\"")),
            "default_dev_setup_commands must install the chromium alias wrapper"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_chromium_wrapper_fails_loudly_when_scope_unavailable() {
        let cmds = default_dev_setup_commands("azureuser");
        assert!(
            cmds.iter().any(|c| c.contains("Chromium requires systemd user scope support on this VM, but systemd tooling is unavailable.")),
            "default_dev_setup_commands must fail loudly when user-systemd tooling is missing"
        );
        assert!(
            cmds.iter().any(|c| c.contains("Chromium requires an active systemd user environment on this VM. Check linger/user-systemd setup.")),
            "default_dev_setup_commands must fail loudly when the user systemd environment is unavailable"
        );
    }

    /// The sentinel moved out of the setup commands and into the preamble's
    /// EXIT trap (#1131).
    ///
    /// As a setup command it was the *last* thing the script did, so it was
    /// reached only when everything before it succeeded — which is why the VM
    /// that started this issue sat in "provisioning" forever with no terminal
    /// state and no explanation. From the trap it is written on every path, and
    /// the separate status file carries whether that path went well.
    #[test]
    fn the_script_writes_its_terminal_state_from_a_trap_not_from_a_setup_command() {
        let script = render_dev_cloud_init_script("azureuser");
        assert!(
            script.contains("trap azlin_finalize EXIT"),
            "the terminal state must be written on every path:\n{script}"
        );
        for path in [
            "/var/lib/azlin/provisioning-complete",
            "/var/lib/azlin/provisioning-status",
        ] {
            assert!(script.contains(path), "{path} is never written:\n{script}");
        }
        assert!(
            !default_dev_setup_commands("azureuser")
                .iter()
                .any(|c| c.contains("/var/lib/azlin/provisioning-complete")),
            "the sentinel must not be a setup command again: a step at the end of \
             the list is reached only when everything before it succeeded"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_install_azlin_binaries_by_archive_member_name() {
        let cmds = default_dev_setup_commands("azureuser");
        let azlin_cmd = cmds
            .iter()
            .find(|c| c.contains("/tmp/azlin-install"))
            .expect("default_dev_setup_commands must install the azlin CLI");

        // Release archives contain platform-suffixed members, not bare `azlin`.
        for (member, dest) in [
            ("azlin-linux-$ARCH", "azlin"),
            ("azdoit-linux-$ARCH", "azdoit"),
            ("ay-linux-$ARCH", "ay"),
        ] {
            assert!(
                azlin_cmd.contains(&format!("cp {member} ~/.cargo/bin/{dest}")),
                "azlin install must copy archive member {member} to ~/.cargo/bin/{dest}, got: {azlin_cmd}"
            );
        }
        assert!(
            !azlin_cmd.contains("cp azlin ~/.cargo/bin/"),
            "azlin install must not reference a bare `azlin` member that the archive does not contain"
        );
    }

    /// The install body must chain with `&&` so a failed step reaches the
    /// reporting branch, and that branch must report *and* fail.
    ///
    /// The suffix used to be `|| echo 'WARNING: …'`, which was the only way to
    /// report a failure while keeping `set -euo pipefail` from ending the whole
    /// script. Sections are isolated and recorded now (#1131), so that spelling
    /// would turn a non-zero status into zero and the ledger would say `ok`.
    #[test]
    fn test_default_dev_setup_commands_install_failures_are_not_swallowed() {
        let cmds = default_dev_setup_commands("azureuser");
        for marker in ["/tmp/azlin-install", "/tmp/amplihack-install"] {
            let cmd = cmds
                .iter()
                .find(|c| c.contains(marker))
                .unwrap_or_else(|| panic!("missing install command for {marker}"));
            let (body, report) = cmd
                .split_once(" || { echo 'WARNING:")
                .unwrap_or_else(|| panic!("{marker} install must report failure: {cmd}"));
            assert!(
                !body.contains("2>/dev/null"),
                "{marker} install must not discard errors and continue past them: {cmd}"
            );
            assert!(
                !body.contains(';'),
                "{marker} install must chain with && so a failed step reaches the \
                 reporting branch: {cmd}"
            );
            assert!(
                report.trim_end().ends_with("false; }"),
                "{marker} install must keep its non-zero status after reporting, or \
                 the section is recorded `ok`: {cmd}"
            );
        }
    }

    /// Rewrites the generated azlin install command into a hermetic, offline
    /// equivalent so a real shell can execute it.
    ///
    /// The download half (`URL=$(curl ...)`, `curl -o azlin.tar.gz`, `tar xzf`)
    /// is dropped and replaced by locally created stand-ins for the archive
    /// members, so the test never touches the network. Everything from
    /// `mkdir -p ~/.cargo/bin` onwards -- the `cp`/`chmod`/`cd`/`rm` tail where
    /// the bugs this PR fixes actually live -- is executed verbatim, including
    /// the `&&` chaining and the `|| { echo 'WARNING: ...'; false; }` branch.
    #[cfg(unix)]
    fn offline_azlin_install_script(staging: &str, present_members: &[&str]) -> String {
        const ARCH: &str = "x86_64";

        let cmds = default_dev_setup_commands("azureuser");
        let cmd = cmds
            .iter()
            .find(|c| c.contains("/tmp/azlin-install"))
            .expect("default_dev_setup_commands must install the azlin CLI")
            .clone();

        // Unwrap `su - <user> -c '<script>' || { echo 'WARNING: ...'; false; }`,
        // keeping the trailing branch so the failure reporting is exercised too.
        let body_start = cmd.find('\'').expect("install command must be quoted") + 1;
        let body_end = body_start
            + cmd[body_start..]
                .find("' || { echo")
                .expect("install command must have a WARNING fallback");
        let script_body = &cmd[body_start..body_end];
        let warning_branch = &cmd[body_end + 1..];

        let mut steps: Vec<String> = Vec::new();
        for step in script_body.split(" && ") {
            if step.starts_with("URL=") || step.starts_with("curl ") || step.starts_with("tar ") {
                continue; // network / archive extraction: stubbed out below
            }
            let step = if step.starts_with("ARCH=") {
                format!("ARCH={ARCH}")
            } else {
                step.replace("/tmp/azlin-install", staging)
            };
            let is_cd_staging = step == format!("cd {staging}");
            steps.push(step);
            if is_cd_staging {
                // Stand in for `tar xzf`: materialise the archive members.
                for member in present_members {
                    steps.push(format!("printf '#!/bin/sh\\n' > {member}-linux-{ARCH}"));
                }
            }
        }

        format!("{} {}", steps.join(" && "), warning_branch)
    }

    /// Executes the generated install tail in a real shell.
    ///
    /// The string-matching tests above are pattern-specific: they blacklist the
    /// exact spellings (`;`, `2>/dev/null`) that were wrong before this fix. This
    /// one is semantic -- it checks the actual exit status and output, so it also
    /// catches failure-swallowing spellings nobody thought to blacklist.
    #[cfg(unix)]
    #[test]
    fn test_default_dev_setup_commands_azlin_install_tail_behaves_under_a_real_shell() {
        use std::process::Command;
        use std::time::{SystemTime, UNIX_EPOCH};

        let unique = format!(
            "azlin-cloud-init-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        let home = root.join("home");
        let staging = root.join("staging");
        std::fs::create_dir_all(&home).expect("create scratch home");

        let run = |present_members: &[&str], suffix: &str| -> (bool, String) {
            let script = offline_azlin_install_script(
                staging.to_str().expect("staging path must be utf-8"),
                present_members,
            );
            let out = Command::new("sh")
                .arg("-c")
                .arg(format!("{script}{suffix}"))
                .env("HOME", &home)
                .current_dir(&root)
                .output()
                .expect("failed to run sh");
            (
                out.status.success(),
                String::from_utf8_lossy(&out.stdout).to_string()
                    + &String::from_utf8_lossy(&out.stderr),
            )
        };

        // Happy path: every archive member present. `&& pwd` proves the shell is
        // still in a live directory afterwards, i.e. the script left the staging
        // dir before deleting it.
        let (ok_status, ok_output) = run(&["azlin", "azdoit", "ay"], " && pwd");
        let installed: Vec<bool> = ["azlin", "azdoit", "ay"]
            .iter()
            .map(|b| home.join(".cargo/bin").join(b).exists())
            .collect();
        let staging_removed = !staging.exists();

        // Failure path: a future tarball drops `ay-linux-<arch>`. The chain must
        // abort, reach the WARNING branch, and still exit non-zero so the
        // section wrapper records it.
        let (missing_status, missing_output) = run(&["azlin", "azdoit"], "");

        let _ = std::fs::remove_dir_all(&root);

        assert!(
            ok_status,
            "install tail must succeed when all archive members exist: {ok_output}"
        );
        assert!(
            !ok_output.contains("WARNING:"),
            "successful install must not emit a WARNING: {ok_output}"
        );
        assert!(
            ok_output.contains(home.to_str().expect("home path must be utf-8")),
            "install must cd home before deleting its staging dir, so later steps have a live cwd: {ok_output}"
        );
        assert!(
            installed.iter().all(|installed| *installed),
            "install must place azlin, azdoit and ay in ~/.cargo/bin: {installed:?}"
        );
        assert!(
            staging_removed,
            "install must clean up its staging directory"
        );

        assert!(
            !missing_status,
            "a missing archive member must leave a non-zero status for the section \
             wrapper to record; keeping provisioning alive is the wrapper's job, \
             not this command's: {missing_output}"
        );
        assert!(
            missing_output.contains("WARNING:"),
            "a missing archive member must surface a WARNING rather than passing silently: {missing_output}"
        );
    }

    #[test]
    fn test_default_dev_setup_commands_leave_working_directory_before_cleanup() {
        let cmds = default_dev_setup_commands("azureuser");
        for dir in ["/tmp/azlin-install", "/tmp/amplihack-install"] {
            let cmd = cmds
                .iter()
                .find(|c| c.contains(dir))
                .unwrap_or_else(|| panic!("missing install command for {dir}"));
            assert!(
                cmd.contains(&format!("cd ~ && rm -rf {dir}")),
                "install must leave {dir} before deleting it, otherwise later steps run from a deleted CWD: {cmd}"
            );
        }
    }

    #[test]
    fn test_default_dev_setup_commands_amplihack_setup_runs_from_valid_cwd() {
        let cmds = default_dev_setup_commands("azureuser");
        let cmd = cmds
            .iter()
            .find(|c| c.contains("/tmp/amplihack-install"))
            .expect("missing amplihack install command");
        let cleanup = cmd
            .find("rm -rf /tmp/amplihack-install")
            .expect("amplihack install must clean up its staging directory");
        let cd_home = cmd.find("cd ~ &&").expect("amplihack install must cd home");
        let framework_setup = cmd
            .find("~/.cargo/bin/amplihack install")
            .expect("amplihack install must run framework setup");
        assert!(
            cd_home < cleanup && cleanup < framework_setup,
            "`amplihack install` must run after cd-ing out of the deleted staging dir: {cmd}"
        );
    }

    /// The five CLIs are installed into ~/.cargo/bin, which only reaches PATH via
    /// ~/.cargo/env sourced from .bashrc -- and bash skips .bashrc for
    /// non-interactive shells. Every one of them must also be linked into
    /// /usr/local/bin, which is on the default PATH for interactive, login,
    /// non-interactive and cron shells alike.
    #[test]
    fn test_default_dev_setup_commands_link_installed_clis_into_usr_local_bin() {
        let cmds = default_dev_setup_commands("devuser");
        let link_cmd = cmds
            .iter()
            .find(|c| c.contains("ln -sf \"$src\" /usr/local/bin/$b"))
            .expect("default_dev_setup_commands must link the installed CLIs into /usr/local/bin");

        for bin in ["amplihack", "amplihack-hooks", "azlin", "azdoit", "ay"] {
            assert!(
                link_cmd.contains(&format!(" {bin} ")) || link_cmd.contains(&format!(" {bin};")),
                "{bin} must be linked onto the default PATH: {link_cmd}"
            );
        }
        assert!(
            link_cmd.contains("/home/devuser/.cargo/bin/$b"),
            "link source must be the provisioned admin user's cargo bin: {link_cmd}"
        );
        assert!(
            link_cmd.contains("if [ -x \"$src\" ]"),
            "linking must be guarded so a failed install cannot leave a dangling symlink: {link_cmd}"
        );
        assert!(
            link_cmd.matches("echo \"WARNING:").count() >= 2,
            "both a failed link and a missing binary must be reported: {link_cmd}"
        );
    }

    /// Semantic counterpart to the string assertions above: runs the generated
    /// link step in a real shell against a scratch "cargo bin" and "/usr/local/bin"
    /// and inspects what actually lands on disk.
    #[cfg(unix)]
    #[test]
    fn test_default_dev_setup_commands_link_step_behaves_under_a_real_shell() {
        use std::process::Command;
        use std::time::{SystemTime, UNIX_EPOCH};

        const BINS: [&str; 5] = ["amplihack", "amplihack-hooks", "azlin", "azdoit", "ay"];

        let unique = format!(
            "azlin-cloud-init-link-test-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        let cargo_bin = root.join("cargo-bin");
        let local_bin = root.join("local-bin");

        let cmds = default_dev_setup_commands("azureuser");
        let link_cmd = cmds
            .iter()
            .find(|c| c.contains("ln -sf \"$src\" /usr/local/bin/$b"))
            .expect("default_dev_setup_commands must link the installed CLIs into /usr/local/bin")
            .replace(
                "/home/azureuser/.cargo/bin",
                cargo_bin.to_str().expect("path must be utf-8"),
            )
            .replace(
                "/usr/local/bin",
                local_bin.to_str().expect("path must be utf-8"),
            );

        // `installed` binaries exist and are executable; the rest are absent, as
        // they would be after a failed installer.
        let run = |installed: &[&str]| -> String {
            let _ = std::fs::remove_dir_all(&root);
            std::fs::create_dir_all(&cargo_bin).expect("create scratch cargo bin");
            for bin in installed {
                let path = cargo_bin.join(bin);
                std::fs::write(&path, "#!/bin/sh\n").expect("write stub binary");
                let mut perms = std::fs::metadata(&path)
                    .expect("stat stub binary")
                    .permissions();
                std::os::unix::fs::PermissionsExt::set_mode(&mut perms, 0o755);
                std::fs::set_permissions(&path, perms).expect("chmod stub binary");
            }
            let out = Command::new("sh")
                .arg("-c")
                .arg(&link_cmd)
                .output()
                .expect("failed to run sh");
            assert!(
                out.status.success(),
                "the link step must never abort provisioning: {}",
                String::from_utf8_lossy(&out.stderr)
            );
            String::from_utf8_lossy(&out.stdout).to_string() + &String::from_utf8_lossy(&out.stderr)
        };

        // Happy path: every CLI installed, so every CLI gets a /usr/local/bin entry
        // that resolves to a real executable.
        let all_output = run(&BINS);
        let linked: Vec<(bool, bool)> = BINS
            .iter()
            .map(|bin| {
                let path = local_bin.join(bin);
                (
                    std::fs::symlink_metadata(&path).is_ok(),
                    path.exists(), // follows the link: false means dangling
                )
            })
            .collect();

        // Failure path: the amplihack installer failed, so its binaries are absent.
        let missing_output = run(&["azlin", "azdoit", "ay"]);
        let amplihack_link = local_bin.join("amplihack");
        let amplihack_link_exists = std::fs::symlink_metadata(&amplihack_link).is_ok();
        let azlin_linked = local_bin.join("azlin").exists();

        let _ = std::fs::remove_dir_all(&root);

        for (bin, (exists, resolves)) in BINS.iter().zip(&linked) {
            assert!(
                *exists && *resolves,
                "{bin} must be reachable from the default PATH via /usr/local/bin: {all_output}"
            );
        }
        assert!(
            !all_output.contains("WARNING:"),
            "linking every installed CLI must not warn: {all_output}"
        );

        assert!(
            !amplihack_link_exists,
            "a CLI that failed to install must not get a dangling /usr/local/bin symlink: {missing_output}"
        );
        assert!(
            missing_output.contains("WARNING:") && missing_output.contains("amplihack"),
            "a missing CLI must be reported, not skipped silently: {missing_output}"
        );
        assert!(
            azlin_linked,
            "one missing CLI must not stop the others from being linked: {missing_output}"
        );
    }

    /// Provisioning must check the CLIs from the same kind of shell that
    /// `ssh <vm> 'amplihack ...'`, cron and CI use. The pre-existing check runs
    /// under `su -` (a login shell), which passed even while every non-interactive
    /// invocation failed.
    #[test]
    fn test_default_dev_setup_commands_verify_clis_on_the_non_interactive_path() {
        let cmds = default_dev_setup_commands("devuser");
        let check = cmds
            .iter()
            .find(|c| c.contains("not on the default non-interactive PATH"))
            .expect("provisioning must verify the CLIs resolve from a non-interactive shell");
        assert!(
            check.starts_with("su devuser -s /bin/bash -c"),
            "the check must run as the admin user in a non-login shell: {check}"
        );
        for bin in ["amplihack", "amplihack-hooks", "azlin", "azdoit", "ay"] {
            assert!(
                check.contains(&format!(" {bin} ")) || check.contains(&format!(" {bin};")),
                "{bin} must be covered by the non-interactive PATH check: {check}"
            );
        }
    }

    /// The .NET install runs inside `( ... || echo WARNING )`, so a failed install
    /// still reaches the `ln`. Linking unconditionally left a dangling
    /// /usr/local/bin/dotnet: `command -v dotnet` succeeded, running it did not.
    #[test]
    fn test_default_dev_setup_commands_never_link_a_missing_dotnet() {
        let cmds = default_dev_setup_commands("azureuser");
        let dotnet = cmds
            .iter()
            .find(|c| c.contains("dotnet-install.sh"))
            .expect("missing .NET install command");
        assert!(
            dotnet.contains("if [ -x /usr/share/dotnet/dotnet ]; then ln -sf /usr/share/dotnet/dotnet /usr/local/bin/dotnet;"),
            "dotnet must only be linked once the SDK is actually present: {dotnet}"
        );
        assert!(
            dotnet.contains("not linking /usr/local/bin/dotnet"),
            "a missing dotnet must be reported instead of linked: {dotnet}"
        );
    }

    #[test]
    fn test_render_dev_cloud_init_script_uses_shared_packages_and_commands() {
        let script = render_dev_cloud_init_script("azureuser");
        assert!(script.starts_with("#!/bin/bash\nset -euo pipefail"));
        assert!(script.contains("fd-find"));
        assert!(script.contains("xdg-utils"));
        assert!(
            script.contains("ln -sf \"$src\" /usr/local/bin/$b"),
            "the rendered script must put the installed CLIs on the default PATH"
        );
        assert!(script.contains("/var/lib/azlin/provisioning-complete"));
        assert!(script.contains("[AZLIN] provisioning finished: status=$azlin_final"));
    }

    #[test]
    fn test_cloud_init_includes_sudo() {
        let yaml = generate_cloud_init("dev", "key", &[], &[]);
        assert!(yaml.contains("sudo"));
        assert!(yaml.contains("NOPASSWD"));
    }

    #[test]
    fn test_cloud_init_includes_docker_group() {
        let yaml = generate_cloud_init("dev", "key", &[], &[]);
        assert!(yaml.contains("docker"));
    }

    #[test]
    fn test_generate_cloud_init_preserves_multiline_setup_commands() {
        let yaml = generate_cloud_init("dev", "key", &[], &[String::from("echo one\necho two")]);
        assert!(yaml.contains("runcmd:\n  - |\n    echo one\n    echo two\n"));
    }

    // -- DiskConfig cloud-init script generation tests ----------------

    #[test]
    fn test_disk_config_no_disks_produces_no_disk_blocks() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: false,
                tmp_disk: false,
            },
        );
        assert!(!script.contains("Data disk setup"));
        assert!(!script.contains("Home disk"));
        assert!(!script.contains("Tmp disk"));
        assert!(!script.contains("/dev/disk/azure/scsi1/lun"));
    }

    #[test]
    fn test_disk_config_home_only_uses_lun0() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must reference LUN 0 for home disk
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun0"),
            "Home disk must use Azure LUN 0 symlink"
        );
        assert!(
            script.contains("Home disk (LUN 0)"),
            "Home disk block must be labeled with LUN 0"
        );
        // Must NOT contain tmp disk block
        assert!(
            !script.contains("Tmp disk"),
            "Should not contain tmp disk block when tmp_disk=false"
        );
        // Must format as ext4
        assert!(
            script.contains("mkfs.ext4"),
            "Home disk must be formatted with ext4"
        );
        // Must bind-mount to /home/azureuser
        assert!(
            script.contains("/home/azureuser"),
            "Home disk must mount to /home/azureuser"
        );
        // Must persist in fstab
        assert!(script.contains("/etc/fstab"), "Must persist mount in fstab");
    }

    #[test]
    fn test_disk_config_tmp_only_uses_lun0() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: false,
                tmp_disk: true,
            },
        );
        // When no home disk, tmp disk should get LUN 0
        assert!(
            script.contains("Tmp disk (LUN 0)"),
            "Tmp disk must use LUN 0 when home disk is absent"
        );
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun0"),
            "Tmp disk must use LUN 0 symlink when home disk is absent"
        );
        // Must NOT contain home disk block
        assert!(
            !script.contains("Home disk"),
            "Should not contain home disk block when home_disk=false"
        );
        // Must set sticky bit on /tmp
        assert!(
            script.contains("chmod 1777"),
            "Tmp disk must set sticky bit (1777) on /tmp"
        );
        // Must persist in fstab
        assert!(script.contains("/etc/fstab"), "Must persist mount in fstab");
    }

    #[test]
    fn test_disk_config_both_disks_uses_lun0_and_lun1() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: true,
            },
        );
        // Home disk at LUN 0
        assert!(
            script.contains("Home disk (LUN 0)"),
            "Home disk must be at LUN 0"
        );
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun0"),
            "Home disk must use LUN 0 symlink"
        );
        // Tmp disk at LUN 1
        assert!(
            script.contains("Tmp disk (LUN 1)"),
            "Tmp disk must be at LUN 1 when home disk is present"
        );
        assert!(
            script.contains("/dev/disk/azure/scsi1/lun1"),
            "Tmp disk must use LUN 1 symlink when home disk is present"
        );
    }

    // -- Hardening assertions -----------------------------------------

    #[test]
    fn test_disk_home_block_has_retry_loop_for_lun_detection() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Retry loop: must poll for LUN device availability
        assert!(
            script.contains("sleep") && script.contains("retry")
                || script.contains("sleep") && script.contains("for ")
                || script.contains("udevadm settle"),
            "Home disk block must include retry/polling logic for LUN device detection"
        );
    }

    #[test]
    fn test_disk_tmp_block_has_retry_loop_for_lun_detection() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: false,
                tmp_disk: true,
            },
        );
        assert!(
            script.contains("sleep") && script.contains("retry")
                || script.contains("sleep") && script.contains("for ")
                || script.contains("udevadm settle"),
            "Tmp disk block must include retry/polling logic for LUN device detection"
        );
    }

    #[test]
    fn test_disk_blocks_use_subshell_isolation() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: true,
            },
        );
        // Each disk block should be wrapped in a subshell so failures don't abort cloud-init
        // The pattern should be: ( ... ) || echo "WARN: ..."
        assert!(
            script.contains("|| echo") || script.contains("|| {"),
            "Disk blocks must use subshell isolation with fallback on failure"
        );
    }

    #[test]
    fn test_disk_home_block_cleans_up_old_home() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must remove /home/azureuser.old after successful bind mount
        assert!(
            script.contains("rm -rf /home/azureuser.old")
                || script.contains("rm -rf \"/home/azureuser.old\""),
            "Home disk block must clean up /home/azureuser.old after bind mount"
        );
    }

    /// The test that proves the section wrapper, by running it.
    ///
    /// This is the one assertion the original wrapper could not have passed,
    /// and no amount of reading the generated script would have revealed it:
    /// `( … ) || rc=$?` suspends `errexit` inside the subshell, so the body ran
    /// past its first failing command and `$rc` came back as the status of the
    /// body's *last* command. Every disk section ends in `echo`, so every
    /// section reported `ok`.
    ///
    /// Concretely, on a VM where `mount "$HOME_DEV" /mnt/home-data` failed, the
    /// body would have gone on to copy into the OS-disk directory, `mv` the
    /// original to `.old`, bind over it, and delete `.old` — losing the home
    /// directory and recording `disk-home ok`.
    ///
    /// So the property is asserted the only way it can be: run it.
    #[cfg(unix)]
    #[test]
    fn the_section_wrapper_stops_the_body_at_its_first_failure() {
        use std::process::Command;
        use std::time::{SystemTime, UNIX_EPOCH};

        let root = std::env::temp_dir().join(format!(
            "azlin-section-wrapper-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).expect("create scratch root");
        let var_lib = root.join("var-lib-azlin");

        // The real preamble and the real wrapper, with only the ledger path
        // redirected into the scratch directory.
        let script = format!(
            "{}{}{}echo AZLIN_REACHED_END\nexit 0\n",
            provisioning_preamble(),
            render_section(&Section {
                name: "probe-a".to_string(),
                needs_network: false,
                body: "  echo AZLIN_A1\n  false\n  echo AZLIN_A2".to_string(),
            }),
            render_section(&Section {
                name: "probe-b".to_string(),
                needs_network: false,
                body: "  echo AZLIN_B1".to_string(),
            }),
        )
        .replace("/var/lib/azlin", var_lib.to_str().expect("utf-8 path"));

        let out = Command::new("bash")
            .arg("-c")
            .arg(&script)
            .current_dir(&root)
            .output()
            .expect("failed to run bash");
        let stdout = String::from_utf8_lossy(&out.stdout).to_string();
        let ledger = std::fs::read_to_string(var_lib.join("provisioning.tsv")).unwrap_or_default();
        let status = std::fs::read_to_string(var_lib.join("provisioning-status"))
            .unwrap_or_default()
            .trim()
            .to_string();
        let _ = std::fs::remove_dir_all(&root);

        assert!(stdout.contains("AZLIN_A1"), "the body never ran:\n{stdout}");
        assert!(
            !stdout.contains("AZLIN_A2"),
            "the body continued past its first failing command; `errexit` is \
             suspended inside the group:\n{stdout}"
        );
        assert!(
            ledger.contains("probe-a\tfailed\t1"),
            "the failure must be recorded with its real status, not the status \
             of the body's last command. Ledger:\n{ledger}"
        );

        // The other half: the failure must not end the script, and a section
        // that succeeds must still be recorded `ok`.
        assert!(
            stdout.contains("AZLIN_B1") && stdout.contains("AZLIN_REACHED_END"),
            "a failed section ended the script:\n{stdout}"
        );
        assert!(
            ledger.contains("probe-b\tok\t0"),
            "a successful section must be recorded `ok`. Ledger:\n{ledger}"
        );
        assert_eq!(
            status, "degraded",
            "a run with a failed section must not report `ok`. Ledger:\n{ledger}"
        );
        assert!(out.status.success(), "script exited non-zero:\n{stdout}");
    }

    /// The copy on the OS disk is the only thing standing between a failed
    /// bind and a lost home directory, so it is removed *last* — after the
    /// fstab entries are written.
    ///
    /// Until fstab is written, the mount does not survive a reboot: a run that
    /// binds successfully and then fails on `blkid` would come back from the
    /// next boot with an empty `/home/<user>` and the data on an unmounted
    /// disk. Deleting `.old` before that point is what would make it
    /// unrecoverable.
    #[test]
    fn the_home_block_deletes_the_original_only_after_fstab_is_written() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Scoped to the section, not the whole script: `azlin_storage_summary`
        // in the preamble also mentions `/etc/fstab`, and matching that offset
        // made this assertion true no matter where the cleanup moved to.
        let block = script
            .split("# ---- section: disk-home ----")
            .nth(1)
            .and_then(|rest| rest.split("# ---- section: ").next())
            .expect("a disk-home section");
        let fstab = block
            .find("/etc/fstab")
            .expect("the home block must persist the mount");
        let cleanup = block
            .find("rm -rf /home/azureuser.old")
            .expect("the home block must clean up the original");
        assert!(
            fstab < cleanup,
            "`rm -rf /home/azureuser.old` at {cleanup} precedes the fstab write at \
             {fstab}; a failure in between would leave no copy on either disk:\n{block}"
        );
    }

    /// A `mount` that returns 0 without producing a mountpoint must fail the
    /// section rather than fall through.
    ///
    /// Falling through would chown, write fstab, and record `disk-home` as
    /// `ok` — with the user's home an empty directory on the OS disk and their
    /// data in `.old`. That is the original bug's signature: a report of
    /// success over storage that is not there.
    #[test]
    fn the_home_block_treats_a_bind_that_did_not_take_as_a_failure() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        let bind = script
            .find("mount --bind /mnt/home-data/azureuser /home/azureuser")
            .expect("a bind step");
        let after = &script[bind..];
        let check = after
            .find("if ! mountpoint -q /home/azureuser; then")
            .expect("the bind must be verified immediately after it is made");
        let exit = after[check..]
            .find("exit 1")
            .expect("an unverified bind must end the section");
        assert!(
            after[check..check + exit].lines().count() < 6,
            "the `exit 1` must belong to the mountpoint check, not to something \
             later:\n{}",
            &after[check..check + exit]
        );
    }

    /// The gate that skips the network-dependent toolchain sections reads two
    /// named variables, not whatever `$rc` happens to hold.
    ///
    /// `$rc` is reused by every section. Reading it here worked only because
    /// the gate sat directly after `apt-install`, so inserting a section
    /// between them would have silently changed which failure the gate was
    /// looking at.
    #[test]
    fn the_archive_gate_reads_named_variables_rather_than_the_ambient_rc() {
        let script = render_dev_cloud_init_script_with_disks("azureuser", &DiskConfig::default());
        assert!(
            script.contains(
                "if [ \"$AZLIN_APT_UPDATE_RC\" -ne 0 ] && [ \"$AZLIN_APT_INSTALL_RC\" -ne 0 ]; then"
            ),
            "the gate must name both signals it depends on:\n{script}"
        );
        for capture in ["AZLIN_APT_UPDATE_RC=$rc", "AZLIN_APT_INSTALL_RC=$rc"] {
            assert!(script.contains(capture), "{capture} is never captured");
        }
    }

    #[test]
    fn test_disk_home_block_has_rollback_trap() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must have a trap to restore /home/azureuser.old on failure
        assert!(
            script.contains("trap") && script.contains("azureuser.old"),
            "Home disk block must include rollback trap to restore /home/user.old on failure"
        );
    }

    #[test]
    fn test_disk_home_block_has_mandatory_rsync() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // rsync must not silently fail (no `|| true` suppression)
        assert!(
            script.contains("rsync"),
            "Home disk block must rsync existing home data"
        );
    }

    #[test]
    fn test_disk_fstab_entries_are_idempotent() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // fstab writes should check for existing entries (grep -q) before appending
        assert!(
            script.contains("grep -q") || script.contains("grep "),
            "fstab entries must be idempotent (check before appending)"
        );
    }

    #[test]
    fn test_disk_blocks_use_udevadm_settle() {
        let script = render_dev_cloud_init_script_with_disks(
            "azureuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Must call udevadm settle before trying to read LUN devices
        assert!(
            script.contains("udevadm settle"),
            "Disk setup must call udevadm settle for device node stability"
        );
    }

    #[test]
    fn test_disk_home_block_uses_custom_username() {
        let script = render_dev_cloud_init_script_with_disks(
            "devuser",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        assert!(
            script.contains("/home/devuser"),
            "Home disk block must use the provided admin username"
        );
        assert!(
            !script.contains("/home/azureuser"),
            "Home disk block must not hardcode azureuser when custom username is provided"
        );
    }

    #[test]
    fn test_disk_home_block_sanitizes_bad_username() {
        let script = render_dev_cloud_init_script_with_disks(
            "evil user",
            &DiskConfig {
                home_disk: true,
                tmp_disk: false,
            },
        );
        // Unsafe username should fall back to azureuser
        assert!(
            script.contains("/home/azureuser"),
            "Bad username must fall back to azureuser in disk blocks"
        );
        assert!(
            !script.contains("evil user"),
            "Unsafe username must not appear in disk blocks"
        );
    }
    /// The Azure CLI install must not fail silently, and must cope with an
    /// Ubuntu release Microsoft has not published an apt dist for.
    ///
    /// Observed on a real Ubuntu 26.04 VM: codename "resolute",
    /// `https://packages.microsoft.com/repos/azure-cli/dists/resolute/Release`
    /// returns 404 (noble returns 200), `which az` reported nothing, and
    /// cloud-init-output.log contained zero mentions of the install — because
    /// `curl -sL ... | bash` exits with bash's status, so a failed download
    /// still succeeded, and `-s` hid the error.
    #[test]
    fn azure_cli_install_reports_failure_and_handles_unpublished_codename() {
        let cmds = default_dev_setup_commands("azureuser");
        let az = cmds
            .iter()
            .find(|c| c.contains("azure-cli"))
            .expect("dev setup must install the Azure CLI");

        assert!(
            !az.contains("InstallAzureCLIDeb"),
            "must not use the aka.ms script, which 404s on unpublished codenames: {az}"
        );
        assert!(
            az.contains("|| { echo 'WARNING: Azure CLI install failed' >&2; false; }"),
            "a failed Azure CLI install must be reported *and* still fail, so the \
             provisioning ledger records it: {az}"
        );
        assert!(
            az.contains("AZ_DIST=noble"),
            "must fall back to a published dist when the running codename is absent: {az}"
        );
        assert!(
            az.contains("lsb_release -cs"),
            "must prefer the running codename when it is published: {az}"
        );
        // `curl -s` hides the very error that needs surfacing; -f makes curl
        // fail loudly on a 404 instead of writing the error page to the pipe.
        assert!(
            az.contains("curl -fsSL"),
            "curl must fail on HTTP errors rather than piping an error page: {az}"
        );
    }

    /// A `| bash` / `| sh` inside `su -c` defeats the outer `|| echo WARNING`.
    ///
    /// The generated script sets `pipefail`, but that is per-shell and the
    /// fresh login shell `su -` starts does not inherit it, so a failed
    /// download leaves the shell reading empty stdin and exiting 0. The guard
    /// below only checks that `|| echo` is *present*, which such a line
    /// satisfies while still being silent — so this asserts the stronger
    /// property directly.
    #[test]
    fn su_payloads_never_pipe_a_download_into_a_shell() {
        for cmd in default_dev_setup_commands("azureuser") {
            if !cmd.contains("su - ") {
                continue;
            }

            let pipes_to_shell = (cmd.contains("| bash") || cmd.contains("| sh"))
                && (cmd.contains("curl ") || cmd.contains("wget "));
            assert!(
                !pipes_to_shell || cmd.contains("set -o pipefail"),
                "a download piped into a shell inside `su -c` cannot report failure \
                 (pipefail is not inherited); download to a file and execute it: {cmd}"
            );
        }
    }

    /// Execute the generated Claude payload against an installer that uses a
    /// Bash array. Ubuntu dash rejects that syntax; Bash runs it and writes the
    /// marker. This tests the command's behavior, not merely its spelling.
    #[cfg(unix)]
    #[test]
    fn generated_claude_install_command_runs_a_bash_installer() {
        use std::process::Command;
        use std::time::{SystemTime, UNIX_EPOCH};

        let command = default_dev_setup_commands("azureuser")
            .into_iter()
            .find(|command| command.contains("claude.ai/install.sh"))
            .expect("Claude installer command");
        let payload = command
            .strip_prefix("su - azureuser -c '")
            .and_then(|rest| rest.split_once("' || {").map(|(payload, _)| payload))
            .expect("single-quoted su payload");

        let root = std::env::temp_dir().join(format!(
            "azlin-claude-installer-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).expect("create scratch directory");
        let fixture = root.join("installer.sh");
        let downloaded = root.join("downloaded.sh");
        let marker = root.join("installed");
        std::fs::write(
            &fixture,
            format!(
                "#!/usr/bin/env bash\nvalues=(claude installed)\nprintf '%s\\n' \"${{values[*]}}\" > '{}'\n",
                marker.display()
            ),
        )
        .expect("write Bash-only installer");

        let dash = Command::new("dash")
            .arg(&fixture)
            .output()
            .expect("run fixture with dash");
        assert!(
            !dash.status.success(),
            "the fixture must reproduce the Ubuntu dash failure or the test \
             cannot distinguish `sh` from `bash`"
        );
        assert!(
            !marker.exists(),
            "the Bash-only installer unexpectedly ran under /bin/sh"
        );

        let runnable = payload
            .replace(
                "curl -fsSL https://claude.ai/install.sh -o /tmp/claude-install.sh",
                &format!("cp '{}' '{}'", fixture.display(), downloaded.display()),
            )
            .replace(
                "/tmp/claude-install.sh",
                downloaded.to_str().expect("utf-8 path"),
            );
        let output = Command::new("bash")
            .arg("-c")
            .arg(&runnable)
            .output()
            .expect("run generated Claude payload");
        let installed = std::fs::read_to_string(&marker).unwrap_or_default();
        let _ = std::fs::remove_dir_all(&root);

        assert!(
            output.status.success(),
            "generated payload failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(installed.trim(), "claude installed");
    }

    /// Every dev-setup step that can fail should say so, and none may swallow
    /// its exit status on the way. This guards the class of bug rather than the
    /// single instance — an unguarded step is how the Azure CLI silently went
    /// missing in the first place.
    ///
    /// The second half is what changed with #1131. Each section's exit status
    /// is now recorded in `/var/lib/azlin/provisioning.tsv`, so a trailing
    /// `|| echo` or `|| true` no longer merely fails to report — it actively
    /// reports the opposite, marking a failed section `ok`.
    #[test]
    fn network_installing_dev_setup_commands_report_their_failures() {
        for cmd in default_dev_setup_commands("azureuser") {
            // Only steps that reach the network can fail for environmental
            // reasons worth reporting.
            if !(cmd.contains("curl ") || cmd.contains("wget ")) {
                continue;
            }
            assert!(
                cmd.contains("WARNING:"),
                "network-installing step has no failure report: {cmd}"
            );
            let tail = cmd.trim_end();
            assert!(
                !tail.ends_with("|| true") && !tail.ends_with('\''),
                "a step whose last operator is an unconditional success hides its \
                 own failure from the provisioning ledger: {cmd}"
            );
        }
    }
}
