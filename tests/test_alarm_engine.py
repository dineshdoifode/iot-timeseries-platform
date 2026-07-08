from datetime import datetime, timedelta, timezone

from app.models.models import AlarmRule
from app.services import alarm_engine


def make_rule(**overrides) -> AlarmRule:
    defaults = dict(
        id=1, name="test-rule", rule_type="threshold_gt", severity="warning",
        notify_channels=["mqtt"], is_enabled=True,
    )
    defaults.update(overrides)
    return AlarmRule(**defaults)


def test_threshold_gt_triggers_above_threshold():
    rule = make_rule(rule_type="threshold_gt", metric="temperature", threshold=30.0)
    result = alarm_engine.evaluate_threshold_gt(rule, 35.0)
    assert result.triggered is True
    assert "35.0" in result.message


def test_threshold_gt_does_not_trigger_below_threshold():
    rule = make_rule(rule_type="threshold_gt", metric="temperature", threshold=30.0)
    result = alarm_engine.evaluate_threshold_gt(rule, 20.0)
    assert result.triggered is False


def test_threshold_gt_handles_missing_value():
    rule = make_rule(rule_type="threshold_gt", metric="temperature", threshold=30.0)
    result = alarm_engine.evaluate_threshold_gt(rule, None)
    assert result.triggered is False


def test_threshold_lt_triggers_below_threshold():
    rule = make_rule(rule_type="threshold_lt", metric="voltage", threshold=3.0)
    result = alarm_engine.evaluate_threshold_lt(rule, 2.5)
    assert result.triggered is True


def test_battery_low_reuses_threshold_lt_semantics():
    rule = make_rule(rule_type="battery_low", metric="battery", threshold=20.0)
    triggered = alarm_engine.evaluate_battery_low(rule, 15.0)
    not_triggered = alarm_engine.evaluate_battery_low(rule, 80.0)
    assert triggered.triggered is True
    assert not_triggered.triggered is False


def test_device_offline_triggers_when_never_seen():
    rule = make_rule(rule_type="device_offline", timeout_seconds=300)
    result = alarm_engine.evaluate_device_offline(rule, None, None)
    assert result.triggered is True


def test_device_offline_triggers_when_status_is_offline():
    rule = make_rule(rule_type="device_offline", timeout_seconds=300)
    recent = datetime.now(timezone.utc) - timedelta(seconds=5)
    result = alarm_engine.evaluate_device_offline(rule, "offline", recent)
    assert result.triggered is True


def test_device_offline_triggers_when_stale_beyond_timeout():
    rule = make_rule(rule_type="device_offline", timeout_seconds=60)
    stale = datetime.now(timezone.utc) - timedelta(seconds=120)
    result = alarm_engine.evaluate_device_offline(rule, "online", stale)
    assert result.triggered is True


def test_device_offline_does_not_trigger_when_recently_online():
    rule = make_rule(rule_type="device_offline", timeout_seconds=300)
    recent = datetime.now(timezone.utc) - timedelta(seconds=10)
    result = alarm_engine.evaluate_device_offline(rule, "online", recent)
    assert result.triggered is False


def test_sensor_timeout_triggers_when_stale():
    rule = make_rule(rule_type="sensor_timeout", metric="temperature", timeout_seconds=60)
    stale = datetime.now(timezone.utc) - timedelta(seconds=200)
    result = alarm_engine.evaluate_sensor_timeout(rule, stale)
    assert result.triggered is True


def test_sensor_timeout_does_not_trigger_when_fresh():
    rule = make_rule(rule_type="sensor_timeout", metric="temperature", timeout_seconds=300)
    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
    result = alarm_engine.evaluate_sensor_timeout(rule, fresh)
    assert result.triggered is False
