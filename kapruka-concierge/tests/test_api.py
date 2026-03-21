"""
Unit tests for api/ — stream, action, image endpoints.
Uses FastAPI TestClient (httpx-based, synchronous).
All external I/O (httpx fetch, orchestrator) is mocked.

Run: pytest tests/test_api.py -v
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fake_process(session_id: str, message: str):
    """Fake orchestrator.process() — yields two events then stops."""
    yield {
        "type":      "dataModelUpdate",
        "surfaceId": "chat_surface",
        "data":      {"message": "Here are some gifts!"},
    }
    yield {
        "type":      "dataModelUpdate",
        "surfaceId": "gallery_surface",
        "data":      {"products": []},
    }


# ============================================================================
# action endpoint
# ============================================================================

class TestActionEndpoint:

    @pytest.fixture()
    def client(self):
        from api.main import app
        return TestClient(app)

    def test_send_message_returns_ok(self, client):
        resp = client.post("/action", json={
            "userAction": {
                "name": "send_message",
                "surfaceId": "chat_surface",
                "sourceComponentId": "input_1",
                "timestamp": "2024-01-01T00:00:00Z",
                "context": {"session_id": "abc123"},
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["session_id"] == "abc123"

    def test_send_message_defaults_session_id(self, client):
        resp = client.post("/action", json={
            "userAction": {
                "name": "send_message",
                "surfaceId": "chat_surface",
                "sourceComponentId": "x",
                "timestamp": "2024-01-01T00:00:00Z",
                "context": {},
            }
        })
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "default"

    def test_change_recipient_returns_recipient(self, client):
        resp = client.post("/action", json={
            "userAction": {
                "name": "change_recipient",
                "surfaceId": "chat_surface",
                "sourceComponentId": "dropdown_1",
                "timestamp": "2024-01-01T00:00:00Z",
                "context": {"recipient": "Mother"},
            }
        })
        assert resp.status_code == 200
        assert resp.json()["recipient"] == "Mother"

    def test_select_product_returns_url(self, client):
        resp = client.post("/action", json={
            "userAction": {
                "name": "select_product",
                "surfaceId": "gallery_surface",
                "sourceComponentId": "card_1",
                "timestamp": "2024-01-01T00:00:00Z",
                "context": {"url": "https://www.kapruka.com/p/123"},
            }
        })
        assert resp.status_code == 200
        assert resp.json()["product_url"] == "https://www.kapruka.com/p/123"

    def test_unknown_action_returns_422(self, client):
        resp = client.post("/action", json={
            "userAction": {
                "name": "fly_to_moon",
                "surfaceId": "chat_surface",
                "sourceComponentId": "x",
                "timestamp": "2024-01-01T00:00:00Z",
                "context": {},
            }
        })
        assert resp.status_code == 422
        assert resp.json()["error"] == "unknown_action"

    def test_missing_body_returns_422(self, client):
        resp = client.post("/action", json={})
        assert resp.status_code == 422  # pydantic validation error


# ============================================================================
# stream endpoint
# ============================================================================

class TestStreamEndpoint:

    @pytest.fixture()
    def client(self):
        from api.main import app
        return TestClient(app)

    def _parse_sse(self, text: str) -> list[dict]:
        """Extract all data: lines from an SSE response body."""
        events = []
        for line in text.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
        return events

    def test_stream_returns_200(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instance = MagicMock()
            instance.process = _fake_process
            MockOrch.return_value = instance

            # Reset session cache so the mock is used
            import api.stream as stream_mod
            stream_mod._sessions.clear()

            resp = client.get("/stream?session_id=t1&message=hello")

        assert resp.status_code == 200

    def test_stream_content_type_is_event_stream(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instance = MagicMock()
            instance.process = _fake_process
            MockOrch.return_value = instance

            import api.stream as stream_mod
            stream_mod._sessions.clear()

            resp = client.get("/stream?session_id=t2&message=hi")

        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_emits_reset_events_first(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instance = MagicMock()
            instance.process = _fake_process
            MockOrch.return_value = instance

            import api.stream as stream_mod
            stream_mod._sessions.clear()

            resp = client.get("/stream?session_id=t3&message=test")

        events = self._parse_sse(resp.text)
        # First events should be resets — all must have type dataModelUpdate
        reset_surfaces = {e["surfaceId"] for e in events[:5]}
        assert "chat_surface" in reset_surfaces
        assert "gallery_surface" in reset_surfaces
        assert "agent_surface" in reset_surfaces

    def test_stream_emits_orchestrator_events(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instance = MagicMock()
            instance.process = _fake_process
            MockOrch.return_value = instance

            import api.stream as stream_mod
            stream_mod._sessions.clear()

            resp = client.get("/stream?session_id=t4&message=gifts")

        events = self._parse_sse(resp.text)
        surface_ids = {e["surfaceId"] for e in events}
        assert "gallery_surface" in surface_ids

        chat_events = [e for e in events if e["surfaceId"] == "chat_surface"
                       and e.get("data", {}).get("message")]
        assert any("gifts" in e["data"]["message"].lower() or
                   "gift" in e["data"]["message"].lower()
                   for e in chat_events)

    def test_stream_ends_with_done_comment(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instance = MagicMock()
            instance.process = _fake_process
            MockOrch.return_value = instance

            import api.stream as stream_mod
            stream_mod._sessions.clear()

            resp = client.get("/stream?session_id=t5&message=x")

        assert ": done" in resp.text

    def test_stream_reuses_orchestrator_for_same_session(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instance = MagicMock()
            instance.process = _fake_process
            MockOrch.return_value = instance

            import api.stream as stream_mod
            stream_mod._sessions.clear()

            client.get("/stream?session_id=reuse&message=first")
            client.get("/stream?session_id=reuse&message=second")

        # Constructor called only once
        assert MockOrch.call_count == 1

    def test_stream_creates_new_orchestrator_per_session(self, client):
        with patch("api.stream.KaprukaConciergeOrchestrator") as MockOrch:
            instances = [MagicMock(), MagicMock()]
            for inst in instances:
                inst.process = _fake_process
            MockOrch.side_effect = instances

            import api.stream as stream_mod
            stream_mod._sessions.clear()

            client.get("/stream?session_id=s_a&message=x")
            client.get("/stream?session_id=s_b&message=y")

        assert MockOrch.call_count == 2


# ============================================================================
# image proxy endpoint
# ============================================================================

class TestImageProxy:

    @pytest.fixture()
    def client(self, tmp_path):
        # Point the image cache at a temp dir for isolation
        import api.image as image_mod
        image_mod._CACHE_DIR = tmp_path
        from api.main import app
        return TestClient(app)

    def test_returns_fallback_for_empty_url(self, client):
        resp = client.get("/api/image?url=")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_returns_fallback_on_fetch_error(self, client, tmp_path):
        import api.image as image_mod
        image_mod._CACHE_DIR = tmp_path

        with patch("api.image.httpx.AsyncClient") as MockClient:
            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(side_effect=Exception("network error"))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_ctx

            resp = client.get("/api/image?url=https://example.com/img.jpg")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"

    def test_proxies_image_and_returns_correct_content_type(self, client, tmp_path):
        import api.image as image_mod
        image_mod._CACHE_DIR = tmp_path

        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 16  # minimal JPEG magic

        with patch("api.image.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-type": "image/jpeg"}
            mock_resp.content = fake_bytes
            mock_resp.raise_for_status = MagicMock()

            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_ctx

            resp = client.get("/api/image?url=https://www.kapruka.com/img.jpg")

        assert resp.status_code == 200
        assert resp.content == fake_bytes
        assert "image/jpeg" in resp.headers["content-type"]

    def test_cache_control_header_present(self, client, tmp_path):
        import api.image as image_mod
        image_mod._CACHE_DIR = tmp_path

        with patch("api.image.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-type": "image/webp"}
            mock_resp.content = b"webpdata"
            mock_resp.raise_for_status = MagicMock()

            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_ctx

            resp = client.get("/api/image?url=https://www.kapruka.com/w.webp")

        assert "max-age=86400" in resp.headers.get("cache-control", "")

    def test_serves_from_disk_cache_on_second_request(self, client, tmp_path):
        import api.image as image_mod
        image_mod._CACHE_DIR = tmp_path

        url = "https://www.kapruka.com/cached.jpg"
        fake_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 8

        with patch("api.image.httpx.AsyncClient") as MockClient:
            mock_resp = MagicMock()
            mock_resp.headers = {"content-type": "image/jpeg"}
            mock_resp.content = fake_bytes
            mock_resp.raise_for_status = MagicMock()

            mock_ctx = MagicMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.get = AsyncMock(return_value=mock_resp)
            MockClient.return_value = mock_ctx

            # First request — fetches from network
            resp1 = client.get(f"/api/image?url={url}")
            # Second request — should hit disk cache, not network
            resp2 = client.get(f"/api/image?url={url}")

        assert resp1.content == resp2.content
        # httpx.get called only once
        assert mock_ctx.get.call_count == 1
