"""Goal parser - converts natural language to goal hierarchy."""

import json
import re
from pathlib import Path

from azlin.doit.goals.models import (
    Connection,
    ConnectionType,
    Goal,
    GoalHierarchy,
    ParsedRequest,
    ResourceType,
)


class GoalParser:
    """Parse natural language requests into structured goals."""

    def __init__(self, prompts_dir: Path | None = None):
        """Initialize parser with prompts directory."""
        if prompts_dir is None:
            prompts_dir = (
                Path(__file__).parent.parent.parent / "prompts" / "doit"
            )
        self.prompts_dir = prompts_dir
        self.system_prompt = self._load_prompt("system_prompt.md")
        self.parser_prompt = self._load_prompt("goal_parser.md")

    def _load_prompt(self, filename: str) -> str:
        """Load a prompt file."""
        path = self.prompts_dir / filename
        if path.exists():
            return path.read_text()
        return ""

    def parse(self, user_request: str) -> ParsedRequest:
        """Parse user request into structured format.

        This is a rule-based parser. In production, this would call an LLM
        to do the parsing using the goal_parser.md prompt.
        """
        # For now, implement rule-based parsing
        # In production, this would use Claude API with the parser prompt

        parsed = ParsedRequest(
            raw_request=user_request,
            primary_goal=self._extract_primary_goal(user_request),
            resource_requests=self._extract_resources(user_request),
            implied_connections=self._extract_connections(user_request),
            constraints=self._extract_constraints(user_request),
        )

        # Build goal hierarchy
        parsed.goal_hierarchy = self._build_hierarchy(parsed)

        return parsed

    def _extract_primary_goal(self, request: str) -> str:
        """Extract high-level goal description."""
        # Simple extraction - in production, LLM would do this
        return f"Deploy Azure infrastructure: {request}"

    def _extract_resources(self, request: str) -> list[dict[str, str]]:
        """Extract Azure resources mentioned in request."""
        resources = []
        request_lower = request.lower()

        # Resource patterns
        patterns = {
            "app service": ResourceType.APP_SERVICE,
            "web app": ResourceType.APP_SERVICE,
            "webapp": ResourceType.APP_SERVICE,
            "cosmos": ResourceType.COSMOS_DB,
            "cosmos db": ResourceType.COSMOS_DB,
            "cosmosdb": ResourceType.COSMOS_DB,
            "api management": ResourceType.API_MANAGEMENT,
            "apim": ResourceType.API_MANAGEMENT,
            "api gateway": ResourceType.API_MANAGEMENT,
            "storage": ResourceType.STORAGE_ACCOUNT,
            "storage account": ResourceType.STORAGE_ACCOUNT,
            "key vault": ResourceType.KEY_VAULT,
            "keyvault": ResourceType.KEY_VAULT,
            "function": ResourceType.FUNCTION_APP,
            "function app": ResourceType.FUNCTION_APP,
            "sql": ResourceType.SQL_DATABASE,
            "sql database": ResourceType.SQL_DATABASE,
            "vnet": ResourceType.VNET,
            "virtual network": ResourceType.VNET,
        }

        for pattern, resource_type in patterns.items():
            if pattern in request_lower:
                resources.append(
                    {
                        "type": resource_type.value,
                        "mentioned": pattern,
                    }
                )

        return resources

    def _extract_connections(self, request: str) -> list[dict[str, str]]:
        """Extract implied connections between resources."""
        connections = []
        request_lower = request.lower()

        # Connection patterns
        if "with" in request_lower:
            # "App Service with Cosmos DB" implies connection
            connections.append(
                {
                    "type": "integration",
                    "pattern": "with",
                }
            )

        if "behind" in request_lower:
            # "App Service behind API Management"
            connections.append(
                {
                    "type": "fronted_by",
                    "pattern": "behind",
                }
            )

        if "connected" in request_lower or "connect" in request_lower:
            connections.append(
                {
                    "type": "connection",
                    "pattern": "connected",
                }
            )

        return connections

    def _extract_constraints(self, request: str) -> dict[str, str]:
        """Extract constraints like region, SKU, etc."""
        constraints = {
            "region": "eastus",  # Default
            "environment": "dev",  # Default
        }

        request_lower = request.lower()

        # Region patterns
        regions = [
            "eastus",
            "westus",
            "westus2",
            "centralus",
            "northeurope",
            "westeurope",
        ]
        for region in regions:
            if region in request_lower:
                constraints["region"] = region
                break

        # Environment patterns
        if "production" in request_lower or "prod" in request_lower:
            constraints["environment"] = "prod"
        elif "staging" in request_lower:
            constraints["environment"] = "staging"

        return constraints

    def _build_hierarchy(self, parsed: ParsedRequest) -> GoalHierarchy:
        """Build complete goal hierarchy from parsed request."""
        hierarchy = GoalHierarchy(primary_goal=parsed.primary_goal)

        # Extract base name from request
        base_name = self._extract_base_name(parsed.raw_request)
        region = parsed.constraints.get("region", "eastus")
        env = parsed.constraints.get("environment", "dev")

        goal_counter = 1

        # Level 0: Foundation resources
        # Always need a resource group
        rg_goal = Goal(
            id=f"goal-{goal_counter:03d}",
            type=ResourceType.RESOURCE_GROUP,
            name=f"rg-{base_name}-{env}-{region}",
            level=0,
            dependencies=[],
            parameters={
                "location": region,
                "tags": {
                    "Environment": env,
                    "ManagedBy": "azlin-doit",
                    "Project": base_name,
                },
            },
        )
        hierarchy.goals.append(rg_goal)
        goal_counter += 1

        # Level 1: Independent resources (data layer)
        level1_goals = []

        # Check if Key Vault needed (usually yes if storing secrets)
        needs_keyvault = any(
            r["type"]
            in [
                ResourceType.COSMOS_DB.value,
                ResourceType.SQL_DATABASE.value,
                ResourceType.STORAGE_ACCOUNT.value,
            ]
            for r in parsed.resource_requests
        )

        if needs_keyvault:
            kv_goal = Goal(
                id=f"goal-{goal_counter:03d}",
                type=ResourceType.KEY_VAULT,
                name=f"kv-{base_name}-{env}",
                level=1,
                dependencies=[rg_goal.id],
                parameters={
                    "resource_group": rg_goal.name,
                    "location": region,
                    "sku": "standard",
                    "enable_rbac": True,
                },
            )
            hierarchy.goals.append(kv_goal)
            level1_goals.append(kv_goal)
            goal_counter += 1

        # Add requested data resources
        for resource in parsed.resource_requests:
            res_type_str = resource["type"]
            try:
                res_type = ResourceType(res_type_str)
            except ValueError:
                continue

            if res_type == ResourceType.COSMOS_DB:
                cosmos_goal = Goal(
                    id=f"goal-{goal_counter:03d}",
                    type=ResourceType.COSMOS_DB,
                    name=f"cosmos-{base_name}-{env}",
                    level=1,
                    dependencies=[rg_goal.id],
                    parameters={
                        "resource_group": rg_goal.name,
                        "location": region,
                        "offer_type": "Standard",
                        "kind": "GlobalDocumentDB",
                    },
                )
                hierarchy.goals.append(cosmos_goal)
                level1_goals.append(cosmos_goal)
                goal_counter += 1

            elif res_type == ResourceType.STORAGE_ACCOUNT:
                storage_goal = Goal(
                    id=f"goal-{goal_counter:03d}",
                    type=ResourceType.STORAGE_ACCOUNT,
                    name=self._make_storage_name(base_name, env, region),
                    level=1,
                    dependencies=[rg_goal.id],
                    parameters={
                        "resource_group": rg_goal.name,
                        "location": region,
                        "sku": "Standard_LRS",
                        "https_only": True,
                    },
                )
                hierarchy.goals.append(storage_goal)
                level1_goals.append(storage_goal)
                goal_counter += 1

        # Level 2: Compute resources (depend on data layer)
        level2_goals = []
        level1_ids = [g.id for g in level1_goals]

        for resource in parsed.resource_requests:
            res_type_str = resource["type"]
            try:
                res_type = ResourceType(res_type_str)
            except ValueError:
                continue

            if res_type == ResourceType.APP_SERVICE:
                # Need App Service Plan first
                plan_goal = Goal(
                    id=f"goal-{goal_counter:03d}",
                    type=ResourceType.APP_SERVICE_PLAN,
                    name=f"plan-{base_name}-{env}",
                    level=2,
                    dependencies=[rg_goal.id],
                    parameters={
                        "resource_group": rg_goal.name,
                        "location": region,
                        "sku": "B1" if env == "dev" else "S1",
                        "os_type": "Linux",
                    },
                )
                hierarchy.goals.append(plan_goal)
                goal_counter += 1

                # Then App Service
                app_goal = Goal(
                    id=f"goal-{goal_counter:03d}",
                    type=ResourceType.APP_SERVICE,
                    name=f"app-{base_name}-{env}",
                    level=2,
                    dependencies=[rg_goal.id, plan_goal.id] + level1_ids,
                    parameters={
                        "resource_group": rg_goal.name,
                        "location": region,
                        "service_plan_id": plan_goal.id,
                        "managed_identity": True,
                        "runtime": "node|18-lts",
                    },
                )
                hierarchy.goals.append(app_goal)
                level2_goals.append(app_goal)
                goal_counter += 1

            elif res_type == ResourceType.API_MANAGEMENT:
                apim_goal = Goal(
                    id=f"goal-{goal_counter:03d}",
                    type=ResourceType.API_MANAGEMENT,
                    name=f"apim-{base_name}-{env}",
                    level=2,
                    dependencies=[rg_goal.id],
                    parameters={
                        "resource_group": rg_goal.name,
                        "location": region,
                        "sku": "Developer" if env == "dev" else "Standard",
                        "publisher_name": "Organization",
                        "publisher_email": "admin@example.com",
                    },
                )
                hierarchy.goals.append(apim_goal)
                level2_goals.append(apim_goal)
                goal_counter += 1

        # Level 3: Connections and configurations
        if parsed.implied_connections:
            self._add_connection_goals(
                hierarchy, level1_goals, level2_goals, goal_counter
            )

        return hierarchy

    def _extract_base_name(self, request: str) -> str:
        """Extract a base name for resources from request."""
        # Simple heuristic - in production, LLM would suggest better names
        request_clean = re.sub(r"[^a-z0-9]+", "-", request.lower())
        words = request_clean.split("-")
        # Take first meaningful word
        for word in words:
            if len(word) > 2 and word not in [
                "give",
                "me",
                "the",
                "with",
                "and",
                "for",
            ]:
                return word[:10]
        return "webapp"

    def _make_storage_name(self, base: str, env: str, region: str) -> str:
        """Create valid storage account name (no hyphens, lowercase, < 24 chars)."""
        # Remove hyphens and limit length
        name = f"st{base}{env}{region}".replace("-", "")[:24]
        return name.lower()

    def _add_connection_goals(
        self,
        hierarchy: GoalHierarchy,
        level1_goals: list[Goal],
        level2_goals: list[Goal],
        start_counter: int,
    ) -> None:
        """Add connection goals between resources."""
        counter = start_counter

        # Find resources that need connections
        app_service_goals = [
            g for g in level2_goals if g.type == ResourceType.APP_SERVICE
        ]
        cosmos_goals = [
            g for g in level1_goals if g.type == ResourceType.COSMOS_DB
        ]
        kv_goals = [g for g in level1_goals if g.type == ResourceType.KEY_VAULT]

        # Connect App Service to Cosmos via Key Vault
        if app_service_goals and cosmos_goals and kv_goals:
            for app in app_service_goals:
                for cosmos in cosmos_goals:
                    for kv in kv_goals:
                        # Connection goal
                        conn_goal = Goal(
                            id=f"goal-{counter:03d}",
                            type=ResourceType.CONNECTION,
                            name=f"connect-{app.name}-to-{cosmos.name}",
                            level=3,
                            dependencies=[app.id, cosmos.id, kv.id],
                            parameters={
                                "from": app.id,
                                "to": cosmos.id,
                                "via": kv.id,
                                "method": "key_vault_secret",
                            },
                        )
                        hierarchy.goals.append(conn_goal)

                        # Add connection metadata
                        conn = Connection(
                            from_goal_id=app.id,
                            to_goal_id=cosmos.id,
                            connection_type=ConnectionType.CONNECTION_STRING,
                            via=kv.id,
                        )
                        hierarchy.connections.append(conn)
                        counter += 1

        # Connect API Management to App Service
        apim_goals = [
            g for g in level2_goals if g.type == ResourceType.API_MANAGEMENT
        ]
        if apim_goals and app_service_goals:
            for apim in apim_goals:
                for app in app_service_goals:
                    conn_goal = Goal(
                        id=f"goal-{counter:03d}",
                        type=ResourceType.CONNECTION,
                        name=f"connect-{apim.name}-to-{app.name}",
                        level=3,
                        dependencies=[apim.id, app.id],
                        parameters={
                            "from": apim.id,
                            "to": app.id,
                            "method": "api_backend",
                        },
                    )
                    hierarchy.goals.append(conn_goal)

                    conn = Connection(
                        from_goal_id=apim.id,
                        to_goal_id=app.id,
                        connection_type=ConnectionType.API_BACKEND,
                    )
                    hierarchy.connections.append(conn)
                    counter += 1
