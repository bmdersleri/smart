import base64
import html as _html
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

    # Tesis değişkenleri bölümü — etiket içeriğinden sonra ekleniyor
    variables_html = ""
    if variables:
        rows = ""
        for v in variables:
            if v["kind"] == "scalar":
                val = "" if v["value"] is None else str(v["value"])
            else:
                val = f"{len(v.get('points') or [])} nokta"
            warn = v.get("warning") or ""
            rows += (
                f"<tr><td>{_html.escape(str(v['code']))}</td>"
                f"<td>{_html.escape(str(v['name']))}</td>"
                f"<td>{_html.escape(str(v['unit']))}</td>"
                f"<td>{_html.escape(str(v['kind']))}</td>"
                f"<td>{_html.escape(val)}</td>"
                f"<td>{_html.escape(str(warn))}</td></tr>"
            )
        variables_html = (
            "<h2>Tesis Değişkenleri</h2>"
            "<table><thead><tr>"
            "<th>Kod</th><th>Ad</th><th>Birim</th>"
            "<th>Tür</th><th>Değer / Seri</th><th>Uyarı</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        html_str = html_str.replace("</body>", variables_html + "\n</body>", 1)

    return HTML(string=html_str).write_pdf()
