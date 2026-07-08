# IoT Time-Series Platform

A complete Docker-based IoT backend stack for MQTT ingestion, TimescaleDB
storage, alarm evaluation, and observability.

This repository has been updated to reflect the latest working configuration
and code fixes for async database integration and test compatibility.

## Latest changes made

- `app/database/session.py`
  - switched the async SQLAlchemy engine to `poolclass=NullPool`
  - fixed `asyncpg` event-loop reuse failures during ASGI test execution
- `pytest.ini`
  - removed invalid `anyio_backend`
  - kept `asyncio_default_fixture_loop_scope = session`
- `docker-compose.yml`
  - removed the obsolete top-level `version` key
- Timestamp handling was updated to timezone-aware UTC in:
  - `app/api/auth.py`
  - `app/api/alarms.py`
  - `app/api/devices.py`
  - `app/repositories/*`
  - `app/workers/mqtt_worker.py`
- Verified test success: `docker compose run --rm -v "<repo>:/srv" api pytest -q` → `22 passed`

## What this project contains

- Mosquitto MQTT broker with password+ACL authentication
- FastAPI REST API with JWT auth, RBAC, and API keys
- Async SQLAlchemy + `asyncpg` talking to TimescaleDB
- MQTT ingestion worker
- Alarm evaluation worker
- Prometheus, Grafana, Loki, and Promtail for observability
- Nginx TLS termination
- Integration tests for auth, devices, and alarms

## Quickstart

Create the environment file:

```bash
cp .env.example .env
```

Edit `.env` with your credentials and run:

```bash
docker compose up -d --build
```

If you have `make`:

```bash
make up
```

### Service URLs

| Service | URL |
|---|---|
| API docs | http://localhost:8000/docs |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Loki | http://localhost:3100 |
| pgAdmin | http://localhost:5050 |
| MQTT broker | localhost:1883 |

## Environment values

Use these working values in `.env`:

```dotenv
POSTGRES_USER=iot_admin
POSTGRES_PASSWORD=change_me_strong_password
POSTGRES_DB=iot_platform
POSTGRES_HOST=timescaledb
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://iot_admin:change_me_strong_password@timescaledb:5432/iot_platform

MQTT_BROKER_HOST=mosquitto
MQTT_BROKER_PORT=1883
MQTT_USERNAME=iot_service
MQTT_PASSWORD=change_me_mqtt_password
MQTT_CLIENT_ID=iot-worker
MQTT_TELEMETRY_TOPIC=phy/+/telemetry
MQTT_STATUS_TOPIC=phy/+/status
MQTT_KEEPALIVE=60
MQTT_RECONNECT_MIN_DELAY=1
MQTT_RECONNECT_MAX_DELAY=30

API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=change_me_jwt_secret
API_ACCESS_TOKEN_EXPIRE_MINUTES=60
ENVIRONMENT=development
LOG_LEVEL=INFO

PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=change_me_pgadmin_password

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change_me_grafana_password

RATE_LIMIT_PER_MINUTE=120
DEVICE_OFFLINE_CHECK_INTERVAL_SECONDS=30
```

## Authentication

A seeded admin user is created on first DB initialization:

```text
username: admin
password: ChangeMe123!
```

Log in:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe123!"}'
```

Use the returned token for protected calls:

```bash
curl http://localhost:8000/api/v1/devices \
  -H "Authorization: Bearer <token>"
```

API keys are supported via `X-API-Key`.

## End-to-end example

Start a device simulator:

```bash
pip install paho-mqtt
python scripts/simulate_device.py --device-id esp32-hvac-001 --interval 2
```

Then use a JWT token to query the API:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe123!"}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/devices | jq
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/devices/esp32-hvac-001/telemetry?metric=temperature&limit=10" | jq
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/stats/fleet | jq
```

Create an alarm rule:

```bash
curl -X POST http://localhost:8000/api/v1/alarms/rules \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "high-temperature",
    "rule_type": "threshold_gt",
    "metric": "temperature",
    "threshold": 25,
    "severity": "critical",
    "device_id": "esp32-hvac-001",
    "notify_channels": ["mqtt"]
  }'
```

Then watch `GET /api/v1/alarms` or the MQTT topic `alarms/esp32-hvac-001`.

## Tests

Run the full suite from the API container:

```bash
docker compose run --rm -v "$(pwd):/srv" api pytest -q
```

## Updated files

- `docker-compose.yml`
- `pytest.ini`
- `app/database/session.py`
- `app/api/auth.py`
- `app/api/alarms.py`
- `app/api/devices.py`
- `app/repositories/device_repository.py`
- `app/repositories/alarm_repository.py`
- `app/repositories/user_repository.py`
- `app/workers/mqtt_worker.py`
- `README.md`

## Notes

- `scripts/setup_mqtt_auth.sh` generates Mosquitto credentials from `.env`.
- Schema is managed in `sql/init.sql`, not from ORM metadata.
- Keep secrets like `API_SECRET_KEY` and database credentials private.
