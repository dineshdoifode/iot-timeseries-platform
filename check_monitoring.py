import urllib.request
import json


def get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    return urllib.request.urlopen(req, timeout=10).read().decode()


login_data = json.dumps({"username": "admin", "password": "ChangeMe123!"}).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8000/api/v1/auth/login",
    data=login_data,
    headers={"Content-Type": "application/json"},
)
login = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
token = login.get("access_token", "")
print("TOKEN", token)
print("FLEET")
print(get("http://localhost:8000/api/v1/stats/fleet", headers={"Authorization": f"Bearer {token}"}))
print("API_METRICS")
print("\n".join([
    l
    for l in get("http://localhost:8000/metrics").splitlines()
    if l.startswith((
        "mqtt_messages_total",
        "mqtt_processing_errors_total",
        "mqtt_connected",
        "db_insert_latency_seconds",
        "connected_devices",
    ))
]))
print("MQTT_METRICS")
print("\n".join([
    l
    for l in get("http://localhost:9100/metrics").splitlines()
    if l.startswith((
        "mqtt_messages_total",
        "mqtt_processing_errors_total",
        "mqtt_connected",
        "mqtt_reconnects_total",
        "db_insert_latency_seconds",
    ))
]))
print("ALARM_METRICS")
print("\n".join([
    l
    for l in get("http://localhost:9101/metrics").splitlines()
    if l.startswith(("alarms_fired_total", "alarms_resolved_total"))
]))
print("PROM_TARGETS")
response = get("http://localhost:9090/api/v1/targets")
data = json.loads(response)
for target in data["data"]["activeTargets"]:
    print(json.dumps(target["labels"]))
