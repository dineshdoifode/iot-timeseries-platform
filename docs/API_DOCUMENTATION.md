# API Documentation — IoT Time-Series Platform

Base URL (local): `http://localhost:8000` (or `https://localhost/api/` via the
Nginx TLS front door — see the main [README](../README.md) for the two
options).

Interactive Swagger UI is always available at `/docs` and a raw OpenAPI 3.0
schema at `/openapi.json` — this document exists as a readable companion,
not a replacement; when in doubt, `/docs` is the source of truth for exact
request/response shapes.

## Table of contents

- [Authentication](#authentication)
- [Roles & permissions](#roles--permissions)
- [Rate limiting](#rate-limiting)
- [Error format](#error-format)
- [Health & metrics](#health--metrics)
- [Auth endpoints](#auth-endpoints)
- [Device endpoints](#device-endpoints)
- [Alarm endpoints](#alarm-endpoints)
- [Stats endpoints](#stats-endpoints)

---

## Authentication

Every endpoint under `/api/v1/` (except `/api/v1/auth/login`) requires one of:

| Method | Header | Who uses it |
|---|---|---|
| JWT bearer token | `Authorization: Bearer <token>` | Human users, dashboards |
| API key | `X-API-Key: <key>` | Services, CI, provisioning scripts |

Both resolve to the same internal `Principal(subject, role)` — route handlers
don't care which one was used, only what role it carries.

**Get a token:**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "ChangeMe123!"}'
```

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in_minutes": 60
}
```

Tokens expire after `API_ACCESS_TOKEN_EXPIRE_MINUTES` (default 60, set in
`.env`). There is no refresh-token flow yet — log in again once it expires.

**Get an API key** (admin only, see [Auth endpoints](#auth-endpoints)):

```bash
curl http://localhost:8000/api/v1/devices -H "X-API-Key: iotk_xxxxxxxx"
```

The raw key is only ever shown once, at creation time. The database stores a
hash, never the raw value — if you lose it, revoke it and issue a new one.

---

## Roles & permissions

Roles are hierarchical: `admin` > `operator` > `viewer`. An endpoint that
requires `operator` also accepts `admin`.

| Role | Can do |
|---|---|
| `viewer` | Read devices, telemetry, alarms, alarm rules, stats |
| `operator` | Everything viewer can, plus: create/update devices, create/update/delete alarm rules, resolve alarms, publish MQTT commands to devices |
| `admin` | Everything operator can, plus: delete devices, register new users, issue/revoke API keys |

Every endpoint's required role is noted in the sections below.

---

## Rate limiting

Default limit: `120 requests/minute` per client IP (`RATE_LIMIT_PER_MINUTE`
in `.env`). Exceeding it returns:

```json
{ "detail": "Rate limit exceeded: 120 per 1 minute" }
```
`HTTP 429 Too Many Requests`

The limiter is currently per-process (in-memory) — see the README's
roadmap section for the Redis-backed distributed version.

---

## Error format

Standard FastAPI/Pydantic error shape:

```json
{ "detail": "Device not found" }
```

Validation errors (HTTP 422) return FastAPI's default structured shape with
a `loc`/`msg`/`type` breakdown per invalid field.

| Status | Meaning |
|---|---|
| 400 | Bad request (e.g. malformed input the schema didn't catch) |
| 401 | Missing/invalid/expired credentials |
| 403 | Authenticated, but role doesn't allow this action |
| 404 | Resource doesn't exist |
| 409 | Conflict (e.g. device_id already registered) |
| 422 | Request body failed schema validation |
| 429 | Rate limit exceeded |
| 503 | A downstream dependency (e.g. MQTT broker) is unavailable |

---

## Health & metrics

### `GET /health`
No auth required. Checks the database connection.

```json
{ "status": "ok", "database": "ok" }
```

### `GET /metrics`
No auth required. Prometheus exposition format — scraped by the bundled
Prometheus service, not meant for humans.

---

## Auth endpoints

### `POST /api/v1/auth/login`
No auth required (this is how you get one).

**Body:**
```json
{ "username": "admin", "password": "ChangeMe123!" }
```
**Response `200`:**
```json
{ "access_token": "...", "token_type": "bearer", "expires_in_minutes": 60 }
```
**`401`** on bad credentials.

### `GET /api/v1/auth/me`
Requires: any authenticated principal.

Returns the current user's `username`, `email`, and `role`.

### `POST /api/v1/auth/register`
Requires: `admin`.

**Body:**
```json
{
  "username": "jane",
  "email": "jane@example.com",
  "password": "SomeStrongPass1!",
  "role": "operator"
}
```
**Response `201`:** the created user (no password field). **`409`** if the
username/email is already taken.

### `POST /api/v1/auth/api-keys`
Requires: `admin`.

**Body:**
```json
{ "name": "ci-pipeline", "role": "viewer", "expires_in_days": 90 }
```
**Response `201`:**
```json
{ "id": 3, "api_key": "iotk_...", "name": "ci-pipeline", "role": "viewer", "expires_at": "2026-10-08T00:00:00Z" }
```
`api_key` is shown exactly once — store it immediately.

### `DELETE /api/v1/auth/api-keys/{key_id}`
Requires: `admin`. Revokes (soft-deletes) the key. `204` on success.

---

## Device endpoints

### `POST /api/v1/devices`
Requires: `operator`+.

**Body:**
```json
{
  "device_id": "esp32-hvac-001",
  "name": "Rooftop HVAC Sensor",
  "device_type": "sensor",
  "firmware_version": "1.2.0",
  "tags": {"building": "A", "floor": "3"},
  "metadata": {},
  "device_group": "hvac"
}
```
**Response `201`:** the created device. **`409`** if `device_id` already exists.

Note: devices are also auto-registered the moment they publish their first
telemetry, even without a prior `POST` here — see the README's design notes.

### `GET /api/v1/devices`
Requires: `viewer`+.

**Query params:** `group` (optional), `limit` (default 100, max 1000), `offset` (default 0)

Returns a list of devices, most recently created first.

### `GET /api/v1/devices/{device_id}`
Requires: `viewer`+. `404` if not found.

### `PATCH /api/v1/devices/{device_id}`
Requires: `operator`+. Partial update — send only the fields you're changing.

```json
{ "name": "Renamed Sensor", "is_active": false }
```

### `DELETE /api/v1/devices/{device_id}`
Requires: `admin`. `204` on success, `404` if not found.

### `GET /api/v1/devices/{device_id}/telemetry`
Requires: `viewer`+.

**Query params:** `metric` (optional, e.g. `temperature`), `start`/`end`
(ISO 8601 datetimes, optional), `limit` (default 100, max 5000)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/devices/esp32-hvac-001/telemetry?metric=temperature&limit=10"
```

Returns telemetry rows newest-first: `time`, `device_id`, `metric`, `value`,
`unit`, `quality`.

### `POST /api/v1/devices/{device_id}/commands`
Requires: `operator`+. Publishes an arbitrary JSON command to
`phy/{device_id}/commands` over MQTT — the one endpoint that reaches out and
can change physical device state.

**Body:**
```json
{ "payload": {"action": "reboot"}, "qos": 1, "retain": false }
```
**Response `202`:**
```json
{ "status": "published", "topic": "phy/esp32-hvac-001/commands" }
```
**`503`** if the MQTT broker is unreachable.

---

## Alarm endpoints

### `POST /api/v1/alarms/rules`
Requires: `operator`+.

**Body:**
```json
{
  "name": "high-temperature",
  "rule_type": "threshold_gt",
  "metric": "temperature",
  "threshold": 30,
  "severity": "critical",
  "device_id": "esp32-hvac-001",
  "notify_channels": ["mqtt", "slack"]
}
```

`rule_type` is one of: `threshold_gt`, `threshold_lt`, `device_offline`,
`battery_low`, `sensor_timeout`. Set exactly one of `device_id` (single
device) or `device_group` (all devices in that group) — leave both null to
apply fleet-wide. `notify_channels` is any subset of `mqtt`, `webhook`,
`slack`, `email` (the latter three need their config set in `.env`).

### `GET /api/v1/alarms/rules`
Requires: `viewer`+. Query param: `enabled_only` (bool, default false).

### `GET /api/v1/alarms/rules/{rule_id}`
Requires: `viewer`+.

### `PATCH /api/v1/alarms/rules/{rule_id}`
Requires: `operator`+. Partial update, same shape as create.

### `DELETE /api/v1/alarms/rules/{rule_id}`
Requires: `operator`+. `204` on success.

### `GET /api/v1/alarms`
Requires: `viewer`+.

**Query params:** `device_id` (optional), `active_only` (bool, default
false), `limit` (default 100, max 1000)

Returns fired alarm instances, newest-first: `id`, `device_id`, `rule_name`,
`severity`, `message`, `triggered_at`, `resolved_at`, `is_active`.

### `POST /api/v1/alarms/{alarm_id}/resolve`
Requires: `operator`+. Manually marks an alarm resolved (e.g. investigated
and confirmed a false positive). Note: if the underlying condition is still
true, the alarm worker will re-fire it on its next evaluation cycle — this
isn't a mute/suppress action.

---

## Stats endpoints

### `GET /api/v1/stats/fleet`
Requires: `viewer`+.

```json
{
  "total_devices": 42,
  "active_devices": 40,
  "online_devices": 37,
  "offline_or_unknown_devices": 3,
  "active_alarms": 2,
  "telemetry_points_last_hour": 15230
}
```

"Online" means the device's most recent status row says `online` and was
seen within the last 5 minutes.

### `GET /api/v1/stats/devices/{device_id}`
Requires: `viewer`+.

```json
{
  "device_id": "esp32-hvac-001",
  "metrics": [
    {
      "metric": "temperature",
      "sample_count": 4820,
      "avg_value": 23.451,
      "min_value": 18.2,
      "max_value": 31.7,
      "last_seen": "2026-07-09T10:14:02Z"
    }
  ],
  "active_alarms": 1
}
```
