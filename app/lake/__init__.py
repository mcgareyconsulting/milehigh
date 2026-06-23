"""Hive Mind data lake (lakehouse-lite on Postgres).

Bronze ingestion + (later) silver normalization + gold serving for the Banana
Boy traceback feature. This increment delivers the first bronze source: the
bb@mhmw.com mailbox (app/lake/ingest/m365_mail.py) landing into
RawSourceRecord. The HTTP surface lives in routes.py (lake_bp).
"""
from app.lake.routes import lake_bp

__all__ = ["lake_bp"]
