from prometheus_client import Counter, Gauge, Histogram

# MQTT
MQTT_MESSAGES_TOTAL = Counter(
    "mqtt_messages_total", "Total MQTT messages received", ["topic_type"]
)
MQTT_PROCESSING_ERRORS_TOTAL = Counter(
    "mqtt_processing_errors_total", "MQTT messages that failed processing", ["topic_type"]
)
MQTT_RECONNECTS_TOTAL = Counter(
    "mqtt_reconnects_total", "Number of times the MQTT worker reconnected to the broker"
)
MQTT_CONNECTED = Gauge(
    "mqtt_connected", "1 if the MQTT worker is currently connected to the broker, else 0"
)
DB_INSERT_LATENCY_SECONDS = Histogram(
    "db_insert_latency_seconds", "Latency of DB insert operations", ["table"]
)

# API
API_REQUEST_LATENCY_SECONDS = Histogram(
    "api_request_latency_seconds", "API request latency", ["method", "path"]
)
CONNECTED_DEVICES = Gauge(
    "connected_devices", "Number of devices currently marked online"
)
