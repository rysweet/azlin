# azlin create

Create a new VM template.

Templates are stored as YAML files in ~/.azlin/templates/ and can be
used when creating VMs with the --template option.


Examples:
    azlin template create dev-vm --vm-size Standard_B2s --region westus2
    azlin template create prod-vm --description "Production configuration"


## Description

Create a new VM template.
Templates are stored as YAML files in ~/.azlin/templates/ and can be
used when creating VMs with the --template option.

Examples:
azlin template create dev-vm --vm-size Standard_B2s --region westus2
azlin template create prod-vm --description "Production configuration"

## Usage

```bash
azlin create NAME [OPTIONS]
```

## Arguments

- `NAME` - No description available

## Options

- `--description` TEXT (default: `Sentinel.UNSET`) - Template description
- `--vm-size` TEXT (default: `Sentinel.UNSET`) - Azure VM size
- `--region` TEXT (default: `Sentinel.UNSET`) - Azure region
- `--cloud-init` PATH (default: `Sentinel.UNSET`) - Path to cloud-init script file
