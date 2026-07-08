#!/usr/bin/env bash
# Generates mosquitto/config/passwd from the MQTT_USERNAME/MQTT_PASSWORD in
# .env, using the mosquitto_passwd tool inside a throwaway container (so you
# don't need mosquitto installed on the host). Run this once before `make up`
# whenever you change MQTT credentials.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "No .env found — copy .env.example to .env and set MQTT_USERNAME/MQTT_PASSWORD first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .env

: "${MQTT_USERNAME:?MQTT_USERNAME not set in .env}"
: "${MQTT_PASSWORD:?MQTT_PASSWORD not set in .env}"

mkdir -p mosquitto/config
rm -f mosquitto/config/passwd
touch mosquitto/config/passwd

docker run --rm -v "$(pwd)/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/config/passwd "$MQTT_USERNAME" "$MQTT_PASSWORD"

echo "Wrote mosquitto/config/passwd for user '$MQTT_USERNAME'."
echo "Remember: the alarm-worker and mqtt-worker containers reuse the same"
echo "MQTT_USERNAME/MQTT_PASSWORD from .env — see acl.conf if you split them"
echo "into separate service accounts later."
