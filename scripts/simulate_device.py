"""
Publishes fake sensor telemetry + status to MQTT so you can see the
whole pipeline (broker -> worker -> TimescaleDB -> API) work end to end.

Usage:
    pip install paho-mqtt
    python scripts/simulate_device.py --device-id esp32-hvac-001 --interval 2
"""

import argparse
import json
import random
import time

import paho.mqtt.client as mqtt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="esp32-hvac-001")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=0, help="0 = run forever")
    args = parser.parse_args()

    client = mqtt.Client(client_id=f"simulator-{args.device_id}")
    if args.username is not None or args.password is not None:
        client.username_pw_set(args.username, args.password)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    status_topic = f"phy/{args.device_id}/status"
    telemetry_topic = f"phy/{args.device_id}/telemetry"

    client.publish(status_topic, json.dumps({"status": "online"}), qos=1, retain=True)

    i = 0
    try:
        while args.count == 0 or i < args.count:
            payload = {
                "metrics": {
                    "temperature": round(20 + random.uniform(-2, 8), 2),
                    "humidity": round(40 + random.uniform(-5, 15), 2),
                    "voltage": round(3.3 + random.uniform(-0.1, 0.1), 3),
                },
                "unit": {"temperature": "C", "humidity": "%", "voltage": "V"},
                "quality": 1,
            }
            client.publish(telemetry_topic, json.dumps(payload), qos=1)
            print(f"Published to {telemetry_topic}: {payload}")
            time.sleep(args.interval)
            i += 1
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(status_topic, json.dumps({"status": "offline"}), qos=1, retain=True)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
