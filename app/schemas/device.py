from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    device_id: str = Field(..., examples=["esp32-hvac-001"])
    name: str
    device_type: str | None = None
    firmware_version: str | None = None
    tags: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
    device_group: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    device_type: str | None = None
    firmware_version: str | None = None
    tags: dict | None = None
    metadata: dict | None = None
    device_group: str | None = None
    is_active: bool | None = None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    name: str
    device_type: str | None
    firmware_version: str | None
    tags: dict
    device_group: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TelemetryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: datetime
    device_id: str
    metric: str
    value: float | None
    unit: str | None
    quality: int


class TelemetryQuery(BaseModel):
    metric: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=100, le=5000)
