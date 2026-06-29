import pytest

from app.services.facility_variables.expression import (
    ExpressionError,
    extract_dependencies,
    infer_shape,
    validate_expression,
)

AGG_DAY = {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "delta", "window": "day"}
SERIES_DAY = {
    "op": "series",
    "source": {"type": "tag", "tag_id": 1},
    "agg": "delta",
    "grain": "day",
    "window": "7d",
}


def test_agg_is_scalar():
    assert infer_shape(AGG_DAY) == "scalar"


def test_series_is_series():
    assert infer_shape(SERIES_DAY) == "series"


def test_reduce_collapses_series_to_scalar():
    node = {"op": "reduce", "source": SERIES_DAY, "reduce": "avg"}
    assert infer_shape(node) == "scalar"


def test_moving_avg_keeps_series():
    node = {"op": "moving_avg", "source": SERIES_DAY, "window_size": 7}
    assert infer_shape(node) == "series"


def test_add_two_scalars_is_scalar():
    node = {"op": "add", "args": [AGG_DAY, {"op": "const", "value": 5}]}
    assert infer_shape(node) == "scalar"


def test_div_without_on_zero_rejected():
    node = {"op": "div", "args": [AGG_DAY, {"op": "const", "value": 2}]}
    with pytest.raises(ExpressionError, match="on_zero"):
        validate_expression(node, "scalar")


def test_div_with_on_zero_ok():
    node = {"op": "div", "args": [AGG_DAY, {"op": "const", "value": 2}], "on_zero": "null"}
    validate_expression(node, "scalar")  # no raise


def test_agg_missing_window_rejected():
    node = {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "delta"}
    with pytest.raises(ExpressionError, match="window"):
        validate_expression(node, "scalar")


def test_series_missing_grain_rejected():
    node = {"op": "series", "source": {"type": "tag", "tag_id": 1}, "agg": "delta", "window": "7d"}
    with pytest.raises(ExpressionError, match="grain"):
        validate_expression(node, "series")


def test_unknown_op_rejected():
    with pytest.raises(ExpressionError, match="bilinmeyen|unknown|op"):
        validate_expression({"op": "frobnicate"}, "scalar")


def test_shape_mismatch_rejected():
    with pytest.raises(ExpressionError, match="kind|shape|scalar|series"):
        validate_expression(SERIES_DAY, "scalar")


def test_unknown_agg_func_rejected():
    node = {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "median", "window": "day"}
    with pytest.raises(ExpressionError, match="agg"):
        validate_expression(node, "scalar")


def test_extract_dependencies_tags_and_vars():
    node = {
        "op": "add",
        "args": [
            AGG_DAY,
            {"op": "ref", "variable_id": 9},
            {"op": "agg", "source": {"type": "tag", "tag_id": 1}, "agg": "sum", "window": "day"},
        ],
    }
    deps = set(extract_dependencies(node))
    assert ("tag", 1, None) in deps
    assert ("variable", None, 9) in deps
    # tag_id 1 appears twice but is deduplicated
    assert sum(1 for d in deps if d == ("tag", 1, None)) == 1
