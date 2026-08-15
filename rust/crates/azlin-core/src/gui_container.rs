//! Containerised remote-desktop planner for `azlin gui install`.
//!
//! `azlin gui` installs a desktop stack with the VM's package manager. That works
//! on distributions whose repositories carry a VNC server, an RDP server and a
//! window manager, and cannot work on those that do not. This module provides the
//! alternative: the whole desktop stack — X server, window manager and the VNC or
//! RDP server — comes from a prebuilt container image running on the VM's Docker,
//! so it is independent of what the VM's repositories happen to contain.
//!
//! Every function here is pure: data in, plan or command strings out. It mirrors
//! the sibling planners in `azlin-azure` so the install, detection and removal
//! rules are fully unit-testable without a VM, without Docker and without Azure.
//!
//! # Security invariants
//!
//! These are enforced by construction here and asserted by the unit tests:
//!
//! * Published ports are **always** bound to `127.0.0.1` on the VM, so the desktop
//!   is unreachable from the network even if a permissive NSG rule existed.
//! * No network-security-group rule is ever created, modified or referenced. This
//!   module emits no `az` command of any kind. Access is expected to happen
//!   exclusively over azlin's existing SSH/bastion tunnel.
//! * The web (noVNC) port of the VNC image is deliberately **not** published.
//! * The desktop always has a password. The password is generated on the VM and
//!   passed to Docker through a `0600` env-file, so it never appears in a process
//!   listing or in `docker inspect` output.
//! * Images are pinned by tag **and** verified by digest after every pull: the
//!   install script compares the `RepoDigests` entry Docker records for the
//!   pulled image against [`GuiImage::index_digest`] — accepting
//!   [`GuiImage::amd64_digest`] as an alternative — and refuses to run the
//!   container (removing the pulled image and exiting non-zero) on a mismatch.
//!   `docker pull <tag>` on a multi-arch repository records the digest of the
//!   *manifest list / OCI index*, not of the platform-specific child manifest,
//!   so the index digest is the value the check must normally expect; the
//!   child digest is accepted too because a pull by an explicit
//!   single-platform reference legitimately records that instead.
//!   A tag is mutable — a compromised or careless registry can repoint
//!   `consol/debian-xfce-vnc:v2.0.4` to different bytes without changing the
//!   string azlin pulls — so the tag alone is not a provenance guarantee. The
//!   digest check is skipped (not failed) when Docker reports no `RepoDigests`
//!   at all, which happens only for images that were not pulled from a
//!   registry; every image `azlin gui install` runs is freshly pulled, so this
//!   is a defensive fallback, not the expected path.
//!
//! # Password strength, stated honestly
//!
//! The generated password is 32 hex characters. The RDP image consumes all of it
//! (`chpasswd` into a yescrypt hash). The RFB protocol used by VNC, however,
//! truncates passwords to **8 bytes** (RFC 6143 §7.2.2): everything past the
//! eighth character is discarded before the DES obfuscation, which is why a VNC
//! `passwd` file is always exactly 8 bytes long. Only the first 8 hex characters
//! therefore survive, giving `8 * 4 = 32` bits of effective entropy no matter how
//! long the generated secret is.
//!
//! Do not restate this as "128-bit" security. It is not. 32 bits is acceptable
//! here *only* because port 5901 is bound to `127.0.0.1` on the VM and is
//! reachable solely through the SSH tunnel, so there is no network-facing
//! brute-force surface. It would not be acceptable for an exposed port.

use serde::{Deserialize, Serialize};

/// Remote-desktop wire protocol to install on the VM.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum GuiProtocol {
    /// TigerVNC RFB, consumed by a standard VNC viewer.
    Vnc,
    /// xrdp, consumed by a standard RDP client.
    Rdp,
}

impl GuiProtocol {
    /// Lowercase wire name, used in generated scripts and in container labels.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Vnc => "vnc",
            Self::Rdp => "rdp",
        }
    }

    /// Parse the wire name emitted by [`build_detect_script`].
    pub fn parse(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "vnc" => Some(Self::Vnc),
            "rdp" => Some(Self::Rdp),
            _ => None,
        }
    }
}

impl std::fmt::Display for GuiProtocol {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Container name azlin manages. Fixed, so install is naturally idempotent and
/// detection needs no bookkeeping beyond Docker itself.
pub const CONTAINER_NAME: &str = "azlin-gui";

/// Directory on the VM holding the generated env-file and the exported VNC
/// password blob. Created `0700`; the files inside are `0600`.
pub const STATE_DIR: &str = "$HOME/.azlin/gui";

/// Path on the VM of the VNC authentication blob exported from the container.
///
/// The blob is produced by the container's own `vncpasswd`, then copied out with
/// `docker cp`. Copying out (rather than bind-mounting over the container's
/// `.vnc` directory) avoids shadowing files the image's startup script writes
/// there, and avoids reimplementing the VNC password format locally.
pub const HOST_VNC_PASSWD_PATH: &str = "$HOME/.azlin/gui/vncpasswd";

/// Path on the VM of the plaintext RDP password, written `0600`.
pub const HOST_RDP_PASSWD_PATH: &str = "$HOME/.azlin/gui/rdppasswd";

/// Path inside the VNC container of the authentication blob to export.
pub const CONTAINER_VNC_PASSWD_PATH: &str = "/headless/.vnc/passwd";

/// Login name used by the RDP image's desktop session.
pub const RDP_USERNAME: &str = "abc";

/// Free space the install requires on the Docker data root, in KiB (4 GiB).
///
/// The desktop images are roughly 2 GiB compressed; 4 GiB leaves room to unpack
/// them without filling the disk.
const REQUIRED_FREE_KIB: u64 = 4 * 1024 * 1024;

/// A container image pinned for one protocol.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GuiImage {
    /// Fully qualified image reference including the pinned tag.
    pub reference: &'static str,
    /// Digest of the multi-arch manifest list / OCI index at the time of
    /// pinning. This is the value `docker pull <tag>` records in `RepoDigests`,
    /// so it is what the install script (see [`build_install_script`]) normally
    /// compares against; a tag that silently moves on the registry is thereby
    /// detected and rejected rather than silently trusted.
    pub index_digest: &'static str,
    /// Digest of the `linux/amd64` child manifest inside [`Self::index_digest`]
    /// at the time of pinning.
    ///
    /// Recorded so the pinning is unambiguous about which platform image azlin
    /// expects to run, and accepted by the install script as an alternative to
    /// the index digest: pulling by an explicit single-platform reference (or a
    /// future single-arch tag) legitimately records the child digest instead.
    /// Any other value still fails closed.
    ///
    /// This assumes the VM is `linux/amd64`: azlin currently provisions only
    /// D-series/E-series v5 VMs, which are x86_64. If an ARM VM family is ever
    /// added, this field and the verification must become architecture-aware.
    pub amd64_digest: &'static str,
    /// Port the desktop server listens on inside the container.
    pub container_port: u16,
    /// Human-readable description of which clients can connect.
    pub client_support: &'static str,
}

/// VNC image: genuine TigerVNC RFB on 5901.
///
/// Verified against the Docker Hub registry API: the `linux/amd64` manifest
/// exposes `5901/tcp` and `6901/tcp`, has entrypoint
/// `/dockerstartup/vnc_startup.sh`, and reads `VNC_PW`, `VNC_RESOLUTION` and
/// `VNC_COL_DEPTH` from the environment.
///
/// `linuxserver/webtop` was evaluated and rejected: it serves KasmVNC over
/// WebSockets, which a standard RFB viewer cannot speak.
pub const VNC_IMAGE: GuiImage = GuiImage {
    reference: "consol/debian-xfce-vnc:v2.0.4",
    index_digest: "sha256:72f53a2a809fdfc362f1127c9bad23d18e6e240eec894d405d0823f95ac54f45",
    amd64_digest: "sha256:b6d53e9f797bb4b4e3b7b317ec07e4242f33c7e3061af16d18685f6866295e58",
    container_port: 5901,
    client_support: "any standard VNC viewer (TigerVNC RFB)",
};

/// RDP image: xrdp on 3389.
///
/// Verified against the GitHub Container Registry API: the `linux/amd64`
/// manifest exposes `3389/tcp` and has entrypoint `/init`. `linux/arm64` is also
/// published.
pub const RDP_IMAGE: GuiImage = GuiImage {
    reference: "lscr.io/linuxserver/rdesktop:ubuntu-xfce",
    index_digest: "sha256:cbf4ee807472acdea1c8d8483c7801c2a0e9a6ad155d1c103fa6c39b5768fb7b",
    amd64_digest: "sha256:85f5e20fbed17a13be2619aafffedd6df2c3c68076693caf951176f133765062",
    container_port: 3389,
    client_support: "any standard RDP client (xfreerdp, mstsc, Microsoft Remote Desktop)",
};

/// Return the pinned image for a protocol.
pub fn image_for(protocol: GuiProtocol) -> GuiImage {
    match protocol {
        GuiProtocol::Vnc => VNC_IMAGE,
        GuiProtocol::Rdp => RDP_IMAGE,
    }
}

/// Loopback address the desktop port is published on.
///
/// Publishing on `127.0.0.1` (rather than Docker's default `0.0.0.0`) is the
/// single most important security property of this module: it makes the desktop
/// unreachable from outside the VM regardless of NSG configuration.
pub const PUBLISH_ADDRESS: &str = "127.0.0.1";

/// Requested desktop geometry and colour depth.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DesktopGeometry {
    pub resolution: String,
    pub depth: u8,
}

impl Default for DesktopGeometry {
    fn default() -> Self {
        Self {
            resolution: "1920x1080".to_string(),
            depth: 24,
        }
    }
}

/// Everything needed to materialise the container on the VM.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuiInstallPlan {
    pub protocol: GuiProtocol,
    pub image: GuiImage,
    pub container_name: String,
    /// Port published on the VM's loopback interface.
    pub host_port: u16,
    pub geometry: DesktopGeometry,
}

impl GuiInstallPlan {
    /// Build the plan for a protocol. The published host port mirrors the
    /// container port, so the SSH tunnel target is predictable.
    pub fn new(protocol: GuiProtocol, geometry: DesktopGeometry) -> Self {
        let image = image_for(protocol);
        Self {
            protocol,
            image,
            container_name: CONTAINER_NAME.to_string(),
            host_port: image.container_port,
            geometry,
        }
    }

    /// The `-p` value published to Docker, always loopback-bound.
    pub fn publish_spec(&self) -> String {
        format!(
            "{}:{}:{}",
            PUBLISH_ADDRESS, self.host_port, self.image.container_port
        )
    }

    /// Arguments to `docker run`, excluding the leading `docker run` itself.
    ///
    /// The desktop password is *not* present here: it is supplied via
    /// `--env-file`, so it never reaches a process listing or `docker inspect`.
    pub fn docker_run_args(&self, env_file: &str) -> Vec<String> {
        vec![
            "-d".to_string(),
            "--name".to_string(),
            self.container_name.clone(),
            "--restart".to_string(),
            "unless-stopped".to_string(),
            "--shm-size".to_string(),
            "1g".to_string(),
            "--env-file".to_string(),
            env_file.to_string(),
            "--label".to_string(),
            format!("azlin.gui.protocol={}", self.protocol),
            "--label".to_string(),
            format!("azlin.gui.image={}", self.image.reference),
            "-p".to_string(),
            self.publish_spec(),
            self.image.reference.to_string(),
        ]
    }

    /// Environment variables written to the `0600` env-file on the VM.
    ///
    /// `password_expr` is substituted by the shell on the VM (the value is
    /// generated there and never travels through azlin), so entries may contain
    /// a shell variable reference.
    pub fn env_file_entries(&self, password_expr: &str) -> Vec<String> {
        match self.protocol {
            GuiProtocol::Vnc => vec![
                format!("VNC_PW={}", password_expr),
                format!("VNC_RESOLUTION={}", self.geometry.resolution),
                format!("VNC_COL_DEPTH={}", self.geometry.depth),
            ],
            // The RDP image takes its credentials from the container user's
            // password, set with `chpasswd` after start, so only non-secret
            // sizing hints belong in the env-file.
            GuiProtocol::Rdp => vec!["PUID=1000".to_string(), "PGID=1000".to_string()],
        }
    }
}

/// Lifecycle state of the managed container, as reported by the probe script.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ContainerState {
    /// No container named [`CONTAINER_NAME`] exists.
    Missing,
    /// The container exists but is not running.
    Stopped,
    /// The container exists and is running.
    Running,
}

impl ContainerState {
    /// Map a `docker inspect -f {{.State.Status}}` value onto a state.
    pub fn parse(value: &str) -> Self {
        match value.trim() {
            "" | "missing" => Self::Missing,
            "running" => Self::Running,
            _ => Self::Stopped,
        }
    }
}

/// Parsed result of the detection probe run on the VM.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuiStatus {
    /// A `docker` binary is on `PATH`.
    pub docker_present: bool,
    /// The Docker daemon is reachable as the connecting user (i.e. the user is
    /// in the `docker` group and the daemon is running).
    pub docker_usable: bool,
    pub container_state: ContainerState,
    /// Protocol recorded on the container label, when a container exists.
    pub protocol: Option<GuiProtocol>,
    /// Loopback port published on the VM, when a container exists.
    pub host_port: Option<u16>,
}

impl GuiStatus {
    /// Whether a containerised desktop is installed at all (running or stopped).
    pub fn is_installed(&self) -> bool {
        self.container_state != ContainerState::Missing
    }

    /// The port to tunnel to, falling back to the image default when Docker did
    /// not report one.
    pub fn effective_port(&self) -> u16 {
        self.host_port.unwrap_or_else(|| {
            image_for(self.protocol.unwrap_or(GuiProtocol::Vnc)).container_port
        })
    }
}

/// The exact command a user should run to install the containerised desktop.
pub fn suggested_install_command(vm_identifier: &str) -> String {
    if vm_identifier.is_empty() {
        "azlin gui install".to_string()
    } else {
        format!("azlin gui install {vm_identifier}")
    }
}

/// Actionable message explaining how to get a containerised desktop, tailored to
/// what the probe found on the VM.
///
/// This is what `azlin gui` prints when the VM's own package repositories cannot
/// provide a desktop stack. Every branch names a concrete next command; a
/// generic "GUI setup failed" is the failure mode this exists to prevent.
pub fn no_desktop_remedy(vm_identifier: &str, status: &GuiStatus) -> String {
    if !status.docker_present {
        return "azlin can also run the desktop as a container, but Docker is not installed on \
                the VM.\n  Install Docker (https://docs.docker.com/engine/install/), then run: \
                sudo systemctl enable --now docker"
            .to_string();
    }
    if !status.docker_usable {
        return "azlin can also run the desktop as a container, but the Docker daemon is not \
                reachable as this user.\n  On the VM run:\n    sudo systemctl enable --now \
                docker\n    sudo usermod -aG docker \"$USER\"   # then reconnect for the new \
                group to apply"
            .to_string();
    }
    format!(
        "If this VM's package repositories have no desktop stack, install the containerised \
         desktop instead:\n  {}",
        suggested_install_command(vm_identifier)
    )
}

// ---------------------------------------------------------------------------
// Script generation
// ---------------------------------------------------------------------------

/// Shell-quote a value for safe single-quoted embedding.
fn sq(value: &str) -> String {
    format!("'{}'", value.replace('\'', r"'\''"))
}

/// Build the detection probe.
///
/// Emits `key=value` lines on stdout and always exits `0`, so a non-zero exit
/// unambiguously means the SSH transport failed rather than "not installed".
pub fn build_detect_script() -> String {
    format!(
        "set -u; \
         if command -v docker >/dev/null 2>&1; then echo docker_present=true; else echo docker_present=false; echo docker_usable=false; echo container_state=missing; exit 0; fi; \
         if docker info >/dev/null 2>&1; then echo docker_usable=true; else echo docker_usable=false; echo container_state=missing; exit 0; fi; \
         state=$(docker inspect -f '{{{{.State.Status}}}}' {name} 2>/dev/null || echo missing); \
         echo \"container_state=$state\"; \
         if [ \"$state\" != missing ]; then \
           echo \"protocol=$(docker inspect -f '{{{{index .Config.Labels \"azlin.gui.protocol\"}}}}' {name} 2>/dev/null)\"; \
           echo \"host_port=$(docker inspect -f '{{{{range $p, $c := .NetworkSettings.Ports}}}}{{{{range $c}}}}{{{{.HostPort}}}}{{{{end}}}}{{{{end}}}}' {name} 2>/dev/null)\"; \
         fi; \
         exit 0",
        name = sq(CONTAINER_NAME),
    )
}

/// Parse the `key=value` output of [`build_detect_script`].
pub fn parse_detect_output(output: &str) -> GuiStatus {
    let mut status = GuiStatus {
        docker_present: false,
        docker_usable: false,
        container_state: ContainerState::Missing,
        protocol: None,
        host_port: None,
    };

    for line in output.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let value = value.trim();
        match key.trim() {
            "docker_present" => status.docker_present = value == "true",
            "docker_usable" => status.docker_usable = value == "true",
            "container_state" => status.container_state = ContainerState::parse(value),
            "protocol" => status.protocol = GuiProtocol::parse(value),
            "host_port" => status.host_port = value.parse().ok(),
            _ => {}
        }
    }

    status
}

/// Build the install script.
///
/// The script is idempotent: an existing container whose image and protocol
/// already match the plan is left in place (and started if stopped); anything
/// else is removed and recreated. Every failure mode is reported with a distinct
/// `azlin-error:` marker and a distinct exit code rather than being swallowed.
///
/// The script never uses `sudo` and never modifies host configuration. It reads
/// free disk space and refuses to proceed if there is too little, rather than
/// attempting to make room.
pub fn build_install_script(plan: &GuiInstallPlan) -> String {
    let name = sq(&plan.container_name);
    let image = sq(plan.image.reference);
    let protocol = plan.protocol.as_str();
    let run_args = plan
        .docker_run_args("\"$ENV_FILE\"")
        .iter()
        .map(|a| {
            // The env-file placeholder must stay an unquoted shell expansion.
            if a == "\"$ENV_FILE\"" {
                a.clone()
            } else {
                sq(a)
            }
        })
        .collect::<Vec<_>>()
        .join(" ");

    let env_lines = plan
        .env_file_entries("$AZLIN_GUI_PW")
        .iter()
        .map(|entry| format!("printf '%s\\n' \"{entry}\" >> \"$ENV_FILE\";"))
        .collect::<Vec<_>>()
        .join(" ");

    // RDP authenticates against the container user's own password, so it is set
    // after the container starts. VNC consumes VNC_PW from the env-file, and its
    // password blob is copied out for the local viewer.
    let post_start = match plan.protocol {
        GuiProtocol::Vnc => format!(
            "for _ in $(seq 1 30); do \
               if docker exec {name} test -f {cpath} >/dev/null 2>&1; then break; fi; sleep 2; \
             done; \
             if ! docker cp {name}:{cpath} \"$STATE_DIR/vncpasswd\" >/dev/null 2>&1; then \
               echo 'azlin-error: the VNC container started but never wrote its password file' >&2; exit 6; \
             fi; \
             chmod 600 \"$STATE_DIR/vncpasswd\"",
            name = name,
            cpath = sq(CONTAINER_VNC_PASSWD_PATH),
        ),
        GuiProtocol::Rdp => format!(
            "for _ in $(seq 1 30); do \
               if docker exec {name} id {user} >/dev/null 2>&1; then break; fi; sleep 2; \
             done; \
             if ! printf '%s:%s' {user} \"$AZLIN_GUI_PW\" | docker exec -i {name} chpasswd >/dev/null 2>&1; then \
               echo 'azlin-error: could not set the RDP desktop password inside the container' >&2; exit 6; \
             fi; \
             printf '%s\\n' \"$AZLIN_GUI_PW\" > \"$STATE_DIR/rdppasswd\"; \
             chmod 600 \"$STATE_DIR/rdppasswd\"",
            name = name,
            user = sq(RDP_USERNAME),
        ),
    };

    let publish_plain = format!("{}:{}", PUBLISH_ADDRESS, plan.host_port);
    let publish_quoted = sq(&publish_plain);

    format!(
        "set -u; \
         if ! command -v docker >/dev/null 2>&1; then \
           echo 'azlin-error: docker is not installed on this VM' >&2; exit 2; fi; \
         if ! docker info >/dev/null 2>&1; then \
           echo 'azlin-error: the docker daemon is not reachable as this user' >&2; exit 3; fi; \
         DROOT=$(docker info -f '{{{{.DockerRootDir}}}}' 2>/dev/null || true); \
         [ -n \"$DROOT\" ] || DROOT=/var/lib/docker; \
         AVAIL=$(df -Pk \"$DROOT\" 2>/dev/null || df -Pk /); \
         AVAIL=$(echo \"$AVAIL\" | awk 'NR==2 {{print $4}}'); \
         if [ -n \"$AVAIL\" ] && [ \"$AVAIL\" -lt {required_kib} ]; then \
           echo \"azlin-error: less than 4 GiB free for the container image on the docker data root $DROOT (${{AVAIL}} KiB available)\" >&2; exit 7; fi; \
         STATE_DIR=\"$HOME/.azlin/gui\"; mkdir -p \"$STATE_DIR\"; chmod 700 \"$STATE_DIR\"; \
         CUR=$(docker inspect -f '{{{{.Config.Image}}}}' {name} 2>/dev/null || true); \
         CUR_PROTO=$(docker inspect -f '{{{{index .Config.Labels \"azlin.gui.protocol\"}}}}' {name} 2>/dev/null || true); \
         if [ \"$CUR\" = {image} ] && [ \"$CUR_PROTO\" = {protocol} ]; then \
           docker start {name} >/dev/null 2>&1 || true; \
           echo 'azlin-result: already-installed'; exit 0; \
         fi; \
         if [ -n \"$CUR\" ]; then docker rm -f {name} >/dev/null 2>&1 || true; fi; \
         if ! PULL_OUT=$(docker pull {image} 2>&1); then \
           echo \"azlin-error: failed to pull the desktop container image: $PULL_OUT\" >&2; exit 4; fi; \
         PULLED_DIGEST=$(docker inspect -f '{{{{index .RepoDigests 0}}}}' {image} 2>/dev/null || true); \
         PULLED_DIGEST=${{PULLED_DIGEST#*@}}; \
         if [ -n \"$PULLED_DIGEST\" ] && [ \"$PULLED_DIGEST\" != {index_digest} ] && [ \"$PULLED_DIGEST\" != {amd64_digest} ]; then \
           docker rmi {image} >/dev/null 2>&1 || true; \
           echo \"azlin-error: pulled image digest $PULLED_DIGEST for {image} does not match the digest azlin pinned ({index_digest}, or the linux/amd64 manifest {amd64_digest}); the tag may have moved on the registry, refusing to run an unverified image\" >&2; exit 10; fi; \
         if command -v openssl >/dev/null 2>&1; then AZLIN_GUI_PW=$(openssl rand -hex 16); \
         else AZLIN_GUI_PW=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \\n'); fi; \
         if [ -z \"$AZLIN_GUI_PW\" ]; then \
           echo 'azlin-error: could not generate a desktop password on the VM' >&2; exit 5; fi; \
         ENV_FILE=\"$STATE_DIR/env\"; \
         : > \"$ENV_FILE\"; chmod 600 \"$ENV_FILE\"; \
         {env_lines} \
         if ! RUN_OUT=$(docker run {run_args} 2>&1); then \
           if ss -ltn 2>/dev/null | grep -q {publish}; then \
             echo 'azlin-error: {publish_plain} is already in use on the VM' >&2; exit 8; fi; \
           echo \"azlin-error: failed to start the desktop container: $RUN_OUT\" >&2; exit 9; fi; \
         {post_start}; \
         echo 'azlin-result: installed'",
        name = name,
        image = image,
        protocol = sq(protocol),
        required_kib = REQUIRED_FREE_KIB,
        index_digest = sq(plan.image.index_digest),
        amd64_digest = sq(plan.image.amd64_digest),
        publish = publish_quoted,
        publish_plain = publish_plain,
        env_lines = env_lines,
        run_args = run_args,
        post_start = post_start,
    )
}

/// Build the script that starts an already-installed but stopped container.
///
/// This is a connect-time repair, not an install: it never pulls an image and
/// never creates a container.
pub fn build_start_script() -> String {
    format!(
        "set -u; \
         if ! docker start {name} >/dev/null 2>&1; then \
           echo 'azlin-error: the desktop container exists but could not be started' >&2; exit 1; fi",
        name = sq(CONTAINER_NAME),
    )
}

/// Build the script that removes the managed container and its state.
pub fn build_uninstall_script() -> String {
    format!(
        "set -u; \
         docker rm -f {name} >/dev/null 2>&1 || true; \
         rm -rf \"$HOME/.azlin/gui\"",
        name = sq(CONTAINER_NAME),
    )
}

/// Classify an install-script exit code into an actionable message.
pub fn describe_install_failure(exit_code: i32, stderr: &str) -> String {
    let detail = stderr
        .lines()
        .find_map(|l| l.trim().strip_prefix("azlin-error:"))
        .map(str::trim)
        .unwrap_or("")
        .to_string();

    let remedy = match exit_code {
        2 => "Install Docker on the VM (https://docs.docker.com/engine/install/), then:\n  sudo systemctl enable --now docker",
        3 => "Start Docker and add your user to the docker group on the VM:\n  sudo systemctl enable --now docker\n  sudo usermod -aG docker \"$USER\"   # then reconnect",
        4 => "Check the VM's outbound network access and retry. If the VM has no internet egress, mirror the image into a registry it can reach.",
        5 | 6 => "Re-run the install. If it keeps failing, remove the container with 'docker rm -f azlin-gui' on the VM and try again.",
        7 => "Free disk space on the VM (the desktop image needs roughly 2-4 GiB) and re-run.",
        8 => "Another process is already listening on that loopback port. Stop it, or remove the stale container with 'docker rm -f azlin-gui'.",
        9 => "Inspect the container logs on the VM:\n  docker logs azlin-gui",
        10 => "The image azlin pulled does not match the digest it has pinned for this tag — neither the multi-arch index digest that `docker pull` normally records, nor the linux/amd64 child manifest digest. This usually means the upstream tag moved: a legitimate new release, or a registry compromise. Do not retry blindly: compare the reported digest against the registry yourself before deciding whether to update azlin's pinned digests.",
        _ => "Re-run with --verbose for the full remote output.",
    };

    if detail.is_empty() {
        format!("GUI install failed (exit {exit_code}).\n{remedy}")
    } else {
        format!("GUI install failed: {detail}.\n{remedy}")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vnc_plan() -> GuiInstallPlan {
        GuiInstallPlan::new(GuiProtocol::Vnc, DesktopGeometry::default())
    }

    fn rdp_plan() -> GuiInstallPlan {
        GuiInstallPlan::new(GuiProtocol::Rdp, DesktopGeometry::default())
    }

    fn all_scripts() -> Vec<String> {
        vec![
            build_install_script(&vnc_plan()),
            build_install_script(&rdp_plan()),
            build_detect_script(),
            build_start_script(),
            build_uninstall_script(),
        ]
    }

    // -- protocol ----------------------------------------------------------

    #[test]
    fn protocol_round_trips_through_its_wire_name() {
        for p in [GuiProtocol::Vnc, GuiProtocol::Rdp] {
            assert_eq!(GuiProtocol::parse(p.as_str()), Some(p));
            assert_eq!(GuiProtocol::parse(&p.to_string().to_uppercase()), Some(p));
        }
        assert_eq!(GuiProtocol::parse("spice"), None);
        assert_eq!(GuiProtocol::parse(""), None);
    }

    // -- plan --------------------------------------------------------------

    #[test]
    fn vnc_and_rdp_select_distinct_pinned_images_and_ports() {
        assert_eq!(vnc_plan().image.reference, "consol/debian-xfce-vnc:v2.0.4");
        assert_eq!(vnc_plan().host_port, 5901);
        assert_eq!(
            rdp_plan().image.reference,
            "lscr.io/linuxserver/rdesktop:ubuntu-xfce"
        );
        assert_eq!(rdp_plan().host_port, 3389);
    }

    #[test]
    fn image_references_are_tag_pinned_not_latest() {
        for image in [VNC_IMAGE, RDP_IMAGE] {
            let tag = image
                .reference
                .rsplit_once(':')
                .expect("image reference must carry an explicit tag")
                .1;
            assert_ne!(tag, "latest", "{} must not float on :latest", image.reference);
            for digest in [image.index_digest, image.amd64_digest] {
                assert!(digest.starts_with("sha256:"));
                assert_eq!(digest.len(), "sha256:".len() + 64);
            }
            assert_ne!(
                image.index_digest, image.amd64_digest,
                "{} pins a multi-arch index; its digest differs from the amd64 child",
                image.reference
            );
        }
    }

    #[test]
    fn install_verifies_the_pulled_digest_against_the_pinned_digest_and_fails_closed() {
        for plan in [vnc_plan(), rdp_plan()] {
            let script = build_install_script(&plan);
            assert!(
                script.contains(&sq(plan.image.index_digest)),
                "install script must compare against the pinned index digest, which is what \
                 `docker pull <tag>` records in RepoDigests: {script}"
            );
            assert!(
                script.contains(&sq(plan.image.amd64_digest)),
                "install script must also accept the pinned linux/amd64 child digest: {script}"
            );
            assert!(
                script.contains("RepoDigests"),
                "install script must inspect the pulled image's RepoDigests: {script}"
            );
            assert!(
                script.contains("exit 10"),
                "a digest mismatch must be a distinct, fail-closed exit code: {script}"
            );
            // On mismatch the unverified image must not be left around to run later.
            assert!(script.contains(&format!("docker rmi {}", sq(plan.image.reference))));
        }
    }

    #[test]
    fn published_port_is_always_loopback_bound() {
        for plan in [vnc_plan(), rdp_plan()] {
            assert!(
                plan.publish_spec().starts_with("127.0.0.1:"),
                "publish spec must be loopback bound, got {}",
                plan.publish_spec()
            );
        }
    }

    #[test]
    fn the_novnc_web_port_is_never_published() {
        let script = build_install_script(&vnc_plan());
        assert!(
            !script.contains("6901"),
            "the noVNC web port must not be published"
        );
    }

    #[test]
    fn the_password_is_never_passed_on_the_docker_command_line() {
        for plan in [vnc_plan(), rdp_plan()] {
            let args = plan.docker_run_args("\"$ENV_FILE\"");
            assert!(args.contains(&"--env-file".to_string()));
            assert!(
                !args
                    .iter()
                    .any(|a| a.contains("VNC_PW") || a == "-e" || a == "--env"),
                "secrets must not appear in argv: {args:?}"
            );
        }
    }

    #[test]
    fn vnc_env_file_carries_geometry_and_password_reference() {
        let plan = GuiInstallPlan::new(
            GuiProtocol::Vnc,
            DesktopGeometry {
                resolution: "1280x800".to_string(),
                depth: 16,
            },
        );
        let entries = plan.env_file_entries("$PW");
        assert!(entries.contains(&"VNC_PW=$PW".to_string()));
        assert!(entries.contains(&"VNC_RESOLUTION=1280x800".to_string()));
        assert!(entries.contains(&"VNC_COL_DEPTH=16".to_string()));
    }

    #[test]
    fn rdp_env_file_carries_no_secret() {
        let entries = rdp_plan().env_file_entries("$PW");
        assert!(
            entries.iter().all(|e| !e.contains("$PW")),
            "the RDP password is set with chpasswd, not through the env-file"
        );
    }

    // -- security invariants ----------------------------------------------

    #[test]
    fn no_generated_script_touches_azure_networking() {
        for script in all_scripts() {
            let lowered = script.to_ascii_lowercase();
            for forbidden in ["nsg", "az network", "network-security", "network security"] {
                assert!(
                    !lowered.contains(forbidden),
                    "generated scripts must never touch Azure networking ({forbidden}): {script}"
                );
            }
            assert!(
                !lowered.contains("az vm") && !lowered.split_whitespace().any(|w| w == "az"),
                "generated scripts must emit no az command: {script}"
            );
        }
    }

    #[test]
    fn no_generated_script_uses_sudo() {
        for script in all_scripts() {
            assert!(
                !script.contains("sudo"),
                "generated scripts must not require root: {script}"
            );
        }
    }

    #[test]
    fn no_generated_script_publishes_on_a_wildcard_address() {
        for script in all_scripts() {
            assert!(
                !script.contains("0.0.0.0"),
                "the desktop must never be published on a wildcard address: {script}"
            );
        }
    }

    #[test]
    fn install_creates_its_state_directory_and_env_file_with_tight_modes() {
        let script = build_install_script(&vnc_plan());
        assert!(script.contains("chmod 700 \"$STATE_DIR\""));
        assert!(script.contains("chmod 600 \"$ENV_FILE\""));
        assert!(script.contains("chmod 600 \"$STATE_DIR/vncpasswd\""));
    }

    #[test]
    fn rdp_install_stores_its_password_with_a_tight_mode() {
        let script = build_install_script(&rdp_plan());
        assert!(script.contains("chmod 600 \"$STATE_DIR/rdppasswd\""));
    }

    // -- install script behaviour -----------------------------------------

    #[test]
    fn install_checks_docker_before_anything_else() {
        let script = build_install_script(&vnc_plan());
        let docker_check = script.find("command -v docker").unwrap();
        let pull = script.find("docker pull").unwrap();
        assert!(docker_check < pull);
    }

    #[test]
    fn install_refuses_to_start_without_enough_free_space() {
        let script = build_install_script(&vnc_plan());
        assert!(script.contains(&REQUIRED_FREE_KIB.to_string()));
        assert!(script.contains("exit 7"));
    }

    #[test]
    fn install_is_idempotent_for_a_matching_container() {
        let script = build_install_script(&vnc_plan());
        assert!(script.contains("azlin-result: already-installed"));
        assert!(script.contains("docker start 'azlin-gui'"));
    }

    #[test]
    fn install_recreates_a_container_built_from_a_different_image() {
        let script = build_install_script(&vnc_plan());
        assert!(script.contains("docker rm -f 'azlin-gui'"));
    }

    #[test]
    fn install_survives_reboot_via_a_restart_policy() {
        assert!(build_install_script(&vnc_plan()).contains("'--restart' 'unless-stopped'"));
    }

    #[test]
    fn install_emits_a_completion_marker() {
        assert!(build_install_script(&vnc_plan()).contains("azlin-result: installed"));
    }

    #[test]
    fn every_install_failure_mode_has_a_distinct_exit_code() {
        let script = build_install_script(&vnc_plan());
        for code in [2, 3, 4, 5, 7, 8, 9, 10] {
            assert!(
                script.contains(&format!("exit {code}")),
                "install script is missing exit {code}"
            );
        }
        assert!(build_install_script(&vnc_plan()).contains("exit 6"));
    }

    #[test]
    fn install_labels_the_container_so_detection_needs_no_local_state() {
        let script = build_install_script(&rdp_plan());
        assert!(script.contains("'azlin.gui.protocol=rdp'"));
        assert!(script.contains("'azlin.gui.image=lscr.io/linuxserver/rdesktop:ubuntu-xfce'"));
    }

    // -- detection ---------------------------------------------------------

    #[test]
    fn detect_always_exits_zero_so_ssh_failures_stay_distinguishable() {
        assert!(build_detect_script().trim_end().ends_with("exit 0"));
    }

    #[test]
    fn parse_detect_output_reads_a_running_vnc_container() {
        let status = parse_detect_output(
            "docker_present=true\ndocker_usable=true\ncontainer_state=running\nprotocol=vnc\nhost_port=5901\n",
        );
        assert!(status.docker_present && status.docker_usable);
        assert_eq!(status.container_state, ContainerState::Running);
        assert_eq!(status.protocol, Some(GuiProtocol::Vnc));
        assert_eq!(status.host_port, Some(5901));
        assert!(status.is_installed());
        assert_eq!(status.effective_port(), 5901);
    }

    #[test]
    fn parse_detect_output_reads_a_stopped_rdp_container() {
        let status = parse_detect_output(
            "docker_present=true\ndocker_usable=true\ncontainer_state=exited\nprotocol=rdp\nhost_port=3389\n",
        );
        assert_eq!(status.container_state, ContainerState::Stopped);
        assert_eq!(status.protocol, Some(GuiProtocol::Rdp));
        assert!(status.is_installed());
    }

    #[test]
    fn parse_detect_output_handles_a_vm_without_docker() {
        let status = parse_detect_output(
            "docker_present=false\ndocker_usable=false\ncontainer_state=missing\n",
        );
        assert!(!status.docker_present);
        assert!(!status.is_installed());
    }

    #[test]
    fn parse_detect_output_ignores_unrelated_login_shell_noise() {
        let status = parse_detect_output(
            "Welcome to Ubuntu\nsome banner line\ndocker_present=true\ndocker_usable=true\ncontainer_state=running\nprotocol=vnc\nhost_port=5901\n",
        );
        assert_eq!(status.container_state, ContainerState::Running);
        assert_eq!(status.host_port, Some(5901));
    }

    #[test]
    fn effective_port_falls_back_to_the_image_default() {
        let status = parse_detect_output(
            "docker_present=true\ndocker_usable=true\ncontainer_state=running\nprotocol=rdp\n",
        );
        assert_eq!(status.host_port, None);
        assert_eq!(status.effective_port(), 3389);
    }

    #[test]
    fn container_state_maps_docker_status_values() {
        assert_eq!(ContainerState::parse("running"), ContainerState::Running);
        assert_eq!(ContainerState::parse("exited"), ContainerState::Stopped);
        assert_eq!(ContainerState::parse("created"), ContainerState::Stopped);
        assert_eq!(ContainerState::parse("missing"), ContainerState::Missing);
        assert_eq!(ContainerState::parse(""), ContainerState::Missing);
    }

    // -- remedies ----------------------------------------------------------

    #[test]
    fn missing_docker_remedy_is_distro_neutral() {
        let status = parse_detect_output("docker_present=false\n");
        let msg = no_desktop_remedy("vm1", &status);
        assert!(msg.contains("docs.docker.com"));
        for distro_specific in ["apt-get", "dnf", "yum", "moby", "zypper", "pacman", "apk"] {
            assert!(
                !msg.contains(distro_specific),
                "remedy must not assume a package manager ({distro_specific}): {msg}"
            );
        }
    }

    #[test]
    fn unusable_docker_remedy_names_the_docker_group() {
        let status = parse_detect_output("docker_present=true\ndocker_usable=false\n");
        assert!(no_desktop_remedy("vm1", &status).contains("usermod -aG docker"));
    }

    #[test]
    fn missing_container_remedy_names_the_exact_install_command() {
        let status =
            parse_detect_output("docker_present=true\ndocker_usable=true\ncontainer_state=missing");
        assert!(no_desktop_remedy("simard", &status).contains("azlin gui install simard"));
        assert_eq!(suggested_install_command(""), "azlin gui install");
    }

    #[test]
    fn install_failures_are_classified_with_actionable_remedies() {
        let cases = [
            (2, "docs.docker.com"),
            (3, "usermod -aG docker"),
            (4, "outbound network access"),
            (5, "Re-run the install"),
            (6, "Re-run the install"),
            (7, "Free disk space"),
            (8, "already listening"),
            (9, "docker logs azlin-gui"),
            (10, "does not match the digest"),
        ];
        for (code, needle) in cases {
            let msg = describe_install_failure(code, "azlin-error: something went wrong\n");
            assert!(
                msg.contains(needle),
                "exit {code} remedy should mention {needle:?}, got: {msg}"
            );
            assert!(msg.contains("something went wrong"));
        }
    }

    #[test]
    fn an_unclassified_failure_still_says_what_to_do() {
        let msg = describe_install_failure(42, "");
        assert!(msg.contains("exit 42"));
        assert!(msg.contains("--verbose"));
    }

    // -- shell safety ------------------------------------------------------

    #[test]
    fn single_quotes_in_values_cannot_break_out_of_quoting() {
        assert_eq!(sq("it's"), r"'it'\''s'");
    }

    #[test]
    fn generated_scripts_are_syntactically_valid_shell() {
        use std::io::Write;
        use std::process::{Command, Stdio};

        for script in all_scripts() {
            let mut child = Command::new("bash")
                .arg("-n")
                .stdin(Stdio::piped())
                .stdout(Stdio::null())
                .stderr(Stdio::piped())
                .spawn()
                .expect("bash must be available to syntax-check generated scripts");
            child
                .stdin
                .as_mut()
                .unwrap()
                .write_all(script.as_bytes())
                .unwrap();
            let out = child.wait_with_output().unwrap();
            assert!(
                out.status.success(),
                "generated script is not valid shell: {}\n{}",
                String::from_utf8_lossy(&out.stderr),
                script
            );
        }
    }

    #[test]
    fn generated_scripts_are_single_line_so_they_survive_ssh_argument_passing() {
        for script in all_scripts() {
            assert!(
                !script.contains('\n'),
                "generated scripts must be a single line: {script}"
            );
        }
    }
}
