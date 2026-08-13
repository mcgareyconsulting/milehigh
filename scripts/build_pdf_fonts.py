#!/usr/bin/env python3
"""Rebuild the TTFs the Job Log PDF export embeds, from the @fontsource WOFFs.

The app is set in Calibri throughout. Calibri is Microsoft-licensed and cannot
be redistributed, so the PDFs embed Carlito - its metric-compatible open twin,
same advance widths and shapes - and a print lays out line-for-line the same
whether the reader's screen showed Calibri or Carlito.

Carlito arrives via `@fontsource/carlito` as WOFF and WOFF2. jsPDF (and reportlab
on the server) can only embed a plain sfnt (TTF), so the printed table used to
fall back to Helvetica and look like a different document. A WOFF *is* an sfnt:
the same table directory, each table zlib-deflated, behind a 44-byte header.
Undoing that needs nothing but zlib, so this converts rather than pulling in a
second copy of the fonts.

The WOFFs are the Google-Fonts `latin` subset, which is the right size for a job
log: ASCII plus the ellipsis and em dash the PDF builder inserts when it
truncates a cell.

    python scripts/build_pdf_fonts.py            # writes frontend/public/fonts/
    python scripts/build_pdf_fonts.py --check    # verify only, no writes

Re-run after bumping @fontsource/carlito.
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FONTSOURCE = REPO_ROOT / "frontend" / "node_modules" / "@fontsource"
OUT_DIR = REPO_ROOT / "frontend" / "public" / "fonts"

# (package, source woff, emitted ttf). The Job Log table sets its header row and
# its Job Comp / Invoiced / Start install / Release # cells bold, and the
# look-ahead PDF sets its empty-state line italic, so all three faces get used.
FACES = [
    ("carlito", "carlito-latin-400-normal.woff", "carlito-400.ttf"),
    ("carlito", "carlito-latin-700-normal.woff", "carlito-700.ttf"),
    ("carlito", "carlito-latin-400-italic.woff", "carlito-400-italic.ttf"),
]

WOFF_HEADER = struct.Struct(">4sIIHHIHHIIIII")  # 44 bytes
WOFF_ENTRY = struct.Struct(">4sIIII")  # 20 bytes per table
SFNT_HEADER = struct.Struct(">IHHHH")  # 12 bytes
SFNT_RECORD = struct.Struct(">4sIII")  # 16 bytes per table

# Tables jsPDF's TTF parser reads. A subset font missing one of these embeds as
# a blank or throws at export time, so it is worth failing loudly here instead.
REQUIRED_TABLES = {b"cmap", b"glyf", b"head", b"hhea", b"hmtx", b"loca", b"maxp"}


def woff_to_ttf(data: bytes) -> bytes:
    """Return the sfnt (TTF) carried inside a WOFF 1.0 container."""
    if len(data) < WOFF_HEADER.size:
        raise ValueError("file is too short to be a WOFF")
    (
        signature, flavor, _length, num_tables, _reserved, _total_sfnt_size,
        _major, _minor, _meta_off, _meta_len, _meta_orig, _priv_off, _priv_len,
    ) = WOFF_HEADER.unpack_from(data, 0)
    if signature != b"wOFF":
        raise ValueError(f"not a WOFF (signature {signature!r}); WOFF2 is not supported")

    tables = []
    for i in range(num_tables):
        tag, offset, comp_len, orig_len, checksum = WOFF_ENTRY.unpack_from(
            data, WOFF_HEADER.size + i * WOFF_ENTRY.size
        )
        raw = data[offset:offset + comp_len]
        # Per spec, an uncompressed table stores compLength == origLength.
        table = raw if comp_len == orig_len else zlib.decompress(raw)
        if len(table) != orig_len:
            raise ValueError(f"table {tag!r} inflated to {len(table)}, expected {orig_len}")
        tables.append((tag, checksum, table))

    missing = REQUIRED_TABLES - {tag for tag, _, _ in tables}
    if missing:
        names = ", ".join(sorted(t.decode("latin-1") for t in missing))
        raise ValueError(f"font is missing table(s) jsPDF needs: {names}")

    # sfnt requires the table records sorted by tag; the data blocks that follow
    # may be in any order, so keep them parallel to the records for simplicity.
    tables.sort(key=lambda t: t[0])

    # Binary-search hints in the sfnt header. Readers that trust them rather
    # than scanning read garbage if these are wrong, so compute them properly.
    entry_selector = max(num_tables.bit_length() - 1, 0)
    search_range = (1 << entry_selector) * 16
    range_shift = num_tables * 16 - search_range

    out = bytearray()
    out += SFNT_HEADER.pack(flavor, num_tables, search_range, entry_selector, range_shift)

    offset = SFNT_HEADER.size + num_tables * SFNT_RECORD.size
    body = bytearray()
    for tag, checksum, table in tables:
        out += SFNT_RECORD.pack(tag, checksum, offset, len(table))
        body += table
        # Every table starts on a 4-byte boundary; the pad is not counted in the
        # record's length.
        pad = -len(table) % 4
        body += b"\0" * pad
        offset += len(table) + pad

    return bytes(out + body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="convert and compare against what is on disk without writing",
    )
    args = parser.parse_args()

    if not FONTSOURCE.exists():
        print(f"error: {FONTSOURCE} not found - run `npm install` in frontend/ first")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stale = []
    for package, woff_name, ttf_name in FACES:
        src = FONTSOURCE / package / "files" / woff_name
        if not src.exists():
            print(f"error: {src} not found")
            return 1
        try:
            ttf = woff_to_ttf(src.read_bytes())
        except ValueError as exc:
            print(f"error: {woff_name}: {exc}")
            return 1

        dest = OUT_DIR / ttf_name
        current = dest.read_bytes() if dest.exists() else None
        if args.check:
            state = "ok" if current == ttf else "STALE"
            if current != ttf:
                stale.append(ttf_name)
            print(f"{state:>6}  {ttf_name}  ({len(ttf):,} bytes)")
        else:
            dest.write_bytes(ttf)
            print(f"wrote  {dest.relative_to(REPO_ROOT)}  ({len(ttf):,} bytes)")

    if stale:
        print(f"\n{len(stale)} font(s) out of date - re-run without --check")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
