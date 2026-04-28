# Test Strategy

This document describes how the test suite is organized, what conventions to follow, and where coverage is strong vs. weak. Read this before adding tests.

## Running tests

```bash
pytest                                   # full suite
pytest tests/dwl/                        # one suite
pytest tests/test_hours_summary.py       # one file
pytest tests/test_hours_summary.py::test_calculate_total_fab_hrs  # one test
pytest -k "stage and not slow"           # by name pattern
pytest -x --ff                           # stop on first fail, run failed first

# coverage
pytest --cov=app --cov-report=term-missing
pytest --cov=app --cov-report=html      # open htmlcov/index.html
```

`tests/conftest.py` sets `TESTING=1` before `create_app()` is imported so the app always uses in-memory SQLite. **Never override this** — it's the only thing standing between the suite and a real sandbox/production DB.

## Layering

Tests fall into three layers. Pick the layer that matches the unit you're testing.

| Layer | Flask app? | DB? | Mocked? | Examples |
|---|---|---|---|---|
| **Pure unit** | no | no | nothing — pure functions | `test_dwl_engine.py`, `test_hours_summary.py`, `test_procore_auth.py` |
| **Service** | sometimes | in-memory or mocked | external APIs only | `test_dwl_service.py` |
| **Integration** | yes (test_client) | in-memory | external APIs only | `test_dwl_routes.py`, webhook handler tests |

**Rule:** prefer the lowest layer that exercises the behavior. A pure unit test for `_normalize_stage` is more valuable than an HTTP test that happens to call it.

## Fixtures

Root `tests/conftest.py` provides the shared fixtures:

- `app` — Flask app with in-memory SQLite, `db.create_all()` / `db.drop_all()` lifecycle
- `client` — `app.test_client()`
- `mock_admin_user`, `mock_non_admin_user` — `Mock`-spec User objects for auth patching

Subdirectory `conftest.py` files add domain-specific fixtures only:

- `tests/dwl/conftest.py` — `mock_submittal`, autouse `setup_auth` (DWL tests run authenticated by default)
- `tests/brain/conftest.py` — `admin_client`, `non_admin_client` (these patch brain-specific call sites of `get_current_user`)

When the patch sites for `get_current_user` differ across blueprints (e.g. `app.brain.job_log.routes` imports it directly), define the auth-patching fixture next to the tests, not in root.

## Mocking conventions

- **External services are always mocked.** Procore API, Trello API, OneDrive Graph — no real network calls in any test.
- **The DB is always real (in-memory).** Don't mock SQLAlchemy unless the test is purely about a service method's business logic. Mocked DB tests are easy to make green and easy to make wrong.
- **Time:** when a test depends on `datetime.utcnow()`, freeze it with `freezegun` or pass timestamps explicitly. Don't rely on real time.
- **Outbox:** when testing code that calls `OutboxService.add`, patch `app.services.outbox_service.OutboxService.add` to avoid creating real DB outbox rows you'll then have to assert on.

## Naming & layout

- Test files: `tests/test_<feature>.py` for cross-cutting; `tests/<domain>/test_<x>.py` for domain-specific
- Test functions: `test_<what>_<condition>_<outcome>` — e.g. `test_login_inactive_user_returns_401`
- One assertion concept per test. Multiple `assert` lines are fine if they verify the same outcome; don't combine unrelated checks.

## Coverage map (as of 2026-04-27)

### Well-tested
- **Drafting Work Load** — engine, service, routes (3-layer pyramid, ~135 tests)
- **Stage ordering / fab order** — comprehensive helper + command coverage
- **Trello ↔ job log sync** — rank gate, hold stickiness, outbound gate
- **Procore helpers** — webhook helpers, token expiry, API client retries
- **Hours summary KPIs** — pure functions
- **Scheduling cascade** — red date protection, hold cascade

### Known gaps (priority order)
- **Auth routes** — login, logout, set-password, check-user (`tests/test_auth_routes.py`)
- **Sync lock** — reentrancy, timeout, decorator (`tests/test_sync_lock.py`)
- **Outbox service** — retry/backoff, max-retry exhaustion (`tests/services/test_outbox_service.py`)
- **Procore webhook handler** — burst dedup, connector skip, create/update branching (`tests/test_procore_webhook.py`)
- **Trello webhook handler** — lock contention, queue overflow (`tests/test_trello_webhook.py`)
- **Board / bug tracker** — CRUD, mentions, status changes (`tests/brain/test_board.py`)

### Out of scope (lower runtime risk)
- `app/sync/sync.py` — large; covered indirectly through Trello sync tests
- `app/services/database_mapping.py` — Excel ingest path
- `app/onedrive/` — polling currently disabled
- `app/history/` — read-only queries
- `app/admin/` — low-frequency manual operations

## Adding a test

1. Pick the layer (pure / service / integration). Prefer pure when possible.
2. Reuse existing fixtures from root or subdirectory conftest. Don't redefine `app` or auth fixtures.
3. Mock external services; let the DB run real (in-memory).
4. Run `pytest <your-file> -v` and `pytest` (full suite) before committing.

## CI

`.github/workflows/test.yml` runs `pytest` with coverage on every PR to `main`. Coverage is reported via `--cov-report=term-missing` and uploaded as an artifact. The `--cov-fail-under` threshold is intentionally set near current measured coverage so it's a regression gate, not a ratchet — bump it explicitly when you've added meaningful new coverage.

### Future direction (not yet implemented)
- Ratchet `--cov-fail-under` upward as gaps are filled
- Split unit (`tests/` minus `*_routes`, `*_webhook`) and integration (`*_routes`, `*_webhook`) into separate jobs for fast-feedback
- Scheduled nightly run to catch flakes that slip past PR gating
- Frontend coverage gate once vitest suite grows past smoke level
