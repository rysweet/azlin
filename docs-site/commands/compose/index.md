# Compose Commands

Multi-VM docker-compose orchestration for azlin.

## Overview

azlin compose extends docker-compose to deploy multi-container applications across multiple VMs. Define your services in a compose file with VM targeting, and azlin handles deployment, networking, and lifecycle management.

## Key Features

- **VM Targeting**: Specify which VM(s) should run each service
- **VM Selectors**: Use wildcards and patterns to target multiple VMs
- **Parallel Deployment**: Deploy services across VMs simultaneously
- **Service Replication**: Run multiple instances across VM pools
- **Inter-Service Networking**: Automatic service discovery and networking
- **Health Checks**: Verify service health after deployment

## Commands

- [up](up.md) - Deploy services from compose file
- [down](down.md) - Stop and remove all services
- [ps](ps.md) - Show status of deployed services

## Quick Start

### 1. Create compose file

Create `docker-compose.azlin.yml`:

```yaml
version: '3.8'

services:
  nginx:
    image: nginx:latest
    vm: web-server
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./html:/usr/share/nginx/html

  api:
    image: myapi:latest
    vm: api-*
    replicas: 3
    environment:
      - DATABASE_URL=postgresql://db:5432/myapp
    ports:
      - "8080:8080"

  database:
    image: postgres:15
    vm: db-server
    environment:
      - POSTGRES_PASSWORD=secret
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### 2. Deploy services

```bash
azlin compose up -f docker-compose.azlin.yml
```

### 3. Check status

```bash
azlin compose ps -f docker-compose.azlin.yml
```

### 4. Tear down

```bash
azlin compose down -f docker-compose.azlin.yml
```

## VM Targeting

### Exact VM Name

```yaml
services:
  web:
    image: nginx
    vm: web-server-1
```

Deploys to VM named exactly `web-server-1`.

### Wildcard Selector

```yaml
services:
  api:
    image: myapi
    vm: api-*
```

Deploys to all VMs matching pattern `api-*` (e.g., `api-1`, `api-2`, `api-staging`).

### Replica Distribution

```yaml
services:
  worker:
    image: worker
    vm: worker-*
    replicas: 5
```

Distributes 5 worker instances across all VMs matching `worker-*`.

## Compose File Format

### Standard docker-compose Fields

All standard docker-compose fields are supported:
- `image` - Container image
- `ports` - Port mappings
- `environment` - Environment variables
- `volumes` - Volume mounts
- `networks` - Network configuration
- `depends_on` - Service dependencies
- `restart` - Restart policy
- `healthcheck` - Health check configuration

### azlin-Specific Fields

#### vm (required)

Specifies target VM(s) for the service:

```yaml
# Single VM
vm: my-vm

# Wildcard pattern
vm: api-*

# All VMs
vm: "*"
```

#### replicas (optional)

Number of service instances:

```yaml
services:
  worker:
    image: worker
    vm: worker-*
    replicas: 10  # Deploy 10 instances across worker-* VMs
```

## Networking

### Inter-Service Communication

Services can communicate using service names:

```yaml
services:
  web:
    image: nginx
    vm: web-server
    environment:
      - API_URL=http://api:8080

  api:
    image: myapi
    vm: api-server
    environment:
      - DB_HOST=database
```

azlin automatically configures service discovery so `api` and `database` resolve correctly.

### Port Mapping

```yaml
services:
  web:
    image: nginx
    vm: web-server
    ports:
      - "80:80"      # Host port 80 -> Container port 80
      - "443:443"    # Host port 443 -> Container port 443
      - "8080:80"    # Host port 8080 -> Container port 80
```

## Common Patterns

### Web Application Stack

```yaml
version: '3.8'

services:
  frontend:
    image: myapp/frontend
    vm: web-server
    ports:
      - "80:80"
    depends_on:
      - api

  api:
    image: myapp/api
    vm: api-server
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgresql://database:5432/myapp
    depends_on:
      - database

  database:
    image: postgres:15
    vm: db-server
    environment:
      - POSTGRES_PASSWORD=secret
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### Distributed Workers

```yaml
version: '3.8'

services:
  redis:
    image: redis:7
    vm: cache-server
    ports:
      - "6379:6379"

  worker:
    image: myapp/worker
    vm: worker-*
    replicas: 20
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
```

### Microservices

```yaml
version: '3.8'

services:
  gateway:
    image: myapp/gateway
    vm: gateway
    ports:
      - "80:80"

  auth:
    image: myapp/auth
    vm: services-*
    environment:
      - DB_HOST=database

  users:
    image: myapp/users
    vm: services-*
    environment:
      - DB_HOST=database

  products:
    image: myapp/products
    vm: services-*
    environment:
      - DB_HOST=database

  database:
    image: postgres:15
    vm: db-server
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

## Best Practices

### 1. Use Named VMs

```bash
# Create VMs with meaningful names
azlin new --name web-server
azlin new --name api-server
azlin new --name db-server

# Reference in compose file
services:
  web:
    vm: web-server
```

### 2. Separate Database VMs

```yaml
# Database on dedicated VM
database:
  image: postgres
  vm: db-server

# Not on shared application VMs
database:
  image: postgres
  vm: app-*  # Don't do this
```

### 3. Use Health Checks

```yaml
services:
  api:
    image: myapi
    vm: api-server
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 4. Tag VMs for Organization

```bash
# Tag VMs by role
azlin tag web-server --add role=frontend
azlin tag api-server --add role=backend
azlin tag db-server --add role=database

# Then use in compose selectors
vm: "*"  # Can filter by tag in future versions
```

### 5. Use Environment Files

```yaml
services:
  api:
    image: myapi
    vm: api-server
    env_file:
      - .env.production
```

## Troubleshooting

### VM not found

```
Error: No VMs match selector 'api-*'
```

**Solution**: Create matching VMs:
```bash
azlin list  # Check existing VMs
azlin new --name api-1
azlin new --name api-2
```

### Port already in use

```
Error: Port 80 is already in use on web-server
```

**Solution**: Stop conflicting service or use different port:
```bash
# Check what's using the port
azlin connect web-server
sudo netstat -tlnp | grep :80

# Change port in compose file
ports:
  - "8080:80"  # Use 8080 instead
```

### Service won't start

```bash
# Check service logs
azlin compose ps -f docker-compose.azlin.yml

# Connect to VM and check Docker
azlin connect web-server
docker ps -a
docker logs <container-id>
```

## Related Commands

- [azlin new](../vm/new.md) - Create VMs for services
- [azlin list](../vm/list.md) - List available VMs
- [azlin batch](../batch/index.md) - Run commands across VMs
