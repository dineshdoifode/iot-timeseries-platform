from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Alarm, AlarmRule, Device, DeviceStatus, Telemetry


class AlarmRuleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, rule: AlarmRule) -> AlarmRule:
        self.session.add(rule)
        await self.session.commit()
        await self.session.refresh(rule)
        return rule

    async def get(self, rule_id: int) -> AlarmRule | None:
        result = await self.session.execute(select(AlarmRule).where(AlarmRule.id == rule_id))
        return result.scalar_one_or_none()

    async def list(self, enabled_only: bool = False) -> list[AlarmRule]:
        stmt = select(AlarmRule)
        if enabled_only:
            stmt = stmt.where(AlarmRule.is_enabled.is_(True))
        result = await self.session.execute(stmt.order_by(AlarmRule.created_at.desc()))
        return list(result.scalars().all())

    async def update(self, rule_id: int, values: dict) -> None:
        values["updated_at"] = datetime.now(timezone.utc)
        await self.session.execute(update(AlarmRule).where(AlarmRule.id == rule_id).values(**values))
        await self.session.commit()

    async def delete(self, rule_id: int) -> None:
        rule = await self.get(rule_id)
        if rule:
            await self.session.delete(rule)
            await self.session.commit()

    async def target_devices(self, rule: AlarmRule) -> list[str]:
        """Resolve which device_ids a rule applies to: specific device > group > all."""
        if rule.device_id:
            return [rule.device_id]

        stmt = select(Device.device_id).where(Device.is_active.is_(True))
        if rule.device_group:
            stmt = stmt.where(Device.device_group == rule.device_group)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]


class AlarmRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active_for_rule(self, device_id: str, rule_id: int) -> Alarm | None:
        """Prevents duplicate alarm spam: only one active alarm per (device, rule)."""
        result = await self.session.execute(
            select(Alarm).where(
                Alarm.device_id == device_id,
                Alarm.rule_id == rule_id,
                Alarm.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, alarm: Alarm) -> Alarm:
        self.session.add(alarm)
        await self.session.commit()
        await self.session.refresh(alarm)
        return alarm

    async def resolve(self, alarm_id: int) -> None:
        await self.session.execute(
            update(Alarm)
            .where(Alarm.id == alarm_id)
            .values(is_active=False, resolved_at=datetime.now(timezone.utc))
        )
        await self.session.commit()

    async def auto_resolve_for_rule(self, device_id: str, rule_id: int) -> None:
        """Called when a rule's condition clears — closes any open alarm for it."""
        active = await self.get_active_for_rule(device_id, rule_id)
        if active:
            await self.resolve(active.id)

    async def list(
        self, device_id: str | None = None, active_only: bool = False, limit: int = 100
    ) -> list[Alarm]:
        stmt = select(Alarm)
        if device_id:
            stmt = stmt.where(Alarm.device_id == device_id)
        if active_only:
            stmt = stmt.where(Alarm.is_active.is_(True))
        stmt = stmt.order_by(Alarm.triggered_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def latest_telemetry_value(self, device_id: str, metric: str) -> Telemetry | None:
        result = await self.session.execute(
            select(Telemetry)
            .where(Telemetry.device_id == device_id, Telemetry.metric == metric)
            .order_by(Telemetry.time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_status(self, device_id: str) -> DeviceStatus | None:
        result = await self.session.execute(
            select(DeviceStatus)
            .where(DeviceStatus.device_id == device_id)
            .order_by(DeviceStatus.time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
