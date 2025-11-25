# azlin bastion delete

Delete Azure Bastion host.

## Synopsis

```bash
azlin bastion delete [NAME] [OPTIONS]
```

## Examples

```bash
# Delete Bastion
azlin bastion delete my-bastion

# Force delete without confirmation
azlin bastion delete my-bastion --force
```

## Cost Savings

Deleting Bastion saves ~$140-290/month depending on SKU.

## Related Commands

- [azlin bastion list](list.md) - List Bastion hosts
- [azlin bastion create](create.md) - Create Bastion
