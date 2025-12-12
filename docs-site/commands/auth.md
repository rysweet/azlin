# azlin auth

Manage service principal authentication profiles.

Service principals enable automated Azure authentication without
interactive login. Use these commands to set up and manage
authentication profiles.


EXAMPLES:
    # Set up a new profile
    $ azlin auth setup --profile production

    # Test authentication
    $ azlin auth test --profile production

    # List all profiles
    $ azlin auth list

    # Show profile details
    $ azlin auth show production

    # Remove a profile
    $ azlin auth remove production


## Description

Manage service principal authentication profiles.
Service principals enable automated Azure authentication without
interactive login. Use these commands to set up and manage
authentication profiles.

EXAMPLES:
# Set up a new profile
$ azlin auth setup --profile production
# Test authentication
$ azlin auth test --profile production
# List all profiles
$ azlin auth list
# Show profile details
$ azlin auth show production
# Remove a profile
$ azlin auth remove production

## Usage

```bash
azlin auth
```

## Subcommands

### list

List available authentication profiles.

Shows all configured service principal profiles with their details.
Secrets and sensitive information are masked.


EXAMPLES:
    $ azlin auth list


### remove

Remove authentication profile.

Deletes the specified authentication profile from configuration.
This does not affect the actual service principal in Azure.


EXAMPLES:
    $ azlin auth remove old-profile
    $ azlin auth remove staging --yes


**Usage:**
```bash
azlin auth remove PROFILE [OPTIONS]
```

**Options:**
- `--yes`, `-y` - Skip confirmation

### setup

Set up service principal authentication profile.

Creates a new authentication profile for service principal authentication.
You can have multiple profiles for different environments (dev, prod, etc).


REQUIRED:
    - Tenant ID
    - Client ID
    - Subscription ID
    - Auth method: certificate OR client secret (from env var)


EXAMPLES:
    # Interactive setup
    $ azlin auth setup

    # Non-interactive with client secret
    $ azlin auth setup --profile prod \
        --tenant-id "YOUR-TENANT-ID" \
        --client-id "YOUR-CLIENT-ID" \
        --subscription-id "YOUR-SUBSCRIPTION-ID"
    # Then set: export AZLIN_SP_CLIENT_SECRET="your-secret"

    # With certificate
    $ azlin auth setup --profile prod \
        --tenant-id "YOUR-TENANT-ID" \
        --client-id "YOUR-CLIENT-ID" \
        --subscription-id "YOUR-SUBSCRIPTION-ID" \
        --use-certificate \
        --certificate-path ~/certs/sp-cert.pem


**Usage:**
```bash
azlin auth setup [OPTIONS]
```

**Options:**
- `--profile`, `-p` - Profile name
- `--tenant-id` - Azure Tenant ID
- `--client-id` - Azure Client ID / Application ID
- `--subscription-id` - Azure Subscription ID
- `--use-certificate` - Use certificate-based auth (otherwise client secret)
- `--certificate-path` - Path to certificate file (for cert-based auth)

### show

Show authentication profile details.

Displays complete information about a specific profile.
Secrets are masked for security.


EXAMPLES:
    $ azlin auth show default
    $ azlin auth show production


**Usage:**
```bash
azlin auth show PROFILE
```

### test

Test service principal authentication.

Validates that the authentication profile works correctly by attempting
to authenticate and optionally test subscription access.


EXAMPLES:
    # Test default profile
    $ azlin auth test

    # Test specific profile
    $ azlin auth test --profile production

    # Test with subscription validation
    $ azlin auth test --profile prod --subscription-id "YOUR-SUB-ID"


**Usage:**
```bash
azlin auth test [OPTIONS]
```

**Options:**
- `--profile`, `-p` - Profile name
- `--subscription-id` - Test specific subscription access
