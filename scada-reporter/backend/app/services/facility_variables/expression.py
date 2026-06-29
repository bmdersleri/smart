"""Tesis değişkeni JSON ifade ağacı: doğrulama, şekil çıkarımı, bağımlılık çıkarımı.

Saf (DB'siz) katman. Engine ve servis bunu ortak kaynak olarak kullanır.
"""

from __future__ import annotations

AGG_FUNCS = frozenset({"sum", "avg", "min", "max", "last", "delta"})
REDUCE_FUNCS = frozenset({"sum", "avg", "min", "max", "last"})
ARITH_OPS = frozenset({"add", "sub", "mul", "div"})
EXPR_OPS = frozenset(
    {"agg", "series", "const", "round", "abs", "coalesce", "moving_avg", "reduce", "ref"}
    | ARITH_OPS
)


class ExpressionError(ValueError):
    """Geçersiz ifade ağacı."""


def _is_tag_source(src: object) -> bool:
    return isinstance(src, dict) and src.get("type") == "tag" and "tag_id" in src


def infer_shape(node: object) -> str:
    """Düğümün şekli: 'scalar' | 'series'. Geçersizse ExpressionError."""
    if not isinstance(node, dict) or "op" not in node:
        raise ExpressionError(f"Geçersiz ifade düğümü: {node!r}")
    op = node["op"]
    if op not in EXPR_OPS:
        raise ExpressionError(f"Bilinmeyen op (unknown): {op!r}")

    if op in ("const", "agg", "ref"):
        return "scalar"
    if op == "series":
        return "series"
    if op == "reduce":
        if infer_shape(node.get("source")) != "series":
            raise ExpressionError("reduce yalnız series kaynağı alır")
        return "scalar"
    if op == "moving_avg":
        if infer_shape(node.get("source")) != "series":
            raise ExpressionError("moving_avg yalnız series kaynağı alır")
        return "series"
    if op in ("round", "abs"):
        return infer_shape(node.get("source"))
    if op in ARITH_OPS or op == "coalesce":
        shapes = [infer_shape(a) for a in node.get("args", [])]
        if not shapes:
            raise ExpressionError(f"{op} en az bir argüman ister")
        # series varsa sonuç series (broadcast); hepsi scalar ise scalar
        return "series" if "series" in shapes else "scalar"
    raise ExpressionError(f"Şekli çıkarılamayan op: {op!r}")  # pragma: no cover


def validate_expression(node: object, kind: str) -> None:
    """Ağacı yapısal doğrula; kök şekil `kind` ile uyuşmalı. Hata → ExpressionError."""
    _validate_node(node)
    shape = infer_shape(node)
    if shape != kind:
        raise ExpressionError(f"İfade şekli '{shape}' değişken kind '{kind}' ile uyuşmuyor")


def _validate_node(node: object) -> None:
    if not isinstance(node, dict) or "op" not in node:
        raise ExpressionError(f"Geçersiz ifade düğümü: {node!r}")
    op = node["op"]
    if op not in EXPR_OPS:
        raise ExpressionError(f"Bilinmeyen op (unknown): {op!r}")

    if op == "const":
        if not isinstance(node.get("value"), (int, float)):
            raise ExpressionError("const sayısal 'value' ister")
        return
    if op == "ref":
        if not isinstance(node.get("variable_id"), int):
            raise ExpressionError("ref tamsayı 'variable_id' ister")
        return
    if op == "agg":
        if not _is_tag_source(node.get("source")):
            raise ExpressionError("agg geçerli bir tag kaynağı ister")
        if node.get("agg") not in AGG_FUNCS:
            raise ExpressionError(f"agg fonksiyonu geçersiz: {node.get('agg')!r}")
        if not node.get("window"):
            raise ExpressionError("agg açık 'window' ister")
        return
    if op == "series":
        if not _is_tag_source(node.get("source")):
            raise ExpressionError("series geçerli bir tag kaynağı ister")
        if node.get("agg") not in AGG_FUNCS:
            raise ExpressionError(f"series agg fonksiyonu geçersiz: {node.get('agg')!r}")
        if not node.get("grain"):
            raise ExpressionError("series açık 'grain' ister")
        if not node.get("window"):
            raise ExpressionError("series açık 'window' ister")
        return
    if op == "reduce":
        if node.get("reduce") not in REDUCE_FUNCS:
            raise ExpressionError(f"reduce fonksiyonu geçersiz: {node.get('reduce')!r}")
        _validate_node(node.get("source"))
        return
    if op == "moving_avg":
        if not isinstance(node.get("window_size"), int) or node["window_size"] < 1:
            raise ExpressionError("moving_avg pozitif tamsayı 'window_size' ister")
        _validate_node(node.get("source"))
        return
    if op == "round":
        if not isinstance(node.get("ndigits", 0), int):
            raise ExpressionError("round tamsayı 'ndigits' ister")
        _validate_node(node.get("source"))
        return
    if op == "abs":
        _validate_node(node.get("source"))
        return
    if op == "div":
        if node.get("on_zero") not in ("null", "zero", "fail"):
            raise ExpressionError("div açık 'on_zero' (null|zero|fail) ister")
        _validate_args(node)
        return
    if op in ARITH_OPS or op == "coalesce":
        _validate_args(node)
        return


def _validate_args(node: dict) -> None:
    args = node.get("args")
    if not isinstance(args, list) or not args:
        raise ExpressionError(f"{node['op']} boş olmayan 'args' listesi ister")
    for a in args:
        _validate_node(a)


def extract_dependencies(node: object) -> list[tuple[str, int | None, int | None]]:
    """Ağaçtaki tüm tag ve variable bağımlılıklarını (tekilleştirilmiş) döndür."""
    seen: set[tuple[str, int | None, int | None]] = set()
    _walk_deps(node, seen)
    return list(seen)


def _walk_deps(node: object, seen: set) -> None:
    if not isinstance(node, dict):
        return
    op = node.get("op")
    if op in ("agg", "series"):
        src = node.get("source")
        if (
            isinstance(src, dict)
            and src.get("type") == "tag"
            and isinstance(src.get("tag_id"), int)
        ):
            seen.add(("tag", src["tag_id"], None))  # type: ignore[index]
        return
    if op == "ref":
        if isinstance(node.get("variable_id"), int):
            seen.add(("variable", None, int(node["variable_id"])))
        return
    if "source" in node:
        _walk_deps(node["source"], seen)
    for a in node.get("args", []):
        _walk_deps(a, seen)
