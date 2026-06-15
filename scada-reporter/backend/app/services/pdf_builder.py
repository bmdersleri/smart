import base64
import os
from datetime import datetime

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

_template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
_env = Environment(loader=FileSystemLoader(_template_dir))


def build_pdf(
    archive,
    per_tag_data: list[dict],
    template,
    facility_name: str,
    generated_at: datetime,
) -> bytes:
    for td in per_tag_data:
        td["chart_b64"] = base64.b64encode(td.get("chart_png", b"")).decode()

    html_str = _env.get_template("report.html.j2").render(
        archive=archive,
        template=template,
        per_tag_data=per_tag_data,
        facility_name=facility_name,
        generated_at=generated_at,
    )
    return HTML(string=html_str).write_pdf()
