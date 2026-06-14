"""Parse the Sunbelt 'Equipment on Rent' CSV export into typed row dicts.

The export (account 519027) has a fixed 17-column header. We map the columns we
keep to our field names, parse money/date/quantity values, and validate the
header so a renamed/garbled file fails loudly instead of silently importing junk.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation


class SunbeltCsvError(ValueError):
    """Raised when the uploaded file is not a recognizable Sunbelt export."""


# Sunbelt header -> our field name. Account # is constant (519027) and dropped.
HEADER_MAP = {
    "Contract #": "contract_number",
    "Job #": "sunbelt_job_label",
    "Job_Location": "job_location",
    "Ordered By": "ordered_by",
    "PO_Number": "po_number",
    "Equipment Type": "equipment_type",
    "Equipment #": "equipment_number",
    "Make": "make",
    "Model": "model",
    "Quantity": "quantity",
    "Est Return Date": "est_return_date",
    "Day Rate": "day_rate",
    "Week Rate": "week_rate",
    "4 Week Rate": "four_week_rate",
    "Billed Through": "billed_through",
    "Date Rented": "date_rented",
}

_MONEY_FIELDS = ("Day Rate", "Week Rate", "4 Week Rate")
_DATE_FIELDS = ("Est Return Date", "Billed Through", "Date Rented")


def _read_text(stream):
    """Accept a str, bytes, or file-like (text/bytes) and return decoded text."""
    if isinstance(stream, str):
        return stream
    if isinstance(stream, (bytes, bytearray)):
        return bytes(stream).decode("utf-8-sig")
    data = stream.read()
    if isinstance(data, (bytes, bytearray)):
        return bytes(data).decode("utf-8-sig")
    return data


def _clean(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _parse_money(raw):
    """'$1,495.00' -> Decimal('1495.00'); blank/unparseable -> None."""
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_date(raw):
    """'M/D/YYYY' (Sunbelt) -> date; blank/unparseable -> None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def parse_sunbelt_csv(stream):
    """Parse a Sunbelt CSV into a list of row dicts keyed by our field names.

    `stream` may be a str, bytes, or file-like object. Raises SunbeltCsvError if
    the header row is missing expected columns. Fully-blank rows are skipped.
    """
    text = _read_text(stream)
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise SunbeltCsvError("CSV is empty — no header row found.")

    headers = {(h or "").strip() for h in reader.fieldnames}
    missing = [h for h in HEADER_MAP if h not in headers]
    if missing:
        raise SunbeltCsvError(
            "Not a recognized Sunbelt export — missing columns: " + ", ".join(missing)
        )

    rows = []
    for raw_row in reader:
        # Normalize keys (the export occasionally pads header whitespace).
        row = {(k or "").strip(): v for k, v in raw_row.items()}
        if not any((v or "").strip() for v in row.values()):
            continue  # skip blank trailing lines

        parsed = {
            our_name: _clean(row.get(sunbelt_name))
            for sunbelt_name, our_name in HEADER_MAP.items()
        }
        for f in _MONEY_FIELDS:
            parsed[HEADER_MAP[f]] = _parse_money(row.get(f))
        for f in _DATE_FIELDS:
            parsed[HEADER_MAP[f]] = _parse_date(row.get(f))
        parsed["quantity"] = _parse_int(row.get("Quantity")) or 1
        rows.append(parsed)

    return rows
