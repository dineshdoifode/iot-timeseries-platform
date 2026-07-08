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


async def test_login_rejects_bad_password(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert resp.status_code == 401


async def test_login_succeeds_with_seeded_admin(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body


async def test_me_returns_current_user(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


async def test_viewer_cannot_register_users(client: AsyncClient):
    # Register a throwaway viewer, log in as them, confirm they're denied admin actions.
    login = await client.post("/api/v1/auth/login", json=ADMIN_CREDENTIALS)
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    create_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "test-viewer",
            "email": "test-viewer@example.com",
            "password": "SomeStrongPass1!",
            "role": "viewer",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code in (201, 409)  # 409 if re-run against same DB

    viewer_login = await client.post(
        "/api/v1/auth/login",
        json={"username": "test-viewer", "password": "SomeStrongPass1!"},
    )
    assert viewer_login.status_code == 200
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}

    forbidden_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "should-fail",
            "email": "should-fail@example.com",
            "password": "AnotherStrongPass1!",
            "role": "viewer",
        },
        headers=viewer_headers,
    )
    assert forbidden_resp.status_code == 403


async def test_api_key_created_and_usable(client: AsyncClient, admin_headers: dict):
    create_resp = await client.post(
        "/api/v1/auth/api-keys",
        json={"name": "ci-test-key", "role": "viewer"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    raw_key = create_resp.json()["api_key"]

    devices_resp = await client.get("/api/v1/devices", headers={"X-API-Key": raw_key})
    assert devices_resp.status_code == 200

    # cleanup
    key_id = create_resp.json()["id"]
    revoke_resp = await client.delete(f"/api/v1/auth/api-keys/{key_id}", headers=admin_headers)
    assert revoke_resp.status_code == 204
