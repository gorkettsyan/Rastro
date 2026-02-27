import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_status_not_connected(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/integrations/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["google"]["connected"] is False


@pytest.mark.asyncio
async def test_sync_returns_queued_count(client: AsyncClient, auth_headers):
    with patch("app.api.integrations.enqueue_all_drive_files", new_callable=AsyncMock, return_value=5), \
         patch("app.api.integrations.enqueue_all_gmail_threads", new_callable=AsyncMock, return_value=3):
        resp = await client.post("/api/v1/integrations/google/sync", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["queued"] == 8


@pytest.mark.asyncio
async def test_integrations_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/integrations/status")
    assert resp.status_code == 403
