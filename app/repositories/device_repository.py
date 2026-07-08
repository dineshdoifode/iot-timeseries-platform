from datetime import datetime, timezone

from cachetools import TTLCache
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Device, Telemetry

# Every inbound MQTT message triggers a "does this device exist?" check
# (upsert_from_telemetry). At any real fleet volume that's a lot of
# otherwise-identical SELECTs for the same handful of device_ids, so we
# cache known-good IDs for a short TTL. Registrations/deletes invalidate
# their own entry immediately rather than waiting out the TTL.
_known_device_cache: TTLCache = TTLCache(maxsize=10_000, ttl=60)


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, device: Device) -> Device:
        self.session.add(device)
        await self.session.commit()
        await self.session.refresh(device)
        _known_device_cache[device.device_id] = True
        return device

    async def get(self, device_id: str) -> Device | None:
        result = await self.session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def list(self, group: str | None = None, limit: int = 100, offset: int = 0) -> list[Device]:
        stmt = select(Device)
        if group:
            stmt = stmt.where(Device.device_group == group)
        stmt = stmt.limit(limit).offset(offset).order_by(Device.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, device_id: str, values: dict) -> None:
        values["updated_at"] = datetime.now(timezone.utc)
        await self.session.execute(
            update(Device).where(Device.device_id == device_id).values(**values)
        )
        await self.session.commit()

    async def delete(self, device_id: str) -> None:
        device = await self.get(device_id)
        if device:
            await self.session.delete(device)
            await self.session.commit()
            _known_device_cache.pop(device_id, None)

    async def upsert_from_telemetry(self, device_id: str) -> None:
        """Ensure a device row exists even if it hasn't been explicitly registered.
        Cache-checked first so steady-state ingestion for known devices skips the DB
        round trip entirely (Phase 12 perf: cached queries on the hot ingest path)."""
        if _known_device_cache.get(device_id):
            return

        existing = await self.get(device_id)
        if existing is None:
            device = Device(
                device_id=device_id,
                name=device_id,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(device)
            await self.session.commit()

        _known_device_cache[device_id] = True


class TelemetryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(self, telemetry: Telemetry) -> None:
        self.session.add(telemetry)
        await self.session.commit()

    async def query(
        self,
        device_id: str,
        metric: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[Telemetry]:
        stmt = select(Telemetry).where(Telemetry.device_id == device_id)
        if metric:
            stmt = stmt.where(Telemetry.metric == metric)
        if start:
            stmt = stmt.where(Telemetry.time >= start)
        if end:
            stmt = stmt.where(Telemetry.time <= end)
        stmt = stmt.order_by(Telemetry.time.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
