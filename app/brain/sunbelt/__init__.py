"""Sunbelt Equipment-on-Rent reporting.

Parses the weekly Sunbelt CSV, reconciles each rental line to one of our jobs
(PO number -> address -> submittal), persists week-over-week snapshots, and
serves an admin report with date/cost discrepancy flags.

All ingestion flows through `ingest.ingest_snapshot` — the admin CSV upload calls
it today; a future bb@mhmw.com email adapter plugs into the same seam.
"""
