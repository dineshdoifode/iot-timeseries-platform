from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_role
from app.database.session import get_db
from app.models.models import AlarmRule
from app.repositories.alarm_repository import AlarmRepository, AlarmRuleRepository
from app.schemas.alarm import AlarmOut, AlarmRuleCreate, AlarmRuleOut, AlarmRuleUpdate

router = APIRouter(prefix="/api/v1/alarms", tags=["alarms"])


# ---- Alarm rules (operator+ to write, viewer+ to read) ----

@router.post("/rules", response_model=AlarmRuleOut, status_code=201)
async def create_rule(
    payload: AlarmRuleCreate,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    now = datetime.now(timezone.utc)
    rule = AlarmRule(
        name=payload.name,
        rule_type=payload.rule_type,
        metric=payload.metric,
        threshold=payload.threshold,
        timeout_seconds=payload.timeout_seconds,
        device_group=payload.device_group,
        device_id=payload.device_id,
        severity=payload.severity,
        is_enabled=payload.is_enabled,
        notify_channels=payload.notify_channels,
        created_at=now,
        updated_at=now,
    )
    repo = AlarmRuleRepository(db)
    return await repo.create(rule)


@router.get("/rules", response_model=list[AlarmRuleOut])
async def list_rules(
    enabled_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    repo = AlarmRuleRepository(db)
    return await repo.list(enabled_only=enabled_only)


@router.get("/rules/{rule_id}", response_model=AlarmRuleOut)
async def get_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    repo = AlarmRuleRepository(db)
    rule = await repo.get(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alarm rule not found")
    return rule


@router.patch("/rules/{rule_id}", response_model=AlarmRuleOut)
async def update_rule(
    rule_id: int,
    payload: AlarmRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    repo = AlarmRuleRepository(db)
    if not await repo.get(rule_id):
        raise HTTPException(status_code=404, detail="Alarm rule not found")
    values = payload.model_dump(exclude_unset=True)
    await repo.update(rule_id, values)
    return await repo.get(rule_id)


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    repo = AlarmRuleRepository(db)
    if not await repo.get(rule_id):
        raise HTTPException(status_code=404, detail="Alarm rule not found")
    await repo.delete(rule_id)


# ---- Alarm instances ----

@router.get("", response_model=list[AlarmOut])
async def list_alarms(
    device_id: str | None = None,
    active_only: bool = False,
    limit: int = Query(default=100, le=1000),
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    repo = AlarmRepository(db)
    return await repo.list(device_id=device_id, active_only=active_only, limit=limit)


@router.post("/{alarm_id}/resolve", status_code=204)
async def resolve_alarm(
    alarm_id: int,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    """Manual override — e.g. an operator investigated and confirmed it's a false positive.
    Note the alarm engine will re-fire this on the next cycle if the underlying
    condition is still true; resolving is for acknowledged/handled alarms, not suppression."""
    repo = AlarmRepository(db)
    await repo.resolve(alarm_id)
