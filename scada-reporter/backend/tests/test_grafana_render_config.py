from app.core.config import settings


def test_render_config_defaults():
    assert settings.GRAFANA_SA_TOKEN == ""
    assert settings.GRAFANA_RENDER_TIMEOUT == 30.0
    assert settings.GRAFANA_RENDER_WIDTH == 1000
    assert settings.GRAFANA_RENDER_HEIGHT == 500
