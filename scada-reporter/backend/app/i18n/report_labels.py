"""
Report label registry for i18n support.

Keys cover every user-facing string found in:
  - app/services/excel_builder.py  (sheet titles, stat block labels, column headers)
  - app/services/pdf_builder.py    (via app/templates/report.html.j2)

Languages: en (canonical), tr (Turkish), ru (Russian), de (German), ar (Arabic).
Fallback: en  — enforced by get_labels() in __init__.py.

RU/DE translations are AI drafts; schedule human review before production.
"""

LABELS: dict[str, dict[str, str]] = {
    "en": {
        # ── Sheet / section titles ───────────────────────────────────────────
        "summary_sheet": "Summary",
        "raw_sheet": "Raw Data",
        "statistics": "Statistics",
        "percentiles": "Percentiles",
        "anomalies": "Anomalies",
        "period_summary": "Period Summary",
        "summary_stats": "Summary Statistics",
        "system_health_summary": "System Health Summary",
        "chart": "Chart",
        # ── Stat-block / column headers (Excel per-tag sheet) ────────────────
        "tag": "Tag",
        "unit": "Unit",
        "total_reads": "Total Reads",
        "good_quality": "Good Quality",
        "availability_pct": "Availability %",
        "average": "Average",
        "std_dev": "Std Dev",
        "std": "Std",
        "minimum": "Min",
        "maximum": "Max",
        "trend": "Trend",
        "trend_slope": "Trend Slope (unit/h)",
        "trend_r2": "R²",
        "anomaly_count": "Anomaly Count",
        "gap_count": "Gap Count",
        "gap_total_seconds": "Total Gap (s)",
        "gap": "Gap",
        # ── Period-aggregation table columns ─────────────────────────────────
        "period": "Period",
        "count": "Count",
        # ── Legacy inline Excel export (reports.py) ───────────────────────────
        "start_label": "Start",
        "end_label": "End",
        "interval_label": "Interval",
        # ── Anomaly table columns ─────────────────────────────────────────────
        "time": "Time",
        "value": "Value",
        "type": "Type",
        "severity": "Severity",
        "detail": "Detail",
        # ── Quality / raw data ────────────────────────────────────────────────
        "quality": "Quality",
        # ── PDF header meta ───────────────────────────────────────────────────
        "report_title": "Report",
        "period_meta": "Period",
        "generated_at": "Generated At",
        "format_label": "Format",
        # ── PDF system health summary ─────────────────────────────────────────
        "total_anomalies": "Total Anomalies",
        "avg_availability": "Average Availability",
        "tag_count": "Tag Count",
        "top_10_anomalies": "Top 10 Anomalies",
        # ── PDF page footer ───────────────────────────────────────────────────
        "page": "Page",
    },
    "tr": {
        # ── Sheet / section titles ───────────────────────────────────────────
        "summary_sheet": "Özet",
        "raw_sheet": "Ham Veri",
        "statistics": "İstatistikler",
        "percentiles": "Persentiller",
        "anomalies": "Anomaliler",
        "period_summary": "Dönem Özeti",
        "summary_stats": "Özet İstatistikler",
        "system_health_summary": "Sistem Sağlık Özeti",
        "chart": "Grafik",
        # ── Stat-block / column headers ──────────────────────────────────────
        "tag": "Tag",
        "unit": "Birim",
        "total_reads": "Toplam Okuma",
        "good_quality": "İyi Kalite",
        "availability_pct": "Erişilebilirlik %",
        "average": "Ortalama",
        "std_dev": "Std Sapma",
        "std": "Std",
        "minimum": "Min",
        "maximum": "Max",
        "trend": "Trend",
        "trend_slope": "Trend Eğimi (birim/saat)",
        "trend_r2": "R²",
        "anomaly_count": "Anomali Sayısı",
        "gap_count": "Boşluk Sayısı",
        "gap_total_seconds": "Toplam Boşluk (sn)",
        "gap": "Boşluk",
        # ── Period-aggregation table columns ─────────────────────────────────
        "period": "Dönem",
        "count": "Sayı",
        # ── Legacy inline Excel export (reports.py) ───────────────────────────
        "start_label": "Başlangıç",
        "end_label": "Bitiş",
        "interval_label": "Aralık",
        # ── Anomaly table columns ─────────────────────────────────────────────
        "time": "Zaman",
        "value": "Değer",
        "type": "Tür",
        "severity": "Şiddet",
        "detail": "Detay",
        # ── Quality / raw data ────────────────────────────────────────────────
        "quality": "Kalite",
        # ── PDF header meta ───────────────────────────────────────────────────
        "report_title": "Rapor",
        "period_meta": "Dönem",
        "generated_at": "Oluşturulma",
        "format_label": "Format",
        # ── PDF system health summary ─────────────────────────────────────────
        "total_anomalies": "Toplam Anomali",
        "avg_availability": "Ortalama Erişilebilirlik",
        "tag_count": "Tag Sayısı",
        "top_10_anomalies": "İlk 10 Anomali",
        # ── PDF page footer ───────────────────────────────────────────────────
        "page": "Sayfa",
    },
    "ru": {
        # ── Sheet / section titles ───────────────────────────────────────────
        "summary_sheet": "Сводка",
        "raw_sheet": "Исходные данные",
        "statistics": "Статистика",
        "percentiles": "Перцентили",
        "anomalies": "Аномалии",
        "period_summary": "Сводка по периодам",
        "summary_stats": "Сводная статистика",
        "system_health_summary": "Общее состояние системы",
        "chart": "График",
        # ── Stat-block / column headers ──────────────────────────────────────
        "tag": "Tag",
        "unit": "Единица",
        "total_reads": "Всего считываний",
        "good_quality": "Хорошее качество",
        "availability_pct": "Доступность %",
        "average": "Среднее",
        "std_dev": "Стд откл",
        "std": "Стд",
        "minimum": "Min",
        "maximum": "Max",
        "trend": "Тренд",
        "trend_slope": "Наклон тренда (ед/ч)",
        "trend_r2": "R²",
        "anomaly_count": "Кол-во аномалий",
        "gap_count": "Кол-во пропусков",
        "gap_total_seconds": "Суммарный пропуск (с)",
        "gap": "Пропуск",
        # ── Period-aggregation table columns ─────────────────────────────────
        "period": "Период",
        "count": "Кол-во",
        # ── Legacy inline Excel export (reports.py) ───────────────────────────
        "start_label": "Начало",
        "end_label": "Конец",
        "interval_label": "Интервал",
        # ── Anomaly table columns ─────────────────────────────────────────────
        "time": "Время",
        "value": "Значение",
        "type": "Тип",
        "severity": "Серьёзность",
        "detail": "Детали",
        # ── Quality / raw data ────────────────────────────────────────────────
        "quality": "Качество",
        # ── PDF header meta ───────────────────────────────────────────────────
        "report_title": "Отчёт",
        "period_meta": "Период",
        "generated_at": "Создан",
        "format_label": "Формат",
        # ── PDF system health summary ─────────────────────────────────────────
        "total_anomalies": "Всего аномалий",
        "avg_availability": "Средняя доступность",
        "tag_count": "Кол-во тегов",
        "top_10_anomalies": "Топ 10 аномалий",
        # ── PDF page footer ───────────────────────────────────────────────────
        "page": "Страница",
    },
    "de": {
        # ── Sheet / section titles ───────────────────────────────────────────
        "summary_sheet": "Übersicht",
        "raw_sheet": "Rohdaten",
        "statistics": "Statistiken",
        "percentiles": "Perzentile",
        "anomalies": "Anomalien",
        "period_summary": "Periodenübersicht",
        "summary_stats": "Zusammenfassende Statistiken",
        "system_health_summary": "Systemgesundheitsübersicht",
        "chart": "Diagramm",
        # ── Stat-block / column headers ──────────────────────────────────────
        "tag": "Tag",
        "unit": "Einheit",
        "total_reads": "Gesamtlesungen",
        "good_quality": "Gute Qualität",
        "availability_pct": "Verfügbarkeit %",
        "average": "Durchschnitt",
        "std_dev": "Std.-Abw.",
        "std": "Std",
        "minimum": "Min",
        "maximum": "Max",
        "trend": "Trend",
        "trend_slope": "Trendneigung (Einh./h)",
        "trend_r2": "R²",
        "anomaly_count": "Anomalieanzahl",
        "gap_count": "Lückenanzahl",
        "gap_total_seconds": "Gesamtlücke (s)",
        "gap": "Lücke",
        # ── Period-aggregation table columns ─────────────────────────────────
        "period": "Zeitraum",
        "count": "Anzahl",
        # ── Legacy inline Excel export (reports.py) ───────────────────────────
        "start_label": "Beginn",
        "end_label": "Ende",
        "interval_label": "Intervall",
        # ── Anomaly table columns ─────────────────────────────────────────────
        "time": "Zeit",
        "value": "Wert",
        "type": "Typ",
        "severity": "Schweregrad",
        "detail": "Detail",
        # ── Quality / raw data ────────────────────────────────────────────────
        "quality": "Qualität",
        # ── PDF header meta ───────────────────────────────────────────────────
        "report_title": "Bericht",
        "period_meta": "Zeitraum",
        "generated_at": "Erstellt am",
        "format_label": "Format",
        # ── PDF system health summary ─────────────────────────────────────────
        "total_anomalies": "Anomalien gesamt",
        "avg_availability": "Durchschnittliche Verfügbarkeit",
        "tag_count": "Tag-Anzahl",
        "top_10_anomalies": "Top 10 Anomalien",
        # ── PDF page footer ───────────────────────────────────────────────────
        "page": "Seite",
    },
    "ar": {
        # ── Sheet / section titles ───────────────────────────────────────────
        "summary_sheet": "ملخص",
        "raw_sheet": "البيانات الخام",
        "statistics": "الإحصائيات",
        "percentiles": "المئينات",
        "anomalies": "الحالات الشاذة",
        "period_summary": "ملخص الفترة",
        "summary_stats": "إحصائيات موجزة",
        "system_health_summary": "ملخص صحة النظام",
        "chart": "رسم بياني",
        # ── Stat-block / column headers ──────────────────────────────────────
        "tag": "الوسم",
        "unit": "الوحدة",
        "total_reads": "إجمالي القراءات",
        "good_quality": "جودة جيدة",
        "availability_pct": "التوفر %",
        "average": "المتوسط",
        "std_dev": "الانحراف المعياري",
        "std": "الانحراف",
        "minimum": "الأدنى",
        "maximum": "الأقصى",
        "trend": "الاتجاه",
        "trend_slope": "ميل الاتجاه (وحدة/ساعة)",
        "trend_r2": "R²",
        "anomaly_count": "عدد الحالات الشاذة",
        "gap_count": "عدد الفجوات",
        "gap_total_seconds": "إجمالي الفجوة (ث)",
        "gap": "فجوة",
        # ── Period-aggregation table columns ─────────────────────────────────
        "period": "الفترة",
        "count": "العدد",
        # ── Legacy inline Excel export (reports.py) ───────────────────────────
        "start_label": "البداية",
        "end_label": "النهاية",
        "interval_label": "الفاصل الزمني",
        # ── Anomaly table columns ─────────────────────────────────────────────
        "time": "الوقت",
        "value": "القيمة",
        "type": "النوع",
        "severity": "الخطورة",
        "detail": "التفاصيل",
        # ── Quality / raw data ────────────────────────────────────────────────
        "quality": "الجودة",
        # ── PDF header meta ───────────────────────────────────────────────────
        "report_title": "تقرير",
        "period_meta": "الفترة",
        "generated_at": "تم الإنشاء في",
        "format_label": "التنسيق",
        # ── PDF system health summary ─────────────────────────────────────────
        "total_anomalies": "إجمالي الحالات الشاذة",
        "avg_availability": "متوسط التوفر",
        "tag_count": "عدد الوسوم",
        "top_10_anomalies": "أعلى 10 حالات شاذة",
        # ── PDF page footer ───────────────────────────────────────────────────
        "page": "صفحة",
    },
}
