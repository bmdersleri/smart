"""Reusable workflow prompt templates for SCADA MCP server."""

PROMPTS: dict[str, str] = {
    "analyze_tag": (
        "'{tag}' tag'ini incele: önce resolve_tag ile doğrula, sonra son {window} "
        "için detect_anomalies ve predict_trend çağır, bulguları özetle."
    ),
    "daily_report": (
        "Son 24 saat için {tags} tag'lerine günlük rapor üret: query_trend ile veriyi "
        "çek, generate_report (format=excel, aggregation=hourly) ile raporla."
    ),
    "system_health_check": (
        "get_system_health çağır; PLC bağlantısı kopuk veya stale tag varsa işaretle "
        "ve list_plcs ile teşhis et."
    ),
}
