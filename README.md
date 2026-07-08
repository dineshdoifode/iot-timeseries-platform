# IoT Time-Series Platform

A full-stack IoT backend for secure MQTT ingestion, time-series storage, alarm evaluation, and real-time observability.

This project is built as a Docker Compose deployment and demonstrates a complete IoT ingestion pipeline with:
- authenticated MQTT ingestion via Mosquitto
- TimescaleDB time-series storage
- FastAPI REST API with JWT and API key authentication
- asynchronous workers for MQTT ingestion and alarm evaluation
- Prometheus metrics, Grafana dashboards, and Loki logging
- Nginx reverse proxy and TLS-ready routing

## What this project does

This platform receives telemetry and device status from MQTT-connected devices, stores the data in TimescaleDB, and exposes REST endpoints for fleet management, history queries, alarm rules, and statistics.

It solves the following operational needs:
- secure device communication through MQTT authentication and ACLs
- high-volume telemetry persistence in a time-series database
- automatic device registration and status tracking
- rule-based alarm detection and notification
- observability for system health, metrics, logs, and dashboards

## Architecture

The core architecture is:

- `Mosquitto` broker: authenticates MQTT clients and enforces ACLs
- `mqtt-worker`: subscribes to `phy/+/telemetry` and `phy/+/status`, validates payloads, and writes telemetry/status to the database
- `TimescaleDB`: stores time-series telemetry and device history with optimized query support
- `FastAPI` service: exposes protected REST APIs for devices, telemetry, alarms, and fleet stats
- `alarm-worker`: periodically evaluates alarm rules against recent telemetry and generates alerts
- `Prometheus`, `Grafana`, and `Loki`: provide metrics, dashboards, and log analysis
- `Nginx`: handles routing and TLS termination

### High-level flow

1. Devices publish MQTT messages to `phy/{device_id}/telemetry` and `phy/{device_id}/status`
2. `mqtt-worker` consumes messages, writes raw audit rows, and persists processed telemetry/status rows
3. `TimescaleDB` stores device data in specialized time-series tables
4. The API serves device inventory, telemetry history, alarm management, and fleet statistics
5. `alarm-worker` evaluates rules and fires alarms when conditions are met
6. Metrics and logs are scraped and displayed in Grafana and Loki

## Features

- authenticated MQTT ingestion with a shared service account
- raw audit storage of incoming MQTT messages
- flexible telemetry parsing with metric names, units, quality, and raw payload
- device status history and online/offline tracking
- alarm rules for thresholds, device offline, battery low, and timeout conditions
- manual alarm resolve support
- role-based API access for admin, operator, and viewer users
- JWT authentication plus API key issuance/revocation
- fleet-level and per-device statistics endpoints
- Prometheus metrics for worker health, MQTT throughput, alarm counts, and connected devices
- Grafana provisioning for dashboards and data sources
- Loki logging for troubleshooting

## API overview

The REST API is available under `/api/v1`.

### Authentication

- `POST /api/v1/auth/login`
  - Login with username/password
  - Returns a JWT access token
- `POST /api/v1/auth/register`
  - Admin-only endpoint to create new users
- `GET /api/v1/auth/me`
  - Returns the current authenticated user
- `POST /api/v1/auth/api-keys`
  - Admin-only create an API key
- `DELETE /api/v1/auth/api-keys/{key_id}`
  - Admin-only revoke an API key

### Devices

- `POST /api/v1/devices`
  - Register a new device
- `GET /api/v1/devices`
  - List devices
- `GET /api/v1/devices/{device_id}`
  - Get device details
- `PATCH /api/v1/devices/{device_id}`
  - Update a device
- `DELETE /api/v1/devices/{device_id}`
  - Delete a device
- `GET /api/v1/devices/{device_id}/telemetry`
  - Query device telemetry by metric, time range, and limit

### Commands

- `POST /api/v1/devices/{device_id}/commands`
  - Publish a command payload to a device via MQTT

### Alarms

- `POST /api/v1/alarms/rules`
  - Create an alarm rule
- `GET /api/v1/alarms/rules`
  - List alarm rules
- `GET /api/v1/alarms/rules/{rule_id}`
  - Get a single alarm rule
- `PATCH /api/v1/alarms/rules/{rule_id}`
  - Update an alarm rule
- `DELETE /api/v1/alarms/rules/{rule_id}`
  - Delete an alarm rule
- `GET /api/v1/alarms`
  - List alarms (optional `device_id`, `active_only`)
- `POST /api/v1/alarms/{alarm_id}/resolve`
  - Manually resolve an alarm instance

### Stats

- `GET /api/v1/stats/fleet`
  - Fleet overview including device counts, online devices, active alarms, and telemetry rate
- `GET /api/v1/stats/devices/{device_id}`
  - Per-device metric summary and active alarm count

## API docs

Interactive documentation is available at:

- http://localhost:8000/docs
- http://localhost:8000/redoc

## Getting started

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Update `.env` with your credentials and secrets.

3. Start the stack:

```bash
docker compose up -d --build
```

Or use Make:

```bash
make up
```

### Default service URLs

| Service | URL |
|---|---|
| API docs | http://localhost:8000/docs |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Loki | http://localhost:3100 |
| pgAdmin | http://localhost:5050 |
| MQTT broker | localhost:1883 |

## Sample device simulator

```bash
pip install paho-mqtt
python scripts/simulate_device.py --device-id esp32-hvac-001 --username iot_service --password change_me_mqtt_password --count 10
```

## End-to-end example

1. Start the Docker stack.
2. Publish telemetry to `phy/{device_id}/telemetry`.
3. Publish status to `phy/{device_id}/status`.
4. Create alarms or query telemetry via the REST API.

### Example login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"ChangeMe123!"}'
```

### Example telemetry query

```bash
TOKEN=<token>

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/devices | jq
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/devices/esp32-hvac-001/telemetry?metric=temperature&limit=10" | jq
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/stats/fleet | jq
```

## Database schema

Core tables include:
- `devices`
- `telemetry`
- `device_status`
- `mqtt_messages`
- `alarms`
- `alarm_rules`
- `users`
- `api_keys`

## Observability

- Prometheus scrapes the API and worker metrics
- Grafana displays dashboards and panels
- Loki collects container logs for troubleshooting
- Nginx routes traffic and enables TLS as needed

## Testing

Run the test suite from the API container:

```bash
docker compose run --rm -v "$(pwd):/srv" api pytest -q
```

## Notes

- Do not commit `.env`.
- Use strong secrets for `API_SECRET_KEY`, MQTT credentials, and DB passwords.
- The platform is designed as a secure IoT demo/prototype with role-based API access, alarm rules, and time-series ingestion.

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
