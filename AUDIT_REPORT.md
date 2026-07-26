# MHMW / milehigh — Deep Codebase Audit

**Date:** 2026-07-05
**Scope:** Flask backend (`app/`), React 19 frontend (`frontend/`), migrations, ops scripts, CI, repo hygiene.
**Method:** Four parallel read-only audit passes (security, performance, reliability/process, code-health), each evidence-driven with the headline items independently re-verified against source. No files were modified; no database or external service was contacted.

---

## Executive summary

The application is well-architected for what it is — an internal ops tool bridging Trello, Procore, and Microsoft Graph — and shows real engineering discipline: a clean outbox/retry pattern, webhook dedup, a cursor-based delta poll with a matching index, a genuine CI gate, a migration-safety playbook born from a real incident, and a recently-completed logging rebuild that held. The feature-folder decomposition under `app/brain/job_log/features/` is a good pattern being followed for new work.

The problems cluster in three places:

1. **Secrets & access control.** Live production **and** sandbox Postgres credentials are hardcoded in three git-tracked scripts (and in git history). Several data-mutating endpoints and all three webhook receivers are completely unauthenticated / unverified. The first-login password flow can be used to seize un-onboarded employee accounts.
2. **Single-process assumptions that break under scale.** The outbox worker, sync lock, Trello queue, and thread pool are all per-process and mostly ungated — they double-run or silently stop the moment the deploy runs more than one worker or a laptop script boots the app. Inbound Trello events live only in memory and are lost on every deploy.
3. **Unindexed grow-forever tables.** The two audit-event tables (`release_events`, `submittal_events`) have no indexes on their query columns, so every history/events page gets permanently slower, and a 30-second poll re-hydrates every column of every release.

**Fix first, in order:** rotate the leaked DB passwords → auth the webhook/health-scan endpoints → gate/harden the outbox worker → index the event tables.

### Severity tally

| Area | Critical | High | Medium | Low |
|---|---|---|---|---|
| Security | 2 | 2 | 7 | 5 |
| Reliability / process | — | 6 | 9 | 4 |
| Performance | — | 5 | 8 | 7 |
| Code health | — | 2 | 8 | 5 |

---

## 1. Critical — do these now

### C1. Live prod & sandbox DB credentials committed to the repo *(verified)*
**Files:** `scripts/fix_release_pm.py:14-15`, `scripts/copy_releases_to_sandbox.py:8-9`, `scripts/drop_submittal.py:19` — all git-tracked, and present in **3 commits of history**.

Full PostgreSQL connection strings *with passwords* for the live Render-hosted prod and sandbox databases are hardcoded, e.g.:
```python
PROD_URL = "postgresql://mile_high_metal_works_..._user:G97rTBCF...@dpg-...oregon-postgres.render.com/..."
SANDBOX_URL = "postgresql://sandbox_mhmw_db_user:SLnOrx7Q...@dpg-...oregon-postgres.render.com/sandbox_mhmw_db"
```
Render external Postgres hosts are internet-reachable. Anyone with repo read access (a contractor, a leaked laptop, or a future public/mirror push) gets full read/write to production data.

**Fix:** Rotate **both** DB passwords in Render immediately — they are compromised and live in git history, so rotation is the only real remediation. Replace the constants with `os.environ["..._DATABASE_URL"]` (matching the pattern the rest of the codebase already uses). Optionally scrub history with `git filter-repo`/BFG afterward. The scope is exactly these three files (`migrations/add_test_users.py` was checked and is clean — it prompts and masks).

### C2. Account takeover via the first-login password flow *(verified)*
**Files:** `app/auth/routes.py:122-160` (`/api/auth/check-user`), `:163-243` (`/api/auth/set-password`)

Both endpoints are unauthenticated. `check-user` returns `{"exists": true, "needs_password_setup": true}` for any username — a user-enumeration oracle. `set-password` then lets **anyone** set the password (and receive a live session) for any account where `password_set == False`:
```python
if user.password_set:
    return jsonify({'error': 'Password has already been set...'}), 400
...
user.password_hash = hash_password(new_password)
session['user_id'] = user.id
```
Employee emails are predictable and even hardcoded (`boneill@mhmw.com`, `dservold@mhmw.com`, … in `config.py:193-198`). An attacker enumerates un-onboarded accounts and claims them — potentially an admin account — before the real employee logs in.

**Fix:** Gate first-login on a server-issued, single-use, time-limited invite token delivered out of band (email); never key it solely on `password_set == False`. Make `check-user` return a uniform response regardless of whether the account exists.

---

## 2. Security

### High

- **S-H1. Unauthenticated data-mutating Procore endpoints.** `POST /procore/health-scan/update` (`app/procore/__init__.py:701`) writes `submittals` rows and emits events with **no decorator**; `GET /procore/health-scan` (`:643`), `/api/webhook/deliveries` (`:393`), `/api/webhook/test` (`:508`) fire extensive outbound Procore calls unauthenticated (cost/DoS + data exfiltration). The `/admin/verify-pin` endpoint does not protect these — they're directly reachable. **Fix:** add `@admin_required`.
- **S-H2. Webhooks accept forged payloads — no signature verification anywhere.** `/trello/webhook` (`app/trello/__init__.py:86`), `/procore/webhook` (`app/procore/__init__.py:43`), and `/brain/meetings/recall-webhook` (`app/brain/meetings/routes.py:281`) do zero HMAC/signature validation (confirmed: no `hmac`/`compare_digest`/`X-Trello-Webhook` references exist). Anyone who learns the guessable URLs can forge card-move / submittal / `transcript.done` events and corrupt job-log and submittal state. **Fix:** verify Trello's `X-Trello-Webhook` HMAC-SHA1, Procore's delivery secret, and Recall's Svix signature before acting.

### Medium

- **S-M1. `SECRET_KEY` silently falls back to a public default** (`app/config.py:30`, `"dev-secret-key-change-in-production"`). If ever unset in prod, session cookies are forgeable for any `user_id` including admin. Fail startup in Sandbox/Production if unset.
- **S-M2. `SESSION_COOKIE_SECURE` is never set** (`app/config.py:31-32` sets HTTPONLY + SameSite=Lax only) — the session cookie can travel over plain HTTP. Set `SECURE = True` in non-local configs.
- **S-M3. Unauthenticated history endpoints leak data** — `/api/jobs/<job>/<release>/history`, `/api/jobs/history`, `/api/submittals/history` (`app/history/__init__.py:404,410,418`) have no decorator while the sibling report route does. Add `@login_required`.
- **S-M4. Unauthenticated write endpoints on the app factory** — `POST /api/create_card` (`app/__init__.py:511`) and `GET/POST /procore/add-link` (`:540`) mutate state anonymously; `add-link` being GET-capable also defeats SameSite CSRF protection. Add auth; make `add-link` POST-only.
- **S-M5. Admin PIN is theater** — `ADMIN_PIN` defaults to `"1234"` (`config.py:132`), plaintext `==` compare, no rate limit, and success sets no session (`app/procore/__init__.py:856-883`). The endpoints it "guards" are unauthenticated anyway (S-H1). Replace with `@admin_required`.
- **S-M6. No brute-force protection on `/api/auth/login`** (`app/auth/routes.py:30`; no rate-limit library present). Combined with S-M3's enumeration oracle, credential stuffing is unimpeded. Add Flask-Limiter + backoff/lockout.
- **S-M7. CORS default is wildcard with credentials** — `CORS_ORIGINS` defaults to `"*"` (`config.py:129`) while `supports_credentials=True` (`app/__init__.py:325-339`). A dangerous combination if the env var is ever unset in prod. Require an explicit allowlist.

### Low

- **S-L1.** Dynamic SQL interpolates column/table *identifiers* via f-string in `app/services/database_mapping.py:275-395` (values are parameterized; keys are internal today — whitelist them before this becomes injection).
- **S-L2.** SPA catch-all uses `send_file(FRONTEND_BUILD_DIR / path)` with a `<path:path>` arg (`app/__init__.py:644-647`); prefer `send_from_directory` (built-in `safe_join`).
- **S-L3.** Any authenticated user can read any release's photos/PDFs — no per-release ownership scoping (`photo_routes.py:107`, `pdf_markup_routes.py:147`). Likely intentional for an internal tool; confirm.
- **S-L4.** Weak password policy — 8-char minimum, no complexity/breach check (`app/auth/routes.py:215`).
- **S-L5.** Aging pinned deps (`psycopg2-binary==2.9.9`, `pandas==2.1.4`, `pytz==2023.3`, `structlog==23.1.0`); no headline RCE but worth a `pip-audit` pass.

### Security — done well
`.env` and secret files are gitignored and untracked; passwords hashed with `pbkdf2:sha256` (werkzeug); DB URIs are host-masked in logs; `TESTING=1` hard-forces in-memory SQLite so tests can never touch real DBs; file uploads validate magic bytes (not just extension) under a 50MB cap with server-generated storage keys; `debug=False` in prod; no `verify=False`, no `dangerouslySetInnerHTML`; the board/meetings/DWL/bb-chat/admin blueprints are consistently decorated and LLM endpoints are auth-gated.

---

## 3. Reliability & process

### High

- **R-H1. Outbox worker runs in every process, ungated, with a non-atomic claim → double delivery** *(verified: the `create_app()` block starting `outbox-retry-worker` has none of the `WERKZEUG_RUN_MAIN`/`IS_RENDER_SCHEDULER`/`TESTING` gating the scheduler has — `app/__init__.py:404-435`)*. The fetch (`outbox_service.py:864-867`) is `status=='pending'` with no `ORDER BY` and no `FOR UPDATE SKIP LOCKED`; the `status='processing'` claim commits per-item *after* the batch is fetched. Two workers (or any root script that boots the app — see R-H5) fetch the same row and the Trello call runs twice (duplicate cards/comments/moves). `ProcoreReconcileService.process_due` has the identical pattern. **Fix:** gate to one process like the scheduler and/or claim atomically (`UPDATE ... WHERE status='pending' RETURNING` / `with_for_update(skip_locked=True)`), add `ORDER BY created_at`.
- **R-H2. Trello inbound is at-most-once, in-memory.** The handler returns 200 immediately after `executor.submit` into an in-process `Queue(maxsize=1000)` (`app/trello/__init__.py:86-224`); nothing is persisted before the ack. Deploy/restart/crash loses every queued and in-flight event; a processing exception drops the event with no requeue; queue-full returns 429 (Trello doesn't reliably redeliver); drain rate is only 5 events / 5 min. This is the largest data-loss window and matches the already-scoped `TrelloInbox` work — prioritize it.
- **R-H3. Outbox items stuck in `processing` forever after a crash.** The row is marked `processing` and committed *before* the API call, but only `pending` rows are ever re-selected (`outbox_service.py:81-82`). A restart mid-flight orphans the row and never closes the linked `ReleaseEvents`. **Fix:** startup/periodic sweeper re-queues `processing` rows older than N minutes.
- **R-H4. Retry exhaustion window is ~62 seconds, then permanent drop.** Backoff is `2**n`, max 5 retries ≈ 62s total (`outbox_service.py:246-247`). Any Trello outage longer than a minute marks items `failed` with **no recovery path** (no admin requeue, no sweeper). Exhaustion *is* logged as ERROR (good). **Fix:** cap-and-hold backoff (e.g. 15 min ceiling, retry 24h) and/or a "requeue failed" admin action + alert on failed-count > 0.
- **R-H5. Root one-off scripts boot the full app, including the prod outbox worker.** `audit_archive.py`, `fix_archived_releases.py`, `check_archived_releases.py`, `run_renumber.py`, etc. call `create_app()`, which (per R-H1) starts the outbox daemon and runs `db.create_all()` against whatever `ENVIRONMENT` points at. Running a "read-only" audit script with `ENVIRONMENT=production` silently drains prod outbox rows with laptop code and can mutate schema. Also `backfill_fc_drawing_viewer_urls.py` **applies by default** (dry-run is opt-in), unlike its siblings. **Fix:** a minimal app/session factory without background threads for scripts; standardize dry-run-by-default; relocate under `scripts/`.
- **R-H6. Unauthenticated/unverified endpoints** — same set as S-H1/S-H2 plus the default `SECRET_KEY`/`ADMIN_PIN` with no prod-boot check. Fail startup in `ProductionConfig` when these are defaults.

### Medium

- **R-M1.** Scheduler gating is a silent single point of failure (`app/__init__.py:53-57`): under gunicorn neither `WERKZEUG_RUN_MAIN` nor `IS_RENDER_SCHEDULER` exists by default → forgetting the env var disables *all* cron work with only an INFO line; setting it on a multi-worker web service double-runs every job. No runtime "is the scheduler alive here" signal.
- **R-M2.** `sync_lock` (`app/sync_lock.py:119`, a module-level `RLock`) and the thread pool are per-process, so the Trello serialization they provide evaporates under multi-worker. `gunicorn.conf.py` sets no `workers`, so today safety rests on Render's start command keeping 1 worker — unenforced.
- **R-M3.** Heartbeat verifies nothing — it's `lambda: logger.info("scheduler_heartbeat")` (`app/__init__.py:88-94`). It proves APScheduler can log, not that the outbox daemon is alive or the backlog is healthy. Emit queue depth + pending/failed outbox counts + thread aliveness.
- **R-M4.** Procore webhook always ACKs 200 on exception (`app/procore/__init__.py:381-391`), depending on the reconcile net, which itself caps at 3 attempts then `failed` with no recovery.
- **R-M5.** Every pytest `app` fixture spawns a permanent `outbox-retry-worker` thread (consequence of R-H1) that keeps polling after `db.drop_all()` — a latent flakiness source.
- **R-M6. No migration ledger.** No table records which of the ~90 `migrations/*.py` ran in which environment (`grep class.*Migration` → nothing). `db.create_all()` auto-creates new *tables* everywhere but not new *columns*, so drift is masked and tracked only in human memory ("migration NOT YET RUN"). Add a tiny ledger + a startup model-vs-schema diff log.
- **R-M7.** Config failure modes are late and quiet — `config.py:22` hardcodes `load_dotenv('/Users/danielmcgarey/.../.env')`, so on any other checkout path every credential silently becomes `None` and fails later with obscure API errors rather than at boot. (Good: sandbox/prod DB URLs *do* raise if unset; unknown `ENVIRONMENT` defaults to local SQLite.)
- **R-M8. Dangerous exception-swallowing** (curated): `app/__init__.py:75-76` (Trello drainer failure logged as WARNING without `exc_info`, violating the project's own standard); bare `except:` at `app/trello/api.py:477` and `app/brain/job_log/routes.py:250,1299,1371,1847` (several `except: pass`); `app/brain/job_log/features/stage/command.py:420` swallows a list-resolution failure into `new_list_id=None`, silently skipping the Trello push — a lost outbound update with no ERROR.
- **R-M9.** Outbox has no ordering guarantee (no `ORDER BY`, retries reorder). Two rapid stage changes on one release can reach Trello out of order, leaving the shop-floor card on the wrong list until the next change.

### Low

- **R-L1.** ~42 committed data artifacts (CSV/XLSX/PDF/PKL), including customer correspondence PDFs — see also code-health H2.
- **R-L2.** CI is narrow — pytest+coverage (30% floor) and vitest on PRs only; no backend lint (no ruff/flake8), no logging-standard grep gate, and Render auto-deploy means a direct push to main bypasses the test gate entirely.
- **R-L3.** Logging drift — `drafting_work_load/routes.py:524-531` uses banned `%s`-style logger calls; `SyncContext` is dead but still exported and imported in `app/trello/sync.py:45` (never instantiated); no `request_id` correlation yet.
- **R-L4.** Dedup bucket-boundary edge — 15s/30s `time // window` buckets can double-process a boundary-straddling burst or drop a legitimate identical action within one bucket.

### Reliability — done well
The reconcile safety net (scheduled before dedup, coalescing, capped, with queryable "rescue" rows); DB-constraint dedup via `WebhookReceipt` unique-hash + `IntegrityError` rollback and `JobEventService` SAVEPOINTs; single-commit write path on the stage happy path; create-card idempotency on retry (adopts an existing same-title card — handles Trello's 5xx-but-created case); host-only credential logging; the incident-derived `migrations/README.md` + templates; the `TESTING=1` double guard; CI with a coverage regression gate; `TRELLO_MOCK` mode. Notably, the README's "known gap" tests now **exist** (webhook, sync-lock, auth, outbox, reconcile, undo) — the README is just stale.

---

## 4. Performance & efficiency

### High

- **P-H1. `release_events` / `submittal_events` have no indexes on their query columns** *(verified — `app/models.py:585-616` defines only a PK and a `payload_hash` unique constraint; `job`, `release`, `submittal_id`, `created_at`, `action` are all unindexed)*. These are the two grow-forever audit tables, queried on every history/events page (`/brain/events` orders by `created_at` + limit; `/api/.../history` filters `job`/`release` **with no limit**; monthly invoicing fetches *every* historical `update_stage` event). Today every such page gets linearly slower forever. **This is the single highest-leverage fix:** one idempotent migration adding `(job, release)`, `created_at`, `action` on `release_events` and `submittal_id`, `created_at` on `submittal_events`.
- **P-H2. `/brain/events/filters` loads every timestamp from both event tables into Python per page view** (`routes.py:2306-2325`) — full scan + per-row tz conversion just to populate a date dropdown. Push to `SELECT DISTINCT date(created_at AT TIME ZONE …)` or cache.
- **P-H3. The 30s poll (`/brain/jobs?since=`) runs `Releases.query.all()` on every poll, even zero-change ones** (`routes.py:606`) — hydrates every column of every release before the scheduling step early-returns. Every logged-in client fires this every 30s. The sibling `get-all-jobs` was already fixed with `with_entities(...)`; copy that here and skip the query when the delta is empty.
- **P-H4. ~40 Trello API calls have no `timeout=`** (`app/trello/api.py`, contrast Procore's 30s), and they run **inside the `sync_lock` and the singleton outbox daemon**. One hung socket freezes the entire Trello inbound pipeline / all outbound retries indefinitely (the lock's 60s timeout bounds acquisition, not the holder). Add `timeout=(5,30)` to every call.
- **P-H5. Scheduling recalc stamps `last_updated_at` on every formula-driven row unconditionally** (`scheduling/service.py:219-227`), before the "did anything change" check — so one fab-order edit dirties every FABRICATION row and, because the cursor poll filters on `last_updated_at`, forces every client to re-download the whole set. Only touch the row when computed values actually change.

### Medium

- **P-M1.** `gunicorn.conf.py` configures nothing but a log filter — no `workers`/`threads`. Defaults to 1 sync worker/1 thread unless Render overrides it; pin the intended shape (likely 1 worker + gthread `threads=N`).
- **P-M2.** Trello queue/lock/executor are per-process memory; multi-worker silently breaks draining, and the in-thread lock-acquisition failure path (`app/trello/__init__.py:179-192`) **drops** the event (the requeue that exists in the pre-check path is missing here).
- **P-M3.** Outbox/reconcile poll every 2s over unindexed (`status`, `next_retry_at`) columns on never-pruned tables — a growing sequential scan. Add a partial index and prune completed rows.
- **P-M4.** No pruning anywhere for append-only operational tables (`webhook_receipts` — whose own docstring says prune-able — `trello_outbox`, `procore_outbox`, `sync_operations/logs`, `job_change_log`). Several are on hot paths.
- **P-M5.** `sort_list_by_fab_order` issues one Trello PUT per card, always, even when already ordered (`api.py:1272`) — a 50-card list is 51 sequential round trips (no timeout) inside the outbox worker. Diff and only move changed cards.
- **P-M6.** Frontend has no route-level code splitting (`App.jsx:19-33`, no `React.lazy`, no `manualChunks`) — `maplibre-gl` (~750KB), `pdfjs-dist` (~1MB+), and `jspdf` all ship in the single entry chunk every user downloads at login. Lazy-load them for a likely 50–70% initial-bundle cut.
- **P-M7.** Job Log rows aren't `React.memo`'d (`JobsTableRow.jsx` 1,462 lines, `TableRow.jsx` 835; mapped directly in `JobLogContent.jsx:272`), so every 30s poll merge re-renders every row across Job Log / PM Board / Timeline — a visible stall on the iPad-class hardware this app targets.
- **P-M8.** Meetings list N+1 — `Meeting.to_dict()` calls `self.items.count()` per meeting (`models.py:1446`), up to 101 queries per `list_meetings`, polled every 8s during live bots. Use a grouped-count subquery like the board route already does.

### Low
`json.dumps(job_data)` per row as throwaway "validation" (`routes.py:552,916`); `/brain/events` fetches then discards half; unindexable `ILIKE '%…%'` search (bounded by `limit(30)` today); deprecated `/gantt-data` still live; per-row mapping fallback in `api/helpers.py:367`; uploads read fully into memory (bounded by the 50MB cap); legacy `Job.query.all()`→pandas in `models.py:555` (verify it's dead).

### Performance — done well
The cursor/delta poll design with its matching composite index and hidden-tab pause; a shared `ReleasesContext` feeding three views from one store; the deliberate index migration for `releases`/`submittals` with a prod-safety playbook; batched lookups replacing N+1 where noticed (`_release_ids_with_drawings`, board `comment_counts`, invoicing bulk fetches); timeouts on Procore/Graph/Anthropic; sane pool config (`pool_pre_ping`, `pool_recycle=280`); capped search/notifications/events endpoints.

---

## 5. Code health & maintainability

### High

- **CH-H1. CLAUDE.md actively misleads on architecture.** `app/onedrive/` **does not exist** (removed in commit `4403227`), yet CLAUDE.md still claims `onedrive_bp` is registered and that APScheduler "polls an Excel file hourly" and the sync lock guards OneDrive — all false. Actual blueprints are `trello/procore/api/brain/auth/history/admin/lake` (CLAUDE.md omits `api_bp`/`lake_bp`, lists nonexistent `onedrive_bp`). Actual scheduled jobs are **6**, not 2 (adds `fc_pdf_retry`, `bb_mail_poll`, `checklist_due_scan`, `calendar_recall_poll`). This is the file agents and new contributors trust first. Update the Blueprints / Data flow / Background processing sections.
- **CH-H2. ~75 MB of one-off data artifacts committed to git** *(verified — `archive-fix.csv` is 39 MB; `banana-boy.png` 5 MB; `JL_Static_Ingestion.csv` 4.1 MB; `480-299-fc.pdf` 1.2 MB; `analysis/sync_log_events.pkl` 1.1 MB; ~16 `icons/*.png` at ~950 KB each; ~15 root CSVs + 3 xlsx; `.git` is 191 MB)*. Several contain live job data / customer correspondence. `git rm --cached` the one-offs, add `*.csv`/`*.xlsx` root ignore patterns (with explicit fixture exceptions), and move real source art out of the repo.

### Medium

- **CH-M1. ~2,600 lines of dead Python in `app/` proper** — `app/seed.py` (1,942 lines, self-declared `imported_by: []` and disabled; also the only stdlib-`logging` violation left), `app/combine.py` (imported only by dead seed), `app/users.py`, `app/ingest_jobsites.py` (never imported; uses `print()`), root `test_csv_preview.py` (tests dead code), `SyncContext` in `logging_config.py:128`, deprecated `/gantt-data` route, and orphaned `frontend/src/components/Sidebar.jsx`. Delete them.
- **CH-M2. Legacy `Job` model retirement is ~95% done but CLAUDE.md overstates its liveness** — no runtime code queries `Job` anymore (only one CLI cleanup script + three migration scripts); the advertised `from app.models import Job as Releases` alias appears nowhere. Finish the retirement or mark it script-only, and clean stale docstrings in `trello/api.py` / `job_log/routes.py` that still describe the old model.
- **CH-M3. `app/brain/job_log/routes.py` is a 3,660-line god module** that violates the repo's own feature-folder rule — `update_job_comp` (`:1392`) and `update_invoiced` (`:1491`), both cascade participants, plus CSV import and card-creation still live inline. Continue the established extraction. (Also: real logic living in package `__init__.py` files — `procore/__init__.py` 894, `history/__init__.py` 651 — makes imports side-effectful.)
- **CH-M4. Inconsistent error-response shape** — `{"error": …}` (47×) vs `{"success": False, …}` (63×) vs `{"message": …}`. A shared `app/route_utils.py` helper exists but is imported by only 3 modules. Pick one envelope and migrate ratchet-style.
- **CH-M5. Frontend bypasses its own service layer** — raw `fetch()` in ~14 components alongside the axios service layer (two error/credential idioms), and `axios.defaults.withCredentials = true` is set as a global mutation in 8+ separate service files. Create one configured axios instance.
- **CH-M6. No React error boundary anywhere** (zero `ErrorBoundary`/`componentDidCatch`) — a render throw in a 1,300-line page or the maplibre/pdfjs surfaces blanks the whole app. Add a top-level boundary + one around PDF/map views.
- **CH-M7. `requirements.txt` mixes concerns** — installs `alembic`/`Flask-Migrate`/`Mako` (unused — "there is no Alembic") and dev tools (`black`, `pytest`, `pylint`) into the prod image, while **missing `Pillow`** that `scripts/make_banana_urgency.py` imports (fails on a fresh env). Split `requirements-dev.txt`.
- **CH-M8. Thin, uneven test coverage relative to risk** — 59 test files; `app/brain` = 91 source files vs 22 tests; the two biggest/riskiest modules (`trello/api.py` 2,485 lines, `procore/procore.py` 2,050) are the least covered; `app/admin`/`app/history`/`app/microsoft` ≈ 1 test or none. Target the two sync giants for the next coverage ratchet.

### Low
11 timestamped `submittals_operations_analysis_*.md` + a pile of stale summary docs (`md.md`, `MAPPING_*`, `*_SUMMARY.md`) and 8 loose scripts at repo root (→ `docs/`/`scripts/` or delete); an orphan root `package-lock.json` with an empty packages map; `app/trello/logging.py` shadows the stdlib module name; `print()` confined to `app/*/scripts/` trees (widen the CLAUDE.md exemption wording or relocate); giant-but-coherent JSX (`JobsTableRow.jsx` owning 6 modals, `TableRow.jsx`'s 28-prop signature are the real extraction candidates).

### Code health — done well
The logging rebuild held (zero stdlib-logging/`app.logger` in runtime code, single `get_logger` idiom); CI is real (pytest+coverage+vitest, `live` LLM tests excluded by default); the feature-folder pattern is a genuinely good decomposition; a single `API_BASE_URL` with no scattered hosts; unusually good and *honest* `@milehigh-header` file docs (dead files admit `imported_by: []`); all frontend deps are used; backend deps fully pinned.

---

## 6. Recommended remediation order

**This week (security-critical):**
1. Rotate both Render DB passwords; replace hardcoded URLs with env lookups (C1).
2. Fix the first-login flow to require an out-of-band invite token (C2).
3. Add auth to `health-scan/update` + the webhook-admin endpoints; verify Trello/Procore/Recall webhook signatures (S-H1, S-H2).
4. Require `SECRET_KEY` (no default) and set `SESSION_COOKIE_SECURE`; fail prod boot on default `ADMIN_PIN` (S-M1, S-M2, R-H6).

**Next sprint (reliability + top perf):**
5. Gate the outbox worker to one process and claim atomically; add a stale-`processing` sweeper and a longer backoff ceiling + failed-item requeue (R-H1, R-H3, R-H4).
6. Ship the one index migration for `release_events` / `submittal_events` (P-H1).
7. Fix the 30s poll to use `with_entities` + empty-delta skip, and stop unconditionally stamping `last_updated_at` in scheduling recalc (P-H3, P-H5).
8. Add `timeout=` to all Trello calls (P-H4).
9. Prioritize the already-scoped durable `TrelloInbox` (R-H2).

**Backlog (hygiene + process):**
10. Purge the 75 MB of data artifacts from tracking + tighten `.gitignore` (CH-H2).
11. Correct CLAUDE.md (OneDrive, blueprints, scheduler jobs) and delete the ~2,600 lines of dead Python (CH-H1, CH-M1).
12. Add a migration ledger + startup schema-diff (R-M6); add lint + a logging-standard grep gate to CI (R-L2).
13. Give scripts a thread-free app factory and dry-run-by-default (R-H5).

---

*Generated by a four-agent parallel audit (security, performance, reliability, code-health). Every Critical and High finding above was re-verified against source before inclusion; line numbers reference the working tree at the audit date.*
