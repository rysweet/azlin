# azlin compose

Multi-VM Docker Compose orchestration across azlin VMs.

## Description

Deploy and manage multi-container applications using Docker Compose across multiple azlin VMs. Coordinate services, share networks, and manage distributed applications.

## Usage

```bash
azlin compose [COMMAND] [OPTIONS]
```

## Commands

| Command | Description |
|---------|-------------|
| `up` | Start services across VMs |
| `down` | Stop services across VMs |
| `ps` | Show running services |
| `logs` | View service logs |
| `exec` | Execute command in service container |

## Examples

### Deploy Multi-VM Application

```bash
# Create compose config
cat > docker-compose-azlin.yaml << 'EOF'
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    deploy:
      vm: web-vm-001

  api:
    image: myapp/api:latest
    ports:
      - "8080:8080"
    deploy:
      vm: api-vm-001

  db:
    image: postgres:15
    deploy:
      vm: db-vm-001
    environment:
      POSTGRES_PASSWORD: secret
EOF

# Deploy across VMs
azlin compose up -f docker-compose-azlin.yaml
```

### Scale Services

```bash
# Scale web service to 3 instances
azlin compose scale web=3

# Distributes across: web-vm-001, web-vm-002, web-vm-003
```

### View Status

```bash
azlin compose ps
```

**Output:**
```
SERVICE   VM            STATUS    PORTS
web       web-vm-001    Running   0.0.0.0:80->80/tcp
api       api-vm-001    Running   0.0.0.0:8080->8080/tcp
db        db-vm-001     Running   5432/tcp
```

## Common Workflows

### Microservices Architecture

```bash
# Deploy microservices across VMs
azlin compose up -f microservices-compose.yaml

# Rolling updates
azlin compose up --no-deps --build web
azlin compose up --no-deps --build api
```

### Development Cluster

```bash
# Create 3-tier app
azlin new --name frontend --template web-tier
azlin new --name backend --template api-tier
azlin new --name database --template db-tier

# Deploy compose stack
azlin compose -f dev-stack.yaml up
```

## Related Commands

- [`azlin new`](../vm/new.md) - Provision VMs for compose services
- [`azlin fleet exec`](../fleet/overview.md) - Execute across fleet
- [`azlin batch`](../batch/index.md) - Batch operations

## See Also

- [Docker Compose](../../advanced/compose.md)
- [Fleet Management](../../batch/fleet.md)
