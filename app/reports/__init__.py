"""
@milehigh-header
schema_version: 1
purpose: Read-only release reporting used by Carmen's admin tools. Lists every
  matching job-log or archive row and renders that same list as CSV and PDF.
exports:
  (package) query, export, and artifact downloads live in the sibling modules.
imports_from: []
imported_by: [app/brain/carmen_chat/release_report.py, app/brain/__init__.py]
invariants:
  - Read-only. Nothing here writes a release, an event, or an outbox row.
  - Drafting workload is a submittal list and is not part of this report.
"""
