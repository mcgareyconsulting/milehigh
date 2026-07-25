"""
@milehigh-header
schema_version: 1
purpose: Render a GC-facing multi-phase look-ahead schedule to a print-ready landscape PDF
  (Gantt only). Compact phase key lives in the footer; no date-table appendix.
exports:
  render_schedule_pdf(schedule) -> bytes
imports_from: [io, datetime, reportlab]
imported_by: [app.brain.lookahead.artifacts, tests]
invariants:
  - Deterministic for a fixed schedule payload.
  - Does not invent dates; draws only bars present on the schedule model.
  - ROW_H must leave room for code + title + stage without adjacent-row overlap.
  - Gantt-only output — no multi-page date appendix.
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
    SOURCE_ESTIMATED,
    SOURCE_HARD,
    SOURCE_MISSING,
    SOURCE_PROJECTED,
)

# Landscape letter — prints cleanly and emails well; tabloid can land later if denser jobs need it.
PAGE = landscape(letter)  # 792 x 612
MARGIN = 0.5 * inch
LABEL_W = 2.55 * inch
# Three-line labels (code / title / stage) need ~28pt of vertical text; 32pt row keeps a gap.
ROW_H = 32
BAR_H = 10
HEADER_H = 42  # title + one subtitle line (no topline legend)
DAY_MIN_W = 8  # px-ish points floor per day column
# Footer holds the compact phase key + page number.
FOOTER_RESERVE = 34

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


def _document_title(schedule: dict[str, Any]) -> str:
    """Human PDF title for the viewer tab / metadata (not just on-page header text)."""
    job = schedule.get("job")
    name = schedule.get("project_name") or (f"Job {job}" if job is not None else "Project")
    title = f"MHMW Production Look-Ahead — {name}"
    if job is not None:
        title += f" (Job {job})"
    return title


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

    title = _document_title(schedule)
    # Short subtitle only — phase key lives in the footer, not a second legend row.
    chart_span_start, chart_span_end = _chart_range(schedule)
    subtitle = (
        f"Chart {chart_span_start.isoformat()} → {chart_span_end.isoformat()}  ·  "
        f"{weeks}-wk look-ahead window {window.get('start', '?')} → {window.get('end', '?')}  ·  "
        f"Generated {generated}"
    )

    # Document metadata — without this, viewers show "Untitled" in the tab.
    c.setTitle(title)
    c.setAuthor("MHMW")
    c.setSubject(f"GC-facing production look-ahead for {name}")
    c.setCreator("MHMW Carmen look-ahead")

    range_start, range_end = chart_span_start, chart_span_end
    total_days = max(1, _days_between(range_start, range_end))

    # --- Gantt pages only ---
    _draw_header(c, page_w, page_h, title, subtitle)
    chart_top = page_h - MARGIN - HEADER_H
    chart_left = MARGIN + LABEL_W
    chart_right = page_w - MARGIN
    chart_w = chart_right - chart_left
    day_w = max(DAY_MIN_W, chart_w / total_days)

    _draw_day_axis(c, chart_left, chart_top, day_w, range_start, total_days)

    # y is the TOP of the current row band (labels and bars sit within [y - ROW_H, y]).
    y = chart_top - 12
    page_num = 1
    floor_y = MARGIN + FOOTER_RESERVE

    def _new_gantt_page():
        nonlocal y, page_num, chart_top
        _draw_footer(c, page_w, page_num, schedule)
        c.showPage()
        page_num += 1
        _draw_header(c, page_w, page_h, title, subtitle)
        chart_top = page_h - MARGIN - HEADER_H
        _draw_day_axis(c, chart_left, chart_top, day_w, range_start, total_days)
        y = chart_top - 12

    for row in rows:
        # Paginate when the next full row would collide with the footer.
        if y - ROW_H < floor_y:
            _new_gantt_page()

        _draw_row_label(c, MARGIN, y, LABEL_W - 8, row)
        _draw_row_grid(c, chart_left, y, chart_w, day_w, total_days)
        for phase in row.get("phases") or []:
            _draw_phase_bar(
                c, chart_left, y, day_w, range_start, total_days, phase
            )
        y -= ROW_H

    if not rows:
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColor(colors.grey)
        c.drawString(chart_left, y - 14, "No active releases or open drafting packages for this job.")

    _draw_footer(c, page_w, page_num, schedule)
    c.save()
    return buf.getvalue()


def _draw_header(c, page_w, page_h, title, subtitle):
    c.setFillColor(colors.Color(0.12, 0.16, 0.22))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, page_h - MARGIN - 12, title)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.Color(0.35, 0.37, 0.40))
    c.drawString(MARGIN, page_h - MARGIN - 26, subtitle)
    c.setStrokeColor(colors.Color(0.78, 0.80, 0.84))
    c.setLineWidth(0.5)
    c.line(MARGIN, page_h - MARGIN - 32, page_w - MARGIN, page_h - MARGIN - 32)


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
    """Draw labels inside the row band [y - ROW_H, y]. `y` is the top of the band."""
    code = (row.get("code") or "")[:20]
    title = (row.get("title") or "")[:48]
    stage = (row.get("stage_label") or "")[:28]

    # Baselines measured down from the band top so lines never spill into the next row.
    code_baseline = y - 11
    title_baseline = y - 20
    stage_baseline = y - 28

    c.setFillColor(colors.Color(0.15, 0.15, 0.18))
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x, code_baseline, code)

    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.Color(0.28, 0.28, 0.32))
    while c.stringWidth(title, "Helvetica", 6.5) > width and len(title) > 4:
        title = title[:-2] + "…" if len(title) > 5 else title[:-1]
    # Avoid double ellipsis if we already shortened awkwardly
    if title.endswith("……"):
        title = title[:-1]
    c.drawString(x, title_baseline, title)

    if stage:
        c.setFillColor(colors.Color(0.42, 0.44, 0.48))
        c.setFont("Helvetica", 5.5)
        while c.stringWidth(stage, "Helvetica", 5.5) > width and len(stage) > 4:
            stage = stage[:-1]
        c.drawString(x, stage_baseline, stage)


def _draw_row_grid(c, left, y, chart_w, day_w, total_days):
    """Hairline under the row band."""
    c.setStrokeColor(colors.Color(0.90, 0.91, 0.93))
    c.setLineWidth(0.35)
    c.line(left, y - ROW_H, left + chart_w, y - ROW_H)


def _draw_phase_bar(c, left, y, day_w, range_start, total_days, phase):
    """`y` is the top of the row band; bar is vertically centered in the band."""
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

    bar_h = BAR_H
    bar_y = y - (ROW_H + bar_h) / 2.0  # center in band
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
    """Compact phase key + source note + page number (replaces the old topline legend)."""
    y_swatch = MARGIN + 10
    y_note = MARGIN - 2

    # Hairline above footer
    c.setStrokeColor(colors.Color(0.82, 0.84, 0.87))
    c.setLineWidth(0.4)
    c.line(MARGIN, MARGIN + 22, page_w - MARGIN, MARGIN + 22)

    items = [
        (PHASE_DRAFTING, "Drafting"),
        (PHASE_FABRICATION, "Fab"),
        (PHASE_PAINT, "Paint*"),
        (PHASE_SHIPPING, "Ship"),
        (PHASE_INSTALLATION, "Install"),
    ]
    cx = MARGIN
    c.setFont("Helvetica", 6.5)
    for phase, label in items:
        c.setFillColor(PHASE_COLORS[phase])
        c.roundRect(cx, y_swatch, 8, 8, 1.2, fill=1, stroke=0)
        c.setFillColor(colors.Color(0.28, 0.28, 0.32))
        c.drawString(cx + 11, y_swatch + 1, label)
        cx += 52

    # Date-source edge key (short)
    c.setFillColor(colors.Color(0.40, 0.42, 0.46))
    c.setFont("Helvetica", 6)
    c.drawString(
        cx + 6,
        y_swatch + 1,
        "Border: green=committed · navy=projected · amber=estimated (hatched)",
    )

    c.setFillColor(colors.Color(0.48, 0.48, 0.52))
    c.setFont("Helvetica", 5.5)
    c.drawString(MARGIN, y_note, "*Paint duration is provisional (3 business days).")
    c.drawRightString(page_w - MARGIN, y_note, f"Page {page_num}")