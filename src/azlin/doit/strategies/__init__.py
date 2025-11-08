"""Azure resource deployment strategies."""

from azlin.doit.goals import ResourceType
from azlin.doit.strategies.api_management import APIManagementStrategy
from azlin.doit.strategies.app_service import (
    AppServicePlanStrategy,
    AppServiceStrategy,
)
from azlin.doit.strategies.base import Strategy
from azlin.doit.strategies.connection import ConnectionStrategy
from azlin.doit.strategies.cosmos_db import CosmosDBStrategy
from azlin.doit.strategies.keyvault import KeyVaultStrategy
from azlin.doit.strategies.resource_group import ResourceGroupStrategy
from azlin.doit.strategies.storage import StorageStrategy

# Strategy registry
_STRATEGIES: dict[ResourceType, type[Strategy]] = {
    ResourceType.RESOURCE_GROUP: ResourceGroupStrategy,
    ResourceType.STORAGE_ACCOUNT: StorageStrategy,
    ResourceType.KEY_VAULT: KeyVaultStrategy,
    ResourceType.COSMOS_DB: CosmosDBStrategy,
    ResourceType.APP_SERVICE_PLAN: AppServicePlanStrategy,
    ResourceType.APP_SERVICE: AppServiceStrategy,
    ResourceType.API_MANAGEMENT: APIManagementStrategy,
    ResourceType.CONNECTION: ConnectionStrategy,
}


def get_strategy(resource_type: ResourceType) -> Strategy:
    """Get strategy instance for resource type."""
    strategy_class = _STRATEGIES.get(resource_type)
    if strategy_class is None:
        raise ValueError(f"No strategy for resource type: {resource_type}")
    return strategy_class()


__all__ = [
    "Strategy",
    "ResourceGroupStrategy",
    "StorageStrategy",
    "KeyVaultStrategy",
    "CosmosDBStrategy",
    "AppServicePlanStrategy",
    "AppServiceStrategy",
    "APIManagementStrategy",
    "ConnectionStrategy",
    "get_strategy",
]
