"""System-usage metrics: AI spend, content, activity, and health rollups.

A read-only aggregation layer over the app's existing event/telemetry tables.
Phase 1 (this module) unions the scattered AI-usage columns and content tables
into one JSON contract; Phase 2 will swap the AI normalizer for a unified
``ai_usage`` ledger without changing the endpoint contract or the UI.
"""
