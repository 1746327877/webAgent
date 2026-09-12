async def test_models_status(client, auth_headers, session_maker):
    from app.ai.model_manager import ModelManager
    from app.main import app
    from tests.fake_provider import FakeProvider

    app.state.model_manager = ModelManager(FakeProvider(), session_factory=session_maker)
    try:
        r = await client.get("/api/v1/models/status", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "current" in data and "loaded" in data and "recent_events" in data
    finally:
        del app.state.model_manager
