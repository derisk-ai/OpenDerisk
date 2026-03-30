"""Risk Dashboard API endpoints.

This module provides REST API endpoints for risk dashboard management.
"""

from functools import cache
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security.http import HTTPAuthorizationCredentials, HTTPBearer

from derisk.component import SystemApp
from derisk_serve.core import Result

from ..config import SERVE_SERVICE_COMPONENT_NAME, ServeConfig
from ..service.service import Service
from .schemas import (
    EntityTypeRequest,
    EntityTypeResponse,
    EntityRequest,
    EntityResponse,
    EntityRelationRequest,
    EntityRelationResponse,
    RiskCheckRecordResponse,
    EntitySubscriptionRequest,
    EntitySubscriptionResponse,
    RiskSummaryResponse,
    HeatmapResponse,
    HeatmapDataPoint,
    EntitySkillConfigRequest,
    EntitySkillConfigResponse,
)

router = APIRouter()

global_system_app: Optional[SystemApp] = None


def get_service() -> Service:
    """Get the service instance."""
    return global_system_app.get_component(SERVE_SERVICE_COMPONENT_NAME, Service)


get_bearer_token = HTTPBearer(auto_error=False)


@cache
def _parse_api_keys(api_keys: str) -> List[str]:
    """Parse the string api keys to a list."""
    if not api_keys:
        return []
    return [key.strip() for key in api_keys.split(",")]


async def check_api_key(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(get_bearer_token),
    request: Request = None,
    service: Service = Depends(get_service),
) -> Optional[str]:
    """Check the api key."""
    if request.url.path.startswith("/api/v1"):
        return None

    if service.config.api_keys:
        api_keys = _parse_api_keys(service.config.api_keys)
        if auth is None or (token := auth.credentials) not in api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": {
                        "message": "",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key",
                    }
                },
            )
        return token
    else:
        return None


# ============ Health Check ============

@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# ============ Dashboard Summary ============

@router.get(
    "/summary",
    response_model=Result[RiskSummaryResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_risk_summary(
    service: Service = Depends(get_service),
) -> Result[RiskSummaryResponse]:
    """Get risk summary for all entities.

    Returns:
        Risk summary with counts for each risk level.
    """
    summary = service.get_risk_summary()
    return Result.succ(summary)


@router.get(
    "/heatmap",
    response_model=Result[HeatmapResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_heatmap(
    days: int = Query(default=30, description="Number of days to include"),
    service: Service = Depends(get_service),
) -> Result[HeatmapResponse]:
    """Get heatmap data for the specified number of days.

    Args:
        days: Number of days to include (default 30).

    Returns:
        Heatmap data with risk counts for each day.
    """
    heatmap_data = service.get_heatmap_data(days)
    return Result.succ(HeatmapResponse(data=heatmap_data))


# ============ Entity Type Endpoints ============

@router.get(
    "/entity-types",
    response_model=Result[List[EntityTypeResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_entity_types(
    service: Service = Depends(get_service),
) -> Result[List[EntityTypeResponse]]:
    """List all entity types.

    Returns:
        List of entity types.
    """
    types = service.list_entity_types()
    return Result.succ(types)


@router.post(
    "/entity-types",
    response_model=Result[EntityTypeResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_entity_type(
    request: EntityTypeRequest,
    service: Service = Depends(get_service),
) -> Result[EntityTypeResponse]:
    """Create a new entity type.

    Args:
        request: The entity type creation request.

    Returns:
        The created entity type.
    """
    response = service.create_entity_type(request)
    return Result.succ(response)


@router.get(
    "/entity-types/{type_id}",
    response_model=Result[EntityTypeResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_entity_type(
    type_id: str,
    service: Service = Depends(get_service),
) -> Result[EntityTypeResponse]:
    """Get a specific entity type by ID.

    Args:
        type_id: The entity type ID.

    Returns:
        The entity type details.
    """
    response = service.get_entity_type(type_id)
    if not response:
        raise HTTPException(status_code=404, detail=f"Entity type not found: {type_id}")
    return Result.succ(response)


@router.delete(
    "/entity-types/{type_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_entity_type(
    type_id: str,
    service: Service = Depends(get_service),
):
    """Delete an entity type.

    Args:
        type_id: The entity type ID.
    """
    removed = service.delete_entity_type(type_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Entity type not found: {type_id}")
    return Result.succ(None)


# ============ Entity Endpoints ============

@router.get(
    "/entities",
    response_model=Result[List[EntityResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_entities(
    type_id: Optional[str] = Query(default=None, description="Filter by entity type"),
    risk_level: Optional[str] = Query(default=None, description="Filter by risk level"),
    user_id: Optional[str] = Query(default=None, description="Filter by subscribed user"),
    service: Service = Depends(get_service),
) -> Result[List[EntityResponse]]:
    """List all entities with optional filters.

    Args:
        type_id: Filter by entity type ID.
        risk_level: Filter by risk level.
        user_id: Filter by subscribed user ID.

    Returns:
        List of entities.
    """
    entities = service.list_entities(type_id=type_id, risk_level=risk_level, user_id=user_id)
    return Result.succ(entities)


@router.post(
    "/entities",
    response_model=Result[EntityResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_entity(
    request: EntityRequest,
    service: Service = Depends(get_service),
) -> Result[EntityResponse]:
    """Create a new entity.

    Args:
        request: The entity creation request.

    Returns:
        The created entity.
    """
    response = service.create_entity(request)
    return Result.succ(response)


@router.get(
    "/entities/{entity_id}",
    response_model=Result[EntityResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_entity(
    entity_id: str,
    service: Service = Depends(get_service),
) -> Result[EntityResponse]:
    """Get a specific entity by ID.

    Args:
        entity_id: The entity ID.

    Returns:
        The entity details.
    """
    response = service.get_entity(entity_id)
    if not response:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    return Result.succ(response)


@router.patch(
    "/entities/{entity_id}",
    response_model=Result[EntityResponse],
    dependencies=[Depends(check_api_key)],
)
async def update_entity(
    entity_id: str,
    request: EntityRequest,
    service: Service = Depends(get_service),
) -> Result[EntityResponse]:
    """Update an entity.

    Args:
        entity_id: The entity ID.
        request: The update request.

    Returns:
        The updated entity.
    """
    try:
        response = service.update_entity(entity_id, request)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/entities/{entity_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_entity(
    entity_id: str,
    service: Service = Depends(get_service),
):
    """Delete an entity.

    Args:
        entity_id: The entity ID.
    """
    removed = service.delete_entity(entity_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Entity not found: {entity_id}")
    return Result.succ(None)


@router.post(
    "/entities/{entity_id}/check",
    response_model=Result[RiskCheckRecordResponse],
    dependencies=[Depends(check_api_key)],
)
async def trigger_check(
    entity_id: str,
    service: Service = Depends(get_service),
) -> Result[RiskCheckRecordResponse]:
    """Trigger a risk check for an entity.

    Args:
        entity_id: The entity ID.

    Returns:
        The check record.
    """
    try:
        response = await service.trigger_check(entity_id)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/entities/{entity_id}/history",
    response_model=Result[List[RiskCheckRecordResponse]],
    dependencies=[Depends(check_api_key)],
)
async def get_check_history(
    entity_id: str,
    limit: int = Query(default=10, description="Maximum number of records"),
    service: Service = Depends(get_service),
) -> Result[List[RiskCheckRecordResponse]]:
    """Get check history for an entity.

    Args:
        entity_id: The entity ID.
        limit: Maximum number of records.

    Returns:
        List of check records.
    """
    history = service.get_check_history(entity_id, limit)
    return Result.succ(history)


# ============ Entity Relation Endpoints ============

@router.get(
    "/entities/{entity_id}/relations",
    response_model=Result[List[EntityRelationResponse]],
    dependencies=[Depends(check_api_key)],
)
async def get_entity_relations(
    entity_id: str,
    service: Service = Depends(get_service),
) -> Result[List[EntityRelationResponse]]:
    """Get all relations for an entity.

    Args:
        entity_id: The entity ID.

    Returns:
        List of entity relations.
    """
    relations = service.get_entity_relations(entity_id)
    return Result.succ(relations)


@router.post(
    "/relations",
    response_model=Result[EntityRelationResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_relation(
    request: EntityRelationRequest,
    service: Service = Depends(get_service),
) -> Result[EntityRelationResponse]:
    """Create an entity relation.

    Args:
        request: The relation creation request.

    Returns:
        The created relation.
    """
    response = service.create_relation(request)
    return Result.succ(response)


@router.delete(
    "/relations/{relation_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_relation(
    relation_id: str,
    service: Service = Depends(get_service),
):
    """Delete an entity relation.

    Args:
        relation_id: The relation ID.
    """
    removed = service.delete_relation(relation_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Relation not found: {relation_id}")
    return Result.succ(None)


# ============ Subscription Endpoints ============

@router.get(
    "/subscriptions",
    response_model=Result[List[EntitySubscriptionResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_subscriptions(
    user_id: str = Query(..., description="User ID"),
    service: Service = Depends(get_service),
) -> Result[List[EntitySubscriptionResponse]]:
    """List all subscriptions for a user.

    Args:
        user_id: The user ID.

    Returns:
        List of subscriptions.
    """
    subscriptions = service.list_subscriptions(user_id)
    return Result.succ(subscriptions)


@router.post(
    "/subscriptions",
    response_model=Result[EntitySubscriptionResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_subscription(
    request: EntitySubscriptionRequest,
    service: Service = Depends(get_service),
) -> Result[EntitySubscriptionResponse]:
    """Create a subscription.

    Args:
        request: The subscription creation request.

    Returns:
        The created subscription.
    """
    response = service.create_subscription(request)
    return Result.succ(response)


@router.delete(
    "/subscriptions/{subscription_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_subscription(
    subscription_id: str,
    service: Service = Depends(get_service),
):
    """Delete a subscription.

    Args:
        subscription_id: The subscription ID.
    """
    removed = service.delete_subscription(subscription_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Subscription not found: {subscription_id}")
    return Result.succ(None)


# ============ Entity Skill Config Endpoints ============

@router.get(
    "/entities/{entity_id}/skills",
    response_model=Result[List[EntitySkillConfigResponse]],
    dependencies=[Depends(check_api_key)],
)
async def list_entity_skills(
    entity_id: str,
    service: Service = Depends(get_service),
) -> Result[List[EntitySkillConfigResponse]]:
    """List all skill configurations for an entity.

    Args:
        entity_id: The entity ID.

    Returns:
        List of skill configurations.
    """
    skills = service.list_entity_skills(entity_id)
    return Result.succ(skills)


@router.post(
    "/entities/{entity_id}/skills",
    response_model=Result[EntitySkillConfigResponse],
    dependencies=[Depends(check_api_key)],
)
async def create_entity_skill(
    entity_id: str,
    request: EntitySkillConfigRequest,
    service: Service = Depends(get_service),
) -> Result[EntitySkillConfigResponse]:
    """Add a skill configuration for an entity.

    Args:
        entity_id: The entity ID.
        request: The skill configuration request.

    Returns:
        The created skill configuration.
    """
    # Ensure entity_id in path matches request
    request.entity_id = entity_id
    try:
        response = service.create_entity_skill(request)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/entities/{entity_id}/skills/{skill_id}",
    response_model=Result[EntitySkillConfigResponse],
    dependencies=[Depends(check_api_key)],
)
async def get_entity_skill(
    entity_id: str,
    skill_id: str,
    service: Service = Depends(get_service),
) -> Result[EntitySkillConfigResponse]:
    """Get a specific skill configuration.

    Args:
        entity_id: The entity ID.
        skill_id: The skill configuration ID.

    Returns:
        The skill configuration.
    """
    response = service.get_entity_skill(entity_id, skill_id)
    if not response:
        raise HTTPException(status_code=404, detail=f"Skill configuration not found: {skill_id}")
    return Result.succ(response)


@router.patch(
    "/entities/{entity_id}/skills/{skill_id}",
    response_model=Result[EntitySkillConfigResponse],
    dependencies=[Depends(check_api_key)],
)
async def update_entity_skill(
    entity_id: str,
    skill_id: str,
    request: EntitySkillConfigRequest,
    service: Service = Depends(get_service),
) -> Result[EntitySkillConfigResponse]:
    """Update a skill configuration.

    Args:
        entity_id: The entity ID.
        skill_id: The skill configuration ID.
        request: The update request.

    Returns:
        The updated skill configuration.
    """
    try:
        response = service.update_entity_skill(entity_id, skill_id, request)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/entities/{entity_id}/skills/{skill_id}/toggle",
    response_model=Result[EntitySkillConfigResponse],
    dependencies=[Depends(check_api_key)],
)
async def toggle_entity_skill(
    entity_id: str,
    skill_id: str,
    service: Service = Depends(get_service),
) -> Result[EntitySkillConfigResponse]:
    """Toggle a skill configuration's enabled state.

    Args:
        entity_id: The entity ID.
        skill_id: The skill configuration ID.

    Returns:
        The updated skill configuration.
    """
    try:
        response = service.toggle_entity_skill(entity_id, skill_id)
        return Result.succ(response)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/entities/{entity_id}/skills/{skill_id}",
    dependencies=[Depends(check_api_key)],
)
async def delete_entity_skill(
    entity_id: str,
    skill_id: str,
    service: Service = Depends(get_service),
):
    """Delete a skill configuration.

    Args:
        entity_id: The entity ID.
        skill_id: The skill configuration ID.
    """
    try:
        removed = service.delete_entity_skill(entity_id, skill_id)
        return Result.succ(None)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))


# ============ Initialization ============

def init_endpoints(system_app: SystemApp, config: ServeConfig) -> None:
    """Initialize the endpoints.

    Args:
        system_app: The system application instance.
        config: The service configuration.
    """
    global global_system_app
    system_app.register(Service, config=config)
    global_system_app = system_app