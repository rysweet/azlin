# azlin compose

Multi-VM docker-compose orchestration commands.

Deploy and manage multi-container applications across multiple VMs
using extended docker-compose syntax.

Example docker-compose.azlin.yml:


version: '3.8'
services:
  web:
    image: nginx:latest
    vm: web-server-1
    ports:
      - "80:80"
  api:
    image: myapi:latest
    vm: api-server-*
    replicas: 3


## Description

Multi-VM docker-compose orchestration commands.
Deploy and manage multi-container applications across multiple VMs
using extended docker-compose syntax.
Example docker-compose.azlin.yml:

version: '3.8'
services:
web:
image: nginx:latest
vm: web-server-1
ports:
- "80:80"
api:
image: myapi:latest
vm: api-server-*
replicas: 3

## Usage

```bash
azlin compose
```

## Subcommands

### down

Stop and remove services deployed from docker-compose.azlin.yml.

This command tears down all services defined in the compose file.


**Usage:**
```bash
azlin compose down [OPTIONS]
```

**Options:**
- `--file`, `-f` - Path to docker-compose.azlin.yml file
- `--resource-group`, `-g` - Azure resource group (uses current context if not specified)

### ps

Show status of services from docker-compose.azlin.yml.

This command displays the current status of all deployed services.


**Usage:**
```bash
azlin compose ps [OPTIONS]
```

**Options:**
- `--file`, `-f` - Path to docker-compose.azlin.yml file
- `--resource-group`, `-g` - Azure resource group (uses current context if not specified)

### up

Deploy services from docker-compose.azlin.yml.

This command:
1. Parses the compose file with VM targeting
2. Resolves VM selectors and plans service placement
3. Deploys containers across VMs in parallel
4. Configures inter-service networking
5. Performs health checks


**Usage:**
```bash
azlin compose up [OPTIONS]
```

**Options:**
- `--file`, `-f` - Path to docker-compose.azlin.yml file
- `--resource-group`, `-g` - Azure resource group (uses current context if not specified)
