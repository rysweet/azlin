# Parallel Execution

Understanding parallelism, performance tuning, and best practices for batch operations.

## How Parallelism Works

azlin uses thread pools to execute operations on multiple VMs simultaneously:

- Default: 10 parallel workers
- Queue remaining VMs
- Continue on individual failures

## Tuning Guidelines

### Operation Type

**Light** (status, simple commands): 10-20 workers
```bash
azlin batch command 'uptime' --all --max-workers 20
```

**Medium** (updates, file operations): 5-10 workers
```bash
azlin batch sync --all --max-workers 8
```

**Heavy** (builds, migrations): 1-5 workers
```bash
azlin batch command 'docker build .' --all --max-workers 3
```

### Network Considerations

- Azure Bastion connections: Reduce to 5-10 workers
- Cross-region VMs: Reduce parallelism
- Local region VMs: Can use higher parallelism

## Performance Tips

1. **Start conservative**: Begin with default (10), adjust based on results
2. **Monitor connections**: Watch for SSH timeouts with high parallelism
3. **Consider timeouts**: Long operations need higher timeouts
4. **Test first**: Run on subset before full fleet

## Example Tuning

```bash
# Too aggressive - may timeout
azlin batch command 'apt upgrade -y' --all --max-workers 20

# Better - balanced for heavy operation
azlin batch command 'apt upgrade -y' --all --max-workers 5 --timeout 900
```

## See Also

- [Batch Operations](index.md)
- [Troubleshooting](../troubleshooting/connection.md)

---

*Documentation last updated: 2025-11-24*
