from app.services.grafana_templates import apply_tag_label

_LABEL = "COALESCE(NULLIF(t.description, ''), t.name)"


def test_trend_metric_swapped():
    old = "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr"
    assert f"{_LABEL} AS metric" in apply_tag_label(old)
    assert "t.name AS metric" not in apply_tag_label(old)


def test_breach_header_swapped():
    old = 'SELECT t.name, sum(CASE WHEN t.min_alarm IS NOT NULL THEN 1 ELSE 0 END) AS "Alt Limit"'
    out = apply_tag_label(old)
    assert f'SELECT {_LABEL} AS "Etiket", sum(CASE' in out


def test_distinct_on_table_swapped():
    old = "SELECT DISTINCT ON (t.id) t.name, tr.value, t.unit FROM tags t"
    out = apply_tag_label(old)
    assert f'SELECT DISTINCT ON (t.id) {_LABEL} AS "Etiket", tr.value' in out


def test_subquery_table_swapped():
    old = (
        "SELECT name, value, unit, quality, timestamp FROM ("
        "SELECT t.id AS tid, t.name, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id WHERE t.id IN (1)"
        ") WHERE rn = 1 ORDER BY tid"
    )
    out = apply_tag_label(old)
    assert f"{_LABEL} AS name" in out
    assert 'SELECT name AS "Etiket", value' in out


def test_facility_subquery_table_swapped():
    old = (
        "SELECT name, device, value, unit, quality, timestamp FROM ("
        "SELECT t.name, t.device, tr.value, t.unit, tr.quality, tr.timestamp, "
        "row_number() OVER (PARTITION BY t.id ORDER BY tr.timestamp DESC) AS rn "
        "FROM tags t JOIN tag_readings tr ON tr.tag_id = t.id"
        ") WHERE rn = 1 ORDER BY timestamp DESC LIMIT 20"
    )
    out = apply_tag_label(old)
    assert f"SELECT {_LABEL} AS name, t.device" in out
    assert 'SELECT name AS "Etiket", device' in out


def test_idempotent():
    old = "SELECT x AS time, t.name AS metric, tr.value AS value FROM tag_readings tr"
    once = apply_tag_label(old)
    assert apply_tag_label(once) == once


def test_lab_param_name_untouched():
    old = "SELECT CAST(strftime('%s', time) AS INTEGER) AS time, param_name AS metric, value"
    assert apply_tag_label(old) == old


def test_unrelated_sql_untouched():
    old = 'SELECT count(*) AS "Tag" FROM tags'
    assert apply_tag_label(old) == old
