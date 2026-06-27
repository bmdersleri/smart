from scada_core import endpoints as ep


def test_query_run_path_is_fixed():
    # eski kod yanlışlıkla "api/query/" kullanıyordu
    assert ep.QUERY_RUN == "api/query/run"


def test_current_values_uses_dashboard_tags():
    # "dashboard/current-values" ucu yok
    assert ep.DASHBOARD_TAGS == "api/dashboard/tags"


def test_trend_range_path():
    assert ep.TREND_RANGE == "api/dashboard/trend_range"


def test_resolve_path():
    assert ep.AI_RESOLVE == "api/ai/resolve"


def test_ready_path():
    assert ep.READY == "ready"
