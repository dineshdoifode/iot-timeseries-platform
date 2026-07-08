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
async def admin_headers(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_alarm_rule_crud_lifecycle(client: AsyncClient, admin_headers: dict):
    create_resp = await client.post(
        "/api/v1/alarms/rules",
        json={
            "name": "high-temp-test-rule",
            "rule_type": "threshold_gt",
            "metric": "temperature",
            "threshold": 40.0,
            "severity": "critical",
            "notify_channels": ["mqtt"],
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    rule_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/alarms/rules", headers=admin_headers)
    assert list_resp.status_code == 200
    assert any(r["id"] == rule_id for r in list_resp.json())

    patch_resp = await client.patch(
        f"/api/v1/alarms/rules/{rule_id}", json={"threshold": 45.0}, headers=admin_headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["threshold"] == 45.0

    delete_resp = await client.delete(f"/api/v1/alarms/rules/{rule_id}", headers=admin_headers)
    assert delete_resp.status_code == 204


async def test_alarm_rules_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/alarms/rules")
    assert resp.status_code == 401


async def test_fleet_stats_returns_expected_shape(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/stats/fleet", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "total_devices", "active_devices", "online_devices",
        "offline_or_unknown_devices", "active_alarms", "telemetry_points_last_hour",
    ):
        assert key in body
