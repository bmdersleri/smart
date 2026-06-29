from app.core.config import Settings


def test_render_config_defaults(monkeypatch):
    # Test the declared defaults in isolation — ignore the deployment .env
    # (which may set GRAFANA_SA_TOKEN) and any inherited process env.
    for key in (
        "GRAFANA_SA_TOKEN",
        "GRAFANA_RENDER_TIMEOUT",
        "GRAFANA_RENDER_WIDTH",
        "GRAFANA_RENDER_HEIGHT",
    ):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.GRAFANA_SA_TOKEN == ""
    assert s.GRAFANA_RENDER_TIMEOUT == 30.0
    assert s.GRAFANA_RENDER_WIDTH == 1000
    assert s.GRAFANA_RENDER_HEIGHT == 500
