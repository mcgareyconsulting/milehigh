"""migrations/rename_paint_complete_to_paint_qc.py — the data backfill behind the
'Paint Complete' -> 'Paint QC' stage rename.

Runs the script's migrate() against a throwaway, file-backed SQLite DB built from the
app's own model metadata, with the URL passed explicitly so ENVIRONMENT / .env never
matter (mirrors tests/test_backfill_paint_stage_group.py, its closest sibling).
"""
import importlib.util
import json
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "migrations", "rename_paint_complete_to_paint_qc.py")


def _load_script():
    spec = importlib.util.spec_from_file_location("rename_paint_complete_to_paint_qc", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_url(tmp_path):
    """A file-backed SQLite DB with releases / release_photos / release_events /
    job_change_logs, seeded with 'Paint Complete' rows plus non-matching controls."""
    from app.models import JobChangeLog, ReleaseEvents, ReleasePhoto, Releases

    path = tmp_path / "rename_paint_qc.sqlite"
    url = f"sqlite:///{path}"

    engine = create_engine(url)
    try:
        Releases.__table__.create(engine)
        ReleasePhoto.__table__.create(engine)
        ReleaseEvents.__table__.create(engine)
        JobChangeLog.__table__.create(engine)

        with engine.begin() as conn:
            conn.execute(Releases.__table__.insert(), [
                dict(
                    id=1, job=290, release="153", job_name="Seed Job",
                    stage="Paint Complete", stage_group="READY_TO_SHIP",
                    trello_list_name="Paint complete",
                ),
                dict(
                    id=2, job=290, release="154", job_name="Seed Job 2",
                    stage="Weld Complete", stage_group="FABRICATION",
                    trello_list_name="Weld Complete",
                ),
            ])

            conn.execute(ReleasePhoto.__table__.insert(), [
                dict(
                    id=1, release_id=1, storage_key="k1", mime_type="image/jpeg",
                    file_size_bytes=100, stage="Paint Complete",
                    uploaded_at=datetime.utcnow(),
                ),
                dict(
                    id=2, release_id=2, storage_key="k2", mime_type="image/jpeg",
                    file_size_bytes=100, stage="Welded QC",
                    uploaded_at=datetime.utcnow(),
                ),
            ])

            # Payload is the model's `db.JSON` column — pass real dicts and let
            # SQLAlchemy's JSON type do the (de)serialization; pre-dumping the value
            # here would double-encode it on SQLite (stored as a JSON string of a
            # JSON string), which the migration would then read back as `str`, not
            # `dict`, and skip.
            conn.execute(ReleaseEvents.__table__.insert(), [
                dict(
                    id=1, job=290, release="153", action="update_stage",
                    payload={"from": "Paint Complete", "to": "Ship Planning"},
                    payload_hash="hash-1", source="Brain",
                ),
                dict(
                    id=2, job=290, release="153", action="update_stage",
                    payload={"from": "Welded QC", "to": "Paint Complete"},
                    payload_hash="hash-2", source="Brain",
                ),
                dict(
                    id=3, job=290, release="153", action="update_stage",
                    payload={
                        "from": "Paint Complete", "to": "Ship Planning", "via": "Paint Complete",
                    },
                    payload_hash="hash-3", source="Brain",
                ),
                dict(
                    # Non-matching: different action entirely — must never be touched,
                    # even though the text 'Paint Complete' appears in the payload.
                    id=4, job=290, release="154", action="update_notes",
                    payload={"note": "Paint Complete inspection done"},
                    payload_hash="hash-4", source="Brain",
                ),
                dict(
                    # Non-matching: update_stage but no 'Paint Complete' value at all.
                    id=5, job=290, release="154", action="update_stage",
                    payload={"from": "Weld Complete", "to": "Welded QC"},
                    payload_hash="hash-5", source="Brain",
                ),
            ])

            conn.execute(JobChangeLog.__table__.insert(), [
                dict(
                    id=1, job=290, release="153", change_type="state_change",
                    from_value="Paint Complete", to_value="Ship Planning",
                    field_name="stage", changed_at=datetime.utcnow(), source="Manual",
                ),
                dict(
                    id=2, job=290, release="153", change_type="state_change",
                    from_value="Welded QC", to_value="Paint Complete",
                    field_name="stage", changed_at=datetime.utcnow(), source="Manual",
                ),
                dict(
                    # Non-matching control.
                    id=3, job=290, release="154", change_type="state_change",
                    from_value="Weld Complete", to_value="Welded QC",
                    field_name="stage", changed_at=datetime.utcnow(), source="Manual",
                ),
            ])
    finally:
        engine.dispose()
    return url


def _state(url):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            releases = {
                r.id: (r.stage, r.trello_list_name)
                for r in conn.execute(text("SELECT id, stage, trello_list_name FROM releases"))
            }
            photos = {r.id: r.stage for r in conn.execute(text("SELECT id, stage FROM release_photos"))}
            events = {
                r.id: json.loads(r.payload)
                for r in conn.execute(text("SELECT id, payload FROM release_events"))
            }
            logs = {
                r.id: (r.from_value, r.to_value)
                for r in conn.execute(text("SELECT id, from_value, to_value FROM job_change_logs"))
            }
        return releases, photos, events, logs
    finally:
        engine.dispose()


def test_dry_run_writes_nothing(sqlite_url):
    mod = _load_script()
    before = _state(sqlite_url)
    assert mod.migrate(sqlite_url, dry_run=True) is True
    assert _state(sqlite_url) == before


def test_rename_updates_every_matching_value(sqlite_url):
    mod = _load_script()
    assert mod.migrate(sqlite_url) is True
    releases, photos, events, logs = _state(sqlite_url)

    # releases.stage renamed; trello_list_name (lowercase-c Trello list) untouched.
    assert releases[1] == ("Paint QC", "Paint complete")
    assert releases[2] == ("Weld Complete", "Weld Complete")

    # release_photos.stage renamed; non-matching row untouched.
    assert photos[1] == "Paint QC"
    assert photos[2] == "Welded QC"

    # release_events.payload: from/to/via rewritten only where they were exactly
    # 'Paint Complete'; non-matching action and non-matching values untouched.
    assert events[1] == {"from": "Paint QC", "to": "Ship Planning"}
    assert events[2] == {"from": "Welded QC", "to": "Paint QC"}
    assert events[3] == {"from": "Paint QC", "to": "Ship Planning", "via": "Paint QC"}
    assert events[4] == {"note": "Paint Complete inspection done"}  # wrong action, untouched
    assert events[5] == {"from": "Weld Complete", "to": "Welded QC"}  # no match, untouched

    # job_change_logs: both from_value and to_value renamed; control row untouched.
    assert logs[1] == ("Paint QC", "Ship Planning")
    assert logs[2] == ("Welded QC", "Paint QC")
    assert logs[3] == ("Weld Complete", "Welded QC")


def test_second_run_is_a_noop(sqlite_url, capsys):
    mod = _load_script()
    assert mod.migrate(sqlite_url) is True
    after_first = _state(sqlite_url)
    capsys.readouterr()  # discard first run's output

    assert mod.migrate(sqlite_url) is True
    captured = capsys.readouterr()

    assert _state(sqlite_url) == after_first
    assert "row(s) updated" not in captured.out
