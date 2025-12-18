from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.web.app import create_web_app


class DummyBot:
    async def send_message(self, *args, **kwargs):
        return None


def test_upload_page_renders(monkeypatch):
    dummy_token_data = SimpleNamespace(admin_id=123)
    monkeypatch.setattr("app.web.app.verify_upload_token", lambda secret, token: dummy_token_data)

    settings = SimpleNamespace(
        upload_secret="secret",
        admin_ids={123},
        import_tmp_dir="/tmp/anki_listen_bot_import",
    )
    app = create_web_app(settings=settings, bot=DummyBot(), bot_username="bot", sessionmaker=None)
    client = TestClient(app)

    resp = client.get("/upload", params={"token": "anything"})

    assert resp.status_code == 200
    assert "Found" in resp.text or "<form" in resp.text
