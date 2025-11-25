# azlin compose down

Stop and remove all services from docker-compose.azlin.yml deployment.

## Synopsis

```bash
azlin compose down -f <compose-file> [OPTIONS]
```

## Description

Tears down all services defined in the compose file. This command:

1. Stops all running containers
2. Removes containers
3. Optionally removes volumes
4. Cleans up networks

## Options

| Option | Description | Required |
|--------|-------------|----------|
| `-f, --file PATH` | Path to docker-compose.azlin.yml file | Yes |
| `-g, --resource-group TEXT` | Azure resource group | No (uses current context) |
| `-h, --help` | Show help message | No |

## Examples

### Stop all services

```bash
azlin compose down -f docker-compose.azlin.yml
```

### Stop services in specific resource group

```bash
azlin compose down -f docker-compose.azlin.yml -g my-rg
```

## Output Example

```
Stopping services from docker-compose.azlin.yml...

Stopping containers...
  web@web-server: Stopping... ✓
  api@api-1: Stopping... ✓
  api@api-2: Stopping... ✓
  api@api-3: Stopping... ✓
  database@db-server: Stopping... ✓

Removing containers...
  web@web-server: Removed ✓
  api@api-1: Removed ✓
  api@api-2: Removed ✓
  api@api-3: Removed ✓
  database@db-server: Removed ✓

Cleanup complete!

Services stopped: 5
Containers removed: 5
VMs affected: 5
```

## What Gets Removed

### Removed:
- Running containers
- Stopped containers
- Networks created by compose

### Preserved:
- Named volumes (unless `--volumes` flag added in future)
- Images
- VMs
- Volume data

## Common Workflows

### Normal teardown

```bash
# Stop and remove services
azlin compose down -f docker-compose.azlin.yml

# VMs remain running
azlin list
# web-server: Running
# api-1: Running
# database: Running
```

### Complete cleanup

```bash
# Stop services
azlin compose down -f docker-compose.azlin.yml

# Stop VMs
azlin stop web-server api-* db-server

# Or delete VMs entirely
azlin destroy web-server --force
azlin destroy api-* --force
azlin destroy db-server --force
```

### Update workflow

```bash
# Stop old version
azlin compose down -f docker-compose.azlin.yml

# Update compose file or images
vim docker-compose.azlin.yml

# Deploy new version
azlin compose up -f docker-compose.azlin.yml
```

### Maintenance window

```bash
# Stop services before VM maintenance
azlin compose down -f docker-compose.azlin.yml

# Perform maintenance
azlin update web-server
azlin update api-*
azlin update db-server

# Restart services
azlin compose up -f docker-compose.azlin.yml
```

## Troubleshooting

### Container won't stop

```
Error: Timeout waiting for web@web-server to stop
```

**Solution**:
```bash
# Force stop on VM
azlin connect web-server
docker kill <container-id>
docker rm <container-id>

# Then retry
azlin compose down -f docker-compose.azlin.yml
```

### Cannot connect to VM

```
Error: Cannot connect to api-1
```

**Solution**:
```bash
# Check VM status
azlin status api-1

# If stopped, start it
azlin start api-1

# Then retry
azlin compose down -f docker-compose.azlin.yml
```

### Some services not found

```
Warning: Service 'old-service' not found on vm-1
```

This is normal if the compose file changed. azlin only stops services currently defined in the file.

**Solution** (clean up old containers):
```bash
# Connect to VMs and clean up manually
azlin connect vm-1
docker ps -a  # List all containers
docker rm $(docker ps -aq)  # Remove all stopped containers
```

## Volume Management

By default, `azlin compose down` preserves volumes and their data.

### Preserve data (default behavior)

```bash
azlin compose down -f docker-compose.azlin.yml
# Volumes preserved, data safe
```

### Manual volume cleanup

```bash
# Stop services
azlin compose down -f docker-compose.azlin.yml

# Connect to VM and remove volumes
azlin connect db-server
docker volume ls
docker volume rm pgdata
```

## Related Commands

- [azlin compose up](up.md) - Deploy services
- [azlin compose ps](ps.md) - View service status
- [azlin stop](../vm/stop.md) - Stop VMs
- [azlin destroy](../vm/destroy.md) - Delete VMs
