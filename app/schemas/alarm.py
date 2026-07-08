from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

RULE_TYPES = ("threshold_gt", "threshold_lt", "device_offline", "battery_low", "sensor_timeout")
SEVERITIES = ("info", "warning", "critical")
CHANNELS = ("mqtt", "webhook", "slack", "email")


class AlarmRuleCreate(BaseModel):
    name: str
    rule_type: str = Field(..., pattern="^(" + "|".join(RULE_TYPES) + ")$")
    metric: str | None = None
    threshold: float | None = None
    timeout_seconds: int | None = None
    device_group: str | None = None
    device_id: str | None = None
    severity: str = Field(default="warning", pattern="^(" + "|".join(SEVERITIES) + ")$")
    is_enabled: bool = True
    notify_channels: list[str] = Field(default_factory=lambda: ["mqtt"])


class AlarmRuleUpdate(BaseModel):
    name: str | None = None
    metric: str | None = None
    threshold: float | None = None
    timeout_seconds: int | None = None
    device_group: str | None = None
    device_id: str | None = None
    severity: str | None = None
    is_enabled: bool | None = None
    notify_channels: list[str] | None = None


class AlarmRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: str
    metric: str | None
    threshold: float | None
    timeout_seconds: int | None
    device_group: str | None
    device_id: str | None
    severity: str
    is_enabled: bool
    notify_channels: list[str]
    created_at: datetime
    updated_at: datetime


class AlarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    rule_id: int | None
    rule_name: str
    severity: str
    message: str
    triggered_at: datetime
    resolved_at: datetime | None
    is_active: bool
