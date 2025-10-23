"""Command groups for azlin CLI."""

from azlin.commands.auth import auth_group
from azlin.commands.storage import storage_group

__all__ = ["auth_group", "storage_group"]
