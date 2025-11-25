# azlin compose ps

Show status of services from docker-compose.azlin.yml deployment.

## Synopsis

```bash
azlin compose ps -f <compose-file> [OPTIONS]
```

## Description

Displays current status of all services defined in the compose file, including:
- Container state (running/stopped/unhealthy)
- VM location
- Port mappings
- Health status
- Resource usage

## Options

| Option | Description | Required |
|--------|-------------|----------|
| `-f, --file PATH` | Path to docker-compose.azlin.yml file | Yes |
| `-g, --resource-group TEXT` | Azure resource group | No (uses current context) |
| `-h, --help` | Show help message | No |

## Examples

### View service status

```bash
azlin compose ps -f docker-compose.azlin.yml
```

### View status in specific resource group

```bash
azlin compose ps -f docker-compose.azlin.yml -g my-rg
```

## Output Example

```
Services from docker-compose.azlin.yml

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Service      VM              Status      Health    Ports              Uptime
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
web          web-server      Running     Healthy   80:80, 443:443     2d 5h
api          api-1           Running     Healthy   8080:8080          2d 5h
api          api-2           Running     Healthy   8080:8080          2d 5h
api          api-3           Running     Healthy   8080:8080          2d 5h
cache        cache-server    Running     N/A       6379:6379          2d 5h
database     db-server       Running     Healthy   5432:5432          2d 5h
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total: 6 services across 5 VMs
  Running: 6
  Stopped: 0
  Unhealthy: 0
```

## Status Values

| Status | Description |
|--------|-------------|
| Running | Container is running normally |
| Stopped | Container is stopped |
| Starting | Container is starting up |
| Unhealthy | Container health check failing |
| Restarting | Container is restarting |
| Dead | Container failed to start |

## Health Status

| Health | Description |
|--------|-------------|
| Healthy | Health checks passing |
| Unhealthy | Health checks failing |
| Starting | Health checks not yet run |
| N/A | No health check configured |

## Detailed Output

### Service with issues

```
Service      VM              Status      Health      Ports         Uptime
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
api          api-1           Running     Unhealthy   8080:8080     10m
                             └─ Health check failed: connection refused

api          api-2           Stopped     N/A         -             -
                             └─ Container exited with code 1

database     db-server       Dead        N/A         -             -
                             └─ Failed to start: port 5432 already in use
```

## Common Workflows

### Monitor deployment

```bash
# Deploy services
azlin compose up -f docker-compose.azlin.yml

# Check status immediately
azlin compose ps -f docker-compose.azlin.yml

# Wait and check again
sleep 30
azlin compose ps -f docker-compose.azlin.yml
```

### Continuous monitoring

```bash
# Watch status
watch -n 5 'azlin compose ps -f docker-compose.azlin.yml'
```

### Check specific service

```bash
# View all services
azlin compose ps -f docker-compose.azlin.yml

# Connect to VM and check specific service
azlin connect api-1
docker ps
docker logs <container-id>
```

### Production health check

```bash
#!/bin/bash
# check-health.sh

output=$(azlin compose ps -f docker-compose.azlin.yml)

if echo "$output" | grep -q "Unhealthy"; then
    echo "ALERT: Unhealthy services detected!"
    echo "$output"
    exit 1
fi

echo "All services healthy"
```

## Troubleshooting Workflows

### Service not running

```bash
# Check status
azlin compose ps -f docker-compose.azlin.yml

# If service stopped, check logs
azlin connect <vm-name>
docker-compose logs <service-name>

# Restart service
azlin compose down -f docker-compose.azlin.yml
azlin compose up -f docker-compose.azlin.yml
```

### Unhealthy service

```bash
# Check status
azlin compose ps -f docker-compose.azlin.yml
# api@api-1: Running (Unhealthy)

# Connect and investigate
azlin connect api-1
docker ps
docker exec <container-id> curl http://localhost:8080/health

# Check logs
docker logs <container-id>

# Check health check config
docker inspect <container-id> | grep -A 10 Healthcheck
```

### Service not listed

```bash
# Check status
azlin compose ps -f docker-compose.azlin.yml
# Service 'worker' not found

# Verify service in compose file
cat docker-compose.azlin.yml | grep -A 5 "worker:"

# If missing, service never deployed
# If present, VM might be wrong or not exist
azlin list  # Check VMs exist
```

## Comparing with Docker Compose

Standard docker-compose ps:
```bash
# Only works on single host
docker-compose ps
```

azlin compose ps:
```bash
# Works across multiple VMs
azlin compose ps -f docker-compose.azlin.yml
```

## Integration with Monitoring

### Export to JSON (future enhancement)

```bash
# Could be added:
azlin compose ps -f docker-compose.azlin.yml --json
```

### Prometheus metrics

```bash
# Example integration script
#!/bin/bash

output=$(azlin compose ps -f docker-compose.azlin.yml)

# Parse output and expose metrics
echo "compose_services_running $(echo "$output" | grep Running | wc -l)"
echo "compose_services_unhealthy $(echo "$output" | grep Unhealthy | wc -l)"
```

## Related Commands

- [azlin compose up](up.md) - Deploy services
- [azlin compose down](down.md) - Stop services
- [azlin status](../vm/status.md) - View VM status
- `docker logs <container>` - View container logs (run via azlin connect)
