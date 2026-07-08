#!/usr/bin/env bash
# Generates a self-signed cert for local/demo TLS termination at Nginx.
# For a real deployment, replace nginx/certs/server.{crt,key} with a
# cert from a real CA (e.g. Let's Encrypt via certbot) instead of running this.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p nginx/certs

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/server.key \
  -out nginx/certs/server.crt \
  -subj "/C=IN/ST=Maharashtra/L=Pune/O=IoT Platform Dev/CN=localhost"

chmod 600 nginx/certs/server.key
echo "Self-signed cert written to nginx/certs/. Browsers will warn about it —"
echo "that's expected for local/demo use; swap in a real CA cert for production."
