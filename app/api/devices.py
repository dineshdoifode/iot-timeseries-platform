from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_role
from app.database.session import get_db
from app.models.models import Device
from app.repositories.device_repository import DeviceRepository, TelemetryRepository
from app.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate, TelemetryOut

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("", response_model=DeviceOut, status_code=201)
async def create_device(
    payload: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    repo = DeviceRepository(db)
    if await repo.get(payload.device_id):
        raise HTTPException(status_code=409, detail="Device already registered")

    now = datetime.now(timezone.utc)
    device = Device(
        device_id=payload.device_id,
        name=payload.name,
        device_type=payload.device_type,
        firmware_version=payload.firmware_version,
        tags=payload.tags,
        metadata_=payload.metadata,
        device_group=payload.device_group,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    return await repo.create(device)


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    group: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    repo = DeviceRepository(db)
    return await repo.list(group=group, limit=limit, offset=offset)


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    repo = DeviceRepository(db)
    device = await repo.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    device_id: str,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    repo = DeviceRepository(db)
    if not await repo.get(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    values = payload.model_dump(exclude_unset=True)
    if "metadata" in values:
        values["metadata_"] = values.pop("metadata")
    await repo.update(device_id, values)
    return await repo.get(device_id)


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("admin")),
):
    repo = DeviceRepository(db)
    if not await repo.get(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    await repo.delete(device_id)


@router.get("/{device_id}/telemetry", response_model=list[TelemetryOut])
async def get_device_telemetry(
    device_id: str,
    metric: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=100, le=5000),
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    device_repo = DeviceRepository(db)
    if not await device_repo.get(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    telemetry_repo = TelemetryRepository(db)
    return await telemetry_repo.query(device_id, metric=metric, start=start, end=end, limit=limit)
