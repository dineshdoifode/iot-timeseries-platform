"""
Alarm rule engine.

Each rule type has a small, testable evaluation function that answers:
"is this device currently in violation of this rule?" The worker calls
`evaluate_rule_for_device` on a schedule; this module has no knowledge of
scheduling, notification transport, or the worker loop, so it's cheap to
unit test in isolation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models.models import AlarmRule


@dataclass
class EvaluationResult:
    triggered: bool
    message: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def evaluate_threshold_gt(rule: AlarmRule, value: float | None) -> EvaluationResult:
    if value is None or rule.threshold is None:
        return EvaluationResult(triggered=False)
    if value > rule.threshold:
        return EvaluationResult(
            triggered=True,
            message=f"{rule.metric} = {value} exceeds threshold {rule.threshold}",
        )
    return EvaluationResult(triggered=False)


def evaluate_threshold_lt(rule: AlarmRule, value: float | None) -> EvaluationResult:
    if value is None or rule.threshold is None:
        return EvaluationResult(triggered=False)
    if value < rule.threshold:
        return EvaluationResult(
            triggered=True,
            message=f"{rule.metric} = {value} below threshold {rule.threshold}",
        )
    return EvaluationResult(triggered=False)


def evaluate_battery_low(rule: AlarmRule, value: float | None) -> EvaluationResult:
    # Same shape as threshold_lt, kept distinct for clearer rule naming/UX
    # and so battery-specific logic (e.g. hysteresis) can diverge later.
    return evaluate_threshold_lt(rule, value)


def evaluate_device_offline(rule: AlarmRule, last_status: str | None, last_seen: datetime | None) -> EvaluationResult:
    if last_seen is None:
        return EvaluationResult(triggered=True, message="Device has never reported status")
    timeout = timedelta(seconds=rule.timeout_seconds or 300)
    if last_status == "offline" or _now() - last_seen > timeout:
        return EvaluationResult(
            triggered=True,
            message=f"Device offline or last seen {(_now() - last_seen).seconds}s ago (timeout {timeout.seconds}s)",
        )
    return EvaluationResult(triggered=False)


def evaluate_sensor_timeout(rule: AlarmRule, last_telemetry_time: datetime | None) -> EvaluationResult:
    if last_telemetry_time is None:
        return EvaluationResult(triggered=True, message=f"No telemetry ever received for metric '{rule.metric}'")
    timeout = timedelta(seconds=rule.timeout_seconds or 300)
    age = _now() - last_telemetry_time
    if age > timeout:
        return EvaluationResult(
            triggered=True,
            message=f"No '{rule.metric}' reading in {age.seconds}s (timeout {timeout.seconds}s)",
        )
    return EvaluationResult(triggered=False)
