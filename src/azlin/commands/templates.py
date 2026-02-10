"""Template command group for azlin.

This module provides CLI commands for VM configuration template management:
- create: Create a new VM template
- list: List all available templates
- delete: Delete a template
- export: Export template to file
- import: Import template from file

Issue #423: Extracted from cli.py as part of CLI decomposition.
"""

import logging
import sys
from pathlib import Path

import click

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager
from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig

logger = logging.getLogger(__name__)


@click.group(name="template")
def template_group():
    """Manage VM configuration templates.

    Templates allow you to save and reuse VM configurations.
    Stored in ~/.azlin/templates/ as YAML files.

    \b
    SUBCOMMANDS:
        create   Create a new template
        list     List all templates
        delete   Delete a template
        export   Export template to file
        import   Import template from file

    \b
    EXAMPLES:
        # Create a template interactively
        azlin template create dev-vm

        # List all templates
        azlin template list

        # Delete a template
        azlin template delete dev-vm

        # Export a template
        azlin template export dev-vm my-template.yaml

        # Import a template
        azlin template import my-template.yaml

        # Use a template when creating VM
        azlin new --template dev-vm
    """
    pass


@template_group.command(name="create")
@click.argument("name", type=str)
@click.option("--description", help="Template description", type=str)
@click.option("--vm-size", help="Azure VM size", type=str)
@click.option("--region", help="Azure region", type=str)
@click.option("--cloud-init", help="Path to cloud-init script file", type=click.Path(exists=True))
def template_create(
    name: str,
    description: str | None,
    vm_size: str | None,
    region: str | None,
    cloud_init: str | None,
):
    """Create a new VM template.

    Templates are stored as YAML files in ~/.azlin/templates/ and can be
    used when creating VMs with the --template option.

    \b
    Examples:
        azlin template create dev-vm --vm-size Standard_B2s --region westus2
        azlin template create prod-vm --description "Production configuration"
    """
    try:
        # Load config for defaults
        try:
            config = ConfigManager.load_config(None)
        except ConfigError:
            config = AzlinConfig()

        # Use provided values or defaults
        final_description = description or f"Template: {name}"
        final_vm_size = vm_size or config.default_vm_size
        final_region = region or config.default_region

        # Load cloud-init if provided
        cloud_init_content = None
        if cloud_init:
            cloud_init_path = Path(cloud_init).expanduser().resolve()
            cloud_init_content = cloud_init_path.read_text()

        # Create template
        template = VMTemplateConfig(
            name=name,
            description=final_description,
            vm_size=final_vm_size,
            region=final_region,
            cloud_init=cloud_init_content,
        )

        TemplateManager.create_template(template)

        click.echo(f"Created template: {name}")
        click.echo(f"  Description: {final_description}")
        click.echo(f"  VM Size:     {final_vm_size}")
        click.echo(f"  Region:      {final_region}")
        if cloud_init_content:
            click.echo("  Cloud-init:  Custom script included")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        logger.exception("Unexpected error in template create")
        sys.exit(1)


@template_group.command(name="list")
def template_list():
    """List all available templates.

    Shows all templates stored in ~/.azlin/templates/.

    \b
    Examples:
        azlin template list
    """
    try:
        templates = TemplateManager.list_templates()

        if not templates:
            click.echo("No templates found.")
            click.echo("\nCreate a template with: azlin template create <name>")
            return

        click.echo(f"\nAvailable Templates ({len(templates)}):")
        click.echo("=" * 90)
        click.echo(f"{'NAME':<25} {'VM SIZE':<20} {'REGION':<15} {'DESCRIPTION':<30}")
        click.echo("=" * 90)

        for t in templates:
            desc = t.description[:27] + "..." if len(t.description) > 30 else t.description
            click.echo(f"{t.name:<25} {t.vm_size:<20} {t.region:<15} {desc:<30}")

        click.echo("=" * 90)
        click.echo("\nUse with: azlin new --template <name>")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="delete")
@click.argument("name", type=str)
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def template_delete(name: str, force: bool):
    """Delete a template.

    Removes the template file from ~/.azlin/templates/.

    \b
    Examples:
        azlin template delete dev-vm
        azlin template delete dev-vm --force
    """
    try:
        # Verify template exists
        template = TemplateManager.get_template(name)

        # Confirm deletion unless --force
        if not force:
            click.echo(f"\nTemplate: {template.name}")
            click.echo(f"  Description: {template.description}")
            click.echo(f"  VM Size:     {template.vm_size}")
            click.echo(f"  Region:      {template.region}")
            click.echo("\nThis action cannot be undone.")

            confirm = input("\nDelete this template? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        # Delete template
        TemplateManager.delete_template(name)
        click.echo(f"Deleted template: {name}")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="export")
@click.argument("name", type=str)
@click.argument("output_file", type=click.Path())
def template_export(name: str, output_file: str):
    """Export a template to a YAML file.

    Exports the template configuration to a file that can be shared
    or imported on another machine.

    \b
    Examples:
        azlin template export dev-vm my-template.yaml
        azlin template export dev-vm ~/shared/template.yaml
    """
    try:
        output_path = Path(output_file).expanduser().resolve()

        # Check if file exists
        if output_path.exists():
            confirm = input(f"\nFile '{output_path}' exists. Overwrite? [y/N]: ").lower()
            if confirm not in ["y", "yes"]:
                click.echo("Cancelled.")
                return

        TemplateManager.export_template(name, output_path)
        click.echo(f"Exported template '{name}' to: {output_path}")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {e}", err=True)
        sys.exit(1)


@template_group.command(name="import")
@click.argument("input_file", type=click.Path(exists=True))
def template_import(input_file: str):
    """Import a template from a YAML file.

    Imports a template configuration from a file and saves it
    to ~/.azlin/templates/.

    \b
    Examples:
        azlin template import my-template.yaml
        azlin template import ~/shared/template.yaml
    """
    try:
        input_path = Path(input_file).expanduser().resolve()

        template = TemplateManager.import_template(input_path)

        click.echo(f"Imported template: {template.name}")
        click.echo(f"  Description: {template.description}")
        click.echo(f"  VM Size:     {template.vm_size}")
        click.echo(f"  Region:      {template.region}")

    except TemplateError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


__all__ = [
    "template_create",
    "template_delete",
    "template_export",
    "template_group",
    "template_import",
    "template_list",
]
