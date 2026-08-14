# GUI Forwarding & Remote Desktop

Run graphical applications on your Azure VMs and display them locally. azlin supports two approaches: **VNC** for a full remote desktop session and **X11 forwarding** for lightweight GUI apps.

## Overview

| Approach | Best For | Latency | Setup |
|----------|----------|---------|-------|
| VNC Desktop | Full desktop environment, multiple apps | Higher (full desktop) | Auto-managed |
| VNC Minimal | Window manager only, no desktop overhead | Medium | Auto-managed |
| VNC Single App | One app in VNC (e.g. browser), exits when app closes | Medium | Auto-managed |
| X11 Forwarding | Individual GUI apps (gitk, meld, xeyes) | Low (per-window) | Minimal |
| Containerised Desktop | VMs whose repos lack a desktop stack; RDP clients | Higher (full desktop) | `azlin gui install` |

Both approaches work transparently through Azure Bastion tunnels when your VM has no public IP.

## Prerequisites

### Local Machine

**WSL2 (Windows)**:
- WSLg is included with WSL2 by default and provides an X server automatically.
- Verify with: `echo $DISPLAY` (should show something like `:0`)

**Linux**:
- An X11 display server is already running if you are in a graphical session.
- Verify with: `echo $DISPLAY`

**macOS**:
- Install [XQuartz](https://www.xquartz.org/): `brew install --cask xquartz`
- Log out and back in after installation.
- Enable "Allow connections from network clients" in XQuartz Preferences > Security.

**VNC Viewer** (for `azlin gui` only):
- `azlin gui` launches a local `vncviewer` command.
- [TigerVNC](https://tigervnc.org/) is the tested viewer and provides that binary on Linux, macOS, and Windows/WSL setups.

### Remote VM

`azlin gui` automatically installs any missing VNC/desktop packages on first
use. If the VM's package repositories do not carry a desktop stack, or you want
an RDP desktop instead, use [`azlin gui install`](#containerised-desktop-azlin-gui-install),
which takes the whole desktop from a container image and only requires Docker on
the VM. `azlin connect --x11` does **not** install remote GUI applications or X11
packages for you; it only enables X11 forwarding on the SSH connection.

## VNC Desktop

Launch a full remote desktop session on the VM and view it locally.

### Usage

```bash
# Full XFCE desktop (default)
azlin gui my-vm

# Minimal window manager only (openbox) -- no desktop overhead
azlin gui my-vm --minimal

# Single application mode -- VNC exits when the app closes
azlin gui my-vm --app "chromium-browser --no-sandbox"
azlin gui my-vm --app "gimp"

# Custom resolution
azlin gui my-vm --resolution 2560x1440

# Specify SSH user and key for setup and tunneling
azlin gui my-vm --user azureuser --key ~/.ssh/azlin_key
```

### VNC Modes

| Mode | Flag | Desktop | Window Manager | Best For |
|------|------|---------|---------------|----------|
| Full Desktop | *(default)* | XFCE | XFCE WM | Multi-app workflows, full desktop experience |
| Minimal | `--minimal` | None | openbox | Lightweight sessions, launch apps from right-click menu |
| Single App | `--app "cmd"` | None | None | Running one heavy GUI app (browser, IDE, GIMP) |

**Minimal mode** starts only the openbox window manager. Right-click on the desktop for an app launcher menu. Drag window edges to resize. Much lighter than a full desktop.

**Single app mode** runs the specified command directly. The VNC window shows only that application. When the app is closed, the VNC server exits automatically.

!!! note "Chromium/browsers"
    Use `--no-sandbox` when running Chromium in VNC: `azlin gui my-vm --app "chromium-browser --no-sandbox"`. When azlin launches Chromium directly, it auto-wraps snap-backed invocations in `systemd-run --user --scope`, which avoids the common `is not a snap cgroup` failure on Ubuntu VMs.

### How It Works

1. **Dependency check**: azlin SSHs into the VM with the same `--user` and `--key` settings you provided and checks for required packages (`tigervnc-standalone-server`, `xfce4`, `dbus-x11`). Missing packages are installed automatically.
2. **VNC server start**: A TigerVNC server is started on the VM, bound to `localhost` only (no network exposure). A random password is generated for the session.
3. **Tunnel creation**: azlin creates an SSH tunnel (or bastion tunnel) forwarding a local port to the VNC server port on the VM.
4. **Viewer launch**: azlin launches your local VNC viewer, connecting to `localhost:<local_port>` with the session password.
5. **Cleanup**: When you close the VNC viewer, azlin stops the VNC server on the VM and tears down the tunnel.

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--resolution` | `1920x1080` | Desktop resolution (WIDTHxHEIGHT) |
| `--depth` | `24` | VNC color depth (8, 16, or 24) |
| `--user` | `azureuser` | SSH username on the VM |
| `--key` | `~/.ssh/azlin_key` | Path to SSH private key |
| `--minimal` | false | Use openbox window manager instead of full XFCE desktop |
| `--app` | none | Run a single application (e.g. `--app "chromium-browser --no-sandbox"`) |
| `-y, --yes` | false | Compatibility flag; GUI dependency setup is already non-interactive |

### Dependency Management

azlin automatically detects and installs missing packages on first use:

| Package | Purpose |
|---------|---------|
| `tigervnc-standalone-server` | VNC server |
| `xfce4` | Lightweight desktop environment |
| `xfce4-terminal` | Terminal emulator for the desktop |
| `dbus-x11` | D-Bus session bus (required by XFCE) |

Installation happens once per VM and takes 2-3 minutes. Subsequent connections
skip this step. The package setup is non-interactive; `--yes` is accepted for
CLI compatibility but does not change the behavior. If setup cannot finish
cleanly, `azlin gui` exits with the setup error instead of waiting indefinitely.

### Security

VNC security is handled through multiple layers:

- **Localhost binding**: The VNC server listens on `127.0.0.1` only. It is never exposed to the network.
- **Random passwords**: A unique password is generated for each session using `openssl rand`. Passwords are not stored on disk.
- **SSH tunnel**: All VNC traffic travels through the encrypted SSH (or bastion) tunnel. No VNC traffic crosses the network unencrypted.
- **Automatic cleanup**: The VNC server is stopped when the session ends, leaving no listening services behind.

## Containerised Desktop (`azlin gui install`)

`azlin gui` installs a desktop with the VM's package manager. That works whenever
the VM's repositories carry a VNC server, an RDP server and a window manager, and
cannot work when they do not. `azlin gui install` is the alternative: the entire
desktop stack -- X server, window manager and the VNC or RDP server -- comes from a
pinned container image running on the VM's Docker.

Because the desktop lives in the container, this path does not depend on what the
VM's repositories contain, and it is the only way to get an **RDP** desktop.

### Usage

```bash
# Install a containerised VNC desktop (default protocol)
azlin gui install my-vm

# Install a containerised RDP desktop instead
azlin gui install my-vm --protocol rdp

# Custom geometry
azlin gui install my-vm --resolution 2560x1440 --depth 24

# Remove the container and its state
azlin gui install my-vm --uninstall
```

Once installed, connect with the ordinary command -- there is no separate connect
verb:

```bash
azlin gui my-vm
```

`azlin gui` probes the VM first. If a containerised desktop is present it tunnels
to the container and launches your local viewer (a VNC viewer, or an RDP client
for an RDP desktop). If no container is present it takes the normal package-based
path described above, unchanged.

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--protocol` | `vnc` | Remote-desktop protocol: `vnc` or `rdp` |
| `--uninstall` | false | Remove the container and its state directory |
| `--resolution` | `1920x1080` | Desktop resolution (WIDTHxHEIGHT) |
| `--depth` | `24` | Colour depth (8, 16, or 24) |
| `--user` | `azureuser` | SSH username on the VM |
| `--key` | `~/.ssh/azlin_key` | Path to SSH private key |
| `--resource-group` | from config | Resource group containing the VM |
| `-y, --yes` | false | Compatibility flag; the install is already non-interactive |

### Images

| Protocol | Image | Port | Notes |
|----------|-------|------|-------|
| `vnc` | `consol/debian-xfce-vnc:v2.0.4` | 5901 | TigerVNC, real RFB -- works with any standard VNC viewer |
| `rdp` | `lscr.io/linuxserver/rdesktop:ubuntu-xfce` | 3389 | xrdp, works with `xfreerdp`, `mstsc`, Microsoft Remote Desktop |

Both images are pinned by tag and carry XFCE. The install script also verifies
the digest of the image it actually pulls against a digest recorded at pinning
time, and refuses to run the container if they don't match -- a tag is a
mutable pointer, so this catches a tag that has moved on the registry rather
than trusting it. `linuxserver/webtop` is deliberately **not** used: it serves
KasmVNC over WebSockets rather than RFB, so a standard VNC client cannot
connect to it.

### Requirements

Docker must already be installed and running on the VM, and the SSH user must be
able to reach the Docker daemon. `azlin gui install` does not install Docker; if
it is missing, the command reports how to install it and stops. The install also
refuses to run when the Docker data root has less than 4 GiB free, since the
desktop images are large relative to a small OS disk.

### How It Works

1. **Preflight**: checks that Docker is present, that the daemon is reachable as
   the SSH user, and that there is enough free space on the Docker data root.
2. **Pull**: pulls the pinned image for the requested protocol.
3. **Password**: generates a random password *on the VM* and writes it to a `0600`
   env-file under `~/.azlin/gui/`. The password is passed to `docker run` via
   `--env-file`, never on the command line, so it does not appear in `ps` output
   or in `docker inspect`.
4. **Run**: starts the container named `azlin-gui`, publishing the desktop port on
   `127.0.0.1` only.
5. **Connect**: `azlin gui my-vm` opens an SSH (or bastion) tunnel to that
   loopback port and launches your local viewer.

Re-running `azlin gui install` with the same protocol is idempotent: it restarts
the existing container rather than pulling again.

### Security

- **Loopback-only publishing**: the desktop port is published as
  `127.0.0.1:<port>` on the VM. It is not reachable from the network.
- **No NSG changes**: this feature creates, modifies and references **no** network
  security group rules. Access is exclusively through azlin's existing SSH or
  bastion tunnel. A unit test asserts that the generated scripts contain no `az`
  command of any kind.
- **No web port**: the VNC image's noVNC web port (6901) is deliberately not
  published.
- **Password handling**: the password is generated on the VM and passed through a
  `0600` env-file, never as a command-line argument.

**VNC password strength, stated honestly.** The generated password is 32 hex
characters, and the RDP desktop uses all of it. The RFB protocol used by VNC,
however, truncates passwords to **8 bytes** (RFC 6143 §7.2.2) -- everything past
the eighth character is discarded, which is why a VNC `passwd` file is always
exactly 8 bytes long. Only the first 8 hex characters survive, giving `8 * 4 = 32`
bits of effective entropy. This is **not** 128-bit security, and it should not be
described as such. It is acceptable here only because port 5901 is bound to
`127.0.0.1` and reachable solely through the SSH tunnel, so there is no
network-facing brute-force surface.

### Containerised Desktop Troubleshooting

**`docker is not installed on this VM`**

Install Docker on the VM and make sure the SSH user can use it:

```bash
# See https://docs.docker.com/engine/install/ for your distribution
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # then reconnect for the group to take effect
```

**`the docker daemon is not reachable as this user`**

The daemon is not running, or the SSH user is not in the `docker` group. Start it
with `sudo systemctl enable --now docker` and add the user to the `docker` group.

**`less than 4 GiB free ... on the docker data root`**

The desktop images need several GiB. Free space on the VM, or attach and use a
larger disk for Docker's data root.

**`127.0.0.1:<port> is already in use on the VM`**

Another process already holds the desktop port. Stop it, or remove a stale
container with `azlin gui install my-vm --uninstall` and install again.

**RDP: no local client found**

azlin looks for `xfreerdp3`, `xfreerdp`, then `mstsc`. If none is present it keeps
the tunnel open and prints the endpoint, username and password so you can connect
with any RDP client, including Microsoft Remote Desktop on macOS.

## X11 Forwarding

Forward individual GUI windows from the VM to your local display. Best for lightweight apps where you don't need a full desktop.

### Usage

```bash
# Connect with X11 forwarding enabled
azlin connect --x11 my-vm
# Short form
azlin connect -X my-vm

# Then on the VM, run any GUI app:
xeyes &
gitk --all &
meld file1 file2 &
```

### How It Works

1. `azlin connect --x11` adds the `-Y` flag (trusted X11 forwarding) to the SSH connection.
2. SSH sets up an encrypted tunnel for X11 protocol traffic.
3. The remote `DISPLAY` environment variable is set automatically by SSH.
4. GUI windows render on your local X server through the tunnel.
5. When connecting through Azure Bastion, the X11 tunnel is layered on top of the bastion tunnel seamlessly.

### Running Specific Applications

Run any remote GUI app directly without opening an interactive session:

```bash
# Run a single app via X11 -- app window appears locally
azlin connect my-vm --x11 --no-tmux -- chromium-browser --no-sandbox
azlin connect my-vm --x11 --no-tmux -- eog ~/screenshot.png
azlin connect my-vm --x11 --no-tmux -- thunar
azlin connect my-vm --x11 --no-tmux -- gitk --all
azlin connect my-vm --x11 --no-tmux -- meld file1.py file2.py
```

The `--no-tmux` flag avoids wrapping in tmux, and `--` separates azlin args from the remote command. The app renders locally and the connection closes when the app exits.

If you open an interactive X11 shell with `azlin connect --x11 my-vm` and then launch Chromium manually on an older VM, use `systemd-run --user --scope chromium-browser --no-sandbox` inside that shell. Newly provisioned azlin VMs install `/usr/local/bin/chromium-browser` and `/usr/local/bin/chromium` wrappers that add the required user-systemd scope automatically.

### Common GUI Applications

| Application | Command | Purpose |
|-------------|---------|---------|
| xeyes | `xeyes` | Quick test that X11 forwarding works |
| gitk | `gitk --all` | Visual git history browser |
| meld | `meld dir1 dir2` | Visual diff and merge tool |
| gedit | `gedit file.py` | Lightweight text editor |
| Chromium | `chromium-browser --no-sandbox` | Web browser (consider VNC for better performance) |
| eog | `eog image.png` | Image viewer |
| thunar | `thunar` | File manager |
| Firefox | `firefox` | Web browser (heavier, consider VNC) |
| VS Code | `code --disable-gpu` | Editor (use `--disable-gpu` over SSH) |

## Troubleshooting

### VNC: Connection refused when viewer launches

The tunnel may not be ready yet. Retry the connection:

```bash
azlin gui my-vm
```

### VNC: `GUI dependency/setup phase failed (exit 1): exit code 1`

This empty setup error usually means the local azlin client is too old and is
packaging the remote GUI dependency check incorrectly, especially on private
VMs that route through Azure Bastion. Upgrade or rebuild azlin, then retry:

```bash
azlin gui my-vm
```

If the error persists after upgrading, verify that basic SSH still works first:

```bash
azlin connect my-vm --no-tmux -- whoami
```

### VNC: Black screen or no desktop

The desktop environment may not have started correctly:

```bash
# SSH into the VM and check the VNC log
azlin connect my-vm
cat ~/.vnc/*.log

# Restart the desktop environment
vncserver -kill :1
vncserver -localhost yes -geometry 1920x1080 :1
```

### VNC: Screen resolution is wrong

Pass the `--resolution` flag:

```bash
azlin gui my-vm --resolution 2560x1440
```

### VNC: Clipboard not working

Install `autocutsel` on the VM for bidirectional clipboard support:

```bash
# On the VM
sudo apt-get install -y autocutsel
autocutsel -fork
```

### X11: Can't open display

The `DISPLAY` variable is not set on the VM. Verify the connection was made with `--x11`:

```bash
azlin connect --x11 my-vm

# On the VM, check DISPLAY is set
echo $DISPLAY
# Should show something like: localhost:10.0
```

### X11: Connection rejected (wrong authentication)

Regenerate xauth cookies:

```bash
# On the VM
xauth generate $DISPLAY . trusted
```

### X11: Apps are slow or laggy

X11 forwarding sends individual draw commands over the network. For heavy GUI usage, switch to VNC (`azlin gui`) which sends compressed screen updates instead.

### Bastion Tunnel Issues

Both X11 and VNC work through Azure Bastion tunnels. If connections fail:

```bash
# Verify Bastion tunnel is working
azlin bastion status my-bastion --resource-group my-rg

# Test basic SSH connectivity first
azlin connect my-vm

# Then try GUI forwarding
azlin connect --x11 my-vm
```

### Performance Tips

- **VNC**: Best for multi-app workflows or desktop environments. Choose a reasonable resolution.
- **X11**: Best for lightweight apps (gitk, meld, xeyes). Avoid full browsers or IDEs.
- **Region proximity**: VMs in regions closer to you will have noticeably lower GUI latency.
- **VM size**: GUI rendering uses CPU; choose at least `Standard_D2s_v3` or above for smooth performance.
