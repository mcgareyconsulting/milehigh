"""Fixtures for the Sunbelt rental-report suite.

Admin routes go through @admin_required (which reads app.auth.utils.get_current_user)
and the upload route also calls get_current_user bound into app.admin — so both
sites are patched. `seed_jobs` lays down releases/projects/submittals mirroring the
sample CSV's interesting cases (exact PO match, address-only match, submittal-only
closed job, overdue rental).
"""
import os
from contextlib import ExitStack
from unittest.mock import patch

import pytest

CSV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "sunbelt_equipment_on_rent.csv",
)

_PATCH_TARGETS = (
    "app.auth.utils.get_current_user",
    "app.admin.get_current_user",
)


def _authed_client(app, user):
    with ExitStack() as stack:
        for target in _PATCH_TARGETS:
            stack.enter_context(patch(target, return_value=user))
        yield app.test_client()


@pytest.fixture
def admin_client(app, mock_admin_user):
    yield from _authed_client(app, mock_admin_user)


@pytest.fixture
def non_admin_client(app, mock_non_admin_user):
    yield from _authed_client(app, mock_non_admin_user)


@pytest.fixture
def seed_jobs(app):
    """Seed releases/projects/submittals mirroring the sample Sunbelt CSV cases."""
    from app.models import db, Releases, Projects, Submittals

    # 480 — active release; exact PO match.
    db.session.add(Releases(
        job=480, release="1", job_name="Wood Partners - Alta Flatirons",
        stage="Cut Start", stage_group="FABRICATION", is_archived=False,
    ))
    # 170 — active release (Banyan); drives the overdue case.
    db.session.add(Releases(
        job=170, release="1", job_name="Garrett - Banyan High Point",
        stage="Weld Start", stage_group="FABRICATION", is_archived=False,
    ))
    # 530 — East Oak Townhomes: matching address + a fully-archived (finished) release.
    #       Sunbelt mis-keys the PO as 520; address must resolve it to 530.
    db.session.add(Projects(
        name="East Oak Townhomes", job_number="530",
        address="220 E Oak St Fort Collins, CO 80524", is_active=True,
    ))
    db.session.add(Releases(
        job=530, release="896", job_name="Shaw - East Oak Townhomes",
        stage="Ship Complete", stage_group="COMPLETE", is_archived=True,
    ))
    # 490 — Capital Hill: submittal-only, all Closed (a finished job with no release).
    db.session.add(Submittals(
        submittal_id="cap-1", project_number="490",
        project_name="Capital Hill", status="Closed",
    ))
    db.session.add(Submittals(
        submittal_id="cap-2", project_number="490",
        project_name="Capital Hill", status="Closed",
    ))
    db.session.commit()
