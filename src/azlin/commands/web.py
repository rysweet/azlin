"""PWA web server management commands.

This module provides commands for starting and stopping the Azlin Mobile PWA
development server.
"""

from __future__ import annotations

import signal
import subprocess
import sys
from pathlib import Path

import click

__all__ = ["web"]


@click.group(name="web")
def web():
    """Manage the Azlin Mobile PWA web server."""
    pass


@web.command(name="start")
@click.option("--port", default=3000, help="Port to run the dev server on", type=int)
@click.option("--host", default="localhost", help="Host to bind to", type=str)
def web_start(port: int, host: str):
    """Start the Azlin Mobile PWA development server.

    This command starts the Vite dev server for the React PWA that manages
    azlin VMs from iPhone/mobile devices.

    Once started, open http://localhost:3000 in Safari on your iPhone and
    add to home screen for a native-like app experience.
    """
    # Find the PWA directory - try multiple locations
    # 1. Development: src/azlin/cli.py -> ../../pwa
    dev_pwa_dir = Path(__file__).parent.parent.parent.parent / "pwa"

    # 2. Installed via pip: site-packages/azlin/cli.py -> ../pwa
    installed_pwa_dir = Path(__file__).parent.parent / "pwa"

    # 3. Git repo: check if we're in a git repo
    git_root_pwa_dir = None
    try:
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=2
        )
        if git_root.returncode == 0:
            git_root_pwa_dir = Path(git_root.stdout.strip()) / "pwa"
    except Exception:
        pass

    # Try paths in order
    pwa_dir = None
    for candidate in [dev_pwa_dir, installed_pwa_dir, git_root_pwa_dir]:
        if candidate and candidate.exists():
            pwa_dir = candidate
            break

    if not pwa_dir:
        click.echo("Error: PWA directory not found. Tried:", err=True)
        click.echo(f"  - {dev_pwa_dir} (development)", err=True)
        click.echo(f"  - {installed_pwa_dir} (installed)", err=True)
        if git_root_pwa_dir:
            click.echo(f"  - {git_root_pwa_dir} (git root)", err=True)
        click.echo("\nThe PWA may not be installed yet.", err=True)
        click.echo("Run this command from the azlin repository root.", err=True)
        sys.exit(1)

    # Auto-generate .env from azlin config if needed
    try:
        from azlin.modules.pwa_config_generator import generate_pwa_env_from_azlin

        result = generate_pwa_env_from_azlin(pwa_dir, force=False)

        # Display success messages
        if result.success and result.message:
            click.echo(f"✅ {result.message}")

            # Show config sources if available
            if result.source_attribution:
                click.echo("\n📋 Configuration sources:")
                for var_name, source in result.source_attribution.items():
                    click.echo(f"  • {var_name}: {source.value}")

        # Display errors (blocking)
        if not result.success:
            click.echo("\n❌ Failed to generate PWA configuration:", err=True)
            if result.error:
                click.echo(f"   {result.error}", err=True)
            click.echo("\n💡 Solutions:", err=True)
            click.echo(
                "   1. Install Azure CLI: https://docs.microsoft.com/cli/azure/install-azure-cli",
                err=True,
            )
            click.echo("   2. Authenticate: az login", err=True)
            click.echo("   3. Or manually create pwa/.env from pwa/.env.example", err=True)
            sys.exit(1)

    except ImportError as e:
        # Module not available - skip config generation
        click.echo(f"⚠️  PWA config generator not available: {e}", err=True)
        click.echo("   Continuing without auto-config generation...", err=True)
    except Exception as e:
        # Non-fatal error - warn but continue
        click.echo(f"⚠️  Config generation failed: {e}", err=True)
        click.echo("   Continuing with manual .env setup...", err=True)

    # Check if node_modules exists
    if not (pwa_dir / "node_modules").exists():
        click.echo("Installing PWA dependencies (first time only)...")
        subprocess.run(["npm", "install"], cwd=pwa_dir, check=True)

    click.echo(f"🏴‍☠️ Starting Azlin Mobile PWA on http://{host}:{port}")
    click.echo("📱 Open in Safari on your iPhone and add to home screen")
    click.echo("Press Ctrl+C to stop the server")
    click.echo("")

    try:
        subprocess.run(
            ["npm", "run", "dev", "--", "--port", str(port), "--host", host],
            cwd=pwa_dir,
            check=True,
        )
    except KeyboardInterrupt:
        click.echo("\n🛑 PWA server stopped")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error starting PWA: {e}", err=True)
        sys.exit(1)


@web.command(name="stop")
def web_stop():
    """Stop the Azlin Mobile PWA development server.

    Finds and terminates any running Vite dev server processes for the PWA.
    """
    try:
        # Find vite processes
        result = subprocess.run(["pgrep", "-f", "vite.*azlin"], capture_output=True, text=True)

        if result.returncode != 0 or not result.stdout.strip():
            click.echo("No running PWA server found")
            return

        pids = result.stdout.strip().split("\n")
        click.echo(f"Found {len(pids)} PWA server process(es)")

        for pid in pids:
            try:
                import os

                os.kill(int(pid), signal.SIGTERM)
                click.echo(f"✓ Stopped PWA server (PID: {pid})")
            except ProcessLookupError:
                pass  # Already stopped
            except Exception as e:
                click.echo(f"Warning: Could not stop PID {pid}: {e}", err=True)

    except Exception as e:
        click.echo(f"Error stopping PWA: {e}", err=True)
        sys.exit(1)
