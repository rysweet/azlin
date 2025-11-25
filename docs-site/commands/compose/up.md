# azlin compose up

Deploy services from docker-compose.azlin.yml file across VMs.

## Synopsis

```bash
azlin compose up -f <compose-file> [OPTIONS]
```

## Description

Deploys all services defined in the compose file to their target VMs. This command:

1. Parses the compose file with VM targeting syntax
2. Resolves VM selectors and plans service placement
3. Pulls container images on target VMs
4. Deploys containers across VMs in parallel
5. Configures inter-service networking
6. Performs health checks

## Options

| Option | Description | Required |
|--------|-------------|----------|
| `-f, --file PATH` | Path to docker-compose.azlin.yml file | Yes |
| `-g, --resource-group TEXT` | Azure resource group | No (uses current context) |
| `-h, --help` | Show help message | No |

## Examples

### Deploy from current directory

```bash
azlin compose up -f docker-compose.azlin.yml
```

### Deploy from specific path

```bash
azlin compose up -f ~/projects/myapp/docker-compose.azlin.yml
```

### Deploy to specific resource group

```bash
azlin compose up -f docker-compose.azlin.yml -g my-rg
```

## Deployment Process

### 1. Planning Phase

```
Planning deployment...
  ✓ Parsed compose file
  ✓ Resolved VM selectors
  ✓ Validated target VMs exist

Deployment Plan:
  web (nginx) -> web-server
  api (myapi) -> api-1, api-2, api-3
  database (postgres) -> db-server
```

### 2. Image Pull Phase

```
Pulling images...
  web-server: Pulling nginx:latest... ✓
  api-1: Pulling myapi:latest... ✓
  api-2: Pulling myapi:latest... ✓
  api-3: Pulling myapi:latest... ✓
  db-server: Pulling postgres:15... ✓
```

### 3. Deployment Phase

```
Deploying services...
  database@db-server: Starting... ✓
  api@api-1: Starting... ✓
  api@api-2: Starting... ✓
  api@api-3: Starting... ✓
  web@web-server: Starting... ✓
```

### 4. Health Check Phase

```
Health checks...
  database@db-server: Healthy ✓
  api@api-1: Healthy ✓
  api@api-2: Healthy ✓
  api@api-3: Healthy ✓
  web@web-server: Healthy ✓
```

### 5. Summary

```
Deployment Complete!

Services deployed:
  web: 1 instance on web-server
  api: 3 instances on api-1, api-2, api-3
  database: 1 instance on db-server

Run 'azlin compose ps -f docker-compose.azlin.yml' to view status.
```

## Example Compose File

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
      - ./html:/usr/share/nginx/html:ro
    restart: unless-stopped

  api:
    image: myorg/myapi:v1.2.0
    vm: api-*
    replicas: 3
    environment:
      - DATABASE_URL=postgresql://database:5432/myapp
      - REDIS_URL=redis://cache:6379
    ports:
      - "8080:8080"
    depends_on:
      - database
      - cache
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

  cache:
    image: redis:7
    vm: cache-server
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped

  database:
    image: postgres:15
    vm: db-server
    environment:
      - POSTGRES_DB=myapp
      - POSTGRES_USER=myapp
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
    volumes:
      - pgdata:/var/lib/postgresql/data
    secrets:
      - db_password
    restart: unless-stopped

volumes:
  pgdata:
  redis-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

## Common Workflows

### Initial deployment

```bash
# Create VMs
azlin new --name web-server
azlin new --name api-1
azlin new --name api-2
azlin new --name api-3
azlin new --name cache-server
azlin new --name db-server

# Deploy services
azlin compose up -f docker-compose.azlin.yml
```

### Update deployment

```bash
# Update compose file
vim docker-compose.azlin.yml

# Redeploy (stops old containers, starts new)
azlin compose down -f docker-compose.azlin.yml
azlin compose up -f docker-compose.azlin.yml
```

### Rolling update

```bash
# For manual rolling updates
azlin compose up -f docker-compose.azlin.yml

# Or update individual services
azlin connect api-1
docker pull myapi:latest
docker-compose up -d api
```

## Troubleshooting

### VM not found

```
Error: No VMs found matching 'api-*'
```

**Solution**:
```bash
# List VMs
azlin list

# Create missing VMs
azlin new --name api-1
azlin new --name api-2
```

### Image pull failed

```
Error: Failed to pull image 'myapi:latest' on api-1
```

**Solution**:
```bash
# Check Docker login on VM
azlin connect api-1
docker login

# Or use public image
# Update compose file with public image
```

### Port conflict

```
Error: Port 80 already in use on web-server
```

**Solution**:
```bash
# Check what's using port
azlin connect web-server
sudo netstat -tlnp | grep :80
sudo docker ps

# Stop conflicting container or change port in compose file
```

### Service unhealthy

```
Warning: api@api-1 health check failed
```

**Solution**:
```bash
# Check service logs
azlin connect api-1
docker-compose logs api

# Check health check endpoint
curl http://localhost:8080/health
```

### Network connectivity issues

```
Error: api cannot connect to database
```

**Solution**:
```bash
# Verify service names resolve
azlin connect api-1
ping database  # Should resolve
telnet database 5432  # Should connect

# Check Docker network
docker network ls
docker network inspect bridge
```

## Related Commands

- [azlin compose down](down.md) - Stop and remove services
- [azlin compose ps](ps.md) - View service status
- [azlin new](../vm/new.md) - Create VMs for services
- [azlin list](../vm/list.md) - List available VMs
