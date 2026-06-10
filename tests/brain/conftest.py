"""Auth-patching test clients for brain blueprint tests.

Brain blueprints import get_current_user directly, so admin_required's
get_current_user lookup goes through app.auth.utils while routes call the
name bound in their own module. Both sites must be patched.
"""
from contextlib import ExitStack

import pytest
from unittest.mock import patch


_BRAIN_PATCH_TARGETS = (
    'app.auth.utils.get_current_user',
    'app.brain.job_log.routes.get_current_user',
    'app.brain.job_log.pdf_markup_routes.get_current_user',
    'app.brain.board.routes.get_current_user',
)


@pytest.fixture(autouse=True)
def _no_background_learning():
    """Keep the post-review learnings step from spawning its background thread in tests —
    it would make a live LLM call and race the in-memory DB teardown. Tests that assert the
    trigger re-patch this target locally to get their own handle."""
    with patch('app.brain.meetings.learn.start_learning'):
        yield


@pytest.fixture(autouse=True)
def _hermetic_meeting_summary():
    """extract_into_meeting now also generates a meeting summary, which would make a live
    LLM call when an ANTHROPIC_API_KEY is present in the dev env. Force the API hop to fail
    so summarize() falls back to its deterministic stub. Tests exercising the success path
    re-patch summary._call_anthropic locally."""
    with patch('app.brain.meetings.summary._call_anthropic',
               side_effect=RuntimeError('hermetic: no live summary in tests')):
        yield


def _authed_client(app, user):
    with ExitStack() as stack:
        for target in _BRAIN_PATCH_TARGETS:
            stack.enter_context(patch(target, return_value=user))
        yield app.test_client()


@pytest.fixture
def admin_client(app, mock_admin_user):
    mock_admin_user.is_drafter = True
    yield from _authed_client(app, mock_admin_user)


@pytest.fixture
def non_admin_client(app, mock_non_admin_user):
    yield from _authed_client(app, mock_non_admin_user)
