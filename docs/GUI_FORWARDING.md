# GUI Forwarding & Remote Desktop

Run graphical applications on your Azure VMs and display them locally. azlin supports two approaches: **X11 forwarding** for lightweight GUI apps and **VNC** for a full remote desktop session.

## Overview

| Approach | Best For | Latency | Setup |
|----------|----------|---------|-------|
| X11 Forwarding | Individual GUI apps (gitk, meld, xeyes) | Low (per-window) | Minimal |
| VNC Desktop | Full desktop environment, multiple apps | Higher (full desktop) | Auto-managed |
| VNC Minimal | Window manager only, no desktop overhead | Medium | Auto-managed |
| VNC Single App | One app in VNC (e.g. browser), exits when app closes | Medium | Auto-managed |

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
- Any VNC client works. Recommendations:
  - [TigerVNC](https://tigervnc.org/) (cross-platform, free)
  - [RealVNC Viewer](https://www.realvnc.com/en/connect/download/viewer/) (cross-platform, free for personal use)
  - Remmina (Linux, free)

### Remote VM

No manual setup required. azlin automatically installs any missing packages on the VM when you use `azlin connect --x11` or `azlin gui`.

## X11 Forwarding

Forward individual GUI windows from the VM to your local display.

### Usage

```bash
# Connect with X11 forwarding enabled
azlin connect --x11 my-vm

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

You can run any remote GUI app directly without opening an interactive session:

```bash
# Run a single app via X11 — app window appears locally
azlin connect devo --x11 --no-tmux -- chromium-browser
azlin connect devo --x11 --no-tmux -- eog ~/screenshot.png
azlin connect devo --x11 --no-tmux -- thunar
azlin connect devo --x11 --no-tmux -- gitk --all
azlin connect devo --x11 --no-tmux -- meld file1.py file2.py
```

The `--no-tmux` flag avoids wrapping in tmux, and `--` separates azlin args from the remote command. The app renders locally and the connection closes when the app exits.

### Common GUI Applications

| Application | Command | Purpose |
|-------------|---------|---------|
| xeyes | `xeyes` | Quick test that X11 forwarding works |
| gitk | `gitk --all` | Visual git history browser |
| meld | `meld dir1 dir2` | Visual diff and merge tool |
| gedit | `gedit file.py` | Lightweight text editor |
| Chromium | `chromium-browser` | Web browser (consider VNC for better performance) |
| eog | `eog image.png` | Image viewer |
| thunar | `thunar` | File manager |
| Firefox | `firefox` | Web browser (heavier, consider VNC) |
| VS Code | `code --disable-gpu` | Editor (use `--disable-gpu` over SSH) |

### X11 Troubleshooting

**`Error: Can't open display`**

The `DISPLAY` variable is not set on the VM. This usually means X11 forwarding was not enabled.

```bash
# Verify the connection was made with --x11
azlin connect --x11 my-vm

# On the VM, check DISPLAY is set
echo $DISPLAY
# Should show something like: localhost:10.0
```

**`X11 connection rejected because of wrong authentication`**

xauth cookies are mismatched. Regenerate them:

```bash
# On the VM
xauth generate $DISPLAY . trusted
```

**`Warning: No xauth data`**

The xauth package may be missing on the VM. azlin installs it automatically, but if you connected without `--x11` first:

```bash
# On the VM
sudo apt-get install -y xauth
# Disconnect and reconnect with --x11
```

**Apps are slow or laggy**

X11 forwarding sends individual draw commands over the network, which can be slow for complex UIs. Options:
- Use `ssh -C` (compression) for lower-bandwidth connections -- azlin enables this automatically.
- For heavy GUI usage, switch to VNC (`azlin gui`) which sends compressed screen updates instead.

## VNC Desktop

Launch a full remote desktop session on the VM and view it locally.

### Usage

```bash
# Full XFCE desktop (default)
azlin gui my-vm

# Minimal window manager only (openbox) — no desktop overhead
azlin gui my-vm --minimal

# Single application mode — VNC exits when the app closes
azlin gui my-vm --app "chromium-browser"
azlin gui my-vm --app "gimp"

# Custom resolution
azlin gui my-vm --resolution 2560x1440

# Specify SSH user and key
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

### How It Works

1. **Dependency check**: azlin SSHs into the VM and checks for required packages (`tigervnc-standalone-server`, `xfce4`, `dbus-x11`). Missing packages are installed automatically.
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
| `--app` | none | Run a single application (e.g. `--app "chromium-browser"`) |
| `-y, --yes` | false | Skip dependency installation prompts |

### Dependency Management

azlin automatically detects and installs missing packages on first use. The following packages are managed:

| Package | Purpose |
|---------|---------|
| `tigervnc-standalone-server` | VNC server |
| `xfce4` | Lightweight desktop environment |
| `xfce4-terminal` | Terminal emulator for the desktop |
| `dbus-x11` | D-Bus session bus (required by XFCE) |

Installation happens once per VM and takes 2-3 minutes. Subsequent connections skip this step.

### Security

VNC security is handled through multiple layers:

- **Localhost binding**: The VNC server listens on `127.0.0.1` only. It is never exposed to the network.
- **Random passwords**: A unique password is generated for each session using `openssl rand`. Passwords are not stored on disk.
- **SSH tunnel**: All VNC traffic travels through the encrypted SSH (or bastion) tunnel. No VNC traffic crosses the network unencrypted.
- **Automatic cleanup**: The VNC server is stopped when the session ends, leaving no listening services behind.

### VNC Troubleshooting

**`Connection refused` when viewer launches**

The tunnel may not be ready yet. azlin waits for the tunnel to be established before launching the viewer, but on slow connections this can race:

```bash
# Retry the connection
azlin gui my-vm

# Or start without auto-viewer and connect manually
azlin gui my-vm --no-viewer
# Then open your VNC viewer and connect to localhost:<port> shown in output
```

**Black screen or no desktop**

The desktop environment may not have started correctly:

```bash
# SSH into the VM and check the VNC log
azlin connect my-vm
cat ~/.vnc/*.log

# Restart the desktop environment
vncserver -kill :1
vncserver -localhost yes -geometry 1920x1080 :1
```

**Screen resolution is wrong**

Pass the `--resolution` flag:

```bash
azlin gui my-vm --resolution 2560x1440
```

Supported resolutions: any valid WIDTHxHEIGHT value (e.g., `1280x720`, `1920x1080`, `2560x1440`, `3840x2160`).

**Clipboard not working between local and remote**

Install `autocutsel` on the VM for bidirectional clipboard support:

```bash
# On the VM
sudo apt-get install -y autocutsel
autocutsel -fork
```

## General Troubleshooting

### Bastion Tunnel Issues

Both X11 and VNC work through Azure Bastion tunnels. If connections fail when using Bastion:

```bash
# Verify Bastion tunnel is working
azlin bastion status my-bastion --resource-group my-rg

# Test basic SSH connectivity first
azlin connect my-vm

# Then try GUI forwarding
azlin connect --x11 my-vm
```

### Firewall / NSG Rules

No additional firewall or NSG rules are needed. Both X11 and VNC traffic travels inside the SSH tunnel, which uses only port 22 (or the bastion tunnel).

### Performance Tips

- **X11**: Best for lightweight apps (gitk, meld, xeyes). Avoid full browsers or IDEs.
- **VNC**: Best for multi-app workflows or desktop environments. Compress traffic by choosing a reasonable resolution.
- **Region proximity**: VMs in regions closer to you will have noticeably lower GUI latency.
- **VM size**: GUI rendering uses CPU; choose at least `Standard_D2s_v3` or above for a smooth experience.
