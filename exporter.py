"""Build a GPT-friendly activity ZIP using only the Python standard library."""

from __future__ import annotations

import csv
import html
import io
import json
import math
import zipfile
from collections.abc import Iterable, Mapping
from typing import Any

ACTIVITY_CHARTS = (
    ("heart_rate", "Heart rate", ("directHeartRate",), "bpm", 1.0),
    ("speed", "Speed", ("directSpeed",), "km/h", 3.6),
    (
        "cadence",
        "Cadence",
        ("directCadence", "directRunCadence", "directBikeCadence", "directDoubleCadence"),
        "rpm / spm",
        1.0,
    ),
    (
        "elevation",
        "Elevation",
        ("directCorrectedElevation", "directElevation", "directUncorrectedElevation"),
        "m",
        1.0,
    ),
    ("power", "Power", ("directPower", "directBikePower"), "W", 1.0),
)


def activity_metric_rows(details: Any) -> list[dict[str, Any]]:
    if not isinstance(details, Mapping):
        return []
    descriptors = details.get("metricDescriptors") or []
    samples = details.get("activityDetailMetrics") or []
    index_to_name: dict[int, str] = {}
    for descriptor in descriptors:
        if not isinstance(descriptor, Mapping):
            continue
        index = descriptor.get("metricsIndex")
        name = descriptor.get("key")
        if isinstance(index, int) and name:
            index_to_name[index] = str(name)

    rows: list[dict[str, Any]] = []
    for sample in samples:
        metrics = sample.get("metrics") if isinstance(sample, Mapping) else None
        if not isinstance(metrics, list):
            continue
        rows.append(
            {
                index_to_name.get(index, f"metric_{index}"): value
                for index, value in enumerate(metrics)
                if value is not None
            }
        )
    return rows


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return value


def metrics_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    columns = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(
        {column: _csv_value(row.get(column)) for column in columns} for row in rows
    )
    return output.getvalue()


def _numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _chart_column(rows: list[dict[str, Any]], candidates: Iterable[str]) -> str | None:
    for candidate in candidates:
        if any(_numeric(row.get(candidate)) is not None for row in rows):
            return candidate
    return None


def _chart_svg(
    rows: list[dict[str, Any]],
    column: str,
    title: str,
    unit: str,
    factor: float,
) -> str:
    points: list[tuple[float, float]] = []
    for index, row in enumerate(rows):
        value = _numeric(row.get(column))
        elapsed = _numeric(row.get("sumElapsedDuration"))
        if value is not None:
            points.append(((elapsed / 60) if elapsed is not None else float(index), value * factor))
    if not points:
        return ""
    if len(points) > 1200:
        last = len(points) - 1
        points = [points[round(index * last / 1199)] for index in range(1200)]

    width, height = 1000, 320
    left, right, top, bottom = 72, 24, 42, 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    if math.isclose(x_min, x_max):
        x_max = x_min + 1
    if math.isclose(y_min, y_max):
        y_max = y_min + 1

    def position(point: tuple[float, float]) -> str:
        x, y = point
        px = left + (x - x_min) / (x_max - x_min) * plot_width
        py = top + (y_max - y) / (y_max - y_min) * plot_height
        return f"{px:.1f},{py:.1f}"

    polyline = " ".join(position(point) for point in points)
    mean = sum(y_values) / len(y_values)
    safe_title = html.escape(title)
    safe_unit = html.escape(unit)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
viewBox="0 0 {width} {height}" role="img" aria-label="{safe_title}">
<rect width="100%" height="100%" fill="#ffffff"/>
<text x="{left}" y="24" font-family="sans-serif" font-size="18"
font-weight="bold">{safe_title}</text>
<text x="{width - right}" y="24" text-anchor="end" font-family="sans-serif" font-size="12"
fill="#475569">min {y_min:.1f} · avg {mean:.1f} · max {y_max:.1f} {safe_unit}</text>
<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#94a3b8"/>
<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"
stroke="#94a3b8"/>
<line x1="{left}" y1="{top}" x2="{width - right}" y2="{top}" stroke="#e2e8f0"/>
<text x="{left - 8}" y="{top + 4}" text-anchor="end" font-family="sans-serif"
font-size="11">{y_max:.1f}</text>
<text x="{left - 8}" y="{height - bottom + 4}" text-anchor="end" font-family="sans-serif"
font-size="11">{y_min:.1f}</text>
<text x="{left}" y="{height - 16}" font-family="sans-serif" font-size="11">{x_min:.1f}</text>
<text x="{width - right}" y="{height - 16}" text-anchor="end" font-family="sans-serif"
font-size="11">{x_max:.1f} minutes</text>
<polyline points="{polyline}" fill="none" stroke="#2563eb" stroke-width="2"
stroke-linejoin="round" stroke-linecap="round"/>
</svg>"""


def activity_report(summary: dict[str, Any], bundle: dict[str, Any]) -> str:
    sections = [
        "# Garmin session report",
        "",
        "Use this session with my broader athlete context to evaluate execution, pacing, "
        "fatigue signals, and implications for the next workout. Do not diagnose medical "
        "conditions.",
        "",
        "## Normalized summary",
        "```json",
        json.dumps(summary, indent=2, default=str),
        "```",
    ]
    for key in (
        "summary",
        "splits",
        "typed_splits",
        "split_summaries",
        "weather",
        "heart_rate_zones",
        "power_zones",
        "exercise_sets",
    ):
        value = bundle.get(key)
        if value is not None:
            sections.extend(
                [
                    "",
                    f"## Garmin {key.replace('_', ' ')}",
                    "```json",
                    json.dumps(value, indent=2, default=str),
                    "```",
                ]
            )
    warnings = bundle.get("warnings") or []
    if warnings:
        sections.extend(["", "## Export warnings"])
        sections.extend(f"- {warning}" for warning in warnings)
    return "\n".join(sections)


def full_activity_export(summary: dict[str, Any], bundle: dict[str, Any]) -> bytes:
    """Build one ZIP without storing it on disk."""
    rows = activity_metric_rows(bundle.get("details"))
    readable_bundle = {key: value for key, value in bundle.items() if key != "original_fit_zip"}
    report = activity_report(summary, bundle)
    report += "\n\n## Archive contents\n"
    report += "- `full_workout.json`: normalized summary and readable Garmin responses.\n"
    report += "- `metrics.csv`: sampled time-series values returned by Garmin.\n"
    report += "- `charts/*.svg`: available metric charts.\n"
    if bundle.get("original_fit_zip"):
        report += "- `original_fit.zip`: Garmin's untouched original FIT download.\n"

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("analysis_prompt_and_report.md", report)
        archive.writestr(
            "full_workout.json",
            json.dumps(
                {"normalized_summary": summary, "garmin": readable_bundle},
                indent=2,
                default=str,
            ),
        )
        if rows:
            archive.writestr("metrics.csv", metrics_csv(rows))
        for slug, title, candidates, unit, factor in ACTIVITY_CHARTS:
            column = _chart_column(rows, candidates)
            if column:
                archive.writestr(
                    f"charts/{slug}.svg",
                    _chart_svg(rows, column, title, unit, factor),
                )
        if original := bundle.get("original_fit_zip"):
            archive.writestr("original_fit.zip", original)
    return output.getvalue()

