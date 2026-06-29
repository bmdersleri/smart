import base64
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.i18n import get_labels

_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir), autoescape=True)


def build_pdf(
    archive,
    per_tag_data: list[dict],
    template,
    facility_name: str,
    generated_at: datetime,
    lang: str = "en",
    grafana_charts: list[dict] | None = None,
    variables: list[dict] | None = None,
) -> bytes:
    L = get_labels(lang)  # noqa: N806 — short alias for label dict, used pervasively

    for td in per_tag_data:
        td["chart_b64"] = base64.b64encode(td.get("chart_png", b"")).decode()

    gf_charts = []
    for gc in grafana_charts or []:
        gf_charts.append(
            {
                "title": gc["title"],
                "b64": base64.b64encode(gc.get("png", b"") or b"").decode(),
                "error": gc.get("error"),
            }
        )

    html_str = _env.get_template("report.html.j2").render(
        archive=archive,
        template=template,
        per_tag_data=per_tag_data,
        facility_name=facility_name,
        generated_at=generated_at,
        L=L,
        lang=lang,
        grafana_charts=gf_charts,
    )
    return HTML(string=html_str).write_pdf()
