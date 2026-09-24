"""migrations/backfill_paint_stage_group.py — the one data step behind the PAINT split.

Runs the script's migrate() against a throwaway SQLite file built from the app's
own models, with the URL passed explicitly so ENVIRONMENT / .env never matter.
"""
import importlib.util
import os

import pytest
from sqlalchemy import create_engine, text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "migrations", "backfill_paint_stage_group.py")


def _load_script():
    spec = importlib.util.spec_from_file_location("backfill_paint_stage_group", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sqlite_url(tmp_path):
    """A file-backed SQLite DB with the app's `releases` table and four seeded rows.

    Built straight from the model metadata: under TESTING the app factory pins its
    engine to :memory:, so going through create_app would never touch this file.
    """
    from app.models import Releases

    path = tmp_path / "backfill.sqlite"
    url = f"sqlite:///{path}"

    engine = create_engine(url)
    try:
        Releases.__table__.create(engine)
        with engine.begin() as conn:
            conn.execute(Releases.__table__.insert(), [
                dict(job=1, release=rel, job_name="Seed", stage=stage, stage_group=group, fab_order=10)
                for rel, stage, group in [
                    ("A", "Welded QC", "READY_TO_SHIP"),
                    ("B", "Paint Start", "READY_TO_SHIP"),
                    ("C", "Paint QC", "READY_TO_SHIP"),
                    ("D", "Weld Complete", "FABRICATION"),
                ]
            ])
    finally:
        engine.dispose()
    return url


def _groups(url):
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT release, stage_group FROM releases ORDER BY release")).all()
        return dict(rows)
    finally:
        engine.dispose()


SEEDED = {"A": "READY_TO_SHIP", "B": "READY_TO_SHIP", "C": "READY_TO_SHIP", "D": "FABRICATION"}
BACKFILLED = {"A": "PAINT", "B": "PAINT", "C": "READY_TO_SHIP", "D": "FABRICATION"}


def test_dry_run_writes_nothing(sqlite_url):
    mod = _load_script()
    assert mod.migrate(sqlite_url, dry_run=True) is True
    assert _groups(sqlite_url) == SEEDED


def test_backfill_moves_exactly_the_paint_stages(sqlite_url):
    mod = _load_script()
    assert mod.migrate(sqlite_url) is True
    assert _groups(sqlite_url) == BACKFILLED


def test_second_run_is_a_noop(sqlite_url):
    mod = _load_script()
    assert mod.migrate(sqlite_url) is True
    assert mod.migrate(sqlite_url) is True
    assert _groups(sqlite_url) == BACKFILLED


def test_script_stages_match_the_mapping():
    from app.api.helpers import STAGE_TO_GROUP
    mod = _load_script()
    assert set(mod.PAINT_STAGES) == {s for s, g in STAGE_TO_GROUP.items() if g == "PAINT"}
