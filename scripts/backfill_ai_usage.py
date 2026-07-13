"""
One-off backfill: populate the unified `ai_usage` ledger from the per-feature usage
columns that predate it.

Reads historical spend from bb_chat_messages, meetings (extract_*), meeting_learnings,
and bb_drawing_reviews and writes one AiUsage row each. Deduped by
(feature, entity_type, entity_id) so it is SAFE TO RE-RUN and safe to run alongside
live writes — a call site that already wrote its ledger row is skipped here.

`material_orders` has no historical usage column (it dropped usage before Phase 2),
so there is nothing to backfill for it — only new calls are metered.

**Prod-safe by construction.** Unlike a create_app()-based script, this connects with
a standalone SQLAlchemy engine/session (like the migration scripts) and NEVER boots the
Flask app — so it does not start the APScheduler or, critically, the outbox retry worker
thread, which would otherwise race the live web process and could double-deliver queued
Trello/Procore calls. The work itself is read-only SELECTs plus append-only INSERTs into
the isolated `ai_usage` table (no locks on live tables).

Run AFTER migrations/add_ai_usage_table.py.

Usage:
    .venv/bin/python -m scripts.backfill_ai_usage           # dry-run, prints counts
    .venv/bin/python -m scripts.backfill_ai_usage --apply    # writes rows
    .venv/bin/python -m scripts.backfill_ai_usage --database-url postgresql://...
"""
import argparse
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Importing the models configures their mappers on db.metadata; it does NOT boot the app.
from app.models import (
    AiUsage, BBChatMessage, BBChatConversation, Meeting, MeetingLearning, BBDrawingReview,
)
from app.services.ai_usage import compute_cost

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(ROOT_DIR, "instance", "jobs.sqlite")
_STUB = "stub"

load_dotenv()


# --- DB URL resolution (mirrors migrations/add_ai_usage_table.py; no create_app) ---

def _normalize_sqlite_path(path: str) -> str:
    if not os.path.isabs(path):
        path = os.path.join(ROOT_DIR, path)
    return f"sqlite:///{path}"


def _coerce_url(value: str) -> str:
    value = value.strip()
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    if value.startswith(("postgresql://", "mysql://", "mariadb://", "sqlite://")):
        return value
    return _normalize_sqlite_path(value)


def infer_database_url(cli_url: str = None) -> str:
    if cli_url:
        return _coerce_url(cli_url)
    environment = (os.environ.get("ENVIRONMENT") or "local").strip().lower()
    if environment in ("production", "sandbox"):
        prefix = "PRODUCTION" if environment == "production" else "SANDBOX"
        value = os.environ.get(f"{prefix}_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not value:
            raise ValueError(
                f"ENVIRONMENT={environment} but neither {prefix}_DATABASE_URL nor "
                "DATABASE_URL is set (refusing to guess; pass --database-url)."
            )
        return _coerce_url(value)
    for value in (os.environ.get("LOCAL_DATABASE_URL"), os.environ.get("DATABASE_URL"),
                  os.environ.get("SQLALCHEMY_DATABASE_URI"), os.environ.get("JOBS_DB_URL")):
        if value:
            return _coerce_url(value)
    return _normalize_sqlite_path(DEFAULT_SQLITE_PATH)


def _mask(url: str) -> str:
    try:
        u = urlparse(url)
        if u.hostname:
            user = f"{u.username}@" if u.username else ""
            return f"{u.scheme}://{user}{u.hostname}/{u.path.lstrip('/')}"
    except Exception:
        pass
    return url.split("@")[-1] if "@" in url else url


# --- Collection + write ---

def _existing_keys(session):
    """Set of (feature, entity_type, entity_id) already in the ledger — for dedup."""
    rows = session.query(AiUsage.feature, AiUsage.entity_type, AiUsage.entity_id).all()
    return {(f, et, ei) for f, et, ei in rows}


def _collect(session):
    """Build the candidate AiUsage rows from each source table. Returns list of dicts."""
    out = []

    # bb_chat — assistant turns carry the full ledger already.
    q = (
        session.query(BBChatMessage, BBChatConversation.user_id)
        .join(BBChatConversation, BBChatMessage.conversation_id == BBChatConversation.id)
        .filter(BBChatMessage.role == "assistant")
    )
    for m, uid in q.all():
        out.append(dict(
            feature="bb_chat", entity_type="bb_chat_message", entity_id=str(m.id),
            user_id=uid, model=m.model,
            input_tokens=m.input_tokens or 0, output_tokens=m.output_tokens or 0,
            cache_read_tokens=m.cache_read_tokens or 0, cache_write_tokens=m.cache_write_tokens or 0,
            cost_usd=m.cost_usd or 0.0, duration_ms=m.duration_ms,
            request_id=m.anthropic_request_id, created_at=m.created_at,
        ))

    # meetings — blended to-do extraction meter on the meeting row.
    for mt in session.query(Meeting).filter(
        Meeting.extract_model.isnot(None), Meeting.extract_model != _STUB,
    ).all():
        out.append(dict(
            feature="meetings", entity_type="meeting", entity_id=str(mt.id),
            user_id=mt.created_by, model=mt.extract_model,
            input_tokens=mt.extract_input_tokens or 0, output_tokens=mt.extract_output_tokens or 0,
            cache_read_tokens=0, cache_write_tokens=0,
            cost_usd=mt.extract_cost_usd or 0.0, duration_ms=None,
            request_id=None, created_at=(mt.extracted_at or mt.created_at),
        ))

    # meeting learnings — synthesis pass.
    for lr in session.query(MeetingLearning).filter(
        MeetingLearning.model.isnot(None), MeetingLearning.model != _STUB,
    ).all():
        out.append(dict(
            feature="meeting_learning", entity_type="meeting_learning", entity_id=str(lr.id),
            user_id=None, model=lr.model,
            input_tokens=lr.input_tokens or 0, output_tokens=lr.output_tokens or 0,
            cache_read_tokens=0, cache_write_tokens=0,
            cost_usd=lr.cost_usd or 0.0, duration_ms=None,
            request_id=None, created_at=lr.created_at,
        ))

    # BB PDF review — stores tokens but no cost; compute it from the shared pricing.
    for rv in session.query(BBDrawingReview).filter(BBDrawingReview.model.isnot(None)).all():
        out.append(dict(
            feature="pdf_review", entity_type="drawing_review", entity_id=str(rv.id),
            user_id=rv.requested_by_user_id, model=rv.model,
            input_tokens=rv.input_tokens or 0, output_tokens=rv.output_tokens or 0,
            cache_read_tokens=0, cache_write_tokens=0,
            cost_usd=compute_cost(rv.model, rv.input_tokens or 0, rv.output_tokens or 0),
            duration_ms=None, request_id=None, created_at=rv.created_at,
        ))

    return out


def backfill(session, apply: bool) -> int:
    """Insert missing ai_usage rows into `session`. Returns the number written."""
    seen = _existing_keys(session)
    candidates = _collect(session)

    per_feature = {}
    written = 0
    for c in candidates:
        key = (c["feature"], c["entity_type"], c["entity_id"])
        if key in seen:
            continue
        seen.add(key)
        per_feature[c["feature"]] = per_feature.get(c["feature"], 0) + 1
        written += 1
        if apply:
            session.add(AiUsage(
                feature=c["feature"], user_id=c["user_id"], model=c["model"],
                anthropic_request_id=c["request_id"],
                input_tokens=c["input_tokens"], output_tokens=c["output_tokens"],
                cache_read_tokens=c["cache_read_tokens"], cache_write_tokens=c["cache_write_tokens"],
                cost_usd=c["cost_usd"], duration_ms=c["duration_ms"],
                entity_type=c["entity_type"], entity_id=c["entity_id"],
                created_at=c["created_at"],
            ))

    if apply:
        session.commit()

    verb = "Wrote" if apply else "Would write"
    print(f"{verb} {written} ai_usage rows:")
    for feat, n in sorted(per_feature.items()):
        print(f"  {feat}: {n}")
    if not apply:
        print("\n(dry-run — re-run with --apply to write)")
    return written


def main():
    parser = argparse.ArgumentParser(description="Backfill the ai_usage ledger from legacy usage columns.")
    parser.add_argument("--apply", action="store_true", help="Write rows (default is dry-run).")
    parser.add_argument("--database-url", help="Override DB URL (otherwise inferred from env).")
    args = parser.parse_args()

    db_url = infer_database_url(args.database_url)
    print(f"Connecting to database: {_mask(db_url)}")
    engine = create_engine(db_url)
    try:
        with Session(engine) as session:
            backfill(session, args.apply)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
