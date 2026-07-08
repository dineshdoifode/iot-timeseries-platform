-- ============================================================
-- IoT Time-Series Platform — initial schema
-- Runs automatically on first container start (docker-entrypoint-initdb.d)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------
-- devices: registry / metadata (not time-series, plain table)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    device_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    device_type     TEXT,
    firmware_version TEXT,
    tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    device_group    TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_devices_group ON devices (device_group);
CREATE INDEX IF NOT EXISTS idx_devices_type ON devices (device_type);
CREATE INDEX IF NOT EXISTS idx_devices_tags ON devices USING GIN (tags);

-- ----------------------------------------------------------------
-- device_status: online/offline + last-seen history (hypertable)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_status (
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    device_id       TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    status          TEXT NOT NULL CHECK (status IN ('online', 'offline', 'unknown')),
    reason          TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);

SELECT create_hypertable('device_status', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_device_status_device_time ON device_status (device_id, time DESC);

-- ----------------------------------------------------------------
-- telemetry: generic wide sensor readings (hypertable)
-- Numeric measurement + flexible JSON payload for custom fields.
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry (
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    device_id       TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    metric          TEXT NOT NULL,        -- e.g. 'temperature', 'humidity', 'voltage'
    value            DOUBLE PRECISION,
    unit            TEXT,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,  -- raw/custom fields
    quality         SMALLINT NOT NULL DEFAULT 1          -- 1=good, 0=bad/uncertain
);

SELECT create_hypertable('telemetry', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_metric_time ON telemetry (device_id, metric, time DESC);

-- Compression: roll up chunks older than 7 days
ALTER TABLE telemetry SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'device_id, metric'
);
SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention: drop raw telemetry older than 180 days (tune per interview/demo needs)
SELECT add_retention_policy('telemetry', INTERVAL '180 days', if_not_exists => TRUE);

-- Continuous aggregate: 1-minute average per device/metric, for fast dashboard queries
CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_1m
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time) AS bucket,
    device_id,
    metric,
    avg(value)  AS avg_value,
    min(value)  AS min_value,
    max(value)  AS max_value,
    count(*)    AS sample_count
FROM telemetry
GROUP BY bucket, device_id, metric
WITH NO DATA;

SELECT add_continuous_aggregate_policy('telemetry_1m',
    start_offset => INTERVAL '1 hour',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);

-- ----------------------------------------------------------------
-- mqtt_messages: raw ingested message log (audit / replay / DLQ debugging)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mqtt_messages (
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    topic           TEXT NOT NULL,
    device_id       TEXT,
    qos             SMALLINT,
    retained        BOOLEAN NOT NULL DEFAULT false,
    payload_raw     TEXT NOT NULL,
    processed       BOOLEAN NOT NULL DEFAULT false,
    error           TEXT
);

SELECT create_hypertable('mqtt_messages', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_mqtt_messages_topic_time ON mqtt_messages (topic, time DESC);
CREATE INDEX IF NOT EXISTS idx_mqtt_messages_unprocessed ON mqtt_messages (processed) WHERE processed = false;

SELECT add_retention_policy('mqtt_messages', INTERVAL '30 days', if_not_exists => TRUE);

-- ----------------------------------------------------------------
-- alarms: fired alarm instances (Phase 6 hook — table ready now)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alarms (
    id              BIGSERIAL PRIMARY KEY,
    device_id       TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    rule_name       TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'warning' CHECK (severity IN ('info','warning','critical')),
    message         TEXT NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_alarms_device_active ON alarms (device_id, is_active);

-- ----------------------------------------------------------------
-- events: generic device/system event stream
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    time            TIMESTAMPTZ NOT NULL DEFAULT now(),
    device_id       TEXT REFERENCES devices(device_id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    description     TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);

SELECT create_hypertable('events', 'time', if_not_exists => TRUE);

-- ----------------------------------------------------------------
-- users / roles: minimal RBAC scaffold (Phase 11 hook)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id      SERIAL PRIMARY KEY,
    name    TEXT UNIQUE NOT NULL
);

INSERT INTO roles (name) VALUES ('admin'), ('operator'), ('viewer')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role_id         INTEGER NOT NULL REFERENCES roles(id),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------
-- audit_logs
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    entity      TEXT,
    entity_id   TEXT,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- ----------------------------------------------------------------
-- device_logs: firmware/debug log lines pushed by devices (optional)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_logs (
    time        TIMESTAMPTZ NOT NULL DEFAULT now(),
    device_id   TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    level       TEXT NOT NULL DEFAULT 'info',
    message     TEXT NOT NULL
);

SELECT create_hypertable('device_logs', 'time', if_not_exists => TRUE);
SELECT add_retention_policy('device_logs', INTERVAL '30 days', if_not_exists => TRUE);

-- ----------------------------------------------------------------
-- alarm_rules: Phase 6 rule engine configuration
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alarm_rules (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    rule_type       TEXT NOT NULL CHECK (rule_type IN
                        ('threshold_gt', 'threshold_lt', 'device_offline', 'battery_low', 'sensor_timeout')),
    metric          TEXT,                       -- required for threshold_gt/lt/battery_low
    threshold       DOUBLE PRECISION,            -- required for threshold_gt/lt/battery_low
    timeout_seconds INTEGER,                     -- required for device_offline/sensor_timeout
    device_group    TEXT,                        -- NULL = applies to all devices
    device_id       TEXT REFERENCES devices(device_id) ON DELETE CASCADE,  -- NULL = applies to group/all
    severity        TEXT NOT NULL DEFAULT 'warning' CHECK (severity IN ('info','warning','critical')),
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    notify_channels JSONB NOT NULL DEFAULT '["mqtt"]'::jsonb,  -- subset of: mqtt, webhook, slack, email
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alarm_rules_group ON alarm_rules (device_group) WHERE is_enabled = true;
CREATE INDEX IF NOT EXISTS idx_alarm_rules_device ON alarm_rules (device_id) WHERE is_enabled = true;

-- link alarms to the rule that fired them (nullable: manual/legacy alarms allowed)
ALTER TABLE alarms ADD COLUMN IF NOT EXISTS rule_id INTEGER REFERENCES alarm_rules(id) ON DELETE SET NULL;

-- ----------------------------------------------------------------
-- api_keys: service-to-service auth (e.g. device provisioning scripts, CI)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    key_hash        TEXT NOT NULL UNIQUE,   -- sha256 hex digest, never store raw key
    role            TEXT NOT NULL DEFAULT 'viewer' CHECK (role IN ('admin','operator','viewer')),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_used_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ
);

-- seed a default admin user for first login: username "admin", password "ChangeMe123!"
-- bcrypt hash below corresponds to that password — ROTATE THIS IMMEDIATELY IN ANY REAL DEPLOYMENT.
INSERT INTO users (username, email, hashed_password, role_id, is_active)
SELECT 'admin', 'admin@iot-platform.local',
       '$2b$12$PKFKwFX97d8MsX5HpqgJbuHtf73kpNRh1YRbTJnsK5YfuWDnYVdu6',
       (SELECT id FROM roles WHERE name = 'admin'),
       true
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');
