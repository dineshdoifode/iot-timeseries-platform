from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_role
from app.database.session import get_db
from app.models.models import Alarm, Device, DeviceStatus, Telemetry

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("/fleet")
async def fleet_stats(
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    total_devices = (await db.execute(select(func.count()).select_from(Device))).scalar_one()
    active_devices = (
        await db.execute(select(func.count()).select_from(Device).where(Device.is_active.is_(True)))
    ).scalar_one()
    active_alarms = (
        await db.execute(select(func.count()).select_from(Alarm).where(Alarm.is_active.is_(True)))
    ).scalar_one()

    # "Online" = most recent status row per device says online, seen in last 5 min.
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    latest_status_subq = (
        select(
            DeviceStatus.device_id,
            func.max(DeviceStatus.time).label("latest_time"),
        )
        .group_by(DeviceStatus.device_id)
        .subquery()
    )
    online_count_stmt = (
        select(func.count())
        .select_from(DeviceStatus)
        .join(
            latest_status_subq,
            (DeviceStatus.device_id == latest_status_subq.c.device_id)
            & (DeviceStatus.time == latest_status_subq.c.latest_time),
        )
        .where(DeviceStatus.status == "online", DeviceStatus.time >= cutoff)
    )
    online_devices = (await db.execute(online_count_stmt)).scalar_one()

    telemetry_last_hour = (
        await db.execute(
            select(func.count())
            .select_from(Telemetry)
            .where(Telemetry.time >= datetime.now(timezone.utc) - timedelta(hours=1))
        )
    ).scalar_one()

    return {
        "total_devices": total_devices,
        "active_devices": active_devices,
        "online_devices": online_devices,
        "offline_or_unknown_devices": active_devices - online_devices,
        "active_alarms": active_alarms,
        "telemetry_points_last_hour": telemetry_last_hour,
    }


@router.get("/devices/{device_id}")
async def device_stats(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("viewer")),
):
    metric_stats_stmt = (
        select(
            Telemetry.metric,
            func.count().label("sample_count"),
            func.avg(Telemetry.value).label("avg_value"),
            func.min(Telemetry.value).label("min_value"),
            func.max(Telemetry.value).label("max_value"),
            func.max(Telemetry.time).label("last_seen"),
        )
        .where(Telemetry.device_id == device_id)
        .group_by(Telemetry.metric)
    )
    result = await db.execute(metric_stats_stmt)
    metrics = [
        {
            "metric": row.metric,
            "sample_count": row.sample_count,
            "avg_value": round(row.avg_value, 3) if row.avg_value is not None else None,
            "min_value": row.min_value,
            "max_value": row.max_value,
            "last_seen": row.last_seen,
        }
        for row in result.all()
    ]

    active_alarm_count = (
        await db.execute(
            select(func.count())
            .select_from(Alarm)
            .where(Alarm.device_id == device_id, Alarm.is_active.is_(True))
        )
    ).scalar_one()

    return {"device_id": device_id, "metrics": metrics, "active_alarms": active_alarm_count}
