# AI Features

azlin includes AI-powered features for natural language VM management and autonomous optimization.

## Commands

### `azlin do` - Natural Language

Run VM management tasks using natural language:

```bash
azlin do "create a new VM with 16GB RAM in westus2"
azlin do "stop all VMs that have been idle for more than 2 hours"
azlin do "show me the most expensive VMs this month"
```

[:octicons-arrow-right-24: Do Command Reference](do.md)

### `azlin doit` - Infrastructure Deployment

Deploy complex infrastructure from natural language descriptions:

```bash
azlin doit deploy "3 web servers behind a load balancer"
azlin doit status
azlin doit cleanup
```

[:octicons-arrow-right-24: Doit Command Reference](azdoit.md)

### `azlin autopilot` - Autonomous Optimization

Enable automated VM lifecycle management:

```bash
azlin autopilot enable myvm --health-checks --self-healing
azlin autopilot status
azlin autopilot config --idle-timeout 30m
```

[:octicons-arrow-right-24: Autopilot Reference](autopilot.md)

## How It Works

AI features use language models to translate natural language into azlin commands. The `do` command parses your intent, maps it to the appropriate azlin CLI commands, and executes them with confirmation.

## See Also

- [Natural Language Details](natural-language.md)
- [Command Reference](../commands/index.md)
