# azlin template

Manage VM configuration templates.

Templates allow you to save and reuse VM configurations.
Stored in ~/.azlin/templates/ as YAML files.


SUBCOMMANDS:
    create   Create a new template
    list     List all templates
    delete   Delete a template
    export   Export template to file
    import   Import template from file


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


## Description

Manage VM configuration templates.
Templates allow you to save and reuse VM configurations.
Stored in ~/.azlin/templates/ as YAML files.

SUBCOMMANDS:
create   Create a new template
list     List all templates
delete   Delete a template
export   Export template to file
import   Import template from file

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

## Usage

```bash
azlin template
```

## Subcommands

### create

Create a new VM template.

Templates are stored as YAML files in ~/.azlin/templates/ and can be
used when creating VMs with the --template option.


Examples:
    azlin template create dev-vm --vm-size Standard_B2s --region westus2
    azlin template create prod-vm --description "Production configuration"


**Usage:**
```bash
azlin template create NAME [OPTIONS]
```

**Options:**
- `--description` - Template description
- `--vm-size` - Azure VM size
- `--region` - Azure region
- `--cloud-init` - Path to cloud-init script file

### delete

Delete a template.

Removes the template file from ~/.azlin/templates/.


Examples:
    azlin template delete dev-vm
    azlin template delete dev-vm --force


**Usage:**
```bash
azlin template delete NAME [OPTIONS]
```

**Options:**
- `--force` - Skip confirmation prompt

### export

Export a template to a YAML file.

Exports the template configuration to a file that can be shared
or imported on another machine.


Examples:
    azlin template export dev-vm my-template.yaml
    azlin template export dev-vm ~/shared/template.yaml


**Usage:**
```bash
azlin template export NAME OUTPUT_FILE
```

### import

Import a template from a YAML file.

Imports a template configuration from a file and saves it
to ~/.azlin/templates/.


Examples:
    azlin template import my-template.yaml
    azlin template import ~/shared/template.yaml


**Usage:**
```bash
azlin template import INPUT_FILE
```

### list

List all available templates.

Shows all templates stored in ~/.azlin/templates/.


Examples:
    azlin template list
