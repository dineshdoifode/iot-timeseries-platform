from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import Principal, require_role
from app.database.session import get_db
from app.mqtt.publisher import mqtt_publisher
from app.repositories.device_repository import DeviceRepository

router = APIRouter(prefix="/api/v1/devices", tags=["commands"])


class PublishCommand(BaseModel):
    payload: dict = Field(..., description="Arbitrary JSON command body, published as-is")
    qos: int = Field(default=1, ge=0, le=2)
    retain: bool = False


@router.post("/{device_id}/commands", status_code=202)
async def publish_command(
    device_id: str,
    command: PublishCommand,
    db: AsyncSession = Depends(get_db),
    _principal: Principal = Depends(require_role("operator")),
):
    """Publishes to `phy/{device_id}/commands` so the device (or a gateway
    subscribed to that topic) can act on it. Requires operator role — this
    is the one endpoint that reaches out and changes physical device state."""
    repo = DeviceRepository(db)
    if not await repo.get(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    import json

    topic = f"phy/{device_id}/commands"
    try:
        await mqtt_publisher.publish(topic, json.dumps(command.payload), qos=command.qos, retain=command.retain)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"MQTT broker unavailable: {exc}") from exc

    return {"status": "published", "topic": topic}
