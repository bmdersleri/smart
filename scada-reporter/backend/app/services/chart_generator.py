from datetime import datetime
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

BG = "#111827"
PANEL = "#1f2937"
GRID = "#374151"
TICK = "#9ca3af"
LINE = "#60a5fa"
ANOMALY = "#ef4444"


def _apply_dark_style(fig, ax):
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=TICK, labelsize=8)
    ax.xaxis.label.set_color(TICK)
    ax.yaxis.label.set_color(TICK)
    ax.title.set_color(TICK)
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.grid(color=GRID, linewidth=0.5, linestyle="--", alpha=0.7)


def generate_timeseries_chart(
    timestamps: list[datetime],
    values: list[float | None],
    anomaly_timestamps: list[datetime],
    tag_name: str,
    unit: str,
    width_in: float = 10,
    height_in: float = 3.5,
) -> bytes:
    fig, ax = plt.subplots(figsize=(width_in, height_in))
    _apply_dark_style(fig, ax)

    clean_ts = [t for t, v in zip(timestamps, values, strict=False) if v is not None]
    clean_vals = [v for v in values if v is not None]

    if clean_ts:
        ax.plot(clean_ts, clean_vals, color=LINE, linewidth=1.2, zorder=2)

    if anomaly_timestamps:
        anom_set = set(anomaly_timestamps)
        anom_ts = [
            t for t, v in zip(timestamps, values, strict=False) if t in anom_set and v is not None
        ]
        anom_vals = [
            v for t, v in zip(timestamps, values, strict=False) if t in anom_set and v is not None
        ]
        if anom_ts:
            ax.scatter(anom_ts, anom_vals, color=ANOMALY, s=30, zorder=3, label="Anomali")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m %H:%M"))
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_title(f"{tag_name}", fontsize=9, pad=4)
    ax.set_ylabel(unit, fontsize=8)

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120, facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def generate_summary_bar_chart(
    tag_names: list[str],
    avg_values: list[float],
    unit: str,
) -> bytes:
    fig, ax = plt.subplots(figsize=(10, max(3, len(tag_names) * 0.5 + 1)))
    _apply_dark_style(fig, ax)

    y_pos = range(len(tag_names))
    ax.barh(list(y_pos), avg_values, color=LINE, height=0.6)
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels([n[:31] for n in tag_names], fontsize=8)
    ax.set_xlabel(f"Ortalama ({unit})", fontsize=8)
    ax.set_title("Tag Ortalamaları", fontsize=9, pad=4)

    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120, facecolor=BG)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
