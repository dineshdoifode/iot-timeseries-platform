.PHONY: up down build logs ps restart clean test simulate psql certs mqtt-auth init

up: certs mqtt-auth
	docker compose up -d --build

init: certs mqtt-auth
	@echo "TLS cert and MQTT credentials are ready. Run 'make up' to start the stack."

certs:
	@if [ ! -f nginx/certs/server.crt ]; then \
		bash scripts/generate_tls_cert.sh; \
	else \
		echo "nginx/certs/server.crt already exists, skipping."; \
	fi

mqtt-auth:
	@bash scripts/setup_mqtt_auth.sh

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

restart:
	docker compose restart api mqtt-worker alarm-worker

clean:
	docker compose down -v

test:
	docker compose exec api pytest -v

simulate:
	python scripts/simulate_device.py

psql:
	docker compose exec timescaledb psql -U iot_admin -d iot_platform
