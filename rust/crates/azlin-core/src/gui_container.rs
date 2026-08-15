//! Containerised remote-desktop planner for `azlin gui install`.
//!
//! # Architecture
//!
//! `azlin gui install` provisions a remote desktop that can serve **either**
//! protocol, because which one will be used is not known until the user
//! connects. It installs three things onto the VM's Docker, and nothing onto
//! the VM itself:
//!
//! * **The desktop** — an X server, a window manager, an XFCE session and a
//!   genuine TigerVNC RFB server, from one pinned image ([`DESKTOP_IMAGE`]).
//!   This container publishes *both* loopback ports.
//! * **The VNC server** — already part of that image; it is what listens on
//!   [`RFB_PORT`].
//! * **The RDP server** — a second, small container ([`BRIDGE_CONTAINER_NAME`])
//!   running `xrdp`, built on the VM as a thin layer *on top of the desktop
//!   image that was just pulled*, so no second base image is ever downloaded.
//!
//! The seam between them is a single **RFB endpoint on the VM's loopback
//! interface**, port [`RFB_PORT`]. Everything converges on it:
//!
//! ```text
//!   vncviewer  ──ssh tunnel──▶ 127.0.0.1:5901 ─┐
//!                                              ├─▶ the one desktop session
//!   RDP client ──ssh tunnel──▶ 127.0.0.1:3389 ─┘
//!                          (azlin-gui-rdp: xrdp bridging RDP → RFB)
//! ```
//!
//! ## Why a second container rather than a second image
//!
//! The bridge container joins the desktop container's *network namespace*
//! (`--network container:azlin-gui`). Three consequences follow, and they are
//! the whole reason for this shape:
//!
//! 1. `127.0.0.1:5901` inside the bridge **is** the desktop's RFB port, so the
//!    bridge needs no inter-container networking, no Docker network, and no
//!    address to discover.
//! 2. A namespace-sharing container cannot publish ports of its own, so *all*
//!    publishing stays on the desktop container, where the loopback-only
//!    invariant is already enforced in one place.
//! 3. Because xrdp's `libvnc.so` module connects to that endpoint as an ordinary
//!    VNC *client*, an RDP user and a VNC user see the **same live session** —
//!    the same windows, the same cursor — exactly as two VNC viewers would.
//!    Switching protocol does not restart, reinstall or replace anything.
//!
//! Rejected alternatives, and why:
//!
//! * *One protocol per image* (the previous design): makes the protocol an
//!   install-time property, which is precisely what this redesign removes. It
//!   also means the two protocols could never share a session.
//! * *One image running both servers, pulled ready-made*: no maintained,
//!   digest-pinnable image does this. Publishing our own would add a registry
//!   and a release process to azlin.
//! * *Two independent desktop containers, one per protocol*: doubles the
//!   ~2 GiB footprint and gives two unrelated sessions, so a user who connects
//!   over RDP after VNC would silently lose their work.
//! * *Installing xrdp natively on the VM*: reintroduces a package manager, and
//!   with it distro-specific behaviour, into a path that is deliberately
//!   distro-neutral — Docker is its only host requirement.
//!
//! ## Honest cost
//!
//! Both protocol servers are installed per-GUI-VM, at `azlin gui install` time.
//! The desktop image is ~2 GiB; the bridge adds one `apt-get install xrdp`
//! layer of roughly 30 MiB and about a minute of build time on top of it. A VM
//! that never runs `azlin gui install` pays **nothing at all** — no image, no
//! disk, no boot time. That is the point of installing here rather than at VM
//! provisioning time.
//!
//! Because the RFB endpoint is the only contract, the bridge works identically
//! against the native `vncserver` that `azlin gui` starts on VMs whose
//! repositories do carry a desktop stack.
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
//!   is unreachable from the network even if a permissive NSG rule existed. Both
//!   the RFB port and the RDP port are published by the same container, through
//!   the same loopback-bound [`PUBLISH_ADDRESS`].
//! * No network-security-group rule is ever created, modified or referenced. This
//!   module emits no `az` command of any kind. Access is expected to happen
//!   exclusively over azlin's existing SSH/bastion tunnel.
//! * The web (noVNC) port of the desktop image is deliberately **not** published.
//! * Images are pinned by tag **and** verified by digest after every pull: the
//!   install script compares the `RepoDigests` entry Docker records for the
//!   pulled image against [`GuiImage::index_digest`] and refuses to run the
//!   container (removing the pulled image and exiting non-zero) on a mismatch.
//!   A tag is mutable — a compromised or careless registry can repoint
//!   `consol/debian-xfce-vnc:v2.0.4` to different bytes without changing the
//!   string azlin pulls — so the tag alone is not a provenance guarantee. The
//!   digest check is skipped (not failed) when Docker reports no `RepoDigests`
//!   at all, which happens only for images that were not pulled from a
//!   registry; every image `azlin gui install` runs is freshly pulled, so this
//!   is a defensive fallback, not the expected path.
//! * The desktop always has a password. The password is generated on the VM and
//!   passed to Docker through a `0600` env-file, so it never appears in a process
//!   listing or in `docker inspect` output.
//! * No generated script uses `sudo`, installs a host package, or modifies any
//!   host configuration. Docker is the only thing touched on the VM.
//! * The bridge's xrdp is configured with `password=ask`: the desktop password
//!   is never written into the bridge image, which is stored unencrypted in the
//!   VM's Docker image store.
//!
//! # Password strength, stated honestly
//!
//! The generated password is 32 hex characters. The RFB protocol truncates
//! passwords to **8 bytes** (RFC 6143 §7.2.2): everything past the eighth
//! character is discarded before the DES obfuscation, which is why a VNC
//! `passwd` file is always exactly 8 bytes long. Only the first 8 hex characters
//! therefore survive, giving `8 * 4 = 32` bits of effective entropy no matter how
//! long the generated secret is. The RDP bridge inherits exactly the same
//! ceiling, because it authenticates against the very same RFB endpoint.
//!
//! Do not restate this as "128-bit" security. It is not. 32 bits is acceptable
//! here *only* because both ports are bound to `127.0.0.1` on the VM and are
//! reachable solely through the SSH tunnel, so there is no network-facing
//! brute-force surface. It would not be acceptable for an exposed port.

use serde::{Deserialize, Serialize};

/// Remote-desktop wire protocol used to *connect* to an already-installed
/// desktop.
///
/// This is deliberately not an install-time concern: `azlin gui install`
/// provisions both protocol servers, and both variants reach the same desktop
/// session over the same [`RFB_PORT`] endpoint — VNC directly, RDP through the
/// xrdp bridge container.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum GuiProtocol {
    /// RFB, consumed by a standard VNC viewer. The default.
    #[default]
    Vnc,
    /// RDP, consumed by a standard RDP client, bridged to RFB by the xrdp
    /// sidecar container.
    Rdp,
}

impl GuiProtocol {
    /// Lowercase wire name, used in generated scripts and user-facing messages.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Vnc => "vnc",
            Self::Rdp => "rdp",
        }
    }

    /// Parse the wire name.
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

/// Directory on the VM holding the generated env-file, the exported RFB
/// password blob and the plaintext desktop password. Created `0700`; the files
/// inside are `0600`.
pub const STATE_DIR: &str = "$HOME/.azlin/gui";

/// Path on the VM of the RFB authentication blob exported from the container.
///
/// The blob is produced by the container's own `vncpasswd`, then copied out with
/// `docker cp`. Copying out (rather than bind-mounting over the container's
/// `.vnc` directory) avoids shadowing files the image's startup script writes
/// there, and avoids reimplementing the VNC password format locally.
pub const HOST_VNC_PASSWD_PATH: &str = "$HOME/.azlin/gui/vncpasswd";

/// Path on the VM of the plaintext desktop password, written `0600`.
///
/// A VNC viewer authenticates with the binary blob above, but the RDP bridge
/// presents an ordinary password prompt that must be answered with the
/// plaintext, so both forms are kept.
pub const HOST_DESKTOP_PASSWD_PATH: &str = "$HOME/.azlin/gui/desktoppw";

/// Path inside the container of the authentication blob to export.
pub const CONTAINER_VNC_PASSWD_PATH: &str = "/headless/.vnc/passwd";

/// Loopback RFB port. The seam between the desktop and every protocol server:
/// the container publishes it, the native `vncserver` path listens on it, and
/// the host's RDP bridge dials it.
pub const RFB_PORT: u16 = 5901;

/// Loopback port the RDP bridge container listens on.
pub const RDP_BRIDGE_PORT: u16 = 3389;

/// Username presented to the RDP bridge. The bridge authenticates against the
/// RFB endpoint, which has no concept of users, so this is a placeholder that
/// xrdp's `libvnc` module ignores. Only the password is meaningful.
pub const RDP_BRIDGE_USERNAME: &str = "na";

/// Name of the sidecar container that serves RDP.
pub const BRIDGE_CONTAINER_NAME: &str = "azlin-gui-rdp";

/// Tag of the bridge image built on the VM.
///
/// Versioned so that changing the generated Dockerfile forces a rebuild rather
/// than silently reusing a stale image.
pub const BRIDGE_IMAGE_TAG: &str = "azlin-gui-rdp:1";

/// xrdp session-section name the bridge autoruns, skipping the session chooser.
const BRIDGE_SESSION_NAME: &str = "azlin";

/// Free space the install requires on the Docker data root, in KiB (4 GiB).
///
/// The desktop image is roughly 2 GiB compressed; 4 GiB leaves room to unpack
/// it without filling the disk.
const REQUIRED_FREE_KIB: u64 = 4 * 1024 * 1024;

/// The pinned desktop container image.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct GuiImage {
    /// Fully qualified image reference including the pinned tag.
    pub reference: &'static str,
    /// Digest of the `linux/amd64` manifest at the time of pinning. The install
    /// script (see [`build_install_script`]) checks the digest of the image it
    /// actually pulled against this value and refuses to run on a mismatch, so
    /// a tag that silently moves on the registry is detected and rejected
    /// rather than silently trusted.
    ///
    /// This assumes the VM is `linux/amd64`: azlin currently provisions only
    /// D-series/E-series v5 VMs, which are x86_64. If an ARM VM family is ever
    /// added, this field and the verification must become architecture-aware.
    ///
    /// This is *not* the value Docker reports in `RepoDigests` — see
    /// [`GuiImage::index_digest`], which is what the install script compares.
    pub amd64_digest: &'static str,
    /// Digest of the multi-arch **image index** the tag resolves to.
    ///
    /// This is the value the install script compares against, because it is the
    /// value `docker pull <tag>` records: pulling by tag from a multi-arch
    /// repository stores the index digest in `RepoDigests`, on every platform,
    /// including `linux/amd64`. Comparing [`GuiImage::amd64_digest`] instead
    /// rejects even a perfectly good pull.
    pub index_digest: &'static str,
    /// Port the desktop's RFB server listens on inside the container.
    pub container_port: u16,
    /// Human-readable description of which clients can connect.
    pub client_support: &'static str,
}

/// The single desktop image: XFCE on a genuine TigerVNC RFB endpoint.
///
/// Verified against the Docker Hub registry API: the `linux/amd64` manifest
/// exposes `5901/tcp` and `6901/tcp`, has entrypoint
/// `/dockerstartup/vnc_startup.sh`, and reads `VNC_PW`, `VNC_RESOLUTION` and
/// `VNC_COL_DEPTH` from the environment.
///
/// `linuxserver/webtop` was evaluated and rejected: it serves KasmVNC over
/// WebSockets, which a standard RFB viewer cannot speak — and, because the RDP
/// bridge also speaks RFB, it could not serve the RDP path either.
pub const DESKTOP_IMAGE: GuiImage = GuiImage {
    reference: "consol/debian-xfce-vnc:v2.0.4",
    amd64_digest: "sha256:b6d53e9f797bb4b4e3b7b317ec07e4242f33c7e3061af16d18685f6866295e58",
    index_digest: "sha256:72f53a2a809fdfc362f1127c9bad23d18e6e240eec894d405d0823f95ac54f45",
    container_port: RFB_PORT,
    client_support: "any standard VNC viewer, or any RDP client via `azlin gui --protocol rdp`",
};

/// Loopback address every desktop port is published on.
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

/// Everything needed to materialise the desktop container on the VM.
///
/// There is deliberately no protocol field: the container serves one desktop
/// and every protocol reaches it through the same RFB endpoint.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GuiInstallPlan {
    pub image: GuiImage,
    pub container_name: String,
    /// Port published on the VM's loopback interface.
    pub host_port: u16,
    pub geometry: DesktopGeometry,
}

impl Default for GuiInstallPlan {
    fn default() -> Self {
        Self::new(DesktopGeometry::default())
    }
}

impl GuiInstallPlan {
    /// Build the plan. The published host port mirrors the container port, so
    /// the SSH tunnel target is predictable and matches the port the host's RDP
    /// bridge is configured to dial.
    pub fn new(geometry: DesktopGeometry) -> Self {
        Self {
            image: DESKTOP_IMAGE,
            container_name: CONTAINER_NAME.to_string(),
            host_port: DESKTOP_IMAGE.container_port,
            geometry,
        }
    }

    /// The `-p` value publishing the RFB port, always loopback-bound.
    pub fn publish_spec(&self) -> String {
        format!(
            "{}:{}:{}",
            PUBLISH_ADDRESS, self.host_port, self.image.container_port
        )
    }

    /// The `-p` value publishing the RDP port, always loopback-bound.
    ///
    /// This is published by the *desktop* container even though the *bridge*
    /// container serves it: the bridge shares the desktop's network namespace,
    /// and a namespace-sharing container cannot publish ports of its own. The
    /// upside is that every published port in this module goes through one
    /// loopback-bound code path.
    pub fn rdp_publish_spec(&self) -> String {
        format!(
            "{}:{}:{}",
            PUBLISH_ADDRESS, RDP_BRIDGE_PORT, RDP_BRIDGE_PORT
        )
    }

    /// The Dockerfile built on the VM to produce the RDP bridge image.
    ///
    /// It is layered on the desktop image that the install has just pulled, so
    /// the build downloads only the `xrdp` package rather than a second base
    /// image. The desktop image itself is never modified.
    ///
    /// The session section uses `password=ask`, so the desktop password is
    /// never baked into an image layer; the RDP client supplies it per
    /// connection.
    pub fn bridge_dockerfile(&self) -> String {
        format!(
            "FROM {image}\nUSER 0\nRUN apt-get update && apt-get install -y --no-install-recommends xrdp && rm -rf /var/lib/apt/lists/*\nRUN sed -i 's|^#*autorun=.*|autorun={session}|' /etc/xrdp/xrdp.ini\nRUN printf '\\n[{session}]\\nname=azlin-desktop\\nlib=libvnc.so\\nip={addr}\\nport={rfb}\\nusername={user}\\npassword=ask\\n' >> /etc/xrdp/xrdp.ini\n",
            image = self.image.reference,
            session = BRIDGE_SESSION_NAME,
            addr = PUBLISH_ADDRESS,
            rfb = self.image.container_port,
            user = RDP_BRIDGE_USERNAME,
        )
    }

    /// Arguments to `docker run` for the RDP bridge sidecar.
    ///
    /// `--network container:<desktop>` is what makes `{addr}:{rfb}` inside the
    /// bridge resolve to the desktop's RFB server. The base image's entrypoint
    /// starts a whole desktop, so it is replaced outright.
    pub fn bridge_run_args(&self) -> Vec<String> {
        vec![
            "-d".to_string(),
            "--name".to_string(),
            BRIDGE_CONTAINER_NAME.to_string(),
            "--restart".to_string(),
            "unless-stopped".to_string(),
            "--network".to_string(),
            format!("container:{}", self.container_name),
            "--label".to_string(),
            format!("azlin.gui.rdp-port={}", RDP_BRIDGE_PORT),
            "--entrypoint".to_string(),
            "/bin/sh".to_string(),
            BRIDGE_IMAGE_TAG.to_string(),
            "-c".to_string(),
            "mkdir -p /var/run/xrdp && exec xrdp --nodaemon".to_string(),
        ]
    }

    /// Arguments to `docker run`, excluding the leading `docker run` itself.
    ///
    /// The desktop password is *not* present here: it is supplied via a mode
    /// `0600` `--env-file`, so it never reaches the command line and therefore
    /// never appears in a process listing, which is world-readable.
    ///
    /// It is *not* a secret from `docker inspect`: Docker copies `--env-file`
    /// entries into `Config.Env`, so anyone who can talk to the daemon can read
    /// it. That is inherent to an image that takes its password by environment
    /// and is acceptable here, because daemon access already implies full
    /// control of the desktop container. The `ps` exposure is the one worth
    /// closing, and this closes it.
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
            format!("azlin.gui.image={}", self.image.reference),
            "--label".to_string(),
            format!("azlin.gui.rfb-port={}", self.host_port),
            "-p".to_string(),
            self.publish_spec(),
            // Published here, served by the bridge sidecar sharing this
            // container's network namespace.
            "-p".to_string(),
            self.rdp_publish_spec(),
            self.image.reference.to_string(),
        ]
    }

    /// Environment variables written to the `0600` env-file on the VM.
    ///
    /// `password_expr` is substituted by the shell on the VM (the value is
    /// generated there and never travels through azlin), so entries may contain
    /// a shell variable reference.
    pub fn env_file_entries(&self, password_expr: &str) -> Vec<String> {
        vec![
            format!("VNC_PW={}", password_expr),
            format!("VNC_RESOLUTION={}", self.geometry.resolution),
            format!("VNC_COL_DEPTH={}", self.geometry.depth),
        ]
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

/// State of the host's RDP→RFB bridge, which `azlin gui install` provisions.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RdpBridgeState {
    /// No bridge container exists: this desktop was installed by an older
    /// azlin, or no desktop is installed at all.
    Absent,
    /// The bridge container exists but is not running.
    NotRunning,
    /// The bridge container is running and serving `127.0.0.1:3389`.
    Listening,
}

impl RdpBridgeState {
    /// Map the probe's `rdp_bridge=` value onto a state.
    pub fn parse(value: &str) -> Self {
        match value.trim() {
            "listening" => Self::Listening,
            "installed" => Self::NotRunning,
            _ => Self::Absent,
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
    /// Loopback RFB port published on the VM, when a container exists.
    pub host_port: Option<u16>,
    /// State of the host's RDP bridge, independent of the container.
    pub rdp_bridge: RdpBridgeState,
}

impl GuiStatus {
    /// A status describing a VM with nothing installed, used when the probe
    /// itself could not be run.
    pub fn unknown() -> Self {
        Self {
            docker_present: false,
            docker_usable: false,
            container_state: ContainerState::Missing,
            host_port: None,
            rdp_bridge: RdpBridgeState::Absent,
        }
    }

    /// Whether a containerised desktop is installed at all (running or stopped).
    pub fn is_installed(&self) -> bool {
        self.container_state != ContainerState::Missing
    }

    /// The RFB port to tunnel to, falling back to the image default when Docker
    /// did not report one.
    pub fn effective_port(&self) -> u16 {
        self.host_port.unwrap_or(RFB_PORT)
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

/// Actionable message for `--protocol rdp` on a VM whose RDP bridge is not
/// usable.
///
/// The bridge is installed alongside the desktop by `azlin gui install`, so
/// the common cause is a VM with no desktop, or one whose desktop was
/// installed by an older azlin. Both remedies are spelled out because
/// reinstalling the desktop is not always acceptable.
pub fn rdp_bridge_remedy(state: RdpBridgeState) -> String {
    match state {
        RdpBridgeState::Listening => String::new(),
        RdpBridgeState::NotRunning => format!(
            "The RDP bridge container ({BRIDGE_CONTAINER_NAME}) is installed on this VM but is \
             not running.\n  Start it on the VM with:\n    docker start \
             {BRIDGE_CONTAINER_NAME}\n  Or connect over VNC, which does not use the bridge:\n    \
             azlin gui <vm> --protocol vnc"
        ),
        RdpBridgeState::Absent => "This VM has no RDP bridge, so it cannot serve RDP. The \
             bridge is installed alongside the desktop, so a VM with no desktop — or one \
             installed by an older azlin — does not have it.\n  Connect over VNC, which does not \
             use the bridge:\n    azlin gui <vm> --protocol vnc\n  Or (re)install the desktop to \
             add the bridge:\n    azlin gui install <vm> --uninstall\n    azlin gui install <vm>"
            .to_string(),
    }
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
///
/// The probe reports on both halves of the install: the desktop container and
/// the RDP bridge sidecar. They are reported separately because a desktop
/// installed by an older azlin has no bridge, and that must produce a specific
/// diagnosis rather than a generic failure.
///
/// The RFB host port is read from the desktop container's port bindings and is
/// matched on the *container* port, so an unrelated published port can never be
/// mistaken for the desktop's.
pub fn build_detect_script() -> String {
    format!(
        "set -u; \
         if command -v docker >/dev/null 2>&1; then echo docker_present=true; else echo docker_present=false; echo docker_usable=false; echo container_state=missing; echo rdp_bridge=absent; exit 0; fi; \
         if docker info >/dev/null 2>&1; then echo docker_usable=true; else echo docker_usable=false; echo container_state=missing; echo rdp_bridge=absent; exit 0; fi; \
         state=$(docker inspect -f '{{{{.State.Status}}}}' {name} 2>/dev/null || echo missing); \
         echo \"container_state=$state\"; \
         if [ \"$state\" != missing ]; then \
           echo \"host_port=$(docker inspect -f '{{{{with index .NetworkSettings.Ports \"{rfb_port}/tcp\"}}}}{{{{range .}}}}{{{{.HostPort}}}}{{{{end}}}}{{{{end}}}}' {name} 2>/dev/null)\"; \
         fi; \
         bridge=$(docker inspect -f '{{{{.State.Status}}}}' {bridge} 2>/dev/null || echo missing); \
         if [ \"$bridge\" = running ]; then echo rdp_bridge=listening; \
         elif [ \"$bridge\" = missing ]; then echo rdp_bridge=absent; \
         else echo rdp_bridge=installed; fi; \
         exit 0",
        name = sq(CONTAINER_NAME),
        bridge = sq(BRIDGE_CONTAINER_NAME),
        rfb_port = RFB_PORT,
    )
}

/// Parse the `key=value` output of [`build_detect_script`].
pub fn parse_detect_output(output: &str) -> GuiStatus {
    let mut status = GuiStatus::unknown();

    for line in output.lines() {
        let Some((key, value)) = line.split_once('=') else {
            continue;
        };
        let value = value.trim();
        match key.trim() {
            "docker_present" => status.docker_present = value == "true",
            "docker_usable" => status.docker_usable = value == "true",
            "container_state" => status.container_state = ContainerState::parse(value),
            "host_port" => status.host_port = value.parse().ok(),
            "rdp_bridge" => status.rdp_bridge = RdpBridgeState::parse(value),
            _ => {}
        }
    }

    status
}

/// Build the install script.
///
/// The script is idempotent: an existing container whose image already matches
/// the plan is left in place (and started if stopped); anything else is removed
/// and recreated. Every failure mode is reported with a distinct `azlin-error:`
/// marker and a distinct exit code rather than being swallowed.
///
/// It installs both protocol servers, because the protocol is not chosen until
/// connect time: the desktop image already carries the VNC server, and the
/// bridge image adds `xrdp`. The bridge is built as a layer on the image the
/// pull has just fetched, so no second base image is downloaded.
///
/// The script never uses `sudo`, never installs a host package and never
/// modifies host configuration; Docker is the only thing on the VM it touches.
/// It reads free disk space and refuses to proceed if there is too little,
/// rather than attempting to make room.
///
/// A bridge failure is **not** fatal: a desktop that serves VNC but not RDP is
/// far more useful than no desktop, so the script reports `installed-vnc-only`
/// and lets `azlin gui --protocol rdp` produce the specific diagnosis.
pub fn build_install_script(plan: &GuiInstallPlan) -> String {
    let name = sq(&plan.container_name);
    let image = sq(plan.image.reference);
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

    let publish_plain = format!("{}:{}", PUBLISH_ADDRESS, plan.host_port);
    let publish_quoted = sq(&publish_plain);

    // Embedded as a printf '%b' payload so the generated script stays a single
    // line: real newlines become `\n`, and the Dockerfile's own literal `\n`
    // sequences are escaped so printf reproduces them verbatim.
    let dockerfile_literal = sq(&plan
        .bridge_dockerfile()
        .replace('\\', "\\\\")
        .replace('\n', "\\n"));

    let bridge_run_args = plan
        .bridge_run_args()
        .iter()
        .map(|a| sq(a))
        .collect::<Vec<_>>()
        .join(" ");

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
         if [ \"$CUR\" = {image} ]; then \
           docker start {name} >/dev/null 2>&1 || true; \
           docker start {bridge} >/dev/null 2>&1 || true; \
           echo 'azlin-result: already-installed'; exit 0; \
         fi; \
         if [ -n \"$CUR\" ]; then docker rm -f {name} >/dev/null 2>&1 || true; fi; \
         if ! PULL_OUT=$(docker pull {image} 2>&1); then \
           echo \"azlin-error: failed to pull the desktop container image: $PULL_OUT\" >&2; exit 4; fi; \
         PULLED_DIGEST=$(docker inspect -f '{{{{index .RepoDigests 0}}}}' {image} 2>/dev/null || true); \
         PULLED_DIGEST=${{PULLED_DIGEST#*@}}; \
         if [ -n \"$PULLED_DIGEST\" ] && [ \"$PULLED_DIGEST\" != {expected_digest} ] && [ \"$PULLED_DIGEST\" != {expected_platform_digest} ]; then \
           docker rmi {image} >/dev/null 2>&1 || true; \
           echo \"azlin-error: pulled image digest $PULLED_DIGEST for {image} does not match the digest azlin pinned ({expected_digest}, or the linux/amd64 manifest {expected_platform_digest}); the tag may have moved on the registry, refusing to run an unverified image\" >&2; exit 10; fi; \
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
         for _ in $(seq 1 30); do \
           if docker exec {name} test -f {cpath} >/dev/null 2>&1; then break; fi; sleep 2; \
         done; \
         if ! docker cp {name}:{cpath} \"$STATE_DIR/vncpasswd\" >/dev/null 2>&1; then \
           echo 'azlin-error: the desktop container started but never wrote its password file' >&2; exit 6; fi; \
         chmod 600 \"$STATE_DIR/vncpasswd\"; \
         ( umask 077; printf '%s\\n' \"$AZLIN_GUI_PW\" > \"$STATE_DIR/desktoppw\" ); \
         chmod 600 \"$STATE_DIR/desktoppw\"; \
         docker rm -f {bridge} >/dev/null 2>&1 || true; \
         BUILD_CTX=\"$STATE_DIR/build\"; rm -rf \"$BUILD_CTX\"; mkdir -p \"$BUILD_CTX\"; \
         if ! BUILD_OUT=$(printf '%b' {dockerfile} | docker build -t {bridge_tag} -f - \"$BUILD_CTX\" 2>&1); then \
           echo \"azlin-warning: the desktop is installed but the RDP bridge could not be built: $BUILD_OUT\" >&2; \
           echo 'azlin-result: installed-vnc-only'; exit 0; fi; \
         if ! BRIDGE_OUT=$(docker run {bridge_run_args} 2>&1); then \
           echo \"azlin-warning: the desktop is installed but the RDP bridge could not be started: $BRIDGE_OUT\" >&2; \
           echo 'azlin-result: installed-vnc-only'; exit 0; fi; \
         echo 'azlin-result: installed'",
        name = name,
        image = image,
        cpath = sq(CONTAINER_VNC_PASSWD_PATH),
        required_kib = REQUIRED_FREE_KIB,
        expected_digest = sq(plan.image.index_digest),
        expected_platform_digest = sq(plan.image.amd64_digest),
        publish = publish_quoted,
        publish_plain = publish_plain,
        env_lines = env_lines,
        run_args = run_args,
        bridge = sq(BRIDGE_CONTAINER_NAME),
        bridge_tag = sq(BRIDGE_IMAGE_TAG),
        bridge_run_args = bridge_run_args,
        dockerfile = dockerfile_literal,
    )
}

/// Build the script that starts an already-installed but stopped container.
///
/// This is a connect-time repair, not an install: it never pulls an image, never
/// builds one and never creates a container. It starts the bridge too, but
/// tolerates its absence — a desktop installed by an older azlin has no bridge,
/// and VNC must keep working there.
pub fn build_start_script() -> String {
    format!(
        "set -u; \
         if ! docker start {name} >/dev/null 2>&1; then \
           echo 'azlin-error: the desktop container exists but could not be started' >&2; exit 1; fi; \
         docker start {bridge} >/dev/null 2>&1 || true",
        name = sq(CONTAINER_NAME),
        bridge = sq(BRIDGE_CONTAINER_NAME),
    )
}

/// Build the script that removes the managed container and its state.
///
/// It leaves the host's protocol servers alone: they are base-machine
/// components that this command did not install and must not remove.
pub fn build_uninstall_script() -> String {
    format!(
        "set -u; \
         docker rm -f {bridge} >/dev/null 2>&1 || true; \
         docker rmi -f {bridge_tag} >/dev/null 2>&1 || true; \
         docker rm -f {name} >/dev/null 2>&1 || true; \
         rm -rf \"$HOME/.azlin/gui\"",
        name = sq(CONTAINER_NAME),
        bridge = sq(BRIDGE_CONTAINER_NAME),
        bridge_tag = sq(BRIDGE_IMAGE_TAG),
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

    fn plan() -> GuiInstallPlan {
        GuiInstallPlan::default()
    }

    fn all_scripts() -> Vec<String> {
        vec![
            build_install_script(&plan()),
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

    #[test]
    fn vnc_is_the_default_protocol() {
        assert_eq!(GuiProtocol::default(), GuiProtocol::Vnc);
    }

    // -- plan --------------------------------------------------------------

    /// The core of the rework: install is protocol-agnostic. There is exactly
    /// one desktop image, and the protocol never selects it. If a second
    /// *desktop* image ever reappears, the connect-time protocol choice has
    /// silently become an install-time choice again.
    #[test]
    fn install_pins_exactly_one_protocol_agnostic_desktop_image() {
        assert_eq!(plan().image.reference, "consol/debian-xfce-vnc:v2.0.4");
        assert_eq!(plan().host_port, RFB_PORT);
        assert_eq!(plan().image.container_port, RFB_PORT);

        let script = build_install_script(&plan());
        assert_eq!(
            script.matches("docker pull").count(),
            1,
            "install must pull exactly one image"
        );
        assert!(
            !script.contains("rdesktop"),
            "the protocol-specific RDP desktop image must be gone: {script}"
        );
        // The bridge is a layer on the image already pulled, never a second
        // base image: that is what keeps "both servers" affordable.
        assert!(
            plan().bridge_dockerfile().starts_with(&format!("FROM {}\n", DESKTOP_IMAGE.reference)),
            "the bridge must build on the pulled desktop image"
        );
    }

    /// One install must serve both protocols, because the choice is not known
    /// until connect time.
    #[test]
    fn install_provisions_both_protocol_servers() {
        let script = build_install_script(&plan());

        // VNC: the desktop image's own RFB server, published on loopback.
        assert!(script.contains("'127.0.0.1:5901:5901'"));
        // RDP: the bridge image is built and the sidecar started.
        assert!(script.contains("docker build"));
        // The build context must be an empty directory we created, never the
        // SSH login directory — otherwise the whole of $HOME is uploaded to the
        // daemon on every install.
        assert!(
            script.contains("mkdir -p \"$BUILD_CTX\"")
                && script.contains("docker build -t 'azlin-gui-rdp:1' -f - \"$BUILD_CTX\""),
            "the bridge build must use an empty context: {script}"
        );
        assert!(script.contains("'azlin-gui-rdp'"));
        assert!(script.contains("'127.0.0.1:3389:3389'"));

        // The bridge must dial the desktop's RFB endpoint, which is what makes
        // both protocols show the same session.
        let dockerfile = plan().bridge_dockerfile();
        assert!(dockerfile.contains("lib=libvnc.so"));
        assert!(dockerfile.contains("ip=127.0.0.1"));
        assert!(dockerfile.contains("port=5901"));
        assert!(
            plan().bridge_run_args().contains(&"container:azlin-gui".to_string()),
            "the bridge must share the desktop's network namespace"
        );
    }

    /// A bridge failure must not cost the user their desktop.
    #[test]
    fn a_failed_bridge_still_leaves_a_working_vnc_desktop() {
        let script = build_install_script(&plan());
        assert_eq!(
            script.matches("azlin-result: installed-vnc-only").count(),
            2,
            "both bridge failure paths must degrade rather than fail"
        );
        // The bridge failure paths end in `exit 0`, never in one of the fatal
        // install exit codes.
        let bridge_section = script.split("docker rm -f 'azlin-gui-rdp'").nth(1).unwrap();
        for code in [2, 3, 4, 5, 6, 7, 8, 9, 10] {
            assert!(
                !bridge_section.contains(&format!("exit {code}")),
                "bridge failure must degrade, not fail with exit {code}"
            );
        }
    }

    /// The desktop password must never be baked into an image layer: the VM's
    /// image store is unencrypted and survives container removal.
    #[test]
    fn the_bridge_image_never_contains_the_password() {
        let dockerfile = plan().bridge_dockerfile();
        assert!(dockerfile.contains("password=ask"));
        assert!(!dockerfile.contains("VNC_PW"));
        assert!(!dockerfile.contains("$AZLIN_GUI_PW"));
    }

    #[test]
    fn image_reference_is_tag_pinned_not_latest() {
        let tag = DESKTOP_IMAGE
            .reference
            .rsplit_once(':')
            .expect("image reference must carry an explicit tag")
            .1;
        assert_ne!(tag, "latest");
        assert!(DESKTOP_IMAGE.amd64_digest.starts_with("sha256:"));
        assert!(DESKTOP_IMAGE.index_digest.starts_with("sha256:"));
    }

    /// Preserved from the merged implementation: a moved tag must fail closed.
    #[test]
    fn install_verifies_the_pulled_digest_against_the_pinned_digest_and_fails_closed() {
        let plan = plan();
        let script = build_install_script(&plan);
        // The compared value must be the digest Docker actually records for a
        // pull-by-tag, which is the *index* digest. Comparing the amd64
        // manifest digest alone rejects every legitimate pull.
        assert!(
            script.contains(&sq(plan.image.index_digest)),
            "install script must compare against the pinned index digest: {script}"
        );
        assert_ne!(
            DESKTOP_IMAGE.index_digest, DESKTOP_IMAGE.amd64_digest,
            "these are different digests; conflating them is the bug this guards"
        );
        assert!(script.contains("RepoDigests"));
        assert!(script.contains("exit 10"));
        // On mismatch the unverified image must not be left around to run later.
        assert!(script.contains(&format!("docker rmi {}", sq(plan.image.reference))));
        // And the bridge must never be built on an unverified base.
        assert!(
            script.find("exit 10").unwrap() < script.find("docker build").unwrap(),
            "the digest check must precede the bridge build"
        );
    }

    #[test]
    fn published_port_is_always_loopback_bound() {
        assert!(
            plan().publish_spec().starts_with("127.0.0.1:"),
            "publish spec must be loopback bound, got {}",
            plan().publish_spec()
        );
    }

    #[test]
    fn the_novnc_web_port_is_never_published() {
        assert!(
            !build_install_script(&plan()).contains("6901"),
            "the noVNC web port must not be published"
        );
    }

    #[test]
    fn the_password_is_never_passed_on_the_docker_command_line() {
        let args = plan().docker_run_args("\"$ENV_FILE\"");
        assert!(args.contains(&"--env-file".to_string()));
        assert!(
            !args
                .iter()
                .any(|a| a.contains("VNC_PW") || a == "-e" || a == "--env"),
            "secrets must not appear in argv: {args:?}"
        );
    }

    #[test]
    fn env_file_carries_geometry_and_password_reference() {
        let plan = GuiInstallPlan::new(DesktopGeometry {
            resolution: "1280x800".to_string(),
            depth: 16,
        });
        let entries = plan.env_file_entries("$PW");
        assert!(entries.contains(&"VNC_PW=$PW".to_string()));
        assert!(entries.contains(&"VNC_RESOLUTION=1280x800".to_string()));
        assert!(entries.contains(&"VNC_COL_DEPTH=16".to_string()));
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

    /// Everything is installed into Docker. The VM's own packages, services and
    /// configuration are never touched — that is what keeps this path
    /// distro-neutral and what makes it safe on a machine azlin does not own.
    #[test]
    fn no_generated_script_modifies_the_host_itself() {
        for script in all_scripts() {
            for forbidden in ["systemctl", "sudo ", "/etc/systemd"] {
                assert!(
                    !script.contains(forbidden),
                    "generated scripts must not manage host components ({forbidden}): {script}"
                );
            }
            // A package manager may appear only inside the Dockerfile handed to
            // `docker build`, never as a host command.
            for (idx, _) in script.match_indices("apt-get") {
                let before = &script[..idx];
                assert!(
                    before.contains("docker build") || before.contains("printf '%b'"),
                    "apt-get may only run inside the container build: {script}"
                );
            }
            // Likewise the xrdp config path: inside the image, never on the host.
            for (idx, _) in script.match_indices("/etc/xrdp") {
                assert!(
                    script[..idx].contains("printf '%b'"),
                    "xrdp configuration must happen inside the image: {script}"
                );
            }
        }
    }

    #[test]
    fn install_creates_its_state_directory_and_secrets_with_tight_modes() {
        let script = build_install_script(&plan());
        assert!(script.contains("chmod 700 \"$STATE_DIR\""));
        assert!(script.contains("chmod 600 \"$ENV_FILE\""));
        assert!(script.contains("chmod 600 \"$STATE_DIR/vncpasswd\""));
        assert!(script.contains("chmod 600 \"$STATE_DIR/desktoppw\""));
        assert!(
            script.contains("umask 077"),
            "the plaintext password must never exist world-readable, even briefly"
        );
    }

    // -- install script behaviour -----------------------------------------

    #[test]
    fn install_checks_docker_before_anything_else() {
        let script = build_install_script(&plan());
        assert!(script.find("command -v docker").unwrap() < script.find("docker pull").unwrap());
    }

    #[test]
    fn install_refuses_to_start_without_enough_free_space() {
        let script = build_install_script(&plan());
        assert!(script.contains(&REQUIRED_FREE_KIB.to_string()));
        assert!(script.contains("exit 7"));
    }

    #[test]
    fn install_is_idempotent_for_a_matching_container() {
        let script = build_install_script(&plan());
        assert!(script.contains("azlin-result: already-installed"));
        assert!(script.contains("docker start 'azlin-gui'"));
    }

    #[test]
    fn install_recreates_a_container_built_from_a_different_image() {
        assert!(build_install_script(&plan()).contains("docker rm -f 'azlin-gui'"));
    }

    #[test]
    fn install_survives_reboot_via_a_restart_policy() {
        assert!(build_install_script(&plan()).contains("'--restart' 'unless-stopped'"));
    }

    #[test]
    fn install_emits_a_completion_marker() {
        assert!(build_install_script(&plan()).contains("azlin-result: installed"));
    }

    #[test]
    fn every_install_failure_mode_has_a_distinct_exit_code() {
        let script = build_install_script(&plan());
        for code in [2, 3, 4, 5, 6, 7, 8, 9, 10] {
            assert!(
                script.contains(&format!("exit {code}")),
                "install script is missing exit {code}"
            );
        }
    }

    #[test]
    fn install_labels_the_container_so_detection_needs_no_local_state() {
        let script = build_install_script(&plan());
        assert!(script.contains("'azlin.gui.image=consol/debian-xfce-vnc:v2.0.4'"));
        assert!(script.contains("'azlin.gui.rfb-port=5901'"));
    }

    // -- detection ---------------------------------------------------------

    #[test]
    fn detect_always_exits_zero_so_ssh_failures_stay_distinguishable() {
        assert!(build_detect_script().trim_end().ends_with("exit 0"));
    }

    /// Every exit path of the probe must report the bridge, so `--protocol rdp`
    /// can always explain itself instead of falling through to a generic error.
    #[test]
    fn detect_reports_the_rdp_bridge_on_every_exit_path() {
        let script = build_detect_script();
        assert_eq!(
            script.matches("exit 0").count(),
            3,
            "the probe has three exits: no docker, unusable docker, and success"
        );
        assert_eq!(
            script.matches("rdp_bridge=").count(),
            5,
            "two early bail-outs plus the three-way container check"
        );
        // The RFB host port must be read from the desktop's 5901 binding
        // specifically, so an unrelated published port cannot be mistaken for it.
        assert!(script.contains("5901/tcp"));
    }

    #[test]
    fn parse_detect_output_reads_a_running_desktop_with_a_live_bridge() {
        let status = parse_detect_output(
            "rdp_bridge=listening\ndocker_present=true\ndocker_usable=true\ncontainer_state=running\nhost_port=5901\n",
        );
        assert!(status.docker_present && status.docker_usable);
        assert_eq!(status.container_state, ContainerState::Running);
        assert_eq!(status.host_port, Some(5901));
        assert_eq!(status.rdp_bridge, RdpBridgeState::Listening);
        assert!(status.is_installed());
        assert_eq!(status.effective_port(), 5901);
    }

    #[test]
    fn parse_detect_output_reads_a_stopped_desktop() {
        let status = parse_detect_output(
            "rdp_bridge=installed\ndocker_present=true\ndocker_usable=true\ncontainer_state=exited\nhost_port=5901\n",
        );
        assert_eq!(status.container_state, ContainerState::Stopped);
        assert_eq!(status.rdp_bridge, RdpBridgeState::NotRunning);
        assert!(status.is_installed());
    }

    #[test]
    fn parse_detect_output_handles_a_vm_without_docker_but_with_a_bridge() {
        let status = parse_detect_output(
            "rdp_bridge=listening\ndocker_present=false\ndocker_usable=false\ncontainer_state=missing\n",
        );
        assert!(!status.docker_present);
        assert!(!status.is_installed());
        assert_eq!(status.rdp_bridge, RdpBridgeState::Listening);
    }

    #[test]
    fn parse_detect_output_ignores_unrelated_login_shell_noise() {
        let status = parse_detect_output(
            "Welcome to Ubuntu\nsome banner line\nrdp_bridge=absent\ndocker_present=true\ndocker_usable=true\ncontainer_state=running\nhost_port=5901\n",
        );
        assert_eq!(status.container_state, ContainerState::Running);
        assert_eq!(status.host_port, Some(5901));
        assert_eq!(status.rdp_bridge, RdpBridgeState::Absent);
    }

    #[test]
    fn effective_port_falls_back_to_the_rfb_default() {
        let status =
            parse_detect_output("docker_present=true\ndocker_usable=true\ncontainer_state=running\n");
        assert_eq!(status.host_port, None);
        assert_eq!(status.effective_port(), RFB_PORT);
    }

    #[test]
    fn container_state_maps_docker_status_values() {
        assert_eq!(ContainerState::parse("running"), ContainerState::Running);
        assert_eq!(ContainerState::parse("exited"), ContainerState::Stopped);
        assert_eq!(ContainerState::parse("created"), ContainerState::Stopped);
        assert_eq!(ContainerState::parse("missing"), ContainerState::Missing);
        assert_eq!(ContainerState::parse(""), ContainerState::Missing);
    }

    #[test]
    fn an_unknown_status_claims_nothing_is_installed() {
        let status = GuiStatus::unknown();
        assert!(!status.is_installed());
        assert_eq!(status.rdp_bridge, RdpBridgeState::Absent);
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

    /// A missing bridge must never be a dead end: VNC always works without one.
    #[test]
    fn an_absent_rdp_bridge_offers_both_vnc_and_a_repair() {
        let msg = rdp_bridge_remedy(RdpBridgeState::Absent);
        assert!(msg.contains("--protocol vnc"));
        assert!(msg.contains("azlin gui install"));
        // The repair is a reinstall of the desktop, never a host package.
        assert!(!msg.contains("apt-get"));
    }

    #[test]
    fn a_stopped_rdp_bridge_says_how_to_start_it() {
        let msg = rdp_bridge_remedy(RdpBridgeState::NotRunning);
        assert!(msg.contains("docker start azlin-gui-rdp"));
        assert!(msg.contains("--protocol vnc"));
    }

    #[test]
    fn a_live_rdp_bridge_has_no_remedy() {
        assert!(rdp_bridge_remedy(RdpBridgeState::Listening).is_empty());
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
