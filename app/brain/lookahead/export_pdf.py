"""
@milehigh-header
schema_version: 1
purpose: Render a GC-facing multi-phase look-ahead schedule to a print-ready landscape PDF
  (Gantt page + date table appendix). Pure: schedule dict in, PDF bytes out. No DB, no Flask.
exports:
  render_schedule_pdf(schedule) -> bytes
imports_from: [io, datetime, reportlab]
imported_by: [app.brain.lookahead.artifacts, tests]
invariants:
  - Deterministic for a fixed schedule payload.
  - Does not invent dates; draws only bars present on the schedule model.
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from app.brain.lookahead.schedule_builder import (
    PHASE_DRAFTING,
    PHASE_FABRICATION,
    PHASE_INSTALLATION,
    PHASE_PAINT,
    PHASE_SHIPPING,
    PHASE_LABELS,
    SOURCE_ESTIMATED,
    SOURCE_HARD,
    SOURCE_MISSING,
    SOURCE_PROJECTED,
)

# Landscape letter — prints cleanly and emails well; tabloid can land later if denser jobs need it.
PAGE = landscape(letter)  # 792 x 612
MARGIN = 0.5 * inch
LABEL_W = 2.35 * inch
ROW_H = 16
HEADER_H = 54
LEGEND_H = 28
DAY_MIN_W = 8  # px-ish points floor per day column

PHASE_COLORS = {
    PHASE_DRAFTING: colors.Color(0.45, 0.35, 0.70),
    PHASE_FABRICATION: colors.Color(0.20, 0.40, 0.70),
    PHASE_PAINT: colors.Color(0.85, 0.50, 0.15),
    PHASE_SHIPPING: colors.Color(0.20, 0.55, 0.35),
    PHASE_INSTALLATION: colors.Color(0.15, 0.55, 0.60),
}

SOURCE_EDGE = {
    SOURCE_HARD: colors.Color(0.10, 0.45, 0.15),      # green-ish stroke
    SOURCE_PROJECTED: colors.Color(0.25, 0.25, 0.55),
    SOURCE_ESTIMATED: colors.Color(0.55, 0.40, 0.10),
    SOURCE_MISSING: colors.Color(0.50, 0.50, 0.50),
}


def _parse_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _chart_range(schedule: dict) -> tuple[date, date]:
    """X-axis covers the declared window expanded to include every phase bar date."""
    window = schedule.get("window") or {}
    start = _parse_date(window.get("start")) or date.today()
    end = _parse_date(window.get("end")) or (start + timedelta(days=21))
    for row in schedule.get("rows") or []:
        for p in row.get("phases") or []:
            s = _parse_date(p.get("start"))
            e = _parse_date(p.get("end"))
            if s and s < start:
                start = s
            if e and e > end:
                end = e
            if s and s > end:
                end = s
            if e and e < start:
                start = e
    if end < start:
        end = start
    # Pad one day on each side for readability.
    return start - timedelta(days=1), end + timedelta(days=1)


def _days_between(a: date, b: date) -> int:
    return (b - a).days


def render_schedule_pdf(schedule: dict[str, Any]) -> bytes:
    """Return PDF bytes for a ``build_lookahead_schedule`` envelope."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    page_w, page_h = PAGE

    job = schedule.get("job")
    name = schedule.get("project_name") or f"Job {job}"
    window = schedule.get("window") or {}
    weeks = window.get("weeks", 3)
    generated = schedule.get("generated_on") or date.today().isoformat()
    rows = list(schedule.get("rows") or [])

    title = f"MHMW Production Look-Ahead — {name}"
    if job is not None:
        title += f"  (Job {job})"
    subtitle = (
        f"{weeks}-week window {window.get('start', '?')} → {window.get('end', '?')}  ·  "
        f"Generated {generated}  ·  GC-facing  ·  Paint bars are provisional estimates"
    )

    range_start, range_end = _chart_range(schedule)
    total_days = max(1, _days_between(range_start, range_end))

    # --- Page 1: Gantt ---
    _draw_header(c, page_w, page_h, title, subtitle)
    chart_top = page_h - MARGIN - HEADER_H - LEGEND_H
    chart_left = MARGIN + LABEL_W
    chart_right = page_w - MARGIN
    chart_w = chart_right - chart_left
    day_w = max(DAY_MIN_W, chart_w / total_days)

    _draw_legend(c, MARGIN, chart_top + 6, page_w - 2 * MARGIN)
    _draw_day_axis(c, chart_left, chart_top, day_w, range_start, total_days)

    y = chart_top - 14
    max_rows_page = int((y - MARGIN - 20) // ROW_H)
    drawn = 0
    page_num = 1

    for row in rows:
        if drawn > 0 and drawn % max_rows_page == 0:
            _draw_footer(c, page_w, page_num, schedule)
            c.showPage()
            page_num += 1
            _draw_header(c, page_w, page_h, title, subtitle)
            chart_top = page_h - MARGIN - HEADER_H - LEGEND_H
            _draw_legend(c, MARGIN, chart_top + 6, page_w - 2 * MARGIN)
            _draw_day_axis(c, chart_left, chart_top, day_w, range_start, total_days)
            y = chart_top - 14
            drawn = 0

        _draw_row_label(c, MARGIN, y, LABEL_W - 6, row)
        _draw_row_grid(c, chart_left, y, chart_w, day_w, total_days)
        for phase in row.get("phases") or []:
            _draw_phase_bar(
                c, chart_left, y, day_w, range_start, total_days, phase
            )
        y -= ROW_H
        drawn += 1

    if not rows:
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColor(colors.grey)
        c.drawString(chart_left, y - 10, "No active releases or open drafting packages for this job.")

    _draw_footer(c, page_w, page_num, schedule)

    # --- Appendix: full date table ---
    c.showPage()
    page_num += 1
    _draw_table_page(c, page_w, page_h, title, schedule, page_num)

    c.save()
    return buf.getvalue()


def _draw_header(c, page_w, page_h, title, subtitle):
    c.setFillColor(colors.Color(0.12, 0.16, 0.22))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGIN, page_h - MARGIN - 14, title)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.Color(0.30, 0.32, 0.36))
    c.drawString(MARGIN, page_h - MARGIN - 28, subtitle)
    c.setStrokeColor(colors.Color(0.75, 0.78, 0.82))
    c.setLineWidth(0.6)
    c.line(MARGIN, page_h - MARGIN - 36, page_w - MARGIN, page_h - MARGIN - 36)


def _draw_legend(c, x, y, width):
    c.setFont("Helvetica", 7)
    items = [
        (PHASE_DRAFTING, "Drafting"),
        (PHASE_FABRICATION, "Fabrication"),
        (PHASE_PAINT, "Paint (est.)"),
        (PHASE_SHIPPING, "Shipping"),
        (PHASE_INSTALLATION, "Installation"),
    ]
    cx = x
    for phase, label in items:
        c.setFillColor(PHASE_COLORS[phase])
        c.rect(cx, y, 9, 9, fill=1, stroke=0)
        c.setFillColor(colors.Color(0.2, 0.2, 0.2))
        c.drawString(cx + 12, y + 1, label)
        cx += 78
    # Source keys
    c.setFillColor(colors.Color(0.2, 0.2, 0.2))
    c.drawString(cx + 8, y + 1, "Edge: green=committed · blue=projected · amber=estimated")


def _draw_day_axis(c, left, top, day_w, range_start, total_days):
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.Color(0.35, 0.35, 0.40))
    for i in range(total_days + 1):
        d = range_start + timedelta(days=i)
        x = left + i * day_w
        # Monday ticks stronger + label
        if d.weekday() == 0 or i == 0 or i == total_days:
            c.setStrokeColor(colors.Color(0.70, 0.72, 0.76))
            c.setLineWidth(0.5)
            c.line(x, top - 4, x, top - 10)
            label = d.strftime("%m/%d")
            c.drawCentredString(x, top - 2, label)
        elif d.weekday() < 5:
            c.setStrokeColor(colors.Color(0.88, 0.90, 0.92))
            c.setLineWidth(0.3)
            c.line(x, top - 6, x, top - 10)


def _draw_row_label(c, x, y, width, row):
    code = (row.get("code") or "")[:18]
    title = (row.get("title") or "")[:42]
    stage = (row.get("stage_label") or "")[:22]
    c.setFillColor(colors.Color(0.15, 0.15, 0.18))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x, y + 6, code)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.Color(0.25, 0.25, 0.28))
    # Truncate title to width
    while c.stringWidth(title, "Helvetica", 6.5) > width and len(title) > 4:
        title = title[:-2]
    c.drawString(x, y - 2, title)
    c.setFillColor(colors.Color(0.40, 0.42, 0.46))
    c.setFont("Helvetica", 5.5)
    c.drawString(x, y - 9, stage)


def _draw_row_grid(c, left, y, chart_w, day_w, total_days):
    c.setStrokeColor(colors.Color(0.92, 0.93, 0.94))
    c.setLineWidth(0.3)
    c.line(left, y - 4, left + chart_w, y - 4)
    # Weekend shading
    # (skipped for speed; axis marks Mondays)


def _draw_phase_bar(c, left, y, day_w, range_start, total_days, phase):
    start = _parse_date(phase.get("start"))
    end = _parse_date(phase.get("end")) or start
    if start is None:
        return
    if end < start:
        start, end = end, start

    # Clip to chart range
    chart_end = range_start + timedelta(days=total_days)
    if end < range_start or start > chart_end:
        return
    s = max(start, range_start)
    e = min(end, chart_end)

    x0 = left + _days_between(range_start, s) * day_w
    # Inclusive end day → at least one day width
    span_days = max(1, _days_between(s, e) + 1)
    w = span_days * day_w
    # Point events (ship) get a minimum visible width
    w = max(w, max(4.0, day_w * 0.6))

    phase_key = phase.get("phase") or ""
    fill = PHASE_COLORS.get(phase_key, colors.Color(0.5, 0.5, 0.5))
    src = phase.get("date_source") or SOURCE_ESTIMATED
    stroke = SOURCE_EDGE.get(src, colors.black)

    bar_y = y - 1
    bar_h = 8
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.8 if src == SOURCE_HARD else 0.5)
    c.roundRect(x0, bar_y, w, bar_h, 2, fill=1, stroke=1)

    # Estimated: light hatch via diagonal ticks
    if src == SOURCE_ESTIMATED and w > 10:
        c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.35))
        c.setLineWidth(0.4)
        step = 4
        xx = x0 + 2
        while xx < x0 + w - 2:
            c.line(xx, bar_y + 1, min(xx + 3, x0 + w - 1), bar_y + bar_h - 1)
            xx += step


def _draw_footer(c, page_w, page_num, schedule):
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.Color(0.45, 0.45, 0.48))
    assumptions = (schedule.get("assumptions") or {}).get("paint_note") or ""
    c.drawString(MARGIN, MARGIN - 4, assumptions[:110])
    c.drawRightString(page_w - MARGIN, MARGIN - 4, f"Page {page_num}")


def _draw_table_page(c, page_w, page_h, title, schedule, page_num):
    _draw_header(
        c, page_w, page_h, title,
        "Date appendix — full phase dates (not clipped to chart window)",
    )
    y = page_h - MARGIN - HEADER_H
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(colors.Color(0.15, 0.15, 0.18))
    headers = ["Code", "Title", "Phase", "Start", "End", "Source", "Status"]
    cols = [70, 180, 70, 60, 60, 70, 100]
    x = MARGIN
    for h, w in zip(headers, cols):
        c.drawString(x, y, h)
        x += w
    y -= 10
    c.setStrokeColor(colors.Color(0.75, 0.78, 0.82))
    c.line(MARGIN, y + 6, page_w - MARGIN, y + 6)

    c.setFont("Helvetica", 7)
    for row in schedule.get("rows") or []:
        code = row.get("code") or ""
        title_s = (row.get("title") or "")[:40]
        stage = row.get("stage_label") or ""
        phases = row.get("phases") or []
        if not phases:
            if y < MARGIN + 30:
                _draw_footer(c, page_w, page_num, schedule)
                c.showPage()
                page_num += 1
                _draw_header(
                    c, page_w, page_h, title,
                    "Date appendix (continued)",
                )
                y = page_h - MARGIN - HEADER_H
                c.setFont("Helvetica", 7)
            _table_line(c, y, cols, [code, title_s, "—", "—", "—", "—", stage])
            y -= 11
            continue
        for phase in phases:
            if y < MARGIN + 30:
                _draw_footer(c, page_w, page_num, schedule)
                c.showPage()
                page_num += 1
                _draw_header(
                    c, page_w, page_h, title,
                    "Date appendix (continued)",
                )
                y = page_h - MARGIN - HEADER_H
                c.setFont("Helvetica", 7)
            label = PHASE_LABELS.get(phase.get("phase"), phase.get("phase") or "")
            _table_line(c, y, cols, [
                code,
                title_s,
                label,
                phase.get("start") or "—",
                phase.get("end") or "—",
                phase.get("date_source") or "—",
                stage,
            ])
            y -= 11
            code = ""  # only first phase shows code/title
            title_s = ""
            stage = ""

    # Flags
    flags = schedule.get("flags") or []
    if flags:
        y -= 14
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.Color(0.2, 0.2, 0.2))
        c.drawString(MARGIN, y, "Data notes")
        y -= 12
        c.setFont("Helvetica", 7)
        for f in flags[:40]:
            if y < MARGIN + 20:
                break
            msg = f.get("message") or f.get("code") or ""
            c.drawString(MARGIN, y, f"• {msg}"[:140])
            y -= 10

    _draw_footer(c, page_w, page_num, schedule)


def _table_line(c, y, cols, values):
    c.setFillColor(colors.Color(0.18, 0.18, 0.20))
    x = MARGIN
    for val, w in zip(values, cols):
        text = str(val) if val is not None else ""
        while c.stringWidth(text, "Helvetica", 7) > w - 4 and len(text) > 3:
            text = text[:-2]
        c.drawString(x, y, text)
        x += w
