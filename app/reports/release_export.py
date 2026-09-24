"""
@milehigh-header
schema_version: 1
purpose: Render a release report dict as CSV and as a landscape PDF. Both are the
  same rows the JSON report returned — the export does not query again.
exports:
  render_release_csv(report) -> str (UTF-8, leading BOM for Excel)
  render_release_pdf(report) -> bytes
imports_from: [csv, io, xml, reportlab, app.pdf_fonts, app.reports.release_query]
imported_by: [app/brain/carmen_chat/release_report.py]
invariants:
  - CSV has one data row per release and no summary row, so a spreadsheet can sum it.
  - PDF lists every release. Group totals are a summary in front of that list.
  - Text is escaped before it goes into a PDF paragraph.
"""
from __future__ import annotations

import csv
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.pdf_fonts import register_pdf_fonts
from app.reports.release_query import report_filename

_INK = colors.Color(0.11, 0.13, 0.12)
_MUTED = colors.Color(0.37, 0.41, 0.38)
_RULE = colors.Color(0.80, 0.83, 0.80)
_HEAD = colors.Color(0.93, 0.94, 0.92)
_ZEBRA = colors.Color(0.97, 0.98, 0.97)

_CSV_COLUMNS = (
    ("release_number", "Release"),
    ("job", "Job"),
    ("job_name", "Job name"),
    ("description", "Description"),
    ("billing_tag", "Billing tag"),
    ("release_tag", "Billing tag code"),
    ("stage", "Stage"),
    ("pm", "PM"),
    ("installer", "Assigned installer"),
    ("install_progress", "Install progress"),
    ("invoice_progress", "Invoice progress"),
    ("fab_hrs", "Fab hrs"),
    ("install_hrs", "Install hrs"),
    ("additional_install_hrs", "Additional install hrs"),
    ("notes", "Notes"),
    ("released", "Released"),
    ("set", "Set"),
    ("splice", "Splice"),
)


def _csv_value(row: dict, key: str):
    if key == "splice":
        return "Yes" if row.get("splice") else ""
    value = row.get(key)
    if value is None:
        return ""
    return value


def render_release_csv(report: dict) -> str:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([label for _, label in _CSV_COLUMNS])
    for row in report["rows"]:
        writer.writerow([_csv_value(row, key) for key, _ in _CSV_COLUMNS])
    return buffer.getvalue()


def _styles(font: str, font_bold: str):
    body = ParagraphStyle(
        "release-body",
        fontName=font,
        fontSize=8,
        leading=10,
        textColor=_INK,
    )
    small = ParagraphStyle(
        "release-small",
        parent=body,
        fontSize=8,
        leading=11,
        textColor=_MUTED,
    )
    title = ParagraphStyle(
        "release-title",
        fontName=font_bold,
        fontSize=16,
        leading=19,
        textColor=_INK,
    )
    section = ParagraphStyle(
        "release-section",
        fontName=font_bold,
        fontSize=10,
        leading=13,
        textColor=_INK,
        spaceBefore=8,
    )
    head = ParagraphStyle(
        "release-head",
        fontName=font_bold,
        fontSize=7.5,
        leading=9,
        textColor=_INK,
    )
    cell = ParagraphStyle(
        "release-cell",
        fontName=font,
        fontSize=7.5,
        leading=9,
        textColor=_INK,
    )
    right = ParagraphStyle("release-right", parent=cell, alignment=2)
    return {
        "body": body,
        "small": small,
        "title": title,
        "section": section,
        "head": head,
        "cell": cell,
        "right": right,
    }


def _p(text, style) -> Paragraph:
    return Paragraph(escape("" if text is None else str(text)), style)


def _hours(value) -> str:
    number = float(value or 0)
    if number == int(number):
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _table(headers: list[str], records: list[list], styles, numeric: set[int], widths):
    head = [_p(label, styles["head"]) for label in headers]
    body = []
    for record in records:
        body.append([
            _p(value, styles["right"] if index in numeric else styles["cell"])
            for index, value in enumerate(record)
        ])
    table = Table([head, *body], colWidths=widths, repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), _HEAD),
        ("TEXTCOLOR", (0, 0), (-1, -1), _INK),
        ("GRID", (0, 0), (-1, -1), 0.3, _RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    for index in numeric:
        commands.append(("ALIGN", (index, 1), (index, -1), "RIGHT"))
    for index in range(1, len(body) + 1):
        if index % 2 == 0:
            commands.append(("BACKGROUND", (0, index), (-1, index), _ZEBRA))
    table.setStyle(TableStyle(commands))
    return table


def _footer(font: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(_MUTED)
        width, _height = landscape(letter)
        canvas.drawString(0.6 * inch, 0.38 * inch, "Read-only. Every matching release is listed.")
        canvas.drawRightString(width - 0.6 * inch, 0.38 * inch, f"Page {doc.page}")
        canvas.restoreState()
    return draw


def render_release_pdf(report: dict) -> bytes:
    font, font_bold, _italic = register_pdf_fonts()
    styles = _styles(font, font_bold)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.6 * inch,
        title="Release report",
    )
    story = [
        Paragraph("Release report", styles["title"]),
        Spacer(1, 4),
        _p(report.get("summary") or "", styles["small"]),
        Spacer(1, 2),
        _p(f"Generated {report.get('generated_at') or ''}", styles["small"]),
        Spacer(1, 8),
    ]

    totals = report["totals"]
    count = totals["releases"]
    noun = "release" if count == 1 else "releases"
    story.append(Paragraph(
        f"<b>{count}</b> {noun}"
        f" · <b>{_hours(totals['fab_hrs'])}</b> fab hrs"
        f" · <b>{_hours(totals['install_hrs'])}</b> install hrs",
        styles["body"],
    ))
    if totals.get("install_note"):
        story.append(Spacer(1, 3))
        story.append(_p(totals["install_note"], styles["small"]))

    printable = landscape(letter)[0] - 1.1 * inch

    if report["group_by"] != "billing_tag" and report["by_tag"]:
        story.append(Paragraph("By billing tag", styles["section"]))
        story.append(_table(
            ["Billing tag", "Releases", "Fab hrs", "Install hrs"],
            [
                [group["label"], group["releases"], _hours(group["fab_hrs"]), _hours(group["install_hrs"])]
                for group in report["by_tag"]
            ],
            styles,
            numeric={1, 2, 3},
            widths=[printable * 0.46, printable * 0.18, printable * 0.18, printable * 0.18],
        ))

    story.append(Paragraph(f"By {report['group_label'].lower()}", styles["section"]))
    if report["groups"]:
        story.append(_table(
            [report["group_label"], "Releases", "Fab hrs", "Install hrs"],
            [
                [group["label"], group["releases"], _hours(group["fab_hrs"]), _hours(group["install_hrs"])]
                for group in report["groups"]
            ],
            styles,
            numeric={1, 2, 3},
            widths=[printable * 0.46, printable * 0.18, printable * 0.18, printable * 0.18],
        ))
        story.append(Spacer(1, 4))
        for group in report["groups"]:
            numbers = ", ".join(group["release_numbers"])
            story.append(Paragraph(
                f"<b>{escape(group['label'])}</b> — {escape(numbers)}",
                styles["small"],
            ))
    else:
        story.append(_p("No releases match.", styles["body"]))

    story.append(Paragraph("Releases", styles["section"]))
    if report["rows"]:
        headers = [
            "Release", "Project", "Description", "Billing tag", "Stage", "PM",
            "Installer", "Install prog", "Invoiced", "Fab", "Install", "Notes",
        ]
        records = []
        for row in report["rows"]:
            project = f"{row['job']} — {row['job_name']}" if row["job_name"] else str(row["job"])
            records.append([
                row["release_number"],
                project,
                row["description"],
                row["billing_tag"],
                row["stage"],
                row["pm"],
                row["installer"],
                row["install_progress"],
                row["invoice_progress"],
                _hours(row["fab_hrs"]),
                _hours(row["install_hrs"]),
                row["notes"],
            ])
        # 12 columns across the printable width. Notes and description take the slack.
        weights = [7, 12, 13, 8, 8, 4, 8, 6, 6, 4, 5, 11]
        total = sum(weights)
        story.append(_table(
            headers,
            records,
            styles,
            numeric={9, 10},
            widths=[printable * (weight / total) for weight in weights],
        ))
    else:
        story.append(_p("No releases match.", styles["body"]))

    doc.build(story, onFirstPage=_footer(font), onLaterPages=_footer(font))
    return buffer.getvalue()


def export_filename(report: dict, extension: str) -> str:
    return report_filename(report, extension)
