"""
Integration tests against a running API + DB (run inside the api container,
or point DATABASE_URL at a local TimescaleDB instance).

    make test

Requires the seeded default admin user from sql/init.sql (username "admin",
password "ChangeMe123!") to exist in the database.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio

ADMIN_CREDENTIALS = {"username": "admin", "password": "ChangeMe123!"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_headers(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert resp.status_code == 200, f"admin login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")


async def test_device_endpoints_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/devices")
    assert resp.status_code == 401


async def test_device_crud_lifecycle(client: AsyncClient, auth_headers: dict):
    device_id = "test-device-001"

    # cleanup from a previous failed run, if any
    await client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers)

    create_resp = await client.post(
        "/api/v1/devices",
        json={"device_id": device_id, "name": "Test Sensor", "device_type": "sensor"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["device_id"] == device_id

    get_resp = await client.get(f"/api/v1/devices/{device_id}", headers=auth_headers)
    assert get_resp.status_code == 200

    patch_resp = await client.patch(
        f"/api/v1/devices/{device_id}", json={"name": "Updated Name"}, headers=auth_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Updated Name"

    list_resp = await client.get("/api/v1/devices", headers=auth_headers)
    assert list_resp.status_code == 200
    assert any(d["device_id"] == device_id for d in list_resp.json())

    delete_resp = await client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers)
    assert delete_resp.status_code == 204

    missing_resp = await client.get(f"/api/v1/devices/{device_id}", headers=auth_headers)
    assert missing_resp.status_code == 404
