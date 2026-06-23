"""Supplier material-order tracking.

Parses supplier order emails forwarded to bb@mhmw.com (Drexel Supply is the
first source) into MaterialOrder line items tagged to a job-release, surfaced on
the release detail modal as outstanding material. Mirrors the "Dencol orders"
path: it tags the release, it does NOT create a Trello card.

Flow: RawSourceRecord (lake bronze) -> parser.parse_order_email ->
service.ingest_* -> MaterialOrder. The bb mail poll calls service.ingest_unprocessed();
the same seam is exercised directly by scripts/load_drexel_fixture.py for testing.
"""
